# tests/test_unreadable_point.py
"""A point that exists but cannot be read (TASK-124).

The leaf gates read a slot with getattr-with-default and hasattr, and both
treat an AttributeError raised from INSIDE a property as an absent name.
The skip is kept: it is defensible Python semantics and the rule stays
pending with the exit report naming it. What these tests pin is the one
addition, the terminal `point_unreadable` record that separates a broken
getter from a typo, and the bound on it: a module `__getattr__` that
raises is indistinguishable from an absent name and produces no record.

Subprocess-real because the activation path and the atexit report are
part of the contract.
"""
import json
import os
import pathlib
import subprocess
import sys

import pytest

HERE = pathlib.Path(__file__).parent
SRC = HERE.parent / "src" / "pyteman"

PROPKG_INIT = """\
class Holder:
    @property
    def boom(self):
        # An unrelated uninitialized dependency, not a statement about
        # the attribute's existence.
        raise AttributeError("self._dep not initialized")

    def plain(self):
        return 5


holder = Holder()
"""


@pytest.fixture
def sandbox(tmp_path):
    pkg = tmp_path / "propkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(PROPKG_INIT)
    return tmp_path


def _run(tmp, rules_body, code):
    rf = tmp / "r.yaml"
    rf.write_text(rules_body)
    env = {
        **os.environ,
        "PYTHONPATH": f"{tmp}:{SRC}",
        "PYTEMAN_RULES": str(rf),
        "PYTEMAN_LOG": str(tmp / "pyteman.log"),
    }
    return subprocess.run([sys.executable, "-c", code],
                          capture_output=True, text=True, env=env,
                          cwd=str(tmp), timeout=60)


def _records(tmp):
    log = tmp / "pyteman.log"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines() if line]


RULES = """\
- id: boom-rule
  point: propkg.holder.boom
  event: entry
  action: {kind: return_value, value: 42}
- id: plain-rule
  point: propkg.holder.plain
  event: entry
  action: {kind: return_value, value: 7}
"""


def test_a_raising_getter_is_skipped_loudly(sandbox):
    """THE case: the point exists, the getter raises, the rule is skipped
    with one terminal record naming the full spelling and the exception."""
    code = (
        "import propkg\n"
        "print('plain=', propkg.holder.plain())\n"
    )
    r = _run(sandbox, RULES, code)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "plain= 7", r.stdout
    assert "pyteman: never landed: rule 'boom-rule' at propkg:holder.boom" \
        in r.stderr, r.stderr
    notes = [rec for rec in _records(sandbox)
             if rec.get("status") == "point_unreadable"]
    assert len(notes) == 1, _records(sandbox)
    rec = notes[0]
    assert rec["rule"] == "boom-rule"
    assert rec["point"] == "propkg.holder.boom"
    assert rec["phase"] == "end"
    # A solitary annotation, not an attempt: attempt and visit are null.
    assert rec["attempt"] is None
    assert rec["visit"] is None
    assert rec["outcome"] == (
        "reading propkg:holder.boom raised AttributeError: "
        "self._dep not initialized; the rule stays pending")


def test_a_typo_produces_no_record(sandbox):
    """The discriminator: an absent name is skipped exactly as quietly as
    before, so the record's presence is the whole signal."""
    rules = """\
- id: typo-rule
  point: propkg.holder.no_such_attr
  event: entry
  action: {kind: return_value, value: 42}
"""
    r = _run(sandbox, rules, "import propkg\nprint('ran')\n")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "ran", r.stdout
    assert "pyteman: never landed:" in r.stderr, r.stderr
    assert not [rec for rec in _records(sandbox)
                if rec.get("status") == "point_unreadable"], _records(sandbox)


def test_a_module_getattr_raising_stays_indistinguishable(sandbox):
    """The documented bound: a module __getattr__ that raises holds
    nothing in the module namespace, so presence cannot be asked and the
    skip is as quiet as a typo."""
    (sandbox / "gmod.py").write_text(
        "def __getattr__(name):\n"
        "    raise AttributeError('nothing is ever here')\n"
    )
    rules = """\
- id: ghost-rule
  point: gmod.anything
  event: entry
  action: {kind: return_value, value: 42}
"""
    r = _run(sandbox, rules, "import gmod\nprint('ran')\n")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "ran", r.stdout
    assert "pyteman: never landed:" in r.stderr, r.stderr
    assert not [rec for rec in _records(sandbox)
                if rec.get("status") == "point_unreadable"], _records(sandbox)


def test_a_hostile_str_does_not_break_the_import(sandbox):
    """A fault-injection target is code under test: an AttributeError
    subclass whose __str__ raises used to escape the annotation and fail
    the workload's import, where the old silent skip let it succeed. The
    message is deferred to _safe_message, which reports a diagnostic that
    cannot be built instead of letting it decide what propagates."""
    body = PROPKG_INIT.replace(
        'raise AttributeError("self._dep not initialized")',
        'raise AttributeErrorHostile()')
    body = body.replace(
        "class Holder:",
        "class AttributeErrorHostile(AttributeError):\n"
        "    def __str__(self):\n"
        "        raise RuntimeError('str refuses')\n"
        "\n"
        "\n"
        "class Holder:",
    )
    assert "AttributeErrorHostile" in body
    pkg = sandbox / "propkg"
    (pkg / "__init__.py").write_text(body)
    code = (
        "import propkg\n"
        "print('import_ok=', propkg.holder.plain())\n"
    )
    r = _run(sandbox, RULES, code)
    assert r.returncode == 0, r.stderr
    # The import survives and the sibling rule's override still answers.
    assert r.stdout.strip() == "import_ok= 7", r.stdout
    notes = [rec for rec in _records(sandbox)
             if rec.get("status") == "point_unreadable"]
    assert len(notes) == 1, _records(sandbox)
    assert "diagnostic unavailable" in notes[0]["outcome"], notes[0]
