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
import types
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


def _load_driver(which):
    """A driver as a module, collision-proof.

    Both example dirs carry a run_repro.py; a bare import returns
    whatever sits in sys.modules, so the file is loaded by path under
    a name of its own.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        f"run_repro_{which}", EXAMPLES / f"hermes-{which}" / "run_repro.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _empty_ruleset(path):
    r = path / "empty.yaml"
    r.write_text("[]\n")
    return r


def _run(driver_dir, stub, ruleset, extra_env, timeout=60):
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
        timeout=timeout,
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

    assert r.returncode in (0, 1, 3), (
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
    assert r.returncode in (0, 1, 3), (
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
    r = _run(EXAMPLES / "hermes-109966", stub,
             _empty_ruleset(tmp_path), {"HOLD_FAIL": mode}, timeout=120)
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
    # No end-to-end leg can produce an unparsable flag: the holder
    # always writes valid JSON. The classifier is probed directly.
    rr = _load_driver("109966")
    # The classifier resolves the recorded error name against the
    # hermes_state module, which the driver always has imported by the
    # time it calls this; the unit probe registers a minimal one so the
    # resolution sees the same shape the runtime sees.
    hermes_state = types.ModuleType("hermes_state")

    class DeletedWalGenerationError(Exception):
        pass

    hermes_state.DeletedWalGenerationError = DeletedWalGenerationError
    sys.modules["hermes_state"] = hermes_state
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
    rr = _load_driver("109966")
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


def test_a_subclass_of_the_refusal_is_still_the_incident(tmp_path):
    """The two doors agree: except accepts subclasses, so must the flag.

    A holder raising a SUBCLASS of DeletedWalGenerationError reaches the
    fresh-opener probe as the incident; the flag classification used to
    compare the exact name, so the same run answered REPRODUCED from one
    door and "fault unrelated to the WAL generation" from the other.
    """
    rr = _load_driver("109966")
    hermes_state = types.ModuleType("hermes_state")

    class DeletedWalGenerationError(Exception):
        pass

    class StaleWalRefusal(DeletedWalGenerationError):
        pass

    hermes_state.DeletedWalGenerationError = DeletedWalGenerationError
    hermes_state.StaleWalRefusal = StaleWalRefusal
    sys.modules["hermes_state"] = hermes_state
    flag = tmp_path / "holder.failed"
    flag.write_text('{"phase": "append", "error_type": "StaleWalRefusal", '
                    '"tick": 3}')
    is_incident, why = rr._holder_failure(str(flag))
    assert is_incident is True
    assert "WAL-generation refusal" in why

    unknown = tmp_path / "unknown.failed"
    unknown.write_text('{"phase": "append", "error_type": "NotAKnownError", '
                       '"tick": 3}')
    is_incident, why = rr._holder_failure(str(unknown))
    assert is_incident is False
    assert "NotAKnownError" in why

    not_object = tmp_path / "list.failed"
    not_object.write_text("[1, 2]")
    is_incident, why = rr._holder_failure(str(not_object))
    assert is_incident is False
    assert "not an object" in why


# ---------------------------------------------------------------------------
# TASK-30 / EX-05: durable verdicts. INCONCLUSIVE without an expectation
# used to exit 0 (indistinguishable from success to whatever greps the
# code), the 111912 driver rmtree'd the scratch BEFORE reporting a
# mismatch, and the 109966 driver rmtree'd on the one mismatch path
# whose verdict was CLEAN. Now: distinct exit codes, an expectation
# validated before anything runs, a manifest.json with the diagnosis and
# provenance written before the preservation decision, and the home kept
# on every outcome except an unambiguous CLEAN.
# ---------------------------------------------------------------------------

def _run_109_with_stub(tmp_path, extra_argv=(), extra_env=None):
    """The 109966 driver against the steerable stub upstream."""
    stub = tmp_path / "stub"
    stub.mkdir(exist_ok=True)
    (stub / "hermes_state.py").write_text(STUB_STATE_29)
    (stub / "hermes_state_dbfile.py").write_text(STUB_DBFILE_109)
    env = dict(os.environ)
    env.pop("PYTEMAN_RULES", None)
    env.pop("PYTEMAN_LOG", None)
    env.update(extra_env or {})
    argv = [sys.executable, "run_repro.py", str(stub), *extra_argv]
    return subprocess.run(
        argv, cwd=EXAMPLES / "hermes-109966", env=env,
        capture_output=True, text=True, timeout=120,
    )


def test_inconclusive_without_expectation_is_not_exit_zero(tmp_path):
    """The audit's headline: an unanswered run is not a successful one.

    A generic holder fault makes the verdict INCONCLUSIVE (TASK-29's
    classification); before the change that fell off main with exit 0.
    """
    r = _run_109_with_stub(tmp_path,
                            extra_env={"HOLD_FAIL": "generic"})
    assert "VERDICT: INCONCLUSIVE" in r.stdout
    assert r.returncode == 3, (
        f"rc={r.returncode}; INCONCLUSIVE must carry its own exit code")
    preserved = [ln for ln in r.stdout.splitlines()
                 if ln.startswith("SCRATCH-HOME-PRESERVED:")]
    assert preserved, "the harness-fault verdict keeps its postmortem"
    manifest = Path(preserved[0].split(": ", 1)[1]) / "manifest.json"
    import json as _json
    data = _json.loads(manifest.read_text(encoding="utf-8"))
    assert data["verdict"] == "INCONCLUSIVE"
    assert "RuntimeError" in data["reason"]


def test_a_clean_run_exits_zero_and_drops_the_home(tmp_path):
    """The other side of the table: the unambiguous CLEAN still cleans."""
    r = _run_109_with_stub(tmp_path, extra_argv=["CLEAN"])
    assert "VERDICT: CLEAN" in r.stdout, r.stdout[-300:]
    assert r.returncode == 0
    assert "SCRATCH-HOME-PRESERVED" not in r.stdout


def test_a_mismatch_keeps_a_home_with_the_diagnosis_in_it(tmp_path):
    """AC #2: after a mismatch, the artifact exists and diagnoses.

    Expecting REPRODUCED against a stub that never reproduces gives a
    CLEAN-verdict mismatch: the one path that used to rmtree first.
    """
    r = _run_109_with_stub(tmp_path, extra_argv=["REPRODUCED"])
    assert "VERDICT: CLEAN" in r.stdout
    assert "EXPECTATION-MISMATCH: expected=REPRODUCED" in r.stdout
    assert r.returncode == 1
    preserved = [ln for ln in r.stdout.splitlines()
                 if ln.startswith("SCRATCH-HOME-PRESERVED:")]
    assert preserved, "the mismatch must keep the home"
    home = Path(preserved[0].split(": ", 1)[1])
    manifest = home / "manifest.json"
    assert manifest.exists(), "AC #2: the artifact must exist"
    import json as _json
    data = _json.loads(manifest.read_text(encoding="utf-8"))
    assert data["verdict"] == "CLEAN"
    assert data["expected"] == "REPRODUCED"
    assert "reason" in data and data["reason"]
    prov = data["provenance"]
    assert prov["ruleset_sha256"] and len(prov["ruleset_sha256"]) == 64
    assert prov["python"] and prov["sqlite"]
    # The stub is not a git checkout: the marker, not an empty string
    # that would read like a stripped value (rev-parse exits 128 with
    # empty stdout, which no exception ever sees).
    assert prov["upstream_revision"] == "not-a-git-checkout"


def test_an_invalid_expectation_is_refused_before_anything_runs(tmp_path):
    """A typo in the expectation costs nothing: validated up front."""
    r = _run_109_with_stub(tmp_path, extra_argv=["REPRODUCDE"])
    assert r.returncode == 2
    assert "expected verdict must be REPRODUCED or CLEAN" in r.stdout
    assert "VERDICT:" not in r.stdout


def _run_111_with_stub(tmp_path, extra_argv=()):
    """The 111912 driver against the steerable stub upstream."""
    stub = tmp_path / "stub111"
    stub.mkdir(exist_ok=True)
    (stub / "hermes_state.py").write_text(STUB_STATE_29)
    (stub / "hermes_state_dbfile.py").write_text(STUB_DBFILE_111)
    (stub / "hermes_cli").mkdir(exist_ok=True)
    (stub / "hermes_cli" / "__init__.py").write_text("")
    (stub / "hermes_cli" / "dashboard_procs.py").write_text(STUB_KILL_111)
    env = dict(os.environ)
    env.pop("PYTEMAN_RULES", None)
    env.pop("PYTEMAN_LOG", None)
    return subprocess.run(
        [sys.executable, "run_repro.py", str(stub),
         str(_empty_ruleset(tmp_path)), *extra_argv],
        cwd=EXAMPLES / "hermes-111912", env=env, capture_output=True,
        text=True, timeout=120,
    )


def test_the_111912_mismatch_keeps_the_manifest(tmp_path):
    """The other driver, whose cleanup used to precede the mismatch.

    The scanner-raising stub leg runs to an exception; the honest
    mismatch probe here uses the empty ruleset: pin unengaged ->
    INCONCLUSIVE -> mismatch against expectation CLEAN, with the
    manifest kept in the home the old code would already have dropped.
    """
    r = _run_111_with_stub(tmp_path, extra_argv=["CLEAN"])
    assert "VERDICT: INCONCLUSIVE" in r.stdout, r.stdout[-300:]
    assert "EXPECTATION-MISMATCH: expected=CLEAN" in r.stdout
    assert r.returncode == 1
    preserved = [ln for ln in r.stdout.splitlines()
                 if ln.startswith("SCRATCH-HOME-PRESERVED:")]
    assert preserved, "the 111912 mismatch must keep the home too"
    home = Path(preserved[0].split(": ", 1)[1])
    manifest = home / "manifest.json"
    assert manifest.exists()
    import json as _json
    data = _json.loads(manifest.read_text(encoding="utf-8"))
    assert data["verdict"] == "INCONCLUSIVE"
    assert data["expected"] == "CLEAN"
    assert data["reason"]


def test_the_111912_inconclusive_exits_three_without_expectation(tmp_path):
    """Both drivers share the exit table, INCONCLUSIVE included."""
    r = _run_111_with_stub(tmp_path)
    assert "VERDICT: INCONCLUSIVE" in r.stdout
    assert r.returncode == 3, (
        f"rc={r.returncode}; the 111912 INCONCLUSIVE must not exit 0")


# ---------------------------------------------------------------------------
# TASK-31 / EX-06: an incompatible checkout ends at once and says why.
# Both drivers imported the upstream names bare, so a tree lacking one
# (an empty dir, a hermes too old to have the WAL guard) died in a raw
# ImportError traceback with exit 1, which is EXIT_MISMATCH: the
# incompatible tree read as an answer. The preflight resolves every name
# inside the checkout before anything is seeded or spawned and refuses
# with the driver-error exit, naming what is missing.
# ---------------------------------------------------------------------------

def _preflight_run(tmp_path, which, stub, extra_env=None):
    """A driver run whose scratch homes land in a dir the test can list."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    env = {"TMPDIR": str(scratch), **(extra_env or {})}
    r = _run(EXAMPLES / f"hermes-{which}", stub, _empty_ruleset(tmp_path),
             env)
    return r, scratch


