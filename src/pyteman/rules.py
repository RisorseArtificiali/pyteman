"""Ruleset loading with full load-time validation.

A rule that only fails at firing has already let the instrumented workload
start, so the experiment produced data under conditions the operator never
authored. Everything checkable without the target module is therefore
checked here: types, ranges, required fields, and the compilability of
every expression.

Expression bodies are compiled here, but the NAMES they read are not
resolved: that check belongs to the evaluation namespace, which lives in
patcher.py and conditions.py, and a partial version of it is worse than
none. symtable reports no free `result` for `(lambda: result)()` nor for
`result or (result := 1)`, yet both NameError at firing, so a check built
on it rejects the plain spelling and waves those two through. Either the
namespace is validated completely or the contract stays documented.

Compatibility policy: the schema is closed. Unknown keys at the rule,
action or fire level are rejected rather than ignored, because the failure
they cause is silent (`mss: 250` next to `ms: 1` sleeps a millisecond,
`wehn:` is an ungated rule). Extending the language means extending the
tables below.
"""
import builtins
import math
import threading
from dataclasses import dataclass, field
from typing import NoReturn, Optional
import yaml

from pyteman.targets import parse_target_spec, validate_target_spec

class RuleError(Exception):
    pass

_EVENTS = ("entry", "exit")
_RULE_KEYS = frozenset({"id", "point", "event", "action", "fire", "when"})
_BARRIER_ROLES = ("open", "wait")

@dataclass
class Rule:
    id: str
    module: str
    symbol: str
    event: str
    action: dict
    fire: dict = field(default_factory=lambda: {"mode": "always"})
    when: Optional[str] = None

    def __post_init__(self):
        _validate_rule_expressions(self)

def parse_point(point: str) -> tuple[str, str]:
    """Split a point string at the LAST dot: "os.path.join" -> ("os.path", "join").

    Rule points deliberately resolve differently: load_rules splits at the
    FIRST dot so "pkg.Class.method" yields module "pkg" and symbol
    "Class.method", the attribute chain walked from the imported module.
    """
    if "." not in point:
        raise RuleError(f"point must be 'module.symbol' (got {point!r})")
    mod, _, sym = point.rpartition(".")
    return mod, sym


def _fail(where, detail) -> NoReturn:
    raise RuleError(f"{where}: {detail}")


def _typename(value):
    return type(value).__name__


def _text(where, name, value):
    """A non-empty string. None/list/bool are typos here, never coerced."""
    if not isinstance(value, str):
        _fail(where, f"{name} must be a string, got {_typename(value)}")
    if not value.strip():
        _fail(where, f"{name} must be a non-empty string")
    return value


def _compile_expression(name, source):
    """Compile a single expression string, raising RuleError on failure."""
    try:
        compile(source, f"<pyteman:{name}>", "eval")
    except SyntaxError as exc:
        raise RuleError(f"{name} is not a valid expression: {exc.msg}") from None


def _expression(where, name, value):
    """A string that compiles in eval mode.

    Compiling here and not at patch time is the point of the check: patching
    happens under the import hook, with the workload already running.
    """
    code = _text(where, name, value)
    try:
        _compile_expression(name, code)
    except RuleError as exc:
        _fail(where, str(exc))
    return code


def _validate_rule_expressions(rule):
    """Validate that a Rule's expressions compile.

    Called from Rule.__post_init__ so that no Rule instance can carry an
    uncompilable expression, whether built by load_rules or by hand through
    the programmatic API.
    """
    rid = rule.id
    if rule.when is not None:
        if not isinstance(rule.when, str):
            raise RuleError(f"rule {rid!r}: when must be a string, "
                            f"got {_typename(rule.when)}")
        try:
            _compile_expression("when", rule.when)
        except RuleError as exc:
            raise RuleError(f"rule {rid!r}: {exc}") from None
    key = rule.fire.get("key") if isinstance(rule.fire, dict) else None
    if key is not None:
        if not isinstance(key, str):
            raise RuleError(f"rule {rid!r}: fire.key must be a string, "
                            f"got {_typename(key)}")
        try:
            _compile_expression("fire.key", key)
        except RuleError as exc:
            raise RuleError(f"rule {rid!r}: {exc}") from None


