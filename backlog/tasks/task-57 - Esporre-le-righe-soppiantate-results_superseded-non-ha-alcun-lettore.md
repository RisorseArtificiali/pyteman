---
id: TASK-57
title: 'Esporre le righe soppiantate: results_superseded non ha alcun lettore'
status: Done
assignee: []
created_date: '2026-09-16 17:45'
updated_date: '2026-09-26 09:07'
labels:
  - audit-2026-09-16
  - run
  - confirmed
  - spun-off
milestone: m-3
dependencies:
  - TASK-19
  - TASK-21
references:
  - src/pyteman/runner/matrix.py
  - src/pyteman/runner/report.py
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Scorporato da TASK-21 (RUN-03) il 2026-09-16, nel turno in cui il punto e stato misurato, per non lasciarlo come sola nota incrociata.

**Evidenza misurata sullo stato corrente.** `grep -rn results_superseded src/ --include=*.py` restituisce esattamente tre occorrenze, tutte in `src/pyteman/runner/matrix.py`: la CREATE TABLE, la INSERT dentro `_archive`, e una menzione nel docstring di `run_matrix`. Nessuna SELECT, in nessun modulo. `report.py` legge solo la tabella `results`.

**Conseguenza.** RUN-01 ha introdotto la garanzia che nessuna riga storica sparisca senza traccia: ogni riga soppiantata (motivi mismatch, legacy, adopted) viene copiata in `results_superseded` nella stessa transazione che installa la sostituzione. La garanzia e vera e testata, ma non e ispezionabile da chi usa lo strumento: l'unico modo di vedere l'archivio e aprire il db con sqlite a mano e conoscerne il nome. Un archivio che nessuna interfaccia mostra e, dal punto di vista dell'operatore, indistinguibile da un archivio che non esiste.

**Perche non in RUN-03.** Il perimetro assegnato a RUN-03 e contratto del risultato, input falsy/list/None, errori storage contro errori di cella, risorse e diagnostica; l'estrazione di schema o helper condivisi e di refactor e esplicitamente esclusa. Aggiungere un lettore dell'archivio e funzionalita nuova, non una correzione di quel perimetro.

**Da decidere in questo task, non qui.** Se esporre l'archivio come sezione aggiuntiva della tabella markdown gia resa da `matrix_markdown`, come funzione di report separata, o come comando; e se mostrare la colonna `reason` e `superseded_at` per riga, che sono il motivo per cui l'archivio vale piu di un backup.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Un lettore pubblico espone le righe di results_superseded con il loro motivo (mismatch, legacy, adopted) e il timestamp di supersessione, senza richiedere sqlite a mano
- [x] #2 Il lettore si comporta correttamente su un db privo della tabella results_superseded, cioe uno scritto prima di RUN-01 o mai soppiantato, senza sollevare un errore sqlite nudo
- [x] #3 Un test copre almeno una supersessione per ciascuno dei motivi archiviati e verifica che la riga originale sia leggibile dopo la sostituzione
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
TASK-57's three ACs are satisfied by the combination of TASK-48's `superseded_rows()` reader (commit f89fc82) and the additional sqlite_master guard plus reason-coverage tests (commit fac6982 on branch `work/task-57-superseded-reader`).

The reader returns dicts with all archive columns including `reason`, `superseded_at`, `displaced_by`, and `seq`, ordered by seq DESC. Pre-RUN-01 databases (no `results_superseded` table) return `[]` instead of raising `OperationalError`, via a `sqlite_master` probe before the query.

Five new tests cover: legacy db without the table, empty db with unrelated tables, mismatch reason, legacy reason, and adopted reason. Each reason test drives the full `run_matrix` pipeline end-to-end and asserts the archived row's reason, cell_id, result_json, and superseded_at.

PR #120 on branch `work/task-57-superseded-reader`. Full suite: 1213 passed, 1 skipped. Gates: /simplify (3 agents, all clean), code-review (no issues at >= 80%), /pa:reflect (READY).
<!-- SECTION:FINAL_SUMMARY:END -->
