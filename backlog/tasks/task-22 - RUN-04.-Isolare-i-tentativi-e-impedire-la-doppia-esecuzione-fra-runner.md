---
id: TASK-22
title: RUN-04. Isolare i tentativi e impedire la doppia esecuzione fra runner
status: Done
assignee: []
created_date: '2026-09-16 12:20'
updated_date: '2026-09-18 20:18'
labels:
  - audit-2026-09-16
  - opus-5
  - run
  - confirmed
milestone: m-3
dependencies:
  - TASK-19
  - TASK-20
  - TASK-21
references:
  - 'src/pyteman/runner/matrix.py:21-37'
documentation:
  - doc-1
  - doc-2
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P1 per esecuzione concorrente, P2 per tentativi; CONFIRMED, aperto.

**File:** `src/pyteman/runner/matrix.py:21-37`.

**Evidenza:** una cella fallita che lascia partial.txt viene rieseguita nella stessa directory e vede il file precedente. Due chiamate indipendenti a run_matrix, sincronizzate nel callback con threading.Barrier e connessioni SQLite separate, eseguono entrambe la stessa cella senza errori. Una seconda prova con due processi spawn conferma due callback sulla stessa directory, due risultati done, exit code zero per entrambi e una sola riga finale nel database. Il tratto SELECT, callback, INSERT non prenota la cella; il database conserva soltanto l'ultimo risultato con INSERT OR REPLACE. La serialità documentata vale dentro una chiamata, non garantisce esclusione fra chiamate concorrenti.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 retry non legge residui salvo ripresa esplicitamente supportata; due runner sulla stessa cella non entrano entrambi nel callback; crash dopo claim e prima/dopo commit recuperabile secondo policy.
- [x] #2 Provenienza di tutti i tentativi preservata.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Proposta iniziale da verificare sul codice corrente, non una correzione già applicata.

directory distinte per attempt e manifest storico, stato running con claim atomico e policy per crash/lease; oppure lock single-runner esplicito se la concorrenza non è un requisito. Non cancellare semplicemente la directory fallita, che contiene prove utili.

2026-09-18, piano rivisto dopo l'assessment in sola lettura su fb1cf40. Si sceglie il ramo lock single-runner esplicito, gia' ammesso dal testo del piano originale, e NON il claim atomico con lease: il claim richiederebbe heartbeat e scadenza per recuperare una prenotazione lasciata da un processo morto, cioe' lo scheduler distribuito che questo task non vuole. Dettaglio, misure e alternative scartate nelle note.

Consegna in due tranche. Tranche 1, committabile da sola: flock non blocante su <results_db>.lock tenuto per tutta la durata di run_matrix, preso prima della directory di experiment e della connessione, con rifiuto immediato e messaggio che nomina il conflitto; test multiprocessing deterministici per esclusione, non vacuita', recovery dopo SIGKILL e assenza di regressione sul percorso sequenziale. Chiude l'AC1.

Tranche 2, non in questo commit: tabella attempts in schema v3 additivo per la provenienza per-tentativo, che e' l'AC2 e coincide con il meccanismo richiesto da TASK-49 AC4. Da progettare insieme a TASK-49, non due volte.

Decisione aperta che blocca la scrittura del codice: comportamento su piattaforme senza fcntl. Raccomandazione, rifiuto esplicito.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: RUN-01, RUN-02, RUN-03; implementare dopo stabilizzazione dello schema.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.

2026-09-16, riferimento incrociato da TASK-19 (RUN-01), non un claim su questo task. RUN-01 ha introdotto in runner/matrix.py una infrastruttura di schema versionato: tabella schema_meta, sonda PRAGMA table_info, migrazione rename-copia-verifica con rollback completo e rifiuto di un database scritto da una versione piu recente. RUN-04 prevede una seconda tabella versionata per la provenienza per-tentativo e sarebbe quindi il secondo consumatore di quella logica, oggi privata e con prefisso underscore dentro matrix.py. TASK-42 (RUN-06) traccia l'estrazione in pyteman.sqlitekit; se RUN-04 parte prima, valutare se fare l'estrazione contestualmente invece di duplicare la sequenza o importare nomi privati.

2026-09-16, riferimento incrociato da TASK-19 (RUN-01), non un claim su questo task. RUN-01 non ha ridotto la finestra di concorrenza che questo task descrive, e in un punto l'ha resa piu esplicita. Una singola chiamata a run_matrix apre tre transazioni distinte sulla stessa connessione: _plan legge le righe memorizzate e decide il destino di ogni cella, _resolve_stored_rows archivia e adotta con il proprio commit, e il ciclo di esecuzione committa una volta per cella. Fra la lettura di _plan e la scrittura della cella corrispondente possono passare minuti, tutto il tempo del callback. Un secondo runner che entra in quella finestra pianifica sugli stessi dati e arriva alle stesse conclusioni.

