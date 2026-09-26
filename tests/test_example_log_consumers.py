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


# --- hermes-109966: end counts and window-open predicate ------------------

@pytest.mark.parametrize("driver", ["109966", "restarter"])
def test_end_count_matches_completed_windows(drivers, tmp_path, driver):
    recs = [r for n in (1, 2, 3) for r in attempt("hold-write-window", n)]
    log = write_log(tmp_path / f"{driver}-ends.jsonl", recs)
    assert drivers[driver]._end_count(log) == 3


@pytest.mark.parametrize("driver", ["109966", "restarter"])
def test_end_count_is_zero_for_open_windows(drivers, tmp_path, driver):
    recs = [r for n in (1, 2) for r in attempt("hold-write-window", n, phase_end=False)]
    log = write_log(tmp_path / f"{driver}-no-end.jsonl", recs)
    assert drivers[driver]._end_count(log) == 0


@pytest.mark.parametrize("driver", ["109966", "restarter"])
def test_end_count_is_zero_for_missing_log(drivers, tmp_path, driver):
    assert drivers[driver]._end_count(str(tmp_path / "absent.jsonl")) == 0


def test_end_count_excludes_other_rules(drivers, tmp_path):
    recs = attempt("hold-write-window", 1) + attempt("some-other-rule", 2)
    log = write_log(tmp_path / "mixed-ends.jsonl", recs)
    assert drivers["restarter"]._end_count(log) == 1


def test_open_window_is_visible_closed_window_is_not(drivers, tmp_path):
    """With one start and no end, _fired_count >= 1 and _end_count <= 0."""
    recs = attempt("hold-write-window", 1, phase_end=False)
    log = write_log(tmp_path / "open-window.jsonl", recs)
    mod = drivers["restarter"]
    starts = mod._fired_count(log)
    ends = mod._end_count(log)
    assert starts >= 1 and ends <= 0, "window 0 should appear open"


def test_closed_window_detected_by_end_count(drivers, tmp_path):
    """With one start and one end, window 0 is closed."""
    recs = attempt("hold-write-window", 1, phase_end=True)
    log = write_log(tmp_path / "closed-window.jsonl", recs)
    mod = drivers["restarter"]
    starts = mod._fired_count(log)
    ends = mod._end_count(log)
    assert starts >= 1 and ends >= 1, "window 0 should appear closed"


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
