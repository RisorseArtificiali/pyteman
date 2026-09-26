# src/pyteman/firing.py
"""Firing-log identity and provenance (LOG-01).

Each record identifies the run (``run_id``), the log handle that wrote it
(``instance``), and the writer process (``pid``); ``seq`` is monotonic within
one ``instance`` only. ``(instance, pid, seq)`` is the unique key for an
event; nothing here promises a global order across instances, processes, or
uncoordinated wall clocks. ``time`` is a UTC wall-clock reading for humans;
``monotonic_ns`` is comparable only within the same process and exists for
duration math, never for cross-process ordering.

Concurrent writers to the same path are supported across processes (spawn,
not fork: a forked child inherits this instance's fd and lock mid-operation,
which is not safe to reuse, so ``record`` and ``close`` both refuse on a pid
mismatch, before ever touching the lock, and ask the child to open its own
instance). Within one process, a ``threading.Lock`` orders same-process
writers; across processes, ``fcntl.flock`` held for the full
write-until-complete loop keeps one process's line from interleaving with
another's, since a regular-file ``write(2)`` is not guaranteed atomic by
POSIX the way a pipe write under ``PIPE_BUF`` is. A crash mid-record can
still leave a truncated final line; nothing here invents durability or
fsync. Every explicit OS call in that section (lock acquire, write, unlock)
can fail two ways: an ``OSError``, which this module always wraps into
``FiringLogError``, or an asynchronous interruption such as
``KeyboardInterrupt`` or ``SystemExit`` that propagates with its original
type unchanged. Either way this instance fails closed: acquiring the lock or
writing the line is the primary failure if either raises; releasing the lock
is always attempted regardless, and whatever it raises is either promoted to
primary (nothing failed before it) or annotated onto the existing primary as
a note rather than replacing it. Closing the fd is what actually releases
the flock, including when the explicit unlock call itself failed or was
never reached (an interruption right as the lock is acquired leaves its
state uncertain, not confirmed released, so this instance poisons itself the
same way rather than risk treating an uncertain lock as a clean one). This
poisoning protects only this instance: a different ``FiringLog`` opened
later against the same path does not inherit this one's closed state and can
still append past whatever partial tail a poisoned instance left behind.

``os.open`` (in the constructor), ``fcntl.flock``, and ``os.close`` can all
raise a raw ``OSError``; this module wraps every one of those into
``FiringLogError`` so a caller only ever has one exception type to catch for
a firing-log failure. A forked child's copy of an unclosed instance is not
left leaking its fd: a ``weakref.finalize`` closes it if the instance is
garbage-collected without an explicit ``close()``, in either the parent or a
child that never touches this instance again. An explicit ``close()``
disarms that finalizer first, so a later, unrelated ``os.open`` call cannot
have its fd number closed out from under it after being recycled.

This module writes through ``os.write`` and ``os.close`` references captured
at construction rather than looking them up on every call. pyteman patches
module attributes, so a rule targeting ``os.write`` would otherwise be
re-entered by the logger's own write while ``record`` holds its
non-reentrant lock, hanging the process; a rule targeting ``os.close`` would
instead see ``record`` refuse (``_closed`` is already set by then) and leave
the fd open with its finalizer already detached, leaking it. Capturing the
two calls made under a held lock removes both. The capture is deliberately
narrow: it binds whatever those attributes are at construction time, it does
not assert they are the genuine builtins, and it says nothing about any other
global. Application code's own ``os.write`` stays fully instrumentable, which
is the intended asymmetry.

Attempt correlation (LOG-02) rides two fields. ``phase`` is ``"start"`` for
the record written before an action runs and ``"end"`` for the terminal
record written after it; ``attempt`` joins the two, since a start record's
``attempt`` is its own ``seq`` and its terminal record repeats that value.
``(instance, pid, attempt)`` therefore groups one attempt with its outcome
without relying on adjacency in the file, which interleaved threads destroy.
``record`` returns that identity as a ``RecordId``, and only after the line
is fully written, so a caller never holds an id for a line that did not
land. A start record with no terminal record means the outcome is UNKNOWN,
never success: a ``kill`` action ends the process from inside the action, and
a crash or a failed terminal write leaves exactly the same shape.

Verified support is Linux on a local filesystem, the same boundary
``pyteman.runner.lock`` documents for its own flock use; macOS is unverified,
and flock over NFS is outside any guarantee this module offers.
"""
import json
import os
import threading
import time
import uuid
import weakref
from collections import namedtuple
from datetime import datetime, timezone

try:
    import fcntl
except ImportError:
    fcntl = None

SCHEMA_VERSION = 2

#: What ``record`` hands back once the line is on disk. ``seq`` identifies
#: the record itself; ``attempt`` is what a terminal record must echo to be
#: joined to it, and the two are equal on a start record by construction.
RecordId = namedtuple("RecordId", "instance pid seq attempt")


