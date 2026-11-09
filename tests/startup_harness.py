# tests/startup_harness.py
"""The startup harness shared by the activation and sitecustomize tests.

Extracted from two near-identical copies that existed only because one
file was reserved to another owner while its task was open. The timeout
and the diagnostic note on it are the load-bearing parts and moved
whole.
"""
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).parent
# The inner directory on PYTHONPATH makes sitecustomize importable at the
# top level, which is the activation shape under test.
SRC = HERE.parent / "src" / "pyteman"


def rules_file(tmp, body):
    f = tmp / "r.yaml"
    f.write_text(body)
    return f


# Present in every sdist, absent from every checkout: the one shared
# discriminator for "running inside a built distribution" (hoisted from
# test_packaging when a second consumer appeared; the battery runs from
# a full checkout and is always on the False side, which is why the
# artifact leg is the only run that can see an artifact-only skip).
INSIDE_A_BUILT_DISTRIBUTION = (HERE.parent / "PKG-INFO").exists()

# Cleared from child environments: these variables activate the real
# instrumentation, so a developer with one exported would make the inert
# and refusal cases environment-dependent.
CLEARED_IN_CHILD = ("PYTEMAN_RULES", "PYTEMAN_LOG", "PYTEMAN_REQUIRE_MARKER")

# Cleared for the other reason (TASK-212): none of these can activate the
# instrumentation alone, but each changes what activated code does once
# something else activates it, strict pragma and barrier refusals and run
# attribution, so a developer with one exported would make behavior
# environment-dependent the same way the activation three make inertness.
CLEARED_BEHAVIOR_IN_CHILD = ("PYTEMAN_STRICT_PRAGMA",
                             "PYTEMAN_STRICT_BARRIER", "PYTEMAN_RUN_ID")

# Everything run_py filters; the two tuples above carry the rationales,
# this carries the membership.
CLEARED_IN_CHILD_ALL = CLEARED_IN_CHILD + CLEARED_BEHAVIOR_IN_CHILD


def clear_ambient_pyteman(monkeypatch):
    """Delete every cleared name from THIS process, via monkeypatch.

    The one loop both process-level consumers call: the conftest autouse
    fixture that makes every test environment-independent, and the shim
    fixture that imports sitecustomize in-process. Structural parity
    rather than two hand-kept copies of the same loop.
    """
    for name in CLEARED_IN_CHILD_ALL:
        monkeypatch.delenv(name, raising=False)


def run_py(tmp, env_extra, code):
    # env_extra is merged last, after the filter, so a caller needing a
    # variable here, or a different import path, supplies it deliberately
    # rather than through a parameter of its own.
    env = {k: v for k, v in os.environ.items()
           if k not in CLEARED_IN_CHILD_ALL}
    env.update({"PYTHONPATH": f"{tmp}:{SRC}", **env_extra})
    try:
        return subprocess.run([sys.executable, "-c", code],
                              capture_output=True, text=True, env=env,
                              cwd=str(tmp), timeout=60)
    except subprocess.TimeoutExpired as exc:
        # TimeoutExpired names only the command, which is the workload
        # inlined after -c and identical across most cases; the activation
        # under test is what differs, so the note carries that. The
        # exception the caller sees is unchanged.
        exc.add_note(f"pyteman: activation {sorted(env_extra)} under {tmp} "
                     f"did not finish in {exc.timeout}s")
        raise
