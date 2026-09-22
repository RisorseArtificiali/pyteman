# tests/test_binding_reach.py
"""What the `param:` binding reaches, and what it deliberately misses.

The redesign derives a callable's parameters from CODE: `__code__` on the
function at the bottom of the layer walk, type-dict reads and real slot
descriptors on the way down. It never calls `inspect.signature` on the target
and never reads `__signature__`, `__wrapped__`, `__partialmethod__` or
`__text_signature__`. This file is the executable form of that claim, and it
has three jobs that a single "it works" test cannot do together.

First, REACH. A table of shapes, each asserted to bind a specific parameter
list or to be deliberately unavailable. A refusal is a RESULT here, not a gap:
the design prefers a clean miss over a guess, so the unavailable rows are
asserted just as hard as the supported ones.

Second, WITHDRAWAL. The old design trusted an undecorated `__signature__`, and
that trust is withdrawn. Withdrawal is only observable as a PAIR: a real shape
that binds, and a decoy of the same shape whose metadata says something else
and which must now miss. A test that only asserts the real one passes under
both designs and proves nothing about the change.

Third, END TO END. The reach table calls the binding helper directly, which is
precise but proves nothing about whether an operator's rule reaches it. The
last section drives five attack vectors through the real `install()` hook, a
real import, a real call and a real sqlite3 connection, and reads the result
off the firing log rather than off any patcher internal.
"""
import functools
import inspect
import json
import sqlite3
import sys
import types

import pytest

from pyteman.patcher import (_BINDING_DEPTH, _binding_signature,
                             _PREBOUND_SHAPE, _TOO_DEEP, install)
from pyteman.firing import open_log
from pyteman.rules import Rule


def binds(obj):
    """The parameter list as text, or None when the binding is unavailable.

    Text rather than a Signature because the assertions below are about which
    parameters a caller can name, and comparing rendered forms keeps the table
    readable without weakening it: a rendered `(x)` cannot be produced by an
    empty or defaulted signature.
    """
    sig, reason = _binding_signature(obj)
    return None if sig is None else str(sig)


def reason_for(obj):
    return _binding_signature(obj)[1]


# --------------------------------------------------------------------------
# The reach table: shapes that bind.
# --------------------------------------------------------------------------

def plain_function(a, b):
    return a, b


def variadic_function(*args):
    return args


class PlainCall:
    def __call__(self, x):
        return "real"


class StaticCall:
    @staticmethod
    def __call__(x):
        return "real"


class ClassmethodCall:
    @classmethod
    def __call__(cls, x):
        return "real"


class PlainVariadic:
    def __call__(self, *args):
        return "real"


class StaticVariadic:
    @staticmethod
    def __call__(*args):
        return "real"


class ClassmethodVariadic:
    @classmethod
    def __call__(cls, *args):
        return "real"


class Receiver:
    def method(self, a, b):
        return a, b


class PlainInit:
    def __init__(self, a, b):
        self.a, self.b = a, b


class NoInit:
    pass


SUPPORTED = [
    ("plain function", plain_function, "(a, b)"),
    ("bound method", Receiver().method, "(a, b)"),
    ("instance, plain __call__", PlainCall(), "(x)"),
    ("instance, staticmethod __call__", StaticCall(), "(x)"),
    ("instance, classmethod __call__", ClassmethodCall(), "(x)"),
    ("instance, plain variadic __call__", PlainVariadic(), "(*args)"),
    ("instance, static variadic __call__", StaticVariadic(), "(*args)"),
    ("instance, classmethod variadic __call__", ClassmethodVariadic(),
     "(*args)"),
    ("class with __init__", PlainInit, "(a, b)"),
    ("class with no __init__", NoInit, "()"),
    ("partial over a function", functools.partial(plain_function, 1), "(b)"),
]


@pytest.mark.parametrize("label,obj,expected",
                         SUPPORTED, ids=[row[0] for row in SUPPORTED])
def test_the_supported_shapes_bind_the_parameters_a_caller_passes(
        label, obj, expected):
    """Each supported shape binds exactly the names a caller may use.

    The variadic rows are the load-bearing ones and are not padding. A receiver
    is ABSORBED by a leading `*args` rather than consuming a named parameter,
    so a blind "drop the first parameter" would shift every later attribution
    one place left and silently mis-name arguments. Asserting `(*args)` for all
    three receiver kinds is what pins the absorption branch.

    The classmethod row is a RESTORATION of behaviour published at b769bf9,
    not a widening introduced here: a classmethod `__call__` receives the class
    rather than the instance, so exactly one receiver is dropped and `(x)` is
    what the caller passes.
    """
    assert binds(obj) == expected


