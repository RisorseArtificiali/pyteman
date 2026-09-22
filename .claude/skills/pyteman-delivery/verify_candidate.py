#!/usr/bin/env python3
"""Verify a trusted candidate in a new export and environment, never in place."""

import argparse
import hashlib
import importlib.machinery
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
import tempfile
from xml.etree import ElementTree


class VerificationError(Exception):
    pass


PROBE_DEPENDENCIES = ("setuptools", "pytest", "yaml")

# Imported by the candidate's own interpreter, in the directory the suite runs in.
IDENTITY_PROBE = """
import importlib.util, json, pathlib, sys
for name in %r:
    if importlib.util.find_spec(name) is None:
        raise RuntimeError('Missing verification dependency: ' + name)
import pyteman
actual = pathlib.Path(pyteman.__file__).resolve().parent
expected = pathlib.Path(sys.argv[1]).resolve() / 'src' / 'pyteman'
if actual != expected:
    raise RuntimeError(f'Wrong candidate import: {actual}, expected {expected}')
print(json.dumps({'python': sys.version, 'executable': sys.executable,
                  'package': str(actual)}))
""" % (PROBE_DEPENDENCIES,)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def clean_env(cache):
    """Drop activation and ambient overrides. A cache of None forbids bytecode.
    Three of these are interpreter behaviour switches rather than path settings,
    and each disarms a guard this runner depends on. PYTHONOPTIMIZE removes
    `assert` from every module the library compiles, while pytest rewrites the
    asserts in test files and keeps them, so an inherited value turns a failing
    suite green and says so only in a warning this runner never reads.
    PYTHONSAFEPATH drops the leading current directory from `sys.path`, so the
    identity probe stops seeing a shadow package that the suite still imports:
    pytest inserts the rootdir itself, which `safe_path` does not suppress.
    Measured, with a `pyteman/` at the export root and a root conftest, the probe
    reported the installed package while the suite imported the shadow, which is
    precisely the disagreement the probe exists to detect. PYTHONINSPECT leaves
    every child in the REPL reading the operator's terminal once its code has
    run, which stalls the first command."""
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(("GIT_", "PYTEMAN_")) or key in {
            "PYTHONPATH", "PYTHONHOME", "PYTHONPYCACHEPREFIX", "VIRTUAL_ENV",
            "PYTHONDONTWRITEBYTECODE", "PYTHONOPTIMIZE", "PYTHONWARNINGS",
            "PYTHONSAFEPATH", "PYTHONINSPECT",
            "PYTEST_ADDOPTS", "PYTEST_PLUGINS",
        }:
            env.pop(key, None)
    # Unsetting GIT_* alone leaves Git reading the user's and system config files.
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    if cache is None:
        env["PYTHONDONTWRITEBYTECODE"] = "1"
    else:
        env["PYTHONPYCACHEPREFIX"] = str(cache)
    return env


def run(command, cwd, env, log=None, timeout=None, check=True):
    """Run one command to completion. Output goes to a log file when given, and
    is captured otherwise. A non-zero exit fails unless the caller reads it."""
    try:
        if log is None:
            result = subprocess.run(command, cwd=cwd, env=env,
                                    capture_output=True, timeout=timeout)
        else:
            with log.open("wb") as output:
                result = subprocess.run(command, cwd=cwd, env=env, timeout=timeout,
                                        stdout=output, stderr=subprocess.STDOUT)
    except subprocess.TimeoutExpired as error:
        # Four phases run the same interpreter, so the name alone would not say
        # which one stalled. The next arguments distinguish them.
        phase = " ".join(str(part)[:40] for part in command[:3])
        detail = f": {log}" if log else ""
        raise VerificationError(f"{phase} exceeded {timeout}s{detail}") from error
    if check and result.returncode:
        detail = str(log) if log else result.stderr.decode(errors="replace")
        raise VerificationError(f"{command[0]} exited {result.returncode}: {detail}")
    return result


