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


def main():
    if not sys.platform.startswith("linux"):
        _fail("Linux only: the upstream holder scan and this driver's /proc probes "
              "are no-ops elsewhere, which would produce a vacuous CLEAN")
    if len(sys.argv) < 3:
        _fail("usage: run_repro.py <hermes-agent checkout> <ruleset.yaml> [expected-verdict]")
    repo, ruleset = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
    expected = sys.argv[3] if len(sys.argv) > 3 else None

    sys.path.insert(0, repo)  # the REAL hermes code under test comes from here
    from hermes_cli.dashboard_procs import _kill_pids_posix
    from hermes_state import DeletedWalGenerationError
    from hermes_state_dbfile import iter_deleted_sqlite_sidecar_holders, refuse_deleted_wal_generation

    here = os.path.dirname(os.path.abspath(__file__))
    home = tempfile.mkdtemp(prefix="h111912-")
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
    )
    for _ in range(200):
        if os.path.exists(ready):
            break
        time.sleep(0.05)
    else:
        for pid in (parent.pid,):
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        _fail(f"child never became ready in 10s (ruleset={ruleset}); the tree was killed")

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

    # The pin must have engaged, or the run proves nothing: without a firing
    # record a silently-unpinned child looks exactly like a fixed build.
    pin_engaged = _rule_fired(firing_log, ruleset)

    print(f"kill_elapsed_s={elapsed:.2f} parent_rc={parent_rc} killed_n={len(killed)} failed_n={len(failed)}")
    print(f"child_orphan_alive={orphan_alive} deleted_sidecar_holders={len(holders)} "
          f"child_holds_deleted_sidecar={child_holds} pin_engaged={pin_engaged}")
    print(f"guard={guard} guard_exc={guard_exc}")

    if guard == "FATAL" and parent_rc == -signal.SIGKILL and pin_engaged and child_holds:
        verdict = "REPRODUCED"
    elif guard == "clean" and parent_rc == 0 and not orphan_alive and pin_engaged:
        verdict = "CLEAN"
    else:
        verdict = "INCONCLUSIVE"
    print(f"VERDICT: {verdict}")

    # Kill (not reap: the orphan was reparented, only its new parent can reap it)
    # the possibly-wedged child, then drop the throwaway home.
    if os.path.isdir(f"/proc/{child_pid}"):
        try:
            os.kill(child_pid, signal.SIGKILL)
        except OSError:
            pass
    shutil.rmtree(home, ignore_errors=True)

    if expected is not None and expected != verdict:
        print(f"EXPECTATION-MISMATCH: expected={expected} verdict={verdict}")
        sys.exit(1)


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
