# pyteman

Rule-based runtime fault injection for Python, inspired by Byteman.

Wrap a function with a YAML rule that fires on entry or exit, under a
condition. The action can inject a sleep, raise an exception, override the
return value, switch a SQLite PRAGMA on a connection passed to the call,
kill the process at the exact injection point (`os._exit`), or hold a named
barrier so two threads meet in the interleaving you want. Each firing is
logged before the action and again after it with the outcome, under a
run/instance/process identity and a sequence number scoped to that instance,
so you can reconstruct both the interleaving and what each attempt actually
did, even across multiple processes or restarts. The second record is the one
that can be missing: a `kill` action never writes it, by construction, and
neither does a process that died mid-action. A firing without it is an unknown
result, never a success. The schema is documented in docs/firing.md.

## Activation contract (safety)

- Put the directory containing `sitecustomize.py` on the PYTHONPATH of TEST
  runs only; that is `src/pyteman`, not `src`. Python imports `sitecustomize`
  as a top-level module from whichever directory holds it. `pyteman.*` itself
  resolves for normal imports via the editable install.
- Without `PYTEMAN_RULES` set, the sitecustomize does nothing and says nothing.
  It imports `os` and `sys`, which the interpreter has already loaded before it
  runs, and touches nothing else: no pyteman module is imported, nothing new
  reaches `sys.modules` beyond the shim itself, and no output is produced.
- Setting `PYTEMAN_RULES` requests activation, and requested activation fails
  CLOSED. No FAILURE between that request and the last callable being wrapped
  is allowed to go quiet: pyteman writes
  `pyteman: refusing to start: <phase>: <detail>` to stderr and halts the
  process with exit code 2, without running your program. The phase says where
  to go look, and there are five: `marker check`, `importing pyteman`,
  `loading rules`, `opening the firing log`, and `installing instrumentation`,
  the last of which is where a rule pyteman cannot plan, and a callable that
  refuses to be replaced, both show up.
  The exit is taken with `os._exit`, which is the only route that both stops
  the workload and keeps the exit code; docs/rules.md explains why the two
  gentler ones do not.
- A point that is NOT THERE is not a failure, and this is the one gap in the
  paragraph above worth knowing before you rely on it. A rule naming an
  attribute its module does not have is skipped rather than refused, on
  activation and on every later import alike, because a rule may legitimately
  name a module this particular run never loads. So a typo in a `point:` costs
  you that rule in silence, and the run exits 0 having injected less than you
  wrote. Check the firing log rather than the exit code to confirm a rule
  actually fired. The full set of checks deferred this way, and why each one
  is deferred rather than hoisted, is under "Checked later, by design" in
  docs/rules.md.
- Patching is atomic under a single thread. A ruleset that fails partway
  through undoes every wrap it made before the failure propagates, on
  activation and on every later import alike. What differs is how you hear
  about it: a failure during activation is the refusal above, while a rule
  whose module is imported later fails as an ordinary traceback out of your own
  `import`. Two threads importing two instrumented modules at once is a
  documented limit, not a guarantee; see the thread-safety entry in
  docs/rules.md.
- The undo behind that is best effort, since restoring an attribute is a
  `setattr` and a container may refuse it. When one does, the wrap stays and the
  failure carries a note saying which attribute and why, so the outcome is
  normally either nothing left behind or an explicit account of what was. One
  shape escapes even that: a failure that cannot carry notes, meaning an
  exception shadowing `__notes__` with something that is not a list, where
  pyteman drops the note rather than let the reporting raise over the error you
  need. Building that note can itself fail too, because every value in it comes
  from your code; what neither can do is cost you the rollback or the exit. A
  failed rendering degrades to `<unprintable T>`, `<unknown type>`,
  `<notes unavailable>` or a rule reported as `<unreadable id>` but still
  located, and in the last
  resort to a count of the attributes
  left wrapped. docs/rules.md has the reasoning.