def safe_name(name):
    path = PurePosixPath(name)
    if (not name or path.is_absolute() or ".." in path.parts
            or ".git" in path.parts or "\\" in name):
        raise VerificationError(f"Unsafe candidate path: {name!r}")


def patch_destinations(patch, cwd, env, timeout=None):
    """Paths the patch writes. A rename reports only its destination, so this
    record is partial; git itself refuses an unsafe path before writing."""
    raw = run(["git", "apply", "--numstat", "-z", str(patch)], cwd, env,
              timeout=timeout).stdout
    names = []
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        fields = entry.split(b"\t", 2)
        if len(fields) != 3:
            raise VerificationError("Unsupported patch path encoding")
        name = os.fsdecode(fields[2])
        safe_name(name)
        names.append(name)
    if not names:
        raise VerificationError("Candidate patch has no changes")
    return names


def extract_export(archive, tree):
    with tarfile.open(fileobj=io.BytesIO(archive)) as source:
        members = source.getmembers()
        for member in members:
            safe_name(member.name)
            if not (member.isfile() or member.isdir()):
                raise VerificationError(f"Unsupported export entry: {member.name}")
        # No links or special files are accepted, and the destination is new.
        for member in members:
            target = tree / member.name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.extractfile(member) as content:
                    target.write_bytes(content.read())
                target.chmod(0o755 if member.mode & 0o111 else 0o644)


def check_links(tree):
    for path in tree.rglob("*"):
        if path.is_symlink():
            raise VerificationError(f"Candidate symlinks are unsupported: {path}")


def check_package_layout(tree):
    """Refuse a second copy of the package outside the installed source root.
    Whatever directory a process starts in leads `sys.path`, and pytest prepends
    each test file's own directory as well, so a copy anywhere else can serve the
    suite while the identity probe certifies the installed one. Listing the
    export settles every such directory at once, including any that a future
    pytest adds. The suffixes come from importlib rather than from a literal
    list, so a compiled or bytecode copy is refused on the same terms as source."""
    source = tree / "src"
    copies = set()
    for suffix in importlib.machinery.all_suffixes():
        copies |= set(tree.rglob(f"pyteman{suffix}"))
        copies |= set(tree.rglob(f"pyteman/__init__{suffix}"))
    outside = sorted(str(path.relative_to(tree)) for path in copies
                     if source not in path.parents)
    if outside:
        raise VerificationError(f"Package copies outside src: {outside}")


def snapshot(tree):
    return {str(path.relative_to(tree)): digest(path.read_bytes())
            for path in sorted(tree.rglob("*")) if path.is_file()}


def rehash(tree, expected):
    """Re-read the files the export started with. A symlink reads back as its
    target's bytes, so it is recorded as absent rather than as that content."""
    after = {}
    for name in expected:
        path = tree / name
        after[name] = (digest(path.read_bytes())
                       if path.is_file() and not path.is_symlink() else None)
    return after


def verify_snapshot(before, after):
    """Modification and deletion fail. An addition does not: an editable install
    writes its own metadata into the export."""
    changed = [name for name, value in before.items() if after[name] != value]
    if changed:
        raise VerificationError(f"Candidate files changed during verification: {changed}")


def check_identity(python, tree, cwd, env, timeout=None):
    raw = run([str(python), "-c", IDENTITY_PROBE, str(tree)], cwd, env,
              timeout=timeout).stdout
    try:
        return json.loads(raw)
    except json.JSONDecodeError as error:
        raise VerificationError(
            f"Identity probe wrote no JSON ({error}): {raw[:500]!r}") from error


def make_environment(python, tree, root, env, timeout=None):
    """A new virtualenv holding the export itself, installed editable."""
    venv = root / "venv"
    run([python, "-m", "venv", str(venv)], root, env, root / "venv.log", timeout)
    executable = venv / "bin/python"
    run([str(executable), "-m", "pip", "install", "-e", str(tree), "pytest",
         "setuptools"], root, env, root / "install.log", timeout)
    return executable


