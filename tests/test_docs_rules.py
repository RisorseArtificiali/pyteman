"""The rule reference must stay loadable.

docs/rules.md now carries contracts the loader documents but deliberately
does not enforce, so a stale example there is not a cosmetic defect: it is
the only statement of what a valid ruleset looks like. Loading every YAML
block in it means a future tightening of load_rules breaks the documentation
in CI rather than in somebody's experiment. The README's yaml blocks meet
the same bar: they are the first thing a new user copies, and a schema
the loader refuses would break every fresh start at the front door. The
quickstart walkthrough's block is on the bar for the same reason: it is
the example a new user is walked through copying first.
"""
import re
import threading
from pathlib import Path

import pytest

from pyteman.patcher import _WRAPPER_CHAIN_LIMIT
from pyteman.rules import _MAX_SLEEP_MS, _UNCONSTRUCTIBLE_EXC, load_rules

_ROOT = Path(__file__).resolve().parent.parent

def _yaml_blocks(text):
    """The fenced yaml blocks of a markdown doc, by the one extractor that
    decides what counts as a loadable example, so every doc on the load
    bar is held to the same fences."""
    return re.findall(r"^```yaml\n(.*?)^```", text, re.M | re.S)


DOC = _ROOT / "docs" / "rules.md"
TEXT = DOC.read_text()
BLOCKS = _yaml_blocks(TEXT)

README = _ROOT / "README.md"
README_TEXT = README.read_text(encoding="utf-8")
README_BLOCKS = _yaml_blocks(README_TEXT)

QUICKSTART = _ROOT / "docs" / "quickstart.md"
QUICKSTART_TEXT = QUICKSTART.read_text(encoding="utf-8")
QUICKSTART_BLOCKS = _yaml_blocks(QUICKSTART_TEXT)


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


def _loaded(tmp_path, block):
    """Materialize one documented block as the ruleset it claims to be."""
    path = tmp_path / "rules.yaml"
    path.write_text(block)
    return load_rules(str(path))


@pytest.mark.parametrize("block", BLOCKS, ids=[_label(b) for b in BLOCKS])
def test_every_documented_ruleset_loads(tmp_path, block):
    assert _loaded(tmp_path, block)


def test_readme_has_yaml_examples_to_check():
    # The exact count, not a floor: once a doc legitimately grows, a floor
    # lets a later removal of a whole fenced example pass silently, both
    # assertions green on the smaller set. The exact count makes every
    # addition and removal a deliberate edit here. The equality below
    # catches the other direction, a fence the extractor fails to match.
    assert len(README_BLOCKS) == 2, (
        "README.md's yaml example count changed; update this pin "
        "deliberately")
    assert len(README_BLOCKS) == README_TEXT.count("```yaml")


def test_quickstart_has_its_yaml_example_to_check():
    # The same exact-count guard as the README's, for the walkthrough.
    assert len(QUICKSTART_BLOCKS) == 1, (
        "docs/quickstart.md's yaml example count changed; update this "
        "pin deliberately")
    assert len(QUICKSTART_BLOCKS) == QUICKSTART_TEXT.count("```yaml")


@pytest.mark.parametrize(
    "block", README_BLOCKS,
    ids=[_label(b) for b in README_BLOCKS],
)
def test_every_readme_ruleset_loads(tmp_path, block):
    assert _loaded(tmp_path, block)


@pytest.mark.parametrize(
    "block", QUICKSTART_BLOCKS,
    ids=[_label(b) for b in QUICKSTART_BLOCKS],
)
def test_the_quickstart_walkthrough_ruleset_loads(tmp_path, block):
    assert _loaded(tmp_path, block)


def test_documented_bounds_match_the_constants():
    """The two ceilings are printed in the reference but derived in the code.

    threading.TIMEOUT_MAX is platform dependent, so the figures in the table
    are a claim about the running interpreter, and nothing else in the suite
    would notice them going stale. The doc says as much next to the table.
    """
    assert str(_MAX_SLEEP_MS) in TEXT
    assert repr(threading.TIMEOUT_MAX) in TEXT


def test_documented_chain_limit_matches_the_constant():
    """The chain-walk bound in the reference is the constant in patcher.py."""
    assert f"runs past {_WRAPPER_CHAIN_LIMIT} links" in TEXT


@pytest.mark.parametrize("heading", [
    "## Where each check happens",
    "## Points whose work does not happen during the call",
    "### What is recognised",
])
def test_sections_the_pointers_name_exist(heading):
    """Docstrings and comments cite these headings; a rename must go red."""
    assert heading in TEXT


def test_documented_denylist_matches_the_constant():
    """The classes the reference names are the ones the loader refuses.

    _UNCONSTRUCTIBLE_EXC is derived from the running interpreter, the same
    way the two ceilings are, so a Python release that fixes one of them
    should break this file rather than leave a ruleset rejected for a reason
    the reference no longer gives.
    """
    for name in _UNCONSTRUCTIBLE_EXC:
        assert name in TEXT, f"{name} is refused at load but not documented"


def test_the_documented_split_refusal_is_the_built_one():
    """The coroutine-exit refusal the reference quotes is the built text.

    The quote is wrapped across lines in the document, so a plain `in`
    misses a divergence that a reformat hides behind. Whitespace is
    collapsed on both sides and the builder is run with the exact names
    the example uses, which ties the fence to the one source of the
    text: _coroutine_exit_refusal.
    """
    from pyteman.patcher import _COROUTINE_PHRASE, _coroutine_exit_refusal
    built = _coroutine_exit_refusal(
        "mypkg.tasks", "fetch", _COROUTINE_PHRASE,
        "rule 'trace-fetch' at mypkg.tasks:fetch")
    flat = " ".join(TEXT.split())
    assert " ".join(built.split()) in flat, (
        "docs/rules.md no longer quotes the refusal the builder produces")


@pytest.mark.parametrize("placeholder", [
    "<unprintable ",
    "<unknown type>",
    "<notes unavailable>",
    "<unreadable id>",
])
def test_degradation_placeholder_documented(placeholder):
    """Each placeholder the code can produce is named in the reference."""
    assert placeholder in TEXT, f"{placeholder} not in docs/rules.md"
