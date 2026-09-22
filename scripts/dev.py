#!/usr/bin/env python3
"""The fast edit-loop commands, dispatched to the tools in the project environment.

    uv run --locked python scripts/dev.py check
    uv run --locked python scripts/dev.py test [pytest arguments]
    uv run --locked python scripts/dev.py format-check [paths]

Every tool below is located from `sys.executable`, so the interpreter that runs
this file decides which ruff and which basedpyright answer. `uv run --locked`
makes that the locked project environment rather than whatever PATH holds.

It installs nothing and repairs nothing: a missing tool is reported and the
command fails. The heavy drivers stay separate commands with their own
preconditions (scripts/run_coverage.py, scripts/verify_artifacts.py).
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# From the UNRESOLVED path. Measured here: .venv/bin/python is a symlink to
# /usr/bin/python3.14, so Path(sys.executable).resolve().parent is /usr/bin.
# Resolving would hand every lookup below to the ambient system tools while the
# command still looked like it had run the pinned ones.
BIN = Path(sys.executable).parent

# The whole tree, deliberately, rather than a list of directories.
#
# A list here is a second copy of the scope pyproject.toml's [tool.ruff]
# extend-exclude already defines, and the two can only drift apart. They had:
# an undefined name in examples/hermes-109966/holder.py passed `ruff check src
# tests scripts` and failed a bare `ruff check`, so this command was quieter
# than the formatter's own default on the same tree. A list also cannot cover a
# root-level module at all, since there is no directory to name.
#
# Measured equivalence before the change, with `ruff check --show-files`: the
# dot yields the 64 paths the four-directory list yielded plus pyproject.toml.
# It is a superset, so no file that was being linted stopped being linted.
LINT_SCOPE = "."

# Swept by prefix rather than named, unlike the fixed triple in
# scripts/run_coverage.py: those compare an artifact against an expectation and
# name what they clear, this only has to hand pytest an environment where the
# package is inert, so a variable added to the runtime later is covered on the
# day it is added.
CLEARED_PREFIX = "PYTEMAN_"

# Each lets an ambient value redefine the run while it still reports success.
# The PYTHON* names change what the interpreter is before any test runs;
# PYTEST_ADDOPTS injects arguments this file never passed, including
# deselections, and PYTEST_PLUGINS loads code the lock file never resolved.
#
# The COVERAGE_* names are the same four scripts/run_coverage.py calls
# REDEFINES_THE_RUN, cleared here for a different reason than there. They do not
# reach pytest: COVERAGE_PROCESS_START arms coverage's .pth hook at interpreter
# startup in every grandchild the suite spawns, and this suite's subject is
# import-time inertness. Measured: with it exported,
# tests/test_sitecustomize.py::test_inert_run_does_not_import_pyteman fails with
# ['typing'] and the file takes 197s; cleared, 25 pass in 17.8s.
CLEARED_IN_CHILD = (
    "PYTHONPATH",
    "PYTHONHOME",
    "PYTHONPYCACHEPREFIX",
    "PYTHONOPTIMIZE",
    "PYTHONINSPECT",
    "PYTHONSAFEPATH",
    "PYTHONWARNINGS",
    "PYTEST_ADDOPTS",
    "PYTEST_PLUGINS",
    "COVERAGE_RCFILE",
    "COVERAGE_PROCESS_CONFIG",
    "COVERAGE_PROCESS_START",
    "COVERAGE_FORCE_CONFIG",
)

# Autoload off keeps the run independent of the operator's installed plugins,
# which scripts/run_coverage.py measures at 0.19s against 2.5s. Bytecode off
# stops this command leaving .pyc residue in a checkout other processes read;
# it does not prevent reading a stale .pyc already on disk, which nothing here
# claims to do.
CHILD_ENV = {
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    "PYTHONDONTWRITEBYTECODE": "1",
}

# Asked of a subprocess rather than of this one: `import pyteman` here would
# answer for this file's interpreter, cwd and environment, and the question is
# what pytest will import.
IDENTITY_PROBE = (
    "import pathlib, pyteman; print(pathlib.Path(pyteman.__file__).resolve().parent)"
)


def child_env():
    """A copy of this environment with the overrides above applied."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(CLEARED_PREFIX)}
    for name in CLEARED_IN_CHILD:
        env.pop(name, None)
    env.update(CHILD_ENV)
    return env


def run(argv, env):
    """One child, its command echoed, its exit status returned unchanged.

    env is required rather than defaulted. A default is how the omission
    happened once already: `format_check` passed nothing and was the only
    command whose child ran under the ambient PYTHONWARNINGS and PYTEMAN_*,
    which reads as a decision rather than the oversight it was.

    Flushed: the children write straight to the terminal while this process's
    stdout is block-buffered as soon as it is piped.

    A child killed by a signal gives subprocess a negative returncode, which
    sys.exit turns into nonsense: measured, SIGKILL yields -9 and the shell
    then sees 247. Reported as 128+signal instead, the convention every shell
    already uses, so an OOM-killed pytest says 137 rather than 247.
    """
    print("$ " + " ".join(str(part) for part in argv), flush=True)
    code = subprocess.run(argv, cwd=ROOT, env=env).returncode
    return 128 - code if code < 0 else code


