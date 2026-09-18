# Coverage

What this project measures, what it refuses to promise, and why the ordinary
test run is deliberately not instrumented. The executable form is
`scripts/run_coverage.py`; this document records the reasoning and the measured
evidence, which no script can hold.

## What the check actually guarantees

Almost nothing interesting in this package runs in the process that runs the
tests. The activation hook is imported by a child at interpreter startup, the
rules fire in that child, and several of the paths worth watching end in
`os._exit`. Both of those facts break coverage in a way that is silent rather
than loud. A child that never starts measuring reports nothing, and a child that
measured everything and then called `os._exit` discards it, because that call
skips `atexit` and the write happens there.

So the acceptance criterion here is not a percentage. It is that two specific
lines, each reachable only from a child process and each ending in `os._exit`,
appear in the combined data:

    pyteman.actions._dispatch         the kill action
    pyteman.sitecustomize._refuse     the hook rejecting a process

That is a contract about two channels being alive, and it is worth being precise
about how narrow it is. It does not say that every subprocess this suite spawns
is measured, it does not say that a new call site added tomorrow is covered, and
it says nothing at all about the children that are not Python running this
package: the suite shells out to a `setuptools` build and reads documents
produced by other tools, and none of that is in scope for any setting in
`pyproject.toml`. What the check buys is that the two mechanisms which would
otherwise fail silently are both working, so that a coverage number produced
here is measuring the subprocesses rather than quietly omitting them.

One more limit, and it is the one most easily misread in the other direction.
The check asks whether a line appears in the combined data, so it is satisfied
by **any one** child that reached it. It therefore says nothing about how many
tests still exercise that channel, and it must not be read as a guard against a
shrinking suite. Measured on 2026-09-17, the two sentinels are lopsided in
exactly that respect. Ten tests in `tests/test_sitecustomize.py` drive a process
into `_refuse`, one of them parametrized, so deleting or deselecting any single
one of them leaves that sentinel reporting `ok`. The kill exit is reached by
exactly one test, `test_kill_uses_os_exit_not_systemexit`; the other callers of
`run_action` in `tests/test_actions.py` exercise the sleep, raise and pragma
actions and never cross that line.

That asymmetry is a fact about the suite rather than a property of the check,
and it cuts both ways. It means the kill sentinel is currently sensitive to the
loss of one test while the refusal sentinel is not, and it means neither
sensitivity is promised: add a second kill test tomorrow and the first sentinel
becomes as insensitive as the second. What the check certifies either way is
that the channel is alive and that data recorded behind an `os._exit` survived
the exit, which is the failure that is otherwise invisible. Test loss is a
different question with a different guard: the deselection list is fixed and
checked by name, and the ordinary matrix runs the whole suite uninstrumented.

Two witnesses rather than one, and the reason is not redundancy. Both lines are
reached only from a child, both end the process where they stand, and measured
against every broken patch list they report `MISS` together, so neither is the
sturdier of the pair and neither tells you which of the two settings went
missing. What the second one buys is the other axis, the way the child was made.
`_dispatch` (the action bodies behind `run_action`, where the kill action's
`os._exit` sits) is reached through `multiprocessing.Process`, which is
forkserver on 3.14 and fork before it. `_refuse` is reached through an exec of a fresh
interpreter, where the activation hook has to load at startup in a process that
inherited nothing but the environment. Those are the two crossings measurement
has to survive in this suite, and it is the same distinction the CI job names
when it pins one version. A third entry is therefore earned by a third way of
starting a child, not by a third `os._exit`.

No threshold is set anywhere, in the configuration or in the script. A threshold
would answer a question nobody asked while leaving this one unanswered.

## The lines are found by symbol, never by number

A line number written into a script is a claim about a file the script does not
own, and it stays true until somebody adds an import. `scripts/run_coverage.py`
names a module and a function instead, parses that module's source, and takes
the line of the `os._exit` call inside it. Anything other than exactly one such
call is an error rather than a guess, because a function that grew a second exit
has changed in a way that makes the contract mean something different.

Two ways that resolution can go quietly wrong, and both are closed by
construction rather than by care.

The search collects **every** definition of the name and fails on anything but
one. Two `def`s sharing a name in one module is legal Python and only the last
one runs, so taking the first match would bind the contract to a body that can
never execute, and the check would then report `MISS` forever while pointing the
operator at the patch list, which is the one place the fault would not be.

