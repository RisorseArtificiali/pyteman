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
        # Exact applied identity and not a substring: the applied entry for a
        # point is "<module>:<symbol>" verbatim, and a substring would also
        # count a hypothetical sibling such as "submod.leafish".
        "count = sum(1 for a in p.applied if a == 'lazypkg:submod.leaf')\n"
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


# --- TASK-177: nothing that fails after the leaf gate goes quiet -------------

FROZPKG_INIT = """\
def plain_fn():
    return 3


class Frozen:
    def __setattr__(self, name, value):
        raise TypeError("frozen by the target")


frozen = Frozen()
object.__setattr__(frozen, "attr", lambda: 5)
"""


def test_pass2_setattr_refusal_keeps_the_rule_pending(sandbox):
    """CR-2: a walk that reaches its leaf but fails in pass 2 must not lose
    the rule. The pending entry used to be popped at leaf confirmation, so a
    hostile __setattr__ left the rule in neither applied nor pending and the
    exit report said nothing about a patch that was asked for and never
    happened."""
    pkg = sandbox / "frozpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(FROZPKG_INIT)
    rules = """\
- id: frozen-rule
  point: frozpkg.frozen.attr
  event: entry
  action: {kind: return_value, value: 0}
"""
    code = (
        "try:\n"
        "    import frozpkg\n"
        "except Exception:\n"
        "    print('IMPORT_FAILED')\n"
    )
    r = _run(sandbox, rules, code)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "IMPORT_FAILED", r.stdout
    assert "pyteman: never landed:" in r.stderr, r.stderr
    assert "frozen-rule" in r.stderr, r.stderr


DELPKG_INIT = '''\
def leaf_target():
    return 7


def _stand_in():
    return 1


def __getattr__(name):
    # Asking for ghost deletes leaf_target during the caller's own walk,
    # which is the window between pass 1 resolving a slot and pass 2
    # re-reading it.
    if name == "ghost":
        import sys
        sys.modules[__name__].__dict__.pop("leaf_target", None)
        return _stand_in
    raise AttributeError(name)
'''


def test_pass2_absent_skip_keeps_the_rule_pending(sandbox):
    """The silent _ABSENT skip in pass 2 must not drop an already resolved
    rule either: a module __getattr__ deletes another rule's segment during
    the same _patch window, pass 2 finds the attribute gone, skips, and the
    rule has to surface in the exit report instead of vanishing."""
    pkg = sandbox / "delpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(DELPKG_INIT)
    rules = """\
- id: deleted-rule
  point: delpkg.leaf_target
  event: entry
  action: {kind: return_value, value: 0}
- id: deleting-rule
  point: delpkg.ghost
  event: entry
  action: {kind: return_value, value: 3}
"""
    code = (
        "import delpkg\n"
        "print(delpkg.ghost())\n"
    )
    r = _run(sandbox, rules, code)
    assert r.returncode == 0, r.stderr
    # The deleting rule lands and its override answers, which is what makes
    # the loss of the OTHER rule non-obvious: nothing about this output says
    # a second rule was asked for and dropped.
    assert r.stdout.strip() == "3", r.stdout
    assert "pyteman: never landed:" in r.stderr, r.stderr
    assert "deleted-rule" in r.stderr, r.stderr
    assert "deleting-rule" not in r.stderr, r.stderr


NONEPKG_INIT = "backend = None\n"


