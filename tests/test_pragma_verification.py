# tests/test_pragma_verification.py
"""Pragma readback verification (CFG-04).

What these tests pin is that the firing log stops recording four materially
different outcomes under one status. The cases that matter are the ones where
SQLite says nothing: a value it ignores, a pragma name it does not know, a
setting that cannot change inside a transaction, and a correct setting
silently overwritten. None of those raise, so none of them were previously
distinguishable from success.

Real SQLite throughout, because the whole subject is what SQLite actually
does rather than what a mock was told it does. The exceptions are the hostile
duck-typed connections, which exist precisely to be things sqlite3 is not.
"""
import json
import sqlite3

import pytest

from pyteman import pragmas
from pyteman.actions import run_action
from pyteman.firing import FiringLog
from pyteman.pragmas import PragmaVerificationError
from pyteman.rules import Rule


def rule(rid, name, value, target=None):
    action = {"kind": "pragma", "name": name, "value": value}
    if target is not None:
        action["target"] = target
    return Rule(id=rid, module="m", symbol="f", event="entry", action=action)


def fire(tmp_path, con, name, value, log=True, target=None):
    """Run one pragma action; return its terminal record (or None).

    `target="self"` reaches the first positional argument whatever its type.
    The no-target path scans for an `isinstance(v, sqlite3.Connection)`, so a
    duck-typed connection is only reachable through an explicit spec, which is
    also how a workload's own wrapper would be targeted in practice.

    The log filename is derived from what is already in `tmp_path`, so the two
    tests that fire twice get two logs without a counter shared across the
    module.
    """
    p = tmp_path / f"f{len(list(tmp_path.glob('f*.jsonl')))}.jsonl"
    fl = FiringLog(str(p)) if log else None
    run_action(rule("r", name, value, target=target),
               {"args": (con,), "kwargs": {}}, log=fl)
    if fl is None:
        return None
    fl.close()
    ends = [json.loads(l) for l in p.read_text().splitlines()
            if json.loads(l)["phase"] == "end"]
    return ends[0]


# --- the four verdicts, against real SQLite --------------------------------

def test_a_pragma_that_takes_effect_is_applied(tmp_path):
    con = sqlite3.connect(":memory:")
    end = fire(tmp_path, con, "foreign_keys", "ON")
    assert end["status"] == "pragma_applied"
    assert "before=0, after=1" in end["outcome"]


def test_a_setting_that_already_held_is_not_reported_as_this_attempts_doing(tmp_path):
    con = sqlite3.connect(":memory:")
    con.execute("PRAGMA foreign_keys=ON")
    end = fire(tmp_path, con, "foreign_keys", "ON")
    # The postcondition holds, but reading the value back cannot tell this
    # firing apart from one that did nothing, so the log says so rather than
    # taking credit.
    assert end["status"] == "pragma_already"
    assert "proved nothing about its own effect" in end["outcome"]


def test_a_pragma_ignored_inside_a_transaction_is_a_mismatch_not_a_success(tmp_path):
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE t(a)")
    con.execute("BEGIN")
    end = fire(tmp_path, con, "foreign_keys", "ON")
    # sqlite.org: foreign_keys "is a no-op within a transaction". Nothing
    # raises, and before this existed the log said `pragma_executed`.
    assert end["status"] == "pragma_mismatch"
    assert "NOT in force" in end["outcome"]
    assert "before=0, after=0" in end["outcome"]


def test_an_unrecognised_value_is_unknown_and_never_a_success(tmp_path):
    con = sqlite3.connect(":memory:")
    con.execute("PRAGMA foreign_keys=ON")
    end = fire(tmp_path, con, "foreign_keys", "banana")
    # The case that makes a total normaliser dangerous: SQLite ignores
    # `banana` and falls back, so the value READ BACK is a legitimate one.
    # Only the absence of an expectation distinguishes it from `off`.
    assert end["status"] == "pragma_unknown"
    assert end["status"] not in ("pragma_applied", "pragma_already")
    # The overwrite is what the operator needs to see, and it is in the record
    # even though the record refuses to say what it means.
    assert "before=1, after=0" in end["outcome"]