Un solo punto oggi se ne accorge: l'adozione in _resolve_stored_rows controlla cur.rowcount e rifiuta se la riga pianificata e sparita sotto i piedi, perche dichiarare skipped una riga che non esiste piu sarebbe un claim su prove inesistenti. Non e un claim atomico, e non protegge il percorso normale: due runner sulla stessa cella con definizione identica entrano entrambi nel callback, e l'INSERT OR REPLACE finale lascia in tabella solo l'ultimo risultato. Il token minted per la directory del tentativo garantisce che i due non si scrivano sopra gli artefatti, quindi le prove di entrambi i tentativi sopravvivono, ma la riga superstite ne indica una sola.

Questo e il contesto per AC1. Il claim atomico va progettato qui, non in RUN-01, che aveva istruzione esplicita di non anticipare lease/claim concorrenti. Vedi anche TASK-49 (RUN-09): l'archiviazione non idempotente su interrupt richiede lo stesso meccanismo di registrazione, quindi conviene progettarli insieme.

## Assessment in sola lettura sul codice MERGIATO, 2026-09-18

Eseguito su work/concurrency-safety a fb1cf40, cioe' dopo che RUN-01 e' entrato in master. Il task era marcato CONFIRMED su a28b126 e NON ho dato per buona quell'etichetta: il codice e' cambiato nel frattempo, quindi ho riprodotto il difetto prima di progettare contro di esso. Nessun file del repository toccato; la sonda vive in /home/pantinor/pyteman-evidence/run04-probe/probe_double_execution.py e scrive solo in una tempdir.

### Il difetto si riproduce, e in una forma peggiore di come il task lo descrive

Due processi spawn, stessa results db, stesso artifact root, stessa identita' experiment, stessa cella. I due callback si danno appuntamento su una mp.Barrier, quindi non sono semplicemente vicini nel tempo: sono dimostrabilmente dentro run_cell nello stesso istante, altrimenti la barriera andrebbe in timeout e non lo fa.

    exit codes: [0, 0]
    outcome: ('B', 'returned', [{'cell_id': 'c', 'status': 'done', 'result': {'ran_by': 'B'}}])
    outcome: ('A', 'returned', [{'cell_id': 'c', 'status': 'done', 'result': {'ran_by': 'A'}}])
    attempt dirs that a callback wrote into: 2
    rows in results: 1
        c done {"ran_by": "A"} c.f7faac733904.23597fd623c2
    rows in results_superseded: 0
    attempt dirs no row points at: ['exp-168e34c2e97d/c.f7faac733904.24454c44a68b']

La parte che il testo del task non dice e che va registrata perche' cambia la gravita': **il processo B ha restituito al proprio chiamante il risultato B con exit code 0, mentre il database conserva il risultato A.** Non e' soltanto che sopravvive una riga sola. E' che a un chiamante viene detto che il suo risultato e' stato registrato quando registrato c'e' quello di un altro, e nessuno dei due processi segnala alcunche'. Un consumatore che legge il valore di ritorno e un consumatore che legge il database ottengono risposte diverse sulla stessa cella.

results_superseded resta a 0, quindi la sovrascrittura non lascia nemmeno la traccia che una supersessione lascerebbe: l'INSERT OR REPLACE non e' una supersessione dichiarata, e' una perdita silenziosa.

La directory orfana conferma anche il lato TASK-49: gli artefatti di B sopravvivono su disco, che e' voluto, ma nessuna riga li raggiunge.

### Scelta del meccanismo, con le alternative scartate e il perche'

Il task ammette esplicitamente il lock single-runner come alternativa al claim atomico, se la concorrenza non e' un requisito. Propongo quel ramo, e queste sono le decisioni che lo compongono.

**flock su file, non una riga di lock nel database.** Una riga di lock non viene rilasciata quando il processo muore, e per recuperarla servirebbe una lease con heartbeat e scadenza, cioe' esattamente lo scheduler distribuito che il task esclude. Un flock lo rilascia il kernel. Questa non e' una convinzione, e' misurata, sonda in probe_flock_crash_release.py:

    while holder alive : refused (11)
    holder exitcode    : -9 (-9 means SIGKILL)
    after SIGKILL      : acquired
    platform           : linux

SIGKILL non e' intercettabile da nessun handler, quindi questo e' il caso peggiore e non uno spegnimento cortese. Il lock torna disponibile senza alcun intervento manuale.

**Lock sull'intero database, non per experiment.** Sembra piu' fine locare per identita', e l'ho scartato per una ragione precisa nel codice: lo strato non namespaced. Con on_legacy 'rerun' o 'adopt', run_matrix scrive righe con experiment='' che OGNI experiment vede e puo' consumare (DELETE alla riga 847, e l'adozione in _adopt_stored_rows). Due experiment diversi che risolvono la stessa riga legacy sono in conflitto reale, e lock per-experiment non li separerebbe. Il lock a livello di database e' quindi la granularita' corretta e per giunta la piu' semplice.

**File di lock distinto dal file del database.** Prendere il lock sul file della db si sovrapporrebbe al locking di SQLite. Un file accanto, nome derivato dal percorso della db, non interferisce.

**Non blocante, rifiuto immediato con messaggio che nomina il conflitto.** Attendere significherebbe scegliere un timeout, cioe' indovinare quanto dura la matrice di un altro. Un rifiuto immediato dice la verita' e lascia la decisione a chi chiama.

