---
id: TASK-118
title: >-
  RT-02k. SlotOwnershipError nomina solo l'ultimo componente del point, quindi
  non distingue due metodi omonimi
status: Done
assignee: []
created_date: '2026-09-17 03:43'
updated_date: '2026-09-25 13:23'
labels:
  - rt-02
  - patcher
  - diagnostics
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Entrambi i siti che sollevano `SlotOwnershipError` in pass 2 compongono il messaggio come `modname + ":" + slot.name`. `slot.name` e' l'ultimo componente del path dell'attributo, quindi un point come `hermes_state.SessionDB._execute_write` viene riportato come `hermes_state:_execute_write`.

La classe intermedia sparisce. Su un modulo che ha piu' classi con un metodo dallo stesso nome, e su un modulo che ha sia una funzione libera sia un metodo omonimo, il messaggio non identifica il point che ha causato il rifiuto, ed e' un messaggio letto esattamente quando qualcosa e' gia' andato storto e l'operatore deve decidere quale regola togliere.

Il walk completo e' disponibile nel punto in cui l'errore viene costruito, quindi il fix e' la composizione del testo, non un cambio di struttura dati.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Il messaggio di SlotOwnershipError nomina il point come lo ha scritto l'operatore, non solo l'attributo finale
- [x] #2 Vale per entrambi i siti che sollevano l'errore in pass 2
- [x] #3 Un test fissa il testo per un point con walk annidato, es. `mod.Classe.metodo`
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
PR #47, commit 54b0efc on branch `work/slot-ownership-fullpath`. Changed all three `raise SlotOwnershipError` sites (one in pass 1, two in pass 2) from `slot.name` to `slot.specs[0][0].symbol`, which carries the full attribute path. Added `test_slot_ownership_error_names_the_full_walk` using a nested `Inner.fn` walk to assert the full path appears in the message. Full suite: 1191 passed, 2 skipped.
<!-- SECTION:FINAL_SUMMARY:END -->
