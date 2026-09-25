"""What the built artifacts carry, checked against the artifacts themselves.

TASK-32 / PKG-01. The reasoning, the measured evidence and the offline
verification commands live in docs/packaging.md. What follows is what a reader
of this file needs and nothing that is written down elsewhere.

Two kinds of check live here and they are deliberately different.

``test_everything_the_suite_reads_is_beside_it`` reads the tree it is running
in. In a checkout that is nearly free and nearly meaningless. Run from an
extracted sdist it is the acceptance criterion stated directly, and it is the
one check here that survives the trip.

The build checks measure an artifact built from the tree instead, which is the
only way to catch a file added to a shipped directory that the manifest never
learned about. Two conditions disable them, and both are announced under
``-rs`` and silent without it, which is why neither is left to be noticed: the
guard below turns either one into a failure wherever it would be a lie.
"""

import fnmatch
import importlib.util
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import NamedTuple

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Present in every sdist, absent from every checkout: this is how the build
# checks know they are running inside an artifact rather than beside one.
INSIDE_A_BUILT_DISTRIBUTION = (ROOT / "PKG-INFO").exists()

# The build is performed by whatever setuptools lives in this interpreter,
# because the backend is called directly rather than through a frontend that
# would provision one. That is what keeps the build offline, and it is also why
# the backend is not guaranteed to be here: a runtime environment has no reason
# to carry build tooling. Measured on the development machine, the python3 first
# on PATH carries pytest and no setuptools at all. Without this check that
# arrives as a build log from a failed subprocess, naming nothing.
BUILD_BACKEND_PRESENT = importlib.util.find_spec("setuptools") is not None

# No grant in MANIFEST.in reaches any of these, so no sdist can contain them and
# finding one means this is a checkout. Three of them rather than one because
# this is what the guard below stands on, and a single marker makes the guard
# only as reliable as one unrelated directory nobody is watching.
CHECKOUT_MARKERS = (".github", ".gitignore", "backlog")
LOOKS_LIKE_A_CHECKOUT = any((ROOT / name).exists() for name in CHECKOUT_MARKERS)

# The directories MANIFEST.in grants whole.
SHIPPED_WHOLE = ("tests", "docs", "examples")

# What a test run, a compiler, an editor and an overwrite leave behind. These
# mirror the global-exclude line in MANIFEST.in: that line enforces, this one
# detects, and a check of an enforcement is not a duplicate of it.
RESIDUE_SUFFIXES = (".pyc", ".pyo", ".pyd", ".so", ".log", ".swp", ".bak")

# Written into the copied tree by the fixture so the residue check measures
# something by construction. Waiting for residue to appear on its own makes the
# check depend on whether this run happened to write bytecode, which is not a
# property of the manifest: PYTHONDONTWRITEBYTECODE, python -B or a fresh
# container all turn it off. One name per pattern in the global-exclude line,
# so that line is verified rather than assumed to work.
PLANTED_RESIDUE = (
    "planted.pyc",
    "planted.pyo",
    "planted.pyd",
    "planted.so",
    "planted.log",
    "planted.swp",
    "planted~",
    ".DS_Store",
    "planted.bak",
    "planted.bak.1",
)

# Planted beside the residue and expected to SHIP, which is the other direction
# and the one nothing else here watches. The backups could have been excluded
# with the single pattern `*.bak*` instead of the two MANIFEST.in carries, and
# that pattern also matches any name holding .bak inside a longer word. This
# file is what turns that difference into a measurement: it belongs in the
# archive, and a residue pattern widened the convenient way removes it.
PLANTED_KEEPER = "notes.bakery.md"

# Read by the suite at runtime. conftest.py puts tests/ on sys.path;
# target_mod.py is the module the patcher rewrites; integrity_corpus.py holds
# the samples three test modules import; the two documents are read and executed
# by the doc tests, which fail on a missing file rather than skipping.
READ_BY_THE_SUITE = (
    "tests/conftest.py",
    "tests/target_mod.py",
    "tests/integrity_corpus.py",
    "docs/rules.md",
    "docs/integrity.md",
)

# Cited by README.md by path rather than opened by a test, which is why no other
# test notices when one goes missing.
CITED_BY_THE_README = ("LICENSE", "docs/targeting.md")

# Kept out of the copy the artifacts are built from. Matched by basename at
# every depth, which is why the expectations are derived from that copy and
# never from ROOT: a docs/build/ or a nested .git would be absent from the
# archive and present in the tree, and the mismatch would be reported as a
# manifest error naming a file the manifest included correctly.
NOT_COPIED = (".git", "*.egg-info", "build", "dist", ".venv")


