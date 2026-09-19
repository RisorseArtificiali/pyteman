# tests/test_unknown_event.py
"""An event the dispatcher cannot serve is refused where nothing is patched yet.

The YAML loader has always checked `event` against the closed set. The
programmatic door had no such check, and the split that consumes the field is
two independent comprehensions, one for "entry" and one for "exit", which
cannot notice what neither of them selects. A rule with any other event was
therefore installed in full: the callable replaced, the slot listed in
`applied`, and the rule unable to fire for the life of the process, with no
error and no note.

These cover the refusal and, as controls, that the two real events still reach
the callable through the same door.
"""
import builtins
import sys
import types

import pytest

from pyteman.patcher import Patcher
from pyteman.rules import Rule, RuleError

MODNAME = "pyteman_unknown_event_victim"


def make_rule(event, rid="r", symbol="ok"):
    return Rule(id=rid, module=MODNAME, symbol=symbol, event=event,
                action={"kind": "return_value", "value": 1},
                fire={"mode": "always"})


@pytest.fixture
def victim():
    mod = types.ModuleType(MODNAME)
    setattr(mod, "ok", lambda: "real")
    setattr(mod, "also", lambda: "real")
    sys.modules[MODNAME] = mod
    try:
        yield mod
    finally:
        del sys.modules[MODNAME]


def test_an_event_outside_the_closed_set_is_refused_before_anything_is_patched(victim):
    """The defect entire, at the door it came through.

    Four spellings rather than one, because they are four different mistakes
    and only some of them look like mistakes on the page. "entires" is a typo,
    "ENTRY" is a case error that reads as correct to a human, "" is what a
    field left unset looks like once it has been through a template, and
    "around" is a plausible event from another library that this one does not
    serve.
    """
    original = victim.ok
    for bad in ("entires", "ENTRY", "", "around"):
        with pytest.raises(RuleError):
            Patcher([make_rule(bad)], None)
        # The point of refusing in __init__ rather than at patch time: there is
        # no Patcher to have patched anything, and the slot is untouched.
        assert victim.ok is original


def test_the_refusal_names_the_rule_and_the_value_it_found():
    """A ruleset has many rules and the operator has to be told which one.

    The value matters as much as the name. "ENTRY" and "entry" render
    identically in a sentence that omits the value, and that is the pair most
    likely to bring someone here.
    """
    with pytest.raises(RuleError) as caught:
        Patcher([make_rule("ENTRY", rid="the-offender")], None)

    rendered = str(caught.value) + "".join(getattr(caught.value, "__notes__", ()))
    assert "the-offender" in rendered
    assert "ENTRY" in rendered
    # The vocabulary the author has to choose from, not merely a complaint that
    # what they wrote was wrong.
    assert "entry" in rendered and "exit" in rendered


def test_an_event_that_is_not_a_string_cannot_talk_its_way_past_the_check():
    """Membership would ask the value whether it is "entry", and it would say yes.

    `x in ("entry", "exit")` is `any(x is e or x == e)`, so an object defining
    __eq__ decides its own classification. The type is checked first and
    exactly, so nothing here reaches a comparison at all.
    """
    calls = []

    class SaysYesToEverything:
        def __eq__(self, other):
            calls.append(other)
            return True

        def __hash__(self):
            return 0

    with pytest.raises(RuleError):
        Patcher([make_rule(SaysYesToEverything())], None)
    assert calls == []


def test_a_string_subclass_that_lies_about_equality_is_refused_too():
    """Exactly str, not "instances of str".

    A subclass is still a str to isinstance while deciding for itself what it
    equals, which is the same vote by a quieter route.
    """
    class Liar(str):
        def __eq__(self, other):
            return True

        def __hash__(self):
            return 0

    with pytest.raises(RuleError):
        Patcher([make_rule(Liar("nonsense"))], None)


def test_the_check_does_not_forgive_whitespace_or_case():
    """Normalising here would admit a ruleset the loader refuses.

    Two doors into one state disagreeing about what an event IS is the defect
    being fixed, so the fix cannot introduce a smaller version of it. A value
    the loader would reject is rejected here in the same spelling.
    """
    for bad in (" entry", "entry ", "Entry", "EXIT", "\tentry"):
        with pytest.raises(RuleError):
            Patcher([make_rule(bad)], None)


def test_an_event_that_cannot_be_read_is_refused_with_its_cause():
    """A getter that raises is a defect too, and a different one.

    Allowing it would mean guessing in the direction that patches.
    """
    class Exploding:
        @property
        def event(self):
            raise ValueError("no event here")

        id = "boom"
        module = MODNAME
        symbol = "ok"
        action = {"kind": "return_value", "value": 1}
        fire = {"mode": "always"}
        when = None

    with pytest.raises(RuleError) as caught:
        Patcher([Exploding()], None)
    rendered = str(caught.value) + "".join(getattr(caught.value, "__notes__", ()))
    assert "no event here" in rendered


def test_an_interrupt_while_reading_the_event_arrives_as_itself():
    """A Ctrl-C during construction is not a ruleset defect.

    Catching BaseException here would report the interrupt as an unreadable
    event, whose str() is empty, and the operator would be sent to look at a
    field that is fine.
    """
    sentinel = KeyboardInterrupt()

    class Interrupting:
        @property
        def event(self):
            raise sentinel

        id = "interrupted"
        module = MODNAME
        symbol = "ok"
        action = {"kind": "return_value", "value": 1}
        fire = {"mode": "always"}
        when = None

    with pytest.raises(KeyboardInterrupt) as caught:
        Patcher([Interrupting()], None)
    assert caught.value is sentinel


def test_a_later_rules_bad_event_leaves_the_earlier_rules_slot_alone(victim):
    """__init__ is the step that mutates nothing, and that is what is being used.

    The refusal is not "the bad rule is skipped": the whole ruleset is refused,
    so a good rule sitting in front of a bad one is not installed either.
    """
    ok_before, also_before = victim.ok, victim.also
    import_before = builtins.__import__

    with pytest.raises(RuleError):
        Patcher([make_rule("entry", rid="good", symbol="ok"),
                 make_rule("sideways", rid="bad", symbol="also")], None)

    assert victim.ok is ok_before
    assert victim.also is also_before
    # Nothing got as far as installing the hook either, which is the other
    # thing a half-built activation leaves behind.
    assert builtins.__import__ is import_before


def test_entry_and_exit_still_reach_the_callable_through_the_same_door():
    """The positive control, and it has to be a firing and not a construction.

    A refusal that refused everything would pass every test above. These two
    prove the vocabulary is admitted and, more than that, that a rule built by
    hand still fires: the AC is about rules that CAN fire being the only ones
    installed.
    """
    for event in ("entry", "exit"):
        mod = types.ModuleType(MODNAME)
        setattr(mod, "ok", lambda: "real")
        sys.modules[MODNAME] = mod
        try:
            p = Patcher([make_rule(event)], None)
            p._patch(mod, MODNAME)
            assert p.applied == [f"{MODNAME}:ok"]
            # The action replaces the return value on either event, so a rule
            # that was installed AND can fire is the only way to see 1 here.
            assert mod.ok() == 1
        finally:
            del sys.modules[MODNAME]
