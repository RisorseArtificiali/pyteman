---
id: TASK-23
title: RUN-05. Escapare i dati nel report Markdown
status: Done
assignee:
  - '@opus-5-run05'
created_date: '2026-09-16 12:20'
updated_date: '2026-09-16 20:28'
labels:
  - audit-2026-09-16
  - opus-5
  - run
  - confirmed
milestone: m-3
dependencies:
  - TASK-21
references:
  - 'src/pyteman/runner/report.py:9-19'
documentation:
  - doc-1
  - doc-2
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P2, CONFIRMED, aperto.

**File:** `src/pyteman/runner/report.py:9-19`.

**Evidenza:** cell id `broken|cell` e signature `a|b\nnext` producono colonne/righe Markdown aggiuntive. I valori sono interpolati senza escaping.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 snapshot del report con pipe, backslash, backtick, newline, HTML, Unicode e errori; ogni risultato rimane nella propria riga e colonna.
- [x] #2 Testare un renderer reale se il contratto include HTML.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Proposta iniziale da verificare sul codice corrente, non una correzione già applicata.

renderer di celle per pipe, newline e markup potenzialmente interpretato; conservare un report leggibile e linkabili gli artefatti senza confondere contenuto ed HTML. Non alterare i valori raw nel database.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: RUN-03 per risultati validati.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.

2026-09-16, RUN-05, requisito derivato dal piano e registrato prima di altre modifiche, su correzione di scope del parent. Non e un cambio di AC deciso qui: e la parte del campo Implementation Plan che la prima lettura di questo task aveva sottopesato.

Il piano dice 'renderer di celle per pipe, newline e markup potenzialmente interpretato' e 'senza confondere contenuto ed HTML'. Gli AC parlano solo di riga e colonna, quindi leggendo i soli AC la promessa risulta strutturale e l'escape gia presente li soddisfa. Leggendo il piano no: le celle contengono dati di risultato e devono arrivare come testo letterale, non come markup attivo.

Contratto vincolante per questa tranche, quindi, piu forte di quello che RUN-05 aveva scritto prima: ogni cella rende come testo letterale. In particolare '*x*', '_x_', i backtick, '<b>x</b>', '&lt;x&gt;' e i link e le immagini in sintassi Markdown restano testo visibile e non diventano elementi attivi. Resta la distinzione fra un backslash-n letterale e un newline reale. I valori nel database non vengono alterati: l'escape e solo di rendering.

Conseguenze sul perimetro. La parte corrispondente di TASK-67 rientra in TASK-23 e non va rinviata per il solo fatto che cambia il sorgente del report; TASK-67 va integrata qui o collegata come risolta da questo task. TASK-68 (collasso dei soli spazi) e TASK-69 (lettori che usano splitlines) restano proposte motivate e fuori perimetro: l'iniettivita completa su spazi e Unicode oltre il contratto esplicito non e richiesta. I test devono usare un renderer reale; pandoc opzionale va bene purche venga davvero eseguito, ma i test core deterministici non possono essere tutti skip.

Stato: nessuna approvazione. I gate vanno rifatti sul diff aggiornato, non sulla versione precedente.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Chiuso su APPROVED del parent (pyteman-89), hash verificati corrispondenti prima e dopo, diff-check pulito.

**Cosa promette adesso il report.** Ogni colonna passa da `_text`, comprese quelle che il runner scrive da se, perche `_read` rende anche results table che questo runner non ha scritto. La promessa ha due meta separate. Strutturale: qualunque carattere contenga un valore memorizzato, resta nella propria riga e nella propria cella, nel file e attraverso un renderer reale. Letterale: i suoi caratteri si vedono come se stessi, quindi `*x*`, `` `x` ``, `[a](u)` e `<script>` arrivano come i caratteri che qualcuno ha memorizzato e non come enfasi, codice, un link o un elemento script. Il database non viene toccato: e un escape di rendering.

**Implementazione.** `_ESCAPES` costruita una volta e applicata con `str.translate`, che percorre il valore una sola volta: backslash davanti a ogni carattere di `string.punctuation`, e le due terminazioni di riga rese come control picture Unicode U+240A e U+240D. `string.punctuation` e carattere per carattere l'insieme di punteggiatura ASCII che CommonMark nomina, verificato elemento per elemento (32 contro 32), quindi la regola copre esattamente il dominio su cui e definita e non richiede giudizio per singolo carattere. Le control picture e non `\n`, perche con l'escape letterale il rendering e quasi l'identita e rendere il newline reale come backslash-n lo stamperebbe identico ai due caratteri memorizzati, perdendo la distinzione proprio dove il lettore la cerca.

