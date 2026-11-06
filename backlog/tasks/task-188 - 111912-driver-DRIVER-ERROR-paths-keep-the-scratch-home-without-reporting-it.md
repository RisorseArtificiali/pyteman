---
id: TASK-188
title: '111912 driver: DRIVER-ERROR paths keep the scratch home without reporting it'
status: To Do
assignee: []
created_date: '2026-09-28 04:10'
labels:
  - examples
  - consistency
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From the TASK-30 review (worktree /home/pantinor/pyteman-evidence/task179impl/tree, branch work/task30-durable-verdicts). The 109966 driver prints SCRATCH-HOME-PRESERVED from its finally on every non-CLEAN outcome including DRIVER-ERROR (_fail) paths; the 111912 driver's preservation logic sits inside the try, so a DRIVER-ERROR (e.g. readiness timeout, empirically reproduced with a nonexistent ruleset: rc=2, home kept, no preserve line, no manifest) leaks the scratch home silently: an operator cannot find it from the output. Base behaved the same, so this is not a regression, but the two drivers now document the same contract ("every outcome except an unambiguous matched CLEAN preserves the scratch home", both READMEs) and only one reports the kept home. Suggested shape: give 111912 the same finally-based report 109966 has (with `matched` initialized before the try so the finally stays total).
<!-- SECTION:DESCRIPTION:END -->