def test_a_bound_method_really_is_callable_with_what_it_binds():
    """The table is a claim about calls, so at least one row is CALLED.

    Without this the whole table could be a self-consistent description of a
    walk that has drifted from what Python actually does at the call site.
    """
    receiver = Receiver()
    assert binds(receiver.method) == "(a, b)"
    assert receiver.method(1, 2) == (1, 2)
    assert str(inspect.signature(receiver.method)) == "(a, b)"


# --------------------------------------------------------------------------
# The reach table: shapes that deliberately miss.
# --------------------------------------------------------------------------

class _OwnGet:
    """A descriptor subclass overriding `__get__`.

    Resolving this would mean modelling an arbitrary descriptor protocol, which
    is a framework the design refuses to carry, so it is unavailable BY
    DECISION rather than by oversight.
    """

    def __init__(self, func):
        self.func = func

    def __get__(self, obj, owner):
        return lambda x: self.func(obj, x)


class DescriptorCall:
    __call__ = _OwnGet(lambda self, x: "real")


class _Forward:
    """Plain and non-descriptor: as `__call__` it receives only the args."""

    def __call__(self, x):
        return "real"


class NestedInstanceCall:
    """`__call__` is an INSTANCE of another class, not a function.

    Genuinely callable, and genuinely unavailable: the parameters belong to the
    forwarder's own `__call__`, one layer further out than this walk attributes
    them to, so the design refuses rather than guessing.
    """

    __call__ = _Forward()


class CustomMeta(type):
    pass


class CustomMetaclassClass(metaclass=CustomMeta):
    def __init__(self, a):
        self.a = a


class OwnNew:
    def __new__(cls, *args, **kwargs):
        return super().__new__(cls)

    def __init__(self, a):
        self.a = a


UNAVAILABLE = [
    ("builtin function", len),
    ("method descriptor", str.upper),
    ("non-callable object", object()),
    ("__call__ via a __get__-overriding descriptor", DescriptorCall()),
    ("__call__ that is itself an instance", NestedInstanceCall()),
    ("class with a custom metaclass", CustomMetaclassClass),
    ("class with its own __new__", OwnNew),
]


@pytest.mark.parametrize("label,obj",
                         UNAVAILABLE, ids=[row[0] for row in UNAVAILABLE])
def test_the_unavailable_shapes_miss_cleanly_rather_than_guessing(label, obj):
    """Unavailable is an answer, and it carries a reason rather than a crash.

    Asserted as hard as the supported table above. A shape that silently bound
    SOMETHING here would be worse than one that refuses: a `param:` target
    would resolve against parameters that are not the ones the call receives,
    and the operator would be told a rule reached an argument it never saw.
    """
    sig, reason = _binding_signature(obj)
    assert sig is None, f"{label} bound {sig} instead of refusing"
    assert reason is not None, f"{label} refused without saying why"


def test_a_genuinely_unavailable_shape_is_still_a_working_callable():
    """The refusals above are about ATTRIBUTION, not about brokenness.

    `NestedInstanceCall` really answers a call. Without this the unavailable
    table could be a list of objects that refuse for the boring reason that
    they do not work at all, which would make it vacuous.
    """
    obj = NestedInstanceCall()
    assert obj(5) == "real"
    assert binds(obj) is None


def test_a_walk_that_never_bottoms_out_is_refused_as_too_deep():
    """The layer walk is bounded, and the bound has its own reason.

    Distinguished from `_UNAVAILABLE` because the two say different things to
    an operator: one means "this shape is not modelled", the other means "this
    shape nests deeper than anything worth modelling".
    """
    # `types.MethodType` binds ANY callable, including another bound method,
    # so each wrap really is one more layer for the walk to follow. That is
    # what this test needs and all it claims; it says nothing about which other
    # shapes could or could not reach the bound.
    layer = variadic_function
    for _ in range(_BINDING_DEPTH + 3):
        layer = types.MethodType(layer, object())
    assert reason_for(layer) is _TOO_DEEP

    # The control that makes the refusal mean something: the SAME shape, three
    # layers instead of thirty-five, resolves. So the refusal above is the
    # bound biting, not this shape being unmodelled, which is the distinction
    # `_TOO_DEEP` exists to draw.
    shallow = variadic_function
    for _ in range(3):
        shallow = types.MethodType(shallow, object())
    assert binds(shallow) == "(*args)"


# --------------------------------------------------------------------------
# Withdrawal: metadata a target declares no longer steers the binding.
# --------------------------------------------------------------------------

def _decorated_real(a, b):
    return a, b


def _wrapper(*args, **kwargs):
    """A decorator's wrapper: what it RECEIVES is `(*args, **kwargs)`."""
    return _decorated_real(*args, **kwargs)


functools.update_wrapper(_wrapper, _decorated_real)


