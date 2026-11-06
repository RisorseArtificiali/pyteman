---
id: TASK-63
title: >-
  Report: una tabella results con experiment ma senza fingerprint perde la
  colonna experiment
status: Done
assignee: []
created_date: '2026-09-16 18:22'
updated_date: '2026-09-25 10:58'
labels:
  - audit-2026-09-16
  - run
  - confirmed
  - from-code-review
milestone: m-3
dependencies:
  - TASK-21
references:
  - 'src/pyteman/runner/report.py:50-60'
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Trovato dalla code review high di RUN-03 (TASK-21), confidenza 85, riprodotto. Non corretto in RUN-03 perche il ramo interessato e codice RUN-01 (TASK-19) gia approvato, e il perimetro di RUN-03 in report.py copre solo la guardia di connect, il ramo tabella assente, il wrapper DatabaseError e il rendering della signature.

**File:** `src/pyteman/runner/report.py:50-60`.

**Difetto:** `if not {"experiment", "fingerprint"} <= columns` manda al ramo pre-provenance qualunque tabella a cui manchi anche una sola delle due colonne. Quel ramo seleziona solo `cell_id, status, result_json` e antepone `(None, None)`, quindi una tabella estranea che dichiara `experiment` ma non `fingerprint` si vede scartare la colonna experiment che possiede.

**Evidenza:** tabella `results(experiment, cell_id, status, result_json)` con una sola cella sotto `rev-A` e `rev-B`, resa:

    | (pre-provenance) | same | done | CLEAN |
    | (pre-provenance) | same | done | CLEAN |

Due righe identiche byte per byte. E esattamente la collisione che il docstring di `matrix_markdown` (righe 100-105) dichiara di esistere per impedire, e l'etichetta `(pre-provenance)` stampa "cio che ha prodotto questa riga e ignoto" sopra righe che il loro esperimento lo dichiarano: la sovrascrittura contro cui e scritto il commento di testata del modulo (righe 4-9).

**Raggiungibilita:** solo database estranei. Lo schema v1 di questo runner non ha nessuna delle due colonne, il v2 le ha entrambe. Ma rendere tabelle estranee e proprio cio che `_read` promette di fare, quindi non e un caso ipotetico.

**Nota sul commento esistente:** le righe 54-58 giustificano il requisito di entrambe le colonne solo con "altrimenti la query fallirebbe". Non considerano che il fallback rende male invece di fallire, che e il caso peggiore dei due.

**Direzione proposta, da verificare:** selezionare `experiment` quando c'e e `NULL` per la colonna mancante, invece di trattare l'assenza parziale come assenza totale.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Una tabella results con experiment ma senza fingerprint rende la colonna experiment invece di scartarla, e due righe con experiment diversi restano distinguibili.
- [x] #2 Una tabella senza nessuna delle due colonne continua a rendere (pre-provenance) come oggi, con test di non regressione.
- [x] #3 Il commento alle righe 54-58 dice perche l'assenza parziale e trattata come e trattata, non solo che la query fallirebbe.
- [x] #4 Test che copre le tre forme: entrambe le colonne, solo experiment, nessuna delle due.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Fix minimo _read in runner/report.py: selezionare experiment e fingerprint indipendentemente quando presenti, NULL per la sola colonna assente; forma tuple e rendering labels invariati, ordine experiment/cell coerente. SQL identifiers solo letterali fissi scelti dalla presenza colonne, nessuna interpolazione arbitraria. Nessuna migrazione o scrittura DB, nessun refactor matrix.

Test quattro combinazioni provenance (both, experiment-only, neither, fingerprint-only), due experiment/cella stessa con inserimento inverso e output distinguibile/ordinato, result JSON mapping valido, legacy labels e required-columns error invariati. Mutante guard originale uccide experiment-only. Commento preciso e conciso, doc extra solo necessario. Base2b3f1d7 export/venv proprio, simplify mirato e review finale indipendente su patch/hash immutabile, coordinator pubblica.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Scout selezionato dal backlog prima probe, prerequisito TASK21 Done. Conferma indipendente coordinator su shared2b3f1d7: results(experiment,cell_id,status,result_json) con rev-A/rev-B e signature CLEAN produce due righe pre-provenance identiche. Evidenza ~/pyteman-evidence/task63-probe-l0ohc2a1. Esclusione PR5-16 non è divieto sul file report.py; TASK63 è ramo esplicitamente differito, quindi procedere senza rilitigare unità merged. TASK64 seconda proposta non riprodotta né assegnata, nessun claim di bug verificato in questa sessione.

PR17 MERGED61a5b55513c554b227a73fe4de2f8a9a3c213099, commitd6464b97f3555079ce5172f7d33f5d89b1202a79; CI35500202706 success, endpoint review/comments/discussion vuoti prima merge. Duefile byte-exact dal candidatoa6b49065 APPROVED, suite indipendente/shared1151/2skip previsti. Tutte quattro forme optional-columns conservate, no DB writes verificato reviewer, old guard mutant3fail controls verdi. Evidence ~/pyteman-evidence/task63-integration-20260920-103258/.
Done respinto hook per gate delegati non riconosciuti in transcript coordinator. Nessun bypass/retry identico, stato In Progress amministrativo con consegna pubblicata e AC verificati.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed 2026-09-25 by backlog audit. PR#17 merged as commit d6464b9 (preserve partially available provenance columns), CI green. Administratively stuck In Progress. Code published in v0.2.0.
<!-- SECTION:FINAL_SUMMARY:END -->
