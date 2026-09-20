# tests/test_unsupported_targets.py
"""A point that is not a supported callable is refused before it is mutated.

The README has excluded classmethod, staticmethod, property and plain data
attributes since the beginning, but a documentary warning is not enforcement:
the patcher wrapped them all. Two different failures came out of that, and a
fix that answers only one of them leaves the task half done.

A descriptor on a CLASS is destroyed permanently. `getattr` runs the protocol,
so the value the ledger records is the product of `__get__` and never the
object the namespace held; the undo writes that product back and reports a
clean release, so `Sub.open` binds a different class for the rest of the
process. A data attribute or a property is restored faithfully and is wrong
only WHILE patched: `f = 42` answers as a function and `C().prop` hands back a
bound dispatcher where a value was. The first group needs the refusal because
the undo cannot be trusted; the second needs it because the patch itself is the
damage. See TASK-6.
"""
import inspect
import sys
import types

import pytest

from pyteman.patcher import (_CLASS_NAMESPACE, Patcher, SuspendableTargetError,
                             UnsupportedTargetError, _unsupported_reason,
                             activate)
from internal_guard import counting_binding_signature
from pyteman.rules import Rule


def make_rule(symbol, rid="r", module="pyteman_unsupported_victim"):
    return Rule(id=rid, module=module, symbol=symbol, event="entry",
                action={"kind": "return_value", "value": 1},
                fire={"mode": "always"}, when=None)


def param_rule(symbol, rid="p", module="pyteman_unsupported_victim"):
    """A rule whose dispatcher needs the callable's real parameters.

    The binding path reads them from type dicts and base slot descriptors and
    runs nothing the target controls, so this is no longer a door through which
    target code runs between the checks and the write. The doors that remain
    are the `getattr` and the `setattr` on the patch path itself.
    """
    return Rule(id=rid, module=module, symbol=symbol, event="entry",
                action={"kind": "pragma", "name": "synchronous",
                        "value": "OFF", "target": "param:a"},
                fire={"mode": "always"}, when=None)


@pytest.fixture
def victim():
    """A module built per test, so a refusal cannot leak into the next one."""
    name = "pyteman_unsupported_victim"
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    try:
        yield mod
    finally:
        del sys.modules[name]


def _activate(mod, *rules):
    return activate(list(rules), log=None, modules=[mod.__name__])


# --------------------------------------------------------------------------
# The shapes AC1 names, refused on a class container.
# --------------------------------------------------------------------------

def test_a_classmethod_is_refused_and_survives_the_uninstall(victim):
    """AC2 and AC3 in one test, because the symptom outlives the removal.

    `uninstall()` is called after the refusal on purpose: it is callable with
    nothing installed, and running it is what proves the refusal left no ledger
    entry that a later undo would act on. The subclass binding is the assertion
    that survives, since it is wrong for the life of the process once the
    descriptor has been replaced by the method it produced.
    """
    class Db:
        @classmethod
        def open(cls, p):
            return f"open({cls.__name__},{p})"

    class Sub(Db):
        pass

    victim.Db = Db
    raw = vars(Db)["open"]
    p = Patcher([make_rule("Db.open")], None)
    with pytest.raises(UnsupportedTargetError) as excinfo:
        p._patch(victim, victim.__name__)
    assert "a classmethod" in str(excinfo.value), str(excinfo.value)
    assert vars(Db)["open"] is raw, "the descriptor object itself, not an equal one"
    assert Sub.open("p") == "open(Sub,p)"
    assert p.uninstall() == []
    assert vars(Db)["open"] is raw
    assert Sub.open("p") == "open(Sub,p)"


def test_a_staticmethod_on_a_class_is_refused(victim):
    """The corruption here is invisible through the class and permanent
    through an instance, which is why it went unnoticed long enough to need a
    task: `C.sm` answers correctly while `C().sm(p)` raises forever."""
    class C:
        @staticmethod
        def sm(p):
            return f"sm({p})"

    victim.C = C
    raw = vars(C)["sm"]
    with pytest.raises(UnsupportedTargetError) as excinfo:
        _activate(victim, make_rule("C.sm"))
    assert "a staticmethod" in str(excinfo.value), str(excinfo.value)
    assert vars(C)["sm"] is raw
    assert C().sm("p") == "sm(p)"


