---
id: TASK-21
title: >-
  RUN-03. Gestire errori di risultato e chiudere risorse anche fuori dal
  callback
status: Done
assignee:
  - '@opus-5-run03'
created_date: '2026-09-16 12:20'
updated_date: '2026-09-16 18:28'
labels:
  - audit-2026-09-16
  - opus-5
  - run
  - confirmed
milestone: m-3
dependencies:
  - TASK-19
references:
  - 'src/pyteman/runner/matrix.py:16-39'
  - 'src/pyteman/runner/report.py:5-8,12-16'
documentation:
  - doc-1
  - doc-2
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P2, CONFIRMED, aperto.

**File:** `src/pyteman/runner/matrix.py:16-39`, `src/pyteman/runner/report.py:5-8,12-16`.

**Evidenza:** callback che restituisce `{'bad': {1}}` termina il runner in json.dumps con TypeError; non salva una riga failed e non esegue la cella successiva. close è solo nel percorso normale. Il callback può restituire JSON non mapping, mentre il report usa `.get` e lo degrada a `?`. `run_cell(...) or {}` perde risultati falsy senza un contratto esplicito.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 set non serializzabile, mapping valido, false/0/list/None secondo contratto, errore callback, errore DB e report senza tabella.
- [x] #2 Le celle recuperabili successive partono, le risorse si chiudono e gli errori di storage restano visibili.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Proposta iniziale da verificare sul codice corrente, non una correzione già applicata.

schema del risultato esplicito (mapping JSON), serializzazione dentro il perimetro dell'errore di cella, risorse chiuse in finally. Distinguere un risultato invalido recuperabile da errore di persistenza/disco pieno, che non deve essere nascosto fingendo di aver salvato. Rendere gli errori report diagnostici.

2026-09-16, confine documentato e non cambiato dopo il gate di review: sqlite3.DataError per una riga oltre SQLITE_MAX_LENGTH e sottoclasse di sqlite3.Error, quindi un risultato serializzabile ma troppo grande alza MatrixStorageError e ferma il run, e poiche nulla viene scritto la cella si ripiana identica a ogni invocazione successiva e le celle in coda restano irraggiungibili. Il docstring di run_matrix ora lo dice esplicitamente. Il cambio di comportamento e una decisione di contratto e non va presa dopo la review senza verifica: aperta come TASK-64.

Rilievi non corretti in RUN-03 e tracciati nello stesso turno: TASK-63 (tabella con experiment ma senza fingerprint, la colonna experiment viene scartata e due righe distinte collassano; ramo RUN-01, fuori perimetro), TASK-64 (riga troppo grande, sopra), TASK-65 (database bloccato riportato come file del tipo sbagliato), TASK-66 (chiavi non stringa nel risultato, oggetto restituito e riga memorizzata si contraddicono).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: RUN-01 per schema persistito.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.

2026-09-16, riferimento incrociato da TASK-19 (RUN-01), non un claim su questo task. RUN-01 aggiunge alla tabella results le colonne experiment e fingerprint e sposta la PRIMARY KEY su (experiment, cell_id); aggiunge inoltre le tabelle schema_meta e results_superseded. La query di report.py:6-7 seleziona colonne per nome e non e stata modificata, quindi per ogni chiamante attuale (un solo esperimento, implicito) l'output resta identico: verificato, tabella con una sola riga per cella. Il limite emerge solo quando un chiamante adotta una seconda identita experiment=: la stessa cella compare due volte con lo stesso cell_id e nessuna colonna che le distingua. Verificato sullo stato corrente: due righe '| c1 | done | CLEAN |' indistinguibili. Non corretto in RUN-01 perche report.py appartiene a questo task. Quando RUN-03 tocca quella query, valutare se proiettare experiment nella tabella o filtrare su una singola identita.