class DeclaresASignature:
    """Ordinary parameters in code, a DIFFERENT story in `__signature__`."""

    def __call__(self, real_name):
        return "real"

    __signature__ = inspect.Signature(
        [inspect.Parameter("decoy_name",
                           inspect.Parameter.POSITIONAL_OR_KEYWORD)])


class DeclaresATextSignature:
    def __call__(self, real_name):
        return "real"

    __text_signature__ = "($self, decoy_name)"


def test_an_undecorated_signature_attribute_no_longer_steers_the_binding():
    """The withdrawal, asserted as a PAIR so it cannot pass under both designs.

    The old design trusted `__signature__` when nothing had decorated the
    callable, on the theory that an object describing itself is describing
    itself honestly. It is not a safe theory: the attribute is ordinary target
    data, and a wrong one silently re-points every `param:` rule on the slot.

    The control is the same shape WITHOUT the attribute. It binds
    `(real_name)`, so the decoy's failure below cannot be explained by this
    shape being unreachable in general.
    """
    class SameShape:
        def __call__(self, real_name):
            return "real"

    assert binds(SameShape()) == "(real_name)"
    # And the decoy binds the CODE's name, not the declared one.
    assert binds(DeclaresASignature()) == "(real_name)"
    assert "decoy_name" not in binds(DeclaresASignature())


def test_the_signature_attribute_is_not_even_read():
    """Stronger than "ignored": the getter never runs.

    Ignoring the answer still means asking the question, and asking runs
    target code at the exact point the redesign exists to keep clear. So the
    decoy here is a PROPERTY that records its own invocation, and the
    assertion is on the counter rather than on the parameters. A design that
    read the attribute and then discarded it would pass the test above and
    fail this one.
    """
    reads = []

    class WatchesTheRead:
        def __call__(self, real_name):
            return "real"

        @property
        def __signature__(self):
            reads.append(1)
            return inspect.Signature([])

    obj = WatchesTheRead()
    assert binds(obj) == "(real_name)"
    assert reads == [], "__signature__ was read on the binding path"


def test_a_declared_text_signature_does_not_steer_the_binding_either():
    """`__text_signature__` is the C-level sibling of the same trust.

    Included because closing one door and leaving the other open would leave
    the withdrawal half done, and the two are read by different branches of
    `inspect`.
    """
    assert binds(DeclaresATextSignature()) == "(real_name)"


def test_a_decorated_wrapper_reports_what_it_receives_not_what_it_wraps():
    """`__wrapped__` is withdrawn too, and this is the case FOR doing so.

    `functools.wraps` sets `__wrapped__`, and `inspect.signature` follows it,
    so the old path reported `(a, b)` for a wrapper that actually receives
    `(*args, **kwargs)`. That is a pleasant fiction everywhere except here: the
    dispatcher binds the arguments of the call that ARRIVES, and the arriving
    call lands in the wrapper. Reporting the wrapped function's names would
    make `param:a` resolve against a parameter the wrapper never has.

    So the fiction is the bug and the blunt answer is the fix. The assertion is
    a pair: what the walk says, and what `inspect` says, shown to differ on
    purpose.
    """
    assert binds(_wrapper) == "(*args, **kwargs)"
    assert str(inspect.signature(_wrapper)) == "(a, b)"
    assert _wrapper.__wrapped__ is _decorated_real


# --------------------------------------------------------------------------
# Parameter kinds.
# --------------------------------------------------------------------------

def positional_only(a, b, /, c):
    return a, b, c


def keyword_only(a, *, b, c=3):
    return a, b, c


def every_kind(a, /, b, *args, c, **kwargs):
    return a, b, args, c, kwargs


class KindsOnCall:
    def __call__(self, a, /, b, *args, c, **kwargs):
        return "real"


KINDS = [
    ("positional-only", positional_only, "(a, b, /, c)"),
    ("keyword-only, default not carried", keyword_only, "(a, *, b, c)"),
    ("every kind at once", every_kind, "(a, /, b, *args, c, **kwargs)"),
]


@pytest.mark.parametrize("label,func,expected",
                         KINDS, ids=[row[0] for row in KINDS])
def test_every_parameter_kind_survives_the_walk_in_order(label, func,
                                                         expected):
    """Kinds and order are preserved, because `param:` binding depends on both.

    `Signature.bind_partial` is what resolves a `param:` target at firing time,
    and it refuses a parameter list whose kinds are out of order. A walk that
    preserved names but lost kinds would produce a signature that raises on
    every call rather than one that misses cleanly.
    """
    assert binds(func) == expected


