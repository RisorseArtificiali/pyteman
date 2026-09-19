# tests/test_log_actions.py
"""The attempt/outcome contract (LOG-02).

A firing record proves an ATTEMPT. What these tests pin is that an attempt's
result is recoverable from the log without ever inferring it from adjacency,
from the absence of a record, or from a rule id, none of which carry the
information. The cases are the ones the audit named: interleaved firings,
a repeated identical failure, a target miss, and a kill in a subprocess.
"""
import builtins as _builtins
import json
import multiprocessing as mp
import sqlite3
import threading
import time

import pytest

from pyteman.actions import run_action
from pyteman.barriers import BarrierTimeoutError
from pyteman.firing import FiringLog, FiringLogError, RecordId
from pyteman.rules import Rule

# Bounds every wait on a child here, so a regression fails red instead of
# hanging the runner.
CHILD_BUDGET_S = 30
REAP_BUDGET_S = 5


def rule(rid, action, module="m", symbol="f"):
    return Rule(id=rid, module=module, symbol=symbol, event="entry", action=action)


def records(path):
    return [json.loads(l) for l in path.read_text().splitlines()]


def starts(recs):
    return [r for r in recs if r["phase"] == "start"]


def ends(recs):
    return [r for r in recs if r["phase"] == "end"]


def attempts(recs):
    """Group each start with its terminal record, the way a consumer must.

    Keyed on (instance, pid, attempt) and never on order in the file, which
    is exactly what interleaved writers destroy.
    """
    grouped = {}
    for r in recs:
        grouped.setdefault((r["instance"], r["pid"], r["attempt"]), {})[r["phase"]] = r
    return grouped


# --- correlation under interleaving ----------------------------------------

