#!/usr/bin/env python3
"""Run the suite under coverage and check that the lines only a child process
can execute were actually measured.

    python scripts/run_coverage.py [--rcfile PATH]

TASK-34.1. The reasoning, the measurements behind each setting, and the exact
scope of what this proves are in docs/coverage.md. What follows is only what a
reader of this file needs.

Why a contract check rather than a percentage. Almost every interesting line in
this package runs in a subprocess, and several of them end in os._exit, which
skips atexit and therefore skips the write coverage does there. Both failures
are silent: the run stays green, the report stays plausible, and the number
drifts down by an amount nobody can distinguish from a deleted test. The check
below names two specific lines, one per mechanism, and fails if either is
missing. A percentage cannot express that, which is why this sets no threshold.

Why the configuration is named rather than found. This script exists to certify
one file, and coverage will read a different one without saying so if
COVERAGE_RCFILE is exported. Every coverage subcommand below is therefore given
an explicit --rcfile, measured to win over the environment variable. --rcfile on
the command line is also how the vacuity check runs this against a deliberately
broken copy of the configuration.

Why the suite is also run uninstrumented elsewhere. Instrumentation is
observable from inside a child process here, so one test in this suite cannot
pass under it and is deselected in this job and nowhere else. The mechanism is
at DESELECTED_UNDER_COVERAGE below, and the deselection is guarded rather than
trusted, because pytest ignores an unknown --deselect without a word.
"""

import ast
import importlib.util
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from _childenv import CLEARED_IN_CHILD, child_env, say

ROOT = Path(__file__).resolve().parent.parent

# The floor is the release whose wheel carries coverage's process-startup hook
# as an ordinary packaged file. Before it, asking for the subprocess patch made
# coverage write a .pth into site-packages at runtime, which fails wherever that
# directory is not writable and leaves a file behind wherever it is.
#
# Read off the wheels rather than the changelog, because the interesting version
# is the one whose prose and whose artifact disagree. 7.12.0 ships no .pth at
# all. 7.12.1b1 ships one, at
# `coverage-7.12.1b1.data/data/lib/python3.14/site-packages/zzz_coverage.pth`,
# which is the wheel data scheme with an interpreter path baked into it and is
# why that build's hook does not land. 7.13.0 moves it to `a1_coverage.pth` at
# the archive root, where an installer puts it in site-packages, and 7.14.1 is
# unchanged in that respect.
#
# So the floor has to be a release that exists: there is no 7.12.1 final, the
# index goes 7.12.0 straight to 7.13.0, and `pip install coverage==7.12.1`
# fails. Naming 7.13.0 also closes a hole rather than merely correcting a
# number, because version_info[:3] of 7.12.1b1 is (7, 12, 1) and a floor of
# (7, 12, 1) admitted precisely the build documented as broken.
MINIMUM_COVERAGE: tuple[int, int, int] = (7, 13, 0)

# One witness per way this suite makes a child, named by the symbol that
# contains the line rather than by number: a line number in a script is a claim
# about a file the script does not own, and it survives every edit to that file
# until the day it silently points at a blank line.
#
# Both are child-only, both end the process where they stand, and measured
# against every broken patch list both report MISS together, so neither is the
# sturdier one and neither says WHICH setting broke. The pair covers the other
# axis instead: _dispatch is reached through multiprocessing.Process and
# _refuse through an exec of a fresh interpreter. A third entry is earned by a
# third way of starting a child, not by a third os._exit, and the argument for
# that is in docs/coverage.md.
#
# The kill action's os._exit sits in `_dispatch`, which `run_action` calls; it
# was named `run_action` here until the action bodies were split out of it.
# The witness is the same line reached the same way, so the contract above is
# untouched: what moved is the symbol containing it. Naming a module-private
# symbol is deliberate, because this is a claim about a line in THIS package,
# not about a public surface.
EXIT_SENTINELS = (
    ("pyteman.actions", "_dispatch"),
    ("pyteman.sitecustomize", "_refuse"),
)