def test_a_default_is_not_carried_and_that_changes_no_resolution():
    """Defaults are deliberately not read, and the omission is proved harmless.

    `_code_parameters` reads `__code__` and nothing else, so `c=3` arrives as a
    bare `c`. Asserted rather than glossed, and then discharged: what resolves
    a `param:` target is `bind_partial`, which never applies defaults, so the
    arguments dict is identical either way. A default that HAD been carried
    would be the dangerous direction, because `param:c` would then resolve to a
    value this call never passed.
    """
    sig = _binding_signature(keyword_only)[0]
    assert str(sig) == "(a, *, b, c)"
    assert sig.parameters["c"].default is inspect.Parameter.empty

    declared = inspect.signature(keyword_only)
    assert declared.parameters["c"].default == 3
    # The property that actually matters, shown on BOTH signatures.
    assert sig.bind_partial(1, b=2).arguments \
        == declared.bind_partial(1, b=2).arguments == {"a": 1, "b": 2}


def test_dropping_a_receiver_leaves_the_remaining_kinds_intact():
    """The receiver drop is the operation most likely to disturb the order.

    A positional-only receiver is removed from the front of a list that still
    contains positional-only, variadic, keyword-only and var-keyword entries,
    and the result must still be a constructible signature in canonical order.
    """
    bound = binds(KindsOnCall())
    assert bound == "(a, /, b, *args, c, **kwargs)"
    # Constructible and usable, not merely rendered: this is the property
    # `resolve_target` depends on at firing time.
    sig = _binding_signature(KindsOnCall())[0]
    assert sig.bind_partial(1, 2, c=3).arguments["c"] == 3


def test_a_positional_only_receiver_is_dropped_rather_than_renamed():
    """The `self` of a positional-only method is gone, not turned into `a`.

    Asserted directly because an off-by-one in the drop is invisible in a
    two-parameter shape: every name would still appear, just attached to the
    wrong argument.
    """
    class PositionalOnlyReceiver:
        def __call__(self, x, /, y):
            return "real"

        def method(self, x, /, y):
            return x, y

    assert binds(PositionalOnlyReceiver()) == "(x, /, y)"
    assert binds(PositionalOnlyReceiver().method) == "(x, /, y)"


# --------------------------------------------------------------------------
# functools.partial: pre-binding, overriding, and Placeholder.
# --------------------------------------------------------------------------

def test_a_partial_consumes_the_parameters_it_pre_bound():
    """Pre-bound positionals disappear; pre-bound keywords gain a default.

    The two are not the same operation and a walk that treated them alike
    would either lose a nameable parameter or keep an unpassable one.
    """
    assert binds(functools.partial(every_kind, 1)) \
        == "(b, *args, c, **kwargs)"
    # A pre-bound KEYWORD stays nameable and becomes keyword-only, because the
    # caller may still override it. It does not gain a default: see the
    # declared limitation below for what that costs.
    assert binds(functools.partial(plain_function, b=2)) == "(a, *, b)"


def test_a_keyword_prebound_by_a_partial_is_nameable_but_unresolvable():
    """DECLARED LIMITATION, asserted so it cannot regress unnoticed.

    `functools.partial(f, b=2)` called as `obj(1)` really does reach `f` with
    `b=2`, but the binding carries no default, so `bind_partial(1)` yields only
    `a` and a `param:b` rule MISSES on a call whose effective value for `b` is
    2. That is the decided behaviour, not a defect. `param:` resolves what the
    CALLER passed in this firing, and defaults are never applied; a value the
    partial supplied is not a value this call passed, so the miss is accurate.
    Asserted here so the policy cannot drift into its opposite unnoticed.

    The direction that would be WORSE is asserted too: the walk must not hand
    back a default it invented, because then `param:b` would resolve to a value
    on calls that never passed one.
    """
    obj = functools.partial(plain_function, b=2)
    assert obj(1) == (1, 2), "the pre-bound value really does reach the call"

    sig = _binding_signature(obj)[0]
    assert sig.parameters["b"].default is inspect.Parameter.empty
    assert "b" not in sig.bind_partial(1).arguments, \
        "the miss is the documented behaviour"
    # An explicitly passed override still resolves, so the parameter is
    # nameable and this is a miss rather than a dead name.
    assert sig.bind_partial(1, b=9).arguments == {"a": 1, "b": 9}


def test_a_partial_over_a_bound_method_applies_the_layers_inward_out():
    """Order of operations, which is the whole reason the walk defers.

    The receiver must be dropped BEFORE the partial's pre-binding is applied,
    because the partial pre-binds against the parameters the receiver already
    left behind. Applying them in walk order instead would consume `self` as
    the pre-bound argument and leave `a` nameable when the caller can no longer
    pass it.
    """
    receiver = Receiver()
    assert binds(functools.partial(receiver.method, 1)) == "(b)"
    assert functools.partial(receiver.method, 1)(2) == (1, 2)


