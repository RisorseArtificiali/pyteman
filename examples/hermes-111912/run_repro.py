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

Exit codes:

    0  valid result (or expected verdict matched)
    1  expectation mismatch (expected given but verdict differs)
    2  driver error (bad arguments, platform, timeout)
    3  inconclusive without expected verdict (harness fault, not a real result)

A verdict.json manifest is written to the scratch home with the full evidence
dictionary, so postmortem tools can parse the result without grepping stdout.
The scratch home is preserved on any non-CLEAN outcome for postmortem.
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


def _fail(msg: str) -> None:
    print(f"DRIVER-ERROR: {msg}")
    sys.exit(2)


def _resolve_exit_code(verdict, expected):
    if expected is not None and expected != verdict:
        return 1
    if verdict == "INCONCLUSIVE" and expected is None:
        return 3
    return 0


def _kill_tree(pgid: int, parent: subprocess.Popen) -> None:
    """Kill the entire process group and reap the direct child.

    The group was created by start_new_session=True on the parent Popen, and
    pgid == parent.pid is captured at spawn time, before any race with reap
    or PID reuse can invalidate it. Descendants inherit the group unless they
    start their own session, so killpg reaches the full tree. ESRCH is benign:
    the group is already gone. The parent.wait reaps the zombie from our own
    process table; the orphaned descendant was reparented and is not ours to
    reap, but killpg already stopped it.
    """
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        parent.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def main():
    if not sys.platform.startswith("linux"):
        _fail("Linux only: the upstream holder scan and this driver's /proc probes "
              "are no-ops elsewhere, which would produce a vacuous CLEAN")
    if len(sys.argv) < 3:
        _fail("usage: run_repro.py <hermes-agent checkout> <ruleset.yaml> [expected-verdict]")
    repo, ruleset = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
    expected = sys.argv[3] if len(sys.argv) > 3 else None

    here = os.path.dirname(os.path.abspath(__file__))
    home = tempfile.mkdtemp(prefix="h111912-")
    # Isolate the driver process from the operator's Hermes profile before
    # importing any hermes module. hermes_state evaluates
    # DEFAULT_DB_PATH = get_hermes_home() / "state.db" at module scope;
    # without this, the driver's own hermes imports bind to the operator's
    # HERMES_HOME, and child processes inherit the operator's profile.
    os.environ["HERMES_HOME"] = home

    sys.path.insert(0, repo)  # the REAL hermes code under test comes from here
    try:
        from hermes_cli.dashboard_procs import _kill_pids_posix
        from hermes_state import DeletedWalGenerationError
        from hermes_state_dbfile import iter_deleted_sqlite_sidecar_holders, refuse_deleted_wal_generation
    except ImportError as exc:
        _fail(
            f"cannot import from hermes-agent checkout ({repo}): {exc}\n"
            "  Tested revisions: 5910de20bc (base), 6602939a4f (PR #112069 head)\n"
            "  Required: hermes_cli.dashboard_procs (_kill_pids_posix),\n"
            "            hermes_state (DeletedWalGenerationError),\n"
            "            hermes_state_dbfile (iter_deleted_sqlite_sidecar_holders,\n"
            "                                 refuse_deleted_wal_generation)\n"
            "  Verify the checkout path and that its modules are importable."
        )

    db = os.path.join(home, "state.db")
    firing_log = os.path.join(home, "pyteman.log")
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE t (x)")
    conn.commit()
    conn.close()

    ready = os.path.join(home, "child.ready")
    import pyteman
    env = dict(os.environ)
    env["PYTEMAN_RULES"] = ruleset
    env["PYTEMAN_LOG"] = firing_log  # firings land in the throwaway home, never the repo
    # sitecustomize.py lives inside the installed package dir; PYTHONPATH must
    # point AT that dir so the child interpreter picks the activation hook up.
    pkg_dir = os.path.dirname(os.path.abspath(pyteman.__file__))
    env["PYTHONPATH"] = pkg_dir + os.pathsep + env.get("PYTHONPATH", "")
    parent = subprocess.Popen(
        [sys.executable, "-c", "import dashboard_sim; dashboard_sim.main()", db, ready],
        cwd=here, env=env,
        start_new_session=True,
    )
    pgid = parent.pid
    verdict = None
    try:
        for _ in range(200):
            if os.path.exists(ready):
                break
            time.sleep(0.05)
        else:
            _fail(f"child never became ready in 10s (ruleset={ruleset})")

        child_pid = int(open(ready, encoding="utf-8").read().strip())

        killed: list = []
        failed: list = []
        t0 = time.monotonic()
        _kill_pids_posix([parent.pid], killed, failed)  # REAL upstream sequence
        elapsed = time.monotonic() - t0
        try:
            parent_rc = parent.wait(timeout=10)  # -9 if SIGKILLed, 0 if it exited gracefully
        except subprocess.TimeoutExpired:
            parent_rc = None
        orphan_alive = os.path.isdir(f"/proc/{child_pid}")
        if orphan_alive:
            # Freeze the orphan so the fd-hold is decoupled from the teardown tail:
            # the rotation below must not race the child's eventual close().
            try:
                os.kill(child_pid, signal.SIGSTOP)
            except OSError:
                pass

        # Rotate like a fresh Hermes instance would on clean handles: checkpoint,
        # drop the old sidecar paths (the orphan keeps the old inode), mint a new
        # WAL generation at the same path.
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

        # Evidence from the same scanner the guard uses, not a reimplementation:
        # drift between two scans would silently collapse into one verdict.
        holders = iter_deleted_sqlite_sidecar_holders(db)
        child_holds = any(pid == child_pid for pid, _target in holders)

        guard, guard_exc = "clean", ""
        try:
            refuse_deleted_wal_generation(db)  # REAL upstream guard
        except DeletedWalGenerationError:
            guard, guard_exc = "FATAL", "DeletedWalGenerationError"
        except Exception as exc:  # never counted as a reproduction
            guard, guard_exc = "ERROR", type(exc).__name__

        pin_engaged = _rule_fired(firing_log, ruleset)

        print(f"kill_elapsed_s={elapsed:.2f} parent_rc={parent_rc} killed_n={len(killed)} failed_n={len(failed)}")
        print(f"child_orphan_alive={orphan_alive} deleted_sidecar_holders={len(holders)} "
              f"child_holds_deleted_sidecar={child_holds} pin_engaged={pin_engaged}")
        print(f"guard={guard} guard_exc={guard_exc}")

        if guard == "FATAL" and parent_rc == -signal.SIGKILL and pin_engaged and child_holds:
            verdict = "REPRODUCED"
            reason = "guard FATAL, orphan holds deleted sidecar"
        elif guard == "clean" and parent_rc == 0 and not orphan_alive and pin_engaged:
            verdict = "CLEAN"
            reason = ""
        else:
            verdict = "INCONCLUSIVE"
            parts = []
            if guard == "ERROR":
                parts.append(f"guard={guard}({guard_exc})")
            if not pin_engaged:
                parts.append("pin_not_engaged")
            if parent_rc not in (-signal.SIGKILL, 0, None):
                parts.append(f"parent_rc={parent_rc}")
            reason = "; ".join(parts) if parts else "indeterminate"

        verdict_line = f"VERDICT: {verdict}"
        if reason:
            verdict_line += f" reason={reason}"
        print(verdict_line)

        exit_code = _resolve_exit_code(verdict, expected)
        manifest = {
            "verdict": verdict,
            "reason": reason,
            "expected": expected,
            "exit_code": exit_code,
            "evidence": {
                "kill_elapsed_s": round(elapsed, 2),
                "parent_rc": parent_rc,
                "killed_n": len(killed),
                "failed_n": len(failed),
                "orphan_alive": orphan_alive,
                "deleted_sidecar_holders": len(holders),
                "child_holds_deleted_sidecar": child_holds,
                "guard": guard,
                "guard_exc": guard_exc,
                "pin_engaged": pin_engaged,
            },
        }
        with open(os.path.join(home, "verdict.json"), "w", encoding="utf-8") as mf:
            json.dump(manifest, mf, indent=2)
            mf.write("\n")
        if exit_code == 1:
            print(f"EXPECTATION-MISMATCH: expected={expected} verdict={verdict}")
        if exit_code != 0:
            sys.exit(exit_code)
    finally:
        _kill_tree(pgid, parent)
        if verdict == "CLEAN":
            shutil.rmtree(home, ignore_errors=True)
        else:
            print(f"SCRATCH-HOME-PRESERVED: {home}")


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
    # match this file's convention: `json`, `yaml` and `pyteman` are too.
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
