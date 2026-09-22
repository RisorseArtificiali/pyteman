# Python development tooling research

Date: 2026-09-22. Depth: standard. Confidence: high for documented capabilities. Local check timings are measured below; end-to-end development speedup is not established.

## Findings

- **uv** provides dependency groups, an editable project environment, a lockfile and cached CI installation. Development groups do not become runtime dependencies. Use `uv sync --locked` and locked commands rather than hand-built environments. Sources: [dependencies](https://docs.astral.sh/uv/concepts/projects/dependencies/), [sync](https://docs.astral.sh/uv/concepts/projects/sync/), [CI](https://docs.astral.sh/uv/guides/integration/github/).
- **Ruff** covers lint and formatting. Official guidance recommends a small explicit rule set. Local measurement with installed Ruff 0.16.8 found four diagnostics under `E9,F`: three unused imports and an intentional colliding-key regression fixture. Broader defaults produced 319 diagnostics; formatting would touch 50 files. A narrower correctness check completed in 0.017 seconds. These are observations of this checkout, not promised speedups. Sources: [lint](https://docs.astral.sh/ruff/linter/), [formatting](https://docs.astral.sh/ruff/formatter/).
- **basedpyright** offers a native baseline for gradual adoption. Existing Pyright took 2.208 seconds and reported 14 diagnostics in dynamic descriptor code and sitecustomize. Those diagnostics are not independently confirmed runtime defects. Use basedpyright standard mode, a reviewed baseline and explicit `--baselinemode=lock`. This mode never writes and fails when the baseline needs updating. Baseline matching is imperfect and the mode is experimental, so pin the tool and prove it detects introduced errors. Sources: [baseline](https://docs.basedpyright.com/latest/benefits-over-pyright/baseline/), [CLI](https://docs.basedpyright.com/latest/configuration/command-line/).
- **prek** runs pre-commit-compatible hooks and supports uv. The checkout currently has only sample Git hooks and core.hooksPath is unset. Recheck before installing a local hook, without force or global configuration changes. Sources: [quickstart](https://prek.j178.dev/quickstart/), [CLI](https://prek.j178.dev/reference/cli/).
- **validate-pyproject** checks package metadata against schemas. **actionlint** checks GitHub Actions syntax and expressions, beyond YAML parsing. Run actionlint for workflow changes, not every Python edit. Neither replaces a real package build. Sources: [metadata validation](https://validate-pyproject.readthedocs.io/en/stable/readme.html), [workflow validation](https://github.com/rhysd/actionlint).
- **pytest and existing release drivers** remain authoritative. Do not enable pytest-xdist until measurements establish a benefit and equivalent behavior for this subprocess-heavy suite. Retain artifact installation tests, subprocess-coverage sentinels and the existing release `twine check`. Sources: [xdist limitations](https://pytest-xdist.readthedocs.io/en/stable/known-limitations.html), [packaging guidance](https://packaging.python.org/en/latest/tutorials/packaging-projects/).
- **MCP/LSP** needs no additional server for this rollout. Context7 and Backlog already exist, and the Python LSP returned actual matrix.py symbols during research. Use CLI tools directly rather than adding MCP wrappers for them. Source: [Claude Code LSP documentation](https://code.claude.com/docs/en/plugins-reference).

## Alternatives not selected

[Astral ty](https://docs.astral.sh/ty/type-checking/) supports partially typed code and watch mode, but its speed was not measured here. Avoid two type gates; basedpyright's baseline addresses the observed adoption problem. [pip-audit](https://github.com/pypa/pip-audit) is useful for known dependency vulnerabilities, not code correctness; keep a network audit out of the edit loop. Do not deploy more tools merely because they exist.

## Confidence and version policy

PyPI metadata read on 2026-09-22 reported uv 0.12.17, Ruff 0.16.8, basedpyright 1.40.1, prek 0.5.3 and validate-pyproject 0.26. Installed uv and Ruff matched. These are single-primary-source release observations, not compatibility proof. Resolve, pin and test the chosen set during deployment. Release metadata came from the individual PyPI endpoints for [uv](https://pypi.org/pypi/uv/json), [Ruff](https://pypi.org/pypi/ruff/json), [basedpyright](https://pypi.org/pypi/basedpyright/json), [prek](https://pypi.org/pypi/prek/json) and [validate-pyproject](https://pypi.org/pypi/validate-pyproject/json).

## Local measurements

These wall-clock measurements came from the rollout on 2026-09-22. They do not
establish how much faster a future development task will finish.

| Command | Seconds |
| --- | ---: |
| `uv sync --locked --python /usr/bin/python3.14`, new environment with existing uv cache | 2.002 |
| `uv sync --locked`, warm environment | 0.125 |
| `uv run --locked ruff check src tests scripts` | 0.018 |
| `uv run --locked basedpyright --baselinemode=lock` | 1.673 |
| `uv run --locked validate-pyproject pyproject.toml` | 0.392 |
| `uv run --locked prek run --all-files`, prepared hook environments | 0.329 |
| Full serial pytest suite in the locked environment | 42.961 |

The full suite reported 1190 passed and two skips. The artifact driver reported
1184 passed and eight explicit skips for each built artifact. Its packaging
self-build tests deliberately skip inside a distribution. The coverage driver
measured both child-only exit sentinels.

Controlled faults verified that Ruff rejected an undefined name, metadata
validation rejected a numeric project name, and actionlint rejected an unknown
workflow key. A separate basedpyright fixture rejected both a new type mismatch
and an obsolete baseline entry without modifying its baseline. Each fault had
a passing control. The baseline remains a gradual-adoption aid, not proof that
all type errors in the source are detectable.
