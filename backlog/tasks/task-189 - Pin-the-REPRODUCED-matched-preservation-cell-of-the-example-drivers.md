---
id: TASK-189
title: Pin the REPRODUCED-matched preservation cell of the example drivers
status: To Do
assignee: []
created_date: '2026-09-28 04:10'
labels:
  - examples
  - test-coverage
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From the TASK-30 review (worktree /home/pantinor/pyteman-evidence/task179impl/tree, branch work/task30-durable-verdicts). The TASK-30 tests pin six of the ten preservation-matrix cells; unpinned: "REPRODUCED matched -> rc 0, home kept" (both drivers), "111912 CLEAN matched -> home dropped", and "109966 INCONCLUSIVE with expectation -> rc 1". All four are base-inherited behaviors (verified correct by out-of-suite probes: 109966 HOLD_FAIL=wal + expectation REPRODUCED keeps the home at rc 0; 111912 with a fast-teardown ruleset drops the home at rc 0), so nothing changed by TASK-30 is unprotected, but a regression in the keep/drop rule's REPRODUCED side would not be caught. Cheapest pin: one test running the 109966 driver with HOLD_FAIL=wal and extra_argv=["REPRODUCED"], asserting rc 0 plus SCRATCH-HOME-PRESERVED with a manifest whose verdict is REPRODUCED.
<!-- SECTION:DESCRIPTION:END -->