def test_a_property_on_a_class_is_refused_and_its_getter_never_runs(victim):
    """Read off the CLASS a property hands back the property object, so this
    refusal does not depend on running fget. The assertion is that it stayed
    that way: a gate that classified by reading the value would have executed
    target code to decide whether it was allowed to touch it."""
    ran = []

    class C:
        @property
        def prop(self):
            ran.append(1)
            return 7

    victim.C = C
    with pytest.raises(UnsupportedTargetError) as excinfo:
        _activate(victim, make_rule("C.prop"))
    assert "a property" in str(excinfo.value), str(excinfo.value)
    assert ran == [], "the gate ran the getter to decide"
    assert C().prop == 7


def test_a_data_attribute_on_a_class_is_refused_rather_than_wrapped(victim):
    """The original report: `f = 42` became a function and an entry
    return_value made the wrapped int look like a working rule."""
    class C:
        f = 42

    victim.C = C
    with pytest.raises(UnsupportedTargetError) as excinfo:
        _activate(victim, make_rule("C.f"))
    assert "a data attribute" in str(excinfo.value), str(excinfo.value)
    assert C.f == 42 and not callable(C.f)


def test_a_custom_descriptor_is_refused_without_its_get_being_invoked(victim):
    """A hostile `__get__` is the reason the classification is static.

    Unlike an ordinary property, a custom descriptor DOES run on class access,
    so a gate that read the attribute to classify it would hand the target a
    vote on its own inspection. This descriptor records every call; the
    assertion is that the list stays empty.
    """
    seen = []

    class Desc:
        def __get__(self, obj, cls=None):
            seen.append((obj, cls))
            return lambda: "product"

    class C:
        handler = Desc()

    victim.C = C
    raw = vars(C)["handler"]
    with pytest.raises(UnsupportedTargetError) as excinfo:
        _activate(victim, make_rule("C.handler"))
    assert "a custom descriptor" in str(excinfo.value), str(excinfo.value)
    assert seen == [], f"__get__ was invoked while deciding: {seen}"
    assert vars(C)["handler"] is raw


def test_an_inherited_classmethod_is_refused_on_the_subclass_too(victim):
    """Named on the subclass the write would CREATE the name there, so the
    undo deletes it and nothing is destroyed. It is refused anyway: AC1 is
    about not mutating an unsupported attribute, and while patched
    `Sub.cm` is a plain function where a bound classmethod was."""
    class Base:
        @classmethod
        def cm(cls):
            return cls.__name__

    class Sub(Base):
        pass

    victim.Sub = Sub
    with pytest.raises(UnsupportedTargetError) as excinfo:
        _activate(victim, make_rule("Sub.cm"))
    assert "a classmethod" in str(excinfo.value), str(excinfo.value)
    assert "cm" not in vars(Sub)
    assert Sub.cm() == "Sub"


def test_a_non_callable_module_attribute_is_refused(victim):
    """A module runs no descriptor protocol, so the static read is the whole
    story there and the only question left is whether the object can be
    called at all."""
    victim.moddata = 42
    with pytest.raises(UnsupportedTargetError) as excinfo:
        _activate(victim, make_rule("moddata"))
    assert "a data attribute" in str(excinfo.value), str(excinfo.value)
    assert victim.moddata == 42


# --------------------------------------------------------------------------
# Containers the static read deliberately says nothing about.
# --------------------------------------------------------------------------

def test_a_data_attribute_on_an_instance_is_refused_by_the_callable_check(victim):
    """An instance is not classified statically, because a property or a
    `__slots__` member reached through one is SUPPORTED and its value is only
    knowable by reading it. What still has to hold is that the value is a
    callable, and that question is asked of every container alike."""
    class Holder:
        def __init__(self):
            self.f = 42

    inst = Holder()
    victim.inst = inst
    with pytest.raises(UnsupportedTargetError) as excinfo:
        _activate(victim, make_rule("inst.f"))
    assert "not callable" in str(excinfo.value), str(excinfo.value)
    assert inst.f == 42