The search stops at any scope nested inside the target function. `ast.walk`
descends into a nested `def`, a nested class body and a lambda, so a function
holding no `os._exit` of its own but exactly one inside an inner scope would
resolve silently against a line that is not the sentinel. Measured on all three
shapes, each of which `ast.walk` accepts without complaint.

The module is located with `importlib.util.find_spec`, which resolves it without
executing it, and that is load-bearing rather than fastidious.
`pyteman.sitecustomize` runs its entry point at import time, and with a rules
file in the environment that path can end in `os._exit`, which would take this
script with it. The result is then required to live inside the checkout: an
ambient non-editable install elsewhere would have the script comparing lines
from one copy of the package against coverage data for another, and that
mismatch would surface as a missing sentinel rather than as the install problem
it is.

## Why the ordinary suite is not instrumented

Instrumentation is observable from inside a child process here, which makes it
more than a cost. Asking coverage to follow subprocesses works by exporting
`COVERAGE_PROCESS_CONFIG`, which every child inherits, and coverage's startup
hook then imports coverage in that child before anything else runs. One test in
this suite measures exactly that kind of purity: it asserts that a child of the
test helper has imported nothing beyond the activation shim, `typing` included,
on the reasoning that the shim sits on the `PYTHONPATH` of every process in the
environment and anything it imports unconditionally is paid for by programs that
never asked for instrumentation.

Under measurement that assertion is false, and it is false because of coverage
rather than because of this package. The honest options are to weaken the test
or to not measure that one run, and weakening it would lose the signal
everywhere. So the test is deselected in the coverage job and nowhere else, and
the matrix keeps running it at full strength on 3.11 through 3.14.

Measured on 2026-09-17 on the working checkout, both halves on the same
interpreter, the Python 3.14.7 venv from the recipe below: 787 passed and 1
skipped uninstrumented, 786 passed, 1 skipped and 1 deselected under coverage.
The deselection accounts for the whole of the difference, which is the
arithmetic worth checking: any other gap would mean instrumentation had changed
what ran rather than only how it was watched. Naming the interpreter is not
pedantry, because it
is the only one here that can import the package at all, and a bare
`python3.14` gives eighteen collection errors rather than a slower run.

The wall clock cost is close to double, and the measurement is worth recording
with its conditions rather than as a number. Three alternating rounds at a load
average near 2 gave 4.35, 4.11 and 3.97 seconds uninstrumented against 7.62,
7.65 and 7.60 instrumented. Three further rounds at a load average between 14
and 20, on a machine running other work, inflated both sides past any absolute
use, 7.80 to 21.06 seconds uninstrumented against 14.92 to 30.96 instrumented,
while the ratio stayed between 1.3 and 1.9 and therefore still bracketed the
figure above. Timing this on a loaded machine is worth nothing and looks
convincing anyway: an earlier attempt at load averages between 14 and 26
reported the instrumented run as the faster of the two, which is contention
speaking rather than the interpreter.

## The deselection is guarded, because pytest will not complain

`--deselect` fails silently in two opposite directions, and the guard has to
answer both because pytest answers neither.

A node id that matches nothing is accepted in silence and the run exits 0.
Measured on 2026-09-17:

    --deselect <a name that does not exist>        1 passed, exit 0
    --collect-only <the real id>                   1 test collected
    --collect-only <a name that does not exist>    no tests collected, exit 4

So the day that test is renamed, the flag quietly stops doing anything and what
it was protecting this job from comes back as a failure naming the test rather
than the deselection.

And `--deselect` matches by **prefix** where `--collect-only` matches exactly, so
a guard built only on the first question is asymmetric with the flag it guards.
Measured with a sibling whose name extends the guarded one: `--deselect <id>`
reports `1 passed, 2 deselected` while collecting that same id reports one test.
A test added tomorrow whose name begins with the guarded id would vanish from
every instrumented run without appearing anywhere.

The script therefore collects the whole file once and asks both questions of the
one result: that the id is present, and that nothing else collected from that
file extends it. Collection is the cheap question that has an answer. Measured
on 2026-09-17 that spawn costs 0.19 seconds of wall clock, under three percent
of the instrumented run, and the figure to quote is that one rather than the
`1 test collected in 0.01s` pytest prints about itself, which leaves out the
interpreter and the imports that dominate it. The gap is not academic: the same
spawn with plugin autoload left on measures 2.5 seconds, which is why the script
disables it for every child it starts.

