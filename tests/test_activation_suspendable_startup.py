# tests/test_activation_suspendable_startup.py
"""A suspendable target refuses the process at startup, not at first call.

The in-process cases live in test_activation_atomic.py. What they cannot show
is what the refusal does to a real interpreter, because the frame that decides
is site.execsitecustomize, and it only exists while Python is starting. That
frame catches Exception, so an ordinary raise out of sitecustomize is printed
as a one-line note and swallowed: the workload then runs uninstrumented and the
process exits 0, and a rule the operator believed was firing is silent.
SuspendableTargetError is a RuntimeError, so it lands squarely in that hole.
Raising SystemExit instead escapes the handler but turns startup into `Fatal
Python error: init_import_site` and exit 1, which reports a CPython failure
rather than a rule the operator can go and edit. The guard in sitecustomize
takes neither route, and this file is where that is measured.

The target is chosen so the refusal is the only thing that could have stopped
it. `_collections_abc.AsyncGenerator.asend` is a coroutine function on an
ordinary Python class, imported by `os` and therefore already in sys.modules
before site.py runs: activation reaches it during startup, and the setattr
would SUCCEED. A C type would have raised TypeError and produced the same exit
code for a reason that has nothing to do with the kind of the callable.
"""
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).parent
SRC = HERE.parent / "src" / "pyteman"

WORKLOAD = "print('WORKLOAD_RAN')"

# Same startup timing, same action, patchable in exactly the same way. The
# only difference is that the callable is an ordinary function, which is what
# makes this a control and not a second version of the case above. os._exists
# is chosen because it is only ever called during os module initialisation,
# which completes before site.py runs; patching it afterwards has no semantic
# effect on the interpreter, unlike _check_methods whose return value alters
# every issubclass check against a collections.abc ABC.
RULES_CONTROL = """
- id: control
  point: os._exists
  event: entry
  action: {kind: return_value, value: 1}
"""

RULES_COROUTINE = """
- id: suspendable
  point: _collections_abc.AsyncGenerator.asend
  event: entry
  action: {kind: return_value, value: 1}
"""

# A rule that installs cleanly, placed AHEAD of the refused one. Written as the
# two above joined, so a later edit to either cannot leave this one describing
# a point the control no longer uses.
RULES_GOOD_THEN_COROUTINE = RULES_CONTROL + RULES_COROUTINE


def rules_file(tmp, body):
    f = tmp / "r.yaml"
    f.write_text(body)
    return f


def run_py(tmp, env_extra, code=WORKLOAD):
    env = {**os.environ, "PYTHONPATH": f"{tmp}:{SRC}", **env_extra}
    try:
        return subprocess.run([sys.executable, "-c", code],
                              capture_output=True, text=True, env=env,
                              cwd=str(tmp), timeout=60)
    except subprocess.TimeoutExpired as exc:
        exc.add_note(f"pyteman: activation {sorted(env_extra)} under {tmp} "
                     f"did not finish in {exc.timeout}s")
        raise


def test_a_startup_rule_on_an_ordinary_callable_still_starts(tmp_path):
    """The control, without which every assertion below passes vacuously.

    If the point could not be patched at startup for some unrelated reason,
    the refusal test would be green while proving nothing about the kind of
    the callable.
    """
    r = run_py(tmp_path, {"PYTEMAN_RULES": str(rules_file(tmp_path,
                                                          RULES_CONTROL))})
    assert r.returncode == 0, r.stderr
    assert "WORKLOAD_RAN" in r.stdout, r.stdout


def test_a_suspendable_startup_target_refuses_the_process(tmp_path):
    """Exit 2 and a silent stdout, which have to hold together.

    A non-zero exit on its own would be satisfied by a process that ran the
    workload uninstrumented and reported badly afterwards, and that is the
    fail-open shape this refusal exists to close.
    """
    r = run_py(tmp_path, {"PYTEMAN_RULES": str(rules_file(tmp_path,
                                                          RULES_COROUTINE))})
    assert r.returncode == 2, f"expected exit 2, got {r.returncode}\n{r.stderr}"
    assert "WORKLOAD_RAN" not in r.stdout, f"workload ran anyway: {r.stdout!r}"
    assert r.stderr.startswith(
        "pyteman: refusing to start: installing instrumentation:"), r.stderr
    # The operator gets the kind, the point and the rule to go and edit, not
    # just the fact that something went wrong during startup. The two halves
    # are asserted separately because they are rendered from different things:
    # the refusal names the slot the way SlotOwnershipError does, as module and
    # bare attribute, while the qualified path an operator actually typed comes
    # from the rule description that follows it.
    assert "SuspendableTargetError" in r.stderr, r.stderr
    assert "_collections_abc:asend is a coroutine function" in r.stderr, r.stderr
    assert ("rule 'suspendable' at _collections_abc:AsyncGenerator.asend"
            in r.stderr), r.stderr


def test_a_refusal_at_startup_names_the_rule_that_caused_it(tmp_path):
    """A refused rule behind a good one still refuses, and says which one.

    The ordering matters because the good rule has already been applied by the
    time the second is judged, and an implementation that reported the rule it
    was on rather than the rule that failed would send the operator to edit a
    point that is fine. What happened to that first rule's slot is settled in
    test_activation_atomic.py, in the process that did the wrapping; a second
    interpreter could not answer it, because a fresh one never had the patch.
    """
    r = run_py(tmp_path, {"PYTEMAN_RULES": str(
        rules_file(tmp_path, RULES_GOOD_THEN_COROUTINE))})
    assert r.returncode == 2, r.stderr
    assert "WORKLOAD_RAN" not in r.stdout, f"workload ran anyway: {r.stdout!r}"
    assert "'suspendable'" in r.stderr, r.stderr
    assert "rule 'control'" not in r.stderr, r.stderr
