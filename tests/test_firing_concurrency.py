"""CON-01. The firing decision under concurrent visits, and the key contract.

`_gate` is driven directly in most of this file, and that is deliberate rather
than a shortcut. The defect these tests pin is a window between a check and an
act, so a test only proves anything if it can hold two threads open INSIDE that
window, and the only instrument that reaches it is the operator's own condition
expression. Driving the gate lets a condition block on a barrier at exactly the
moment that matters. Where a test does not need that control it goes through
`install` and a real call instead.

Every threaded test here joins with a timeout and then asserts the thread is
dead. A regression that reintroduces a lock around operator code does not fail
these tests by returning the wrong number, it fails them by hanging, and a hung
test that is never bounded takes the whole suite with it.
"""
import subprocess
import sys
import threading
import tracemalloc

import pytest

from pyteman.patcher import (OncePerKeyError, _ONCE_PER_KEY_DEPTH,
                             _ONCE_PER_KEY_NODES, _ONCE_PER_KEY_TYPES, _gate,
                             _check_once_per_key, _new_state, install)
from pyteman.rules import Rule

JOIN_TIMEOUT = 5


def code(source):
    return compile(source, "<test_firing_concurrency>", "eval")


def once_per_rule(key="k"):
    return Rule(id="op", module="target_mod", symbol="plain", event="entry",
                action={"kind": "return_value", "value": 99},
                fire={"mode": "once_per", "key": key})


def countdown_rule(n=1):
    return Rule(id="cd", module="target_mod", symbol="plain", event="entry",
                action={"kind": "return_value", "value": 99},
                fire={"mode": "countdown", "n": n})


def run_threads(targets):
    """Start every callable, join each with a bound, report any that is stuck.

    The workers are daemonic, and that is the whole point rather than a detail.
    A regression here shows up as a thread that never returns, and a non-daemon
    worker in that state keeps the interpreter alive after the test has already
    failed: `threading._shutdown` joins it at exit, so the assertion below fires,
    pytest prints its report, and the process then hangs forever with no test
    left to blame. Measured, not assumed: the same helper with non-daemon threads
    printed its failure and then had to be killed by an external watchdog.

    So the guarantee is stated precisely. A stuck worker is REPORTED and cannot
    block the run from ending; it is not stopped. It stays parked on whatever it
    is waiting for until the process exits, which for a deadlocked `_gate` means
    it also keeps holding that rule's lock, and any later test sharing that state
    object would fail too. Every test here builds its own state, so that does not
    leak across them.
    """
    threads = [threading.Thread(target=t, daemon=True) for t in targets]
    for t in threads:
        t.start()
    for t in threads:
        t.join(JOIN_TIMEOUT)
    alive = [t for t in threads if t.is_alive()]
    assert not alive, "{} thread(s) still running after {}s".format(
        len(alive), JOIN_TIMEOUT)


def gate_in_threads(rule, state, contexts, when_code):
    """One `_gate` call per context, concurrently, returning what each decided."""
    results = [None] * len(contexts)
    errors = [None] * len(contexts)
    key_code = code(rule.fire["key"]) if rule.fire.get("key") else None

    def one(i):
        def run():
            try:
                results[i] = _gate(rule, state, contexts[i], when_code, key_code)
            except BaseException as exc:
                errors[i] = exc
        return run

    run_threads([one(i) for i in range(len(contexts))])
    return results, errors


# --- the race itself ------------------------------------------------------

def test_two_threads_holding_the_same_key_produce_exactly_one_fire():
    """The window is the condition, so the condition is where they are held.

    Both threads reach the barrier from inside `when`, which is precisely
    between the membership check and the claim. Before CON-01 both had already
    read an empty `seen_keys` by then and both were told to fire, which is the
    one promise once_per makes.
    """
    rule = once_per_rule()
    state = _new_state()
    barrier = threading.Barrier(2)
    contexts = [{"args": (), "kwargs": {}, "k": "K",
                 "sync": lambda: barrier.wait(timeout=JOIN_TIMEOUT)}
                for _ in range(2)]

    results, errors = gate_in_threads(
        rule, state, contexts, code("sync() is not None or True"))

    assert errors == [None, None]
    assert sum(1 for r in results if r) == 1
    assert state["seen_keys"] == {"K"}
    assert state["fires"] == 2


