# tests/test_firing.py
"""LOG-01: identity, provenance, and same-process concurrency for FiringLog.

Cross-process writer tests live in test_firing_multiprocess.py, since they
need real subprocesses rather than threads.
"""
import fcntl
import gc
import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid

import pytest

from pyteman.firing import FiringLog, FiringLogError
from pyteman.rules import Rule
from test_firing_concurrency import JOIN_TIMEOUT, run_threads

WAITPID_TIMEOUT = 10
SELF_INSTRUMENTATION_TIMEOUT = 30


def _rule(id="r1"):
    return Rule(id=id, module="m", symbol="f", event="entry",
                action={"kind": "return_none"})


def _waitpid_bounded(pid, timeout=WAITPID_TIMEOUT, kill_timeout=5):
    """os.waitpid(pid, 0) with a deadline: kill and reap rather than hang.

    A regression that reintroduces a fork-across-a-held-lock deadlock must
    fail this test by going red, not by hanging the whole suite. The reap
    after SIGKILL is bounded too: SIGKILL can't be caught or ignored, but a
    process stuck in an uninterruptible kernel wait could still leave a
    plain os.waitpid(pid, 0) blocked, and this helper's only job is to never
    block unboundedly, regardless of the reason.
    """
    def poll_until(deadline):
        while time.monotonic() < deadline:
            wpid, status = os.waitpid(pid, os.WNOHANG)
            if wpid != 0:
                return status
            time.sleep(0.02)
        return None

    status = poll_until(time.monotonic() + timeout)
    if status is not None:
        return status

    os.kill(pid, signal.SIGKILL)
    status = poll_until(time.monotonic() + kill_timeout)
    if status is None:
        pytest.fail(
            f"child pid {pid} did not exit within {timeout}s and was still "
            f"not reapable {kill_timeout}s after SIGKILL")
    pytest.fail(f"child pid {pid} did not exit within {timeout}s; killed")


def test_log_records_sequenced_lines(tmp_path):
    p = tmp_path / "f.jsonl"
    log = FiringLog(str(p))
    r = _rule()
    log.record(r, {"args": (1,), "kwargs": {}, "fires": 1}, note="x")
    log.record(r, {"args": (), "kwargs": {}, "fires": 2})
    lines = [json.loads(l) for l in p.read_text().splitlines()]
    assert [l["seq"] for l in lines] == [1, 2]
    assert lines[0]["rule"] == "r1" and lines[0]["thread"]
    assert lines[0]["note"] == "x"


def test_record_carries_identity_and_point(tmp_path):
    p = tmp_path / "f.jsonl"
    log = FiringLog(str(p))
    log.record(_rule(), {"fires": 3})
    rec = json.loads(p.read_text().splitlines()[0])

    assert rec["schema"] == 2
    assert rec["run_id"] == log.run_id
    assert rec["instance"] == log.instance
    assert rec["pid"] == os.getpid()
    assert rec["point"] == "m.f"
    assert rec["visit"] == 3
    assert isinstance(rec["monotonic_ns"], int)
    assert rec["time"].endswith("+00:00")


def test_visit_is_none_without_a_fires_ticket_in_ctx(tmp_path):
    # A direct run_action call outside the normal _gate path has no "fires"
    # ticket; the schema says so rather than inventing one.
    p = tmp_path / "f.jsonl"
    log = FiringLog(str(p))
    log.record(_rule(), {"args": (), "kwargs": {}})
    rec = json.loads(p.read_text().splitlines()[0])
    assert rec["visit"] is None


def test_reopen_gives_a_fresh_instance_and_restarts_seq_at_one(tmp_path):
    p = tmp_path / "f.jsonl"
    first = FiringLog(str(p))
    first.record(_rule(), {"fires": 1})
    first.close()
    second = FiringLog(str(p))
    second.record(_rule(), {"fires": 1})
    second.close()

    lines = [json.loads(l) for l in p.read_text().splitlines()]
    assert lines[0]["seq"] == lines[1]["seq"] == 1
    # The old bug: two "[1]" sequences with nothing to tell them apart.
    # instance is what makes them distinguishable now.
    assert lines[0]["instance"] != lines[1]["instance"]