def test_a_misspelled_pragma_name_is_unknown_and_is_never_read_back(tmp_path):
    con = sqlite3.connect(":memory:")
    end = fire(tmp_path, con, "syncronous", "OFF")
    assert end["status"] == "pragma_unknown"
    assert "outside the verified perimeter" in end["outcome"]
    assert "before=<unreadable>, after=<unreadable>" in end["outcome"]


def test_an_undocumented_integer_is_unknown_even_though_sqlite_accepts_it(tmp_path):
    con = sqlite3.connect(":memory:")
    end = fire(tmp_path, con, "synchronous", "4")
    # `4` is outside the documented grammar (0|OFF|1|NORMAL|2|FULL|3|EXTRA)
    # yet SQLite stores it, so the readback WOULD agree with a naive
    # expectation. Certifying it would rest the verdict on an accident of the
    # implementation rather than on the contract.
    assert end["status"] == "pragma_unknown"
    assert "before=2, after=4" in end["outcome"]


def test_journal_mode_is_verified_as_text(tmp_path):
    con = sqlite3.connect(str(tmp_path / "j.db"))
    end = fire(tmp_path, con, "journal_mode", "WAL")
    assert end["status"] == "pragma_applied"
    assert "before='delete', after='wal'" in end["outcome"]


def test_a_boolean_value_is_outside_the_journal_mode_grammar(tmp_path):
    con = sqlite3.connect(str(tmp_path / "j2.db"))
    end = fire(tmp_path, con, "journal_mode", "ON")
    # README's own words: a quoted "ON" "loads, runs, and leaves the mode
    # exactly where it was".
    assert end["status"] == "pragma_unknown"
    assert "before='delete', after='delete'" in end["outcome"]


# --- the perimeter is a correctness requirement ----------------------------

def test_a_pragma_outside_the_perimeter_is_executed_but_never_queried(tmp_path):
    """The read form of a pragma is not always a read.

    `PRAGMA wal_checkpoint` checkpoints and `PRAGMA optimize` runs ANALYZE.
    A generic readback by name would mutate the database under test, so the
    whitelist is checked before any query is issued.
    """
    issued = []

    class Recording:
        def __init__(self, real):
            self._real = real

        def execute(self, sql):
            issued.append(sql)
            return self._real.execute(sql)

    con = sqlite3.connect(str(tmp_path / "w.db"))
    con.execute("CREATE TABLE t(a)")
    end = fire(tmp_path, Recording(con), "wal_checkpoint", "FULL", target="self")
    assert end["status"] == "pragma_unknown"
    assert issued == ["PRAGMA wal_checkpoint=FULL"], \
        "no read may be issued for a pragma outside the whitelist"


def test_a_readback_does_not_end_the_workloads_transaction(tmp_path):
    con = sqlite3.connect(str(tmp_path / "t.db"))
    con.execute("CREATE TABLE t(a)")
    con.execute("BEGIN")
    con.execute("INSERT INTO t VALUES (1)")
    fire(tmp_path, con, "foreign_keys", "ON")
    assert con.in_transaction, \
        "verifying a pragma must not commit or roll back the workload's work"
    con.rollback()
    assert con.execute("SELECT count(*) FROM t").fetchone()[0] == 0


# --- hostile ducks: the connection is workload-controlled ------------------

class HostileValue:
    def __str__(self):
        raise RuntimeError("hostile __str__")
    __repr__ = __str__

    def __eq__(self, other):
        return True  # would certify any expectation as met

    __hash__ = None


class HostileCursor:
    def __init__(self, value):
        self._value = value

    def fetchone(self):
        return (self._value,)

    def close(self):
        pass


class HostileConnection:
    """Duck-typed, as targeting explicitly permits."""

    def __init__(self, value):
        self._value = value

    def execute(self, sql):
        return HostileCursor(self._value)


def test_a_readback_value_that_lies_about_equality_cannot_claim_applied(tmp_path):
    end = fire(tmp_path, HostileConnection(HostileValue()), "foreign_keys", "ON",
                target="self")
    # `HostileValue.__eq__` returns True for everything. Comparing against it
    # at all would let a workload certify its own pragma, so the value is
    # rejected on its exact type before any comparison happens.
    assert end["status"] == "pragma_unknown"
    assert "could not be read back" in end["outcome"]