def test_two_threads_holding_different_keys_both_fire():
    """The control, and it is not a formality.

    A fix that simply serialises the whole gate closes the test above and breaks
    this one, because the two visits would queue instead of overlapping and the
    barrier would time out. Different keys are independent decisions and both
    must still be reached.
    """
    rule = once_per_rule()
    state = _new_state()
    barrier = threading.Barrier(2)
    contexts = [{"args": (), "kwargs": {}, "k": key,
                 "sync": lambda: barrier.wait(timeout=JOIN_TIMEOUT)}
                for key in ("K1", "K2")]

    results, errors = gate_in_threads(
        rule, state, contexts, code("sync() is not None or True"))

    assert errors == [None, None]
    assert results == [True, True]
    assert state["seen_keys"] == {"K1", "K2"}


def test_a_condition_that_is_false_leaves_the_key_for_the_other_thread():
    """A refused visit must not consume the key, concurrently as it does serially.

    Both threads carry the same key and meet in the condition; one then says no.
    The contract is that a false condition costs the visit but not the key, so
    the thread that says yes still fires.
    """
    rule = once_per_rule()
    state = _new_state()
    barrier = threading.Barrier(2)
    contexts = [{"args": (), "kwargs": {}, "k": "K", "yes": yes,
                 "sync": lambda: barrier.wait(timeout=JOIN_TIMEOUT)}
                for yes in (True, False)]

    results, errors = gate_in_threads(
        rule, state, contexts, code("(sync() is not None or True) and yes"))

    assert errors == [None, None]
    assert results == [True, False]
    assert state["seen_keys"] == {"K"}


# --- the key contract -----------------------------------------------------

class HostileKey:
    """Records being asked, which is the thing that must never happen.

    Both methods answer harmlessly. The point is not that they misbehave, it is
    that under the old code they would run at all, holding whatever lock the
    membership test holds, on an object the operator supplied.
    """

    def __init__(self):
        self.hashed = 0
        self.compared = 0

    def __hash__(self):
        self.hashed += 1
        return 0

    def __eq__(self, other):
        self.compared += 1
        return self is other


class SneakyStr(str):
    """A str subclass, which is how an operator __eq__ arrives wearing a name.

    `isinstance(x, str)` would accept this and then run the methods below on the
    claim path. `type(x) is str` does not, and that is the whole reason the check
    is written with exact types.
    """

    hashed = 0
    compared = 0

    def __hash__(self):
        type(self).hashed += 1
        return str.__hash__(self)

    def __eq__(self, other):
        type(self).compared += 1
        return str.__eq__(self, other)


def gate_once(rule, state, key):
    ctx = {"args": (), "kwargs": {}, "k": key}
    return _gate(rule, state, ctx, None, code("k"))


def test_a_key_with_its_own_dunders_is_refused_without_either_being_called():
    rule = once_per_rule()
    state = _new_state()
    hostile = HostileKey()

    with pytest.raises(OncePerKeyError) as caught:
        gate_once(rule, state, hostile)

    assert "HostileKey" in str(caught.value)
    assert (hostile.hashed, hostile.compared) == (0, 0)
    assert state["seen_keys"] == set()
    # The visit still counted. A refusal is not a call that never happened.
    assert state["fires"] == 1


def test_a_builtin_subclass_is_refused_and_is_never_asked_anything():
    rule = once_per_rule()
    state = _new_state()
    SneakyStr.hashed = SneakyStr.compared = 0

    with pytest.raises(OncePerKeyError) as caught:
        gate_once(rule, state, SneakyStr("K"))

    assert "SneakyStr" in str(caught.value)
    assert (SneakyStr.hashed, SneakyStr.compared) == (0, 0)


