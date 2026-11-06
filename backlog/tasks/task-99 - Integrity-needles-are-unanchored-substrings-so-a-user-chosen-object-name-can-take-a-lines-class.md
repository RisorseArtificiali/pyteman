---
id: TASK-99
title: >-
  Integrity needles are unanchored substrings, so a user-chosen object name can
  take a line's class
status: Done
assignee: []
created_date: '2026-09-17 00:04'
updated_date: '2026-09-26 23:37'
labels:
  - audit-2026-09-16
  - sqlitekit
  - deferred-from-task-24
  - confirmed
milestone: m-3
dependencies:
  - TASK-24
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The entries in `_SIGNATURES` are matched with `needle in line.lower()`: unanchored, case-insensitive substrings. SQLite interpolates user-chosen object names into its finding lines, so a name that contains a needle puts that needle inside a line that is about something else.

**Scope of this task after TASK-24 was reopened.** TASK-24 now fixes the FTS half by matching the FTS diagnostics at the start of the message rather than anywhere inside the line. What remains here is the residue on the needles approved under TASK-25: `out of order`, `wrong # of entries in index`, `file is not a database` and `malformed database schema`.

Measured:

    classify_integrity("no such table: out of order")
    -> damaged, ["CANONICAL_ROWID_DISORDER"]

The serious form is not the false class but the suppression behind it. The matching loop breaks on the first needle that hits, so a line naming an index called `"out of order"` that reports a genuine entry-count fault is filed under CANONICAL_ROWID_DISORDER, the correct CANONICAL_INDEX_COUNT is never reached, and `unclassified` comes back empty, so nothing in the verdict says a line was read wrongly rather than not read.

## Correction of this task's original evidence, 2026-09-17

Three claims in the first version of this description were wrong, and they are recorded here rather than deleted because they are what caused the FTS half to be deferred instead of fixed.

**Refuted: "no capture from a genuinely damaged database reaches it", and the related claim that both reviewers tried and could not.** A genuinely damaged database reaches it in five statements, on SQLite 3.51.2:

    con.create_function("identity", 1, lambda x: x, deterministic=True)
    CREATE TABLE ordinary(x); INSERT INTO ordinary(x) VALUES (1);
    CREATE INDEX "fts5: corrupt" ON ordinary(identity(x));
    # then re-register identity as lambda x: x + 1
    PRAGMA integrity_check  ->  row 1 missing from index fts5: corrupt

The index is an ordinary b-tree over an expression, the database holds no FTS of any kind, the damage is real, and the capture is real SQLite output rather than constructed text. The reason the earlier attempts failed is that they tried names embedded in a longer identifier; SQLite prints the identifier unquoted, so a name that IS the needle exactly reproduces the needle exactly.

**Refuted: "anchoring is not the fix."** That was argued from a true premise and a missing step. The shell does prefix its error lines, measured again on shell 3.53.4, and the prefixes form a small closed family with a locator and a colon:

    Parse error in 2nd command line argument: file is not a database (26)
    Parse error near line 1: file is not a database (26)
    Parse error near line 1 of script.sql: near "hello": syntax error
    Error in 2nd command line argument: fts5: missing row 2 from content table 'main'.'messages_fts_content'
    Error near line 1: fts5: missing row 2 from content table 'main'.'messages_fts_content'

Stripping that wrapper and then anchoring keeps the shell path working, which is the combination the original note never considered. TASK-24 implements it for the FTS needles.

**Narrowed: the residue here is not uniformly anchorable, and that is the real reason it stays open.** The two families have different shapes. An FTS diagnostic is a whole message and begins the line, so it can be anchored. `out of order` is a fragment inside a larger finding, `Tree 2 page 2 cell 0: Rowid 2 out of order`, so anchoring cannot be applied to it at all and a different mechanism is needed. `file is not a database` and `malformed database schema` do begin their messages and could move onto the mechanism TASK-24 builds; that was left out of TASK-24 deliberately to keep its scope to the defect it was reopened for, and it is the cheapest thing to do here first.

