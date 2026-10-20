"""Shared child-process tooling for the verification scripts.

Both run_coverage.py and verify_artifacts.py spawn children that must not
inherit the operator's pyteman configuration and must not load plugins the
operator happens to have installed. The constants and the helper here are
the single source for those decisions; each script adds its own extras on
top.

Not shipped. scripts/ is not granted by MANIFEST.in and is pruned by
neither a grant nor an exclude, so it stays out of every artifact by the
same mechanism the other scripts do.
"""
import os

CLEARED_IN_CHILD = ("PYTEMAN_RULES", "PYTEMAN_LOG", "PYTEMAN_REQUIRE_MARKER")

BASE_CHILD_ENV = {"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}


def say(message):
    """Progress, flushed, because children write straight to the terminal
    while a piped script's own stdout is block-buffered."""
    print(message, flush=True)


def child_env(extra=None, clear=CLEARED_IN_CHILD):
    """os.environ extended with the base child settings then clearances.

    *extra* is merged after the base, so a caller that needs
    PYTHONDONTWRITEBYTECODE adds it there and sees it in the result.
    *clear* defaults to CLEARED_IN_CHILD; run_coverage.py widens it to
    include its own coverage-redefining names.
    """
    env = {**os.environ, **BASE_CHILD_ENV, **(extra or {})}
    for name in clear:
        env.pop(name, None)
    return env