def read_report(path, allowed):
    """Counts and skip dispositions taken from pytest's own structured report."""
    if not path.is_file():
        raise VerificationError("pytest wrote no report; counts are unavailable")
    try:
        document = ElementTree.parse(path).getroot()
    except ElementTree.ParseError as error:
        raise VerificationError(f"Unreadable pytest report: {error}") from error
    # iter() descends from the root inclusive, so this reads a <testsuites>
    # document and a bare <testsuite> alike.
    cases = list(document.iter("testcase"))
    if not cases:
        raise VerificationError("pytest report holds no test cases")
    counts = {"total": len(cases), "failures": 0, "errors": 0, "skipped": 0}
    skips = []
    for case in cases:
        # One element can carry several outcomes, so every skip is read before
        # the columns are decided; a skip that shares its element with a
        # failure or an error would otherwise never reach the allowlist.
        # Measured on pytest 9.0.3, four shapes put two outcomes on one
        # element: a body skip with an exploding teardown gives [skipped,
        # error]; a failing body with a skipping teardown gives [failure,
        # skipped]; an xfail with a skipping teardown gives [skipped, skipped]
        # carrying two different reasons; and an xfail with an exploding
        # teardown gives [skipped, skipped] repeating the xfail reason, with no
        # error child at all, so that teardown's exception is absent from the
        # report and `errors` stays 0 however it is read. The last two exit 0,
        # as does a passing body with a skipping teardown, which writes a lone
        # skipped child. A fifth shape, a failing body with a failing teardown,
        # is described with the counting below. Two skipping teardowns on one
        # test do not produce two children: pytest joins their reasons into one
        # message, so an allowlist rule naming either reason accepts the pair.
        skipped_children = case.findall("skipped")
        for skipped in skipped_children:
            # A module-level importorskip puts "collection skipped" in the
            # attribute and the module and reason in the element text. Reading
            # the attribute alone would leave the placeholder as the only rule
            # that matches it, which is precisely the blanket rule this
            # allowlist exists to prevent.
            name = "::".join(part for part in (case.get("classname"), case.get("name"))
                             if part)
            message = (skipped.get("message") or "").strip()
            detail = (skipped.text or "").strip()
            reason = (detail if message and message in detail
                      else " ".join(part for part in (message, detail) if part))
            skips.append({"test": name, "kind": skipped.get("type") or "",
                          "reason": reason,
                          "allowed_by": next((rule for rule in allowed
                                              if rule in name or rule in reason), None)})
        # Each element counts once, under its most severe outcome, so the
        # columns sum to `total` and `skipped` counts elements while `skips`
        # lists reasons. Each test below asks only whether an outcome is
        # present, never which one came first. A test that fails and then
        # errors in teardown is the one case pytest writes as two elements
        # sharing a name, which inflates `total`: measured, five tests produced
        # six elements. Such a run has already failed on the failures column,
        # so `--min-tests` cannot be satisfied by the inflation alone; the
        # counts record is what overstates, not the refusal.
        if case.find("failure") is not None:
            counts["failures"] += 1
        elif case.find("error") is not None:
            counts["errors"] += 1
        elif skipped_children:
            counts["skipped"] += 1
    counts["passed"] = (counts["total"] - counts["failures"] - counts["errors"]
                        - counts["skipped"])
    return {"counts": counts, "skips": skips,
            "unexpected_skips": [skip["test"] for skip in skips
                                 if skip["allowed_by"] is None]}