class PartialSubclassPlain(functools.partial):
    """A subclass that does NOT redefine `__call__`: reduces to its func."""


class PartialSubclassOverriding(functools.partial):
    """A subclass that DOES redefine `__call__`.

    What it does with the pre-bound arguments is its own business, so the walk
    must stop treating it as a partial and attribute the parameters to this
    `__call__` instead.
    """

    def __call__(self, only_mine):
        return "real"


def test_a_partial_subclass_that_keeps_call_still_reduces_to_its_func():
    """The control for the override test below.

    Without it, "the overriding subclass binds its own parameters" would be
    consistent with the walk refusing every partial subclass outright.
    """
    assert binds(PartialSubclassPlain(plain_function, 1)) == "(b)"


def test_a_partial_subclass_that_overrides_call_binds_its_own_parameters():
    """The pre-bound arguments stop being an attribution fact.

    A subclass that redefines `__call__` may ignore `args` entirely, reorder
    them, or use them for something unrelated. Continuing to subtract them from
    the wrapped function's parameters would report a signature nothing accepts.
    """
    obj = PartialSubclassOverriding(plain_function, 1)
    assert binds(obj) == "(only_mine)"


def test_a_partial_reads_its_own_args_through_the_real_slots():
    """A subclass cannot steer the pre-binding by redefining `args`/`func`.

    These are read through descriptors taken off the real `functools.partial`
    type, so a property of the same name on a subclass never runs. Without
    that, a hostile subclass could report no pre-bound arguments and have the
    walk hand back a signature with parameters the caller can no longer pass.
    """
    class LiesAboutItsArgs(functools.partial):
        @property
        def args(self):
            raise AssertionError("args was read off the subclass")

        @property
        def func(self):
            raise AssertionError("func was read off the subclass")

    assert binds(LiesAboutItsArgs(plain_function, 1)) == "(b)"


def test_the_call_slot_is_found_through_the_real_mro_not_the_forged_one():
    """A metaclass cannot hide the real `__call__` behind a decoy.

    The sibling of `test_a_partial_reads_its_own_args_through_the_real_slots`,
    for the other place the walk reads a namespace. `_own_call` takes the mro
    and the class dict through the unbound getset descriptors off `type`, so a
    metaclass that defines `__mro__` and `__dict__` as properties never gets to
    answer. Reading them as attributes instead is a one-word change that keeps
    the whole suite green, which is why it needs its own test.

    What the change would buy an attacker is the worst outcome this design has:
    not a refusal and not a crash, but a FALSE CERTIFICATION. The forged mro
    hands back a decoy whose `__call__` is `(real, decoy)`, so a `param:real`
    rule binds confidently against a callable that actually takes `(*a, **k)`
    and does something else entirely with them.

    Both halves are asserted. The claim must be the real one, AND the forged
    properties must run ZERO times: a walk that read them and then recovered
    would still have executed target code inside a check whose entire promise
    is that it does not.
    """
    ran = []

    class Decoy:
        def __call__(self, real, decoy):
            return "decoy"

    class ForgedMeta(type):
        @property
        def __mro__(cls):
            ran.append("mro")
            return (Decoy,)

        @property
        def __dict__(cls):
            ran.append("dict")
            return {"__call__": Decoy.__dict__["__call__"]}

    class Forged(metaclass=ForgedMeta):
        def __call__(self, *a, **k):
            return "real"

    assert binds(Forged()) == "(*a, **k)", "the forged mro steered the walk"
    assert ran == [], "the walk ran metaclass code: %r" % ran


def test_a_lying_class_attribute_cannot_pass_itself_off_as_a_function():
    """`type(x) is types.FunctionType`, never `isinstance`.

    This is the guarantee `_code_parameters`' docstring calls load-bearing:
    `types.FunctionType` is final, so an exact type check proves that every
    read below it is a real slot read on a real function. Relaxing the check to
    `isinstance` keeps the suite green and dissolves that proof, because
    `isinstance` consults `__class__` and an object may simply declare one.

    The forged `__code__` is what makes it a false certification rather than a
    crash: the walk would read it, find well-formed parameter names, and report
    a decoy's parameters as though they were this callable's own.
    """
    def _template(real, decoy):
        return "decoy"

    class LiesAboutItsType:
        __class__ = types.FunctionType
        __code__ = _template.__code__

        def __call__(self, *a, **k):
            return "real"

    liar = LiesAboutItsType()
    assert isinstance(liar, types.FunctionType), "the premise: the lie works"
    assert type(liar) is not types.FunctionType

    assert binds(liar) == "(*a, **k)", "the forged __code__ was reported"


