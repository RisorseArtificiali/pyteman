"""Shared constants and helpers for the scripts that run the suite in
specialised environments.

Both run_coverage.py and verify_artifacts.py spawn child processes with
a sanitised environment and flushed progress output. The constants and
the environment builder live here so that neither file re-derives the
other's copy.
"""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Cleared so a child running the suite cannot inherit this script's own
# instrumentation: measured with PYTEMAN_RULES pointing at a missing file,
# the run came out 72 failed, 641 passed, and nothing in the output named
# the variable that caused it.
CLEARED_IN_CHILD = ("PYTEMAN_RULES", "PYTEMAN_LOG", "PYTEMAN_REQUIRE_MARKER")

# Cleared for the other reason (TASK-212): none of these can activate
# instrumentation alone, but each changes what activated code does, and
# measured with PYTEMAN_STRICT_PRAGMA exported the suite inside these
# scripts' children failed 43 of 1633 on pragma refusals the operator
# never asked for. extra merges after the clearing, so deliberate
# supply still works.
CLEARED_BEHAVIOR_IN_CHILD = ("PYTEMAN_STRICT_PRAGMA",
                             "PYTEMAN_STRICT_BARRIER", "PYTEMAN_RUN_ID")

_BASE_CHILD_ENV = {"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}


def say(message):
    """Progress, flushed, because children write straight to the terminal
    while this script's own stdout is block-buffered whenever it is
    piped."""
    print(message, flush=True)


def child_env(extra=None, also_clear=()):
    """Build a sanitised environment for a child process.

    Starts from os.environ, removes CLEARED_IN_CHILD, the behavior
    three and any additional keys in *also_clear*, then adds the base
    child settings and any *extra* mapping: deliberate supply merges
    after the clearing and wins, the same order the startup harness
    filters in (TASK-212; the old order cleared what extra had supplied,
    so no script could hand a child one of these names on purpose).
    """
    env = {k: v for k, v in os.environ.items()
           if k not in CLEARED_IN_CHILD
           and k not in CLEARED_BEHAVIOR_IN_CHILD}
    for name in also_clear:
        env.pop(name, None)
    env.update(_BASE_CHILD_ENV)
    env.update(extra or {})
    return env


def run_child(argv, *, cwd=None, env, capture=False, check=True):
    """Run a subprocess with optional capture and checking.

    Returns the CompletedProcess. Callers that need only the stripped
    stdout can read it from the result.
    """
    done = subprocess.run(
        argv, cwd=cwd, env=env, text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )
    if check and done.returncode != 0:
        if capture:
            say(done.stdout)
        raise SystemExit(
            f"FAILED ({done.returncode}): {' '.join(map(str, argv))}"
        )
    return done
