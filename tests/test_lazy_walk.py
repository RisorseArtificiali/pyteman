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


# --- dotted-first gap (TASK-176) -------------------------------------------


RULES_LAZY_NESTED = """\
- id: lazy-nested
  point: lazypkg.submod.leaf
  event: entry
  action: {kind: return_value, value: 99}
"""


def test_dotted_first_fires(sandbox):
    """First import is dotted (`import lazypkg.submod`), no by-name
    `import lazypkg` anywhere: rule fires after the submodule import."""
    code = (
        "import lazypkg.submod\n"
        "print(lazypkg.submod.leaf())\n"
    )
    r = _run(sandbox, RULES_LAZY_NESTED, code)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "99", (
        f"expected overridden 99, got {r.stdout.strip()!r} "
        f"(original is 7); stderr: {r.stderr}"
    )
    assert "never landed" not in r.stderr, r.stderr


def test_fromlist_fires(sandbox):
    """Pin row C: `from lazypkg import submod` passes the TOP module
    name to __import__ and already fires today."""
    code = (
        "from lazypkg import submod\n"
        "print(submod.leaf())\n"
    )
    r = _run(sandbox, RULES_LAZY_NESTED, code)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "99", (
        f"expected overridden 99, got {r.stdout.strip()!r}; stderr: {r.stderr}"
    )
    assert "never landed" not in r.stderr, r.stderr


def test_dotted_first_never_landed_report(sandbox):
    """Dotted import, but the RULE targets a segment that never arrives;
    the atexit report must fire now that a pending entry is created."""
    rules = """\
- id: ghost
  point: lazypkg.phantom.fn
  event: entry
  action: {kind: return_value, value: 0}
"""
    code = "import lazypkg.submod\n"
    r = _run(sandbox, rules, code)
    assert r.returncode == 0, f"exit code must stay 0; stderr: {r.stderr}"
    assert "pyteman: never landed:" in r.stderr, r.stderr
    assert "ghost" in r.stderr, r.stderr


def test_dotted_first_no_double_patch(sandbox):
    """Dotted-first followed by by-name import: rule fires exactly once,
    no double-wrap or duplicate applied entries."""
    code = (
        "import lazypkg.submod\n"
        "import lazypkg\n"
        "print(lazypkg.submod.leaf())\n"
        "import sys\n"
        "p = sys._pyteman['patcher']\n"
        "count = sum(1 for a in p.applied if 'submod.leaf' in a)\n"
        "print(f'applied={count}')\n"
    )
    r = _run(sandbox, RULES_LAZY_NESTED, code)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.strip().splitlines()
    assert lines[0] == "99", lines
    assert lines[1] == "applied=1", (
        f"expected exactly 1 applied entry, got {lines[1]!r}"
    )


def test_leaf_typo_reports_at_exit(sandbox):
    """A typo at the LEAF, past a complete intermediate walk, is reported too.

    The intermediate walk succeeds (the script imports the submodule), the
    leaf name does not exist. Before pending was made total this shape was
    silently skipped by the hasattr gate after the walk had already popped
    the entry, so the exit report stayed empty for exactly the typo the
    README promises to name.
    """
    rules = """\
- id: leaf-typo
  point: lazypkg.submod.nonexistent
  event: entry
  action: {kind: return_value, value: 0}
"""
    r = _run(sandbox, rules, "import lazypkg.submod\nprint(lazypkg.submod.leaf())\n")
    assert r.returncode == 0, f"exit code must stay 0; stderr: {r.stderr}"
    assert r.stdout.strip() == "7", r.stdout
    assert "pyteman: never landed:" in r.stderr, r.stderr
    assert "leaf-typo" in r.stderr, r.stderr


def test_never_imported_module_reports_at_exit(sandbox):
    """A rule whose module never imports at all is reported, not dropped.

    No walk ever runs for it, so before pending was made total it produced
    neither a wrap nor a pending entry: the quietest possible outcome for a
    requested rule.
    """
    rules = """\
- id: never-mod
  point: lazypkg.ghostmodule.fn
  event: entry
  action: {kind: return_value, value: 0}
"""
    r = _run(sandbox, rules, "print('plain')\n")
    assert r.returncode == 0, f"exit code must stay 0; stderr: {r.stderr}"
    assert r.stdout.strip() == "plain", r.stdout
    assert "pyteman: never landed:" in r.stderr, r.stderr
    assert "never-mod" in r.stderr, r.stderr


def test_leaf_typo_via_rearm_retry_still_reports(sandbox):
    """THE retry-hole regression: a leaf typo whose walk first missed on an
    intermediate segment. Importing the top module by name creates the
    re-arm key; importing the submodule then drains it and retries the walk,
    which reaches the absent leaf. The retry must not consume the report:
    the drain used to delete the entry before retrying, so this exact shape
    went quiet at exit even with pending total.
    """
    rules = """\
- id: retry-typo
  point: lazypkg.submod.nonexistent
  event: entry
  action: {kind: return_value, value: 0}
"""
    code = (
        "import lazypkg\n"
        "import lazypkg.submod\n"
        "print(lazypkg.submod.leaf())\n"
    )
    r = _run(sandbox, rules, code)
    assert r.returncode == 0, f"exit code must stay 0; stderr: {r.stderr}"
    assert r.stdout.strip() == "7", r.stdout
    assert "pyteman: never landed:" in r.stderr, r.stderr
    assert "retry-typo" in r.stderr, r.stderr


def test_landed_rule_not_resurrected_by_later_miss(sandbox):
    """Anti false-report: a rule that landed stays landed even when its
    submodule attribute is deleted afterwards and a later import re-runs the
    walk. The re-key used to re-add landed ordinals unconditionally, so the
    process exited reporting 'never landed' for a rule that had fired."""
    code = (
        "import lazypkg\n"
        "import lazypkg.submod\n"
        "assert lazypkg.submod.leaf() == 99\n"
        "del lazypkg.submod\n"
        "import lazypkg.eager\n"
        "print('survived')\n"
    )
    r = _run(sandbox, RULES_LAZY_NESTED, code)
    assert r.returncode == 0, f"exit code must stay 0; stderr: {r.stderr}"
    assert r.stdout.strip() == "survived", r.stdout
    assert "never landed" not in r.stderr, r.stderr
