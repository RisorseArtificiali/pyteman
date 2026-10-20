# Packaging

What the two build artifacts carry, why they carry it, and how to check that
they still do. The checks are executable and live in `tests/test_packaging.py`;
this document records the reasoning and the commands, which no test can hold.

## The two artifacts have different jobs

The **wheel** is what gets installed. It carries the importable package and
nothing else: `pyteman/` with its subpackages, `py.typed`, and the license in
`dist-info/`. No tests, no documents, no examples. Anything else in a wheel is
installed into somebody's environment whether they wanted it or not.

The **sdist** is the source. It carries everything needed to build the wheel
and everything needed to check that the wheel is right, which means the whole
suite, the documents the suite reads, and the reproducers.

The test that pins the wheel's half of this is the sharper of the two. The
activation hook is `src/pyteman/sitecustomize.py` and ships as
`pyteman/sitecustomize.py`, nested. A top-level `sitecustomize.py` is imported
by every Python process in the environment, so publishing one would change the
behaviour of programs that never installed this package.

## Why MANIFEST.in exists

Without it, setuptools falls back to a default inherited from distutils: an
optional glob `tests/test*.py`. That glob matches `test_*.py` and nothing else.
The consequence measured on 2026-09-17, before the manifest was written, was an
sdist carrying nineteen test modules and none of `tests/conftest.py`,
`tests/target_mod.py` or `tests/integrity_corpus.py`, and no `docs/` at all.
Installing that sdist into a clean environment and running the suite from the
extracted archive gave five collection errors:

    ModuleNotFoundError: No module named 'integrity_corpus'   (three modules)
    ModuleNotFoundError: No module named 'target_mod'
    FileNotFoundError: .../docs/rules.md

So the inclusion that did work was an accident of a default rather than a
decision. That is the argument for stating the contents explicitly, and it is
also the argument for stating them as a whitelist: the working tree holds a
task tracker, editor configuration and caches, and an artifact assembled by
exclusion acquires each new one of those by default.

## Why the grants name directories rather than extensions

The obvious way to write the manifest is `recursive-include tests *.py`, and it
produces a correct archive today. It also rebuilds the defect it was written to
fix, one extension over, in a form that is harder to see because a test appears
to be watching.

The mechanism is a shared predicate. A test defending that line derives its
expectation from the tree, and the natural derivation is `glob("*.py")`, the
same suffix filter. Add `tests/fixtures.json` and it is missing from the archive
and missing from the expectation in the same instant, so the assertion stays
green while the sdist is broken. Measured on 2026-09-17 by building an sdist
from a copy carrying the extension-filtered manifest and that one added file:

    fixtures.json in the archive : False
    OLD predicate (subset, .py)  : PASS
    NEW predicate (equality, all): FAIL, missing ['tests/fixtures.json']

So the grants are written `recursive-include tests *` and the expectation is
derived unfiltered, compared by equality rather than containment. Equality is
not symmetry for its own sake. Containment catches the manifest omitting a
file; equality also catches it carrying one the tree does not have, which is a
live hazard here rather than a hypothetical, because setuptools unions any
`SOURCES.txt` it finds into the archive.

Widening the patterns changed no release content. At the time of the change
`tests/` held twenty three files, all `.py`; `docs/` held four, all `.md`; and
`examples/` held eleven `.py`, `.yaml` and `.md` files. The wide form ships the
same bytes as the narrow one and fails differently in the future, which was the
entire point.

The counterweight is that whatever sits in a granted directory now ships. The
`global-exclude` line at the bottom of `MANIFEST.in` is therefore load-bearing
rather than decorative: it is the half of the design that lets the grants stay
wide, and deleting it turns two of these tests red.

The `prune` lines beneath it are a different thing, and conflating the two is
worth avoiding because it makes the design look like it rests on four lines that
do nothing. They remove nothing today, since no grant reaches the directories
they name, and stripping all four produces a byte-identical file list. They are
kept against a future grant widened toward the repository root, on the reasoning
that publishing is irreversible. An unnoticed redundant prune costs a line,
while a leaked tracker cannot be withdrawn once it is on an index.

## Which residue patterns, and why the backups need two of them

That line is not a list of file types somebody happened to like. Each pattern is
there because something produced one here, and the two backup patterns are two
rather than one for a reason that had to be measured.

