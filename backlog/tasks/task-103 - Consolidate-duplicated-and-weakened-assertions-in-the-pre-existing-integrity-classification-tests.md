---
id: TASK-103
title: >-
  Consolidate duplicated and weakened assertions in the pre-existing integrity
  classification tests
status: Done
assignee:
  - tree-28
created_date: '2026-09-17 01:38'
updated_date: '2026-11-08 20:19'
labels:
  - audit-2026-09-16
  - sqlitekit
  - deferred-from-task-24
  - tests
milestone: m-3
dependencies:
  - TASK-24
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Four simplification findings raised against `tests/test_integrity_classification.py` and `tests/integrity_corpus.py` during the TASK-24 review. All four target code that predates TASK-24 and sits outside its diff, so they were deliberately not fixed there: touching them would have mixed unrelated churn into a diff under review and widened a tranche that was reopened for one specific defect. They are filed here rather than mentioned and dropped.

None of the four is a correctness bug. Each is a maintenance cost: a regression in one behaviour is reported more than once, or a test asserts less than the thing it is named for.

**1. Duplicate parametrized case, `tests/test_integrity_classification.py:505-517.** Two entries in the same parametrization exercise the same needle through the same path and differ only in the sample they read it from. One regression prints two failures.

**2. Three near-miss tests that disagree by one assertion, `tests/test_integrity_classification.py:422-454` and `:520-537`.** The near-miss samples are each checked by a test of its own, and the tests are the same shape except that one of them also asserts on `unclassified` while the others stop at the class list. Either the extra assertion is load bearing for all of them or for none; as it stands a reader cannot tell which, and the odd one out looks like an accident rather than a decision.

**3. The weaker sweep, `tests/test_integrity_classification.py:194-196`.** A sweep asserts `!= CLEAN` where the samples it walks support the exact verdict. `!= CLEAN` passes for UNKNOWN, INCONCLUSIVE and NO_OUTPUT alike, so the sweep stays green through exactly the misclassification the corpus exists to catch.

**4. The `btree_index_named_fts` note, `tests/integrity_corpus.py:238-246`.** Same shape as the `fts5_corruption` note that TASK-24 trimmed: the note carries a cross-reference to another sample that nothing resolves, so renaming that sample leaves this note stale and the suite green. `test_the_prose_cites_samples_that_are_in_the_corpus` resolves citations in `docs/integrity.md` only.

Perimeter for any work here: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 <env>/bin/python -m pytest -q tests/test_integrity.py tests/test_integrity_classification.py tests/test_docs_integrity.py`, which stands at 282 passing as of 2026-09-17.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The duplicate parametrized case at test_integrity_classification.py:505-517 is reduced to one case, or its second case is given an assertion the first does not make
- [ ] #2 The three near-miss tests assert the same set of facts as each other, or the one that differs carries a comment saying why
- [ ] #3 The != CLEAN sweep asserts the exact verdict each sample is recorded as having
- [ ] #4 The btree_index_named_fts note no longer cross-references a sample name that no test resolves
- [ ] #5 The perimeter suite still passes and no test outside it regresses
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #75. Added lines already present on master per PR: #75 11/56=19%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.

2026-11-06, landed from the TASK-167 review chain: the changed-text mutation in test_the_unordered_comparison_forgives_order_and_nothing_else is a hand-written literal ('row 9 missing from index i') that matches its neighbors' shape today but would silently lose that property if the surrounding literals ever change. Deriving it (e.g. 'row 9' + rows[1][len('row 9'):]) keeps the mutation shape-preserving by construction. Candidate to fold into this task's consolidation when #75 is revived.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closure restored 2026-11-08 (tracker repair): the day-2 Done marker was lost to a working-tree revert; the work had landed. Landed by direct push 61537fd after three review rounds (v3 applied seven code-review findings plus the uppercase-prefix fix; superseded PR #75 closed with a pointer citing the reshaped tests and the strictly improved coverage). Full chain in the durable handoff, day-two sets.
<!-- SECTION:FINAL_SUMMARY:END -->
