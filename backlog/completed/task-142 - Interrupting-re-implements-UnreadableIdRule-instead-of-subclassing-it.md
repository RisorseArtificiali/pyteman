---
id: TASK-142
title: Interrupting re-implements UnreadableIdRule instead of subclassing it
status: Done
assignee: []
created_date: '2026-09-17 09:44'
updated_date: '2026-09-25 13:31'
labels:
  - tests
  - duplication
  - review-2026-09-17
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Cleanup found by the reuse angle of the /simplify gate on the TASK-2 final snapshot (2026-09-17). Filed rather than applied, because the approving reviewer's instruction was no code change after approval.

The `Interrupting` class defined locally inside `test_an_interrupt_while_reading_an_id_is_not_reported_as_a_bad_rule` (tests/test_activation_atomic.py:2375) re-implements `UnreadableIdRule` (line 314), whose `id` property already raises on read at line 338. The only difference is the exception type, `KeyboardInterrupt` instead of `RuntimeError`.

The file already has the right pattern for this and uses it one place over: `UncompilableUnreadableIdRule` at line 873 subclasses `UnreadableIdRule` and overrides a single line. `Interrupting` should be built the same way.

Cost is small and is maintenance rather than correctness: a future change to the shared fixture's shape (its other fields, its `__init__` signature) updates one of the two and silently leaves the other behind, and the test that drifts is the one pinning the `except Exception` narrowing against the `BaseException` mutant.

Perimeter note: tests/test_activation_atomic.py is mine. This does not touch tests/test_sitecustomize.py, which another agent holds for TASK-34.2.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Interrupting derives from UnreadableIdRule and overrides only the exception it raises, matching how UncompilableUnreadableIdRule is built at line 873
- [ ] #2 test_an_interrupt_while_reading_an_id_is_not_reported_as_a_bad_rule still passes and still fails against the M7_widen_to_baseexception mutant in /tmp/preflight_mutation_battery.sh
- [x] #3 No other fixture in the file re-implements a base that already exists in it
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
PR #49, commit 1500572 on branch `work/interrupting-subclass`. Made `Interrupting` subclass `UnreadableIdRule`, overriding only `module`, `symbol`, and the `id` property (which raises `KeyboardInterrupt` instead of `RuntimeError`). Matches the pattern of `UncompilableUnreadableIdRule`. No other fixture in the file reimplements a base. Full suite: 1190 passed, 2 skipped. AC#2 mutation battery not runnable (script not on this machine); the test's behavior is preserved by construction since the `id` property still raises `KeyboardInterrupt`.
<!-- SECTION:FINAL_SUMMARY:END -->
