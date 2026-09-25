# Run development checks

## Set up this checkout

Use this guide from a Git checkout on Linux or macOS. The developer dispatcher
uses POSIX executable names and is not supported on Windows. This limitation
applies to the developer commands, not to the runtime's documented behavior.
Release archives intentionally omit the lockfile, hooks and developer scripts.

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then run:

```bash
uv sync --locked --python 3.14
uv run --locked prek install
```

Use one `.venv` per checkout. Do not copy it to another checkout; the editable
installation points at this source tree. The dev group does not change pyteman's
runtime dependencies.

The Git hook installation is local to this repository. If an existing hook or
`core.hooksPath` prevents installation, inspect it rather than using `--force`.
The first workflow-hook run may download a Go toolchain for pinned actionlint.
The hook configuration in `.pre-commit-config.yaml` uses `repo: builtin`, which
is a prek extension. It is not compatible with upstream pre-commit.

## Check a change

Run the affected tests while editing:

```bash
uv run --locked python scripts/dev.py test tests/test_matrix_results.py
```

Before review, run the fast checks and the complete serial suite:

```bash
uv run --locked python scripts/dev.py check
uv run --locked python scripts/dev.py test
uv run --locked python scripts/dev.py test scripts/tests
uv run --locked prek run --all-files
```

`check` checks lock freshness, Ruff correctness rules, the type baseline and
package metadata. Ruff scans the checkout using the exclusions in
`pyproject.toml`, including `src/`, `tests/`, `scripts/` and `examples/`.
The type check covers only `src/`; a successful check does not certify types in
tests, developer scripts or examples. `test` verifies the editable import, clears ambient pyteman
activation and Python overrides, and prints skip reasons. Review every skip;
a successful pytest exit does not certify that every optional check ran.

The default pytest suite does not collect `scripts/tests`. Run that directory
explicitly when changing the dispatcher. The quality CI job does so too.

For files not yet tracked, pass them explicitly to `prek run --files`.
Neither `--all-files` nor a commit hook scans arbitrary untracked files.
The hooks check files without fixing them. actionlint checks changed workflows;
its optional shellcheck and pyflakes integrations are disabled, so they do not
vary with tools installed on the host.

## Format selected files

Check only the files you intend to format:

```bash
uv run --locked python scripts/dev.py format-check scripts/dev.py scripts/tests/test_dev.py
uv run --locked ruff format scripts/dev.py scripts/tests/test_dev.py
```

Review the diff after formatting. Legacy formatting is not a mandatory gate;
`format-check` with no paths reports the whole configured code scope and can fail
on unchanged files. Do not format the entire repository as part of a bug fix.

## Update dependencies and the type baseline

To update dependencies deliberately, run `uv lock --upgrade`, inspect `uv.lock`,
then run `uv sync --locked` and the checks above. Keep diagnostic tools pinned
until their changed output has been reviewed.

The initial type baseline contains 14 diagnostics, 13 in `patcher.py` and one in
`sitecustomize.py`. They concern dynamic descriptors and runtime attributes.
The baseline records existing debt; it does not establish that the code is
correct. Ordinary checks use `--baselinemode=lock`, which never writes it and
fails on diagnostics not matched by the baseline or on obsolete entries.
Matching uses the file, diagnostic rule and column range, not a unique error
identity. A changed error at a matching position can remain suppressed; review
changes to baselined code rather than treating the baseline as full type coverage.

After fixing a baselined issue, run `uv run --locked basedpyright` locally to
remove obsolete entries, then inspect the baseline diff. If new diagnostics
remain, basedpyright exits non-zero and does not prune obsolete entries; resolve
the new diagnostics first, then rerun to get a clean baseline diff. Do not use
`--writebaseline` to silence a new diagnostic. Initial adoption used that flag
once, after inspecting the diagnostics.

## Run release validation separately

Keep coverage outside the ordinary test environment's startup path:

```bash
uv run --locked python scripts/run_coverage.py
```

Run artifact validation with a clean base interpreter carrying pip, setuptools,
pytest and PyYAML, but no pyteman installation. On a host satisfying those
preconditions, the command is:

```bash
/usr/bin/python3.14 scripts/verify_artifacts.py
```

Do not substitute the project's uv interpreter blindly. The artifact driver
checks what its child environments inherit from the base interpreter, not only
what the launcher can import. Follow [the packaging guide](packaging.md) on
other hosts. The existing artifact and coverage CI jobs retain their separate
environments and checks.

Run the required simplification and high-effort review after the implementation
is stable. A lint result or baseline check is not independent approval. Re-review
changes made in response to findings; avoid duplicate assessments of unchanged
bytes. Keep the mandatory release and publication gates.

## Use the existing agent tools

Use Context7 for current library documentation, Backlog for task state and the
existing Python LSP for symbol navigation. No additional MCP server is needed to
run these local commands. Do not add a second type checker or enable pytest-xdist
without comparing its results and runtime with the serial suite.
