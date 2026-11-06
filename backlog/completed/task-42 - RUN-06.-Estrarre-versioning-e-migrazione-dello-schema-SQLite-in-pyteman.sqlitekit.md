---
id: TASK-42
title: >-
  RUN-06. Estrarre versioning e migrazione dello schema SQLite in
  pyteman.sqlitekit
status: Done
assignee: []
created_date: '2026-09-16 13:42'
updated_date: '2026-09-26 08:15'
labels:
  - audit-2026-09-16
  - run
  - review-followup
  - reuse
milestone: m-3
dependencies: []
references:
  - src/pyteman/runner/matrix.py
  - src/pyteman/sqlitekit/__init__.py
  - src/pyteman/sqlitekit/integrity.py
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Emersa dalla review Reuse del lavoro RUN-01 (TASK-19), 2026-09-16. Non e un difetto: e duplicazione che si paga al secondo consumatore.

src/pyteman/runner/matrix.py contiene ora una piccola infrastruttura generica di schema versionato: sonda PRAGMA table_info, migrazione rename-copia-verifica con rollback completo sul fallimento, tabella schema_meta e rifiuto di un database scritto da una versione piu recente di quella compresa. Nulla di tutto questo e specifico della matrice tranne le stringhe DDL.

src/pyteman/sqlitekit/__init__.py e un file vuoto e sqlitekit/integrity.py contiene un solo classificatore: quel package e la sede stabilita per le preoccupazioni sqlite del progetto.

Costo del rinvio: TASK-22 (RUN-04) aggiunge una seconda tabella versionata per la provenienza per-tentativo. Senza estrazione quel task importa nomi privati con prefisso underscore da pyteman.runner.matrix, oppure copia una seconda volta la sequenza rename/verify/stamp.

Non bloccante per RUN-01. Il momento giusto e prima o durante RUN-04, quando esiste il secondo chiamante.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Una funzione condivisa in pyteman.sqlitekit applica versione, creazione e migrazioni a una tabella qualsiasi, ricevendo DDL e callback di migrazione dal chiamante
- [x] #2 matrix.py usa la funzione condivisa e non contiene piu logica di versioning propria; il comportamento osservabile dei test RUN-01 esistenti resta invariato
- [x] #3 Il rifiuto di un database scritto da una versione di schema piu recente resta attivo e coperto da test
- [x] #4 La seconda tabella versionata introdotta da RUN-04 usa lo stesso meccanismo senza importare nomi privati da altri moduli
- [x] #5 report.py non duplica piu il riconoscimento di una tabella pre-provenance: oggi matrix.py sonda la colonna fingerprint e report.py sonda experiment e fingerprint, due predicati separati sulla stessa nozione. Un solo predicato condiviso, oppure e documentato perche report.py deve restare indipendente
- [x] #6 Il sentinel dello stratum non namespacizzato non e piu scritto a mano in report.py: matrix.py lo definisce come _LEGACY_EXPERIMENT e report.py lo ridichiara implicitamente testando experiment falsy. Va importato o esposto, non riscritto
- [x] #7 Deciso se report.py debba leggere schema_meta invece di dedurre la forma della tabella. Oggi non lo consulta affatto e sniffa PRAGMA table_info, il che e voluto perche rende anche tabelle results scritte da altri produttori: o resta cosi con la ragione scritta nel codice, o passa alla versione registrata
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Extracted schema versioning from matrix.py into pyteman.sqlitekit.versioning: `stored_version()`, `ensure_schema(con, version, setup=callback)`, `SchemaVersionError`. matrix.py delegates via `_setup_or_migrate` callback; `_stored_version` deleted. `LEGACY_EXPERIMENT` made public, imported by report.py (explicit sentinel check replaces truthiness). Column-sniffing independence in report.py documented as deliberate. 10 unit tests for versioning module; 1185 tests pass. PR #117.
<!-- SECTION:FINAL_SUMMARY:END -->
