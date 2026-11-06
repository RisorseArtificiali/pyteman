---
id: TASK-92
title: >-
  SQL-05. Nessuna funzione possiede la cattura, quindi NO_OUTPUT resta il
  risultato normale del chiamante ingenuo
status: Done
assignee: []
created_date: '2026-09-16 21:21'
updated_date: '2026-09-30 18:21'
labels:
  - sql
  - follow-up-task-25
  - api
dependencies: []
references:
  - src/pyteman/sqlitekit/integrity.py
  - docs/integrity.md
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Follow-up individuato durante TASK-25 (SQL-02).

`classify_integrity` legge una cattura che qualcun altro ha fatto. TASK-25 ha documentato e misurato il motivo per cui questo e delicato: i guasti peggiori non arrivano come righe. Su SQLite 3.51.2 e 3.53.4, `file is not a database`, `malformed database schema` e `database disk image is malformed` fanno sollevare un'eccezione alla PRAGMA; attraverso la shell finiscono su stderr con exit 1 e stdout vuoto.

Ne segue che il chiamante ingenuo, quello che redirige soltanto stdout, ottiene la stringa vuota proprio dai database distrutti. `classify_integrity` risponde correttamente NO_OUTPUT e la diagnosi lo manda a guardare stderr e l'exit code, ma il modulo non offre nulla che faccia quella cattura al posto suo. Ogni consumatore deve riscoprire da solo che servono due canali.

Un sibling che possiede la cattura, cioe che esegue il controllo, raccoglie sia le righe sia il messaggio dell'eccezione e passa il risultato a `classify_integrity`, toglierebbe NO_OUTPUT dal percorso normale lasciandolo a significare quello che deve: la cattura non e stata fatta.

Fuori dal perimetro di TASK-25 che riguarda la lettura del testo e non l'esecuzione del controllo. Richiede inoltre di decidere dove vive l'apertura di un database in sqlitekit.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Esiste una funzione che esegue il controllo e cattura entrambi i canali e restituisce lo stesso verdetto di classify_integrity
- [x] #2 Un file che non e un database produce NOTADB tramite quella funzione invece di NO_OUTPUT
- [x] #3 classify_integrity resta pubblica e invariata per chi ha gia una cattura propria
- [x] #4 La documentazione indica quale delle due e il punto di ingresso consigliato
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #69. Added lines already present on master per PR: #69 0/125=0% absentfiles=1. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge.

Merged 2026-09-30 via #213 (b993a3d). Evidence under /home/pantinor/pyteman-evidence/t191/: diff92.patch sha256 20117e8a, tree92-hold1.sha256, mutants-92.log, VERDICT-92.md in t191rev.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by PR #213, squash-merged as b993a3d on master at 2026-09-30 18:20Z. AC1: check_integrity(path) exists and owns the capture. AC2: a file that is not a database produces NOTADB through this function where a stdout-only caller saw NO_OUTPUT. AC3: classify_integrity stays public and unchanged. AC4: docs/integrity.md's Running-the-check section names check_integrity the recommended entry point. The reviewer probed capture totality and close-on-every-path. Supersedes #69, closed with a pointer. Gates at 2f5cdc7: suite 1562 passed 3 skipped, check green, delivery 41, battery 3/3, independent verdict APPROVED (VERDICT-92.md).
<!-- SECTION:FINAL_SUMMARY:END -->