`global-exclude` is not a free-floating substring match. distutils calls
`FileList.exclude_pattern(pattern, anchor=False)` and compiles the glob through
`glob_to_re`, which appends `\z`, so a pattern is free at the start of the path
and anchored at its end. Measured on 2026-09-17 against setuptools 80.10.2 by
compiling the real expressions out of `setuptools._distutils.filelist` rather
than by reading the manifest format documentation, X meaning the file is kept
out of the archive:

    pattern     docs/x.md.bak.1789617984   docs/notes.bak   docs/notes.bakery.md
    *.bak       .                          X                .
    *.bak.*     X                          .                .
    *.bak*      X                          X                X

The first column is the one that matters, because it is the only form this
repository has ever produced. The working rule that a file is copied before it
is overwritten writes `file.bak.$(date +%s)`, and all three backups present in
the tree on 2026-09-17 have that shape. `*.bak` on its own would have looked
like the fix and caught none of them.

The third row is why the pair is not collapsed into the single pattern that
covers both forms. `*.bak*` also removes `notes.bakery.md`, and a wanted file
dropped from a release is the same defect as an unwanted one added, minus the
symptom: the archive is smaller and nothing about it looks wrong. That case is
planted as `PLANTED_KEEPER` and asserted in the second half of
`test_the_sdist_carries_no_residue`, so the
choice between the pair and the single pattern is executed rather than argued.

`*.orig` and `*.rej` are deliberately absent. No conflict residue has ever
appeared in this tree, and a pattern copied out of somebody else's list is a
pattern nobody has measured. Adding either means adding its planted file at the
same time, or `test_every_excluded_pattern_is_exercised_by_a_planted_file` goes
red saying exactly that.

## Why the suite did not see the backups

Worth recording precisely, because the obvious explanation is wrong and it aims
the correction at the wrong place.

A backup left in `docs/` shipped, and `tests/test_packaging.py` passed all
sixteen of its checks with that file in the archive. Measured on 2026-09-17 by
restoring the pre-fix manifest and suite into a copy and planting one backup in
its `docs/`: 16 passed, and the archive carries

    pyteman-0.1.0/docs/coverage.md.bak.1789632119

The tempting reading is that the equality check is blind because it compares the
archive against a derivation of the tree, which makes the tree both the input
and the oracle. That is not what happened, and equality would have caught a
divergence between the two. What happened is narrower. `_is_residue` did not
know the `.bak` forms, so the file was counted on both sides at once and the
equality held honestly.

The correction therefore belongs in the detector rather than in the derivation,
and that detector is kept by hand rather than read out of `MANIFEST.in`. Derived
from the line it is checking, it could only ever ask whether setuptools obeys
that line. It could never ask whether the line is right, which is the question
that was open here. The same copy with the two patterns in place builds a
seventy seven entry archive with no `.bak` entry in it at all.

## The patterns match the filesystem, not git

Two durable reasons, neither of which expires. An sdist has to be buildable
from an export carrying no `.git` at all, which is the normal state of a
distribution build root. And deriving contents from version control would
impose a build-time VCS dependency on every downstream packager. That several
test modules and two of the documents happen to be uncommitted right now is a
corroborating example, not the argument.

## Verifying it, offline

No network is involved at any step. The `build` frontend is not required: the
backend is called directly, so there is no isolated environment to populate.
The cost of calling the backend directly is that nothing provisions it, so the
interpreter running this has to carry setuptools itself.

Build from a copy, never from the working tree. Two reasons, and the second one
is the one that bites. A build writes `build/` and rewrites `*.egg-info` in
place. And setuptools **reads** `SOURCES.txt` out of an existing `*.egg-info`
and unions its contents into the archive, so building over a stale one measures
a cache written by an earlier manifest instead of the manifest on disk now.

    python -c "
    import shutil, os, sys
    shutil.copytree('.', '/tmp/pkg/checkout', ignore=shutil.ignore_patterns(
        '.git', '*.egg-info', 'build', 'dist'))
    os.chdir('/tmp/pkg/checkout'); sys.path.insert(0, '')
    from setuptools import build_meta as b
    print(b.build_sdist('/tmp/pkg')); print(b.build_wheel('/tmp/pkg'))"

That exclusion list is short on purpose, and the omissions are the interesting
part. `__pycache__`, `.pytest_cache`, `backlog/` and `.claude/` are copied
deliberately, because the checks that assert their absence from the archive are
vacuous if they were never present in the tree the archive was built from. An
artifact test that tidies up first proves only that a clean tree produces a
clean archive.

