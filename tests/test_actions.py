# tests/test_actions.py
import sqlite3
import time
import pytest
from pyteman.actions import run_action
from pyteman.rules import Rule, load_rules

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

def test_pragma_on_connection_in_kwargs():
    con = sqlite3.connect(":memory:")
    run_action(r({"kind": "pragma", "name": "synchronous", "value": "OFF"}),
               {"args": (), "kwargs": {"con": con}})
    assert con.execute("PRAGMA synchronous").fetchone()[0] == 0

def test_pragma_no_connection_is_noop():
    run_action(r({"kind": "pragma", "name": "synchronous", "value": "OFF"}),
               {"args": (), "kwargs": {}})


# The pragma value contract, measured against a real database instead of
# declared. TASK-9 / CFG-03. Two things are pinned here and the loader can
# prove neither, because it only ever sees the YAML.
#
# A value the loader accepts is not a value SQLite applies. journal_mode is
# keyword-valued, so a quoted "ON" and a bare integer both load, both execute,
# and both leave the mode exactly where it was. Quoting removes the YAML
# ambiguity and nothing else.
#
# The baselines are chosen rather than convenient. An unrecognised word on a
# boolean-valued pragma resolves to that pragma's default, so a case whose
# expected answer happens to equal that default cannot tell recognition from
# fallback. Every row claiming an effect therefore starts on the opposite side
# of the default, which is why synchronous starts at 2 and foreign_keys at 0.
#
# What the toolkit should RECORD when an accepted value has no effect is
# CFG-04, and nothing here anticipates that decision.
PRAGMA_EFFECTS = [
    # pragma, baseline, the value as written in YAML, the value read back after
    ("journal_mode", "delete", '"OFF"', "off"),
    ("journal_mode", "delete", '"ON"', "delete"),
    ("journal_mode", "delete", "1", "delete"),
    ("synchronous", "2", '"OFF"', 0),
    ("synchronous", "0", "3", 3),
    ("foreign_keys", "0", '"ON"', 1),
    ("foreign_keys", "1", '"OFF"', 0),
]


def _loaded(tmp_path, name, written):
    """One pragma rule, through the real loader, from real YAML text.

    Written as text rather than built as a Rule so that the quoting policy
    under test is exercised by the code that enforces it.
    """
    path = tmp_path / "rules.yaml"
    path.write_text(
        "- id: probe\n"
        "  point: m.f\n"
        "  event: entry\n"
        "  action:\n"
        "    kind: pragma\n"
        f"    name: {name}\n"
        f"    value: {written}\n"
    )
    return load_rules(str(path))[0]


def _on_disk(tmp_path, tag, name, baseline):
    con = sqlite3.connect(tmp_path / f"{tag}.db")
    con.execute("CREATE TABLE t (x)")  # materializes the journal mode
    con.execute(f"PRAGMA {name}={baseline}")
    assert str(con.execute(f"PRAGMA {name}").fetchone()[0]).lower() == baseline
    return con


@pytest.mark.parametrize(
    "name,baseline,written,expected", PRAGMA_EFFECTS,
    ids=[f"{n}={w}-from-{b}" for n, b, w, _ in PRAGMA_EFFECTS],
)
def test_a_loaded_pragma_value_lands_where_the_matrix_says(
        tmp_path, name, baseline, written, expected):
    con = _on_disk(tmp_path, name, name, baseline)
    run_action(_loaded(tmp_path, name, written), {"args": (con,), "kwargs": {}})
    assert con.execute(f"PRAGMA {name}").fetchone()[0] == expected


def test_a_value_the_loader_accepts_can_still_do_nothing(tmp_path):
    """The no-effect rows above, kept from passing vacuously.

    "ON" leaving journal_mode alone is evidence of a silent no-op only if the
    same loader, the same action and the same database can be shown to move
    that mode at all. The pair is the assertion; either half alone would hold
    just as well if run_action did nothing whatsoever.
    """
    con = _on_disk(tmp_path, "contrast", "journal_mode", "delete")

    run_action(_loaded(tmp_path, "journal_mode", '"ON"'),
               {"args": (con,), "kwargs": {}})
    assert con.execute("PRAGMA journal_mode").fetchone()[0] == "delete"

    run_action(_loaded(tmp_path, "journal_mode", '"OFF"'),
               {"args": (con,), "kwargs": {}})
    assert con.execute("PRAGMA journal_mode").fetchone()[0] == "off"
