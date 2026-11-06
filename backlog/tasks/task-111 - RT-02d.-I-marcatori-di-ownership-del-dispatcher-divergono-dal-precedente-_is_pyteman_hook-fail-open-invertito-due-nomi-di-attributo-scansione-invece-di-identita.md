---
id: TASK-111
title: >-
  RT-02d. I marcatori di ownership del dispatcher divergono dal precedente
  _is_pyteman_hook: fail-open invertito, due nomi di attributo, scansione invece
  di identita'
status: Done
assignee: []
created_date: '2026-09-17 03:09'
updated_date: '2026-09-27 11:29'
labels:
  - rt
  - opus-5
  - review-rt-02
  - coerenza
dependencies:
  - TASK-2
references:
  - src/pyteman/patcher.py
  - tests/test_activation_atomic.py
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Trovato dall'agente altitude della review /simplify su RT-02 (TASK-2), 2026-09-17. Il codice funziona; il reperto e' che RT-02 ha introdotto un SECONDO meccanismo di riconoscimento "roba nostra" che diverge dal primo su tre assi, e nessuno dei tre e' una scelta dichiarata.

Lo stesso file risolve gia' la domanda "questo oggetto e' nostro?" per gli import hook, con `_is_pyteman_hook`. RT-02 la risolve di nuovo per i dispatcher, con `_pyteman_owner` piu' `_inflight` piu' la scansione del ledger. Le due risposte differiscono cosi':

1. **Direzione del fail-open invertita.** `_is_pyteman_hook` in caso di dubbio dice SI', cioe' tratta l'ignoto come nostro, e il costo di sbagliare e' rifiutare un uninstall legittimo. Il percorso dispatcher in caso di dubbio dice NO, cioe' tratta l'ignoto come di nessuno, e il costo di sbagliare e' AVVOLGERE qualcosa che non andava avvolto. Sono due politiche opposte per la stessa domanda nello stesso file, e la seconda e' esattamente il meccanismo della corsa residua di TASK-58.

2. **Due nomi di attributo per lo stesso concetto.** `_pyteman_patcher` e `_pyteman_owner` coesistono. Chi legge il file deve scoprire da solo che non sono la stessa cosa, o peggio assumere che lo siano.

3. **Scansione contro lettura scalare.** L'hook risponde leggendo un attributo. Il dispatcher risponde consultando una mappa e poi, se quella non basta, scandendo una lista. Il costo e' nel task sull'efficienza; qui il reperto e' che la forma della risposta e' diversa per nessuna ragione visibile.

**Tensione da risolvere prima di unificare, NON ignorare.** Il test `test_a_callable_that_synthesises_an_owner_is_a_stranger_not_a_patcher` (tests/test_activation_atomic.py, intorno a riga 2241) pinna deliberatamente che un callable che si SINTETIZZA un attributo di ownership non venga creduto: l'identita' e' decisa internamente dal Patcher, non letta da quello che l'oggetto dichiara di essere. Questo e' anche il motivo per cui `_pyteman_state` e' scritto ma non riletto in produzione, documentato a patcher.py:276. Qualunque unificazione che "semplifichi" tornando a credere all'attributo ROMPE quel test, e va bene cosi': il test e' la specifica, non un ostacolo. L'unificazione giusta porta l'hook verso la disciplina del dispatcher, non il contrario.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Una sola funzione risponde a 'questo oggetto appartiene a un Patcher, e a quale', usata sia dal percorso hook sia dal percorso dispatcher, oppure la divergenza resta ed e' DICHIARATA in un commento che dice perche' le due politiche di fail-open sono opposte di proposito
- [x] #2 La direzione del fail-open di ciascun percorso e' scritta accanto al codice insieme al costo di sbagliare in quella direzione
- [x] #3 _pyteman_patcher e _pyteman_owner sono un solo nome, oppure i due nomi sopravvivono con un commento che dice cosa distingue i due concetti
- [x] #4 test_a_callable_that_synthesises_an_owner_is_a_stranger_not_a_patcher continua a passare senza essere indebolito: l'identita' resta decisa dal Patcher e non letta da cio' che l'oggetto dichiara
- [x] #5 La nota a patcher.py:276 sulla scelta identita'-invece-di-marcatore resta vera dopo la modifica, o viene aggiornata nello stesso diff
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Merged as 25a0a78 via PR #162 (head 13be501, comments-only, gate-exempt). The task's first disjunct satisfied: the divergence is DECLARED at both sites, with each path's fail-open direction and its cost of being wrong written beside the code, and the two marker names documented as one concept per side. AC #4 confirmed: the synthesized-attribute test passes unchanged and unweakened. Battery check clean, 1271 passed 2 skipped; PR CI green; master CI green.
<!-- SECTION:FINAL_SUMMARY:END -->
