# tests/test_example_log_consumers.py
"""The example drivers read the firing log; they must read it correctly.

Each driver decides whether the scenario is on track by counting firings.
Under the LOG-02 schema every firing writes two records, so a driver that
still counts lines, or that counts "a record with no outcome", sees twice
the firings it should and rides windows that were never opened. These tests
feed the real parser functions a synthetic log with both phases in it.

The examples are scripts, not an installed package, so each parser is loaded
from its path; `restarter.py` imports the vendored hermes module at import
time and gets a stub, since none of that is under test here.
"""
import importlib.util
import json
import sys
import time
import types
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def drivers():
    # `restarter.py` imports hermes_state at module scope, so the stub has to
    # exist for the duration of the import and then be taken back out again.
    # Leaving it in sys.modules would silently satisfy that import for every
    # later test in the session, including ones meant to fail without it.
    # `monkeypatch` itself is function-scoped; `MonkeyPatch.context()` gives
    # the same undo bookkeeping at the scope this fixture actually needs,
    # restoring a pre-existing `hermes_state` rather than deleting it.
    with pytest.MonkeyPatch.context() as mp:
        stub = types.ModuleType("hermes_state")
        stub.SessionDB = object  # imported at module scope, never called here
        mp.setitem(sys.modules, "hermes_state", stub)
        yield {
            "109966": load(EXAMPLES / "hermes-109966" / "run_repro.py", "ex109966_run"),
            "restarter": load(EXAMPLES / "hermes-109966" / "restarter.py", "ex109966_restart"),
            "111912": load(EXAMPLES / "hermes-111912" / "run_repro.py", "ex111912_run"),
        }


def write_log(path, records):
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    return str(path)


def attempt(rule, n, status="slept", phase_end=True, outcome=None):
    """One firing as the log really writes it: a start, then a terminal."""
    start = {"schema": 2, "instance": "i", "pid": 7, "seq": n, "attempt": n,
             "rule": rule, "point": "m.f", "phase": "start", "visit": None}
    if not phase_end:
        return [start]
    end = {"schema": 2, "instance": "i", "pid": 7, "seq": n + 100, "attempt": n,
           "rule": rule, "point": "m.f", "phase": "end", "status": status,
           "visit": None}
    if outcome is not None:
        end["outcome"] = outcome
    return [start, end]


# --- hermes-109966: the window counters ------------------------------------

@pytest.mark.parametrize("driver", ["109966", "restarter"])
def test_three_firings_count_as_three_windows(drivers, tmp_path, driver):
    # A "slept" terminal carries no outcome text, so the record has no
    # "outcome" key at all: the pre-LOG-02 predicate counted it as another
    # firing and reported six windows where three were opened.
    recs = [r for n in (1, 2, 3) for r in attempt("hold-write-window", n)]
    log = write_log(tmp_path / f"{driver}.jsonl", recs)
    assert drivers[driver]._fired_count(log) == 3


@pytest.mark.parametrize("driver", ["109966", "restarter"])
def test_other_rules_and_unreadable_lines_are_not_counted(drivers, tmp_path, driver):
    log = tmp_path / f"{driver}-mixed.jsonl"
    write_log(log, attempt("hold-write-window", 1) + attempt("some-other-rule", 2))
    with open(log, "a", encoding="utf-8") as fh:
        fh.write("{not json\n")  # a torn tail must not crash the driver
    assert drivers[driver]._fired_count(str(log)) == 1


@pytest.mark.parametrize("driver", ["109966", "restarter"])
def test_a_missing_log_is_zero_not_an_error(drivers, tmp_path, driver):
    assert drivers[driver]._fired_count(str(tmp_path / "absent.jsonl")) == 0


def test_a_firing_is_visible_before_its_action_finishes(drivers, tmp_path):
    # The restarter waits on this count to ride a window that is still open,
    # so the start record alone has to be enough; waiting for the terminal
    # would mean waiting for the very sleep it is supposed to race.
    log = write_log(tmp_path / "open.jsonl",
                    attempt("hold-write-window", 1, phase_end=False))
    assert drivers["restarter"]._fired_count(log) == 1


# --- hermes-111912: did the injection take effect --------------------------

@pytest.fixture
def ruleset(tmp_path):
    f = tmp_path / "rules.yaml"
    f.write_text("- id: slow-ui-tui-teardown\n  point: tui_child.graceful_shutdown\n"
                 "  event: entry\n  action: {kind: sleep, ms: 5000}\n")
    return str(f)


def test_a_completed_firing_counts_as_fired(drivers, tmp_path, ruleset):
    log = write_log(tmp_path / "f.jsonl", attempt("slow-ui-tui-teardown", 1))
    assert drivers["111912"]._rule_fired(log, ruleset) is True


