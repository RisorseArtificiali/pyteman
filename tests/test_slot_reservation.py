# tests/test_slot_reservation.py
"""One install per slot at a time, across every Patcher in the process.

The defect these cover is not a torn write. It is a stale ownership read: the
decision to install is taken from a read of the slot, and `setattr` plus every
check before it run target code, so a second installer can land between the
decision and the write. Both calls then succeed on one slot, the loser's
dispatcher is overwritten while its Patcher still names the slot in `applied`,
and its rules stop firing with nothing reporting it.

Two shapes reach that window and both are here. One thread re-enters through an
import fired from inside `__setattr__`, which is how it happens in a real
process. Two threads reach it concurrently, which needs `Event`s: the second
thread has to arrive while the first is between its read and its write, and a
test that waits and hopes proves nothing on a green run.

The reservation covers the install write and nothing wider. The ownership
question asked earlier in `_patch`, from the read at the top of the loop, is
outside it, and `uninstall` is not synchronised at all.
"""
import contextlib
import gc
import sys
import threading
import types
import weakref

import pytest

from pyteman.patcher import (Patcher, SlotOwnershipError, _SLOT_RESERVATIONS,
                             install)
from pyteman.rules import Rule

MODNAME = "pyteman_reservation_victim"

# Read 3 of the slot in one `_patch` is the one the install decision is made
# from; reads 1 and 2 are the classification and the top-of-loop ownership
# question. Parking there is parking inside the window under test. Every test
# that parks also asserts it parked, because a probe that never reached the
# window prints the same clean result as one that found no defect.
_DECIDING_READ = 3

# No test may outlive its reservations. Left behind, one would make its slot
# unpatchable for the rest of the session, and the failure would surface in
# whatever test ran next rather than in the one that leaked.
@pytest.fixture(autouse=True)
def _registry_is_left_empty():
    yield
    assert _SLOT_RESERVATIONS == {}


def _rule(rid, module=MODNAME, symbol="f"):
    return Rule(id=rid, module=module, symbol=symbol, event="entry",
                action={"kind": "return_value", "value": 1},
                fire={"mode": "always"})


def original(a):
    return ("original", a)


@contextlib.contextmanager
def _victim(name, cls=types.ModuleType):
    """A module in `sys.modules` whose `f` is `original`, removed after.

    Written with `types.ModuleType.__setattr__` rather than `mod.f = ...`
    because these containers override `__setattr__` and the fixture must not
    be the thing that arms them.
    """
    mod = cls(name)
    types.ModuleType.__setattr__(mod, "f", original)
    sys.modules[name] = mod
    try:
        yield mod
    finally:
        del sys.modules[name]


def _import_driven_victim(name, catch):
    """A module that re-enters `_patch` on its own slot, through an import.

    The re-entry goes through `__import__` rather than through a direct
    `force_patch_module`, because that is the shape a real process produces:
    `install_hook` patches whatever `sys.modules` holds on EVERY import, so an
    ordinary import of an already-imported module re-enters on the same slot.
    """
    state = {"reentered": False, "inner": None}

    class Victim(types.ModuleType):
        def __setattr__(self, attr, value):
            if attr == "f" and not state["reentered"]:
                state["reentered"] = True
                if catch:
                    try:
                        __import__(name)
                    except SlotOwnershipError as exc:
                        state["inner"] = exc
                else:
                    __import__(name)
            types.ModuleType.__setattr__(self, attr, value)

    return Victim, state


def test_an_install_reached_through_an_import_cannot_take_a_slot_being_written():
    """The inner install is refused, and the refusal names the slot."""
    inner = install([_rule("inner")], log=None)
    outer = Patcher([_rule("outer")], None)
    Victim, state = _import_driven_victim(MODNAME, catch=True)
    try:
        with _victim(MODNAME, Victim) as mod:
            outer.force_patch_module(MODNAME)
            assert state["reentered"], "the import never re-entered _patch"
            assert isinstance(state["inner"], SlotOwnershipError)
            assert MODNAME + ":f" in str(state["inner"])
            # The inner call installed nothing, so there is one dispatcher on
            # the slot and one Patcher answering for it.
            assert inner.applied == []
            assert inner._wrapped == []
            assert outer.applied == [MODNAME + ":f"]
            assert mod.__dict__["f"] is not original
            assert outer.uninstall() == []
            assert mod.__dict__["f"] is original
    finally:
        inner.uninstall()


