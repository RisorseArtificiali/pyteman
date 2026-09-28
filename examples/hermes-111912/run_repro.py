"""Driver for the NousResearch/hermes-agent#111912 repro.

Runs the REAL upstream kill sequence (hermes_cli.dashboard_procs._kill_pids_posix)
and the REAL deleted-WAL generation guard (hermes_state_dbfile.refuse_deleted_wal_generation)
against a pyteman-pinned process tree, so the race is an asserted interleaving
instead of a timing lottery.

Usage (Linux only; the upstream holder scan reads /proc and is a no-op elsewhere,
which the platform gate below turns into a hard failure rather than a vacuous
CLEAN):

    python3 run_repro.py <hermes-agent checkout> <ruleset.yaml> [expected-verdict]

The optional expected verdict (REPRODUCED or CLEAN) makes drift loud: exit code
0 only when the run's verdict matches, so a scenario that stops discriminating
after an upstream change fails instead of reading as a pass. Evidence lines are
stable tokens (no PIDs, no embedded spaces) for CI grepping.
"""
import json
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time


def _sha256_file(path):
    """The file's digest, or the reason it could not be read."""
    import hashlib
    try:
        return hashlib.sha256(
            open(path, "rb").read()).hexdigest()
    except OSError as exc:
        return f"unreadable ({exc!r})"


