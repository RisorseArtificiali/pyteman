---
id: TASK-77
title: 'Report: le due etichette di errore sono stringhe ripetute invece che costanti'
status: Done
assignee: []
created_date: '2026-09-16 19:33'
updated_date: '2026-09-30 15:44'
labels:
  - audit-2026-09-16
  - run
  - proposta
  - report
dependencies: []
references:
  - src/pyteman/runner/report.py
  - tests/test_report.py
  - tests/test_report_escaping.py
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Emerso dalla review reuse del gate di TASK-23 (RUN-05).

`(unreadable result)` e `(result is not a mapping)` sono scritte come letterali in sei punti: due in `matrix_markdown` e quattro nei test. Le due etichette confrontabili dello stesso modulo, `_NO_EXPERIMENT` e `_PRE_PROVENANCE`, sono invece costanti che i test importano.

Costo: cambiare il testo di un'etichetta richiede un grep su tre file invece di una modifica in un punto solo.

Non fatto in TASK-23 perche i due punti da toccare in `matrix_markdown` stanno fuori dal perimetro di quel task, in codice gia approvato con RUN-03.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Le etichette diventano costanti di modulo accanto a _NO_EXPERIMENT e _PRE_PROVENANCE
- [x] #2 matrix_markdown e i test le importano invece di riscriverle
- [x] #3 Nessun cambiamento di output: le stringhe restano identiche
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #36. Added lines already present on master per PR: #36 0/16=0%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.

Merged 2026-09-30 via #209 (460f6ed). Evidence under /home/pantinor/pyteman-evidence/t191/: diff77.patch sha256 8ac69f45, tree77-hold1.sha256, VERDICT-77.md in t191rev.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by PR #209, squash-merged as 460f6ed on master at 2026-09-30 15:43Z. AC1: the two error labels are module constants beside _NO_EXPERIMENT and _PRE_PROVENANCE. AC2: matrix_markdown reads the constants at both use sites and the tests import them (the rebase resolution initially let master's literal survive at the second site; the follow-up restored the constant). AC3: no output change; the constants hold exactly the old literals. Supersedes #36, closed with a pointer. Gates at dd66cb6: suite 1547 passed 3 skipped, check green, delivery 41, independent verdict APPROVED (VERDICT-77.md).
<!-- SECTION:FINAL_SUMMARY:END -->