@pytest.mark.skipif(not hasattr(functools, "Placeholder"),
                    reason="functools.Placeholder is 3.14 and later")
def test_a_placeholder_leaves_the_parameter_it_stands_in_for_nameable():
    """A Placeholder reserves a slot; it does not fill it.

    The caller must still pass that argument, so the parameter stays in the
    signature. Consuming it as though it were pre-bound would make `param:a`
    miss on a call that really does pass `a`, which is the one direction this
    design must never take: reporting a parameter as unpassed when the caller
    passed it.
    """
    obj = functools.partial(plain_function, functools.Placeholder, 2)
    assert binds(obj) == "(a, /)"
    assert obj(1) == (1, 2)


@pytest.mark.skipif(hasattr(functools, "Placeholder"),
                    reason="the pre-3.14 path, where there is no Placeholder")
def test_without_placeholder_the_ordinary_prebinding_still_holds():
    """The same file has to be honest on 3.11 to 3.13, where the type is absent.

    Paired with the test above by construction: exactly one of the two runs on
    any interpreter, and neither version of the suite is silently empty here.
    """
    assert binds(functools.partial(plain_function, 1)) == "(b)"


def test_a_prebinding_that_cannot_be_modelled_is_refused_with_its_own_reason():
    """More pre-bound positionals than the function has parameters.

    Refused as `_PREBOUND_SHAPE` rather than as the generic unavailable
    reason, because the two are different diagnostics: this one says the
    pre-binding does not fit the function, which is a fact about this partial,
    not about the shape being unmodelled.
    """
    obj = functools.partial(plain_function, 1, 2, 3)
    assert reason_for(obj) is _PREBOUND_SHAPE


# --------------------------------------------------------------------------
# End to end: five vectors through a real import, a real call and a real
# sqlite3 connection.
# --------------------------------------------------------------------------
#
# The table above calls `_binding_signature` directly, which is precise and
# proves nothing about whether an operator's rule reaches it. These drive the
# whole path instead: `install()` hooks `__import__`, the module is imported
# for the first time INSIDE the hook, the rule fires on a real call, and the
# result is read off the connection's own PRAGMA rather than off any patcher
# internal.
#
# Every vector passes TWO connections and names exactly one. The second is a
# DECOY and its assertion is the load-bearing half: receiver handling is a
# question of alignment, so a walk that drops one parameter too many or too
# few still resolves a name and still flips a connection, just the WRONG one.
# Asserting only the real connection would pass under that misalignment.

VECTOR_SOURCE = '''
import functools
import types

def free_function(real, decoy):
    return "ok"

class Holder:
    def method(self, real, decoy):
        return "ok"

class Callable:
    def __call__(self, real, decoy):
        return "ok"

class Constructed:
    def __init__(self, real, decoy):
        self.seen = True

def _decorate(fn):
    @functools.wraps(fn)
    def _wrapper(*args, **kwargs):
        return fn(*args, **kwargs)
    return _wrapper

@_decorate
def decorated(real, decoy):
    return "ok"

holder = Holder()
instance = Callable()
bound = holder.method


class _Decoy:
    def __call__(self, real, decoy):
        return "decoy"


class ForgedMeta(type):
    """Hides the real `__call__` behind a decoy, if anyone reads the mro."""

    @property
    def __mro__(cls):
        return (_Decoy,)

    @property
    def __dict__(cls):
        return {"__call__": _Decoy.__dict__["__call__"]}


class ForgedMro(metaclass=ForgedMeta):
    def __call__(self, *a, **k):
        return "real"


def _template(real, decoy):
    return "decoy"


class LyingType:
    __class__ = types.FunctionType
    __code__ = _template.__code__

    def __call__(self, *a, **k):
        return "real"


forged_mro = ForgedMro()
lying_type = LyingType()

'''


def _import_under_hook(tmp_path, name, patcher):
    """Write a real module and import it for the first time under the hook.

    Written to disk and imported rather than assembled with `ModuleType`,
    because the import hook is half of what is under test here: a vector that
    is hand-built and then force-patched skips the path an operator uses.
    """
    (tmp_path / (name + ".py")).write_text(VECTOR_SOURCE)
    sys.path.insert(0, str(tmp_path))
    try:
        return __import__(name)
    finally:
        sys.path.remove(str(tmp_path))


def _pragma_rule(module, symbol, param):
    return Rule(id="vector", module=module, symbol=symbol, event="entry",
                action={"kind": "pragma", "name": "synchronous", "value": "OFF",
                        "target": "param:" + param},
                fire={"mode": "always"}, when=None)


def _sync(con):
    return con.execute("PRAGMA synchronous").fetchone()[0]


