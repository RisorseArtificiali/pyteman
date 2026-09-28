# tests/test_example_driver_isolation.py
"""The example drivers isolate their whole process tree's Hermes profile.

The audit (TASK-28 / EX-03): both drivers imported the upstream Hermes
code and constructed SessionDBs for seeding while the process still
pointed wherever the operator pointed it, so the DRIVER process read and
wrote the OPERATOR's profile; on the pinned upstream tip this created the
operator's entire home tree and overwrote its config.yaml (recorded in
the task notes). The drivers now build the scratch home and export it as
their own HERMES_HOME BEFORE the first upstream import, refuse ambient
pyteman activation of the driver process, and the 111912 children inherit
the scratch too.

The upstream here is a stub that records the environment it saw at
import and at first use: the suite must not depend on a hermes checkout.
The ordering the stub observes is exactly the ordering the real upstream
experiences.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"

# The stub resolves HERMES_HOME the way the real one does (environment
# first) and records what it saw, at import and at SessionDB use, into a
# file the TEST names: the driver's scratch home is a mkdtemp the test
# cannot enumerate, so the record must ride an explicit path.
STUB_STATE = '''import os

_home = os.environ.get("HERMES_HOME", "/UNSET")
_seen = os.environ.get("STUB_RECORD", "/tmp/stub-saw-unrouted.json")
# APPEND, never truncate: the 109966 children (holder, restarter)
# import this same stub, and a truncating import-time record would
# erase the driver's line, leaving only the children's scratch-home
# lines and making the isolation test blind to exactly the
# import-before-scratch reorder it exists to catch.
with open(_seen, "a", encoding="utf-8") as fh:
    fh.write("\\nimport:" + _home)


class DeletedWalGenerationError(Exception):
    pass


class SessionDB:
    def __init__(self, db_path=None):
        with open(_seen, "a", encoding="utf-8") as fh:
            fh.write("\\nuse:" + os.environ.get("HERMES_HOME", "/UNSET"))

    def create_session(self, *a, **k):
        pass

    def append_message(self, *a, **k):
        pass

    def close(self):
        pass
'''

STUB_DBFILE_109 = '''def iter_deleted_sqlite_sidecar_holders(db):
    return []
'''

STUB_KILL_111 = '''import os, signal, time


def _kill_pids_posix(pids, killed, failed):
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(0.1)
            os.kill(pid, signal.SIGKILL)
            killed.append(pid)
        except OSError as exc:
            failed.append((pid, exc))
'''

STUB_DBFILE_111 = '''import os


def iter_deleted_sqlite_sidecar_holders(db):
    return []


def refuse_deleted_wal_generation(db):
    return None
'''


def _stub_repo(path, which):
    path.mkdir(parents=True, exist_ok=True)
    (path / "hermes_state.py").write_text(STUB_STATE)
    (path / "hermes_state_dbfile.py").write_text(
        STUB_DBFILE_111 if which == "111912" else STUB_DBFILE_109)
    if which == "111912":
        (path / "hermes_cli").mkdir()
        (path / "hermes_cli" / "__init__.py").write_text("")
        (path / "hermes_cli" / "dashboard_procs.py").write_text(STUB_KILL_111)
    return path


def _empty_ruleset(path):
    r = path / "empty.yaml"
    r.write_text("[]\n")
    return r


def _run(driver_dir, stub, ruleset, extra_env):
    """Run a driver with the stub upstream. The CLIs differ: 111912 takes
    (repo, ruleset, [expected]); 109966 takes (repo, [expected]) and
    reads its ruleset from beside itself, so the ruleset argument only
    exists for 111912 and 109966 gets the stub path as its expected
    verdict, which never matches and ends in the mismatch exit 1 that
    the caller's rc assertion allows."""
    env = dict(os.environ)
    env.pop("PYTEMAN_RULES", None)
    env.pop("PYTEMAN_LOG", None)
    env.update(extra_env)
    argv = [sys.executable, "run_repro.py", str(stub)]
    if driver_dir.name.endswith("111912"):
        argv.append(str(ruleset))
    return subprocess.run(
        argv, cwd=driver_dir, env=env, capture_output=True, text=True,
        timeout=60,
    )


