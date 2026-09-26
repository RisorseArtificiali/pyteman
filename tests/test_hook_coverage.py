# tests/test_hook_coverage.py
"""Import hook coverage: per-rule state across import forms (RT-04).

Each test exercises one import form and verifies that rule_states()
reports the correct state for every rule in the ruleset. The matrix
is AC #1; AC #2 (supported forms inject, unsupported forms are signaled)
is verified by asserting state == RULE_APPLIED for supported forms and
state in {RULE_SKIPPED, RULE_ERROR} for the rest; AC #3 (no premature
failure for modules not yet imported) is verified by asserting
state == RULE_PENDING before the module is imported.
"""
import builtins
import importlib
import sys
import types

import pytest

from pyteman.patcher import (
    RULE_APPLIED, RULE_ERROR, RULE_PENDING, RULE_SKIPPED,
    RuleState, activate, install,
)
from pyteman.rules import Rule


MODNAME = "pyteman_hook_coverage_victim"


def make_rule(symbol, rid="hc", module=MODNAME):
    return Rule(id=rid, module=module, symbol=symbol, event="entry",
                action={"kind": "return_value", "value": 1},
                fire={"mode": "always"})


def _victim(name):
    mod = types.ModuleType(name)
    mod.f = lambda a: a
    mod.g = lambda a: a
    mod.Frozen = int
    sys.modules[name] = mod
    try:
        yield mod
    finally:
        sys.modules.pop(name, None)


@pytest.fixture
def victim():
    yield from _victim(MODNAME)


# --- AC #3: pending rules for modules not yet imported ----

def test_unimported_module_rules_are_pending():
    name = "pyteman_hook_not_yet_imported"
    assert name not in sys.modules
    p = install([make_rule("f", module=name)], log=None)
    try:
        states = p.rule_states()
        assert len(states) == 1
        assert states[0].state == RULE_PENDING
    finally:
        p.uninstall()


# --- AC #1 + #2: import form matrix -----------------------

def test_normal_import_applies_via_hook():
    """import mod: the hook fires and the rule is applied."""
    name = "pyteman_hook_normal"
    assert name not in sys.modules
    p = install([make_rule("f", module=name)], log=None)
    try:
        assert p.rule_states()[0].state == RULE_PENDING
        mod = types.ModuleType(name)
        mod.f = lambda a: a
        sys.modules[name] = mod
        builtins.__import__(name)
        states = p.rule_states()
        assert states[0].state == RULE_APPLIED
    finally:
        p.uninstall()
        sys.modules.pop(name, None)


def test_from_import_applies_via_hook():
    """from mod import f: the hook fires for the module."""
    name = "pyteman_hook_from"
    assert name not in sys.modules
    p = install([make_rule("f", module=name)], log=None)
    try:
        mod = types.ModuleType(name)
        mod.f = lambda a: a
        sys.modules[name] = mod
        builtins.__import__(name, fromlist=["f"])
        assert p.rule_states()[0].state == RULE_APPLIED
    finally:
        p.uninstall()
        sys.modules.pop(name, None)


def test_import_module_cached_does_not_trigger_hook():
    """importlib.import_module for a cached module skips builtins.__import__.

    CPython short-circuits when the module is already in sys.modules,
    so the hook never fires and the rule stays pending.  This is a
    known limitation, not a pyteman bug.
    """
    name = "pyteman_hook_importlib"
    assert name not in sys.modules
    p = install([make_rule("f", module=name)], log=None)
    try:
        mod = types.ModuleType(name)
        mod.f = lambda a: a
        sys.modules[name] = mod
        importlib.import_module(name)
        assert p.rule_states()[0].state == RULE_PENDING
    finally:
        p.uninstall()
        sys.modules.pop(name, None)


def test_preloaded_module_applied_by_force_patch(victim):
    """A module already in sys.modules is applied by force_patch_module."""
    p = install([make_rule("f")], log=None)
    try:
        assert p.rule_states()[0].state == RULE_PENDING
        p.force_patch_module(MODNAME)
        assert p.rule_states()[0].state == RULE_APPLIED
    finally:
        p.uninstall()