@pytest.mark.parametrize("key", [None, True, 7, 1.5, "K", b"K",
                                 (1, "a"), ((1, 2), (b"c", None)), ()])
def test_the_accepted_types_still_key_by_python_equality(key):
    """Accepted keys are not converted, so a repeat is recognised as a repeat."""
    rule = once_per_rule()
    state = _new_state()

    assert gate_once(rule, state, key) is True
    assert gate_once(rule, state, key) is False
    assert state["seen_keys"] == {key}


def test_a_tuple_is_refused_for_what_it_contains():
    """The walk goes in. A tuple is only as safe as its elements."""
    rule = once_per_rule()
    state = _new_state()
    hostile = HostileKey()

    with pytest.raises(OncePerKeyError) as caught:
        gate_once(rule, state, (1, (2, hostile)))

    assert "HostileKey" in str(caught.value)
    assert (hostile.hashed, hostile.compared) == (0, 0)


def nest(depth):
    key = ()
    for _ in range(depth):
        key = (key,)
    return key


def test_a_tuple_nested_to_the_limit_is_accepted():
    """The walk is iterative, so the limit is the contract and not the stack."""
    rule = once_per_rule()
    state = _new_state()

    assert gate_once(rule, state, nest(_ONCE_PER_KEY_DEPTH - 1)) is True


SHARED_SUBTUPLE_PROBE = """
import sys
from pyteman.patcher import OncePerKeyError, _check_once_per_key


class Rule:
    fire = {"mode": "once_per"}
    id = "op"
    module = "m"
    symbol = "s"


key = ()
for _ in range(40):
    key = (key, key)

try:
    _check_once_per_key(Rule(), key)
except OncePerKeyError as exc:
    print("REFUSED", "elements to visit" in str(exc))
    sys.exit(0)
print("ACCEPTED")
sys.exit(1)
"""


def test_a_shallow_tuple_that_shares_its_subtuples_is_refused_quickly():
    """Depth is not size, and the hash pays for size.

    Each level here doubles the element count while adding one to the depth, so
    forty levels is trivially within the nesting limit and has about a trillion
    nodes. Nothing caches a tuple's hash, so hashing this key would walk every
    one of them while holding the rule's lock. Measured before the budget
    existed, the walk alone quadrupled for every two levels added and took
    nineteen seconds at depth twenty-four.

    This one runs in a child rather than in-process, and that is the difference
    between a test and a trap. Against an implementation with no element budget
    the walk does not fail, it does not return either, and an in-process version
    would hang the whole suite on the defect it exists to report. The child can
    be killed, so the failure arrives as a failure.
    """
    probe = subprocess.run([sys.executable, "-c", SHARED_SUBTUPLE_PROBE],
                           capture_output=True, text=True, timeout=JOIN_TIMEOUT)

    assert probe.returncode == 0, "child said: {}{}".format(
        probe.stdout, probe.stderr)
    assert probe.stdout.split() == ["REFUSED", "True"]


def test_a_wide_but_ordinary_tuple_is_still_a_key():
    """The budget has to be out of the way of anything an operator would write."""
    rule = once_per_rule()
    state = _new_state()

    assert gate_once(rule, state, tuple(range(1000))) is True
    assert gate_once(rule, state, tuple(range(1000))) is False