def test_a_container_that_catches_the_refusal_keeps_the_outer_patch():
    """Refusing the inner call does not decide the outer call's fate.

    The refusal travels out through the container's `__setattr__`, so what
    happens to the outer write is the container's to choose. One that swallows
    it and completes the store is left with a working patch.
    """
    inner = install([_rule("inner")], log=None)
    outer = Patcher([_rule("outer")], None)
    Victim, state = _import_driven_victim(MODNAME, catch=True)
    try:
        with _victim(MODNAME, Victim) as mod:
            outer.force_patch_module(MODNAME)
            assert state["inner"] is not None
            assert outer.applied == [MODNAME + ":f"]
            assert mod.__dict__["f"] is not original
            outer.uninstall()
    finally:
        inner.uninstall()


def test_a_refusal_the_container_lets_through_unwinds_the_outer_patch():
    """Fail closed: nobody installs, and the slot is left as it was found."""
    inner = install([_rule("inner")], log=None)
    outer = Patcher([_rule("outer")], None)
    Victim, state = _import_driven_victim(MODNAME, catch=False)
    try:
        with _victim(MODNAME, Victim) as mod:
            with pytest.raises(SlotOwnershipError):
                outer.force_patch_module(MODNAME)
            assert state["reentered"]
            assert outer.applied == []
            assert outer._wrapped == []
            assert inner.applied == []
            assert mod.__dict__["f"] is original
    finally:
        inner.uninstall()


class _ParkOnRead:
    """Parks one nominated thread inside a read of the slot.

    The park happens AFTER the value has been read, not before. Parking first
    would hand the parked thread whatever the other thread wrote while it
    waited, which is a fresh read and the opposite of the case under test.
    """

    def __init__(self, at=_DECIDING_READ):
        self.at = at
        self.parked = threading.Event()
        self.resume = threading.Event()
        # Set in `run`, and deliberately nobody until then: a read arriving on
        # the main thread before the worker exists is not a read this park is
        # counting, and counting it would shift the park onto the wrong one.
        self.thread = None
        self.reads = 0

    def victim(self):
        outer = self

        class Victim(types.ModuleType):
            def __getattribute__(self, attr):
                value = types.ModuleType.__getattribute__(self, attr)
                if (attr == "f"
                        and threading.current_thread() is outer.thread):
                    outer.reads += 1
                    if outer.reads == outer.at:
                        outer.parked.set()
                        outer.resume.wait(10)
                return value

        return Victim

    def run(self, patcher, module):
        """Patch `module` on a second thread, parked mid-decision."""
        failure = []

        def body():
            try:
                patcher.force_patch_module(module)
            except BaseException as exc:          # noqa: BLE001, reported
                failure.append(exc)

        self.thread = threading.Thread(target=body)
        self.thread.start()
        assert self.parked.wait(10), "the thread never reached the read"
        return failure

    def join(self):
        self.resume.set()
        self.thread.join(10)
        assert not self.thread.is_alive()


def test_a_second_patcher_cannot_install_while_a_read_decision_is_in_flight():
    """The window is closed at the read, not at the write.

    A reservation taken just before the `setattr` would leave this green for
    the wrong reason: by then the parked thread's decision is already stale,
    the other thread has installed AND released, and the registry is free.
    """
    park = _ParkOnRead()
    first, second = Patcher([_rule("a")], None), Patcher([_rule("b")], None)
    with _victim(MODNAME, park.victim()) as mod:
        first_failed = park.run(first, MODNAME)
        with pytest.raises(SlotOwnershipError):
            second.force_patch_module(MODNAME)
        park.join()

        assert first_failed == []
        assert first.applied == [MODNAME + ":f"]
        assert second.applied == []
        assert second._wrapped == []
        # One dispatcher, and it is the one whose Patcher can take it back.
        assert mod.__dict__["f"] is not original
        assert first.uninstall() == []
        assert mod.__dict__["f"] is original


def test_one_patcher_cannot_install_on_one_slot_from_two_threads():
    """Same owner is not the same call.

    Admitting an owner by identity alone lets a Patcher patching one slot from
    two threads through, and it lands exactly where two Patchers do: two ledger
    entries on one slot, the first naming a wrapper that is no longer live.
    """
    park = _ParkOnRead()
    patcher = Patcher([_rule("a")], None)
    with _victim(MODNAME, park.victim()) as mod:
        failed = park.run(patcher, MODNAME)
        with pytest.raises(SlotOwnershipError):
            patcher.force_patch_module(MODNAME)
        park.join()

        assert failed == []
        assert patcher.applied == [MODNAME + ":f"]
        assert len(patcher._wrapped) == 1
        assert patcher.uninstall() == []
        assert mod.__dict__["f"] is original


