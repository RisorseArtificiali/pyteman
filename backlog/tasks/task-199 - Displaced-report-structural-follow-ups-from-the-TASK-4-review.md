---
id: TASK-199
title: Displaced-report structural follow-ups from the TASK-4 review
status: To Do
assignee: []
created_date: '2026-09-29 16:54'
labels:
  - follow-up
  - refactor
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Three deferrals from the /simplify altitude review of tree4 at 67c9e2e (2026-09-29), filed the same turn they were read. 1) Ledger identity: displaced() reconstructs the ordinal-to-entries mapping by probing entry[3]._pyteman_composite.rank(); the publish sites (patcher.py ~2914) already hold both facts, so recording served ordinals on the ledger entry (or a side map) at publish time would let displaced() iterate the ledger directly instead of making a private wrapper attribute load-bearing for a public report contract. Sibling of TASK-197. 2) Point-reading contracts: _walk_point is a third shape beside _read_point and _patch's inline walk, with coarser semantics (one try, BaseException to _ABSENT) that erases the absent-vs-raising distinction TASK-124 preserved; either give _walk_point the (value, exc) shape and let displaced() decide, or factor the pure core of _patch's resolution into one shared resolver. The coarse fold is deliberate and docstringed for displaced(), so this is optional hardening, not a defect. 3) Disposition rendering: the report prefixes and ordering live in sitecustomize's atexit consumer while the list contracts live in Patcher; a second consumer would have to copy the prefixes. If a second consumer ever appears, move rendering into Patcher ((disposition, described) pairs or ready lines) and leave sitecustomize the writer.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Decide and record whether each of the three lands or is declined with the single-consumer / coarse-fold rationale
<!-- AC:END -->