## The configuration is named, and the environment is cleared

Coverage reads a different configuration file without saying so if
`COVERAGE_RCFILE` is exported, which would leave this script certifying a file
it never opened. Every coverage subcommand is therefore given an explicit
`--rcfile`, measured to win over the environment variable: with the flag the
report totalled 4 statements, without it 2, against the same tree.

Five variables are additionally removed from every child, for a sharper reason
than the three `PYTEMAN_*` names the script also clears. Each of these lets an
ambient value redefine what is being measured while every check still passes.
`COVERAGE_RCFILE` and `COVERAGE_PROCESS_CONFIG` replace the configuration
wholesale. `PYTEST_ADDOPTS` injects deselections through the same blind spot the
deselection guard exists to close, silently shrinking the suite.
`COVERAGE_PROCESS_START` and `COVERAGE_FORCE_CONFIG` are the pair most easily
missed, and naming them is what keeps this list from being pruned back to the
obvious three. `COVERAGE_PROCESS_START` arms coverage's startup hook, together
with `COVERAGE_PROCESS_CONFIG` and through the same test in `pth_file.py`, and
that hook runs before argv is parsed. `COVERAGE_FORCE_CONFIG` is applied after
the named file rather than before it, so it overrides that file outright.
Naming the configuration on the command line reaches neither. It is a real
backstop for `COVERAGE_RCFILE`, where this list is belt and braces; for the
other three it is this list alone that does the work.

## The settings, and the one that was removed

`[tool.coverage.run]` in `pyproject.toml` carries four settings and the reasons
are not interchangeable.

`source = ["src/pyteman"]` matches by **filename**, and it is the only channel
that can see the activation hook. The hook ships as `pyteman/sitecustomize.py`
but is imported as top-level `sitecustomize`, so a matcher comparing module
names against `pyteman` can never match it however the file is laid out. The
path is relative and coverage resolves it against the working directory of the
process that starts measurement, which is why the script pins its own cwd to the
project root.

`source_pkgs = ["pyteman"]` was configured here and then removed, and the reason
is worth recording because the setting looks obviously correct. It matches by
module **name**, and several tests in this suite build a fake package called
`pyteman` in a temporary directory in order to check what the hook refuses.
Those fixtures matched, and their files were reported as though they were this
project's code. Measured on 2026-09-17 against the tree as it stood that
morning, with and without it: 1232 statements against 1185, with every real
module reporting identical numbers either way. The whole difference was fixtures
impersonating the package, which is the opposite of telling this project's
runtime apart from the tools around it.

`parallel = true` because the suite is almost entirely subprocesses and a single
data file would be written by many processes at once. The consequence is that
`combine` is a real step rather than a formality, and the script runs it
explicitly instead of letting a report combine implicitly, so that a child whose
data never arrived is visible rather than absorbed. The section below is about
what makes that visibility real.

`branch = true` is the one setting nothing in this job consumes, and it is worth
saying so rather than leaving a reader to check. The contract check asks whether
a line is in the executed set, not whether both arms of a condition were taken,
and there is no threshold for partial branches to fall below. What it changes is
the report a human reads: without it the run prints statements alone, and with
it the same run prints 472 branches with 26 partial beside them, which is where
a rule that has only ever been evaluated one way becomes visible. It is kept for
the reader rather than for the check.

`patch = ["subprocess", "_exit"]` is the pair that makes any of this work.
`subprocess` carries the configuration into children. `_exit` installs the
handler that flushes before `os._exit`. Neither is a default.

## The version floor, read off the wheels

The floor is coverage **7.13.0**, declared in the workflow and checked by the
script. It is the first release whose wheel carries the process-startup hook as
an ordinary packaged file. Before it, asking for the subprocess patch made
coverage write a `.pth` into `site-packages` at runtime, which fails wherever
that directory is not writable and leaves a file behind wherever it is. This
project writes no `.pth` of its own and does not need one.

That number was established by downloading the wheels and listing them, rather
than from release prose, because the interesting version is precisely the one
whose prose and whose artifact disagree. Measured on 2026-09-17:

    7.12.0     no .pth in the wheel at all
    7.12.1b1   coverage-7.12.1b1.data/data/lib/python3.14/site-packages/
               zzz_coverage.pth
    7.13.0     a1_coverage.pth at the archive root
    7.14.1     unchanged from 7.13.0 in this respect