def test_an_int_subclass_is_not_accepted_as_a_readback(tmp_path):
    class Sneaky(int):
        def __eq__(self, other):
            return True
        __hash__ = int.__hash__

    end = fire(tmp_path, HostileConnection(Sneaky(0)), "foreign_keys", "ON",
                target="self")
    # `isinstance(x, int)` would pass here. Exact-type checking is the point.
    assert end["status"] == "pragma_unknown"


def test_rendering_a_hostile_value_cannot_decide_what_propagates(tmp_path):
    """The diagnostic is deferred, so building it cannot become the failure.

    A readback value is fetched through a connection the workload supplied,
    so rendering it runs workload code. An eager outcome text would raise
    from inside the action and turn a reported no-op into a failure of the
    run, which is the invariant `_safe_message` exists to hold.
    """
    con = HostileConnection(HostileValue())
    # No exception escapes, with a log or without one.
    end = fire(tmp_path, con, "synchronous", "OFF", target="self")
    assert end["status"] == "pragma_unknown"
    assert fire(tmp_path, con, "synchronous", "OFF", log=False,
                target="self") is None


def test_a_connection_whose_execute_raises_is_still_a_reported_failure(tmp_path):
    class Broken:
        def execute(self, sql):
            raise sqlite3.OperationalError("nope")

    end = fire(tmp_path, Broken(), "foreign_keys", "ON", target="self")
    # Unchanged contract: a pragma that will not apply is reported, never
    # turned into a failure of the workload under test.
    assert end["status"] == "pragma_failed"


def _hostile(self, *args):
    raise RuntimeError("hostile row")


class RowCursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row

    def close(self):
        pass


class RowConnection:
    """Hostile in the row CONTAINER rather than in the value inside it."""

    def __init__(self, row):
        self._row = row
        self.issued = []

    def execute(self, sql):
        self.issued.append(sql)
        return RowCursor(self._row)


@pytest.mark.parametrize("attribute", ["__len__", "__getitem__"])
def test_a_hostile_row_container_is_unreadable_and_still_gets_injected(
        tmp_path, attribute):
    """The shape check reads the row, and reading a row runs workload code.

    `fetchone` returns whatever the targeted object's cursor hands back, and a
    `tuple` subclass may override `__len__` or `__getitem__`. Checking the
    shape outside the `try` breaks both of this module's promises at once:
    `read` stops being total, and the baseline read stops being harmless,
    because it runs BEFORE the execute and so cancels the injection it was
    only supposed to describe.
    """
    con = RowConnection(type("Row", (tuple,), {attribute: _hostile})([1]))
    end = fire(tmp_path, con, "foreign_keys", "ON", target="self")
    assert end["status"] == "pragma_unknown"
    assert "PRAGMA foreign_keys=ON" in con.issued


class CountingCursor:
    def __init__(self, owner):
        self._owner = owner

    def fetchone(self):
        return (1,)

    def close(self):
        self._owner.closed += 1


class CountingConnection:
    """Records how many of the cursors it hands out get closed."""

    def __init__(self):
        self.closed = 0
        self.issued = []

    def execute(self, sql):
        self.issued.append(sql)
        return CountingCursor(self)


def test_the_set_statements_cursor_is_released(tmp_path):
    """A live SET statement holds a lock, so its cursor must not be dropped.

    `PRAGMA journal_mode=...` is the only pragma in the perimeter whose SET
    form returns a row, and a statement that produced a row and was never
    finalised keeps an exclusive lock: an independent connection asking for a
    write lock gets "database is locked". CPython happens to free a discarded
    cursor by refcount immediately, which is why this never surfaced, but the
    package declares no interpreter implementation, and under deferred
    finalisation the injector itself becomes the cause of the lock contention
    it exists to measure.

    Three cursors are handed out per firing (baseline read, the SET, the
    readback) and all three must come back.
    """
    con = CountingConnection()
    fire(tmp_path, con, "journal_mode", "WAL", target="self")
    assert con.issued == ["PRAGMA journal_mode", "PRAGMA journal_mode=WAL",
                          "PRAGMA journal_mode"]
    assert con.closed == 3


