#!/usr/bin/env python3
"""Build both artifacts and exercise each one from an environment that has no
other route to this package.

    python scripts/verify_artifacts.py

TASK-34 / PKG-03, criterion 2. The reasoning behind the recipe this automates,
and the failure modes it exists to catch, are in docs/packaging.md. What follows
is only what a reader of this file needs.

Why a script rather than steps in the workflow. Every command here needs a path
computed from a previous command's output, and several need a multi-line Python
snippet. Expressed as shell inside YAML that becomes three levels of quoting
around code nobody can run locally to check. This runs the same way on a laptop
and on a runner, which is the property that matters: a CI-only check is one
nobody debugs until it is already red.

Why the environments are built with --system-site-packages. Installing an sdist
calls the backend's metadata hook even under --no-build-isolation, so setuptools
has to be importable in the installing environment. The base interpreter
supplies it, along with pytest and PyYAML, and this script refuses to run if it
does not. What the base must NOT supply is pyteman itself, which is checked
rather than assumed: an ambient copy would make every check below pass while
measuring nothing.
"""

import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Mirrors the fixture in tests/test_packaging.py, and for the same reason: an
# existing *.egg-info is not clutter, it is a cache that setuptools READS and
# unions into the archive, so building over a stale one measures an earlier
# manifest rather than the one on disk now.
NOT_COPIED = (".git", "*.egg-info", "build", "dist", ".venv")

# The base interpreter has to carry these because the artifacts are installed
# with --no-deps: the point is to measure what the archive contains, not what an
# index happens to resolve today, and reaching the network would make the answer
# depend on the weather. pip is here because the environments below are built
# --without-pip and borrow this one, which costs about three seconds a venv.
REQUIRED_IN_BASE = ("pip", "setuptools", "pytest", "yaml")

# What the LAUNCHER needs, which is a shorter list and a different question.
# This interpreter runs the build backend itself, in build_both_artifacts, so it
# needs setuptools in its own right. It needs nothing else: pip, pytest and
# PyYAML are used only inside the environments built below, which inherit them
# from the base rather than from here.
REQUIRED_IN_LAUNCHER = ("setuptools",)

# The clean room, extended to pytest. These environments are built
# --system-site-packages, so every plugin registered by an entry point in the
# base interpreter is visible to pytest inside them, and a measurement that
# varies with what the operator happens to have installed is not a measurement.
# One such plugin on this development machine injects an autouse fixture into
# every test, which is the case that prompted this, not the reason for it.
#
# The cost of the setting is worth naming: the day this project takes a pytest
# plugin as a real dependency, that plugin stops loading here and the failure
# will have nothing to do with packaging.
CHILD_ENV = {"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTHONDONTWRITEBYTECODE": "1"}

# Removed from every child rather than merely left unset here. The suite spawns
# its own subprocesses and several of them rebuild an environment from
# os.environ, so an exported rules file reaches the tests whatever this script
# does with its own. Measured with PYTEMAN_RULES pointing at a missing file:
# 72 failed, 641 passed, and nothing in the output names the variable.
CLEARED_IN_CHILD = ("PYTEMAN_RULES", "PYTEMAN_LOG", "PYTEMAN_REQUIRE_MARKER")


def say(message):
    """Progress, flushed.

    Children write straight to the terminal while this script's own stdout is
    block-buffered whenever it is piped, which is always in CI. Unflushed, the
    labels arrive after the output they label, and a log that says which
    artifact failed underneath the failure is a log nobody can read.
    """
    print(message, flush=True)


def run(argv, cwd=None, extra_env=None, capture=False):
    """A child process, with the failure reported where it happened."""
    env = {**os.environ, **CHILD_ENV, **(extra_env or {})}
    for name in CLEARED_IN_CHILD:
        env.pop(name, None)
    done = subprocess.run(
        argv, cwd=cwd, env=env, text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )
    if done.returncode != 0:
        if capture:
            say(done.stdout)
        raise SystemExit(f"FAILED ({done.returncode}): {' '.join(map(str, argv))}")
    return (done.stdout or "").strip()


