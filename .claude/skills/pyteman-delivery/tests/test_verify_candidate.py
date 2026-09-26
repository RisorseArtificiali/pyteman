import argparse
import contextlib
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import pty
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree


SCRIPT = Path(__file__).resolve().parents[1] / "verify_candidate.py"
spec = importlib.util.spec_from_file_location("verify_candidate", SCRIPT)
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)

GIT_IDENTITY = ("-c", "user.email=candidate@example.invalid",
                "-c", "user.name=Candidate", "-c", "commit.gpgsign=false")

# Stands in for the virtualenv interpreter. Everything but "-m pytest" runs on the
# real interpreter with the export on the path, the way an editable install leaves it.
SHIM = '''#!%(real)s
import json, os, shutil, sys

arguments = sys.argv[1:]
if arguments[:2] == ["-m", "pytest"]:
    with open("%(record)s", "w") as record:
        json.dump({"arguments": arguments, "cwd": os.getcwd(),
                   "cache": os.environ.get("PYTHONPYCACHEPREFIX"),
                   "pythonpath": os.environ.get("PYTHONPATH")}, record)
    if os.path.exists("%(mutate)s"):
        with open("%(mutate)s", "w") as source:
            source.write("rewritten while the suite ran")
    wanted = [word for word in arguments if word.startswith("--junit-xml=")]
    if wanted and os.path.exists("%(report)s"):
        shutil.copyfile("%(report)s", wanted[0].split("=", 1)[1])
    sys.exit(%(code)d)
environment = dict(os.environ)
environment["PYTHONPATH"] = os.pathsep.join(["%(src)s", "%(stubs)s"])
os.execve("%(real)s", ["%(real)s"] + arguments, environment)
'''


def archive_bytes(name="src/pyteman/runner/matrix.py", kind=tarfile.REGTYPE):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as archive:
        entry = tarfile.TarInfo(name)
        entry.type = kind
        entry.mode = 0o444
        if kind == tarfile.REGTYPE:
            entry.size = 4
            archive.addfile(entry, io.BytesIO(b"pass"))
        else:
            entry.linkname = "/outside"
            archive.addfile(entry)
    return output.getvalue()


def junit(cases):
    """A report shaped like the one pytest writes, without needing pytest.
    A case is (classname, name, outcome, message) and may carry a fifth element
    holding the child's text, which is where pytest puts the real reason for a
    module-level importorskip. `outcome` may instead be a list of
    (tag, message) or (tag, message, text) children: pytest writes more than one
    when a test and its teardown report different outcomes, and a model that
    cannot express that would agree with a reader that only looks at the first.
    Each child in that form carries its own message, so the case's own `message`
    is inert and those call sites pass an empty one."""
    suites = ElementTree.Element("testsuites", name="pytest tests")
    suite = ElementTree.SubElement(suites, "testsuite", name="pytest",
                                   tests=str(len(cases)))
    for classname, name, outcome, message, *rest in cases:
        case = ElementTree.SubElement(suite, "testcase", classname=classname, name=name)
        children = ([] if outcome is None
                    else outcome if isinstance(outcome, list)
                    else [(outcome, message, *rest)])
        for tag, child_message, *text in children:
            child = ElementTree.SubElement(case, tag, message=child_message)
            child.text = text[0] if text else None
    return ElementTree.tostring(suites, encoding="unicode")


def stub_modules(directory):
    """The dependencies the identity probe insists on, as importable files."""
    directory.mkdir(parents=True, exist_ok=True)
    for name in verify.PROBE_DEPENDENCIES:
        (directory / f"{name}.py").write_text("")
    return directory


