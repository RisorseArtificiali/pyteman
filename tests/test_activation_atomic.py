# tests/test_activation_atomic.py
"""Activation through the programmatic API is all-or-nothing.

The subprocess tests in test_sitecustomize.py cover the failures that happen
before anything is touched. These cover the ones that happen halfway: the
import hook is already in place and some callables are already wrapped when a
later rule fails. Partial instrumentation is worse than none, because it is
injection nobody authored running in a process that is about to be told it
failed.
"""
import builtins
import contextlib
import functools
import inspect
import json
import os
import sys
import types
import warnings

import pytest

from pyteman.patcher import (Patcher, SlotOwnershipError, SuspendableTargetError,
                             UninstallOrderError, _WRAPPER_CHAIN_LIMIT,
                             _disclose, _restore, _suspendable_reason, _text,
                             _typename, activate, install)
from pyteman.rules import Rule, RuleError
from pyteman.firing import FiringLog, RecordId

MODNAME = "pyteman_atomic_victim"
MODNAME2 = "pyteman_atomic_victim_two"
MODNAME3 = "pyteman_atomic_victim_refusing"
MODNAME4 = "pyteman_atomic_victim_inherits"


def make_rule(symbol, rid="r", when=None, module=MODNAME):
    return Rule(id=rid, module=module, symbol=symbol, event="entry",
                action={"kind": "return_value", "value": 1},
                fire={"mode": "always"}, when=when)


def _victim_module(name):
    mod = types.ModuleType(name)
    # setattr, not `mod.ok = ...`: a dynamically built module has no declared
    # attributes, so the plain spelling is a type error at every use.
    setattr(mod, "ok", lambda a: a)
    setattr(mod, "also", lambda a: a)
    setattr(mod, "Frozen", int)
    sys.modules[name] = mod
    try:
        yield mod
    finally:
        del sys.modules[name]


def _entry(container, name, original, wrapper, owned=True):
    """A ledger entry in the shape _patch publishes, with `wrapper` installed.

    _restore settles a slot only while it still holds the EXACT wrapper its
    entry recorded, so an entry a test invents by hand has to put one there
    first; a slot holding anything else is a released slot and is skipped.
    Installed through the type or object slot rather than a plain setattr, so
    that a container written to REFUSE writes still starts out wrapped. That is
    the real sequence anyway: it accepted the patch and only later stopped
    accepting. Going around a hostile __setattr__ also keeps the fixtures that
    count writes or mutate the ledger from firing during setup.
    """
    if isinstance(container, type):
        type.__setattr__(container, name, wrapper)
    else:
        object.__setattr__(container, name, wrapper)
    return (container, name, original, wrapper, owned)


@pytest.fixture
def victim():
    """A module already in sys.modules, holding one immutable-type attribute.

    Built here rather than reusing tests/target_mod.py so the refused setattr
    is part of the fixture's stated purpose: `int` is a C type, so patching an
    attribute of it raises TypeError, which is the failure class no static
    check can predict and the reason the patch loop needs a rollback at all.
    """
    yield from _victim_module(MODNAME)


@pytest.fixture
def victim2():
    """A second one, for the failure that spans two modules."""
    yield from _victim_module(MODNAME2)


def test_activate_patches_and_uninstall_restores(victim):
    # The guard that keeps the two rollback tests below from passing vacuously:
    # if activate() patched nothing, "nothing was left behind" would be true
    # for the wrong reason.
    import_before, ok_before = builtins.__import__, victim.ok
    p = activate([make_rule("ok")], log=None, modules=[MODNAME])
    try:
        assert victim.ok is not ok_before
        assert victim.ok(5) == 1  # the action really fires, not just a wrapper
        assert builtins.__import__ is not import_before
    finally:
        p.uninstall()
    assert victim.ok is ok_before
    assert builtins.__import__ is import_before


def test_activate_rolls_back_when_a_later_patch_is_refused(victim):
    import_before, ok_before = builtins.__import__, victim.ok
    # Rule order is patch order within a module, so the first rule is applied
    # and the second is refused: the state under test is one wrap deep.
    rules = [make_rule("ok", "first"), make_rule("Frozen.bit_length", "second")]
    with pytest.raises(TypeError):
        activate(rules, log=None, modules=[MODNAME])
    assert victim.ok is ok_before
    assert builtins.__import__ is import_before


def test_activate_rolls_back_a_module_it_had_already_finished(victim, victim2):
    """The one wrap nothing inside _patch can reach.

    _patch unwinds the module it is working on. A module patched CLEANLY in an
    earlier iteration of activate()'s loop is finished: its call returned, its
    local list was published, and no handler will ever look at it again. That
    wrap survives unless activate() removes it from outside, and a process told
    its activation was refused would then run with injection nobody authored.

    Both mechanisms are exercised at once, which is why the second module also
    carries a good rule ahead of the bad one: `also` in module two is undone by
    _patch's own handler, `ok` in module one only by activate's.
    """
    import_before = builtins.__import__
    ok_before, also_before = victim.ok, victim2.also
    rules = [make_rule("ok", "first"),
             make_rule("also", "second", module=MODNAME2),
             make_rule("Frozen.bit_length", "third", module=MODNAME2)]
    with pytest.raises(TypeError):
        activate(rules, log=None, modules=[MODNAME, MODNAME2])
    assert victim.ok is ok_before
    assert victim2.also is also_before
    assert builtins.__import__ is import_before


def test_import_hook_rolls_back_the_module_it_was_patching(victim):
    """The same refusal, reached through the hook instead of through activate().

    activate() can only unwind modules it drove itself. A module imported later,
    while the workload is already running, is patched from inside hooked(), on
    the workload's own import stack, and there is no handler above it: that path
    is reachable only because _patch unwinds its own work.

    The hook is deliberately still installed afterwards. _patch owns the wraps it
    made and undoes them; it does not own the hook, and the rules for every other
    module are still good.
    """
    import_before, ok_before = builtins.__import__, victim.ok
    rules = [make_rule("ok", "first"), make_rule("Frozen.bit_length", "second")]
    p = install(rules, log=None)
    try:
        with pytest.raises(TypeError):
            builtins.__import__(MODNAME)
        assert victim.ok is ok_before
        # applied is what the report reads; a name left here for a wrap that was
        # rolled back would describe an experiment that never ran.
        assert p.applied == []
        assert builtins.__import__ is not import_before
    finally:
        p.uninstall()
    assert builtins.__import__ is import_before


def test_uncompilable_expression_fails_before_any_mutation(victim):
    """A hand-built Rule never went through load_rules, so nothing compiled it.

    This is the case criterion #2 names: the programmatic API accepts Rule
    objects directly. Compiling every expression in Patcher.__init__ moves the
    failure ahead of the import hook and of the first setattr, so there is no
    rollback to get right.
    """
    import_before, ok_before, also_before = builtins.__import__, victim.ok, victim.also
    rules = [make_rule("ok", "good"), make_rule("also", "bad", when="(")]
    # Asserted against the CONSTRUCTOR, because that is what the docstring
    # claims and the assertions below cannot tell apart. Move the compiles back
    # into _make_dispatcher and every one of them still holds: activate would
    # install the hook, wrap `ok`, fail on 'bad', roll back and uninstall,
    # arriving at the same end state by the path this test exists to rule out.
    with pytest.raises(RuleError):
        Patcher(rules, None)
    with pytest.raises(RuleError) as excinfo:
        activate(rules, log=None, modules=[MODNAME])
    # Both halves of the diagnostic: what is wrong, and which rule to go fix.
    assert "is not a valid expression" in str(excinfo.value)
    assert "'bad'" in str(excinfo.value)
    assert victim.ok is ok_before
    assert victim.also is also_before
    assert builtins.__import__ is import_before


def test_install_still_does_not_patch_loaded_modules(victim):
    # install() hooks __import__ and patches as modules arrive; it deliberately
    # does not sweep sys.modules, and callers drive force_patch_module
    # themselves. activate() is an additional entry point, not a change to this.
    ok_before = victim.ok
    p = install([make_rule("ok")], log=None)
    try:
        assert victim.ok is ok_before
    finally:
        p.uninstall()


# --- the unwind is best effort, and says so when it falls short -------------
#
# Every test above asserts the rollback SUCCEEDED. These cover the case where it
# cannot: a container that accepts the wrapper and then refuses to take the
# original back. The wrap survives, which is unavoidable, and the contract is
# therefore about disclosure rather than about cleanliness. Silence here would
# be read as "nothing was left behind" by an operator whose process is still
# carrying injection nobody authored.


class _RefusingModule(types.ModuleType):
    """Accepts a pyteman wrapper, refuses the restore.

    Not a contrived shape: lazy-loader shims and deprecation proxies define
    __setattr__, and one that is picky about what it accepts can take the
    wrapper on the way in and reject the original on the way out.
    """

    def __setattr__(self, name, value):
        # The wrapper carries _pyteman_state and the original does not, which
        # is the whole of the test: accept the way in, refuse the way out. No
        # attribute-name clause, because the fixture below installs its own
        # attributes through object.__setattr__ and the only writes that reach
        # here are the patcher's.
        if getattr(value, "_pyteman_state", None) is None:
            raise AttributeError(f"this module refuses to have {name} restored")
        object.__setattr__(self, name, value)


@pytest.fixture
def refusing():
    mod = _RefusingModule(MODNAME3)
    # object.__setattr__ for the setup, so the guard above governs only what
    # the patcher does and the fixture is not fighting itself.
    object.__setattr__(mod, "f", lambda a: a)
    object.__setattr__(mod, "Frozen", int)
    sys.modules[MODNAME3] = mod
    try:
        yield mod
    finally:
        del sys.modules[MODNAME3]


def _refusal_notes(exc):
    return [n for n in getattr(exc, "__notes__", []) if "could not restore" in n]


class Hostile(Exception):
    """An exception that will not say what it is."""

    def __str__(self):
        raise RuntimeError("boom from __str__")


class _HostileNameMeta(type):
    """Serves __name__ from a property, which is ordinary metaclass practice.

    ORM models, plugin registries and generic-alias shims all synthesise
    __name__ this way. What makes it interesting here is only that the property
    may return something other than a string, and the attribute lookup still
    SUCCEEDS: a try/except around it sees nothing wrong and passes the value on.
    """

    @property
    def __name__(cls):  # type: ignore[override]
        class Unrenderable:
            def __str__(self):
                raise RuntimeError("this name refuses to render")

            __repr__ = __str__

        return Unrenderable()


class HostileName(metaclass=_HostileNameMeta):
    # Hostile to str() as well, so one object exercises both helpers: _text
    # falls through to its last-resort branch, and that branch renders a type
    # name, which is exactly where the metaclass above is waiting.
    def __str__(self):
        raise RuntimeError("this object refuses to render")


class BoomStr(str):
    """A str that passes every isinstance check and then refuses to render.

    The subtler half of the same defect. `str()` returns whatever __str__ gave
    it as long as that is a str INSTANCE, and a subclass carries its own
    __repr__ and __format__, so a value that looks like plain text to every
    guard still runs user code the moment a caller interpolates it.
    """

    def __repr__(self):
        raise RuntimeError("no repr for you")

    def __format__(self, spec):
        raise RuntimeError("no format for you")


class HostileId:
    """A rule id that renders as a str subclass rather than as a str.

    Not a contrived shape for a hand-built Rule: an id carried over from an
    enum, a path-like wrapper or a lazily-interpolated template class is an
    ordinary thing to pass, and Rule is a plain dataclass that checks nothing.
    """

    def __str__(self):
        return BoomStr("hostile-id")


class UnreadableIdRule:
    """A rule whose `id` cannot be READ, as opposed to cannot be rendered.

    Not a Rule instance, and it does not need to be: Patcher never checks, and
    a rule reaches it as whatever the caller built. The distinction from
    HostileId above is the whole point. There the attribute is readable and its
    RENDERING is hostile, which _text absorbs; here the access itself raises,
    which no guard around str() can reach, because the access is the argument
    being passed to it.

    A property that raises is what a lazily-resolved id looks like when its
    backing store has gone away, which is an ordinary way for a long-lived
    ruleset object to end up here.
    """

    module = MODNAME3
    symbol = "Frozen.bit_length"
    event = "entry"
    action = {"kind": "return_value", "value": 1}
    fire = {"mode": "always"}
    when = None

    @property
    def id(self):
        raise RuntimeError("this id refuses to be read")


class _SubclassNameMeta(type):
    @property
    def __name__(cls):  # type: ignore[override]
        return BoomStr("Victim")


class SubclassName(metaclass=_SubclassNameMeta):
    pass


def test_activate_reports_a_rollback_it_could_not_complete(refusing):
    """The failure the operator cannot infer from the exception they are handed.

    The TypeError names `Frozen.bit_length`. What it does not say, and what no
    amount of reading it will reveal, is that `f` is a different callable that
    is still wrapped. _restore has always collected that; _patch used to drop it
    on the floor.
    """
    rules = [make_rule("f", "good", module=MODNAME3),
             make_rule("Frozen.bit_length", "bad", module=MODNAME3)]
    with pytest.raises(TypeError) as excinfo:
        activate(rules, log=None, modules=[MODNAME3])
    notes = _refusal_notes(excinfo.value)
    assert len(notes) == 1, getattr(excinfo.value, "__notes__", None)
    # The container, the attribute, and why: all three are needed to find it.
    # The container as the RULE names it. This fixture is a ModuleType
    # SUBCLASS, so it is also the case that caught the container naming: the
    # note used to read `_RefusingModule.f`, after a private test class the
    # operator has no way to connect to `module: pyteman_atomic_victim_refusing`
    # in their own ruleset.
    assert f"{MODNAME3}.f" in notes[0], notes[0]
    assert "AttributeError" in notes[0]
    # The rule note still has to be there. The refusal is additional context,
    # never a replacement for what the operator has to go and edit.
    assert any("'bad'" in n for n in excinfo.value.__notes__)
    assert getattr(refusing.f, "_pyteman_state", None) is not None  # really stuck


def test_a_rollback_that_falls_apart_does_not_replace_the_failure(refusing,
                                                                 monkeypatch):
    """Cleanup coming apart must not cost the operator the failure to fix.

    activate() calls uninstall() from inside its own handler, so anything
    raised there propagates INSTEAD of the exception being handled. _restore
    walks a fixed index range rather than an iterator, so a ledger that SHRINKS
    under it indexes past the end; only a concurrent or re-entered uninstall
    can shrink it, which sits inside the documented thread-safety limit. The
    limit is about losing instrumentation, though, and this would additionally
    hand the operator an IndexError about a list where the rule they have to go
    and edit should be.

    The IndexError is reproducible for real, with a container whose __setattr__
    re-enters uninstall. Building it that way here would pin the race instead
    of the guarantee, and the guarantee is what activate() owes whatever
    uninstall() does, so the failure is injected rather than provoked.
    """

    def explodes(self):
        raise IndexError("list assignment index out of range")

    # Breaking uninstall() also breaks the only thing that takes the import
    # hook back off, so this test has to return it itself. Setting __import__
    # to what it already is does nothing now and registers the restore for
    # teardown; without it the hook outlives the test and the next one to
    # assert a clean interpreter fails in its place.
    monkeypatch.setattr(builtins, "__import__", builtins.__import__)
    monkeypatch.setattr(Patcher, "uninstall", explodes)
    rules = [make_rule("f", "good", module=MODNAME3),
             make_rule("Frozen.bit_length", "bad", module=MODNAME3)]
    # TypeError and not IndexError: the failure outlives its own cleanup.
    with pytest.raises(TypeError) as excinfo:
        activate(rules, log=None, modules=[MODNAME3])
    notes = [str(n) for n in getattr(excinfo.value, "__notes__", [])]
    assert any("the rollback did not finish" in n for n in notes), notes
    assert any("IndexError" in n for n in notes), notes
    # The rule note survives too: the cleanup report is additional context and
    # never a replacement for what has to be edited.
    assert any("'bad'" in n for n in notes), notes


def test_force_patch_module_reports_a_rollback_it_could_not_complete(refusing):
    """The same disclosure on the path activate() never sees.

    force_patch_module and the import hook both call _patch directly, with no
    handler above them. If the note were attached by activate() rather than by
    _patch, this path would stay silent, and it is the path that runs while the
    workload is live.
    """
    rules = [make_rule("f", "good", module=MODNAME3),
             make_rule("Frozen.bit_length", "bad", module=MODNAME3)]
    p = install(rules, log=None)
    try:
        with pytest.raises(TypeError) as excinfo:
            p.force_patch_module(MODNAME3)
        assert len(_refusal_notes(excinfo.value)) == 1
        # The note is not merely present, it is true: `f` really did stay
        # wrapped, so the disclosure describes the process as it now is.
        assert getattr(refusing.f, "_pyteman_state", None) is not None
    finally:
        p.uninstall()


def test_restore_finishes_the_loop_whatever_the_refusal_is():
    """_restore attempts every entry and renders none of them.

    The loop catches BaseException per entry precisely so that one refusal
    cannot strand the entries after it. It used to build the message inside that
    handler, which runs __str__ and __repr__ on user objects, so an exception
    hostile to either escaped from inside the one handler written to keep the
    loop going. Rendering now happens in _disclose, after the last setattr has
    been attempted, so nothing the reporting does can shorten the unwind.
    """

    class Refuses:
        def __setattr__(self, name, value):
            raise Hostile()

    class Accepts:
        # Declared on the class, not assigned on the instance: a bare class has
        # no attributes to a type checker, the same reason _victim_module above
        # builds its module with setattr.
        x = "WRAPPED"

    accepts = Accepts()
    refuses = Refuses()
    # reversed(): the refusing entry is handled FIRST, so the one after it is
    # the one that gets stranded if the loop dies.
    refusing_entry = _entry(refuses, "y", 1, "WRAPPED-Y")
    entries = [_entry(accepts, "x", "ORIGINAL", "WRAPPED-X"), refusing_entry]
    refused = _restore(entries)
    assert accepts.x == "ORIGINAL"
    # A triple, not a sentence. The objects travel unrendered so that deciding
    # how to describe them is somebody else's problem and cannot be this loop's.
    assert len(refused) == 1
    container, name, exc = refused[0]
    assert isinstance(container, Refuses) and name == "y"
    assert isinstance(exc, Hostile)
    # The list is CONSUMED, and what survives it is what is still wrapped. This
    # is the half that makes a caller's ledger correct without the caller
    # reconciling anything: the entry that went back is gone, the entry that
    # refused is still there. Both callers used to discard the whole list on the
    # assumption the undo worked.
    assert entries == [refusing_entry]


def test_disclose_degrades_rather_than_raising_over_the_real_failure():
    """The rendering is user code, and it runs while an exception is unwinding.

    Three hostilities at once, because they fail in different places: the
    container's type NAME, the refusal's type name, and the refusal's message.
    Each is reached from a different helper, and any one of them escaping would
    replace the exception the operator has to act on with a failure from the
    code describing it.
    """
    original = TypeError("cannot set 'bit_length' of immutable type 'int'")
    _disclose(original, [(HostileName(), "f", Hostile())])
    notes = _refusal_notes(original)
    assert len(notes) == 1
    # Degraded, never silent, and never at the price of the original.
    assert "<unknown type>" in notes[0] and "unprintable" in notes[0]
    assert str(original).startswith("cannot set")


def test_disclose_counts_refusals_it_cannot_describe_at_all():
    """The last line of defence, when even the degraded rendering will not run.

    _typename and _text each absorb their own failure, so reaching the outer
    handler takes an object that breaks the comprehension itself. What survives
    is the COUNT, and that is the deliberate part: how many callables are still
    wrapped is the one thing an operator cannot work out from anywhere else.
    """

    class Exploding:
        """Not iterable the way `for container, name, exc in refused` needs."""

        def __iter__(self):
            raise RuntimeError("this refusal will not unpack")

    original = TypeError("the real failure")
    _disclose(original, [Exploding()])
    notes = _refusal_notes(original)
    assert len(notes) == 1 and "1 attribute(s)" in notes[0]
    assert str(original) == "the real failure"


def test_disclose_names_the_attribute_whose_name_will_not_render():
    """Degrading is the floor, not the target: the detail is worth recovering.

    The attribute name was the one value in this note not routed through _text,
    on the assumption that it is always a plain str. It is not: it comes from
    `rule.symbol.split(".")`, and a symbol that is a str SUBCLASS returns
    whatever its own split returns. The guard around the comprehension still
    caught the resulting __format__, so nothing crashed, which is exactly why
    this was worth finding: the failure mode is a silent downgrade from "this
    attribute, for this reason" to a bare count.

    Which attribute is still wrapped is the part an operator cannot work out
    from anywhere else, so losing it to the name's own rendering gives up the
    substance of the note while keeping its shape.
    """
    original = TypeError("the real failure")
    _disclose(original, [(HostileName(), BoomStr("f"), RuntimeError("refused"))])
    notes = _refusal_notes(original)
    assert len(notes) == 1
    # The name survives as text, and the count fallback was NOT taken.
    assert ".f: " in notes[0], notes[0]
    assert "attribute(s)" not in notes[0], notes[0]
    assert str(original) == "the real failure"


def test_the_note_names_the_container_an_operator_would_recognise():
    """`type.m` names nothing: the container is usually a class or a module.

    The note's one job is to say WHICH callable is still wrapped. The container
    comes from walking `rule.symbol.split(".")`, so it is the class for `C.m`
    and the module itself for a bare `f`. Asking for its TYPE answered `type`
    and `module`, the same answer for every rule in the ruleset. An instance
    container is the one shape that always rendered, and the one that hardly
    ever occurs, which is why this went unnoticed: the existing tests above
    build their containers as instances.
    """

    class Container:
        pass

    module = types.ModuleType("named_victim_module")
    original = TypeError("the real failure")
    _disclose(original, [(Container, "m", RuntimeError("refused")),
                         (module, "f", RuntimeError("refused"))])
    note = _refusal_notes(original)[0]
    assert "Container.m" in note, note
    assert "named_victim_module.f" in note, note
    assert "type." not in note, note


def test_disclose_says_a_strand_once_however_many_times_it_is_reported():
    """The same stranded callable, reported twice, has to read as one.

    _restore KEEPS what it could not restore, so a strand survives in the
    ledger and every later unwind retries it and refuses it again. _patch
    discloses the module it was working on, then activate() discloses
    everything still wrapped, which is a SUPERSET whenever an earlier module
    stranded something too. Comparing whole NOTES sees two different strings
    there and attaches both, and the operator reads one stuck callable as two
    and goes looking for a second one that does not exist.
    """

    class Early:
        pass

    class Late:
        pass

    original = TypeError("the real failure")
    first = (Early, "a", RuntimeError("refused"))
    second = (Late, "b", RuntimeError("refused"))

    _disclose(original, [first])
    # The superset: the strand already disclosed, plus one that is new.
    _disclose(original, [first, second])

    notes = _refusal_notes(original)
    assert len(notes) == 2, notes
    assert "Early.a" in notes[0] and "Late.b" not in notes[0], notes[0]
    # Only what is new, so the shared strand is named exactly once overall.
    assert "Late.b" in notes[1], notes[1]
    assert "Early.a" not in notes[1], notes[1]

    # A disclosure that adds nothing attaches nothing, rather than an empty
    # note the operator still has to read and dismiss.
    _disclose(original, [first, second])
    assert len(_refusal_notes(original)) == 2


def test_a_refusal_message_holding_the_separator_is_disclosed_twice():
    """The dedup splits on its own separator, and a message may contain it.

    Recovering the previous strands means splitting a note back up on "; ", so
    a refusal whose own message contains that sequence splits into pieces that
    match nothing and the strand is disclosed again. This pins the direction
    rather than the mechanism: a repeated strand is visible to whoever reads
    the notes, and one suppressed by a looser substring match is not, so when
    the matching has to be wrong it must be wrong this way round.
    """

    class Splits:
        pass

    original = TypeError("the real failure")
    strand = (Splits, "m", RuntimeError("refused; and could not retry"))
    _disclose(original, [strand])
    _disclose(original, [strand])
    notes = _refusal_notes(original)
    assert len(notes) == 2, notes
    assert notes[0] == notes[1], notes


def test_typename_survives_a_type_whose_name_is_not_a_string():
    """The lookup can succeed and still hand back something unrenderable.

    __name__ is an ordinary attribute of the type object, and a metaclass may
    serve it from a property. Guarding only the lookup left _typename returning
    a hostile object into its caller's f-string, which put the failure back
    inside the helpers written to absorb it, _text's own fallback included.
    """
    assert _typename(HostileName()) == "<unknown type>"
    # _text's fallback branch renders a type name, so it inherits the hole.
    assert _text(HostileName()) == "<unprintable <unknown type>>"


def test_the_helpers_return_exact_strings_not_merely_str_instances():
    """`isinstance(x, str)` is true for exactly the objects that defeat it.

    A str subclass passes every type guard and then runs its own __repr__ or
    __format__ inside the caller's f-string, so "returns a str" was never the
    invariant the callers needed: the value has to be INERT. Both helpers
    therefore normalise, and the assertions below check the type rather than
    the value, because an isinstance-based assertion would pass against the bug
    this closes.
    """
    assert type(_typename(SubclassName())) is str
    assert _typename(SubclassName()) == "<unknown type>"
    # _text keeps the text, since rendering succeeded; what it drops is the
    # subclass, which is the part that would have run in the caller's f-string.
    assert type(_text(HostileId())) is str
    assert _text(HostileId()) == "hostile-id"
    assert f"{_text(HostileId())!r}" == "'hostile-id'"