# Deselected under instrumentation and nowhere else. It asserts that a child of
# this suite imports nothing beyond the activation shim, which is true of an
# ordinary run and false of an instrumented one for a reason that belongs to
# coverage rather than to this package: the .pth that carries measurement into
# children imports coverage, and coverage imports typing. Weakening the test
# would lose that signal on every interpreter; deselecting it here loses it in
# one job while the uninstrumented matrix keeps running it on all four.
DESELECTED_UNDER_COVERAGE = (
    "tests/test_sitecustomize.py::test_inert_run_does_not_import_pyteman",
)

# CHILD_ENV and CLEARED_IN_CHILD are in _childenv.py. This script does NOT
# add PYTHONDONTWRITEBYTECODE, deliberately: nothing is built here, and the
# residue that matters is coverage data, not bytecode. verify_artifacts.py
# adds it because stray bytecode would corrupt its tree comparison.

# A different reason, and a sharper one. Each of these lets an ambient value
# redefine what is being measured while every check below still passes, which
# is the exact failure this script exists to make impossible. Read from the
# coverage source rather than assumed: COVERAGE_RCFILE replaces the
# configuration wholesale, so the run certifies a file it never opened;
# PYTEST_ADDOPTS injects deselections through the same blind spot the
# deselection guard exists to close, silently shrinking the suite.
#
# The two startup names are the pair most easily missed, because the obvious
# backstop does not reach either of them. COVERAGE_PROCESS_START and
# COVERAGE_PROCESS_CONFIG arm the same hook, `if os.getenv(...) or
# os.getenv(...)` in coverage's pth_file.py, and that hook runs at interpreter
# startup before argv is parsed, so naming the configuration on the command
# line cannot override it. COVERAGE_FORCE_CONFIG is applied in
# read_coverage_config as step 5, after the named file at step 2 and after the
# constructor arguments at step 4, so it overrides the named file outright.
#
# So the claim to make here is narrow: naming the file on the command line wins
# over COVERAGE_RCFILE, and for these three it is this list that does the work.
REDEFINES_THE_RUN = (
    "COVERAGE_RCFILE",
    "COVERAGE_PROCESS_CONFIG",
    "COVERAGE_PROCESS_START",
    "COVERAGE_FORCE_CONFIG",
    "PYTEST_ADDOPTS",
)


def run(argv, data_file, capture=False, check=True):
    env = child_env(
        extra={"COVERAGE_FILE": str(data_file)},
        clear=CLEARED_IN_CHILD + REDEFINES_THE_RUN,
    )
    done = subprocess.run(
        argv, cwd=ROOT, env=env, text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )
    if check and done.returncode != 0:
        if capture:
            say(done.stdout)
        raise SystemExit(f"FAILED ({done.returncode}): {' '.join(map(str, argv))}")
    return done


def resolve_rcfile(argv):
    """The configuration this run certifies, named rather than discovered.

    Defaults to the project's pyproject.toml. The override exists for the
    vacuity check, which has to run this script against a copy whose patch list
    has been broken on purpose, and passing it as an argument keeps that
    procedure visible in the command instead of hidden in the environment.
    """
    if not argv:
        return ROOT / "pyproject.toml"
    if len(argv) == 2 and argv[0] == "--rcfile":
        rcfile = Path(argv[1]).resolve()
        if not rcfile.is_file():
            raise SystemExit(f"--rcfile {rcfile} does not exist")
        return rcfile
    raise SystemExit("usage: run_coverage.py [--rcfile PATH]")


def check_the_tool_is_here():
    """coverage is a test tool rather than a dependency of this package, so it
    is absent by default and its absence has to name itself."""
    floor = ".".join(map(str, MINIMUM_COVERAGE))
    try:
        import coverage
    except ImportError:
        raise SystemExit(
            f"{sys.executable} has no coverage. This is a test tool and not a "
            "runtime dependency of pyteman, so nothing installs it for you: "
            f"pip install 'coverage>={floor}'"
        )
    # version_info rather than a split of __version__, which carries a suffix
    # on every prerelease and turns this check into a ValueError.
    if coverage.version_info[:3] < MINIMUM_COVERAGE:
        raise SystemExit(
            f"coverage {coverage.__version__} is older than {floor}, which is "
            "the first release that ships the process-startup hook with the "
            "package. Before it, measuring subprocesses wrote a .pth into "
            "site-packages at runtime."
        )


