---
id: TASK-39
title: OPT-03. Misurare overhead e crescita dello stato prima di ottimizzare
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
  - TASK-4
  - TASK-6
  - TASK-10
  - TASK-11
  - TASK-12
  - TASK-13
  - TASK-18
  - TASK-16
  - TASK-22
  - TASK-23
  - TASK-24
references:
  - 'src/pyteman/patcher.py:24-26,104-108'
  - 'src/pyteman/actions.py:68-84'
  - 'src/pyteman/firing.py:25-29'
  - 'src/pyteman/barriers.py:5'
documentation:
  - doc-1
  - doc-2
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P3, PROPOSTA, aperto.

**File:** `src/pyteman/patcher.py:24-26,104-108`, `src/pyteman/actions.py:68-84`, `src/pyteman/firing.py:25-29`, `src/pyteman/barriers.py:5`.

**Evidenza di opportunità:** ogni import attraversa tutte le regole in _patch; ogni firing scrive e flush-a il log; seen_keys, nomi di barriere e messaggi outcome distinti non hanno un limite intrinseco. Nessuna regressione di performance quantificata in questo audit.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 benchmark riproducibili con versione/ambiente e confronto baseline; ottimizzazioni accompagnate da numeri reali e test di semantica.
- [ ] #2 Qualunque logging buffered deve conservare la prova precedente a os._exit secondo policy esplicita.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Proposta iniziale da verificare sul codice corrente, non una correzione già applicata.

benchmark separati per nessuna attivazione, condition falsa, firing con/senza log, molte regole, once_per ad alta cardinalità e molte finestre. Se i risultati lo giustificano, indicizzare per modulo/target e aggiungere lifecycle dello stato. Non sostituire set esatti con eviction che faccia rifire once_per senza cambiare il contratto.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: M1 fino a M4 stabilizzate, LOG-03.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.
<!-- SECTION:NOTES:END -->
