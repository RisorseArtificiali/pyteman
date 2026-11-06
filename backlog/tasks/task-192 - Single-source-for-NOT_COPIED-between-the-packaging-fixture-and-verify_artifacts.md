---
id: TASK-192
title: >-
  Single source for NOT_COPIED between the packaging fixture and
  verify_artifacts
status: To Do
assignee: []
created_date: '2026-09-28 19:10'
labels:
  - tests
  - packaging
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
tests/test_packaging.py and scripts/verify_artifacts.py each define NOT_COPIED verbatim, linked only by a 'Mirrors the fixture' comment; no test asserts they match. The .venv fix (TASK-173.2) had to edit both, and the next addition can drift silently. Found by the /simplify simplification review of the TASK-173 follow-ups on 2026-09-28.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The packaging test reads NOT_COPIED from scripts/verify_artifacts.py (importlib spec_from_file_location, as other tests already do) or asserts equality with it
- [ ] #2 A mutation that adds an entry to only one of the two sites fails the suite
<!-- AC:END -->
