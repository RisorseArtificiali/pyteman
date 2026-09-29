"""Which import forms inject, and how each one that does not is signaled.

Every row calls the target and checks what it returned, so injection is proved
by the rule's value coming back, never by a marker on the callable. Every row
also pins the two signals: pending() for a rule that never landed, displaced()
for one that landed and was replaced since. A form that does not inject must
show up in exactly one of them; that is the no-false-success contract.

The rules come from load_rules, so every point is one a ruleset can express:
the module is the first dotted segment and the rest is walked from it.
"""
import importlib
import os
import pathlib
import subprocess
import sys

import pytest

from pyteman.patcher import activate, install
from pyteman.rules import load_rules

SRC = pathlib.Path(__file__).parent.parent / "src" / "pyteman"

FILES = {
    "ihc_flat.py": "def greet(n):\n    return n\n",
    "ihc_cls.py": "class K:\n    def m(self):\n        return 1\n",
    "ihc_bad.py": "from builtins import int as CInt\ndef ok():\n    return 1\n",
    "ihc_lazy.py": (
        "import types\n"
        "reads = []\n"
        "_box = types.SimpleNamespace(fn=lambda: 1)\n"
        "def __getattr__(name):\n"
        "    if name != 'box':\n"
        "        raise AttributeError(name)\n"
        "    reads.append(name)\n"
        "    return _box\n"
    ),
    "ihc_pkg/__init__.py": "",
    "ihc_pkg/leaf.py": "def compute(x):\n    return x * 2\n",
    "ihc_pkg/sub.py": "def work():\n    return 1\n",
    "ihc_pkg/rel_sub.py": "from . import sub\ndef call():\n    return sub.work()\n",
    "ihc_pkg/rel_from_sub.py": "from .sub import work\n",
    "ihc_pkg/abs_from_sub.py": "from ihc_pkg.sub import work\n",
    "ihc_pkg/lazy.py": "def go():\n    from . import sub\n    return sub.work()\n",
}

TOPS = ("ihc_flat", "ihc_cls", "ihc_bad", "ihc_lazy", "ihc_pkg", "ihc_never")


class EqualsAnything:
    """A replacement that `==` cannot tell from our wrapper; only `is` can."""

    def __eq__(self, other):
        return True

    __hash__ = object.__hash__


def _forget():
    for name in list(sys.modules):
        if name.split(".")[0] in TOPS:
            del sys.modules[name]


@pytest.fixture
def tree(tmp_path, monkeypatch):
    for rel, body in FILES.items():
        path = tmp_path / rel
        path.parent.mkdir(exist_ok=True)
        path.write_text(body)
    _forget()
    monkeypatch.syspath_prepend(str(tmp_path))
    yield tmp_path
    _forget()


def _rules(tmp, *points):
    body = "".join(
        f"- id: r{i}\n  point: {point}\n  event: entry\n"
        f"  action: {{kind: return_value, value: P}}\n"
        for i, point in enumerate(points))
    path = tmp / "rules.yaml"
    path.write_text(body)
    return load_rules(str(path))


def _desc(i, point):
    mod, _, sym = point.partition(".")
    return f"rule 'r{i}' at {mod}:{sym}"


@pytest.fixture
def patcher():
    live = []

    def start(rules, modules=None):
        p = install(rules) if modules is None else activate(rules, None, modules)
        live.append(p)
        return p

    yield start
    for p in reversed(live):
        p.uninstall()


# --- forms that inject ------------------------------------------------------


def test_import_flat(tree, patcher):
    p = patcher(_rules(tree, "ihc_flat.greet"))
    import ihc_flat
    assert ihc_flat.greet(1) == "P"
    assert p.pending() == () and p.displaced() == ()


def test_from_flat_import_binds_the_dispatcher(tree, patcher):
    p = patcher(_rules(tree, "ihc_flat.greet"))
    from ihc_flat import greet
    assert greet(1) == "P"
    assert p.pending() == () and p.displaced() == ()


