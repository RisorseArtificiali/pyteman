"""CFG-02. Nested scopes in `when` and `fire.key` see the evaluation context.

`eval_expr` used to hand `ctx` to `eval()` as locals alone. A flat expression
resolves fine against locals, but a lambda body or a generator expression is
its own code object and CPython resolves its free names against `eval()`'s
GLOBALS only, never against the locals mapping the outer expression used. So
`args[0] < kwargs['limit']` fired, `max(x < kwargs['limit'] for x in args)`
and `(lambda: fires)()` raised `NameError` on `kwargs` and `fires`, and the
same held for `result`/`exc` on exit and for a nested `fire.key`.

Every test here goes through the real Patcher on a real instrumented call:
`_gate` and `eval_expr` are exercised the way a firing rule exercises them,
not by calling `eval_expr` directly, because the defect these tests pin is
about what a CONDITION sees at firing time, not about the function in
isolation. The one exception is
`test_the_namespace_is_a_shallow_copy_of_the_context`, which calls
`eval_expr` directly and says in its own docstring why it has to.
"""
import os
import sys
import threading
import types

import pytest

from pyteman.firing import RecordId
from pyteman.patcher import Patcher
from pyteman.rules import Rule

MODNAME = "pyteman_conditions_victim"


class Recorder:
    """One row per firing: (rule id, args, kwargs, result, exc), each read
    from `ctx` at the moment the rule ran.

    LOG-02 calls `record` twice per firing, so the terminal `phase: end`
    record is held apart from `seen` rather than folded into it: these tests
    assert on WHICH rules fired and on what each one saw, and counting the
    outcome record as a second firing would double every entry. `record` also
    has to hand back the attempt id, which `run_action` reads before it lets
    the action run.
    """

    def __init__(self):
        self.seen = []
        self.terminals = []
        self._seq = 0

    def record(self, rule, ctx, note=None, outcome=None,
               phase="start", attempt=None, status=None):
        self._seq += 1
        if phase == "end":
            self.terminals.append((rule.id, attempt, status, outcome))
        else:
            # Snapshotted, not referenced: one ctx dict serves every rule on
            # the call, so holding it would leave each row describing the LAST
            # rule's view.
            self.seen.append((rule.id, ctx.get("args"), ctx.get("kwargs"),
                              ctx.get("result"), ctx.get("exc")))
            attempt = self._seq
        return RecordId("test", os.getpid(), self._seq, attempt)

    @property
    def ids(self):
        return [rid for rid, *_ in self.seen]


def crule(rid, event="entry", when=None, fire=None, action=None, symbol="f"):
    return Rule(id=rid, module=MODNAME, symbol=symbol, event=event,
                action=action or {"kind": "return_value", "value": rid},
                fire=fire or {"mode": "always"}, when=when)


@pytest.fixture
def victim():
    """A fresh victim module per test, so no patch state crosses tests."""
    mod = types.ModuleType(MODNAME)
    setattr(mod, "f", lambda *a, **k: "real")
    sys.modules[MODNAME] = mod
    try:
        yield mod
    finally:
        sys.modules.pop(MODNAME, None)


def test_entry_lambda_sees_args_kwargs_and_fires(victim):
    log = Recorder()
    p = Patcher([crule("r", when="(lambda: args[0] < kwargs['limit'])()")], log)
    p.force_patch_module(MODNAME)
    assert sys.modules[MODNAME].f(5, limit=10) == "r"
    assert sys.modules[MODNAME].f(50, limit=10) == "real"
    assert log.ids == ["r"]


def test_entry_genexp_sees_args_and_kwargs(victim):
    log = Recorder()
    p = Patcher([crule("r", when="max(x < kwargs['limit'] for x in args)")], log)
    p.force_patch_module(MODNAME)
    assert sys.modules[MODNAME].f(1, 2, limit=10) == "r"
    assert sys.modules[MODNAME].f(20, 30, limit=10) == "real"


