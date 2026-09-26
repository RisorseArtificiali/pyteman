# src/pyteman/actions.py
"""Action execution for injected rules.

Trusted-operator posture: rules come from operator-authored YAML used for
local test tooling, never from untrusted input. By design, `when` condition
expressions and `pragma` name/value strings are passed through unsanitized;
`raise` resolves only builtin exception classes. Extending this module to
face untrusted rule sources would require sanitizing all three.

Attempt/outcome logging (LOG-02). With a log configured, and when the action
reaches an end that can be recorded, it logs twice: a `phase: start` record
written BEFORE the action runs, which proves an attempt and nothing more, and
a `phase: end` terminal record carrying a `status`. They are joined by
`attempt`, the start record's own `seq`, so interleaved threads and repeated
visits stay distinguishable without relying on adjacency in the file. Three
cases produce no pair: without a log nothing is written at all, a `kill`
action leaves its start record deliberately unmatched because `os._exit`
skips every finalizer, and a terminal write can itself fail. All three look
the same from the file, which is why a start record with no terminal means
the outcome is UNKNOWN, never success.

The statuses claim only what this module can observe from where it stands:

- `override_requested`: the override was placed in `ctx`. What the patched
  body finally returns is decided after `run_action` returns, where this
  module cannot see it, so nothing here says the call WAS overridden.
- `slept`, `pragma_skipped`, `pragma_failed`, `barrier_opened`,
  `barrier_passed`, `barrier_timeout`.
- The four pragma verdicts, which replace the old `pragma_executed`. That
  status meant "the statement did not raise", which SQLite gives away for
  free even for a misspelled pragma it ignored entirely, so it was recorded
  identically for a pragma that applied and one that did nothing.
  `pragma_applied` is the postcondition OBSERVED and not a claim of exclusive
  causality, since the connection may be shared; `pragma_already` means it
  held before the attempt, which therefore proved nothing about its own
  effect; `pragma_mismatch` means SQLite accepted the statement and the
  setting is not the one asked for, which is not the same as no effect,
  because the effect may be present and wrong; `pragma_unknown` makes no
  claim in either direction, and is what an unverifiable value or a pragma
  outside the supported perimeter gets instead of a success. See
  `pyteman.pragmas`.
- `raised`: a `raise` action's exception was instantiated and deliberately
  raised. Everything else that escapes, including an unresolvable exception
  class or a failure constructing one, is `failed`, and the original
  exception propagates with its identity unchanged either way.

Under `PYTEMAN_STRICT_PRAGMA=1` an unverified pragma additionally raises
`pragma.PragmaVerificationError` AFTER its terminal record is written, so an
experiment built on a setting that never took effect stops instead of
reporting a result. The guarantee is narrower than "the run dies" and is
documented as such on that class: a workload that catches the exception
continues, and the record is then the only evidence.

Under `PYTEMAN_STRICT_BARRIER=1` a `barrier` whose wait timed out raises
`barriers.BarrierTimeoutError` the same way and with the same caveat, plus one
of its own: on an exit rule the refusal is raised inside the patcher's
`finally` and displaces the body's exception. That is documented on the class.
Neither switch is read here; each module owns its own policy.

Logging never overrides an exception the action is already carrying, which is
a rule about precedence and not a promise that logging is silent. Writing the
start record can fail, and that failure propagates instead of the action
running: an attempt that could not be recorded must not run unrecorded. On
the way out the precedence applies: when the action is already on its way out
with an exception, that exception wins whatever goes wrong writing the
terminal record, including an asynchronous interruption, and the log failure
rides along as a note; when the action completed, a failed terminal write is
raised with its own identity intact, so an outcome that was never recorded is
not passed off as one that was. The `outcome` diagnostics that have to
render an object the workload controls are deferred, and built only if there
is a log to receive them, because rendering an exception or a connection runs
the workload's own `__str__`: that is `failed`, `raised`, `pragma_failed` and
every one of the four pragma verdicts, whose texts carry values read back
through a connection the workload supplied. The other outcome texts
(`pragma_skipped`, `barrier_timeout`) interpolate only values this module
already holds, and are built whether or not a log is there.
"""
import builtins as _builtins
import os
import sqlite3
import time
from collections import namedtuple

import pyteman.pragmas as pragmas
from pyteman.targets import resolve_target


#: What `_dispatch` reports back. `status` is the only required field, so an
#: action that just did its job and returns nothing says so in one word
#: instead of padding three positional `None`s. `message` becomes the
#: terminal record's human-readable `outcome` (a string, or a zero-arg
#: callable deferred until a log actually needs it; see `_safe_message`),
#: `value` is what `run_action` returns to the patched body, and `to_raise`
#: carries an exception the action raises deliberately: the one a `raise`
#: action built, or the one strict mode refuses an unverified pragma with.
_Dispatched = namedtuple("_Dispatched", "status message value to_raise",
                         defaults=(None, None, None))


