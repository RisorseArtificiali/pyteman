"""Exclusion between concurrent runners: RUN-04, the first tranche.

The defect these pin is not a crash. Two runners on one results db both ran the
same cell, both returned a result to their own caller with no error, and the db
kept one of them. The runner that lost was told its result had been recorded.

Every test here drives real processes rather than threads, because the property
is about separate interpreters holding separate sqlite connections, and orders
them with an Event rather than a sleep: a sleep long enough to pass today is a
test that passes for the wrong reason tomorrow. The exclusion test is paired
with one that disables the lock and shows both runners get through, so "the
second was refused" cannot be satisfied by a second runner that never started.

Every test that asserts the lock came back asserts it through
``_assert_the_lock_is_free_and_real``, which both takes the lock and shows the
next taker is refused. Acquiring alone would also succeed against a lock that
was never implemented, which is the shape these tests exist to rule out.
"""

import contextlib
import os
import pathlib
import signal
import sqlite3
import sys

import pytest

from pyteman.runner import lock as lock_module
from pyteman.runner.lock import MatrixLockError
from pyteman.runner.matrix import MatrixStorageError, run_matrix

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="every test here needs a lock the runner cannot take on win32, "
           "where it refuses to run at all; that refusal has no coverage on "
           "the platform it describes and is asserted from Linux instead, by "
           "making the fcntl import fail")

# Long enough that a loaded machine does not trip it, short enough that a
# genuinely stuck process is reported rather than hanging the suite.
TIMEOUT = 30

EXPERIMENT = {"harness": "1.0"}
CELL = {"id": "c", "params": {"x": 1}}


def _context():
    # spawn, not fork: a forked child would inherit the parent's descriptors,
    # including any lock it holds, which is the one thing these tests must not
    # let the harness fake.
    import multiprocessing as mp
    return mp.get_context("spawn")


def _wait_for_processes(procs):
    for p in procs:
        p.join(TIMEOUT)
        if p.is_alive():
            p.kill()
            p.join(10)


def _rows(db):
    con = sqlite3.connect(db)
    try:
        return list(con.execute("SELECT cell_id, status, result_json FROM results"))
    finally:
        con.close()


def _assert_the_lock_is_free_and_real(db):
    """The lock came back, and it is a lock rather than a no-op.

    Taking it has to succeed, and while it is held the next taker has to be
    refused. Without the second half this passes against a runner that never
    locked anything, which is exactly the state these tests came from.
    """
    fd = lock_module.acquire(db)
    try:
        assert os.fstat(fd) == os.stat(lock_module.lock_path(db))
        with pytest.raises(MatrixLockError):
            lock_module.acquire(db)
    finally:
        lock_module.release(fd)


def _child(tag, db, root, out, entered=None, release=None, disable_lock=False,
           hang=False):
    """One runner in its own interpreter, reporting how its run ended.

    Every child in this module is this function under different arguments: what
    varies between them is whether the callback waits, hangs, or returns at
    once, and whether exclusion is disabled first.
    """
    if disable_lock:
        # The control arm. With exclusion removed this runner gets through,
        # which is what makes the refusal in the paired test attributable to
        # the lock rather than to anything else about the setup. Replacing the
        # attribute matrix reads, rather than reaching into the lock module,
        # because the lock module is what the assertions use to check the
        # result and it has to keep working.
        from types import SimpleNamespace

        from pyteman.runner import matrix as matrix_module
        matrix_module._lock = SimpleNamespace(
            held=lambda results_db: contextlib.nullcontext())

    def run_cell(cell, adir):
        if entered is not None:
            entered.set()
        if hang:
            import time
            time.sleep(300)
        if release is not None:
            release.wait(TIMEOUT)
        return {"ran_by": tag}

    try:
        result = run_matrix([CELL], run_cell, db, root, experiment=EXPERIMENT)
        if out is not None:
            out.put((tag, "returned", result))
    except BaseException as e:
        if out is None:
            # Nobody is reading, so swallowing this would leave a child that
            # failed looking exactly like one that was killed on purpose.
            raise
        out.put((tag, type(e).__name__, str(e)))


def _outcomes(out, expected):
    got = {}
    for _ in range(expected):
        try:
            tag, kind, payload = out.get(timeout=TIMEOUT)
        except Exception as e:
            raise AssertionError(
                f"only {len(got)} of {expected} runners reported an outcome "
                f"within {TIMEOUT}s; got {got}") from e
        got[tag] = (kind, payload)
    return got