def test_one_very_wide_tuple_is_refused_before_it_is_expanded():
    """The budget has to stop the walk, not merely notice afterwards.

    A per-element check gets no turn while a single tuple is being expanded, so
    a key of two references to one very wide tuple was refused only after the
    whole width had been copied onto the walk's stack. Measured against that
    shape at five million elements: 0.489s and 306MB of transient allocation for
    a key that was rejected anyway. Charging the width before expanding refuses
    the same key in under a millisecond and allocates almost nothing.

    Allocation is the right thing to assert on, since that is what the defect
    moved, but it has to be measured as allocation attributable to THIS call.
    Peak RSS cannot do that: it is a high-water mark for the whole pytest
    process, so any earlier test that allocated more than this one would leave
    the difference at zero and the test would pass against the defective walk.
    `tracemalloc` peak, reset immediately before the call, is scoped to the
    window instead. The key is built before the window opens so that its own
    cost is excluded and only the walk's allocation is measured, and the figure
    is in bytes on every platform rather than in units that differ across them.

    `reset_peak` rebases the peak to what is currently traced rather than to
    zero, so the peak is read as a difference against that baseline. Without
    that subtraction the measurement is still absolute whenever tracing was
    already running when this test began, which is the one case where the key
    itself is also traced, and a retained buffer elsewhere in the process would
    fail the assertion on memory this call never allocated.
    """
    rule = once_per_rule()
    wide = tuple(range(1000000))
    key = (wide, wide)

    was_tracing = tracemalloc.is_tracing()
    if not was_tracing:
        tracemalloc.start()
    try:
        baseline_bytes = tracemalloc.get_traced_memory()[0]
        tracemalloc.reset_peak()
        with pytest.raises(OncePerKeyError) as caught:
            _check_once_per_key(rule, key)
        allocated_bytes = tracemalloc.get_traced_memory()[1] - baseline_bytes
    finally:
        if not was_tracing:
            tracemalloc.stop()

    assert str(_ONCE_PER_KEY_NODES) in str(caught.value)
    assert allocated_bytes < 8 * 1024 * 1024, (
        "refusing a wide key allocated {} bytes".format(allocated_bytes))


def test_two_equal_tuples_at_the_limit_are_one_key():
    """The bound has to survive the operations the key exists for.

    Accepting the first insert only proves the validator walked it. The claim
    path then hashes the key and, on a collision, compares it, and both of those
    recurse to the same depth inside the critical section. Two distinct objects
    that are equal at the limit exercise hashing and equality rather than
    identity, so this is what shows the bound is safe for the real work and not
    just for the check.
    """
    rule = once_per_rule()
    state = _new_state()
    first = nest(_ONCE_PER_KEY_DEPTH - 1)
    second = nest(_ONCE_PER_KEY_DEPTH - 1)

    assert first is not second
    assert first == second
    assert hash(first) == hash(second)
    assert gate_once(rule, state, first) is True
    assert gate_once(rule, state, second) is False
    assert len(state["seen_keys"]) == 1


def test_a_tuple_nested_past_the_limit_is_refused_rather_than_hashed():
    """Past the bound the refusal has to arrive as an error, not a segfault.

    `nest(_ONCE_PER_KEY_DEPTH)` is the shallowest tuple the walk refuses: its
    innermost element sits at walk-depth `_ONCE_PER_KEY_DEPTH`, one past the
    deepest accepted key from the boundary tests above. Testing exactly that
    key, rather than something further past it, pins the refusal to the true
    edge instead of leaving a gap where an off-by-one in the guard could hide.

    `tuple.__hash__` recurses through the C stack once per level with no guard,
    and it would run inside the critical section. Refusing here is what keeps a
    deep key from taking the interpreter down instead of raising.
    """
    rule = once_per_rule()
    state = _new_state()

    with pytest.raises(OncePerKeyError) as caught:
        gate_once(rule, state, nest(_ONCE_PER_KEY_DEPTH))

    assert "nested deeper" in str(caught.value)
    assert state["seen_keys"] == set()


def test_a_refused_key_reaches_the_operator_through_a_real_call():
    """End to end: the refusal is not swallowed into a silent non-fire."""
    import target_mod
    rule = Rule(id="op", module="target_mod", symbol="plain", event="entry",
                action={"kind": "return_value", "value": 99},
                fire={"mode": "once_per", "key": "args[0]"})
    p = install([rule], log=None)
    try:
        p.force_patch_module("target_mod")
        with pytest.raises(OncePerKeyError):
            target_mod.plain(HostileKey())
    finally:
        p.uninstall()
    assert target_mod.plain(1, 2) == 3


