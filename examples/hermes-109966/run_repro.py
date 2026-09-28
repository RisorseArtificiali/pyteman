"""Driver for the NousResearch/hermes-agent#109966 confirmation.

Answers the wave's open question (does the WAL handoff chain still reproduce
on a current tip?) with real upstream code and a pinned interleaving: a
long-lived holder writes through a real SessionDB while a restart-shaped
sibling opens, writes and closes INSIDE the holder's stalled write windows
(a when-gated always rule stalls the first three append_message calls), which
is the concurrent version of what tests/hermes_state/test_wal_lock_guard.py
covers sequentially.

Usage (Linux only; the holder scan reads /proc):

    python3 run_repro.py <hermes-agent checkout> [expected-verdict]

CLEAN means the incident's signatures are absent: no process holds a deleted
sidecar generation, a fresh SessionDB opens and writes, and the holder kept
writing. REPRODUCED means an incident signature appeared. INCONCLUSIVE means
a harness fault (pin, choreography or process health), never counted as
either. The optional expected verdict makes drift loud via the exit code; the
scratch home is preserved on any non-CLEAN outcome for postmortem.
"""
import json
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time


EXIT_OK = 0            # a verdict was reached and matched (or none was asked)
EXIT_MISMATCH = 1      # the run answered, not what the caller expected
EXIT_DRIVER_ERROR = 2  # _fail: the harness itself could not run
EXIT_INCONCLUSIVE = 3  # the harness could not answer; never a success


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


def _fail(msg: str) -> None:
    print(f"DRIVER-ERROR: {msg}")
    sys.exit(EXIT_DRIVER_ERROR)


def _read_heartbeat(path):
    """The heartbeat, or None with a reason the verdict can name.

    Absent, empty and unreadable are three different facts about the
    holder's liveness, and none of them may crash the driver: a verdict
    must always print, because an aborted run with no verdict line is
    indistinguishable from a hung one to whatever greps the output.
    """
    try:
        content = open(path, encoding="utf-8").read().strip()
    except FileNotFoundError:
        return None, "absent"
    except (OSError, ValueError) as exc:
        # ValueError widens the net past OSError deliberately: bytes the
        # decoding cannot read raise UnicodeDecodeError, a ValueError,
        # and a heartbeat nobody can decode is a fact to NAME, not a
        # crash that eats the verdict.
        return None, f"unreadable ({exc!r})"
    if not content:
        return None, "empty"
    return content, ""


def _holder_failure(path):
    """The holder's structured failure evidence, classified.

    Returns ``(is_incident, description)``: the WAL-generation refusal is
    the incident under test, so it is the one error type that may feed
    REPRODUCED; every other error, and an unparsable flag, is a fault of
    this run and reads as INCONCLUSIVE with the diagnostic named.
    """
    try:
        evidence = json.loads(open(path, encoding="utf-8").read())
        if not isinstance(evidence, dict):
            return False, ("holder failed with unparsable evidence "
                           f"(JSON {type(evidence).__name__}, not an object)")
        error_type = evidence.get("error_type", "")
    except (OSError, ValueError) as exc:
        return False, f"holder failed with unparsable evidence ({exc!r})"
    where = (f"phase {evidence.get('phase', '?')} "
             f"tick {evidence.get('tick', '?')}")
    # The fresh-opener probe accepts SUBCLASSES of the refusal (an
    # except clause does), so the flag classification must too or the
    # two doors disagree about the same incident: the holder failing
    # with a subclass would read here as a fault unrelated to the WAL
    # generation. The recorded name is resolved against the driver's
    # own hermes_state import; an unknown name means evidence from a
    # holder this driver does not understand, which is a fault, not an
    # incident.
    incident = False
    if error_type and "hermes_state" in sys.modules:
        refusal = sys.modules["hermes_state"].DeletedWalGenerationError
        candidate = getattr(sys.modules["hermes_state"], error_type, None)
        incident = (candidate is not None
                    and isinstance(candidate, type)
                    and issubclass(candidate, refusal))
    if incident:
        return True, f"holder hit the WAL-generation refusal ({where})"
    return False, (f"holder fault unrelated to the WAL generation "
                   f"({error_type or 'unknown type'} at {where})")


def _fired_count(firing_log: str) -> int:
    """Count the write windows opened so far, one per firing of the rule.

    Every firing writes a ``phase: start`` record before the action and a
    ``phase: end`` terminal record after it, so only the start records are
    counted here; a terminal is the same firing finishing, not another one.
    """
    if not os.path.exists(firing_log):
        return 0
    n = 0
    for line in open(firing_log, encoding="utf-8", errors="replace"):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("rule") == "hold-write-window" and rec.get("phase") == "start":
            n += 1
    return n


def _expected_windows(ruleset: str) -> int:
    """Derive the window count from the rule's ``when: fires <= N`` gate, so a
    rules edit that desyncs the scenario from the driver fails loudly."""
    import yaml

    for rule in yaml.safe_load(open(ruleset, encoding="utf-8")):
        m = re.search(r"fires\s*<=\s*(\d+)", str(rule.get("when", "")))
        if m:
            return int(m.group(1))
    _fail(f"ruleset {ruleset} lacks a 'when: fires <= N' gate to derive windows from")