def test_dotted_import_of_a_submodule(tree, patcher):
    p = patcher(_rules(tree, "ihc_pkg.leaf.compute"))
    import ihc_pkg.leaf
    assert ihc_pkg.leaf.compute(1) == "P"
    assert p.pending() == () and p.displaced() == ()


def test_from_package_import_submodule(tree, patcher):
    p = patcher(_rules(tree, "ihc_pkg.leaf.compute"))
    from ihc_pkg import leaf
    assert leaf.compute(1) == "P"
    assert p.pending() == () and p.displaced() == ()


def test_from_submodule_import_binds_the_dispatcher(tree, patcher):
    p = patcher(_rules(tree, "ihc_pkg.leaf.compute"))
    from ihc_pkg.leaf import compute
    assert compute(1) == "P"
    assert p.pending() == () and p.displaced() == ()


def test_relative_module_import_at_package_import(tree, patcher):
    p = patcher(_rules(tree, "ihc_pkg.sub.work"))
    import ihc_pkg.rel_sub
    assert ihc_pkg.rel_sub.call() == "P"
    assert p.pending() == () and p.displaced() == ()


def test_absolute_from_import_in_a_module_body_binds_the_dispatcher(
        tree, patcher):
    p = patcher(_rules(tree, "ihc_pkg.sub.work"))
    import ihc_pkg.abs_from_sub
    assert ihc_pkg.abs_from_sub.work() == "P"
    assert p.pending() == () and p.displaced() == ()


def test_relative_from_import_binds_the_original_unsignaled(tree, patcher):
    # The relative spelling of the row above. The hook sees `sub` at level 1,
    # finds no such module, and patches only when the outer import returns,
    # after the module body bound its alias to the original. The point is
    # patched and still is, so neither signal fires: a known gap, pinned.
    p = patcher(_rules(tree, "ihc_pkg.sub.work"))
    import ihc_pkg.rel_from_sub
    assert ihc_pkg.sub.work() == "P"
    assert ihc_pkg.rel_from_sub.work() == 1
    assert p.pending() == () and p.displaced() == ()


def test_preloaded_module_patched_by_activate(tree, patcher):
    import ihc_flat
    p = patcher(_rules(tree, "ihc_flat.greet"), modules=["ihc_flat"])
    assert ihc_flat.greet(1) == "P"
    assert p.pending() == () and p.displaced() == ()


def test_preloaded_module_patched_by_a_later_import_statement(tree, patcher):
    import ihc_flat
    p = patcher(_rules(tree, "ihc_flat.greet"))
    import ihc_flat  # noqa: F811, the statement is what the hook sees
    assert ihc_flat.greet(1) == "P"
    assert p.pending() == () and p.displaced() == ()


# --- forms that do not inject, each signaled --------------------------------


@pytest.mark.parametrize("modname, point, call", [
    ("ihc_flat", "ihc_flat.greet", lambda m: m.greet(1)),
    ("ihc_pkg.leaf", "ihc_pkg.leaf.compute", lambda m: m.compute(1)),
])
def test_import_module_stays_pending(tree, patcher, modname, point, call):
    p = patcher(_rules(tree, point))
    mod = importlib.import_module(modname)
    assert call(mod) in (1, 2)
    assert p.pending() == (_desc(0, point),)
    assert p.displaced() == ()


def test_relative_import_run_after_its_package_stays_pending(tree, patcher):
    p = patcher(_rules(tree, "ihc_pkg.sub.work"))
    import ihc_pkg.lazy
    assert ihc_pkg.lazy.go() == 1
    assert p.pending() == (_desc(0, "ihc_pkg.sub.work"),)
    assert p.displaced() == ()


def test_preloaded_module_under_bare_install_stays_pending(tree, patcher):
    import ihc_flat
    p = patcher(_rules(tree, "ihc_flat.greet"))
    assert ihc_flat.greet(1) == 1
    assert p.pending() == (_desc(0, "ihc_flat.greet"),)
    assert p.displaced() == ()


