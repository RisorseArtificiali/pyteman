"""The package surface the docs promise, pinned so it cannot drift silently.

TASK-158's contract: the three patch-time refusals share PatchRefusalError,
the name is reachable from a bare ``import pyteman`` without importing the
machinery, and the lazy export stays discoverable. The suite passed with the
re-parenting reverted before this file existed, which is exactly the hole
these assertions close.
"""

import os
import pytest
import subprocess
import sys

from pyteman.patcher import (
    PatchRefusalError,
    SlotOwnershipError,
    SuspendableTargetError,
    UnsupportedTargetError,
)


def test_the_three_patch_time_refusals_share_the_base():
    for leaf in (SlotOwnershipError, SuspendableTargetError, UnsupportedTargetError):
        assert issubclass(leaf, PatchRefusalError), leaf
    assert issubclass(PatchRefusalError, RuntimeError)


def test_the_base_is_reachable_from_a_bare_import():
    env = {
        k: v for k, v in os.environ.items()
        if not k.startswith("PYTEMAN") and k != "PYTHONPATH"
    }
    probe = subprocess.run(
        [sys.executable, "-c",
         "import pyteman, sys; print('pyteman.patcher' in sys.modules);"
         " print(pyteman.PatchRefusalError.__name__);"
         " import pyteman.patcher;"
         " print(pyteman.PatchRefusalError is pyteman.patcher.PatchRefusalError)"],
        capture_output=True, text=True, timeout=30, env=env)
    assert probe.returncode == 0, \
        f"surface probe failed (rc={probe.returncode}): {probe.stderr}"
    lines = probe.stdout.split()
    assert lines[0] == "False", \
        "a bare import must not load pyteman.patcher; the export is lazy"
    assert lines[1] == "PatchRefusalError", probe.stdout
    assert lines[2] == "True", \
        "the exported name must be the class _patch raises, not a shadow"


def test_the_lazy_export_stays_discoverable():
    import pyteman
    assert "PatchRefusalError" in dir(pyteman)


def test_an_unknown_name_still_raises_attribute_error():
    """The fallback importlib relies on: a miss must not return None."""
    import pyteman
    with pytest.raises(AttributeError):
        pyteman.definitely_not_a_name
    assert not hasattr(pyteman, "definitely_not_a_name")
