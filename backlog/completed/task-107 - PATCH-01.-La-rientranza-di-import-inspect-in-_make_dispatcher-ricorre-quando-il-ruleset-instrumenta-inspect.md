---
id: TASK-107
title: >-
  PATCH-01. La rientranza di import inspect in _make_dispatcher ricorre quando
  il ruleset instrumenta inspect
status: Done
assignee: []
created_date: '2026-09-17 02:33'
updated_date: '2026-09-25 14:05'
labels:
  - patcher
  - reentrancy
  - pre-existing
dependencies: []
references:
  - src/pyteman/patcher.py
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`_make_dispatcher` esegue `import inspect` dentro il corpo del metodo, deliberatamente fuori dal `try`, perche' quell'import e' servito dall'hook vivo e un setattr rifiutato di UN'ALTRA regola deve emergere li' come fallimento anziche' essere confuso con un callable non introspezionabile. Quella scelta e' corretta e documentata sul posto.

L'effetto collaterale: se il ruleset instrumenta `inspect` stesso ed esiste almeno una regola con target `param:`, l'import rientra in `_patch` per il modulo `inspect`, che costruisce un altro dispatcher, che importa di nuovo `inspect`. Riprodotto (code review high effort, 2026-09-17): termina con `RecursionError: maximum recursion depth exceeded`, e `uninstall()` restituisce poi `[]` su un ledger che non e' quello che l'operatore aveva chiesto.

Verificato identico anche prima della tranche RT-02, quindi preesistente: RT-02 non lo causa ne' lo peggiora.

Perche' vale la pena guardarlo come una cosa sola: due difetti gia' corretti dentro TASK-2 (la finestra di pubblicazione del ledger, e `slot.original` stantio nel pass 2) hanno la stessa radice, cioe' che `_make_dispatcher` importa mentre l'hook e' vivo. Spostare l'import a livello di modulo eliminerebbe la rientranza alla sorgente, ma va pesato contro la ragione per cui e' li': serve a distinguere il TypeError di un setattr rifiutato da quello di un callable non introspezionabile. Una soluzione deve conservare quella distinzione.

Opzioni da valutare, non ancora decise: import a livello di modulo piu' un canale separato per il fallimento del setattr; oppure una guardia di rientranza per (Patcher, modulo) che renda l'auto-instrumentazione di `inspect` un rifiuto esplicito invece di una ricorsione.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Un ruleset che instrumenta inspect.signature insieme a una regola con target param: non produce RecursionError: o funziona, o viene rifiutato con diagnostica che nomina la causa
- [ ] #2 La distinzione oggi garantita dalla posizione dell'import resta intatta: un setattr rifiutato di un'altra regola non viene piu' classificato come signature non leggibile
- [ ] #3 Dopo l'esito, il ledger e uninstall descrivono lo stato reale: nessun uninstall che riporta [] su un ledger incompleto
- [ ] #4 Test di regressione che riproduce la ricorsione e la pinna al comportamento scelto
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Duplicate of TASK-146 (PR #54). The module-level import of inspect already existed before TASK-146; TASK-146 cleaned up stale comments and added test_param_rule_on_inspect_does_not_recurse which covers AC#1 and AC#4. Identified by tree-27.
<!-- SECTION:FINAL_SUMMARY:END -->