def test_interleaved_threads_on_one_rule_produce_distinct_attempts(tmp_path):
    # Same rule, same log, no "fires" ticket, so `visit` is null on every
    # record and cannot be the join key. The attempt id has to carry it.
    p = tmp_path / "f.jsonl"
    log = FiringLog(str(p))
    r = rule("w", {"kind": "sleep", "ms": 1})
    barrier = threading.Barrier(4)

    def fire():
        barrier.wait()
        for _ in range(5):
            run_action(r, {}, log=log)

    threads = [threading.Thread(target=fire) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(CHILD_BUDGET_S)
        assert not t.is_alive(), f"a firing thread was still running after {CHILD_BUDGET_S}s"
    log.close()

    recs = records(p)
    assert len(starts(recs)) == 20 and len(ends(recs)) == 20
    assert all(r["visit"] is None for r in recs), \
        "the fixture must have no fires ticket, or it is not testing the attempt id"

    grouped = attempts(recs)
    assert len(grouped) == 20, "20 attempts must stay 20 distinct correlation keys"
    for key, pair in grouped.items():
        assert set(pair) == {"start", "end"}, f"attempt {key} is missing a phase"
        assert pair["start"]["seq"] == pair["start"]["attempt"], \
            "a start record's attempt is its own seq"
        assert pair["end"]["status"] == "slept"
        # The pairing must hold on identity, not on the two records happening
        # to sit next to each other or to share a thread name.
        assert pair["start"]["rule"] == pair["end"]["rule"] == "w"


def test_two_rules_sharing_an_id_are_still_separate_attempts(tmp_path):
    # rule.id is unique only within one load_rules call, so two scopes can
    # both emit id "w". Nothing in the correlation may lean on it.
    p = tmp_path / "f.jsonl"
    log = FiringLog(str(p))
    first = rule("w", {"kind": "sleep", "ms": 0}, module="one")
    second = rule("w", {"kind": "return_none"}, module="two")
    run_action(first, {}, log=log)
    run_action(second, {}, log=log)
    log.close()

    recs = records(p)
    grouped = attempts(recs)
    assert len(grouped) == 2, "a shared rule id must not collapse two attempts into one"
    by_point = {pair["start"]["point"]: pair["end"]["status"] for pair in grouped.values()}
    assert by_point == {"one.f": "slept", "two.f": "override_requested"}


# --- a repeated identical failure ------------------------------------------

def test_every_repeat_of_one_miss_gets_its_own_terminal_record(tmp_path):
    # The old dedup wrote this once, which made three misses indistinguishable
    # from one and broke the attempt count outright.
    p = tmp_path / "f.jsonl"
    log = FiringLog(str(p))
    r = rule("miss", {"kind": "pragma", "name": "synchronous", "value": "OFF"})
    for _ in range(3):
        run_action(r, {"args": (), "kwargs": {}}, log=log)
    log.close()

    recs = records(p)
    assert len(starts(recs)) == 3
    terminals = ends(recs)
    assert len(terminals) == 3
    assert {t["status"] for t in terminals} == {"pragma_skipped"}
    assert all("no target spec" in t["outcome"] for t in terminals)
    assert len({t["attempt"] for t in terminals}) == 3, \
        "three misses must correlate to three different attempts"


def test_a_pragma_that_applies_is_logged_as_applied_with_both_readings(tmp_path):
    p = tmp_path / "f.jsonl"
    log = FiringLog(str(p))
    con = sqlite3.connect(":memory:")
    try:
        run_action(rule("ok", {"kind": "pragma", "name": "synchronous", "value": "OFF"}),
                   {"args": (con,), "kwargs": {}}, log=log)
    finally:
        con.close()
    log.close()

    end = ends(records(p))[0]
    # This replaces the retired `pragma_executed`, which meant only that the
    # statement did not raise. SQLite gives that away for free even for a
    # pragma it ignored entirely, so it was recorded identically whether the
    # setting took effect or not.
    assert end["status"] == "pragma_applied"
    assert "before=2, after=0" in end["outcome"]
    # "Observed" and not "caused": the connection may be shared, so the log
    # must not be sayable as a claim of exclusive causality.
    assert "not a claim of exclusive causality" in end["outcome"]


def test_a_pragma_that_fails_is_reported_and_does_not_propagate(tmp_path):
    p = tmp_path / "f.jsonl"
    log = FiringLog(str(p))
    con = sqlite3.connect(":memory:")
    con.close()  # every execute on it now raises
    run_action(rule("boom", {"kind": "pragma", "name": "synchronous", "value": "OFF"}),
               {"args": (con,), "kwargs": {}}, log=log)  # must not raise
    log.close()

    end = ends(records(p))[0]
    assert end["status"] == "pragma_failed"
    assert "pragma execute failed" in end["outcome"]


# --- intended raise versus an unexpected failure ---------------------------

def test_a_deliberate_raise_is_logged_as_raised_not_failed(tmp_path):
    p = tmp_path / "f.jsonl"
    log = FiringLog(str(p))
    with pytest.raises(ValueError, match="boom"):
        run_action(rule("r", {"kind": "raise", "exc": "ValueError", "message": "boom"}),
                   {}, log=log)
    log.close()

    recs = records(p)
    end = ends(recs)[0]
    assert end["status"] == "raised", \
        "the action did exactly what it was asked to do; that is not a failure"
    assert end["attempt"] == starts(recs)[0]["seq"]
    assert "ValueError: boom" in end["outcome"]


def test_an_unresolvable_exception_class_is_logged_as_failed(tmp_path):
    p = tmp_path / "f.jsonl"
    log = FiringLog(str(p))
    with pytest.raises(RuntimeError, match="unknown exception class"):
        run_action(rule("r", {"kind": "raise", "exc": "NotABuiltin"}), {}, log=log)
    log.close()

    end = ends(records(p))[0]
    assert end["status"] == "failed", \
        "the rule could not be carried out at all, which is a different fact"
    assert "unknown exception class" in end["outcome"]


def test_a_failure_constructing_the_exception_is_failed_and_keeps_its_identity(tmp_path):
    # UnicodeDecodeError needs five arguments; one string is a TypeError out
    # of the constructor, before anything is deliberately raised.
    p = tmp_path / "f.jsonl"
    log = FiringLog(str(p))
    with pytest.raises(TypeError) as excinfo:
        run_action(rule("r", {"kind": "raise", "exc": "UnicodeDecodeError",
                              "message": "nope"}), {}, log=log)
    log.close()

    assert type(excinfo.value) is TypeError, "the original exception must reach the caller"
    end = ends(records(p))[0]
    assert end["status"] == "failed"
    assert end["outcome"].startswith("TypeError")


def test_an_unknown_action_kind_is_failed(tmp_path):
    p = tmp_path / "f.jsonl"
    log = FiringLog(str(p))
    with pytest.raises(NotImplementedError):
        run_action(rule("r", {"kind": "nonesuch"}), {}, log=log)
    log.close()

    assert ends(records(p))[0]["status"] == "failed"


# --- override is a request, not an outcome ---------------------------------

def test_an_override_is_logged_as_requested_only(tmp_path):
    p = tmp_path / "f.jsonl"
    log = FiringLog(str(p))
    ctx = {}
    run_action(rule("o", {"kind": "return_value", "value": "S"}), ctx, log=log)
    log.close()

    end = ends(records(p))[0]
    assert ctx["_override"] == "S"
    # run_action returns before the patcher decides what the call returns, so
    # the log may not claim the body WAS overridden.
    assert end["status"] == "override_requested"
    assert "applied" not in (end.get("outcome") or "")


# --- a barrier timeout is visible without changing what the caller gets -----

def test_a_barrier_timeout_is_a_visible_outcome_and_the_return_value_is_unchanged(tmp_path, monkeypatch):
    # Explicit, because this case now depends on an environment variable it
    # does not set: inherited from the operator's shell, PYTEMAN_STRICT_BARRIER
    # would turn the documented default under test into a refusal and this
    # test would report the default as broken.
    monkeypatch.delenv("PYTEMAN_STRICT_BARRIER", raising=False)
    p = tmp_path / "f.jsonl"
    log = FiringLog(str(p))
    r = rule("b", {"kind": "barrier", "barrier": "never-opened", "timeout_s": 0.05})
    result = run_action(r, {}, log=log)
    log.close()

    assert result is False, "the wait's own return value must reach the caller untouched"
    end = ends(records(p))[0]
    assert end["status"] == "barrier_timeout"
    assert "timed out" in end["outcome"]


def test_a_barrier_that_opens_is_logged_and_still_returns_true(tmp_path):
    p = tmp_path / "f.jsonl"
    log = FiringLog(str(p))
    r = rule("b", {"kind": "barrier", "barrier": "opened-here", "role": "open"})
    assert run_action(r, {}, log=log) is True
    log.close()

    assert ends(records(p))[0]["status"] == "barrier_opened"


# --- strict mode turns a failed barrier into a refusal ---------------------

def _barrier_rule(rid="b", name="never-opened", **extra):
    # The wait budget is added only for a wait. An `open` rule carrying
    # timeout_s is exactly the shape the loader now refuses, and building one
    # here would document dispatch behaviour for a rule no operator can
    # write; `rule()` goes straight to the Rule constructor, so nothing else
    # in this module would notice.
    action = {"kind": "barrier", "barrier": name}
    if extra.get("role", "wait") != "open":
        action["timeout_s"] = 0.05
    return rule(rid, dict(action, **extra))


@pytest.fixture
def clean_barriers():
    # barriers._state is process-global and this module has no autouse reset,
    # so a name opened by one test would stay open for every test after it.
    from pyteman import barriers
    barriers.reset_all()
    yield
    barriers.reset_all()


def test_strict_refuses_a_timed_out_barrier_under_its_own_status(tmp_path,
                                                                 monkeypatch):
    """One attempt, one terminal record, and that record is not `failed`.

    The status is what says WHY the experiment was refused. Raising from
    inside `_dispatch` would take the generic handler in `run_action` and
    write `failed`, which is also what an action kind that does not exist
    writes, so the log could no longer tell a synchronisation failure from a
    broken rule.
    """
    monkeypatch.setenv("PYTEMAN_STRICT_BARRIER", "1")
    p = tmp_path / "f.jsonl"
    log = FiringLog(str(p))
    with pytest.raises(BarrierTimeoutError):
        run_action(_barrier_rule(), {}, log=log)
    log.close()

    recs = records(p)
    assert len(starts(recs)) == 1 and len(recs) == 2, "one attempt, one start, one end"
    end = ends(recs)[0]
    assert end["status"] == "barrier_timeout"
    assert "timed out" in end["outcome"]


def test_strict_leaves_an_opened_barrier_and_a_released_wait_alone(tmp_path,
                                                                   monkeypatch,
                                                                   clean_barriers):
    """A negative control, and only that.

    It pins that strict mode leaves the two non-timeout branches alone, which
    is what a refusal wired one branch too high would break. It passes with
    the `to_raise` wiring reverted, so it is not evidence that the wiring
    works; the four cases around it are.
    """
    monkeypatch.setenv("PYTEMAN_STRICT_BARRIER", "1")
    p = tmp_path / "f.jsonl"
    log = FiringLog(str(p))
    assert run_action(_barrier_rule("o", "strict-opened", role="open"), {}, log=log) is True
    # Opened just above, so the wait is released rather than timing out and
    # strict mode has nothing to refuse.
    assert run_action(_barrier_rule("w", "strict-opened"), {}, log=log) is True
    log.close()
    assert [r["status"] for r in ends(records(p))] == ["barrier_opened", "barrier_passed"]


def test_strict_is_off_by_default_and_read_at_firing_time(tmp_path, monkeypatch):
    monkeypatch.delenv("PYTEMAN_STRICT_BARRIER", raising=False)
    p = tmp_path / "f.jsonl"
    log = FiringLog(str(p))
    # The documented default: the timeout is reported, the caller gets False
    # and the body runs.
    assert run_action(_barrier_rule(), {}, log=log) is False
    monkeypatch.setenv("PYTEMAN_STRICT_BARRIER", "1")
    # A matrix cell sets the variable for the run it is about to execute; a
    # value frozen at import would apply the previous cell's setting to it.
    with pytest.raises(BarrierTimeoutError):
        run_action(_barrier_rule(), {}, log=log)
    log.close()
    assert [r["status"] for r in ends(records(p))] == ["barrier_timeout"] * 2


def test_strict_refuses_even_with_no_log_configured(monkeypatch):
    monkeypatch.setenv("PYTEMAN_STRICT_BARRIER", "1")
    # There is no terminal record to fall back on here, which is exactly why
    # the refusal cannot be conditional on logging being set up.
    with pytest.raises(BarrierTimeoutError):
        run_action(_barrier_rule(), {}, log=None)


def test_the_strict_barrier_error_outranks_a_failed_terminal_write(monkeypatch):
    monkeypatch.setenv("PYTEMAN_STRICT_BARRIER", "1")
    log = _FailingTerminal()
    with pytest.raises(BarrierTimeoutError) as excinfo:
        run_action(_barrier_rule(), {}, log=log)
    # The refusal is what the caller must see; the logging failure rides
    # along as a note rather than masking it.
    notes = "\n".join(getattr(excinfo.value, "__notes__", []))
    assert "terminal write failed" in notes and "'barrier_timeout'" in notes


# --- kill: a start with no terminal, by construction ------------------------

def _kill_child(path):
    log = FiringLog(path)  # its own instance: fork is refused, this is spawn
    run_action(rule("k", {"kind": "kill", "exit_code": 66}), {}, log=log)
    log.close()  # unreachable: os._exit runs inside the action


def test_a_killed_process_leaves_an_attempt_with_no_outcome(tmp_path):
    p = tmp_path / "f.jsonl"
    proc = mp.get_context("spawn").Process(target=_kill_child, args=(str(p),))
    proc.start()
    try:
        proc.join(CHILD_BUDGET_S)
        assert not proc.is_alive(), \
            f"the kill child was still running after {CHILD_BUDGET_S}s"
        assert proc.exitcode == 66
    finally:
        if proc.is_alive():
            proc.kill()
            proc.join(REAP_BUDGET_S)

    recs = records(p)
    assert len(starts(recs)) == 1 and ends(recs) == [], \
        "os._exit skips every finalizer, so there is no terminal record to write"
    # The point of the whole task: this shape means UNKNOWN, and a consumer
    # that reads a missing terminal as success is reading it wrong.
    (pair,) = attempts(recs).values()
    assert "end" not in pair


# --- what happens when the terminal record itself cannot be written --------

class _FailingTerminal:
    """Writes the start record, then refuses the terminal one."""

    def __init__(self):
        self.calls = []

    def record(self, rule, ctx, note=None, outcome=None,
               phase="start", attempt=None, status=None):
        self.calls.append(phase)
        if phase == "end":
            raise FiringLogError("terminal write failed")
        return RecordId("i", 1, 1, 1)


def test_a_failed_terminal_write_after_a_clean_action_is_reported():
    log = _FailingTerminal()
    ctx = {}
    with pytest.raises(FiringLogError, match="terminal write failed"):
        run_action(rule("o", {"kind": "return_value", "value": "S"}), ctx, log=log)
    # The action ran and its effect stands; what failed is the logging, and
    # saying so is not the same as saying the action failed.
    assert ctx["_override"] == "S"
    assert log.calls == ["start", "end"]


def test_the_actions_own_error_outranks_a_failed_terminal_write():
    log = _FailingTerminal()
    with pytest.raises(ValueError, match="boom") as excinfo:
        run_action(rule("r", {"kind": "raise", "exc": "ValueError", "message": "boom"}),
                   {}, log=log)
    # The injected exception is what the caller must see; the logging failure
    # rides along as a note rather than masking it.
    assert type(excinfo.value) is ValueError
    notes = "\n".join(getattr(excinfo.value, "__notes__", []))
    assert "terminal write failed" in notes and "'raised'" in notes


def test_a_failed_start_record_means_the_action_never_runs():
    class _RefusingLog:
        def record(self, *a, **k):
            raise FiringLogError("start write failed")

    ctx = {}
    with pytest.raises(FiringLogError, match="start write failed"):
        run_action(rule("o", {"kind": "return_value", "value": "S"}), ctx, log=_RefusingLog())
    assert "_override" not in ctx, \
        "an attempt that could not be recorded must not have happened"


def test_a_log_that_returns_no_attempt_id_is_named_not_an_attribute_error():
    # The pre-LOG-02 record() returned None. A log shim still written that
    # way must fail saying which contract is missing, instead of an
    # AttributeError on NoneType surfacing inside the workload under test.
    class _OldStyleLog:
        def record(self, *a, **k):
            return None

    ctx = {}
    with pytest.raises(TypeError, match="must return a RecordId"):
        run_action(rule("o", {"kind": "return_value", "value": "S"}), ctx, log=_OldStyleLog())
    assert "_override" not in ctx, "the action must not run on a broken log contract"


def test_a_ctrl_c_during_the_terminal_write_does_not_erase_the_actions_exception():
    # The action's own exception has not been RAISED yet when the terminal
    # record is written, so an interruption escaping here would not even
    # leave it behind as __context__: it would be gone outright.
    class _InterruptedTerminal:
        def record(self, rule, ctx, note=None, outcome=None,
                   phase="start", attempt=None, status=None):
            if phase == "end":
                raise KeyboardInterrupt("ctrl-c mid-write")
            return RecordId("i", 1, 1, 1)

    exc = raises_exactly(
        ValueError,
        lambda: run_action(
            rule("r", {"kind": "raise", "exc": "ValueError", "message": "boom"}),
            {}, log=_InterruptedTerminal()))
    assert "boom" in str(exc)
    notes = "\n".join(getattr(exc, "__notes__", []))
    assert "KeyboardInterrupt" in notes, \
        "the interruption must still be visible, as a note on the winner"


def raises_exactly(expected, call):
    """Assert `call` raises exactly `expected`, and return it.

    Deliberately not `pytest.raises`: pytest treats an escaping
    KeyboardInterrupt as a session interrupt, so a regression in these rows
    would end the run at the first one with no FAILED line and every later
    test silently unrun. Catching BaseException here keeps a failure a
    failure.
    """
    try:
        call()
    except BaseException as exc:
        assert type(exc) is expected, f"expected {expected.__name__}, got {type(exc).__name__}"
        return exc
    raise AssertionError(f"expected {expected.__name__}, nothing was raised")


@pytest.mark.parametrize("action_exc", ["ValueError", "KeyboardInterrupt"])
@pytest.mark.parametrize("log_exc", [OSError, KeyboardInterrupt, SystemExit])
def test_the_actions_exception_always_outranks_the_terminal_write(action_exc, log_exc):
    """One rule, no special case: if the action is already failing, it wins.

    The table is the point. There is no class of log failure that gets to
    replace the action's own exception, and no class of action exception that
    forfeits its place, so neither axis needs to be reasoned about at a call
    site.
    """
    class _FailingTerminal:
        def record(self, rule, ctx, note=None, outcome=None,
                   phase="start", attempt=None, status=None):
            if phase == "end":
                raise log_exc("terminal write failed")
            return RecordId("i", 1, 1, 1)

    expected = getattr(_builtins, action_exc)
    exc = raises_exactly(
        expected,
        lambda: run_action(
            rule("r", {"kind": "raise", "exc": action_exc, "message": "boom"}),
            {}, log=_FailingTerminal()))
    notes = "\n".join(getattr(exc, "__notes__", []))
    assert log_exc.__name__ in notes and "terminal write failed" in notes


@pytest.mark.parametrize("log_exc", [OSError, KeyboardInterrupt, SystemExit])
def test_without_an_action_error_the_terminal_failure_propagates_untranslated(log_exc):
    # Nothing is competing with it here, so it must arrive as itself rather
    # than wrapped: an interruption stays an interruption.
    class _FailingTerminal:
        def record(self, rule, ctx, note=None, outcome=None,
                   phase="start", attempt=None, status=None):
            if phase == "end":
                raise log_exc("terminal write failed")
            return RecordId("i", 1, 1, 1)

    ctx = {}
    raises_exactly(
        log_exc,
        lambda: run_action(rule("o", {"kind": "return_value", "value": "S"}),
                           ctx, log=_FailingTerminal()))
    assert ctx["_override"] == "S", "the action ran; what failed is the logging"


# --- a hostile __str__ must not change what propagates ----------------------

class _Hostile(Exception):
    """An exception whose rendering fails, as a workload's own class may."""

    def __str__(self):
        raise RuntimeError("hostile __str__")


def _raising_sleep(_seconds):
    raise _Hostile()


def test_a_hostile_str_does_not_replace_the_exception_when_there_is_no_log(monkeypatch):
    # With log=None there is no diagnostic to build at all. Building one
    # anyway ran the workload's __str__ and propagated ITS failure instead of
    # the original, which is the tool corrupting the very thing it measures.
    monkeypatch.setattr(time, "sleep", _raising_sleep)
    with pytest.raises(_Hostile):
        run_action(rule("s", {"kind": "sleep", "ms": 1}), {}, log=None)


def test_a_hostile_str_does_not_replace_the_exception_with_a_real_log(tmp_path, monkeypatch):
    monkeypatch.setattr(time, "sleep", _raising_sleep)
    p = tmp_path / "f.jsonl"
    log = FiringLog(str(p))
    with pytest.raises(_Hostile):
        run_action(rule("s", {"kind": "sleep", "ms": 1}), {}, log=log)
    log.close()

    end = ends(records(p))[0]
    assert end["status"] == "failed"
    # The record still lands, saying plainly that the detail could not be
    # rendered rather than inventing one or dropping the record.
    assert "diagnostic unavailable" in end["outcome"]


def test_a_pragma_whose_error_will_not_render_stays_non_propagating(tmp_path):
    # A failed pragma is reported, never raised. A diagnostic built eagerly
    # made that promise conditional on the error being printable.
    class _HostileConnection:
        def execute(self, _sql):
            raise _Hostile()

    p = tmp_path / "f.jsonl"
    log = FiringLog(str(p))
    run_action(rule("p", {"kind": "pragma", "name": "synchronous", "value": "OFF",
                          "target": "self"}),
               {"args": (_HostileConnection(),), "kwargs": {}}, log=log)  # must not raise
    log.close()

    end = ends(records(p))[0]
    assert end["status"] == "pragma_failed"
    assert "diagnostic unavailable" in end["outcome"]


# --- reentrancy -------------------------------------------------------------

def test_a_reentrant_run_action_during_the_start_record_cannot_steal_the_outcome():
    # A rule can fire on something the logger touches, so run_action can be
    # re-entered while an outer attempt is mid-flight. The outer attempt's
    # own effect and its own attempt id must both survive that.
    seen = []

    class _ReenteringLog:
        def __init__(self):
            self.seq = 0
            self.inner_done = False

        def record(self, rule, ctx, note=None, outcome=None,
                   phase="start", attempt=None, status=None):
            self.seq += 1
            mine = self.seq
            seen.append((rule.id, phase, attempt if phase == "end" else mine))
            if phase == "start" and not self.inner_done:
                self.inner_done = True
                run_action(rule_inner, ctx, log=self)
            return RecordId("i", 1, mine, mine if phase == "start" else attempt)

    rule_inner = rule("inner", {"kind": "return_none"})
    log = _ReenteringLog()
    ctx = {}
    run_action(rule("outer", {"kind": "return_value", "value": "OUTER"}), ctx, log=log)

    assert ctx["_override"] == "OUTER", \
        "the outer action ran after the reentrant one and its effect must stand"
    outer_start = next(s for s in seen if s[:2] == ("outer", "start"))
    outer_end = next(s for s in seen if s[:2] == ("outer", "end"))
    assert outer_end[2] == outer_start[2], \
        "the outer terminal must point at the outer attempt, not the inner one"
    inner_start = next(s for s in seen if s[:2] == ("inner", "start"))
    assert inner_start[2] != outer_start[2]


def test_a_target_whose_resolution_raises_is_a_failure_not_a_skip(tmp_path):
    # A resolver that raises is a BUG, not a known miss, so it takes the
    # generic failure path and the original exception propagates unchanged.
    # `pragma_skipped` is reserved for a miss the resolver REPORTS, and
    # widening it to cover this would hide a defect behind a status that
    # means "there was nothing to act on".
    class _HostileMeta(type):
        @property
        def __name__(cls):
            raise RuntimeError("hostile type name")

    class _Hostile(metaclass=_HostileMeta):
        pass

    p = tmp_path / "f.jsonl"
    log = FiringLog(str(p))
    exc = raises_exactly(
        RuntimeError,
        lambda: run_action(
            rule("p", {"kind": "pragma", "name": "synchronous", "value": "OFF",
                       "target": "self.missing"}),
            {"args": (_Hostile(),), "kwargs": {}}, log=log))
    assert "hostile type name" in str(exc), "the original exception, not a translation"
    log.close()

    end = ends(records(p))[0]
    assert end["status"] == "failed"
    assert end["outcome"] == "RuntimeError: hostile type name"