def statements_of(function_node):
    """Every node in this function's own scope, stopping at any scope nested
    inside it.

    ast.walk would descend into a nested def, a nested class body and a lambda,
    so a function containing none of its own os._exit calls but holding exactly
    one in an inner scope would resolve silently against a line that is not the
    sentinel. Measured on all three shapes, each of which ast.walk accepts
    without complaint.
    """
    pending = list(function_node.body)
    while pending:
        node = pending.pop()
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef, ast.Lambda)):
            continue
        pending.extend(ast.iter_child_nodes(node))


def resolve_exit_line(module_name, function_name):
    """The file and line of the os._exit call inside a named function.

    find_spec locates the module without executing it, which is the whole
    reason this reads source rather than importing. Both modules here call
    os._exit on some path, and one of them does so from code that runs at
    import time.
    """
    # Caught rather than tested against None, because the two failures are not
    # the same call. A missing submodule of an installed package returns None;
    # a package that is not installed at all raises from the parent import, and
    # that is the case a developer actually hits.
    try:
        spec = importlib.util.find_spec(module_name)
    except ModuleNotFoundError:
        spec = None
    if spec is None or not spec.origin:
        raise SystemExit(
            f"cannot locate {module_name}. The suite imports this package "
            "rather than reading src/ off the path, so it has to be installed: "
            "pip install -e ."
        )
    path = Path(spec.origin).resolve()
    # An ambient non-editable install would put this under site-packages while
    # the suite measured the checkout, and the mismatch would surface as a
    # missing sentinel rather than as the install problem it is.
    if not path.is_relative_to(ROOT):
        raise SystemExit(
            f"{module_name} resolves to {path}, outside {ROOT}. This run would "
            "compare lines from one copy of the package against coverage data "
            "for another: install this checkout with pip install -e ."
        )
    tree = ast.parse(path.read_text(), filename=str(path))
    # Every definition of the name, not the first one found. Two defs sharing a
    # name are legal Python and only the last one runs, so taking the first
    # would bind this check to a body that can never execute and report MISS
    # forever while pointing the operator at the patch list.
    targets = [node for node in ast.walk(tree)
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
               and node.name == function_name]
    if len(targets) != 1:
        raise SystemExit(
            f"{module_name} holds {len(targets)} definitions named "
            f"{function_name}"
            + (": this script's EXIT_SENTINELS list has drifted from the code "
               "it is meant to watch"
               if not targets else
               f" at lines {[node.lineno for node in targets]}, so which one "
               "this contract is about is ambiguous")
        )
    lines = sorted({
        node.lineno
        for node in statements_of(targets[0])
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_exit"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "os"
    })
    if len(lines) != 1:
        raise SystemExit(
            f"{module_name}.{function_name} holds {len(lines)} os._exit calls "
            f"at {lines} in its own scope, and this check is written for "
            "exactly one. The function has changed shape, so what the contract "
            "means has changed with it: revisit EXIT_SENTINELS and "
            "docs/coverage.md together rather than adjusting this number."
        )
    return path, lines[0]


def check_the_deselections_still_resolve(data_file):
    """A deselection that stopped matching, or that grew to match more, caught
    before either one rots.

    Two different silent failures, and the guard has to answer both because
    pytest answers neither. It accepts --deselect for a node id that does not
    exist and says nothing, exiting 0, so a renamed test turns the flag into a
    no-op. And it deselects by PREFIX rather than by equality, measured: given a
    sibling whose name extends the guarded one, `--deselect <id>` reports "1
    passed, 2 deselected" while collecting that same id reports one test. So
    this collects the whole file once and asks both questions of the result.
    """
    for node_id in DESELECTED_UNDER_COVERAGE:
        test_file = node_id.split("::", 1)[0]
        done = run([sys.executable, "-m", "pytest", "--collect-only", "-q", test_file],
                   data_file, capture=True, check=False)
        if done.returncode != 0:
            say(done.stdout)
            raise SystemExit(
                f"collecting {test_file} failed, so nothing here can be "
                "trusted about the deselection below. Fix the collection error "
                "first: this is not necessarily anything to do with "
                f"{node_id}."
            )
        collected = [line.strip() for line in done.stdout.splitlines()
                     if "::" in line]
        if node_id not in collected:
            raise SystemExit(
                f"{node_id} is not among the {len(collected)} tests collected "
                f"from {test_file}, so the --deselect below would be accepted "
                "and ignored. Either the test was renamed, in which case "
                "update DESELECTED_UNDER_COVERAGE, or it was deleted, in which "
                "case remove the entry."
            )
        # The predicate pytest itself applies, asked here so that the answer is
        # known before the suite runs rather than inferred from a count after.
        also_removed = [name for name in collected
                        if name != node_id and name.startswith(node_id)]
        if also_removed:
            raise SystemExit(
                f"--deselect {node_id} would also remove {also_removed}, "
                "because pytest deselects by prefix while this guard was "
                "written about one test. Those tests would vanish from every "
                "instrumented run without appearing anywhere. Rename the new "
                "test so it does not extend the guarded id, or add it to "
                "DESELECTED_UNDER_COVERAGE deliberately."
            )