def test_reload_is_displaced_not_silent(tree, patcher):
    p = patcher(_rules(tree, "ihc_flat.greet"))
    import ihc_flat
    assert ihc_flat.greet(1) == "P"
    importlib.reload(ihc_flat)
    assert ihc_flat.greet(1) == 1
    assert p.pending() == ()
    assert p.displaced() == (_desc(0, "ihc_flat.greet"),)


def test_reload_of_a_class_is_displaced(tree, patcher):
    # The ledger slot is the OLD class, which still holds the dispatcher; only
    # walking the point from the module sees that calls no longer reach it.
    p = patcher(_rules(tree, "ihc_cls.K.m"))
    import ihc_cls
    assert ihc_cls.K().m() == "P"
    importlib.reload(ihc_cls)
    assert ihc_cls.K().m() == 1
    assert p.displaced() == (_desc(0, "ihc_cls.K.m"),)


def test_reload_then_import_is_in_force_again(tree, patcher):
    p = patcher(_rules(tree, "ihc_flat.greet"))
    import ihc_flat
    importlib.reload(ihc_flat)
    import ihc_flat  # noqa: F811, the statement is what the hook sees
    assert ihc_flat.greet(1) == "P"
    assert p.pending() == () and p.displaced() == ()


def test_hook_time_failure_raises_and_stays_pending(tree, patcher):
    p = patcher(_rules(tree, "ihc_bad.ok", "ihc_bad.CInt.bit_length"))
    with pytest.raises(TypeError) as info:
        import ihc_bad  # noqa: F401
    assert any(note.startswith("pyteman: while patching rule 'r1'")
               for note in info.value.__notes__)
    assert sys.modules["ihc_bad"].ok() == 1
    assert p.pending() == (_desc(0, "ihc_bad.ok"),
                           _desc(1, "ihc_bad.CInt.bit_length"))
    assert p.displaced() == ()


def test_module_never_imported_is_no_failure(tree, patcher):
    p = patcher(_rules(tree, "ihc_never.fn", "ihc_flat.greet"))
    import ihc_flat
    assert ihc_flat.greet(1) == "P"
    assert p.pending() == (_desc(0, "ihc_never.fn"),)
    assert p.displaced() == ()


# --- displaced() on its own terms -------------------------------------------


def test_third_party_replacement_is_displaced(tree, patcher):
    p = patcher(_rules(tree, "ihc_flat.greet"))
    import ihc_flat
    inner = ihc_flat.greet
    ihc_flat.greet = lambda n: ("theirs", inner(n))
    assert ihc_flat.greet(1) == ("theirs", "P")
    assert p.displaced() == (_desc(0, "ihc_flat.greet"),)


def test_a_replacement_that_claims_equality_is_still_displaced(tree, patcher):
    p = patcher(_rules(tree, "ihc_flat.greet"))
    import ihc_flat
    ihc_flat.greet = EqualsAnything()
    assert p.displaced() == (_desc(0, "ihc_flat.greet"),)


def test_absent_and_raising_points_are_displaced_without_escaping(tree,
                                                                  patcher):
    p = patcher(_rules(tree, "ihc_flat.greet"))
    import ihc_flat
    del ihc_flat.greet
    assert p.displaced() == (_desc(0, "ihc_flat.greet"),)

    def boom(name):
        raise RuntimeError(name)

    ihc_flat.__getattr__ = boom
    assert p.displaced() == (_desc(0, "ihc_flat.greet"),)


def test_module_gone_from_sys_modules_asks_the_slot(tree, patcher):
    p = patcher(_rules(tree, "ihc_flat.greet"))
    import ihc_flat
    del sys.modules["ihc_flat"]
    assert ihc_flat.greet(1) == "P"
    assert p.displaced() == ()

    ihc_flat.greet = EqualsAnything()
    assert p.displaced() == (_desc(0, "ihc_flat.greet"),)


def test_displaced_is_in_ruleset_order_and_deduplicated(tree, patcher):
    # Ledger order is import order (ihc_flat first); the report is not.
    p = patcher(_rules(tree, "ihc_cls.K.m", "ihc_flat.greet", "ihc_flat.greet"))
    import ihc_flat
    import ihc_cls
    importlib.reload(ihc_flat)
    importlib.reload(ihc_cls)
    assert p.displaced() == (_desc(0, "ihc_cls.K.m"),
                             _desc(1, "ihc_flat.greet"),
                             _desc(2, "ihc_flat.greet"))