def test_a_property_on_an_instance_is_still_patched_and_restored(victim):
    """Positive control. The value a supported property yields is a callable
    and stays supported, so this is the case a container-blind descriptor
    refusal would have broken."""
    real = lambda a: a

    class Holder:
        def __init__(self):
            self._h = real

        @property
        def handler(self):
            return self._h

        @handler.setter
        def handler(self, v):
            self._h = v

    holder = Holder()
    victim.holder = holder
    p = Patcher([make_rule("holder.handler")], None)
    p._patch(victim, victim.__name__)
    assert holder.handler is not real, "the dispatcher was not installed"
    assert holder.handler(1) == 1
    assert p.uninstall() == []
    assert holder.handler is real


def test_a_slots_member_on_an_instance_is_still_patched_and_restored(victim):
    """Positive control for the other instance shape, whose undo goes through
    `setattr` and not `delattr`: the name is held by a data descriptor on the
    type and never appears in the instance namespace."""
    real = lambda a: a

    class Svc:
        __slots__ = ("handler",)

    svc = Svc()
    svc.handler = real
    victim.svc = svc
    p = Patcher([make_rule("svc.handler")], None)
    p._patch(victim, victim.__name__)
    assert svc.handler is not real
    assert p.uninstall() == []
    assert svc.handler is real
    assert "handler" not in getattr(svc, "__dict__", {})


def test_a_module_level_staticmethod_still_reaches_the_suspendable_refusal(victim):
    """The regression this gate could plausibly cause, asserted directly.

    A module runs no descriptor protocol, so `handler = staticmethod(coro)` at
    module scope is handed to the gates as the descriptor object itself, and it
    is CALLABLE. It must stay allowed by the static classifier so that the
    coroutine refusal, which is a different and older check, is still the one
    that speaks. See TASK-3 and TASK-164.
    """
    async def coro(a):
        return a

    victim.handler = staticmethod(coro)
    before = victim.handler
    with pytest.raises(SuspendableTargetError) as excinfo:
        _activate(victim, make_rule("handler"))
    assert "a coroutine function" in str(excinfo.value), str(excinfo.value)
    assert victim.handler is before


def test_a_supported_function_keeps_its_binding_and_signature(victim):
    """Positive control for AC1's other half: the supported shapes go on
    working, and the dispatcher keeps the signature a `param:` target needs to
    bind by name."""
    class C:
        def meth(self, a, b=2):
            return (a, b)

    victim.C = C
    before = inspect.signature(C.meth)
    p = Patcher([make_rule("C.meth")], None)
    p._patch(victim, victim.__name__)
    assert inspect.signature(C.meth) == before
    assert C().meth(1) == 1, "the entry action's value"
    assert p.uninstall() == []
    assert C().meth(1) == (1, 2)


# --------------------------------------------------------------------------
# The checks around the write.
# --------------------------------------------------------------------------

def test_a_shape_that_appears_while_the_dispatcher_is_built_is_refused(victim):
    """The recheck exists for a real door, not a hypothetical one.

    DECLARED INTERNAL-GUARD TEST. The door this recheck guards is the gap
    between the ownership gate and the write, and the suite used to reach it
    with a `__signature__` property, because the binding path called
    `inspect.signature` and so ran code the target owned. It does not any more:
    the parameters are read from type dicts and base slot descriptors, and no
    ordinary target can stand in that gap.

    The gap itself is NOT closed, and that is why this test is kept rather than
    deleted. `setattr` on the way out is still target code, a metaclass
    `__setattr__` or a `ModuleType` subclass runs on the write, and other
    threads exist. What is gone is the suite's way of standing there on demand,
    so the wrapper below supplies one. It delegates in full and substitutes
    nothing, so production computes exactly the answer it would have computed
    alone; what the wrapper adds is a place to stand.

    Only a change of SHAPE is caught, and only one performed before the write;
    the general identity question in that gap is TASK-123 and stays open.
    """
    swapped = []

    class Callable:
        def __call__(self, a):
            return a

    class C:
        f = Callable()

    def swap():
        swapped.append(1)
        C.f = classmethod(lambda cls: "cm")

    victim.C = C
    with counting_binding_signature(hook=swap) as calls:
        with pytest.raises(UnsupportedTargetError) as excinfo:
            _activate(victim, param_rule("C.f"))
    # ARRIVAL: the window really opened, and it opened INSIDE the build rather
    # than before or after it, which is the only placement this recheck is
    # about.
    assert len(calls) == 1, "the build never reached the read"
    assert swapped == [1], "the window never opened, so this proves nothing"
    assert "a classmethod" in str(excinfo.value), str(excinfo.value)
    assert type(vars(C)["f"]) is classmethod, "the write landed anyway"


