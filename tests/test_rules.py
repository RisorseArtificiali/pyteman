import builtins
import re
import threading
import time

import pytest
from pyteman.rules import (_MAX_SLEEP_MS, _UNCONSTRUCTIBLE_EXC, Rule,
                           RuleError, load_rules, parse_point)

def write(tmp_path, text):
    p = tmp_path / "rules.yaml"; p.write_text(text); return str(p)

def test_parse_point_splits_at_last_dot():
    assert parse_point("os.path.join") == ("os.path", "join")
    assert parse_point("mod.fn") == ("mod", "fn")

def test_load_valid_rules(tmp_path):
    p = write(tmp_path, """
- id: hold-commit
  point: hermes_state.SessionDB._execute_write
  event: entry
  when: "fires > 3"
  action: {kind: sleep, ms: 250}
  fire: {mode: once_per, key: "kwargs.get('sid')"}
- id: kill5
  point: hermes_state.SessionDB.commit
  event: exit
  action: {kind: kill, exit_code: 70}
  fire: {mode: countdown, n: 5}
""")
    rules = load_rules(p)
    assert rules[0].module == "hermes_state"
    assert rules[0].symbol == "SessionDB._execute_write"
    assert rules[0].event == "entry"
    assert rules[0].action == {"kind": "sleep", "ms": 250}
    assert rules[1].fire == {"mode": "countdown", "n": 5}

def test_load_rejects_null_fire(tmp_path):
    p = write(tmp_path, "- id: x\n  point: mod.fn\n  event: entry\n  action: {kind: sleep, ms: 1}\n  fire:\n")
    with pytest.raises(RuleError, match="fire"):
        load_rules(p)

def test_default_fire_is_always(tmp_path):
    p = write(tmp_path, "- id: x\n  point: mod.fn\n  event: entry\n  action: {kind: sleep, ms: 1}\n")
    r = load_rules(p)[0]
    assert r.fire == {"mode": "always"}
    assert r.when is None


# --- load-time validation table -------------------------------------------
#
# A rule that only fails at firing has already let the workload start, so the
# experiment produced data under conditions the operator never authored. Every
# malformed rule must therefore die in load_rules, naming the offending field.
# The table covers null/list/bool where a string or an int is expected: YAML
# spells all three without quotes, and Python's bool-is-an-int makes
# `ms: true` read as `ms: 1` unless it is rejected on purpose.

VALID = [
    ("minimal sleep", "{id: a, point: m.f, event: entry, action: {kind: sleep, ms: 0}}"),
    ("dotted symbol", "{id: a, point: hermes_state.SessionDB.commit, event: exit,"
                      " action: {kind: sleep, ms: 250}}"),
    ("return_value", "{id: a, point: m.f, event: entry,"
                     " action: {kind: return_value, value: 42}}"),
    ("return_value null", "{id: a, point: m.f, event: entry,"
                          " action: {kind: return_value, value: ~}}"),
    ("return_none", "{id: a, point: m.f, event: exit, action: {kind: return_none}}"),
    ("raise default exc", "{id: a, point: m.f, event: entry, action: {kind: raise}}"),
    ("raise named exc", "{id: a, point: m.f, event: entry,"
                        " action: {kind: raise, exc: ValueError, message: boom}}"),
    ("kill low code", "{id: a, point: m.f, event: exit, action: {kind: kill, exit_code: 0}}"),
    ("kill high code", "{id: a, point: m.f, event: exit, action: {kind: kill, exit_code: 255}}"),
    ("pragma", "{id: a, point: m.f, event: entry,"
               " action: {kind: pragma, name: synchronous, value: 'OFF'}}"),
    ("pragma int value", "{id: a, point: m.f, event: entry,"
                         " action: {kind: pragma, name: synchronous, value: 0}}"),
    ("pragma self target", "{id: a, point: m.f, event: entry,"
                           " action: {kind: pragma, name: synchronous, value: 'OFF',"
                           " target: self._conn}}"),
    ("pragma result target on exit", "{id: a, point: m.f, event: exit,"
                                     " action: {kind: pragma, name: synchronous, value: 'OFF',"
                                     " target: result}}"),
    ("barrier open", "{id: a, point: m.f, event: entry,"
                     " action: {kind: barrier, barrier: b, role: open}}"),
    ("barrier wait", "{id: a, point: m.f, event: entry,"
                     " action: {kind: barrier, barrier: b, role: wait, timeout_s: 0.5}}"),
    ("fire always", "{id: a, point: m.f, event: entry, action: {kind: sleep, ms: 1},"
                    " fire: {mode: always}}"),
    ("fire once_per", "{id: a, point: m.f, event: entry, action: {kind: sleep, ms: 1},"
                      " fire: {mode: once_per, key: \"kwargs.get('sid')\"}}"),
    ("fire countdown zero", "{id: a, point: m.f, event: entry, action: {kind: sleep, ms: 1},"
                            " fire: {mode: countdown, n: 0}}"),
    ("when expression", "{id: a, point: m.f, event: entry, when: 'fires <= 3',"
                        " action: {kind: sleep, ms: 1}}"),
    # result/exc are bound only on the exit branch, and this row is an exit
    # rule, so it is valid on both counts. It stays as a guard: a future name
    # check broad enough to reject the correct spelling turns this row red.
    ("when reads result on exit", "{id: a, point: m.f, event: exit, when: 'result is None',"
                                  " action: {kind: sleep, ms: 1}}"),
    # loads only; nothing here ever sleeps.
    ("sleep at the conversion ceiling", "{id: a, point: m.f, event: entry,"
                                        " action: {kind: sleep, ms: "
                                        + str(_MAX_SLEEP_MS) + "}}"),
]