@pytest.mark.parametrize("which", ["109966", "111912"])
def test_the_driver_process_resolves_the_scratch_home_not_the_operators(
        tmp_path, which):
    """The whole point: import-time and first-use both see the scratch.

    The stub records HERMES_HOME at import (module top level) and at
    SessionDB construction. Before the fix both read the operator's
    sentinel; the ordering fix must make both read the scratch home the
    driver built, and the operator's sentinel must not gain a single
    file.
    """
    driver_dir = EXAMPLES / f"hermes-{which}"
    stub = _stub_repo(tmp_path / "stub", which)
    sentinel = tmp_path / "operator-home"
    sentinel.mkdir()
    (sentinel / "config.yaml").write_text("journal_mode: delete\n")
    before = sorted(p.name for p in sentinel.iterdir())

    record = tmp_path / "saw.json"
    r = _run(driver_dir, stub, _empty_ruleset(tmp_path),
             {"HERMES_HOME": str(sentinel), "STUB_RECORD": str(record)})

    assert r.returncode in (0, 1), (
        f"the driver must run to its own conclusion; rc={r.returncode} "
        f"stdout={r.stdout[-300:]} stderr={r.stderr[-300:]}")
    # The sentinel must hold ONLY its original files.
    after = sorted(p.name for p in sentinel.iterdir())
    assert after == before, (
        f"the operator's home was written: {set(after) - set(before)}")
    assert record.exists(), (
        "the stub never recorded; the driver imported a hermes_state "
        "that is not this stub. stdout: " + r.stdout[-200:])
    seen = record.read_text(encoding="utf-8")
    homes = [line.split(":", 1)[1] for line in seen.splitlines()
             if ":" in line]
    assert homes, seen
    assert all(h != str(sentinel) for h in homes), (
        f"the operator's home leaked into the driver: {seen!r}")
    # Every observation names ONE home: the scratch the driver built,
    # which is neither the sentinel nor unset. It is a mkdtemp the
    # driver owns, so the test asserts its shape rather than its path.
    assert len(set(homes)) == 1, (
        f"the driver changed homes mid-run: {seen!r}")
    assert homes[0] not in ("", "/UNSET"), seen


@pytest.mark.parametrize("which", ["109966", "111912"])
def test_ambient_pyteman_activation_of_the_driver_is_refused_clearly(
        tmp_path, which):
    """An instrumented driver is not the scenario; it fails loudly.

    The example sets its own rules for its children; an ambient
    PYTEMAN_RULES would instrument the DRIVER process itself with rules
    nobody here chose.
    """
    driver_dir = EXAMPLES / f"hermes-{which}"
    stub = _stub_repo(tmp_path / "stub", which)
    r = _run(driver_dir, stub, _empty_ruleset(tmp_path),
             {"PYTEMAN_RULES": "/nonexistent/ambient.yaml"})
    assert r.returncode == 2, (
        f"rc={r.returncode}; the refusal must be the driver's _fail exit")
    assert "PYTEMAN_RULES is set in the ambient environment" in r.stdout
    assert "instrumented driver is not this scenario" in r.stdout


@pytest.mark.parametrize("which", ["109966", "111912"])
def test_an_ambient_marker_does_not_reach_the_children(tmp_path, which):
    """The children start from a pyteman-clean environment.

    Before the strip, an ambient PYTEMAN_REQUIRE_MARKER pointing at a
    file that does not exist rode dict(os.environ) into the children:
    the child refused at sitecustomize while the driver reported a
    readiness timeout, a misattributed failure. With the strip the
    children never see the marker and the run proceeds.
    """
    driver_dir = EXAMPLES / f"hermes-{which}"
    stub = _stub_repo(tmp_path / "stub", which)
    sentinel = tmp_path / "operator-home"
    sentinel.mkdir()
    r = _run(driver_dir, stub, _empty_ruleset(tmp_path),
             {"HERMES_HOME": str(sentinel),
              "PYTEMAN_REQUIRE_MARKER": str(tmp_path / "absent.marker")})
    assert r.returncode in (0, 1), (
        f"rc={r.returncode}; a marker the children never see cannot be "
        f"the failure. stdout={r.stdout[-300:]}")
    assert "never became ready" not in r.stdout, (
        "the readiness timeout is the misattributed shape the strip "
        "exists to prevent")


# ---------------------------------------------------------------------------
# TASK-29 / EX-04: the holder's failure is classified, not assumed. A fail
# flag holding anything at all used to read as REPRODUCED, so a generic
# disk-full fault claimed to be the WAL-generation incident; a holder dead
# before its first heartbeat crashed the driver's heartbeat read with no
# verdict at all. The holder now writes STRUCTURED evidence (phase, error
# type, tick) and publishes the heartbeat atomically; only the WAL refusal
# feeds REPRODUCED, everything else is a named harness fault.
# ---------------------------------------------------------------------------