def _assert_refused(r, scratch, *needles):
    assert r.returncode == 2, (
        f"rc={r.returncode}; an incompatible checkout is a driver error, "
        f"never a mismatch. stdout={r.stdout[-300:]} stderr={r.stderr[-300:]}")
    assert "Traceback" not in r.stderr, r.stderr[-500:]
    assert "VERDICT:" not in r.stdout
    line = next((ln for ln in r.stdout.splitlines()
                 if ln.startswith("DRIVER-ERROR:")), "")
    for needle in ("is not a compatible hermes-agent checkout", "Tested on",
                   *needles):
        assert needle in line, (needle, r.stdout[-300:])
    assert list(scratch.iterdir()) == [], (
        f"the refusal left a scratch home behind: {list(scratch.iterdir())}")


@pytest.mark.parametrize("which,needles", [
    ("109966", ["no module hermes_state;", "no module hermes_state_dbfile"]),
    ("111912", ["no module hermes_cli.dashboard_procs",
                "no module hermes_state;", "no module hermes_state_dbfile"]),
])
def test_an_empty_checkout_is_refused_before_anything_runs(
        tmp_path, which, needles):
    empty = tmp_path / "empty"
    empty.mkdir()
    r, scratch = _preflight_run(tmp_path, which, empty)
    _assert_refused(r, scratch, *needles,
                    f"{empty} (revision not-a-git-checkout)")