def test_the_same_patcher_may_reenter_on_its_own_thread():
    """The control for the test above, and it must not be refused.

    A nested call on this stack is this call continuing, not a competitor. If
    the reservation refused it, an import fired from inside `__setattr__` would
    break every patch that touches such a module.
    """
    patcher = Patcher([_rule("a")], None)
    state = {"reentered": False}

    class Victim(types.ModuleType):
        def __setattr__(self, attr, value):
            if attr == "f" and not state["reentered"]:
                state["reentered"] = True
                patcher.force_patch_module(MODNAME)
            types.ModuleType.__setattr__(self, attr, value)

    with _victim(MODNAME, Victim) as mod:
        patcher.force_patch_module(MODNAME)
        assert state["reentered"]
        assert mod.__dict__["f"] is not original
        assert patcher.uninstall() == []
        assert mod.__dict__["f"] is original


# ---------------------------------------------------------------------------
# TASK-123: a third party substituting the value between the read the
# decision rests on and the write. The reservation above refuses another
# PATCHER in that gap; a non-pyteman replacement was written over silently,
# and a later uninstall restored the stale original over it and reported a
# clean release. The identity comparison that would have caught it broke
# every descriptor-built point, so it is asked only where identity is
# answerable: a slot whose two reads agree.
# ---------------------------------------------------------------------------

def replacement(a):
    return ("replacement", a)


def _swap_victim(at, armed):
    """A module that stores a third-party callable, then answers it.

    Reads of `f` pass through until read `at`, which FIRST stores
    `replacement` in the module and THEN answers it. The patcher's decision
    was made from `original`; the slot now holds `replacement`, exactly what
    a program reassigning the attribute during dispatcher construction
    produces. With `armed` False the same container never swaps and is the
    control for the refusal: an ordinary install through an overridden
    `__getattribute__`.
    """
    reads = [0]

    class Victim(types.ModuleType):
        def __getattribute__(self, attr):
            value = types.ModuleType.__getattribute__(self, attr)
            if attr == "f":
                reads[0] += 1
                if armed and reads[0] == at:
                    types.ModuleType.__setattr__(self, "f", replacement)
                    value = replacement
            return value

    return Victim


def test_a_third_party_substitution_during_construction_is_refused():
    """The refusal names the slot, and the substitute stays where it landed.

    The refusal has to leave the replacement in place: overwriting it is the
    destruction the refusal exists to prevent, and restoring `original`, what
    a clean uninstall of the never-landed patch would do, is the same
    destruction one call later.
    """
    patcher = Patcher([_rule("a")], None)
    with _victim(MODNAME, _swap_victim(_DECIDING_READ, True)) as mod:
        with pytest.raises(SlotOwnershipError, match="was replaced while"):
            patcher.force_patch_module(MODNAME)
        assert mod.__dict__["f"] is replacement
        assert patcher.applied == []
        assert patcher._wrapped == []
        assert mod.f(1) == ("replacement", 1)


def test_the_swap_container_installs_when_nothing_substitutes():
    """The control: the same container with the swap disarmed must install.

    A refusal test passes for any error, so the container itself is proven
    benign here: an install through it lands, fires through the dispatcher,
    and uninstalls back to `original`.
    """
    victim = _swap_victim(_DECIDING_READ, False)
    patcher = Patcher([_rule("a")], None)
    with _victim(MODNAME, victim) as mod:
        patcher.force_patch_module(MODNAME)
        assert patcher.applied == [MODNAME + ":f"]
        assert mod.f(5) == 1
        assert patcher.uninstall() == []
        assert mod.__dict__["f"] is original