def tool(name):
    """A tool in the project environment, or a failure naming where it was sought.

    Absence is reported rather than repaired: installing from inside a check
    would mean the check had changed the environment it measured.

    Executability, not mere existence: a directory of that name, or a file left
    non-executable by an interrupted `uv sync`, satisfies exists() and then dies
    inside subprocess.run with a raw PermissionError traceback, which is the
    failure shape this function exists to replace.
    """
    path = BIN / name
    if not (path.is_file() and os.access(path, os.X_OK)):
        raise SystemExit(
            f"{name} is not an executable in {BIN}. Run `uv sync --locked`, and "
            "invoke this script as `uv run --locked python scripts/dev.py ...` "
            "so it runs from the project environment."
        )
    return path


def uv():
    """uv comes from PATH, not BIN: it is the launcher that chose the
    interpreter above, not a member of the environment it creates."""
    found = shutil.which("uv")
    if found is None:
        raise SystemExit(
            "uv is not on PATH. It builds and validates the locked environment "
            "this script runs in: https://docs.astral.sh/uv/"
        )
    return found


def require_project_environment():
    """Turn a cascade of missing tools into one sentence.

    Against sys.prefix rather than a hardcoded .venv, so a
    UV_PROJECT_ENVIRONMENT elsewhere still passes.
    """
    if sys.prefix == sys.base_prefix:
        raise SystemExit(
            f"{sys.executable} is a base interpreter, not the project "
            "environment, so the tools this script invokes would be whatever "
            "is installed globally. Run it as "
            "`uv run --locked python scripts/dev.py ...`."
        )


def check(rest):
    """Lock freshness, lint, types and metadata, stopping at the first failure.

    The lock is asked first: stale, it makes every later answer describe an
    environment that is not the one pinned.

    These children get the same cleaned environment as the suite, so the two
    commands are the peers the module docstring says they are. Measured: under
    an ambient PYTHONWARNINGS=error, validate-pyproject exits 1 on a
    PendingDeprecationWarning raised inside argparse, so `check` called this
    project's metadata invalid while nothing was wrong with it.
    """
    require_project_environment()
    if rest:
        raise SystemExit(
            f"check takes no arguments, so {' '.join(rest)} would have been "
            "dropped without running anything. Lint a subset with "
            "`uv run --locked ruff check <paths>`, or pass pytest arguments to `test`."
        )
    env = child_env()
    steps = (
        [uv(), "lock", "--check"],
        [tool("ruff"), "check", LINT_SCOPE],
        # Lock mode fails when the baseline would need updating instead of
        # updating it, which is what stops a check from accepting a new
        # diagnostic by recording it.
        [tool("basedpyright"), "--baselinemode=lock"],
        [tool("validate-pyproject"), "pyproject.toml"],
    )
    for argv in steps:
        code = run(argv, env=env)
        if code != 0:
            return code
    return 0


def test(rest):
    """The suite, or the subset the forwarded arguments name.

    -rs because a skip whose reason nobody reads is indistinguishable from a
    test that does not exist.
    """
    require_project_environment()
    env = child_env()
    verify_import_identity(env)
    return run([sys.executable, "-m", "pytest", "-q", "-rs", *rest], env=env)


def verify_import_identity(env):
    """Check that a plain `import pyteman` here resolves to this checkout.

    The suite imports pyteman rather than reading src/ off the path, so an
    ambient non-editable copy earlier on sys.path would run the whole suite
    against code that is not being edited, and pass. The probe uses the same
    interpreter, cwd and environment as the pytest call it guards, because each
    of those changes the answer. It is a check on the default import, not a
    guarantee about every path a test may later construct for itself.

    Both sides are resolved. The probe prints a resolved path, so comparing it
    against an unresolved expectation would refuse a correct editable install
    whenever src/ or src/pyteman/ is a symlink, with advice that cannot fix it.
    """
    expected = (ROOT / "src" / "pyteman").resolve()
    done = subprocess.run(
        [sys.executable, "-c", IDENTITY_PROBE],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )
    if done.returncode != 0:
        raise SystemExit(
            f"{sys.executable} cannot import pyteman, so there is nothing for "
            "the suite to test:\n"
            + done.stderr.strip()
            + "\nInstall the checkout with `uv sync --locked`."
        )
    found = done.stdout.strip()
    if found != str(expected):
        raise SystemExit(
            f"{sys.executable} imports pyteman from {found}, not from "
            f"{expected}. The suite would measure that copy instead of this "
            "checkout and would pass doing it. Reinstall this tree as editable "
            "with `uv sync --locked`."
        )


def format_check(rest):
    """Formatting, reported and never applied.

    Separate from `check` on purpose: most of this tree predates the formatter,
    so this is advisory for the operator and a gate on nothing.

    The child still gets the cleaned environment. Advisory is not a reason to
    let an ambient PYTHONWARNINGS or PYTHONPATH change what the answer is.
    """
    require_project_environment()
    return run(
        [tool("ruff"), "format", "--check", *(rest or [LINT_SCOPE])], env=child_env()
    )


COMMANDS = {"check": check, "test": test, "format-check": format_check}


def main(argv):
    # REMAINDER hangs off the top-level parser with the command as a plain
    # positional rather than off a subparser. Measured on this argparse: a
    # REMAINDER inside a subparser rejects `test -x` with "unrecognized
    # arguments", so pytest flags could not be forwarded at all.
    parser = argparse.ArgumentParser(
        prog="dev.py", description="Fast checks against the project environment."
    )
    parser.add_argument("command", choices=sorted(COMMANDS))
    parser.add_argument(
        "rest", nargs=argparse.REMAINDER, help="passed to the underlying tool unchanged"
    )
    args = parser.parse_args(argv)
    return COMMANDS[args.command](args.rest)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
