---
id: TASK-49
title: >-
  RUN-09: an interrupted attempt leaves an artifact directory that no row points
  at
status: Done
assignee: []
created_date: '2026-09-16 15:16'
updated_date: '2026-09-18 11:54'
labels:
  - runner
  - provenance
  - confirmed
  - opus-5
milestone: m-3
dependencies:
  - TASK-19
  - TASK-22
references:
  - 'src/pyteman/runner/matrix.py:144-168'
  - 'src/pyteman/runner/matrix.py:582'
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by the TASK-19 (RUN-01) review and reproduced against the tree on 2026-09-16. Rewritten on 2026-09-16 after the duplicate-archive half was closed inside TASK-19; what remains here is the artifact-directory lifecycle and the constraint on existing data.

**Closed elsewhere, recorded so this task is not re-opened for it.** The original task paired two symptoms: duplicated `results_superseded` rows and orphaned artifact directories. The duplicates are fixed in TASK-19. The archive copy is no longer written when the plan is made; for a superseding run it is written in the same transaction as the INSERT that installs the replacement and as the DELETE that drains the legacy row, so it comes into being exactly when the supersession does. Adoption keeps its archive and its UPDATE together in the pre-run transaction, because an adoption is complete the moment it is taken. Pinned by `test_interrupted_supersessions_do_not_accumulate_archive_rows` and by an added assertion in `test_legacy_row_survives_an_interrupt_during_its_replacement`, both proven load-bearing by mutation M24. That fix needed no lease or claim, so it did not have to wait for TASK-22 (RUN-04).

**What is still open.** `_attempt_dir` creates the directory before `run_cell` is called, and the row that would point at it is written only after the callback returns. An interrupt in between leaves a directory on disk that no row in either table references. Every retry of an interrupted cell mints a fresh attempt token, so the orphans accumulate one per interrupt:

    attempt dirs on disk: 3
    orphans (no row points at them): ['c.580d26812ef0.0007dab41db3', 'c.580d26812ef0.08d791a16c77']

This is much less serious than the duplicate rows were. The artifacts of an interrupted attempt are still evidence, and RUN-01 deliberately does not delete the directories of failed or interrupted attempts. What is missing is any record that they exist, so a reader walking the artifact tree finds directories the database cannot explain, and a cleanup cannot tell an orphan from evidence something still points at.

Recording an attempt before it runs is the same mechanism a concurrent claim needs, so it should land with or after TASK-22 (RUN-04) rather than inventing a second one. Distinct from TASK-48 (RUN-08), which is about the archive not recording which run superseded a row.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 An interrupted attempt's artifact directory is reachable from the results database, or its absence from the record is documented in the runner as intended, with the reason stated
- [x] #2 Whatever records the directory does not delete the artifacts of an interrupted or failed attempt: RUN-01 keeps them deliberately, because they are evidence of what was attempted
- [x] #3 Databases already written keep every archived row they hold, duplicates from the pre-fix behaviour included: retroactively deduplicating history would itself be a claim about what happened, so no migration may merge or remove those rows
- [x] #4 The mechanism that records an attempt before it runs is the one TASK-22 (RUN-04) needs for a concurrent claim, not a second one built alongside it
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Closed by the same TASK-22.2 implementation, per this task's own AC4 (same mechanism, not a second one). An attempt's row is written and committed before its directory exists, so a killed/interrupted attempt's directory is always reachable from `attempts` (status='running', never deleted, never reinterpreted as dead/orphaned). Schema v3 is purely additive; no results/results_superseded row is touched. See TASK-22.2's note for the full implementation/verification detail.

Round 2 (2026-09-18): two bugs an independent peer session found in this same mechanism were reproduced and fixed (a foreign attempts table silently accepted instead of refused before the schema_version bump; a finish-failure error message that falsely implied the attempt row didn't exist), each with a permanent red/green-verified regression test, plus a further gap the /simplify Altitude review caught (the attempts-shape check compared column names only, so a foreign table missing the PRIMARY KEY on attempt_id would have passed preflight and then silently accepted a colliding attempt_id insert instead of refusing it) fixed with an explicit PK check and its own regression test. Full detail, including the two /simplify follow-ups filed as TASK-168 and TASK-169, is in TASK-22.2's implementation notes rather than duplicated here, since both tasks share this one implementation. Full suite: 846 passed, 1 skipped. Still uncommitted on branch work/attempt-history, pending commit authorization.

Round 3 (2026-09-18, high-effort code-review gate): three further Important findings in this same mechanism, all fixed, none deferred. A composite-primary-key foreign attempts table (PRIMARY KEY(attempt_id, experiment)) bypassed the round-2 PK check because PRAGMA table_info's pk column is a position within the key, not a yes/no flag; fixed by requiring attempt_id be the sole PK column. The attempts-shape checks still ran after DDL/migration that autocommits, so the "Nothing has been changed" refusal message was false in two reproduced scenarios; fixed by moving those checks before any schema mutation. The finish-transaction's UPDATE on attempts did not check its rowcount, so a concurrently deleted attempts row let a result commit as 'done' with no corresponding attempts row; fixed by mirroring _adopt_stored_rows's existing rowcount-guard pattern. Each fix carries its own red/green-verified regression test. Full detail in TASK-22.2's implementation notes. Full suite: 848 passed, 1 skipped. Still uncommitted on branch work/attempt-history, pending commit authorization.

Closure (2026-09-18): same mechanism as TASK-22.2, closed on the same independently-verified evidence (PR #3 merged to master at af56150, CI run 35341459651 green at head 5c6dc74). Detail in TASK-22.2's notes. All 4 acceptance criteria on this task were already checked. Marking Done.
<!-- SECTION:NOTES:END -->