def test_a_ruleset_handed_over_as_an_iterator_is_read_exactly_once(victim):
    """Nothing says a ruleset arrives as a list, and consuming it twice is silent.

    `install` and `Patcher` take whatever iterable the caller has. The plan is
    built by iterating it, and the copy kept on the Patcher was built by
    iterating it again, so a generator filled the plan and left the copy empty:
    two views of one ruleset disagreeing about which rules exist. That is the
    exact alignment failure the plan was introduced to rule out, arriving
    through the code that builds the plan.

    Both halves matter. The lengths agreeing is what the bug broke, and the
    patching still working is what says the fix materialised the rules rather
    than merely counting them somewhere convenient.
    """
    rules = [make_rule("ok"), make_rule("also", "second")]
    p = install(iter(rules), log=None)
    try:
        assert len(p._plan) == len(p.rules) == 2
        p.force_patch_module(MODNAME)
        assert getattr(victim.ok, "_pyteman_state", None) is not None
        assert getattr(victim.also, "_pyteman_state", None) is not None
    finally:
        p.uninstall()


def test_a_hostile_rule_id_costs_neither_the_failure_nor_the_disclosure(refusing):
    """The reporting runs user code, and it runs while an exception unwinds.

    _patch names the rule in a note so the operator knows what to go and edit.
    With `id` rendering to a str subclass, a `!r` over that value called a
    __repr__ that raises: the RuntimeError from the reporting replaced the
    TypeError the operator has to act on, and _disclose below it never ran, so
    a callable left wrapped went unmentioned in a process being told its patch
    had failed. That is precisely the outcome the contract rules out.

    The rendering now happens in _describe_rule, called from __init__ before
    anything is patched, which is what keeps this note out of the unwind
    entirely. This test pins the outcome rather than the location, so it stays
    honest wherever the rendering lives.

    Both halves are asserted, because closing only the first would leave the
    quieter one: the exception is the original, AND the refusal is still
    disclosed.
    """
    rules = [make_rule("f", "good", module=MODNAME3),
             # A str SUBCLASS, deliberately, and this is the shape preflight
             # admits rather than the one it turns away. __init__ now demands a
             # readable non-empty str id, and a BoomStr is one: it satisfies
             # every isinstance check and still runs user code the moment a
             # caller interpolates it. So the hazard this test is about survives
             # the new gate, which is the reason the gate is not a substitute
             # for rendering the identity once, up front, through _text.
             make_rule("Frozen.bit_length", BoomStr("hostile-id"),
                       module=MODNAME3)]
    with pytest.raises(TypeError) as excinfo:
        activate(rules, log=None, modules=[MODNAME3])
    notes = getattr(excinfo.value, "__notes__", [])
    assert any("while patching rule" in n for n in notes), notes
    assert any("hostile-id" in n for n in notes), notes
    # Exactly one, and this count now carries a second guarantee. The strand
    # survives in the ledger, so activate()'s unwind retries it and re-refuses,
    # and _disclose drops the repeat: one stranded callable reads as one. Before
    # _restore kept its refusals, this passed for the opposite reason, because
    # the ledger reaching uninstall() was empty.
    assert len(_refusal_notes(excinfo.value)) == 1, notes
    assert getattr(refusing.f, "_pyteman_state", None) is not None


def test_a_rule_id_that_cannot_be_read_is_refused_before_anything_is_patched(refusing):
    """The other half of the hazard is not absorbed now, it is turned away.

    The test above is about a value that will not RENDER, which _text absorbs
    and preflight admits. This is about an attribute access that raises, which
    _text cannot absorb at any strength, because `_text(rule.id)` evaluates the
    access to produce the argument.

    Absorbing it was the old answer, and it was wrong about what an id is for.
    _rule_id can degrade the id wherever a rule is only being NAMED, and it
    still does. It cannot degrade the reads that matter at runtime:
    `FiringLog.record` takes `rule.id` raw, inside the instrumented callable,
    for the `phase: start` record and again for the terminal `phase: end` one. A rule that will not name itself therefore did not
    cost a placeholder, it replaced the slot and then raised out of the
    caller's workload on the first firing, with no firing record written.

    So the refusal happens here, at the one step that mutates nothing, and the
    guarantee to assert is stronger than a readable note: the module the rule
    aimed at is left exactly as it was found. The note is still asserted,
    because a refusal nobody can act on is its own defect, and it is built from
    the placeholder and the location, which is what _rule_id is still for.
    """
    before = refusing.f
    rules = [make_rule("f", "good", module=MODNAME3),
             # Not a Rule, which is the premise: see UnreadableIdRule.
             UnreadableIdRule()]  # type: ignore[list-item]
    with pytest.raises(RuleError) as excinfo:
        activate(rules, log=None, modules=[MODNAME3])
    assert "id could not be read" in str(excinfo.value)
    # The degradation survives where it belongs: the refusal names the rule by
    # placeholder and keeps the LOCATION, which is what the operator greps
    # their ruleset for. Only the read that raised costs anything.
    notes = getattr(excinfo.value, "__notes__", [])
    assert any("<unreadable id>" in n for n in notes), notes
    assert any(f"{MODNAME3}:Frozen.bit_length" in n for n in notes), notes
    # Nothing was wrapped, so there is nothing to disclose and nothing to undo.
    # This is the assertion the old behaviour could not make: it reached
    # _patch, instrumented the slot, and left it instrumented.
    assert refusing.f is before
    assert getattr(refusing.f, "_pyteman_state", None) is None


def test_the_note_names_the_rule_that_failed_not_the_one_before_it(victim):
    """Which rule the note names, when the failure precedes its own setattr.

    Every other failure in this file happens AT the setattr, the last statement
    in the loop body that can fail, and `current` is correct there wherever in
    the body it is assigned. This is the case that tells the placements apart.

    The failure is put at `rule.symbol.split(".")`, which is the first
    statement that can fail for a rule the module filter lets through, so the
    assertion pins `current = described` above the split. It does NOT reach the
    top of the body: the `rule.module != modname` filter runs first, and a
    `current` assigned between the filter and the split would satisfy every
    assertion here. test_the_note_degrades_when_the_rule_cannot_say_which_module
    _it_is_for is the one that closes that gap, by failing inside the filter
    itself. With the first rule resolved, any placement below the split leaves
    `current` naming the rule that SUCCEEDED, and an operator reading that note
    goes off to edit a rule that is perfectly fine: a wrong diagnosis, which is
    worse than none, because it reads as a diagnosis.

    A non-str symbol is the cheapest way to fail that early. load_rules rejects
    it and the programmatic API does not, which is the whole reason the patcher
    re-checks what it is handed.
    """
    rules = [make_rule("ok", "first"),
             # A non-str symbol is the premise of the test, so the type
             # checker's objection to it is the point rather than a problem.
             Rule(id="second", module=MODNAME, symbol=None,  # type: ignore[arg-type]
                  event="entry", action={"kind": "return_value", "value": 1},
                  fire={"mode": "always"}, when=None)]
    with pytest.raises(AttributeError) as excinfo:
        activate(rules, log=None, modules=[MODNAME])
    notes = getattr(excinfo.value, "__notes__", [])
    assert any("'second'" in n for n in notes), notes
    assert not any("'first'" in n for n in notes), notes
    # `first` is unwrapped here, and since the two-pass _patch that is because
    # it was never wrapped: this failure lands in resolution, which precedes
    # every setattr. Kept rather than deleted, because `is None` is the right
    # assertion under both orderings and it is the thing that would catch a
    # later change moving installation back up into the resolution pass. It is
    # a guard against a regression, not evidence of a rollback; the rollback
    # itself is pinned by the tests that fail AT the setattr.
    assert getattr(victim.ok, "_pyteman_state", None) is None


def test_a_refused_patch_is_not_reported_as_an_unparseable_signature(victim):
    """A guard must not be wider than the operation it claims to describe.

    Building a dispatcher for a `param:` target needs the callable's real
    signature, so _make_dispatcher imports inspect. That import runs while the
    hook is LIVE, so it is served by the hook and patches module `inspect`
    against the whole ruleset. When the import sat inside the try, a different
    rule's refused setattr arrived here as a TypeError, which is also what an
    unintrospectable callable raises, so it was recorded as "this signature
    would not parse" and activation RETURNED NORMALLY: half applied, no
    diagnostic, in a process that believes its instrumentation is in place.

    `function.__call__` is chosen because refusing is its documented behaviour
    rather than a property of this test: it belongs to an immutable C type, so
    the setattr raises whatever anyone does. The two notes are the assertion
    that matters. They read as a stack, innermost first: rule 'refused' is the
    cause, rule 'param' is what was being patched when it surfaced.
    """
    param_rule = Rule(id="param", module=MODNAME, symbol="ok", event="entry",
                      action={"kind": "pragma", "name": "synchronous",
                              "value": "OFF", "target": "param:a"},
                      fire={"mode": "always"}, when=None)
    refused_rule = Rule(id="refused", module="inspect",
                        symbol="types.FunctionType.__call__", event="entry",
                        action={"kind": "return_value", "value": 1},
                        fire={"mode": "always"}, when=None)
    with pytest.raises(TypeError) as excinfo:
        activate([param_rule, refused_rule], log=None, modules=[MODNAME])
    notes = getattr(excinfo.value, "__notes__", [])
    patching = [n for n in notes if "while patching" in n]
    # ORDER, not merely presence. docs/rules.md tells the operator to read these
    # as a stack and take the FIRST as the cause, so attaching the outer note
    # ahead of the inner one would make the documented reading rule false while
    # two `any` assertions stayed green. The count is asserted too: a third
    # level would mean the re-entry is not bounded the way the docs say.
    assert len(patching) == 2, notes
    assert "'refused'" in patching[0], notes
    assert "'param'" in patching[1], notes
    # Fail-closed means nothing is left running, not merely that something was
    # raised. `ok` is unwrapped and the hook is off. The unwrapped half is a
    # weaker claim than it looks, and is kept for the same reason as the one in
    # test_the_note_names_the_rule_that_failed_not_the_one_before_it: the
    # failure surfaces inside _make_dispatcher, which runs BEFORE this slot's
    # setattr, so `ok` was never wrapped rather than wrapped and restored. The
    # hook assertion below is the one carrying weight here.
    assert getattr(victim.ok, "_pyteman_state", None) is None
    assert builtins.__import__.__module__ != "pyteman.patcher"


class UncompilableUnreadableIdRule(UnreadableIdRule):
    """The unreadable id again, on the one path that had to read it twice."""

    when = "("


def test_a_rule_id_that_cannot_be_read_still_names_the_field_that_will_not_compile():
    """_compile names the rule, so _compile must survive a rule that will not.

    UnreadableIdRule above leaves `when` empty, so _compile returns at its first
    line and its body is never reached. That is the coverage gap this closes:
    both of _compile's f-strings read `rule.id`, the second from inside an
    `except SyntaxError`, and each did the attribute access as an ARGUMENT to
    _text, outside the guard. A rule that will not say what it is called
    therefore replaced "when is not a valid expression" with a RuntimeError
    from the reporting, carrying no notes and naming no field, which leaves the
    operator with a broken ruleset and nothing to act on.

    Constructor-time, so the assertion that nothing was mutated is about the
    guarantee rather than the fixture: this must die before the hook exists.
    """
    before = builtins.__import__
    with pytest.raises(RuleError) as excinfo:
        install([UncompilableUnreadableIdRule()], log=None)  # type: ignore[list-item]
    message = str(excinfo.value)
    assert "when is not a valid expression" in message, message
    # Degraded to a placeholder rather than dropped: "a rule" is not actionable,
    # and the field name is what the operator needs either way.
    assert "<unreadable id>" in message, message
    assert builtins.__import__ is before


class UnreadableModuleRule:
    """A rule that will not say which module it is for.

    The one shape that fails BEFORE the module filter rather than at the
    setattr, which is what tells the two placements of `current` apart: every
    other failure in this file happens later in the body, where either
    placement names the right rule.
    """

    symbol = "ok"
    event = "entry"
    action = {"kind": "return_value", "value": 1}
    fire = {"mode": "always"}
    when = None
    id = "unreadable-module"

    @property
    def module(self):
        raise RuntimeError("this rule will not say which module it is for")


def test_the_note_degrades_when_the_rule_cannot_say_which_module_it_is_for(victim):
    """`current` is assigned above the module filter, and that is load-bearing.

    The filter itself reads `rule.module`, so it is user code and it can raise.
    Assigned below it, `current` still holds the PREVIOUS rule when it does,
    and the note names a rule that patched perfectly well. An operator reading
    that goes and edits a rule that is not broken, which is worse than no note
    at all, because a wrong diagnosis reads exactly like a right one.
    """
    rules = [make_rule("ok", "first"),
             UnreadableModuleRule()]  # type: ignore[list-item]
    with pytest.raises(RuntimeError) as excinfo:
        activate(rules, log=None, modules=[MODNAME])
    notes = getattr(excinfo.value, "__notes__", [])
    # Naming the right rule is the assertion; the absence of 'first' is the
    # same claim stated negatively, and both are kept because they fail on
    # different mistakes. The id read cleanly here, so only the module and
    # symbol degrade: a `current` assigned below the filter would produce a
    # note naming 'first', and a _describe_rule guarding all three fields
    # under one handler would produce one naming nothing.
    assert any("'unreadable-module'" in n for n in notes), notes
    assert any("module and symbol could not be read" in n for n in notes), notes
    assert not any("'first'" in n for n in notes), notes
    # Unwrapped because the module filter it died in runs in the resolution
    # pass, ahead of every setattr, so 'first' was resolved and never
    # installed. Kept as the guard that this stays true.
    assert getattr(victim.ok, "_pyteman_state", None) is None


class RefusesNotes(Exception):
    """A failure that cannot carry notes, because __notes__ is not a list.

    add_note appends to whatever `__notes__` holds and raises TypeError when it
    is not a list. A subclass shadowing the attribute is the one shape that
    does that, and it is reachable from ordinary code: an exception class with
    a `__notes__` field of its own, defined without knowing the interpreter
    claims the name.
    """

    __notes__ = "not a list"  # type: ignore[assignment]


def test_a_failure_that_cannot_carry_notes_still_arrives_as_itself():
    """The reporting must not become the failure it is reporting.

    Everything else in this file protects the RENDERING of a note. This is the
    attachment: add_note raises here, from inside the except block that exists
    to make the failure more legible. Unguarded, the operator gets "Cannot add
    note: __notes__ is not a list" instead of the refusal from their own
    module, and the disclosure below it never runs either.

    Dropping the note is the accepted cost, and the only one available: the
    exception on its way out is worth more than the sentence about it.
    """

    class _NoteRefusingModule(types.ModuleType):
        def __setattr__(self, name, value):
            raise RefusesNotes("this module refuses the patch")

    mod = _NoteRefusingModule("pyteman_atomic_victim_notes")
    object.__setattr__(mod, "ok", lambda a: a)
    sys.modules[mod.__name__] = mod
    try:
        with pytest.raises(RefusesNotes) as excinfo:
            activate([make_rule("ok", "r", module=mod.__name__)], log=None,
                     modules=[mod.__name__])
        assert str(excinfo.value) == "this module refuses the patch"
        # Untouched, which is the proof the guard swallowed rather than wrote.
        assert excinfo.value.__notes__ == "not a list"
    finally:
        del sys.modules[mod.__name__]


def test_restore_completes_through_a_refusal_that_is_not_an_exception():
    """_restore catches BaseException, and Exception would not be enough.

    The test above it uses a refusal that derives from Exception, so narrowing
    this handler leaves that one passing while the guarantee is gone. A
    KeyboardInterrupt arriving between two setattr calls is the case the wider
    catch is written for: the operator pressed ctrl-c during a rollback, and
    the half of the module after that entry would otherwise stay wrapped
    forever, in a process that is on its way out and will never revisit it.
    """

    class Interrupts:
        def __setattr__(self, name, value):
            raise KeyboardInterrupt()

    class Accepts:
        x = "WRAPPED"

    accepts = Accepts()
    # reversed(): the interrupting entry goes first, so the entry after it is
    # the one stranded if the handler does not cover it.
    #
    # Caught here rather than left to propagate, because an escaping
    # KeyboardInterrupt is a pytest SESSION abort: the run ends at this line,
    # every test after it is silently skipped, and the summary reads as a
    # shorter passing run rather than as a failure. The guarantee is that
    # nothing escapes, so the test says exactly that.
    try:
        refused = _restore([_entry(accepts, "x", "ORIGINAL", "WRAPPED-X"),
                            _entry(Interrupts(), "y", 1, "WRAPPED-Y")])
    except BaseException as exc:  # pragma: no cover - the assertion is the point
        pytest.fail(f"_restore let {type(exc).__name__} escape, stranding "
                    f"every entry after it")
    assert accepts.x == "ORIGINAL"
    assert len(refused) == 1
    assert isinstance(refused[0][2], KeyboardInterrupt)


class LazyWhenRule:
    """A rule whose `when` is resolved on read, and refuses.

    Every hostile-field fixture above attacks `id`, `module` or `symbol`, which
    is exactly why the planning hole survived: the threat model the fixtures
    encode had three fields in it and the plan reads five. A rule object is
    whatever the programmatic API was handed, so `when` and `fire` are as much
    user code as the other three, and a lazily-resolved `when` backed by a
    store that has gone away is the ordinary way that happens by accident
    rather than by malice.
    """

    id = "lazy-when"
    module = "builtins"
    symbol = "int.bit_length"
    event = "entry"
    action = {"kind": "sleep", "ms": 1}
    fire = {"mode": "always"}

    @property
    def when(self):
        raise RuntimeError("backing store gone")


class NonMappingFireRule:
    """`fire` that is not a mapping, so `.get` is the thing that raises.

    A different mechanism from the property above and the same consequence,
    kept separate because a guard could plausibly cover one and not the other:
    this one fails on an attribute lookup INSIDE the value rather than on the
    read that produced it.
    """

    id = "bad-fire"
    module = "builtins"
    symbol = "int.bit_length"
    event = "entry"
    action = {"kind": "sleep", "ms": 1}
    when = None
    fire = ["mode", "always"]


class NonStringWhenRule:
    """`when` reads cleanly and is not source at all.

    The shape that gets past _compile's own guard. `except SyntaxError` is a
    claim that the SOURCE is invalid, and this is not invalid source, it is not
    source, so compile() raises TypeError through a handler that was never
    about it. A guard narrower than its operation reports nothing, the same way
    a guard wider than its operation reports something untrue.
    """

    id = "int-when"
    module = "builtins"
    symbol = "int.bit_length"
    event = "entry"
    action = {"kind": "sleep", "ms": 1}
    fire = {"mode": "always"}
    when = 5


@pytest.mark.parametrize("rule_cls, exc_type, rule_id", [
    (LazyWhenRule, RuntimeError, "lazy-when"),
    (NonMappingFireRule, AttributeError, "bad-fire"),
    (NonStringWhenRule, TypeError, "int-when"),
])
def test_a_rule_whose_own_fields_refuse_is_still_named(rule_cls, exc_type, rule_id):
    """A field that will not be read must not cost the operator the rule's name.

    These three failed IDENTICALLY before: the exception left Patcher.__init__
    carrying no notes at all, naming no rule out of a whole ruleset, because
    `r.when` and `r.fire` were evaluated as ARGUMENTS and tuple elements
    evaluate left to right, so _describe_rule had not run yet. The same failure
    on `module` arrived fully described, and nothing pointed at the asymmetry
    because every other fixture here reaches this code through fields that read
    cleanly.

    The exception itself is asserted unchanged, not just the note. Naming the
    rule is worth nothing if the reporting swapped out the failure to do it:
    that is the substitution the whole rollback path is written against, and it
    would be a poor place to introduce it.
    """
    with pytest.raises(exc_type) as excinfo:
        Patcher([rule_cls()], None)  # type: ignore[list-item]
    notes = getattr(excinfo.value, "__notes__", [])
    assert any("while planning" in n for n in notes), notes
    assert any(repr(rule_id) in n for n in notes), notes
    # The location too, since _describe_rule renders it and these rules can
    # give it: a note naming the rule but not where it points is one grep
    # short of useful in a ruleset with forty of them.
    assert any("builtins:int.bit_length" in n for n in notes), notes


def test_planning_says_planning_and_not_patching():
    """The two notes are different words on purpose, and the difference is load bearing.

    "while patching" means a callable was being replaced, so the rollback
    disclosure beside it is the operator's account of what was left behind.
    "while planning" means nothing had been touched yet, which tells them there
    is nothing to clean up. Reusing the patching wording here would be a
    smaller diff and would make the note say something false, which is the
    failure mode docs/rules.md is written to prevent.
    """
    before = builtins.__import__
    with pytest.raises(RuntimeError) as excinfo:
        activate([LazyWhenRule()], log=None, modules=["builtins"])  # type: ignore[list-item]
    notes = getattr(excinfo.value, "__notes__", [])
    assert any("while planning" in n for n in notes), notes
    assert not any("while patching" in n for n in notes), notes
    # Through activate() rather than the constructor, so this also pins the
    # claim the note makes: the hook is never installed, because the ruleset
    # died before install_hook was reached.
    assert builtins.__import__ is before


class _Sealable(type):
    """A container that accepts a budget of setattrs and then refuses.

    A metaclass because the container in a real rule is usually a class, and
    `setattr` on a class is what the wrap and the unwrap both do. The budget
    lets one test allow the wrap and refuse the undo, which is the ordering the
    rollback path cannot control and has to survive.

    The budget lives on the container, not here. A counter on the metaclass is
    one counter shared by every container in the module, so a test spends or
    replenishes the budget of whatever runs next and each result depends on the
    order. Per container there is nothing to leak: each test builds its own.
    """

    def __setattr__(cls, name, value):
        budget = cls.__dict__.get("_budget", 0)
        if budget <= 0:
            raise TypeError(f"cannot set {name!r} on a sealed container")
        type.__setattr__(cls, "_budget", budget - 1)
        type.__setattr__(cls, name, value)


def _seal(cls, budget):
    """Set a container's setattr budget without spending any of it.

    `type.__setattr__` goes around the guard, which is also how a test writes
    its own setup: the guard then governs only what the patcher does and the
    fixture is not fighting itself, the same reason the `refusing` module
    fixture above sets its attributes through `object.__setattr__`.
    """
    type.__setattr__(cls, "_budget", budget)


class _HostileActionRule:
    """Passes planning and slot resolution, fails in _make_dispatcher.

    Planning reads `when` and `fire`, and resolution reads `module` and
    `symbol`; the dispatcher build is the first step that reads `action`. A
    rule that answers the first two and raises on the third is how a test
    reaches _patch's handler with an earlier slot already wrapped, which is
    the state the rollback exists for.
    """

    id, module, symbol = "blows-up", "sealedmod", "Victim.m2"
    when, fire = "True", {"mode": "always"}
    event = "entry"

    @property
    def action(self):
        raise RuntimeError("action backing store gone")


def test_a_wrap_the_rollback_could_not_undo_stays_in_the_ledger():
    """A refused restore is still a wrap, so something has to keep naming it.

    The disclosure note already told the operator a callable was left behind.
    That is a sentence on an exception; it is not a handle. _patch builds its
    ledger in a local, and the raise that carries the failure out used to skip
    the line that publishes it, so the entries the rollback could NOT undo
    reached no record at all. The callable stayed wrapped, `_wrapped` was
    empty, and uninstall() therefore reported success with nothing to do: the
    one API for removing the wrap could no longer see it.

    The container is sealed after exactly one setattr, so the first rule wraps
    and the rollback refuses. The second rule fails during _make_dispatcher
    rather than during planning, which is what gets us into _patch's handler
    with work already done.
    """

    class Victim(metaclass=_Sealable):
        def m(self):
            return "original"

        def m2(self):
            return "original2"

    module = types.ModuleType("sealedmod")
    setattr(module, "Victim", Victim)
    original = Victim.__dict__["m"]

    _seal(Victim, 1)
    patcher = Patcher([make_rule("Victim.m", rid="wraps-ok",
                                 module="sealedmod"),
                       _HostileActionRule()], None)  # type: ignore[list-item]
    with pytest.raises(RuntimeError) as excinfo:
        patcher._patch(module, "sealedmod")

    assert _refusal_notes(excinfo.value), getattr(excinfo.value, "__notes__", [])
    assert Victim.__dict__["m"] is not original, "the wrap should have survived"
    # The ledger, not just the note. This is the assertion the old code
    # failed: `_wrapped` was [] while the attribute above was still wrapped.
    assert [(c, n) for c, n, *_ in patcher._wrapped] == [(Victim, "m")]
    # `applied` stays empty, because the wrap was rolled back as far as the
    # container allowed and was never published as an injection that ran.
    assert patcher.applied == []

    # And the handle is a working one: once the container stops refusing,
    # uninstall() finds the entry and puts the original back.
    _seal(Victim, 99)
    assert patcher.uninstall() == []
    assert Victim.__dict__["m"] is original