def check_combine_left_nothing_behind(work):
    """Data files that combine could not read, named by the fact that they are
    still there.

    `coverage combine` discards a file it cannot read, warns into whatever
    scrolled past, and exits 0: measured as `Combined 1 file, skipped 1, 1 file
    errored` with a zero return code. So the explicit combine does not by itself
    make a lost child visible, which was the reason for running it explicitly.

    The signal is structural rather than prose. Combine deletes every file it
    consumed, including the ones it skips as duplicate content, and keeps the
    ones that raised. Measured against a planted corrupt file beside two good
    ones: both good files gone, the corrupt one still on disk. So a leftover is
    a failure by construction, and asking after the fact also catches a child
    that flushed while combine was already running, which a check made before it
    cannot see.
    """
    leftovers = sorted(work.glob(".coverage.*"))
    if not leftovers:
        return

    from coverage import CoverageData

    reasons = []
    for path in leftovers:
        try:
            CoverageData(basename=str(path)).read()
        except Exception as exc:
            reasons.append(f"{path.name}: {exc}")
        else:
            reasons.append(f"{path.name}: left behind but readable now")
    raise SystemExit(
        "combine could not read the data these children wrote, and discarded "
        "it while still exiting 0: " + "; ".join(reasons)
        + ". A child killed mid-write leaves exactly this, and the measurement "
        "above is missing whatever it had recorded."
    )


def check_no_data_landed_in_the_checkout():
    """The packaging invariant, asked rather than argued.

    Pointing COVERAGE_FILE at an absolute tmpdir holds only for processes that
    inherit that variable and honour it. A child that rebuilds its environment
    from scratch, or a collector armed by an ambient startup variable whose
    configuration carries a relative data_file, writes into its own working
    directory instead, which for children of this suite is normally the project
    root.

    That failure is silent by the same mechanism as the two this script was
    written for. The suite stays green, and the sdist comparison fails later and
    somewhere else: tests/ is granted whole by MANIFEST.in and the check that
    the archive carries it compares by EQUALITY, so one stray file is a
    packaging failure with nothing connecting it back to a coverage run. Left in
    place rather than deleted, because a file this script did not write is
    evidence about which process ignored the setting.
    """
    # Matched by coverage's actual data-file spelling, `.coverage` itself or the
    # `.coverage.<host>.<pid>.<rand>` a parallel run writes. A `.coverage*` glob
    # would be the obvious form and would also match `.coveragerc`, which is a
    # configuration file rather than data and would make this fail on a tree
    # that is fine.
    strays = sorted(
        p for p in ROOT.rglob(".coverage*")
        if p.name == ".coverage" or p.name.startswith(".coverage.")
    )
    if strays:
        raise SystemExit(
            "coverage data was written inside the checkout, which the sdist "
            "check compares by equality and will fail on: "
            + ", ".join(str(p.relative_to(ROOT)) for p in strays)
            + ". Some process did not inherit COVERAGE_FILE. The files are left "
            "in place on purpose; delete them once you know which one wrote "
            "them."
        )


def measured_lines(data_file):
    """Every line the combined data records as executed, by resolved path.

    Files with no executed lines are present here rather than absent, so this
    cannot answer whether the run measured anything at all. Nothing below asks
    it to: the sentinel check answers that by naming lines.
    """
    # The top-level name, which coverage re-exports explicitly for exactly this
    # use. coverage.sqldata is where the class is defined and is not the name
    # to import: coverage's own __init__ reaches it through coverage.data.
    from coverage import CoverageData

    data = CoverageData(basename=str(data_file))
    data.read()
    return {
        Path(name).resolve(): set(data.lines(name) or ())
        for name in data.measured_files()
    }