def test_entry_listcomp_sees_context(victim):
    """Comprehensions bite on 3.11 only: PEP 709 inlines list/set/dict
    comprehensions into the enclosing scope from 3.12, so this expression is
    already fine there before the fix. It is kept because 3.11 is supported
    and because the inlining does not extend to the genexp and lambda tests
    above, which fail on every supported interpreter without the fix."""
    log = Recorder()
    p = Patcher([crule("r", when="len([x for x in args if x > kwargs['floor']]) > 0")], log)
    p.force_patch_module(MODNAME)
    assert sys.modules[MODNAME].f(5, floor=1) == "r"
    assert sys.modules[MODNAME].f(0, floor=1) == "real"


def test_entry_dictcomp_sees_context(victim):
    """PEP 709 applies here too; see `test_entry_listcomp_sees_context`."""
    log = Recorder()
    p = Patcher([crule("r", when="len({x: 1 for x in args if x > kwargs['floor']}) > 0")], log)
    p.force_patch_module(MODNAME)
    assert sys.modules[MODNAME].f(5, floor=1) == "r"
    assert sys.modules[MODNAME].f(0, floor=1) == "real"


def test_entry_naming_fires_through_a_lambda(victim):
    """Countdown fires on the (n+1)th reach, so n=1 fires on the 2nd call."""
    log = Recorder()
    p = Patcher([crule("r", fire={"mode": "countdown", "n": 1},
                        when="(lambda: fires >= 2)()")], log)
    p.force_patch_module(MODNAME)
    assert sys.modules[MODNAME].f() == "real"
    assert sys.modules[MODNAME].f() == "r"
    assert log.ids == ["r"]


def test_exit_lambda_sees_result(victim):
    """The lambda sees `result`, so its true condition fires the exit rule
    and the rule's own return_value action overrides the call's result."""
    log = Recorder()
    p = Patcher([crule("r", event="exit", when="(lambda: result == 'real')()")], log)
    p.force_patch_module(MODNAME)
    assert sys.modules[MODNAME].f() == "r"
    assert log.ids == ["r"]


def test_exit_genexp_sees_exc(victim):
    def body(*a, **k):
        raise ValueError("boom")

    setattr(victim, "f", body)
    log = Recorder()
    p = Patcher([crule("r", event="exit",
                        when="max((exc is not None) for _ in (0,))")], log)
    p.force_patch_module(MODNAME)
    with pytest.raises(ValueError, match="boom"):
        sys.modules[MODNAME].f()
    assert log.ids == ["r"]


def test_entry_naming_result_or_exc_still_raises_nameerror(victim):
    """Entry has no `result`/`exc` in ctx at all; this fix does not add them.

    The nested-scope fix makes a GLOBALS lookup succeed for whatever IS in
    ctx. It cannot manufacture a key ctx never had. An entry condition that
    reaches `result` as a genuine lookup still raises `NameError`, exactly as
    documented, whether the read happens flat or through a lambda.
    """
    log = Recorder()
    p = Patcher([crule("r", when="(lambda: result)()")], log)
    p.force_patch_module(MODNAME)
    with pytest.raises(NameError, match="result"):
        sys.modules[MODNAME].f()


def test_disallowed_builtin_through_a_lambda_still_raises_nameerror(victim):
    """The ten-name allowlist is unchanged; a lambda cannot reach past it."""
    log = Recorder()
    p = Patcher([crule("r", when="(lambda: sum(args))()")], log)
    p.force_patch_module(MODNAME)
    with pytest.raises(NameError, match="sum"):
        sys.modules[MODNAME].f(1, 2)


def test_missing_kwarg_through_a_genexp_still_raises_keyerror(victim):
    """Lookup errors inside the newly-visible scope still propagate, not swallowed."""
    log = Recorder()
    p = Patcher([crule("r", when="max(kwargs['missing'] for _ in args)")], log)
    p.force_patch_module(MODNAME)
    with pytest.raises(KeyError):
        sys.modules[MODNAME].f(1)


