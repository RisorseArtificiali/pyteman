---
id: TASK-46
title: >-
  DOC-02. Documentare la policy schema chiuso e i campi ora obbligatori delle
  regole
status: Done
assignee:
  - '@tree-28'
created_date: '2026-09-16 14:02'
updated_date: '2026-09-25 17:09'
labels:
  - audit-2026-09-16
  - doc
  - cfg
  - follow-up
dependencies:
  - TASK-7
references:
  - src/pyteman/rules.py
  - docs/rules.md
  - tests/test_docs_rules.py
  - README.md
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Aperto da TASK-7 (CFG-01) il 2026-09-16. RIDIMENSIONATO il 2026-09-16 dallo stesso implementer, dopo che l'orchestrator ha revocato in parte il divieto di toccare la documentazione e ha chiesto di integrare in TASK-7 la documentazione necessaria invece di rinviarla.

**Cosa ha gia' consegnato TASK-7.** Il nuovo `docs/rules.md` e' il riferimento completo del linguaggio delle regole: policy di schema chiuso con la tabella dei refusi silenziosi, tabella dei campi di rule, le condizioni con i dieci nomi disponibili, la tabella delle action campo per campo con i limiti reali, il fire gating con l'asimmetria di conteggio, e la forma dei messaggi di errore. Il README lo linka dalla sezione "Ruleset example" (unica porzione autorizzata) con un paragrafo di quattro righe sulla policy di schema chiuso. `tests/test_docs_rules.py` carica ogni blocco YAML del riferimento con `load_rules`, piu' una guardia che fallisce se il regex smette di trovare blocchi, cosi' la suite non diventa verde a vuoto.

I punti 1, 2, 4, 5 e 6 dell'elenco originale sono coperti li'.

**Il punto 3 originale e' ora FALSO e non va scritto da nessuna parte.** Diceva che una regola `event: entry` non puo' nominare `result` ne' `exc`, e che il controllo statico e' conservativo al punto da rifiutare `False and result`. Quel controllo (`_free_names` / `_reject_exit_only`) e' stato RIMOSSO in TASK-7 su direttiva dell'orchestrator, perche' `symtable` non vede il nome libero dentro uno scope annidato (`(lambda: result)()` produce una tabella top vuota) ne' la lettura che precede un walrus (`result or (result := 1)` risulta assegnato). Il controllo rifiutava quindi la forma piatta e lasciava passare due NameError reali: una promessa parziale di validazione che crea falsa sicurezza mentre rompe condizioni funzionanti. `docs/rules.md` documenta il vincolo entry/exit come contratto verificato al firing, non al load, e dice esplicitamente perche' il controllo e' stato tolto.

**Cosa resta davvero aperto qui.** Solo l'esempio YAML dentro il README stesso non e' caricato da nessun test. Scelta deliberata in TASK-7: il README e' in carico concorrente a un altro agente in questa tranche, e accoppiarci un test avrebbe fatto fallire la suite su modifiche altrui fuori dal perimetro. Il giorno in cui il README non e' piu' conteso, il test in `tests/test_docs_rules.py` si estende al file con tre righe.

