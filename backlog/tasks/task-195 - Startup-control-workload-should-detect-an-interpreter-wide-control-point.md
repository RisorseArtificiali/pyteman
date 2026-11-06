---
id: TASK-195
title: Startup control workload should detect an interpreter-wide control point
status: To Do
assignee: []
created_date: '2026-09-29 06:20'
labels:
  - audit-2026-09-16
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by the independent review of TASK-161 (F1, Low) at f40464f. Reverting the control point in tests/test_activation_suspendable_startup.py to _collections_abc._check_methods still passes all three tests, because the workload print('WORKLOAD_RAN') never runs an issubclass or isinstance against a collections.abc class. AC1 of TASK-161 is met by the probed inertness of Generator.close, but nothing in the suite pins it. One isinstance against a collections.abc class in the control's workload would make that revert fail on the exit-code assertion.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The control's workload performs an issubclass or isinstance against a collections.abc class, so the refusal tests still share an identical workload
- [ ] #2 A mutation that moves the control point back to _check_methods fails the control test, shown with a restore and sha256 check
<!-- AC:END -->