def _two_connections(tmp_path, tag):
    real = sqlite3.connect(str(tmp_path / (tag + "-real.db")))
    decoy = sqlite3.connect(str(tmp_path / (tag + "-decoy.db")))
    # The premise of every assertion below: neither is already OFF, so a flip
    # is something this run caused rather than a state it started in.
    assert _sync(real) != 0 and _sync(decoy) != 0
    return real, decoy


VECTORS = [
    ("free function", "free_function", lambda mod: mod.free_function),
    # Two genuinely different shapes, and the difference is easy to miss.
    # Patching `Holder.method` wraps the class attribute, which is a plain
    # FUNCTION whose first parameter really is passed by the call, so nothing
    # is dropped. Patching the module-level `bound` wraps a MethodType whose
    # receiver the call does NOT pass, so the receiver must be dropped. A
    # mutant that stopped dropping receivers was caught by the table but
    # survived here until both rows existed.
    ("method patched on the class", "Holder.method",
     lambda mod: mod.holder.method),
    ("bound method at module level", "bound", lambda mod: mod.bound),
    ("instance with __call__", "instance", lambda mod: mod.instance),
    ("class constructor", "Constructed", lambda mod: mod.Constructed),
]


@pytest.mark.parametrize("label,symbol,get_callable",
                         VECTORS, ids=[row[0] for row in VECTORS])
def test_a_real_rule_reaches_the_named_parameter_and_not_its_neighbour(
        tmp_path, label, symbol, get_callable):
    """A `param:real` rule flips the real connection and leaves the decoy.

    The decoy assertion is why the receiver rows in the table above are not
    decoration. `Holder.method`, `instance` and `Constructed` all arrive with a
    receiver that the caller never passes; attributing `real` to the receiver's
    position would name `decoy` instead, flip the wrong connection, and still
    look like a success to any test that checked only that SOMETHING was
    flipped.
    """
    name = "vec_%s" % label.replace(" ", "_").replace("__", "")
    logpath = tmp_path / "firing.jsonl"
    log = open_log(str(logpath))
    p = install([_pragma_rule(name, symbol, "real")], log=log)
    real, decoy = _two_connections(tmp_path, name)
    try:
        mod = _import_under_hook(tmp_path, name, p)
        get_callable(mod)(real, decoy)
        # The decoy is read FIRST, deliberately. A misalignment fails both
        # assertions, and whichever runs first is the one an operator reads:
        # "the rule landed on the wrong parameter" names the fault, while
        # "never reached" would send them looking for a rule that did not fire.
        assert _sync(decoy) != 0, "the rule landed on the wrong parameter"
        assert _sync(real) == 0, "the named parameter was never reached"
    finally:
        p.uninstall()
        real.close()
        decoy.close()
        sys.modules.pop(name, None)
    log.close()
    records = [json.loads(line) for line in
               logpath.read_text().splitlines()]
    # `outcome` is prose and is present on BOTH a success and a miss, so the
    # discriminator is `status`. Asserting the absence of an outcome would
    # have passed only by accident.
    statuses = [record.get("status") for record in records
                if record.get("phase") == "end"]
    assert statuses == ["pragma_applied"], \
        "the log disagrees with the connection: %r" % statuses


def test_a_decorated_wrapper_misses_honestly_and_touches_neither(tmp_path):
    """The fifth vector, and the only one that must NOT fire.

    `functools.wraps` copies `__wrapped__`, so the old design read through it
    and resolved `param:real` against the signature of a function the wrapper
    might never call with those names. The redesign binds what the wrapper
    ACTUALLY receives, `(*args, **kwargs)`, so the name is unbindable and the
    rule misses.

    A miss is only honest if it is visible, so both halves are asserted: no
    connection is touched, AND the firing log carries a terminal record saying
    why. Silence here would be the worst outcome of the three, because an
    operator would read an unfired rule as a condition that did not hold.
    """
    name = "vec_decorated"
    logpath = tmp_path / "firing.jsonl"
    log = open_log(str(logpath))
    p = install([_pragma_rule(name, "decorated", "real")], log=log)
    real, decoy = _two_connections(tmp_path, name)
    try:
        mod = _import_under_hook(tmp_path, name, p)
        assert mod.decorated(real, decoy) == "ok", "the call was broken"
        assert _sync(real) != 0 and _sync(decoy) != 0, \
            "an unbindable name still reached a connection"
    finally:
        p.uninstall()
        real.close()
        decoy.close()
        sys.modules.pop(name, None)
    log.close()
    records = [json.loads(line) for line in logpath.read_text().splitlines()]
    ends = [record for record in records if record.get("phase") == "end"]
    assert ends, "the miss was silent: no terminal record"
    assert all(record.get("status") != "pragma_applied" for record in ends), \
        "the log claims a pragma was applied: %r" % ends
    assert any("real" in (record.get("outcome") or "") for record in ends), \
        "the record does not name the parameter that could not be bound: %r" % ends