INVALID = [
    # id: it keys every record a rule writes to the firing log, so it must be
    # a non-empty unique string. The string check runs before the uniqueness
    # one, so a list id is refused for its type rather than for being
    # unhashable in `seen_ids`.
    ("id null", "{id: ~, point: m.f, event: entry, action: {kind: sleep, ms: 1}}", "id must be a string"),
    ("id list", "{id: [1, 2], point: m.f, event: entry, action: {kind: sleep, ms: 1}}", "id must be a string"),
    ("id int", "{id: 5, point: m.f, event: entry, action: {kind: sleep, ms: 1}}", "id must be a string"),
    ("id bool", "{id: true, point: m.f, event: entry, action: {kind: sleep, ms: 1}}", "id must be a string"),
    ("id empty", "{id: '', point: m.f, event: entry, action: {kind: sleep, ms: 1}}", "non-empty"),
    # point: every dot component is walked as an attribute name.
    ("point leading dot", "{id: a, point: .f, event: entry, action: {kind: sleep, ms: 1}}", "point"),
    ("point trailing dot", "{id: a, point: 'm.', event: entry, action: {kind: sleep, ms: 1}}", "point"),
    ("point empty component", "{id: a, point: m..f, event: entry, action: {kind: sleep, ms: 1}}", "point"),
    ("point no dot", "{id: a, point: nodot, event: entry, action: {kind: sleep, ms: 1}}", "point"),
    ("point int", "{id: a, point: 123, event: entry, action: {kind: sleep, ms: 1}}", "point must be a string"),
    ("point null", "{id: a, point: ~, event: entry, action: {kind: sleep, ms: 1}}", "point must be a string"),
    ("event unknown", "{id: a, point: m.f, event: middle, action: {kind: sleep, ms: 1}}", "event"),
    # when: a falsy-but-present value must never be read as "no condition".
    ("when bool false", "{id: a, point: m.f, event: entry, when: false, action: {kind: sleep, ms: 1}}",
     "when must be a string"),
    ("when bool true", "{id: a, point: m.f, event: entry, when: true, action: {kind: sleep, ms: 1}}",
     "when must be a string"),
    ("when list", "{id: a, point: m.f, event: entry, when: [], action: {kind: sleep, ms: 1}}",
     "when must be a string"),
    ("when null", "{id: a, point: m.f, event: entry, when: ~, action: {kind: sleep, ms: 1}}",
     "when must be a string"),
    ("when empty", "{id: a, point: m.f, event: entry, when: '', action: {kind: sleep, ms: 1}}", "non-empty"),
    ("when syntax error", "{id: a, point: m.f, event: entry, when: 'x ==', action: {kind: sleep, ms: 1}}",
     "not a valid expression"),
    ("when statement", "{id: a, point: m.f, event: entry, when: 'x = 1', action: {kind: sleep, ms: 1}}",
     "not a valid expression"),
    # action shape and per-kind fields.
    ("action not mapping", "{id: a, point: m.f, event: entry, action: hello}", "action must be a mapping"),
    ("action null", "{id: a, point: m.f, event: entry, action: ~}", "action must be a mapping"),
    ("action kind unknown", "{id: a, point: m.f, event: entry, action: {kind: nap, ms: 1}}", "action.kind"),
    ("action kind missing", "{id: a, point: m.f, event: entry, action: {ms: 1}}", "action.kind"),
    ("sleep without ms", "{id: a, point: m.f, event: entry, action: {kind: sleep}}",
     "sleep action needs 'ms'"),
    ("sleep ms negative", "{id: a, point: m.f, event: entry, action: {kind: sleep, ms: -1}}", "non-negative"),
    ("sleep ms bool", "{id: a, point: m.f, event: entry, action: {kind: sleep, ms: true}}", "integer"),
    ("sleep ms float", "{id: a, point: m.f, event: entry, action: {kind: sleep, ms: 1.5}}", "integer"),
    ("sleep ms infinite", "{id: a, point: m.f, event: entry, action: {kind: sleep, ms: .inf}}", "integer"),
    ("sleep ms string", "{id: a, point: m.f, event: entry, action: {kind: sleep, ms: fast}}", "integer"),
    # Two rows, not a duplicate: the unconvertible int and the merely-too-large
    # one reach OverflowError by different routes inside the firing call. See
    # _millis for both. One int comparison turns them away at the load instead.
    ("sleep ms unconvertible int", "{id: a, point: m.f, event: entry,"
                                   " action: {kind: sleep, ms: 1" + "0" * 400 + "}}",
     "must be at most " + str(_MAX_SLEEP_MS)),
    ("sleep ms past the ceiling", "{id: a, point: m.f, event: entry,"
                                  " action: {kind: sleep, ms: "
                                  + str(_MAX_SLEEP_MS + 1) + "}}",
     "must be at most " + str(_MAX_SLEEP_MS)),
    ("sleep typo'd field", "{id: a, point: m.f, event: entry, action: {kind: sleep, ms: 1, mss: 250}}",
     "unknown action field"),
    ("raise unknown exc", "{id: a, point: m.f, event: entry, action: {kind: raise, exc: Nope}}",
     "builtin exception"),
    ("raise non-exception exc", "{id: a, point: m.f, event: entry, action: {kind: raise, exc: len}}",
     "builtin exception"),
    ("raise exc int", "{id: a, point: m.f, event: entry, action: {kind: raise, exc: 5}}",
     "exc must be a string"),
    ("kill exit_code string", "{id: a, point: m.f, event: exit, action: {kind: kill, exit_code: abc}}",
     "integer"),
    ("kill exit_code negative", "{id: a, point: m.f, event: exit, action: {kind: kill, exit_code: -1}}",
     "non-negative"),
    ("kill exit_code too large", "{id: a, point: m.f, event: exit, action: {kind: kill, exit_code: 256}}",
     "255"),
    ("pragma without name", "{id: a, point: m.f, event: entry, action: {kind: pragma, value: 'OFF'}}",
     "pragma action needs 'name'"),
    ("pragma without value", "{id: a, point: m.f, event: entry, action: {kind: pragma, name: synchronous}}",
     "pragma action needs 'value'"),
    ("pragma value null", "{id: a, point: m.f, event: entry,"
                          " action: {kind: pragma, name: synchronous, value: ~}}", "value must be"),
    ("pragma value list", "{id: a, point: m.f, event: entry,"
                          " action: {kind: pragma, name: synchronous, value: [1]}}", "value must be"),
    # The rejection is one uniform rule, but the harm it names is not uniform.
    # journal_mode takes only its own keywords, so "PRAGMA journal_mode=False"
    # is a statement SQLite accepts while leaving the mode untouched. On the
    # boolean-valued pragmas below, that same coerced text is recognised and
    # does apply, so what the quotes buy there is an unambiguous source rather
    # than a different outcome. tests/test_actions.py measures both halves.
    ("pragma value unquoted OFF", "{id: a, point: m.f, event: entry,"
                                  " action: {kind: pragma, name: journal_mode, value: OFF}}",
     "must be quoted"),
    ("pragma value unquoted ON", "{id: a, point: m.f, event: entry,"
                                 " action: {kind: pragma, name: foreign_keys, value: ON}}",
     "must be quoted"),
    ("target on non-pragma", "{id: a, point: m.f, event: entry,"
                             " action: {kind: sleep, ms: 1, target: self}}", "only consumed by pragma"),
    # `timeout_s` is read only by the wait branch, exactly as `target` above is
    # read only by pragma. Both values below are refused, the wait default
    # included, because what is wrong is the field being there at all rather
    # than the number written in it.
    ("timeout on barrier open", "{id: a, point: m.f, event: entry,"
                                " action: {kind: barrier, barrier: b, role: open, timeout_s: 5}}",
     "only consumed by barrier waits"),
    ("timeout on barrier open at the wait default", "{id: a, point: m.f, event: entry,"
                                                    " action: {kind: barrier, barrier: b,"
                                                    " role: open, timeout_s: 30}}",
     "only consumed by barrier waits"),
    ("target result on entry", "{id: a, point: m.f, event: entry,"
                               " action: {kind: pragma, name: s, value: 'OFF', target: result}}",
     "exit events"),
    ("target empty step", "{id: a, point: m.f, event: entry,"
                          " action: {kind: pragma, name: s, value: 'OFF', target: 'self..a'}}", "empty step"),
    ("target trailing dot", "{id: a, point: m.f, event: entry,"
                            " action: {kind: pragma, name: s, value: 'OFF', target: 'self.'}}", "empty step"),
    ("target param trailing dot", "{id: a, point: m.f, event: entry,"
                                  " action: {kind: pragma, name: s, value: 'OFF', target: 'param:db.'}}",
     "empty step"),
    # _target calls _text before validate_target_spec, and this row is the only
    # thing pinning what that buys: the field-qualified "action.target" wording
    # instead of the parser's bare "target must be a non-empty string".
    ("target not a string", "{id: a, point: m.f, event: entry,"
                            " action: {kind: pragma, name: s, value: 'OFF', target: 5}}",
     "action.target must be a string"),
    # 'result' resolves to the return value itself and no walk runs on it, so
    # the rejection has to say that rather than blame the root.
    ("target result with a walk", "{id: a, point: m.f, event: exit,"
                                  " action: {kind: pragma, name: s, value: 'OFF', target: 'result._conn'}}",
     "takes no attribute walk"),
    ("barrier without name", "{id: a, point: m.f, event: entry, action: {kind: barrier, role: open}}",
     "barrier action needs 'barrier'"),
    ("barrier role typo", "{id: a, point: m.f, event: entry,"
                          " action: {kind: barrier, barrier: b, role: opne}}", "role"),
    ("barrier timeout zero", "{id: a, point: m.f, event: entry,"
                             " action: {kind: barrier, barrier: b, timeout_s: 0}}", "positive"),
    ("barrier timeout negative", "{id: a, point: m.f, event: entry,"
                                 " action: {kind: barrier, barrier: b, timeout_s: -1}}", "positive"),
    ("barrier timeout infinite", "{id: a, point: m.f, event: entry,"
                                 " action: {kind: barrier, barrier: b, timeout_s: .inf}}", "finite"),
    ("barrier timeout string", "{id: a, point: m.f, event: entry,"
                               " action: {kind: barrier, barrier: b, timeout_s: soon}}", "number"),
    # Two ways a too-large value escapes as OverflowError instead of failing a
    # comparison: float() cannot convert the int at all, and Event.wait rejects
    # anything past TIMEOUT_MAX once the workload is already running. Each row
    # asserts on a fragment unique to its branch, so neither can drift into the
    # other's and still pass.
    ("barrier timeout unconvertible int", "{id: a, point: m.f, event: entry,"
                                          " action: {kind: barrier, barrier: b,"
                                          " timeout_s: 1" + "0" * 400 + "}}",
     "too large to convert to a float"),
    ("barrier timeout past TIMEOUT_MAX", "{id: a, point: m.f, event: entry,"
                                         " action: {kind: barrier, barrier: b,"
                                         " timeout_s: 1.0e+19}}", "got 1e+19"),
    # fire gating.
    ("fire not mapping", "{id: a, point: m.f, event: entry, action: {kind: sleep, ms: 1}, fire: hello}",
     "fire must be a mapping"),
    ("fire mode unknown", "{id: a, point: m.f, event: entry, action: {kind: sleep, ms: 1},"
                          " fire: {mode: sometimes}}", "fire.mode"),
    ("once_per without key", "{id: a, point: m.f, event: entry, action: {kind: sleep, ms: 1},"
                             " fire: {mode: once_per}}", "once_per fire needs 'key'"),
    ("once_per key int", "{id: a, point: m.f, event: entry, action: {kind: sleep, ms: 1},"
                         " fire: {mode: once_per, key: 5}}", "key must be a string"),
    ("once_per key syntax error", "{id: a, point: m.f, event: entry, action: {kind: sleep, ms: 1},"
                                  " fire: {mode: once_per, key: 'a ,, b'}}", "not a valid expression"),
    ("countdown without n", "{id: a, point: m.f, event: entry, action: {kind: sleep, ms: 1},"
                            " fire: {mode: countdown}}", "countdown fire needs 'n'"),
    ("countdown n negative", "{id: a, point: m.f, event: entry, action: {kind: sleep, ms: 1},"
                             " fire: {mode: countdown, n: -1}}", "non-negative"),
    ("countdown n string", "{id: a, point: m.f, event: entry, action: {kind: sleep, ms: 1},"
                           " fire: {mode: countdown, n: abc}}", "integer"),
    ("countdown n bool", "{id: a, point: m.f, event: entry, action: {kind: sleep, ms: 1},"
                         " fire: {mode: countdown, n: true}}", "integer"),
    ("fire typo'd field", "{id: a, point: m.f, event: entry, action: {kind: sleep, ms: 1},"
                          " fire: {mode: always, n: 3}}", "unknown fire field"),
    # a misspelled top-level key silently disables the field it meant to set.
    ("rule typo'd field", "{id: a, point: m.f, event: entry, action: {kind: sleep, ms: 1}, wehn: 'x'}",
     "unknown"),
    ("rule mixed-type typos", "{id: a, point: m.f, event: entry, action: {kind: sleep, ms: 1},"
                              " wehn: 'x', 3: y}", "unknown"),
    # the discriminators are looked up in a dict, so an unhashable value must
    # be turned away by type before it is ever hashed.
    ("action kind list", "{id: a, point: m.f, event: entry, action: {kind: [sleep], ms: 1}}",
     "action.kind"),
    ("fire mode mapping", "{id: a, point: m.f, event: entry, action: {kind: sleep, ms: 1},"
                          " fire: {mode: {always: true}}}", "fire.mode"),
    # required keys are reported against the id, which is read first.
    ("rule missing point", "{id: a, event: entry, action: {kind: sleep, ms: 1}}", "missing point"),
    ("rule missing event", "{id: a, point: m.f, action: {kind: sleep, ms: 1}}", "missing event"),
    ("rule missing action", "{id: a, point: m.f, event: entry}", "missing action"),
    # actions.py calls exc(message); the _UNCONSTRUCTIBLE_EXC classes reject it,
    # so the rule would raise TypeError instead of the exception it asked for.
    ("raise exc needing more than a message", "{id: a, point: m.f, event: entry,"
                                              " action: {kind: raise, exc: UnicodeDecodeError}}",
     "cannot be built from a message alone"),
]