def test_run_id_is_read_from_the_environment_when_set(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTEMAN_RUN_ID", "fixed-run")
    log = FiringLog(str(tmp_path / "f.jsonl"))
    assert log.run_id == "fixed-run"


def test_run_id_is_fresh_per_instance_without_the_env_var(tmp_path, monkeypatch):
    monkeypatch.delenv("PYTEMAN_RUN_ID", raising=False)
    a = FiringLog(str(tmp_path / "a.jsonl"))
    b = FiringLog(str(tmp_path / "b.jsonl"))
    assert a.run_id != b.run_id
    uuid.UUID(a.run_id)  # a real uuid4 hex, not a placeholder string


def test_close_is_idempotent_and_record_after_close_raises(tmp_path):
    log = FiringLog(str(tmp_path / "f.jsonl"))
    log.close()
    log.close()  # must not raise a second time
    with pytest.raises(FiringLogError):
        log.record(_rule(), {})


def test_context_manager_closes_on_exit(tmp_path):
    p = tmp_path / "f.jsonl"
    with FiringLog(str(p)) as log:
        log.record(_rule(), {"fires": 1})
    with pytest.raises(FiringLogError):
        log.record(_rule(), {})


@pytest.mark.skipif(not hasattr(os, "fork"), reason="fork is POSIX-only")
def test_a_forked_child_is_refused_rather_than_reusing_the_fd_and_lock(tmp_path):
    log = FiringLog(str(tmp_path / "f.jsonl"))
    read_fd, write_fd = os.pipe()

    pid = os.fork()
    if pid == 0:
        os.close(read_fd)
        try:
            log.record(_rule(), {})
            os.write(write_fd, b"NO_ERROR")
        except FiringLogError:
            os.write(write_fd, b"REFUSED")
        except BaseException:
            os.write(write_fd, b"OTHER")
        finally:
            os._exit(0)

    os.close(write_fd)
    status = _waitpid_bounded(pid)
    result = os.read(read_fd, 100)
    os.close(read_fd)

    assert result == b"REFUSED"
    assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0


@pytest.mark.skipif(not hasattr(os, "fork"), reason="fork is POSIX-only")
def test_a_forked_child_calling_close_is_refused_not_deadlocked(tmp_path):
    # The bug this pins: close() used to take self._lock unconditionally. A
    # fork mid-record (lock held by the thread that no longer exists in the
    # child) left the child's copy of that lock permanently acquired, so a
    # child that called close() hung forever instead of being refused.
    log = FiringLog(str(tmp_path / "f.jsonl"))
    read_fd, write_fd = os.pipe()
    log._lock.acquire()  # simulate a fork happening mid-record

    pid = os.fork()
    if pid == 0:
        os.close(read_fd)
        try:
            log.close()
            os.write(write_fd, b"NO_ERROR")
        except FiringLogError:
            os.write(write_fd, b"REFUSED")
        except BaseException:
            os.write(write_fd, b"OTHER")
        finally:
            os._exit(0)

    log._lock.release()
    os.close(write_fd)
    status = _waitpid_bounded(pid)
    result = os.read(read_fd, 100)
    os.close(read_fd)

    assert result == b"REFUSED"
    assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0


class _DelegatingOS:
    """Delegates every attribute except `write` to the real os module."""

    def __getattr__(self, name):
        return getattr(os, name)


def test_a_write_failure_raises_visibly(tmp_path, monkeypatch):
    import pyteman.firing as firing_module

    class FailingOS(_DelegatingOS):
        def write(self, fd, data):
            raise OSError("disk full")

    monkeypatch.setattr(firing_module, "os", FailingOS())
    log = FiringLog(str(tmp_path / "f.jsonl"))
    with pytest.raises(FiringLogError, match="disk full"):
        log.record(_rule(), {})


def test_a_write_failure_poisons_the_log_so_later_records_fail_closed(tmp_path, monkeypatch):
    import pyteman.firing as firing_module

    class FailOnceOS(_DelegatingOS):
        def __init__(self):
            self.write_calls = 0

        def write(self, fd, data):
            self.write_calls += 1
            if self.write_calls == 1:
                raise OSError("disk full")
            return os.write(fd, data)

    stub = FailOnceOS()
    monkeypatch.setattr(firing_module, "os", stub)
    log = FiringLog(str(tmp_path / "f.jsonl"))
    with pytest.raises(FiringLogError, match="disk full"):
        log.record(_rule(), {"fires": 1})

    # The underlying os.write would now succeed (this is call #2), but a
    # poisoned instance must refuse rather than append past its own
    # unknown partial tail from the failed first attempt.
    with pytest.raises(FiringLogError, match="closed"):
        log.record(_rule(), {"fires": 2})
    assert stub.write_calls == 1


def test_a_short_write_is_retried_until_the_whole_line_lands(tmp_path, monkeypatch):
    import pyteman.firing as firing_module

    p = tmp_path / "f.jsonl"
    real_write = os.write
    calls = []

    class ShortWriteOS(_DelegatingOS):
        def write(self, fd, data):
            data = bytes(data)
            calls.append(len(data))
            return real_write(fd, data[:3])  # force a short write every call

    # Patched before the instance exists: FiringLog snapshots os.write in
    # __init__ (so a rule on os.write can't re-enter its own logger), which
    # means a stub installed afterwards would never be seen.
    monkeypatch.setattr(firing_module, "os", ShortWriteOS())
    log = FiringLog(str(p))
    log.record(_rule(), {"fires": 1})
    log.close()

    lines = p.read_text().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])  # the reassembled line is still whole, valid JSON
    assert rec["seq"] == 1
    assert len(calls) > 1, "the write was never actually forced short"


