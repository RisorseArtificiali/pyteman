---
id: TASK-93
title: >-
  SQL-06. Le fixture legacy di test_integrity.py duplicano il corpus senza
  etichetta di provenienza
status: Done
assignee:
  - tree-28
created_date: '2026-09-16 21:21'
updated_date: '2026-09-30 19:00'
labels:
  - sql
  - follow-up-task-25
  - test
dependencies: []
references:
  - tests/test_integrity.py
  - tests/integrity_corpus.py
  - docs/integrity.md
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Follow-up individuato durante TASK-25 (SQL-02).

tests/test_integrity.py definisce due fixture proprie, `INCIDENT_ROOT` e `CODER_PAOLO_FTS`, che precedono il corpus etichettato introdotto da TASK-25 e ne duplicano il contenuto: `INCIDENT_ROOT` e il campione `mixed_known_and_unknown` senza le due righe di residuo, e `CODER_PAOLO_FTS` e il secondo dei due messaggi FTS5 reali.

Il costo non e la duplicazione in se ma l'assenza di etichetta. Il criterio numero 1 di TASK-25 e che ogni campione dica da dove viene, perche altrimenti un test finisce per asserire che SQLite garantisce una forma che nessuno ha mai osservato. Queste due sfuggono a quel criterio e al test che lo verifica.

Da notare per chi prendera il task: `malformed inverted index for FTS5 table %s.%s` e stato verificato essere una vera format string di SQLite, presente in libsqlite3.so.0 accanto a `fts5: corruption found reading blob %lld from table "%s"`. Le due fixture sono quindi plausibili, non inventate; manca la registrazione della provenienza e della procedura di riproduzione.

Non fatto in TASK-25 perche gli altri quattro test di quel file erano fuori perimetro e la consegna escludeva i refactor.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Le fixture legacy di test_integrity.py o portano un'etichetta di provenienza o vengono sostituite dal campione corrispondente del corpus
- [x] #2 Nessun testo di integrity_check resta definito in due punti con provenienza diversa
- [x] #3 I cinque test originali continuano a coprire le stesse classificazioni di prima
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #73. Added lines already present on master per PR: #73 1/39=2%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.

Merged 2026-09-30 via #214 (9d1314f). Evidence under /home/pantinor/pyteman-evidence/t191/: diff93.patch sha256 416df3ef, tree93-hold1.sha256, mutants-93.log, VERDICT-93.md in t191rev.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by PR #214, squash-merged as 9d1314f on master at 2026-09-30 18:59Z. AC1: the legacy INCIDENT_ROOT fixture is replaced by a reference to the new incident_root corpus sample (OBSERVED, the note stating the page numbers, rowid and index name are the incident's own). AC2: no integrity_check text remains defined in two places with different provenance (the single _INCIDENT_TEXT constant feeds both samples). AC3: the five original tests cover the same classifications. The OBSERVED definition is widened honestly and docs/integrity.md names the incident sample as the exception to the reproduction procedure. Supersedes #73, closed with a pointer. Gates at 6165b41: suite 1570 passed 3 skipped, check green, delivery 41, battery 3/3, independent verdict APPROVED (VERDICT-93.md). The reviewer's informational findings are on the verdict file.
<!-- SECTION:FINAL_SUMMARY:END -->