def test_uninstall_keeps_what_it_could_not_restore_so_a_retry_can_work():
    """The same defect at the other call site, which nobody reported.

    uninstall() cleared `_wrapped` unconditionally after asking _restore to
    empty it. When a container refused, the triple came back in the return
    value and was erased from the ledger in the same breath, so a caller that
    handled the refusal and retried had nothing left to retry FROM. The return
    value is a report; the ledger is the state. Clearing the state on the
    strength of an attempt is what both sites had in common.

    Driven through _wrapped directly rather than through a patch, because what
    is under test is the bookkeeping and not how the entry got there.
    """

    class Victim(metaclass=_Sealable):
        pass

    # Setup goes around the guard, so the container is sealed from the start
    # and the only writes the guard judges are the ones under test.
    patcher = Patcher([], None)
    entry = _entry(Victim, "m", "ORIGINAL", "WRAPPER")
    patcher._wrapped.append(entry)

    refused = patcher.uninstall()
    assert len(refused) == 1 and refused[0][1] == "m"
    assert Victim.__dict__["m"] == "WRAPPER", "the container refused, so it stays"
    # Reported AND retained: the entry is still the ledger's, unchanged.
    assert patcher._wrapped == [entry]

    _seal(Victim, 99)
    assert patcher.uninstall() == []
    assert Victim.__dict__["m"] == "ORIGINAL"
    # Emptied only now, by a setattr that actually returned.
    assert patcher._wrapped == []


class _Plain:
    """A container that just accepts a setattr, to sit between the awkward ones."""


def test_restore_deletes_what_it_restored_and_not_whatever_index_it_held():
    """A stale index deleted the record of a wrap that was never restored.

    The descending walk was chosen so a deletion could not shift an index the
    loop had yet to visit, and that argument only ever covered the loop's OWN
    deletions. `setattr` is user code and can remove entries BELOW the cursor,
    which re-seats every index from the cursor up, so `del entries[i]` reached
    a different entry than the one just put back.

    A retained refusal is what makes it reachable HERE. While every attempt
    succeeded the list shrank in step with the walk and nothing above the
    cursor was left to mis-address, and a kept entry breaks that lockstep. It
    is not the only thing that does: a concurrent _patch reaching its `finally`
    extends the same ledger above the range this walk fixed at entry, and a
    removal below the cursor then slides that published wrap onto an index the
    walk is about to delete, with no refusal involved anywhere. The extend on
    its own strands nothing, the range being built once so an appended entry is
    never visited. The sibling test covers that route. This one holds the
    refusal shape still, because it is the one RT-01 introduced.

    What it costs is the whole point of consuming the ledger on success: the
    entry deleted here belongs to a container that REFUSED, so the callable is
    still wrapped in the process and its original is now recorded nowhere. The
    unfixed walk does not even stop there. It goes on, revisits the restored
    entry at its new index, and empties the list, after which uninstall()
    reports complete success with instrumentation live.
    """

    class Refuses:
        def __setattr__(self, name, value):
            raise RuntimeError("sealed")

    class RemovesAnEarlierEntry:
        """A stand-in for a racing uninstall, made deterministic.

        Doing it from inside __setattr__ puts the mutation exactly where a
        concurrent one would land, between the read of entries[i] and the
        delete, without needing a thread to cooperate.
        """
        done = False

        def __setattr__(self, name, value):
            if not RemovesAnEarlierEntry.done:
                RemovesAnEarlierEntry.done = True
                del entries[0]
            object.__setattr__(self, name, value)

    first, second = _Plain(), _Plain()
    restored = RemovesAnEarlierEntry()
    strand = Refuses()

    entries = [_entry(first, "a", "ORIGINAL-A", "W-A"),
               _entry(second, "b", "ORIGINAL-B", "W-B"),
               _entry(restored, "c", "ORIGINAL-C", "W-C"),
               _entry(strand, "d", "ORIGINAL-D", "W-D")]

    refused = _restore(entries)

    assert [(c, n) for c, n, _ in refused] == [(strand, "d")]
    assert getattr(restored, "c") == "ORIGINAL-C", "the restore itself still runs"
    # The one that matters: the refused entry is the one still wrapped, so it
    # is the one that must survive. Deleting it is unrecoverable, because
    # writing the original back is safe only while the ledger still knows it
    # AND the slot still holds the wrap this entry was written to undo.
    assert any(c is strand for c, *_ in entries), (
        "the strand's record was deleted by a stale index; nothing can "
        f"restore it now. Ledger: {[(type(c).__name__, n) for c, n, *_ in entries]}")
    # And it is genuinely retryable rather than merely present.
    assert [(c, n) for c, n, _ in _restore(entries)] == [(strand, "d")]


def test_restore_does_not_compare_entries_with_equality():
    """Locating the entry again must not hand the loop back to user code.

    The delete cannot use `==`. Comparing the tuples compares their elements,
    a container's __eq__ is the same user code the loop is written to survive,
    and raising there escapes the else branch and aborts the unwind, stranding
    every entry the walk had not yet reached.

    Building that takes care, because `==` is not always a comparison. CPython
    short-circuits on identity before it dispatches __eq__, so handing it the
    entry just restored proves nothing: that is precisely the case where `==`
    and `is` agree without ever consulting the container. The distinction only
    exists once index i has been re-seated onto a DIFFERENT entry, so that is
    what this arranges. It does so by publishing from underneath rather than by
    refusing, because a concurrent _patch reaching its `finally` extends the
    same ledger and is the second way an entry outlives the walk that started
    below it; the fix is not owed solely to keeping refusals.
    """

    class RaisesOnCompare:
        def __eq__(self, other):
            raise AssertionError("_restore compared entries with ==")

    published = RaisesOnCompare()

    class PublishesAndRemoves:
        """Two racing actors at the one moment they are observable.

        A _patch finishing appends its wrap above the range this walk fixed at
        entry, and an unrelated uninstall drops an entry below the cursor. The
        net effect is the one that matters: index i now addresses the published
        entry instead of this one.
        """
        done = False

        def __setattr__(self, name, value):
            if not PublishesAndRemoves.done:
                PublishesAndRemoves.done = True
                # Built by hand rather than through _entry: this entry sits
                # above the range the walk fixed at entry, so nothing ever
                # reads its slot, and leaving `published` bare is what the
                # untouched assertion at the end of this test checks.
                entries.append((published, "p", "ORIGINAL-P", "W-P", True))
                del entries[0]
            object.__setattr__(self, name, value)

    dropped, middle = _Plain(), _Plain()
    mover = PublishesAndRemoves()
    entries = [_entry(dropped, "a", "ORIGINAL-A", "W-A"),
               _entry(middle, "b", "ORIGINAL-B", "W-B"),
               _entry(mover, "m", "ORIGINAL-M", "W-M")]

    # Under `==` this call does not return at all: the comparison at i reaches
    # RaisesOnCompare and the AssertionError leaves _restore, so `middle` is
    # never reached and the unwind stops half done.
    assert _restore(entries) == []

    assert getattr(mover, "m") == "ORIGINAL-M"
    assert getattr(middle, "b") == "ORIGINAL-B", "the walk ran to completion"
    # The published entry is untouched and still recorded: it was never in the
    # range this walk undertook to fix, so leaving it for the next uninstall is
    # correct, and it is the only thing left. Spelled without `==` on the list,
    # so that a failure here reports the ledger rather than tripping
    # RaisesOnCompare on its way to building the message.
    assert len(entries) == 1, [n for _, n, *_ in entries]
    assert entries[0][0] is published
    assert not hasattr(published, "p")


def test_restore_survives_a_ledger_that_shrank_to_the_cursor():
    """The bounds half of the guard, which the identity half cannot cover.

    `entries[i] is entry` cannot run at all once the list is no longer than i:
    the subscript raises IndexError first, and where that lands decides what it
    costs. Only uninstall() can reach it. _restore's other call site is _patch,
    which hands it the method-local list it publishes in its `finally`, so no
    user code holds a reference to shrink it; the shared ledger is uninstall's.
    activate() calls uninstall() from inside its own handler and survives the
    raise, keeping the rule failure and attaching the unwind's as a note, but
    it buys the save with an empty refusal list, so its disclosure never names
    what is still wrapped. Holders of the Patcher from install() and
    force_patch_module() invoke uninstall() themselves and see it raise.

    The window is worth naming precisely, because it is narrower than "the list
    shrank". Each iteration opens with an unguarded `entries[i]`, so a shrink
    leaving the list shorter than that raises on the NEXT pass whatever this
    guard does. The guard decides exactly one shape: len == i, index i one past
    the end while i-1 is still valid, so the walk goes on and finishes the
    unwind. A single removal produces it only while the walk is in lockstep,
    with nothing surviving above the cursor to hold the length up, which is
    what this test arranges and both siblings deliberately break.

    Neither sibling reaches this. Both leave len > i at the moment of the test,
    so the identity half decides there and the bounds half is never consulted.
    """
    writes = []

    class RemovesTheOnlyEntryBelow:
        done = False

        def __setattr__(self, name, value):
            writes.append(value)
            if not RemovesTheOnlyEntryBelow.done:
                RemovesTheOnlyEntryBelow.done = True
                del entries[0]
            object.__setattr__(self, name, value)

    dropped, mover = _Plain(), RemovesTheOnlyEntryBelow()
    entries = [_entry(dropped, "a", "ORIGINAL-A", "W-A"),
               _entry(mover, "m", "ORIGINAL-M", "W-M")]

    # The walk opens at i=1; the removal leaves len 1, so entries[1] is off the
    # end. Without the bounds test this raises IndexError instead of returning.
    assert _restore(entries) == []

    assert getattr(mover, "m") == "ORIGINAL-M"
    assert entries == [], "the walk still consumed everything it restored"
    # The documented cost of a shift used to be a SECOND write: sliding the
    # entry down to an index the walk had yet to visit meant it was restored
    # again, over whatever held the slot by then. Recording the wrapper in the
    # entry retired that. The second visit reads the slot, finds the original
    # rather than the wrapper this entry owns, and releases instead of writing,
    # so the shift now costs a wasted read. Measured rather than asserted in
    # prose, because it is the difference between one write and two.
    assert writes == ["ORIGINAL-M"]


# --- uninstall really gives the process back -------------------------------
#
# Everything above is about a FAILED activation unwinding. These are about a
# successful one being taken back: what uninstall owes the process once the
# instrumentation has done its job. The two are the same machinery seen from
# opposite ends, which is why they share a file.


@pytest.fixture
def inheriting():
    """A module whose Sub does NOT define the method a rule can still name.

    `_patch` gates on hasattr, which walks the MRO, so `Sub.meth` is a legal
    target even though the function lives on Base. That is the shape the undo
    has to tell from an ordinary one: the patch CREATES `meth` in Sub's own
    namespace, and putting the original back there with setattr would make the
    accident permanent.
    """
    mod = types.ModuleType(MODNAME4)

    class Base:
        def meth(self):
            return "base"

    class Sub(Base):
        pass

    setattr(mod, "Base", Base)
    setattr(mod, "Sub", Sub)
    sys.modules[MODNAME4] = mod
    try:
        yield mod
    finally:
        del sys.modules[MODNAME4]


def test_install_hook_twice_leaves_one_hook_and_one_real_import():
    real = builtins.__import__
    p = Patcher([], None)
    try:
        p.install_hook()
        hook = builtins.__import__
        p.install_hook()

        # The second call used to wrap the first, saving OUR hook as the thing
        # to put back. One uninstall then restored a hook, not the import.
        assert builtins.__import__ is hook, "the second call installed a second hook"

        assert p.uninstall() == []
        assert builtins.__import__ is real, "a hook outlived its only uninstall"
    finally:
        builtins.__import__ = real


def test_uninstall_out_of_order_is_refused_before_anything_moves(victim):
    real = builtins.__import__
    outer = Patcher([make_rule("ok")], None)
    inner = Patcher([], None)
    try:
        outer.install_hook()
        outer.force_patch_module(MODNAME)
        outer_hook = builtins.__import__
        inner.install_hook()
        inner_hook = builtins.__import__
        ledger = list(outer._wrapped)

        # Abstaining here is not enough. `inner` saved OUR hook as its
        # _orig_import, so an outer that merely declines to touch the slot gets
        # resurrected by the inner one's own perfectly correct uninstall.
        with pytest.raises(UninstallOrderError):
            outer.uninstall()

        # Refused before the first mutation, so it is a no-op and not a
        # half-uninstalled Patcher: hook, ledger and wraps all as they were.
        assert builtins.__import__ is inner_hook
        assert outer._wrapped == ledger
        assert outer._hook is outer_hook
        assert getattr(victim, "ok")(3) == 1, "the refusal unwrapped something"

        # And the refusal is not terminal. LIFO order works, including the
        # retry of the very call that was refused.
        assert inner.uninstall() == []
        assert builtins.__import__ is outer_hook
        assert outer.uninstall() == []
        assert builtins.__import__ is real
        assert getattr(victim, "ok")(3) == 3
    finally:
        builtins.__import__ = real


def test_a_foreign_hook_that_delegates_to_ours_survives_and_ours_goes_inert(victim2):
    real = builtins.__import__
    p = Patcher([make_rule("ok", module=MODNAME2)], None)
    seen = []
    try:
        p.install_hook()
        ours = builtins.__import__

        def foreign(name, *a, **k):
            seen.append(name)
            return ours(name, *a, **k)

        builtins.__import__ = foreign
        assert p.uninstall() == []

        # We do not own this slot any more, so we leave it alone. Writing
        # _orig_import back here would delete a third party's hook to tidy up
        # our own, and theirs may be the one the process depends on.
        assert builtins.__import__ is foreign

        # Our closure is still reachable, inside theirs, and cannot be removed
        # from it. So it is retired instead: it delegates, and applies nothing.
        builtins.__import__(MODNAME2)
        assert seen == [MODNAME2], "the foreign hook stopped running"
        assert getattr(victim2, "ok")(3) == 3, "the retired hook patched a module"
        assert p._wrapped == []
    finally:
        builtins.__import__ = real


def test_a_foreign_hook_that_simply_replaced_ours_is_left_alone():
    real = builtins.__import__
    p = Patcher([], None)
    try:
        p.install_hook()

        def foreign(name, *a, **k):
            return real(name, *a, **k)

        # No delegation this time: they dropped our hook entirely. Same
        # obligation, and worth its own test because the delegating case can
        # pass by accident when the chain happens to keep our closure alive.
        builtins.__import__ = foreign
        assert p.uninstall() == []
        assert builtins.__import__ is foreign
    finally:
        builtins.__import__ = real


def test_a_slot_taken_over_after_we_wrapped_it_is_released_not_refused(victim):
    p = Patcher([make_rule("ok")], None)
    p.force_patch_module(MODNAME)
    assert getattr(victim, "ok")(3) == 1

    def other_library(a):
        return "other"

    setattr(victim, "ok", other_library)

    # Not ours to give back: restoring would delete whatever replaced us, and
    # the replacement is the newer decision. Letting go is the job done, so it
    # is reported as a success and not as a refusal anyone has to read.
    assert p.uninstall() == []
    assert getattr(victim, "ok") is other_library, "we overwrote the newer callable"
    assert p._wrapped == [], "a released entry was kept for a later retry"


def test_an_inherited_method_is_not_pinned_onto_the_subclass(inheriting):
    Base = getattr(inheriting, "Base")
    Sub = getattr(inheriting, "Sub")
    assert "meth" not in vars(Sub)

    p = Patcher([make_rule("Sub.meth", module=MODNAME4)], None)
    p.force_patch_module(MODNAME4)
    assert "meth" in vars(Sub), "the patch creates the entry, which is the hazard"
    assert Sub().meth() == 1

    assert p.uninstall() == []
    # setattr would leave Base's ORIGINAL function frozen into Sub, which reads
    # as restored and is not: the link to Base is gone, silently and forever.
    assert "meth" not in vars(Sub), "uninstall pinned an inherited method"

    def replacement(self):
        return "base-v2"

    setattr(Base, "meth", replacement)
    assert Sub().meth() == "base-v2", "the subclass stopped inheriting"


def test_applied_is_a_history_not_a_live_inventory(victim):
    p = Patcher([make_rule("ok")], None)
    p.force_patch_module(MODNAME)
    assert p.applied == [f"{MODNAME}:ok"]

    # Idempotent: the already-wrapped guard skips, so the history does not gain
    # an event for a patch that did not happen.
    p.force_patch_module(MODNAME)
    assert p.applied == [f"{MODNAME}:ok"]

    assert p.uninstall() == []
    assert getattr(victim, "ok")(3) == 3
    # Deliberately not cleared. `applied` answers what this Patcher ever
    # wrapped, which is what a report of a finished run needs; the live
    # inventory is _wrapped, and that one IS empty.
    assert p.applied == [f"{MODNAME}:ok"]
    assert p._wrapped == []

    # Uninstalling again is a no-op rather than an error, so a caller with a
    # finally block does not have to remember whether it already ran.
    assert p.uninstall() == []
    assert getattr(victim, "ok")(3) == 3

    # A genuine second patch, so a second occurrence is the history being
    # accurate about two separate wraps rather than double-counting one.
    p.force_patch_module(MODNAME)
    assert p.applied == [f"{MODNAME}:ok"] * 2
    assert getattr(victim, "ok")(3) == 1
    assert p.uninstall() == []
    assert getattr(victim, "ok")(3) == 3


# --- the two shapes the first cut of the undo got wrong ---------------------
#
# Both were found by review rather than by the tests above, and both are silent
# in the worst way: one destroys the original and reports a clean restore, the
# other refuses an uninstall on behalf of a Patcher that has already left.

def test_a_retired_pyteman_hook_does_not_wedge_the_patcher_under_it():
    real = builtins.__import__
    p1 = Patcher([], None)
    p2 = Patcher([], None)
    try:
        p1.install_hook()
        p2.install_hook()
        h2 = builtins.__import__

        def stranger(name, *a, **k):
            return h2(name, *a, **k)

        # A third party wraps p2's hook, p2 releases the slot to it, and then
        # the third party unwinds correctly, putting h2 back. h2 is now inert:
        # p2._hook is None, so p2 can never be asked to clear it again.
        builtins.__import__ = stranger
        assert p2.uninstall() == []
        builtins.__import__ = h2

        # Classifying on the MARKER alone refuses here, and the refusal can
        # never be lifted by anyone: p1 is wedged, and because the refusal
        # comes first, its WRAPS are stuck too.
        assert p1.uninstall() == []
        assert p1._hook is None

        # h2 stays in the slot, which is the conservative branch doing its job:
        # p1 cannot tell a retired pyteman hook from any other third party, and
        # guessing wrong deletes someone's live instrumentation. Both closures
        # are inert by now, so the chain is a pass-through to the real import.
        assert builtins.__import__ is h2
        assert builtins.__import__("sys") is sys
    finally:
        builtins.__import__ = real


def test_a_mock_standing_in_for_import_is_a_stranger_not_a_nested_patcher():
    real = builtins.__import__
    p = Patcher([], None)
    try:
        p.install_hook()

        class Synthesising:
            """Answers every attribute, as MagicMock does."""

            def __getattr__(self, name):
                return Synthesising()

            def __call__(self, name, *a, **k):
                return real(name, *a, **k)

        builtins.__import__ = Synthesising()
        live = builtins.__import__

        # It answers the marker probe with a truthy object. Only asking the
        # claimed owner whether this is still ITS hook tells the two apart.
        assert getattr(live, "_pyteman_patcher", None) is not None
        assert p.uninstall() == []
        assert builtins.__import__ is live, "we deleted a third party's hook"
    finally:
        builtins.__import__ = real


def test_a_slot_is_restored_by_setattr_and_not_emptied_by_delattr():
    mod = types.ModuleType("pyteman_atomic_victim_slots")

    class Base:
        __slots__ = ("handler",)

    class Svc(Base):
        pass

    def real_handler(x):
        return x

    svc = Svc()
    svc.handler = real_handler
    setattr(mod, "svc", svc)
    sys.modules[mod.__name__] = mod
    try:
        # The hazard: hasattr finds the slot, vars(svc) does not list it, so
        # "not in __dict__" reads as "inherited" when it is the container's own
        # storage held by a data descriptor.
        assert "handler" not in vars(svc)
        assert hasattr(svc, "handler")

        p = Patcher([make_rule("svc.handler", module=mod.__name__)], None)
        p.force_patch_module(mod.__name__)
        assert svc.handler(3) == 1

        assert p.uninstall() == []
        # delattr here CLEARS the slot: the original is gone from the process
        # and uninstall still returns [], a clean restore that destroyed data.
        assert svc.handler is real_handler, "the original was destroyed"
    finally:
        del sys.modules[mod.__name__]


def test_a_property_without_a_deleter_is_restored_rather_than_refused():
    mod = types.ModuleType("pyteman_atomic_victim_prop")

    def real_handler(x):
        return x

    class Holder:
        def __init__(self):
            self._h = real_handler

        @property
        def handler(self):
            return self._h

        @handler.setter
        def handler(self, value):
            self._h = value

    holder = Holder()
    setattr(mod, "holder", holder)
    sys.modules[mod.__name__] = mod
    try:
        p = Patcher([make_rule("holder.handler", module=mod.__name__)], None)
        p.force_patch_module(mod.__name__)
        assert holder.handler(3) == 1

        # delattr raises for want of a deleter, which becomes a refusal that is
        # retained and re-reported forever, for a slot a setattr restores.
        assert p.uninstall() == []
        assert holder.handler is real_handler
        assert p._wrapped == []
    finally:
        del sys.modules[mod.__name__]


# ---------------------------------------------------------------------------
# RT-02: more than one rule on one point.
#
# Before this, the patch loop skipped any callable already carrying a pyteman
# marker, so the SECOND rule aimed at a point was dropped without a word and
# the ruleset silently did something other than what it said. The tests below
# are about the composition contract that replaced that skip: what order the
# rules run in, what each one sees, and what stops the rest.
# ---------------------------------------------------------------------------

MODNAME5 = "pyteman_atomic_victim_composed"
MODNAME6 = "pyteman_atomic_victim_composed_two"


class Recorder:
    """A FiringLog seam that keeps what each rule saw at the moment it fired.

    The composition contract is mostly about the ORDER rules run in and the
    context each one is handed, and both are invisible in a return value alone.
    run_action already reports every firing here, so the tests observe through
    the seam the Patcher uses in production rather than by reading state off
    the wrapper, which is how a test ends up pinned to an implementation it was
    supposed to outlive.
    """

    def __init__(self):
        self.seen = []
        self.terminals = []
        self._seq = 0

    def record(self, rule, ctx, note=None, outcome=None,
               phase="start", attempt=None, status=None):
        # Snapshotted, not referenced: one ctx dict serves every rule on the
        # slot, so keeping it would leave each entry describing the LAST
        # rule's view of the call.
        self._seq += 1
        if phase == "end":
            # Kept rather than dropped, so a terminal record can still be
            # asserted on from here, but held apart from `seen`: these tests
            # are about the ORDER firings happen in, and folding an outcome
            # record into that list would double every entry.
            self.terminals.append((rule.id, attempt, status, outcome))
        else:
            self.seen.append((rule.id, ctx.get("result"), ctx.get("exc")))
            attempt = self._seq
        return RecordId("recorder", os.getpid(), self._seq, attempt)

    @property
    def ids(self):
        return [rid for rid, _, _ in self.seen]


def crule(rid, event="entry", action=None, fire=None, symbol="f",
          module=MODNAME5, when=None):
    """A rule with every composition-relevant field open.

    make_rule above fixes the event and the action, which is what the atomicity
    tests need and the exact opposite of what these do.
    """
    return Rule(id=rid, module=module, symbol=symbol, event=event,
                action=action or {"kind": "return_value", "value": rid},
                fire=fire or {"mode": "always"}, when=when)


def composed(body=None, name=MODNAME5):
    """A victim module whose callable can be told to raise."""
    mod = types.ModuleType(name)
    setattr(mod, "f", body or (lambda *a, **k: "real"))
    sys.modules[name] = mod
    return mod


@pytest.fixture
def composed_victim():
    mod = composed()
    try:
        yield mod
    finally:
        sys.modules.pop(MODNAME5, None)
        sys.modules.pop(MODNAME6, None)


def test_an_entry_and_an_exit_on_one_point_both_fire_under_one_wrapper(composed_victim):
    """The case the old skip dropped, and the ledger shape that replaced it.

    Both rules are recorded in `applied`, because both were installed; the
    ledger holds ONE entry, because one attribute was written. Those two counts
    differing is the point of a dispatcher: `applied` answers "what is this run
    doing", the ledger answers "what has to be put back".
    """
    log = Recorder()
    p = Patcher([crule("in", "entry", {"kind": "sleep", "ms": 0}),
                 crule("out", "exit", {"kind": "return_value", "value": "O"})], log)
    p.force_patch_module(MODNAME5)

    assert p.applied == [f"{MODNAME5}:f", f"{MODNAME5}:f"]
    assert len(p._wrapped) == 1
    assert composed_victim.f(1) == "O"
    assert log.ids == ["in", "out"]


def test_entry_rules_fire_in_ruleset_order_and_the_first_return_ends_the_call(composed_victim):
    """Declared order is the whole ordering contract; there is no priority field.

    Reversing the list has to reverse the winner, otherwise the order that made
    it pass was some property of the rules rather than where they sit. The
    fixture is requested for its teardown alone: each iteration needs a module
    nobody has patched yet, so the loop builds its own.
    """
    for order, winner in ((("a", "b"), "a"), (("b", "a"), "b")):
        composed()
        log = Recorder()
        p = Patcher([crule(rid) for rid in order], log)
        p.force_patch_module(MODNAME5)
        assert sys.modules[MODNAME5].f(1) == winner
        # The loser never ran at all, which is stronger than "its value lost".
        assert log.ids == [winner]


