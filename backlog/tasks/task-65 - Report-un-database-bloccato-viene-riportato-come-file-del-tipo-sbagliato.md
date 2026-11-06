---
id: TASK-65
title: 'Report: un database bloccato viene riportato come file del tipo sbagliato'
status: Done
assignee: []
created_date: '2026-09-16 18:23'
updated_date: '2026-09-30 12:57'
labels:
  - audit-2026-09-16
  - run
  - confirmed
  - from-code-review
milestone: m-3
dependencies:
  - TASK-21
references:
  - 'src/pyteman/runner/report.py:64-72'
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Trovato dalla code review high di RUN-03 (TASK-21), riprodotto dal reviewer con un `BEGIN EXCLUSIVE` concorrente. Non corretto in RUN-03 perche non avevo una formulazione migliore abbastanza ovvia da giustificare un cambio di testo dopo il gate di review; tracciato invece di rinviato a nota.

**File:** `src/pyteman/runner/report.py:64-72` (il wrapper `except sqlite3.DatabaseError`).

**Difetto:** un database temporaneamente bloccato viene riportato come `'<path>' could not be read as a results database: database is locked`. La frase afferma che il file e del tipo sbagliato, quando invece e il file giusto nel momento sbagliato. Il dettaglio sqlite e incluso, quindi l'utente puo capirlo, ma deve contraddire la frase principale per farlo.

**Perche non e teorico:** lanciare il report mentre un `run_matrix` tiene il lock di scrittura e un modo realistico di arrivarci, ed e proprio l'uso che il report ha (lo lancia una persona a mano, spesso mentre qualcosa gira).

**Nota di perimetro:** `MatrixReportError` resta il tipo giusto; la questione e solo la formulazione. Una `sqlite3.OperationalError` per lock e sottoclasse di `DatabaseError`, quindi separarla significa discriminare sul messaggio, non sul tipo: verificare che la discriminazione scelta non diventi fragile rispetto alle versioni di sqlite.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Un database bloccato da un writer concorrente produce un messaggio che non afferma che il file sia del tipo sbagliato.
- [x] #2 Il dettaglio sqlite resta nel messaggio, perche e cio che distingue i casi.
- [x] #3 Test con un BEGIN EXCLUSIVE concorrente che blocca la formulazione scelta.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #94. Added lines already present on master per PR: #94 5/27=18%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.

Merged 2026-09-30 via #205 (a38b8eb). Evidence under /home/pantinor/pyteman-evidence/t191/: diff65.patch sha256 09ae123f, tree65-hold1.sha256, mutants-65.log, VERDICT-65.md in t191rev.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by PR #205, squash-merged as a38b8eb on master at 2026-09-30 12:56Z. AC1: a database locked by a concurrent writer produces MatrixReportError saying it could not be read because it is locked, not the wrong-file wording. AC2: the sqlite detail stays in the message, pinned after the battery's detail-dropped mutant survived the first cut. AC3: the test drives a real BEGIN EXCLUSIVE holder against a real run's database, connect timeout zeroed so the lock bites. The reviewer's informational note on defensive depth is recorded on the tracker. Supersedes #94, closed with a pointer. Gates at cdaf490: suite 1542 passed 2 skipped, check green, delivery 41, battery 3/3, independent verdict APPROVED (VERDICT-65.md).
<!-- SECTION:FINAL_SUMMARY:END -->
