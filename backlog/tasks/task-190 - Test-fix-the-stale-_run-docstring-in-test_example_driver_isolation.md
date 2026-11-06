---
id: TASK-190
title: 'Test: fix the stale _run docstring in test_example_driver_isolation'
status: To Do
assignee: []
created_date: '2026-09-28 15:08'
labels: []
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
tests/test_example_driver_isolation.py:128-134, pre-existing at d3b6470 (TASK-31 independent review, observation 4). The _run docstring says 109966 receives the stub path as its expected verdict and ends in mismatch exit 1, but _run appends the ruleset argument only for 111912, so 109966 runs with no expectation at all. Cosmetic: the docstring must describe what the helper does.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The _run docstring states that 109966 runs with no expected verdict and names the exit codes callers actually allow
<!-- AC:END -->