@pytest.mark.parametrize("body", [c[1] for c in VALID], ids=[c[0] for c in VALID])
def test_valid_rules_load(tmp_path, body):
    load_rules(write(tmp_path, "- " + body + "\n"))


@pytest.mark.parametrize("body,expected", [c[1:] for c in INVALID], ids=[c[0] for c in INVALID])
def test_invalid_rules_rejected_at_load(tmp_path, body, expected):
    with pytest.raises(RuleError, match=re.escape(expected)):
        load_rules(write(tmp_path, "- " + body + "\n"))


@pytest.mark.parametrize("name,body", [c[:2] for c in INVALID], ids=[c[0] for c in INVALID])
def test_rejection_names_the_rule(tmp_path, name, body):
    """Every message locates the rule by index, and by id once it is known."""
    # Offset the bad rule so an index of 0 cannot pass by accident.
    good = "- {id: first, point: m.f, event: entry, action: {kind: sleep, ms: 1}}\n"
    with pytest.raises(RuleError) as excinfo:
        load_rules(write(tmp_path, good + "- " + body + "\n"))
    message = str(excinfo.value)
    assert "rule #1" in message
    # Keyed off the case name, not off the message under test: the id rows are
    # exactly the ones whose id never becomes known, and matching on the text
    # would let a message opt itself out of the check.
    if not name.startswith("id "):
        assert "id 'a'" in message