def test_once_per_key_built_from_a_lambda(victim):
    """`fire.key` is compiled and eval'd through the same `eval_expr`."""
    log = Recorder()
    p = Patcher([crule("r", fire={"mode": "once_per",
                                   "key": "(lambda: args[0])()"})], log)
    p.force_patch_module(MODNAME)
    assert sys.modules[MODNAME].f(1) == "r"
    assert sys.modules[MODNAME].f(1) == "real"
    assert sys.modules[MODNAME].f(2) == "r"
    assert log.ids == ["r", "r"]


def test_once_per_key_from_a_genexp_over_kwargs(victim):
    """`tuple` is not in the ten-name allowlist; wrap the genexp in `sorted`
    instead, so the key stays a plain scalar the genexp actually produces.

    The lookup is `kwargs[k] for k in kwargs` and not `kwargs.values()` on
    purpose. A genexp's OUTERMOST iterable is evaluated eagerly in the
    enclosing scope, so `kwargs.values()` resolves `kwargs` outside the nested
    code object and the test would pass without the fix. Reading `kwargs[k]`
    in the body puts the lookup where the defect actually lives.
    """
    log = Recorder()
    p = Patcher([crule("r", fire={"mode": "once_per",
                                   "key": "sorted(kwargs[k] for k in kwargs)[0]"})], log)
    p.force_patch_module(MODNAME)
    assert sys.modules[MODNAME].f(sid="a") == "r"
    assert sys.modules[MODNAME].f(sid="a") == "real"
    assert sys.modules[MODNAME].f(sid="b") == "r"


def test_a_top_level_walrus_no_longer_writes_through_to_ctx(victim):
    """A condition asks a question about the call; it does not edit the call.

    This is the one behaviour CFG-02 deliberately changes. `clobber`'s own
    top-level walrus used to rebind the per-call ctx, so the rules after it on
    the same call read an `exc` the body never raised. Both rules still fire
    and `reader` still sees the real ValueError, as before; what changed is
    that `clobber` now reads the real one too, because its write landed in the
    evaluation namespace rather than in ctx.
    """
    def body(*a, **k):
        raise ValueError("from the body")

    setattr(victim, "f", body)
    log = Recorder()
    p = Patcher([crule("clobber", event="exit", when="(exc := None) is None"),
                 crule("reader", event="exit", when="exc is not None")], log)
    p.force_patch_module(MODNAME)
    with pytest.raises(ValueError, match="from the body"):
        sys.modules[MODNAME].f()
    assert log.ids == ["clobber", "reader"]
    saw = {rid: exc for rid, _, _, _, exc in log.seen}
    assert type(saw["clobber"]) is ValueError, \
        "a condition's own walrus edited the call it was asked about"
    assert type(saw["reader"]) is ValueError


def test_a_name_bound_mid_expression_reads_back_the_same_everywhere(victim):
    """One expression must not contradict itself about a name it just bound.

    Splitting globals and locals would bind a top-level walrus in the locals
    mapping, which flat code reads and a lambda or genexpr cannot, so the same
    name would resolve in one half of an expression and raise NameError in the
    other. PEP 709 makes that split interpreter-dependent on top: from 3.12 a
    comprehension is inlined and WOULD see the binding while a genexpr beside
    it would not. Each condition here binds `cap` once and reads it back
    through a different construct; all four must agree.

    Each condition gets its OWN symbol, so each is evaluated against a ctx
    built fresh for its own call. Sharing one symbol would hide the very
    thing under test: with globals and locals split, the first rule's walrus
    lands in the shared ctx and the next rule's snapshot is built from that
    ctx, so a genexp that cannot see its own binding resolves the PREVIOUS
    rule's and the test passes for the wrong reason.
    """
    def body(*a, **k):
        return 1

    CASES = [
        ("flat", "(cap := args[0]) and cap == 1"),
        ("listcomp", "(cap := args[0]) and min([x == cap for x in args])"),
        ("genexp", "(cap := args[0]) and max(x == cap for x in args)"),
        ("lambda", "(cap := args[0]) and (lambda: cap == 1)()"),
    ]
    for rid, _ in CASES:
        setattr(victim, rid, body)

    log = Recorder()
    p = Patcher([crule(rid, event="entry", when=when, symbol=rid,
                       action={"kind": "sleep", "ms": 0})
                 for rid, when in CASES], log)
    p.force_patch_module(MODNAME)
    for rid, _ in CASES:
        getattr(sys.modules[MODNAME], rid)(1)

    assert log.ids == [rid for rid, _ in CASES], \
        "a name bound at the top of a condition did not survive into a " \
        "nested scope of the same condition"


