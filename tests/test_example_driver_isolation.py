# tests/test_example_driver_isolation.py
"""Verify that both example drivers isolate HERMES_HOME before importing hermes.

The drivers import hermes_state, which evaluates DEFAULT_DB_PATH at module
scope via get_hermes_home(). If HERMES_HOME is not set to the scratch
directory before that import, the driver's own hermes operations bind to the
operator's ambient profile. These tests verify the ordering by parsing the
driver source: os.environ["HERMES_HOME"] must precede every hermes import
inside the main() function.
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


def _is_hermes_home_assignment(node: ast.stmt) -> bool:
    """True for os.environ["HERMES_HOME"] = ..."""
    if not isinstance(node, ast.Assign):
        return False
    for target in node.targets:
        if (isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Attribute)
                and isinstance(target.value.value, ast.Name)
                and target.value.value.id == "os"
                and target.value.attr == "environ"
                and isinstance(target.slice, ast.Constant)
                and target.slice.value == "HERMES_HOME"):
            return True
    return False


def _is_hermes_import(node: ast.stmt) -> bool:
    """True for 'from hermes_* import ...' or 'import hermes_*'."""
    if isinstance(node, ast.ImportFrom):
        if node.module:
            top = node.module.split(".")[0]
            return top in HERMES_MODULES
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name.split(".")[0] in HERMES_MODULES:
                return True
    return False


def _flatten(stmts):
    """Yield (line, node) for every statement, descending into if/for/while."""
    for node in stmts:
        yield (node.lineno, node)
        for field_name in ("body", "orelse", "handlers", "finalbody"):
            child_stmts = getattr(node, field_name, None)
            if isinstance(child_stmts, list):
                yield from _flatten(child_stmts)


@pytest.mark.parametrize("example,script", DRIVERS, ids=[d[0] for d in DRIVERS])
def test_no_module_level_hermes_imports(example, script):
    """A module-level hermes import would execute before main() runs."""
    source = (EXAMPLES / example / script).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=script)
    violations = []
    for node in tree.body:
        if _is_hermes_import(node):
            violations.append(f"line {node.lineno}: {ast.dump(node)}")
    assert not violations, (
        f"{example}/{script}: hermes imports at module level bypass "
        f"HERMES_HOME isolation:\n" + "\n".join(violations)
    )


@pytest.mark.parametrize("example,script", DRIVERS, ids=[d[0] for d in DRIVERS])
def test_hermes_home_is_set_before_hermes_imports(example, script):
    source = (EXAMPLES / example / script).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=script)
    body = _find_main_body(tree)
    stmts = list(_flatten(body))

    hermes_home_line = None
    first_hermes_import_line = None

    for lineno, node in stmts:
        if hermes_home_line is None and _is_hermes_home_assignment(node):
            hermes_home_line = lineno
        if first_hermes_import_line is None and _is_hermes_import(node):
            first_hermes_import_line = lineno

    assert hermes_home_line is not None, (
        f"{example}/{script}: os.environ['HERMES_HOME'] assignment not found in main()"
    )
    assert first_hermes_import_line is not None, (
        f"{example}/{script}: no hermes import found in main()"
    )
    assert hermes_home_line < first_hermes_import_line, (
        f"{example}/{script}: HERMES_HOME is set at line {hermes_home_line} but "
        f"the first hermes import is at line {first_hermes_import_line}; "
        f"the assignment must come first to isolate from the operator's profile"
    )