def echoed_values(output, *names):
    """Values read by name from marker lines, never by position.

    Positional reading is wrong three times over here. Subprocesses print their
    own logs around the answer; ``capture`` folds stderr into stdout, and under
    --system-site-packages every .pth in the base runs at startup and some of
    them write there; and an empty value at the front is eaten by the strip in
    ``run``, which silently shifts every later value up one slot.

    A name that never appeared comes back empty rather than raising, so each
    caller decides what an absent marker means to it. None of them may ignore it.
    """
    found = {
        name: value
        for name, sep, value in (line.partition("=") for line in output.splitlines())
        if sep and name in names
    }
    return [found.get(name, "") for name in names]


def check_the_base_is_a_clean_room():
    """Both halves of the precondition, because both are silent when wrong.

    A missing setuptools fails later with BackendUnavailable, or with a bare
    ModuleNotFoundError from the build, and neither names packaging nor this
    project. An environment that already has pyteman fails in the worse
    direction: nothing fails at all, and every check below passes against a
    copy that did not come out of the artifact under test.

    TWO interpreters are checked because this script uses two, and whenever it
    is launched from a virtual environment they are not the same one.
    build_both_artifacts runs the backend under sys.executable, which is the
    launcher. Every environment built here is made with --system-site-packages,
    which inherits from sys.base_prefix and therefore does NOT see what pip put
    into a launching venv. Both directions were measured, each by running the
    script with one interpreter equipped and the other not, and each produced
    exactly the unattributable failure this function exists to pre-empt.

    The inherited side is probed inside a throwaway environment built by
    make_environment rather than reasoned about from prefixes, so what is
    checked is what the real environments will actually see.
    """
    probe = (
        "import importlib.util as u;"
        "print('MISSING=' + ','.join(n for n in %r if u.find_spec(n) is None));"
        "s = u.find_spec('pyteman');"
        "print('AMBIENT=' + (s.origin or '?' if s else ''))"
    )
    with tempfile.TemporaryDirectory(prefix="pyteman-precondition-") as tmp:
        inherited = make_environment(Path(tmp) / "probe")
        # cwd is pinned away from wherever the operator invoked this, because
        # `python -c` puts the working directory first on sys.path. Run from a
        # directory holding a pyteman package, or a bare pyteman directory
        # reached as a namespace package, the ambient check below would abort on
        # something the built environments never import: they run with cwd set
        # to the tree under test, at check_provenance.
        missing, ambient = echoed_values(
            run([str(inherited), "-c", probe % (REQUIRED_IN_BASE,)],
                cwd=tmp, capture=True),
            "MISSING", "AMBIENT",
        )
        launcher_missing, _ = echoed_values(
            run([sys.executable, "-c", probe % (REQUIRED_IN_LAUNCHER,)],
                cwd=tmp, capture=True),
            "MISSING", "AMBIENT",
        )
    if launcher_missing:
        raise SystemExit(
            f"{sys.executable} is missing {launcher_missing}. This interpreter "
            "runs the build backend directly, so it needs these itself, "
            "whatever the environments it goes on to create inherit."
        )
    if missing:
        raise SystemExit(
            f"the site-packages inherited from {sys.base_prefix} is missing "
            f"{missing}. Every environment built here inherits from there and "
            "installs the artifacts with --no-deps, so it takes these from it. "
            "Install them into that interpreter, or run this script with it "
            "directly rather than from a virtual environment layered over it."
        )
    if ambient:
        raise SystemExit(
            f"the environments built here already import pyteman from "
            f"{ambient}. Every check below would pass against that copy "
            "instead of the artifact, so this script refuses to run rather "
            "than report a result it cannot stand behind."
        )


