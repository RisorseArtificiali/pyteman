"""Structural tests for reproducibility prerequisites in example drivers.

Verifies that hermes imports inside main() are wrapped in try/except
ImportError with an actionable message naming tested revisions, so an
incompatible checkout fails immediately instead of crashing deep in the
scenario.
"""
from __future__ import annotations

import ast
import os

import pytest

EXAMPLES_DIR = os.path.join(os.path.dirname(__file__), os.pardir, "examples")

DRIVERS = [
    ("hermes-109966", os.path.join(EXAMPLES_DIR, "hermes-109966", "run_repro.py")),
    ("hermes-111912", os.path.join(EXAMPLES_DIR, "hermes-111912", "run_repro.py")),
]


def _parse_main(path: str) -> tuple[str, ast.FunctionDef]:
    with open(path, encoding="utf-8") as fh:
        source = fh.read()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            return source, node
    pytest.fail(f"no main() found in {path}")


def _hermes_module(name: str) -> bool:
    return name.startswith("hermes_state") or name.startswith("hermes_cli")


def _find_hermes_imports(body: list[ast.stmt]) -> list[ast.stmt]:
    result = []
    for stmt in body:
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            names = []
            if isinstance(stmt, ast.ImportFrom) and stmt.module:
                names.append(stmt.module)
            for alias in stmt.names:
                names.append(alias.name)
            if any(_hermes_module(n) for n in names):
                result.append(stmt)
    return result


@pytest.mark.parametrize("label,path", DRIVERS, ids=[d[0] for d in DRIVERS])
def test_hermes_imports_are_inside_try_except_importerror(label, path):
    _source, main_fn = _parse_main(path)
    bare = _find_hermes_imports(main_fn.body)
    assert not bare, (
        f"{label}: hermes imports in main() must be inside try/except ImportError, "
        f"found {len(bare)} bare import(s) at line(s) {[s.lineno for s in bare]}"
    )
    found_handler = False
    for stmt in ast.walk(main_fn):
        if isinstance(stmt, ast.Try):
            for handler in stmt.handlers:
                if (isinstance(handler.type, ast.Name)
                        and handler.type.id == "ImportError"):
                    guarded = _find_hermes_imports(stmt.body)
                    if guarded:
                        found_handler = True
    assert found_handler, f"{label}: no try/except ImportError wrapping hermes imports in main()"


@pytest.mark.parametrize("label,path", DRIVERS, ids=[d[0] for d in DRIVERS])
def test_preflight_names_tested_revision(label, path):
    source, main_fn = _parse_main(path)
    segment = ast.get_source_segment(source, main_fn)
    assert segment is not None, f"could not extract main() source from {path}"
    found = "Tested revision" in segment or "Tested revisions" in segment
    assert found, (
        f"{label}: the ImportError handler must mention 'Tested revision(s)' "
        "so users know which upstream commits the driver was verified against"
    )
