# tests/test_parse_cost.py
"""parse_target_spec runs only for pragma rules (TASK-71/RT-18).

The parse used to be unconditional in the wrapper builder: every rule
paid a str() and a full grammar parse whose result was discarded unless
the kind was pragma. The parse now lives in _needs_signature behind the
kind check, and this test pins that shape by counting calls through the
whole install path: a non-pragma rule parses nothing, a param-target
pragma parses exactly once. A future edit that moves the parse back in
front of the kind check fails the first count; one that parses twice
fails the second.
"""
import sys
import types
import uuid

import pytest

import pyteman.patcher as patcher
import pyteman.targets as targets
from pyteman.rules import Rule


@pytest.fixture
def victim():
    name = f"victim_{uuid.uuid4().hex[:8]}"
    mod = types.ModuleType(name)

    def plain(a, b=2):
        return a + b

    mod.plain = plain
    sys.modules[name] = mod
    yield mod, name
    del sys.modules[name]


def _counting(monkeypatch):
    calls = []
    real = targets.parse_target_spec

    def spy(spec):
        calls.append(spec)
        return real(spec)

    monkeypatch.setattr(patcher, "parse_target_spec", spy)
    return calls


def test_a_non_pragma_rule_parses_nothing_at_install(victim, monkeypatch):
    mod, name = victim
    calls = _counting(monkeypatch)
    rule = Rule(id="plain", module=name, symbol="plain", event="entry",
                action={"kind": "return_value", "value": 9},
                fire={"mode": "always"})
    p = patcher.Patcher([rule], None)
    p.force_patch_module(name)
    assert mod.plain is not rule  # the dispatcher is installed
    assert calls == [], calls
    assert p.uninstall() == []


def test_a_param_pragma_rule_parses_exactly_once(victim, monkeypatch):
    mod, name = victim
    calls = _counting(monkeypatch)
    rule = Rule(id="pr", module=name, symbol="plain", event="entry",
                action={"kind": "pragma", "name": "synchronous",
                        "value": "OFF", "target": "param:a"},
                fire={"mode": "always"})
    p = patcher.Patcher([rule], None)
    p.force_patch_module(name)
    # Once at planning (_needs_signature); the signature it asks for is
    # cached on the composite, so no second parse follows.
    assert calls == ["param:a"], calls
    assert p.uninstall() == []



def test_the_action_dump_is_rendered_once_per_rule(victim):
    """TASK-110's second half: run_action used to rebuild str(rule.action)
    on every firing. The render now happens once at bind time and rides in
    the per-rule state, and the dispatchers hand it to run_action, so the
    record's note stays the rendering taken at bind. The discriminator is
    mutation: editing rule.action after install cannot change what later
    firings annotate, where the per-firing render followed the edit.
    """
    mod, name = victim
    rule = Rule(id="sleeper", module=name, symbol="plain", event="entry",
                action={"kind": "sleep", "ms": 0},
                fire={"mode": "always"})
    p = patcher.Patcher([rule], None)
    p.force_patch_module(name)
    state = mod.plain._pyteman_composite.entries[0].state
    original = state["action_repr"]
    assert original == str({"kind": "sleep", "ms": 0})

    captured = []

    class Log:
        def record(self, rule, ctx, note=None, phase="start", **_):
            if phase == "start":
                captured.append(note)
            class Ident:
                attempt = 1

            return Ident()

    import pyteman.actions as actions

    # Through the DISPATCHER, which is the seam the diff changed: the
    # note on every firing is the bind-time render, unchanged by the
    # post-install edit below.
    class ListLog:
        def __init__(self):
            self.notes = []

        def record(self, rule, ctx, note=None, phase="start", **_):
            if phase == "start":
                self.notes.append(note)

            class Ident:
                attempt = 1

            return Ident()

    assert p.uninstall() == []  # free the slot for the second Patcher
    log = ListLog()
    rule2 = Rule(id="sleeper", module=name, symbol="plain", event="entry",
                 action={"kind": "sleep", "ms": 0},
                 fire={"mode": "always"})
    p2 = patcher.Patcher([rule2], log)
    p2.force_patch_module(name)
    rule2.action = {"kind": "sleep", "ms": 999}  # the edit
    mod.plain(1)
    mod.plain(2)
    assert log.notes == [str({"kind": "sleep", "ms": 0})] * 2, log.notes
    assert p2.uninstall() == []
    # The first Patcher's slot was freed above; nothing leaked by the
    # second install either.

    # Direct call fallback still renders for a caller with no binding
    # behind it: rule2's action was edited above, so the fallback renders
    # the edited mapping.
    actions.run_action(rule2, {}, log=Log(), action_repr=None)
    assert captured[-1] == str({"kind": "sleep", "ms": 999})


def test_the_gate_reads_its_inputs_from_the_state_not_the_rule(victim):
    """TASK-110's declared semantic delta, pinned: mode and n ride in the
    per-rule state from bind time, so editing rule.fire after install has
    no effect on firing. Under the old per-visit read the edit worked,
    by accident nobody had pinned; now the accident is a contract."""
    mod, name = victim
    rule = Rule(id="once", module=name, symbol="plain", event="entry",
                action={"kind": "return_value", "value": "FIRED"},
                fire={"mode": "countdown", "n": 2})
    p = patcher.Patcher([rule], None)
    p.force_patch_module(name)
    rule.fire = {"mode": "always"}  # the edit that used to work
    results = [mod.plain(1) for _ in range(4)]
    # Countdown n=2 from bind time gates: only the third call fires, and
    # the post-install edit to always changes nothing. Under the old
    # per-visit read every call after the edit returned FIRED.
    assert results == [3, 3, "FIRED", 3], results
    state = mod.plain._pyteman_composite.entries[0].state
    assert state["mode"] == "countdown" and state["n"] == 2
    assert p.uninstall() == []


def test_an_unconvertible_n_fails_at_bind_not_at_first_firing(victim):
    """The second declared delta, also an improvement: a countdown n that
    cannot convert to int used to explode inside the first firing, inside
    the workload; it now fails at patch time, in the fail-closed phase."""
    from pyteman.patcher import RuleError
    mod, name = victim
    rule = Rule(id="badn", module=name, symbol="plain", event="entry",
                action={"kind": "sleep", "ms": 0},
                fire={"mode": "countdown", "n": "two"})
    with pytest.raises((RuleError, ValueError, TypeError)) as excinfo:
        patcher.Patcher([rule], None).force_patch_module(name)
    assert "int" in str(excinfo.value) or "invalid literal" in str(
        excinfo.value), excinfo.value
