---
id: TASK-168
title: Factor the attempts/results column-mismatch idiom into one shared helper
status: Done
assignee: []
created_date: '2026-09-18 10:55'
updated_date: '2026-09-25 13:33'
labels:
  - tech-debt
  - runner
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`/simplify`'s Reuse agent flagged that the new attempts-table shape check in `_ensure_schema` (src/pyteman/runner/matrix.py) reimplements the "PRAGMA table_info -> compare to expected column set -> raise MatrixIdentityError with unknown/missing breakdown" idiom that `_migrate_v1_to_v2` already has (same file, ~line 359). Applied the unknown/missing diagnostic breakdown inline in this round (so the new check's error message is no worse than the existing one), but did not extract a shared helper (e.g. `_require_columns(con, table, expected)`) because that would edit `_migrate_v1_to_v2`, which is already-gated code from a prior round, outside this round's reviewed diff. Worth doing as its own small refactor: extract the shared column-check-and-raise idiom into one helper both call sites use.
<!-- SECTION:DESCRIPTION:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
PR #50, commit dd8a0aa on branch `work/require-columns-helper`. Extracted `_column_mismatch(actual, expected)` in matrix.py, replacing inline unknown/missing computation at both `_migrate_v1_to_v2` and `_ensure_schema`. Helper placed next to the column constants. 139 matrix tests pass; no output change.
<!-- SECTION:FINAL_SUMMARY:END -->