- With `PYTEMAN_REQUIRE_MARKER=<file>` set, pyteman refuses to start unless
  that marker file exists, through the same refusal path. Callers use the
  marker to pin execution to scratch directories. Never install sitecustomize
  into production venvs or images.

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
`result`/`exc`. They are trusted operator input for test tooling. `fires`
counts the times that rule was reached, not the times the point was called.

Actions: `sleep`, `raise`, `return_value`, `return_none`, `pragma` (reaches
attribute-held connections through `target:` specs, see docs/targeting.md),
`kill` (`os._exit`), `barrier` (role `wait` or `open`).

`return_value`/`return_none` follow Byteman RETURN semantics and depend on the
event. On an ENTRY event the wrapped body is skipped entirely and the override
value is returned in its place. On an EXIT event the original body has already
run and the override swaps the result it produced.

Several rules may share one point, and all of them apply, in the order they
appear in the ruleset. `entry` rules run first; the first one that returns a
value skips the body and every `exit` rule, since an `exit` rule is a
statement about a call that happened, and an `entry` action that raises ends
the call the same way. `exit` rules then run in the same order, each seeing
the previous one's `result`, and the last override wins.
When the body raises, the `exit` rules see `exc` and cannot suppress it.
Composition is within one ruleset: a second `Patcher` over a point the first
is still dispatching on is refused with `SlotOwnershipError` and rolls back
its own writes, where it used to be discarded in silence. Within one ruleset
how the rules arrive does not matter. A rule reaching a point this same
`Patcher` already wrapped on an earlier import, through a module alias or a
second module naming it, joins the dispatcher already there and fires in
ruleset order.
What joins is a second route to the same attribute, not a second copy of the
callable. A module that ran `from target import f` before the wrap holds the
original function itself rather than a way back to the attribute, so calls
through that name never reach the dispatcher and never appear in the firing
log, while `applied` still names the rule as applied. Point the rule at the
module the callers actually go through, or name both points.

Fire gating uses `fire: {mode: ...}` with three modes. `always` is the
default. `once_per <key-expr>` consumes its key only when the condition
passes. `countdown n` fires on the rule's n+1th reach. Both counts are
per-rule, so a rule an earlier short-circuit jumped over does not advance.

The schema is closed: an unknown key is rejected at load rather than
ignored, because a typo like `mss: 250` written next to `ms: 1` would
otherwise leave the rule sleeping a millisecond. Every field, the values it
accepts, and which contracts are checked only when a rule fires are in
docs/rules.md.

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
Runs on one results db are exclusive. A run holds an advisory lock on
`<results_db>.lock` from before it touches the tree or the db until it returns,
and a second runner meeting a held lock raises `MatrixLockError` at once rather
than waiting, because how long another matrix will take is not something this
one can guess. Everything a run reads or changes on the filesystem, in the
database and through the callback happens while the lock is held; the exception
is what taking the lock itself needs, which is the lock file and the directory
it goes in. The argument checks come first and are pure, so a run refused by one
of them touches nothing. A run that fails once the lock is taken, including one
that fails its artifact-root check, may therefore leave the lock file and that
directory behind, and those two are the whole of what the lock added to what a
failed run leaves: a run failing later still leaves the artifact and experiment
directories and the results db, exactly as it did before. May rather than does:
a directory
that was already there is left as it was, and an existing lock file is reused
rather than replaced. Without the lock two
runners both execute the same
cell and both return success to their own caller while the db keeps one result,
so the losing caller is told its result was recorded when another's was.
The lock is released by the kernel, so a runner killed outright leaves nothing
to clear away and the next run acquires it; the exception is a `run_cell` that
forks a child outliving the run, since the child inherits the descriptor the
lock belongs to. It is keyed on the canonical path, so a relative path, an
absolute one and a symlink to one db all contend, while two hard links to it do
not. It is advisory, which binds every caller that goes through `run_matrix`
and nothing that writes to the db by itself. Verified on Linux on a local
filesystem. macOS is unverified, flock over NFS is outside any guarantee, and a
platform without `fcntl` is refused rather than run unprotected. `results_db`
has to name a file: `":memory:"` and `""` are refused, because sqlite gives
each connection its own such database and no later run can resume from one.
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

