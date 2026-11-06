---
id: TASK-45
title: TEST-05. Helper condiviso per le query sqlite nei test
status: Done
assignee: []
created_date: '2026-09-16 13:47'
updated_date: '2026-09-27 06:32'
labels:
  - audit-2026-09-16
  - review-followup
  - reuse
  - test
dependencies: []
references:
  - tests/conftest.py
  - tests/test_matrix_identity.py
  - tests/test_matrix.py
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Emersa dalla review Reuse del lavoro RUN-01 (TASK-19), 2026-09-16. Igiene dei test, nessun impatto sul codice di produzione.

Verificato il 2026-09-16: cinque file sotto tests/ aprono connessioni sqlite a mano (target_mod.py, test_matrix.py, test_actions.py, test_targets.py, test_matrix_identity.py), ciascuno con la propria coppia connect/close. tests/conftest.py contiene oggi solo due righe di manipolazione di sys.path e nessun helper condiviso.

Il costo e duplice. La forma piu diffusa e connect, execute, close senza try/finally, quindi un assert che fallisce lascia la connessione aperta; su Windows questo puo bloccare la rimozione della directory tmp_path, e in generale trasforma un fallimento pulito in un secondo errore che lo maschera. La forma corretta con try/finally esiste in test_matrix_identity.py (funzione query) ed e proprio quella che varrebbe la pena promuovere a fixture condivisa.

Precondizione di coordinamento: test_actions.py e test_targets.py sono sotto ownership di un altro agente nell audit 2026-09-16. Schedulare quando quel lavoro e chiuso.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 tests/conftest.py espone un helper o una fixture che esegue una query sqlite chiudendo sempre la connessione, anche quando l'assert chiamante fallisce
- [x] #2 I file di test che aprono connessioni a mano usano l'helper condiviso e non ripetono la coppia connect/close
- [x] #3 La suite completa passa con PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 senza modifiche alle asserzioni esistenti
- [x] #4 LEGACY_SCHEMA e l'helper legacy_db di tests/test_matrix_identity.py sono promossi a conftest insieme a query: costruiscono un database pre-provenance ed e la stessa cosa che servira a qualunque test di migrazione futuro. Non spostati durante RUN-01 perche conftest.py e un file condiviso fuori dalla ownership di quell'agente
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-09-16, osservazione dal gate reuse di RUN-05, non una modifica applicata. Caso concreto per questo task: tests/test_report.py ripete inline sei volte la stessa sequenza CREATE TABLE results + INSERT di semina. Il nuovo tests/test_report_escaping.py ne ha estratta una versione parametrica in _foreign_db (una riga per caso ostile, la colonna sotto test scelta dal chiamante, piu due righe con result_json illeggibile). Se questo task viene eseguito, _foreign_db e il punto di partenza gia scritto e gia coperto da test, non un helper da progettare da zero. Attenzione pero a una differenza deliberata e non accidentale fra i due file: l'helper body_rows di test_report.py usa splitlines() e quello nuovo usa split("\n"); la direzione corretta dell'unificazione e fissata in TASK-69 e non e quella ovvia.

Scoping decision (2026-09-27, per the four-angle review): the shared helper lives in tests/sqlite_harness.py, a plain sibling module, and not in conftest.py as the ACs name literally, because conftest is a two-line sys.path shim holding nothing else and the suite's established homes for shared test code are exactly such siblings (startup_harness, integrity_corpus, internal_guard), all imported the same way; the deviation is precedent-following, not drift. Deliberately NOT converted, each for a structural reason the review verified: test_actions' pragma connections are held across the action under test (the open connection's pragma state IS the test subject), test_targets' connections are fixture builders creating databases under alternative pragma regimes, target_mod.py is the victim module, test_matrix_attempts' blocker and rival connections deliberately hold the writer slot, and test_matrix_oversized's _rows/_row_bytes must go through _CONNECT because that suite patches sqlite3.connect itself. The third consumer the first pass missed (test_matrix_attempts importing query from test_matrix_identity) is re-pointed to the canonical home; the unused params parameter and three inert noqa markers are gone.

Follow-up filed rather than dropped (review finding 3): the same-shape reads the promotion leaves standing are test_matrix_results.py stored_rows plus inline reads near 221 and 394, test_matrix_concurrency.py _rows (list() vs fetchall), and the no-finally reads at test_report_escaping.py:329 and test_pragma_verification.py:720, plus test_report.py's three inline repetitions of the LEGACY_SCHEMA seed (lines 61, 115, 213) whose parametric replacement the task's own notes already sketched via _foreign_db; recorded here for whichever task takes the report-side test hygiene (TASK-128 is the adjacent umbrella). _foreign_db and _signature_db do not overlap query: they are write builders over the report schema.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Merged as 6b4ef3f via PR #155 (head 74e7902). Gates: /simplify four-angle findings applied (the missed third consumer re-pointed from the test-module import, the unused params parameter dropped, three inert noqa markers removed); code-reviewer-typed high review CLEAN with both conversion shapes, the failure paths, and the dangling-import sweep verified by probe; battery check clean, 1264 passed 2 skipped; independent review APPROVED at 74e7902; PR CI green; master CI green. Scoping decisions and the follow-up read-site list are in the implementation notes: the sibling module over conftest (suite precedent, recorded), the live-connection sites left alone each for a verified structural reason, and the remaining same-shape reads plus the report-side schema seeds filed in the notes for the report-side hygiene task.
<!-- SECTION:FINAL_SUMMARY:END -->
