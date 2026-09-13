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
        con = _find_connection(ctx)
        if con is not None:
            con.execute(f"PRAGMA {rule.action['name']}={rule.action['value']}")
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
    for v in list(ctx.get("args", ())) + list(ctx.get("kwargs", {}).values()):
        if isinstance(v, sqlite3.Connection):
            return v
    return None