def _whole(where, name, value):
    """A non-negative int. bool is excluded explicitly: True IS an int in
    Python, so `ms: true` would otherwise read as a one-millisecond sleep."""
    if isinstance(value, bool) or not isinstance(value, int):
        _fail(where, f"{name} must be an integer, got {_typename(value)}")
    if value < 0:
        _fail(where, f"{name} must be non-negative, got {value}")
    return value


def _exit_code(where, name, value):
    code = _whole(where, name, value)
    if code > 255:
        _fail(where, f"{name} must be at most 255, got {code}")
    return code


# TIMEOUT_MAX is the ceiling the lock and Event timeouts enforce, and it sits
# just under the one time.sleep converts against, so a single constant serves
# both actions. Milliseconds because that is the unit the rule is written in;
# the operator should not have to do the division to read the message.
_MAX_SLEEP_MS = int(threading.TIMEOUT_MAX * 1000)


def _millis(where, name, value):
    """A delay the sleep action can convert.

    actions.py evaluates `ms / 1000.0`, so an int too large to become a float
    raises OverflowError right there, and time.sleep raises it again for
    anything past its int64-nanosecond ceiling. Both escape the firing call
    as OverflowError rather than as a RuleError naming the field. The bound
    is TIMEOUT_MAX rather than that ceiling exactly: 0.85s stricter on a
    value that already means 292 years, and one constant instead of two.

    What it bounds is the conversion, not the wait. time.sleep counts against
    an ABSOLUTE monotonic deadline, so the largest value it will really sleep
    is the ceiling minus the clock's current reading, and everything above
    that saturates the deadline and fails with OSError EINVAL instead. At
    TIMEOUT_MAX itself that is what happens on any machine whose monotonic
    clock has advanced at all. That boundary moves while the process runs and
    so cannot be checked here; it is also 292 years out, which is why this
    check exists for the ordinary typo and not for it.
    """
    ms = _whole(where, name, value)
    # Compared as ints on purpose: float(ms) is itself one of the failures
    # this bound exists to turn away, not something caught below.
    if ms > _MAX_SLEEP_MS:
        _fail(where, f"{name} must be at most {_MAX_SLEEP_MS} "
                     f"(threading.TIMEOUT_MAX in milliseconds), got {ms}")
    return ms


