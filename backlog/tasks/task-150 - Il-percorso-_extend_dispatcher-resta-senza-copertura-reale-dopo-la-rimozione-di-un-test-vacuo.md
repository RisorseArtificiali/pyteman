---
id: TASK-150
title: >-
  Il percorso _extend_dispatcher resta senza copertura reale dopo la rimozione
  di un test vacuo
status: In Progress
assignee: []
created_date: '2026-09-17 11:03'
updated_date: '2026-09-25 14:38'
labels:
  - opus-5
  - deferred-from-task-3
  - test-gap
dependencies: []
references:
  - src/pyteman/patcher.py
  - tests/test_activation_atomic.py
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Durante TASK-3 (2026-09-17) avevo scritto `test_a_dispatcher_already_on_a_slot_is_not_reclassified` per coprire il percorso di estensione: un secondo rule su uno slot gia' patchato deve estendere il dispatcher e non essere rigiudicato dal gate suspendable.

Due gate indipendenti (simplify e code-review) hanno dimostrato che il test non esercitava nulla. Due regole nella stessa `activate` vengono raggruppate in un solo `_Slot`, quindi `_extend_dispatcher` veniva chiamato zero volte; e il test passava invariato contro una copia del sorgente con il rifiuto rimosso del tutto.

Il test e' stato rimosso invece di essere lasciato verde e falso. La proprieta' che voleva coprire resta non testata: serve una costruzione in cui `_extend_dispatcher` venga davvero raggiunto, per esempio via l'import hook che ripatcha un modulo reimportato.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Esiste un test in cui _extend_dispatcher viene effettivamente chiamato, dimostrato contandolo o strumentandolo.
- [ ] #2 Il test fallisce se il gate suspendable viene applicato al dispatcher invece che al callable originale.
- [ ] #3 Il test fallisce se _extend_dispatcher non viene chiamato affatto, cioe' non e' vacuo come quello rimosso.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-09-25: PR #42 (branch work/extend-dispatcher-coverage, tree-27) already covers AC#1 and AC#3 with CI green. AC#2 (suspendable gate not applied to dispatcher) not covered by PR #42. pyteman-92 notified tree-27 of the gap.
<!-- SECTION:NOTES:END -->