def test_a_skipped_attempt_is_not_a_firing(drivers, tmp_path, ruleset):
    log = write_log(tmp_path / "s.jsonl",
                    attempt("slow-ui-tui-teardown", 1, status="pragma_skipped",
                            outcome="pragma skipped: no target spec"))
    assert drivers["111912"]._rule_fired(log, ruleset) is False


def test_a_failed_attempt_is_not_a_firing(drivers, tmp_path, ruleset):
    log = write_log(tmp_path / "x.jsonl",
                    attempt("slow-ui-tui-teardown", 1, status="failed",
                            outcome="RuntimeError: nope"))
    assert drivers["111912"]._rule_fired(log, ruleset) is False


@pytest.mark.parametrize("status", ["pragma_unknown", "pragma_mismatch"])
def test_a_pragma_that_was_not_verified_is_not_a_firing(drivers, tmp_path,
                                                        ruleset, status):
    """The over-report this driver was documented to be capable of.

    Its `refuting` set used to be written out by hand, so a status added to
    actions.py stayed absent from it and the attempt was counted as a firing:
    `pin_engaged` read True for a run whose pragma may never have applied.
    The set is imported now, and these are the two statuses CFG-04 added.
    """
    log = write_log(tmp_path / f"{status}.jsonl",
                    attempt("slow-ui-tui-teardown", 1, status=status,
                            outcome="PRAGMA foreign_keys=banana: ..."))
    assert drivers["111912"]._rule_fired(log, ruleset) is False


@pytest.mark.parametrize("status", ["pragma_applied", "pragma_already"])
def test_a_verified_pragma_is_still_a_firing(drivers, tmp_path, ruleset, status):
    # The other half: tightening that set must not start refuting the attempts
    # that did attest the setting.
    log = write_log(tmp_path / f"{status}.jsonl",
                    attempt("slow-ui-tui-teardown", 1, status=status))
    assert drivers["111912"]._rule_fired(log, ruleset) is True


def test_one_good_firing_survives_an_earlier_skip(drivers, tmp_path, ruleset):
    # The terminal that refutes attempt 1 must not refute attempt 2; that is
    # the whole point of correlating on the attempt id rather than the rule.
    recs = (attempt("slow-ui-tui-teardown", 1, status="pragma_skipped",
                    outcome="pragma skipped: no target spec")
            + attempt("slow-ui-tui-teardown", 2))
    assert drivers["111912"]._rule_fired(write_log(tmp_path / "m.jsonl", recs),
                                         ruleset) is True


def test_an_unfinished_firing_still_counts(drivers, tmp_path, ruleset):
    # The child is killed mid-action in this scenario, so the terminal record
    # never lands. Nothing refutes the attempt, so it stands as a firing.
    log = write_log(tmp_path / "k.jsonl",
                    attempt("slow-ui-tui-teardown", 1, phase_end=False))
    assert drivers["111912"]._rule_fired(log, ruleset) is True


def test_a_terminal_alone_is_never_read_as_a_firing(drivers, tmp_path, ruleset):
    # A log rotated or truncated so that only the tail survives has terminals
    # with no starts. The driver must not invent a firing out of one.
    end = attempt("slow-ui-tui-teardown", 1)[1]
    assert drivers["111912"]._rule_fired(write_log(tmp_path / "t.jsonl", [end]),
                                         ruleset) is False


def test_a_different_ruleset_does_not_match(drivers, tmp_path, ruleset):
    log = write_log(tmp_path / "o.jsonl", attempt("wedged-ui-tui-teardown", 1))
    assert drivers["111912"]._rule_fired(log, ruleset) is False


def test_a_missing_log_is_not_a_firing(drivers, tmp_path, ruleset):
    assert drivers["111912"]._rule_fired(str(tmp_path / "absent.jsonl"), ruleset) is False


# ---------------------------------------------------------------------------
# TASK-26 / EX-01: the restarter's per-window handshake. A close is proven
# concurrent only against BOTH edges of its window in the firing log; a
# count total cannot say it, and a window that never opened or already
# closed refuses the cycle instead of performing an out-of-window close
# and presenting it as valid. These run the real restarter module against
# synthetic logs with the same stub hermes_state the fixture above builds.
# ---------------------------------------------------------------------------

class _CloseRecorder:
    """A hermes_state stub whose SessionDB records every close."""

    def __init__(self, db_path=None):
        pass

    def append_message(self, *args, **kwargs):
        pass

    def close(self):
        CLOSES.append(time.monotonic_ns())


@pytest.fixture()
def restarter_driver(monkeypatch):
    CLOSES.clear()
    monkeypatch.setitem(sys.modules, "hermes_state", types.ModuleType("hermes_state"))
    sys.modules["hermes_state"].SessionDB = _CloseRecorder
    # load() never registers the module in sys.modules, so there is
    # nothing to take back: the stub's lifetime is this fixture's.
    yield load(EXAMPLES / "hermes-109966" / "restarter.py",
               "restarter_handshake")