def _concurrent_pair(tmp_path, disable_lock):
    """Starts a holder, waits until it is provably inside the callback, then
    starts a second runner against the same db and reports both outcomes."""
    db = str(tmp_path / "results.db")
    root = str(tmp_path / "artifacts")
    ctx = _context()
    entered, release, out = ctx.Event(), ctx.Event(), ctx.Queue()
    holder = ctx.Process(target=_child,
                         args=("holder", db, root, out, entered, release))
    contender = ctx.Process(target=_child, args=("contender", db, root, out),
                            kwargs={"disable_lock": disable_lock})
    try:
        holder.start()
        assert entered.wait(TIMEOUT), "the holder never reached its callback"
        contender.start()
        contender.join(TIMEOUT)
        release.set()
        got = _outcomes(out, 2)
    finally:
        release.set()
        _wait_for_processes([holder, contender])
    return db, got


def test_a_second_runner_is_refused_while_the_first_is_inside_the_callback(tmp_path):
    db, got = _concurrent_pair(tmp_path, disable_lock=False)

    assert got["contender"][0] == "MatrixLockError"
    assert db in got["contender"][1]
    assert lock_module.lock_path(db) in got["contender"][1]

    # The refusal has to be the second runner being kept out, not both runners
    # dying. The holder ran to completion and its result is the one recorded.
    assert got["holder"][0] == "returned"
    assert got["holder"][1] == [{"cell_id": "c", "status": "done",
                                 "result": {"ran_by": "holder"}}]
    assert _rows(db) == [("c", "done", '{"ran_by": "holder"}')]


def test_without_the_lock_the_second_runner_gets_through(tmp_path):
    """The control for the test above, and the defect as it stood.

    Both runners execute the cell, both return success to their own caller,
    and the db keeps one result. Nothing reports a conflict.
    """
    db, got = _concurrent_pair(tmp_path, disable_lock=True)

    assert got["contender"][0] == "returned"
    assert got["holder"][0] == "returned"
    assert got["contender"][1] == [{"cell_id": "c", "status": "done",
                                    "result": {"ran_by": "contender"}}]
    assert len(_rows(db)) == 1


def test_a_second_acquire_in_one_process_fails_fast_instead_of_deadlocking(tmp_path):
    db = str(tmp_path / "results.db")
    fd = lock_module.acquire(db)
    try:
        # flock belongs to the open file description rather than to the
        # process, so this is refused exactly as another process would be.
        with pytest.raises(MatrixLockError):
            lock_module.acquire(db)
    finally:
        lock_module.release(fd)


def test_a_run_that_raises_leaves_the_lock_free(tmp_path):
    """An exception on the way up from inside the lock still releases it.

    The artifact root here is a regular file, so the failure comes from the
    filesystem rather than from the runner, which is the point: the release
    cannot depend on the run failing in a way the runner anticipated.
    """
    db = str(tmp_path / "results.db")
    not_a_directory = tmp_path / "blocked"
    not_a_directory.write_text("")

    with pytest.raises(NotADirectoryError):
        run_matrix([CELL], lambda cell, adir: {}, db, str(not_a_directory),
                   experiment=EXPERIMENT)

    _assert_the_lock_is_free_and_real(db)


def test_a_run_refused_before_it_starts_leaves_the_lock_file_and_nothing_else(tmp_path):
    """What a failed run is allowed to leave behind, stated as a test.

    The lock is taken before the artifact root is checked, so a run that fails
    that check has already created the db's parent directory and the lock file
    in it. That is the whole of what it leaves: no results db, and no
    experiment directory.
    """
    db = str(tmp_path / "fresh" / "nested" / "results.db")
    not_a_directory = tmp_path / "blocked"
    not_a_directory.write_text("")

    with pytest.raises(NotADirectoryError):
        run_matrix([CELL], lambda cell, adir: {}, db, str(not_a_directory),
                   experiment=EXPERIMENT)

    assert sorted(p.name for p in (tmp_path / "fresh" / "nested").iterdir()) == \
        ["results.db.lock"]

    # And a second refusal into the same place adds nothing: the directory was
    # already there and is left as it was, the lock file is reused rather than
    # replaced. That is why the contract says a failed run may leave these two
    # rather than that it does. Compared by inode and mode rather than by name,
    # since a name is the same whether the file was reused, truncated, or
    # unlinked and made again, which are the ways the claim could be lost.
    def _state():
        home = tmp_path / "fresh" / "nested"
        return sorted((p.name, p.stat().st_ino, p.stat().st_mode,
                       p.stat().st_size) for p in home.iterdir()), \
            (home.stat().st_ino, home.stat().st_mode)

    before = _state()
    with pytest.raises(NotADirectoryError):
        run_matrix([CELL], lambda cell, adir: {}, db, str(not_a_directory),
                   experiment=EXPERIMENT)
    assert _state() == before