def test_exit_rules_fire_in_ruleset_order_and_the_last_override_wins(composed_victim):
    """An exit does not short-circuit: the call already happened.

    Each exit sees the result the one before it left, so the chain is visible
    in what they were handed and not only in what came out.
    """
    log = Recorder()
    p = Patcher([crule("first", "exit", {"kind": "return_value", "value": "F"}),
                 crule("second", "exit", {"kind": "return_value", "value": "S"})], log)
    p.force_patch_module(MODNAME5)

    assert composed_victim.f(1) == "S"
    assert log.ids == ["first", "second"]
    # first was handed the body's result, second was handed first's override.
    assert [result for _, result, _ in log.seen] == ["real", "F"]


def test_an_entry_return_skips_the_body_and_every_exit(composed_victim):
    """An exit rule is a statement about a call that happened.

    The body is not called, so there is no exit to run, and nothing arranges
    that: returning out of the entry loop is BEFORE the try, so there is no
    finally to fire on a body that was never entered.
    """
    calls = []
    composed(lambda *a, **k: calls.append(1))
    log = Recorder()
    p = Patcher([crule("stop", "entry", {"kind": "return_value", "value": "S"}),
                 crule("never", "exit", {"kind": "return_value", "value": "N"})], log)
    p.force_patch_module(MODNAME5)

    assert sys.modules[MODNAME5].f(1) == "S"
    assert calls == []
    assert log.ids == ["stop"]


def test_an_entry_that_raises_leaves_the_body_and_the_exits_unrun(composed_victim):
    """Same stop, reached the other way, and the same reason it needs no code."""
    calls = []
    composed(lambda *a, **k: calls.append(1))
    log = Recorder()
    p = Patcher([crule("boom", "entry", {"kind": "raise", "exc": "KeyError"}),
                 crule("never", "exit", {"kind": "return_value", "value": "N"})], log)
    p.force_patch_module(MODNAME5)

    with pytest.raises(KeyError):
        sys.modules[MODNAME5].f(1)
    assert calls == []
    assert log.ids == ["boom"]


def test_every_exit_reached_sees_the_body_exception_and_cannot_swallow_it(composed_victim):
    """The failing path is where an exit rule is most tempting and least allowed.

    Composition did not come with permission to suppress. Both exits run, both
    are handed the ORIGINAL exception and a result of None rather than a
    half-built value, and the return_value each asks for is discarded instead
    of turning a crash into a plausible answer.
    """
    def body(*a, **k):
        raise ValueError("from the body")

    composed(body)
    log = Recorder()
    p = Patcher([crule("first", "exit", {"kind": "return_value", "value": "F"}),
                 crule("second", "exit", {"kind": "return_value", "value": "S"})], log)
    p.force_patch_module(MODNAME5)

    with pytest.raises(ValueError, match="from the body"):
        sys.modules[MODNAME5].f(1)
    assert log.ids == ["first", "second"]
    assert [result for _, result, _ in log.seen] == [None, None]
    assert {type(exc) for _, _, exc in log.seen} == {ValueError}


def test_one_exits_condition_cannot_hide_the_body_error_from_the_next(composed_victim):
    """The same contract as above, attacked from inside a `when` rather than an action.

    An action cannot suppress the body's exception, and the test above pins
    that. A CONDITION reached the same place by another door: eval_expr used
    to hand the per-call ctx to eval as the LOCALS mapping, so an assignment
    expression in one rule's `when` wrote into the very dict the next rule
    reads its `exc` out of. Seeding `exc` once above the exit loop was enough
    for every rule that does not write, and left the rules after one that does
    reading a value the body never raised.

    `clobber` fires on a condition that is true and destructive at once, and
    `reader` asks the only question that tells the two worlds apart. It firing
    is the assertion; the recorded exception is what makes it the RIGHT one,
    since a `reader` that fired on some other truthy leftover would prove
    nothing. What `clobber` itself sees is asserted too, and it is now the
    body's exception as well: CFG-02 evaluates conditions against a namespace
    built from ctx rather than against ctx itself, so the write has nowhere to
    land and a rule no longer reads back what it wrote. That was the piece
    this docstring used to record as tracked separately; it is closed here.
    """
    def body(*a, **k):
        raise ValueError("from the body")

    composed(body)
    log = Recorder()
    p = Patcher([crule("clobber", "exit", when="(exc := None) is None"),
                 crule("reader", "exit", when="exc is not None")], log)
    p.force_patch_module(MODNAME5)

    with pytest.raises(ValueError, match="from the body"):
        sys.modules[MODNAME5].f(1)
    assert log.ids == ["clobber", "reader"], \
        "an exit rule's condition hid the body error from the rules after it"
    saw = {rid: exc for rid, _, exc in log.seen}
    assert type(saw["reader"]) is ValueError
    assert type(saw["clobber"]) is ValueError


def test_an_exit_that_raises_stops_the_later_exits_and_chains_onto_the_body_error(composed_victim):
    """The injected exception replaces the body's, and says what it replaced.

    Nothing in the dispatcher builds that chain. Raising inside the finally
    while an exception is in flight is what sets __context__, so the contract
    asks for ordinary Python here and ordinary Python is what delivers it.
    """
    def body(*a, **k):
        raise ValueError("from the body")

    composed(body)
    log = Recorder()
    p = Patcher([crule("thrower", "exit", {"kind": "raise", "exc": "KeyError"}),
                 crule("never", "exit", {"kind": "return_value", "value": "N"})], log)
    p.force_patch_module(MODNAME5)

    with pytest.raises(KeyError) as excinfo:
        sys.modules[MODNAME5].f(1)
    assert isinstance(excinfo.value.__context__, ValueError)
    assert log.ids == ["thrower"]


def test_an_exit_that_raises_after_a_clean_body_chains_onto_nothing(composed_victim):
    """The same stop, and deliberately NOT the same chain.

    Pinned separately from the failing-body case because the two differ in a
    way the phrase "ordinary Python chaining" hides. __context__ is set by
    raising while an exception is in flight, and after a callable that
    returned there is none, so it stays None. A test that only ever exercised
    the failing path would let docs promise a chain that this path cannot
    produce.
    """
    composed(lambda *a, **k: "clean")
    log = Recorder()
    p = Patcher([crule("thrower", "exit", {"kind": "raise", "exc": "KeyError"}),
                 crule("never", "exit", {"kind": "return_value", "value": "N"})], log)
    p.force_patch_module(MODNAME5)

    with pytest.raises(KeyError) as excinfo:
        sys.modules[MODNAME5].f(1)
    assert excinfo.value.__context__ is None
    assert log.ids == ["thrower"]


# The two tests above pin the ACTION door on both body paths. This one pins all
# three doors at once, and the reason it is worth its overlap is that the other
# two are not actions at all: `when` and a once_per `key` run inside _gate,
# BEFORE run_action has recorded anything, so they leave the same replaced
# exception behind with no firing record to explain it. Documenting that the
# injected exception is the one that leaves the call is a promise about all
# three, and only one of them was pinned.
_EXIT_DOORS = [
    # extra crule kwargs, the type the door raises, and the (rule id, terminal
    # status) pairs the firing log should hold afterwards
    pytest.param({"when": "result.anything"}, AttributeError, [], id="when"),
    pytest.param({"fire": {"mode": "once_per", "key": "result.anything"}},
                 AttributeError, [], id="key"),
    pytest.param({"action": {"kind": "raise", "exc": "KeyError"}},
                 KeyError, [("thrower", "raised")], id="action"),
]


@pytest.mark.parametrize("kwargs,injected,firings", _EXIT_DOORS)
@pytest.mark.parametrize("body_raises", [True, False],
                         ids=["body-raises", "body-returns"])
def test_an_exit_rule_that_raises_anywhere_replaces_the_call_s_own_outcome(
        composed_victim, kwargs, injected, firings, body_raises):
    """The documented behaviour, held where it is decided rather than described.

    `result` is None once the body has raised and is the body's value once it
    has returned, so `result.anything` raises on either path, which is what
    lets one expression exercise the condition door and the key door without
    either case being a special construction.

    __context__ is asserted by identity and not by type: the promise in the
    docs is that the operator's own exception is still reachable, and an
    equally-typed stand-in would satisfy `isinstance` while losing it.
    """
    own = ValueError("the workload's own failure")

    def body(*a, **k):
        if body_raises:
            raise own
        return "clean"

    composed(body)
    log = Recorder()
    p = Patcher([crule("thrower", "exit", **kwargs),
                 crule("never", "exit", {"kind": "return_value", "value": "N"})],
                log)
    p.force_patch_module(MODNAME5)

    with pytest.raises(injected) as excinfo:
        sys.modules[MODNAME5].f(1)

    # Identity, both ways round: after a body that raised the operator's own
    # exception is still reachable as the context, and after one that returned
    # there was nothing in flight for Python to chain onto.
    assert excinfo.value.__context__ is (own if body_raises else None)
    # Exact, not a membership test: it pins that `never` did not run after the
    # raising rule, AND that the gate doors record nothing at all, because the
    # start record is written inside run_action and neither of them reaches it.
    # The docs must not offer a firing record as the place to look for those
    # two. The terminal is pinned with its status, so the docs' claim that a
    # deliberate raise is logged under `raised` has a test behind it.
    assert log.ids == [rid for rid, _ in firings]
    assert [(t[0], t[2]) for t in log.terminals] == firings


def test_a_rule_skipped_by_a_short_circuit_does_not_advance_its_own_countdown(composed_victim):
    """Each rule counts its OWN reaches, and a reach it never got does not count.

    The discriminating call is the third. `late` has been reached twice by then
    and fires on its third, so a counter shared across the slot, or one bumped
    for a rule the short-circuit jumped over, brings it forward to call three.
    Reading it off the schedule rather than off the state keeps the assertion
    about behaviour.
    """
    log = Recorder()
    p = Patcher([crule("early", fire={"mode": "countdown", "n": 1}),
                 crule("late", fire={"mode": "countdown", "n": 2})], log)
    p.force_patch_module(MODNAME5)
    f = composed_victim.f

    # Call 2 fires `early` and never reaches `late`, so `late`'s third reach
    # lands on call 4 rather than call 3.
    assert [f(1) for _ in range(4)] == ["real", "early", "real", "late"]
    assert log.ids == ["early", "late"]


def test_two_symbols_resolving_to_one_attribute_land_in_one_dispatcher(composed_victim):
    """Grouping is by the slot the rules resolve to, never by the text they used.

    `alias.f` and `f` are one attribute here. Keyed on the spelling, this builds
    two dispatchers and the second setattr drops the first, which loses a rule
    exactly the way the skip used to and leaves `applied` claiming otherwise.
    """
    setattr(composed_victim, "alias", composed_victim)
    log = Recorder()
    p = Patcher([crule("direct", "entry", {"kind": "sleep", "ms": 0}, symbol="f"),
                 crule("aliased", "exit", {"kind": "return_value", "value": "A"},
                       symbol="alias.f")], log)
    p.force_patch_module(MODNAME5)

    assert len(p._wrapped) == 1
    assert composed_victim.f(1) == "A"
    assert log.ids == ["direct", "aliased"]


def test_repatching_the_same_module_adds_no_second_wrapper_and_no_extra_firings(composed_victim):
    """The guarantee the old skip was written for, kept once the skip is gone.

    It used to fall out of "this callable is already marked". That answer also
    excluded every other rule and every other Patcher, so it had to go, and the
    idempotence it was really protecting now rests on asking WHO owns the slot
    and recognising the answer as ourselves.

    The entry rule sleeps rather than returning, and that is the whole point of
    the firing assertion. An entry `return_value` short-circuits, so under a
    double wrap the outer dispatcher would answer first and the log would read
    `["a"]` either way: the assertion would hold while the thing it is named
    for was broken. A rule that lets the body through means a second wrapper
    shows up as a second firing of BOTH rules.
    """
    log = Recorder()
    p = Patcher([crule("a", action={"kind": "sleep", "ms": 0}),
                 crule("b", "exit", {"kind": "return_value", "value": "B"})], log)
    p.force_patch_module(MODNAME5)
    first = composed_victim.f

    p.force_patch_module(MODNAME5)
    assert composed_victim.f is first
    assert len(p._wrapped) == 1
    assert p.applied == [f"{MODNAME5}:f", f"{MODNAME5}:f"]

    assert composed_victim.f(1) == "B"
    assert log.ids == ["a", "b"]  # once per rule per call, not once per patch


def test_a_second_patcher_over_a_live_dispatcher_is_refused_and_rolls_itself_back(composed_victim):
    """Refused with a diagnostic, where it used to be discarded in silence.

    The second Patcher previously recorded an empty `applied`, published an
    empty ledger and returned success on instrumentation it had not installed,
    so a run could report a ruleset it never applied. The rollback is what
    makes the refusal safe to act on: the slot this call DID take is released,
    and the one the first Patcher owns is untouched.
    """
    setattr(composed_victim, "g", lambda *a, **k: "real-g")
    g_before = composed_victim.g

    p1 = Patcher([crule("one")], None)
    p1.force_patch_module(MODNAME5)
    dispatcher = composed_victim.f

    # `g` is free and comes first, `f` is owned and comes second, so the refusal
    # arrives with one of this call's own slots already written.
    p2 = Patcher([crule("mine", symbol="g"), crule("theirs", symbol="f")], None)
    with pytest.raises(SlotOwnershipError) as excinfo:
        p2.force_patch_module(MODNAME5)

    message = str(excinfo.value)
    assert MODNAME5 in message and "f" in message
    assert composed_victim.g is g_before
    assert composed_victim.f is dispatcher
    assert p2._wrapped == []
    assert composed_victim.f(1) == "one"
    assert p1.uninstall() == []


def test_two_patchers_on_disjoint_targets_do_not_refuse_each_other(composed_victim):
    """The refusal is about one slot, not about the presence of another Patcher.

    Without this, "is anybody else patching" would be an easy and wrong reading
    of the rule, and it would break the independent-hook ordering the uninstall
    tests above rely on.
    """
    mod2 = composed(name=MODNAME6)
    p1 = Patcher([crule("one")], None)
    p1.force_patch_module(MODNAME5)
    p2 = Patcher([crule("two", symbol="f", module=MODNAME6)], None)
    p2.force_patch_module(MODNAME6)

    assert composed_victim.f(1) == "one"
    assert mod2.f(1) == "two"
    assert p2.uninstall() == []
    assert p1.uninstall() == []


def test_a_duplicate_rule_id_is_refused_before_anything_is_patched(composed_victim):
    """load_rules refuses this at the file; the programmatic API is a second door.

    Constructor-time, so the refusal cannot be half applied: an id keys every
    record a rule writes to the firing log, and two rules answering to one id
    make a run's own record unreadable after the fact, when it is too late to
    notice.
    """
    before = composed_victim.f
    with pytest.raises(RuleError) as excinfo:
        Patcher([crule("same"), crule("same", "exit")], None)
    assert "id is already used" in str(excinfo.value)
    assert composed_victim.f is before


def test_two_rules_with_one_content_and_different_ids_are_two_rules(composed_victim):
    """Deduplication is by id and stops there.

    Identical bodies under different ids are how a ruleset says "do this twice",
    most visibly with sleep or barrier actions, so collapsing them by content
    would quietly halve a delay the author asked for.
    """
    log = Recorder()
    action = {"kind": "sleep", "ms": 0}
    p = Patcher([crule("a", "entry", dict(action)),
                 crule("b", "entry", dict(action))], log)
    p.force_patch_module(MODNAME5)

    assert composed_victim.f(1) == "real"
    assert log.ids == ["a", "b"]


def test_uninstall_puts_the_real_callable_back_in_one_write(composed_victim):
    """The reason this is a dispatcher and not a stack of nested wrappers.

    N rules leave one entry, so the slot goes back to the user's callable in a
    single write. Nested wrappers would leave N entries on one attribute, where
    a refusal partway through the unwind can settle at a depth that is neither
    the patched state nor the original one.
    """
    original = composed_victim.f
    p = Patcher([crule("a"), crule("b", "exit"), crule("c", "exit")], None)
    p.force_patch_module(MODNAME5)
    assert composed_victim.f is not original

    assert p.uninstall() == []
    assert composed_victim.f is original
    assert p._wrapped == []


def test_a_retired_dispatcher_left_on_some_other_name_does_not_wedge_the_next_patcher(composed_victim):
    """Ownership is a live relationship, not a stamp a callable carries forever.

    `g` is aliased to the dispatcher while it is installed, so uninstall
    restores `f` and leaves `g` holding an object that still says it belongs to
    the first Patcher. Answering the refusal from the marker alone would put
    that slot permanently out of reach of every Patcher, including the one
    whose name is on it. Asking the claimed owner whether the object is still
    in ITS ledger is what tells a live dispatcher from a retired one, and it is
    the same question _is_pyteman_hook had to start asking about the hook.
    """
    p1 = Patcher([crule("one")], None)
    p1.force_patch_module(MODNAME5)
    retired = composed_victim.f
    setattr(composed_victim, "g", retired)
    assert p1.uninstall() == []
    assert getattr(retired, "_pyteman_owner", None) is p1  # still stamped

    p2 = Patcher([crule("two", symbol="g")], None)
    p2.force_patch_module(MODNAME5)  # the refusal must not fire here
    assert composed_victim.g(1) == "two"
    assert p2.uninstall() == []
    assert composed_victim.g is retired


def test_a_callable_that_synthesises_an_owner_is_a_stranger_not_a_patcher(composed_victim):
    """The marker probe is answerable by anything; the ledger lookup is not.

    A test double that answers every attribute hands back a truthy object for
    `_pyteman_owner`, and a refusal keyed on that would make pyteman unable to
    patch a module under test the moment a mock stood in for one of its
    callables. Whatever the synthesised owner is, it cannot produce a ledger
    holding this exact object.
    """

    class Synthesising:
        """Answers every ordinary attribute, as MagicMock does.

        Dunders are refused so functools.wraps can read the real ones off it.
        A double that synthesised `__name__` too would fail the patch for a
        reason that has nothing to do with ownership, which would leave this
        test green for the wrong reason.
        """

        def __getattr__(self, name):
            if name.startswith("__"):
                raise AttributeError(name)
            return Synthesising()

        def __call__(self, *a, **k):
            return "real"

    setattr(composed_victim, "f", Synthesising())
    live = composed_victim.f
    assert getattr(live, "_pyteman_owner", None) is not None

    p = Patcher([crule("mine")], None)
    p.force_patch_module(MODNAME5)
    assert composed_victim.f(1) == "mine"
    assert p.uninstall() == []
    assert composed_victim.f is live


def test_a_rule_that_will_not_name_itself_is_refused_one_at_a_time():
    """Each unnamed rule is refused on its own, never by comparing placeholders.

    The old answer skipped an unreadable id in the duplicate check, for a
    reason that was right on its own terms: _rule_id renders every unreadable
    id to ONE placeholder, so comparing placeholders would refuse two unrelated
    rules for a collision that exists only in the rendering.

    That reasoning still has to hold, which is what the two-rule case guards.
    It cannot OBSERVE a distinction the current code makes, because the first
    rule is refused at the read and the second is never reached. What it would
    catch is the reintroduction of placeholder comparison: a version that
    compared renderings would still raise here, but with the wrong message, so
    the assertion is on the text and not merely on the refusal. The message
    names the read that failed, which is what tells the two reasons apart.
    """
    # Neither is a Rule, which is the premise: see UnreadableIdRule.
    with pytest.raises(RuleError, match="id could not be read"):
        Patcher([UnreadableIdRule(), UnreadableIdRule()], None)  # type: ignore[list-item]
    # Alone, on its own merits, with no second rule to be confused with.
    with pytest.raises(RuleError, match="id could not be read"):
        Patcher([UnreadableIdRule()], None)  # type: ignore[list-item]


def test_an_interrupt_while_reading_an_id_is_not_reported_as_a_bad_rule():
    """Ctrl-C during construction is an interrupt, never a ruleset defect.

    The guard on this read catches Exception and not BaseException, which is
    the narrower choice in a file that almost always takes the broader one.
    Elsewhere the breadth protects something: _rule_id must not raise while it
    reports, and _undo_one must not leave a module half restored if an
    interrupt lands mid-loop. __init__ mutates nothing, so there is nothing
    here for the breadth to protect, and it has a cost. str() of a
    KeyboardInterrupt is empty, so relabelling produced the message
    "id could not be read: ", which trails off after the colon and tells the
    operator their ruleset is broken when it is not. A wrong diagnosis is worse
    than none, because it reads as a diagnosis.
    """
    class Interrupting:
        module, symbol, event, when = MODNAME, "ok", "entry", None
        action = {"kind": "return_value", "value": 1}
        fire = {"mode": "always"}

        @property
        def id(self):
            raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        Patcher([Interrupting()], None)  # type: ignore[list-item]


def test_one_rule_object_listed_twice_is_refused_like_any_other_duplicate():
    """The same OBJECT twice is the shape that reaches the patcher by accident.

    A ruleset assembled by concatenation, or a rule appended to a list that was
    already passed somewhere, arrives as two references to one object rather
    than as two equal rules. There is no second identity to collide with, so it
    is worth pinning that the check reads the id per LIST ENTRY and not per
    distinct object: one point would otherwise be planned twice.

    What that cost is visible without the refusal: the composite carried two
    entries for one slot while its manifest reported one, and `applied` named
    the point twice, which is the manifest-against-entries disagreement the
    ruleset is supposed to make impossible.
    """
    r = make_rule("ok", "once")
    with pytest.raises(RuleError, match="id is already used"):
        Patcher([r, r], None)


def test_an_id_that_is_not_a_usable_string_is_refused_at_the_same_gate():
    """The two doors into one state agree on what an identity is.

    load_rules demands a non-empty str and refuses to coerce: `id: 5` is a typo
    in a ruleset, not an integer identity. The programmatic API used to accept
    whatever str() would render, so the same ruleset was legal through one door
    and rejected by the other, and the id keys the firing log for both.

    Empty and blank are the same refusal for the same reason. An id is what the
    operator greps the firing log for, and "" is not something anyone can grep.
    """
    # The typename is asserted, not just the refusal: `id: null` and `id: 5`
    # are different typos and the message is the only thing that tells the
    # author which one they made.
    for bad, typename in ((5, "int"), (None, "NoneType"), (("a",), "tuple")):
        with pytest.raises(RuleError,
                           match="id must be a string, got " + typename):
            Patcher([make_rule("ok", bad)], None)  # type: ignore[arg-type]

    for blank in ("", "   ", "\t\n"):
        with pytest.raises(RuleError, match="id must be a non-empty string"):
            Patcher([make_rule("ok", blank)], None)


def test_a_str_subclass_cannot_smuggle_a_duplicate_past_the_dedup_set():
    """The id enters the set normalised, so the set compares strings.

    A str subclass is a legal id and stays one, but it can carry its own
    __hash__ and __eq__, and a set asks the STORED element those questions. An
    id stored raw would therefore be findable only by another value that agrees
    with it, and a plain "same" would not, so a ruleset naming one id twice
    would be admitted with the second spelling wearing a subclass.

    That is worth a test rather than a comment because the difference is one
    call wide: `seen_ids.add(rid)` against `seen_ids.add(raw_id)` reads as a
    tidy-up either way, and only this pins which one is correct. The refusal is
    what proves the set saw two equal strings.
    """
    class Aloof(str):
        __hash__ = object.__hash__  # never equal to the plain str it spells

        def __eq__(self, other):
            return self is other

    assert Aloof("same") not in {"same"}, "premise: the raw value hides"
    with pytest.raises(RuleError, match="id is already used"):
        Patcher([make_rule("ok", Aloof("same")), make_rule("also", "same")],
                None)


def test_a_subclass_id_is_keyed_by_its_characters_and_not_by_its_str():
    """The identity is what the log will write, not what the id prints as.

    A str subclass can override __str__, and the house renderer _text calls
    str(), so normalising the id through _text would key the ruleset on user
    code while the firing log keyed it on the true characters. The two then
    disagree, and every way they disagree is a defect: `str.__str__` is used
    instead, which reads the characters and cannot run anything.

    All three failures below are what _text produced, confirmed against the
    real Patcher before this was written. They are asserted here rather than
    described, because the correct and incorrect spellings differ by one call.
    """
    class Collapsing(str):
        def __str__(self):
            return "collapsed"

    class Unprintable(str):
        def __str__(self):
            raise RuntimeError("no")

    # Distinct ids stay distinct. Through _text both render "collapsed" and the
    # second rule was refused for a duplicate that does not exist, which is a
    # legal ruleset rejected with a false reason.
    p = Patcher([make_rule("ok", Collapsing("x")),
                 make_rule("also", Collapsing("y"))], None)
    assert len(p._plan) == 2

    # Same again where __str__ raises: _text renders both to one placeholder.
    p = Patcher([make_rule("ok", Unprintable("a")),
                 make_rule("also", Unprintable("b"))], None)
    assert len(p._plan) == 2

    # And an id whose real content is "" is still empty, however it prints.
    # Through _text this passed, on the strength of "<unprintable Unprintable>",
    # and the log would then have recorded the "" nobody can grep for.
    with pytest.raises(RuleError, match="id must be a non-empty string"):
        Patcher([make_rule("ok", Unprintable(""))], None)
    with pytest.raises(RuleError, match="id must be a non-empty string"):
        Patcher([make_rule("ok", Collapsing("  "))], None)

    # The duplicate check still reads characters, so a collapsing spelling
    # cannot hide a real collision either.
    with pytest.raises(RuleError, match="id is already used"):
        Patcher([make_rule("ok", Collapsing("dup")),
                 make_rule("also", "dup")], None)


