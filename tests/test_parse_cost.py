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