def _is_residue(name):
    return (
        name.endswith(RESIDUE_SUFFIXES)
        or name.endswith("~")
        or name == ".DS_Store"
        # The timestamped backup, which no suffix can express because the tail
        # after .bak. is an epoch and differs on every write. Matched on the dot
        # that follows and not on a bare `.bak` substring: notes.bakery.md holds
        # one of those and has to keep shipping. The loose form would drop it
        # from the archive and from the expectation together, which is the
        # cancellation _files_under's docstring exists to explain.
        or ".bak." in name
    )


def _files_under(subdir, tree):
    """Every file in a granted directory, unfiltered by extension.

    Filtering this by suffix would re-apply the predicate that caused the
    defect in the first place. The first fixture that is not a .py file would
    be absent from the archive and absent from the expectation at the same
    time, and the assertion would pass while the sdist was broken.

    ``tree`` is the copy the artifact was built from, not ROOT. The two differ
    by NOT_COPIED and by anything written between the build and this call.
    """
    found = {
        str(path.relative_to(tree))
        for path in (tree / subdir).rglob("*")
        if path.is_file() and not _is_residue(path.name)
    }
    assert found, f"nothing found under {subdir}/, the derivation is broken"
    return found


class Artifacts(NamedTuple):
    sdist: set
    wheel: set
    tree: Path


@pytest.mark.parametrize("relative", READ_BY_THE_SUITE + CITED_BY_THE_README)
def test_everything_the_suite_reads_is_beside_it(relative):
    """The acceptance criterion, asserted wherever this suite happens to run."""
    assert (ROOT / relative).is_file(), f"{relative} is missing from {ROOT}"


def test_the_build_checks_cannot_be_disabled_silently():
    """Both conditions that turn off the build checks, checked for honesty.

    This test never skips, which is the point. Seven checks that quietly do not
    run are worse than seven that fail, because the run stays green and the
    suite reports a number that looks like success. Without ``-rs`` pytest does
    not even print the reasons, and this project sets no addopts to supply it.
    """
    if not LOOKS_LIKE_A_CHECKOUT and INSIDE_A_BUILT_DISTRIBUTION:
        # A built distribution, where PKG-INFO is honest by construction and
        # there is no tree to build from anyway. Nothing to guard.
        #
        # Both conditions, because they are not the same state. A tree with
        # neither the markers nor a PKG-INFO is a source tree that something
        # stripped, a container build whose .dockerignore drops dot-entries
        # being the ordinary way to produce one. It has everything needed to
        # build and must not take this exit.
        return
    assert not INSIDE_A_BUILT_DISTRIBUTION, (
        f"{ROOT} holds {CHECKOUT_MARKERS} and a PKG-INFO: the marker is lying "
        "and the build checks are skipping in what is actually a checkout"
    )
    assert BUILD_BACKEND_PRESENT, (
        f"{sys.executable} has no setuptools, so every check of what the "
        "artifacts carry would skip here and this run would prove nothing "
        "about packaging: install setuptools in this interpreter"
    )


def test_every_excluded_pattern_is_exercised_by_a_planted_file():
    """The comment on PLANTED_RESIDUE, turned into a check that can fail.

    One list that has to track another is the defect this file exists for, one
    level up. A pattern added to the global-exclude line without a name here is
    never exercised: the residue check narrows silently and nothing goes red to
    say so.

    Only this direction needs asserting. A planted name matching no pattern
    ships, and then either the residue check or the equality check fails on it
    depending on what _is_residue makes of the name, so that direction is
    already mechanically covered.
    """
    manifest = (ROOT / "MANIFEST.in").read_text().splitlines()
    # Every global-exclude line, not the first one. Splitting the patterns over
    # a second line is the natural way to extend them, and reading only the
    # first would make the later ones invisible here: no planted file would be
    # demanded for them, the residue check would quietly stop measuring them,
    # and this test, whose whole purpose is to catch an unexercised pattern,
    # would stay green through exactly the narrowing it exists to detect.
    patterns = [
        pattern
        for text in manifest if text.startswith("global-exclude ")
        for pattern in text.split()[1:]
    ]
    assert patterns, "MANIFEST.in has no global-exclude line to read patterns from"
    unexercised = [
        pattern
        for pattern in patterns
        if not any(fnmatch.fnmatch(name, pattern) for name in PLANTED_RESIDUE)
    ]
    assert unexercised == [], (
        f"MANIFEST.in excludes {unexercised} and PLANTED_RESIDUE holds no name "
        "matching them, so the residue check never measures those patterns: "
        "add one file name per pattern"
    )