def test_the_extension_path_binds_as_the_initial_build_does(tmp_path):
    """Both the initial build and the EXTENSION resolve the same parameter.

    The binding is computed where the dispatcher is assembled, and a rule that
    arrives later takes a different route into that code: it merges into a
    dispatcher that is already live rather than building one. A test that only
    ever patches once leaves that second route unexercised, and it is the route
    where a stale or re-derived binding would show up.

    Provoked the way the concurrency suite provokes it, with a second module
    that ALIASES the first, because patching the same module twice is a no-op
    and would let this pass without the extension ever running.
    """
    name = "vec_extension"
    logpath = tmp_path / "firing.jsonl"
    log = open_log(str(logpath))
    initial = _pragma_rule(name, "free_function", "real")
    later = Rule(id="later", module=name + "_alias", symbol="via.free_function",
                 event="entry",
                 action={"kind": "pragma", "name": "synchronous", "value": "OFF",
                         "target": "param:decoy"},
                 fire={"mode": "always"}, when=None)
    p = install([initial, later], log=log)
    real, decoy = _two_connections(tmp_path, name)
    try:
        mod = _import_under_hook(tmp_path, name, p)
        mod.free_function(real, decoy)
        assert _sync(real) == 0, "the initial build never bound"
        assert _sync(decoy) != 0, "the extension fired before it existed"

        alias = types.ModuleType(name + "_alias")
        alias.via = mod
        sys.modules[name + "_alias"] = alias
        p.force_patch_module(name + "_alias")
        assert len(mod.free_function._pyteman_state) == 2, \
            "the extension path was never reached"

        second_decoy = sqlite3.connect(str(tmp_path / "second-decoy.db"))
        try:
            mod.free_function(real, second_decoy)
            # The extension's rule names the OTHER parameter, so this is the
            # same alignment question asked on the second route: a binding
            # re-derived wrongly here would flip `real` twice and leave this
            # connection alone.
            assert _sync(second_decoy) == 0, "the extension never bound"
        finally:
            second_decoy.close()
    finally:
        p.uninstall()
        real.close()
        decoy.close()
        sys.modules.pop(name, None)
        sys.modules.pop(name + "_alias", None)
    log.close()


# --------------------------------------------------------------------------
# The two forged shapes, driven through the real pipeline.
# --------------------------------------------------------------------------
#
# The two tests above call the helper and count hooks, which is where the
# ZERO-RUNS property can be observed at all. These are their end-to-end halves:
# the same forged objects, but reached through `install()`, a real import, a
# real call and two real connections, so the claim is about what an operator's
# rule does rather than about what a helper returns.
#
# Both must MISS. The real routing is `(*a, **k)` in each case, so `param:real`
# is unbindable and neither connection may be touched. Under the reviewer's
# mutants the forged parameters `(real, decoy)` bind instead, and the miss
# turns into a confident flip of a real connection: a false certification, not
# a crash, which is why neither mutant disturbs the suite.

FORGED = [
    ("forged mro", "forged_mro"),
    ("lying __class__", "lying_type"),
]


@pytest.mark.parametrize("label,symbol", FORGED, ids=[r[0] for r in FORGED])
def test_a_forged_shape_misses_end_to_end_and_touches_no_connection(
        tmp_path, label, symbol):
    """A forged callable binds nothing, and the log says so.

    The decoy is asserted alongside the real connection for the same reason it
    is everywhere else in this file: a mutant that attributes the forged
    parameters flips ONE of the two, and which one depends on the forgery. The
    assertion that neither moved is the one that holds under both.
    """
    name = "vec_forged_%s" % symbol
    logpath = tmp_path / "firing.jsonl"
    log = open_log(str(logpath))
    p = install([_pragma_rule(name, symbol, "real")], log=log)
    real, decoy = _two_connections(tmp_path, name)
    try:
        mod = _import_under_hook(tmp_path, name, p)
        assert getattr(mod, symbol)(real, decoy) == "real", \
            "the real routing was not the one that ran"
        assert _sync(real) != 0, "the forged parameters were attributed"
        assert _sync(decoy) != 0, "the forged parameters were attributed"
    finally:
        p.uninstall()
        real.close()
        decoy.close()
        sys.modules.pop(name, None)
    log.close()
    ends = [json.loads(line) for line in logpath.read_text().splitlines()
            if json.loads(line).get("phase") == "end"]
    assert ends, "the miss was silent"
    assert all(record.get("status") != "pragma_applied" for record in ends), \
        "the log certifies a pragma that never applied: %r" % ends
