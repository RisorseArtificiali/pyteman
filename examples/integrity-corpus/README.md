# Integrity corpus reproducers

Executable reproducers for every observed sample in `tests/integrity_corpus.py`.
Each one builds a fresh database, applies the damage procedure documented in
`docs/integrity.md`, captures the `PRAGMA integrity_check` output (or the
exception message, for the error-channel samples), and diffs it against the
corpus text.

## Usage

```bash
python3 examples/integrity-corpus/run_repro.py
```

To reproduce specific samples:

```bash
python3 examples/integrity-corpus/run_repro.py rowid_disorder fts5_corruption
```

## Output

A table of sample name, host SQLite version, and result:

- **matched**: the captured text equals the corpus byte for byte (or as sorted
  lines, since line order varies across builds).
- **matched (structural)**: the text matches after normalizing parts that vary
  per run, such as internal blob ids, page numbers, or rowids.
- **diverged**: the text differs in content, not just in internal addresses.
  This is news about the host SQLite, not a defect in this repository.
- **skipped**: an optional module (FTS5 or FTS4) is missing from this build.

The exit code is 0 unless a reproducer itself errors out. Divergence does not
fail the run, because the host SQLite version is not pinned.

## What this is not

This is not a test suite and not a suite gate. The messages are SQLite's and
the host version is whatever is installed, so a divergence is a report about
SQLite rather than a failure in this repository. Turning it into a red test
would make the suite fail on an SQLite upgrade nobody made here.

## Samples with varying internal addresses

Four samples embed addresses that SQLite allocates at runtime and that the
procedure cannot pin:

- `fts5_corruption`: the blob id of the zeroed block
- `fts5_missing_content_row_message`: the rowid in the message
- `fts5_missing_row_from_healthy_index`: the rowid in the message
- `fts5_shadow_table_btree_damage`: page and cell numbers

These report "matched (structural)" when the message template matches and only
the embedded numbers differ. `orphan_pages` and `malformed_schema_message` are
also normalised, since SQLite 3.53.4 allocates pages differently from 3.51.2
and changed the wording of one error message.
