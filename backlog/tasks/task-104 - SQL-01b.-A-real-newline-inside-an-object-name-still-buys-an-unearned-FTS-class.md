---
id: TASK-104
title: SQL-01b. A real newline inside an object name still buys an unearned FTS class
status: To Do
assignee: []
created_date: '2026-09-17 01:55'
updated_date: '2026-09-28 18:16'
labels:
  - audit-2026-09-16
  - sql
  - follow-up
  - confirmed
milestone: m-3
dependencies:
  - TASK-24
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Residue left by TASK-24, named in shipped code and documentation before this task existed, which is why it is filed now.

TASK-24 fixed the family of invented line boundaries: classify_integrity split its input with str.splitlines(), which breaks on \v, \f, \r, \x1c, \x1d, \x1e, \x85, U+2028 and U+2029. SQLite emits none of those as a line break, and an object name may contain any of them, so the parser manufactured a line out of a character the user chose and then anchored an FTS needle on it. The split is now text.split("\n"), and that closes every one of those nine.

It does not close \n itself, and no rule reading text alone can. SQLite emits object names unquoted into PRAGMA integrity_check findings, so an index named with an embedded newline produces one row whose text is byte for byte what two findings would look like. Confirmed on SQLite 3.51.2, in process:

    index name: "x\nmalformed inverted index for FTS5 table main.t"
    PRAGMA integrity_check returned ONE row:
      row 1 missing from index x
      malformed inverted index for FTS5 table main.t
    classify_integrity: damaged ["FTS_CORRUPTION"], unclassified ["row 1 missing from index x"]

The database held no FTS of any kind. The reproduction is the deterministic-function trick used by the live section of tests/test_integrity_classification.py: an expression index over identity(x) with identity re-registered afterwards as x + 1, which puts the index out of step without touching any page.

A second shape of the same defect: an index named "x\n*** in database main ***" produces a line that _is_header drops, so the evidence leaves the capture entirely and unclassified comes back short rather than merely unread.

Fixing this needs a source of truth the text does not carry. The candidates worth measuring are reading the rows of the pragma one at a time rather than joining them (sqlite3 returns one row per finding, and the join in _capture is what destroys the boundary in the first place), and consulting sqlite_schema for the names actually present before trusting an anchored match. The first looks cheap and may close it outright for the in-process caller while leaving the shell-capture caller exposed, which would be worth stating rather than hiding.

Pinned by test_a_real_newline_inside_a_name_is_the_residue_task_104_holds in tests/test_integrity_classification.py, which asserts the WRONG verdict on purpose. That test fails when this task lands, and that failure is the signal.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A capture whose object name contains a real newline no longer reports an FTS class the database has not earned, or the task records with measurement why no parser reading the pragma can decide it and what the caller must do instead
- [ ] #2 The in-process path and the shell-capture path are stated separately, since a fix that reads rows individually helps only the first
- [ ] #3 test_a_real_newline_inside_a_name_is_the_residue_task_104_holds is updated from tripwire to assertion of the correct verdict, and the header-swallow shape is covered too
- [ ] #4 docs/integrity.md stops describing this as residue and records what closed it, with the tool version measured
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #93. Added lines already present on master per PR: #93 22/164=13%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added `classify_integrity_rows()` to `src/pyteman/sqlitekit/integrity.py`, closing the false FTS_CORRUPTION verdict that a newline inside an index name caused through the text-based `classify_integrity()`. The new function reads PRAGMA rows individually: index-check rows are never split (so a `\\n` in a name stays inside its row), and compound b-tree rows are recognised by the header prefix and split internally. The shell-capture (text) path remains exposed and is documented as such in the function docstring, the module docstring, and docs/integrity.md. Measured on SQLite 3.53.4. Seven new tests: two live-database tests (newline-in-name correct verdict, header-swallow shape) and five basic API tests. PR #97, branch work/integrity-newline-in-name, commit 7d0963b.
<!-- SECTION:FINAL_SUMMARY:END -->