def test_a_rule_displaced_twice_is_reported_once(tree, patcher):
    p = patcher(_rules(tree, "ihc_flat.greet"))
    import ihc_flat
    importlib.reload(ihc_flat)
    import ihc_flat  # noqa: F811, the statement is what the hook sees
    importlib.reload(ihc_flat)
    assert ihc_flat.greet(1) == 1
    assert p.displaced() == (_desc(0, "ihc_flat.greet"),)


def test_each_point_is_read_once_however_many_rules_name_it(tree, patcher):
    # The walk runs target code: here a module __getattr__ that counts.
    p = patcher(_rules(tree, "ihc_lazy.box.fn", "ihc_lazy.box.fn"))
    import ihc_lazy
    assert ihc_lazy.box.fn() == "P"
    ihc_lazy.reads.clear()
    assert p.displaced() == ()
    assert ihc_lazy.reads == ["box"]


def test_displaced_reads_without_changing_state(tree, patcher):
    import ihc_flat
    original = ihc_flat.greet
    p = patcher(_rules(tree, "ihc_flat.greet", "ihc_never.fn"))
    import ihc_flat  # noqa: F811, the statement is what the hook sees
    wrapper = ihc_flat.greet
    ihc_flat.greet = original
    applied = list(p.applied)
    assert p.displaced() == p.displaced() == (_desc(0, "ihc_flat.greet"),)
    assert p.pending() == (_desc(1, "ihc_never.fn"),)
    assert p.applied == applied
    ihc_flat.greet = wrapper
    assert p.displaced() == ()
    p.uninstall()
    assert ihc_flat.greet is original


def test_displaced_is_empty_after_uninstall(tree, patcher):
    p = patcher(_rules(tree, "ihc_flat.greet"))
    import ihc_flat
    importlib.reload(ihc_flat)
    assert p.displaced() != ()
    assert p.uninstall() == []
    assert p.displaced() == ()


# --- the exit report, through a real interpreter ----------------------------


def _run(tmp, rules_body, code):
    rf = tmp / "r.yaml"
    rf.write_text(rules_body)
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


RELOADED = """\
- id: reloaded
  point: ihc_flat.greet
  event: entry
  action: {kind: return_value, value: P}
"""

NEVER = """\
- id: never
  point: ihc_never.fn
  event: entry
  action: {kind: return_value, value: P}
"""

REPLACED_LINE = "pyteman: replaced after landing: rule 'reloaded' at ihc_flat:greet"


def test_exit_report_names_a_reloaded_rule(tree):
    r = _run(tree, RELOADED, (
        "import importlib, ihc_flat\n"
        "print(ihc_flat.greet(1))\n"
        "importlib.reload(ihc_flat)\n"
        "print(ihc_flat.greet(1))\n"
    ))
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ["P", "1"], r.stdout
    assert REPLACED_LINE + "\n" in r.stderr, r.stderr
    assert "never landed" not in r.stderr, r.stderr


def test_exit_report_is_silent_without_a_reload(tree):
    r = _run(tree, RELOADED, "import ihc_flat\nprint(ihc_flat.greet(1))\n")
    assert r.returncode == 0, r.stderr
    assert r.stdout.split() == ["P"], r.stdout
    assert "replaced after landing" not in r.stderr, r.stderr
    assert "never landed" not in r.stderr, r.stderr


def test_exit_report_lists_never_landed_before_replaced(tree):
    r = _run(tree, RELOADED + NEVER, (
        "import importlib, ihc_flat\n"
        "importlib.reload(ihc_flat)\n"
    ))
    assert r.returncode == 0, r.stderr
    never = "pyteman: never landed: rule 'never' at ihc_never:fn\n"
    assert never in r.stderr and REPLACED_LINE in r.stderr, r.stderr
    assert r.stderr.index(never) < r.stderr.index(REPLACED_LINE), r.stderr
