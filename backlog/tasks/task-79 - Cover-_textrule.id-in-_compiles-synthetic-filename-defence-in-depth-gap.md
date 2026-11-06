---
id: TASK-79
title: Cover _text(rule.id) in _compile's synthetic filename (defence-in-depth gap)
status: Done
assignee: []
created_date: '2026-09-16 19:38'
updated_date: '2026-09-30 16:37'
labels:
  - rt-01
  - tests
  - hardening
  - review-followup
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by the RT-01 re-review and confirmed by reverting it: `_compile` builds the synthetic code filename as `f"<pyteman:{_text(rule.id)}:{field}>"` (src/pyteman/patcher.py:24), and replacing `_text(rule.id)` with a bare `{rule.id}` leaves the whole suite green. No test exercises a hostile `rule.id` reaching that f-string.

Severity is defence-in-depth, not guarantee-bearing, and the reasoning is worth keeping so nobody re-rates it later. An f-string on a value with no format spec calls `__format__`; `object.__format__` returns `str(self)` for an empty spec, and a str subclass is accepted unchanged. So a hostile `__format__` or `__str__` on a str-subclass id CAN run user code here, but the result is only a mangled filename inside a code object that is never rendered on the fail-closed path.

The guarantee-bearing use of the same helper is the `!r` now in `_describe_rule` (src/pyteman/patcher.py:108), and that one IS covered, by test_a_hostile_rule_id_costs_neither_the_failure_nor_the_disclosure. A sibling test, test_a_rule_id_that_cannot_be_read_costs_neither_of_them_either, covers the other half of the same hazard: an `id` whose ACCESS raises rather than whose rendering does.

Note that `_compile` runs in Patcher.__init__, the same non-mutating phase `_describe_rule` was moved into, so a failure here also costs nothing to unwind. That is a further reason the severity stays low, and it is not a reason to leave the call site untested.

Not done inside the RT-01 tranche because that tranche is scoped to completing the RT-01 guarantees exactly and the orchestrator ruled out new work beyond them.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A test builds a Rule whose id is a str subclass with a hostile __format__ or __str__ and drives it through Patcher construction, asserting the compile does not raise and the failure path still reports normally
- [x] #2 The test is proved non-vacuous by reverting _text(rule.id) to a bare rule.id at patcher.py:24 and observing the new test fail while the rest of the suite passes
- [x] #3 Backup taken before the temporary revert and the file restored with sha256 verified identical afterwards
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #38. Added lines already present on master per PR: #38 1/16=6%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.

Merged 2026-09-30 via #210 (7e61280). Evidence under /home/pantinor/pyteman-evidence/t191/: diff79.patch sha256 1f2b2c04, tree79-hold2.sha256, mutants-79.log, VERDICT-79*.md in t191rev.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by PR #210, squash-merged as 7e61280 on master at 2026-09-30 16:36Z. AC1: the test builds a duck-typed rule (no stash, so _compile's filename f-string is actually built) whose id is a str subclass with both hostile halves, drives it through Patcher construction, and asserts the compiled when-code's co_filename carries the sanitised id as an exact str. AC2: the non-vacuousness is mechanised and doubly proven: the revert mutant and the normalisation-drop mutant both die on THIS TEST ALONE (targeted single-test runs) and in the full battery. AC3: the backup-and-restore discipline is the battery's byte-exact sha256 verification. The review's CHANGES REQUESTED at the first head (wrong module's path through the stash short-circuit; BoomStr leaving the normalisation inert) drove the repair; APPROVED at the final head. Supersedes #38, closed with a pointer. Gates at e3cc982: suite 1548 passed 3 skipped, check green, delivery 41.
<!-- SECTION:FINAL_SUMMARY:END -->
