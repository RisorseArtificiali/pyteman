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
- `slept`, `pragma_executed` (the statement executed; the value is NOT read
  back, so this is not a claim that SQLite applied it), `pragma_skipped`,
  `pragma_failed`, `barrier_opened`, `barrier_passed`, `barrier_timeout`.
- `raised`: a `raise` action's exception was instantiated and deliberately
  raised. Everything else that escapes, including an unresolvable exception
  class or a failure constructing one, is `failed`, and the original
  exception propagates with its identity unchanged either way.

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
the workload's own `__str__`: that is `failed`, `raised` and `pragma_failed`.
The other outcome texts (`pragma_skipped`, `pragma_executed`,
`barrier_timeout`) interpolate only values this module already holds, and are
built whether or not a log is there.
"""
import builtins as _builtins
import os
import sqlite3
import time
from collections import namedtuple

from pyteman.targets import resolve_target

#: What `_dispatch` reports back. `status` is the only required field, so an
#: action that just did its job and returns nothing says so in one word
#: instead of padding three positional `None`s. `message` becomes the
#: terminal record's human-readable `outcome` (a string, or a zero-arg
#: callable deferred until a log actually needs it; see `_safe_message`),
#: `value` is what `run_action` returns to the patched body, and `to_raise`
#: carries the deliberate exception of a `raise` action.
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

    `to_raise` is the one exception this module raises on purpose, kept out
    of the exception path so a deliberate `raise` action is logged as
    `raised` rather than being mistaken for a failure of the tool itself.
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
        # Deliberately unguarded. A resolver that raises is not a known miss,
        # it is a bug (in a spec, in the resolver, or in a workload getter it
        # walks), and it takes the generic `failed` path in `run_action` with
        # the original exception propagating unchanged. Demoting it to
        # `pragma_skipped` here would hide a defect behind a status that means
        # "there was nothing to act on", and would change runtime policy: only
        # a miss the resolver REPORTS (`con is None`) is a skip.
        con, why = (resolve_target(ctx, target_spec) if target_spec is not None
                    else _find_connection(ctx))
        if con is None:
            return _Dispatched("pragma_skipped", f"pragma skipped: {why}")
        try:
            con.execute(f"PRAGMA {rule.action['name']}={rule.action['value']}")
        except Exception as exc:
            # Still non-propagating, as it has always been: a pragma that
            # will not apply is reported, not turned into a failure of the
            # workload under test. Deferring the diagnostic is what keeps
            # that true even when rendering `exc` or `con` raises.
            return _Dispatched(
                "pragma_failed",
                lambda exc=exc, con=con:
                    f"pragma execute failed on {type(con).__name__}: {exc}")
        return _Dispatched(
            "pragma_executed",
            f"PRAGMA {rule.action['name']}={rule.action['value']} executed; "
            "the value was not read back")
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
        # caller gets back, which is the wait's own return value as before.
        return _Dispatched("barrier_timeout",
                           f"barrier {name!r} timed out after {timeout_s}s",
                           value=passed)
    raise NotImplementedError(f"unknown action kind {kind}")

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
