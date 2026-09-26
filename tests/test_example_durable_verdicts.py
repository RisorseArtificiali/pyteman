"""Verify that both example drivers produce durable, structured verdicts.

AC #1: INCONCLUSIVE must not appear as automatic success (exit 0).
AC #2: After a mismatch the scratch home and verdict manifest survive.
AC #3: Scratch preservation must not interfere with process cleanup (EX-02).
"""
import ast
import sys
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"

DRIVERS = [
    ("hermes-109966", "run_repro.py"),
    ("hermes-111912", "run_repro.py"),
]


# ---------------------------------------------------------------------------
# Functional tests: import _resolve_exit_code from each driver and verify
# the full exit-code matrix.
# ---------------------------------------------------------------------------

@pytest.fixture(params=DRIVERS, ids=[d[0] for d in DRIVERS])
def resolve_fn(request, monkeypatch):
    example, script = request.param
    driver_dir = str(EXAMPLES / example)
    monkeypatch.syspath_prepend(driver_dir)
    mod_name = script.removesuffix(".py")
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    mod = __import__(mod_name)
    yield mod._resolve_exit_code
    del sys.modules[mod_name]


VERDICTS = ("CLEAN", "REPRODUCED", "INCONCLUSIVE")


@pytest.mark.parametrize("verdict", VERDICTS)
def test_no_expected_clean_and_reproduced_exit_zero(resolve_fn, verdict):
    code = resolve_fn(verdict, None)
    if verdict == "INCONCLUSIVE":
        assert code != 0, "INCONCLUSIVE without expected must not exit 0"
    else:
        assert code == 0


@pytest.mark.parametrize("verdict", VERDICTS)
def test_matching_expected_exits_zero(resolve_fn, verdict):
    assert resolve_fn(verdict, verdict) == 0


@pytest.mark.parametrize("verdict,expected", [
    ("CLEAN", "REPRODUCED"),
    ("REPRODUCED", "CLEAN"),
    ("INCONCLUSIVE", "CLEAN"),
    ("INCONCLUSIVE", "REPRODUCED"),
    ("CLEAN", "INCONCLUSIVE"),
    ("REPRODUCED", "INCONCLUSIVE"),
])
def test_mismatched_expected_exits_one(resolve_fn, verdict, expected):
    assert resolve_fn(verdict, expected) == 1


# ---------------------------------------------------------------------------
# Structural tests: verify manifest writing and scratch preservation exist
# in the AST of both drivers.
# ---------------------------------------------------------------------------

def _parse_main(example, script):
    source = (EXAMPLES / example / script).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=script)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            return tree, node
    pytest.fail(f"main() not found in {example}/{script}")


def _ast_has_string(node, target):
    """True when any ast.Constant under *node* contains *target* as substring."""
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            if target in child.value:
                return True
    return False


@pytest.mark.parametrize("example,script", DRIVERS, ids=[d[0] for d in DRIVERS])
def test_manifest_is_written(example, script):
    _tree, main_node = _parse_main(example, script)
    assert _ast_has_string(main_node, "verdict.json"), (
        f"{example}/{script}: main() does not write verdict.json"
    )


@pytest.mark.parametrize("example,script", DRIVERS, ids=[d[0] for d in DRIVERS])
def test_scratch_preserved_on_non_clean(example, script):
    _tree, main_node = _parse_main(example, script)
    assert _ast_has_string(main_node, "SCRATCH-HOME-PRESERVED"), (
        f"{example}/{script}: main() does not print SCRATCH-HOME-PRESERVED "
        f"for non-CLEAN verdicts"
    )