class FiringLogError(Exception):
    """Raised for a firing-log usage or I/O error the caller must see."""


def _write_all(fd, data, write):
    view = memoryview(data)
    while view:
        try:
            n = write(fd, view)
        except OSError as exc:
            raise FiringLogError(f"firing log write failed: {exc}") from exc
        if n == 0:
            raise FiringLogError(
                "firing log write returned 0 bytes (disk full, or the fd "
                "was closed by another writer concurrently)")
        view = view[n:]


def _annotate(exc, label, secondary_exc):
    # Best-effort: a secondary cleanup failure must never cost the primary
    # exception its trip out of record(). That includes the note string's
    # own formatting -- str(secondary_exc) or its type name could in theory
    # be hostile -- not just the add_note call itself, so both are inside
    # this one guarded try.
    #
    # Parallel to patcher._note, which guards the same add_note call for the
    # rollback path.  Not consolidated because sitecustomize.py imports this
    # module lazily to avoid patcher's chain (actions, conditions, rules,
    # targets); a shared leaf module for four guarded lines would cost more
    # in indirection than the duplication.  Keep the two in sync: both must
    # catch BaseException and swallow it silently.
    try:
        exc.add_note(
            f"additionally, {label} failed: "
            f"{type(secondary_exc).__name__}: {secondary_exc}")
    except BaseException:
        pass


