"""Exclusion between concurrent runners, held for the whole of a run.

The runner reads a cell's stored row, runs the callback, and writes the result
back. Nothing in that sequence reserves the cell, so two runners on one results
db both execute it and the second write displaces the first. What the losing
runner returns to its caller is its own result while the db holds the other's,
and neither process reports anything.

The lock lives in the filesystem rather than in the db because of what has to
happen when a runner dies. A lock row in a table is not released by a crash,
and reclaiming one needs a lease with a heartbeat and an expiry. The kernel
drops an flock when the holding open file description goes away, so a runner
killed outright leaves nothing to clean up. Measured with SIGKILL, which no
handler can intercept: the lock was refused while the holder lived and acquired
immediately after it died.

Support is Linux on a local filesystem, which is what is verified. macOS is
unverified. flock over NFS is outside any guarantee this module offers.
"""
import contextlib
import errno
import os

# Locking the db file itself would sit on top of sqlite's own locking of that
# same file. A separate file next to it does not.
_LOCK_SUFFIX = ".lock"

# sqlite gives each connection its own database for these two, so two runners
# never share one and there is nothing to exclude. They are refused rather than
# locked because the runner's whole contract is a durable record that a later
# run resumes from, and neither of them keeps one.
_NON_DURABLE = {":memory:": "an in-memory database",
                "": "a temporary database"}


class MatrixLockError(RuntimeError):
    """Another runner holds this results db, or no lock can be taken at all."""


def lock_path(results_db):
    """The lock file for ``results_db``, one per database.

    The path is canonicalised, so a relative path, an absolute one and a
    symlink to the same db all name the same lock. Two hard links to one db are
    distinct paths that resolve to themselves, and this does not detect that
    they are the same file: such a pair would be locked independently.

    ``bytes`` and ``os.PathLike`` are decoded rather than refused, because
    sqlite accepts both and the suffix this appends is text. Without the
    decode, a ``bytes`` results_db that worked before this lock existed would
    now fail on the concatenation, since ``realpath`` returns whatever type it
    was given.
    """
    return os.path.realpath(os.fsdecode(results_db)) + _LOCK_SUFFIX


def acquire(results_db):
    """Take the exclusive lock for ``results_db`` and return its descriptor.

    Raises ``MatrixLockError`` if another runner holds it, if this process
    already does, if this platform has no flock, or if the lock file cannot be
    opened at all. The caller closes the descriptor to release, and a crash
    releases it without one.

    Creates the directory the lock file goes in, which is the directory the
    results db goes in. The runner depends on that: since this runs before the
    db is opened, it is what lets a first run on a fresh matrix work without
    the caller making a home for the db first.
    """
    name = os.fsdecode(results_db)
    if name in _NON_DURABLE:
        raise MatrixLockError(
            f"results_db={results_db!r} is {_NON_DURABLE[name]}, which is "
            "discarded when the connection closes and cannot be resumed from. "
            "The runner needs a named file")

    try:
        import fcntl
    except ImportError as e:
        # Imported here rather than at module scope so that importing pyteman
        # on a platform without fcntl still works. Refused rather than run
        # unprotected: a runner that claims exclusion it does not have is worse
        # than one that says it cannot run here.
        raise MatrixLockError(
            "no flock on this platform, so concurrent runners cannot be kept "
            "apart and the runner will not run without that. Verified support "
            "is Linux on a local filesystem"
        ) from e

    path = lock_path(results_db)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # O_TRUNC is deliberately absent. The file is never written by this
        # module, but it is a path the caller chose and truncating whatever
        # happens to be there is not this module's to do.
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o666)
    except OSError as e:
        # Reported as a lock failure rather than as a raw OSError, because a
        # caller told to expect MatrixLockError from a run gets this on one of
        # the ways the run does not get the lock. The case that made this
        # concrete is a results db shared between two users: the file is
        # created 0o666 but lands at 0o644 under the usual umask, so the second
        # user is stopped by the permissions rather than by the lock, and
        # without this would see a bare EACCES naming a file they never asked
        # for.
        raise MatrixLockError(f"cannot open the lock file {path!r}: {e}") from e

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as e:
        os.close(fd)
        if e.errno in (errno.EACCES, errno.EAGAIN):
            # Also the path a second acquire from this same process takes:
            # flock belongs to the open file description, not to the process,
            # so a re-entrant call is refused here rather than deadlocking.
            raise MatrixLockError(
                f"another runner is using {results_db!r}: the lock {path!r} is "
                "held. Runs on one results db are exclusive, so wait for that "
                "one to finish rather than running both"
            ) from e
        raise MatrixLockError(f"cannot lock {path!r}: {e}") from e
    except BaseException:
        os.close(fd)
        raise
    return fd


def release(fd):
    """Drop the lock. The file is left in place on purpose.

    Unlinking it would let the next runner create a fresh file and lock that,
    while a runner still holding a descriptor on the old inode believes it has
    exclusive use. Nor is a lock ever broken because the pid that took it is
    gone: the kernel is what releases this lock, so a lock that is still held
    is held by something alive, or by a process that inherited the descriptor.
    """
    os.close(fd)


@contextlib.contextmanager
def held(results_db):
    """Hold the lock for the body of the block, and drop it however it ends."""
    fd = acquire(results_db)
    try:
        yield fd
    finally:
        release(fd)
