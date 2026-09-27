# tests/test_example_process_tree.py
"""The 111912 driver's process tree dies on every exit (TASK-27 / EX-02).

The audit found no try/finally around the driver's process lifecycle: an
upstream stop that raised, a failed scanner, a SQLite fault during
rotation or a readiness timeout all skipped the cleanup, leaving orphans
that could be SIGSTOPped and still holding the database. These tests pin
the handle that now owns the tree (unit level, real subprocesses) and
the driver itself (integration level, failure injection through a stub
upstream, the driver run as an isolated process under an external
timeout).
"""
import importlib.util
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
HERE_111912 = EXAMPLES / "hermes-111912"
VENV_PYTHON = sys.executable

PARK_LOOP = "import time; time.sleep(120)"
# Spawns a descendant that parks too, like dashboard_sim spawning
# tui_child, and announces its pid the way tui_child does: an atomically
# replaced ready file, so the tests read the descendant instead of
# polling pgrep for it.
SPAWNER_LOOP = (
    "import os, subprocess, sys, time\n"
    f"child = subprocess.Popen([sys.executable, '-c', {PARK_LOOP!r}])\n"
    "tmp = sys.argv[1] + '.tmp'\n"
    "with open(tmp, 'w') as fh:\n"
    "    fh.write(str(child.pid))\n"
    "os.replace(tmp, sys.argv[1])\n"
    "time.sleep(120)\n"
)


def _wait_marker(path, deadline_s=10.0):
    """Read a pid from a ready marker once it appears, with a deadline."""
    end = time.monotonic() + deadline_s
    while time.monotonic() < end:
        if path.exists():
            return int(path.read_text(encoding="utf-8").strip())
        time.sleep(0.02)
    return None