def test_the_ordinary_ruleset_is_untouched_by_the_gate(victim):
    """The gate costs nothing to a ruleset that was always going to be fine.

    A refusal added at preflight is only as good as its silence on everything
    else, and "the rest of the suite still passes" is a weaker statement than
    this one: distinct readable ids plan, patch, fire and uninstall exactly as
    before, including a str subclass, which is a legal id and stays one.
    """
    rules = [make_rule("ok", "first"), make_rule("also", "second"),
             make_rule("ok", BoomStr("third"))]
    p = install(rules, log=None)
    try:
        assert len(p._plan) == 3
        p.force_patch_module(MODNAME)
        assert getattr(victim.ok, "_pyteman_state", None) is not None
        assert getattr(victim.also, "_pyteman_state", None) is not None
        # Actually fire, rather than only observing that the slot was replaced.
        # The rule returns 1 for any argument, so a 5 coming back as 1 is the
        # dispatcher running with a BoomStr id in the plan. It does not reach
        # the raw `rule.id` reads in firing.py and actions.py, which sit behind
        # `if log is not None` and this file runs log-free throughout.
        assert victim.ok(5) == 1
        assert victim.also(5) == 1
    finally:
        assert p.uninstall() == []
    assert getattr(victim.ok, "_pyteman_state", None) is None


# ---------------------------------------------------------------------------
# RT-02: a dispatcher is ours from the setattr, not from the publish.
#
# Recognising our own work used to be a stamp on the wrapper, true the instant
# the object existed. Composition needs to know WHOSE it is, so the question
# became a relationship to a Patcher, answered from the ledger. _patch
# publishes to that ledger only when the whole module is done, so the new
# question has a window the old one did not: between writing a dispatcher into
# its attribute and publishing it, our own dispatcher reads as a stranger.
# ---------------------------------------------------------------------------

MODNAME7 = "pyteman_atomic_victim_reentrant"


class ReentrantSignature:
    """A callable whose signature lookup imports the module being patched.

    _make_dispatcher reads `inspect.signature(original)` for a rule carrying a
    `target:` spec, and `__signature__` is ordinary code belonging to the
    object being patched, so that read happens on the victim's terms. Importing
    from inside it re-enters the live hook, and so re-enters _patch, while an
    earlier slot of the same call is already written and not yet published.
    That reaches the window deterministically and single-threaded, where in
    production it is a thread arriving at an import mid-patch.

    One shot, because the re-entrant patch reads this signature too and a
    vector that keeps firing recurses rather than reproducing anything.
    """

    reentered = False

    def __call__(self, x):
        return "hostile"

    @property
    def __signature__(self):
        if not ReentrantSignature.reentered:
            ReentrantSignature.reentered = True
            __import__(MODNAME7)
        # Unintrospectable from here on, which _make_dispatcher already handles
        # and which keeps this fixture to the one thing it is for.
        raise TypeError("unintrospectable")


def test_a_reentrant_patch_does_not_wrap_a_slot_this_call_already_took():
    """Our own half-installed dispatcher must not read as someone else's.

    When it does, the re-entrant call wraps a slot this call already took and
    the ledger carries two entries for it. That is not merely redundant work:
    uninstall walks newest-first, so it reaches the INNER entry while the
    attribute still holds the outer wrapper, fails the identity check, and
    concludes a third party replaced our wrapper. It then releases the slot and
    drops the entry, leaving the callable wrapped and still firing while
    reporting nothing refused, which is the opposite of the fail-closed promise
    in the README.

    So the assertion that matters is the pair: one entry for the slot, and an
    uninstall that both reports clean and leaves the real callable behind.
    """
    real_import = builtins.__import__
    ReentrantSignature.reentered = False
    calls = []

    def plain(x):
        calls.append(x)
        return f"real({x})"

    mod = types.ModuleType(MODNAME7)
    setattr(mod, "b", plain)
    setattr(mod, "a", ReentrantSignature())
    sys.modules[MODNAME7] = mod

    # `b` first, so its slot is written and unpublished when `a`'s dispatcher
    # construction re-enters. `a` second, and with a target: spec, because the
    # signature read is the re-entry vector.
    rules = [
        Rule(id="on-b", module=MODNAME7, symbol="b", event="entry",
             action={"kind": "return_value", "value": "OVERRIDE"},
             fire={"mode": "always"}, when=None),
        Rule(id="on-a", module=MODNAME7, symbol="a", event="entry",
             action={"kind": "pragma", "name": "synchronous", "value": "OFF",
                     "target": "param:x"},
             fire={"mode": "always"}, when=None),
    ]
    p = Patcher(rules, None)
    try:
        p.install_hook()
        builtins.__import__(MODNAME7)
        assert ReentrantSignature.reentered, "the re-entry never happened"

        entries = [name for _, name, _, _, _ in p._wrapped if name == "b"]
        assert entries == ["b"], f"the slot was taken {len(entries)} times"

        assert p.uninstall() == []
        assert getattr(mod, "b") is plain, "the callable was left wrapped"
        calls.clear()
        assert getattr(mod, "b")(9) == "real(9)"
        assert calls == [9], "the body did not run after a clean uninstall"
    finally:
        builtins.__import__ = real_import
        del sys.modules[MODNAME7]


MODNAME8 = "pyteman_atomic_victim_stale"
MODNAME9 = "pyteman_atomic_victim_stale_nested"


class ImportsASecondModule:
    """Like ReentrantSignature, but the re-entry patches a DIFFERENT module.

    That is what makes the re-entrant call install on a slot the outer call has
    resolved and not yet reached, which is the only way pass 1's reading of that
    slot can go stale while pass 2 is running.
    """

    reentered = False

    def __call__(self, x):
        return "outer"

    @property
    def __signature__(self):
        if not ImportsASecondModule.reentered:
            ImportsASecondModule.reentered = True
            __import__(MODNAME9)
        raise TypeError("unintrospectable")


def test_pass_two_asks_about_the_value_that_is_there_not_the_one_it_remembered():
    """A slot taken between the two passes must not be written over.

    Pass 1 resolves every rule before pass 2 writes anything, which is what
    lets two rules be recognised as one slot. The gap between them is not
    quiet: building an earlier slot's dispatcher reads a signature, that read
    imports, and the hook patches whatever came in. So a slot pass 1 read as a
    plain callable can be holding one of our own dispatchers by the time pass 2
    arrives.

    Judging it by the remembered value wraps the stale original and setattr's
    over the live dispatcher. The rules that dispatcher served stop firing
    permanently, `applied` reports them installed anyway, and the ledger keeps
    an entry for a wrapper no longer in its slot, which uninstall reads as a
    third party's replacement and releases without a word. The invariant that
    catches all three at once is that every published entry still holds its own
    wrapper.
    """
    real_import = builtins.__import__
    ImportsASecondModule.reentered = False

    def g(x):
        return f"real-g({x})"

    outer = types.ModuleType(MODNAME8)
    nested = types.ModuleType(MODNAME9)
    setattr(nested, "g", g)
    setattr(outer, "f", ImportsASecondModule())
    setattr(outer, "nested", nested)
    sys.modules[MODNAME8] = outer
    sys.modules[MODNAME9] = nested

    log = Recorder()
    rules = [
        # First, and the only one needing a signature, so its construction is
        # what re-enters.
        Rule(id="forces-the-reentry", module=MODNAME8, symbol="f",
             event="entry",
             action={"kind": "pragma", "name": "synchronous", "value": "OFF",
                     "target": "param:x"},
             fire={"mode": "always"}, when=None),
        # Reaches the nested module's attribute from the outer module, in pass
        # 2, after the re-entrant call has already taken that slot.
        Rule(id="via-alias", module=MODNAME8, symbol="nested.g", event="entry",
             action={"kind": "return_value", "value": "ALIAS"},
             fire={"mode": "always"}, when=None),
        # What the re-entrant call installs.
        Rule(id="direct", module=MODNAME9, symbol="g", event="entry",
             action={"kind": "return_value", "value": "NESTED"},
             fire={"mode": "always"}, when=None),
    ]
    p = Patcher(rules, log)
    try:
        p.install_hook()
        builtins.__import__(MODNAME8)
        assert ImportsASecondModule.reentered, "the re-entry never happened"

        dead = [name for container, name, _, wrapper, _ in p._wrapped
                if getattr(container, name) is not wrapper]
        assert dead == [], f"a published entry lost its slot: {dead}"

        log.seen.clear()
        # Both rules are on this one attribute now: `direct`, which the nested
        # call installed, and `via-alias`, which the outer call reached through
        # another module's namespace and which used to be dropped here without a
        # word. Asking the dispatcher what it serves is the assertion that says
        # so, because the call below cannot: `via-alias` returns a value and
        # short-circuits, so a log naming it alone is equally consistent with
        # `direct` having been lost.
        served = [spec[0].id for spec in
                  getattr(nested, "g")._pyteman_composite.rank()]
        assert served == ["via-alias", "direct"], served

        # `via-alias` wins, and the reason is ruleset order rather than anything
        # about which call arrived first: it is written above `direct` and was
        # discovered after it. Arrival order would answer "NESTED" here.
        assert getattr(nested, "g")(1) == "ALIAS"
        assert log.ids == ["via-alias"], "a return_value rule stops the chain"

        assert p.uninstall() == []
        assert getattr(nested, "g") is g
    finally:
        builtins.__import__ = real_import
        del sys.modules[MODNAME8]
        del sys.modules[MODNAME9]


def test_each_rules_when_expression_reads_its_own_fire_count(composed_victim):
    """`fires` inside a `when` is per rule, not per call of the shared point.

    docs/rules.md states this twice and nothing evaluated it: the countdown
    test next door pins the per-rule `state["fires"]` that gates a mode, which
    is a different reader from the `ctx["fires"]` an operator's expression sees.
    Both rules ask the same question, `fires == 2`, so a shared counter is not
    a subtle difference here. It would put the second rule at 2 on the very
    first call and answer "b" before "a" has ever fired.
    """
    log = Recorder()
    p = Patcher([crule("a", when="fires == 2"), crule("b", when="fires == 2")],
                log)
    p.force_patch_module(MODNAME5)

    # Call 1 reaches both, neither passes. Call 2 is a's, and it short-circuits
    # before b is reached, which is why b is still at 1 afterwards. Call 3 gets
    # past a and is b's second reach.
    assert [composed_victim.f(1) for _ in range(3)] == ["real", "a", "b"]
    assert log.ids == ["a", "b"]
    assert p.uninstall() == []


def test_a_resolution_failure_says_resolving_and_not_patching(composed_victim):
    """The third phase word, and the same argument that separates the first two.

    `_patch` resolves every rule before it writes anything, so a `symbol` walk
    that raises comes out of a pass where no callable was replaced and there is
    nothing to roll back. Calling that "while patching" tells the operator to
    go looking for instrumentation this call never installed, which is the
    failure test_planning_says_planning_and_not_patching exists to prevent one
    level up.
    """
    class Hostile:
        def __getattr__(self, name):
            raise RuntimeError("attribute access refused")

    setattr(composed_victim, "hostile", Hostile())
    f_before = composed_victim.f

    p = Patcher([crule("walker", symbol="hostile.f")], None)
    with pytest.raises(RuntimeError) as excinfo:
        p.force_patch_module(MODNAME5)

    notes = getattr(excinfo.value, "__notes__", [])
    assert any("while resolving" in n for n in notes), notes
    assert not any("while patching" in n for n in notes), notes
    assert any(repr("walker") in n for n in notes), notes
    # The claim the word makes, checked rather than taken on trust.
    assert p._wrapped == []
    assert composed_victim.f is f_before


def test_the_dispatcher_keeps_the_signature_of_what_it_replaced(composed_victim):
    """The half of the wraps contract that nothing was checking.

    Ordering, gating and rollback each have tests. `functools.wraps` had only
    its own line in the source, so deleting the decorator broke no test at all.
    It carries more than tidiness: a `pragma` rule with a `param:` target binds
    its argument through `inspect.signature(original)`, and `signature` follows
    `__wrapped__`, so the decorator is what keeps that resolution working
    through a dispatcher written as `(*args, **kwargs)`. Anything else in the
    process that introspects the callable reads the wrapper too, and
    instrumentation that renames what it instruments is instrumentation the
    program under test can see.
    """
    import inspect

    def real(alpha, beta=2, *rest, **kw):
        """The docstring a caller would read."""
        return "real"

    composed(body=real)
    p = Patcher([crule("a"), crule("b", "exit")], None)
    p.force_patch_module(MODNAME5)

    live = sys.modules[MODNAME5].f
    assert live is not real
    assert live.__name__ == "real"
    assert live.__doc__ == "The docstring a caller would read."
    # Stronger than the two above: __name__ could be satisfied by a copied
    # attribute, while this is the link inspect actually walks.
    assert live.__wrapped__ is real
    assert str(inspect.signature(live)) == "(alpha, beta=2, *rest, **kw)"
    assert p.uninstall() == []


MODNAME10 = "pyteman_atomic_victim_takeover"
MODNAME11 = "pyteman_atomic_victim_takeover_alias"


class ImportsAnAliasingModule:
    """Like ReentrantSignature, but the module it pulls in aliases it back.

    ReentrantSignature re-enters on the module being patched, so the nested
    call resolves the SAME rules and either dispatcher would serve them. Here
    the nested call arrives through a different module holding `alias = victim`
    and carries a rule of its own, so it resolves a DIFFERENT rule onto the one
    attribute the outer call is at that moment building a dispatcher for. That
    is the only shape in which the two dispatchers are not interchangeable.
    """

    reentered = False

    def __call__(self, x):
        return "real"

    @property
    def __signature__(self):
        if not ImportsAnAliasingModule.reentered:
            ImportsAnAliasingModule.reentered = True
            __import__(MODNAME11)
        raise TypeError("unintrospectable")


def test_a_reentrant_patch_that_takes_the_slot_being_built_leaves_one_entry():
    """The gap the re-read at the top of pass 2 cannot see.

    That re-read happens before the dispatcher is built, and building it is
    what re-enters: a `target:` spec sends _make_dispatcher through
    inspect.signature, which runs the victim's own __signature__. A nested
    _patch reaching THIS attribute installs on it while the outer call is still
    building a dispatcher for it, and the outer setattr used to land anyway. The
    ledger then carried two entries for one attribute, the older naming a
    wrapper no longer in it, and `applied` named a rule that had stopped firing.

    Which of the two rules wins is pinned below, and now as a guarantee. The
    outer call's rule used to be dropped here: its dispatcher lost the race for
    the slot, and standing down took its rules with it silently. It no longer
    does. The rules go into the dispatcher that won, so one attribute carries
    one wrapper serving both, and the rule that fires first is the one written
    first in the ruleset rather than the one whose call happened to arrive
    first. Those two orders disagree in this test, which is what makes it able
    to tell them apart.
    """
    real_import = builtins.__import__
    ImportsAnAliasingModule.reentered = False

    victim = types.ModuleType(MODNAME10)
    setattr(victim, "a", ImportsAnAliasingModule())
    sys.modules[MODNAME10] = victim

    aliasing = types.ModuleType(MODNAME11)
    setattr(aliasing, "alias", victim)
    sys.modules[MODNAME11] = aliasing

    rules = [
        Rule(id="outer", module=MODNAME10, symbol="a", event="entry",
             action={"kind": "pragma", "name": "synchronous", "value": "OFF",
                     "target": "param:x"},
             fire={"mode": "always"}, when=None),
        Rule(id="inner", module=MODNAME11, symbol="alias.a", event="entry",
             action={"kind": "return_value", "value": "INNER"},
             fire={"mode": "always"}, when=None),
    ]
    p = Patcher(rules, None)
    try:
        p.install_hook()
        builtins.__import__(MODNAME10)
        assert ImportsAnAliasingModule.reentered, "the re-entry never happened"

        taken = [name for _, name, _, _, _ in p._wrapped if name == "a"]
        assert taken == ["a"], f"the slot was taken {len(taken)} times"
        dead = [n for c, n, _, w, _ in p._wrapped if getattr(c, n, None) is not w]
        assert dead == [], "the ledger names a wrapper that is not in its slot"

        # One wrapper, both rules. `applied` names them in the order the two
        # calls published them, which is the only order it has ever had: it
        # accumulates across every import and no single call sees the whole of
        # it. Firing order is a separate question, answered below.
        assert p.applied == [f"{MODNAME11}:alias.a", f"{MODNAME10}:a"]
        served = [spec[0].id for spec in
                  getattr(victim, "a")._pyteman_composite.rank()]
        assert served == ["outer", "inner"], served

        # "INNER" is now evidence rather than the whole story. `outer` runs
        # first, being written first, and it is a param pragma on a callable
        # whose __signature__ raises, so it notes the true cause and declines to
        # act. Passing the call on is what lets `inner` answer. If `outer` had
        # been dropped the result would be identical, which is why `served`
        # above is the assertion carrying the claim.
        assert getattr(victim, "a")(9) == "INNER"

        assert p.uninstall() == []
        assert isinstance(getattr(victim, "a"), ImportsAnAliasingModule), \
            "the real callable did not come back"
    finally:
        builtins.__import__ = real_import
        del sys.modules[MODNAME10]
        del sys.modules[MODNAME11]


MODNAME12 = "pyteman_atomic_victim_instance"


class Session:
    """A module-level singleton, the `point: myapp.session.db.append` shape."""

    def query(self, sql):
        return f"rows({sql})"


def test_a_point_on_a_module_level_instance_patches_fires_and_restores():
    """A slot the descriptor protocol BUILDS on every read.

    `inst.query is inst.query` is False, because a bound method is manufactured
    by function.__get__ at each access. Pass 2 reads the attribute once before
    deciding what to do with it and again just before writing, and comparing
    those two reads for IDENTITY calls this slot replaced every single time. It
    refused an ordinary patch with a message naming a race that had not
    happened, and because the refusal raises, one singleton point took every
    other rule in the same module down with it. Asking who owns the value found
    there, rather than whether it is the same object, is what the gap needs:
    identity is unanswerable on a slot the descriptor protocol rebuilds on every
    read, so ownership is the strongest question the guard can ask there.

    No other test in this file reaches a point this way. The `inheriting`
    fixture uses a plain function on a base class, and `getattr(Sub, "meth")`
    for that IS identity-stable, so it cannot see this.
    """
    fired = []

    class Log:
        def record(self, rule, ctx, note=None, outcome=None,
                   phase="start", attempt=None, status=None):
            # Only the firing is counted here; the terminal record is this
            # test's noise, and `fired` is asserted to be exactly one entry.
            if phase == "start":
                fired.append(rule.id)
            return RecordId("log", os.getpid(), 1, 1)

        def close(self):
            pass

    mod = types.ModuleType(MODNAME12)
    session = Session()
    setattr(mod, "session", session)
    sys.modules[MODNAME12] = mod
    try:
        assert getattr(session, "query") is not getattr(session, "query"), \
            "the fixture reads identity-stable, so it cannot test this at all"

        rule = Rule(id="on_query", module=MODNAME12, symbol="session.query",
                    event="entry", action={"kind": "sleep", "ms": 0},
                    fire={"mode": "always"}, when=None)
        p = Patcher([rule], Log())
        p.force_patch_module(MODNAME12)

        assert p.applied == [f"{MODNAME12}:session.query"]
        assert session.query("x") == "rows(x)"
        assert fired == ["on_query"], "the rule never fired"

        assert p.uninstall() == []
        assert session.query("x") == "rows(x)"
        # delattr and not a setattr of the original: the name lives on the
        # class, so the patch CREATED it on the instance and putting a bound
        # method back would shadow Session.query for this object forever.
        assert "query" not in vars(session), \
            "uninstall left the instance shadowing its class"
    finally:
        del sys.modules[MODNAME12]


MODNAME13 = "pyteman_atomic_victim_vanishing"


class VanishesDuringSignature:
    """Removes the attribute holding it while its dispatcher is being built."""

    victim: object = None
    ran = False

    def __call__(self, x):
        return "real"

    @property
    def __signature__(self):
        if not VanishesDuringSignature.ran:
            VanishesDuringSignature.ran = True
            delattr(VanishesDuringSignature.victim, "a")
        raise TypeError("unintrospectable")


def test_an_attribute_deleted_while_its_dispatcher_was_built_is_skipped():
    """Absence answers the same way at both readings in pass 2.

    A `target:` spec sends _make_dispatcher through inspect.signature, which
    runs the victim's own `__signature__`, and here that removes the attribute
    being patched. The second reading therefore finds nothing where the first
    found a callable.

    Skipped, not refused, and for a reason the first reading does not have: the
    write would put back a name the target program had just deleted, which is a
    change to the program pyteman is only supposed to observe. Refusing instead
    would also take down every other rule in the module over an attribute that
    no longer exists. Losing this slot's rules is the cost, and it is bounded,
    since the publish sits below the point this leaves from: `applied` names
    none of this slot's rules and the ledger carries no entry for it, so no
    operator is told a rule is live when it is not. Every other rule in the
    module is installed and published as usual.
    """
    mod = types.ModuleType(MODNAME13)
    VanishesDuringSignature.victim = mod
    VanishesDuringSignature.ran = False
    setattr(mod, "a", VanishesDuringSignature())
    setattr(mod, "b", lambda x: x)
    sys.modules[MODNAME13] = mod
    try:
        rules = [
            Rule(id="vanishing", module=MODNAME13, symbol="a", event="entry",
                 action={"kind": "pragma", "name": "synchronous",
                         "value": "OFF", "target": "param:x"},
                 fire={"mode": "always"}, when=None),
            Rule(id="survivor", module=MODNAME13, symbol="b", event="entry",
                 action={"kind": "return_value", "value": "B"},
                 fire={"mode": "always"}, when=None),
        ]
        p = Patcher(rules, None)
        p.force_patch_module(MODNAME13)

        assert VanishesDuringSignature.ran, "the deletion never happened"
        assert not hasattr(mod, "a"), "the slot was resurrected"
        # The rule on the vanished slot is named nowhere, and the rule on the
        # surviving slot is unaffected: no refusal took the module down.
        assert p.applied == [f"{MODNAME13}:b"]
        assert [n for _, n, _, _, _ in p._wrapped] == ["b"]
        assert getattr(mod, "b")(1) == "B"

        assert p.uninstall() == []
        assert getattr(mod, "b")(7) == 7, "the survivor was not restored"
    finally:
        VanishesDuringSignature.victim = None
        del sys.modules[MODNAME13]


MODNAME14 = "pyteman_atomic_victim_stolen"


class StolenDuringSignature:
    """Lets a SECOND Patcher take this attribute while its dispatcher is built."""

    thief: object = None
    ran = False

    def __call__(self, x):
        return "real"

    @property
    def __signature__(self):
        if not StolenDuringSignature.ran:
            StolenDuringSignature.ran = True
            StolenDuringSignature.thief.force_patch_module(MODNAME14)
        raise TypeError("unintrospectable")


def test_a_slot_taken_by_another_patcher_mid_build_is_refused_and_rolled_back():
    """The refusal branch of the second reading, which nothing else reaches.

    The top-of-loop reading has its own refusal test, and it fires before any
    dispatcher is built. This one can only be reached through the gap the build
    opens: `inspect.signature` runs the victim's `__signature__`, and a second
    Patcher installs on this very attribute while it runs. Deleting the raise
    or inverting its condition leaves the rest of the suite green, so without
    this the branch is free to regress into silently overwriting a stranger's
    live dispatcher.

    Refused rather than skipped, which is the opposite of what absence gets a
    few lines above, and the asymmetry is the point: a deleted name is the
    target program's own doing and costs only this slot, while another
    Patcher's dispatcher is instrumentation an operator installed and expects
    to keep firing. Standing down silently would leave that operator's rules
    live and this ruleset reporting success on rules it never installed.
    """
    mod = types.ModuleType(MODNAME14)
    setattr(mod, "a", lambda x: x)
    setattr(mod, "b", StolenDuringSignature())
    sys.modules[MODNAME14] = mod
    a_before = getattr(mod, "a")
    thief = Patcher(
        [Rule(id="thief", module=MODNAME14, symbol="b", event="entry",
              action={"kind": "return_value", "value": "THIEF"},
              fire={"mode": "always"}, when=None)], None)
    StolenDuringSignature.thief = thief
    StolenDuringSignature.ran = False
    try:
        # `a` first and free, `b` second and stolen, so the refusal arrives with
        # one of this call's own slots already written.
        rules = [
            Rule(id="ours_a", module=MODNAME14, symbol="a", event="entry",
                 action={"kind": "return_value", "value": "A"},
                 fire={"mode": "always"}, when=None),
            Rule(id="ours_b", module=MODNAME14, symbol="b", event="entry",
                 action={"kind": "pragma", "name": "synchronous",
                         "value": "OFF", "target": "param:x"},
                 fire={"mode": "always"}, when=None),
        ]
        p = Patcher(rules, None)
        with pytest.raises(SlotOwnershipError) as excinfo:
            p.force_patch_module(MODNAME14)

        assert StolenDuringSignature.ran, "the theft never happened"
        message = str(excinfo.value)
        assert MODNAME14 in message and "b" in message
        assert "while its dispatcher was being built" in message, \
            "the diagnostic does not say which of the two readings refused"

        # This call's own slot is released, and `applied` names nothing, so no
        # operator is told a rule is live after a refusal.
        assert getattr(mod, "a") is a_before
        assert getattr(mod, "a")(1) == 1
        assert p.applied == []
        assert p._wrapped == []

        # The other Patcher keeps the slot it took, untouched.
        assert getattr(mod, "b")(1) == "THIEF"
        assert thief.uninstall() == []
    finally:
        StolenDuringSignature.thief = None
        del sys.modules[MODNAME14]