def test_a_nested_walrus_does_not_survive_into_the_next_condition(victim):
    """The namespace is per-evaluation, so a condition cannot poison the process.

    This is the only place a nested walrus is observable at all, and it is why
    the namespace is built inside `eval_expr` rather than once at import. A
    walrus inside a genexp is targeted by PEP 572 at the enclosing scope, which
    at eval()'s top level is the GLOBALS mapping. A test asserting such a
    binding does not reach `ctx` would pass under every implementation, since
    `ctx` is the LOCALS mapping and the binding never lands there; two such
    tests stood here and were deleted as vacuous. With one module-level globals
    dict shared by every evaluation, `writer`'s binding outlived its call, and
    every later condition in the process resolved that name on any rule, on
    any call, in any thread, until the process ended.

    `late` asks for that name and must not find it. A condition that raises
    leaves the visit counted and the rule not fired (see `_gate`), so the
    NameError reaching the caller IS the assertion: the name is gone. Before
    this fix `late` fired instead, on a value another rule left behind.
    """
    log = Recorder()
    p = Patcher([crule("writer", event="exit",
                       when="max((hijack := 'poison') is not None for _ in (0,)) and False"),
                 crule("late", event="exit", when="hijack == 'poison'")], log)
    p.force_patch_module(MODNAME)

    with pytest.raises(NameError, match="hijack"):
        sys.modules[MODNAME].f()
    assert log.ids == [], \
        "a walrus in one condition outlived it and reached a later rule"


