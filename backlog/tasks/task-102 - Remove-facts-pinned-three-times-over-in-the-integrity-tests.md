---
id: TASK-102
title: Remove facts pinned three times over in the integrity tests
status: Done
assignee:
  - tree-28
created_date: '2026-09-17 00:32'
updated_date: '2026-11-08 20:19'
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
Closure restored 2026-11-08 (tracker repair): the day-3 Done marker was lost to a working-tree revert; the work had landed. Landed by direct push 644a7b6 after four review deltas, plus same-session fix-forward 429f777 for the run's first red tip (os.walk on 3.11); superseded PR #76 closed with a pointer. Full chain in the durable handoff, set fifty-sixth.
<!-- SECTION:FINAL_SUMMARY:END -->