def test_the_refusal_rolls_back_a_slot_this_call_already_wrapped(victim):
    """Refusing before the setattr is what buys atomicity, so the test is
    about the OTHER slot: the one this same call had already installed."""
    class C:
        @classmethod
        def cm(cls):
            return "cm"

    real = lambda a: a
    victim.ok = real
    victim.C = C
    with pytest.raises(UnsupportedTargetError):
        _activate(victim, make_rule("ok", rid="first"),
                  make_rule("C.cm", rid="second"))
    assert victim.ok is real, "the earlier wrap was not rolled back"


def test_a_namespace_that_cannot_be_read_is_refused_with_its_cause(monkeypatch):
    """An introspection failure is not the same answer as an absent name.

    A name that is not there is SKIPPED, which is a documented promise. A
    namespace this check cannot read is a different fact: it means the shape
    was never established, and allowing the write on that basis would be
    guessing in the destructive direction. The cause travels with the refusal
    so the operator sees what actually failed.
    """
    import pyteman.patcher as patcher

    boom = RuntimeError("namespace unavailable")

    def raising(_cls):
        raise boom

    monkeypatch.setattr(patcher, "_CLASS_NAMESPACE", raising)

    class C:
        def meth(self):
            return 1

    reason, cause = _unsupported_reason(C, "meth")
    assert reason is not None and "could not be read" in reason, reason
    assert cause is boom


def test_a_supported_target_answers_with_no_reason():
    """The helper's negative side, so the tests above cannot pass by refusing
    everything."""
    class C:
        def meth(self):
            return 1

    assert _unsupported_reason(C, "meth") == (None, None)
    assert _unsupported_reason(int, "bit_length") == (None, None)
    assert _unsupported_reason(types.FunctionType, "__call__") == (None, None)


class _FiresOnWrite(type):
    """A metaclass that runs target code when an attribute of the class is set.

    The vector the suite used here was a `__signature__` property, which the
    binding path no longer reads. A metaclass `__setattr__` is a different
    live one, named as such by `patcher.py`, and it reaches the SAME window:
    pass 2 writes an earlier slot's dispatcher, that write runs this, and this
    runs while a slot pass 1 already classified has not been reached yet.

    It is armed explicitly, so building the class and populating it in the test
    body cannot fire it before the hook is installed.
    """

    def __new__(mcls, name, bases, ns):
        cls = super().__new__(mcls, name, bases, ns)
        type.__setattr__(cls, "_on_write", None)
        return cls

    def __setattr__(cls, name, value):
        super().__setattr__(name, value)
        hook = type.__getattribute__(cls, "_on_write")
        if hook is not None and name != "_on_write":
            type.__setattr__(cls, "_on_write", None)  # one shot
            hook()


def test_a_shape_that_appears_between_the_two_passes_is_refused_unread(victim):
    """The second static check earns its place by what it does NOT do.

    Pass 1 classified every slot before any dispatcher existed, and pass 2 runs
    target code on its way through: the `setattr` that publishes an earlier
    slot's dispatcher is not inert, and here it drops a hostile descriptor on
    the class slot this loop has not reached yet. A refusal at the write would
    still stop the damage, but pass 2 READS the attribute on its way there, and
    reading it is what hands the descriptor control. Checking before that read
    is what keeps `__get__` uninvoked, which is what the empty list below
    asserts.
    """
    seen = []

    class Desc:
        def __get__(self, obj, cls=None):
            seen.append((obj, cls))
            return lambda: "product"

    class C:
        def target(self):
            return "target"

    class Holder(metaclass=_FiresOnWrite):
        def first(self):
            return "first"

    swapped = []

    def swap():
        swapped.append(1)
        C.target = Desc()

    victim.Holder = Holder
    victim.C = C
    Holder._on_write = swap

    with pytest.raises(UnsupportedTargetError) as excinfo:
        _activate(victim, make_rule("Holder.first", rid="first"),
                  make_rule("C.target", rid="second"))
    # ARRIVAL: the window really opened, before any claim about the refusal.
    assert swapped == [1], "the window never opened, so this proves nothing"
    assert "a custom descriptor" in str(excinfo.value), str(excinfo.value)
    assert seen == [], f"the slot was read on the way to the refusal: {seen}"