def test_a_failing_callback_leaves_the_lock_free(tmp_path):
    db = str(tmp_path / "results.db")
    root = str(tmp_path / "artifacts")

    def explodes(cell, adir):
        raise ValueError("boom")

    out = run_matrix([CELL], explodes, db, root, experiment=EXPERIMENT)
    assert out[0]["status"] == "failed"

    _assert_the_lock_is_free_and_real(db)


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0,
                    reason="root writes to a read-only file, so the storage "
                           "failure this needs cannot be provoked")
def test_a_storage_failure_leaves_the_lock_free(tmp_path):
    """The path that raises from inside the per-cell write.

    The cell has already run when the row is refused, so this leaves the run
    through the narrowest exit there is, and the lock still has to come back.
    """
    db = str(tmp_path / "results.db")
    root = str(tmp_path / "artifacts")
    run_matrix([CELL], lambda cell, adir: {"x": 1}, db, root, experiment=EXPERIMENT)
    os.chmod(db, 0o444)

    try:
        with pytest.raises(MatrixStorageError):
            run_matrix([{"id": "c", "params": {"x": 2}}], lambda cell, adir: {"x": 2},
                       db, root, experiment=EXPERIMENT, on_mismatch="rerun")
    finally:
        os.chmod(db, 0o644)

    _assert_the_lock_is_free_and_real(db)


def test_a_runner_killed_outright_releases_the_lock_to_the_next_run(tmp_path):
    """SIGKILL, which no handler can intercept, so nothing tidied up on the
    way out. The next run has to acquire and finish without any intervention."""
    db = str(tmp_path / "results.db")
    root = str(tmp_path / "artifacts")
    ctx = _context()
    entered, out = ctx.Event(), ctx.Queue()
    victim = ctx.Process(target=_child, args=("victim", db, root, None, entered),
                         kwargs={"hang": True})
    fresh = ctx.Process(target=_child, args=("fresh", db, root, out))
    try:
        victim.start()
        assert entered.wait(TIMEOUT), "the victim never took the lock"
        # Refused while the victim is alive, so what the fresh run acquires
        # below is a lock that was genuinely held and then released by the
        # kill, rather than one nobody ever took.
        with pytest.raises(MatrixLockError):
            lock_module.acquire(db)

        os.kill(victim.pid, signal.SIGKILL)
        victim.join(TIMEOUT)
        assert victim.exitcode == -signal.SIGKILL

        fresh.start()
        fresh.join(TIMEOUT)
        got = _outcomes(out, 1)
    finally:
        _wait_for_processes([victim, fresh])

    assert got["fresh"][0] == "returned"
    assert got["fresh"][1] == [{"cell_id": "c", "status": "done",
                                "result": {"ran_by": "fresh"}}]
    # The cell the killed run never recorded is run again rather than skipped.
    assert _rows(db) == [("c", "done", '{"ran_by": "fresh"}')]


def test_two_names_for_one_database_contend(tmp_path, monkeypatch):
    """A symlink and a relative path are the same db, so they are one lock."""
    real = tmp_path / "real.db"
    real.write_bytes(b"")
    link = tmp_path / "link.db"
    link.symlink_to(real)
    monkeypatch.chdir(tmp_path)

    fd = lock_module.acquire(str(real))
    try:
        with pytest.raises(MatrixLockError):
            lock_module.acquire(str(link))
        with pytest.raises(MatrixLockError):
            lock_module.acquire("real.db")
    finally:
        lock_module.release(fd)


def test_the_path_types_sqlite_accepts_all_still_run(tmp_path):
    """bytes and Path reach sqlite unchanged, so the lock cannot refuse them.

    ``os.path.realpath`` returns the type it was given, so a bytes db would
    have failed on the text suffix the lock file appends. That is a run which
    worked before this lock existed, and it has to keep working.
    """
    for name, db in (("bytes", bytes(tmp_path / "b.db")),
                     ("path", pathlib.Path(tmp_path / "p.db"))):
        out = run_matrix([CELL], lambda cell, adir: {"x": 1}, db,
                         str(tmp_path / "artifacts"), experiment=EXPERIMENT)
        assert out == [{"cell_id": "c", "status": "done", "result": {"x": 1}}], name