The middle entry is the trap. That path is the wheel **data scheme** with an
interpreter version baked into it, so the hook does not land where an installer
would put a root level file, which is why that build measures no subprocesses
despite shipping something that looks like the fix.

Two further facts make 7.13.0 the only defensible floor rather than a rounded up
one. There is no 7.12.1 final at all: `pip index versions coverage` goes from
7.12.0 straight to 7.13.0, and `pip install coverage==7.12.1` reports no
matching distribution. And `version_info[:3]` of `7.12.1b1` is `(7, 12, 1)`, so
a floor written as `(7, 12, 1)` would admit exactly the build described above.
Naming 7.13.0 closes that hole rather than merely correcting a number.

No upper bound is declared, and that is a decision rather than an omission. What
this job asserts is a contract on two named lines, so a coverage release that
broke subprocess measurement would fail it loudly instead of drifting a
percentage. A ceiling would buy a reproducible report nobody reads at the cost
of a job that goes red on a release that is fine.

## The data never lands in the checkout

`COVERAGE_FILE` is set by the script to a path in a temporary directory outside
the project, and the script refuses to run if `TMPDIR` puts that directory inside
the checkout. That guard runs **before** the directory is created, because a
guard that creates what it then refuses to use has planted the residue it was
written to prevent, and it compares resolved paths, because a `TMPDIR`
symlinked into the checkout points outside it by spelling and inside it in fact.

This is a packaging requirement rather than tidiness. `MANIFEST.in` grants
`tests/` whole, and `test_the_sdist_carries_a_granted_directory_exactly`
compares the archive against the tree by **equality**, so a single stray
`.coverage.*` written under `tests/` between a build and that comparison is a
packaging failure. The residue filter that check applies does not list coverage
data files, and widening it would be the wrong fix: the data has no business
being there in the first place.

## A child whose data never arrived

Running `combine` explicitly was supposed to make a lost child visible, and by
itself it does not. `coverage combine` discards a file it cannot read, warns into
whatever has scrolled past, and exits 0. Measured on 2026-09-17 against two good
data files and one deliberately corrupt one: `Combined 1 file, skipped 1, 1 file
errored`, return code 0.

The signal that does work is structural rather than prose, and it comes from how
combine treats the files it has consumed. It deletes every file it read,
including the ones it skips as duplicate content, and keeps the ones that
raised. In the same measurement both good files were gone afterwards and the
corrupt one was still on disk. So **a surviving `.coverage.*` after combine is a
failure by construction**, and the script asks that one question with a glob
instead of parsing the tool's output.

Asking afterwards rather than before is also what makes the question race free.
An earlier version counted the data files before combining and reported 23 where
combine then accounted for 24, because a child flushed in between. A check made
before the combine cannot see that child; a check made after it cannot miss it.

Verified in both directions before being trusted: it raises against the planted
corrupt file, and it stays silent against a clean run.

## Running it

The package has to be installed, because the suite imports `pyteman` rather than
reading `src/` off the path, and it has to be the copy in this checkout. The
script checks that and says so, since an ambient install elsewhere would have it
comparing lines from one copy against coverage data for another.

    python -m venv --system-site-packages /tmp/cov/venv
    /tmp/cov/venv/bin/pip install --no-index --no-deps --no-build-isolation -e .
    /tmp/cov/venv/bin/pip install 'coverage>=7.13.0'
    /tmp/cov/venv/bin/python scripts/run_coverage.py

Measured on 2026-09-17: 786 passed, 1 skipped and 1 deselected, 22 data files
combined and 6 skipped as duplicate content, a total of 1249 statements with 52
missed and 472 branches with 26 partial, and both sentinel lines reported `ok`.

Read the statement total as a reading taken on one day rather than as a figure
CI should reproduce. This checkout is worked on by several people at once, and
over the course of writing this document the total moved 1185, 1188, 1192 while
the missed count held at 52 throughout. A reader who measures a different total
is therefore looking at a newer tree, not at a defect, and that is the argument
for the contract check rather than against recording numbers: the sentinels and
the combine accounting mean the same thing on any tree, which a percentage does
not.

