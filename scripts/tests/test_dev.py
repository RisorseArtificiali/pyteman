"""The dispatcher's own tests.

    uv run --locked python scripts/dev.py test scripts/tests

Not under tests/. That directory is the package's suite, it ships in the source
distribution, and these are about a development command that does not. Running
them is one argument to the command they test, which is the whole reason `test`
forwards paths.

What these check is the dispatch: which argv is built, in which directory, with
which environment, and what happens to a child's exit status. They do not
re-check that ruff lints or that pytest collects, because those tools have their
own suites and asserting their behavior here would only pin this file to their
current output.

Every refusal below is asserted against the SENTENCE it produces, not merely
against SystemExit. A test that accepts any exception passes when the command
dies for an unrelated reason, which is exactly how a guard rots into a no-op
while its test stays green.
"""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
DEV = ROOT / "scripts" / "dev.py"

# Resolved, and spelled once because it was spelled unresolved in three places.
# dev.verify_import_identity compares a resolved probe answer against a resolved
# expectation, so an unresolved stand-in for either is faithful only on a tree
# where the two coincide. Measured on a symlinked checkout, installed editable
# for real rather than put on PYTHONPATH: unresolved fails
# test_the_expected_checkout_is_accepted, test_a_foreign_pyteman_is_refused_by_
# name and test_the_probe_matches_the_pytest_call against a correct dev.py, the
# last being the one test here that measures production code rather than a
# substitute for it.
INSTALLED_PACKAGE = (ROOT / "src" / "pyteman").resolve()


def load_dev():
    """The module under test, imported by path.

    scripts/ is not a package and not importable by name, and adding an
    __init__.py to make it one would change what the source distribution
    carries. Loading by path keeps that question out of this file.
    """
    spec = importlib.util.spec_from_file_location("dev_under_test", DEV)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {DEV}: it is missing or unreadable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dev = load_dev()


def executable(path):
    """A file tool() will accept: present, a file, and runnable.

    Spelled once because a plain touch() no longer satisfies the lookup, and a
    control that quietly stops being a control is the failure this file is
    written to avoid.
    """
    path.touch()
    path.chmod(0o755)
    return path