**AC #1, soddisfatto.** tests/test_report_escaping.py fissa lo snapshot su un campione ostile di 30 valori con pipe, backslash, backtick, newline, HTML, Unicode ed errori, e verifica che ogni risultato resti nella propria riga e colonna. Misura prima e dopo con pandoc (`-f gfm -t html`): il solo escape strutturale lasciava 10 valori su 30 resi come elementi attivi, l'escape attuale ne lascia 0.

Nota di metodo registrata nel test: GFM normalizza ogni riga del corpo alla larghezza dell'intestazione, scartando in silenzio le celle in eccesso e riempiendo quelle mancanti. Verificato con pandoc, una riga da 5 celle sotto un'intestazione da 4 colonne rende esattamente 4 `<td>`. Una rottura di colonna e quindi distruttiva in modo silenzioso e mai visibilmente larga, e un'asserzione sull'insieme delle larghezze non puo fallire. Il test strutturale e stato riorientato su cio che una rottura perturba davvero, cioe il contenuto delle colonne vicine: la mutazione sulla pipe passa da `4 passed` a `3 failed, 1 passed`, e la parametrizzazione superstite e esattamente la colonna signature che la docstring prevede.

**AC #2, soddisfatto.** Due renderer reali, entrambi realmente eseguiti in questo ambiente: pandoc 3.7.0.2 (`-f gfm -t html`) e python-markdown 3.10.3. Nessun elemento attivo su entrambi. Su python-markdown, 0 elementi attivi e 30/30 valori distinti; 8 valori su 30 arrivano con un backslash visibile dove quel renderer non riconosce l'escape, per cui il contratto dichiara la meta letterale come promessa CommonMark/GFM e la meta di sicurezza come verificata su entrambi. Il nucleo deterministico (8 test) non dipende da alcun renderer esterno, quindi i test core non sono tutti skip.

**Verifica indipendente del parent.** Probe con SQLite e pandoc GFM: `*x*`, `_x_`, backtick, `<b>`, entita, link e immagini, script, commento, pipe, Unicode, newline e backslash-n conservano il testo atteso, nessun elemento attivo nelle celle, DB byte invariato.