def test_the_misplaced_timeout_is_diagnosed_before_its_own_value(tmp_path):
    """Which of two true complaints the operator is shown, and why.

    A `timeout_s` on `role: open` can be wrong twice over: the field does not
    belong on that branch AT ALL, and the number written in it may itself be
    out of range. Reporting the range is a dead end here, because no value
    would have made the rule valid; reporting the placement ends the hunt in
    one step. So placement wins, which is only observable when both are wrong
    at once.

    The second case pins the other side of the order. `role` has not been
    validated when the placement check runs, so a misspelled role is not
    `open`, the placement check does not fire, and the role message is what
    survives. That is the right answer for a different reason: with the role
    unreadable, nothing yet knows whether the timeout is misplaced.
    """
    both_wrong = ("- {id: a, point: m.f, event: entry, action: {kind: barrier,"
                  " barrier: b, role: open, timeout_s: -1}}\n")
    with pytest.raises(RuleError) as excinfo:
        load_rules(write(tmp_path, both_wrong))
    assert "only consumed by barrier waits" in str(excinfo.value)

    bad_role = ("- {id: a, point: m.f, event: entry, action: {kind: barrier,"
                " barrier: b, role: opne, timeout_s: 5}}\n")
    with pytest.raises(RuleError) as excinfo:
        load_rules(write(tmp_path, bad_role))
    assert "only consumed by barrier waits" not in str(excinfo.value)