MODNAME15 = "pyteman_atomic_victim_crosscall"
MODNAME16 = "pyteman_atomic_victim_crosscall_alias"


@pytest.fixture
def crosscall():
    """Two modules, the second holding a reference to the first.

    The re-entrancy tests above reach the same slot twice from inside one
    import. Nothing re-enters here: the two `_patch` calls are separate and
    ordinary, which is the shape an operator actually meets when a ruleset
    names a callable both where it is defined and where another module
    imported it, and the two modules are imported at different times.
    """
    victim = types.ModuleType(MODNAME15)
    setattr(victim, "f", lambda *a, **k: "real")
    sys.modules[MODNAME15] = victim

    holder = types.ModuleType(MODNAME16)
    setattr(holder, "via", victim)
    setattr(holder, "g", lambda *a, **k: "real-g")
    sys.modules[MODNAME16] = holder
    try:
        yield victim, holder
    finally:
        sys.modules.pop(MODNAME15, None)
        sys.modules.pop(MODNAME16, None)


def test_a_later_patch_call_reaching_a_slot_we_already_own_extends_it(crosscall):
    """The silent drop, in the plain shape that has nothing exotic in it.

    A rule resolving onto an attribute THIS Patcher wrapped on an earlier
    import used to be discarded: it never fired, it never reached `applied`,
    and no refusal was raised, so the only way to find out was to notice a rule
    that did nothing. The dispatcher could not have done better, because what
    it published about itself was a list of anonymous state dicts: it knew it
    was ours and could not know which rules it served.

    `late` is written FIRST in the ruleset and discovered SECOND. That
    disagreement is the test: ruleset order is what an operator can see and
    reason about, while discovery order depends on which module happened to be
    imported first, which is not a thing a ruleset can express.
    """
    victim, _holder = crosscall
    log = Recorder()
    rules = [crule("late", "entry", {"kind": "sleep", "ms": 0},
                   symbol="via.f", module=MODNAME16),
             crule("early", "entry", {"kind": "sleep", "ms": 0},
                   symbol="f", module=MODNAME15)]
    p = Patcher(rules, log)

    p.force_patch_module(MODNAME15)
    dispatcher = victim.f
    assert [s[0].id for s in dispatcher._pyteman_composite.rank()] == ["early"]

    p.force_patch_module(MODNAME16)

    # Extended, not wrapped again: one attribute, one wrapper, one ledger entry
    # to put back. `applied` grows by exactly the rule that was added, named by
    # the spelling that reached it.
    assert victim.f is dispatcher, "a second wrapper was installed"
    assert len(p._wrapped) == 1
    assert p.applied == [f"{MODNAME15}:f", f"{MODNAME16}:via.f"]

    # Neither rule returns a value, so both reach the log and the order is
    # readable. Appending on arrival would answer ["early", "late"].
    assert victim.f(1) == "real"
    assert log.ids == ["late", "early"]

    assert p.uninstall() == []
    assert victim.f(1) == "real"


def test_extending_a_dispatcher_leaves_the_state_the_live_rules_already_reached(crosscall):
    """An added rule must not cost the rules already there what they have done.

    Both kinds of per-rule memory are in play, because they fail differently. A
    rebuilt `fires` makes a countdown restart, so a rule fires later than the
    operator asked or never at all. A rebuilt `seen_keys` makes `once_per` fire
    again for a key it has already served, which is the mode's one promise.

    Neither is visible in the dispatcher's shape, only in what it does on the
    calls after the extension, so this is all behavioural.
    """
    victim, _holder = crosscall
    log = Recorder()
    rules = [crule("added", "entry", {"kind": "sleep", "ms": 0},
                   symbol="via.f", module=MODNAME16),
             crule("counting", "entry", {"kind": "sleep", "ms": 0},
                   symbol="f", module=MODNAME15,
                   fire={"mode": "countdown", "n": 1}),
             crule("keyed", "entry", {"kind": "sleep", "ms": 0},
                   symbol="f", module=MODNAME15,
                   fire={"mode": "once_per", "key": "args[0]"})]
    p = Patcher(rules, log)
    p.force_patch_module(MODNAME15)

    # One call before the extension. `counting` takes the first of the two
    # reaches it needs; `keyed` banks the key "a".
    assert victim.f("a") == "real"
    assert log.ids == ["keyed"]

    log.seen.clear()
    p.force_patch_module(MODNAME16)

    # `counting` is now at its n+1 reach, so it fires. A counter rebuilt by the
    # extension would put it back at its first and leave it out of this log.
    # `keyed` is handed a key it has already served and stays quiet, which an
    # emptied `seen_keys` would turn into a second firing.
    assert victim.f("a") == "real"
    assert log.ids == ["added", "counting"]

    # A key it has NOT served, to show the quiet above was the banked key and
    # not the rule having been dropped from the dispatcher.
    log.seen.clear()
    assert victim.f("b") == "real"
    assert log.ids == ["added", "keyed"]


def test_a_failed_call_that_extended_a_dispatcher_takes_back_only_its_own_rules(crosscall):
    """Rollback reaches the additions, and stops exactly there.

    A call can do both things before it fails: install a wrapper on one slot
    and add rules to a wrapper already live on another. Restoring only the
    installs would leave the additions firing under an `applied` that was never
    published, which is the same divergence between what runs and what is
    recorded that the refusal exists to prevent.

    Overshooting is the opposite failure and the worse one: the dispatcher
    being extended belongs to an EARLIER call that succeeded, so taking its
    rules or its state with us would break instrumentation that was never part
    of this call.
    """
    victim, _holder = crosscall
    log = Recorder()

    # A second Patcher takes `g`, so walking MODNAME16 refuses partway through.
    thief = Patcher([crule("thief", "entry",
                           {"kind": "return_value", "value": "THIEF"},
                           symbol="g", module=MODNAME16)], None)
    thief.force_patch_module(MODNAME16)

    rules = [
        # Written first, so after the merge the ADDED rule sits ahead of the
        # surviving one. That ordering is deliberate: a rollback that trimmed
        # the list from the end instead of removing by rule identity would drop
        # `pre` and keep `added`, and every assertion below would still have to
        # fail rather than pass by luck.
        crule("added", "entry", {"kind": "sleep", "ms": 0},
              symbol="via.f", module=MODNAME16),
        crule("pre", "entry", {"kind": "sleep", "ms": 0},
              symbol="f", module=MODNAME15,
              fire={"mode": "countdown", "n": 1}),
        # Reached after `added`, and refused. Ruleset order is what puts the
        # extension before the refusal rather than after it.
        crule("doomed", "entry", {"kind": "sleep", "ms": 0},
              symbol="g", module=MODNAME16)]
    p = Patcher(rules, log)
    p.force_patch_module(MODNAME15)
    dispatcher = victim.f
    state_before = dispatcher._pyteman_state[0]
    applied_before = list(p.applied)

    assert victim.f(1) == "real"  # `pre` takes the first of its two reaches
    assert log.ids == []

    log.seen.clear()
    with pytest.raises(SlotOwnershipError):
        p.force_patch_module(MODNAME16)

    # The dispatcher is where it was, serving what it served, and `applied`
    # never learned about a rule that is no longer there.
    assert victim.f is dispatcher
    assert [s[0].id for s in dispatcher._pyteman_composite.rank()] == ["pre"]
    assert p.applied == applied_before
    assert len(p._wrapped) == 1

    # The surviving rule keeps the reach it banked, by the same dict and not a
    # replacement built to look like it.
    assert dispatcher._pyteman_state[0] is state_before
    assert victim.f(1) == "real"
    assert log.ids == ["pre"]

    assert thief.uninstall() == []


def test_an_exit_rule_added_by_a_later_call_merges_into_ruleset_order(crosscall):
    """The exit list is merged by the same rule the entry list is, and separately.

    Every composition test above this one extends a dispatcher with ENTRY rules,
    so the exit list has only ever been built in one pass and never grown in a
    second. That leaves the two merges pinned unequally: the entry one is read
    by the whole file, the exit one by nothing, and it is a separate statement
    on a separate list. Sorting one and appending the other is a change no
    assertion in this suite would have noticed.

    `late` is written FIRST and discovered SECOND, which is the disagreement
    between ruleset order and import order that the sort exists to settle.
    Appending on arrival answers ["early", "late"].
    """
    victim, _holder = crosscall
    log = Recorder()
    rules = [crule("late", "exit", {"kind": "sleep", "ms": 0},
                   symbol="via.f", module=MODNAME16),
             crule("early", "exit", {"kind": "sleep", "ms": 0},
                   symbol="f", module=MODNAME15)]
    p = Patcher(rules, log)

    p.force_patch_module(MODNAME15)
    dispatcher = victim.f
    p.force_patch_module(MODNAME16)

    assert victim.f is dispatcher, "a second wrapper was installed"
    assert p.applied == [f"{MODNAME15}:f", f"{MODNAME16}:via.f"]

    comp = dispatcher._pyteman_composite
    assert [s[0].id for s in comp.entries] == []
    assert [s[0].id for s in comp.exits] == ["late", "early"]

    assert victim.f(1) == "real"
    assert log.ids == ["late", "early"]

    assert p.uninstall() == []


def test_a_failed_call_takes_back_the_exit_rules_it_added(crosscall):
    """Rolling back an extension reaches the exit list too.

    _unextend removes the added rules from `entries` and from `exits` in two
    statements, and until now only the first of them was reached by a test: an
    exit rule has never been added to a live dispatcher by a call that then
    failed. Dropping the second statement leaves the suite green while a rolled
    back rule goes on firing, and it does so INVISIBLY, because `served` is
    cleaned either way. `rank()` and `_pyteman_state` would both report the
    survivor alone while the call still ran two rules.

    So the assertion that matters here is the behavioural one. The shape checks
    come first because they say which list is wrong when it breaks.
    """
    victim, _holder = crosscall
    log = Recorder()

    thief = Patcher([crule("thief", "entry",
                           {"kind": "return_value", "value": "THIEF"},
                           symbol="g", module=MODNAME16)], None)
    thief.force_patch_module(MODNAME16)

    rules = [
        # Written first, so the merge puts the added rule AHEAD of the survivor
        # and a rollback that trimmed from the end would keep the wrong one.
        crule("added", "exit", {"kind": "sleep", "ms": 0},
              symbol="via.f", module=MODNAME16),
        crule("pre", "exit", {"kind": "sleep", "ms": 0},
              symbol="f", module=MODNAME15),
        # Reached after `added`, and refused.
        crule("doomed", "entry", {"kind": "sleep", "ms": 0},
              symbol="g", module=MODNAME16)]
    p = Patcher(rules, log)
    p.force_patch_module(MODNAME15)
    dispatcher = victim.f
    applied_before = list(p.applied)

    with pytest.raises(SlotOwnershipError):
        p.force_patch_module(MODNAME16)

    comp = dispatcher._pyteman_composite
    assert victim.f is dispatcher
    assert [s[0].id for s in comp.exits] == ["pre"]
    assert [s[0].id for s in comp.rank()] == ["pre"]
    assert len(dispatcher._pyteman_state) == 1
    assert p.applied == applied_before

    # What the manifest cannot tell us: a rule left in `exits` still runs.
    assert victim.f(1) == "real"
    assert log.ids == ["pre"]

    assert thief.uninstall() == []



MODNAME17 = "pyteman_atomic_victim_remerge"
MODNAME18 = "pyteman_atomic_victim_remerge_alias"


class ReentersDuringExtension:
    """Re-enters _patch from inside the signature read of an EXTENSION.

    The re-entrancy classes above open their window while a dispatcher is being
    BUILT. This one opens it while a dispatcher that already exists is being
    added to, which is a different window with a different victim: not the slot,
    which is already written and stays written, but the list of rules the
    extension resolved a moment earlier and is about to merge.
    """

    patcher: object = None
    ran = False

    def __call__(self, x):
        return "real"

    @property
    def __signature__(self):
        if not ReentersDuringExtension.ran:
            ReentersDuringExtension.ran = True
            ReentersDuringExtension.patcher.force_patch_module(MODNAME18)
        raise TypeError("unintrospectable")


def test_a_reentrant_patch_during_an_extension_merges_its_rules_once():
    """The rules an extension resolved are re-asked after the signature read.

    `fresh` is computed against the manifest, and the signature read that comes
    next runs target code. A re-entry it causes does not merely LOOK at this
    dispatcher, which the read being first already makes safe: it can reach this
    same slot and merge the very rules `fresh` names, publishing them in
    `applied` as its own. Merging them a second time on the way back puts two
    specs carrying two separate states on one rule, so the rule counts one reach
    twice, its `countdown` arrives at the threshold on a call the operator never
    wrote, and its `once_per` fires twice for one key.

    Nothing reports that on its own. `served` is keyed by rule identity and
    keeps one spec per rule, so the duplicate is invisible to exactly the
    manifest this composition exists to make drops visible in: `rank()` and
    `_pyteman_state` both publish ONE state while TWO are being counted.
    """
    victim = types.ModuleType(MODNAME17)
    setattr(victim, "f", ReentersDuringExtension())
    sys.modules[MODNAME17] = victim
    holder = types.ModuleType(MODNAME18)
    setattr(holder, "via", victim)
    sys.modules[MODNAME18] = holder
    ReentersDuringExtension.ran = False
    try:
        log = Recorder()
        rules = [
            # Needs no signature, so the dispatcher is built with no answer
            # cached and the extension below is what first asks for one.
            crule("early", "entry", {"kind": "sleep", "ms": 0},
                  symbol="f", module=MODNAME17),
            # A param target is what makes the extension ask at all, so this
            # rule opens the window it then falls into.
            crule("late", "entry",
                  {"kind": "pragma", "name": "synchronous", "value": "OFF",
                   "target": "param:x"},
                  symbol="via.f", module=MODNAME18),
        ]
        p = Patcher(rules, log)
        ReentersDuringExtension.patcher = p
        p.force_patch_module(MODNAME17)
        p.force_patch_module(MODNAME18)

        assert ReentersDuringExtension.ran, "the re-entry never happened"
        dispatcher = victim.f
        comp = dispatcher._pyteman_composite

        # What fires and what is published are the same list. The manifest
        # cannot report the duplicate, so this is the comparison that can.
        assert [s[0].id for s in comp.entries] == ["early", "late"]
        assert [s[0].id for s in comp.rank()] == ["early", "late"]
        assert len(dispatcher._pyteman_state) == len(comp.entries)

        # One rule, one state. Two specs for `late` would be two `seen_keys`
        # sets and two `fires` counters under one id.
        assert len({id(s[3]) for s in comp.entries}) == 2

        # Named once. `applied` accumulates across calls and is the only thing
        # an operator sees, so a rule listed twice is a rule reported as
        # installed twice.
        assert p.applied == [f"{MODNAME17}:f", f"{MODNAME18}:via.f"]

        # One call is one reach for each rule. Counted here rather than in the
        # firing log because a pragma that cannot resolve its target records a
        # second time for the skip, which is pre-existing and not a duplicate.
        dispatcher(1)
        assert [s[3]["fires"] for s in comp.entries] == [1, 1]
    finally:
        ReentersDuringExtension.patcher = None
        sys.modules.pop(MODNAME17, None)
        sys.modules.pop(MODNAME18, None)


MODNAME19 = "pyteman_atomic_victim_sigrollback"
MODNAME20 = "pyteman_atomic_victim_sigrollback_alias"


class Unintrospectable:
    """A callable inspect.signature always refuses, counting who asked."""

    asked = 0

    def __call__(self, x):
        return "real"

    @property
    def __signature__(self):
        Unintrospectable.asked += 1
        raise TypeError("unintrospectable")


def test_a_failed_call_takes_back_the_signature_it_cached():
    """A cached signature is not a fact about the rules that asked for it.

    The dispatcher offers `_signature_unparseable` to every `when` expression
    on the slot, not only to the rule whose param target made it ask. So an
    extension that caches one and then fails has changed the namespace the
    rules it never touched are evaluated in, and `_unextend` removing only the
    specs would leave that behind: the rule is gone and its residue is still
    being read.

    Dropped rather than restored from a saved value, because the write happens
    only on a slot with no answer yet. That is also what keeps a re-entrant
    call's own answer safe: an extension that found one already there wrote
    nothing and takes nothing back.

    Proved by asking again. A cache the failed call left behind would answer a
    later param rule without consulting the callable, so the count of reads is
    what says whether the question was genuinely re-opened.
    """
    Unintrospectable.asked = 0
    victim = types.ModuleType(MODNAME19)
    setattr(victim, "f", Unintrospectable())
    sys.modules[MODNAME19] = victim
    holder = types.ModuleType(MODNAME20)
    setattr(holder, "via", victim)
    setattr(holder, "g", lambda *a, **k: "real-g")
    sys.modules[MODNAME20] = holder
    try:
        # A second Patcher takes `g`, so walking MODNAME20 refuses after the
        # extension above it has already been made.
        thief = Patcher([crule("thief", "entry",
                               {"kind": "return_value", "value": "THIEF"},
                               symbol="g", module=MODNAME20)], None)
        thief.force_patch_module(MODNAME20)

        log = Recorder()
        rules = [
            # Asks for nothing itself, and is the rule that must not be able to
            # tell that another one ever asked.
            crule("watcher", "entry", {"kind": "sleep", "ms": 0},
                  symbol="f", module=MODNAME19),
            crule("asks", "entry",
                  {"kind": "pragma", "name": "synchronous", "value": "OFF",
                   "target": "param:x"},
                  symbol="via.f", module=MODNAME20),
            crule("doomed", "entry", {"kind": "sleep", "ms": 0},
                  symbol="g", module=MODNAME20),
        ]
        p = Patcher(rules, log)
        p.force_patch_module(MODNAME19)
        comp = victim.f._pyteman_composite
        assert comp.sig_unparseable is False, "nothing has asked yet"

        with pytest.raises(SlotOwnershipError):
            p.force_patch_module(MODNAME20)

        assert Unintrospectable.asked == 1, "the extension never asked"
        assert comp.sig is None
        assert comp.sig_unparseable is False
        assert [s[0].id for s in comp.rank()] == ["watcher"]

        # Asked AGAIN when a param rule reaches the slot for real, which is
        # what says the answer was dropped rather than merely hidden. The
        # rolled-back call is the only reason the slot had one at all.
        assert thief.uninstall() == []
        p.force_patch_module(MODNAME20)
        assert Unintrospectable.asked == 2
        assert [s[0].id for s in comp.rank()] == ["watcher", "asks"]
        assert comp.sig_unparseable is True
    finally:
        sys.modules.pop(MODNAME19, None)
        sys.modules.pop(MODNAME20, None)


MODNAME21 = "pyteman_atomic_victim_nested_sig"
MODNAME22 = "pyteman_atomic_victim_nested_sig_a"
MODNAME23 = "pyteman_atomic_victim_nested_sig_b"


class ReentersWithAnotherParamRule:
    """Brings a SECOND param rule to this slot from inside the first one's read."""

    patcher: object = None
    asked = 0

    def __call__(self, x):
        return "real"

    @property
    def __signature__(self):
        ReentersWithAnotherParamRule.asked += 1
        if ReentersWithAnotherParamRule.asked == 1:
            ReentersWithAnotherParamRule.patcher.force_patch_module(MODNAME23)
        raise TypeError("unintrospectable")


def test_a_failed_call_leaves_a_signature_a_nested_call_published():
    """Taking back a cached signature stops at the ones this call cached.

    The failing call is not always the one that answered. A re-entry during its
    signature read can reach the same slot, ask first, publish the answer and
    install rules of its own that have been read against it ever since. The
    failing call then finds the question already settled, writes nothing, and
    owes nothing back: resetting anyway would reach past its own additions into
    a call that succeeded, which is the overshoot _unextend exists to avoid,
    arriving through the signature rather than through the rule lists.
    """
    ReentersWithAnotherParamRule.asked = 0
    victim = types.ModuleType(MODNAME21)
    setattr(victim, "f", ReentersWithAnotherParamRule())
    sys.modules[MODNAME21] = victim
    alias_a = types.ModuleType(MODNAME22)
    setattr(alias_a, "via", victim)
    setattr(alias_a, "g", lambda *a, **k: "real-g")
    sys.modules[MODNAME22] = alias_a
    alias_b = types.ModuleType(MODNAME23)
    setattr(alias_b, "other", victim)
    sys.modules[MODNAME23] = alias_b
    try:
        thief = Patcher([crule("thief", "entry",
                               {"kind": "return_value", "value": "THIEF"},
                               symbol="g", module=MODNAME22)], None)
        thief.force_patch_module(MODNAME22)

        pragma = {"kind": "pragma", "name": "synchronous", "value": "OFF",
                  "target": "param:x"}
        rules = [
            crule("early", "entry", {"kind": "sleep", "ms": 0},
                  symbol="f", module=MODNAME21),
            # Opens the window, and is rolled back with the call that made it.
            crule("doomed_param", "entry", dict(pragma),
                  symbol="via.f", module=MODNAME22),
            crule("doomed", "entry", {"kind": "sleep", "ms": 0},
                  symbol="g", module=MODNAME22),
            # Arrives through the window, and survives.
            crule("nested_param", "entry", dict(pragma),
                  symbol="other.f", module=MODNAME23),
        ]
        p = Patcher(rules, Recorder())
        ReentersWithAnotherParamRule.patcher = p
        p.force_patch_module(MODNAME21)
        comp = victim.f._pyteman_composite

        with pytest.raises(SlotOwnershipError):
            p.force_patch_module(MODNAME22)

        assert ReentersWithAnotherParamRule.asked == 2, \
            "the two calls did not both reach the read"
        # The nested call asked first, so the answer is its own and stays.
        assert comp.sig_unparseable is True
        assert [s[0].id for s in comp.rank()] == ["early", "nested_param"]
        assert p.applied == [f"{MODNAME21}:f", f"{MODNAME23}:other.f"]

        assert thief.uninstall() == []
    finally:
        ReentersWithAnotherParamRule.patcher = None
        sys.modules.pop(MODNAME21, None)
        sys.modules.pop(MODNAME22, None)
        sys.modules.pop(MODNAME23, None)


MODNAME24 = "pyteman_atomic_victim_remerge_nosig"
MODNAME25 = "pyteman_atomic_victim_remerge_nosig_alias"


class ReentersFromItsAction:
    """Re-enters from `action`, the read that comes BEFORE the signature read.

    ReentersDuringExtension above re-enters from `__signature__`, so it travels
    through the signature block. This one never gets there. `action` is read
    first, to decide whether a signature is wanted at all, and the answer it
    returns is an ordinary action that wants none. The block is skipped whole,
    and with it anything that block contains.
    """

    patcher: object = None
    ran = False

    id = "late"
    module = MODNAME25
    symbol = "via.f"
    event = "entry"
    when = None
    # Fires on the SECOND reach, which is what turns a duplicated spec from a
    # bookkeeping detail into a firing the operator did not ask for.
    fire = {"mode": "countdown", "n": 1}

    @property
    def action(self):
        if not ReentersFromItsAction.ran:
            ReentersFromItsAction.ran = True
            ReentersFromItsAction.patcher.force_patch_module(MODNAME25)
        return {"kind": "sleep", "ms": 0}


def test_an_extension_that_needs_no_signature_still_re_asks_the_manifest():
    """The re-filter cannot live under the test for whether to read a signature.

    Three reads in the extension can run target code, and only the middle one is
    the signature. `_needs_signature` reads `action` and stringifies `target`
    before it, the entry/exit split reads `event` after it. The first of those is
    also a term of the condition guarding the signature read, so a rule that
    re-enters from `action` and then answers "no signature needed" takes that
    condition to False and skips the block: the manifest is never re-asked, and
    the merge below proceeds against rules the re-entry has already installed.

    The consequence is the duplicate ReentersDuringExtension describes, reached
    by the path that test cannot reach. Two specs on one rule means two `fires`
    counters, so a `countdown` rule arrives at its threshold twice in the same
    call, and the manifest stays silent about it because `served` keeps one spec
    per rule no matter how many the entry list carries.
    """
    victim = types.ModuleType(MODNAME24)
    setattr(victim, "f", lambda x: "real")
    sys.modules[MODNAME24] = victim
    holder = types.ModuleType(MODNAME25)
    setattr(holder, "via", victim)
    sys.modules[MODNAME25] = holder
    ReentersFromItsAction.ran = False
    try:
        log = Recorder()
        rules = [
            crule("early", "entry", {"kind": "sleep", "ms": 0},
                  symbol="f", module=MODNAME24),
            ReentersFromItsAction(),
        ]
        p = Patcher(rules, log)
        ReentersFromItsAction.patcher = p
        p.force_patch_module(MODNAME24)
        p.force_patch_module(MODNAME25)

        assert ReentersFromItsAction.ran, "the re-entry never happened"
        dispatcher = victim.f
        comp = dispatcher._pyteman_composite

        assert [s[0].id for s in comp.entries] == ["early", "late"]
        assert [s[0].id for s in comp.rank()] == ["early", "late"]
        assert len(dispatcher._pyteman_state) == len(comp.entries)
        assert len({id(s[3]) for s in comp.entries}) == 2
        assert p.applied == [f"{MODNAME24}:f", f"{MODNAME25}:via.f"]

        # What the duplicate costs, at the only place an operator would meet it.
        # The threshold belongs to the rule, not to the spec, so `late` fires on
        # the second CALL and once there. Two states would spend both reaches of
        # that call and fire twice, then never again.
        fired = []
        for _ in range(3):
            log.seen.clear()
            dispatcher(1)
            fired.append(log.ids)
        assert fired == [["early"], ["early", "late"], ["early"]]
        assert [s[3]["fires"] for s in comp.entries] == [3, 3]
    finally:
        ReentersFromItsAction.patcher = None
        sys.modules.pop(MODNAME24, None)
        sys.modules.pop(MODNAME25, None)


