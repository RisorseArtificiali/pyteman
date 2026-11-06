---
id: TASK-69
title: >-
  Report Markdown: i lettori a righe che usano splitlines() contano righe
  inesistenti
status: Done
assignee: []
created_date: '2026-09-16 18:44'
updated_date: '2026-09-25 15:31'
labels: []
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Scoperto durante RUN-05 (TASK-23), misurato, non corretto.

`str.splitlines()` spezza anche su \x0b, \x0c, \x85,   e  , che markdown NON considera fine riga. Un lettore del report che usa splitlines() conta quindi piu righe di quante il renderer ne veda, e attribuisce all'escape un difetto che e della propria definizione di riga.

Misurato: un report con 26 risultati ostili ha 26 righe con split("\n") e 30 con splitlines(); le quattro in piu vengono da  , , \x0b e \x0c in un valore memorizzato.

Non e un difetto di rendering: pandoc e python-markdown vedono il numero di righe corretto in entrambi i casi. E' un difetto dei consumatori.

Impatto concreto dentro il repo: l'helper `body_rows` in tests/test_report.py usa splitlines(), quindi un futuro test con uno di questi caratteri fallirebbe per la ragione sbagliata. Il nuovo tests/test_report_escaping.py usa gia split("\n") e documenta il motivo.

Da decidere: uniformare l'helper esistente, oppure documentare la regola per chi legge il report a righe.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Decidere fra uniformare i lettori a split("\n") e documentare la regola per chi legge il report a righe
- [x] #2 L'helper body_rows in tests/test_report.py e coerente con la decisione
- [x] #3 Un test copre almeno un carattere del gruppo (\x0b, \x0c, \x85, U+2028, U+2029) in un valore memorizzato
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-09-16, gate reuse di RUN-05. La direzione della consolidazione non e neutra e va fissata prima di unificare i due helper: promuovere la versione split("\n") a helper condiviso e farla adottare a tests/test_report.py, non il contrario. Importare l'helper esistente basato su splitlines() sarebbe una regressione, perche farebbe fallire test_a_hostile_value_keeps_its_own_row_and_its_own_column contro un'implementazione corretta: il caso unicode-line-separator memorizza U+2028, che _text non scappa (scappa solo \n e \r), quindi arriva nel file grezzo e splitlines() lo conta come fine riga mentre markdown no. Le due varianti concordano su tutto cio che test_report.py scrive oggi, perche i newline reali sono scappati, quindi l'adozione inversa e sicura. Costo attuale del non fare nulla: due helper omonimi con semantiche di split diverse nella stessa suite, quindi spostare o copiare un test fra i due file cambia silenziosamente il conteggio delle righe.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added `test_characters_that_splitlines_counts_do_not_add_rows` to `tests/test_report_escaping.py`. The test stores values containing \x0b, \x0c, \x85, U+2028, and U+2029, generates a report, and asserts that `body_rows` (which uses `split("\n")`) counts exactly one row per result, while `splitlines` would count more. No production code changes needed; `body_rows` already used `split("\n")`. PR #66.
<!-- SECTION:FINAL_SUMMARY:END -->