def _git_rev(repo):
    """The checkout's HEAD, or the honest marker when it is not a repo.

    A non-repo is not an exception to git: rev-parse exits 128 with
    empty stdout, so the empty string is folded into the marker rather
    than written as provenance that reads like a stripped value.
    """
    try:
        rev = subprocess.run(
            ["git", "-C", repo, "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        rev = ""
    return rev or "not-a-git-checkout"


EXIT_OK = 0            # a verdict was reached and matched (or none was asked)
EXIT_MISMATCH = 1      # the run answered, not what the caller expected
EXIT_DRIVER_ERROR = 2  # _fail: the harness itself could not run
EXIT_INCONCLUSIVE = 3  # the harness could not answer; never a success


def _fail(msg: str) -> None:
    print(f"DRIVER-ERROR: {msg}")
    sys.exit(EXIT_DRIVER_ERROR)


class _TreeHandle:
    """Every process this driver creates, killable as one unit on any exit.

    The parent is spawned as its own session, so the whole tree (the
    dashboard parent and the ui-tui descendant it spawns) shares one
    process group whose id is the parent's pid, known the instant the
    spawn returns: no read-time lookup, which would race a parent
    already reaped or a pid already recycled. Cleanup signals that one
    captured group and nothing else, so no unrelated process sharing a
    name or a parent can ever be reached; SIGKILL is delivered to a
    SIGSTOPped process too, which is the case that used to leak a wedged
    orphan still holding the database fds.
    """

    def __init__(self):
        self.parent = None
        self.pgid = None
        self.child_pid = None

    def spawn(self, *popen_args, **popen_kwargs):
        self.parent = subprocess.Popen(
            *popen_args, start_new_session=True, **popen_kwargs)
        # A session leader's process group id is its own pid, set before
        # Popen returns: capturing it here is the whole safety story.
        self.pgid = self.parent.pid

    def kill(self):
        """SIGKILL the tree; return cleanup errors, never raise over one.

        Idempotent: a second call finds the group gone (ESRCH) and
        treats it as the success it is. The parent this driver owns is
        reaped; the descendant was reparented when its parent died and
        is reaped by whoever adopted it, so only its death is ensured
        here.
        """
        errors = []
        if self.pgid is not None:
            try:
                os.killpg(self.pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass  # the group is already gone: the goal, reached
            except OSError as exc:
                errors.append(f"killpg({self.pgid}) failed: {exc!r}")
        # Belt and braces for a descendant that left the group: the
        # example's children inherit it today, but a TUI that grabs a
        # controlling terminal plausibly sets its own session, and the
        # one child pid the driver learned is the only other address
        # cleanup may ever use. A child still IN the group is already
        # dead; signaling it again is the ESRCH no-op above.
        if self.child_pid is not None:
            try:
                os.kill(self.child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except OSError as exc:
                errors.append(f"kill({self.child_pid}) failed: {exc!r}")
        if self.parent is not None and self.parent.poll() is None:
            try:
                self.parent.wait(timeout=10)
            except subprocess.TimeoutExpired:
                errors.append(f"parent pid {self.parent.pid} did not die")
        return errors


def main():
    if not sys.platform.startswith("linux"):
        _fail("Linux only: the upstream holder scan and this driver's /proc probes "
              "are no-ops elsewhere, which would produce a vacuous CLEAN")
    if len(sys.argv) < 3:
        _fail("usage: run_repro.py <hermes-agent checkout> <ruleset.yaml> [expected-verdict]")
    repo, ruleset = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
    expected = sys.argv[3] if len(sys.argv) > 3 else None
    # Validated BEFORE anything runs: a typo in the expectation would
    # otherwise surface only after the whole scenario has paid for it,
    # as a mismatch against a verdict that was never a candidate.
    if expected is not None and expected not in ("REPRODUCED", "CLEAN"):
        _fail(f"expected verdict must be REPRODUCED or CLEAN, "
              f"got {expected!r}")

    # Ambient pyteman activation would instrument THIS driver process
    # with rules nobody here chose, beside the pin this example sets for
    # its children: refuse clearly rather than run half-instrumented.
    for var in ("PYTEMAN_RULES", "PYTEMAN_LOG"):
        if os.environ.get(var):
            _fail(f"{var} is set in the ambient environment; an "
                  "instrumented driver is not this scenario. Unset it or "
                  "run from a clean shell")

    # The scratch home exists and is THIS process's Hermes home BEFORE
    # any upstream import, and the child env below carries it too: the
    # upstream tree resolves HERMES_HOME at import and at first use, so
    # leaving the operator's value in place would let both the driver
    # and the children read and write the OPERATOR's profile.
    here = os.path.dirname(os.path.abspath(__file__))
    home = tempfile.mkdtemp(prefix="h111912-")
    os.environ["HERMES_HOME"] = home

    sys.path.insert(0, repo)  # the REAL hermes code under test comes from here
    from hermes_cli.dashboard_procs import _kill_pids_posix
    from hermes_state import DeletedWalGenerationError
    from hermes_state_dbfile import iter_deleted_sqlite_sidecar_holders, refuse_deleted_wal_generation

    db = os.path.join(home, "state.db")
    firing_log = os.path.join(home, "pyteman.log")
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE t (x)")
    conn.commit()
    conn.close()

    ready = os.path.join(home, "child.ready")
    import pyteman
    # The children start from an environment with NO ambient pyteman
    # state at all, not from the operator's with two names overridden:
    # REQUIRE_MARKER, STRICT_* and anything added later ride a wholesale
    # copy and land as misattributed readiness failures (a missing
    # operator marker refuses the child at sitecustomize while the
    # driver reports a timeout). The rules and log this example chooses
    # are set explicitly below; nothing else pyteman-shaped comes in.
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("PYTEMAN_")}
    env["HERMES_HOME"] = home  # the children live in the scratch profile too
    env["PYTEMAN_RULES"] = ruleset
    env["PYTEMAN_LOG"] = firing_log  # firings land in the throwaway home, never the repo
    # sitecustomize.py lives inside the installed package dir; PYTHONPATH must
    # point AT that dir so the child interpreter picks the activation hook up.
    pkg_dir = os.path.dirname(os.path.abspath(pyteman.__file__))
    env["PYTHONPATH"] = pkg_dir + os.pathsep + env.get("PYTHONPATH", "")
    tree = _TreeHandle()
    # Everything from here to the end of main runs under one finally: an
    # upstream stop that raises, a failed scanner, a SQLite fault during
    # rotation or a readiness timeout all land in it, and the tree dies
    # on every exit rather than only the ones the old code anticipated.
    try:
        tree.spawn(
            [sys.executable, "-c",
             "import dashboard_sim; dashboard_sim.main()", db, ready],
            cwd=here, env=env,
        )
        for _ in range(200):
            if os.path.exists(ready):
                break
            time.sleep(0.05)
        else:
            # The finally does the killing: the WHOLE tree, not only the
            # parent this branch used to reach.
            _fail(f"child never became ready in 10s (ruleset={ruleset})")

        child_pid = int(open(ready, encoding="utf-8").read().strip())
        tree.child_pid = child_pid

        killed: list = []
        failed: list = []
        t0 = time.monotonic()
        _kill_pids_posix([tree.parent.pid], killed, failed)  # REAL upstream sequence
        elapsed = time.monotonic() - t0
        try:
            # -9 if SIGKILLed, 0 if it exited gracefully
            parent_rc = tree.parent.wait(timeout=10)
        except subprocess.TimeoutExpired:
            parent_rc = None
        orphan_alive = os.path.isdir(f"/proc/{child_pid}")
        if orphan_alive:
            # Freeze the orphan so the fd-hold is decoupled from the teardown
            # tail: the rotation below must not race the child's eventual
            # close(). The finally still SIGKILLs it: SIGKILL reaches a
            # SIGSTOPped process.
            try:
                os.kill(child_pid, signal.SIGSTOP)
            except OSError:
                pass

        # Rotate like a fresh Hermes instance would on clean handles:
        # checkpoint, drop the old sidecar paths (the orphan keeps the old
        # inode), mint a new WAL generation at the same path.
        conn = sqlite3.connect(db, timeout=10)
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
        for suffix in ("-wal", "-shm"):
            sidecar = db + suffix
            if os.path.exists(sidecar):
                os.unlink(sidecar)
        conn = sqlite3.connect(db, timeout=10)
        conn.execute("INSERT INTO t VALUES (1)")
        conn.commit()
        conn.close()

        # Evidence from the same scanner the guard uses, not a
        # reimplementation: drift between two scans would silently collapse
        # into one verdict.
        holders = iter_deleted_sqlite_sidecar_holders(db)
        child_holds = any(pid == child_pid for pid, _target in holders)

        guard, guard_exc = "clean", ""
        try:
            refuse_deleted_wal_generation(db)  # REAL upstream guard
        except DeletedWalGenerationError:
            guard, guard_exc = "FATAL", "DeletedWalGenerationError"
        except Exception as exc:  # never counted as a reproduction
            guard, guard_exc = "ERROR", type(exc).__name__

        # The pin must have engaged, or the run proves nothing: without a
        # firing record a silently-unpinned child looks exactly like a fixed
        # build.
        pin_engaged = _rule_fired(firing_log, ruleset)

        print(f"kill_elapsed_s={elapsed:.2f} parent_rc={parent_rc} "
              f"killed_n={len(killed)} failed_n={len(failed)}")
        print(f"child_orphan_alive={orphan_alive} "
              f"deleted_sidecar_holders={len(holders)} "
              f"child_holds_deleted_sidecar={child_holds} "
              f"pin_engaged={pin_engaged}")
        print(f"guard={guard} guard_exc={guard_exc}")

        if (guard == "FATAL" and parent_rc == -signal.SIGKILL
                and pin_engaged and child_holds):
            verdict = "REPRODUCED"
            reason = (f"guard FATAL ({guard_exc}), parent SIGKILLed, "
                      f"pin engaged, child holds the deleted sidecar")
        elif (guard == "clean" and parent_rc == 0 and not orphan_alive
                and pin_engaged):
            verdict = "CLEAN"
            reason = "guard clean, parent exited gracefully, no orphan"
        else:
            verdict = "INCONCLUSIVE"
            why = []
            if guard == "ERROR":
                why.append(f"guard raised {guard_exc}")
            if parent_rc is None:
                why.append("parent did not die within 10s")
            elif parent_rc not in (0, -signal.SIGKILL):
                why.append(f"parent rc {parent_rc}")
            if not pin_engaged:
                why.append("pin never engaged")
            if guard != "FATAL" and not child_holds and orphan_alive:
                why.append("orphan alive but holds nothing")
            reason = ("harness fault: " + "; ".join(why)
                      if why else "conditions for neither verdict held")
        print(f"VERDICT: {verdict}")
        print(f"REASON: {reason}")

        # The durable verdict: a manifest in the scratch home, written
        # BEFORE any preservation decision, so every outcome that keeps
        # the home keeps the diagnosis inside it (AC #2). Provenance is
        # captured here because the home is the one place a later reader
        # is guaranteed to look.
        manifest = {
            "verdict": verdict,
            "reason": reason,
            "expected": expected,
            "evidence": {
                "kill_elapsed_s": round(elapsed, 3),
                "parent_rc": parent_rc,
                "child_orphan_alive": orphan_alive,
                "deleted_sidecar_holders": len(holders),
                "child_holds_deleted_sidecar": child_holds,
                "pin_engaged": pin_engaged,
                "guard": guard,
                "guard_exc": guard_exc,
                "killed": list(killed),
                "failed": [repr(f) for f in failed],
            },
            "provenance": {
                "ruleset": ruleset,
                "ruleset_sha256": _sha256_file(ruleset),
                "upstream_checkout": repo,
                "upstream_revision": _git_rev(repo),
                "python": sys.version.split()[0],
                "sqlite": sqlite3.sqlite_version,
                "platform": sys.platform,
                "argv": sys.argv[1:],
            },
        }
        with open(os.path.join(home, "manifest.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=1, sort_keys=True)
            fh.write("\n")

        # The tree dies before any preservation decision touches the
        # home, so no fd outlives the evidence it belongs to (EX-02's
        # cleanup is never impeded by conservation); kill() is
        # idempotent, so the finally's second call after the normal
        # path lands as ESRCH and does nothing.
        tree.kill()

        # The home survives every outcome except an unambiguous CLEAN:
        # a mismatch keeps it (the diagnosis must exist to be read, AC
        # #2), and INCONCLUSIVE keeps it (the harness fault is the one
        # outcome whose postmortem needs the most context).
        matched = expected is None or expected == verdict
        keep_home = not (verdict == "CLEAN" and matched)
        if keep_home:
            print(f"SCRATCH-HOME-PRESERVED: {home}")
        else:
            shutil.rmtree(home, ignore_errors=True)

        # INCONCLUSIVE is never a success: without an expectation it
        # used to fall off main with exit 0, indistinguishable from a
        # clean answer to whatever grepped the code.
        if not matched:
            print(f"EXPECTATION-MISMATCH: expected={expected} verdict={verdict}")
            sys.exit(EXIT_MISMATCH)
        if verdict == "INCONCLUSIVE":
            sys.exit(EXIT_INCONCLUSIVE)
        sys.exit(EXIT_OK)
    finally:
        # Every exit, including the ones nobody planned: an upstream stop
        # that raised, a failed scanner, a rotation fault, a readiness
        # timeout. Cleanup failures are OBSERVED, never raised over an
        # exception already on its way out.
        for err in tree.kill():
            print(f"CLEANUP-ERROR: {err}")


def _rule_fired(firing_log: str, ruleset: str) -> bool:
    """True when one of the ruleset's rules actually fired in the child.

    Records carry the rule id (not the point). Each firing writes a
    ``phase: start`` record, which proves an attempt and nothing more, and a
    ``phase: end`` terminal record carrying the ``status``; the two are joined
    by ``attempt``. A skipped or failed attempt is not a firing, so the start
    records whose terminal reports one of those are excluded. A start with no
    terminal at all is an unknown outcome, and this driver counts it as fired
    only if nothing says otherwise, which is the same reading the rest of the
    scenario uses for a child that was killed mid-action.
    """
    import json

    import yaml  # pyteman's own dependency

    try:
        rule_ids = {r["id"] for r in yaml.safe_load(open(ruleset, encoding="utf-8"))}
    except Exception:
        return False
    if not rule_ids or not os.path.exists(firing_log):
        return False
    # The statuses that say the attempt did NOT take effect. This
    # classification is PERMISSIVE by construction: an unrecognised status is
    # simply absent from `refuting`, so its attempt stays in
    # `started - refuted` and is counted as a firing, and `pin_engaged` then
    # reads True for a run whose pin may have taken no effect at all. Nothing
    # here fails, warns, or skips when that happens. The set used to be
    # written out by hand here, which made every status added to actions.py a
    # silent over-report until someone remembered this line; CFG-04 added two.
    # It is imported instead, so a status that means "did not take effect"
    # arrives by being defined where it is produced. `pragma_unknown` is in
    # it: an unverifiable pragma is not an engaged one. `failed` is unioned in
    # here rather than imported, because it is the generic action-level status
    # and belongs to no single action kind. The import is function-local to
    # match this file's convention: `yaml` and `pyteman` are too.
    from pyteman.pragmas import REFUTING
    refuting = REFUTING | {"failed"}
    started, refuted = set(), set()
    for line in open(firing_log, encoding="utf-8", errors="replace"):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("rule") not in rule_ids:
            continue
        key = (rec.get("instance"), rec.get("pid"), rec.get("attempt"))
        if rec.get("phase") == "start":
            started.add(key)
        elif rec.get("status") in refuting:
            refuted.add(key)
    return bool(started - refuted)


if __name__ == "__main__":
    main()
