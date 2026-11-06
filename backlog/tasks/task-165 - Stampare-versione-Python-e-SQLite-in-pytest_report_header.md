---
id: TASK-165
title: Stampare versione Python e SQLite in pytest_report_header
status: Done
assignee: []
created_date: '2026-09-17 21:12'
updated_date: '2026-11-06 20:33'
labels:
  - tests
  - ci
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Il passo aggiunto in .github/workflows/tests.yml nomina la build SQLite solo su GitHub Actions, e come passo separato il cui output sta sopra a quello di pytest invece che dentro. Un hook pytest_report_header in tests/conftest.py metterebbe python e sqlite in testa a ogni esecuzione di pytest: in locale, su qualsiasi altra CI, e in un bug report incollato da un utente. Emerso dalla revisione altitude del fix di ordinamento (commit ac3400d). Costo stimato quattro righe, nessuna modifica ai test. Il passo in CI resterebbe ridondante ma innocuo.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 tests/conftest.py definisce pytest_report_header che stampa sys.version e sqlite3.sqlite_version
- [x] #2 L'intestazione compare in una esecuzione locale di pytest verificata leggendo l'output
- [x] #3 Decisione motivata scritta nel task se il passo in .github/workflows/tests.yml viene rimosso o tenuto
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #25. Added lines already present on master per PR: #25 0/3=0%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Merged as PR #218, squash 84bb3ff, supersedes #25 (closed with a pointer). tests/conftest.py now defines pytest_report_header returning the python and sqlite lines in the same format the CI step emits, so local bare-pytest logs carry their own provenance; the imports were split alphabetically to the prevailing style. Correction to the earlier unmerged summary: the CI workflow step is NOT redundant. pytest 9 suppresses the entire header block under -q (verbosity -1), and every scripted invocation in this repo (dev.py, run_coverage.py, verify_artifacts.py, all CI jobs) passes -q, so on Actions the step is the only recorder of the two versions and must stay; the hook's value is the local run, which is this task's own scope. Gates: battery on 3.13.15 at the exact artifact (candidate-gcl3ldsa, 1570 passed, 3 skips declared), /simplify 3/3 CLEAN, /code-review high two findings dispositioned sound (the -q suppression is by design with CI covered by the step; the python line stays because the task names sys.version), independent APPROVED at 8eca3bf, CI 7/7.
<!-- SECTION:FINAL_SUMMARY:END -->