def run_action(rule, ctx, log=None):
    attempt = None
    if log is not None:
        # Before the action, and its failure propagates: an attempt that
        # could not be recorded must not run unrecorded.
        ident = log.record(rule, ctx, note=str(rule.action))
        attempt = getattr(ident, "attempt", None)
        if attempt is None:
            # Schema 2 needs the attempt id back from record(), and a log
            # object written against the older signature returns None. Saying
            # which contract is missing beats an AttributeError surfacing
            # inside the workload under test.
            raise TypeError(
                f"{type(log).__name__}.record() returned {ident!r}: the firing "
                "log must return a RecordId carrying the attempt id")
    try:
        done = _dispatch(rule, ctx)
    except BaseException as exc:
        # Unexpected: an action kind that does not exist, an exception class
        # that does not resolve, a constructor that blew up, or an
        # asynchronous interruption. The bare `raise` preserves identity, and
        # the diagnostic is deferred (see `_safe_message`) so that rendering
        # this exception cannot be what decides which one propagates.
        _terminal(log, rule, ctx, attempt, "failed",
                  lambda exc=exc: f"{type(exc).__name__}: {exc}", primary=exc)
        raise
    if done.to_raise is not None:
        _terminal(log, rule, ctx, attempt, done.status, done.message,
                  primary=done.to_raise)
        raise done.to_raise
    _terminal(log, rule, ctx, attempt, done.status, done.message)
    return done.value


def _dispatch(rule, ctx):
    """Run the action; return a `_Dispatched`.

    `to_raise` carries an exception this module raises on purpose, kept out
    of the exception path so that a deliberate raise is logged under its own
    status rather than being mistaken for a failure of the tool itself. Two
    actions use it: a `raise` action, logged as `raised`, and a pragma
    refused by strict mode, logged under the pragma verdict that refused it.
    """
    kind = rule.action["kind"]
    if kind == "return_value":
        ctx["_override"] = rule.action.get("value")
        return _Dispatched("override_requested")
    if kind == "return_none":
        ctx["_override"] = None
        return _Dispatched("override_requested")
    if kind == "sleep":
        time.sleep(int(rule.action.get("ms", 0)) / 1000.0)
        return _Dispatched("slept")
    if kind == "raise":
        name = rule.action.get("exc", "RuntimeError")
        exc = getattr(_builtins, name, None)
        if not isinstance(exc, type) or not issubclass(exc, BaseException):
            raise RuntimeError(f"unknown exception class {name}")
        instance = exc(rule.action.get("message", "pyteman injected"))
        return _Dispatched("raised",
                           lambda i=instance: f"{type(i).__name__}: {i}",
                           to_raise=instance)
    if kind == "pragma":
        target_spec = rule.action.get("target")
        name, value = rule.action["name"], rule.action["value"]
        # Guarded (CFG-06). A resolver that raises is a resolution error,
        # not a known miss and not an unidentified workload incident.
        # Exception is caught; BaseException still escapes. The status is
        # FAILED, not SKIPPED: "skipped" means the resolver found nothing
        # to act on (con is None), while a getter that raises is a failure
        # of the resolution step. Under strict mode FAILED triggers the
        # same refusal an execute failure does.
        try:
            con, why = (resolve_target(ctx, target_spec)
                        if target_spec is not None
                        else _find_connection(ctx))
        except Exception as exc:
            return _pragma_result(
                name, value, pragmas.FAILED,
                lambda exc=exc:
                    f"target resolution failed: {type(exc).__name__}: {exc}")
        if con is None:
            return _pragma_result(name, value, pragmas.SKIPPED,
                                  f"pragma skipped: {why}")
        # Read the baseline BEFORE executing, and never let that read stand in
        # the way of the execution. `read` reports an observational failure as
        # `UNREADABLE` instead of raising, so a connection that cannot be
        # inspected still gets the pragma it was sent: this action injects
        # first and reports second. Normalising first would be worse than
        # useless here, because a value the vocabulary rejects would never
        # reach SQLite at all, and a fault-injection tool that silently
        # declines to inject the hostile value has hidden the very thing it
        # exists to make visible.
        before = pragmas.read(con, name)
        try:
            cur = con.execute(f"PRAGMA {name}={value}")
        except Exception as exc:
            # Still non-propagating, as it has always been: a pragma that
            # will not apply is reported, not turned into a failure of the
            # workload under test. Deferring the diagnostic is what keeps
            # that true even when rendering `exc` or `con` raises.
            return _pragma_result(
                name, value, pragmas.FAILED,
                lambda exc=exc, con=con:
                    f"pragma execute failed on {type(con).__name__}: {exc}")
        _release(cur)
        status, message = pragmas.classify(
            name, value, before, pragmas.read(con, name))
        return _pragma_result(name, value, status, message)
    if kind == "kill":
        # No terminal record by construction: os._exit skips every finalizer,
        # so this attempt's start record is deliberately left unmatched.
        os._exit(int(rule.action.get("exit_code", 70)))
    if kind == "barrier":
        from pyteman import barriers
        name = rule.action["barrier"]
        if rule.action.get("role", "wait") == "open":
            barriers.open(name)
            return _Dispatched("barrier_opened", value=True)
        timeout_s = float(rule.action.get("timeout_s", 30))
        passed = barriers.wait(name, timeout_s=timeout_s)
        if passed:
            return _Dispatched("barrier_passed", value=passed)
        # The timeout becomes visible in the log without changing what the
        # caller gets back by default, which is the wait's own return value as
        # before. Under strict mode the same record is written and then the
        # refusal is raised; the policy lives in barriers.refusal, so nothing
        # here decides whether a failed barrier is fatal.
        return _Dispatched("barrier_timeout",
                           f"barrier {name!r} timed out after {timeout_s}s",
                           value=passed,
                           to_raise=barriers.refusal(name, timeout_s))
    raise NotImplementedError(f"unknown action kind {kind}")