def test_none_middle_segment_reports_without_rearm(sandbox):
    """CR-5: a real None on the walk is not an absent segment. The old
    getattr default misread it as one and created a re-armable pending entry
    keyed on a name that exists. The walk now walks through the None and
    misses on the next lookup, which is unrearmable."""
    rules = """\
- id: cr5-none
  point: nonepkg.backend.do_work
  event: entry
  action: {kind: return_value, value: 42}
"""
    pkg = sandbox / "nonepkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(NONEPKG_INIT)
    # The pending key is the discriminator: the old getattr-default walk
    # also reported never-landed, but keyed the entry on "nonepkg.backend",
    # a name that exists, so the hook would retry the walk on every import
    # of that name. Pinned white-box because pending() exposes descriptions
    # only and the key is the whole behavioral difference.
    code = (
        "import nonepkg\n"
        "import sys\n"
        "keys = sorted(repr(v[0]) for v in"
        " sys._pyteman['patcher']._pending.values())\n"
        "print('none-middle')\n"
        "print(keys)\n"
    )
    r = _run(sandbox, rules, code)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.strip().splitlines()
    assert lines[0] == "none-middle", r.stdout
    # _pending maps ordinal -> (pkey, plan_entry); only the pkey matters.
    assert lines[1].count("None") >= 1, r.stdout
    assert "nonepkg.backend" not in lines[1], r.stdout
    assert "pyteman: never landed:" in r.stderr, r.stderr
    assert "cr5-none" in r.stderr, r.stderr


def test_none_leaf_is_refused_as_a_data_attribute(sandbox):
    """The other half of the sentinel choice: a None that IS the leaf gets
    the ordinary data-attribute refusal, the same answer an attribute holding
    any other non-callable gets, and not a silent walk miss."""
    pkg = sandbox / "nonepkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(NONEPKG_INIT)
    rules = """\
- id: cr5-leaf
  point: nonepkg.backend
  event: entry
  action: {kind: return_value, value: 42}
"""
    code = (
        "try:\n"
        "    import nonepkg\n"
        "except Exception as exc:\n"
        "    print(type(exc).__name__)\n"
    )
    r = _run(sandbox, rules, code)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "UnsupportedTargetError", r.stdout
    # The refusal text rides the exception the workload catches; the rule
    # also stays pending, so it is named at exit rather than dropped.
    assert "pyteman: never landed:" in r.stderr, r.stderr
    assert "cr5-leaf" in r.stderr, r.stderr


def test_atexit_survives_a_rebound_sys_pyteman(sandbox):
    """CR-1: the atexit handler reads sys._pyteman inside its guard, so a
    workload that rebinds it to a non-dict exits without an AttributeError
    traceback printed after the workload's own output."""
    code = (
        "import sys\n"
        "import lazypkg\n"
        "print(lazypkg.eager.eager_fn())\n"
        "sys._pyteman = ['not a dict']\n"
    )
    r = _run(sandbox, RULES_LAZY_NESTED, code)
    assert r.returncode == 0, r.stderr
    assert "Traceback" not in r.stderr, r.stderr
    assert "AttributeError" not in r.stderr, r.stderr


def test_rollback_restores_a_rule_applied_earlier_in_the_call(sandbox):
    """The handler half of CR-2: a rule that applied on an earlier slot and
    was popped on that strength is installed nowhere once the unwind rolls
    the whole call back, so the exit report has to name it too. Without the
    restore in the handler the rule would be lost exactly like a pass-2
    refusal loses one."""
    pkg = sandbox / "frozpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(FROZPKG_INIT)
    rules = """\
- id: plain-rule
  point: frozpkg.plain_fn
  event: entry
  action: {kind: return_value, value: 0}
- id: frozen-rule
  point: frozpkg.frozen.attr
  event: entry
  action: {kind: return_value, value: 0}
"""
    code = (
        "import sys\n"
        "try:\n"
        "    import frozpkg\n"
        "except Exception:\n"
        "    print('IMPORT_FAILED')\n"
        "p = sys._pyteman['patcher']\n"
        "print(f'applied={len(p.applied)}')\n"
    )
    r = _run(sandbox, rules, code)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.strip().splitlines()
    assert lines[0] == "IMPORT_FAILED", r.stdout
    assert lines[1] == "applied=0", r.stdout
    assert "pyteman: never landed:" in r.stderr, r.stderr
    assert "plain-rule" in r.stderr, r.stderr
    assert "frozen-rule" in r.stderr, r.stderr


EXTPKG_INIT = """\
def fn1():
    return 1


class Flippable:
    hostile = False

    def __setattr__(self, name, value):
        if type(self).hostile:
            raise TypeError("flipped hostile")
        object.__setattr__(self, name, value)


victim = Flippable()
"""