MODNAME26 = "pyteman_atomic_victim_inflight"
MODNAME27 = "pyteman_atomic_victim_inflight_alias"


class ReentersFromSetattr(types.ModuleType):
    """A container that runs target code on the write, AFTER the value lands.

    The re-entrancy classes above all open their window on a READ: a property,
    a `__signature__`, an `action`. This one opens it on the write itself, which
    is the one statement the in-flight map was supposed to cover and the only
    place a dispatcher is live in its attribute while no ledger names it.

    super() first, deliberately. Re-entering before it is the other window, the
    one where the nested call installs and this call writes over it; that is
    TASK-122 and fails by losing a wrap. This one fails by nesting one.
    """

    patcher: object = None
    ran = False

    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        if (name == "f" and not ReentersFromSetattr.ran
                and getattr(value, "_pyteman_owner", None) is not None):
            ReentersFromSetattr.ran = True
            ReentersFromSetattr.patcher.force_patch_module(MODNAME27)


def test_a_dispatcher_is_answerable_as_ours_before_the_write_not_after():
    """A re-entry from the write itself must still find the slot ours.

    `_inflight` exists so that a dispatcher sitting in its attribute, before the
    module-wide publish, does not read as a stranger to the Patcher that put it
    there. It was registered one statement AFTER the setattr, so for the width of
    that write the map answered no, and `setattr` is not inert: a metaclass or a
    `ModuleType` subclass runs target code on it.

    A nested call landing there is told the live dispatcher belongs to nobody. It
    does not extend it and it does not refuse it. It WRAPS it, and the slot ends
    up carrying two of our dispatchers and the ledger two entries for one
    attribute. The LIFO undo then hands the outer entry a slot holding an object
    it does not recognise, which is the third-party contract, so it releases and
    reports nothing refused, and the inner entry restores the dispatcher
    underneath. `uninstall()` answers `[]` over a callable that is still
    instrumented and still firing.
    """
    victim = ReentersFromSetattr(MODNAME26)
    victim.f = lambda x: "real"
    sys.modules[MODNAME26] = victim
    holder = types.ModuleType(MODNAME27)
    setattr(holder, "via", victim)
    sys.modules[MODNAME27] = holder
    ReentersFromSetattr.ran = False
    try:
        log = Recorder()
        rules = [crule("base", "entry", {"kind": "sleep", "ms": 0},
                       symbol="f", module=MODNAME26),
                 crule("aliased", "entry", {"kind": "sleep", "ms": 0},
                       symbol="via.f", module=MODNAME27)]
        p = Patcher(rules, log)
        ReentersFromSetattr.patcher = p
        p.force_patch_module(MODNAME26)

        assert ReentersFromSetattr.ran, "the re-entry never happened"

        # One attribute, one wrapper, one entry to put back. Two entries here
        # are two undos racing over one slot.
        assert len(p._wrapped) == 1
        dispatcher = victim.__dict__["f"]
        assert getattr(dispatcher, "__wrapped__", None) is not dispatcher
        assert getattr(getattr(dispatcher, "__wrapped__", None),
                       "_pyteman_owner", None) is None, \
            "our dispatcher was wrapped in a second one"

        # The nested call's rule went INTO the dispatcher rather than around it.
        comp = dispatcher._pyteman_composite
        assert [s[0].id for s in comp.rank()] == ["base", "aliased"]
        assert sorted(p.applied) == sorted(
            [f"{MODNAME26}:f", f"{MODNAME27}:via.f"])

        assert victim.f(1) == "real"
        assert log.ids == ["base", "aliased"]

        # The consequence an operator meets. A slot left instrumented under a
        # clean report is the failure this whole file exists to prevent.
        assert p.uninstall() == []
        assert getattr(victim.__dict__["f"], "_pyteman_owner", None) is None
        log.seen.clear()
        assert victim.f(1) == "real"
        assert log.ids == []
    finally:
        ReentersFromSetattr.patcher = None
        sys.modules.pop(MODNAME26, None)
        sys.modules.pop(MODNAME27, None)


MODNAME28 = "pyteman_atomic_victim_leaked"
MODNAME29 = "pyteman_atomic_victim_leaked_alias"


class LeaksBeforeSuper(types.ModuleType):
    """A container that publishes the incoming value elsewhere, then re-enters.

    `ReentersFromSetattr` above calls super() first, so the re-entry finds the
    dispatcher in the slot it was written to. This one never gets that far: it
    copies `value` into a second module and re-enters while its own attribute
    still holds the original. The dispatcher is reachable anyway, off the
    attribute the leak created.
    """

    patcher: object = None
    holder: object = None
    ran = False
    slot_held_the_dispatcher = None

    def __setattr__(self, name, value):
        if (name == "f" and not LeaksBeforeSuper.ran
                and getattr(value, "_pyteman_owner", None) is not None):
            LeaksBeforeSuper.ran = True
            LeaksBeforeSuper.slot_held_the_dispatcher = (
                self.__dict__.get("f") is value)
            setattr(LeaksBeforeSuper.holder, "leaked", value)
            LeaksBeforeSuper.patcher.force_patch_module(MODNAME29)
        super().__setattr__(name, value)


def test_a_dispatcher_reached_through_a_leak_is_extended_not_wrapped():
    """The in-flight window is safe because of the answer, not unreachability.

    Registering in `_inflight` before the setattr is what closes the window the
    test above pins, and the tempting reading of why is that the dispatcher is
    in no attribute yet so nothing can ask about it. That reading is wrong.
    `setattr` hands the object to `__setattr__` as its `value`, so a container
    can put it somewhere of its own and re-enter from there, and the re-entry
    reads it off a real attribute while the intended slot still holds the
    original.

    What makes it harmless is the answer that reader gets. Told the dispatcher
    is ours, it takes the branch that extends an existing dispatcher: no second
    wrapper, no second ledger entry, and the leaked rule joins the composite
    instead of a layer around it. This test pins that branch, which is the part
    an edit to the `owner is self` path could quietly break while the test above
    kept passing.
    """
    victim = LeaksBeforeSuper(MODNAME28)
    sys.modules[MODNAME28] = victim
    holder = types.ModuleType(MODNAME29)
    sys.modules[MODNAME29] = holder
    LeaksBeforeSuper.holder = holder
    LeaksBeforeSuper.ran = False
    LeaksBeforeSuper.slot_held_the_dispatcher = None
    victim.f = lambda x: "real"
    try:
        log = Recorder()
        rules = [crule("base", "entry", {"kind": "sleep", "ms": 0},
                       symbol="f", module=MODNAME28),
                 crule("leaked", "entry", {"kind": "sleep", "ms": 0},
                       symbol="leaked", module=MODNAME29)]
        p = Patcher(rules, log)
        LeaksBeforeSuper.patcher = p
        p.force_patch_module(MODNAME28)

        assert LeaksBeforeSuper.ran, "the re-entry never happened"
        assert LeaksBeforeSuper.slot_held_the_dispatcher is False, \
            "the leak did not run before the write it was meant to precede"

        assert len(p._wrapped) == 1
        dispatcher = victim.__dict__["f"]
        assert holder.leaked is dispatcher
        assert getattr(getattr(dispatcher, "__wrapped__", None),
                       "_pyteman_owner", None) is None, \
            "our dispatcher was wrapped in a second one"

        comp = dispatcher._pyteman_composite
        assert [s[0].id for s in comp.rank()] == ["base", "leaked"]
        assert victim.f(1) == "real"
        assert log.ids == ["base", "leaked"]

        assert p.uninstall() == []
        assert getattr(victim.__dict__["f"], "_pyteman_owner", None) is None
    finally:
        LeaksBeforeSuper.patcher = None
        LeaksBeforeSuper.holder = None
        sys.modules.pop(MODNAME28, None)
        sys.modules.pop(MODNAME29, None)


# --- callables whose work does not happen during the call -------------------
#
# A dispatcher records entry before calling the original and exit after it
# returns. A coroutine function, a generator function and an async generator
# function all return a suspended object from the call and run their body
# later, so both records describe a moment nobody asked about, and an action
# supplying a return value hands back an ordinary object where an awaitable or
# an iterator was expected. An exit action goes further and discards the
# suspended object entirely, so the body never runs; that damage is the same
# for all three, and only the coroutine case leaves a trace, a RuntimeWarning
# whenever the collector reaches the orphan. These cover the refusal that keeps
# such a slot unmutated.
#
# What the refusal reads is call semantics and nothing else: the three kind
# predicates, functools.partial.func, and the type's __call__. It deliberately
# does NOT read __wrapped__, which records where a wrapper came from and says
# nothing about what calling it does. The positive cases below are the reason.
# A @contextlib.contextmanager function is synchronous and wraps a generator
# function; a synchronous adapter built with functools.wraps around an
# `async def` is an ordinary function. Both would be refused by a walk that
# followed provenance, and both are correct to instrument. The price is that a
# synchronous adapter which really does hand back the awaitable is outside what
# this gate can decide, the same way an ordinary `def` returning a coroutine
# is, and it is left instrumentable rather than guessed at.

MODNAME30 = "pyteman_atomic_victim_suspendable"

# Appended to by the bodies that run on invocation. Only a synchronous shape
# can report here at all: calling a coroutine or generator function builds an
# object and runs no body, so an empty RAN says nothing about those. What it
# does bear on is `detector`, a recording function behind a partial, which is a
# shape the gate walks into and a shape whose body a call really would run.
# Classification has to leave RAN empty and invoking the original has to fill
# it, and the second half is what keeps the first from passing because nothing
# could ever have appended.
RAN = []


def _suspendable_module():
    """One attribute per shape the refusal has to decide.

    Spelled out rather than generated from a table, because what is under test
    is the shape of the object sitting in the slot and a factory would put its
    own closure in front of half of them.
    """
    mod = types.ModuleType(MODNAME30)

    async def coro(a):
        return a

    def gen(a):
        yield a

    async def agen(a):
        yield a

    class AsyncCallable:
        async def __call__(self, a):
            return a

    class WrappedIsAProperty:
        @property
        def __wrapped__(self):
            raise RuntimeError("the gate read __wrapped__")

        def __call__(self, a):
            return a

    class HostileClass:
        @property
        def __class__(self):
            raise RuntimeError("hostile __class__")

        def __call__(self, a):
            return a

    @contextlib.contextmanager
    def managed(a):
        yield a

    @functools.wraps(coro)
    def sync_adapter(a):
        # Provenance says coroutine function, call semantics say otherwise:
        # this returns a value, and instrumenting it times a real call.
        return a

    @functools.wraps(gen)
    def listified(a):
        return list(gen(a))

    def link_one(a):
        return a

    def link_two(a):
        return a

    link_one.__wrapped__ = link_two
    link_two.__wrapped__ = link_one

    def records(a):
        RAN.append("detector")
        return a

    def sync_stored(a):
        return a

    # The four shapes below all put the deciding kind somewhere the predicates
    # do not look. A partial subclass that defines __call__ calls `func` only
    # if its own body says so, yet the predicates unwrap `func` and answer
    # about it, so the stored callable is deliberately the OPPOSITE kind to the
    # override in every one of them: whichever the gate reports, it can only
    # have got there by reading the right one.
    class AsyncOverridingPartial(functools.partial):
        async def __call__(self, a):
            return a

    class GenOverridingPartial(functools.partial):
        def __call__(self, a):
            yield a

    class AsyncGenOverridingPartial(functools.partial):
        async def __call__(self, a):
            yield a

    class SyncOverridingPartial(functools.partial):
        # The same trap facing the other way, and the one that matters most:
        # calling this returns a value, so refusing it would be the false
        # positive that walking __wrapped__ produced and that got that walk
        # removed. A gate reading `func` reports a coroutine function here.
        def __call__(self, a):
            return a

    # A __call__ can hold its callable in a form that is not a plain function.
    # These are the spellings that were found doing it.
    class StaticmethodCallIsAsync:
        __call__ = staticmethod(coro)

    class PartialCallIsAsync:
        __call__ = functools.partial(coro)

    class ClassmethodCallIsAsync:
        @classmethod
        async def __call__(cls, a):
            return a

    # The same edge in the direction that must NOT refuse. CPython hands the
    # instance to the slot only for callables carrying the method-descriptor
    # flag, which a plain function has and neither of these two does: the
    # staticmethod below is called as sync_slot(5), and the classmethod above
    # arrives already bound to the class, so its `cls` is filled by the binding
    # and `a` takes the 5. Measured on 3.11 through 3.14, and the reason each
    # of these takes exactly one argument of its own.
    def sync_slot(a):
        return a

    class StaticmethodCallIsSync:
        __call__ = staticmethod(sync_slot)

    # A call slot holding a descriptor that holds another one. CPython unwraps
    # the outer layer before the call happens, so what runs is whatever the
    # INNER one holds, and the gate has to walk the same distance to see it.
    class NestedStaticmethodCallIsAsync:
        __call__ = staticmethod(staticmethod(coro))

    class NestedStaticmethodCallIsSync:
        __call__ = staticmethod(staticmethod(sync_slot))

    class ClassmethodCallIsSync:
        @classmethod
        def __call__(cls, a):
            return a

    # Whether this is a two-layer nest or one flattened partial is decided by
    # the interpreter, not by the test: subclasses flatten on 3.13 and 3.14 and
    # do not on 3.11 and 3.12. Kept here as the pair, and judged against what
    # calling it actually does, by the one test below that asks.
    class PlainPartial(functools.partial):
        pass

    nested_pair = PlainPartial(SyncOverridingPartial(coro))

    setattr(mod, "coro", coro)
    setattr(mod, "gen", gen)
    setattr(mod, "agen", agen)
    setattr(mod, "partial_coro", functools.partial(coro))
    setattr(mod, "instance", AsyncCallable())
    # The composite the predicates do not reduce on their own. Unwrapping this
    # one lands on an instance and they stop; reaching the kind needs
    # partial.func and then the type's __call__.
    setattr(mod, "partial_instance", functools.partial(AsyncCallable()))
    setattr(mod, "hostile", HostileClass())
    setattr(mod, "subclass_async", AsyncOverridingPartial(sync_stored))
    setattr(mod, "subclass_gen", GenOverridingPartial(coro))
    setattr(mod, "subclass_agen", AsyncGenOverridingPartial(sync_stored))
    setattr(mod, "static_call", StaticmethodCallIsAsync())
    setattr(mod, "partial_call", PartialCallIsAsync())
    setattr(mod, "classmethod_call", ClassmethodCallIsAsync())
    setattr(mod, "plain", lambda a: a)
    setattr(mod, "managed", managed)
    setattr(mod, "sync_adapter", sync_adapter)
    setattr(mod, "listified", listified)
    setattr(mod, "subclass_sync", SyncOverridingPartial(coro))
    setattr(mod, "static_sync", StaticmethodCallIsSync())
    setattr(mod, "nested_static_call", NestedStaticmethodCallIsAsync())
    setattr(mod, "nested_static_sync", NestedStaticmethodCallIsSync())
    setattr(mod, "classmethod_sync", ClassmethodCallIsSync())
    setattr(mod, "nested_pair", nested_pair)
    setattr(mod, "cyclic", link_one)
    setattr(mod, "property_wrapped", WrappedIsAProperty())
    setattr(mod, "detector", functools.partial(records))
    return mod


@pytest.fixture
def suspendable():
    mod = _suspendable_module()
    sys.modules[MODNAME30] = mod
    RAN.clear()
    try:
        yield mod
    finally:
        del sys.modules[MODNAME30]
        RAN.clear()


@pytest.mark.parametrize("symbol, reason", [
    ("coro", "a coroutine function"),
    ("gen", "a generator function"),
    ("agen", "an async generator function"),
    # The plain single partial. One `func` arc and then the predicate, which
    # is the shortest path through the walk.
    ("partial_coro", "a coroutine function"),
    # Reached only by reading the type's __call__ without calling it.
    ("instance", "a coroutine function"),
    # Reached only by following partial.func AND then the type's __call__.
    ("partial_instance", "a coroutine function"),
    # A partial subclass that defines __call__ decides there, not in the `func`
    # the predicates unwrap to. The stored callable is the opposite kind in all
    # three, so reading the wrong one cannot produce these answers by accident.
    ("subclass_async", "a coroutine function"),
    ("subclass_gen", "a generator function"),
    ("subclass_agen", "an async generator function"),
    # A __call__ that holds its callable as a staticmethod, a partial or a
    # classmethod rather than as a plain function. All three really do return
    # a coroutine.
    ("static_call", "a coroutine function"),
    ("partial_call", "a coroutine function"),
    ("classmethod_call", "a coroutine function"),
    # The same slot one layer deeper. A single hop off the outer descriptor
    # lands on another descriptor, which is neither a function nor a partial,
    # and a walk that stops there instruments a coroutine function in silence.
    ("nested_static_call", "a coroutine function"),
])
def test_a_suspendable_target_is_refused_with_its_slot_untouched(
        suspendable, symbol, reason):
    """The refusal names the kind, the point and the rule, and mutates nothing.

    All three halves matter. An operator who wrote the rule needs to know which
    rule to go and edit, which is why the description is in the message; and
    the slot has to still hold the original, because a refusal that left a
    half-built dispatcher behind would be worse than the mistimed record it
    was avoiding.
    """
    before = getattr(suspendable, symbol)
    import_before = builtins.__import__
    rules = [make_rule(symbol, "r-" + symbol, module=MODNAME30)]
    with pytest.raises(SuspendableTargetError) as excinfo:
        activate(rules, log=None, modules=[MODNAME30])
    message = str(excinfo.value)
    assert reason in message, message
    assert MODNAME30 + ":" + symbol in message, message
    assert "'r-" + symbol + "'" in message, message
    assert getattr(suspendable, symbol) is before
    assert builtins.__import__ is import_before


@pytest.mark.parametrize("symbol", ["cyclic", "property_wrapped"])
def test_provenance_alone_does_not_refuse_and_is_never_read(
        suspendable, symbol):
    """__wrapped__ is not consulted, which these two make visible.

    An earlier draft of this gate walked it, and the cost was the positive
    cases in the test below: a link that records where a wrapper came from was
    being read as a claim about what calling it does. Both attributes here are
    ordinary synchronous callables wearing a __wrapped__ that a walk would
    choke on. `cyclic` points at a function that points back at it, so a walk
    following provenance either loops or refuses. `property_wrapped` puts it
    behind a property that raises the moment anything reads it, so an
    exception here would be the gate touching it; getting an installed
    dispatcher instead is the evidence that it does not.
    """
    before = getattr(suspendable, symbol)
    p = activate([make_rule(symbol, "r", module=MODNAME30)], log=None,
                 modules=[MODNAME30])
    try:
        assert p.applied == [MODNAME30 + ":" + symbol]
        assert getattr(suspendable, symbol)(5) == 1
    finally:
        p.uninstall()
    assert getattr(suspendable, symbol) is before


def test_an_introspection_error_is_refused_and_keeps_its_cause(suspendable):
    """A target that breaks the check is reported as one, cause attached.

    The message says the kind could not be read and names the exception, and
    the original is chained rather than summarised, so the traceback still
    points at the line in the target that raised.
    """
    before = getattr(suspendable, "hostile")
    rules = [make_rule("hostile", "r-hostile", module=MODNAME30)]
    with pytest.raises(SuspendableTargetError) as excinfo:
        activate(rules, log=None, modules=[MODNAME30])
    message = str(excinfo.value)
    assert "could not be read" in message, message
    assert "hostile __class__" in message, message
    assert isinstance(excinfo.value.__cause__, RuntimeError)
    assert getattr(suspendable, "hostile") is before


def test_a_refusal_unwinds_the_wraps_the_same_call_already_made(suspendable):
    """Whole ruleset or none of it, measured at the activate() boundary.

    What this pins is the guarantee an operator sees: the call raised and the
    module is as it was. It cannot say WHICH handler did the restoring, because
    activate() catches and calls uninstall(), which restores the ledger on its
    own. The test below removes that second handler and asks the narrower
    question.
    """
    import_before = builtins.__import__
    plain_before = getattr(suspendable, "plain")
    coro_before = getattr(suspendable, "coro")
    rules = [make_rule("plain", "sync-first", module=MODNAME30),
             make_rule("coro", "coro-second", module=MODNAME30)]
    with pytest.raises(SuspendableTargetError) as excinfo:
        activate(rules, log=None, modules=[MODNAME30])
    # The refusal names the rule that caused it, not the one already applied.
    assert "'coro-second'" in str(excinfo.value), str(excinfo.value)
    assert getattr(suspendable, "plain") is plain_before
    assert getattr(suspendable, "coro") is coro_before
    assert getattr(suspendable, "plain")(3) == 3
    assert builtins.__import__ is import_before


def test_the_refusal_is_undone_by_the_patch_call_that_raised(suspendable):
    """The same claim with activate()'s safety net taken away.

    activate() is not the only door. A module imported after install() is
    patched by the import hook, and there the refusal comes out of the
    operator's own `import` statement with nobody above it to call uninstall().
    Whatever that call wrapped before it refused has to be put back by the call
    itself, or the process runs with a rule installed while being told
    activation failed, which is injection nobody authored.

    Driving force_patch_module directly is that door reduced to its decisive
    part: same code path as the hook, no wrapper catching anything. Deleting
    the restore inside _patch leaves the test above green and this one red.
    """
    plain_before = getattr(suspendable, "plain")
    managed_before = getattr(suspendable, "managed")
    # Two wraps before the refusal, not one. With a single wrap a rollback that
    # settles only the newest entry is indistinguishable from one that settles
    # all of them, and `_restore` undoing exactly its last wrap is the shape
    # that leaves an earlier rule live under a ruleset reported as failed.
    rules = [make_rule("plain", "sync-first", module=MODNAME30),
             make_rule("managed", "sync-second", module=MODNAME30),
             make_rule("coro", "coro-third", module=MODNAME30)]
    writes = []

    class Recording(types.ModuleType):
        """Remembers what this call wrote, because the end state cannot say.

        A call that wrapped and then took the wrap back leaves a slot
        indistinguishable from one that was never touched, so every assertion
        below is equally satisfied by an implementation that judges `coro`
        first and never reaches the other two. Measured: reversing the slot
        order leaves this test green with the restore deleted outright.
        """

        def __setattr__(self, name, value):
            state = getattr(value, "_pyteman_state", None)
            writes.append((name, state is not None))
            super().__setattr__(name, value)

    suspendable.__class__ = Recording
    p = install(rules, log=None)
    try:
        with pytest.raises(SuspendableTargetError):
            p.force_patch_module(MODNAME30)
        # Both dispatchers went in, and both originals came back inside the
        # call that raised. Newest first on the way out, which is the order
        # _restore documents and which one wrap cannot express.
        assert writes == [("plain", True), ("managed", True),
                          ("managed", False), ("plain", False)], writes
        assert getattr(suspendable, "plain") is plain_before
        assert getattr(suspendable, "managed") is managed_before
        assert getattr(suspendable, "plain")(3) == 3
        # `applied` is the note and `_wrapped` is the ledger, and the claim
        # needs both: nothing survived for uninstall to find, and nothing was
        # published that the slot would disagree with.
        assert p.applied == []
        assert p._wrapped == []
    finally:
        suspendable.__class__ = types.ModuleType
        p.uninstall()