def test_unconstructible_exceptions_match_reality():
    """The denylist is derived from the interpreter, never guessed.

    actions.py raises `exc(message)`. Every builtin exception class either
    accepts that single argument or is listed, and a future Python that adds
    or fixes one fails here rather than at some operator's firing time.
    """
    for name in dir(builtins):
        cls = getattr(builtins, name)
        if not (isinstance(cls, type) and issubclass(cls, BaseException)):
            continue
        try:
            cls("pyteman injected")
        except TypeError:
            assert name in _UNCONSTRUCTIBLE_EXC, f"{name} rejects a message but is not listed"
        else:
            assert name not in _UNCONSTRUCTIBLE_EXC, f"{name} accepts a message but is listed"


def test_timeout_at_the_platform_ceiling_is_accepted(tmp_path):
    """The bound is exactly what threading honours, not a rounder guess.

    TIMEOUT_MAX itself must load and must be accepted as a timeout; past it is
    the "past TIMEOUT_MAX" row above.
    """
    body = ("- {id: a, point: m.f, event: entry, action: {kind: barrier,"
            " barrier: b, role: wait, timeout_s: " + repr(threading.TIMEOUT_MAX) + "}}\n")
    rule = load_rules(write(tmp_path, body))[0]
    assert rule.action["timeout_s"] == threading.TIMEOUT_MAX
    # Lock.acquire converts the timeout the same way Event.wait does, but does
    # it while parsing arguments, so an uncontended lock returns at once and
    # still proves the value is representable. A set Event would not: it
    # returns on the flag without ever looking at the timeout, and an unset one
    # at TIMEOUT_MAX would be a real wait.
    assert threading.Lock().acquire(True, rule.action["timeout_s"]) is True