def check_the_sentinels_were_measured(measured, sentinels):
    missing = []
    for module_name, function_name, path, line in sentinels:
        label = f"{module_name}.{function_name} ({path.relative_to(ROOT)}:{line})"
        hit = line in measured.get(path, ())
        say(f"  {'ok  ' if hit else 'MISS'} {label}")
        if not hit:
            missing.append(label)
    if missing:
        raise SystemExit(
            "these lines ran during the suite and were not measured: "
            + "; ".join(missing)
            + ". Both are executed only in child processes and both end in "
            "os._exit, so the usual cause is the [tool.coverage.run] patch "
            "list in pyproject.toml having lost `subprocess` or `_exit`."
        )


def main(argv):
    rcfile = resolve_rcfile(argv)
    check_the_tool_is_here()

    # Resolved before anything runs. A sentinel that no longer matches the code
    # is a one second failure here and a several minute one after the suite.
    sentinels = [(module_name, function_name,
                  *resolve_exit_line(module_name, function_name))
                 for module_name, function_name in EXIT_SENTINELS]

    # Checked before the directory exists rather than after, because a guard
    # that creates what it then refuses to use has planted the residue it was
    # written to prevent. Resolved because the comparison is about where the
    # files land: a TMPDIR symlinked into the checkout points outside it by
    # spelling and inside it in fact.
    tmp_root = Path(tempfile.gettempdir()).resolve()
    # Data files land outside the tree, and that is a packaging requirement
    # rather than tidiness. tests/ is granted whole by MANIFEST.in, and the
    # check that the sdist carries that directory exactly compares by EQUALITY,
    # so one stray .coverage.* written into the tree between a build and that
    # comparison is a packaging failure.
    if tmp_root.is_relative_to(ROOT):
        raise SystemExit(
            f"TMPDIR resolves to {tmp_root}, inside {ROOT}: point it elsewhere"
        )
    work = Path(tempfile.mkdtemp(prefix="pyteman-coverage-")).resolve()
    data_file = work / ".coverage"
    say(f"coverage data in {work}")
    say(f"configuration from {rcfile}")

    check_the_deselections_still_resolve(data_file)

    deselect = [arg for node_id in DESELECTED_UNDER_COVERAGE for arg in ("--deselect", node_id)]
    say("running the suite under coverage")
    run([sys.executable, "-m", "coverage", "run", f"--rcfile={rcfile}",
         "-m", "pytest", "-q", "-rs", *deselect], data_file)

    # Explicit, and never left to a report that would combine implicitly: with
    # parallel = true every process writes its own file, and a report that
    # silently combined them would hide a child that wrote nothing at all. The
    # check after it is what turns a lost child into a failure rather than a
    # warning in the scrollback.
    say("\ncombining")
    run([sys.executable, "-m", "coverage", "combine", f"--rcfile={rcfile}"], data_file)
    check_combine_left_nothing_behind(work)
    check_no_data_landed_in_the_checkout()

    # Read here rather than after the report, because `coverage report` is not
    # the read-only step it looks like. Its command path runs load() followed by
    # combine(strict=False, keep=False) and, unlike the explicit combine action,
    # never saves; combine deletes every file it consumes. So a grandchild that
    # outlived the suite and flushed after the check above would be absorbed
    # into the printed percentage, deleted from disk, and absent from a later
    # reopen. If it carried a sentinel, the failure would blame the patch list
    # and the file that disproved that has already been removed.
    measured = measured_lines(data_file)
    run([sys.executable, "-m", "coverage", "report", f"--rcfile={rcfile}"], data_file)

    # No threshold anywhere above. This is the acceptance criterion instead.
    say("\nlines that only a child process can execute:")
    check_the_sentinels_were_measured(measured, sentinels)

    shutil.rmtree(work)
    say("\nThe suite ran instrumented and both child-only exits were measured.")


if __name__ == "__main__":
    main(sys.argv[1:])
