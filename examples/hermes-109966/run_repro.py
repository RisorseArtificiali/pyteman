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
import subprocess
import sys
import tempfile
import time


def _fail(msg: str) -> None:
    print(f"DRIVER-ERROR: {msg}")
    sys.exit(2)


WAL_INCIDENT_TYPES = frozenset({
    "DeletedWalGenerationError",
    "OperationalError",
})


def _read_holder_failure(fail_flag: str):
    """Read structured failure evidence written by the holder.

    Returns (is_incident, reason) where is_incident is True only for
    exception types that are known WAL-incident signatures, False for
    generic faults, and None when no failure was recorded.
    """
    if not os.path.exists(fail_flag):
        return None, ""
    try:
        with open(fail_flag, encoding="utf-8") as fh:
            info = json.load(fh)
        exc_type = info.get("type", "")
        reason = f"{exc_type}: {info.get('message', '')} (tick={info.get('tick', '?')})"
        return exc_type in WAL_INCIDENT_TYPES, reason
    except (json.JSONDecodeError, OSError, TypeError, AttributeError):
        return False, "fail_flag unreadable or not JSON"


def _read_heartbeat(path: str):
    """Read the heartbeat value, returning None when the file is absent,
    empty, or unreadable (holder died before writing or mid-atomic-replace)."""
    try:
        value = open(path, encoding="utf-8").read().strip()
        return value if value else None
    except OSError:
        return None


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

    sys.path.insert(0, repo)  # the REAL hermes code under test comes from here
    from hermes_state import DeletedWalGenerationError, SessionDB
    from hermes_state_dbfile import iter_deleted_sqlite_sidecar_holders

    here = os.path.dirname(os.path.abspath(__file__))
    home = tempfile.mkdtemp(prefix="h109966-")
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
    env = dict(os.environ)
    env["HERMES_HOME"] = home
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
    try:
        for _ in range(200):
            if os.path.exists(marker):
                break
            time.sleep(0.05)
        else:
            _fail("holder never became ready in 10s")

        # Synchronize on the pin: once the rule has fired, the holder is INSIDE
        # a stalled write window. The restarter gates each cycle on the next
        # firing record, so every close is asserted concurrent, not inferred.
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
        heartbeat_before = _read_heartbeat(heartbeat)
        time.sleep(1.0)
        heartbeat_after = _read_heartbeat(heartbeat)
        holder_writing = (heartbeat_before is not None
                          and heartbeat_after is not None
                          and heartbeat_after != heartbeat_before)
        holder_incident, holder_reason = _read_holder_failure(fail_flag)
        holder_alive = holder.poll() is None and holder_incident is None
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

        print(f"restarter_rc={restarter.returncode} windows_fired={windows}/{want_windows} "
              f"holder_alive={holder_alive} holder_writing={holder_writing}")
        print(f"deleted_sidecar_holders={len(holders)} fresh_opener_refused={fresh_refused}")
        if holder_reason:
            print(f"holder_failure={holder_reason}")

        if holders or fresh_refused or holder_incident is True:
            reason = "; ".join(filter(None, [
                f"holders={len(holders)}" if holders else "",
                "fresh_opener_refused" if fresh_refused else "",
                holder_reason if holder_incident else "",
            ]))
            verdict = "REPRODUCED"
        elif holder_incident is False:
            reason = f"holder failed with non-incident error: {holder_reason}"
            verdict = "INCONCLUSIVE"
        elif (restarter.returncode != 0 or windows != want_windows
              or not holder_alive or not holder_writing):
            parts = []
            if restarter.returncode != 0:
                parts.append(f"restarter_rc={restarter.returncode}")
            if windows != want_windows:
                parts.append(f"windows={windows}/{want_windows}")
            if not holder_alive:
                parts.append("holder_dead")
            if not holder_writing:
                parts.append("holder_not_writing")
            reason = "harness: " + ", ".join(parts)
            verdict = "INCONCLUSIVE"
        else:
            reason = ""
            verdict = "CLEAN"
        verdict_line = f"VERDICT: {verdict}"
        if reason:
            verdict_line += f" reason={reason}"
        print(verdict_line)

        if expected is not None and expected != verdict:
            print(f"EXPECTATION-MISMATCH: expected={expected} verdict={verdict}")
            sys.exit(1)
    finally:
        try:
            os.kill(holder.pid, signal.SIGKILL)
            holder.wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            pass
        if verdict == "CLEAN":
            shutil.rmtree(home, ignore_errors=True)
        else:
            print(f"SCRATCH-HOME-PRESERVED: {home}")


if __name__ == "__main__":
    main()