def test_a_slot_that_builds_a_fresh_value_per_read_is_not_refused():
    """The gate stays silent where identity is unanswerable.

    A descriptor-built point answers a NEW object on every read, so the pair
    of reads the stability question rests on never agrees and the value the
    decision was made from always differs from the settled one. Refusing
    there would break every instance point whose function lives on its
    class, which is what the ungated comparison did. The install wraps what
    it read, as it did before the gate existed.
    """

    def make_fresh():
        def fresh(a):
            return ("fresh", a)
        return fresh

    class FreshEachRead(types.ModuleType):
        def __getattribute__(self, attr):
            if attr == "f":
                return make_fresh()
            return types.ModuleType.__getattribute__(self, attr)

    patcher = Patcher([_rule("a")], None)
    with _victim(MODNAME, FreshEachRead) as mod:
        patcher.force_patch_module(MODNAME)
        assert patcher.applied == [MODNAME + ":f"]
        # The dispatcher sits in the module's own storage; the reads above
        # it keep answering fresh values, so the release below finds a
        # stranger and settles by dropping the entry, as it does for any
        # third-party replacement after install.
        assert mod.__dict__["f"] is not original
        assert patcher.uninstall() == []


# ---------------------------------------------------------------------------
# TASK-184: the caching-descriptor directions of the gate above. A descriptor
# that memoizes measures identity-stable, so it lands in the refusal branch,
# and its own rebuild between the decision read and the settled read is
# refused as if a third party had substituted the value: the conservative
# direction docs/rules.md promises. These pin both that refusal and its
# boundary: the stability is a MEASUREMENT, not a classification, and a slot
# rebuilt twice in a row measures unstable and disarms.
# ---------------------------------------------------------------------------

class _MemoDesc:
    """A memoizing data descriptor: rebuilds only when the generation moves.

    Models a cached_property whose cache is invalidated at a chosen read:
    reads before the bump answer the cached callable, the first read after
    it builds and caches a new one, later reads answer that. `bumps` is a
    list of read numbers; each one met moves the generation once more.
    Every built callable is recorded, and every write too, so a test can
    tell "the rebuilt value stayed" from "something wrote the stale
    original back over it", which behave identically.
    """

    def __init__(self, state):
        self.state = state

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        state = self.state
        state["reads"] += 1
        if state["reads"] in state["bumps"]:
            state["gen"] += 1
        gen = state["gen"]
        if obj.__dict__.get("gen") != gen:
            value = _fresh_callable()
            state["built"].append(value)
            obj.__dict__["gen"] = gen
            obj.__dict__["val"] = value
        return obj.__dict__["val"]

    def __set__(self, obj, value):
        self.state["sets"].append(value)
        obj.__dict__["gen"] = self.state["gen"]
        obj.__dict__["val"] = value


@contextlib.contextmanager
def _memo_victim(name, bumps):
    """A module whose `holder.handler` is a memoized descriptor-built point.

    Reads of `handler` are counted in the state the descriptor closes over,
    starting empty per victim, so a test's own reads participate in the same
    count the choreography reasons about. Writes and builds are recorded
    there too; see _MemoDesc for why the writes matter.
    """
    state = {"reads": 0, "gen": 0, "bumps": list(bumps),
             "built": [], "sets": []}

    class Holder:
        handler = _MemoDesc(state)

    with _victim(name) as mod:
        types.ModuleType.__setattr__(mod, "holder", Holder())
        yield mod, state


def _fresh_callable():
    def handler(a):
        return ("handler", a)
    return handler


MEMOMOD = "pyteman_reservation_memo_victim"


def test_a_cached_descriptor_rebuilt_before_the_settled_read_is_refused():
    """The docs' conservative direction, committed: refused, nothing applied.

    The generation moves at read 3, the settled read: reads 1 and 2 answer
    the cached original the dispatcher was built around, read 3 rebuilds a
    new callable, read 4 (the probe) answers it again, so the slot measures
    stable with a changed value and the gate refuses. No third party ever
    touched anything; the refusal is the documented price of asking identity
    of a slot that caches, and the rebuilt value stays exactly where it is.
    """
    patcher = Patcher([_rule("a", MEMOMOD, symbol="holder.handler")], None)
    with _memo_victim(MEMOMOD, bumps=[_DECIDING_READ]) as (mod, state):
        with pytest.raises(SlotOwnershipError, match="was replaced while"):
            patcher.force_patch_module(MEMOMOD)
        assert state["reads"] == _DECIDING_READ + 1
        # The rebuilt value stayed BY IDENTITY, not only by behavior: the
        # two are indistinguishable here, and a refusal path that wrote
        # the stale original back over the slot would pass a behavioral
        # assertion while committing the exact destruction the gate
        # exists to prevent.
        assert state["sets"] == []
        assert mod.holder.handler is state["built"][-1]
        assert len(state["built"]) == 2
        assert mod.holder.handler(1) == ("handler", 1)
        assert patcher.applied == []
        assert patcher._wrapped == []


