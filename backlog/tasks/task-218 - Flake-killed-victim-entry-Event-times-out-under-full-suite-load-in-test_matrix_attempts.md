---
id: TASK-218
title: >-
  Flake: killed-victim entry Event times out under full-suite load in
  test_matrix_attempts
status: To Do
assignee: []
created_date: '2026-11-08 10:34'
labels:
  - flake
  - runner
  - tests
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
First occurrence 2026-11-08, T113 delivery battery: verify_candidate run candidate-hmo55o10 (base 0613029, delta touching only src/pyteman/patcher.py and tests/test_activation_atomic.py) failed exactly one test, tests/test_matrix_attempts.py::test_a_process_killed_before_its_directory_exists_leaves_its_row_running, with the spawned victim never setting its entry Event within the 30s wait (AssertionError wait(30) False at test line 187; victim traceback shows it dying inside run_matrix before signaling). The test passed 3/3 in isolation and the whole file 10/10 immediately after on the same worktree, and the delta cannot plausibly reach it (multiprocessing spawn race under full-suite load). Same shape as TASK-201's class (load-sensitive concurrency timing) but a different site: file this so the pattern has a record; if it recurs, the remedy candidates are a longer entry wait under battery load or marking the entry signal more robust.
<!-- SECTION:DESCRIPTION:END -->
