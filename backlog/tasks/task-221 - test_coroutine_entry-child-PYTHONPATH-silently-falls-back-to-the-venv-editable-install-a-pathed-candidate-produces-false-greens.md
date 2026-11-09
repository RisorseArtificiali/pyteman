---
id: TASK-221
title: >-
  test_coroutine_entry child PYTHONPATH silently falls back to the venv editable
  install; a pathed candidate produces false greens
status: To Do
assignee: []
created_date: '2026-11-08 23:17'
labels:
  - tests
  - review-finding
dependencies: []
references:
  - tests/test_coroutine_entry.py
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found 2026-11-09 by the TASK-85 skeptic (strongest remaining doubt). tests/test_coroutine_entry.py builds its child PYTHONPATH as `tmp:SRC` (lines ~19 and ~80), where SRC is the package directory of whatever tree the venv resolves. When a candidate tree is merely pathed rather than installed (the standard probe rig: copy the tree, run the worktree venv interpreter with PYTHONPATH pointed at the copy), the child process falls through to the venv's editable install and silently tests the ORIGINAL worktree instead of the copy: a false green for exactly the class of change these subprocess tests exist to catch (the skeptic's first probe C run was void for this reason and produced a wrong all-green before the rig was corrected by hand with uv pip install -e of the copy). The hazard is the known PYTHONPATH-is-not-isolation memory, live in the shipped rig. Fix direction: the child harness should fail closed when the pyteman it imported does not resolve inside the tree the test meant to exercise (assert pyteman.__file__ startswith the intended root in the child, or pass the intended root and refuse to run on mismatch), so a mis-pathed rig announces itself instead of quietly passing.
<!-- SECTION:DESCRIPTION:END -->