def _seconds(where, name, value):
    """A finite positive wait the platform can actually honour.

    Two ways a too-large value escapes as OverflowError rather than
    RuleError: float() rejects an int too large to convert at all, and
    threading.Event.wait, the only consumer today, rejects anything above
    TIMEOUT_MAX with "timestamp out of range" from inside the firing call.
    An infinite timeout is a wedge, not a wait.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(where, f"{name} must be a number, got {_typename(value)}")
    try:
        seconds = float(value)
    except OverflowError:
        _fail(where, f"{name} must be at most threading.TIMEOUT_MAX "
                     f"({threading.TIMEOUT_MAX}), got an integer too large to "
                     f"convert to a float")
    if not math.isfinite(seconds):
        _fail(where, f"{name} must be finite, got {value!r}")
    if seconds <= 0:
        _fail(where, f"{name} must be positive, got {value!r}")
    if seconds > threading.TIMEOUT_MAX:
        _fail(where, f"{name} must be at most threading.TIMEOUT_MAX "
                     f"({threading.TIMEOUT_MAX}), got {value!r}")
    return seconds


# Builtin exception classes that reject the single message argument
# actions.py passes, so `raise exc(message)` would raise TypeError instead of
# the exception the rule asked for. Derived by construction, not guessed:
# tests/test_rules.py::test_unconstructible_exceptions_match_reality pins the
# set against every builtin exception on the running interpreter.
_UNCONSTRUCTIBLE_EXC = frozenset({
    "BaseExceptionGroup", "ExceptionGroup",
    "UnicodeDecodeError", "UnicodeEncodeError", "UnicodeTranslateError",
})


def _exception_name(where, name, value):
    # Same lookup actions.py performs at firing, so an unknown class dies here.
    text = _text(where, name, value)
    exc = getattr(builtins, text, None)
    if not isinstance(exc, type) or not issubclass(exc, BaseException):
        _fail(where, f"{name} {text!r} is not a builtin exception class")
    if text in _UNCONSTRUCTIBLE_EXC:
        _fail(where, f"{name} {text!r} cannot be built from a message alone, "
                     f"so the action would raise TypeError instead of it")
    return text


def _pragma_value(where, name, value):
    # Interpolated into "PRAGMA <name>=<value>". YAML 1.1 reads the bare words
    # ON/OFF/YES/NO as booleans, so `journal_mode: OFF` reaches SQLite as
    # "False": a statement SQLite accepts without error while leaving the mode
    # untouched. Demand the quotes rather than guess what was meant.
    if isinstance(value, bool):
        _fail(where, f"{name} must be quoted: YAML reads ON/OFF/YES/NO as "
                     f"booleans, so this reaches SQLite as {str(value)!r}")
    if not isinstance(value, (str, int)):
        _fail(where, f"{name} must be a string or an integer, got {_typename(value)}")
    if isinstance(value, str) and not value.strip():
        _fail(where, f"{name} must be a non-empty string")
    return value


def _barrier_role(where, name, value):
    role = _text(where, name, value)
    if role not in _BARRIER_ROLES:
        _fail(where, f"{name} must be one of {_BARRIER_ROLES}, got {role!r}")
    return role


def _target(where, name, value):
    _text(where, name, value)
    try:
        validate_target_spec(value, where)
    except ValueError as exc:
        raise RuleError(str(exc)) from None
    return value


def _anything(_where, _name, value):
    """An injected return value is any YAML scalar or structure, None included."""
    return value


def _point(where, value):
    point = _text(where, "point", value)
    parts = point.split(".")
    if len(parts) < 2 or not all(part.isidentifier() for part in parts):
        _fail(where, f"point must be 'module.symbol' with identifier "
                     f"components, got {point!r}")
    return point


# kind -> (required fields, optional fields), each mapped to its validator.
_ACTION_SCHEMA = {
    "sleep":        ({"ms": _millis}, {}),
    "raise":        ({}, {"exc": _exception_name, "message": _text}),
    "return_value": ({}, {"value": _anything}),
    "return_none":  ({}, {}),
    "kill":         ({}, {"exit_code": _exit_code}),
    "pragma":       ({"name": _text, "value": _pragma_value}, {"target": _target}),
    "barrier":      ({"barrier": _text}, {"role": _barrier_role, "timeout_s": _seconds}),
}

# A countdown needs its count and an once_per its key: defaulting either one
# turns a typo into a silently retimed experiment.
_FIRE_SCHEMA = {
    "always":    ({}, {}),
    "once_per":  ({"key": _expression}, {}),
    "countdown": ({"n": _whole}, {}),
}

_ACTION_KINDS = tuple(_ACTION_SCHEMA)
_FIRE_MODES = tuple(_FIRE_SCHEMA)

# noun -> (the key naming the variant, the schema keyed by it). A table rather
# than a conditional, so adding a third section cannot silently inherit the
# fire schema from an else branch.
_SECTIONS = {"action": ("kind", _ACTION_SCHEMA), "fire": ("mode", _FIRE_SCHEMA)}


def _check_section(where, noun, section, kind):
    discriminator, schema = _SECTIONS[noun]
    required, optional = schema[kind]
    for name, check in required.items():
        if name not in section:
            _fail(where, f"{kind} {noun} needs {name!r}")
        check(where, f"{noun}.{name}", section[name])
    for name, value in section.items():
        if name == discriminator or name in required:
            continue
        check = optional.get(name)
        if check is None:
            _fail(where, f"unknown {noun} field {name!r} for {kind!r}")
        check(where, f"{noun}.{name}", value)


def load_rules(path: str) -> list[Rule]:
    with open(path) as fh:
        raw = yaml.safe_load(fh)
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raise RuleError("ruleset must be a YAML list")
    rules = []
    seen_ids = set()
    for i, item in enumerate(raw):
        where = f"rule #{i}"
        if not isinstance(item, dict):
            _fail(where, "mapping required")
        # The id keys every record a rule writes to the firing log, so it must
        # be a hashable non-empty string; it is read before anything else so
        # that it labels every later message, including the missing-field ones,
        # and a ruleset can be fixed without counting list entries.
        if "id" not in item:
            _fail(where, "missing id")
        rule_id = _text(where, "id", item["id"])
        where = f"{where} (id {rule_id!r})"
        if rule_id in seen_ids:
            _fail(where, "id is already used by an earlier rule")
        seen_ids.add(rule_id)
        for key in ("point", "event", "action"):
            if key not in item:
                _fail(where, f"missing {key}")
        # Sorted on repr: unknown keys are unvalidated YAML, so a rule carrying
        # both `3:` and `wehn:` must not die comparing an int with a str.
        unknown = sorted(set(item) - _RULE_KEYS, key=repr)
        if unknown:
            _fail(where, f"unknown rule field(s) {unknown}")
        point = _point(where, item["point"])
        event = item["event"]
        if event not in _EVENTS:
            _fail(where, f"event must be one of {_EVENTS}")
        # A present-but-falsy `when` must never read as "no condition": a bool
        # is rejected rather than coerced, so `when: false` cannot silently
        # become an unconditional injection.
        if "when" in item:
            _expression(where, "when", item["when"])
        action = item["action"]
        if not isinstance(action, dict):
            _fail(where, f"action must be a mapping, got {_typename(action)}")
        # isinstance before the lookup: _ACTION_SCHEMA is a dict, so membership
        # hashes the candidate and an unhashable one would raise TypeError out
        # of load_rules instead of a RuleError naming the rule.
        kind = action.get("kind")
        if not isinstance(kind, str) or kind not in _ACTION_SCHEMA:
            _fail(where, f"action.kind must be one of {_ACTION_KINDS}, got {kind!r}")
        # target: is consumed by pragma only (today). Say so explicitly: the
        # generic unknown-field message would send the operator hunting a typo.
        if "target" in action and kind != "pragma":
            _fail(where, "'target' is only consumed by pragma actions")
        # timeout_s: same shape one branch down. The open branch of the
        # barrier action returns before any timeout is read, so a limit
        # written here is silently no limit at all. Refused whatever the
        # number is, the wait default included, because what is wrong is the
        # field being present rather than the value in it; that is also why
        # this sits ahead of _check_section, which would otherwise answer a
        # bad number with a range the operator cannot act on.
        if (kind == "barrier" and "timeout_s" in action
                and action.get("role", "wait") == "open"):
            _fail(where, "'timeout_s' is only consumed by barrier waits, "
                         "and role: open does not wait")
        _check_section(where, "action", action, kind)
        if kind == "pragma" and "target" in action:
            parsed, _ = parse_target_spec(action["target"])
            if parsed is not None and parsed[0] == "result" and event == "entry":
                _fail(where, "target 'result' can only resolve on exit events")
        fire = item.get("fire", {"mode": "always"})
        if not isinstance(fire, dict):
            _fail(where, f"fire must be a mapping, got {_typename(fire)}")
        mode = fire.get("mode")
        if not isinstance(mode, str) or mode not in _FIRE_SCHEMA:
            _fail(where, f"fire.mode must be one of {_FIRE_MODES}, got {mode!r}")
        _check_section(where, "fire", fire, mode)
        # Rule targets are "module.Class.method": the module is the first dot
        # component and the symbol is the attribute path walked from it, so the
        # split here is at the FIRST dot (parse_point keeps the last-dot split
        # for module-path interpretation).
        mod, _, sym = point.partition(".")
        rules.append(Rule(id=rule_id, module=mod, symbol=sym, event=event,
                          action=action, fire=fire, when=item.get("when")))
    return rules
