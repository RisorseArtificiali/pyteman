# Firing-log schema (LOG-01)

`pyteman.firing.FiringLog` writes one JSON object per line to the path given
by `PYTEMAN_LOG` (see `sitecustomize.py`). Each record:

| field          | meaning |
|----------------|---------|
| `schema`       | schema version, currently `1` |
| `run_id`       | `PYTEMAN_RUN_ID` if set in the environment, else a fresh `uuid4().hex` per `FiringLog` instance |
| `instance`     | `uuid4().hex`, one per `FiringLog()` construction |
| `pid`          | the process that opened this instance |
| `seq`          | 1-based, monotonic within this `instance` only |
| `rule`         | the firing rule's `id` |
| `point`        | `rule.module + "." + rule.symbol`, byte-identical to the rule's YAML `point:` string |
| `event`        | `entry` or `exit` |
| `thread`       | `threading.current_thread().name` |
| `time`         | UTC wall clock, `datetime.isoformat()` |
| `monotonic_ns` | `time.monotonic_ns()`, valid only within the writing process |
| `visit`        | the rule's per-rule fire ticket, `ctx["fires"]` (documented in docs/rules.md's context contract), or `null` if the record was written outside that path |
| `note`         | the action dump for a firing record, or `null` |
| `outcome`      | present only on an outcome annotation (a skip or an execute failure); absent on an ordinary firing record |

## Unique key and ordering

`(instance, pid, seq)` uniquely identifies an event. Nothing here promises a
global order: across instances, across processes, or against wall-clock time
from an uncoordinated clock. `run_id` groups records from one logical run
(set `PYTEMAN_RUN_ID` yourself to aggregate several process's records into
one run; leave it unset and each `FiringLog` instance mints its own). Reopening
the same log path produces a new `instance` and restarts `seq` at 1, so two
records that both read `seq: 1` are distinguished by `instance`, not by
position in the file.

`monotonic_ns` is for duration math within one process; never compare it
across `pid`s.

## Concurrency and platform support

The rationale for the locking design (why `PIPE_BUF` atomicity doesn't apply
here, what `flock` actually protects, the platform boundary) is in the
`pyteman.firing` module docstring; this section only states the scope that
matters for a caller.

JSON serialization happens before any lock is taken. Only allocating `seq`,
splicing it into the already-serialized line, and the write itself happen
inside the lock: first the in-process `threading.Lock` (orders threads
sharing one `FiringLog`), then `fcntl.flock(LOCK_EX)` (orders writers across
processes to the same path). The write loop retries on a short write and
raises `FiringLogError` on an `OSError` or a zero-byte write; nothing here
masks a write failure behind a payload-size assumption. A crash mid-record
can still leave a truncated final line, since nothing here adds fsync or any
durability beyond what `O_APPEND` plus `flock` already gives.

If `fcntl` is unavailable (for example, on Windows), `FiringLog(path)`
raises immediately rather than opening the log unprotected.

A write failure can leave a partial trailing line in the file (a short
write that failed partway through the retry loop), and a failure to
release the lock afterward can leave it held against every other writer to
the same path, so any exception out of lock acquisition, the write step, or
the unlock step poisons this instance the same way an explicit `close()`
would: the fd is released (closing it is what actually releases the flock,
even when the explicit unlock call itself failed or was never reached) and
every later `record()` call on this instance raises immediately. An
`OSError` from acquisition or unlock is wrapped into `FiringLogError`; an
`OSError` from the write is wrapped by the write step itself. A non-`OSError`
exception from any of the three (an asynchronous interruption such as
`KeyboardInterrupt`) still poisons the instance this way, but propagates with
its own original type unchanged rather than being wrapped. This guarantee is
scoped to the one poisoned instance, not the file: a
different `FiringLog` opened later against the same path does not inherit
this instance's `_closed` state, since it is in-memory and per-instance,
and can still append past whatever partial or corrupt tail the poisoned
instance left behind. Nothing here detects or repairs that tail across
instances; a caller that reopens the same path after a poisoned instance is
not told the tail may be suspect.

## I/O error contract

`os.open` (in the constructor), `fcntl.flock` (lock acquire and release),
and `os.close` can all raise a raw `OSError`; this module wraps every one
of those into `FiringLogError`, so a caller only ever has one exception
type to catch for a firing-log failure from those paths. Lock acquisition,
the write step, and unlock are all exceptions to that in one specific case:
an asynchronous interruption (`KeyboardInterrupt`, `SystemExit`) during any
of the three still poisons the instance (see "Concurrency and platform
support" above) but propagates with its own original type unchanged, never
translated into `FiringLogError`. A failure to *release* the lock in
`record()`'s cleanup step is not swallowed: it poisons the instance and is
raised (wrapped into `FiringLogError` if it was an `OSError`, unchanged
otherwise), unless the write already failed, in which case the write
failure is what's raised (whatever its type) and the unlock failure is
attached to it as a note (`BaseException.add_note`) rather than replacing
it. A close failure during that same poisoning step is best-effort and is
likewise never allowed to replace the exception actually raised; when there
is one to attach it to, it is annotated the same way rather than silently
dropped, and the annotation itself is best-effort too, so a hostile
exception cannot block the cleanup it is being attached to.

## Not self-instrumenting

`FiringLog` captures `os.write` and `os.close` at construction and calls
those references, instead of looking the names up on each call. A rule
targeting `os.write` would otherwise be re-entered by the logger's own write
while `record()` holds its non-reentrant lock, hanging the process; a rule
targeting `os.close` would instead see `record()` refuse (`_closed` is
already set by then) and leave the fd open with its finalizer already
detached, leaking it. The capture covers only those two calls, the ones made
under a held lock. It binds whatever the attributes are at construction time
rather than asserting they are the genuine builtins, and `os.open` is not
covered, since it runs once before any lock exists. Instrumenting `os.write`
in the program under test still works normally: only this module's own I/O
is out of band.

## Fd lifecycle

An instance that is garbage-collected without an explicit `close()` (for
example, a reference dropped after a fork, or a caller that simply forgets)
does not leak its fd: a `weakref.finalize` closes it as a safety net.
Calling `close()` explicitly disarms that finalizer first, so a later,
unrelated `os.open()` call that happens to recycle the same fd number can't
have it closed out from under it by a delayed finalizer.

## Fork vs. spawn

A `FiringLog` instance's fd and lock are not safe to reuse across `fork()`:
a forked child can inherit them mid-operation, including a locked mutex it
can never release (the thread that held it doesn't exist in the child to
release it). Both `record()` and `close()` (and therefore `__exit__`, which
calls `close()`) check `os.getpid()` against the pid that opened the
instance before ever touching the lock, and raise `FiringLogError` on a
mismatch. Only `multiprocessing.get_context("spawn")`-based multiprocess use
is supported and tested; a child process opens its own `FiringLog` against
the shared path instead of inheriting the parent's.

## API

`FiringLog(path)` opens (creating if needed) in append mode. `record(rule,
ctx, note=None, outcome=None)` writes one line. `close()` is idempotent;
`record()` after `close()` raises `FiringLogError`. `FiringLog` is also a
context manager, closing on `__exit__`.

## Deferred

Correlating a firing record with its later outcome annotation (TASK-15) is
not implemented here; `visit` is provided as the join key a future pass can
use, but no join or attempt/outcome schema is defined by this document.
