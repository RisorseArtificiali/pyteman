---
id: TASK-102
title: Remove facts pinned three times over in the integrity tests
status: To Do
assignee:
  - tree-28
created_date: '2026-09-17 00:32'
updated_date: '2026-09-28 18:16'
labels:
  - audit-2026-09-16
  - sql
  - cleanup
  - deferred-from-task-24
milestone: m-3
dependencies:
  - TASK-24
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Redundancy found by the TASK-24 simplify reviewers in test code approved under TASK-25, left in place because deleting approved assertions is outside what TASK-24 was dispatched to change. Each item is a fact already pinned exactly somewhere else, so a behaviour change reddens several tests where one would localise it.

1. tests/test_integrity_classification.py: the loop asserting five samples are not CLEAN. Every one of the five has its status pinned to a specific value elsewhere in the same file, and equality to any other status entails inequality to CLEAN, so the loop asserts nothing new. The reviewer confirmed all five pins by line number.

2. tests/test_integrity_classification.py: `test_declining_that_sentence_costs_no_coverage_of_the_damaged_database` is the third pin of one sample's verdict, after the parametrized FTS test and tests/test_integrity.py::test_fts_corruption. Its value is the argument in its docstring rather than its assertion. Deliberately kept by TASK-24 because it is the only place the claim and its proof sit together; revisit once the corpus carries expected verdicts as data, which would make the point differently.

3. tests/test_docs_integrity.py: `DOCUMENTED_PROCEDURES` is `set(BODY_BY_NAME)` and both consumers read it as a membership test and a sort key, which the dict answers directly. The comment on it belongs on the parsing step above.

4. src/pyteman/sqlitekit/integrity.py: the comprehension variable `l` where the two neighbouring comprehensions use `s` and `line`. Three names for one thing in nine lines, and the one a linter objects to.

5. The account of why the FTS criterion changed is written out three times over: the module docstring, docs/integrity.md and the corpus notes. Each was individually justified and the set of them drifts as a unit, which TASK-24 saw happen when two of the three went stale from one edit. Decide which one is canonical and have the others point at it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Each fact identified above is pinned in exactly one place and the perimeter test count drops by the number of assertions removed
- [ ] #2 No assertion is removed without confirming by line number where the fact it asserted remains pinned
- [ ] #3 The account of the FTS criterion change has one canonical home and the other two sites reference it rather than restating it
- [ ] #4 The full integrity perimeter passes after the removals
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #76. Added lines already present on master per PR: #76 0/39=0%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Each fact that was pinned three times now has exactly one canonical assertion. The != CLEAN loop was removed (5 samples already pinned by exact-status parametrized tests). test_declining_that_sentence_costs_no_coverage_of_the_damaged_database was removed (the verdict is pinned by the parametrized FTS corruption test and test_fts_corruption in test_integrity.py). DOCUMENTED_PROCEDURES = set(BODY_BY_NAME) was eliminated; three call sites now use BODY_BY_NAME directly. The FTS criterion change narrative is consolidated to docs/integrity.md; the module docstring and three corpus notes point there. Comprehension variable l renamed to line.

Perimeter: 284 passed (down from 285). Full suite: 1189 passed, 2 skipped. PR #76 on branch work/integrity-triple-pinned-facts.
<!-- SECTION:FINAL_SUMMARY:END -->
