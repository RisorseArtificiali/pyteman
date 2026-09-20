# Targeting state the callable holds, not receives

Design decision record for the `target:` mechanism (TASK-108, 2026-09-14).

## The problem

Actions run against the firing context: the call's arguments, keyword
values, fire count, and (on exit events) the result and exception. The
`pragma` action originally scanned just the arguments for a
`sqlite3.Connection`. Real targets hold state as attributes: the Hermes
`SessionDB` carries its connection as `self._conn`, so no argument scan
could ever find it, and the action silently did nothing. The faultlab
adapter worked around this with a parallel `_apply_pragmas` channel,
which is how the gap stayed invisible.

## The mechanism

An action may declare `target:`. Resolution lives in
`pyteman.targets.resolve_target(ctx, spec)` and supports:

- `self`, with an optional dotted attribute walk (`self._conn`,
  `self.pool.engine`): the first positional argument. For a method patched
  through its class, that is the receiver; for a plain function it is
  simply the first argument.
- `param:<name>`, with an optional dotted tail: an argument by parameter
  name, bound through the parameters the instrumented callable really
  receives, so positional and keyword calls both resolve. The parameters are
  derived once at patch time (next to the compiled `when`/`key` expressions)
  and reach the resolver through the firing context; the user's callable is
  never mutated. What "really receives" means is the subject of the next
  section.
- `result`: the return value, exit events only.

One parser (`parse_target_spec`) defines the grammar for both the
load-time validator and the runtime resolver, so the two can never drift
apart.

## What `param:` can name

The parameters are read from CODE: the `__code__` of the function at the
bottom of the layer walk, with type-dict reads and real slot descriptors on
the way down. `inspect.signature` is never called on the target, and
`__signature__`, `__wrapped__`, `__partialmethod__` and `__text_signature__`
are never read.

That is a deliberate withdrawal of trust. Those attributes describe what a
callable WANTS to look like, and a `param:` target has to be resolved against
what the call actually passes. A decorated wrapper is the clearest case:
`functools.wraps` copies `__wrapped__` from the wrapped function, so reading
it would resolve `param:db` against a signature the wrapper itself may never
be called with. The wrapper reports its own `(*args, **kwargs)` instead, the
name does not bind, and the rule misses openly.

Supported shapes, each binding exactly the names a caller may pass:

| shape | binds |
| --- | --- |
| plain function | its parameters |
| bound method | its parameters, receiver dropped |
| instance with `__call__` (plain, `staticmethod` or `classmethod`) | the parameters of `__call__`, one receiver dropped |
| the same with a leading `*args` | `(*args)`: the receiver is ABSORBED, and no named parameter disappears |
| class with `__init__` | `__init__`'s parameters, receiver dropped |
| class with no `__init__` | no parameters |
| `functools.partial` | what the partial leaves for the caller |

Deliberately unavailable, reported as a miss rather than guessed at:

| shape | why |
| --- | --- |
| builtins and method descriptors (`len`, `str.upper`) | no `__code__` to read |
| `__call__` reached through a `__get__`-overriding descriptor | resolving it means modelling an arbitrary descriptor protocol |
| `__call__` that is itself an instance | the parameters belong one layer further out |
| class with a custom metaclass, or its own `__new__` | construction does not reach a readable `__init__` |
| a callable nested deeper than 32 layers | reported as its own reason, distinct from "not modelled" |

One declared limitation, recorded rather than fixed. A keyword pre-bound by a
partial (`functools.partial(f, b=2)`) stays nameable but carries no default,
so a `param:b` rule misses on a call that really does reach `f` with `b=2`.
Making it resolve means reading the partial's keywords at firing time, which
is a change to resolution rather than to the walk. The conservative direction
was taken: the miss is reported honestly and no value is invented.

## Failure policy: loud, never silent

Two layers:

1. Spec syntax is validated at ruleset load (`validate_target_spec`): an
   unknown root, a bare `param:`, an empty walk step (`self..a`), a
   `target:` on a non-pragma action, a pragma action missing `name` or
   `value`, or a `result` target on an entry event raises `RuleError`
   before anything runs. A typo'd rule must die at load, never fire as a
   no-op.
2. Runtime misses (attribute absent on this object, parameter not passed
   in this call, `result` on an entry event) return `(None, reason)`; the
   pragma action records the reason and skips. A failed `execute` on a
   resolved target is recorded the same way. The log is the operator's only
   channel when the workload runs in a container, so the reason reaches it
   as the `outcome` field of a terminal `phase: end` record whose `status`
   says which of the two happened: `pragma_skipped` for a miss,
   `pragma_failed` for an execute that raised. A target that resolves and
   executes gets a third kind of status, from reading the pragma back on the
   object that was resolved rather than on a fresh connection to the same
   file: `foreign_keys` is per-connection, so a second connection would read
   a different answer at the same instant. See the status table in
   `docs/firing.md`. That record is joined by the
   `attempt` field to the `phase: start` record written before the action
   ran, which carries the action dump in `note` and proves an attempt and
   nothing more. A miss is therefore readable as one attempt that took no
   effect, rather than as an absence indistinguishable from a rule that
   never fired. Repeats are not collapsed: under `fire: always`, three
   identical misses are three terminal records, and collapsing them is
   exactly what would make the attempt count impossible to reconstruct.

## Scope decisions

- `target:` is consumed by the `pragma` action only. Other actions take no
  operand today, so accepting a target there would silently ignore it;
  load validation enforces this. Extending to a new action means adding
  one resolve call plus a validation tweak.
- The resolved object is not exposed to `when` expressions. The condition
  language already sees `args`/`kwargs`/`fires`/`result`/`exc`; threading
  `target` in would couple condition evaluation to action parameters for
  no current consumer.
- No chains through mappings or calls (`self.map["k"]`,
  `self.factory()`): attribute walks only, so a spec cannot execute
  arbitrary code beyond `getattr` (conditions remain the deliberate
  trusted-operator surface for expressions).

## Relation to the faultlab adapter

`faultlab-hermes` keeps its `_apply_pragmas` channel. The channel applies
scenario baseline pragmas exactly once per connection at open time, which
is workload setup, not fault injection; a rule firing on every call would
be the wrong tool for that. What changed is that the channel is no longer
a workaround for a missing engine capability: injection-time pragmas on
attribute-held connections are now expressible directly (see
`faultlab-hermes/tests/test_targeting_integration.py`).
