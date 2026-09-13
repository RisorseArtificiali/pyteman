from pyteman.rules import Rule
from pyteman.patcher import install

def make_rule(point, action=None, when=None):
    return Rule(id="t", module="target_mod", symbol=point, event="entry",
                action=action or {"kind": "return_value", "value": 99},
                when=when, fire={"mode": "always"})

def test_patching_plain_function():
    import target_mod
    p = install([make_rule("plain")], log=None)
    try:
        p.force_patch_module("target_mod")
        assert target_mod.plain(1) == 99
        assert "target_mod:plain" in p.applied
    finally:
        p.uninstall()
    assert target_mod.plain(1, 2) == 3

def test_patching_class_method():
    import target_mod
    p = install([make_rule("Calc.add")], log=None)
    try:
        p.force_patch_module("target_mod")
        assert target_mod.Calc().add(1) == 99
        assert "target_mod:Calc.add" in p.applied
    finally:
        p.uninstall()
    assert target_mod.Calc().add(1) == 2

def test_condition_gates_firing():
    import target_mod
    p = install([make_rule("plain", when="args[0] == 7")], log=None)
    try:
        p.force_patch_module("target_mod")
        assert target_mod.plain(1) == 1
        assert target_mod.plain(7) == 99
    finally:
        p.uninstall()

def test_exit_event_can_override():
    import target_mod
    from pyteman.rules import Rule as R
    r = R(id="ex", module="target_mod", symbol="plain", event="exit",
          action={"kind": "return_value", "value": -1})
    p = install([r], log=None)
    try:
        p.force_patch_module("target_mod")
        assert target_mod.plain(5) == -1
    finally:
        p.uninstall()