def ruff_would_check(*paths):
    """The set of files the installed ruff says it would lint, repo-relative.

    Asked of ruff rather than reasoned about, because the answer depends on
    pyproject.toml's extend-exclude, on ruff's own defaults and on its version,
    none of which this file should be restating. `--show-files` lists them and
    lints nothing, so the answer does not depend on whether the tree is clean.

    ruff is located here rather than through dev.BIN on purpose. Reaching
    through the module under test coupled these scope tests to the tool-lookup
    code: measured, mutating BIN to resolve through the interpreter symlink
    failed all six of them alongside the one test that actually names the
    problem, burying it.
    """
    done = subprocess.run(
        [str(RUFF), "check", "--show-files", *paths],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if done.returncode != 0:
        raise AssertionError(f"ruff --show-files failed: {done.stderr.strip()}")
    return {
        Path(line).relative_to(ROOT)
        for line in (raw.strip() for raw in done.stdout.splitlines())
        if line
    }


RUFF = Path(sys.executable).parent / "ruff"
# The same predicate tool() applies, not merely is_file(). They differ in exactly
# the state test_a_non_executable_file_is_refused_like_a_missing_one dramatizes:
# an interrupted `uv sync` leaves the file with its bits unset, is_file() is then
# True so these tests would run rather than skip, and ruff_would_check raises a
# raw PermissionError traceback out of subprocess during precisely the
# half-installed environment this suite should be diagnosing clearly.
needs_ruff = pytest.mark.skipif(
    not (RUFF.is_file() and os.access(RUFF, os.X_OK)),
    reason="no usable ruff in this interpreter's environment: run `uv sync --locked`",
)


class Recorder:
    """Stands in for subprocess.run, remembering every call and returning the
    exit statuses it was given, in order. The last status repeats once the list
    is exhausted, so Recorder(0) answers every call.

    stdout defaults to this checkout's package path so that the real
    verify_import_identity is satisfied by it. That lets a test exercise
    production code rather than a substitute for it.
    """

    def __init__(self, *codes, stdout=None, stderr=""):
        self.codes = list(codes) or [0]
        self.calls = []
        self.stdout = str(INSTALLED_PACKAGE) + "\n" if stdout is None else stdout
        self.stderr = stderr

    def __call__(self, argv, cwd=None, env=None, **kwargs):
        self.calls.append(
            {
                "argv": [str(part) for part in argv],
                "cwd": cwd,
                "env": env,
                "kwargs": kwargs,
            }
        )
        code = self.codes.pop(0) if len(self.codes) > 1 else self.codes[0]
        return subprocess.CompletedProcess(
            argv, code, stdout=self.stdout, stderr=self.stderr
        )


@pytest.fixture
def recorder(monkeypatch):
    """A Recorder installed over subprocess.run, which eleven tests below did
    verbatim. Tests needing a non-zero status build their own."""
    installed = Recorder(0)
    monkeypatch.setattr(dev.subprocess, "run", installed)
    return installed


@pytest.fixture
def stubbed_tools(monkeypatch):
    """Locations for the tools the commands invoke, so their tests assert on
    the argv built rather than on whether this machine has basedpyright.

    The spellings are here only, and this fixture is the sole way to install
    them: a test spelling `/fake/bin/...` for itself is a second copy that can
    drift from the assertion it is supposed to match.

    Returns the list of names tool() was asked for, so the test about lookup
    shares this stub instead of building its own.
    """
    sought = []
    monkeypatch.setattr(dev, "uv", lambda: "/fake/uv")
    monkeypatch.setattr(
        dev, "tool", lambda name: sought.append(name) or f"/fake/bin/{name}"
    )
    return sought


@pytest.fixture
def no_identity_check(monkeypatch):
    """Silences the import-origin probe for the tests that are about argument
    forwarding rather than about identity.

    The probe has its own tests below. Leaving it live in these would make every
    one of them depend on the project environment being installed, which is
    precisely the coupling the split avoids.
    """
    monkeypatch.setattr(dev, "verify_import_identity", lambda env: None)


@pytest.fixture
def in_project_env(monkeypatch):
    """Satisfies require_project_environment without needing a real venv."""
    monkeypatch.setattr(sys, "base_prefix", sys.prefix + "-not-this")


# --- argv construction and forwarding ---------------------------------------


@pytest.mark.parametrize(
    "rest, tail",
    [
        ([], []),
        (["-x"], ["-x"]),
        (["-k", "binding"], ["-k", "binding"]),
        (["tests/test_rules.py::test_one"], ["tests/test_rules.py::test_one"]),
        (
            ["--collect-only", "-q", "scripts/tests"],
            ["--collect-only", "-q", "scripts/tests"],
        ),
    ],
)
def test_test_forwards_arguments_after_its_own(
    in_project_env, no_identity_check, recorder, rest, tail
):
    """Whatever follows `test` reaches pytest unchanged, and always after -q -rs
    so a forwarded flag can override them."""
    assert dev.test(rest) == 0
    assert recorder.calls[0]["argv"] == [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-rs",
        *tail,
    ]


def test_flags_survive_the_command_line(in_project_env, no_identity_check, recorder):
    """The parser, not just the function: a leading flag after the command is
    the case argparse gets wrong inside a subparser, and this is the test that
    would catch a regression to that shape."""
    assert dev.main(["test", "-x", "--lf"]) == 0
    assert recorder.calls[0]["argv"][-2:] == ["-x", "--lf"]


def test_check_runs_the_four_tools_in_order(in_project_env, stubbed_tools, recorder):
    assert dev.check([]) == 0
    assert [call["argv"] for call in recorder.calls] == [
        ["/fake/uv", "lock", "--check"],
        ["/fake/bin/ruff", "check", "."],
        ["/fake/bin/basedpyright", "--baselinemode=lock"],
        ["/fake/bin/validate-pyproject", "pyproject.toml"],
    ]


# Spelled out here rather than read from dev.LINT_SCOPE, for the reason
# MUST_BE_CLEARED is: asserting that the scope under test appears in the command
# built from that same value is true of any value, including a narrower one, so
# narrowing it would delete its own test.
MUST_BE_LINTED = ("src", "tests", "scripts", "examples")


@needs_ruff
@pytest.mark.parametrize("directory", MUST_BE_LINTED)
def test_the_lint_scope_reaches_every_source_directory(directory):
    """Asked of the real ruff, because the question is about coverage.

    examples/ is the one that was missing while the scope was a hand-written
    list of directories: it sits inside the ruff configuration's own scope, so
    leaving it out made `check` report success on a tree that a bare
    `ruff check` rejects. Measured then: an undefined name appended to
    examples/hermes-109966/holder.py passed `ruff check src tests scripts` and
    failed `ruff check`.

    A list could not cover a root-level module at all, having no directory to
    name, which is why the scope is now the tree and the authority is
    pyproject.toml's extend-exclude rather than a second copy of it here.
    """
    listed = ruff_would_check(dev.LINT_SCOPE)
    assert any(path.parts[0] == directory for path in listed), (
        f"{directory} is outside the lint scope {dev.LINT_SCOPE!r}"
    )


@needs_ruff
def test_the_lint_scope_is_not_narrower_than_ruffs_own():
    """The invariant behind the parametrized test above, stated once.

    Whatever ruff would check when asked about this project, `check` must ask
    about too. Anything less makes the command quieter than the formatter it
    wraps, which is how the examples/ gap survived unnoticed.
    """
    assert ruff_would_check() <= ruff_would_check(dev.LINT_SCOPE)


@needs_ruff
def test_an_excluded_directory_is_still_excluded():
    """The control. A scope that had somehow become 'everything on disk' would
    satisfy both tests above and start linting .venv and build output."""
    listed = ruff_would_check(dev.LINT_SCOPE)
    excluded = {".venv", "build", "dist", "backlog", ".claude"}
    assert not [path for path in listed if path.parts[0] in excluded]


def test_every_tool_check_runs_is_looked_up_in_the_environment(
    in_project_env, recorder, stubbed_tools
):
    """Ruff went through `python -m ruff` while the other two went through
    tool(), which meant a missing ruff produced a bare `No module named ruff`
    rather than the sentence tool() exists to produce. This asserts the four
    share one lookup: uv from PATH, the rest from BIN.
    """
    dev.check([])
    assert stubbed_tools == ["ruff", "basedpyright", "validate-pyproject"]


def test_check_refuses_arguments_rather_than_dropping_them(in_project_env, recorder):
    """check forwards nothing, so an argument silently discarded would let
    `dev.py check -k something` look like it had narrowed the run."""
    with pytest.raises(SystemExit) as caught:
        dev.check(["-k", "binding"])
    assert "check takes no arguments" in str(caught.value)
    assert recorder.calls == []


def test_format_check_defaults_to_the_lint_scope(
    in_project_env, recorder, stubbed_tools
):
    """The same scope check lints, so the two never disagree about what the
    project's source is."""
    assert dev.format_check([]) == 0
    assert recorder.calls[0]["argv"] == [
        "/fake/bin/ruff",
        "format",
        "--check",
        dev.LINT_SCOPE,
    ]


def test_format_check_takes_the_paths_it_is_given(
    in_project_env, recorder, stubbed_tools
):
    assert dev.format_check(["scripts/dev.py"]) == 0
    assert recorder.calls[0]["argv"][-1:] == ["scripts/dev.py"]


def test_format_check_gets_the_cleaned_environment_too(
    monkeypatch, in_project_env, recorder, stubbed_tools
):
    """The third command, asserted separately from the other two.

    It was the one that inherited the ambient environment, and it did so
    silently because run() had an env default: passing nothing read as a
    decision rather than the oversight it was. The parameter is now required,
    and this is the test that says so at the level of what the child receives.
    """
    monkeypatch.setenv("PYTHONWARNINGS", "error")
    monkeypatch.setenv("PYTEMAN_RULES", "/tmp/rules.yaml")
    assert dev.format_check([]) == 0
    env = recorder.calls[0]["env"]
    assert "PYTHONWARNINGS" not in env and "PYTEMAN_RULES" not in env
    assert env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"


def test_no_command_runs_through_a_shell(in_project_env, no_identity_check, recorder):
    """shell=True would reinterpret a path containing a space or a glob."""
    dev.test(["-k", "a or b"])
    assert recorder.calls[0]["kwargs"].get("shell") in (None, False)


# --- working directory ------------------------------------------------------


def test_children_run_in_the_repository_root(
    in_project_env, no_identity_check, recorder
):
    """pytest's rootdir, the coverage source path and every relative argument a
    caller passes are all resolved against this, so it is pinned rather than
    inherited from wherever the operator happened to be standing."""
    dev.test([])
    assert recorder.calls[0]["cwd"] == ROOT


# --- exit status propagation ------------------------------------------------


@pytest.mark.parametrize("code", [1, 2, 5, 130])
def test_a_childs_exit_status_is_returned_unchanged(
    monkeypatch, in_project_env, no_identity_check, code
):
    """pytest's statuses are distinct and meaningful: 1 is a failure, 2 an
    interruption, 5 an empty collection. Collapsing them to 1 would lose the
    difference between a failing suite and one that ran nothing."""
    monkeypatch.setattr(dev.subprocess, "run", Recorder(code))
    assert dev.test([]) == code


def test_check_stops_at_the_first_failure(monkeypatch, in_project_env, stubbed_tools):
    """A stale lock makes every later answer describe the wrong environment, so
    the later steps must not run at all."""
    recorder = Recorder(3, 0, 0, 0)
    monkeypatch.setattr(dev.subprocess, "run", recorder)
    assert dev.check([]) == 3
    assert len(recorder.calls) == 1
    assert recorder.calls[0]["argv"][1:] == ["lock", "--check"]


def test_check_reports_a_late_failure_too(monkeypatch, in_project_env, stubbed_tools):
    """The mirror of the test above: with the first three green the fourth still
    decides the result. Without this, a `return 0` written before the loop would
    pass the test above and be wrong."""
    recorder = Recorder(0, 0, 0, 7)
    monkeypatch.setattr(dev.subprocess, "run", recorder)
    assert dev.check([]) == 7
    assert len(recorder.calls) == 4


@pytest.mark.parametrize(
    "returncode, reported", [(-9, 137), (-15, 143), (-2, 130), (-6, 134)]
)
def test_a_signal_death_is_reported_the_way_a_shell_reports_it(
    monkeypatch, in_project_env, no_identity_check, returncode, reported
):
    """subprocess reports a signal as a negative number, and sys.exit takes the
    low byte of it.

    Measured: a pytest killed by SIGKILL returns -9, and the shell that ran the
    command then sees 247, which names no signal and collides with nothing
    recognisable. 128+signal is what every shell already prints, so an
    OOM-killed suite says 137.
    """
    monkeypatch.setattr(dev.subprocess, "run", Recorder(returncode))
    assert dev.test([]) == reported


def test_an_ordinary_failure_is_not_shifted(
    monkeypatch, in_project_env, no_identity_check
):
    """The control for the test above. A translation applied unconditionally
    would turn pytest's 1 into 127 and pass a test that only checked signals."""
    monkeypatch.setattr(dev.subprocess, "run", Recorder(1))
    assert dev.test([]) == 1


# --- missing tools ----------------------------------------------------------


def test_a_missing_tool_names_itself_and_where_it_was_sought(monkeypatch, tmp_path):
    monkeypatch.setattr(dev, "BIN", tmp_path)
    with pytest.raises(SystemExit) as caught:
        dev.tool("basedpyright")
    message = str(caught.value)
    assert "basedpyright" in message and str(tmp_path) in message
    assert "uv sync --locked" in message


def test_a_present_tool_resolves_to_the_project_environment(monkeypatch, tmp_path):
    """The control for the test above. Without it, a `tool` that raised
    unconditionally would pass every refusal test in this file."""
    monkeypatch.setattr(dev, "BIN", tmp_path)
    executable(tmp_path / "basedpyright")
    assert dev.tool("basedpyright") == tmp_path / "basedpyright"


def test_a_non_executable_file_is_refused_like_a_missing_one(monkeypatch, tmp_path):
    """An interrupted `uv sync` leaves the file with its bits unset.

    exists() is satisfied by it, and the command then dies inside
    subprocess.run with a raw PermissionError traceback instead of the sentence
    naming the environment. Paired with the control above, which uses the same
    path with the bits set, so only the executable test can tell them apart.
    """
    monkeypatch.setattr(dev, "BIN", tmp_path)
    (tmp_path / "basedpyright").touch()
    (tmp_path / "basedpyright").chmod(0o644)
    with pytest.raises(SystemExit) as caught:
        dev.tool("basedpyright")
    assert str(tmp_path) in str(caught.value)


def test_a_directory_is_not_mistaken_for_a_tool(monkeypatch, tmp_path):
    """The other way exists() says yes about something unrunnable."""
    monkeypatch.setattr(dev, "BIN", tmp_path)
    (tmp_path / "basedpyright").mkdir()
    with pytest.raises(SystemExit) as caught:
        dev.tool("basedpyright")
    assert str(tmp_path) in str(caught.value)


def test_tools_are_not_taken_from_the_ambient_path(monkeypatch, tmp_path):
    """A tool present on PATH but absent from BIN is still a failure.

    Both directories are constructed, because the interesting case needs BIN
    empty AND PATH populated at once: leaving BIN as the real environment would
    let the tool resolve there and prove nothing about PATH.
    """
    empty_bin, on_path = tmp_path / "bin", tmp_path / "elsewhere"
    empty_bin.mkdir()
    on_path.mkdir()
    executable(on_path / "basedpyright")
    monkeypatch.setattr(dev, "BIN", empty_bin)
    monkeypatch.setenv("PATH", str(on_path))
    with pytest.raises(SystemExit) as caught:
        dev.tool("basedpyright")
    assert str(empty_bin) in str(caught.value)


def test_bin_stays_inside_the_project_environment():
    """The invariant, asserted rather than restated.

    An earlier version of this test read `dev.BIN == Path(sys.executable).parent`,
    which is the source line copied into the test file: it holds for any
    definition of BIN written that way, including a wrong one. What actually
    matters is that BIN is inside the environment whose tools are meant to
    answer.
    """
    assert dev.BIN.is_relative_to(sys.prefix)


@pytest.mark.skipif(
    not Path(sys.executable).is_symlink(),
    reason="interpreter is a real file, so resolving it cannot escape the venv",
)
def test_resolving_the_interpreter_would_leave_the_environment():
    """What makes the test above discriminating, on the venv layout this
    checkout has.

    Measured here: .venv/bin/python is a symlink to /usr/bin/python3.14, so
    Path(sys.executable).resolve().parent is /usr/bin. Had BIN been built from
    the resolved path, every tool lookup would have found the ambient system
    copy while the command still looked like it had run the pinned one. Skipped
    rather than asserted on a --copies environment, where resolving is harmless
    and this would fail against a correct implementation.
    """
    assert not Path(sys.executable).resolve().parent.is_relative_to(sys.prefix)


def test_missing_uv_says_what_uv_is_for(monkeypatch):
    monkeypatch.setattr(dev.shutil, "which", lambda name: None)
    with pytest.raises(SystemExit) as caught:
        dev.uv()
    assert "uv is not on PATH" in str(caught.value)


def test_uv_is_found_on_path_rather_than_in_bin(monkeypatch):
    """uv is the launcher, not a member of the environment it builds."""
    monkeypatch.setattr(dev.shutil, "which", lambda name: f"/elsewhere/{name}")
    assert dev.uv() == "/elsewhere/uv"


# --- the environment guard --------------------------------------------------


def test_a_base_interpreter_is_refused(monkeypatch):
    monkeypatch.setattr(sys, "base_prefix", sys.prefix)
    with pytest.raises(SystemExit) as caught:
        dev.require_project_environment()
    assert "base interpreter" in str(caught.value)


def test_a_virtual_environment_is_accepted(in_project_env):
    """The control. A guard that refused everything would satisfy the test
    above and break the command for everyone."""
    assert dev.require_project_environment() is None


@pytest.mark.parametrize("command", ["check", "test", "format-check"])
def test_every_command_guards_the_environment(monkeypatch, command):
    """The guard is on each command rather than on main, so this asks each one
    separately: a command added without it would be caught here."""
    monkeypatch.setattr(sys, "base_prefix", sys.prefix)
    monkeypatch.setattr(dev.subprocess, "run", Recorder(0))
    with pytest.raises(SystemExit) as caught:
        dev.COMMANDS[command]([])
    assert "base interpreter" in str(caught.value)


# --- environment cleaning ---------------------------------------------------


def test_ambient_pyteman_variables_are_cleared(monkeypatch):
    """By prefix, so a variable the runtime grows later is covered on the day it
    is added. Any of these reaching the suite would arm the package against the
    tests that check it is inert."""
    monkeypatch.setenv("PYTEMAN_RULES", "/tmp/rules.yaml")
    monkeypatch.setenv("PYTEMAN_LOG", "/tmp/pyteman.log")
    monkeypatch.setenv("PYTEMAN_REQUIRE_MARKER", "1")
    monkeypatch.setenv("PYTEMAN_SOMETHING_INVENTED_LATER", "1")
    env = dev.child_env()
    assert not [name for name in env if name.startswith("PYTEMAN_")]


# Named here rather than read from dev.CLEARED_IN_CHILD. Parametrizing over the
# tuple under test asks only "is each listed name cleared", which is true of any
# list including an empty one, so deleting an entry would delete its own test
# and the suite would stay green. Measured: dropping PYTHONPATH from the tuple
# survived a parametrized-from-source version of this test.
MUST_BE_CLEARED = (
    "PYTHONPATH",
    "PYTHONHOME",
    "PYTHONPYCACHEPREFIX",
    "PYTHONOPTIMIZE",
    "PYTHONINSPECT",
    "PYTHONSAFEPATH",
    "PYTHONWARNINGS",
    "PYTEST_ADDOPTS",
    "PYTEST_PLUGINS",
    # The four with the most argument behind them in dev.py, and the four this
    # list omitted longest. Measured both halves: deleting all four from
    # CLEARED_IN_CHILD left this suite at 72 passed, 2 skipped, while
    # COVERAGE_PROCESS_START exported into the package's own suite fails
    # tests/test_sitecustomize.py::test_inert_run_does_not_import_pyteman with
    # `+ ['typing']`. That export is routine after a scripts/run_coverage.py
    # session in the same shell.
    "COVERAGE_RCFILE",
    "COVERAGE_PROCESS_CONFIG",
    "COVERAGE_PROCESS_START",
    "COVERAGE_FORCE_CONFIG",
)


@pytest.mark.parametrize("name", MUST_BE_CLEARED)
def test_each_interpreter_override_is_cleared(monkeypatch, name):
    monkeypatch.setenv(name, "ambient")
    assert name not in dev.child_env()


def test_nothing_required_has_been_dropped_from_the_source_list(monkeypatch):
    """The two lists are allowed to diverge in one direction only.

    dev.CLEARED_IN_CHILD may grow past this file; it may not shrink below it
    without the removal being stated here and argued for.
    """
    assert set(MUST_BE_CLEARED) <= set(dev.CLEARED_IN_CHILD)


def test_unrelated_variables_survive(monkeypatch):
    """The control for the two tests above. An env built from scratch rather
    than filtered would pass both of them and break every child that needs HOME,
    PATH or a terminal."""
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("HOME", "/home/somebody")
    env = dev.child_env()
    assert env["PATH"] == "/usr/bin"
    assert env["HOME"] == "/home/somebody"


def test_plugin_autoload_is_disabled_and_bytecode_suppressed():
    env = dev.child_env()
    assert env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"


def test_the_cleaned_environment_is_what_pytest_receives(
    monkeypatch, in_project_env, no_identity_check
):
    """The cleaning is only worth anything if it reaches the child. Without
    this, child_env could be correct and unused."""
    monkeypatch.setenv("PYTEMAN_RULES", "/tmp/rules.yaml")
    monkeypatch.setenv("PYTEST_ADDOPTS", "--deselect tests/test_rules.py")
    recorder = Recorder(0)
    monkeypatch.setattr(dev.subprocess, "run", recorder)
    dev.test([])
    env = recorder.calls[0]["env"]
    assert "PYTEMAN_RULES" not in env and "PYTEST_ADDOPTS" not in env
    assert env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"


def test_check_children_get_the_cleaned_environment_too(
    monkeypatch, in_project_env, stubbed_tools, recorder
):
    """`check` and `test` are peers in the module docstring, so they must be
    peers here.

    Measured with the inherited environment: an ambient PYTHONWARNINGS=error
    made validate-pyproject exit 1 on a PendingDeprecationWarning raised inside
    argparse, so `check` reported this project's metadata invalid while nothing
    was wrong with it. Asserted over every step rather than the first, because
    the variable that broke it was read by the last one.
    """
    monkeypatch.setenv("PYTHONWARNINGS", "error")
    monkeypatch.setenv("PYTEMAN_RULES", "/tmp/rules.yaml")
    assert dev.check([]) == 0
    assert len(recorder.calls) == 4
    for call in recorder.calls:
        assert call["env"] is not None
        assert "PYTHONWARNINGS" not in call["env"]
        assert "PYTEMAN_RULES" not in call["env"]
        assert call["env"]["PATH"] == os.environ["PATH"]


def test_this_process_environment_is_not_mutated(monkeypatch):
    """The cleaning builds a copy. Mutating os.environ would change the
    interpreter running this script and everything it later spawns."""
    monkeypatch.setenv("PYTEMAN_RULES", "/tmp/rules.yaml")
    dev.child_env()
    assert os.environ["PYTEMAN_RULES"] == "/tmp/rules.yaml"


# --- import identity --------------------------------------------------------


def fake_probe(monkeypatch, stdout="", stderr="", code=0):
    """A Recorder whose answer the probe will read. Separate from the `recorder`
    fixture only because these tests need a specific stdout or a failure."""
    monkeypatch.setattr(
        dev.subprocess, "run", Recorder(code, stdout=stdout, stderr=stderr)
    )


def test_the_expected_checkout_is_accepted(monkeypatch):
    """The control that makes the two refusals below mean something."""
    fake_probe(monkeypatch, stdout=str(INSTALLED_PACKAGE) + "\n")
    assert dev.verify_import_identity({}) is None


def test_a_foreign_pyteman_is_refused_by_name(monkeypatch):
    """The failure this guard exists for: an ambient non-editable install earlier
    on sys.path runs the entire suite against code that is not the code being
    edited, and passes."""
    fake_probe(monkeypatch, stdout="/usr/lib/python3.14/site-packages/pyteman\n")
    with pytest.raises(SystemExit) as caught:
        dev.verify_import_identity({})
    message = str(caught.value)
    assert "/usr/lib/python3.14/site-packages/pyteman" in message
    assert str(INSTALLED_PACKAGE) in message


def test_an_uninstalled_package_is_reported_as_such(monkeypatch):
    """A different sentence from the one above, because it is a different
    problem with a different fix, and a guard that said 'wrong copy' when there
    was no copy would send the operator looking for one."""
    fake_probe(
        monkeypatch, stderr="ModuleNotFoundError: No module named 'pyteman'", code=1
    )
    with pytest.raises(SystemExit) as caught:
        dev.verify_import_identity({})
    message = str(caught.value)
    assert "cannot import pyteman" in message
    assert "ModuleNotFoundError" in message


def test_a_symlinked_checkout_is_still_this_checkout(monkeypatch, tmp_path):
    """Both sides of the comparison are resolved, so a symlink is not a mismatch.

    The probe prints a resolved path, because that is the only form that
    identifies a directory uniquely. Comparing it against an unresolved
    expectation refuses a perfectly correct editable install whenever src/ or
    src/pyteman/ is a link, and then advises `uv sync --locked`, which cannot
    fix it: the reinstall reproduces the same layout and the same refusal.
    """
    real = tmp_path / "elsewhere" / "pyteman"
    real.mkdir(parents=True)
    checkout = tmp_path / "checkout"
    (checkout / "src").mkdir(parents=True)
    (checkout / "src" / "pyteman").symlink_to(real, target_is_directory=True)
    monkeypatch.setattr(dev, "ROOT", checkout)
    fake_probe(monkeypatch, stdout=str(real) + "\n")
    assert dev.verify_import_identity({}) is None


def test_a_foreign_path_is_still_refused_under_the_same_layout(monkeypatch, tmp_path):
    """The control for the test above. Resolving both sides must not degrade
    into accepting anything: the same symlinked checkout, a different answer
    from the probe, and the refusal still fires."""
    real = tmp_path / "elsewhere" / "pyteman"
    real.mkdir(parents=True)
    checkout = tmp_path / "checkout"
    (checkout / "src").mkdir(parents=True)
    (checkout / "src" / "pyteman").symlink_to(real, target_is_directory=True)
    monkeypatch.setattr(dev, "ROOT", checkout)
    fake_probe(monkeypatch, stdout="/usr/lib/python3.14/site-packages/pyteman\n")
    with pytest.raises(SystemExit) as caught:
        dev.verify_import_identity({})
    assert "/usr/lib/python3.14/site-packages/pyteman" in str(caught.value)


def test_the_probe_matches_the_pytest_call(in_project_env, recorder):
    """Same interpreter, same working directory, same environment. Any of the
    three differing would make the probe answer a question about a process that
    is not the one being guarded.

    The real verify_import_identity runs here; only subprocess.run is replaced,
    so what is asserted is the call production code makes. An earlier version
    substituted a reimplementation of the probe and then checked that, which
    measured the test's own copy: dropped into it, a probe given the wrong cwd
    and a probe given an uncleaned environment both passed.
    """
    dev.test([])
    probe, pytest_call = recorder.calls
    assert probe["argv"] == [sys.executable, "-c", dev.IDENTITY_PROBE]
    assert probe["argv"][0] == pytest_call["argv"][0] == sys.executable
    assert probe["cwd"] == pytest_call["cwd"] == ROOT
    assert probe["env"] == pytest_call["env"]
    assert "PYTEST_DISABLE_PLUGIN_AUTOLOAD" in probe["env"]


def test_identity_is_verified_before_pytest_starts(monkeypatch, in_project_env):
    """Order, not just presence: verifying afterwards would report the mismatch
    only once the wrong suite had already run and passed."""
    order = []
    monkeypatch.setattr(
        dev, "verify_import_identity", lambda env: order.append("probe")
    )
    monkeypatch.setattr(
        dev.subprocess,
        "run",
        lambda *a, **k: order.append("pytest") or subprocess.CompletedProcess(a[0], 0),
    )
    dev.test([])
    assert order == ["probe", "pytest"]


# --- the command line itself ------------------------------------------------


@pytest.mark.parametrize("argv", [[], ["bogus"], ["--nonsense"]])
def test_an_unusable_command_line_exits_two(argv):
    """argparse's own status for a usage error, kept distinct from a tool's
    failure so a caller can tell 'you typed it wrong' from 'it found a bug'."""
    with pytest.raises(SystemExit) as caught:
        dev.main(argv)
    assert caught.value.code == 2


def test_every_advertised_command_is_accepted_by_the_parser(monkeypatch):
    """The parser's choices come from COMMANDS, so this checks the other
    direction: that each key actually dispatches rather than merely parsing."""
    called = []
    for name in dev.COMMANDS:
        monkeypatch.setitem(
            dev.COMMANDS, name, lambda rest, name=name: called.append(name) or 0
        )
    for name in list(dev.COMMANDS):
        assert dev.main([name]) == 0
    assert sorted(called) == sorted(dev.COMMANDS)


# --- against the real environment -------------------------------------------


def this_checkout_is_the_installed_one():
    """Whether `import pyteman` here resolves to the tree these tests live in.

    That, and not the presence of a .venv, is what the two end-to-end tests
    below actually require: they run dev.py out of ROOT, and dev.py refuses to
    run a suite against a checkout other than the installed one.

    Both cheaper predicates get it wrong somewhere. A literal `.venv` check
    skips under UV_PROJECT_ENVIRONMENT, where the environment is real and
    elsewhere. A sys.prefix check passes inside a copy of this file planted in
    a temporary tree, where the tests then fail for a reason that has nothing
    to do with the dispatcher. find_spec answers the real question and, unlike
    the probe it mirrors, leaves pyteman out of sys.modules.

    Both sides resolved, for the reason verify_import_identity gives: on a
    checkout where src/pyteman is a symlink, the layout
    test_a_symlinked_checkout_is_still_this_checkout declares supported,
    resolving only the left side compares a link target against a link path and
    answers False. That would skip the only two tests in this file that run the
    real dispatcher, under a reason telling the operator to `uv sync --locked`,
    which cannot fix it.
    """
    found = importlib.util.find_spec("pyteman")
    if found is None or found.origin is None:
        return False
    return Path(found.origin).resolve().parent == (ROOT / "src" / "pyteman").resolve()


needs_this_checkout_installed = pytest.mark.skipif(
    not this_checkout_is_the_installed_one(),
    reason="this tree is not the installed pyteman: run `uv sync --locked`",
)


@needs_this_checkout_installed
def test_the_real_dispatcher_forwards_to_a_real_pytest():
    """One end-to-end run through the actual entry point, because everything
    above replaces subprocess.run and so proves nothing about whether the real
    command works.

    --collect-only keeps it fast and keeps it from recursing into itself.
    """
    done = subprocess.run(
        [
            sys.executable,
            str(DEV),
            "test",
            "--collect-only",
            "-q",
            "scripts/tests/test_dev.py",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert "test_dev.py" in done.stdout


@needs_this_checkout_installed
def test_the_real_identity_probe_finds_this_checkout():
    """The probe against the installed environment rather than a fake, which is
    the only form that would notice a broken editable install."""
    assert dev.verify_import_identity(dev.child_env()) is None
