---
id: TASK-159
title: >-
  The refusal message string is joined eagerly for every slot on every import,
  and read only when something raises
status: Done
assignee: []
created_date: '2026-09-17 11:25'
updated_date: '2026-11-08 20:23'
labels:
  - audit-2026-09-16
  - opus-5
  - efficiency-gate
  - task-3-followup
  - performance
dependencies: []
references:
  - 'src/pyteman/patcher.py:1083'
  - 'src/pyteman/patcher.py:1098'
  - 'src/pyteman/patcher.py:1164'
  - 'src/pyteman/patcher.py:1309'
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Efficiency gate on TASK-3, 2026-09-17. This one is not startup-only, which is what makes it worth filing.

src/pyteman/patcher.py:1083 computes current = "; ".join(d for _, _, _, d, _ in slot.specs) at the top of the install loop. It sits ahead of the `live is _ABSENT` skip at 1098 and ahead of both extend branches, so every slot pays it on every pass, including slots that are then skipped. Its only two readers are the SuspendableTargetError message at 1164 and the _note at 1309, both of which run only when something raises.

Measured 1.53 us per single-spec slot and 2.08 us for three specs, against 0.18 us for indexing the tuple.

_patch runs on every __import__ of an instrumented module, and a re-import takes the `owner is self` extend branch, which still pays the join per slot. On a 5-point patched module, best of 9 across three process pairs, a re-import costs 40.3 to 44.8 us as written and 34.8 to 43.0 us with a single-spec fast path on that line. That is roughly 5 to 8 us, or 12 to 18 percent of the repeat-import cost, spent rendering a string nobody reads. Baseline for an uninstrumented re-import is 3.1 us. Any workload with an import inside a function body pays this per call.

The fix with byte-identical output is to carry slot.specs, or the slot itself, in `current` and do the join at the two consumers. Both consumers join strings that Rule.__init__ already rendered, so moving the join inside the handler does not weaken the existing rule against reading rule fields from an except block.

Pre-existing code. TASK-3 added the second consumer at 1164 and did not create the eager join, so fixing it there would have been a drive-by change to a hot path outside the assigned surface.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 La join della descrizione non viene piu' eseguita sul percorso normale: e' fatta solo dai due consumatori che la leggono davvero.
- [ ] #2 Il testo del messaggio di rifiuto e della nota resta identico byte per byte a quello attuale, provato da un test che confronta la stringa.
- [ ] #3 Il re-import di un modulo gia' instrumentato non paga piu' la join per slot; misurato prima e dopo con output reale registrato.
- [ ] #4 Nessun campo della regola viene letto dentro un except block: i due consumatori uniscono stringhe gia' rese da Rule.__init__.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #51. Added lines already present on master per PR: #51 6/53=11%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closure restored 2026-11-08 (tracker repair): the day-3 Done marker was lost to a working-tree revert; the work had landed. Landed by direct push b2eb726 after code-review at 989d7bf (two comment fixes) and a measurement recorded for AC3 (microbenchmark 740-860 ns/slot at 1-4 specs, durable at t159rev/measurement.txt); superseded PRs #51 and #67 closed with pointers. Full chain in the durable handoff, day-two pair resolution.
<!-- SECTION:FINAL_SUMMARY:END -->