**Nessuna transazione lunga sul callback.** Questo e' il vincolo che il parent ha posto e il lock lo rispetta per costruzione: l'esclusione vive nel filesystem, quindi le transazioni SQLite restano quelle di oggi, una per cella dopo il ritorno del callback. Non tocco la struttura transazionale.

### Tranche 1 proposta, committabile da sola

Ambito: esclusione single-runner. Chiude la meta' esclusione dell'AC1 e la meta' crash, NON l'AC2.

1. Un context manager che prende il flock non blocante su `<results_db>.lock`, aperto e tenuto per tutta la durata di run_matrix, rilasciato dal finally accanto a con.close(). Un secondo runner riceve un errore dedicato che nomina il file di lock e la db contesa.
2. Il lock va preso PRIMA di _prepare_experiment_dir e prima di aprire la connessione, cosi' che un runner rifiutato non crei directory di experiment ne' tocchi la db.
3. Documentazione del contratto nel docstring di run_matrix: la funzione ora puo' rifiutare, ed e' un cambio di contratto voluto.

Test, tutti deterministici e senza sleep come prova di ordinamento, coerentemente con l'AC5 di TASK-34:

- **Esclusione.** Due processi spawn. Il primo prende il lock ed espone un Event quando e' dentro il callback; il secondo parte solo dopo quell'Event e deve fallire con l'errore dedicato. Determinismo dall'Event, non dal tempo.
- **Non vacuita'.** Lo stesso test deve fallire se il lock viene rimosso: e' la forma red-green che la mia memoria registra come necessaria, perche' un test di esclusione passa banalmente se il secondo processo non parte mai. Il test asserisce anche che il primo runner ha completato e ha scritto la sua riga, cosi' 'il secondo e' stato rifiutato' non puo' essere soddisfatto da 'entrambi sono morti'.
- **Recovery dopo crash.** Un figlio prende il lock, entra nel callback e viene ucciso con SIGKILL. Il padre verifica exitcode -9, poi lancia un run nuovo sulla stessa db che deve ACQUISIRE il lock e completare la cella. Questo prova il rilascio da parte del kernel dentro la suite e non solo nella mia sonda, e prova la policy di ripresa: la cella non ha riga, quindi viene rieseguita.
- **Nessuna regressione sul percorso normale.** Un run sequenziale dopo l'altro sulla stessa db continua a fare skip della cella gia' done.

### Limiti dichiarati, non risolti

- **Piattaforma.** `fcntl` non esiste su Windows. La CI gira solo su ubuntu-latest (lacuna 3 di TASK-34) e il pacchetto non dichiara piattaforme. Questa e' una decisione che non prendo da solo: o si rifiuta esplicitamente su piattaforme senza fcntl, oppure si aggiunge un ramo msvcrt. **Raccomando il rifiuto esplicito con messaggio chiaro**, perche' girare senza protezione fingendo di averla e' peggio che dire di non supportare la piattaforma. Serve una decisione prima che io scriva il codice.
- **NFS.** La semantica di flock su NFS e' notoriamente inaffidabile. NON l'ho misurata e quindi non affermo nulla: va scritto come limite dichiarato nel docstring, non come garanzia.
- **Il lock e' advisory.** Protegge i runner che passano da run_matrix. Un processo che scrive nella db per conto proprio non e' vincolato, e questo va detto.
- **Misurato su linux, Python 3.14.7.** Non ho verificato macOS.

### Cosa resta aperto dopo la tranche 1

L'**AC2, provenienza di tutti i tentativi, NON e' chiuso dal lock.** Il lock impedisce la doppia esecuzione concorrente, quindi toglie quella sorgente di orfani, ma un tentativo interrotto continua a lasciare una directory che nessuna riga raggiunge: e' esattamente TASK-49 (RUN-09), gia' aperto e riprodotto anche dalla mia sonda.

Tranche 2 proposta: tabella `attempts` in schema v3, additiva, scritta PRIMA di run_cell in una transazione breve propria e chiusa con l'esito dopo. E' lo stesso meccanismo che l'AC4 di TASK-49 richiede di non duplicare, quindi le due chiudono insieme. Vincolo da rispettare li': l'AC3 di TASK-49 vieta qualunque migrazione che unisca o rimuova righe gia' scritte, duplicati storici compresi, quindi v2 a v3 deve essere solo additiva e non toccare ne' results ne' results_superseded.

Non apro task nuovi: TASK-49 esiste gia' e copre quella meta'.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
RUN-04 completato dalle sottounità pubblicate nelle PR #2 e #3: lock del database contro runner concorrenti e storia dei tentativi registrata prima degli artifact. Retry distinti preservano precedenti tentativi e artifact; righe non finalizzate rimangono incomplete senza inferire cause. Riconciliazione 2026-09-18: entrambe le PR confermate MERGED, nessuna review o commento pendente; CI 35359891183 sul merge corrente b1a886d con sei job success. Suite locale attuale 926 passed, 1 skipped opzionale. gate-exempt per sola riconciliazione del parent nel tracker, nessuna nuova implementazione.
<!-- SECTION:FINAL_SUMMARY:END -->