@pytest.fixture(scope="module")
def artifacts(tmp_path_factory):
    """An sdist and a wheel built from a copy of this tree, offline.

    The copy is what makes the measurement honest. It keeps the build out of the
    working tree, which would otherwise acquire a build/ directory and a
    rewritten egg-info from running the suite. And it drops any existing
    *.egg-info, because setuptools READS the SOURCES.txt it finds there and adds
    its contents to the archive: build over a stale one and the test measures a
    cache written by an earlier manifest rather than the manifest on disk now.

    What it does NOT drop is deliberate. backlog/, .claude/ and .pytest_cache/
    are copied so that asserting their absence from the archive means something.
    Residue is planted for the same reason, rather than hoping the tree has some,
    and one file is planted to be KEPT rather than swept, so that a residue
    pattern written too wide is measured here too instead of being argued about.
    An artifact test that tidies the tree first proves only that a clean tree
    produces a clean archive.

    The build runs in a subprocess, and not only for isolation: setuptools
    changes the working directory and mutates global distutils state, and an
    in-process build leaves both behind for whatever test runs next. No network
    is involved; the backend is called directly, so there is no build isolation
    step to fetch anything.
    """
    work = tmp_path_factory.mktemp("packaging")
    checkout = work / "checkout"
    shutil.copytree(ROOT, checkout, ignore=shutil.ignore_patterns(*NOT_COPIED))
    for name in PLANTED_RESIDUE + (PLANTED_KEEPER,):
        (checkout / "tests" / name).write_bytes(b"planted by the packaging suite\n")

    # The names are echoed behind markers rather than read off the end of the
    # output: setuptools writes its own build log to stdout, so the last lines
    # belong to the build that ran most recently and not to the value returned.
    script = (
        "import sys; sys.path.insert(0, '');"
        "from setuptools import build_meta as b;"
        f"s = b.build_sdist({str(work)!r});"
        f"w = b.build_wheel({str(work)!r});"
        "print('SDIST=' + s); print('WHEEL=' + w)"
    )
    # A generous budget because this is a real setuptools build of both
    # artifacts rather than a probe: it is here to bound a hang, not to police
    # a duration, and it sits well inside the job's own timeout-minutes. No
    # cleanup is written around it, because run() kills and reaps the child it
    # started. What it does not reap is that build's own grandchildren, which
    # is a stated limit of this check and not a reason to build a process
    # group here.
    done = subprocess.run(
        [sys.executable, "-c", script], cwd=checkout, capture_output=True,
        text=True, timeout=300
    )
    assert done.returncode == 0, f"build failed:\n{done.stdout}\n{done.stderr}"
    echoed = dict(
        line.split("=", 1)
        for line in done.stdout.splitlines()
        if line.startswith(("SDIST=", "WHEEL="))
    )

    # Members, not names: a tarball carries an entry per directory as well, and
    # those have no file behind them to compare against the tree.
    with tarfile.open(work / echoed["SDIST"]) as tar:
        prefix = Path(echoed["SDIST"]).name.removesuffix(".tar.gz") + "/"
        sdist = {
            member.name.removeprefix(prefix)
            for member in tar.getmembers()
            if member.isfile() and member.name.startswith(prefix)
        }
    with zipfile.ZipFile(work / echoed["WHEEL"]) as zf:
        wheel = set(zf.namelist())
    return Artifacts(sdist, wheel, checkout)