def test_concurrent_calls_do_not_share_context(victim):
    """Two threads, two distinct `args`, each firing must see only its own.

    `ctx` is built fresh per call in the dispatcher; the globals snapshot
    `eval_expr` now builds is taken from that same per-call `ctx`, so this
    proves the fix did not turn per-call state into anything shared.

    The recorder here is local rather than the module's `Recorder` because
    `Recorder` is not thread-safe: its `_seq` counter and its lists are
    unguarded, so sharing it across the two threads would race on the
    bookkeeping and not on the property under test.
    """
    seen = []
    lock = threading.Lock()

    def body(*a, **k):
        return a[0]

    setattr(victim, "f", body)

    def record(rule, ctx, note=None, outcome=None,
               phase="start", attempt=None, status=None):
        with lock:
            if phase != "end":
                seen.append(ctx["args"][0])
            return RecordId("test", os.getpid(), len(seen), len(seen))

    log = types.SimpleNamespace(record=record)
    p = Patcher([crule("r", event="exit",
                        when="(lambda: result == args[0])()",
                        action={"kind": "sleep", "ms": 0})], log)
    p.force_patch_module(MODNAME)

    def call(n):
        assert sys.modules[MODNAME].f(n) == n

    threads = [threading.Thread(target=call, args=(n,), daemon=True)
               for n in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
        assert not t.is_alive()

    assert sorted(seen) == list(range(20))


def test_a_rule_cannot_rebind_args_for_the_rules_after_it(victim):
    """RT-02h, entry half. `args` is seeded once per call, not once per rule.

    With `ctx` serving as eval's locals, a top-level walrus wrote straight into
    the per-call dict every rule on the slot shares, so `writer` handed its own
    `args` to every rule below it. `writer` forces `and False` so it never
    fires and never reaches its action: the only thing it does on this call is
    the rebinding. `reader` must still see what the caller passed.
    """
    log = Recorder()
    p = Patcher([crule("writer", when="(args := (99,)) and False"),
                 crule("reader", when="args[0] == 1")], log)
    p.force_patch_module(MODNAME)
    assert sys.modules[MODNAME].f(1) == "reader"
    assert log.ids == ["reader"]
    saw = {rid: a for rid, a, _, _, _ in log.seen}
    assert saw["reader"] == (1,), "a condition's walrus rewrote args for the next rule"


def test_a_rule_cannot_rebind_kwargs_for_the_rules_after_it(victim):
    """RT-02h, exit half. Same defect on the other seeded name and the other
    event, because the exit loop re-seeds `result` and `exc` per rule and has
    never re-seeded `kwargs`.
    """
    log = Recorder()
    p = Patcher([crule("writer", event="exit",
                       when="(kwargs := {'x': 99}) and False"),
                 crule("reader", event="exit", when="kwargs['x'] == 1")], log)
    p.force_patch_module(MODNAME)
    assert sys.modules[MODNAME].f(x=1) == "reader"
    assert log.ids == ["reader"]
    saw = {rid: k for rid, _, k, _, _ in log.seen}
    assert saw["reader"] == {"x": 1}, "a condition's walrus rewrote kwargs for the next rule"


def test_the_namespace_is_a_shallow_copy_of_the_context(victim):
    """What the namespace copies and what it shares, pinned in one place.

    This is the only test here that calls `eval_expr` directly, and
    deliberately so: the property is about the mapping the function builds,
    and a generator is the cleanest way to hold that mapping still and look at
    it. `when` does not retain the value it returns and `_check_once_per_key`
    rejects generator and function keys, but neither closes the lifetime
    question: a condition can stash a closure into an object reachable from
    the context, which `test_a_condition_can_retain_its_namespace_past_the_call`
    shows through the real Patcher. Nothing here is a lifetime or isolation
    guarantee.

    The distinction it does pin is the whole read/write contract: rebinding a
    key in `ctx` afterwards does NOT reach the namespace, because the
    namespace took its own binding, while mutating the object that key points
    at DOES, because both mappings hold the same object.
    """
    from pyteman.conditions import eval_expr

    code = compile("(x + bump for x in args)", "<pyteman:test>", "eval")

    ctx = {"args": [1, 2], "bump": 10}
    gen = eval_expr(code, ctx)
    ctx["bump"] = 1000
    assert list(gen) == [11, 12], "a rebinding in ctx reached a live namespace"

    ctx = {"args": [1, 2], "bump": 10}
    gen = eval_expr(code, ctx)
    ctx["args"].append(3)
    assert list(gen) == [11, 12, 13], "the namespace copied the list instead of sharing it"


def test_a_condition_can_retain_its_namespace_past_the_call(victim):
    """Documents a reachable limit; it does not propose a contract.

    A condition that appends a lambda to a list the caller passed leaves that
    lambda alive after the call returns, holding the namespace it was built
    against. So the per-call mapping is not a lifetime or isolation boundary,
    and the docs say so. This is the ordinary consequence of the namespace
    sharing the context's objects rather than copying them, not a separate
    defect: conditions are trusted operator input.
    """
    log = Recorder()
    p = Patcher([crule("r", when="kwargs['saved'].append(lambda: args[0]) is None")], log)
    p.force_patch_module(MODNAME)
    saved = []
    assert sys.modules[MODNAME].f(42, saved=saved) == "r"
    assert len(saved) == 1
    assert saved[0]() == 42, "the retained closure lost the namespace it was built against"