class UnclosableCursor(CountingCursor):
    def close(self):
        raise RuntimeError("hostile close")


class UnclosableConnection(CountingConnection):
    """Refuses to close the SET statement's cursor, and only that one.

    The two readback cursors close normally, so this isolates the release
    added at the SET site instead of also measuring what `read` does when its
    own cleanup fails, which is a separate question about a different call.
    """

    def execute(self, sql):
        self.issued.append(sql)
        if "=" in sql:
            return UnclosableCursor(self)
        return CountingCursor(self)


def test_a_cursor_that_refuses_to_close_does_not_change_the_verdict(tmp_path):
    """Releasing the cursor is housekeeping, and housekeeping cannot vote.

    `close` belongs to an object the workload supplied, so it is workload code
    like any other. The statement has already run by the time `execute`
    returns, which means the pragma is applied or not regardless of what
    happens next; letting a hostile `close` propagate would report an applied
    pragma as `pragma_failed` and, under strict mode, refuse a sound
    experiment on the strength of a cleanup call.
    """
    con = UnclosableConnection()
    end = fire(tmp_path, con, "foreign_keys", "ON", target="self")
    # Differential, because the claim is precisely that the refusal changed
    # nothing: the same firing against a cursor that closes cleanly must reach
    # the same verdict. Naming a status literally here would assert the stub's
    # readback value instead of the property under test.
    compliant = fire(tmp_path, CountingConnection(), "foreign_keys", "ON",
                     target="self")
    assert end["status"] == compliant["status"] != "pragma_failed"


class ReadbackUnclosableConnection(CountingConnection):
    """The mirror image: only the READBACK cursors refuse to close.

    The SET statement's cursor closes normally, so this measures `pragmas.read`
    and its own cleanup contract rather than the release added at the SET site.
    The two sites deliberately disagree, and this pair of stubs is what makes
    the disagreement executable instead of merely documented.
    """

    def execute(self, sql):
        self.issued.append(sql)
        if "=" in sql:
            return CountingCursor(self)
        return UnclosableCursor(self)


def test_a_readback_whose_cursor_will_not_close_is_not_certified(tmp_path):
    """A verification whose own cleanup failed is not one `read` will certify.

    This pins a decision, not an implementation detail. `read` closes its
    cursor inside the `try` that guards the value, so a `close` that raises
    costs the value already fetched and the observation becomes `UNREADABLE`,
    which reaches the log as `pragma_unknown`: no claim in either direction.

    That is the opposite of `_release` at the SET site, and the asymmetry is
    the point. The SET statement must execute whatever happens around it, so
    letting its cleanup vote would state something FALSE, reporting a pragma
    that is in force as `pragma_failed`. A readback is a verification, so
    declining to certify one whose own cleanup failed states something TRUE.
    Without this test the difference lives only in a docstring: moving `read`'s
    close into a `finally` outside the value path leaves the whole suite green
    while a hostile-close readback turns from a refusal into a certified
    `pragma_applied`.

    `CountingCursor.fetchone` returns `(1,)`, so the value itself is perfectly
    readable and the cleanup is the only thing that fails. Reaching
    `pragma_unknown` therefore cannot be blamed on an unreadable value.
    """
    con = ReadbackUnclosableConnection()
    end = fire(tmp_path, con, "foreign_keys", "ON", target="self")
    assert end["status"] == pragmas.UNVERIFIED
    # The SET still ran: declining to certify is not declining to inject.
    assert "PRAGMA foreign_keys=ON" in con.issued


def test_strict_refuses_a_readback_whose_cursor_will_not_close(tmp_path, strict):
    """And the refusal is load-bearing, not merely a word in the log.

    `pragma_unknown` is in `REFUTING`, so under strict mode an experiment built
    on a pragma that could not be verified stops instead of reporting a result.
    Asserting the verdict alone would leave a refactor free to keep the status
    and lose the consequence.
    """
    with pytest.raises(PragmaVerificationError):
        fire(tmp_path, ReadbackUnclosableConnection(), "foreign_keys", "ON",
             target="self")