The fixture in `tests/test_packaging.py` is the executable form of this build,
and it is the copy to trust about the build if the two ever disagree. It is not
the copy to trust about the whole sequence: it stops at the archive and never
installs one, which is the half `scripts/verify_artifacts.py` exists for. The
section below draws that line. It goes one step further
than the commands above: it writes one file per pattern in the `global-exclude`
line into the copy before building. Relying on whatever bytecode happens to be
lying around would make that check depend on `PYTHONDONTWRITEBYTECODE`, on
`python -B`, and on whether the container is fresh, none of which say anything
about the manifest. Planting the residue makes the check measure the exclusion
every time it runs.

Then install the sdist into an environment that has no other route to this
package, and run the suite from the extracted archive. That environment needs
setuptools as well, which is easy to miss because the build needed it for a
different reason and the failure names neither packaging nor this project: pip
calls the backend's metadata hook even under `--no-build-isolation`, so a venv
without one stops at `BackendUnavailable: Cannot import 'setuptools.build_meta'`.
`--system-site-packages` is what supplies it, which means the interpreter
creating the venv has to be one that carries it. Naming that interpreter by path
rather than as a bare `python` is the difference between the recipe working and
it failing for a reason that has nothing to do with the archive.

    /usr/bin/python3 -m venv --system-site-packages /tmp/pkg/venv
    /tmp/pkg/venv/bin/pip install --no-index --no-deps --no-build-isolation \
        /tmp/pkg/pyteman-0.1.0.tar.gz
    mkdir -p /tmp/pkg/extracted
    tar xzf /tmp/pkg/pyteman-0.1.0.tar.gz -C /tmp/pkg/extracted
    cd /tmp/pkg/extracted/pyteman-0.1.0
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /tmp/pkg/venv/bin/python -m pytest -q -rs

The environment is the part to get right, and getting it wrong produces a
green run that proves nothing. An editable install of this project puts the
checkout's `src/` on `sys.path`, so a suite run against it imports from the
checkout and passes whatever the archive contains. Check provenance rather than
assuming it, and name the interpreter explicitly, since a bare `python` here
would interrogate the ambient one and answer a question nobody asked:

    /tmp/pkg/venv/bin/python -c "import pyteman; print(pyteman.__file__)"

It has to name a path inside the target environment. If it names the checkout,
the run is measuring the wrong thing.

`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` is unrelated to packaging. It is here
because a pytest plugin installed globally on the development machine injects
an autouse fixture into every test.

## The same recipe, executable

`scripts/verify_artifacts.py` is the whole sequence above in one command, and
it is the copy to run rather than pasting the pieces:

    /usr/bin/python3.14 scripts/verify_artifacts.py

It builds both artifacts from a clean snapshot, installs each into its own
environment, checks provenance from the directory the suite will run in, and
runs the suite from the extracted sdist against both. It extracts the sdist
twice, once per environment, so that no state at all is shared between the two
runs; at 0.03 seconds an extraction there is no reason to economise here.

Against the wheel it adds one check the sdist does not need: that the nested
activation hook loads from the installed package and stays inert with no
`PYTEMAN_RULES` set. That check asks for the loaded module's identity rather
than its presence, and the difference is the whole value of it. `sitecustomize`
is a name any environment may already own, and Debian and Ubuntu do own it, at
`/usr/lib/python3/dist-packages/sitecustomize.py`, which these environments
inherit through `--system-site-packages`. Measured on 2026-09-17 against a wheel
with `pyteman/sitecustomize.py` deleted and a foreign top-level hook in its
place, a presence test reports exactly the pair it accepts as success:

    sitecustomize in sys.modules: True | pyteman in sys.modules: False

Comparing `sys.modules['sitecustomize'].__file__` against
`<purelib>/pyteman/sitecustomize.py` reports the same case as a failure naming
both paths. This matters more here than anywhere else in the file, because
inside the extracted sdist every `TestBuiltArtifacts` check skips on
`PKG-INFO`, so this is the only thing in the run still looking at the wheel.

It refuses to start unless two preconditions hold, and it checks two
interpreters because it uses two. The interpreter running it has to carry
setuptools, since it runs the build backend itself. The site-packages that
`--system-site-packages` inherits, which is `sys.base_prefix` and NOT the
launcher when the launcher is a virtual environment, has to carry pip,
setuptools, pytest and PyYAML and must **not** carry pyteman. Every half
matters and every half is silent when wrong. Measured on 2026-09-17, the
`python3` first on `PATH` here is a linuxbrew 3.14 with pytest and no
setuptools, which is why the command above names the interpreter by path.

