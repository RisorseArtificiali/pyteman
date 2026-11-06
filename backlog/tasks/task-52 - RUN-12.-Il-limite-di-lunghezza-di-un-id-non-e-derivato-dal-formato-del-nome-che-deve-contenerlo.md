---
id: TASK-52
title: >-
  RUN-12. Il limite di lunghezza di un id non e derivato dal formato del nome
  che deve contenerlo
status: Done
assignee: []
created_date: '2026-09-16 16:22'
updated_date: '2026-09-30 12:04'
labels:
  - runner
  - refactor
  - review-followup
  - audit-2026-09-16
milestone: m-3
dependencies: []
references:
  - 'src/pyteman/runner/matrix.py:32'
  - 'src/pyteman/runner/matrix.py:166'
  - 'src/pyteman/runner/matrix.py:292'
  - 'TASK-19 (RUN-01): origine'
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Emersa dalla review Altitude sullo stato finale di RUN-01 (TASK-19), 2026-09-16. Non e un difetto corrente: il valore di oggi e corretto. E un accoppiamento non dichiarato fra due punti distanti, che diventa falso in silenzio alla prima modifica del formato.

`_MAX_ID_BYTES = 200` (src/pyteman/runner/matrix.py:32) e corretto soltanto per il suffisso attuale del nome del tentativo, `.<12>.<12>`, cioe 26 byte contro il limite di 255 per componente di ext4, APFS e NTFS. La derivazione vive in un commento; il formato vive in una f-string dentro `_attempt_dir` (~riga 166), 130 righe piu in basso. Nulla collega i due punti.

Costo concreto: allargare il prefisso del fingerprint, o aggiungere un terzo token al nome del tentativo, lascia il validatore ad accettare id che ora non entrano piu, con un commento diventato falso senza che nulla lo segnali. Il fallimento si sposta allora su `os.makedirs` DENTRO il ciclo di esecuzione, che e esattamente il modo di fallire che il pre-pass esiste per impedire: il docstring di `_check_cell_ids` (~righe 292-297) promette che nessuna cella giri finche la matrice non e nota eseguibile, e a quel punto le celle precedenti hanno gia girato e committato. La promessa si rompe senza che un test la veda cadere.

Forma proposta dalla review: costruire il nome del tentativo in una sola funzione e derivare il budget da quella, per esempio `_MAX_ID_BYTES = 255 - len(_attempt_suffix(campione))`, oppure far chiamare a `_check_cell_ids` la stessa funzione di costruzione del nome su un id di prova e misurare il risultato.

Non incluso in TASK-19: il perimetro di RUN-01 era la validazione dell'identita e la correzione del difetto di archiviazione, e lo stato era congelato e gia verificato dall'orchestrator quando la review e arrivata.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Il budget in byte per un id di cella e derivato dalla funzione che costruisce il nome del tentativo, non scritto a mano: allargare il prefisso del fingerprint o aggiungere un terzo token sposta il limite senza interventi manuali
- [x] #2 Un test dimostra l'accoppiamento: cambiato il formato del nome del tentativo, un id che prima passava e ora non entrerebbe piu nel limite del filesystem viene rifiutato dal pre-pass e non da os.makedirs
- [x] #3 Il rifiuto continua ad avvenire prima che qualunque cella giri, cioe la promessa di _check_cell_ids resta intatta
- [x] #4 La suite resta verde e la batteria di mutazione continua a uccidere M18 (rimozione del bound di lunghezza)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #62. Added lines already present on master per PR: #62 3/46=6%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.

Merged 2026-09-30 via #203 (7816627). Evidence under /home/pantinor/pyteman-evidence/t191/: diff52.patch sha256 a8f5764a, tree52-hold2.sha256, mutants-52.log, VERDICT-52*.md in t191rev.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by PR #203, squash-merged as 7816627 on master at 2026-09-30 12:04Z. AC1: the byte budget is derived from the format that spends it (_MAX_ID_BYTES = _COMPONENT_LIMIT - _ATTEMPT_SUFFIX_LEN, the suffix from the two slice constants, and _attempt_dir plus the token mint read the constants instead of their own literal 12s), so widening either slice moves the limit with no manual edit; adding a third field is held against a built name (the name's length minus the id's must equal the formula), the reviewer's mutant proving the first cut unguarded. AC2: the coupling test widens the fingerprint slice by eight and proves the borderline id that fit before is refused by the pre-pass, not by os.makedirs. AC3: the refusal stays ahead of every write (the emptiness claims in the file's tests). AC4: the suite is green (1538 passed, 2 skipped) and the battery kills the hand-written-200 mutant plus three coupling shapes (both literal 12s; the third field), restores byte-exact; the test-of-test deletion mutant is retired in the script with its reason. The derivation also widens the budget from 200 to 229 bytes, the formula's natural consequence, safe at the component boundary and declared in the PR body. Supersedes #62, closed with a pointer. Gates at 25c118b: suite, check, delivery 41, independent verdicts APPROVED at 90b5665 and reissued at 25c118b (VERDICT-52.md, VERDICT-52b.md).
<!-- SECTION:FINAL_SUMMARY:END -->
