"""Verify that example drivers detect incompatible checkouts before creating processes.

Each driver wraps its hermes imports in try/except ImportError and calls _fail
with an actionable message that names the missing module and the tested
revision. This is a structural test: it parses the AST to confirm the pattern,
so it does not require a hermes-agent checkout.
"""
import ast
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"

DRIVERS = [
    ("hermes-109966", "run_repro.py"),
    ("hermes-111912", "run_repro.py"),
]

HERMES_MODULES = frozenset({
    "hermes_state", "hermes_state_dbfile", "hermes_cli",
    "hermes_constants", "hermes_logging", "hermes_time",
})


def _find_main_body(tree: ast.Module) -> list[ast.stmt]:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            return node.body
    pytest.fail("main() not found in driver source")


def _flatten(stmts):
    for node in stmts:
        yield node
        for field_name in ("body", "orelse", "handlers", "finalbody"):
            child_stmts = getattr(node, field_name, None)
            if isinstance(child_stmts, list):
                yield from _flatten(child_stmts)


def _is_hermes_import(node: ast.stmt) -> bool:
    if isinstance(node, ast.ImportFrom):
        if node.module:
            top = node.module.split(".")[0]
            return top in HERMES_MODULES
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name.split(".")[0] in HERMES_MODULES:
                return True
    return False


@pytest.mark.parametrize("example,script", DRIVERS, ids=[d[0] for d in DRIVERS])
def test_hermes_imports_are_inside_try_except_importerror(example, script):
    """Every hermes import in main() must be inside a try/except ImportError."""
    source = (EXAMPLES / example / script).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=script)
    body = _find_main_body(tree)

    unguarded = []
    for node in _flatten(body):
        if not _is_hermes_import(node):
            continue
        guarded = False
        for outer in body:
            if not isinstance(outer, ast.Try):
                continue
            for handler in outer.handlers:
                if handler.type is None:
                    continue
                handler_names = set()
                if isinstance(handler.type, ast.Name):
                    handler_names.add(handler.type.id)
                elif isinstance(handler.type, ast.Tuple):
                    for elt in handler.type.elts:
                        if isinstance(elt, ast.Name):
                            handler_names.add(elt.id)
                if "ImportError" not in handler_names:
                    continue
                for inner in _flatten(outer.body):
                    if inner is node:
                        guarded = True
                        break
                if guarded:
                    break
            if guarded:
                break
        if not guarded:
            unguarded.append(f"line {node.lineno}: {ast.dump(node)}")

    assert not unguarded, (
        f"{example}/{script}: hermes imports outside try/except ImportError:\n"
        + "\n".join(unguarded)
    )


@pytest.mark.parametrize("example,script", DRIVERS, ids=[d[0] for d in DRIVERS])
def test_preflight_names_tested_revision(example, script):
    """The ImportError handler must mention a tested revision for actionability."""
    source = (EXAMPLES / example / script).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=script)
    body = _find_main_body(tree)

    found_revision_ref = False
    for node in _flatten(body):
        if not isinstance(node, ast.Try):
            continue
        for handler in node.handlers:
            if handler.type is None:
                continue
            handler_names = set()
            if isinstance(handler.type, ast.Name):
                handler_names.add(handler.type.id)
            elif isinstance(handler.type, ast.Tuple):
                for elt in handler.type.elts:
                    if isinstance(elt, ast.Name):
                        handler_names.add(elt.id)
            if "ImportError" not in handler_names:
                continue
            for child in ast.walk(handler):
                if isinstance(child, ast.Constant) and isinstance(child.value, str):
                    if "Tested revision" in child.value or "Tested revisions" in child.value:
                        found_revision_ref = True
                        break
            if found_revision_ref:
                break
        if found_revision_ref:
            break

    assert found_revision_ref, (
        f"{example}/{script}: ImportError handler does not mention tested revision"
    )