Confirming it is not vacuous costs one command, and it is the same technique
the suite gets. Copy the tree, delete `MANIFEST.in`, run the script from the
copy. Measured on 2026-09-17 that exits 1 with five collection errors naming
`integrity_corpus`, `target_mod` and `docs/rules.md`, which is the defect this
whole file exists for.

`scripts/` is deliberately not granted in `MANIFEST.in`, so the script does not
ship. It builds an archive out of the tree it sits in, and inside an extracted
sdist that would measure the archive against itself, which is the same vacuity
the build checks skip for. Nothing needs to watch that boundary by hand:
`test_the_sdist_carries_no_top_level_entry_that_was_not_granted` fails the day
it starts shipping.

## In CI

`.github/workflows/tests.yml` runs the suite on 3.11 through 3.14 and then runs
the script once, in a job that deliberately does not install the package.

The install step names `setuptools` and the reason is easy to lose. A PEP 517
build provisions the backend in a throwaway environment and never in the target
one, and `ensurepip` stopped bundling setuptools after 3.11. Measured on 3.14 in
a bare venv: after `pip install -e . pytest` setuptools is not importable, the
the build checks skip, and `test_the_build_checks_cannot_be_disabled_silently`
fails. That failure is the design working. Without the guard the run would be
green while proving nothing about packaging. Adding `setuptools` to that step
turns it green honestly: 787 passed, 1 skipped on 2026-09-17.

The artifact job reports a different pair and the difference is the point: 781
passed, 7 skipped in each of the two environments. The skipped are the build
checks, skipped on `PKG-INFO` because the suite is running from inside the
extracted sdist, and they are printed rather than swallowed because the script
passes `-rs`.

## When the build checks skip, and why they say so

Two conditions turn `TestBuiltArtifacts` off. Both are announced under `-rs`,
and neither is announced without it, since pytest prints skip reasons only when
asked and this project sets no `addopts` to ask on its behalf. That is why the
guard described at the end of this section exists.

The first is running from an extracted sdist, detected by the `PKG-INFO` that
every sdist carries at its root and no checkout has. Building an archive out of
an archive would measure it against itself. The presence checks in the same file
do not skip: run from the extracted archive they are the acceptance criterion
stated directly, and they are the ones that matter there.

The second is setuptools not being importable, which is not hypothetical. On
the development machine the `python3` first on `PATH` carries pytest 9.0.3 and
no setuptools at all, because a runtime environment has no reason to hold build
tooling. Without that check, the absence arrives as a build log from a failed
subprocess, naming nothing. With it, the run says which checks did not apply
and what to install to get them back.

A skip that nobody notices is the failure mode of this whole arrangement, so
one test never skips. It first decides whether it is looking at a checkout, by
the presence of `.github/`, `.gitignore` or `backlog/`. None of those reach the
sdist, and the mechanism is worth stating precisely because it is easy to get
backwards: they are absent from the archive because no grant in `MANIFEST.in`
includes them, not because the `prune` lines remove them. Stripping all four
prunes produces a byte-identical file list, which is exactly what their own
comment says. They are kept against a future grant that would reach that far,
and they are not what the guard stands on.

Having established it is in a checkout, the guard then requires both markers to
be honest: no `PKG-INFO` at the root, and setuptools importable. Either one
alone would leave the build checks silently skipped in a green run.

## Confirming the checks are not vacuous

A packaging test that has never failed is a decoration. The cheap way to see
these ones work is to break a copy and watch, which takes about a second:

    rsync -a --exclude .git --exclude '*.egg-info' --exclude build \
        --exclude dist . /tmp/pkg/broken/
    rm /tmp/pkg/broken/MANIFEST.in
    cd /tmp/pkg/broken
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_packaging.py -q

Measured on 2026-09-17 that gives six failures: one per granted directory naming
the files that went missing, the top level check, the cross check that goes
looking for the manifest it can no longer read, and the residue check, which
passes its first half and fails its second because a build without a manifest
stops shipping the keeper too. Adding a file with an unexpected
extension under `tests/` is the other half of the check and is described above.

## Known residue

The README's references do not resolve on the package page. `[LICENSE](LICENSE)`
and the `docs/*.md` citations are embedded in the wheel's `METADATA` as the
long description, which is what PyPI renders, and there is no `LICENSE` or
`docs/` beside that page. In the sdist they all resolve. TASK-105 holds the
fix, which is to make them absolute repository URLs.

Two gaps sit outside this file's reach and are tracked separately. The release
workflow never runs these checks before publishing (TASK-108), and the sdist
declares no test requirements for whoever receives it (TASK-109).