2026-09-16, secondo riferimento incrociato da TASK-19 (RUN-01), non un claim su questo task. La tabella results_superseded introdotta da RUN-01 conserva ogni riga soppiantata (motivi mismatch, legacy, adopted) ma nessun lettore la espone: report.py legge solo results. L'archivio e quindi verificabile solo con sqlite a mano. Non corretto in RUN-01 perche report.py appartiene a questo task. Quando RUN-03 tocca il report, valutare una sezione o un comando che mostri le righe soppiantate con il loro motivo, altrimenti la garanzia nessuna riga storica sparisce senza traccia resta vera ma non ispezionabile dall'utente.

2026-09-16, verifica di confine da TASK-19 (RUN-01). La riscrittura di RUN-01 ha toccato ogni riga di runner/matrix.py, quindi il difetto descritto qui e stato riprovato sullo stato corrente per escludere che si fosse spostato o fosse stato risolto per effetto collaterale. Risultato: intatto. Un callback che restituisce {'bad': {1,2}} fa morire run_matrix con TypeError Object of type set is not JSON serializable, non persiste alcuna riga failed (SELECT cell_id, status FROM results restituisce lista vuota) e la cella successiva della matrice non parte. Unica differenza introdotta da RUN-01: la connessione sqlite e ora chiusa in un blocco finally, perche le nuove vie di rifiuto sollevano prima del punto in cui avveniva la close originale e senza il finally RUN-01 avrebbe introdotto una connessione che perde. La parte restante di questo task, cioe serializzazione dentro il perimetro dell'errore di cella, contratto esplicito sul risultato e distinzione fra risultato invalido ed errore di persistenza, resta interamente aperta.

2026-09-16, RUN-03, correzione di due note incrociate sopra. Misurate stale sullo stato corrente prima di implementare, non dedotte dal testo del tracker.

(1) La nota che dichiara che la query di report.py non e stata modificata e che due esperimenti producono righe indistinguibili non vale piu. report.py e stato riscritto: l'header e ora | experiment | cell | status | signature | e la colonna experiment viene proiettata. Misurato: due run della stessa cella con experiment diversi rendono due righe distinte, e tests/test_report.py::test_rows_from_different_experiments_are_distinguishable blocca la proprieta. Nessun residuo su quel punto per RUN-03.

(2) La nota di verifica di confine che dichiara il difetto di serializzazione 'intatto' non vale piu. Misurato: un callback che restituisce {'bad': {1,2}} produce una riga failed per quella sola cella, con error 'result is not JSON-serialisable: TypeError(Object of type set is not JSON serializable)'; la cella successiva parte; entrambe le righe sono persistite. La serializzazione e gia dentro il perimetro dell'errore di cella. Non ricorretta da RUN-03.

Residui reali misurati e presi in carico da RUN-03: (a) run_cell(...) or {} piegava {}, 0, False, None, '' e [] tutti in status done, result {}, stored '{}', quindi mutuamente indistinguibili e senza contratto dichiarato; (b) un ritorno non-mapping ma serializzabile ([1,2], 'text', 42, True) veniva memorizzato verbatim e il report lo degradava a '?'; (c) un errore di persistenza propagava come sqlite3.OperationalError nudo senza nominare la cella; (d) il report su un db privo di tabella results, o su un file che non e un database, dava OperationalError/DatabaseError nudi.

Il punto results_superseded senza alcun lettore e fuori dal perimetro assegnato a RUN-03 e viene aperto come task separato nello stesso turno, non rinviato a una nota.