def test_extend_rollback_restores_the_plan_identity(sandbox):
    """The extend half of the restore: a rule landed by EXTENDING a
    dispatcher that was already live, in a call that then fails on a fresh
    install, is rolled back and must re-enter pending carrying its plan
    entry. The restore used to slice the spec in hand, and the specs
    _extend_dispatcher returns carry a fresh _State where a plan entry
    carries the described identity, so the exit report printed a state repr
    instead of naming the rule."""
    pkg = sandbox / "extpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(EXTPKG_INIT)
    (pkg / "submod.py").write_text("x = 1\n")
    rules = """\
- id: fn1-rule
  point: extpkg.fn1
  event: entry
  action: {kind: return_value, value: 0}
- id: alias-rule
  point: extpkg.fn1_alias
  event: entry
  action: {kind: return_value, value: 0}
- id: victim-rule
  point: extpkg.victim.attr
  event: entry
  action: {kind: return_value, value: 0}
"""
    code = (
        "import extpkg\n"
        "extpkg.fn1_alias = extpkg.fn1\n"
        "extpkg.Flippable.hostile = True\n"
        "object.__setattr__(extpkg.victim, 'attr', lambda: 2)\n"
        "try:\n"
        "    import extpkg.submod\n"
        "except Exception:\n"
        "    print('CALL2_FAILED')\n"
        "import sys\n"
        "p = sys._pyteman['patcher']\n"
        "print('fn1_applied=', any("
        "a == 'extpkg:fn1' for a in p.applied))\n"
        "print('alias_applied=', any("
        "a == 'extpkg:fn1_alias' for a in p.applied))\n"
    )
    r = _run(sandbox, rules, code)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.strip().splitlines()
    assert lines[0] == "CALL2_FAILED", r.stdout
    # fn1-rule landed in the first call and its dispatcher survived the
    # second call's failure untouched; the alias rule was published by no
    # call, because the call that landed it is the one that failed.
    assert lines[1] == "fn1_applied= True", r.stdout
    assert lines[2] == "alias_applied= False", r.stdout
    assert "pyteman: never landed:" in r.stderr, r.stderr
    # The restored entry reports the described identity, not a state repr.
    assert "rule 'alias-rule' at extpkg:fn1_alias" in r.stderr, r.stderr
    assert "rule 'victim-rule' at extpkg:victim.attr" in r.stderr, r.stderr
    assert "fn1-rule" not in r.stderr, r.stderr


def test_foreign_module_key_rearms_through_the_drain_scan(sandbox):
    """A pending key can name a module OUTSIDE the rule's own tree, because
    the walk follows attributes, not package structure: mypkg re-exports
    other.util, a rule on mypkg.util.fn.work misses on fn and keys itself
    on "other.util.fn", whose prefixes are no rule module. The prefix loop
    patches nothing on `import other.util.fn`; the drain scan below it is
    the only retry the hook runs, and it is what makes this rule fire. The
    block used to be commented 'unreachable by construction', which this
    test disproves; any re-arm index built to replace the scan must answer
    non-prefix keys too."""
    for path in ("mypkg/__init__.py", "other/__init__.py",
                 "other/util/__init__.py"):
        (sandbox / path).parent.mkdir(parents=True, exist_ok=True)
        (sandbox / path).write_text("")
    (sandbox / "mypkg" / "__init__.py").write_text("from other import util\n")
    (sandbox / "other" / "util" / "fn.py").write_text(
        "def work():\n    return 7\n")
    rules = """\
- id: foreign-key
  point: mypkg.util.fn.work
  event: entry
  action: {kind: return_value, value: 42}
  fire: {mode: always}
"""
    code = (
        "import mypkg\n"
        "import other.util.fn\n"
        "print('result=', mypkg.util.fn.work())\n"
        "import sys\n"
        "p = sys._pyteman['patcher']\n"
        "print('applied=', p.applied)\n"
    )
    r = _run(sandbox, rules, code)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.strip().splitlines()
    assert lines[0] == "result= 42", r.stdout
    assert lines[1] == "applied= ['mypkg:util.fn.work']", r.stdout
    assert "never landed" not in r.stderr, r.stderr
