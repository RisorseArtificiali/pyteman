---
id: TASK-224
title: >-
  Kept-home exits other than the rotation raises still leave the scratch home
  with no manifest (scanner raise, readiness timeout, any mid-run exception)
status: To Do
assignee: []
created_date: '2026-11-09 05:33'
labels:
  - examples
  - review-finding
dependencies: []
references:
  - examples/hermes-111912/run_repro.py
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found 2026-11-09 by the TASK-201 final review pass (finding 1 of 7, pre-existing gap surfaced by the set's new handler). The hermes-111912 driver's kept-home contract ("every outcome that keeps the home keeps the diagnosis inside it") is enforced only for the rotation's designed raises, which set 79 wrapped with an emergency DRIVER-ERROR manifest plus SCRATCH-HOME-PRESERVED print; every OTHER failure after the home exists still keeps the home silently: the upstream scanner raising (a path the suite actually injects: test_example_process_tree.py's scanner-raises leg), the readiness timeout _fail, a garbage ready file at the int(open(ready)) read, and any unexpected exception between home creation and the normal manifest write. On those paths the home survives with no manifest.json and no SCRATCH-HOME-PRESERVED line, the silent shape occurrence 9 had. Fix direction: generalize the emergency-manifest handler to the whole try body (a single except around main's post-home region, writing the same DRIVER-ERROR manifest with provenance, killing the tree first per the documented ordering, printing the preserved line, re-raising), or restructure so the manifest write and keep-home decision live in the finally with the verdict-dependent rmtree gated on reaching them. The suite's scanner-raises leg doubles as the discriminating test once the handler covers it (today it exits rc=2 with a kept silent home; after the fix the home carries the manifest).
<!-- SECTION:DESCRIPTION:END -->
