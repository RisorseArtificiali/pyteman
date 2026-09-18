"""Per-attempt provenance: TASK-22.2 / TASK-49.

``run_matrix`` records an attempt in the ``attempts`` table before it creates
that attempt's directory or calls back into user code, and commits that record
before either of those things happens. A process killed at any point after
that leaves its row exactly as it was: ``status='running'``, with nothing
here ever reinterpreting that as "dead" or "orphaned". These tests pin that
guarantee at the three points where a kill can land: before the attempt's
directory exists, after it exists but before the callback starts, and while
the callback is running. Each one also checks that a retry afterwards mints a
new row and directory rather than touching the old ones.

The three kill tests drive real subprocesses ordered with an ``Event``, the
same pattern ``test_matrix_concurrency.py`` uses and for the same reason: the
property under test is about a process dying mid-flight, which a thread
cannot stand in for.
"""

import multiprocessing as mp
import os
import signal
import sqlite3
import sys
import time
from types import SimpleNamespace

import pytest

from pyteman.runner.matrix import (
    MatrixStorageError,
    _attempt_dir,
    _experiment_key,
    _freeze,
    _prepare_experiment_dir,
    run_matrix,
)
from test_matrix_identity import query

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="the kill tests need SIGKILL, which win32 does not have; skipped "
           "there for the same reason test_matrix_concurrency.py is")

TIMEOUT = 30
EXPERIMENT = {"harness": "1.0"}
CELL = {"id": "c", "params": {}}


def _context():
    # spawn, not fork: a forked child would inherit descriptors and any
    # in-process monkeypatch state from whichever test ran before it, which is
    # exactly what must not leak into a process this test is about to kill.
    return mp.get_context("spawn")


def _wait_for_processes(procs):
    for p in procs:
        p.join(TIMEOUT)
        if p.is_alive():
            p.kill()
            p.join(10)


def _attempts(db):
    return query(db, "SELECT attempt_id, status, artifact_dir, result_json FROM attempts "
                     "ORDER BY started_at")


def _results(db):
    return query(db, "SELECT cell_id, status FROM results")


def test_a_successful_attempt_finalizes_its_own_row_to_done(tmp_path):
    db = str(tmp_path / "r.db")
    out = run_matrix([CELL], lambda cell, adir: {"ok": True}, db,
                      str(tmp_path / "art"), experiment=EXPERIMENT)

    assert out == [{"cell_id": "c", "status": "done", "result": {"ok": True}}]
    rows = _attempts(db)
    assert len(rows) == 1
    attempt_id, status, artifact_dir, result_json = rows[0]
    assert status == "done"
    assert result_json == '{"ok": true}'
    assert os.path.isdir(artifact_dir)


def test_a_raising_callback_finalizes_the_same_row_to_failed(tmp_path):
    db = str(tmp_path / "r.db")

    def run_cell(cell, adir):
        raise ValueError("boom")

    out = run_matrix([CELL], run_cell, db, str(tmp_path / "art"),
                      experiment=EXPERIMENT)

    assert out[0]["status"] == "failed"
    rows = _attempts(db)
    assert len(rows) == 1
    assert rows[0][1] == "failed"
    assert "boom" in rows[0][3]
    # The directory a failed cell already claimed is left in place: nothing
    # here deletes an attempt's artifacts, whatever the outcome.
    assert os.path.isdir(rows[0][2])


def test_a_directory_collision_is_this_attempts_own_failure_not_a_matrix_abort(
        tmp_path, monkeypatch):
    """Caught synchronously, in the run that produced it, unlike a kill.

    A killed process leaves its row at ``running`` forever, because nothing
    later ever ran to say otherwise. A directory collision is the opposite: it
    is witnessed directly, right here, so it is finalised at once as this
    attempt's own failure rather than left unresolved.
    """
    root = str(tmp_path / "art")
    db = str(tmp_path / "r.db")
    experiment_dir = _prepare_experiment_dir(os.path.abspath(root),
                                              _experiment_key(EXPERIMENT))
    frozen = _freeze(CELL)
    token = "aaaaaaaaaaaa"
    collision_dir = _attempt_dir(experiment_dir, frozen, token)
    os.makedirs(collision_dir)

    monkeypatch.setattr("pyteman.runner.matrix.uuid.uuid4",
                         lambda: SimpleNamespace(hex=token))

    out = run_matrix([CELL], lambda cell, adir: {"ok": True}, db, root,
                      experiment=EXPERIMENT)

    assert out[0]["status"] == "failed"
    assert "attempt directory could not be created" in out[0]["result"]["error"]
    rows = _attempts(db)
    assert len(rows) == 1
    assert rows[0][0] == token
    assert rows[0][1] == "failed"
    assert _results(db) == [("c", "failed")]