def build_both_artifacts(work):
    """Build from a copy, never from the working tree.

    A build writes build/ and rewrites *.egg-info in place, so building here
    would mutate a checkout somebody else may be using. The stale egg-info
    reason above is the one that actually corrupts the measurement.
    """
    snapshot = work / "snapshot"
    shutil.copytree(ROOT, snapshot, ignore=shutil.ignore_patterns(*NOT_COPIED))
    out = work / "dist"

    # Echoed behind markers rather than read off the end of the output:
    # setuptools writes its own build log to stdout, so the last line belongs to
    # whatever it happened to log and not to the value returned.
    script = (
        "import sys; sys.path.insert(0, '');"
        "from setuptools import build_meta as b;"
        f"s = b.build_sdist({str(out)!r});"
        f"w = b.build_wheel({str(out)!r});"
        "print('SDIST=' + s); print('WHEEL=' + w)"
    )
    sdist_name, wheel_name = echoed_values(
        run([sys.executable, "-c", script], cwd=snapshot, capture=True), "SDIST", "WHEEL"
    )
    # Checked rather than trusted, because this is the one reader of a marker
    # where an empty value does not fail closed: `out / ""` is `out`, so a
    # missing marker would hand the dist directory to pip and surface as a pip
    # error naming neither the build nor the marker.
    if not sdist_name or not wheel_name:
        raise SystemExit(
            f"the build printed SDIST={sdist_name!r} WHEEL={wheel_name!r}: the "
            "backend returned no name for one of the two artifacts"
        )
    return out / sdist_name, out / wheel_name


def make_environment(path):
    # --without-pip because bootstrapping one costs about 3.4 seconds a venv
    # against 0.09 without, and buys nothing: --system-site-packages makes the
    # base interpreter's pip importable, and pip installs into the environment
    # of whichever interpreter runs it, which is this one.
    run([sys.executable, "-m", "venv", "--without-pip", "--system-site-packages", str(path)])
    return path / "bin" / "python"


def venv_root(python):
    return python.parent.parent


def install(python, artifact):
    run([str(python), "-m", "pip", "install", "--quiet",
         "--no-index", "--no-deps", "--no-build-isolation", str(artifact)])


def check_provenance(python, label, cwd):
    """Where the import actually comes from, asked from the directory the suite
    will run in.

    Asked from anywhere else the question is easier than the real one. sys.path
    starts with the working directory, so a stray copy beside the tests would
    shadow the installed package for pytest and not for a probe run elsewhere.
    Asked from here, one comparison covers both that case and an editable
    install pointing back at the checkout.
    """
    probe = "import pyteman; print('ORIGIN=' + pyteman.__file__)"
    origin, = echoed_values(
        run([str(python), "-c", probe], cwd=cwd, capture=True), "ORIGIN"
    )
    # is_relative_to rather than a substring test: /tmp/w/venv-sdist is a
    # substring of /tmp/w/venv-sdist.bak/lib/... and that path is not inside
    # this environment.
    if not origin or not Path(origin).is_relative_to(venv_root(python)):
        raise SystemExit(f"{label}: imported {origin!r}, which is not inside its own environment")
    say(f"  provenance ok: {origin}")


def extract(sdist, into):
    # filter="data" is the default from Python 3.14 and a DeprecationWarning
    # short of it before that, so naming it keeps every supported interpreter on
    # the same extraction rules instead of one that shifted under us.
    with tarfile.open(sdist) as tar:
        tar.extractall(into, filter="data")
    # An sdist has exactly one top-level directory. Taking the first entry of an
    # unordered readdir would silently pick one of several, and taking it from an
    # empty directory would escape as a bare StopIteration.
    entries = sorted(into.iterdir())
    if len(entries) != 1 or not entries[0].is_dir():
        raise SystemExit(f"expected one directory in {sdist.name}, found {entries}")
    return entries[0]


