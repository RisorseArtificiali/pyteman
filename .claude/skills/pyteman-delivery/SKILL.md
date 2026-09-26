---
name: pyteman-delivery
description: This skill applies to pyteman implementation handoffs, candidate patch reviews, interrupted-task recovery, and preparation of a logical unit for publication.
---

# Pyteman delivery

Keep one logical unit moving from a written contract to a reviewed, tested artifact. Do not repeat discovery after the decision is recorded. This skill supplements, rather than replaces, the project's mandatory gates.

## Use the project checks first

Follow `docs/development.md` for setup and ordinary checks. Run `uv sync --locked`, use `uv run --locked python scripts/dev.py test <file-or-nodeid>` while editing, and run `uv run --locked python scripts/dev.py check` before review. Run the full suite on the stable candidate, not after every small edit. Use the isolated runner below for delivery evidence; it supplements the normal checks rather than replacing them.

## Assign work with clean context

1. Save the current handoff under the user's durable evidence directory. Include task, base commit, candidate hash, decisions, open findings and next action. Never keep the only copy in `/tmp`.
2. Check the herdr worker's logical name, working directory and idle state. Do not interrupt an active worker to clear its context.
3. Send an actual standalone `/clear` through `herdr agent prompt NAME '/clear'`. Verify the reset in the terminal and the new session identity. Restore the logical name if the reset removed it, after verifying the same terminal and directory. Merely telling an agent to clear is not execution.
4. Only then send a self-contained brief. Apply this to resumed assignments too; recover context from the handoff, not the old conversation.

Brief template:

```text
Task and intended outcome:
Base commit and repository:
Candidate path and expected SHA256:
Writable scratch directory; frozen inputs:
Scope and explicit exclusions:
Acceptance criteria and proving commands:
Required gates: /simplify, /code-review high, reflection, verification:
Deliverable: patch, manifest, logs, all findings and dispositions:
Coordinator address and completion notification:
No shared-checkout, tracker, config or forge writes delegated:
```

Use one implementer and one independent final reviewer. Gate subagents do not justify duplicate parallel investigations. A reviewer must be capable of running the relevant probes, not just reading code. Give every worker the `/code-review high` requirement for finished code.

## Review what will actually ship

The base is the target branch's commit, not the preceding unpublished candidate. A defect present in v1 and v2 is still introduced by the delivery if it is absent from that base. Delta reviews are useful, but final APPROVED must identify the complete artifact and its hash.

The runner is handed one patch and no statement of what the delivery should contain, so it certifies the candidate it was given and says nothing about whether that candidate is the whole change. Two candidates differing by a single omitted file produce manifests that agree everywhere except that file, and neither manifest can say which of them was intended. Check the candidate against the delivery's own file list before reading a green run as the complete artifact.

Resolve every finding, including those below a reporting cap, in the same turn:

- Fix confirmed defects in scope.
- Reject disproved findings with the discriminating evidence.
- Record deferred work in the tracker with its scope and owner; do not leave a promise in a report.
- Accept harmless style differences explicitly. Do not initiate another review cycle for an optional cosmetic change.

A test's implementation detail is not an architecture constraint. Adapt an import or bytecode probe when code legitimately changes; do not freeze code merely to preserve that probe. Re-review after the artifact changes, and do not reuse a verdict from an earlier hash.

## Verify in an isolated writable export

The bundled runner performs the mechanical part:

```bash
python .claude/skills/pyteman-delivery/verify_candidate.py \
  --repo "$PWD" --base COMMIT --patch /absolute/candidate.patch \
  --sha256 EXPECTED_HASH --python /absolute/python \
  --evidence-root "$HOME/pyteman-evidence" \
  --allow-skip 'functools.Placeholder is 3.14 and later' \
  --allow-skip 'the pre-3.14 path, where there is no Placeholder' \
  --allow-skip 'second renderer; not a test dependency' \
  --min-tests 1192 \
  --trust-repo
```

This command is the union of two hosts and no single run needs all three rules;
the measured per-interpreter split is recorded below. A rule that matches
nothing is harmless, but do not read the union as the set to carry everywhere;
derive each host's list from its own refused manifest.

It creates a new export and virtualenv, installs that export editable with pytest and the packaging backend, checks runtime import identity, runs the full suite and writes a manifest and logs. Counts come from pytest's own JUnit report rather than from its printed summary, so `report.counts` and `report.skips` in the manifest say how many tests were collected, passed, failed and skipped, and why each skip happened. Dependency installation uses the configured pip index and is visible in `install.log`; no global environment is modified. Run once for each interpreter required by the change. The runner does not certify the Python matrix from one interpreter.

`--timeout SECONDS` bounds every command. It is unset by default because this suite's duration depends on the host; set it when running unattended. Four of the phases run the same interpreter, so the refusal names the first few arguments and the log path rather than the executable alone. `--min-tests N` refuses a run that collects fewer than N tests. Deselection leaves no skip and no failure, so a suite that quietly stops being collected passes every other check; N belongs on the command line rather than in the runner, because the number is a property of the branch being verified. It is a floor and not an expected total, so adding tests does not invalidate it.