def _release(cur):
    """Finish with the SET statement's cursor, ignoring whatever it does.

    `PRAGMA journal_mode=...` is the only pragma in the supported perimeter
    whose SET form returns a row, and a statement that has produced a row and
    has not been finalised keeps an exclusive lock: an independent connection
    asking for a write lock gets "database is locked", and `close()` alone
    releases it without reading anything further. CPython frees a discarded
    cursor by refcount the moment `execute` returns, which is why this was
    never visible, but the correctness of an injector must not rest on an
    interpreter detail the package never declares. Under deferred
    finalisation the lock survives until a collection runs, which would make
    pyteman itself the cause of the contention it exists to measure.

    Nothing here may change the outcome. The statement ran before `execute`
    returned, so the pragma is in force or not regardless of this call, and
    `cur` came from a connection the workload supplied, which makes its
    `close` workload code like any other. A hostile or merely absent `close`
    that propagated would report an applied pragma as `pragma_failed` and,
    under strict mode, refuse a sound experiment over housekeeping.
    """
    try:
        close = getattr(cur, "close", None)
        if close is not None:
            close()
    except Exception:
        pass


def _pragma_result(name, value, status, message):
    """Every exit of the pragma branch, so strict mode has one gate.

    A pragma that never reached a connection invalidates the experiment
    exactly as much as one that reached it and did not apply, so `REFUTING`
    covers the skip and the execute failure too, and they must not leave by a
    door the gate does not sit on. The policy itself lives in
    `pragmas.refusal`; this function exists to make sure nothing bypasses it.
    """
    return _Dispatched(status, message,
                       to_raise=pragmas.refusal(name, value, status))


def _find_connection(ctx):
    """Legacy no-target path: (con, None) or (None, reason), same protocol
    as resolve_target so the pragma action has one miss branch."""
    for v in list(ctx.get("args", ())) + list(ctx.get("kwargs", {}).values()):
        if isinstance(v, sqlite3.Connection):
            return v, None
    return None, "no target spec and no sqlite3.Connection in the call arguments"


def _safe_message(message):
    """Resolve a terminal record's `outcome` without letting it change control flow.

    A message is either a plain string or a zero-arg callable, deferred so it
    is built only when a log is actually there to receive it. Deferring
    matters because rendering an exception or a connection runs the
    workload's OWN `__str__`, which in a fault-injection tool is code under
    test: it can raise, and a diagnostic that nobody asked for must never be
    what decides which exception propagates, nor turn a reported no-op (a
    failed pragma) into a failure of the run. A diagnostic that cannot be
    built is reported as missing rather than allowed to escape.
    """
    if not callable(message):
        return message
    try:
        return message()
    except BaseException as exc:
        try:
            return f"<diagnostic unavailable: {type(exc).__name__}>"
        except BaseException:
            return "<diagnostic unavailable>"


def _terminal(log, rule, ctx, attempt, status, message=None, primary=None):
    # One terminal record per attempt, with no suppression of repeats: an
    # identical miss on every call under `fire: always` is exactly what makes
    # the attempt count reconstructible, and a deduplicated line destroys it.
    if log is None:
        return
    try:
        log.record(rule, ctx, phase="end", attempt=attempt,
                   status=status, outcome=_safe_message(message))
    except BaseException as exc:
        if primary is None:
            # The action itself completed; the log did not. Saying so is the
            # honest report, and it must not be read as the action failing.
            # The bare `raise` keeps the failure's own identity, so an
            # asynchronous interruption stays a KeyboardInterrupt rather than
            # being translated. On an exit rule this replaces the body's
            # in-flight exception, which stays reachable as __context__; see
            # the "Attempts and outcomes" section of docs/firing.md.
            raise
        # The action already has an error on its way out, and that one wins
        # WHATEVER either exception is. Losing the firing log is the lesser
        # fact and rides out as a note. This is deliberately BaseException:
        # a KeyboardInterrupt from the log would otherwise erase the action's
        # own exception entirely, and because the primary has not been raised
        # yet at this point it would not even survive as __context__.
        try:
            primary.add_note(
                f"additionally, recording the {status!r} outcome of this "
                f"action failed: {type(exc).__name__}: {exc}")
        # Best effort: neither a hostile __notes__ nor a __str__ that raises
        # may block the primary exception it is being attached to.
        except BaseException:
            pass