def test_an_already_seen_key_returns_before_the_condition_runs():
    """The early membership read is a promise, so something has to hold it.

    A key already claimed is a decision that is already made, and `when` is
    operator code that may be expensive or may have effects. The gate is
    documented to return before running it on a repeat visit, and without this
    test that read could be deleted with the whole file still green, because the
    later re-check would produce the same answer by a slower and noisier route.
    """
    rule = once_per_rule()
    state = _new_state()
    ran = []

    def condition():
        ran.append(len(ran))
        return True

    def visit():
        ctx = {"args": (), "kwargs": {}, "k": "K", "cond": condition}
        return _gate(rule, state, ctx, code("cond()"), code("k"))

    assert visit() is True
    assert ran == [0]
    assert visit() is False
    assert ran == [0], "the condition ran again for a key already claimed"


# --- re-entrancy ----------------------------------------------------------

def test_a_condition_that_re_enters_the_same_gate_does_not_deadlock():
    """The lock is not reentrant, and it must never be held across `when`.

    An RLock here would hide the violation rather than fix it, because the
    dangerous wait is on ANOTHER thread inside a key's method, which re-entrancy
    does nothing for. So the invariant is that no operator code runs under the
    lock at all, and this test is what notices when that stops being true.
    """
    rule = once_per_rule()
    state = _new_state()
    inner = {}

    def reenter():
        inner["result"] = _gate(
            rule, state, {"args": (), "kwargs": {}, "k": "inner"},
            None, code("k"))
        return True

    ctx = {"args": (), "kwargs": {}, "k": "outer", "reenter": reenter}
    done = []

    def run():
        done.append(_gate(rule, state, ctx, code("reenter()"), code("k")))

    run_threads([run])

    assert done == [True]
    assert inner["result"] is True
    assert state["seen_keys"] == {"outer", "inner"}
    assert state["fires"] == 2


class Reenterer:
    """Re-enters the patched callable from inside the condition.

    The re-entry has to be provoked from `when` rather than from an action,
    because the outer visit is mid-gate at that moment and that is the only
    point where a lock the gate failed to release could bite. It arrives through
    an argument because the condition namespace holds only `args`, `kwargs` and
    `fires`, so a method on the argument is the operator's real reach.
    """

    def __init__(self, name, depth):
        self.name = name
        self.depth = depth

    def again(self):
        if self.depth:
            import target_mod
            assert target_mod.plain(Reenterer("inner", self.depth - 1)) == 99
        return True


def test_a_re_entrant_condition_through_a_real_call_does_not_deadlock():
    import target_mod
    rule = Rule(id="op", module="target_mod", symbol="plain", event="entry",
                action={"kind": "return_value", "value": 99},
                when="args[0].again()",
                fire={"mode": "once_per", "key": "args[0].name"})
    p = install([rule], log=None)
    outcome = []
    try:
        p.force_patch_module("target_mod")
        seen_keys = target_mod.plain._pyteman_state[0]["seen_keys"]
        run_threads([lambda: outcome.append(
            target_mod.plain(Reenterer("outer", 1)))])
        assert outcome == [99]
        assert seen_keys == {"outer", "inner"}
    finally:
        p.uninstall()


# --- per-rule locks -------------------------------------------------------

def test_each_rule_on_one_callable_gets_a_lock_of_its_own():
    """A shared lock would make one rule's key hashing stall every other rule."""
    import target_mod
    p = install([once_per_rule(), countdown_rule()], log=None)
    try:
        p.force_patch_module("target_mod")
        locks = [st["lock"] for st in target_mod.plain._pyteman_state]
        assert len(locks) == 2
        assert locks[0] is not locks[1]
    finally:
        p.uninstall()


