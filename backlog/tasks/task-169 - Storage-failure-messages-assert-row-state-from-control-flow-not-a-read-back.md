---
id: TASK-169
title: 'Storage-failure messages assert row state from control flow, not a read-back'
status: Done
assignee: []
created_date: '2026-09-18 10:55'
updated_date: '2026-09-27 02:02'
labels:
  - tech-debt
  - runner
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`/simplify`'s Altitude agent flagged that the rewritten `MatrixStorageError` message in `run_matrix`'s finish-transaction failure branch (src/pyteman/runner/matrix.py, the "...is left at status='running'..." message) is correct by construction (rollback reverts to `_begin_attempt`'s committed state) but is asserted from control-flow reasoning rather than an actual read-back of the row after rollback. The same pattern already exists, unaddressed, at the `_begin_attempt` failure message ("nothing on disk names anything that has") and the attempts shape-check's "Nothing has been changed" wording. This round's rewrite fixed the one call site's wording but left the class-wide pattern untouched elsewhere in the function. Consider whether any of these should read the row back (e.g. via a rollback-then-SELECT) before asserting its state in the message, rather than relying on transactional reasoning alone.
<!-- SECTION:DESCRIPTION:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Merged as e26e960 via PR #148 (head 1ac1d13). Both finish-transaction failure branches (plain sqlite3.Error and the SQLITE_TOOBIG double refusal) now read the attempt row's status back after the rollback and report the observed value, an absent row, or a failed read reported as unobserved; three tests pin the clause. Scoping decisions, recorded per the simplify reviews: the two pre-write schema refusals ('Nothing has been changed') stay reasoned because they fire before any write or DDL, the ordering is enforced by the comment at _ensure_schema, and no SELECT can confirm a claim about the whole database; the _begin_attempt failure stays reasoned because its minted token is internal to that function, so on an INSERT failure the caller holds no attempt_id to read back, and its claim is about the filesystem rather than the row. The absent-row and failed-read branches of the observed clause are untested (only the status='running' branch is pinned): judged not worth forcing a deleted-row or broken-connection fixture for a low-priority diagnostics task; both branches are message text only, reached from the same tested raise. Gates: /simplify combined-angle findings applied (sibling branch healed in the same pass); code-reviewer-typed high review CLEAN with all suspicions cleared against sqlite3 semantics; mutation kills; battery check clean, 1263 passed 2 skipped; independent review APPROVED at 1ac1d13; master CI green.
<!-- SECTION:FINAL_SUMMARY:END -->