# --------------------------------------------------------------------------
# The classification asks no questions the target can answer.
# --------------------------------------------------------------------------

class _CountingMeta(type):
    """A metaclass whose `__eq__` answers truthily and records being asked.

    This is not a contrived shape. A class that overloads comparison to build
    expressions, the ORM and query-DSL pattern, has exactly this metaclass
    behaviour, and it answers something truthy to every comparison because the
    expression object it returns is truthy. `x in some_tuple` is
    `any(x is e or x == e)`, so membership alone is enough to consult it.
    """

    invocations = []

    def __eq__(cls, other):
        _CountingMeta.invocations.append(getattr(other, "__name__", other))
        return True

    def __hash__(cls):
        return id(cls)


@pytest.fixture
def equality_calls():
    _CountingMeta.invocations.clear()
    yield _CountingMeta.invocations
    _CountingMeta.invocations.clear()


def test_a_callable_whose_metaclass_answers_every_comparison_is_still_admitted(
        victim, equality_calls):
    """The false POSITIVE half: a working setup must not start being refused.

    Classified with `in`, this object matches the first label it is compared
    against and a plain callable is reported as "a classmethod", so a program
    that instruments a DSL object would break on upgrade with a refusal naming
    a shape it never used.
    """
    class Truthy(metaclass=_CountingMeta):
        def __call__(self, a):
            return a

    class C:
        handler = Truthy()

    victim.C = C
    assert _unsupported_reason(C, "handler") == (None, None)
    assert equality_calls == [], f"the target was consulted: {equality_calls}"


def test_a_descriptor_that_claims_to_be_a_builtin_is_refused_before_it_runs(
        victim, equality_calls):
    """The false NEGATIVE half, which is the one that destroys a program.

    Answering truthily to `kind is MemberDescriptorType`, asked as membership,
    let this object through the allowlist of builtin self-returning
    descriptors. It is then patched like an ordinary callable, and the
    uninstall writes the wrapper back over the descriptor: the exact
    permanent corruption this whole change exists to prevent, reached by a
    target that simply answered a comparison.
    """
    touched = []

    class Hostile(metaclass=_CountingMeta):
        def __get__(self, obj, cls=None):
            touched.append("get")
            return lambda: "product"

        def __set__(self, obj, value):
            touched.append("set")

    class C:
        handler = Hostile()

    victim.C = C
    raw = _CLASS_NAMESPACE(C)["handler"]
    with pytest.raises(UnsupportedTargetError) as excinfo:
        _activate(victim, make_rule("C.handler"))
    assert "a custom descriptor" in str(excinfo.value), str(excinfo.value)
    assert equality_calls == [], f"the target was consulted: {equality_calls}"
    assert touched == [], f"the descriptor ran: {touched}"
    assert _CLASS_NAMESPACE(C)["handler"] is raw


def test_an_ordinary_hostile_descriptor_is_refused_identically(victim):
    """Control for the test above: the refusal has to come from the SHAPE.

    Without this, a refusal produced by some accident of the counting
    metaclass would look like the guarantee being claimed.
    """
    class Hostile:
        def __get__(self, obj, cls=None):
            raise AssertionError("the getter ran")

    class C:
        handler = Hostile()

    victim.C = C
    with pytest.raises(UnsupportedTargetError) as excinfo:
        _activate(victim, make_rule("C.handler"))
    assert "a custom descriptor" in str(excinfo.value), str(excinfo.value)


def test_the_container_kind_is_decided_without_consulting_the_container(
        equality_calls):
    """The other two comparison sites, which ask what the CONTAINER is.

    `type in mro` and `ModuleType in mro` are membership tests over the
    container's own metaclass mro, so the container gets the same vote the
    stored object was getting. Both containers here answer truthily to
    everything; both must be classified correctly anyway, and in silence.
    """
    class C(metaclass=_CountingMeta):
        def meth(self):
            return 1

    assert _unsupported_reason(C, "meth") == (None, None)
    assert _unsupported_reason(C, "absent") == (None, None)

    class LoudModule(types.ModuleType, metaclass=_CountingMeta):
        pass

    mod = LoudModule("pyteman_loud_module")
    mod.data = 42
    reason, _cause = _unsupported_reason(mod, "data")
    assert reason is not None and "a data attribute" in reason, reason
    assert equality_calls == [], f"the container was consulted: {equality_calls}"