@pytest.mark.parametrize("which,module,name", [
    ("109966", "hermes_state", "DeletedWalGenerationError"),
    ("109966", "hermes_state_dbfile", "iter_deleted_sqlite_sidecar_holders"),
    ("111912", "hermes_state_dbfile", "refuse_deleted_wal_generation"),
    ("111912", "hermes_cli/dashboard_procs", "_kill_pids_posix"),
])
def test_a_checkout_missing_one_name_is_refused_naming_it(
        tmp_path, which, module, name):
    """The old-tip shape: the modules import, one name is absent."""
    stub = _stub_repo(tmp_path / "stub", which)
    path = stub / f"{module}.py"
    source = path.read_text()
    renamed = source.replace(name, f"{name}_renamed")
    assert renamed != source, f"the stub never defined {name}"
    path.write_text(renamed)
    r, scratch = _preflight_run(tmp_path, which, stub)
    _assert_refused(r, scratch,
                    f"{module.replace('/', '.')}.{name} is missing")


@pytest.mark.parametrize("which", ["109966", "111912"])
def test_a_missing_upstream_dependency_is_named_not_confused_with_hermes(
        tmp_path, which):
    """A pinned checkout on an interpreter without its deps (PyYAML at
    the verified tip) is a prerequisites gap, reported as one."""
    stub = _stub_repo(tmp_path / "stub", which)
    state = stub / "hermes_state.py"
    state.write_text("import no_such_dependency_31\n" + state.read_text())
    r, scratch = _preflight_run(tmp_path, which, stub)
    _assert_refused(r, scratch,
                    "importing hermes_state needs module "
                    "'no_such_dependency_31'")