Acceptance criterion 2 below is already satisfied by the prefix stripper TASK-24 adds and is kept so that this task cannot regress it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A finding line whose object name embeds a needle no longer takes that needle's class instead of its own
- [x] #2 The sqlite3 shell capture path still classifies: a line prefixed by the shell such as Parse error in 2nd command line argument: file is not a database (26) still reports NOTADB
- [x] #3 A test covers the suppression case where a correct b-tree class is lost and unclassified comes back empty
- [x] #4 docs/integrity.md states the hazard and the bound on it
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
## Measured evidence, 2026-09-17 (from the TASK-24 altitude review)

The residue named in this task's description is not hypothetical. Measured against the on-disk module AFTER TASK-24's fix landed:

- `row 1 missing from index file is not a database` -> damaged ['NOTADB'], unclassified=0
- `wrong # of entries in index file is not a database` -> damaged ['NOTADB'], unclassified=0
- `wrong # of entries in index malformed database schema` -> damaged ['SCHEMA'], unclassified=0
- `Tree 1 page 2 cell 0: Rowid 2 out of order` -> damaged ['CANONICAL_ROWID_DISORDER'], unclassified=0

The second and third are the SUPPRESSION shape, identical to the one TASK-24 fixed for the FTS needles: the line is a genuine CANONICAL_INDEX_COUNT finding, the class it deserved is never reached because an earlier needle matched inside the index NAME and broke out of the loop, and `unclassified` comes back empty, so nothing in the verdict marks that a line was misread rather than merely unread.

Reproduction: the procedure recorded in docs/integrity.md for `index_named_fts_message` reproduces each of these by substituting the index name. The count form additionally needs the hidden-index route (writable_schema ON, delete the index row from sqlite_schema, insert rows, restore the row with its own saved rootpage), which needs a file on disk because the schema is re-read on open.

### Why NOTADB and SCHEMA were not simply anchored in TASK-24

The mechanism was present and unused, and anchoring them is a one-word change per row, so the deferral needs a reason better than scope. It is this: anchoring is not evidently safe for these two. `file is not a database` is observed wrapped as `Error: file is not a database`, and that bare `Error: ` form carries no locator, so `_SHELL_WRAPPER` does not strip it (the pattern requires `near line N` or `in Nth command line argument`). Anchoring without first widening the wrapper, or first confirming which capture forms are actually observed, would turn a currently classified real capture into UNKNOWN. That is the fail-closed direction and so not a disaster, but it is a behaviour change that needs its own evidence rather than a one-word edit. Until then `_CONTAINED` carries two meanings at once, 'this needle is a fragment' and 'this row is not yet evidenced', which is a real cost to a reader and is recorded here rather than left implicit.

### Named mechanism for the real fix

So the next person does not re-derive it. Anchoring is a proxy for the actual rule, which is: a needle counts only where SQLite wrote, never inside a slot SQLite interpolated. The rule is reachable from text alone, without a schema. Match each line against patterns derived from SQLite's own format strings, with the %s and %d slots as capture groups, and reject any needle falling inside a captured slot. `row \d+ missing from index (.*)` identifies `fts5: corrupt` as a NAME, and crucially the same machinery handles `out of order` and `wrong # of entries in index`, which anchoring cannot touch at all because they are fragments with no start of their own.

Cost, stated so the estimate is honest: the b-tree check's format strings must be enumerated as well as FTS5's, which is a much larger surface, and the table becomes a small grammar version-locked to SQLite. When an upstream format string changes, its line becomes unparseable, which again falls to UNKNOWN rather than to an invented class.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Merged as ce9a350 via PR #144 (branch work/task99-integrity-needles, heads 05ac308 + the 019bb78 review fixup). Review cycle: first verdict CHANGES-REQUIRED at 05ac308 on one docs defect (the slot-literal enumeration omitting 'of index'; the fix had sat in edit attempts that aborted before writing and nothing re-grepped), fixed and re-approved at 019bb78 with the behavioral sweep carried over (contract points 1-4 held with mechanical evidence; all three corpus samples reproduced byte-for-byte by the reviewer). Gates: /simplify 4-angle findings applied (span-to-cut collapse, fourth tail from pragma.c, frame fix, stale prose, suffix invariant); code-reviewer-typed high review with both findings applied; mutations killed. Non-blocking observations O1 (locator path with ': ' defeats the wrapper strip, fails toward UNKNOWN) and O3 (each test guards a different direction) recorded here.
<!-- SECTION:FINAL_SUMMARY:END -->