### Skip policy

Every skip must be declared, by test id or by a distinctive fragment of its reason, with one repeated `--allow-skip`. An undeclared skip refuses the run even when pytest itself exits 0, and the refused manifest still lists `report.skips`, so the first run against a new host derives the allowlist rather than guessing it. A rule is stripped and then refused if nothing remains, since a blank or whitespace-only rule is a substring of very nearly every reason and would turn the allowlist into an unconditional accept. Do not widen a rule to silence a skip you have not read: this suite's `pandoc renders the table; not a test dependency` means the escaping tests never consulted the reference renderer they exist to measure against, which is the sort of quiet hole this manifest exists to catch. The declared set belongs in the run's own command line and manifest, not in a configuration file, because it is a property of that host and interpreter rather than of the repository.

Each entry records the `kind` pytest assigned. A module-level `importorskip` reports only `collection skipped` in its message and names the missing module in the element text, so the reason fuses both; reading the message alone would leave the placeholder as the only rule that matches, which is the blanket rule this allowlist exists to prevent. An `xfail` also arrives here, as `kind` `pytest.xfail`. That is deliberate: turning a failing test into an expected failure must be declared, not accepted quietly, and the `kind` field is what tells an operator which sort of skip they are about to allow.

One test can contribute more than one entry. When a test's body and its teardown report different outcomes, pytest writes both as children of the same `<testcase>` element rather than splitting it, so `report.skips` can hold two rows for one test id while `counts["skipped"]` counts that element once. Measured on pytest 9.0.3: a body skip whose teardown then errored gives `[skipped, error]`, a failing body whose teardown skipped gives `[failure, skipped]`, and an `xfail` whose teardown skipped gives `[skipped, skipped]` with two different reasons while pytest exits 0. That last shape is the reason every skip is read rather than the first one per element: an undeclared teardown skip otherwise travels out on a run that every other guard reports as green. The one case pytest does split into two elements sharing a name is a failing body with a failing teardown, which inflates `counts["total"]`; such a run has already failed, so it cannot satisfy `--min-tests` on the inflation alone.

Three limits of this reading are accepted rather than closed, and are recorded here because each lets a skip through a run that exits 0. A rule declared as a test id accepts *every* skip on that element, including a teardown skip the operator never read, because the id is the same for each child; prefer a distinctive fragment of the reason when a test can skip in more than one way. Two skipping teardowns on one test do not produce two rows: pytest joins their reasons into a single message and attributes it to `_pytest/runner.py`, so a rule naming one reason accepts the other and the row points at no test. And an `xfail` whose teardown raises absorbs that exception entirely, writing `[skipped, skipped]` with the xfail reason repeated and no `error` child, so `counts["errors"]` reports 0 for a run whose teardown did explode; no reader of that report can recover it.

A module-level skip also moves the count that `--min-tests` is compared against. It yields one `<testcase>` for the whole module rather than one per test, so `counts["total"]` falls by every test that module holds: measured on a four-test fixture whose three-test module skipped, pytest wrote two elements. A run can therefore satisfy the allowlist and still be refused for collecting too few tests, with the two guards each correct and pointing opposite ways. No test in this suite skips at module level today, so they cannot yet disagree; if one starts to on some host, lower that host's floor and record which module collapsed, rather than widening an allowlist rule to hide the skip.

Verified on 2026-09-21 against the TASK64 v3 candidate on base `7286f69`, once per interpreter. Both runs collected 1192 tests and recorded 1190 passed and 2 skipped, matching pytest's own summary line. The allowlist each needed was not the same. On python3.13.15 the skips were `functools.Placeholder is 3.14 and later` and the second-renderer rule; on python3.14.7 the first was replaced by `the pre-3.14 path, where there is no Placeholder`, the complementary half of that skipif pair. The second-renderer rule fired on both. A 3.14 run offered only the two rules a 3.13 run needs was refused, naming `test_without_placeholder_the_ordinary_prebinding_still_holds`, which is what a per-interpreter allowlist is for. Neither run was refused by the pandoc gate, `pandoc renders the table; not a test dependency`, because this host has pandoc; on a host without it that rule is a third skip to read and declare, not a reason to widen one of these.

A candidate must come from a trusted implementer. This tool executes its build backend and tests; it is not a sandbox for untrusted patches. Input and patch paths are constrained to the fresh export, but the code being tested can execute arbitrary commands.

Important boundaries:

