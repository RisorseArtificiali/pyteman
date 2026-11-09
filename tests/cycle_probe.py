"""The shared weakref cycle probe (TASK-215, extracting the skeleton
the TASK-116 probe introduced), a plain module like the suite's other
shared test helpers rather than conftest machinery.

A raising frame that keeps a local bound to the exception it raises
retains the exception-traceback-frame cycle past the caller's catch
and drop: with the generational collector disabled, a weakref to the
dropped exception must die by refcount alone, or some local in the
raising frame is the loop back into it.
"""
import gc


def assert_dies_by_refcount(make_ref, label, rounds=3):
    """Run *make_ref* *rounds* times with gc disabled; every returned
    weakref must be dead.

    *make_ref* performs one round: it triggers the raise path, catches
    the exception into a weakref, drops every strong reference it held,
    and returns the weakref, or a list of weakrefs when one round
    measures several objects (a wrapper plus its annotated peers). A
    round that returns None or an empty list without raising fails here
    by name: that is the vacuous shape a broken probe must not be able
    to pass (the guard lives in this helper, not in each caller's
    diligence).
    """
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        refs = []
        for _ in range(rounds):
            ref = make_ref()
            if isinstance(ref, list):
                assert ref, (
                    f"{label}: make_ref returned an empty list without "
                    "raising; nothing was measured")
                refs.extend(ref)
            else:
                assert ref is not None, (
                    f"{label}: make_ref returned None without raising; "
                    "nothing was measured")
                refs.append(ref)
        alive = sum(1 for r in refs if r() is not None)
        assert alive == 0, (
            f"{alive}/{len(refs)} exceptions retained without gc; {label}"
        )
    finally:
        if was_enabled:
            gc.enable()
