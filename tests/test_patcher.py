from pyteman.rules import Rule
from pyteman.patcher import install

def make_rule(point, action=None, when=None, module="target_mod"):
    return Rule(id="t", module=module, symbol=point, event="entry",
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

def _closure_cells(fn):
    """Every live value the wrapper's closure holds, empty cells skipped."""
    out = []
    for cell in fn.__closure__ or ():
        try:
            out.append(cell.cell_contents)
        except ValueError:
            pass
    return out

def test_the_dispatcher_does_not_retain_the_patcher():
    """The closure reads the instance once, before the def, for the logger.

    The dispatcher needs exactly one thing from the Patcher, `self.log`,
    captured before the `def` so the closure binds the logger itself. The
    deliberate retention of the Patcher lives in the `_pyteman_owner` marker
    set after wraps, which is what _live_dispatcher_owner reads; the closure
    must add no second route to the instance. Pinned at the cell level, not
    by variable name: a future `_owner = self` above the def would pass a
    name check and retain the Patcher all the same.
    """
    import target_mod
    p = install([make_rule("plain")], log=None)
    try:
        p.force_patch_module("target_mod")
        assert target_mod.plain(5) == 99
        assert "self" not in target_mod.plain.__code__.co_freevars
        assert p not in _closure_cells(target_mod.plain)
    finally:
        p.uninstall()

def test_the_coroutine_dispatcher_does_not_retain_the_patcher(tmp_path,
                                                              monkeypatch):
    """The async wrapper obeys the same one-read constraint.

    The coroutine dispatcher captures `log = self.log` before its body like
    the sync one, and nothing else in the suite pins its closure. The test
    below would stay green through any regression that re-captures `self`
    inside the async def, because its own dispatcher is the sync one; hence
    a real async target, driven in-process.
    """
    import asyncio
    (tmp_path / "pasync_target.py").write_text(
        "async def afn(v):\n    return v + 1\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    import pasync_target
    p = install([make_rule("afn", module="pasync_target")], log=None)
    try:
        p.force_patch_module("pasync_target")
        assert asyncio.run(pasync_target.afn(1)) == 99
        assert "self" not in pasync_target.afn.__code__.co_freevars
        assert p not in _closure_cells(pasync_target.afn)
    finally:
        p.uninstall()
        import sys
        sys.modules.pop("pasync_target", None)

def test_the_captured_logger_still_receives_every_firing(tmp_path):
    """Capturing the logger instead of the instance must cost no records.

    The point of the capture is minimal retention. This is the other half
    of the same claim: the firing log still sees exactly one start and one
    end record for the single firing the call makes.
    """
    import json
    import target_mod
    from pyteman.firing import FiringLog

    log_path = tmp_path / "firing.jsonl"
    with FiringLog(str(log_path)) as log:
        p = install([make_rule("plain", action={"kind": "return_value",
                                                "value": 42})], log=log)
        try:
            p.force_patch_module("target_mod")
            assert target_mod.plain(5) == 42
        finally:
            p.uninstall()
    records = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert len(records) == 2, records
    assert {r["phase"] for r in records} == {"start", "end"}
    assert {r["rule"] for r in records} == {"t"}

def test_the_exit_road_reaches_the_captured_logger_too(tmp_path):
    """The exit loop hands the same captured logger to its actions.

    Entry is not the only road that fires: an exit-event rule runs after
    the body and needs the logger just as much, through the run_action
    call in the dispatcher's exit loop rather than the entries server.
    """
    import json
    import target_mod
    from pyteman.firing import FiringLog
    from pyteman.rules import Rule

    rule = Rule(id="t", module="target_mod", symbol="plain", event="exit",
                action={"kind": "return_value", "value": 7},
                fire={"mode": "always"})
    log_path = tmp_path / "firing.jsonl"
    with FiringLog(str(log_path)) as log:
        p = install([rule], log=log)
        try:
            p.force_patch_module("target_mod")
            target_mod.plain(5)
        finally:
            p.uninstall()
    records = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert records, "the exit firing never reached the log"
    assert {r["phase"] for r in records} >= {"start", "end"}
    assert {r["rule"] for r in records} == {"t"}

def test_uninstall_clears_applied():
    """applied is empty after uninstall, not a cumulative history."""
    import target_mod  # noqa: F401 -- ensures module is in sys.modules
    p = install([make_rule("plain")], log=None)
    p.force_patch_module("target_mod")
    assert "target_mod:plain" in p.applied
    p.uninstall()
    assert p.applied == []
