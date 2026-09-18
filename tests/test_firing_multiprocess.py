# tests/test_firing_multiprocess.py
"""Cross-process firing-log writers: LOG-01's multi-process claim.

Every test here uses spawn, not fork: a forked child inherits this log's
open fd and lock mid-operation, which FiringLog.record refuses outright (see
test_firing.py's fork-refusal test). spawn is the supported path, with each
child opening its own FiringLog instance against the shared path.
"""
import json
import sys
import time

import pytest

from pyteman.firing import FiringLog
from pyteman.rules import Rule
from test_matrix_attempts import _context

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="the firing log requires fcntl, which win32 does not have; "
           "skipped there for the same reason test_matrix_concurrency.py is")

TIMEOUT = 30
RULE = Rule(id="r", module="m", symbol="f", event="entry",
            action={"kind": "return_none"})


def _join_all_bounded(procs, timeout, kill_timeout=5):
    """proc.join(timeout) for each, escalating terminate()/SIGTERM to kill()/SIGKILL.

    A hung child (e.g. the deadlock defect #2 guards against) must fail this
    test outright, not leave an un-reaped process behind or hang the runner.
    terminate() sends SIGTERM, which a child can install a handler for and
    ignore, so a process still alive after that gets escalated to kill()
    (SIGKILL, not catchable) before this gives up.
    """
    deadline = time.monotonic() + timeout
    for proc in procs:
        proc.join(max(0, deadline - time.monotonic()))

    hung = [proc for proc in procs if proc.is_alive()]
    for proc in hung:
        proc.terminate()
    for proc in hung:
        proc.join(kill_timeout)

    still_hung = [proc for proc in procs if proc.is_alive()]
    for proc in still_hung:
        proc.kill()
    for proc in still_hung:
        proc.join(kill_timeout)

    unreaped = [proc.pid for proc in procs if proc.is_alive()]
    if unreaped:
        pytest.fail(f"process(es) {unreaped} still alive after SIGTERM and SIGKILL; giving up")
    if hung:
        pytest.fail(f"{len(hung)} process(es) did not exit within {timeout}s; terminated/killed")

    bad = [(proc.pid, proc.exitcode) for proc in procs if proc.exitcode != 0]
    if bad:
        pytest.fail(f"process(es) exited nonzero: {bad}")


def _writer(path, n, note):
    log = FiringLog(path)
    try:
        for i in range(n):
            log.record(RULE, {"fires": i + 1}, note=note)
    finally:
        log.close()


def _short_write_writer(path, note, barrier):
    # A picklable module-level target (spawn requires it): stubs os.write to
    # split every write into short chunks, then uses the barrier to make it
    # likely both processes are mid-record at the same moment. This is an
    # empirical, not a deterministic, technique -- it reliably reproduces
    # the flock-removal mutation under observed scheduling, but it does not
    # guarantee the exact interleaving order of the individual chunks the
    # way the closed-race test's forced monkeypatch hook does. If flock is
    # not actually serializing the write-until-complete loop, these chunks
    # can interleave in the file and the line stops being valid JSON.
    import os

    import pyteman.firing as firing_module

    real_write = os.write

    class ShortWriteOS:
        def __getattr__(self, name):
            return getattr(os, name)

        def write(self, fd, data):
            n = real_write(fd, bytes(data)[:4])
            time.sleep(0.005)
            return n

    firing_module.os = ShortWriteOS()
    log = FiringLog(path)
    barrier.wait(timeout=TIMEOUT)
    try:
        log.record(RULE, {"fires": 1}, note=note)
    finally:
        log.close()


def _ignore_sigterm_and_hang():
    import signal

    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    while True:
        time.sleep(1)


def test_two_processes_appending_concurrently_never_corrupt_a_line(tmp_path):
    p = str(tmp_path / "f.jsonl")
    ctx = _context()
    n = 200
    procs = [ctx.Process(target=_writer, args=(p, n, "x")) for _ in range(2)]
    for proc in procs:
        proc.start()
    _join_all_bounded(procs, TIMEOUT)

    lines = open(p).read().splitlines()
    assert len(lines) == 2 * n
    records = [json.loads(l) for l in lines]  # raises if any line is corrupt
    keys = {(r["instance"], r["pid"], r["seq"]) for r in records}
    assert len(keys) == len(records)
    assert len({r["pid"] for r in records}) == 2


def test_a_payload_past_the_old_assumed_atomic_threshold_still_lands_whole(tmp_path):
    # 4096 bytes was the old, wrong PIPE_BUF-for-regular-files assumption;
    # this proves flock, not payload size, is what protects a line here.
    p = str(tmp_path / "f.jsonl")
    big_note = "x" * 8192
    ctx = _context()
    procs = [ctx.Process(target=_writer, args=(p, 20, big_note)) for _ in range(2)]
    for proc in procs:
        proc.start()
    _join_all_bounded(procs, TIMEOUT)

    lines = open(p).read().splitlines()
    assert len(lines) == 40
    for l in lines:
        rec = json.loads(l)  # raises if the line was split/interleaved
        assert rec["note"] == big_note


def test_flock_prevents_interleaved_short_writes_across_processes(tmp_path):
    p = str(tmp_path / "f.jsonl")
    ctx = _context()
    barrier = ctx.Barrier(2)
    notes = ["a" * 500, "b" * 500]
    procs = [ctx.Process(target=_short_write_writer, args=(p, notes[i], barrier))
             for i in range(2)]
    for proc in procs:
        proc.start()
    _join_all_bounded(procs, TIMEOUT)

    lines = open(p).read().splitlines()
    assert len(lines) == 2
    seen = {json.loads(l)["note"] for l in lines}  # raises if a line was split/interleaved
    assert seen == set(notes)


def test_join_all_bounded_escalates_to_sigkill_for_a_child_that_ignores_sigterm():
    # Proves the SIGKILL escalation path: terminate() sends SIGTERM, which
    # this child explicitly ignores, so only kill() (SIGKILL) can reap it.
    # Without that escalation this test would hang the suite instead of
    # going red.
    ctx = _context()
    proc = ctx.Process(target=_ignore_sigterm_and_hang)
    proc.start()
    try:
        with pytest.raises(pytest.fail.Exception):
            _join_all_bounded([proc], timeout=1, kill_timeout=5)
        assert not proc.is_alive(), "SIGKILL escalation did not actually reap the child"
    finally:
        if proc.is_alive():
            proc.kill()
            proc.join(5)
