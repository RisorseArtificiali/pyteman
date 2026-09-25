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

def test_once_per_key_not_consumed_when_condition_fails():
    import target_mod
    from pyteman.rules import Rule as R
    # key on args[0], gate on kwargs so the when can be false first and true
    # later for the SAME key value (a when keyed on args[0] like "args[0] != 1"
    # is degenerate: it excludes that key value forever).
    r = R(id="op", module="target_mod", symbol="plain", event="entry",
          action={"kind": "return_value", "value": 99},
          when="kwargs.get('b', 0) == 1", fire={"mode": "once_per", "key": "args[0]"})
    p = install([r], log=None)
    try:
        p.force_patch_module("target_mod")
        assert target_mod.plain(5) == 5        # when false: no fire, key not consumed
        assert target_mod.plain(5, b=1) == 99  # when true: fires, key consumed
        assert target_mod.plain(5) == 5        # when false again: natural
        assert target_mod.plain(5, b=1) == 6   # key consumed by the fire: no re-fire (natural 5+1)
        assert target_mod.plain(6, b=1) == 99  # different key fires independently
    finally:
        p.uninstall()

def test_entry_override_skips_body():
    import target_mod
    p = install([make_rule("record_len")], log=None)
    try:
        p.force_patch_module("target_mod")
        assert target_mod.record_len() == 99
        assert target_mod.calls == []      # body never ran
    finally:
        p.uninstall()
    assert target_mod.record_len() == 1    # restored, body runs again


def test_uninstall_clears_applied():
    """applied is empty after uninstall, not a cumulative history."""
    import target_mod  # noqa: F401 -- ensures module is in sys.modules
    p = install([make_rule("plain")], log=None)
    p.force_patch_module("target_mod")
    assert "target_mod:plain" in p.applied
    p.uninstall()
    assert p.applied == []