@pytest.mark.parametrize("which", ["109966", "111912"])
def test_a_module_found_outside_the_checkout_is_refused(tmp_path, which):
    """An installed or ambient hermes must not stand in for the tree
    under test: the checkout lacks hermes_state_dbfile, a complete one
    sits on PYTHONPATH, and the driver refuses rather than run it."""
    stub = _stub_repo(tmp_path / "stub", which)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (stub / "hermes_state_dbfile.py").rename(elsewhere / "hermes_state_dbfile.py")
    r, scratch = _preflight_run(tmp_path, which, stub,
                                {"PYTHONPATH": str(elsewhere)})
    _assert_refused(r, scratch, "hermes_state_dbfile resolves to "
                    f"{elsewhere / 'hermes_state_dbfile.py'}, outside the checkout")


def _module_literal(path, name):
    import ast
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", None) == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{path} defines no {name}")


@pytest.mark.parametrize("which,children", [
    ("109966", ["holder.py", "restarter.py"]),
    ("111912", ["dashboard_sim.py", "tui_child.py"]),
])
def test_the_preflight_table_is_every_upstream_import(which, children):
    """UPSTREAM_API restates the import lines, the driver's and its
    children's: a name imported and not listed would be a crash the
    preflight never names, a name listed and not imported a refusal of
    a checkout that works."""
    import ast
    here = EXAMPLES / f"hermes-{which}"
    imported = {}
    for name in ["run_repro.py", *children]:
        for node in ast.walk(ast.parse((here / name).read_text())):
            if (isinstance(node, ast.ImportFrom) and node.module
                    and node.module.split(".")[0].startswith("hermes")):
                imported.setdefault(node.module, set()).update(
                    a.name for a in node.names)
            elif isinstance(node, ast.Import):
                assert not any(a.name.startswith("hermes") for a in node.names), (
                    f"{name}: a bare hermes import names nothing to check")
    table = {m: set(ns) for m, ns in
             _module_literal(here / "run_repro.py", "UPSTREAM_API").items()}
    assert table == imported