def main():
    if not sys.platform.startswith("linux"):
        _fail("Linux only: the upstream holder scan and this driver's /proc probes "
              "are no-ops elsewhere, which would produce a vacuous CLEAN")
    if len(sys.argv) < 2:
        _fail("usage: run_repro.py <hermes-agent checkout> [expected-verdict]")
    repo = os.path.abspath(sys.argv[1])
    expected = sys.argv[2] if len(sys.argv) > 2 else None
    # Validated BEFORE anything runs: a typo in the expectation would
    # otherwise surface only after the whole scenario has paid for it,
    # as a mismatch against a verdict that was never a candidate.
    if expected is not None and expected not in ("REPRODUCED", "CLEAN"):
        _fail(f"expected verdict must be REPRODUCED or CLEAN, "
              f"got {expected!r}")

    # Ambient pyteman activation would instrument THIS driver process
    # with rules nobody here chose, beside the ones this example sets for
    # its children: refuse clearly rather than run half-instrumented.
    for var in ("PYTEMAN_RULES", "PYTEMAN_LOG"):
        if os.environ.get(var):
            _fail(f"{var} is set in the ambient environment; an "
                  "instrumented driver is not this scenario. Unset it or "
                  "run from a clean shell")

    # The scratch home exists and is THIS process's Hermes home BEFORE
    # any upstream import: hermes resolves HERMES_HOME at import and at
    # first use, so importing first would read (and write: the profile
    # tree, the config) the OPERATOR's home. The child env below carries
    # the same scratch.
    here = os.path.dirname(os.path.abspath(__file__))
    home = tempfile.mkdtemp(prefix="h109966-")
    os.environ["HERMES_HOME"] = home

    sys.path.insert(0, repo)  # the REAL hermes code under test comes from here
    from hermes_state import DeletedWalGenerationError, SessionDB
    from hermes_state_dbfile import iter_deleted_sqlite_sidecar_holders

    ruleset = os.path.join(here, "rules-hold-write-window.yaml")
    want_windows = _expected_windows(ruleset)
    db_path = os.path.join(home, "state.db")
    marker = os.path.join(home, "holder.ready")
    heartbeat = os.path.join(home, "holder.heartbeat")
    fail_flag = os.path.join(home, "holder.failed")
    firing_log = os.path.join(home, "pyteman.log")
    # Pin the journal mode and isolate from the operator's ambient config.
    with open(os.path.join(home, "config.yaml"), "w", encoding="utf-8") as fh:
        fh.write("database:\n  journal_mode: wal\n")

    from pathlib import Path
    seed = SessionDB(db_path=Path(db_path))
    seed.create_session("holder", "cli")
    seed.create_session("restarter", "cli")
    seed.append_message("holder", role="user", content="seed")
    seed.close()

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
    env["HERMES_HOME"] = home  # same scratch this driver already uses
    env["PYTEMAN_RULES"] = ruleset
    env["PYTEMAN_LOG"] = firing_log
    pkg_dir = os.path.dirname(os.path.abspath(pyteman.__file__))
    env["PYTHONPATH"] = pkg_dir + os.pathsep + repo + os.pathsep + env.get("PYTHONPATH", "")
    holder = subprocess.Popen(
        [sys.executable, "-c", "import holder; holder.main()",
         db_path, marker, heartbeat, fail_flag],
        cwd=here, env=env,
    )
    verdict = "INCONCLUSIVE"
    # Bound BEFORE the try: the finally reads it, and the window between
    # a reached verdict and the matched assignment (the manifest write)
    # must not turn a crash into an UnboundLocalError that masks the
    # original error and skips the preservation report.
    matched = False
    try:
        for _ in range(200):
            if os.path.exists(marker):
                break
            time.sleep(0.05)
        else:
            _fail("holder never became ready in 10s")

        # Synchronize on the pin: once the rule has fired, the holder is INSIDE
        # a stalled write window. The restarter asserts each close against
        # BOTH edges of its window, read from the firing log the rule itself
        # writes: it refuses to close a window whose end record is already
        # on disk, and refuses the run when a window never opens. Its
        # nonzero exit therefore reaches the INCONCLUSIVE below, never
        # CLEAN: a count total cannot certify what the per-window
        # choreography did not.
        for _ in range(200):
            if _fired_count(firing_log) >= 1:
                break
            time.sleep(0.05)
        else:
            _fail("pin never engaged (no firing record); cannot assert anything")

        r_env = {k: v for k, v in env.items() if k != "PYTEMAN_RULES"}  # pin only the holder
        try:
            restarter = subprocess.run(
                [sys.executable, "-c", "import restarter; restarter.main()",
                 db_path, str(want_windows), firing_log],
                cwd=here, env=r_env, timeout=120,
            )
        except subprocess.TimeoutExpired:
            _fail("restarter hung; scratch home preserved for postmortem")

        # Let every window fully pass; stop waiting if the holder dies.
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if _fired_count(firing_log) >= want_windows:
                break
            if holder.poll() is not None:
                break
            time.sleep(0.2)
        time.sleep(4.0)

        windows = _fired_count(firing_log)
        hb_before, hb_before_why = _read_heartbeat(heartbeat)
        time.sleep(1.0)
        hb_after, hb_after_why = _read_heartbeat(heartbeat)
        holder_writing = (hb_before is not None and hb_after is not None
                          and hb_after != hb_before)
        holder_alive = holder.poll() is None and not os.path.exists(fail_flag)
        holders = iter_deleted_sqlite_sidecar_holders(db_path)

        # The refusal happens in SessionDB construction, so the constructor
        # itself sits inside the try.
        fresh_refused = False
        fresh = None
        try:
            fresh = SessionDB(db_path=Path(db_path))
            fresh.append_message("restarter", role="user", content="fresh opener")
        except DeletedWalGenerationError:
            fresh_refused = True
        finally:
            if fresh is not None:
                fresh.close()

        # Heartbeat problems are named, never guessed: a None heartbeat
        # makes holder_writing False, and the reason rides the evidence
        # line so the operator reads WHICH liveness fact failed.
        hb_note = ""
        if hb_before is None or hb_after is None:
            hb_note = (f" heartbeat_before={hb_before_why or 'ok'}"
                       f" heartbeat_after={hb_after_why or 'ok'}")
        holder_incident, holder_why = (False, "")
        if os.path.exists(fail_flag):
            holder_incident, holder_why = _holder_failure(fail_flag)

        print(f"restarter_rc={restarter.returncode} windows_fired={windows}/{want_windows} "
              f"holder_alive={holder_alive} holder_writing={holder_writing}")
        print(f"deleted_sidecar_holders={len(holders)} fresh_opener_refused={fresh_refused}"
              f"{hb_note}")

        # Only explicit incident signatures may read as REPRODUCED: the
        # sidecar holders, the fresh opener's WAL refusal, or the holder
        # failing WITH the WAL-generation refusal. A fail flag holding any
        # other error is a fault of this run, not the incident, and the
        # reason line says which it was.
        signatures = []
        if holders:
            signatures.append(f"deleted sidecar holders: {len(holders)}")
        if fresh_refused:
            signatures.append("fresh opener refused (WAL generation)")
        if holder_incident:
            signatures.append(holder_why)
        # Built BEFORE the branch that consumes it, so the printed
        # reason and the branch condition cannot drift apart when a
        # fault kind is added.
        faults = []
        if restarter.returncode != 0:
            faults.append(f"restarter rc {restarter.returncode}")
        if windows != want_windows:
            faults.append(f"windows {windows}/{want_windows}")
        if not holder_alive:
            faults.append("holder not alive")
        if not holder_writing:
            why = hb_before_why or hb_after_why
            faults.append("holder not writing" + (f" ({why})" if why else ""))
        if signatures:
            verdict = "REPRODUCED"
            reason = "; ".join(signatures)
        elif os.path.exists(fail_flag):
            verdict = "INCONCLUSIVE"
            reason = f"harness fault: {holder_why}"
        elif faults:
            verdict = "INCONCLUSIVE"  # harness fault, never a durable answer
            reason = "harness fault: " + "; ".join(faults)
        else:
            verdict = "CLEAN"
            reason = "all incident signatures absent, choreography complete"
        print(f"VERDICT: {verdict}")
        print(f"REASON: {reason}")

        # The durable verdict: a manifest in the scratch home, written
        # BEFORE the preservation decision, so the mismatch's diagnosis
        # exists even on the one mismatch path that used to rmtree
        # first (a CLEAN answer against expectation REPRODUCED).
        manifest = {
            "verdict": verdict,
            "reason": reason,
            "expected": expected,
            "evidence": {
                "restarter_rc": restarter.returncode,
                "windows_fired": windows,
                "windows_wanted": want_windows,
                "holder_alive": holder_alive,
                "holder_writing": holder_writing,
                "deleted_sidecar_holders": len(holders),
                "fresh_opener_refused": fresh_refused,
                "heartbeat_before": hb_before_why or hb_before,
                "heartbeat_after": hb_after_why or hb_after,
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

        # INCONCLUSIVE is never a success: without an expectation it
        # used to fall off main with exit 0, and a matched expectation
        # kept the home on a verdict the caller never asked to match.
        matched = expected is None or expected == verdict
        exit_code = (EXIT_MISMATCH if not matched
                     else EXIT_INCONCLUSIVE if verdict == "INCONCLUSIVE"
                     else EXIT_OK)
    finally:
        try:
            os.kill(holder.pid, signal.SIGKILL)
            holder.wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            pass
        # The home survives every outcome except an unambiguous CLEAN:
        # mismatches keep the diagnosis (AC #2), INCONCLUSIVE keeps the
        # postmortem, and the process cleanup above has already run, so
        # conservation never impedes EX-02.
        if verdict == "CLEAN" and matched:
            shutil.rmtree(home, ignore_errors=True)
        else:
            print(f"SCRATCH-HOME-PRESERVED: {home}")
    if not matched:
        print(f"EXPECTATION-MISMATCH: expected={expected} verdict={verdict}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