def test_the_lock_file_survives_the_run_it_belonged_to(tmp_path):
    """Unlinking it would let the next runner lock a fresh inode while a
    runner holding the old one still believes it has exclusive use."""
    db = str(tmp_path / "results.db")
    run_matrix([CELL], lambda cell, adir: {"x": 1}, db, str(tmp_path / "artifacts"),
               experiment=EXPERIMENT)

    assert os.path.exists(lock_module.lock_path(db))


def test_an_existing_lock_file_is_not_truncated(tmp_path):
    db = str(tmp_path / "results.db")
    path = lock_module.lock_path(db)
    with open(path, "w") as fh:
        fh.write("not ours")

    fd = lock_module.acquire(db)
    try:
        assert os.fstat(fd) == os.stat(path)
    finally:
        lock_module.release(fd)

    with open(path) as fh:
        assert fh.read() == "not ours"


def test_a_lock_file_that_cannot_be_opened_is_reported_as_a_lock_failure(tmp_path):
    """The one branch whose whole job is converting an error class.

    A caller is told a run raises ``MatrixLockError`` when it does not get the
    lock, and being unable to create the lock file at all is one of the ways
    that happens. The provocation is a results db whose parent is a regular
    file, which makes the directory creation fail outright rather than
    depending on which user is running the suite.
    """
    blocking_file = tmp_path / "in_the_way"
    blocking_file.write_text("")
    db = str(blocking_file / "results.db")

    with pytest.raises(MatrixLockError) as excinfo:
        run_matrix([CELL], lambda cell, adir: {}, db, str(tmp_path / "artifacts"),
                   experiment=EXPERIMENT)

    # Named as a lock failure, and the underlying errno kept rather than
    # swallowed, because it is what says which of the two went wrong.
    assert "cannot open the lock file" in str(excinfo.value)
    assert lock_module.lock_path(db) in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, OSError)


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0,
                    reason="root creates files in a read-only directory, so "
                           "the permission failure this needs cannot be "
                           "provoked; the conversion itself is covered without "
                           "a skip by the test above")
def test_a_lock_file_refused_by_permissions_is_reported_the_same_way(tmp_path):
    """The case that sends real users here: a db directory they cannot write.

    Separate from the test above because it fails at the open rather than at
    the directory creation, and because this is the shape a results db shared
    between two users takes. The lock file is created 0o666 but lands at 0o644
    under the usual umask, so the second user is stopped by the permissions.
    """
    home = tmp_path / "readonly"
    home.mkdir()
    db = str(home / "results.db")
    os.chmod(home, 0o555)

    try:
        with pytest.raises(MatrixLockError) as excinfo:
            run_matrix([CELL], lambda cell, adir: {}, db,
                       str(tmp_path / "artifacts"), experiment=EXPERIMENT)
    finally:
        os.chmod(home, 0o755)

    assert "cannot open the lock file" in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, PermissionError)


def test_a_database_the_next_run_cannot_resume_from_is_refused(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for name in (":memory:", ""):
        with pytest.raises(MatrixLockError) as excinfo:
            run_matrix([CELL], lambda cell, adir: {}, name,
                       str(tmp_path / "artifacts"), experiment=EXPERIMENT)
        assert "named file" in str(excinfo.value)

    # And no lock file was invented for a path that is not one.
    assert sorted(p.name for p in tmp_path.iterdir()) == []


def test_a_platform_without_fcntl_is_refused_rather_than_unprotected(tmp_path, monkeypatch):
    """Running unprotected while claiming exclusion is worse than not running."""
    import builtins

    monkeypatch.setitem(sys.modules, "fcntl", None)
    real_import = builtins.__import__

    def no_fcntl(name, *args, **kwargs):
        if name == "fcntl":
            raise ImportError("no fcntl here")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", no_fcntl)
    with pytest.raises(MatrixLockError) as excinfo:
        run_matrix([CELL], lambda cell, adir: {}, str(tmp_path / "results.db"),
                   str(tmp_path / "artifacts"), experiment=EXPERIMENT)
    assert "flock" in str(excinfo.value)


def test_a_sequential_resume_still_skips_the_cell_it_already_ran(tmp_path):
    """The lock is held for one run at a time, so consecutive runs on one db
    behave exactly as they did before it existed."""
    db = str(tmp_path / "results.db")
    root = str(tmp_path / "artifacts")
    calls = []

    def run_cell(cell, adir):
        calls.append(cell["id"])
        return {"x": 1}

    first = run_matrix([CELL], run_cell, db, root, experiment=EXPERIMENT)
    second = run_matrix([CELL], run_cell, db, root, experiment=EXPERIMENT)

    assert first[0]["status"] == "done"
    assert second == [{"cell_id": "c", "status": "skipped"}]
    assert calls == ["c"]