@pytest.mark.parametrize("symbol", [
    "plain",
    # Synchronous, and wrapping a generator function. A gate reading provenance
    # would call this a generator function and refuse the commonest decorator
    # in the standard library.
    "managed",
    # The mirror image: provenance says `async def`, the call returns a value.
    "sync_adapter",
    # And the same for a generator turned into a collection.
    "listified",
    # A partial subclass whose own __call__ is synchronous, over a stored
    # `async def`. Calling it returns a value, so refusing it would be the same
    # false positive that reading provenance produced: the gate would be
    # answering about a callable this object never invokes.
    "subclass_sync",
    # The staticmethod and classmethod call slots in the direction that must
    # not refuse, so the edge added for the async case cannot pass by refusing
    # everything it sees.
    "static_sync",
    "classmethod_sync",
    # The nested slot in the direction that must not refuse, so the deeper
    # walk cannot pass its own negative case by refusing whatever it reaches.
    "nested_static_sync",
])
def test_ordinary_synchronous_callables_are_still_patched(
        suspendable, symbol):
    """The control the refusals above would otherwise pass vacuously without.

    A gate that refused everything would satisfy every assertion in the
    refusal tests. These are all shapes an operator has a real reason to
    instrument, and most of them are ones an over-eager walk took away.
    """
    before = getattr(suspendable, symbol)
    p = activate([make_rule(symbol, "r", module=MODNAME30)], log=None,
                 modules=[MODNAME30])
    try:
        assert p.applied == [MODNAME30 + ":" + symbol]
        assert getattr(suspendable, symbol) is not before
        assert getattr(suspendable, symbol)(5) == 1
    finally:
        p.uninstall()
    assert getattr(suspendable, symbol) is before


def test_the_synchronous_call_slots_are_callable_as_written(suspendable):
    """The positive table above cannot tell a real fixture from a broken one.

    Its rule returns 1 without ever invoking the original, so a __call__ whose
    parameter list does not match how CPython actually invokes the slot sails
    through it: the gate lets the object past, the dispatcher answers 1, and
    nothing calls the callable that would have raised. Both of these were
    written from a wrong account of that convention once already. Calling them
    here is what makes their entries above mean the gate passed something that
    works, rather than the gate passed something.
    """
    assert suspendable.static_sync(5) == 5
    assert suspendable.classmethod_sync(5) == 5
    assert suspendable.nested_static_sync(5) == 5


def test_a_nested_partial_is_judged_by_the_layout_the_interpreter_built(
        suspendable):
    """Whether the nest exists is the interpreter's choice, so the test asks.

    PlainPartial(SyncOverridingPartial(coro)) is two layers on 3.11 and 3.12,
    where the outer partial keeps the subclass instance and calling it reaches
    the synchronous override, and one flattened partial holding `coro` on 3.13
    and 3.14, where the override is discarded at construction and calling it
    really does return a coroutine. Both are correct behaviour for their
    version, and the verdict that is correct differs with them.

    So the expectation is taken from the object rather than from a version
    number: call it once, see what comes back, and require the gate to agree.
    That is the property the gate actually owes, it holds on every interpreter
    including ones not yet released, and it fails loudly if a future version
    changes the layout again. Asserting a fixed answer here would have to
    encode the 3.13 boundary in the test suite, which is how the false positive
    this test exists for got written in the first place.
    """
    before = suspendable.nested_pair
    result = before(5)
    rules = [make_rule("nested_pair", "r-nested", module=MODNAME30)]

    if inspect.iscoroutine(result):
        result.close()
        with pytest.raises(SuspendableTargetError) as excinfo:
            activate(rules, log=None, modules=[MODNAME30])
        assert "a coroutine function" in str(excinfo.value), str(excinfo.value)
        assert suspendable.nested_pair is before
        return

    assert result == 5, result
    p = activate(rules, log=None, modules=[MODNAME30])
    try:
        assert p.applied == [MODNAME30 + ":nested_pair"]
        assert suspendable.nested_pair is not before
        assert suspendable.nested_pair(5) == 1
    finally:
        p.uninstall()
    assert suspendable.nested_pair is before


def test_deciding_the_kind_does_not_call_the_callable(suspendable):
    """Read, never run, measured on a shape where running would show.

    Most of the refused shapes cannot report this. Calling a coroutine or a
    generator function builds an object and executes no body, so a gate that
    called them would leave no trace to assert on. `detector` is a recording
    function behind a partial: the walk goes through it, and a call really
    would run it. The second half of the test invokes the original and watches
    RAN fill, which is what stops the first half from passing because nothing
    could ever have appended.
    """
    before = getattr(suspendable, "detector")
    p = activate([make_rule("detector", "r", module=MODNAME30)], log=None,
                 modules=[MODNAME30])
    try:
        assert p.applied == [MODNAME30 + ":detector"]
        assert RAN == []
    finally:
        p.uninstall()
    assert getattr(suspendable, "detector") is before
    assert before(5) == 5
    assert RAN == ["detector"]


def _nested_static(depth, terminal):
    for _ in range(depth):
        terminal = staticmethod(terminal)
    return terminal


def _call_slot_instance(slot):
    return type("Slotted", (), {"__call__": slot})()


def _assert_the_verdict_matches_the_call(instance):
    """Call the object once and require the gate to agree with what came back.

    Every test below takes its expectation from here rather than stating one.
    How many descriptor layers survive into a call is the interpreter's
    business, so a fixed answer would encode today's unwrapping convention in
    the suite and would go on passing after the convention moved.
    """
    produced = instance(5)
    reason, cause = _suspendable_reason(instance)
    assert cause is None
    if inspect.iscoroutine(produced):
        produced.close()
        assert reason == "a coroutine function", reason
    elif inspect.isgenerator(produced):
        produced.close()
        assert reason == "a generator function", reason
    else:
        assert produced == 5
        assert reason is None, reason


@pytest.mark.parametrize("terminal", ["coro", "gen", "sync"])
def test_a_nested_call_slot_is_judged_by_what_calling_it_returns(terminal):
    """A descriptor still sitting under a descriptor is walked to the bottom.

    One hop used to end the read, so a slot holding two layers answered
    nothing at all and the object was instrumented while calling it really
    returned a coroutine. The sync row is the control: the deeper walk must
    not buy its refusals by refusing everything it touches.
    """

    async def coro(a):
        return a

    def gen(a):
        yield a

    def sync(a):
        return a

    _assert_the_verdict_matches_the_call(_call_slot_instance(
        _nested_static(2, {"coro": coro, "gen": gen, "sync": sync}[terminal])))


@pytest.mark.parametrize("stored", ["coro", "sync"])
def test_a_call_slot_descriptor_is_read_for_what_it_stores(stored):
    """In this one position the stored callable decides, not the override.

    A descriptor met along the partial arc or sitting on a module attribute is
    asked what its own __call__ does first, because that is what invoking it
    runs. A descriptor sitting in a type's __call__ is not invoked at all:
    CPython resolves the slot through __get__ and calls what comes out, so the
    override never runs and the stored callable is what the caller reaches.
    Both subclasses below store the OPPOSITE kind to the one their override
    returns, so a verdict can only be right by having read the correct half,
    and the expectation is taken from calling the object rather than asserted.
    """

    async def coro(a):
        return a

    def sync(a):
        return a

    class SynchronousOverride(staticmethod):
        def __call__(self, a):
            return a

    class CoroutineOverride(staticmethod):
        async def __call__(self, a):
            return a

    override = SynchronousOverride if stored == "coro" else CoroutineOverride
    _assert_the_verdict_matches_the_call(_call_slot_instance(
        override({"coro": coro, "sync": sync}[stored])))


@pytest.mark.parametrize("outer,inner", [(staticmethod, classmethod),
                                         (classmethod, staticmethod),
                                         (classmethod, classmethod)])
@pytest.mark.parametrize("terminal", ["coro", "sync"])
def test_a_classmethod_layer_is_read_like_a_staticmethod_one(outer, inner,
                                                             terminal):
    """Both descriptor spellings are carried, and one of these really calls.

    Whether a nest of these is callable at all is the interpreter's business
    and it moved: `classmethod(staticmethod(coro))` in a slot really returns a
    coroutine on 3.11 and 3.12, and raises from 3.13, where classmethod lost
    the chaining __get__. Where the object does call, the verdict is taken
    from what came back, which is what makes those rows bite. Where it cannot
    be called, nothing it does can contradict a verdict, so the weaker claim
    is the one asserted: the read still reached the terminal underneath
    instead of stopping on the residue and answering nothing.
    """
    stored = _coroutine_terminal if terminal == "coro" else _plain_terminal
    instance = _call_slot_instance(outer(inner(stored)))
    reason, cause = _suspendable_reason(instance)
    assert cause is None
    try:
        produced = instance(5)
    except TypeError:
        # Not callable in this spelling on this interpreter.
        assert reason == ("a coroutine function" if terminal == "coro"
                          else None), reason
        return
    _assert_the_verdict_matches_the_call(instance)
    if inspect.iscoroutine(produced):
        produced.close()


@pytest.mark.parametrize("terminal", ["coro", "sync"])
def test_a_partial_subclass_reaches_a_nested_slot_too(terminal):
    """The residue is handed back at the partial call site as well.

    `_call_slot` is read on the partial edge before `func` is taken, so a
    partial subclass whose own __call__ holds a nest is the second way into
    the new return value. Special casing it to the other branches would leave
    this silently instrumented.

    `func` is given the OPPOSITE kind to the one the slot nest holds. The
    object really does what the slot says, so a walk that dropped the residue
    and fell back to `func` reaches a terminal of the other kind and disagrees
    with the call. Handing both ends the same callable lets that fallback
    arrive at the right verdict by the wrong route, which leaves the test
    green against code that never reads the slot at all.
    """
    stored = _coroutine_terminal if terminal == "coro" else _plain_terminal
    fallback = _plain_terminal if terminal == "coro" else _coroutine_terminal
    subclass = type("NestedPartial", (functools.partial,),
                    {"__call__": _nested_static(2, stored)})
    _assert_the_verdict_matches_the_call(subclass(fallback))


def test_nested_call_slots_spend_the_same_budget_as_every_other_edge():
    """One walk, one bound: the descriptor edge does not get its own.

    A nest deep enough to exhaust the budget is refused with the chain message
    rather than walked to its terminal, which is how this edge is kept from
    multiplying the limit or looping without one. The shallow nest below is
    the control: the refusal has to come from the depth and not from the shape.
    """
    shallow = _call_slot_instance(_nested_static(8, _plain_terminal))
    assert _suspendable_reason(shallow) == (None, None)
    deep = _call_slot_instance(
        _nested_static(_WRAPPER_CHAIN_LIMIT + 2, _plain_terminal))
    reason, cause = _suspendable_reason(deep)
    assert reason == ("reached through a chain of wrappers that did not end "
                      "within " + str(_WRAPPER_CHAIN_LIMIT) + " links"), reason
    assert cause is None


class _KeepsANest(functools.partial):
    """A partial subclass that really nests, for counting links.

    Plain `functools.partial(functools.partial(f))` cannot be used to build a
    chain of a known length: partial flattens a partial argument at
    construction, so any depth of that spelling is one link. Setting an
    instance attribute defeats the flattening on every version this package
    supports, which is the row the table above _WRAPPER_CHAIN_LIMIT records as
    2 for two layers on 3.11 through 3.14. One link per layer, measured rather
    than assumed, is what lets the boundary tests below name an exact number.
    """

    def __init__(self, *args, **kwargs):
        self.keeps_a_dict = True


def _links(count, terminal):
    for _ in range(count):
        terminal = _KeepsANest(terminal)
    return terminal


def _plain_terminal(a):
    return a


async def _coroutine_terminal(a):
    return a


@pytest.mark.parametrize("count", [_WRAPPER_CHAIN_LIMIT - 1, _WRAPPER_CHAIN_LIMIT])
def test_a_chain_at_the_limit_is_walked_to_its_terminal(count):
    """The budget is inclusive, and both sides of the boundary are asserted.

    The loop spends one iteration per link and one more on the terminal, so a
    chain of exactly _WRAPPER_CHAIN_LIMIT links has to fit. Without the `+ 1`
    in the range the last iteration takes a hop and never looks at what it
    landed on, and an ordinary synchronous function at the end of a full-length
    chain would be refused while calling it plainly returns a value. The
    coroutine case is the same walk asked to still be reading kinds at the far
    end rather than merely surviving the distance.
    """
    assert _suspendable_reason(_links(count, _plain_terminal)) == (None, None)
    reason, cause = _suspendable_reason(_links(count, _coroutine_terminal))
    assert reason == "a coroutine function", reason
    assert cause is None


def test_a_chain_one_link_past_the_limit_is_refused():
    """One more link than the budget, and the refusal names the bound.

    This is the negative control for the test above. Both terminals are
    refused for the same reason and neither is reported by its own kind: past
    the bound the walk never reaches the terminal to ask, so the coroutine is
    refused as an unterminated chain rather than as a coroutine. The message
    carries the number so an operator can tell this refusal from a kind.
    """
    expected = ("reached through a chain of wrappers that did not end within "
                + str(_WRAPPER_CHAIN_LIMIT) + " links")
    for terminal in (_plain_terminal, _coroutine_terminal):
        reason, cause = _suspendable_reason(_links(_WRAPPER_CHAIN_LIMIT + 1,
                                                   terminal))
        assert reason == expected, reason
        assert cause is None


def test_a_cycle_is_caught_by_the_bound_and_is_right_to_be_refused():
    """There is no cycle check, and this is why the bound stands in for one.

    A class whose __call__ is a partial over an instance of that same class
    closes a cycle through the __call__ edge, so the walk would not terminate
    on its own. The second half is the part that makes refusing correct rather
    than merely safe: the object is genuinely uncallable, and calling it raises
    RecursionError. Asserting only the refusal would leave the comment's
    justification untested and would still pass if the object were fine.
    """

    class Cycle:
        def __call__(self, *args):
            return 1

    instance = Cycle()
    Cycle.__call__ = functools.partial(instance)

    reason, cause = _suspendable_reason(instance)
    assert reason == ("reached through a chain of wrappers that did not end "
                      "within " + str(_WRAPPER_CHAIN_LIMIT) + " links"), reason
    assert cause is None
    # 3.13 warns that a partial in this slot will become a method descriptor,
    # a change 3.14 has already made. The transition alters how the receiver is
    # passed, not whether the loop closes, and the RecursionError below is
    # raised on 3.11 through 3.14 alike. Scoped to this call so the suite stays
    # quiet without a filter that could hide the same warning elsewhere.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        with pytest.raises(RecursionError):
            instance(1)


@pytest.mark.parametrize("wrapper", [staticmethod, classmethod])
def test_a_descriptor_holding_a_coroutine_is_read_through_func(wrapper):
    """The kind lives on __func__, and the predicates do not look there.

    `inspect.iscoroutinefunction(staticmethod(coro))` is False: it answers
    about the descriptor, not about what the descriptor holds. Reading the
    attribute off a CLASS hides that, because getattr runs __get__ and the
    gate is handed the underlying function, which is why a suite built on
    classes passes without the __func__ hop. The nested case is here because a
    descriptor over a descriptor has to keep hopping rather than give up after
    one, and the synchronous terminal is the control that stops this from
    passing with a blanket refusal of every descriptor.
    """
    assert _suspendable_reason(wrapper(_coroutine_terminal))[0] == \
        "a coroutine function"
    assert _suspendable_reason(wrapper(wrapper(_coroutine_terminal)))[0] == \
        "a coroutine function"
    assert _suspendable_reason(wrapper(_plain_terminal)) == (None, None)


def test_a_partial_over_a_descriptor_keeps_walking_to_the_kind():
    """The two edges in sequence, on the only pair that can be built.

    This is staticmethod alone rather than a parametrized pair because a
    classmethod object is not callable, so functools.partial refuses to hold
    one and raises TypeError at construction. The walk takes the partial edge
    first, lands on the descriptor, hops through __func__, and only then asks
    the predicates. That is the one-layer-per-turn discipline surviving a
    change of edge rather than only a repeat of the same edge.
    """
    assert _suspendable_reason(
        functools.partial(staticmethod(_coroutine_terminal))
        )[0] == "a coroutine function"
    assert _suspendable_reason(
        functools.partial(staticmethod(_plain_terminal))) == (None, None)


def test_a_module_level_descriptor_over_a_coroutine_refuses_the_install():
    """The reachable spelling of the bug, asserted through the public API.

    A module runs no descriptor protocol on attribute access, so
    `handler = staticmethod(coro)` at module scope hands the gate the
    descriptor itself. Before the __func__ hop this install was accepted and
    the wrapped attribute returned the entry action's value, an int, where
    every caller awaits a coroutine: injection changed the type contract of
    the program it was measuring. The refusal happens before the setattr, so
    the attribute is still the original object afterwards.
    """
    modname = "pyteman_atomic_victim_module_descriptor"
    mod = types.ModuleType(modname)
    mod.handler = staticmethod(_coroutine_terminal)
    before = mod.handler
    sys.modules[modname] = mod
    try:
        with pytest.raises(SuspendableTargetError) as excinfo:
            activate([make_rule("handler", "r-descriptor", module=modname)],
                     log=None, modules=[modname])
        assert "a coroutine function" in str(excinfo.value), str(excinfo.value)
        assert mod.handler is before
    finally:
        del sys.modules[modname]


def test_a_descriptor_cannot_choose_what_the_walk_follows():
    """The target does not get a vote, and the gate still reads nothing.

    A staticmethod subclass may define __func__ as a property. Read off the
    instance it decides for itself what the walk sees, and it can answer with
    a plain function while really holding an `async def`, which is the shape
    this check exists to refuse. Worse, reading it runs the property body, so
    a check whose contract is to read and never run would execute target code
    while deciding.

    _through_func reads __func__ off the defining class and applies it to the
    object, the same way the partial arc takes `func` off functools.partial
    itself rather than off the instance. RAN is the half that would still be
    empty if the property had simply not been consulted, so the assertion on
    the kind is what makes it load-bearing: both routes must reach the
    coroutine underneath.
    """
    ran = []

    class Sneaky(staticmethod):
        @property
        def __func__(self):
            ran.append("the property body ran inside the gate")
            return _plain_terminal

    assert _suspendable_reason(Sneaky(_coroutine_terminal))[0] == \
        "a coroutine function"

    class HeldInASlot:
        __call__ = Sneaky(_coroutine_terminal)

    assert _suspendable_reason(HeldInASlot())[0] == "a coroutine function"
    assert ran == [], ran

    # The same guarantee one layer down, where the deeper walk is what does
    # the reading. The verdict is the discriminating half: the property hands
    # back a synchronous function, so a gate that consulted it would answer
    # None here, and an empty `ran` on its own cannot tell "not consulted"
    # apart from "not reachable".
    class NestedInASlot:
        __call__ = staticmethod(Sneaky(_coroutine_terminal))

    assert _suspendable_reason(NestedInASlot())[0] == "a coroutine function"
    assert ran == [], ran
    assert NestedInASlot.__call__.__func__ is _plain_terminal
    assert ran == ["the property body ran inside the gate"]


@pytest.mark.parametrize("kind", [staticmethod, classmethod])
def test_a_descriptor_override_decides_over_what_it_stores(kind):
    """A descriptor subclass that overrides __call__ is judged by the override.

    The storage arc is the fallback, not the first read, on exactly the terms
    the partial edge uses. Both directions are asserted against what calling
    the object really does, because reading __func__ first is wrong in both
    and a suite that only covered plain descriptors stayed green on both.

    Fail-open: an `async def __call__` over a stored synchronous function
    really returns a coroutine, so instrumenting it with synchronous entry
    semantics returns a value where the caller awaits. Fail-closed: the mirror
    shape really returns a value and a refusal would block a legal install.
    """

    class AsyncOverride(kind):
        async def __call__(self, *args):
            return 1

    class SyncOverride(kind):
        def __call__(self, *args):
            return 1

    holds_sync = AsyncOverride(_plain_terminal)
    holds_coroutine = SyncOverride(_coroutine_terminal)

    # What the objects really do, established before asking the gate, so the
    # expectations below are anchored to behaviour rather than to the walk.
    called = holds_sync(1)
    assert inspect.iscoroutine(called)
    called.close()
    assert holds_coroutine(1) == 1

    assert _suspendable_reason(holds_sync)[0] == "a coroutine function"
    assert _suspendable_reason(holds_coroutine) == (None, None)


MODNAME10 = "pyteman_atomic_victim_history"
MODNAME11 = "pyteman_atomic_victim_history_alias"


class RefusesOneName(types.ModuleType):
    """Refuses one attribute, on write only, so the failure lands in pass 2.

    It raises a caller-supplied INSTANCE rather than building one, so the test
    can assert the object that arrives is the object this container threw. A
    comparison on the message would pass just as well against a fresh
    exception raised somewhere on the rollback path, which is the substitution
    the fail-closed handler exists to prevent.
    """

    refuse = None
    refusal = None

    def __setattr__(self, name, value):
        if name == type(self).refuse:
            raise type(self).refusal
        super().__setattr__(name, value)


class ReentersThenFires:
    """Slot `b`'s callable, whose signature read re-enters and then calls.

    The hook does two things in the window, in order: it runs a nested patch
    that succeeds and publishes, and it then CALLS the attribute that patch
    instrumented. So by the time the outer call fails, the nested rule has
    genuinely reached its action through the ordinary dispatcher.
    """

    def __init__(self):
        self.hook = None
        self.fired = False

    def __call__(self, x):
        return x

    @property
    def __signature__(self):
        if self.hook is not None and not self.fired:
            self.fired = True
            self.hook()
        raise TypeError("unintrospectable")


def _records(path):
    """(rule id, phase, status) for every record the real firing log wrote.

    `status` is carried here because a terminal record alone does not say the
    action succeeded: `run_action` writes one for a failure too. The status is
    what tells a completed action from a recorded attempt at one.
    """
    with open(path) as handle:
        return [(rec["rule"], rec["phase"], rec.get("status"))
                for rec in (json.loads(line) for line in handle if line.strip())]


def test_a_nested_call_that_published_keeps_its_history_when_the_outer_fails(
        tmp_path):
    """`applied` records publications, so a later failure elsewhere cannot edit it.

    This is the contract, not a defect awaiting a fix. `applied` names what a
    SUCCESSFUL _patch call installed. The nested call here succeeds, and its
    rule reaches its action before the outer call fails, so its entry is
    accurate history of an activation that really happened. Retracting it
    when the outer call rolls back would leave the firing log showing a rule
    that ran and `applied` denying it was ever installed, which is the
    divergence between what runs and what is recorded that the rollback path
    exists to prevent, pointing the wrong way.

    The outer call's own entries are a different matter and are withheld, as
    `_patch`'s failure path says: a rolled-back call must not read as one that
    ran. That invariant is scoped to the call that rolled back.

    Nothing here asserts what the slot will serve afterwards. `applied` is not
    a description of the current binding and not a prediction that a rule will
    fire again; the restored slot below is checked as the outer call's undo,
    not as a statement about the nested rule's future.
    """
    path = str(tmp_path / "firing.jsonl")
    log = FiringLog(path)

    def a(n):
        return n

    mod = RefusesOneName(MODNAME10)
    # The exact object the container will throw, so the assertion at the end
    # is an identity check rather than a comparison a lookalike would pass.
    refusal = TypeError("this module refuses to set 'b'")
    RefusesOneName.refuse = "b"
    RefusesOneName.refusal = refusal
    # setattr on the type, since the module itself is the thing refusing.
    types.ModuleType.__setattr__(mod, "a", a)
    types.ModuleType.__setattr__(mod, "b", ReentersThenFires())
    sys.modules[MODNAME10] = mod
    # The same module object under a second name, so the nested call joins the
    # dispatcher the outer call has already installed on `a` rather than
    # building its own.
    sys.modules[MODNAME11] = mod

    rules = [
        # Pass 2 takes `a` first and installs a dispatcher there.
        Rule(id="outer-a", module=MODNAME10, symbol="a", event="entry",
             action={"kind": "sleep", "ms": 0}, fire={"mode": "always"},
             when=None),
        # Then `b`: the pragma needs a parameter, reading the signature is how
        # it finds one, and that read is the re-entry vector. The refused
        # setattr on `b` is what fails the outer call afterwards.
        Rule(id="outer-b", module=MODNAME10, symbol="b", event="entry",
             action={"kind": "pragma", "name": "foreign_keys", "value": "ON",
                     "target": "param:x"},
             fire={"mode": "always"}, when=None),
        # The nested call's rule, joining `a` through the alias.
        Rule(id="nested-a", module=MODNAME11, symbol="a", event="entry",
             action={"kind": "sleep", "ms": 0}, fire={"mode": "always"},
             when=None),
    ]
    p = Patcher(rules, log)

    def reenter():
        p._patch(mod, MODNAME11)
        # Inside the window, through the ordinary attribute: this is the call
        # that puts the nested rule in the log before the outer call fails.
        types.ModuleType.__getattribute__(mod, "a")(1)

    types.ModuleType.__getattribute__(mod, "b").hook = reenter

    raised = None
    try:
        with pytest.raises(TypeError) as excinfo:
            p._patch(mod, MODNAME10)
        raised = excinfo.value
    finally:
        RefusesOneName.refuse = None
        RefusesOneName.refusal = None
        log.close()
        del sys.modules[MODNAME10]
        del sys.modules[MODNAME11]

    # The container's own refusal arrives, by identity, rather than something
    # raised in its place while rolling back.
    assert raised is refusal

    # The nested rule reached its action, and the log says so from both ends.
    # The start record proves an attempt only; "slept" on the terminal record
    # is the sleep action reporting that it ran to completion.
    assert _records(path) == [("outer-a", "start", None),
                              ("outer-a", "end", "slept"),
                              ("nested-a", "start", None),
                              ("nested-a", "end", "slept")]

    # The history stands: the call that succeeded is named, the call that
    # rolled back is not.
    assert p.applied == [f"{MODNAME11}:a"]

    # And the outer call's undo really ran, which is what makes the entry
    # above a claim about the past rather than about this slot.
    assert types.ModuleType.__getattribute__(mod, "a") is a