def test_a_pragma_name_in_capitals_is_verified_like_any_other(tmp_path):
    # SQLite is case-insensitive about pragma names, so this one really is
    # applied. A case-sensitive perimeter lookup would report it as outside
    # the perimeter, which is a false statement in the message and, under
    # strict mode, a refusal of an experiment that was fine.
    con = sqlite3.connect(":memory:")
    end = fire(tmp_path, con, "FOREIGN_KEYS", "ON")
    assert end["status"] == "pragma_applied"
    assert con.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_an_unreadable_baseline_does_not_suppress_the_injection():
    """Observation must never stand in the way of injection.

    A tool that declines to inject when it cannot verify has hidden the very
    thing it exists to make visible.
    """
    con = sqlite3.connect(":memory:")
    reads = {"n": 0}
    real_execute = con.execute

    class FlakyBaseline:
        def execute(self, sql):
            if sql == "PRAGMA foreign_keys" and reads["n"] == 0:
                reads["n"] += 1
                raise sqlite3.OperationalError("baseline read failed")
            return real_execute(sql)

    run_action(rule("r", "foreign_keys", "ON", target="self"),
               {"args": (FlakyBaseline(),), "kwargs": {}}, log=None)
    assert con.execute("PRAGMA foreign_keys").fetchone()[0] == 1, \
        "the pragma must be executed even when the baseline cannot be read"


def test_an_unreadable_baseline_fails_closed(tmp_path):
    con = sqlite3.connect(":memory:")
    real_execute = con.execute

    class NoBaseline:
        def __init__(self):
            self.seen = 0

        def execute(self, sql):
            if sql == "PRAGMA foreign_keys":
                self.seen += 1
                if self.seen == 1:
                    raise sqlite3.OperationalError("baseline read failed")
            return real_execute(sql)

    end = fire(tmp_path, NoBaseline(), "foreign_keys", "ON", target="self")
    # The postcondition holds, but with no baseline there is no way to say
    # whether this attempt established it, so it reports the weaker verdict
    # rather than the flattering one.
    assert end["status"] == "pragma_unknown"
    assert "baseline could not be read" in end["outcome"]


# --- the normaliser is partial, and that is the point ----------------------

@pytest.mark.parametrize("name,value,expected", [
    ("foreign_keys", "ON", 1), ("foreign_keys", "on", 1),
    ("foreign_keys", "true", 1), ("foreign_keys", "yes", 1),
    ("foreign_keys", 1, 1), ("foreign_keys", "1", 1),
    ("foreign_keys", "OFF", 0), ("foreign_keys", "false", 0),
    ("foreign_keys", "no", 0), ("foreign_keys", 0, 0),
    ("synchronous", "NORMAL", 1), ("synchronous", "FULL", 2),
    ("synchronous", "EXTRA", 3), ("synchronous", "2", 2),
    ("synchronous", "off", 0),
    ("journal_mode", "WAL", "wal"), ("journal_mode", "wal", "wal"),
    ("journal_mode", "DELETE", "delete"),
])
def test_the_documented_vocabulary_normalises(name, value, expected):
    assert pragmas.normalise(name, value) == expected


@pytest.mark.parametrize("name,value", [
    ("foreign_keys", "banana"), ("foreign_keys", ""), ("foreign_keys", "2"),
    ("synchronous", "4"), ("synchronous", "-1"), ("synchronous", "banana"),
    ("journal_mode", "ON"), ("journal_mode", "1"), ("journal_mode", "banana"),
    ("temp.synchronous", "OFF"), ("syncronous", "OFF"), ("optimize", "1"),
])
def test_everything_outside_it_has_no_expectation_at_all(name, value):
    # Partial by design: an unrecognised token must not be mapped to a
    # default, because the default is what SQLite falls back to anyway, which
    # would make the two indistinguishable.
    assert pragmas.normalise(name, value) is pragmas.UNKNOWN


