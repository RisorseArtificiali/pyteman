# src/pyteman/actions.py
"""Action execution for injected rules.

Trusted-operator posture: rules come from operator-authored YAML used for
local test tooling, never from untrusted input. By design, `when` condition
expressions and `pragma` name/value strings are passed through unsanitized;
`raise` resolves only builtin exception classes. Extending this module to
face untrusted rule sources would require sanitizing all three.
"""
import builtins as _builtins
import os
import sqlite3
import time

from pyteman.targets import resolve_target

def run_action(rule, ctx, log=None):
    if log is not None:
        log.record(rule, ctx, note=str(rule.action))
    kind = rule.action["kind"]
    if kind == "return_value":
        ctx["_override"] = rule.action.get("value")
        return
    if kind == "return_none":
        ctx["_override"] = None
        return
    if kind == "sleep":
        time.sleep(int(rule.action.get("ms", 0)) / 1000.0)
        return
    if kind == "raise":
        name = rule.action.get("exc", "RuntimeError")
        exc = getattr(_builtins, name, None)
        if not isinstance(exc, type) or not issubclass(exc, BaseException):
            raise RuntimeError(f"unknown exception class {name}")
        raise exc(rule.action.get("message", "pyteman injected"))
    if kind == "pragma":
        target_spec = rule.action.get("target")
        con, why = (resolve_target(ctx, target_spec) if target_spec is not None
                    else _find_connection(ctx))
        if con is None:
            _note(log, rule, ctx, f"pragma skipped: {why}")
            return
        try:
            con.execute(f"PRAGMA {rule.action['name']}={rule.action['value']}")
        except Exception as exc:
            _note(log, rule, ctx, f"pragma execute failed on {type(con).__name__}: {exc}")
        return
    if kind == "kill":
        os._exit(int(rule.action.get("exit_code", 70)))
    if kind == "barrier":
        from pyteman import barriers
        name = rule.action["barrier"]
        if rule.action.get("role", "wait") == "open":
            barriers.open(name)
            return True
        return barriers.wait(name, timeout_s=float(rule.action.get("timeout_s", 30)))
    raise NotImplementedError(f"unknown action kind {kind}")

def _find_connection(ctx):
    """Legacy no-target path: (con, None) or (None, reason), same protocol
    as resolve_target so the pragma action has one miss branch."""
    for v in list(ctx.get("args", ())) + list(ctx.get("kwargs", {}).values()):
        if isinstance(v, sqlite3.Connection):
            return v, None
    return None, "no target spec and no sqlite3.Connection in the call arguments"


def _note(log, rule, ctx, message):
    # Unresolvable pragma targets must be visible, not silent no-ops: the
    # firing log is the operator's only channel when the workload runs in a
    # container. A separate outcome record (new seq) keeps the attempt and
    # its result distinguishable; but an identical miss repeats on every
    # call under fire: always, so record each distinct (rule, message) once
    # per LOG INSTANCE, never per process: a second FiringLog in the same
    # process (a reopened leg, a new test) must still see its own note.
    if log is None:
        return
    noted = getattr(log, "_pyteman_noted", None)
    if noted is None:
        noted = log._pyteman_noted = set()
    key = (rule.id, message)
    if key not in noted:
        noted.add(key)  # idempotent; a rare check-then-add race costs one duplicate line
        log.record(rule, ctx, outcome=message)
