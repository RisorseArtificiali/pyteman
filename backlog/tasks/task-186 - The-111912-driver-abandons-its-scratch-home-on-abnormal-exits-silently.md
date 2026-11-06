---
id: TASK-186
title: 'The 111912 driver abandons its scratch home on abnormal exits, silently'
status: To Do
assignee: []
created_date: '2026-09-28 01:09'
labels: []
dependencies: []
references:
  - examples/hermes-111912/run_repro.py
  - examples/hermes-109966/run_repro.py
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found during the TASK-28 review (2026-09-28), pre-existing at fa81110, not introduced by the TASK-28 diff. examples/hermes-111912/run_repro.py removes its mkdtemp scratch home (shutil.rmtree at the end of the try) only on the normal flow. Abnormal exits leave it behind with no announcement: the readiness _fail (child never became ready in 10s, exit 2) and any mid-run exception both skip the rmtree, and unlike the 109966 driver (which prints SCRATCH-HOME-PRESERVED: <path> on non-CLEAN) the 111912 finally only kills the tree, so the leftover home is silent. Observed: about 140 h111912-* dirs accumulated in /tmp between 01:07 and 02:48 on 2026-09-28 during TASK-28 iteration (readiness timeouts and mutation runs); /tmp is wiped daily by systemd-tmpfiles, so this is transient, but each abnormal run leaks a dir containing state.db and pyteman.log that nobody is told about. Controlled clean runs (normal flow, any verdict incl. INCONCLUSIVE) always rmtree, verified 2026-09-28. Minimal fix: on the abnormal path print the preserved path the way 109966 does, or rmtree the home in the readiness-timeout branch when nothing is worth postmorteming.
<!-- SECTION:DESCRIPTION:END -->