def test_the_refuting_set_names_every_status_that_is_not_an_attestation():
    assert pragmas.REFUTING == {"pragma_mismatch", "pragma_unknown",
                                "pragma_failed", "pragma_skipped"}
    assert pragmas.APPLIED not in pragmas.REFUTING
    assert pragmas.ALREADY not in pragmas.REFUTING
    # `failed` is deliberately absent: it is the generic action-level status,
    # produced by `run_action` for any action kind, and this module has no
    # business owning it. A consumer that wants both unions it in, which is
    # what `examples/hermes-111912/run_repro.py` does; the test that it still
    # refutes a generic `failed` after that switch lives beside it in
    # `tests/test_example_log_consumers.py`.
    assert "failed" not in pragmas.REFUTING


# --- strict mode -----------------------------------------------------------

@pytest.fixture
def strict(monkeypatch):
    monkeypatch.setenv("PYTEMAN_STRICT_PRAGMA", "1")


@pytest.mark.parametrize("name,value,status", [
    ("foreign_keys", "banana", "pragma_unknown"),
    ("syncronous", "OFF", "pragma_unknown"),
])
def test_strict_refuses_an_unverified_pragma(tmp_path, strict, name, value, status):
    con = sqlite3.connect(":memory:")
    p = tmp_path / "f.jsonl"
    log = FiringLog(str(p))
    with pytest.raises(PragmaVerificationError):
        run_action(rule("r", name, value), {"args": (con,), "kwargs": {}}, log=log)
    log.close()

    end = [json.loads(l) for l in p.read_text().splitlines()
           if json.loads(l)["phase"] == "end"][0]
    # The record keeps the SEMANTIC status. Raising from inside `_dispatch`
    # would have taken the generic handler and recorded `failed`, losing
    # which of the four verdicts refused the experiment.
    assert end["status"] == status
    starts = [json.loads(l) for l in p.read_text().splitlines()
              if json.loads(l)["phase"] == "start"]
    assert len(starts) == 1 and len(p.read_text().splitlines()) == 2, \
        "one attempt, one start, one end"


def test_strict_refuses_a_skip_and_a_failure(strict):
    with pytest.raises(PragmaVerificationError):
        run_action(rule("r", "foreign_keys", "ON"),
                   {"args": (), "kwargs": {}}, log=None)
    con = sqlite3.connect(":memory:")
    con.close()
    with pytest.raises(PragmaVerificationError):
        run_action(rule("r", "foreign_keys", "ON"),
                   {"args": (con,), "kwargs": {}}, log=None)


def test_strict_allows_a_verified_pragma_through(tmp_path, strict):
    con = sqlite3.connect(":memory:")
    assert fire(tmp_path, con, "foreign_keys", "ON")["status"] == "pragma_applied"
    assert fire(tmp_path, con, "foreign_keys", "ON")["status"] == "pragma_already"


def test_strict_is_off_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("PYTEMAN_STRICT_PRAGMA", raising=False)
    con = sqlite3.connect(":memory:")
    # The documented promise that a pragma is reported and never raised holds
    # unless the operator opts out of it.
    assert fire(tmp_path, con, "foreign_keys", "banana")["status"] == "pragma_unknown"


def test_strict_is_read_at_firing_time_not_at_import(tmp_path, monkeypatch):
    con = sqlite3.connect(":memory:")
    monkeypatch.delenv("PYTEMAN_STRICT_PRAGMA", raising=False)
    assert fire(tmp_path, con, "foreign_keys", "banana")["status"] == "pragma_unknown"
    monkeypatch.setenv("PYTEMAN_STRICT_PRAGMA", "1")
    # A matrix cell sets the variable for the run it is about to execute; a
    # value frozen at import would apply the previous cell's setting.
    with pytest.raises(PragmaVerificationError):
        run_action(rule("r", "foreign_keys", "banana"),
                   {"args": (con,), "kwargs": {}}, log=None)


