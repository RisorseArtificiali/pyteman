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

Actions: `sleep`, `raise`, `return_value`, `return_none`, `pragma` (reaches
attribute-held connections through `target:` specs, see docs/targeting.md),
`kill` (`os._exit`), `barrier` (role `wait` or `open`).

`return_value`/`return_none` follow Byteman RETURN semantics and depend on the
event. On an ENTRY event the wrapped body is skipped entirely and the override
value is returned in its place. On an EXIT event the original body has already
run and the override swaps the result it produced.

Fire gating uses `fire: {mode: ...}` with three modes. `always` is the
default. `once_per <key-expr>` consumes its key only when the condition
passes. `countdown n` fires on call n+1.

## Runner and sqlitekit

`pyteman.runner.matrix.run_matrix(cells, run_cell, results_db, artifact_root, *,
experiment, on_mismatch="error", on_legacy="error")` runs cells sequentially and
resumes across re-runs via the results SQLite. A cell is skipped only when the
stored row was produced by the same `experiment` and by a definition identical
to the one being submitted; `experiment` is required, and passing `None` writes
into the same unnamespaced stratum that databases predating this argument use,
distinguished from those rows by carrying a fingerprint, so a named experiment
can never resume one of them.
`run_cell(definition, attempt_dir)` returns a `dict` of results, or `None` if
it has nothing to report. Anything else, including `0`, `False`, `''` and `[]`,
is that cell's own failure and is recorded as a `failed` row carrying the
reason, leaving the rest of the matrix to run; so is a `dict` that will not
serialise to JSON. Writing the row down is not: a results db that refuses the
row raises `MatrixStorageError` and stops the run rather than going on to
produce evidence nothing is keeping.
When the stored definition differs, `on_mismatch` chooses between `error` (the
default) and `rerun`, which runs again and copies the stored row into
`results_superseded` in the same transaction that installs the replacement, so
an interrupted run supersedes nothing and leaves no record saying it did.
`on_legacy` governs a row written before provenance was tracked and adds
`adopt`, which stamps that row with the submitted identity
instead of re-running it, but only when the stored row is recorded as `done`.
Adoption asserts that stored evidence describes the submitted definition; a
legacy row recorded as `failed` is not evidence, so there is nothing to assert
and that cell is re-run, exactly as it is under the default `error`.
Both non-error policies consume the unnamespaced row rather than leaving it
where it was: `rerun` deletes it in the transaction that installs the
replacement, and `adopt` re-stamps it with the submitted experiment. Either
way that cell holds nothing in the unnamespaced stratum afterwards, so a
later experiment meeting the same cell id finds no legacy row to resolve and
runs it as new. The first run to apply a non-error policy therefore settles
that row on behalf of every experiment, and what it settled stays readable:
the original is copied into `results_superseded` before either policy touches
it.
A results db predating provenance tracking is migrated
in place on first open, keeping every historical row. Only the four columns a
pre-provenance table is known to hold are migrated: a table carrying any other
column is refused with `MatrixIdentityError` and left untouched, because the
migration copies the columns it knows by name and then drops the original, so
an unknown column would be destroyed with no copy of it kept.
Under the default policy (`on_mismatch='error'`, `on_legacy='error'`) a stored
`done` row the run cannot claim as its own raises `MatrixIdentityError`, which
is also what a duplicate cell id, an unusable id, and a results db written by a
newer pyteman raise. A refusal about where the artifacts would go raises
`MatrixArtifactError` instead, so `except MatrixArtifactError` catches the
artifact-root containment refusal and nothing else.
`pyteman.runner.report.matrix_markdown` renders the outcome table, one row per
experiment and cell. It raises `MatrixReportError` when the file it is handed
cannot be opened at all, holds no `results` table, or is not a database,
because sqlite opens any name it is given and invents an empty file for the
ones that do not exist.
Every column is escaped, including the ones this runner writes itself, because
the report renders foreign databases and none of them is guaranteed to hold
what a run would have put there. A cell holds result data, and result data is
not markup, so the promise has two halves. Structurally, whatever characters a
stored value holds, it stays in its own row and its own cell, in the file and
through a real renderer. Literally, its characters are shown as themselves:
`*x*`, `` `x` ``, `[a](u)` and `<script>` arrive as the characters someone
stored and not as emphasis, code, a link or a script element. Every ASCII
punctuation character is therefore backslashed, which CommonMark renders as the
character itself, and the two line endings become the Unicode control pictures
for them, since a cell is one line by construction; that is also what keeps a
stored `\n` distinct from a stored newline. The database is not touched, and a
report is a rendering of it rather than a replacement for it.
The literal half is stated against CommonMark and the GFM tables built on it.
A renderer outside that family honours a narrower set of escapes, so a value
can arrive carrying a visible backslash; what was measured to hold on both
renderers tried is that nothing renders as an active element, and that no two
of the sample values collapsed into one rendering. How far distinctness goes in
general is bounded by the limits below. The report file is written as UTF-8
whatever the locale says, because the control pictures are not ASCII and a
stored newline is enough to produce one.
Three limits remain, all measured rather than assumed. Values differing only in
whitespace arrive alike, because markdown collapses spaces inside a cell before
any escape can speak. A stored control picture renders the same as the line
ending it stands for, a collision kept knowingly because removing it only moves
it elsewhere. And the promise covers characters rather than glyphs: a bidi
format control such as U+202E travels the escape untouched and reorders what a
reader sees without altering what is there. Treat a rendered report as a local
artefact for the operator who ran it.

Artifacts are confined to `artifact_root`. Each attempt is written to
`<artifact_root>/exp-<digest>/<cell_id>.<fingerprint prefix>.<token>`, where the
experiment digest, the fingerprint prefix and the per-attempt token are each 12
hex characters rather than a full digest. A cell id
must be a single path component: separators, embedded NULs, a Windows drive
specifier such as `D:evil`, and names over 200 bytes are refused before the
first cell runs. That 200-byte limit is what leaves the `.<12>.<12>` suffix
room: 200 plus the two dots and the two 12-character fields is 226, inside the
255 bytes ext4, APFS and NTFS each allow one path component.
The experiment directory is resolved once per run and the run is
refused with `MatrixArtifactError` if it resolves outside the root; a symlinked
`artifact_root` is
honoured, a link from inside the root pointing outwards is not. That check
reads the filesystem as the run begins, and the callback is handed a path, so
it is not a defence against a substitution made concurrently with the run.

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

The `pragma` action reaches its `sqlite3.Connection` in two ways. Without a
`target:` it scans the call's direct arguments and keyword values. With a
`target:` spec it resolves state the callable holds instead of receives:

```yaml
- id: flip-sync
  point: myapp.session.SessionDB.append
  event: entry
  action:
    kind: pragma
    name: synchronous
    value: "OFF"
    target: self._conn
```

`self` is the first positional argument (the receiver for a patched method)
with an optional dotted attribute walk; `param:<name>` binds an argument by
name through the real signature; `result` is the exit-event return value.
Spec syntax is validated when the ruleset loads, and a spec that resolves
for no call leaves an `outcome` record in the firing log instead of
silently doing nothing. The full grammar and failure policy live in
`docs/targeting.md`.

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
