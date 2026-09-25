"""The rule reference must stay loadable.

docs/rules.md now carries contracts the loader documents but deliberately
does not enforce, so a stale example there is not a cosmetic defect: it is
the only statement of what a valid ruleset looks like. Loading every YAML
block in it means a future tightening of load_rules breaks the documentation
in CI rather than in somebody's experiment.
"""
import re
import threading
from pathlib import Path

import pytest

from pyteman.rules import _MAX_SLEEP_MS, _UNCONSTRUCTIBLE_EXC, load_rules

DOC = Path(__file__).resolve().parent.parent / "docs" / "rules.md"
TEXT = DOC.read_text()
BLOCKS = re.findall(r"^```yaml\n(.*?)^```", TEXT, re.M | re.S)


def _label(block):
    """First rule id in the block, so a failure names the example it broke."""
    found = re.search(r"^- id: (\S+)", block, re.M)
    return found.group(1) if found else "unlabelled"


def test_the_reference_has_examples_to_check():
    # The floor comes first because the equality alone is satisfied by zero on
    # both sides: reformat the fences and every example silently leaves the
    # parametrization while this file stays green. The equality then catches
    # the other direction, a fence the regex fails to match.
    assert len(BLOCKS) >= 3, "docs/rules.md lost its yaml examples"
    assert len(BLOCKS) == TEXT.count("```yaml")


@pytest.mark.parametrize("block", BLOCKS, ids=[_label(b) for b in BLOCKS])
def test_every_documented_ruleset_loads(tmp_path, block):
    path = tmp_path / "rules.yaml"
    path.write_text(block)
    assert load_rules(str(path))


def test_documented_bounds_match_the_constants():
    """The two ceilings are printed in the reference but derived in the code.

    threading.TIMEOUT_MAX is platform dependent, so the figures in the table
    are a claim about the running interpreter, and nothing else in the suite
    would notice them going stale. The doc says as much next to the table.
    """
    assert str(_MAX_SLEEP_MS) in TEXT
    assert repr(threading.TIMEOUT_MAX) in TEXT


def test_documented_denylist_matches_the_constant():
    """The classes the reference names are the ones the loader refuses.

    _UNCONSTRUCTIBLE_EXC is derived from the running interpreter, the same
    way the two ceilings are, so a Python release that fixes one of them
    should break this file rather than leave a ruleset rejected for a reason
    the reference no longer gives.
    """
    for name in _UNCONSTRUCTIBLE_EXC:
        assert name in TEXT, f"{name} is refused at load but not documented"


@pytest.mark.parametrize("placeholder", [
    "<unprintable ",
    "<unknown type>",
    "<notes unavailable>",
    "<unreadable id>",
])
def test_degradation_placeholder_documented(placeholder):
    """Each placeholder the code can produce is named in the reference."""
    assert placeholder in TEXT, f"{placeholder} not in docs/rules.md"
