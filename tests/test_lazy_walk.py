# tests/test_lazy_walk.py
"""Re-arm of walk misses on lazily-imported submodule segments.

Every test uses a real subprocess with sitecustomize activation, because the
import hook fires during interpreter startup and the atexit handler runs at
interpreter exit; both are unreachable from an in-process call.
"""
import os
import pathlib
import subprocess
import sys

import pytest

HERE = pathlib.Path(__file__).parent
SRC = HERE.parent / "src" / "pyteman"


# --- fixture package --------------------------------------------------------

LAZYPKG_INIT = """\
# Only eager is imported here; submod is deliberately lazy.
from . import eager
"""

LAZYPKG_EAGER = """\
def eager_fn():
    return 8
"""

LAZYPKG_SUBMOD = """\
def leaf():
    return 7
"""


@pytest.fixture
def sandbox(tmp_path):
    pkg = tmp_path / "lazypkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(LAZYPKG_INIT)
    (pkg / "eager.py").write_text(LAZYPKG_EAGER)
    (pkg / "submod.py").write_text(LAZYPKG_SUBMOD)
    return tmp_path


def _rules_file(tmp, body):
    f = tmp / "r.yaml"
    f.write_text(body)
    return f


def _run(tmp, rules_body, code):
    rf = _rules_file(tmp, rules_body)
    env = {
        **os.environ,
        "PYTHONPATH": f"{tmp}:{SRC}",
        "PYTEMAN_RULES": str(rf),
        "PYTEMAN_LOG": str(tmp / "pyteman.log"),
    }
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, env=env,
        cwd=str(tmp), timeout=60,
    )


# --- test cases -------------------------------------------------------------


RULES_FULL = """\
- id: flat-shutil
  point: shutil.rmtree
  event: entry
  action: {kind: return_value, value: 0}
- id: eager-nested
  point: lazypkg.eager.eager_fn
  event: entry
  action: {kind: return_value, value: 0}
- id: lazy-nested
  point: lazypkg.submod.leaf
  event: entry
  action: {kind: return_value, value: 99}
"""


def test_flat_fires(sandbox):
    r = _run(sandbox, RULES_FULL, (
        "import shutil; print(shutil.rmtree('/tmp/_t176_no', ignore_errors=True))"
    ))
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "0"


def test_eager_nested_fires(sandbox):
    r = _run(sandbox, RULES_FULL, (
        "import lazypkg; print(lazypkg.eager.eager_fn())"
    ))
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "0"


def test_lazy_nested_fires_after_submodule_import(sandbox):
    """THE regression test: lazy-nested fires after importing the submodule,
    without any re-import of the top module."""
    code = (
        "import lazypkg\n"
        "import lazypkg.submod\n"
        "print(lazypkg.submod.leaf())\n"
    )
    r = _run(sandbox, RULES_FULL, code)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "99", (
        f"expected overridden 99, got {r.stdout.strip()!r} "
        f"(original is 7); stderr: {r.stderr}"
    )


def test_typo_point_reports_at_exit(sandbox):
    rules = """\
- id: typo-rule
  point: lazypkg.no_such_attr.fn
  event: entry
  action: {kind: return_value, value: 0}
"""
    r = _run(sandbox, rules, "import lazypkg")
    assert r.returncode == 0, f"exit code must stay 0; stderr: {r.stderr}"
    assert "pyteman: never landed:" in r.stderr, r.stderr
    assert "typo-rule" in r.stderr, r.stderr


def test_pending_reflects_state(sandbox):
    rules = """\
- id: lazy-nested
  point: lazypkg.submod.leaf
  event: entry
  action: {kind: return_value, value: 99}
"""
    code = (
        "import sys, lazypkg\n"
        "p = sys._pyteman['patcher']\n"
        "before = len(p.pending())\n"
        "import lazypkg.submod\n"
        "after = len(p.pending())\n"
        "print(f'before={before} after={after}')\n"
        "print(lazypkg.submod.leaf())\n"
    )
    r = _run(sandbox, rules, code)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.strip().splitlines()
    assert lines[0] == "before=1 after=0", lines
    assert lines[1] == "99", lines


def test_unrearmable_nonmodule_miss_reports_at_exit(sandbox):
    (sandbox / "clsmod.py").write_text(
        "class Holder:\n    pass\n"
    )
    rules = """\
- id: unrearmable
  point: clsmod.Holder.missing.fn
  event: entry
  action: {kind: return_value, value: 0}
"""
    r = _run(sandbox, rules, "import clsmod")
    assert r.returncode == 0, f"exit code must stay 0; stderr: {r.stderr}"
    assert "pyteman: never landed:" in r.stderr, r.stderr
    assert "unrearmable" in r.stderr, r.stderr


def test_no_exit_report_when_all_rules_land(sandbox):
    rules = """\
- id: eager-only
  point: lazypkg.eager.eager_fn
  event: entry
  action: {kind: return_value, value: 0}
"""
    r = _run(sandbox, rules, "import lazypkg; lazypkg.eager.eager_fn()")
    assert r.returncode == 0
    assert "never landed" not in r.stderr, r.stderr
