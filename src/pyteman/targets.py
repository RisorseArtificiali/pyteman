# src/pyteman/targets.py
"""Resolution of `target:` specs against the firing context.

Rules sometimes need to reach state the instrumented callable holds rather
than receives: a SessionDB carries its sqlite3.Connection as `self._conn`,
so no argument scan can find it. An action may declare:

    target: self._conn     first positional argument, then attribute walk
    target: param:db       argument by parameter name (signature-bound,
                           positional or keyword)
    target: result         the exit-event return value

For a method patched through its class ("pkg.Session.append"), `self` is
the receiver; for a plain function it is simply the first argument.

One parser (parse_target_spec) defines the grammar for both consumers:
load-time validation dies loudly on a bad spec, and resolve_target turns
runtime misses (attribute absent, parameter not passed) into
(value=None, reason) so callers leave a firing-log note instead of
silently no-op'ing. This module deliberately depends on nothing else in
pyteman.
"""
from functools import lru_cache


def resolve_target(ctx, spec):
    parsed, err = _parse(spec)
    if parsed is None:
        return None, err
    kind, name, dotted = parsed
    if kind == "result":
        if "result" not in ctx:
            return None, "'result' is only available on exit events"
        if ctx["result"] is None:
            return None, "target 'result' resolved to None"
        return ctx["result"], None
    if kind == "param":
        if ctx.get("_signature_unparseable"):
            return None, "the instrumented callable has no parseable signature"
        sig = ctx.get("_signature")
        if sig is None:
            return None, "param: target reached without an instrumented context"
        try:
            bound = sig.bind_partial(*ctx.get("args", ()), **ctx.get("kwargs", {})).arguments
        except TypeError:
            return None, f"arguments do not bind for parameter {name!r}"
        if name not in bound:
            return None, f"parameter {name!r} not passed in this call"
        obj = bound[name]
    else:  # self
        args = ctx.get("args") or ()
        if not args:
            return None, f"{spec!r}: call has no positional arguments"
        obj = args[0]
    if not dotted:
        if obj is None:
            return None, f"target {spec!r} resolved to None"
        return obj, None
    for step in dotted:
        try:
            obj = getattr(obj, step)
        except AttributeError:
            return None, f"{spec!r}: no attribute {step!r} on {type(obj).__name__}"
    if obj is None:
        return None, f"target {spec!r} resolved to None"
    return obj, None


@lru_cache(maxsize=256)
def parse_target_spec(spec):
    """Structured form of a spec: ((kind, name, dotted), None) or (None, reason).

    Cached: specs are per-rule constants resolved on every firing.
    Raises nothing; callers decide the failure policy.
    """
    if not isinstance(spec, str) or not spec.strip():
        return None, "target must be a non-empty string"
    spec = spec.strip()
    if spec == "result":
        return ("result", None, ()), None
    if spec.startswith("param:"):
        rest = spec[len("param") + 1:]
        name, _, tail = rest.partition(".")
        if not name:
            return None, "param: needs a parameter name"
        dotted, err = _steps(tail, spec)
        if err:
            return None, err
        return ("param", name, dotted), None
    root, _, tail = spec.partition(".")
    if root == "self":
        dotted, err = _steps(tail, spec)
        if err:
            return None, err
        return ("self", None, dotted), None
    return None, f"target root must be self/param:<name>/result (got {root!r})"


def _steps(tail, spec):
    """Dotted walk steps, or an error: empty components are a typo, not a
    spelling of a shorter walk, so 'self..a' is rejected rather than read
    as 'self.a'."""
    if not tail:
        return (), None
    steps = tuple(tail.split("."))
    if any(not st for st in steps):
        return None, f"bad target spec {spec!r} (empty step)"
    return steps, None


def _parse(spec):
    # lru_cache requires hashables and the spec is operator-authored YAML
    # (a string by construction); guard anyway for direct API callers.
    try:
        return parse_target_spec(spec)
    except TypeError:
        return None, "target must be a string"


def validate_target_spec(spec, where):
    """Load-time check; raises ValueError when the spec can never resolve.

    rules.py wraps this in its RuleError so this module stays a leaf.
    """
    parsed, reason = _parse(spec)
    if parsed is None:
        raise ValueError(f"{where}: {reason}")