def test_init_wraps_an_open_failure_in_a_firing_log_error(tmp_path, monkeypatch):
    import pyteman.firing as firing_module

    class FailingOpenOS(_DelegatingOS):
        def open(self, *args, **kwargs):
            raise OSError("permission denied")

    monkeypatch.setattr(firing_module, "os", FailingOpenOS())
    with pytest.raises(FiringLogError, match="permission denied"):
        FiringLog(str(tmp_path / "f.jsonl"))


def test_a_lock_failure_raises_a_firing_log_error(tmp_path, monkeypatch):
    log = FiringLog(str(tmp_path / "f.jsonl"))

    def failing_flock(fd, op):
        raise OSError("lock failed")

    monkeypatch.setattr(log, "_flock", failing_flock)
    with pytest.raises(FiringLogError, match="lock failed"):
        log.record(_rule(), {"fires": 1})


def test_an_unlock_failure_poisons_the_log_and_is_not_silently_swallowed(tmp_path, monkeypatch):
    # Peer-reproduced probe: only the LOCK_UN call raises OSError while the
    # write itself succeeds. record() used to return None (success) with
    # _closed left False, leaving the flock possibly still held against
    # every other writer to this path while the caller believed it worked.
    log = FiringLog(str(tmp_path / "f.jsonl"))
    real_flock = log._flock

    def flaky_unlock(fd, op):
        if op == log._lock_un:
            raise OSError("EIO")
        return real_flock(fd, op)

    monkeypatch.setattr(log, "_flock", flaky_unlock)
    with pytest.raises(FiringLogError, match="unlock failed"):
        log.record(_rule(), {"fires": 1})

    assert log._closed, "an unlock failure must poison the instance, not silently succeed"
    with pytest.raises(FiringLogError, match="closed"):
        log.record(_rule(), {"fires": 2})

    # The line the write itself produced is unaffected; only this
    # instance's ability to append further is what the unlock failure costs.
    lines = (tmp_path / "f.jsonl").read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["seq"] == 1


