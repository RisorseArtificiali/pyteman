# tests/test_actions.py
import sqlite3
import time
import pytest
from pyteman.actions import run_action
from pyteman.rules import Rule

def r(action):
    return Rule(id="a", module="m", symbol="f", event="entry", action=action)

def test_sleep():
    t0 = time.monotonic()
    run_action(r({"kind": "sleep", "ms": 120}), {})
    assert time.monotonic() - t0 >= 0.12

def test_raise_builtin():
    with pytest.raises(ValueError, match="boom"):
        run_action(r({"kind": "raise", "exc": "ValueError", "message": "boom"}), {})

def test_raise_unknown_is_runtimeerror():
    with pytest.raises(RuntimeError):
        run_action(r({"kind": "raise", "exc": "NotABuiltin"}), {})

def test_pragma_on_connection_in_args():
    con = sqlite3.connect(":memory:")
    run_action(r({"kind": "pragma", "name": "synchronous", "value": "OFF"}),
               {"args": (con,), "kwargs": {}})
    assert con.execute("PRAGMA synchronous").fetchone()[0] == 0

def test_pragma_no_connection_is_noop():
    run_action(r({"kind": "pragma", "name": "synchronous", "value": "OFF"}),
               {"args": (), "kwargs": {}})