STUB_STATE_29 = '''import os
import sys


class DeletedWalGenerationError(Exception):
    pass


class SessionDB:
    def __init__(self, db_path=None):
        self._n = 0

    def create_session(self, *a, **k):
        pass

    def append_message(self, *a, **k):
        self._n += 1
        mode = os.environ.get("HOLD_FAIL", "")
        # Only in the HOLDER process (its argv carries the holder.ready
        # marker path): the driver's own seed call must succeed so the
        # run reaches the holder at all.
        in_holder = any(str(a).endswith("holder.ready") for a in sys.argv)
        if mode == "generic" and in_holder and self._n > 2:
            raise RuntimeError("synthetic disk-full fault")
        if mode == "wal" and in_holder and self._n > 2:
            raise DeletedWalGenerationError("synthetic WAL refusal")
        if mode == "before" and in_holder:
            raise RuntimeError("synthetic fault before first heartbeat")

    def close(self):
        pass
'''


@pytest.mark.parametrize("mode,verdict,reason_needle", [
    ("generic", "INCONCLUSIVE",
     "holder fault unrelated to the WAL generation (RuntimeError"),
    ("wal", "REPRODUCED",
     "holder hit the WAL-generation refusal"),
    ("before", "INCONCLUSIVE",
     "holder fault unrelated to the WAL generation (RuntimeError"),
], ids=["generic-fault", "wal-refusal", "dead-before-heartbeat"])
def test_the_holder_failure_is_classified_not_assumed(tmp_path, mode,
                                                       verdict, reason_needle):
    """Three legs, three answers, and a reason that names which.

    The pre-fix driver printed REPRODUCED for the generic fault (any
    fail flag was the incident) and crashed with no verdict when the
    holder died before its first heartbeat. The stub steers the holder
    only; the driver's own seed always succeeds.
    """
    stub = tmp_path / "stub"
    stub.mkdir()
    (stub / "hermes_state.py").write_text(STUB_STATE_29)
    (stub / "hermes_state_dbfile.py").write_text(STUB_DBFILE_109)
    env = dict(os.environ)
    env.pop("PYTEMAN_RULES", None)
    env.pop("PYTEMAN_LOG", None)
    env["HOLD_FAIL"] = mode
    r = subprocess.run(
        [sys.executable, "run_repro.py", str(stub)],
        cwd=EXAMPLES / "hermes-109966", env=env, capture_output=True,
        text=True, timeout=90,
    )
    out = r.stdout
    assert f"VERDICT: {verdict}" in out, out[-500:]
    assert "REASON:" in out, "every verdict carries a reason"
    assert reason_needle in out, out[-500:]
    # The verdict line keeps its stable token for CI grepping: the
    # reason rides its own line.
    for line in out.splitlines():
        if line.startswith("VERDICT:"):
            assert line.strip() == f"VERDICT: {verdict}", line


def test_an_unparsable_fail_flag_is_a_named_harness_fault(tmp_path):
    """Evidence the classifier cannot read is INCONCLUSIVE, never a
    silent incident claim and never a crash."""
    stub = tmp_path / "stub"
    stub.mkdir()
    (stub / "hermes_state.py").write_text(STUB_STATE_29)
    (stub / "hermes_state_dbfile.py").write_text(STUB_DBFILE_109)
    # Corrupt the flag after a generic-fault run wrote it: run once,
    # then break the file and... the run already finished. Instead:
    # pre-create a scenario where the holder writes nothing but a
    # foreign fail flag exists is not reachable; the honest probe is
    # the classifier function itself.
    driver_dir = EXAMPLES / "hermes-109966"
    sys.path.insert(0, str(driver_dir))
    try:
        import run_repro as rr
    finally:
        sys.path.pop(0)
    bad = tmp_path / "holder.failed"
    bad.write_text("not json at all")
    is_incident, why = rr._holder_failure(str(bad))
    assert is_incident is False
    assert "unparsable evidence" in why
    ok = tmp_path / "ok.failed"
    ok.write_text('{"phase": "append", "error_type": '
                  '"DeletedWalGenerationError", "tick": 4}')
    is_incident, why = rr._holder_failure(str(ok))
    assert is_incident is True
    assert "phase append tick 4" in why


def test_heartbeat_states_are_named_not_fatal(tmp_path):
    """Absent, empty and unreadable heartbeats answer (None, reason)."""
    driver_dir = EXAMPLES / "hermes-109966"
    sys.path.insert(0, str(driver_dir))
    try:
        import run_repro as rr
    finally:
        sys.path.pop(0)
    assert rr._read_heartbeat(str(tmp_path / "absent")) == (None, "absent")
    empty = tmp_path / "empty"
    empty.write_text("   ")
    assert rr._read_heartbeat(str(empty)) == (None, "empty")
    locked = tmp_path / "dir"
    locked.mkdir()
    # A directory cannot be read as a file: the OSError branch.
    content, why = rr._read_heartbeat(str(locked))
    assert content is None
    assert why.startswith("unreadable (")
    good = tmp_path / "good"
    good.write_text("7")
    assert rr._read_heartbeat(str(good)) == ("7", "")
