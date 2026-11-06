---
id: TASK-90
title: SQL-03. Il verdetto non dice a quale database ATTACHed appartiene un finding
status: Done
assignee: []
created_date: '2026-09-16 21:20'
updated_date: '2026-09-27 18:44'
labels:
  - sql
  - follow-up-task-25
  - opus-5
dependencies: []
references:
  - src/pyteman/sqlitekit/integrity.py
  - tests/integrity_corpus.py
  - docs/integrity.md
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Follow-up individuato durante TASK-25 (SQL-02) e deliberatamente escluso dal suo perimetro.

TASK-25 ha corretto il riconoscimento dell'header: `*** in database <nome> ***` viene ora riconosciuto per forma e non confrontato con la stringa letterale che nomina `main`. Osservato su SQLite 3.51.2, un file controllato tramite ATTACH stampa `*** in database aux1 ***`; il campione `attached_database_header` in tests/integrity_corpus.py lo conserva.

L'header viene però soltanto rimosso, non letto. Una cattura che copre più database attaccati produce più header, ciascuno seguito dai propri finding, e `classify_integrity` restituisce un unico insieme piatto di `classes` e `unclassified` senza dire quale database ha prodotto cosa. Un operatore che riceve `CANONICAL_INDEX_COUNT` non sa su quale dei file allegati intervenire.

Il nome del database è già presente nel testo e viene scartato: l'informazione non manca, viene buttata via.

Non affrontato in TASK-25 perché cambierebbe la forma della risposta, che TASK-24 deve poter assumere stabile.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Riprodurre su SQLite reale una cattura con due database attaccati entrambi danneggiati e conservarla come campione osservato nel corpus
- [x] #2 Il verdetto attribuisce ogni finding al database che lo ha prodotto senza perdere l'ordine originale delle righe
- [x] #3 Lo schema della risposta resta retrocompatibile per un chiamante che legge solo status/classes/unclassified/diagnosis/raw oppure la rottura e documentata esplicitamente
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
IMPLEMENTAZIONE (2026-09-27): un solo passaggio sulle righe legge ogni header come cambio-sezione (_header_database estrae il nome fra i due marker), attribuisce ogni finding al database corrente (righe pre-header: 'main', perche' e' il nome che SQLite dà al database della pragma quando nomina le sezioni), e il verdetto porta un campo ADDITIVO 'databases' ({nome: {classes, unclassified}} in ordine d'incontro; {} sui cammini NO_OUTPUT/CLEAN/INCONCLUSIVE; una frase di diagnosi in piu' quando piu' database attribuiti). Campione OSSERVATO attached_databases_attribution nel corpus: due db FTS5 danneggiati (60/400 byte azzerati a offset 40 di pagina 5), ATTACH come aux1, pragma sulla connessione: 3 righe, 102 linee, main con classe FTS_CORRUPTION + 30 non classificate, aux1 con 69 non classificate; procedura registrata in docs/integrity.md secondo la convenzione del corpus (il test dei docs chiede che ogni numero citato dal campione compaia nella procedura).

GATE (2026-09-27): /simplify combinato 4 finding APPLICATI (le due affermazioni 'cinque chiavi' in docstring-modulo e docs/integrity.md ora 'sei chiavi' con bullet databases; la ricetta tolta dalla nota del corpus e rimessa ai docs dove vive; setdefault del bucket hoist-ato fuori dai due rami; lista findings vestigiale sostituita da un test all-headers). BELT: CHANGES-REQUIRED con due finding confermate: (1) il test 'headerless' usava rowid_disorder che HA l'header, quindi il default current='main' non era mai esercitato (mutazione current=None: zero fallimenti) -> test rinforzato con un campione davvero senza header (index_count_with_residue), mutazione ora uccide; (2) docstring-modulo e README ancora a cinque chiavi -> aggiornati. La belt ha anche RIPRODOTTO la procedura su SQLite 3.53.4 ottenendo la stessa forma e gli stessi numeri del campione registrato su 3.51.2, e verificato i bordi (nome vuoto, nome col marker dentro, solo header, header senza finding: tutti onesti e conformi ai docstring). Mutazioni finali: attribuzione rimossa -> 5 test falliscono; default main rimosso -> test headerless fallisce. Batteria 1316 passed 2 skipped.

INCIDENTE DI PROCESSO REGISTRATO: due script di edit consecutivi sono morti silenziosamente su ancore con wrapping diverso (assert fallito prima della scrittura), mentre i comandi successivi della stessa catena continuavano: i finding docs/corpus erano applicati, quelli su integrity.py e test no, e la mutazione B passava ancora. Scoperto rileggendo i byte reali dopo la belt. Correzione immediata: rifatti con marcatori per-edit e verifica grep per byte. Lezione: ogni script di edit deve stampare un marcatore per modifica e il comando dopo deve verificare il byte atteso, non la sola exit della catena.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Chiuso con il merge 816037d (PR #172, squash di e27b151 su master e734671). Gli header '*** in database <nome> ***' sono ora letti come cambi di sezione: un solo passaggio attribuisce ogni finding al database che l'ha prodotto (righe pre-header: main), e il verdetto porta il campo ADDITIVO 'databases' ({nome: {classes, unclassified}} in ordine d'incontro, {} sui cammini senza finding da attribuire, una frase di diagnosi in piu' quando piu' database). Campione OSSERVATO nel corpus con entrambi i database ATTACHed danneggiati (procedura in docs/integrity.md, riprodotta indipendentemente dalla belt su SQLite 3.53.4 e dalla revisione indipendente con la stessa forma e gli stessi numeri), sei test di attribuzione, pin dello schema a sei chiavi, docstring e README allineati. Retrocompatibilita' AC3: campo additivo, i cinque campi originali invariati (verificato per grep su ogni consumatore e per batteria). Gate: /simplify 4 finding applicati; belt CHANGES-REQUIRED (test headerless vacuo sotto mutazione current=None, e docstring/README a cinque chiavi) fissati e mutazioni ora uccidono; revisione indipendente APPROVED a e27b151 (note informative only); CI verde 7 check sullo stesso head; batteria 1316 passed 2 skipped.
<!-- SECTION:FINAL_SUMMARY:END -->