def test_extending_a_dispatcher_leaves_the_bound_rules_their_own_lock():
    """A rebuilt lock is a rebuilt decision boundary for rules already running.

    The extension has to be provoked properly. Patching the same module twice is
    a no-op and would let this pass against a `_gate` that rebuilt the lock on
    every call, so the second rule points at a SECOND module that aliases the
    first, which is how a later patch reaches a dispatcher that is already live
    and merges a rule into it.
    """
    import types

    import target_mod

    alias = types.ModuleType("con01_alias")
    alias.via = target_mod
    sys.modules["con01_alias"] = alias
    added = Rule(id="added", module="con01_alias", symbol="via.plain",
                 event="entry", action={"kind": "sleep", "ms": 0},
                 fire={"mode": "always"})
    p = install([once_per_rule(), added], log=None)
    try:
        p.force_patch_module("target_mod")
        state = target_mod.plain._pyteman_state
        assert len(state) == 1
        before = state[0]["lock"]

        p.force_patch_module("con01_alias")
        extended = target_mod.plain._pyteman_state
        assert len(extended) == 2, "the extension path was not reached"
        assert extended[0]["lock"] is before
        assert extended[0]["lock"] is not extended[1]["lock"]
    finally:
        p.uninstall()
        sys.modules.pop("con01_alias", None)


# --- the counter ----------------------------------------------------------

def test_a_countdown_under_many_threads_fires_once_and_counts_every_visit():
    """Each visit decides from its own ticket, never from the shared counter.

    Re-reading `state["fires"]` after taking it would let two threads that
    incremented back to back both read `n + 1` and both fire, and would let a
    lost increment move the firing visit somewhere the operator did not ask for.
    """
    n_threads = 200
    rule = countdown_rule(n=1)
    state = _new_state()
    barrier = threading.Barrier(n_threads)
    results = [None] * n_threads

    def one(i):
        def run():
            barrier.wait(timeout=JOIN_TIMEOUT)
            results[i] = _gate(rule, state, {"args": (), "kwargs": {}})
        return run

    run_threads([one(i) for i in range(n_threads)])

    assert sum(1 for r in results if r) == 1
    assert state["fires"] == n_threads


def test_the_key_expression_reads_the_ticket_of_its_own_visit():
    """`key: fires` is legal, so the ticket has to be published before the key.

    Evaluating the key against the shared counter instead would give a visit a
    key belonging to whichever visit incremented last, so two visits could
    collide on one key and one of them would be silently refused.
    """
    n_threads = 50
    rule = once_per_rule(key="fires")
    state = _new_state()
    barrier = threading.Barrier(n_threads)
    contexts = [{"args": (), "kwargs": {},
                 "sync": lambda: barrier.wait(timeout=JOIN_TIMEOUT)}
                for _ in range(n_threads)]

    results, errors = gate_in_threads(
        rule, state, contexts, code("sync() is not None or True"))

    assert errors == [None] * n_threads
    assert results == [True] * n_threads
    assert state["seen_keys"] == set(range(1, n_threads + 1))


# --- the reference and the constant ---------------------------------------

def test_the_documented_key_types_are_the_ones_the_code_accepts():
    """Prose that lists a constant has to break when the constant moves.

    docs/rules.md names the accepted types one by one. Without this, adding or
    removing a type leaves the reference quietly wrong, which is the failure
    mode a reference document can least afford.
    """
    import pathlib

    text = pathlib.Path(__file__).resolve().parents[1] / "docs" / "rules.md"
    section = text.read_text().split("### What `once_per` accepts as a key")[1]
    section = section.split("\n## ")[0]

    documented = {name for name in
                  ("None", "bool", "int", "float", "str", "bytes")
                  if "`{}`".format(name) in section}
    expected = {"None" if t is type(None) else t.__name__
                for t in _ONCE_PER_KEY_TYPES}
    assert documented == expected
    assert "tuple" in section