def test_the_leg_script_runs_exactly_the_tested_revisions():
    """The drivers' TESTED_REVISIONS and the leg script's pinned SHAs
    name one set: a revision the refusal calls tested is one the script
    runs, and the script runs nothing the drivers do not claim."""
    import re
    pinned = set(re.findall(r"^\w+=([0-9a-f]{40})\b",
                            (EXAMPLES / "verify_hermes_legs.sh").read_text(),
                            re.M))
    claimed = [p for which in ("109966", "111912") for p in _module_literal(
        EXAMPLES / f"hermes-{which}" / "run_repro.py", "TESTED_REVISIONS")]
    assert len(pinned) == 3
    assert sorted(s[:10] for s in pinned) == sorted(claimed)


@pytest.mark.parametrize("which", ["109966", "111912"])
def test_an_upstream_exit_at_import_is_a_refusal_not_an_answer(
        tmp_path, which):
    """SystemExit is no Exception: an upstream that exits while being
    imported would pass through an `except Exception` preflight with
    its own code, and sys.exit(1) is EXIT_MISMATCH."""
    stub = _stub_repo(tmp_path / "stub", which)
    state = stub / "hermes_state.py"
    state.write_text("import sys\nsys.exit(1)\n" + state.read_text())
    r, scratch = _preflight_run(tmp_path, which, stub)
    _assert_refused(r, scratch, "importing hermes_state raised SystemExit: 1")


_CRASH_SITES = {
    "109966": ("hermes_state.py",
               "    def create_session(self, *a, **k):\n        pass",
               "    def create_session(self, *a, **k):\n        {raise_}"),
    "111912": ("hermes_cli/dashboard_procs.py",
               "    for pid in pids:",
               "    {raise_}\n    for pid in pids:"),
}


@pytest.mark.parametrize("raise_,kind", [
    ("raise TypeError('the signature changed')", "TypeError"),
    # An upstream sys.exit(0) mid-run would otherwise read as a match.
    ("raise SystemExit(0)", "SystemExit"),
])
@pytest.mark.parametrize("which", ["109966", "111912"])
def test_a_crash_past_the_preflight_is_a_driver_error_not_a_mismatch(
        tmp_path, which, raise_, kind):
    """The same defect one step later: every name resolves, then a call
    into the upstream raises (a signature a later tip changed) or exits.
    Python's own exit for the first is 1, EXIT_MISMATCH, and the second
    exits with whatever code the upstream chose; the driver maps both
    to 2."""
    module, old, new = _CRASH_SITES[which]
    stub = _stub_repo(tmp_path / "stub", which)
    path = stub / module
    source = path.read_text()
    assert old in source
    path.write_text(source.replace(old, new.format(raise_=raise_)))
    r, _ = _preflight_run(tmp_path, which, stub)
    assert r.returncode == 2, (r.returncode, r.stdout[-300:], r.stderr[-300:])
    assert "VERDICT:" not in r.stdout
    assert f"DRIVER-ERROR: unhandled {kind}" in r.stdout, r.stdout[-300:]
    assert "Traceback" in r.stderr and kind in r.stderr, r.stderr[-300:]


@pytest.mark.parametrize("which", ["109966", "111912"])
def test_a_directory_inside_another_repository_has_no_revision(
        tmp_path, which):
    """git rev-parse walks upward, so a plain directory under some
    enclosing repository would report that repository's HEAD as the
    checkout's revision, in the refusal line and in the manifest; and
    a repository with no commit yet would report the word HEAD."""
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t",
           "-c", "commit.gpgsign=false"]
    outer = tmp_path / "outer"
    inner = outer / "inner"
    inner.mkdir(parents=True)
    subprocess.run([*git, "init", "-q", str(outer)], check=True)
    subprocess.run([*git, "-C", str(outer), "commit", "-q", "--allow-empty",
                    "-m", "x"], check=True)
    head = subprocess.run(["git", "-C", str(outer), "rev-parse", "HEAD"],
                          capture_output=True, text=True,
                          check=True).stdout.strip()
    unborn = tmp_path / "unborn"
    subprocess.run([*git, "init", "-q", str(unborn)], check=True)
    rev = _load_driver(which)._git_rev
    assert rev(str(outer)) == head
    assert rev(str(inner)) == "not-a-git-checkout"
    assert rev(str(unborn)) == "not-a-git-checkout"