@pytest.mark.skipif(
    INSIDE_A_BUILT_DISTRIBUTION,
    reason="already inside a built distribution: building one from it would "
    "measure the archive against itself",
)
@pytest.mark.skipif(
    not BUILD_BACKEND_PRESENT,
    reason="setuptools is not importable here, so there is no build backend to "
    "call: install it in this interpreter to run the packaging checks",
)
class TestBuiltArtifacts:
    """Checks that need a checkout to build from, and say so when they skip."""

    @pytest.mark.parametrize("subdir", SHIPPED_WHOLE)
    def test_the_sdist_carries_a_granted_directory_exactly(self, subdir, artifacts):
        """Equality, not containment, and for a reason beyond symmetry.

        Containment would catch the manifest omitting a file. Equality also
        catches it carrying one the tree does not have, which is a live hazard
        here rather than a hypothetical: setuptools unions the contents of any
        SOURCES.txt it finds into the archive, so a stale cache shows up as an
        entry with no file behind it.
        """
        carried = {name for name in artifacts.sdist if name.startswith(f"{subdir}/")}
        assert carried == _files_under(subdir, artifacts.tree)

    def test_the_sdist_carries_no_top_level_entry_that_was_not_granted(
        self, artifacts
    ):
        """The check a list of unwanted names cannot perform.

        A tracker, editor configuration and caches are the three that were in
        mind when this was written, which is exactly why naming them would be
        the wrong shape. The fourth one nobody has thought of yet fails here too.

        The scope is the top level only. Below src/ the contents come from
        setuptools package discovery rather than from MANIFEST.in, and the two
        granted directories that are checked file by file are checked above.
        """
        granted = {
            "LICENSE",
            "MANIFEST.in",
            "PKG-INFO",
            "README.md",
            "pyproject.toml",
            "setup.cfg",  # generated into the sdist by setuptools, not in the tree
            "src",
            *SHIPPED_WHOLE,
        }
        top_level = {name.split("/", 1)[0] for name in artifacts.sdist if name}
        assert top_level <= granted, sorted(top_level - granted)

        # The other direction, and deliberately not equality against the whole
        # set above. PKG-INFO and setup.cfg are written by the backend rather
        # than granted by the manifest, so demanding them would make this test
        # report a manifest error the day a setuptools release stops emitting
        # one. These four are the root files MANIFEST.in names, and a file that
        # stops shipping is otherwise caught by nothing.
        always_shipped = {"LICENSE", "README.md", "pyproject.toml", "MANIFEST.in"}
        assert always_shipped <= top_level, sorted(always_shipped - top_level)

    def test_the_sdist_carries_no_residue(self, artifacts):
        """What MANIFEST.in's global-exclude enforces, measured in the archive.

        Never skipped and never vacuous: the fixture plants one file per pattern
        in that line, inside a directory granted whole, so this measures the
        exclusion rather than the tidiness of whoever ran the suite.
        """
        assert sorted(n for n in artifacts.sdist if _is_residue(Path(n).name)) == []

        # The other direction, and the reason PLANTED_KEEPER is planted at all.
        # A residue pattern written too wide fails silently: the archive comes
        # out smaller and nothing about it looks wrong. The equality check on
        # tests/ goes red on this too and does name the file, but it reports a
        # set difference and no reason. This is the only thing here holding
        # MANIFEST.in to the pair `*.bak` plus `*.bak.*` rather than `*.bak*`.
        assert f"tests/{PLANTED_KEEPER}" in artifacts.sdist, (
            f"{PLANTED_KEEPER} was planted in a directory granted whole and did "
            "not ship, so a residue pattern is matching a name that merely "
            "contains one of their prefixes: the exclusions are now removing "
            "wanted files, which is the same defect as shipping unwanted ones "
            "with nothing to notice it"
        )

    def test_the_wheel_keeps_the_activation_hook_nested(self, artifacts):
        """The hook ships as pyteman.sitecustomize and never at the top level.

        A top-level sitecustomize.py on sys.path is imported by every Python
        process in the environment, so installing this package would change the
        behaviour of programs that never asked for it.
        """
        assert "pyteman/sitecustomize.py" in artifacts.wheel
        assert "sitecustomize.py" not in artifacts.wheel
        assert "pyteman/py.typed" in artifacts.wheel

    def test_the_wheel_installs_no_tests_documents_or_examples(self, artifacts):
        """The sdist carries them; the runtime namespace must not.

        Matched on any path component rather than the leading one, so vendoring
        them under the package as pyteman/tests/ fails here too. That is the
        form the wheel would actually take if package discovery ever widened.

        The cost of that width is that a deliberate pyteman/examples/ subpackage
        would fail here as well, which for a toolkit that already ships an
        examples/ tree is not far-fetched. That case is a decision rather than a
        mistake, so the message says which of the two this is and what to do.
        """
        intruders = sorted(
            name
            for name in artifacts.wheel
            if set(Path(name).parts[:-1]) & set(SHIPPED_WHOLE)
        )
        assert intruders == [], (
            f"the wheel carries {intruders}. If that is a vendored copy of what "
            "belongs in the sdist, the packaging is wrong. If it is a deliberate "
            f"subpackage, this test is where that decision gets made: rename it "
            "or narrow SHIPPED_WHOLE for the wheel"
        )