Non copre la quotatura dei valori PRAGMA: e' il criterio di accettazione #2 di TASK-9 (CFG-03) e va scritta li' per non duplicare gli esempi. `docs/rules.md` ne riporta solo la conseguenza di caricamento (un bare `OFF` viene rifiutato perche' YAML 1.1 lo legge come booleano), non la matrice degli effetti su SQLite.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Gli esempi YAML nel README sono caricati da un test, come gia' avviene per docs/rules.md, una volta che il README non e' piu' in carico concorrente a un altro agente.
- [x] #2 La deriva di docs/rules.md rispetto a rules.py e' sorvegliata per le parti meccanizzabili (limiti numerici e classi di eccezione, gia' coperte da test) e riletta a mano per le parti in prosa, che nessun test puo' controllare: ordine di valutazione del gate, timing del NameError, visibilita' dei nomi negli scope annidati.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Delta dal gate pass 1 di TASK-7 (2026-09-16). Due dettagli della descrizione sopra sono stati superati nello stesso giorno e vanno letti cosi'.

1. La guardia di `tests/test_docs_rules.py` non e' piu' "fallisce se il regex smette di trovare blocchi": e' un confronto di UGUAGLIANZA fra il numero di blocchi estratti e il numero di fence ```yaml presenti nel file. Il floor precedente lasciava passare il caso peggiore, cioe' un blocco che il regex non intercetta e che quindi sparisce dalla parametrizzazione senza che il run diventi rosso. Gli id dei casi derivano ora dal primo `id:` di ogni blocco invece che dall'indice.

2. I limiti numerici stampati nella tabella delle action sono ora PINNATI da `test_documented_bounds_match_the_constants`, che asserisce la presenza di `str(_MAX_SLEEP_MS)` e `repr(threading.TIMEOUT_MAX)` nel testo del documento. Il criterio #2 e' stato riscritto di conseguenza: la meta' meccanizzabile e' coperta, mentre resta a carico umano la prosa che nessun test puo' verificare.

3. Verificato in questa tranche su tre interpreti reali (3.11.14, 3.12.12, 3.14.7) il paragrafo sugli scope annidati, che prima era dedotto da PEP 709 e non misurato. Corpo di lambda e corpo di generator expression alzano NameError su tutte e tre; l'iterabile piu' esterno di una genexp funziona su tutte e tre; list, set e dict comprehension funzionano su 3.12 e 3.14 e alzano NameError su 3.11. `requires-python = ">=3.11"`, quindi entrambi i lati della divisione sono in scope e il documento li riporta entrambi.

Delta dal gate pass 2 di TASK-7 (2026-09-16). Tre aggiunte al documento, due delle quali cambiano cosa resta a carico umano nel criterio #2.

4. Terzo pin meccanico: `test_documented_denylist_matches_the_constant` asserisce che ognuno dei cinque nomi in `_UNCONSTRUCTIBLE_EXC` compaia nel testo del riferimento. La costante e' derivata dall'interprete in esecuzione, come i due tetti numerici, quindi una release di Python che renda costruibile una di quelle classi rompe questo file invece di lasciare in giro un ruleset rifiutato per un motivo che il riferimento non da' piu'. Verificata la non vacuita': i cinque nomi reali passano, un `UnicodeFrobError` inventato fallisce.

5. La riga `sleep` della tabella delle action e' stata riscritta dopo la misura delle tre bande di `time.sleep` (verbale completo su TASK-7). Diceva che il limite e' sulla durata; dice ora che e' sulla CONVERSIONE, che `time.sleep` conta contro una scadenza monotona assoluta, e che il limite stesso fallisce con OSError su una macchina accesa da un tempo qualsiasi. La cifra `9223372036000` resta a testo perche' e' quella che il pin del punto 2 sorveglia.

6. Aggiunto un paragrafo che qualifica la semantica RETURN sugli eventi exit: se il corpo ALZA, l'override viene scartato mentre il firing risulta comunque registrato. E' documentazione di un difetto reale, non del comportamento voluto, e dipende quindi da **TASK-52**: il giorno in cui quel task viene risolto il paragrafo va riletto e quasi certamente riscritto. Registrato qui perche' e' esattamente il tipo di prosa che il criterio #2 dice che nessun test puo' sorvegliare.

Analogamente, la premessa di "Where each check happens" descrive oggi il comportamento di **TASK-51** (il ruleset invalido non ferma il run, esce 0). Anche quella va riletta quando TASK-51 viene chiuso.

Rilievi dal gate /simplify di TASK-1 (RT-01), rieseguito in sola lettura il 2026-09-17 sullo stato finale approvato. Depositati qui invece di aprire task separati, su disposizione dell'orchestrator. NON sono lavoro svolto su questo task: alimentano il criterio #2, che e' esattamente la meta' in prosa che nessun test puo' sorvegliare. Nessuno di questi e' un difetto di correttezza; il codice era congelato quando sono stati raccolti e nulla e' stato applicato.

Un censimento sbagliato in un commento, che e' il caso in cui la prosa e' gia' derivata dal codice e ha derivato male. `src/pyteman/sitecustomize.py:139-141` dichiara che i lettori della stringa di contratto `<notes unavailable>` sono QUATTRO. Sono cinque: `docs/rules.md:166`, `tests/test_activation_atomic.py` alle righe 287, 328 e 357, e `README.md:63`, che il commento non conta e che nessun test copre. Verificato con grep il 2026-09-17. E' il genere di conteggio che andrebbe pinnato come i tetti numerici del punto 2, oppure scritto senza cifra.

Stessa derivazione ripetuta a quattro altitudini diverse. La catena `site.execsitecustomize` / `os._exit` compare per esteso in quattro punti fra sorgente, test e documentazione. Una sola copia dovrebbe portare la derivazione e le altre tre rimandarci.

La frase di contratto sul prefisso `_ROLLBACK` compare due volte, nel commento a `patcher.py:271-273` e nel docstring di `_disclose` a 282-283, a poche righe di distanza.

La derivazione `isinstance` contro `type(x) is list` compare per esteso tre volte.

Dentro `tests/test_activation_atomic.py`, la spiegazione 'la fixture scrive attraverso il setattr di base' e' ripetuta per esteso quattro volte.

Cosmetici, raccolti nello stesso giro: riavvolgimenti di riga irregolari in `docs/rules.md` e nel README; un rimando incrociato a un nome di test spezzato a meta' su fine riga fra le righe 756 e 757 di `tests/test_activation_atomic.py`, che lo rende non greppabile proprio mentre serve da indice; e `README.md:28`, che afferma 'there are five' fasi senza che nulla pinni quel conteggio, cioe' la stessa classe di guasto del censimento sopra.

Rilievo dal gate /simplify di TASK-5 (2026-09-17), depositato qui accanto ai rilievi omologhi del gate di TASK-1. NON e' lavoro svolto su questo task: alimenta il criterio #2, ed e' la stessa classe del punto "stessa derivazione ripetuta a quattro altitudini diverse" sopra, vista pero' dal lato della REGOLA invece che dal lato delle occorrenze.

**Non esiste una convenzione dichiarata su dove viva una derivazione, e la tranche ne applica due opposte a poche funzioni di distanza.** Il docstring di `_restore` in `src/pyteman/patcher.py` rimanda esplicitamente a `docs/rules.md` per la derivazione completa, con la motivazione scritta di non ripeterla "una seconda volta qui". Il docstring di `uninstall`, nello stesso file, fa il contrario: riderivar per esteso la classificazione a tre vie dell'hook vivo, che `docs/rules.md` deriva gia' per esteso a sua volta. Nessuna delle due scelte e' sbagliata isolatamente, e ognuna ha una giustificazione locale plausibile (il lettore di `uninstall` ha bisogno del contratto sotto gli occhi, quello di `_restore` no). Insieme pero' significano che la prossima persona che tocca una di quelle due derivazioni non ha modo di sapere quante copie deve aggiornare, ed e' esattamente il meccanismo con cui nasce la deriva che questo task sorveglia.

Confidenza dichiarata piu' bassa degli altri rilievi depositati: e' una questione di convenzione, non una prosa che contraddice il codice, e va risolta decidendo invece che correggendo. La decisione utile e' una sola riga di policy, del tipo "la derivazione vive in `docs/rules.md` e il docstring ne porta la conseguenza operativa piu' un rimando", oppure la sua opposta; qualunque delle due, applicata in modo uniforme, rende meccanico il censimento delle copie che oggi non lo e'.

Nota di stato: le tre derivazioni citate nel blocco di rilievi di TASK-1 sopra (la catena `site.execsitecustomize` / `os._exit`, la frase sul prefisso `_ROLLBACK`, il confronto `isinstance` contro `type(x) is list`) sono state raccolte su codice congelato e non sono state toccate. Il testo di `patcher.py` e' invece cambiato con TASK-5, quindi i riferimenti di riga di quel blocco vanno riverificati prima dell'uso, non i fatti.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
PR #81 (branch work/readme-yaml-tests). Added three tests to tests/test_docs_rules.py: a guard (test_readme_has_yaml_examples_to_check, floor >= 2 plus fence-count equality) and a parametrized loader (test_every_readme_ruleset_loads) covering both README YAML blocks (hold-commit and flip-sync). AC #2 was already satisfied by existing tests (test_documented_bounds_match_the_constants, test_documented_denylist_matches_the_constant); prose portions are manual review by definition. Suite: 1193 passed, 2 skipped, no regressions. Gates: /simplify clean (3/3), code-review clean, /pa:reflect READY.
<!-- SECTION:FINAL_SUMMARY:END -->