**Otto correzioni applicate su due giri di review high, ciascuna con la mutazione che la uccide.**
1. Uguaglianza sull'insieme completo di `string.punctuation`: la batteria di restringimento con entrambi i renderer nascosti passa da `20 passed, 8 skipped` a `1 failed` per `&;`, `:/.`, backtick, `*_` e `\`.
2. Cifre e caratteri non di punteggiatura fissati esplicitamente. L'uguaglianza precedente e un controllo per sottoinsieme e non vede un escape che cresce: aggiungendo `string.digits` alla tabella, uno `<script>alert(1)</script>` memorizzato raggiunge il lettore come `alert(\1)`, perche CommonMark non da significato di escape a un backslash davanti a una cifra. Quella mutazione passava verde con entrambi i renderer nascosti (`8 passed, 8 skipped`) ed era colta solo da pandoc; ora `1 failed, 7 passed, 8 skipped`.
3. Test strutturale riorientato sullo spostamento delle colonne benigne (vedi AC #1).
4. `_Table` dotato di `handle_comment`, `handle_decl` e `handle_pi`: sono terminali e non arrivano mai a `handle_data`, quindi una cella finita li si rileggeva come `''`, indistinguibile da un valore reso come se stesso.
5. `unknown_decl` coperto con gli altri tre: pandoc passa `<![CDATA[secret]]>` attraverso una cella GFM dentro il `<td>` senza alterarlo, e il `_Table` reale lo inghiottiva come `''`. Ora la riga si legge `['«markup»', 'plain', '«markup»', '«markup»']`.
6. Rimosso il filtro di larghezza in `_data_rows`: codice morto misurato (0 righe scartate su entrambi i renderer e tutte e quattro le parametrizzazioni), il cui unico effetto raggiungibile era nascondere una riga malformata, e perdere in silenzio una riga e cio che uno strumento di misura non deve fare.
7. `encoding="utf-8"` nella scrittura del report (vedi sotto).
8. README e docstring allineati al fatto che la meta letterale e specifica alla famiglia del renderer; corretta anche una condizione dichiarata in docstring, da "misurato con pandoc assente" a "con nessuno dei due renderer installato", perche il test in questione si apre su `importorskip("markdown")` e non porta il marker `@pandoc`. La mutazione sul backtick e colta dal solo test sul secondo renderer (`2 failed, 7 passed, 7 skipped`).

**Modifica fuori dal perimetro inizialmente dichiarato, autorizzata dal parent.** `matrix_markdown` ora apre il file con `encoding="utf-8"` invece che con la codifica di locale. La riga `open` precede questo task, ma le control picture sono gli unici caratteri non ASCII che il report fabbrica e li fabbrica da un fine riga memorizzato, che e ASCII puro: e l'escape introdotto qui ad aver portato un crash latente a portata di dati ordinari. Un results db contenente nient'altro che un newline produceva un report che sotto un locale non UTF-8 non si scriveva affatto. PEP 538 forza `C`, quindi serve un locale esplicitamente non UTF-8 per innescarlo, e Python 3.14 non ha ancora reso predefinita la modalita UTF-8 (PEP 686 punta alla 3.15). Rosso-verde reale: tolto il kwarg il nuovo test cattura `UnicodeEncodeError: 'latin-1' codec can't encode character '␊' in position 100`, ripristinato torna verde. Il parent ha accettato la modifica come necessaria al rendering introdotto e ne ha chiesto la permanenza.

**Limiti dichiarati, misurati e non assunti**, scritti sia nel docstring di `_text` sia nella sezione Runner del README. Due valori che differiscono solo per spazi arrivano uguali, perche markdown collassa gli spazi dentro una cella prima che qualunque escape possa parlare: TASK-68. Una control picture memorizzata rende come il fine riga che rappresenta, collisione tenuta consapevolmente perche rimuoverla la sposta soltanto su un backslash seguito da un newline reale. La promessa riguarda i caratteri e non i glifi: un controllo bidi come U+202E attraversa l'escape intatto e riordina cio che il lettore vede senza alterare un carattere di cio che c'e, quindi TASK-76 lo tiene. TASK-68 e TASK-69 restano proposte motivate, fuori perimetro per decisione del parent.

**Test.** Comando `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /tmp/pyteman-audit-env-OOeElF/bin/python -m pytest -q`. Perimetro 29 passed, 0 skipped: tests/test_report.py 11, tests/test_report_escaping.py 16, tests/test_matrix.py 2. Dei 16 in test_report_escaping.py, 8 sono condizionati (4 funzioni marcate `@pandoc` che diventano 7 item dopo parametrizzazione, 1 su `importorskip("markdown")`) e tutti e 8 hanno girato realmente qui. Suite completa 361 passed; erano 358 a inizio tranche e il delta di +3 e di un agente concorrente su tests/test_targets.py (17 a 20), non di questo task.

**SHA256 dello stato approvato.**
- `bd0b0770fbd348775668ffcdc8283d0366989267d86770d6df2166f2b3d13e6e  src/pyteman/runner/report.py`
- `6e8c41690ce77594ab6a166beb42cc6d9c17dd29ba961209a558adaf0586110c  tests/test_report_escaping.py`
- `6c30d1016edf074266f2b6236eee9d3fbfd2052c1460d2c0292bcb0215cb4e35  tests/test_report.py`
- `16f191d8ed7523c7807ae13de236ea8290fd48073176da8c5933abcf1d3c1599  tests/test_matrix.py`
- `9e58940ae7f094faee1f4e0a0738cc32868a929680ac1db722a79bab85a6e1fe  README.md` (file condiviso: il digest copre anche il lavoro di un agente concorrente, la parte di questo task sono le sole righe 133-161 nella sezione Runner)

**Ambiente.** Python 3.14.7, pytest 9.0.3, pandoc 3.7.0.2, python-markdown 3.10.3.

La parte corrispondente di TASK-67 e stata integrata qui e quel task viene chiuso insieme a questo. Nessun commit e nessun push: il checkout e condiviso.
<!-- SECTION:FINAL_SUMMARY:END -->