def _victim_killed_before_its_directory_exists(db, root, entered):
    real_makedirs = os.makedirs

    def blocked(path, *a, exist_ok=False, **k):
        # ``_prepare_experiment_dir`` calls ``os.makedirs`` too, with
        # ``exist_ok=True``; only the attempt's own call, made without it,
        # is the one this test means to block.
        if exist_ok:
            return real_makedirs(path, *a, exist_ok=exist_ok, **k)
        entered.set()
        time.sleep(300)

    os.makedirs = blocked
    run_matrix([CELL], lambda cell, adir: {"ok": True}, db, root,
                experiment=EXPERIMENT)


def _victim_killed_after_its_directory_exists(db, root, entered):
    real_makedirs = os.makedirs

    def blocked(path, *a, exist_ok=False, **k):
        if exist_ok:
            return real_makedirs(path, *a, exist_ok=exist_ok, **k)
        real_makedirs(path, *a, **k)
        entered.set()
        time.sleep(300)

    os.makedirs = blocked
    run_matrix([CELL], lambda cell, adir: {"ok": True}, db, root,
                experiment=EXPERIMENT)


def _victim_killed_mid_callback(db, root, entered):
    def run_cell(cell, adir):
        entered.set()
        time.sleep(300)

    run_matrix([CELL], run_cell, db, root, experiment=EXPERIMENT)


def _kill_and_retry(tmp_path, victim_target, dir_state_after_kill):
    db = str(tmp_path / "r.db")
    root = str(tmp_path / "art")
    ctx = _context()
    entered = ctx.Event()
    victim = ctx.Process(target=victim_target, args=(db, root, entered))
    try:
        victim.start()
        assert entered.wait(TIMEOUT), "the victim never reached the blocked point"
        os.kill(victim.pid, signal.SIGKILL)
        victim.join(TIMEOUT)
        assert victim.exitcode == -signal.SIGKILL
    finally:
        _wait_for_processes([victim])

    rows_before = _attempts(db)
    assert len(rows_before) == 1
    old_attempt_id, old_status, old_dir, old_result_json = rows_before[0]
    assert old_status == "running"
    assert old_result_json is None
    dir_state_after_kill(old_dir)

    out = run_matrix([CELL], lambda cell, adir: {"ran_by": "fresh"}, db, root,
                      experiment=EXPERIMENT)
    assert out == [{"cell_id": "c", "status": "done",
                     "result": {"ran_by": "fresh"}}]

    rows_after = _attempts(db)
    assert len(rows_after) == 2
    by_id = {r[0]: r for r in rows_after}
    # The killed attempt's row survives untouched: nothing here inferred a
    # cause for it or rewrote it once the retry succeeded.
    assert by_id[old_attempt_id] == rows_before[0]
    new_row = by_id[[i for i in by_id if i != old_attempt_id][0]]
    assert new_row[1] == "done"
    assert new_row[2] != old_dir
    assert _results(db) == [("c", "done")]


def test_a_process_killed_before_its_directory_exists_leaves_its_row_running(
        tmp_path):
    def check(old_dir):
        assert not os.path.exists(old_dir)

    _kill_and_retry(tmp_path, _victim_killed_before_its_directory_exists, check)


def test_a_process_killed_after_its_directory_exists_leaves_its_row_running(
        tmp_path):
    def check(old_dir):
        assert os.path.isdir(old_dir)
        assert os.listdir(old_dir) == []

    _kill_and_retry(tmp_path, _victim_killed_after_its_directory_exists, check)


def test_a_process_killed_mid_callback_leaves_its_row_running(tmp_path):
    def check(old_dir):
        assert os.path.isdir(old_dir)

    _kill_and_retry(tmp_path, _victim_killed_mid_callback, check)


