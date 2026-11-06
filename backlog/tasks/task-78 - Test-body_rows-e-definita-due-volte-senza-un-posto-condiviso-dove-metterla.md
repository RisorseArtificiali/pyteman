---
id: TASK-78
title: 'Test: body_rows e definita due volte, senza un posto condiviso dove metterla'
status: Done
assignee: []
created_date: '2026-09-16 19:34'
updated_date: '2026-09-25 12:04'
labels:
  - audit-2026-09-16
  - run
  - proposta
  - test
dependencies: []
references:
  - tests/test_report.py
  - tests/test_report_escaping.py
  - tests/conftest.py
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Emerso dalle review reuse e simplification del gate di TASK-23 (RUN-05).

`body_rows` esiste in `tests/test_report.py` e in `tests/test_report_escaping.py`, con lo stesso nome e lo stesso ruolo. `unescaped_pipes` esiste come helper nominato nel secondo file e come espressione inline nel primo.

In TASK-23 e stato chiuso il rischio concreto, cioe la differenza di comportamento fra le due copie sui caratteri che `str.splitlines` tratta come fine riga e markdown no. Resta la duplicazione.

Non unificato in TASK-23 per due motivi. Primo: la suite non ha alcun meccanismo di helper condivisi. `tests/conftest.py` contiene solo manipolazione di sys.path e nessun helper, e nessuno dei 18 file di test importa da un altro. Introdurlo e una decisione sulla convenzione della suite intera, non una pulizia locale. Secondo: `conftest.py` e condiviso con i test di un altro agente, quindi toccarlo durante lavoro concorrente non e appropriato.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Decidere se la suite adotta un meccanismo di helper condivisi o se la duplicazione resta la convenzione
- [ ] #2 Se adottato: body_rows e unescaped_pipes hanno una sola definizione e i due file la importano
- [x] #3 La scelta vale per tutta la suite, non solo per i due file del report
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Decision: keep the duplication; no shared test helper module.

The suite has 18 test files, none of which imports from another, and `conftest.py` holds only sys.path setup. This self-containment is a deliberate convention: each test module is readable without chasing imports across other test files. Introducing a shared helper module for one 4-line function (`body_rows`) would change this convention for the entire suite while saving roughly 5 lines.

The concrete risk (the two copies diverging on `splitlines` vs `\n`) was already closed in TASK-23, which aligned both implementations. What remains is the duplication itself, and one duplicated function does not warrant an architectural change. If the pattern grows (a third or fourth test module needing `body_rows`), that would be the point to reconsider. Until then, the self-contained convention serves the suite better than DRY would.

No code changes.
<!-- SECTION:FINAL_SUMMARY:END -->