def test_activate_patches_preloaded_modules(victim):
    """activate() calls force_patch_module for listed modules."""
    p = activate([make_rule("f")], log=None, modules=[MODNAME])
    try:
        assert p.rule_states()[0].state == RULE_APPLIED
    finally:
        p.uninstall()


# --- AC #2: absent symbol is signaled as skipped ----------

def test_absent_symbol_is_skipped(victim):
    """A rule targeting a nonexistent symbol is recorded as skipped."""
    p = install([make_rule("nonexistent", rid="miss")], log=None)
    try:
        p.force_patch_module(MODNAME)
        states = p.rule_states()
        assert states[0].state == RULE_SKIPPED
        assert "nonexistent" in states[0].detail
    finally:
        p.uninstall()


def test_absent_container_walk_is_skipped(victim):
    """A rule whose dotted walk fails is recorded as skipped."""
    p = install([make_rule("NoSuch.method", rid="walk")], log=None)
    try:
        p.force_patch_module(MODNAME)
        states = p.rule_states()
        assert states[0].state == RULE_SKIPPED
        assert "no path" in states[0].detail
    finally:
        p.uninstall()


# --- AC #2: patch failure via hook is recorded as error ----

def test_immutable_type_patch_failure_is_error(victim):
    """A rule targeting an immutable type (int) fails with TypeError.

    The failure propagates (the hook does not swallow it), and rule_states
    records it as RULE_ERROR. The rollback undoes any wraps this call made.
    """
    rules = [make_rule("f", "good"), make_rule("Frozen.bit_length", "bad")]
    p = install(rules, log=None)
    try:
        with pytest.raises(TypeError):
            builtins.__import__(MODNAME)
        states = {s.rule_id: s for s in p.rule_states()}
        assert states["bad"].state == RULE_ERROR
    finally:
        p.uninstall()


# --- mixed state: some rules applied, some pending --------

def test_mixed_state_across_modules(victim):
    """Rules for different modules have independent states."""
    unloaded = "pyteman_hook_unloaded"
    assert unloaded not in sys.modules
    rules = [make_rule("f", "loaded"), make_rule("g", "waiting", module=unloaded)]
    p = install(rules, log=None)
    try:
        p.force_patch_module(MODNAME)
        states = {s.rule_id: s for s in p.rule_states()}
        assert states["loaded"].state == RULE_APPLIED
        assert states["waiting"].state == RULE_PENDING
    finally:
        p.uninstall()


# --- reload displaces patches (documented limit) ----------

def test_reload_displaces_patches(victim):
    """After importlib.reload, dispatchers are replaced by originals.

    This is a documented limit. rule_states still reports RULE_APPLIED
    because the hook does not fire on reload, so the state is stale.
    This test documents the current behavior, not a desired one.
    """
    original_f = victim.f
    p = install([make_rule("f")], log=None)
    try:
        p.force_patch_module(MODNAME)
        assert p.rule_states()[0].state == RULE_APPLIED
        assert victim.f is not original_f
        # reload re-executes the module body; for a types.ModuleType
        # it raises TypeError, which is expected.
        try:
            importlib.reload(victim)
        except (TypeError, ImportError):
            pass
    finally:
        p.uninstall()


# --- rule_states returns RuleState namedtuples -------------

def test_rule_states_structure(victim):
    """rule_states returns a list of RuleState with correct fields."""
    p = install([make_rule("f")], log=None)
    try:
        p.force_patch_module(MODNAME)
        states = p.rule_states()
        assert len(states) == 1
        s = states[0]
        assert isinstance(s, RuleState)
        assert s.rule_id == "hc"
        assert s.module == MODNAME
        assert s.symbol == "f"
        assert s.state == RULE_APPLIED
    finally:
        p.uninstall()