def test_rejected_sleep_durations_really_break_the_action():
    """The ms bound is the platform's, not a number picked to look round.

    Bracketed from both sides, and neither side ever waits. Below the bound,
    a timed lock acquire converts the value and returns at once because the
    lock is free. That proves the number converts, and only that: time.sleep
    counts against an absolute monotonic deadline and fails with OSError
    anywhere near the ceiling, while the lock validates against TIMEOUT_MAX
    and never builds a deadline at all. Above the bound, both rejected shapes
    raise OverflowError out of the very expression actions.py evaluates,
    which without the bound happens inside the instrumented call.

    The first assertion is the one that would catch a bound raised too far:
    probing only far above the ceiling passes for any constant, however
    wrong, and a constant merely too large fails by sleeping rather than by
    going red.
    """
    # PyTime_t is int64 nanoseconds, so this is time.sleep's true ceiling in ms.
    ns_ceiling_ms = (2 ** 63 - 1) / 1_000_000
    assert _MAX_SLEEP_MS <= ns_ceiling_ms
    assert threading.Lock().acquire(True, _MAX_SLEEP_MS / 1000.0) is True
    with pytest.raises(OverflowError):
        _ = 10 ** 400 / 1000.0
    with pytest.raises(OverflowError):
        time.sleep(2.0 ** 63)