def new_file_patch(path, name, body, mode="100644"):
    # git writes a symlink's target without a trailing newline.
    lines = body.splitlines()
    text = (f"diff --git a/{name} b/{name}\nnew file mode {mode}\n"
            f"--- /dev/null\n+++ b/{name}\n@@ -0,0 +1,{len(lines)} @@\n"
            + "".join(f"+{line}\n" for line in lines)
            + ("\\ No newline at end of file\n" if mode == "120000" else ""))
    path.write_bytes(text.encode())
    return path


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="candidate tests ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def isolated_interpreter(self):
        """A real interpreter that ignores site-packages, so the fixture is the
        whole import path on any host."""
        wrapper = self.root / "python-without-site"
        wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" -S "$@"\n')
        wrapper.chmod(0o755)
        return wrapper

    def test_unsafe_paths_are_rejected(self):
        for name in ("/outside", "../outside", "src/../../outside", ".git/config",
                     "src/.git/config", "src\\outside", ""):
            with self.subTest(name=name), self.assertRaises(verify.VerificationError):
                verify.safe_name(name)
        verify.safe_name("tests/a name.py")

    def test_real_patch_paths_are_checked(self):
        for name in ("../outside", "/outside", ".git/config", "safe file.py"):
            candidate = new_file_patch(self.root / "candidate.patch", name, "pass\n")
            env = verify.clean_env(self.root / "cache")
            if name == "safe file.py":
                self.assertEqual(
                    verify.patch_destinations(candidate, self.root, env), [name])
            else:
                with self.assertRaises(verify.VerificationError):
                    verify.patch_destinations(candidate, self.root, env)
            self.assertFalse((self.root.parent / "outside").exists())

    def test_export_rejects_links_and_traversal_before_writing(self):
        for name, kind in (("../bad", tarfile.REGTYPE),
                           ("link", tarfile.SYMTYPE), ("hard", tarfile.LNKTYPE)):
            with self.subTest(name=name), self.assertRaises(verify.VerificationError):
                verify.extract_export(archive_bytes(name, kind), self.root)
            self.assertEqual(list(self.root.iterdir()), [])

    def test_export_is_writable_even_if_source_mode_is_readonly(self):
        verify.extract_export(archive_bytes(), self.root)
        path = self.root / "src/pyteman/runner/matrix.py"
        self.assertTrue(path.stat().st_mode & 0o200)
        path.write_text("updated")

    def test_source_change_and_missing_source_are_rejected(self):
        path = self.root / "module.py"
        path.write_text("initial")
        before = verify.snapshot(self.root)
        verify.verify_snapshot(before, verify.rehash(self.root, before))
        path.write_text("changed")
        with self.assertRaises(verify.VerificationError):
            verify.verify_snapshot(before, verify.rehash(self.root, before))
        path.unlink()
        with self.assertRaises(verify.VerificationError):
            verify.verify_snapshot(before, verify.rehash(self.root, before))
        # A symlink to identical content reads back as the expected bytes, so
        # the hash alone cannot tell that the file the suite ran on was replaced.
        (self.root / "elsewhere.py").write_text("initial")
        path.symlink_to(self.root / "elsewhere.py")
        self.assertEqual(path.read_text(), "initial")
        with self.assertRaises(verify.VerificationError):
            verify.verify_snapshot(before, verify.rehash(self.root, before))

    def test_package_copies_outside_src_are_refused(self):
        tree = self.root / "tree"
        (tree / "src/pyteman").mkdir(parents=True)
        (tree / "src/pyteman/__init__.py").write_text("")
        (tree / "tests").mkdir()
        verify.check_package_layout(tree)
        # pytest prepends each test file's own directory, so a package here
        # serves the suite while the probe still certifies the installed one.
        # Every suffix the import system accepts is refused, not just source:
        # a committed .pyc or .so shadows exactly as effectively as a .py.
        names = []
        for suffix in importlib.machinery.all_suffixes():
            names += [f"tests/pyteman/__init__{suffix}", f"pyteman/__init__{suffix}",
                      f"pyteman{suffix}", f"tests/pyteman{suffix}"]
        self.assertIn("pyteman.pyc", names)
        for name in names:
            copy = tree / name
            copy.parent.mkdir(parents=True, exist_ok=True)
            copy.write_text("")
            with self.subTest(name=name):
                with self.assertRaisesRegex(verify.VerificationError,
                                            "Package copies outside src"):
                    verify.check_package_layout(tree)
            copy.unlink()
        # A bare directory is only a namespace portion: a regular package later
        # on the path still wins, so refusing it would be a false alarm.
        (tree / "tests/pyteman").mkdir(parents=True, exist_ok=True)
        verify.check_package_layout(tree)

    def test_environment_removes_activation_and_ambient_overrides(self):
        values = {"PYTEMAN_RULES": "bad", "PYTHONPATH": "bad", "GIT_DIR": "bad",
                  "PYTHONDONTWRITEBYTECODE": "1", "PYTEST_ADDOPTS": "--collect-only",
                  "PYTHONOPTIMIZE": "1", "PYTHONWARNINGS": "ignore",
                  "PYTHONSAFEPATH": "1", "PYTHONINSPECT": "1",
                  "KEEP_ME": "yes"}
        with patch.dict(os.environ, values):
            env = verify.clean_env(self.root / "cache")
            preflight = verify.clean_env(None)
        for name in values.keys() - {"KEEP_ME"}:
            self.assertNotIn(name, env)
        self.assertEqual(env["KEEP_ME"], "yes")
        self.assertEqual(env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"], "1")
        self.assertEqual(env["PYTHONPYCACHEPREFIX"], str(self.root / "cache"))
        # The preflight runs before any evidence directory exists, so it writes
        # no bytecode rather than sharing a cache with another run.
        self.assertEqual(preflight["PYTHONDONTWRITEBYTECODE"], "1")
        self.assertNotIn("PYTHONPYCACHEPREFIX", preflight)
        with patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": "host-global",
                                     "GIT_CONFIG_SYSTEM": "host-system"}):
            for cache in (None, self.root / "cache"):
                isolated = verify.clean_env(cache)
                self.assertEqual(isolated["GIT_CONFIG_GLOBAL"], os.devnull)
                self.assertEqual(isolated["GIT_CONFIG_SYSTEM"], os.devnull)

    def git_config_environments(self, settings):
        home = self.root / "home"
        xdg = self.root / "xdg"
        home.mkdir()
        (xdg / "git").mkdir(parents=True)
        configs = {
            "home": home / ".gitconfig",
            "xdg": xdg / "git/config",
            "system": self.root / "system.gitconfig",
        }
        for config in configs.values():
            config.write_text(settings)
        with patch.dict(os.environ, {"HOME": str(home), "XDG_CONFIG_HOME": str(xdg),
                                     "GIT_CONFIG_GLOBAL": str(configs["home"]),
                                     "GIT_CONFIG_SYSTEM": str(configs["system"])}):
            cleaned = verify.clean_env(None)
        # apply runs outside a repository, as it does on the runner's export.
        cleaned["GIT_CEILING_DIRECTORIES"] = str(self.root)
        for name, config in configs.items():
            inherited = dict(cleaned)
            if name == "system":
                inherited["GIT_CONFIG_SYSTEM"] = str(config)
            else:
                inherited.pop("GIT_CONFIG_GLOBAL", None)
                if name == "xdg":
                    inherited["HOME"] = str(self.root / "empty-home")
            yield name, cleaned, inherited

    def test_host_git_config_cannot_relax_patch_context(self):
        source = "def value():\n    return 1\n"
        candidate = self.root / "context.patch"
        mismatch = ("diff --git a/example.py b/example.py\n"
                    "--- a/example.py\n+++ b/example.py\n"
                    "@@ -1,2 +1,3 @@\n def value():\n"
                    "+    added = 2\n         return 1\n")
        for name, cleaned, inherited in self.git_config_environments(
                "[apply]\n    ignoreWhitespace = change\n"):
            with self.subTest(config=name):
                tree = self.root / f"export-{name}"
                tree.mkdir()
                module = tree / "example.py"
                module.write_text(source)
                candidate.write_text(mismatch)
                command = ["git", "apply", str(candidate)]
                refused = verify.run(command, tree, cleaned, check=False)
                self.assertNotEqual(refused.returncode, 0)
                self.assertIn(b"patch does not apply", refused.stderr)
                self.assertEqual(module.read_text(), source)
                verify.run(command, tree, inherited)
                self.assertEqual(module.read_text(),
                                 "def value():\n    added = 2\n    return 1\n")
                module.write_text(source)
                candidate.write_text(mismatch.replace("         return", "     return"))
                verify.run(command, tree, cleaned)
                self.assertEqual(module.read_text(),
                                 "def value():\n    added = 2\n    return 1\n")

    def test_host_git_config_cannot_rewrite_added_bytes(self):
        content = "value = 1  \n"
        candidate = new_file_patch(self.root / "bytes.patch", "example.py", content)
        for name, cleaned, inherited in self.git_config_environments(
                "[apply]\n    whitespace = fix\n"):
            with self.subTest(config=name):
                for label, env, expected in (("clean", cleaned, content),
                                             ("host", inherited, "value = 1\n")):
                    tree = self.root / f"{name}-{label}"
                    tree.mkdir()
                    verify.run(["git", "apply", str(candidate)], tree, env)
                    self.assertEqual((tree / "example.py").read_bytes(),
                                     expected.encode())

    def test_an_inherited_inspect_flag_does_not_stall_the_first_command(self):
        """PYTHONINSPECT drops a child into the REPL once its code has run, and
        run() captures stdout and stderr while leaving stdin inherited, so the
        child reads the operator's terminal and never returns. The interpreter
        enters that loop only for a stdin it considers interactive, which is why
        this uses a pty rather than a pipe, and why the first arm has to block:
        a harness that never made the child interactive would satisfy the second
        arm whatever clean_env did with the variable."""
        # The master end stays open for the duration: closing it would make the
        # slave read EIO instead of blocking, and the first arm would pass for
        # the wrong reason. Cleanups run in reverse, so fd 0 is restored first.
        master, slave = pty.openpty()
        # Closing is registered before the guard below rather than after it: the
        # guard's own failure path would otherwise leak both descriptors, since
        # a failed assertion leaves the method without reaching the two lines
        # that would have closed them. Measured, two fds survive the run that
        # fires the assertion when it precedes these lines, and none when it
        # follows them.
        self.addCleanup(os.close, master)
        self.addCleanup(os.close, slave)
        # openpty() takes the lowest free descriptors, so a caller arriving here
        # with fd 0 already closed gets master == 0, and the last cleanup then
        # closes the descriptor the first one restored, leaving the rest of the
        # process without a stdin. Refuse that rather than accommodate it: every
        # ordinary path into this test has one.
        self.assertGreater(min(master, slave), 2,
                           "the pty took a standard descriptor; stdin was closed")
        saved = os.dup(0)
        self.addCleanup(os.close, saved)
        os.dup2(slave, 0)
        self.addCleanup(os.dup2, saved, 0)
        command = [sys.executable, "-c", "pass"]
        with patch.dict(os.environ, {"PYTHONINSPECT": "1"}):
            inherited = os.environ.copy()
            cleaned = verify.clean_env(None)
        with self.assertRaisesRegex(verify.VerificationError, "-c pass exceeded 3s"):
            verify.run(command, self.root, inherited, timeout=3)
        verify.run(command, self.root, cleaned, timeout=60)

    def installed_export(self):
        """An export whose package is reachable the way an editable install
        makes it reachable: after the starting directory, before site-packages."""
        tree = self.root / "tree"
        (tree / "src/pyteman").mkdir(parents=True)
        (tree / "src/pyteman/__init__.py").write_text("")
        env = verify.clean_env(self.root / "cache")
        env["PYTHONPATH"] = os.pathsep.join(
            [str(tree / "src"), str(stub_modules(self.root / "stubs"))])
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        return tree, elsewhere, env

    def test_identity_is_bound_to_the_directory_the_suite_runs_in(self):
        python = self.isolated_interpreter()
        tree, elsewhere, env = self.installed_export()
        self.assertEqual(verify.check_identity(python, tree, elsewhere, env)["package"],
                         str((tree / "src/pyteman").resolve()))
        # A top-level package the patch adds passes every path check, and shadows
        # the install for any process started in the export.
        (tree / "pyteman").mkdir()
        (tree / "pyteman/__init__.py").write_text("")
        self.assertEqual(verify.check_identity(python, tree, elsewhere, env)["package"],
                         str((tree / "src/pyteman").resolve()),
                         "certifying from another directory cannot see the shadow")
        with self.assertRaisesRegex(verify.VerificationError, "Wrong candidate import"):
            verify.check_identity(python, tree, tree, env)

    def test_an_inherited_safe_path_does_not_disarm_the_identity_probe(self):
        """PYTHONSAFEPATH drops the leading current directory from sys.path, and
        that entry is what lets the probe, run inside the tree, see a shadow at
        the export root at all. An inherited value hides that shadow from the
        probe while pytest still imports it, because pytest inserts the rootdir
        itself and `safe_path` does not suppress that insertion: measured, the
        probe reported the installed package while the suite imported the root
        shadow. This arm covers the root shadow only; a copy under `tests/` is
        invisible to the probe either way, which is why check_package_layout
        refuses every such directory from the file listing rather than relying
        on this probe. The control arm re-adds the variable and establishes that
        it really does disarm the probe, so the assertion above it is about
        clean_env rather than about something else refusing."""
        python = self.isolated_interpreter()
        tree, _, env = self.installed_export()
        (tree / "pyteman").mkdir()
        (tree / "pyteman/__init__.py").write_text("")
        with patch.dict(os.environ, {"PYTHONSAFEPATH": "1"}):
            cleaned = verify.clean_env(self.root / "cache")
        cleaned["PYTHONPATH"] = env["PYTHONPATH"]
        with self.assertRaisesRegex(verify.VerificationError, "Wrong candidate import"):
            verify.check_identity(python, tree, tree, cleaned)
        disarmed = dict(cleaned, PYTHONSAFEPATH="1")
        self.assertEqual(verify.check_identity(python, tree, tree, disarmed)["package"],
                         str((tree / "src/pyteman").resolve()),
                         "the shadow must go unseen once the cwd entry is gone")

    def test_foreign_import_is_rejected_by_actual_interpreter(self):
        python = self.isolated_interpreter()
        _, elsewhere, env = self.installed_export()
        with self.assertRaisesRegex(verify.VerificationError, "Wrong candidate import"):
            verify.check_identity(python, self.root / "other tree", elsewhere, env)

    def test_missing_backend_is_rejected_by_actual_interpreter(self):
        python = self.isolated_interpreter()
        tree, elsewhere, env = self.installed_export()
        (self.root / "stubs/setuptools.py").unlink()
        with self.assertRaisesRegex(verify.VerificationError,
                                    "Missing verification dependency: setuptools"):
            verify.check_identity(python, tree, elsewhere, env)

    def test_identity_probe_output_that_is_not_json_is_named_as_such(self):
        python = self.isolated_interpreter()
        tree, elsewhere, env = self.installed_export()
        # A candidate that prints while importing, a deprecation notice say,
        # leaves the probe's JSON preceded by prose.
        (tree / "src/pyteman/__init__.py").write_text("print('deprecated')\n")
        with self.assertRaisesRegex(verify.VerificationError, "wrote no JSON"):
            verify.check_identity(python, tree, elsewhere, env)

    @unittest.skipUnless(importlib.util.find_spec("pytest"),
                         "needs pytest to produce a genuine report")
    def test_real_pytest_report_agrees_with_the_synthetic_one(self):
        """The reports above are this suite's model of pytest. Read one report
        pytest actually wrote, so the model cannot drift away from it unseen."""
        tests = self.root / "tests"
        tests.mkdir()
        (tests / "test_shapes.py").write_text(
            "import pytest\n"
            "def test_ok():\n    assert True\n"
            "def test_gate():\n    pytest.skip('needs pandoc')\n"
            "@pytest.mark.xfail(reason='known bad')\n"
            "def test_known():\n    assert False\n")
        (tests / "test_import.py").write_text(
            "import pytest\n"
            "pytest.importorskip('absent_dependency')\n"
            "def test_never():\n    pass\n")
        # The multi-outcome shape the synthetic model above asserts. pytest
        # exits 0 for this file on its own, which is what makes the undeclared
        # teardown skip invisible to every other guard the runner has.
        (tests / "test_two_outcomes.py").write_text(
            "import pytest\n"
            "@pytest.fixture\n"
            "def skipping_teardown():\n"
            "    yield\n"
            "    pytest.skip('UNDECLARED teardown')\n"
            "@pytest.mark.xfail(reason='declared and allowed')\n"
            "def test_xfail_td(skipping_teardown):\n    assert False\n")
        report = self.root / "real.xml"
        verify.run([sys.executable, "-m", "pytest", "-q", f"--junit-xml={report}",
                    "tests"], self.root, verify.clean_env(None), check=False)
        parsed = verify.read_report(report, ["needs pandoc"])
        self.assertEqual(parsed["counts"]["total"], 5)
        found = {skip["test"].rsplit("::", 1)[-1]: skip for skip in parsed["skips"]}
        self.assertEqual(found["test_gate"]["allowed_by"], "needs pandoc")
        # An xfail reaches the report as a skip, so neutralising a failing test
        # has to be declared rather than passing quietly. Its kind says which.
        self.assertEqual(found["test_known"]["kind"], "pytest.xfail")
        self.assertIn("tests.test_shapes::test_known", parsed["unexpected_skips"])
        # The module-level skip's message is only the placeholder "collection
        # skipped"; its real reason is reachable because the text is read too.
        module = found["tests.test_import"]
        self.assertIn("collection skipped", module["reason"])
        self.assertIn("absent_dependency", module["reason"])
        # The element carrying two outcomes: pytest reported this file as
        # passing, and both of its skips are here rather than only the first.
        two = [skip for skip in parsed["skips"] if skip["test"].endswith("test_xfail_td")]
        self.assertEqual(len(two), 2)
        self.assertIn("declared and allowed", two[0]["reason"])
        self.assertIn("UNDECLARED teardown", two[1]["reason"])
        self.assertIn("tests.test_two_outcomes::test_xfail_td",
                      parsed["unexpected_skips"])
        self.assertEqual(
            verify.read_report(report, ["absent_dependency"])["unexpected_skips"],
            ["tests.test_shapes::test_gate", "tests.test_shapes::test_known",
             "tests.test_two_outcomes::test_xfail_td",
             "tests.test_two_outcomes::test_xfail_td"])

    def test_a_second_outcome_on_one_element_does_not_hide_its_skip(self):
        """pytest writes one element per test, not one child, so a test whose
        teardown disagrees with its body carries two outcomes. Reading a single
        child lets the second one through the allowlist. The two xfail shapes
        are the dangerous ones: pytest exits 0 for both, so no other guard in
        the runner fires and an undeclared skip rides out on a green run."""
        path = self.root / "report.xml"
        path.write_text(junit([
            # Measured shapes, pytest 9.0.3. An xfail whose teardown skips.
            ("tests.test_a", "test_xfail_td", [("skipped", "declared and allowed"),
                                               ("skipped", "UNDECLARED teardown")], ""),
            # A body skip whose teardown then errored.
            ("tests.test_b", "test_skip_td", [("skipped", "UNDECLARED body"),
                                              ("error", "teardown exploded")], ""),
            # A failing body whose teardown skipped.
            ("tests.test_c", "test_fail_td", [("failure", "assert False"),
                                              ("skipped", "UNDECLARED after failure")], ""),
            # An xfail whose teardown raised: pytest absorbs the exception and
            # writes the xfail reason twice with no error child, so this element
            # contributes two rows and nothing to the errors column.
            ("tests.test_d", "test_xfail_boom", [("skipped", "UNDECLARED xfail"),
                                                 ("skipped", "UNDECLARED xfail")], ""),
        ]))
        report = verify.read_report(path, ["declared and allowed"])
        self.assertEqual(report["unexpected_skips"],
                         ["tests.test_a::test_xfail_td", "tests.test_b::test_skip_td",
                          "tests.test_c::test_fail_td", "tests.test_d::test_xfail_boom",
                          "tests.test_d::test_xfail_boom"])
        # Both reasons on the xfail element are recorded, not just the first.
        self.assertEqual([skip["reason"] for skip in report["skips"]
                          if skip["test"].endswith("test_xfail_td")],
                         ["declared and allowed", "UNDECLARED teardown"])
        # Each element is still counted once, under its most severe outcome, so
        # the columns continue to sum to the number of elements. The absorbed
        # teardown exception is invisible here by construction: the element has
        # no error child to count, which is why errors stays at one.
        self.assertEqual(report["counts"], {"total": 4, "failures": 1, "errors": 1,
                                            "skipped": 2, "passed": 0})
        # Control: declaring every reason leaves nothing unexpected, so the
        # assertions above fail for the undeclared skips and not for the shape.
        self.assertEqual(
            verify.read_report(path, ["declared and allowed", "UNDECLARED"])
            ["unexpected_skips"], [])

    def test_report_counts_classify_every_outcome(self):
        path = self.root / "report.xml"
        path.write_text(junit([("tests.test_a", "test_ok", None, ""),
                               ("tests.test_a", "test_bad", "failure", "assert False"),
                               ("tests.test_b", "test_setup", "error", "fixture blew up"),
                               ("tests.test_c", "test_tool", "skipped", "needs pandoc")]))
        report = verify.read_report(path, [])
        self.assertEqual(report["counts"], {"total": 4, "failures": 1, "errors": 1,
                                            "skipped": 1, "passed": 1})
        self.assertEqual(report["unexpected_skips"], ["tests.test_c::test_tool"])

    def test_allowlist_accepts_a_declared_test_or_reason_and_nothing_else(self):
        path = self.root / "report.xml"
        path.write_text(junit([
            ("tests.test_a", "test_tool", "skipped", "needs pandoc"),
            ("tests.test_b", "test_fork", "skipped", "fork is POSIX-only"),
            ("tests.test_c", "test_new", "skipped", "temporarily disabled")]))
        report = verify.read_report(path, ["needs pandoc", "tests.test_b::test_fork"])
        self.assertEqual([skip["allowed_by"] for skip in report["skips"]],
                         ["needs pandoc", "tests.test_b::test_fork", None])
        self.assertEqual(report["unexpected_skips"], ["tests.test_c::test_new"])
        self.assertEqual(report["counts"]["skipped"], 3)

    def test_skip_reason_fuses_message_and_text_without_repeating_either(self):
        """pytest splits a skip reason across the attribute and the element text,
        and which half carries the reason depends on how the skip was raised.
        This is synthetic on purpose: the real-pytest test below covers the same
        ground but is skipped on a host without pytest, which is exactly the host
        this model exists for."""
        path = self.root / "report.xml"
        path.write_text(junit([
            # A module-level importorskip: placeholder attribute, real reason
            # in the text. Both halves must survive.
            ("tests.test_import", "tests.test_import", "skipped",
             "collection skipped", "Skipped: could not import 'absent_dependency'"),
            # A plain skip: pytest repeats the message inside the text, prefixed
            # by the file and line. Reading both naively would print it twice.
            ("tests.test_a", "test_tool", "skipped", "needs pandoc",
             "/tree/tests/test_a.py:12: needs pandoc"),
            # Text only, which is how an xfail arrives.
            ("tests.test_b", "test_known", "skipped", "", "expected to fail")]))
        reasons = [skip["reason"] for skip in verify.read_report(path, [])["skips"]]
        self.assertEqual(reasons[0],
                         "collection skipped Skipped: could not import 'absent_dependency'")
        self.assertEqual(reasons[1], "/tree/tests/test_a.py:12: needs pandoc")
        self.assertEqual(reasons[2], "expected to fail")
        # The placeholder alone must not be the only rule that matches, since
        # that rule blanket-accepts every module-level import failure.
        allowed = verify.read_report(path, ["absent_dependency"])
        self.assertEqual(allowed["skips"][0]["allowed_by"], "absent_dependency")

    def test_absent_unreadable_or_empty_report_is_an_error(self):
        with self.assertRaisesRegex(verify.VerificationError, "wrote no report"):
            verify.read_report(self.root / "missing.xml", [])
        empty = self.root / "empty.xml"
        empty.write_text('<?xml version="1.0"?><testsuites>'
                         '<testsuite name="pytest" /></testsuites>')
        with self.assertRaisesRegex(verify.VerificationError, "no test cases"):
            verify.read_report(empty, [])
        broken = self.root / "broken.xml"
        broken.write_text("<testsuites>")
        with self.assertRaisesRegex(verify.VerificationError, "Unreadable"):
            verify.read_report(broken, [])

    def test_authorize_repo_injects_scoped_safe_directory(self):
        env = verify.clean_env(None)
        target = self.root / "some-repo"
        verify._authorize_repo(env, target)
        self.assertEqual(env["GIT_CONFIG_COUNT"], "1")
        self.assertEqual(env["GIT_CONFIG_KEY_0"], "safe.directory")
        self.assertEqual(env["GIT_CONFIG_VALUE_0"], str(target.resolve()))

    def test_authorize_repo_appends_to_existing_config_count(self):
        env = verify.clean_env(None)
        env["GIT_CONFIG_COUNT"] = "2"
        env["GIT_CONFIG_KEY_0"] = "core.autocrlf"
        env["GIT_CONFIG_VALUE_0"] = "false"
        env["GIT_CONFIG_KEY_1"] = "user.name"
        env["GIT_CONFIG_VALUE_1"] = "test"
        verify._authorize_repo(env, self.root)
        self.assertEqual(env["GIT_CONFIG_COUNT"], "3")
        self.assertEqual(env["GIT_CONFIG_KEY_2"], "safe.directory")
        self.assertEqual(env["GIT_CONFIG_VALUE_2"], str(self.root.resolve()))
        self.assertEqual(env["GIT_CONFIG_KEY_0"], "core.autocrlf")

    def test_authorize_repo_resolves_the_path(self):
        nested = self.root / "a" / ".." / "b"
        env = {}
        verify._authorize_repo(env, nested)
        self.assertEqual(env["GIT_CONFIG_VALUE_0"], str((self.root / "b").resolve()))

    def test_bad_hash_creates_no_evidence_directory(self):
        source = self.root / "input.patch"
        source.write_bytes(b"candidate")
        args = argparse.Namespace(repo=self.root, base="HEAD", patch=source,
                                  sha256="0" * 64, python=sys.executable,
                                  timeout=None, allow_skip=[], min_tests=None,
                                  evidence_root=self.root / "evidence")
        with self.assertRaisesRegex(verify.VerificationError, "SHA256"):
            verify.verify(args)
        self.assertFalse(args.evidence_root.exists())
        # An empty rule is a substring of every reason, so it would silently
        # turn the allowlist into an unconditional accept. A rule that is only
        # whitespace does the same job, since a reason almost always has a space.
        args.sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
        for rule in ("", "   ", "\t"):
            with self.subTest(rule=repr(rule)):
                args.allow_skip = [rule]
                with self.assertRaisesRegex(verify.VerificationError,
                                            "empty --allow-skip"):
                    verify.verify(args)
                self.assertFalse(args.evidence_root.exists())


