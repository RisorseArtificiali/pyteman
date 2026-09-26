# tests/test_example_process_cleanup.py
"""Process tree cleanup for the #111912 driver.

The driver spawns a parent + child tree and must kill the entire group on
every exit path, including failures before readiness, during the upstream
kill sequence, after SIGSTOP, and during WAL rotation. These tests exercise
the _kill_tree helper with real processes and process groups so the cleanup
is proved against the kernel, not a mock.

Linux only: uses /proc to inspect process state, and process groups with
start_new_session to isolate the test tree from the test runner's own group.
"""
import importlib.util
import os
import signal
import sqlite3
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="process group cleanup and /proc inspection are Linux only",
)

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def load_driver():
    spec = importlib.util.spec_from_file_location(
        "run_repro_111912", EXAMPLES / "hermes-111912" / "run_repro.py",
        submodule_search_locations=[],
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHILD_SCRIPT = textwrap.dedent("""\
    import os, signal, subprocess, sys, time

    ready_marker = sys.argv[1]

    child = subprocess.Popen(
        [sys.executable, "-c",
         "import time; time.sleep(300)"],
    )

    tmp = ready_marker + ".tmp"
    with open(tmp, "w") as fh:
        fh.write(str(child.pid))
    os.replace(tmp, ready_marker)

    while True:
        time.sleep(0.5)
""")


def spawn_tree(tmp_path):
    """Spawn a two-level process tree in its own session.

    Returns (parent Popen, pgid, ready_marker path). The parent spawns a
    grandchild that sleeps indefinitely, then writes the grandchild's PID to
    the ready marker. Both inherit the session created by start_new_session.
    """
    ready = str(tmp_path / "child.ready")
    script = str(tmp_path / "parent.py")
    Path(script).write_text(CHILD_SCRIPT)
    parent = subprocess.Popen(
        [sys.executable, script, ready],
        start_new_session=True,
    )
    pgid = parent.pid
    return parent, pgid, ready


def wait_ready(ready, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if os.path.exists(ready):
            return int(Path(ready).read_text().strip())
        time.sleep(0.05)
    raise TimeoutError("child never became ready")


def proc_alive(pid):
    return os.path.isdir(f"/proc/{pid}")


def assert_tree_dead(pgid, parent_pid, child_pid, label=""):
    """Verify no process from the group survives."""
    time.sleep(0.1)
    suffix = f" ({label})" if label else ""
    assert not proc_alive(parent_pid), (
        f"parent {parent_pid} still alive after cleanup{suffix}"
    )
    assert not proc_alive(child_pid), (
        f"child {child_pid} still alive after cleanup{suffix}"
    )


class TestKillTree:
    """Direct tests of the _kill_tree helper from run_repro.py."""

    @pytest.fixture(autouse=True)
    def _load_driver(self):
        self.driver = load_driver()

    def test_kills_both_parent_and_child(self, tmp_path):
        parent, pgid, ready = spawn_tree(tmp_path)
        child_pid = wait_ready(ready)
        assert proc_alive(parent.pid)
        assert proc_alive(child_pid)
        self.driver._kill_tree(pgid, parent)
        assert_tree_dead(pgid, parent.pid, child_pid, "normal kill")

    def test_kills_orphan_after_parent_already_dead(self, tmp_path):
        parent, pgid, ready = spawn_tree(tmp_path)
        child_pid = wait_ready(ready)
        os.kill(parent.pid, signal.SIGKILL)
        parent.wait(timeout=5)
        assert not proc_alive(parent.pid)
        assert proc_alive(child_pid), "child should be orphaned, not dead"
        self.driver._kill_tree(pgid, parent)
        assert_tree_dead(pgid, parent.pid, child_pid, "orphan cleanup")

    def test_kills_stopped_child(self, tmp_path):
        parent, pgid, ready = spawn_tree(tmp_path)
        child_pid = wait_ready(ready)
        os.kill(parent.pid, signal.SIGKILL)
        parent.wait(timeout=5)
        os.kill(child_pid, signal.SIGSTOP)
        assert proc_alive(child_pid), "stopped child should still be in /proc"
        self.driver._kill_tree(pgid, parent)
        assert_tree_dead(pgid, parent.pid, child_pid, "stopped child cleanup")

    def test_idempotent_when_group_already_gone(self, tmp_path):
        parent, pgid, ready = spawn_tree(tmp_path)
        child_pid = wait_ready(ready)
        os.killpg(pgid, signal.SIGKILL)
        parent.wait(timeout=5)
        time.sleep(0.1)
        self.driver._kill_tree(pgid, parent)
        assert_tree_dead(pgid, parent.pid, child_pid, "already-dead group")


class TestDriverCleanupPaths:
    """Simulate each failure injection point and verify the tree is dead.

    Each test spawns a real process tree, then exercises the failure path
    that would leave orphans without the try/finally guard. The tree is
    managed with the same start_new_session + _kill_tree pattern the
    driver uses.
    """

    @pytest.fixture(autouse=True)
    def _load_driver(self):
        self.driver = load_driver()

    def test_failure_before_readiness(self, tmp_path):
        """Process that never writes the ready marker: the tree must still
        be killed when the caller gives up."""
        ready = str(tmp_path / "child.ready")
        parent = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(300)"],
            start_new_session=True,
        )
        pgid = parent.pid
        try:
            for _ in range(10):
                if os.path.exists(ready):
                    break
                time.sleep(0.01)
            assert not os.path.exists(ready)
        finally:
            self.driver._kill_tree(pgid, parent)
        time.sleep(0.1)
        assert not proc_alive(parent.pid), (
            "parent survived readiness-timeout cleanup"
        )

    def test_failure_during_upstream_kill(self, tmp_path):
        """An exception from the kill sequence (e.g. upstream raises) must
        not skip the finally block."""
        parent, pgid, ready = spawn_tree(tmp_path)
        child_pid = wait_ready(ready)

        def failing_kill(pids, killed, failed):
            raise RuntimeError("controlled upstream failure")

        try:
            failing_kill([parent.pid], [], [])
        except RuntimeError:
            pass
        finally:
            self.driver._kill_tree(pgid, parent)
        assert_tree_dead(pgid, parent.pid, child_pid, "upstream kill failure")

    def test_failure_after_sigstop(self, tmp_path):
        """An exception after SIGSTOP (e.g. during WAL rotation) must not
        leave the child stopped and holding the database."""
        parent, pgid, ready = spawn_tree(tmp_path)
        child_pid = wait_ready(ready)
        os.kill(parent.pid, signal.SIGKILL)
        parent.wait(timeout=5)
        os.kill(child_pid, signal.SIGSTOP)
        assert proc_alive(child_pid)
        try:
            raise sqlite3.OperationalError("controlled rotation failure")
        except sqlite3.OperationalError:
            pass
        finally:
            self.driver._kill_tree(pgid, parent)
        assert_tree_dead(pgid, parent.pid, child_pid, "post-SIGSTOP failure")

    def test_failure_during_rotation(self, tmp_path):
        """A SQLite error during the WAL rotation must not leak the tree."""
        parent, pgid, ready = spawn_tree(tmp_path)
        child_pid = wait_ready(ready)
        try:
            raise sqlite3.OperationalError("database is locked")
        except sqlite3.OperationalError:
            pass
        finally:
            self.driver._kill_tree(pgid, parent)
        assert_tree_dead(pgid, parent.pid, child_pid, "rotation failure")

    def test_no_signal_to_unrelated_processes(self, tmp_path):
        """The group kill must not reach processes outside the session."""
        unrelated = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(300)"],
        )
        try:
            parent, pgid, ready = spawn_tree(tmp_path)
            child_pid = wait_ready(ready)
            self.driver._kill_tree(pgid, parent)
            assert_tree_dead(pgid, parent.pid, child_pid, "tree cleanup")
            assert proc_alive(unrelated.pid), (
                "unrelated process was killed by group cleanup"
            )
        finally:
            unrelated.kill()
            unrelated.wait(timeout=5)
