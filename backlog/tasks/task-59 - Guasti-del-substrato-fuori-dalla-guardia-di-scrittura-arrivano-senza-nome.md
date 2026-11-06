---
id: TASK-59
title: Guasti del substrato fuori dalla guardia di scrittura arrivano senza nome
status: Done
assignee: []
created_date: '2026-09-16 18:03'
updated_date: '2026-09-30 12:34'
labels:
  - audit-2026-09-16
  - run
  - confirmed
  - spun-off
milestone: m-3
dependencies:
  - TASK-21
references:
  - src/pyteman/runner/matrix.py
  - src/pyteman/runner/report.py
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Scorporato da TASK-21 (RUN-03) il 2026-09-16, nel turno in cui il punto e stato misurato, a valle della review di altitudine.

**Cosa copre oggi MatrixStorageError.** Solo la scrittura della riga di una cella, cioe il blocco `try` introdotto da RUN-03 attorno a `_archive` + INSERT + DELETE + commit. Dentro quel perimetro il messaggio nomina la cella, il percorso del db e la directory degli artefatti.

**Evidenza misurata, non dedotta.** Ho sondato quattro condizioni reali con `run_matrix`:

- db di risultati in sola lettura con schema gia corrente: cade DENTRO la guardia, `MatrixStorageError` corretto. Nota: la review di altitudine sosteneva che questo caso fallisse prima, in `_ensure_schema`; e falso, perche `_ensure_schema` usa `CREATE TABLE IF NOT EXISTS` e non scrive nulla quando lo schema e gia aggiornato.
- db nuovo sotto una directory in sola lettura: `sqlite3.OperationalError: unable to open database file`, sollevata a matrix.py:716 dalla `sqlite3.connect`, FUORI dalla guardia.
- percorso dei risultati che e una directory: identico al precedente, matrix.py:716.
- directory padre inesistente: nessun errore, perche matrix.py:715 fa `os.makedirs(..., exist_ok=True)` prima di connettersi.

Inoltre `_attempt_dir` chiama `os.makedirs(d)` dentro il ciclo senza guardia: un disco pieno o un permesso revocato fra una cella e l'altra produce un `OSError` nudo senza id di cella, mentre la stessa condizione quindici righe dopo produce il messaggio curato.

**Il costo.** Le due condizioni che restano scoperte sono esattamente l'errore piu probabile di un operatore, cioe il percorso sbagliato. `unable to open database file` non nomina ne il percorso ne cosa si stava tentando. La stessa scelta e gia stata fatta diversamente in `report.py`, dove la `connect` E avvolta in un errore con nome proprio: la asimmetria fra i due moduli non e motivata.

**Perche non in RUN-03.** Le righe 715-727 sono codice RUN-01/RUN-02 gia approvato e fuori dalla regione assegnata a RUN-03 (753-798). Allargare la guardia cambierebbe il tipo di eccezione di percorsi di fallimento preesistenti, che e una modifica di comportamento su codice di altri.

**Da decidere qui.** Se allargare la guardia alla vita della connessione o aggiungerne una separata per l'apertura, dato che prima del ciclo non esiste una cella da nominare e il messaggio deve avere forma diversa; e se il fallimento di `os.makedirs` in `_attempt_dir` debba usare `MatrixArtifactError`, che esiste gia e il cui docstring indica proprio `artifact_root` come rimedio.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Un risultato db che non puo essere aperto produce un errore che nomina il percorso e cosa si stava tentando, non un sqlite3.OperationalError nudo
- [x] #2 Un fallimento di os.makedirs in _attempt_dir nomina la cella e la radice degli artefatti invece di un OSError nudo
- [x] #3 I messaggi prima del ciclo non fingono di conoscere una cella, dato che nessuna cella e ancora stata eseguita
- [x] #4 Un test copre almeno il percorso che e una directory e il disco non scrivibile prima della prima cella
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #63. Added lines already present on master per PR: #63 12/91=13%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.

Merged 2026-09-30 via #204 (4093667). Evidence under /home/pantinor/pyteman-evidence/t191/: diff59.patch sha256 72506aac, tree59-hold1.sha256, mutants-59.log, VERDICT-59.md in t191rev.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by PR #204, squash-merged as 4093667 on master at 2026-09-30 12:33Z. AC1: a results db that cannot be opened raises MatrixStorageError naming the path and the attempt, not a naked OperationalError; the class docstring honestly describes both its shapes. AC2: an os.makedirs failure in the attempt-directory path records the cell's id and the artifact root. AC3: pre-loop messages name no cell. AC4: the tests cover the path-is-a-directory shape, a monkeypatched connect failure, and the makedirs failure naming cell and root; the battery kills the guard-dropped and names-lost mutants byte-exact. The reviewer's remaining-faults answer is filed on TASK-198; the lock layer pre-empting the connect guard for directory-permission shapes is acceptable naming through a different door. Supersedes #63, closed with a pointer. Gates at fa6c5a7: suite 1541 passed 2 skipped, check green, delivery 41, independent verdict APPROVED (VERDICT-59.md). One CI flake (TASK-201's lock, fourth occurrence) rerun green.
<!-- SECTION:FINAL_SUMMARY:END -->