def smoke_the_activation_hook(python):
    """The wheel's hook, reached the way a user reaches it.

    The hook ships nested as pyteman/sitecustomize.py, so a user puts that
    directory on PYTHONPATH to make `sitecustomize` top-level importable and
    CPython imports it at interpreter startup. Two things are asserted, and the
    second is the one worth having: that the module that loaded is THIS one, and
    that with no PYTEMAN_RULES in the environment it did nothing, leaving
    pyteman itself unimported in a process that never asked for it.

    Identity rather than presence, because presence is satisfied by any
    sitecustomize at all. These environments inherit the base interpreter's
    site-packages, and Debian and Ubuntu ship one there. Measured: with a
    foreign hook installed and PYTHONPATH pointed at a directory carrying no
    hook of ours, a presence check reports success, and it reports it for a
    wheel that stopped shipping the file altogether.
    """
    purelib, = echoed_values(
        run([str(python), "-c",
             "import sysconfig; print('PURELIB=' + sysconfig.get_paths()['purelib'])"],
            capture=True), "PURELIB")
    expected = Path(purelib) / "pyteman" / "sitecustomize.py"
    probe = (
        "import sys;"
        "m = sys.modules.get('sitecustomize');"
        "print('HOOK=' + (getattr(m, '__file__', '') or ''));"
        "print('IMPORTED=' + str('pyteman' in sys.modules))"
    )
    hook, imported = echoed_values(
        run([str(python), "-c", probe], capture=True,
            extra_env={"PYTHONPATH": str(expected.parent)}), "HOOK", "IMPORTED")
    if not hook or Path(hook).resolve() != expected.resolve():
        raise SystemExit(
            f"wheel: sitecustomize loaded from {hook!r}, not from the installed "
            f"package at {expected}"
        )
    if imported != "False":
        raise SystemExit("wheel: the hook imported pyteman with no PYTEMAN_RULES set")
    say("  activation hook loads from the wheel and stays inert without PYTEMAN_RULES")


def main():
    check_the_base_is_a_clean_room()
    work = Path(tempfile.mkdtemp(prefix="pyteman-artifacts-"))
    # A TMPDIR inside the checkout makes the snapshot copy re-enter itself.
    # Measured: about ninety nested levels before shutil gives up with "File
    # name too long", leaving the garbage behind and naming no cause.
    if work.is_relative_to(ROOT):
        raise SystemExit(f"TMPDIR puts the work directory inside {ROOT}: point it elsewhere")
    say(f"working in {work}")

    sdist, wheel = build_both_artifacts(work)
    say(f"built {sdist.name} and {wheel.name}")

    # Extracted twice on purpose, and cheaply: 0.03 seconds each. One tree per
    # environment keeps the two runs from sharing any state at all, which is the
    # property worth having here rather than any one mechanism it rules out.
    for label, artifact in (("sdist", sdist), ("wheel", wheel)):
        say(f"\n== {label} ==")
        python = make_environment(work / f"venv-{label}")
        install(python, artifact)
        tree = extract(sdist, work / f"tests-for-{label}")
        check_provenance(python, label, cwd=tree)
        if label == "wheel":
            smoke_the_activation_hook(python)
        # The suite comes from the sdist in both cases, because the wheel does
        # not carry tests and must not. Against the wheel this is the check that
        # it is functionally complete: same tests, package taken from the wheel.
        #
        # -rs because seven artifact-build checks skip here by design, PKG-INFO
        # being present meaning a build from this tree would measure an archive
        # against itself. Skipping silently is what this flag prevents.
        say(f"  running the suite from {tree}")
        run([str(python), "-m", "pytest", "-q", "-rs"], cwd=tree)

    # Only on success. Every failure above raises, which leaves the tree in
    # place for the post mortem, and that is the one time it is worth its 6 MB.
    shutil.rmtree(work)
    say("\nBoth artifacts install, import from their own environment, and pass the suite.")


if __name__ == "__main__":
    main()