class RealCandidateTests(unittest.TestCase):
    """Real git, real patches, real interpreter, real caches. Only the virtualenv
    build is replaced, so every other guard has to hold on its own."""

    passing = [("tests.test_smoke", "test_smoke", None, ""),
               ("tests.test_added", "test_added", None, "")]

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="candidate tests ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.stubs = stub_modules(self.root / "stubs")
        self.record = self.root / "pytest-invocation.json"
        self.report = self.root / "report.xml"
        self.report.write_text(junit(self.passing))
        self.exit_code = 0
        self.mutate = None
        self.head = self.build_repo()

    def git(self, *arguments):
        env = verify.clean_env(None)
        env["HOME"] = str(self.root)
        result = subprocess.run(["git", *arguments], cwd=self.repo, env=env,
                                capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        return result.stdout.decode().strip()

    def build_repo(self):
        self.repo = repo = self.root / "repo"
        (repo / "src/pyteman/runner").mkdir(parents=True)
        (repo / "tests").mkdir()
        (repo / "tools").mkdir()
        (repo / "pyproject.toml").write_text(
            '[project]\nname = "pyteman"\nversion = "0"\n')
        (repo / "src/pyteman/__init__.py").write_text("VERSION = '0'\n")
        (repo / "src/pyteman/runner/__init__.py").write_text("")
        (repo / "src/pyteman/runner/matrix.py").write_text("def plan():\n    return []\n")
        (repo / "tests/test_smoke.py").write_text("def test_smoke():\n    assert True\n")
        release = repo / "tools/release.sh"
        release.write_text("#!/bin/sh\nexit 0\n")
        release.chmod(0o755)
        self.git("-c", "init.defaultBranch=main", "init", "-q", ".")
        self.git("add", "-A")
        self.git(*GIT_IDENTITY, "commit", "-q", "-m", "base")
        return self.git("rev-parse", "HEAD")

    def test_host_git_config_cannot_rewrite_the_base_archive(self):
        home = self.root / "host-config"
        home.mkdir()
        (home / ".gitconfig").write_text("[core]\n    autocrlf = true\n")
        with patch.dict(os.environ, {"HOME": str(home)}):
            cleaned = verify.clean_env(None)
        inherited = dict(cleaned)
        inherited.pop("GIT_CONFIG_GLOBAL", None)
        content = b"def plan():\n    return []\n"
        for label, env, expected in (("clean", cleaned, content),
                                     ("host", inherited, content.replace(b"\n", b"\r\n"))):
            with self.subTest(config=label):
                archive = verify.run(["git", "archive", self.head], self.repo, env).stdout
                tree = self.root / label
                tree.mkdir()
                verify.extract_export(archive, tree)
                self.assertEqual((tree / "src/pyteman/runner/matrix.py").read_bytes(),
                                 expected)

    def environment(self, python, tree, root, env, timeout=None):
        home = root / "fakevenv/bin"
        home.mkdir(parents=True)
        executable = home / "python"
        executable.write_text(SHIM % {
            "real": sys.executable, "record": self.record, "report": self.report,
            "mutate": tree / self.mutate if self.mutate else root / "no-mutation",
            "src": tree / "src", "stubs": self.stubs, "code": self.exit_code})
        executable.chmod(0o755)
        return executable

    def candidate(self, source, allow_skip=(), min_tests=None):
        args = argparse.Namespace(
            repo=self.repo, base=self.head, patch=source,
            sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            python=sys.executable, timeout=120, allow_skip=list(allow_skip),
            min_tests=min_tests, trust_repo=False,
            evidence_root=self.root / "long path" / ("x" * 120))
        printed = io.StringIO()
        with patch.object(verify, "make_environment", self.environment), \
                contextlib.redirect_stdout(printed):
            code = verify.verify(args)
        # The run names its own manifest on its last line. Globbing the evidence
        # root would return whichever directory os.scandir listed first, and
        # several calls share that root within one test, so a later call would
        # assert against an earlier call's manifest on any filesystem that does
        # not happen to list in creation order.
        reported = json.loads(printed.getvalue().splitlines()[-1])
        self.assertEqual(reported["exit_code"], code)
        manifest_path = Path(reported["manifest"])
        return code, json.loads(manifest_path.read_text()), manifest_path.parent

    def added_test(self):
        return new_file_patch(self.root / "candidate.patch", "tests/test_added.py",
                              "def test_added():\n    assert True\n")

    def report_with_skip(self, reason="needs pandoc"):
        self.report.write_text(junit(self.passing + [
            ("tests.test_report", "test_pandoc", "skipped", reason)]))

    def test_candidate_is_exported_patched_installed_and_reported(self):
        code, manifest, evidence = self.candidate(self.added_test())
        tree = evidence / "tree"
        self.assertEqual(code, 0, manifest.get("error"))
        self.assertTrue(manifest["tests_passed"])
        self.assertEqual(manifest["review"], "not_performed")
        self.assertEqual(manifest["base"], self.head)
        self.assertEqual(manifest["interpreter"]["requested"], sys.executable)
        # The patch reached the export, and the export is what was imported.
        self.assertIn("def test_added", (tree / "tests/test_added.py").read_text())
        self.assertIn("tests/test_added.py", manifest["source_hashes"])
        self.assertEqual(manifest["patch_destinations"], ["tests/test_added.py"])
        self.assertEqual(manifest["identity"]["package"],
                         str((tree / "src/pyteman").resolve()))
        # git archive preserves the mode bits the repository recorded.
        self.assertTrue((tree / "tools/release.sh").stat().st_mode & 0o111)
        # The suite ran on the environment interpreter, in the export, with its
        # own bytecode cache and no inherited path.
        invocation = json.loads(self.record.read_text())
        self.assertEqual(invocation["cwd"], str(tree))
        self.assertEqual(invocation["cache"], str(evidence / "test-bytecode"))
        self.assertIsNone(invocation["pythonpath"])
        self.assertIn(f"--junit-xml={evidence / 'pytest-report.xml'}",
                      invocation["arguments"])
        self.assertEqual(list(tree.rglob("__pycache__")), [])
        self.assertTrue((evidence / "bytecode").is_dir())
        self.assertEqual(manifest["report"]["counts"],
                         {"total": 2, "failures": 0, "errors": 0, "skipped": 0,
                          "passed": 2})

    def test_shadow_package_added_by_the_patch_is_refused(self):
        for name in ("pyteman/__init__.py", "tests/pyteman/__init__.py"):
            with self.subTest(name=name):
                source = new_file_patch(self.root / "candidate.patch", name,
                                        "VERSION = 'shadow'\n")
                code, manifest, _ = self.candidate(source)
                self.assertNotEqual(code, 0)
                self.assertIn("Package copies outside src", manifest["error"])
                self.assertFalse(manifest["tests_passed"])
                self.assertFalse(self.record.exists(),
                                 "the suite must not run unverified")

    def test_shadow_package_is_caught_again_without_the_layout_guard(self):
        """The layout guard refuses a shadow from the file listing, the probe
        refuses it from the import system. Remove the first to show the second
        holds on its own, in the directory the suite is about to run in."""
        source = new_file_patch(self.root / "candidate.patch", "pyteman/__init__.py",
                                "VERSION = 'shadow'\n")
        with patch.object(verify, "check_package_layout", lambda tree: None):
            code, manifest, _ = self.candidate(source)
        self.assertNotEqual(code, 0)
        self.assertIn("Wrong candidate import", manifest["error"])
        self.assertFalse(self.record.exists(), "the suite must not run unverified")

    def test_symlink_added_by_the_patch_is_refused(self):
        source = new_file_patch(self.root / "candidate.patch", "tests/link.py",
                                "/etc/passwd", mode="120000")
        code, manifest, _ = self.candidate(source)
        self.assertNotEqual(code, 0)
        self.assertIn("symlinks are unsupported", manifest["error"])
        self.assertFalse(self.record.exists())

    def test_failing_suite_propagates_its_own_exit_code(self):
        self.exit_code = 3
        self.report.write_text(junit([("tests.test_added", "test_added",
                                       "failure", "assert False")]))
        code, manifest, _ = self.candidate(self.added_test())
        self.assertEqual(code, 3)
        self.assertEqual(manifest["pytest_exit_code"], 3)
        self.assertFalse(manifest["tests_passed"])
        self.assertEqual(manifest["report"]["counts"]["failures"], 1)

    def test_undeclared_skip_refuses_a_clean_exit(self):
        self.report_with_skip()
        code, manifest, _ = self.candidate(self.added_test())
        self.assertNotEqual(code, 0)
        self.assertEqual(manifest["pytest_exit_code"], 0)
        self.assertFalse(manifest["tests_passed"])
        self.assertEqual(manifest["report"]["unexpected_skips"],
                         ["tests.test_report::test_pandoc"])
        self.assertIn("Skips outside the declared allowlist", manifest["error"])

    def test_declared_skip_is_accepted_and_recorded_with_its_reason(self):
        self.report_with_skip()
        code, manifest, _ = self.candidate(self.added_test(),
                                           allow_skip=["needs pandoc"])
        self.assertEqual(code, 0, manifest.get("error"))
        self.assertTrue(manifest["tests_passed"])
        self.assertEqual(manifest["allowed_skips"], ["needs pandoc"])
        self.assertEqual(manifest["report"]["skips"],
                         [{"test": "tests.test_report::test_pandoc", "kind": "",
                           "reason": "needs pandoc", "allowed_by": "needs pandoc"}])
        self.assertEqual(manifest["report"]["counts"]["skipped"], 1)

    def test_a_suite_that_stops_being_collected_refuses_a_clean_exit(self):
        """Deselection leaves no skip and no failure, so only the floor sees it."""
        code, manifest, _ = self.candidate(self.added_test(), min_tests=2)
        self.assertEqual(code, 0, manifest.get("error"))
        self.report.write_text(junit(self.passing[:1]))
        code, manifest, _ = self.candidate(self.added_test(), min_tests=2)
        self.assertNotEqual(code, 0)
        self.assertEqual(manifest["pytest_exit_code"], 0)
        self.assertFalse(manifest["tests_passed"])
        self.assertEqual(manifest["min_tests"], 2)
        self.assertIn("Only 1 tests were collected", manifest["error"])

    def test_suite_without_a_report_refuses_a_clean_exit(self):
        self.report.unlink()
        code, manifest, _ = self.candidate(self.added_test())
        self.assertNotEqual(code, 0)
        self.assertEqual(manifest["pytest_exit_code"], 0)
        self.assertFalse(manifest["tests_passed"])
        self.assertIn("wrote no report", manifest["error"])
        # The run a reader most wants the integrity record for is the one that
        # ended badly, so the rehash is taken before the report is read.
        self.assertEqual(manifest["source_hashes_after"], manifest["source_hashes"])

    def test_sources_rewritten_while_the_suite_ran_are_not_certified(self):
        self.mutate = "src/pyteman/runner/matrix.py"
        code, manifest, _ = self.candidate(self.added_test())
        self.assertNotEqual(code, 0)
        self.assertFalse(manifest["tests_passed"])
        self.assertIn("changed during verification", manifest["error"])

    def _foreign_clean_env_factory(self):
        """Return a clean_env wrapper that injects GIT_TEST_ASSUME_DIFFERENT_OWNER.
        Captures the real function before patching to avoid recursion."""
        real = verify.clean_env
        def wrapper(cache):
            env = real(cache)
            env["GIT_TEST_ASSUME_DIFFERENT_OWNER"] = "1"
            return env
        return wrapper

    def test_foreign_owned_repo_is_refused_with_a_clear_message(self):
        """Without --trust-repo, a foreign-owned repo produces a specific
        error naming --trust-repo, not a raw Git exit code."""
        source = self.added_test()
        args = argparse.Namespace(
            repo=self.repo, base=self.head, patch=source,
            sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            python=sys.executable, timeout=120, allow_skip=[],
            min_tests=None, trust_repo=False,
            evidence_root=self.root / "evidence-foreign")
        foreign = self._foreign_clean_env_factory()
        with patch.object(verify, "clean_env", side_effect=foreign):
            with self.assertRaisesRegex(verify.VerificationError,
                                        "owned by a different OS user") as ctx:
                verify.verify(args)
        self.assertIn("--trust-repo", str(ctx.exception))
        self.assertFalse(args.evidence_root.exists(),
                         "no evidence directory should be created for a refused repo")

    def test_trust_repo_authorizes_a_foreign_owned_repository(self):
        """With --trust-repo, the runner proceeds past the ownership check
        and the safe.directory authorization is scoped to the exact path."""
        source = self.added_test()
        args = argparse.Namespace(
            repo=self.repo, base=self.head, patch=source,
            sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            python=sys.executable, timeout=120, allow_skip=[],
            min_tests=None, trust_repo=True,
            evidence_root=self.root / "evidence-trusted")
        foreign = self._foreign_clean_env_factory()
        printed = io.StringIO()
        with patch.object(verify, "clean_env", side_effect=foreign), \
                patch.object(verify, "make_environment", self.environment), \
                contextlib.redirect_stdout(printed):
            code = verify.verify(args)
        reported = json.loads(printed.getvalue().splitlines()[-1])
        manifest = json.loads(Path(reported["manifest"]).read_text())
        self.assertEqual(code, 0, manifest.get("error"))
        self.assertTrue(manifest["tests_passed"])


if __name__ == "__main__":
    unittest.main()