def test_a_write_failure_survives_a_close_failure_and_annotates_it(tmp_path, monkeypatch):
    # The bug this pins: the old cleanup code's unguarded os.close() in the
    # write-failure branch could raise and replace the pending FiringLogError
    # entirely, propagating a bare close() OSError instead of the write
    # failure that actually caused the poisoning.
    import pyteman.firing as firing_module

    class FailWriteAndCloseOS(_DelegatingOS):
        def write(self, fd, data):
            raise OSError("disk full")

        def close(self, fd):
            raise OSError("EIO on close")

    monkeypatch.setattr(firing_module, "os", FailWriteAndCloseOS())
    log = FiringLog(str(tmp_path / "f.jsonl"))
    with pytest.raises(FiringLogError, match="disk full") as excinfo:
        log.record(_rule(), {"fires": 1})

    assert log._closed, "a write failure must still poison the instance even if closing the fd also fails"
    notes = getattr(excinfo.value, "__notes__", [])
    assert any("closing the firing log fd failed" in n for n in notes), (
        "the close() failure during poisoning must be annotated, not silently dropped"
    )
    with pytest.raises(FiringLogError, match="closed"):
        log.record(_rule(), {"fires": 2})


@pytest.mark.parametrize("exc_type", [KeyboardInterrupt, SystemExit])
def test_an_interruption_during_write_propagates_untranslated_and_releases_the_lock(
        tmp_path, monkeypatch, exc_type):
    # Peer-reproduced probe: only `except FiringLogError` guarded the write,
    # so a BaseException _write_all doesn't itself raise -- KeyboardInterrupt,
    # SystemExit, a signal handler's exception -- skipped the unlock attempt
    # and poisoning entirely, leaving the flock held and _closed False after
    # the caller caught it.
    import pyteman.firing as firing_module

    def raising_write_all(fd, data, write):
        raise exc_type

    monkeypatch.setattr(firing_module, "_write_all", raising_write_all)
    p = tmp_path / "f.jsonl"
    log = FiringLog(str(p))
    with pytest.raises(exc_type):
        log.record(_rule(), {"fires": 1})

    assert log._closed, "an interruption during the write must still poison the instance"

    # The lock is only actually proven released by a second instance
    # acquiring it non-blocking; a poisoned _closed flag alone doesn't show
    # the underlying flock was let go.
    second = FiringLog(str(p))
    fcntl.flock(second._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    second.close()


@pytest.mark.parametrize("exc_type", [KeyboardInterrupt, SystemExit])
def test_an_interruption_during_unlock_propagates_untranslated_and_releases_the_lock(
        tmp_path, monkeypatch, exc_type):
    # Same bug, one step later: only `except OSError` guarded the unlock
    # call, so an interruption during LOCK_UN itself skipped poisoning too,
    # leaving the flock held and _closed False even though the write already
    # succeeded and the caller caught the interruption.
    p = tmp_path / "f.jsonl"
    log = FiringLog(str(p))
    real_flock = log._flock

    def flaky_unlock(fd, op):
        if op == log._lock_un:
            raise exc_type
        return real_flock(fd, op)

    monkeypatch.setattr(log, "_flock", flaky_unlock)
    with pytest.raises(exc_type):
        log.record(_rule(), {"fires": 1})

    assert log._closed, "an interruption during unlock must still poison the instance"

    second = FiringLog(str(p))
    fcntl.flock(second._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    second.close()

    # The write itself went through fine before the unlock was interrupted.
    lines = p.read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["seq"] == 1


def test_an_interruption_during_lock_acquisition_fails_closed_and_releases_the_fd(
        tmp_path, monkeypatch):
    # The acquire step is not exempt either: an interruption right as flock()
    # returns must not leave the lock's state uncertain (actually taken at
    # the OS level, but with nothing in this process having attempted to
    # release it). Fail closed the same way as write/unlock, and preserve
    # the interruption's own identity.
    p = tmp_path / "f.jsonl"
    log = FiringLog(str(p))
    real_flock = log._flock

    def flaky_acquire(fd, op):
        if op == log._lock_ex:
            raise KeyboardInterrupt
        return real_flock(fd, op)

    monkeypatch.setattr(log, "_flock", flaky_acquire)
    with pytest.raises(KeyboardInterrupt):
        log.record(_rule(), {"fires": 1})

    assert log._closed, "an interruption during lock acquisition must still fail closed"
    assert p.read_text() == "", "nothing should have been written if acquisition never returned"

    second = FiringLog(str(p))
    fcntl.flock(second._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    second.close()


def test_a_write_failure_survives_an_unlock_interruption_and_preserves_the_write_error(
        tmp_path, monkeypatch):
    # The write fails first with a normal OSError, wrapped into
    # FiringLogError; the unlock step is then interrupted by a BaseException
    # that is not an OSError. The write's FiringLogError -- the true primary
    # -- is what record() raises; the interruption is annotated onto it as a
    # note, never promoted over it. The fd must still be freed either way.
    import pyteman.firing as firing_module

    class FailingOS(_DelegatingOS):
        def write(self, fd, data):
            raise OSError("disk full")

    monkeypatch.setattr(firing_module, "os", FailingOS())
    p = tmp_path / "f.jsonl"
    log = FiringLog(str(p))
    real_flock = log._flock

    def flaky_unlock(fd, op):
        if op == log._lock_un:
            raise KeyboardInterrupt
        return real_flock(fd, op)

    monkeypatch.setattr(log, "_flock", flaky_unlock)
    with pytest.raises(FiringLogError, match="disk full") as excinfo:
        log.record(_rule(), {"fires": 1})

    assert log._closed
    notes = getattr(excinfo.value, "__notes__", [])
    assert any("KeyboardInterrupt" in n for n in notes), (
        "the unlock interruption must be annotated onto the write failure, not dropped"
    )

    second = FiringLog(str(p))
    fcntl.flock(second._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    second.close()


def test_many_threads_in_one_instance_get_unique_contiguous_seq(tmp_path):
    p = tmp_path / "f.jsonl"
    log = FiringLog(str(p))
    n = 100
    errors = []

    def one(i):
        try:
            log.record(_rule(), {"fires": i})
        except BaseException as exc:
            errors.append(exc)

    run_threads([lambda i=i: one(i) for i in range(n)])
    log.close()

    assert errors == []
    lines = [json.loads(l) for l in p.read_text().splitlines()]
    assert len(lines) == n
    assert sorted(l["seq"] for l in lines) == list(range(1, n + 1))


def test_close_racing_a_record_is_caught_not_silently_written(tmp_path, monkeypatch):
    # Pins the closed-check race a prior review found: record() used to
    # check self._closed only once, before the lock. Force close() to run
    # in another thread at exactly that window -- the threading.current_thread()
    # call already sits there, after the outer check and before the lock.
    import pyteman.firing as firing_module

    p = tmp_path / "f.jsonl"
    log = FiringLog(str(p))
    real_current_thread = threading.current_thread
    fired = threading.Event()

    def hook():
        if not fired.is_set():
            fired.set()
            closer = threading.Thread(target=log.close)
            closer.start()
            closer.join(JOIN_TIMEOUT)
            assert not closer.is_alive(), "close() did not finish inside the window"
        return real_current_thread()

    monkeypatch.setattr(firing_module.threading, "current_thread", hook)

    with pytest.raises(FiringLogError):
        log.record(_rule(), {"fires": 1})
    assert fired.is_set(), "the hook never fired; the test proves nothing"


# The child runs in its own interpreter because activate() patches the real
# os module process-wide; doing that in-process would instrument pytest's own
# I/O for the rest of the session.
_SELF_INSTRUMENTATION_CHILD = r"""
import errno
import json
import os
import sys

from pyteman.firing import FiringLog
from pyteman.patcher import activate
from pyteman.rules import Rule

log_path, scratch_path = sys.argv[1], sys.argv[2]


def rule(id, symbol):
    # sleep 0 fires and logs, then lets the real call proceed; an action that
    # replaced the return value would break every write in the interpreter.
    return Rule(id=id, module="os", symbol=symbol, event="entry",
                action={"kind": "sleep", "ms": 0})


def read_records():
    with open(log_path) as fh:
        return [json.loads(l) for l in fh.read().splitlines()]


log = FiringLog(log_path)
log_fd = log._fd
scratch_fd = os.open(scratch_path, os.O_WRONLY | os.O_CREAT, 0o644)

activate([rule("w", "write"), rule("c", "close")], log=log, modules=("os",))

# 1. The logger's own write must not fire the os.write rule. If it did, this
#    call would re-enter record() under a lock record() already holds and
#    never return, and the parent's timeout is what catches that.
log.record(Rule(id="marker", module="m", symbol="f", event="entry",
                action={"kind": "return_none"}), {"fires": 1})
after_marker = read_records()

# 2. Non-vacuity: the same rule must still fire for the program under test.
os.write(scratch_fd, b"x")
os.close(scratch_fd)
after_app_io = read_records()

# 3. close() must actually close the fd, not leave it open. Before the
#    snapshot, a rule on os.close made record() refuse (_closed is set by
#    then) and the fd leaked with its finalizer already detached.
log.close()
try:
    os.fstat(log_fd)
    fd_state = "open"
except OSError as exc:
    if exc.errno != errno.EBADF:
        raise
    fd_state = "closed"

print(json.dumps({
    "marker_rules": [r["rule"] for r in after_marker],
    "app_rules": sorted({r["rule"] for r in after_app_io}),
    "fd_state": fd_state,
}))
"""


def test_the_logger_does_not_instrument_its_own_io(tmp_path):
    # Bounded on purpose: every failure this pins is a hang or a leak, and a
    # hang must turn this test red rather than stall the suite.
    log_path = tmp_path / "f.jsonl"
    scratch = tmp_path / "scratch.bin"
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _SELF_INSTRUMENTATION_CHILD, str(log_path), str(scratch)],
            capture_output=True, text=True, timeout=SELF_INSTRUMENTATION_TIMEOUT)
    except subprocess.TimeoutExpired:
        pytest.fail(
            f"the child hung for {SELF_INSTRUMENTATION_TIMEOUT}s: the logger "
            "re-entered its own record() through a patched os.write")

    assert proc.returncode == 0, (
        f"child failed (rc={proc.returncode}); stderr:\n{proc.stderr}")
    result = json.loads(proc.stdout.splitlines()[-1])

    assert result["marker_rules"] == ["marker"], (
        "the logger's own write fired the os.write rule; its I/O is being "
        f"instrumented by the rules it is logging: {result['marker_rules']}")
    assert "w" in result["app_rules"] and "c" in result["app_rules"], (
        "os.write/os.close stopped firing for the program under test, so the "
        f"first assertion proves nothing: {result['app_rules']}")
    assert result["fd_state"] == "closed", (
        "close() returned without closing the fd while os.close was patched")


def test_a_dropped_instance_without_close_does_not_leak_its_fd(tmp_path):
    if not os.path.isdir("/proc/self/fd"):
        pytest.skip("fd-count probe needs /proc/self/fd (Linux)")

    def open_fds():
        return len(os.listdir("/proc/self/fd"))

    before = open_fds()
    for i in range(20):
        log = FiringLog(str(tmp_path / f"f{i}.jsonl"))
        log.record(_rule(), {"fires": 1})
        del log
    gc.collect()
    after = open_fds()
    assert after <= before + 1, (
        f"fd count grew from {before} to {after} across 20 unclosed instances; "
        "the finalizer did not run")


def test_close_disarms_the_finalizer_so_gc_does_not_close_a_recycled_fd(tmp_path):
    if not os.path.isdir("/proc/self/fd"):
        pytest.skip("fd-recycling probe needs /proc/self/fd (Linux)")

    log = FiringLog(str(tmp_path / "f.jsonl"))
    log.close()
    other_fd = os.open(str(tmp_path / "other"), os.O_WRONLY | os.O_CREAT, 0o644)
    try:
        del log
        gc.collect()
        os.write(other_fd, b"still alive")  # raises EBADF if wrongly closed
    finally:
        os.close(other_fd)
