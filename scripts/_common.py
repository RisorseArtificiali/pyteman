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

CLEARED_IN_CHILD = ("PYTEMAN_RULES", "PYTEMAN_LOG", "PYTEMAN_REQUIRE_MARKER")

_BASE_CHILD_ENV = {"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}


def say(message):
    """Progress, flushed, because children write straight to the terminal
    while this script's own stdout is block-buffered whenever it is
    piped."""
    print(message, flush=True)


def child_env(extra=None, also_clear=()):
    """Build a sanitised environment for a child process.

    Starts from os.environ, adds the base child settings and any
    *extra* mapping, then removes CLEARED_IN_CHILD and any additional
    keys in *also_clear*.
    """
    env = {**os.environ, **_BASE_CHILD_ENV, **(extra or {})}
    for name in (*CLEARED_IN_CHILD, *also_clear):
        env.pop(name, None)
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
