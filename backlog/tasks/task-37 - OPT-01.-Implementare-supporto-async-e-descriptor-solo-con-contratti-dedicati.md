---
id: TASK-37
title: OPT-01. Implementare supporto async e descriptor solo con contratti dedicati
status: To Do
assignee: []
created_date: '2026-09-16 12:20'
updated_date: '2026-09-16 12:20'
labels:
  - audit-2026-09-16
  - opus-5
  - opt
  - proposal
milestone: m-6
dependencies:
  - TASK-2
  - TASK-3
  - TASK-5
  - TASK-6
  - TASK-13
references:
  - src/pyteman/patcher.py
  - src/pyteman/actions.py
  - 'README.md:74-87'
documentation:
  - doc-1
  - doc-2
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P3, PROPOSTA, aperto.

**File:** `src/pyteman/patcher.py`, `src/pyteman/actions.py`, `README.md:74-87`.

**Motivazione:** applicazioni Python usano coroutine e descriptor; oggi il comportamento sicuro richiesto da RT-03/RT-06 è il rifiuto. Un supporto reale estenderebbe l'applicabilità senza nascondere incompatibilità.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 test end-to-end await, exception, cancellation, descriptor via classe/istanza; nessun blocco dell'event loop non richiesto.
- [ ] #2 Confronto con comportamento originale quando le condizioni sono false; limiti restanti documentati.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Proposta iniziale da verificare sul codice corrente, non una correzione già applicata.

prima coroutine con wrapper async, sleep non bloccante e cancellation preservata; descriptor con static inspection e corretta ricostruzione del binding. Generator/async-generator sono un passo successivo con semantica esplicita di iteration, close, throw e risultato finale; non inserirli implicitamente nel primo supporto async.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: RT-02, RT-03, RT-05, RT-06, CON-01.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.
<!-- SECTION:NOTES:END -->