def verify(args):
    repo = args.repo.resolve()
    patch_data = args.patch.resolve().read_bytes()
    if digest(patch_data) != args.sha256.lower():
        raise VerificationError("Patch SHA256 does not match expected value")
    python = shutil.which(args.python)
    if not python or not shutil.which("git"):
        raise VerificationError("Requested Python and git must be available")
    timeout = args.timeout
    # A rule is matched as a raw substring, so a blank or whitespace-only one
    # would accept every reason that happens to contain a space.
    allowed = [rule.strip() for rule in (args.allow_skip or [])]
    if not all(allowed):
        raise VerificationError("An empty --allow-skip would accept every skip")
    env = clean_env(None)
    base = run(["git", "rev-parse", "--verify", "--end-of-options",
                args.base + "^{commit}"], repo, env,
               timeout=timeout).stdout.decode().strip()
    run([python, "-c", "import venv, ensurepip"], repo, env, timeout=timeout)
    args.evidence_root.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="candidate-", dir=args.evidence_root.resolve()))
    print(f"Evidence: {root}", flush=True)
    tree = root / "tree"
    tree.mkdir()
    env = clean_env(root / "bytecode")
    env["GIT_CEILING_DIRECTORIES"] = str(root)
    patch = root / "candidate.patch"
    patch.write_bytes(patch_data)
    report = root / "pytest-report.xml"
    manifest = {"base": base, "patch_sha256": digest(patch_data), "tree": str(tree),
                "interpreter": {"requested": args.python, "resolved": python},
                "allowed_skips": allowed, "min_tests": args.min_tests,
                "timeout": timeout,
                "tests_passed": False, "review": "not_performed"}
    exit_code = 1
    try:
        manifest["patch_destinations"] = patch_destinations(patch, root, env, timeout)
        archive = run(["git", "archive", base], repo, env, timeout=timeout).stdout
        extract_export(archive, tree)
        run(["git", "apply", str(patch)], tree, env, timeout=timeout)
        check_links(tree)
        check_package_layout(tree)
        manifest["source_hashes"] = snapshot(tree)
        executable = make_environment(python, tree, root, env, timeout)
        # Certified where the suite runs, so the two agree on what `pyteman` means.
        manifest["identity"] = check_identity(executable, tree, cwd=tree, env=env,
                                              timeout=timeout)
        # Neither an inherited .pyc nor a cache populated during installation
        # is used by the test interpreter.
        env["PYTHONPYCACHEPREFIX"] = str(root / "test-bytecode")
        command = [str(executable), "-m", "pytest", "-q", "-rs",
                   f"--junit-xml={report}"]
        manifest["test_command"] = command
        result = run(command, tree, env, root / "pytest.log", timeout, check=False)
        manifest["pytest_exit_code"] = result.returncode
        exit_code = result.returncode if result.returncode >= 0 else 1
        # Recorded before the report is read, so a pytest crash that leaves no
        # usable report still says whether the candidate rewrote its own sources.
        manifest["source_hashes_after"] = rehash(tree, manifest["source_hashes"])
        verify_snapshot(manifest["source_hashes"], manifest["source_hashes_after"])
        manifest["report"] = read_report(report, allowed)
        collected = manifest["report"]["counts"]["total"]
        if args.min_tests and collected < args.min_tests:
            raise VerificationError(f"Only {collected} tests were collected, fewer "
                                    f"than the required {args.min_tests}")
        if manifest["report"]["unexpected_skips"]:
            raise VerificationError("Skips outside the declared allowlist: "
                                    + ", ".join(manifest["report"]["unexpected_skips"]))
        manifest["tests_passed"] = exit_code == 0
    except (VerificationError, OSError, ValueError, tarfile.TarError) as error:
        manifest["error"] = str(error)
        exit_code = exit_code or 1
        print(str(error), file=sys.stderr)
    finally:
        manifest["exit_code"] = exit_code
        (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        print(json.dumps({"manifest": str(root / "manifest.json"),
                          "tests_passed": manifest["tests_passed"],
                          "exit_code": exit_code}), flush=True)
    return exit_code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--patch", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--python", required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--allow-skip", action="append", metavar="TEXT",
                        help="accept a skip whose test id or reason contains TEXT. "
                             "Repeatable; any other skip refuses the run.")
    parser.add_argument("--min-tests", type=int, metavar="N",
                        help="refuse a run that collects fewer than N tests, so a "
                             "suite that quietly stops being collected is caught "
                             "the way an undeclared skip is.")
    parser.add_argument("--timeout", type=float, metavar="SECONDS",
                        help="limit for each command. Unset by default: this suite's "
                             "duration depends on the host.")
    args = parser.parse_args()
    try:
        return verify(args)
    except (VerificationError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