class FiringLog:
    def __init__(self, path):
        if fcntl is None:
            raise FiringLogError(
                "no flock on this platform, so concurrent writers to the "
                "firing log cannot be kept from interleaving, and the log "
                "will not open without that. Verified support is Linux on "
                "a local filesystem")
        self.path = path
        self.run_id = os.environ.get("PYTEMAN_RUN_ID") or uuid.uuid4().hex
        self.instance = uuid.uuid4().hex
        self._creator_pid = os.getpid()
        self._seq = 0
        self._lock = threading.Lock()
        self._closed = False
        try:
            self._fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        except OSError as exc:
            # type(exc).__name__ is folded into the message itself, not left
            # to __cause__: sitecustomize's own refusal-reporting renders only
            # the exception it directly caught, so an operator diagnosing a
            # startup refusal still sees FileNotFoundError/PermissionError,
            # not just this wrapper's name.
            raise FiringLogError(
                f"could not open firing log {path!r}: "
                f"{type(exc).__name__}: {exc}") from exc
        # Bound here, while fcntl is known non-None, so record() never has to
        # re-narrow an Optional module global on every call.
        self._flock = fcntl.flock
        self._lock_ex = fcntl.LOCK_EX
        self._lock_un = fcntl.LOCK_UN
        # Snapshotted for the same reason, plus one specific to this project:
        # pyteman patches module attributes, so a rule targeting os.write or
        # os.close would otherwise be re-entered by the logger's own I/O. A
        # measuring instrument must not sit inside the injection surface it
        # measures. These bind whatever os.write/os.close are at construction
        # time; they do not assert those are the genuine builtins (a rule
        # installed before this instance is captured as-is, deliberately, so
        # the tests' own stubs keep working), and they protect only these two
        # calls, not arbitrary globals.
        self._write = os.write
        self._close = os.close
        # Safety net only: a well-behaved caller closes explicitly, which
        # detaches this before it ever runs. Passing the raw fd (not a bound
        # method on self) is what lets self become unreachable at all.
        self._finalizer = weakref.finalize(self, self._close, self._fd)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False

    def _refuse_if_wrong_process(self, action):
        pid = os.getpid()
        if pid != self._creator_pid:
            raise FiringLogError(
                f"FiringLog instance {self.instance!r} was opened in pid "
                f"{self._creator_pid}; pid {pid} (likely a forked child) "
                f"must not {action} across a fork; open its own FiringLog "
                "instead")

    def close(self):
        # Checked before the lock: a lock inherited mid-acquisition across a
        # fork stays acquired forever in the child, since the thread that
        # held it does not exist there to release it.
        self._refuse_if_wrong_process("call close()")
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._finalizer.detach()
            try:
                self._close(self._fd)
            except OSError as exc:
                raise FiringLogError(
                    f"firing log close failed: {type(exc).__name__}: {exc}") from exc

    def record(self, rule, ctx, note=None, outcome=None,
               phase="start", attempt=None, status=None):
        # "phase" is what tells a firing apart from its outcome: "start" is
        # written before the action runs and proves an ATTEMPT only, "end"
        # is the terminal record and carries "status". "outcome" stays the
        # human-readable message on a terminal record.
        #
        # The default phase is "start" because that is what a bare
        # record(rule, ctx) means: an event happened. A caller writing a
        # solitary annotation with no attempt of its own passes
        # phase="end" and leaves attempt None, which logs an UNCORRELATED
        # outcome rather than inventing a start record to point at.
        if self._closed:
            raise FiringLogError("record() called on a closed FiringLog")
        self._refuse_if_wrong_process("call record()")
        # A start record refers to itself, and its seq is not known until the
        # lock below is held, so its "attempt" is spliced in with the seq
        # rather than serialized here.
        self_attempt = phase == "start" and attempt is None
        rec = {
            "schema": SCHEMA_VERSION,
            "run_id": self.run_id,
            "instance": self.instance,
            "pid": self._creator_pid,
            "rule": rule.id,
            "point": f"{rule.module}.{rule.symbol}",
            "event": rule.event,
            "phase": phase,
            "thread": threading.current_thread().name,
            "time": datetime.now(timezone.utc).isoformat(),
            "monotonic_ns": time.monotonic_ns(),
            "visit": ctx.get("fires"),
            "note": note,
        }
        if not self_attempt:
            rec["attempt"] = attempt
        if status is not None:
            rec["status"] = status
        if outcome is not None:
            rec["outcome"] = outcome
        # Serialized without "seq": nothing above this point depends on the
        # counter, so only its allocation, its splice into this line, and the
        # write itself need to happen inside the lock below.
        body = json.dumps(rec)
        with self._lock:
            if self._closed:
                raise FiringLogError("record() called on a closed FiringLog")
            self._seq += 1
            seq = self._seq
            own_attempt = f', "attempt": {seq}' if self_attempt else ""
            line = f'{body[:-1]}, "seq": {seq}{own_attempt}}}\n'.encode("utf-8")

            # One disciplined path for every explicit OS call under the
            # lock: acquire, write, unlock. An OSError from acquire or
            # unlock is wrapped into FiringLogError (this module's existing
            # contract); any other BaseException (an asynchronous
            # interruption such as KeyboardInterrupt or SystemExit) is kept
            # as-is, never wrapped, since its identity is what a caller
            # catching it upstream needs to see unchanged. Acquire and
            # write are the primary-error source; unlock is always
            # attempted regardless of what happened before it (releasing a
            # lock this instance may not actually hold is a harmless no-op)
            # and is only ever promoted to primary when nothing failed
            # ahead of it, never allowed to replace an existing primary.
            primary = None
            try:
                self._flock(self._fd, self._lock_ex)
            except OSError as exc:
                primary = FiringLogError(
                    f"firing log lock failed: {type(exc).__name__}: {exc}")
                primary.__cause__ = exc
            except BaseException as exc:
                # The OS-level lock may have actually been taken right as
                # this call was interrupted; its state is uncertain, not
                # confirmed unacquired, so this falls into the same
                # fail-closed path below rather than being assumed harmless.
                primary = exc
            else:
                try:
                    _write_all(self._fd, line, self._write)
                except BaseException as exc:
                    primary = exc

            unlock_exc = None
            try:
                self._flock(self._fd, self._lock_un)
            except BaseException as exc:
                unlock_exc = exc

            if primary is None and unlock_exc is None:
                # The only success exit, so the id is handed out only for a
                # line that is fully written and unlocked. Every other path
                # below raises, and a caller that gets an exception holds no
                # attempt id to correlate against.
                return RecordId(self.instance, self._creator_pid, seq,
                                seq if self_attempt else attempt)

            # A short write can leave a partial trailing line behind; a
            # failed or interrupted unlock (or acquire) can leave the flock
            # held against every other writer to this path. Either way this
            # instance fails closed: a later record() must not risk landing
            # past an unknown partial tail or racing a lock nobody
            # released. Closing the fd is what actually releases the flock
            # even when the explicit unlock call above failed or was never
            # reached, and it is the only close attempt made on this fd --
            # on this module's supported platform (Linux, a local
            # filesystem) that invalidates the fd number regardless of
            # whether close() raises, so nothing past this point may touch
            # it again; EINTR's effect on a raising close() is not uniform
            # across every POSIX platform, which is why this is scoped to
            # Linux rather than stated as a universal rule.
            self._closed = True
            self._finalizer.detach()
            close_exc = None
            try:
                self._close(self._fd)
            except BaseException as exc:
                close_exc = exc

            if primary is not None:
                if unlock_exc is not None:
                    _annotate(primary, "releasing the firing log lock", unlock_exc)
            elif isinstance(unlock_exc, OSError):
                primary = FiringLogError(
                    "firing log unlock failed: "
                    f"{type(unlock_exc).__name__}: {unlock_exc}; poisoning "
                    "this instance since the lock may still be held")
                primary.__cause__ = unlock_exc
            else:
                # Not an OSError: an interruption during unlock itself, kept
                # with its own identity rather than wrapped.
                primary = unlock_exc

            if close_exc is not None:
                _annotate(primary, "closing the firing log fd", close_exc)

            assert primary is not None  # guaranteed by the early return above
            raise primary


def open_log(path):
    return FiringLog(path) if path else None
