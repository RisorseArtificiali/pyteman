---
id: TASK-14.1
title: >-
  LOG-01 follow-up: close test-coverage gaps in firing-log round-4
  unlock/acquire poisoning tests
status: Done
assignee: []
created_date: '2026-09-18 13:41'
updated_date: '2026-09-25 14:10'
labels:
  - log
  - test-coverage
  - round-4-review
dependencies: []
parent_task_id: TASK-14
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Round 4 high-effort code review (2026-09-18) of the unified acquire/write/unlock fail-closed structure in src/pyteman/firing.py found no correctness bug, only test-coverage gaps in tests/test_firing.py:

1. test_a_lock_failure_raises_a_firing_log_error (acquire-OSError branch) asserts only the raised exception type, never log._closed, a refusal on a second record(), or a non-blocking flock probe from a second fd. A regression that dropped poisoning on the acquire-OSError path specifically would pass this test today.
2. test_an_unlock_failure_poisons_the_log_... (unlock-OSError branch) asserts log._closed and that a later record() refuses, but unlike the newer interruption tests it never independently proves the flock was released via a second fd's LOCK_EX|LOCK_NB probe.
3. No test covers the combination "unlock fails with OSError (becomes primary) AND os.close also fails", i.e. the close-failure note being annotated onto an unlock-promoted primary rather than only ever onto a write-derived one.

None of these are blocking; the underlying code path is exercised and correct by trace and by the round-4 mutation RED/GREEN cycle, but a future regression in exactly these three branches would go undetected by the current suite.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 #1 test_a_lock_failure_raises_a_firing_log_error also asserts log._closed and a second fd's non-blocking LOCK_EX probe succeeds (proving release), and that a subsequent record() call raises
- [x] #2 #2 the unlock-OSError poisoning test adds the same second-fd non-blocking LOCK_EX probe already used by the interruption tests, not just a log._closed assertion
- [x] #3 #3 a new test covers unlock raising OSError (promoted to primary) combined with os.close also raising, asserting the unlock-derived FiringLogError is what's raised and the close failure is annotated onto it via a note
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
PR #57: https://github.com/RisorseArtificiali/pyteman/pull/57\nBranch: work/firing-log-coverage-gaps (commit 03a15ed on master at 3a38482).\n\nThree test-coverage gaps closed:\n1. test_a_lock_failure now asserts _closed, record refusal, and flock probe (AC#1)\n2. test_an_unlock_failure now has the flock probe matching the interruption tests (AC#2)\n3. New test for unlock-OSError + close-failure combination with annotation check (AC#3)\n\nFull suite: 1191 passed, 2 skipped. /simplify clean (3 agents, no findings). Code review pending.
<!-- SECTION:FINAL_SUMMARY:END -->
