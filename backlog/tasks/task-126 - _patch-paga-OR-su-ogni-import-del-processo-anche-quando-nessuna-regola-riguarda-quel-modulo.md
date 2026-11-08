---
id: TASK-126
title: >-
  _patch paga O(R) su ogni import del processo anche quando nessuna regola
  riguarda quel modulo
status: Done
assignee: []
created_date: '2026-09-17 04:39'
updated_date: '2026-11-08 20:24'
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
Closure restored 2026-11-08 (tracker repair): the day-3 Done marker was lost to a working-tree revert; the work had landed. The plan-indexing substance landed via PR #197 (squash b13b535, TASK-70's set, which superseded #132 where this task's index work had been staged); the O(R)-per-import scan is gone from master's _patch (indexed _by_module lookup). Phase-one record in TASK-191 notes, set thirteen.
<!-- SECTION:FINAL_SUMMARY:END -->
