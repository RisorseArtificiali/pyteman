---
id: TASK-67
title: 'Report Markdown: valori distinti collassano nel rendering (markup inline)'
status: Done
assignee: []
created_date: '2026-09-16 18:42'
updated_date: '2026-09-16 20:28'
labels:
  - audit-2026-09-16
  - run-05-residue
  - report
dependencies: []
references:
  - 'src/pyteman/runner/report.py:85-97'
  - tests/test_report_escaping.py
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Scoperto durante RUN-05 (TASK-23), misurato, non corretto.

`_text` garantisce l'integrita strutturale: ogni valore resta nella propria riga e nella propria colonna, nel file e attraverso un renderer reale. Non garantisce l'iniettivita del rendering: il renderer interpreta ogni cella come markdown inline, quindi valori distinti nel database arrivano identici al lettore.

Misurato su 87 casi ostili con pandoc (-f gfm -t html) e python-markdown 3.10.3, entrambi i renderer concordi: `*x*` e `_x_` rendono entrambi em-x; il letterale backslash-n e un newline reale rendono entrambi lo stesso testo.

E' la stessa classe di misattribuzione per cui esiste la colonna experiment: due risultati diversi che il lettore non puo distinguere.

Candidato misurato, non applicato: backslash davanti a ogni carattere di punteggiatura ASCII (CommonMark da al backslash il carattere letterale solo prima della punteggiatura, quindi e l'unica regola indipendente dal renderer), piu il backslash stesso raddoppiato perche sopravviva al rendering. Su quel set porta a zero i collassi da markup su entrambi i renderer. Costo: cambia l'aspetto del sorgente di ogni report, quindi e una decisione di scope, non una correzione interna.

Non risolve i collassi da spazi: vedi TASK-68.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Decidere se il report promette l'iniettivita del rendering o solo l'integrita strutturale; la scelta e scritta nel docstring di _text e nella sezione Runner del README
- [x] #2 Se si adotta l'escape esteso: test con due renderer indipendenti che nessun valore distinto collassi per markup
- [x] #3 tests/test_report_escaping.py aggiornato: il test che oggi fissa il collasso come atteso deve cambiare insieme al contratto
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Risolto dentro TASK-23 (RUN-05), non separatamente: il piano di TASK-23 chiedeva gia 'markup potenzialmente interpretato' e 'senza confondere contenuto ed HTML', quindi l'escape esteso rientrava in quella tranche.

Applicato in src/pyteman/runner/report.py: `_text` ora fa `str.translate` su una tabella costruita una volta, con backslash davanti a ogni carattere di punteggiatura ASCII e le due terminazioni di riga rese come control picture Unicode (U+240A / U+240D). Le control picture, e non backslash-n, perche con l'escape letterale il rendering e quasi l'identita: rendere il newline reale come backslash-n lo farebbe stampare identico ai due caratteri memorizzati, perdendo la distinzione proprio dove il lettore la cerca.

Misura prima e dopo (26 casi, pandoc -f gfm -t html): escape strutturale precedente = 10 valori resi come elementi attivi; escape attuale = 0.

AC #1: soddisfatto. La scelta e scritta nel docstring di `_text` e nella sezione Runner del README.
AC #2: soddisfatto come formulato ('nessun valore distinto collassi per markup'), con una precisazione misurata e non assunta. Su python-markdown 3.10.3 (non CommonMark): 0 elementi attivi e 30/30 valori distinti, quindi la proprieta richiesta dall'AC vale su entrambi i renderer. L'uguaglianza esatta del testo invece no: 8 valori su 30 arrivano con un backslash visibile dove quel renderer non riconosce l'escape. Per questo il contratto dichiara la meta letterale come promessa CommonMark/GFM, e la meta di sicurezza come verificata su entrambi. Test: tests/test_report_escaping.py::test_a_second_renderer_agrees_that_no_value_becomes_markup.
AC #3: soddisfatto. I due test che fissavano il collasso come atteso sono stati sostituiti; il contratto residuo (spazi, collisione control picture) resta fissato in test_what_the_escape_still_does_not_promise.

Stato lasciato a To Do di proposito: la chiusura segue l'approvazione di TASK-23, secondo la sequenza concordata.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Risolto dentro TASK-23 (RUN-05) e chiuso con esso sullo stesso APPROVED del parent (pyteman-89). Non e stata una tranche separata: il campo Implementation Plan di TASK-23 chiedeva gia 'markup potenzialmente interpretato' e 'senza confondere contenuto ed HTML', quindi l'escape esteso rientrava in quel perimetro e rinviarlo sarebbe stato un rinvio motivato solo dal fatto che cambia il sorgente del report.

**La decisione presa.** Il report promette entrambe le cose, con una divisione netta e dichiarata. L'integrita strutturale vale su qualunque renderer: ogni valore resta nella propria riga e nella propria cella. L'iniettivita del rendering e promessa come contratto CommonMark/GFM, perche e li che il backslash davanti alla punteggiatura ASCII ha significato definito; fuori da quella famiglia resta verificata la meta di sicurezza, cioe che nessun valore diventi elemento attivo. La scelta e scritta nel docstring di `_text` e nella sezione Runner del README, come chiedeva AC #1.

**Implementazione.** `_text` fa `str.translate` su una tabella costruita una volta: backslash davanti a ogni carattere di punteggiatura ASCII e le due terminazioni di riga rese come control picture Unicode U+240A e U+240D. Le control picture e non backslash-n, perche con l'escape letterale il rendering e quasi l'identita e rendere il newline reale come backslash-n lo stamperebbe identico ai due caratteri memorizzati, perdendo proprio la distinzione che questo task esisteva per recuperare. Il backslash stesso rientra nella punteggiatura ASCII, quindi viene raddoppiato e l'escape resta iniettivo come codifica.

**Misura prima e dopo**, pandoc `-f gfm -t html`: l'escape strutturale precedente lasciava 10 valori su 30 resi come elementi attivi, l'escape attuale ne lascia 0.

**AC #1, soddisfatto.** La scelta e scritta nel docstring di `_text` e nella sezione Runner del README, insieme ai tre limiti che restano.

**AC #2, soddisfatto** come formulato ('nessun valore distinto collassi per markup'), con una precisazione misurata e non assunta. Su python-markdown 3.10.3, che non e CommonMark: 0 elementi attivi e 30/30 valori distinti, quindi la proprieta richiesta dall'AC vale su entrambi i renderer indipendenti. L'uguaglianza esatta del testo invece no, perche 8 valori su 30 arrivano con un backslash visibile dove quel renderer non riconosce l'escape; per questo il contratto separa la meta letterale (promessa CommonMark/GFM) dalla meta di sicurezza (verificata su entrambi). Test: tests/test_report_escaping.py::test_a_second_renderer_agrees_that_no_value_becomes_markup, che si apre su `importorskip("markdown")` e non porta il marker `@pandoc`, quindi misura davvero un renderer diverso e non una seconda passata dello stesso.

**AC #3, soddisfatto.** I due test che fissavano il collasso come atteso sono stati sostituiti insieme al contratto. Il contratto residuo resta fissato in test_what_the_escape_still_does_not_promise: collasso dei soli spazi (TASK-68) e collisione fra una control picture memorizzata e il fine riga che rappresenta, tenuta consapevolmente perche rimuoverla la sposta soltanto su un backslash seguito da un newline reale. Il terzo limite, i controlli bidi come U+202E che attraversano l'escape intatto e riordinano cio che il lettore vede senza alterare un carattere di cio che c'e, resta a TASK-76 perche chiuderlo e un cambio di comportamento e non di formulazione.

**Verifica indipendente del parent** sullo stato finale: probe con SQLite e pandoc GFM, dove `*x*`, `_x_`, backtick, `<b>`, entita, link e immagini, script, commento, pipe, Unicode, newline e backslash-n conservano il testo atteso, nessun elemento attivo nelle celle e DB byte invariato.

**Test e hash** sono quelli registrati nel finalSummary di TASK-23: perimetro 29 passed con 0 skip, suite completa 361 passed, SHA256 dei cinque file toccati. Il codice e congelato su quello stato e questo task non lo modifica.
<!-- SECTION:FINAL_SUMMARY:END -->
