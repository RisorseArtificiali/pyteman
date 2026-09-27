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


def run_py(tmp, env_extra, code):
    # env_extra is merged last, so a caller needing a different import path
    # overrides PYTHONPATH here rather than through a parameter of its own.
    env = {**os.environ, "PYTHONPATH": f"{tmp}:{SRC}", **env_extra}
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