Every attempt is also recorded in an `attempts` table before its directory
exists or `run_cell` is called: its token, the cell and experiment it belongs
to, the directory it is about to claim, and a status of `running`, committed
in its own short transaction before anything *it* does to the filesystem: the
lock file, the artifact root, the experiment directory, and the results db
itself may already exist from earlier calls, but this attempt's own directory
does not yet. A process killed at any point after that commit leaves the row
exactly as it was.
Nothing in the runner ever reinterprets a `running` row as failed, dead, or
orphaned; retrying the cell mints a fresh token and a fresh row rather than
overwriting or requiring resolution of the old one. Creating the directory can
still fail on its own, almost always a token collision, and unlike a killed
process that failure is caught in the same run that produced it, so it is
recorded at once as a `failed` row against that attempt. Once the cell has run,
the same transaction that writes the `results` row also stamps the `attempts`
row with its outcome (`done` or `failed`, the JSON result, and a finish time),
so a storage failure rolls both back together and leaves the attempt at
`running` rather than asserting a result that was never kept.

`pyteman.sqlitekit.integrity.classify_integrity` reads captured `PRAGMA
integrity_check` output into an explicit verdict: a `status` (`clean`,
`damaged`, `unknown`, `inconclusive`, `no_output`), the signatures it
recognised, every finding line it could not read, a diagnosis, and the raw
text. The unread lines are kept in the order SQLite printed them and stripped
of surrounding whitespace; only the raw text comes back exactly as captured.
Nothing captured, a truncated capture and text it cannot read
are three different answers rather than one empty list, which matters because
the failures that destroy a database are raised rather than printed: an empty
stdout is what a caller gets from a file that is not a database, while a
zero-byte file is a valid empty database that reports `ok`. Text it cannot read
is reported as unread rather than as damage, because that same error channel
carries `database is locked` from a database with nothing wrong with it. The
signature names, and what each one does and does not claim, are in
docs/integrity.md.

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

Quote the `value:`. YAML 1.1 reads the bare words `ON`, `OFF`, `YES` and `NO`
as booleans, so `value: OFF` would arrive as the text `False`. The loader
rejects an unquoted one outright rather than guess what was meant, and only
strings and integers get through.

Quoting settles what the value is, not what SQLite does with it. The value is
interpolated into the statement verbatim and every pragma reads it its own way:

- `journal_mode` takes only its own keywords (`delete`, `truncate`, `persist`,
  `memory`, `wal`, `off`). A quoted `"ON"`, or any integer, loads, runs, and
  leaves the mode exactly where it was.
- `synchronous` and `foreign_keys` take a word or a number, so `"OFF"`,
  `"off"`, `"false"` and `0` all reach the same state.

Neither kind raises on a value it does not recognise, so the statement
returning without error says nothing about whether the setting is in force.
The action therefore reads the pragma back on the same connection and compares
it against the documented vocabulary, and the firing log says which of four
things happened: `pragma_applied`, `pragma_already`, `pragma_mismatch`, or
`pragma_unknown` when no claim can be made at all. A value outside the
documented grammar, or a pragma outside the verified perimeter
(`foreign_keys`, `ignore_check_constraints`, `synchronous`, `journal_mode`),
is reported as unknown rather than as a success, and is never read back: the
read form of a pragma is not always a read, since `PRAGMA wal_checkpoint`
checkpoints and `PRAGMA optimize` runs ANALYZE. Set `PYTEMAN_STRICT_PRAGMA=1`
to have an unverified pragma refuse the experiment instead of reporting it.
The measured matrix is in `tests/test_actions.py` and
`tests/test_pragma_verification.py`.

`self` is the first positional argument (the receiver for a patched method)
with an optional dotted attribute walk; `param:<name>` binds an argument by
name through the real signature; `result` is the exit-event return value.
Spec syntax is validated when the ruleset loads, and a spec that resolves
for no call leaves a `pragma_skipped` outcome record in the firing log,
once per attempt, instead of silently doing nothing. The full grammar and
failure policy live in
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
