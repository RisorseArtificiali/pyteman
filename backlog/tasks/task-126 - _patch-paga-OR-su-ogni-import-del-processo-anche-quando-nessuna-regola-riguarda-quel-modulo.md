---
id: TASK-126
title: >-
  _patch paga O(R) su ogni import del processo anche quando nessuna regola
  riguarda quel modulo
status: To Do
assignee: []
created_date: '2026-09-17 04:39'
updated_date: '2026-09-28 18:16'
labels:
  - patcher
  - performance
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Segnalato dal gate di efficienza del 2026-09-17.

`_patch` gira a ogni import servito dal hook, quindi anche per i moduli che nessuna regola nomina. Oggi il cammino comune scorre l'intero `self._plan` e alloca quattro strutture prima di scoprire che non c'e' nulla da fare, e il costo cresce con il numero di regole del ruleset invece che con il numero di regole pertinenti al modulo appena importato.

La forma proposta e' un indice `self._by_module` costruito una volta in `__init__`, che mappa il nome del modulo sulle sole specifiche che lo riguardano. Il cammino comune diventa una singola ricerca in dizionario con uscita immediata.

Da confermare prima di intervenire: che `rule.module` sia davvero immutabile dopo la costruzione del Patcher, altrimenti l'indice si disallinea dal piano. Da misurare prima e dopo su un ruleset realistico, perche' senza un numero questa resta una congettura sul costo.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Un import di un modulo che nessuna regola nomina non scorre piu' l'intero piano
- [ ] #2 L'indice e' costruito una volta sola e la sua validita' rispetto alla immutabilita' di rule.module e' verificata
- [ ] #3 Esiste una misura prima e dopo su un ruleset realistico, non una stima
- [ ] #4 La suite resta verde
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #132. Added lines already present on master per PR: #132 16/31=51%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Built a `_by_module` dict in `Patcher.__init__` keyed by module name. `_patch` pass 1 does a dict lookup instead of scanning the entire plan. Rules whose `module` property raises (duck-typed objects) are parked in `_unindexed` and processed with the original linear scan, preserving the error path. Measured on 500 rules across 100 modules: match case 42.7 us to 6.8 us (6x), no-match case 41 us to 1.6 us (26x). Code review addressed two findings: `except BaseException` narrowed to `except Exception`, and ordinal sort added for the edge case where unindexed and indexed rules share a slot. Suite: 1190 passed, 2 skipped. PR #132. Supersedes TASK-70. Satisfies TASK-110 AC#2.
<!-- SECTION:FINAL_SUMMARY:END -->
