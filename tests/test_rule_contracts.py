"""Gating contracts the load-time validation must not quietly change.

CFG-01 tightens `fire:` (countdown now requires an explicit non-negative `n`,
once_per an explicit `key`). These tests pin the SEMANTICS those fields feed,
as documented in the README: `countdown n` fires on call n+1. A stricter
loader that shifted that off-by-one would silently re-time every experiment
built on the old contract. The companion once_per contract, a key consumed
only when the condition passes, is already pinned by
tests/test_patcher.py::test_once_per_key_not_consumed_when_condition_fails.
"""
import pytest

from pyteman.rules import Rule
from pyteman.patcher import install


def _rule(fire, when=None):
    return Rule(id="t", module="target_mod", symbol="plain", event="entry",
                action={"kind": "return_value", "value": 99}, when=when, fire=fire)


def _call_sequence(rule, calls):
    """Return value of `plain(1)` for each call, with the rule installed."""
    import target_mod
    p = install([rule], log=None)
    try:
        p.force_patch_module("target_mod")
        return [target_mod.plain(1) for _ in range(calls)]
    finally:
        p.uninstall()


@pytest.mark.parametrize("n", [0, 1, 3, 5])
def test_countdown_fires_on_call_n_plus_one(n):
    # plain(1) naturally returns 1; 99 marks the single injected call. Asserting
    # the whole sequence pins position, uniqueness and the untouched calls at
    # once, and spells out that n=0 fires immediately.
    assert _call_sequence(_rule({"mode": "countdown", "n": n}), n + 3) == [1] * n + [99, 1, 1]


def test_countdown_counts_calls_not_matches():
    """A false `when` still burns the countdown slot, unlike once_per's key.

    _gate increments `fires` before it evaluates anything, so `n` counts calls
    to the point rather than calls that satisfy the condition. The asymmetry
    with once_per is deliberate and load-bearing: a rule whose condition is
    false on call n+1 never fires at all.
    """
    rule = _rule({"mode": "countdown", "n": 1}, when="kwargs.get('b', 0) == 1")
    import target_mod
    p = install([rule], log=None)
    try:
        p.force_patch_module("target_mod")
        assert target_mod.plain(1) == 1          # call 1: countdown not reached
        assert target_mod.plain(1) == 1          # call 2 is the slot, but when is false
        assert target_mod.plain(1, b=1) == 2     # slot spent: no fire, natural 1+1
    finally:
        p.uninstall()


def test_entry_rule_naming_result_dies_inside_the_instrumented_call():
    """The contract rules.py documents instead of enforcing, pinned end to end.

    `result` is bound on the exit branch only, so an entry rule reading it
    compiles at load and raises NameError out of the workload's own call. The
    load-time free-name check that would have caught it was removed: it could
    see neither `(lambda: result)()` nor `result or (result := 1)`, and a
    check that rejects the plain spelling while passing those two is a
    guarantee that misleads. This test is what remains of that guarantee.

    WHEN it dies follows the gate's evaluation order, and the two answers
    differ: `always` evaluates the condition on every call, so the very first
    one raises, while `countdown` returns early without evaluating anything
    until call n + 1.
    """
    import target_mod
    for fire, survivors in (({"mode": "always"}, 0),
                            ({"mode": "countdown", "n": 2}, 2)):
        rule = _rule(fire, when="result is None")
        p = install([rule], log=None)
        try:
            p.force_patch_module("target_mod")
            for _ in range(survivors):
                assert target_mod.plain(1) == 1
            with pytest.raises(NameError, match="result"):
                target_mod.plain(1)
        finally:
            p.uninstall()
