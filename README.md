# pyteman

Rule-based runtime fault injection for Python, inspired by Byteman.

Wrap a function with a YAML rule that fires on entry or exit, under a
condition. The action can inject a sleep, raise an exception, override the
return value, switch a SQLite PRAGMA on a connection passed to the call,
kill the process at the exact injection point (`os._exit`), or hold a named
barrier so two threads meet in the interleaving you want. Each firing is
logged with a sequence number, so you can reconstruct the interleaving after
the run.

## Activation contract (safety)

- Put the directory containing `sitecustomize.py` on the PYTHONPATH of TEST
  runs only; that is `src/pyteman`, not `src`. Python imports `sitecustomize`
  as a top-level module from whichever directory holds it. `pyteman.*` itself
  resolves for normal imports via the editable install.
- Without `PYTEMAN_RULES` set, the sitecustomize does nothing.
- With `PYTEMAN_REQUIRE_MARKER=<file>` set, pyteman refuses to start unless
  that marker file exists. It writes a refusal message to stderr and exits
  with code 2 via `os._exit`. The hard exit is deliberate: a `SystemExit`
  raised inside sitecustomize escapes into interpreter startup, and the
  interpreter dies with a Fatal Python error and status 1 instead of your
  exit code. Callers use the marker to pin execution to scratch directories.
  Never install sitecustomize into production venvs or images.

## Ruleset example

```yaml
- id: hold-commit
  point: hermes_state.SessionDB._execute_write
  event: entry
  when: "fires > 3 and kwargs.get('sid', '').startswith('stress-')"
  action: {kind: sleep, ms: 250}
  fire: {mode: once_per, key: "kwargs.get('sid')"}
- id: crash-at-commit
  point: hermes_state.SessionDB.commit
  event: exit
  action: {kind: kill, exit_code: 70}
  fire: {mode: countdown, n: 50}
```

The module is everything before the FIRST dot of `point`; the remainder is an
attribute path walked from the module, and the final component is the patched
attribute. `hermes_state.SessionDB._execute_write` resolves to module
`hermes_state` with attribute path `SessionDB._execute_write`.

Conditions see `args`, `kwargs`, `fires`, and on exit events also
`result`/`exc`. They are trusted operator input for test tooling.

Actions: `sleep`, `raise`, `return_value`, `return_none`, `pragma` (see the
Patchable-target contract for its connection-targeting limit), `kill`
(`os._exit`), `barrier` (role `wait` or `open`).

`return_value`/`return_none` follow Byteman RETURN semantics and depend on the
event. On an ENTRY event the wrapped body is skipped entirely and the override
value is returned in its place. On an EXIT event the original body has already
run and the override swaps the result it produced.

Fire gating uses `fire: {mode: ...}` with three modes. `always` is the
default. `once_per <key-expr>` consumes its key only when the condition
passes. `countdown n` fires on call n+1.

## Runner and sqlitekit

`pyteman.runner.matrix.run_matrix(cells, run_cell, results_db, artifact_root)`
runs cells sequentially and resumes across re-runs via the results SQLite;
`pyteman.runner.report.matrix_markdown` renders the outcome table.
`pyteman.sqlitekit.integrity.classify_integrity` parses `PRAGMA
integrity_check` output into typed signatures (CLEAN / FTS_ONLY /
CANONICAL_INDEX_COUNT / CANONICAL_ROWID_DISORDER / SCHEMA / NOTADB).

## Patchable-target contract

Rules can patch two shapes of callable:

- Plain module-level functions: `point: mymodule.my_function`.
- Instance methods, addressed through the class:
  `point: mymodule.MyClass.my_method` (resolution as in the Ruleset example
  above).

Not supported: `classmethod`, `staticmethod`, and other descriptor-based
attributes. Patching replaces the class attribute, so descriptor binding is
lost. Calls through the instance pass `self` into the wrapper, so you usually
get a TypeError, not a silent no-op. If you need them, wrap an inner plain
function instead.

The `pragma` action needs its `sqlite3.Connection` among the call's direct
arguments or keyword values. A connection held as an attribute (for example
`self._conn`) is invisible to it, and the action does nothing.

## Import-hook name matching

Patching happens when the target module is imported. The import hook matches
the module name Python passes to `import`, so rules must name the target's
absolute TOP-LEVEL module as it is imported directly: `import mymodule` or
`from mymodule import thing`. Two shapes do not match:

- Relative imports (`from . import x` inside a package) never reach the hook.
  importlib resolves them internally; the hook only sees the outer top-level
  import. No rule-module renaming can match them.
- Submodule imports (`import package.mymodule`) do not match a rule on the
  submodule. The hook sees the full dotted name, but a ruleset cannot express
  a dotted module, because the point splits at the first dot. The form
  `from package import mymodule` does match a rule anchored on the parent
  (`point: package.mymodule.func`). The hook sees `package`, and the symbol
  walk descends into the submodule attribute.

## Status

Pre-release; born out of a real SQLite corruption investigation.

## License

MIT; see [LICENSE](LICENSE).
