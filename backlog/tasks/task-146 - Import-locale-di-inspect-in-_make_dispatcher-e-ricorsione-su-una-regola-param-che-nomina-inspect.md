---
id: TASK-146
title: >-
  Import locale di inspect in _make_dispatcher e ricorsione su una regola param:
  che nomina inspect
status: Done
assignee: []
created_date: '2026-09-17 11:02'
updated_date: '2026-11-08 20:20'
labels:
  - opus-5
  - deferred-from-task-3
dependencies: []
references:
  - src/pyteman/patcher.py
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Trovato dal gate efficiency durante TASK-3 (2026-09-17), non applicato perche' fuori dalla superficie assegnata e perche' tocca il percorso di parsing delle firme.

`src/pyteman/patcher.py` importa `inspect` a livello di modulo (necessario: l'hook chiama `_patch` a ogni `__import__`, quindi un import dentro il ciclo per-slot rientra in `_patch`). Restano due `import inspect` locali in `_make_dispatcher`, presi solo quando un target `param:` ha bisogno di una firma. Sono ridondanti rispetto al binding di modulo.

Il problema vero non e' la ridondanza ma cosa succede con una regola `param:` su un punto del modulo `inspect`: l'import locale rientra in `_patch` per `inspect`, il pass 1 indicizza le regole di quel modulo, e si ricorre fino a RecursionError. Preesistente a TASK-3.

Aggravante introdotta da TASK-3: `_suspendable_reason` cattura `Exception` e rende il RecursionError come "of a kind that could not be read", cioe' attribuisce al target una colpa che e' dell'infrastruttura.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 I due import locali di inspect in _make_dispatcher sono rimossi e il binding di modulo e' l'unico usato.
- [ ] #2 Esiste un test che attiva una regola param: su un punto del modulo inspect e mostra che il processo non ricorre.
- [ ] #3 Se il caso resta irrisolvibile, il messaggio di errore dice che la ricorsione e' dell'infrastruttura e non un difetto del target.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #54. Added lines already present on master per PR: #54 1/35=2%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closure restored 2026-11-08 (tracker repair): the day-3 Done marker was lost to a working-tree revert; the work had landed. Landed by direct push 0d798c5 (superseded PR #54 closed with a pointer). Full chain in the durable handoff, set fifty-second. The TASK-150-era reference to this task's test as the stronger recursion pin remains accurate: test_param_rule_on_inspect_does_not_recurse covers what the deleted T95 branch test held.
<!-- SECTION:FINAL_SUMMARY:END -->
