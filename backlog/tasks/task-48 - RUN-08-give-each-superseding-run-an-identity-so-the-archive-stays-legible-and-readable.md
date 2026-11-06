---
id: TASK-48
title: >-
  RUN-08: give each superseding run an identity, so the archive stays legible
  and readable
status: Done
assignee: []
created_date: '2026-09-16 14:05'
updated_date: '2026-09-27 21:58'
labels:
  - runner
  - schema
  - provenance
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`results_superseded` records which row was displaced but not which run displaced it. Two consequences remain from that gap, both found by the TASK-19 (RUN-01) code review and both optional: the archive is already complete and lossless, it is just not fully legible.

1. Repeated supersessions of the same cell accumulate rows that are indistinguishable from one another. The only ordering column is `superseded_at`, populated from `time.time()`, which is not monotonic: an NTP step backwards reorders the archive. Nothing is lost, but the order in which displacements happened cannot be recovered from the table.

2. Nothing reads `results_superseded` back. It is written on every supersession and is currently only inspectable by hand in SQL, so a caller who supersedes a row has no supported way to recover what was displaced. This overlaps TASK-21, which already carries a note that the archive has no reader.

Scope note: this task touches the schema, so it should land with or after RUN-06 (TASK-42, extracting the sqlite schema versioning).

Resolved in TASK-19, no longer part of this task: artifact directories colliding across a supersession cycle. The original third point here described A, B, A, B over one cell id overwriting the artifacts an archived row still pointed at. That was history loss rather than an optional capability, it contradicted RUN-01's own promise, and it was fixed in RUN-01 by claiming every attempt directory with an exclusive create under an experiment-namespaced path, with `tests/test_matrix_identity.py::test_a_returning_definition_never_reuses_an_archived_directory` pinning the four-run cycle.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Each superseding run carries an identity that is recorded on the archived row and is distinct across two runs of the same cell definition
- [x] #2 Archive ordering does not depend on wall-clock time and survives a clock that steps backwards
- [x] #3 A supported reader returns what was displaced for a given cell, without hand-written SQL
- [x] #4 Existing results databases written by RUN-01 migrate without losing any archived row
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
RICONCILIAZIONE (2026-09-27, PR #175, head 167e4db): il lavoro completato ma non unito (branch work/task-48-supersession-identity, PR #119, scritto contro la v4 che lo stratum split di TASK-50 ha poi occupato) e' stato portato su master come v5: displaced_by (un uuid per invocazione run_matrix) e seq (contatore monotono locale al db, allocato nella transazione dell'insert) sulla tabella results_superseded; migrazione in place per v4 (colonne archive) e per v3 (entrambe le migrazioni in un'apertura, timbro 5, nulla perso; righe pre-esistenti NULL displaced_by onesto + seq backfillato per superseded_at/rowid); superseded_rows(results_db, cell_id=None) lettore supportato (chiude anche TASK-57), coi tre rifiuti in vocabolario pyteman (path irraggiungibile, tabella assente, archivio pre-identita' col rimedio nominato: una run migra in place perche' leggere non scrive). Con esso TASK-42: estrazione di stored_version/ensure_schema/SchemaVersionError in pyteman.sqlitekit.versioning (attributi stored/understood per il rewording nel vocabolario del runner senza parsare i messaggi; report legge la versione attraverso il modulo in modo tollerante dove il runner rifiuta).

GATE (2026-09-27): /simplify combinato 5 finding APPLICATI (il secondo consumatore mancante dell'estrazione; il lettore ignorava le convenzioni di fault del lettore di report (due rifiuti aggiunti + rammo piegato); CREATE schema_meta ridondante lasciato dal porto; lista colonne hand-copiata derivata da _RESULT_COLUMNS; ri-lettura della versione in ensure_schema); BELT high CHANGES-REQUIRED 3 finding APPLICATI (il lettore su archivio pre-v5 perdeva vocabolario sqlite: rifiuto col rimedio + test; il ramo unreadable del rewording senza pin: test a entrambi i livelli + attributi pinned; la fiducia sui db timbrati dichiarata nel docstring). Mutazioni che uccidono: allocazione seq, identita' costante, migrazione archive, rimedio del lettore. Batteria 1338 passed 2 skipped.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Aggiornamento (2026-09-27): chiuso per davvero con il merge fc7f934 (PR #175, che porta questo lavoro su master come schema v5 dopo lo stratum split). Il lettore supportato e' superseded_rows(results_db, cell_id=None) in pyteman.runner.matrix: righe archiviate come dict (tutte le colonne, incluso displaced_by e seq), ordinate per seq DESC, con i tre rifiuti in vocabolario pyteman (path irraggiungibile, tabella assente, archivio pre-identita' col rimedio nominato). Il PR #119 (branch originale, mai unito) e' stato chiuso con un puntatore a #175. Il Final Summary precedente sotto descriveva lo stato pre-riconciliazione (v4, PR #119) ed e' da leggere come storia, non come stato.
<!-- SECTION:FINAL_SUMMARY:END -->