CLOSES = []


def _log_with(seq_pairs):
    """One window per pair: (start_ns, end_ns or None)."""
    lines = []
    seq = 0
    for start_ns, end_ns in seq_pairs:
        seq += 1
        lines.append(json.dumps(
            {"rule": "hold-write-window", "phase": "start", "seq": seq,
             "monotonic_ns": start_ns}))
        if end_ns is not None:
            seq += 1
            lines.append(json.dumps(
                {"rule": "hold-write-window", "phase": "end", "seq": seq,
                 "monotonic_ns": end_ns}))
    return "\n".join(lines) + "\n"


def test_a_dead_log_refuses_before_any_close(tmp_path, restarter_driver,
                                              capsys, monkeypatch):
    """AC: zero live firing, log already complete, sibling arrives late.

    The pre-fix restarter rode all three windows in a tenth of a second
    and exited zero; the handshake refuses at cycle one, before a single
    close, because window 1's end is already on disk.
    """
    log = tmp_path / "firing.jsonl"
    log.write_text(_log_with([(100, 400), (1100, 1400), (2100, 2400)]))
    monkeypatch.setattr(sys, "argv",
                        ["restarter", str(tmp_path / "db.sqlite"), "3",
                         str(log)])
    with pytest.raises(SystemExit) as excinfo:
        restarter_driver.main()
    assert excinfo.value.code == restarter_driver.EXIT_OUT_OF_WINDOW
    assert CLOSES == [], "refused before performing any close"
    assert "window 1 already closed" in capsys.readouterr().err


def test_a_window_that_never_opens_times_out_as_an_error(
        tmp_path, restarter_driver, monkeypatch):
    """AC: firing absent entirely: the wait budget expires, no close."""
    log = tmp_path / "firing.jsonl"
    log.write_text("")
    monkeypatch.setattr(sys, "argv",
                        ["restarter", str(tmp_path / "db.sqlite"), "1",
                         str(log)])
    # The wait budget is 30s; a test cannot pay it, so the clock leaps
    # past every deadline on the second read.
    ticks = iter([0.0, 1e12])
    monkeypatch.setattr(restarter_driver.time, "monotonic",
                        lambda: next(ticks, 1e12))
    with pytest.raises(SystemExit) as excinfo:
        restarter_driver.main()
    assert excinfo.value.code == restarter_driver.EXIT_WINDOW_TIMEOUT
    assert CLOSES == []


def test_a_live_window_closes_and_proves_it(tmp_path, restarter_driver,
                                             capsys, monkeypatch):
    """The healthy choreography: start on disk, end not, close, end later."""
    log = tmp_path / "firing.jsonl"
    log.write_text(_log_with([(100, None)]))

    # The end record lands just after the close, like a real release.
    real_windows = restarter_driver._windows

    def windows_after_close(firing_log):
        found = real_windows(firing_log)
        if CLOSES:
            # First read after the close sees the released window, with
            # the end comfortably after every sample the restarter takes:
            # its own close_ns read happens after the stub's, so a +1ns
            # margin would land between the two and read as a refusal.
            log.write_text(_log_with([(100, CLOSES[0] + 10**9)]))
            return real_windows(firing_log)
        return found

    monkeypatch.setattr(restarter_driver, "_windows", windows_after_close)
    monkeypatch.setattr(sys, "argv",
                        ["restarter", str(tmp_path / "db.sqlite"), "1",
                         str(log)])
    restarter_driver.main()
    assert len(CLOSES) == 1
    assert "close inside window" in capsys.readouterr().out


def test_a_close_after_the_end_refuses_even_mid_cycle(tmp_path,
                                                       restarter_driver,
                                                       capsys, monkeypatch):
    """The post-close proof: an end that beat the close is a refusal."""
    log = tmp_path / "firing.jsonl"
    log.write_text(_log_with([(100, None)]))
    real_windows = restarter_driver._windows

    def windows_early_end(firing_log):
        found = real_windows(firing_log)
        if CLOSES:
            # The release was on disk BEFORE the close finished.
            log.write_text(_log_with([(100, CLOSES[0] - 1)]))
            return real_windows(firing_log)
        return found

    monkeypatch.setattr(restarter_driver, "_windows", windows_early_end)
    monkeypatch.setattr(sys, "argv",
                        ["restarter", str(tmp_path / "db.sqlite"), "1",
                         str(log)])
    with pytest.raises(SystemExit) as excinfo:
        restarter_driver.main()
    assert excinfo.value.code == restarter_driver.EXIT_OUT_OF_WINDOW
    assert "closed after its window ended" in capsys.readouterr().err
