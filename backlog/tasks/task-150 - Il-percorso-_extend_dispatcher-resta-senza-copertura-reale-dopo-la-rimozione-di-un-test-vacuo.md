---
id: TASK-150
title: >-
  Il percorso _extend_dispatcher resta senza copertura reale dopo la rimozione
  di un test vacuo
status: Done
assignee: []
created_date: '2026-09-17 11:03'
updated_date: '2026-11-08 17:15'
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
- [x] #1 Esiste un test in cui _extend_dispatcher viene effettivamente raggiunto, dimostrato dal comportamento (il test va rosso se la chiamata viene rimossa o se il fallimento avviene prima della chiamata) e da mutazioni discriminanti dello stesso, in linea con lo standard che il postmortem di TASK-3 ha stabilito per i test non vacui
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-09-25: PR #42 (branch work/extend-dispatcher-coverage, tree-27) already covers AC#1 and AC#3 with CI green. AC#2 (suspendable gate not applied to dispatcher) not covered by PR #42. pyteman-92 notified tree-27 of the gap.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by direct push 64210b9 on master (base c633045); PR #42 closed with a pointer because its tests targeted the 0.2.0-era API and the extend road is already pinned behaviourally by the master suite (identity, applied growth, both rules firing, rollback, exit merge, and the exit-rule alias refusal with the install door's text). The one genuinely unpinned property, AC2, is now pinned by test_alias_extension_judges_the_original_not_the_dispatcher in tests/test_coroutine_entry.py: on the coroutine alias road it asserts the alias slot keeps the dispatcher that was live, the composite rank is ruleset order rather than arrival order (RULES_ALIAS_ENTRY, shared with the merging-entry test, declares the late rule first for exactly that discrimination), the merged override fires, and the disposition report stays empty. Three discriminating mutations were run against it: a gate re-applied to the dispatcher at the top of the owner-is-self branch fails the identity leg; a no-op _extend_dispatcher fails the rank leg; an arrival-order rank() fails the order pin. Note on AC1's letter: the demonstration is behavioural plus discriminating mutations rather than a literal counter or instrumentation, which is the standard the TASK-3 postmortem established (the removed vacuous test had passed against a deleted refusal) and is stronger than a counter, because it proves the test is load-bearing for the behaviour and not merely that the call happened. Gate chain at the shipping hash: /simplify, /code-review high over two rounds with dispositions verified, skeptic 4/4 CONFIRMED at the prior hash with the final delta confined to reviewer-verified findings, battery green (mqa5o38n: 1598 collected, 1595 passed, 3 declared skips). The fourth copy of the alias-road subprocess prefix flagged in review was filed as TASK-216 rather than folded into this one-test delta.
<!-- SECTION:FINAL_SUMMARY:END -->
