---
id: TASK-211
title: >-
  ps probe in _tree_processes runs without a returncode check (clean-tree assert
  passes vacuously)
status: To Do
assignee: []
created_date: '2026-11-06 21:19'
labels:
  - tests
  - review-finding
dependencies: []
references:
  - tests/test_example_process_tree.py
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found 2026-11-06 by the TASK-145 review chain (reuse same-disease sweep). tests/test_example_process_tree.py:254-256: _tree_processes() runs subprocess.run(["ps", "-eo", "pid=,stat=,args="], capture_output=True, text=True) and reads .stdout with no returncode check and no check=True. If ps fails, stdout is empty, found becomes {}, and _assert_no_tree_left's subset assert (line ~287) passes vacuously: a dead probe is indistinguishable from a clean tree, the same silent-degradation shape TASK-145 fixed for the locale probe. Fix: assert the returncode (carrying stderr in the message) before interpreting stdout, matching the suite idiom (~20 sites).
<!-- SECTION:DESCRIPTION:END -->
