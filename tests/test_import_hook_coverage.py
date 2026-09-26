# tests/test_import_hook_coverage.py
"""Import hook coverage matrix (TASK-4, AC#1, AC#2, AC#3).

Tests which forms of import trigger the hook and result in patching, and
which do not. The matrix is: normal import, from-import, dotted, direct
__import__ call, importlib.import_module, preloaded module, and
importlib.reload. Relative imports are not testable from a flat test file
without a real package install, so they are noted as a documented limit
rather than driven here.

Also tests per-rule state tracking (AC#2): the `rule_states` property
reports whether each rule is pending, applied, skipped, or refused.

Each row has one expected outcome:
    applied     the hook fired and the callable was replaced
    not_applied the import completed but the hook never saw the module
    removed     the import undid an existing patch (reload)
"""
import builtins
import importlib
import sys

import pytest

from pyteman.patcher import install, activate
from pyteman.rules import Rule

MODNAME = "hook_coverage_target"
PKG_MODNAME = "hook_coverage_pkg.leaf"


def _rule(module, symbol="greet", rid="r1"):
    return Rule(
        id=rid, module=module, symbol=symbol, event="entry",
        action={"kind": "return_value", "value": "patched"},
        fire={"mode": "always"},
    )


def _is_patched(mod, attr="greet"):
    fn = getattr(mod, attr)
    return hasattr(fn, "_pyteman_state")


@pytest.fixture(autouse=True)
def _clean_modules():
    """Remove test modules from sys.modules before and after each test.

    The import hook and the uninstall both rely on sys.modules state, so
    every test starts from a clean slate.
    """
    to_clean = [MODNAME, PKG_MODNAME, "hook_coverage_pkg"]
    for name in to_clean:
        sys.modules.pop(name, None)
    yield
    for name in to_clean:
        sys.modules.pop(name, None)


# --- import forms that go through builtins.__import__ ---------------------

class TestNormalImport:
    def test_normal_import_triggers_hook(self):
        """A bare `import mod` statement goes through __import__."""
        p = install([_rule(MODNAME)], log=None)
        try:
            mod = builtins.__import__(MODNAME)
            assert _is_patched(mod), (
                "normal import did not trigger the hook; the callable was "
                "not replaced"
            )
        finally:
            p.uninstall()


class TestFromImport:
    def test_from_import_triggers_hook(self):
        """`from mod import name` goes through __import__ for the module."""
        p = install([_rule(MODNAME)], log=None)
        try:
            mod = builtins.__import__(MODNAME, fromlist=["greet"])
            assert _is_patched(mod), (
                "from-import did not trigger the hook"
            )
        finally:
            p.uninstall()


class TestDottedImport:
    def test_dotted_import_triggers_hook(self):
        """`import pkg.sub` goes through __import__ with the dotted name."""
        p = install([_rule(PKG_MODNAME, symbol="compute")], log=None)
        try:
            builtins.__import__(PKG_MODNAME)
            mod = sys.modules[PKG_MODNAME]
            assert _is_patched(mod, "compute"), (
                "dotted import did not trigger the hook"
            )
        finally:
            p.uninstall()


class TestDirectImportCall:
    def test_builtins_import_triggers_hook(self):
        """Calling builtins.__import__ directly goes through the hook."""
        p = install([_rule(MODNAME)], log=None)
        try:
            mod = builtins.__import__(MODNAME)
            assert _is_patched(mod), (
                "builtins.__import__ did not trigger the hook"
            )
        finally:
            p.uninstall()


# --- import forms that bypass builtins.__import__ -------------------------

class TestImportlibImportModule:
    def test_importlib_import_module_bypasses_hook(self):
        """importlib.import_module does not go through builtins.__import__.

        This is a documented limit of the __import__-based hook. The module
        is loaded into sys.modules but the hook never fires for it, so the
        rule is never applied.
        """
        p = install([_rule(MODNAME)], log=None)
        try:
            mod = importlib.import_module(MODNAME)
            assert not _is_patched(mod), (
                "importlib.import_module unexpectedly triggered the hook; "
                "if CPython changed this behavior, the documented limit "
                "may need updating"
            )
        finally:
            p.uninstall()


class TestImportlibReload:
    def test_reload_removes_existing_patch(self):
        """importlib.reload replaces module attributes, undoing patches.

        After a module is patched via the hook, reload() re-executes the
        module body and reassigns all its attributes, so the patched
        callable is replaced with the original definition. The hook does
        not re-fire for reload.
        """
        p = install([_rule(MODNAME)], log=None)
        try:
            mod = builtins.__import__(MODNAME)
            assert _is_patched(mod), "setup: import should have patched"
            importlib.reload(mod)
            assert not _is_patched(mod), (
                "reload did not remove the patch; if the hook now fires "
                "for reload, the documented limit may need updating"
            )
        finally:
            p.uninstall()


# --- preloaded modules ----------------------------------------------------