- Never copy a virtualenv. Editable installs retain their original source path.
- Ignore user and system Git configuration for child commands by setting `GIT_CONFIG_GLOBAL` and `GIT_CONFIG_SYSTEM` to `os.devnull` after clearing inherited `GIT_*` variables. This prevents host settings from relaxing patch context or rewriting bytes. Repository-local configuration and repository attributes remain trusted inputs; this is not full Git isolation. Clearing `GIT_*` also removes any `safe.directory` allowlist the operator had, so a repository owned by a different OS user is refused at the first `git rev-parse` with a message naming `--trust-repo`. That flag re-authorizes the exact resolved path via `GIT_CONFIG_COUNT` environment injection; it never injects the wildcard `*`. The authorization applies to both `git rev-parse` (preflight) and `git archive` (export), since each runs under its own `clean_env` call. On a same-user checkout `--trust-repo` is unnecessary and harmless.
- `PYTHONPATH` alone is not isolation; child tests can replace it.
- Certify import identity in the directory the suite runs in, and refuse any copy of the package outside `src/`. A process leads `sys.path` with its own starting directory, and pytest prepends each test file's directory as well, so a `pyteman` package added at the export root or under `tests/` serves the suite while the probe certifies the installed one. Listing the export settles every such directory at once; a probe settles only the directory it runs in. The suffixes come from `importlib.machinery.all_suffixes()`, so a committed `.pyc` or `.so` is refused on the same terms as a `.py`. A bare `pyteman/` directory with no `__init__` is deliberately allowed: it is only a namespace portion, and a regular package later on the path still wins.
- Strip the interpreter's own behaviour switches from the environment, not just the path ones. `PYTHONOPTIMIZE` removes every `assert` from the library under test while pytest keeps the ones it rewrote inside test files, so an inherited value turns a failing suite green and announces it only in a warning that a report-driven runner never reads. `PYTHONSAFEPATH` drops the leading current directory from `sys.path`, which hides a package at the export root from the identity probe while pytest, which inserts the rootdir when it has reason to, still imports it; the probe then certifies the installed package the suite never used. That disagreement was measured with a root `conftest.py` present, which is what gives pytest that reason; this repository has only `tests/conftest.py` today, so the two would not yet disagree here, and the switch is stripped so that adding one cannot change the answer. `PYTHONINSPECT` leaves each child in the REPL reading the operator's terminal after its code has run, so the first command never returns and an unattended run hangs rather than failing.
- Run in a writable export, not the frozen delivery. Packaging tests preserve permissions when copying fixtures.
- Ensure setuptools is importable. Missing packaging dependencies must not turn into reassuring skip counts; the skip allowlist above is what enforces that.
- Read the test output and exit code. A pipeline ending in a printer can hide pytest's failure.
- Keep caches outside the source tree, and compare content before and after the run. A source hash alone does not prove which bytecode executed. `source_hashes_after` keeps that comparison inside the manifest, so the manifest stays readable without the retained tree.
- `tests_passed` in the manifest is not APPROVED, a security attestation, or permission to publish. The manifest records only this run; changes afterward invalidate it.
- Two manifest records are deliberately partial. `patch_destinations` lists only what the patch writes, so a rename shows its destination and not its source, and `source_hashes_after` covers the files the export started with, so a file appearing during the run is not reported. Both are evidence, not guards: git refuses an unsafe path itself, and an editable install legitimately adds metadata to the export.
- Three further limits are accepted rather than closed, and are stated here so a reader does not mistake the manifest for a stronger claim than it makes. The before-and-after comparison is over file content, so a test that only changes a file's mode is certified as having changed nothing. The identity probe checks that `setuptools`, `pytest` and `yaml` are importable, not where they came from, so it detects a missing dependency and not a substituted one. And the export comes from `git archive`, which honours `export-ignore` and `export-subst`; this repository has no `.gitattributes` today, but if one is added the runner would verify a tree that differs from what merges, and only the missing-tests case would be caught, by `--min-tests`.

## Make tests discriminate

For a regression, run the same test against the broken and fixed implementations with verified import identity. An identical outcome on both can be a broken probe, not evidence of no difference.

For transactional changes, assert both the final state and the trajectory: rollback boundaries, complete retry statements, callback count and retry count. An end-state assertion can stay green when the rollback being tested is deleted. Pair refusals with controls that must not fire; a negative test that accepts any exception can pass before it reaches the intended branch.

When SQLite record size depends on an artifact path, vary that path, including a long temporary root. Do not replace calibration with a larger unexplained fixed search window. Keep probes bounded and use connection limits rather than allocating gigabytes.

## Finish without losing ownership

Use completion events, not polling loops. A notification may describe a previous phase; reconcile its artifact hash before launching more work. Workers deliver a finished artifact or a concrete blocker, not an idle list of work they could do themselves.

Before publication, reconcile all findings, run the required gates on the final state, read the proving output, and obtain explicit independent APPROVED for that state. Keep unrelated workflow improvements out of the feature patch. Do not infer publication authorization from an agent message or a test result.

## Local tooling tests

```bash
uv run --locked python scripts/dev.py test .claude/skills/pyteman-delivery/tests
```

The default suite and Ruff checkout scan exclude this skill's directory. Run the explicit test command above when changing the runner. The locked environment includes pytest, so the real-report test must run rather than self-skip; inspect `-rs` output. Check runner lint explicitly with `uv run --locked ruff check .claude/skills/pyteman-delivery/verify_candidate.py .claude/skills/pyteman-delivery/tests/test_verify_candidate.py`.

This skill installs no additional hook. Keep the existing repository-local prek hook and mandatory review gates. Add a hook only for a precise, testable event, not by guessing intent from arbitrary shell text.