def test_a_skipped_cell_creates_no_attempt_row(tmp_path):
    """Resuming a done cell must not mint an attempt for work that never runs.

    An attempt row exists to say "this ran, here, starting at this time"; a
    skip is the opposite of that, so nothing here should write one.
    """
    db = str(tmp_path / "r.db")
    root = str(tmp_path / "art")
    run_matrix([CELL], lambda cell, adir: {"ok": True}, db, root, experiment=EXPERIMENT)
    assert len(_attempts(db)) == 1

    out = run_matrix([CELL], lambda cell, adir: {"ok": "must not run"}, db, root,
                      experiment=EXPERIMENT)

    assert out == [{"cell_id": "c", "status": "skipped"}]
    assert len(_attempts(db)) == 1


def test_a_finish_transaction_failure_leaves_the_start_row_running(tmp_path):
    """The finish write can fail after the cell already ran and produced a result.

    The start row committed by ``_begin_attempt`` before the callback ran is
    the only durable trace of the attempt if the finish write then fails; this
    pins that it survives exactly as it was, at ``status='running'``, and that
    the accompanying ``results``/``attempts`` writes both roll back together.
    """
    db = str(tmp_path / "r.db")
    root = str(tmp_path / "art")

    def run_cell(cell, adir):
        blocker = sqlite3.connect(db)
        try:
            blocker.execute(
                "CREATE TRIGGER block_finish BEFORE UPDATE ON attempts "
                "BEGIN SELECT RAISE(ABORT, 'forced finish failure'); END")
        finally:
            blocker.close()
        return {"ok": True}

    with pytest.raises(MatrixStorageError) as excinfo:
        run_matrix([CELL], run_cell, db, root, experiment=EXPERIMENT)

    message = str(excinfo.value)
    assert "forced finish failure" in message
    assert "status='running'" in message

    rows = _attempts(db)
    assert len(rows) == 1
    attempt_id, status, artifact_dir, result_json = rows[0]
    assert status == "running"
    assert result_json is None
    assert f"Attempt {attempt_id!r}" in message
    assert artifact_dir in message
    assert _results(db) == []


def test_a_concurrently_deleted_attempts_row_stops_the_finish_write(tmp_path):
    """The finish UPDATE must check it actually matched a row.

    A second connection deleting the attempt's own row between the start
    write and the finish write is the same class of concurrent-writer race
    ``_adopt_stored_rows`` already guards against for its own UPDATE: the
    finish write must not silently match zero rows and then commit a results
    row for an attempt nothing now attests to.
    """
    db = str(tmp_path / "r.db")
    root = str(tmp_path / "art")

    def run_cell(cell, adir):
        rival = sqlite3.connect(db)
        try:
            rival.execute(
                "DELETE FROM attempts WHERE cell_id=? AND status='running'",
                (cell["id"],))
            rival.commit()
        finally:
            rival.close()
        return {"ok": True}

    with pytest.raises(MatrixStorageError) as excinfo:
        run_matrix([CELL], run_cell, db, root, experiment=EXPERIMENT)

    message = str(excinfo.value)
    assert "vanished" in message
    assert CELL["id"] in message
    assert _attempts(db) == []
    assert _results(db) == []


def test_a_duplicate_attempt_token_is_refused_not_overwritten(tmp_path, monkeypatch):
    """A token collision at insert time must not replace the row already there.

    ``_begin_attempt`` uses a plain ``INSERT``, not ``INSERT OR REPLACE``,
    because a fresh ``uuid4`` colliding with an existing row is not this run's
    name to reuse; the existing row's history would otherwise be silently
    discarded. The colliding row is minted by a real ``_begin_attempt`` call
    rather than a hand-built literal, so it stays whatever production actually
    writes rather than a copy of that statement that could drift from it.
    """
    db = str(tmp_path / "r.db")
    root = str(tmp_path / "art")
    token = "bbbbbbbbbbbb"

    monkeypatch.setattr("pyteman.runner.matrix.uuid.uuid4",
                         lambda: SimpleNamespace(hex=token))

    run_matrix([{"id": "first", "params": {}}], lambda cell, adir: {"first": True},
               db, root, experiment=EXPERIMENT)
    original_row = _attempts(db)[0]
    assert original_row[0] == token, "the fixture must actually mint this token"

    with pytest.raises(MatrixStorageError) as excinfo:
        run_matrix([CELL], lambda cell, adir: {"ok": True}, db, root,
                    experiment=EXPERIMENT)

    assert "could not be recorded as a starting attempt" in str(excinfo.value)
    rows = _attempts(db)
    assert len(rows) == 1
    assert rows[0] == original_row, (
        "the pre-existing row must survive untouched, not be replaced")
    assert _results(db) == [("first", "done")]