2026-09-16, RUN-03, esito del gate di code review high sullo stato finale. Tre rilievi importanti, sei minori, nessuno critico. Applicati in questo turno, con mutazione a prova di non vacuita: (1) report.py, json.loads(rj or "{}") ripiegava su truthiness, quindi 0, 0.0, False, b'' e '' in una colonna estranea rendevano una signature vuota, indistinguibile da una cella che non ha nulla da riportare, mentre 42 nella stessa colonna veniva etichettato illeggibile. E la stessa piega falsy che RUN-03 toglie al runner, sopravvissuta sul lato lettura. Corretto in "{}" if rj is None else rj, perche solo NULL significa che nulla e stato registrato. (2) matrix.py, il commento della guardia di storage affermava che restringere a sqlite3.Error lascia emergere come se stesso un errore nelle istruzioni sopra: falso, ProgrammingError e InterfaceError sono sottoclassi di sqlite3.Error e verrebbero riportati come riga non scrivibile. Commento riscritto con il limite dichiarato. (3) matrix.py, il docstring di _cell_result giustificava dict invece di Mapping sostenendo che json.dumps rifiuta tutto il resto: falso, serializza liste, stringhe e scalari. La ragione vera e la prima meta del docstring; paragrafo riscritto. (4) test_matrix_results.py, il commento diceva che l'asserzione legge il testo memorizzato mentre leggeva il dict restituito: ora legge stored_rows(db)['bad'], che e anche piu forte. (5) nuovo test sulla supersessione che non ha potuto essere scritta: results_superseded resta vuoto e la riga viva sopravvive. Il docstring dichiara che pinna la proprieta e non la riga con.rollback(), che resta neutra alla mutazione perche close() scarta la stessa transazione. (6) README, MatrixReportError copre anche il file che non si apre affatto.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
RUN-03 chiude il contratto del risultato, separa la colpa della cella da quella dello storage e rende diagnostici gli errori del report.

Contratto. run_cell restituisce un dict, oppure None per dire che non ha nulla da riportare. Qualunque altra cosa, inclusi 0, False, '' e [], e colpa della cella e viene registrata come riga failed con la ragione, lasciando correre il resto della matrice. Prima `run_cell(...) or {}` piegava {}, 0, False, None, '' e [] tutti nello stesso status done con result {}, mutuamente indistinguibili e senza contratto dichiarato. La validazione sta dentro il try esistente, quindi entra nello stesso percorso except che gia gestisce un callback che solleva.

Confine dello storage. La scrittura della riga non e colpa della cella: un results db che rifiuta la riga alza MatrixStorageError e ferma il run, invece di proseguire producendo prove che nessuno sta conservando. Il messaggio nomina la cella e la directory dei tentativi, che e l'evidenza che esiste comunque.

Report. Un db senza tabella results, un file che non e un database e un percorso che non si apre affatto alzano MatrixReportError che nomina il file, invece di OperationalError nudi da tre frame piu giu; sqlite inventa un file vuoto per qualsiasi nome, quindi il refuso nel percorso e il caso di gran lunga piu comune. Un result_json che non e JSON e uno che e JSON ma non e un mapping ora si distinguono in tabella, perche i rimedi sono diversi.

Due note del tracker misurate stale e corrette invece che ereditate: la query di report.py era gia stata riscritta da RUN-01 e proietta experiment, e la serializzazione era gia dentro il perimetro della cella.

Gate di review high sullo stato finale: tre rilievi importanti, sei minori, nessuno critico; sei applicati in questo turno, quattro tracciati come TASK-63/64/65/66. Il piu rilevante e la stessa piega falsy sopravvissuta sul lato lettura, dove json.loads(rj or "{}") rendeva 0, b'' e '' come signature vuota mentre 42 nella stessa colonna era etichettato illeggibile; ora solo NULL, che e l'unico valore che significa davvero che nulla e stato registrato, ottiene il default vuoto.

Confine documentato e non cambiato: un risultato serializzabile ma troppo grande per sqlite alza MatrixStorageError, e poiche nulla viene scritto la cella si ripiana identica per sempre. Il docstring di run_matrix lo dice; il cambio di comportamento resta proposta in TASK-64.

Prove: tre mutazioni tutte uccise dal test scritto per esse; perimetro RUN-03 15 test (9 in tests/test_matrix_results.py, 6 degli 11 in tests/test_report.py); suite completa 332 passed. Verifica indipendente del parent su None/{}/False/0/''/[]/set annidato/dict valido, su un trigger sqlite che rifiuta le scritture e su db di report invalidi: conforme. APPROVED.
<!-- SECTION:FINAL_SUMMARY:END -->