def load_driver():
    spec = importlib.util.spec_from_file_location(
        "run_repro_111912", HERE_111912 / "run_repro.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _alive(pid):
    """True while /proc/<pid> exists (zombies included: they must go too)."""
    return os.path.isdir(f"/proc/{pid}")


def _gone(pid, deadline=10.0):
    """True once the pid leaves /proc entirely, zombie included.

    A killed descendant is reaped by whoever adopted it, not by us, so
    the wait has a deadline rather than an assumption.
    """
    end = time.monotonic() + deadline
    while time.monotonic() < end:
        if not _alive(pid):
            return True
        time.sleep(0.05)
    return False


@pytest.fixture()
def driver():
    return load_driver()


@pytest.fixture()
def handle(driver):
    h = driver._TreeHandle()
    yield h
    h.kill()


def test_a_failure_right_after_spawn_leaves_no_orphan(handle, tmp_path):
    """AC #1's first leg: the crash window before any ready marker.

    The spawner parent and its parked descendant are both live when the
    failure lands; the cleanup must take both, and the descendant is not
    this test's child, so only group-killing reaches it.
    """
    marker = tmp_path / "spawn-ready"
    handle.spawn([VENV_PYTHON, "-c", SPAWNER_LOOP, str(marker)])
    descendant = _wait_marker(marker)
    assert descendant is not None, "the spawner never announced a descendant"

    errors = handle.kill()  # what the finally does when anything raises

    assert errors == []
    assert handle.parent.poll() is not None, "the parent was reaped"
    assert _gone(descendant), "the descendant survived the cleanup"


def test_a_sigstopped_descendant_is_killed_not_left_wedged(
        handle, tmp_path):
    """The worst orphan: SIGSTOPped, still holding the database fds.

    SIGKILL is deliverable to a stopped process; a cleanup that only
    SIGTERMed, or never reached the child, would leave it parked forever.
    """
    marker = tmp_path / "stop-ready"
    handle.spawn([VENV_PYTHON, "-c", SPAWNER_LOOP, str(marker)])
    descendant = _wait_marker(marker)
    assert descendant is not None
    handle.child_pid = descendant
    os.kill(descendant, signal.SIGSTOP)
    # The stop landed: the process state (third field of /proc/<pid>/stat,
    # after the parenthesized name) reads T. The signal needs a
    # scheduling tick to take effect, so this POLLS with a deadline
    # rather than reading once; a timeout here means the test would
    # prove nothing, and it fails itself instead of passing vacuously.
    stopped = False
    stop_deadline = time.monotonic() + 5
    while time.monotonic() < stop_deadline:
        stat_fields = open(f"/proc/{descendant}/stat",
                           encoding="utf-8").read().rsplit(") ", 1)[1].split()
        if stat_fields[0].startswith("T"):
            stopped = True
            break
        time.sleep(0.02)
    assert stopped, (
        f"the SIGSTOP never landed; state stayed {stat_fields[0]!r}, "
        "the test would prove nothing")

    errors = handle.kill()

    assert errors == []
    assert _gone(descendant), "the stopped descendant survived"


def test_cleanup_signals_only_the_captured_group(driver, monkeypatch):
    """AC #3: no signal can reach a process the driver did not create.

    killpg is observed rather than trusted: the only id it may ever be
    called with is the pgid captured at spawn, which can never be this
    test's own group because the spawn created a fresh session.
    """
    h = driver._TreeHandle()
    h.spawn([VENV_PYTHON, "-c", PARK_LOOP])
    assert h.pgid == h.parent.pid
    # The property itself, not a corollary: the child's ACTUAL group is
    # its own pid (it is a session leader), which differs from this
    # test's group. Comparing only pids would pass even without the
    # fresh session, since a fresh pid never equals an old pgid.
    assert os.getpgid(h.parent.pid) == h.parent.pid, \
        "the spawn must create a fresh group the child leads"
    assert h.pgid != os.getpgrp()

    calls = []
    real_killpg = os.killpg

    def recording_killpg(pgid, sig):
        calls.append((pgid, sig))
        return real_killpg(pgid, sig)

    monkeypatch.setattr(os, "killpg", recording_killpg)
    h.kill()
    monkeypatch.setattr(os, "killpg", real_killpg)

    assert calls == [(h.pgid, signal.SIGKILL)]
    assert h.parent.poll() is not None


def test_kill_is_idempotent_and_reports_errors_not_exceptions(handle):
    """The finally runs after the normal path already killed the tree.

    The second kill must be quiet (ESRCH is the goal, reached) and must
    never raise over an exception already propagating.
    """
    handle.spawn([VENV_PYTHON, "-c", PARK_LOOP])
    assert handle.kill() == []
    assert handle.kill() == [], "the second call is a no-op, not an error"
    assert handle.parent.poll() is not None


# ---------------------------------------------------------------------------
# Driver level: the real run_repro.py, isolated in a subprocess under an
# external timeout (AC #4), with a stub upstream whose stop and scanner
# can be made to fail. The stub is the only stand-in: dashboard_sim and
# tui_child are the real example processes, and the real ruleset pins the
# real teardown, so the tree under cleanup is the tree the audit worried
# about.
# ---------------------------------------------------------------------------

STUB_KILL = '''import os, signal, time


def _kill_pids_posix(pids, killed, failed):
    if os.environ.get("STUB_KILL_MODE") == "raise":
        raise RuntimeError("controlled upstream failure")
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(0.1)
            os.kill(pid, signal.SIGKILL)
            killed.append(pid)
        except OSError as exc:
            failed.append((pid, exc))
'''

STUB_STATE = '''class DeletedWalGenerationError(Exception):
    pass
'''

STUB_DBFILE = '''import os


def iter_deleted_sqlite_sidecar_holders(db):
    if os.environ.get("STUB_SCANNER_MODE") == "raise":
        raise RuntimeError("controlled scanner failure")
    return []


def refuse_deleted_wal_generation(db):
    return None
'''


@pytest.fixture(scope="module")
def stub_repo(tmp_path_factory):
    repo = tmp_path_factory.mktemp("stub-hermes")
    (repo / "hermes_cli").mkdir()
    (repo / "hermes_cli" / "__init__.py").write_text("")
    (repo / "hermes_cli" / "dashboard_procs.py").write_text(STUB_KILL)
    (repo / "hermes_state.py").write_text(STUB_STATE)
    (repo / "hermes_state_dbfile.py").write_text(STUB_DBFILE)
    return repo


def _tree_processes():
    """Pids of example tree processes alive right now, with their state.

    Matched by the script names in the command line, which only this
    example's children carry; the suite is serial, so a before/after
    comparison is exact.
    """
    out = subprocess.run(
        ["ps", "-eo", "pid=,stat=,args="],
        capture_output=True, text=True).stdout
    found = {}
    for line in out.splitlines():
        if "dashboard_sim" in line or "tui_child" in line:
            pid_s, stat = line.split(None, 2)[0], line.split(None, 2)[1]
            found[int(pid_s)] = stat
    return found


def _assert_no_tree_left(baseline, symptom, settle_s=5.0):
    """Poll until the example's processes are back to the baseline set.

    A fixed sleep both wastes time and leaves a flake window if adoption
    and reaping take longer than the sleep; a bounded poll with the
    survivors named on expiry is the same idiom the SIGSTOP check uses.
    """
    end = time.monotonic() + settle_s
    left = _tree_processes()
    while time.monotonic() < end and not set(left) <= set(baseline):
        time.sleep(0.05)
        left = _tree_processes()
    assert set(left) <= set(baseline), (
        f"{symptom}: processes survived the driver's exit: "
        f"{ {pid: left[pid] for pid in set(left) - set(baseline)} }")
    assert not any("T" in st for st in left.values()), (
        f"{symptom}: a stopped process survived")


def _run_driver(stub_repo, tmp_path, extra_env, ruleset=None):
    env = dict(os.environ)
    env.update(extra_env)
    if ruleset is None:
        # An empty ruleset asks the hook to engage with no rules: the pin
        # stays out of the way, and the lifecycle under test is the driver's.
        ruleset = tmp_path / "empty.yaml"
        ruleset.write_text("[]\n")
    return subprocess.run(
        [sys.executable, "run_repro.py", str(stub_repo), str(ruleset)],
        cwd=HERE_111912, env=env, capture_output=True, text=True,
        timeout=60,
    )


@pytest.mark.parametrize("extra_env,ruleset_name,symptom", [
    ({"STUB_KILL_MODE": "raise"}, "empty",
     "inside the upstream stop: _kill_pids_posix raises"),
    # The real ruleset or the scanner leg is vacuous: with no pin the
    # forwarded SIGTERM finishes tui_child before the crash, so nothing
    # is left to clean up and the leg passed even with cleanup fully
    # neutered (measured by the review belt). Under the pin the stop
    # lands mid-teardown, the orphan lives and is SIGSTOPped, and the
    # scanner raises over it: the audit's exact post-SIGSTOP crash.
    ({"STUB_SCANNER_MODE": "raise"}, "slow",
     "after SIGSTOP: the holder scanner raises"),
], ids=["upstream-stop-raises", "scanner-raises"])
def test_the_driver_leaves_no_tree_behind_on_injected_failure(
        stub_repo, tmp_path, extra_env, ruleset_name, symptom):
    """AC #1's failure legs at driver level: crash, and nothing survives.

    The injected failure lands where the audit showed cleanup being
    skipped; the finally must kill the whole tree regardless, and no
    process of the run may remain alive OR stopped.
    """
    baseline = _tree_processes()
    ruleset = (HERE_111912 / "rules-slow-teardown.yaml"
               if ruleset_name == "slow" else None)
    r = _run_driver(stub_repo, tmp_path, extra_env, ruleset=ruleset)

    assert r.returncode != 0, (
        f"{symptom}: the injected failure must surface, not be swallowed; "
        f"rc={r.returncode} stdout={r.stdout[-400:]}")
    _assert_no_tree_left(baseline, symptom)


def test_the_driver_uses_the_real_ruleset_tree_and_cleans_it(
        stub_repo, tmp_path):
    """The same finally under the real pin: teardown slowed, stop lands
    mid-teardown, orphan held and SIGSTOPped, scanner fine, verdict
    reached; the tree still dies before the driver exits."""
    baseline = _tree_processes()
    ruleset = HERE_111912 / "rules-slow-teardown.yaml"
    run = _run_driver(stub_repo, tmp_path, {"STUB_KILL_MODE": ""},
                      ruleset=ruleset)
    assert "VERDICT:" in run.stdout, (
        f"the real-ruleset run must reach a verdict; stdout tail: "
        f"{run.stdout[-300:]} stderr tail: {run.stderr[-300:]}")
    _assert_no_tree_left(baseline, "the real-ruleset run")
