"""Declared internal-guard tooling, shared by the re-entry tests.

NOT a workload scenario, and deliberately kept in its own module so that
nothing here can be mistaken for a fixture describing something a real target
does. Everything in here stands INSIDE production's own call path because no
ordinary target can reach that point any more, and each user says so in its own
docstring.
"""
import contextlib

import pyteman.patcher as patcher_module


@contextlib.contextmanager
def counting_binding_signature(hook=None, hook_on=1):
    """Count, and optionally re-enter, at the real signature read.

    DECLARED INTERNAL-GUARD TOOL, not a workload scenario. The suite's original
    lever was a `__signature__` property on the target, which worked only
    because the old binding path called `inspect.signature` and therefore ran
    the target's own code. This design reads type dicts and base slot
    descriptors and runs nothing the target controls, so the lever is gone
    together with the hazard it exploited, and no ordinary target can reach
    this window any more.

    The contracts the lever was serving are unaffected and still need a call
    placed INSIDE that window, so this supplies one. It delegates in full and
    never substitutes a result, so production sees exactly the answer it would
    have computed on its own; what the wrapper adds is a count and a place to
    stand. Tests that a real import, getter or setter can still drive are NOT
    converted to this.
    """
    calls = []
    real = patcher_module._binding_signature

    def wrapper(original):
        calls.append(original)
        # Before delegating, so the re-entry is inside the read rather than
        # after it, which is where the original property fired.
        if hook is not None and len(calls) == hook_on:
            hook()
        return real(original)

    patcher_module._binding_signature = wrapper
    try:
        yield calls
    finally:
        patcher_module._binding_signature = real