def test_duplicate_ids_rejected(tmp_path):
    p = write(tmp_path, "- {id: a, point: m.f, event: entry, action: {kind: sleep, ms: 1}}\n"
                        "- {id: a, point: m.g, event: entry, action: {kind: sleep, ms: 1}}\n")
    with pytest.raises(RuleError, match="already used"):
        load_rules(p)


# -- Rule.__post_init__ expression validation (TASK-80) -----------------------


def _rule(**overrides):
    defaults = dict(id="r", module="m", symbol="f", event="entry",
                    action={"kind": "sleep", "ms": 1})
    defaults.update(overrides)
    return Rule(**defaults)


def test_post_init_rejects_uncompilable_when():
    with pytest.raises(RuleError, match="is not a valid expression"):
        _rule(when="(")


def test_post_init_rejects_non_string_when():
    with pytest.raises(RuleError, match="when must be a string"):
        _rule(when=42)


def test_post_init_accepts_valid_when():
    r = _rule(when="fires <= 3")
    assert r.when == "fires <= 3"


def test_post_init_accepts_none_when():
    r = _rule(when=None)
    assert r.when is None


def test_post_init_rejects_uncompilable_fire_key():
    with pytest.raises(RuleError, match="is not a valid expression"):
        _rule(fire={"mode": "once_per", "key": "a ,, b"})


def test_post_init_rejects_non_string_fire_key():
    with pytest.raises(RuleError, match="fire.key must be a string"):
        _rule(fire={"mode": "once_per", "key": 42})


def test_post_init_accepts_valid_fire_key():
    r = _rule(fire={"mode": "once_per", "key": "result"})
    assert r.fire["key"] == "result"


def test_post_init_error_names_the_rule():
    with pytest.raises(RuleError, match="rule 'myrule'"):
        _rule(id="myrule", when="(")


def test_post_init_and_load_rules_share_core_wording(tmp_path):
    """AC #2: both doors produce the same diagnostic for the same defect."""
    with pytest.raises(RuleError) as direct:
        _rule(id="r1", when="x ==")
    p = write(tmp_path,
              "- {id: r1, point: m.f, event: entry, when: 'x ==', "
              "action: {kind: sleep, ms: 1}}\n")
    with pytest.raises(RuleError) as loaded:
        load_rules(p)
    core = "is not a valid expression"
    assert core in str(direct.value)
    assert core in str(loaded.value)