class TestPreloaded:
    def test_install_does_not_patch_preloaded(self):
        """install() hooks __import__ but does not sweep sys.modules.

        A module already loaded before install() is called will not be
        patched until force_patch_module is explicitly called.
        """
        builtins.__import__(MODNAME)
        mod = sys.modules[MODNAME]
        p = install([_rule(MODNAME)], log=None)
        try:
            assert not _is_patched(mod), (
                "install() patched a preloaded module; it should only "
                "set up the hook for future imports"
            )
        finally:
            p.uninstall()

    def test_force_patch_module_patches_preloaded(self):
        """force_patch_module explicitly patches a module already loaded."""
        builtins.__import__(MODNAME)
        mod = sys.modules[MODNAME]
        p = install([_rule(MODNAME)], log=None)
        try:
            p.force_patch_module(MODNAME)
            assert _is_patched(mod), (
                "force_patch_module did not patch the preloaded module"
            )
        finally:
            p.uninstall()

    def test_activate_with_modules_patches_preloaded(self):
        """activate(modules=[...]) patches named modules as part of startup."""
        builtins.__import__(MODNAME)
        mod = sys.modules[MODNAME]
        p = activate([_rule(MODNAME)], log=None, modules=[MODNAME])
        try:
            assert _is_patched(mod), (
                "activate(modules=[MODNAME]) did not patch the preloaded "
                "module"
            )
        finally:
            p.uninstall()


# --- not-yet-imported modules (AC#3) --------------------------------------

class TestNotYetImported:
    def test_rule_for_absent_module_does_not_fail(self):
        """A rule naming a module not in sys.modules is not an error.

        The module will be patched later when it is imported, through the
        hook. This is the primary use case: sitecustomize installs the hook
        before the workload imports its own modules.
        """
        p = install([_rule("not_yet_loaded_module_xyz")], log=None)
        try:
            assert p.applied == []
        finally:
            p.uninstall()

    def test_pending_rule_fires_on_later_import(self):
        """A rule pending at install time fires when the module arrives."""
        p = install([_rule(MODNAME)], log=None)
        try:
            assert p.applied == []
            mod = builtins.__import__(MODNAME)
            assert _is_patched(mod), (
                "the hook did not patch the module when it was imported "
                "after install()"
            )
            assert len(p.applied) > 0
        finally:
            p.uninstall()


# --- summary of the import form matrix ------------------------------------
#
# form                        triggers hook    rule applied
# ─────────────────────────── ──────────────── ────────────
# import mod                  yes              yes
# from mod import name        yes              yes
# import pkg.mod              yes              yes
# builtins.__import__(mod)    yes              yes
# importlib.import_module     NO               NO (limit)
# importlib.reload            NO               removes existing patch
# preloaded (before install)  n/a              NO (need force_patch_module)
# relative import             yes (statement)  yes (same mechanism)
#
# Relative imports use the same `import` statement path and go through
# __import__, so they trigger the hook. They are not tested here because
# exercising them requires the test itself to be inside a package with a
# real __init__.py, which complicates test layout for no new coverage.


# --- per-rule state tracking (AC#2) ---------------------------------------

class TestRuleStates:
    def test_pending_before_import(self):
        """A rule starts as pending when its module is not yet imported."""
        p = install([_rule(MODNAME)], log=None)
        try:
            assert p.rule_states == {"r1": "pending"}
        finally:
            p.uninstall()

    def test_applied_after_import(self):
        """The state moves to applied once the hook patches the callable."""
        p = install([_rule(MODNAME)], log=None)
        try:
            builtins.__import__(MODNAME)
            assert p.rule_states == {"r1": "applied"}
        finally:
            p.uninstall()

    def test_applied_via_force_patch(self):
        """force_patch_module also transitions the state to applied."""
        builtins.__import__(MODNAME)
        p = install([_rule(MODNAME)], log=None)
        try:
            assert p.rule_states == {"r1": "pending"}
            p.force_patch_module(MODNAME)
            assert p.rule_states == {"r1": "applied"}
        finally:
            p.uninstall()

    def test_skipped_when_symbol_absent(self):
        """A rule targeting a nonexistent symbol is skipped, not failed."""
        p = install([_rule(MODNAME, symbol="no_such_function")], log=None)
        try:
            builtins.__import__(MODNAME)
            assert p.rule_states == {"r1": "skipped"}
        finally:
            p.uninstall()

    def test_multiple_rules_independent_states(self):
        """Each rule tracks its own state independently."""
        rules = [
            _rule(MODNAME, symbol="greet", rid="r1"),
            _rule(MODNAME, symbol="no_such_function", rid="r2"),
            _rule("not_loaded_module_xyz", symbol="fn", rid="r3"),
        ]
        p = install(rules, log=None)
        try:
            builtins.__import__(MODNAME)
            states = p.rule_states
            assert states["r1"] == "applied"
            assert states["r2"] == "skipped"
            assert states["r3"] == "pending"
        finally:
            p.uninstall()

    def test_state_stays_pending_for_importlib_import_module(self):
        """importlib.import_module bypasses the hook, so state stays pending.

        This is the diagnostic signal AC#2 requires: the operator can
        check rule_states and see that a module was loaded but the rule
        was never applied, which signals an unsupported import form.
        """
        p = install([_rule(MODNAME)], log=None)
        try:
            importlib.import_module(MODNAME)
            assert p.rule_states == {"r1": "pending"}, (
                "importlib.import_module should not transition the state; "
                "the rule stays pending because the hook never fired"
            )
        finally:
            p.uninstall()