def test_the_strict_error_carries_no_value_read_from_the_workload(strict):
    con = HostileConnection(HostileValue())
    with pytest.raises(PragmaVerificationError) as ei:
        run_action(rule("r", "foreign_keys", "ON", target="self"),
                   {"args": (con,), "kwargs": {}}, log=None)
    # Constructing the message must not render a workload-controlled value:
    # that would raise from the constructor and replace this exception with
    # an unrelated one.
    assert "foreign_keys=ON" in str(ei.value)
    assert "pragma_unknown" in str(ei.value)


def test_strict_raises_even_with_no_log_configured(strict):
    con = sqlite3.connect(":memory:")
    # There is no terminal record to fall back on here, which is exactly why
    # the exception cannot be conditional on logging being set up.
    with pytest.raises(PragmaVerificationError):
        run_action(rule("r", "foreign_keys", "banana"),
                   {"args": (con,), "kwargs": {}}, log=None)


def test_a_failing_log_does_not_replace_the_strict_error(strict):
    class BrokenLog:
        def record(self, rule, ctx, **kw):
            if kw.get("phase") == "end":
                raise OSError("disk full")
            return type("Id", (), {"attempt": 1})()

    con = sqlite3.connect(":memory:")
    with pytest.raises(PragmaVerificationError) as ei:
        run_action(rule("r", "foreign_keys", "banana"),
                   {"args": (con,), "kwargs": {}}, log=BrokenLog())
    # Precedence, unchanged by this task: the exception the action is already
    # carrying wins, and the log failure rides along as a note.
    assert any("disk full" in n for n in getattr(ei.value, "__notes__", []))


def test_the_strict_error_is_not_a_class_a_raise_action_can_name():
    import builtins
    assert not hasattr(builtins, "PragmaVerificationError")
    # So an injected fault can never be mistaken for a refusal to run, nor
    # the other way round.
    assert isinstance(PragmaVerificationError("x"), AssertionError)


def test_an_uncaught_strict_error_leaves_the_instrumented_body(strict):
    """What strict actually guarantees, and no more.

    The exception leaves the patched call, so the body does not continue past
    the pragma. It does NOT guarantee the process ends: an ordinary
    `except Exception` in the workload swallows it like any other, and
    nothing reconciles the firing log against the results database.
    """
    con = sqlite3.connect(":memory:")
    reached = []

    def body():
        run_action(rule("r", "foreign_keys", "banana"),
                   {"args": (con,), "kwargs": {}}, log=None)
        reached.append("after the pragma")

    with pytest.raises(PragmaVerificationError):
        body()
    assert reached == [], "the instrumented body must not continue"

    def catching_body():
        try:
            run_action(rule("r", "foreign_keys", "banana"),
                       {"args": (con,), "kwargs": {}}, log=None)
        except Exception:
            pass
        reached.append("workload swallowed it")

    catching_body()
    assert reached == ["workload swallowed it"], \
        "a workload that catches it continues; the docs must not promise otherwise"


def test_the_runner_records_the_cell_as_failed_when_strict_refuses(tmp_path, strict):
    """The one place strict mode's guarantee is actually cashed.

    The exception has to travel the whole way: out of the action, out of the
    workload's cell callback, into `run_matrix`'s `except Exception`, and into
    the results database. Asserting on the raise alone would prove that the
    exception exists, not that anything acts on it, and nothing reconciles the
    firing log against this table afterwards.
    """
    from pyteman.runner.matrix import run_matrix

    def run_cell(cell, adir):
        con = sqlite3.connect(":memory:")
        run_action(rule("r", "foreign_keys", "banana"),
                   {"args": (con,), "kwargs": {}}, log=None)
        return {"signature": "REACHED"}   # never, if the refusal works

    db = str(tmp_path / "r.db")
    out = run_matrix([{"id": "c1", "params": {}}], run_cell, db,
                     str(tmp_path / "art"), experiment=None)
    assert [r["status"] for r in out] == ["failed"]

    con = sqlite3.connect(db)
    status, result = con.execute(
        "SELECT status, result_json FROM results WHERE cell_id='c1'").fetchone()
    con.close()
    assert status == "failed"
    # The stored error names the refusal, so an operator reading the results
    # table alone can tell an invalid experiment from a workload bug.
    assert "PragmaVerificationError" in result
    assert "REACHED" not in result