def test_the_same_cached_descriptor_with_no_rebuild_installs():
    """The control: the memoized point with the cache held installs cleanly.

    A refusal test passes for any error, so the same descriptor with no
    generation move must install, fire through the dispatcher, and
    uninstall back to the cached original.
    """
    patcher = Patcher([_rule("a", MEMOMOD, symbol="holder.handler")], None)
    with _memo_victim(MEMOMOD, bumps=[]) as (mod, state):
        cached = mod.holder.handler
        patcher.force_patch_module(MEMOMOD)
        # One read of our own, then the patcher's three; the probe is never
        # spent on a slot whose settled value is the one it decided on.
        assert state["reads"] == _DECIDING_READ + 1
        assert patcher.applied == [MEMOMOD + ":holder.handler"]
        assert mod.holder.handler(9) == 1
        assert patcher.uninstall() == []
        assert mod.holder.handler is cached


def test_a_cached_descriptor_rebuilt_again_before_the_probe_disarms():
    """Stability is a measurement, not a classification of the attribute.

    The generation moves at read 3 AND read 4: the settled value is a new
    callable, and the probe reads yet another one, so the pair disagrees,
    the slot measures unstable, and the gate stands down. This is the
    boundary the refusal above must not cross: a slot that happens to
    rebuild between the two probe reads is answered like any other
    identity-unanswerable point, ownership-only, install proceeding.
    """
    patcher = Patcher([_rule("a", MEMOMOD, symbol="holder.handler")], None)
    with _memo_victim(MEMOMOD,
                      bumps=[_DECIDING_READ, _DECIDING_READ + 1]) as (mod, state):
        patcher.force_patch_module(MEMOMOD)
        assert state["reads"] == _DECIDING_READ + 1
        assert patcher.applied == [MEMOMOD + ":holder.handler"]
        assert mod.holder.handler(9) == 1
        assert patcher.uninstall() == []


@pytest.mark.parametrize("refusing_half", ["write", "read"])
def test_a_container_that_refuses_leaves_no_reservation_behind(refusing_half):
    """Every exit releases, including the ones the target forces.

    A reservation that outlives its call is worse than the defect it prevents:
    the registry is process-wide, so the slot would refuse every later install
    for the life of the process with no way to clear it.

    The refusing read has to be the DECIDING one. Refusing the first read
    instead aborts the call during slot resolution, before the reservation is
    taken, so that arm would assert an empty registry about a call that
    reserved nothing and would stay green with the release deleted. Measured:
    with the release loop removed the write arm fails and a first-read arm
    passes.
    """
    reads = [0]

    class Victim(types.ModuleType):
        def __getattribute__(self, attr):
            if attr == "f" and refusing_half == "read" and armed:
                reads[0] += 1
                if reads[0] == _DECIDING_READ:
                    raise RuntimeError("the deciding read itself refuses")
            return types.ModuleType.__getattribute__(self, attr)

        def __setattr__(self, attr, value):
            if attr == "f" and refusing_half == "write" and armed:
                raise RuntimeError("refuses, stores nothing")
            types.ModuleType.__setattr__(self, attr, value)

    armed = False
    patcher = Patcher([_rule("a")], None)
    with _victim(MODNAME, Victim) as mod:
        armed = True
        with pytest.raises(RuntimeError):
            patcher.force_patch_module(MODNAME)
        armed = False
        if refusing_half == "read":
            assert reads[0] == _DECIDING_READ, "never reached the deciding read"
        assert _SLOT_RESERVATIONS == {}
        assert patcher._wrapped == []
        assert mod.__dict__["f"] is original


def test_a_released_reservation_holds_no_reference_to_its_patcher():
    """The registry must not keep a Patcher, or a target, alive.

    While held, the entry names its owner, which is the only way a nested call
    can be recognised. Once released it must name nothing: a Patcher pinned
    here would keep its rules, its log and every original it wrapped alive for
    the rest of the process.
    """
    patcher = Patcher([_rule("a")], None)
    seen = weakref.ref(patcher)
    with _victim(MODNAME) as mod:
        patcher.force_patch_module(MODNAME)
        assert patcher.uninstall() == []
        assert mod.__dict__["f"] is original
    del patcher
    gc.collect()
    assert seen() is None