One trap is worth naming for anyone writing their own harness around this suite,
because it produces a failure that names neither the harness nor this package.
On 3.14 `multiprocessing` defaults to forkserver, and a forkserver child
reconstructs `__main__` by importing the main module **by path**. Invoke pytest
from `python -` or `python -c` and that path is the literal string `<stdin>` or
`-c`, no such file exists, the forkserver dies inside `spawn.import_main_path`
and the parent sees `ConnectionResetError: [Errno 104] Connection reset by
peer`. Measured on 2026-09-17 while hiding an optional dependency, where it cost
one falsely attributed failure before the traceback was read. The identical code
in a `.py` file passes. Run harnesses from a file.

## Confirming the check is not vacuous

The requirement this was built against is that removing either half of the patch
list makes the **verification fail**, not merely lowers a number. That is what
the `--rcfile` argument exists for: the script is pointed at a copy of
`pyproject.toml` whose patch list has been broken on purpose, which keeps the
procedure visible in the command instead of hidden in an environment variable.
Measured on 2026-09-17, three ways:

    patch = ["_exit"]        786 passed, 87 missed, both sentinels MISS, exit 1
    patch = ["subprocess"]   786 passed, 74 missed, both sentinels MISS, exit 1
    patch = []               786 passed, 87 missed, both sentinels MISS, exit 1

The suite stayed green in all three. That is the point rather than a footnote:
the tests cannot see this failure, and the only thing that goes red is the
contract check, which names both lines and says which setting to look at.

The missed counts are the argument against a threshold, stated in numbers.
Against 52 missed in a healthy run, dropping `_exit` while keeping `subprocess`
loses 22 lines rather than all of them, because every child that exits normally
still flushes at `atexit`. A reviewer watching the percentage would see 93
instead of 95 and could reasonably attribute two points to a deleted test. The
contract does not degrade that way: both sentinels are absent in all three
cases, identically, whatever the percentage does.

One thing this cannot stand on is worth naming, because it is the tempting
shortcut. The presence of data files, or a `grep` for a line in a report, proves
nothing about whether a line executed. The check reads the combined data through
coverage's own `CoverageData` and asks for the executed lines of a specific file.
Nor can it stand on the absence of measured files: coverage records a source file
it knows about whether or not anything in it ran, so an empty result is not the
symptom of a misconfigured source and was measured not to be.

## What the counts above do and do not predict

Every count in this document was measured on a development machine where four
optional conditions happen to be satisfied, which is why the local run reports
zero skips. A machine missing any of them runs a smaller suite, and the numbers
here are therefore a ceiling rather than a prediction of what CI will print.

Measured on 2026-09-17 by removing them one at a time, against the tree as it
stood at 731 collected tests. They are left at that size rather than restated
against the 735 above, because a re-measurement was not run and inventing the
difference would defeat the point of recording them. The figures still sum to
their own total, which is the check worth being able to make:

    pandoc absent from PATH        724 passed, 7 skipped
    `markdown` not importable      730 passed, 1 skipped
    no non-UTF-8 locale available  one further test skips

The last line is read from the skip condition in
`test_the_report_writes_where_the_locale_is_not_utf_8` rather than measured by
forcing it, and is labelled that way on purpose. A fourth condition, SQLite
built with FTS5, is satisfied here and depends on how the interpreter's SQLite
was compiled.

The first two are not hypothetical on a runner. `markdown` is not a dependency
of this package and is not named in any workflow install step, so CI has it only
by accident. Neither tool is a test dependency, which is what the skip reasons
say, and `-rs` is passed in every job so that the skips are announced rather
than silently subtracted.

## In CI

`.github/workflows/tests.yml` runs this in a job of its own, on Ubuntu and on
Python 3.14 named explicitly rather than derived from the matrix. That version is
the only one the arrangement has been measured on end to end, and this document
makes no claim about 3.11 through 3.13. Widening it is a separate decision that
has to be measured rather than assumed, because 3.14 defaults `multiprocessing`
to `forkserver` where the earlier three default to `fork`, and how a child is
started is precisely what this job depends on.

The matrix job stays uninstrumented, which is what keeps the deselected test
running on every supported version and what makes a difference between the two
runs visible instead of absorbed.

The coverage job declares `coverage>=7.13.0` in its own install step, because
coverage is a test tool and deliberately not a dependency of this package, so
nothing else installs it.
