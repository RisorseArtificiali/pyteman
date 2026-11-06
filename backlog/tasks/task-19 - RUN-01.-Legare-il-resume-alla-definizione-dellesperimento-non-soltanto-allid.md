---
id: TASK-19
title: >-
  RUN-01. Legare il resume alla definizione dell'esperimento, non soltanto
  all'id
status: Done
assignee:
  - opus-5-run01
created_date: '2026-09-16 12:20'
updated_date: '2026-09-16 16:23'
labels:
  - audit-2026-09-16
  - opus-5
  - run
  - confirmed
milestone: m-3
dependencies: []
references:
  - 'src/pyteman/runner/matrix.py:17-25'
documentation:
  - doc-1
  - doc-2
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P1, CONFIRMED, aperto.

**File:** `src/pyteman/runner/matrix.py:17-25`.

**Evidenza:** prima esecuzione con `{id: same, params: {x: 1}}`, seconda con x=2: il callback viene chiamato solo per x=1, la seconda è skipped e nel database resta il risultato 1. Non vengono salvati configurazione della cella, hash ruleset, revisione workload o versione harness.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 config identica salta, config/revisione/ruleset diversi rieseguono o falliscono esplicitamente; due definizioni con stesso id nella stessa matrice vengono rilevate.
- [x] #2 Resume non attribuisce prove vecchie a codice nuovo; nessun dato storico viene sovrascritto senza policy.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Proposta iniziale da verificare sul codice corrente, non una correzione già applicata.

schema versionato e fingerprint canonico della cella più identità esplicita dell'esperimento fornita dal chiamante. Rifiutare collisioni o aprire una nuova run, non riusare risultati incongruenti. Validare id duplicati nell'input prima di eseguire celle. Definire migrazione conservativa dei risultati preesistenti senza provenienza.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: nessuna; RUN-04 riusa run/fingerprint.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.

2026-09-16: claim da agente Herdr implementatore (modello copilot/claude-opus-5). Ownership file: src/pyteman/runner/matrix.py, tests/test_matrix.py e nuovi test runner. Milestone verificata: m-3 corrisponde a "M4: runner, persistenza e classificazione", nessuna correzione di milestone necessaria. Prossimo passo: riproduzione del difetto sullo stato corrente prima di qualsiasi modifica.

2026-09-16, decisione deliberata registrata dalla review Efficiency. La colonna experiment conserva il JSON canonico grezzo dell'identita passata dal chiamante, non il suo hash. Un hash darebbe righe di lunghezza fissa e una chiave piu compatta, ma renderebbe l'identita illeggibile proprio nel momento in cui serve, cioe quando un operatore apre il database per capire da quale ruleset o revisione di harness proviene una riga. Il fingerprint della cella e hashato perche la definizione integrale e gia persistita accanto in cell_json; per l'esperimento non esiste una seconda copia leggibile, quindi l'unica rappresentazione deve restare quella ispezionabile. Costo accettato: chiavi primarie piu lunghe su matrici con identita verbose.

2026-09-16, documentazione obsoleta prodotta da questo task e BLOCCATA su coordinamento. README.md:67 documenta letteralmente la firma a quattro argomenti `pyteman.runner.matrix.run_matrix(cells, run_cell, results_db, artifact_root)`. RUN-01 rende experiment un parametro keyword-only obbligatorio, quindi quella riga descrive una chiamata che oggi solleva TypeError. Le note di implementazione di questo task chiedono di aggiornare la documentazione pertinente nello stesso task, ma l'incarico dell'agente vieta modifiche a README e documenti comuni senza coordinamento: conflitto sollevato al parent invece di essere risolto unilateralmente. Verificato inoltre che examples/hermes-111912/README.md:58 nomina la funzione solo in prosa e non contiene firme, quindi non e intaccato, contrariamente a quanto riportato dalla review. Nessun altro riferimento a run_matrix fuori da test e tracker.

2026-09-16, raccomandazioni di review depositate nel tracker perche fuori dalla ownership di questo task: TASK-42 (RUN-06, estrazione del versioning schema in pyteman.sqlitekit), TASK-43 (API-05, base comune PytemanError e rilevazione duplicati unica con rules.py), TASK-44 (RUN-07, strumenti espliciti per lo strato legacy), TASK-45 (TEST-05, helper sqlite condiviso in conftest). Riferimenti incrociati aggiunti a TASK-20 (collisione directory artefatti fra esperimenti), TASK-21 (report.py non distingue gli esperimenti e non legge results_superseded) e TASK-22 (RUN-04 secondo consumatore del versioning schema).

2026-09-16, code-review high effort completata: 7 difetti CONFIRMED, tutti in file di mia ownership, tutti corretti in questo turno. C1 la migrazione v1->v2 non era atomica perche sqlite3 autocommitta il DDL fuori da una transazione esplicita, quindi un interrupt fra ALTER e INSERT lasciava un database che si presenta come corrente e nasconde ogni riga storica in results_v1; corretto con un BEGIN esplicito che rende applicabile il DDL transazionale di SQLite, il che ha reso superfluo il blocco di undo manuale. C2 cell_fingerprint collideva sulle chiavi non stringa perche json.dumps le converte, cioe esattamente la misattribuzione che RUN-01 esiste per impedire; ora rifiutate. C3 il messaggio di rifiuto suggeriva una nuova identita experiment anche per i conflitti legacy, rimedio falso perche lo strato non namespaced e visibile da ogni esperimento; ora il rimedio dipende dal tipo di conflitto. C4 la DELETE della riga legacy veniva committata prima che il rimpiazzo esistesse, quindi un interrupt durante run_cell lasciava la cella senza alcuna riga; la cancellazione e ora nella stessa transazione della INSERT che la sostituisce. C5 la directory artefatti derivava dal solo cell id, quindi una riesecuzione sovrascriveva gli artefatti della riga appena archiviata; una run che soppianta scrive ora in <artifact_root>/<cell_id>.<prefisso fingerprint>. C6 test_changed_definition_is_refused_before_any_cell_runs metteva la cella in conflitto per prima e quindi passava anche con un controllo ingenuo dentro il loop di esecuzione; ordine invertito. C7 il ramo adopt su riga fallita non era coperto.

2026-09-16, verifica di carico dei test nuovi tramite mutazione manuale su copia in /tmp, non sul checkout. Ogni difetto e stato reintrodotto uno alla volta e il test corrispondente deve fallire: C1 senza BEGIN, C2 senza rifiuto delle chiavi, C4 con DELETE anticipata, C5 con directory condivisa, C7 con adopt su riga fallita, C3 con rimedio falso, S4 con id non stringa. Esito: tutti e sette i test falliscono come richiesto. Per C6 la mutazione e strutturale, il controllo di conflitto e stato spostato dentro il loop di esecuzione: con il nuovo ordine delle celle il test fallisce, con il vecchio ordine passa, il che dimostra che l'inversione e cio che vincola il pre-pass. Un test verde prima e dopo una correzione non prova nulla, e C6 era esattamente quel caso.

2026-09-16, findings sospetti della review risolti in codice e non rinviati: S1 il messaggio prometteva che il database fosse intatto mentre schema_meta e results_superseded venivano creati prima del tentativo, ora il messaggio e circoscritto alla tabella results e la creazione di results_superseded e stata spostata dopo la migrazione, quindi un database che questo runner rifiuta di migrare conserva la forma scritta dal pyteman vecchio. S4 cell_id ha affinita TEXT, quindi l'id 1 e l'id '1' avrebbero indirizzato la stessa riga, stessa famiglia di difetto di C2, ora rifiutato. S6 la UPDATE di adozione non controllava rowcount e avrebbe riportato skipped per una riga sparita sotto una scrittura concorrente, ora verifica e fa rollback. S5 righe scritte con experiment=None non sono orfane ma un namespace distinto, raggiungibile ripassando None, comportamento lasciato invariato e documentato nel docstring. Residuo non risolto depositato in TASK-48 (RUN-08): l'archivio non registra quale run ha soppiantato una riga, da cui righe di archivio indistinguibili, ordinamento affidato a time.time() non monotono, e la collisione residua di directory artefatti nel ciclo A,B,A,B che il solo fingerprint non puo chiudere.

2026-09-16, ready-for-final-verification. File modificati, tutti entro la ownership assegnata: src/pyteman/runner/matrix.py (riscritto), tests/test_matrix_identity.py (nuovo, 29 test), tests/test_matrix.py (solo experiment=None ai quattro call site esistenti). Nessuna modifica a report.py, altri runtime, pyproject.toml, workflow, README o documenti comuni. Comandi e output reali, Python 3.14.7 da /tmp/pyteman-audit-env-OOeElF/bin/python, nessuna installazione globale: file di mia ownership 31 passed; suite completa 264 passed, exit=0. Il numero della suite completa oscilla fra esecuzioni perche un altro agente sta modificando test_rules.py, test_targets.py e test_rule_contracts.py in contemporanea sullo stesso checkout; i 31 dei miei file sono stabili. Criteri di accettazione verificati clausola per clausola contro il codice in esecuzione e non contro i test: config identica salta, config diversa viene rifiutata esplicitamente senza eseguire, ruleset diverso apre una nuova run, id duplicati rilevati prima di eseguire qualunque cella, ogni riga porta il proprio fingerprint, zero righe archiviate senza policy e archiviazione corretta con policy. Limiti dichiarati: README.md:67 documenta ancora la firma a quattro argomenti e resta bloccato su coordinamento; il ciclo A,B,A,B sugli artefatti e in TASK-48; nessuna copertura di concorrenza reale multi-processo. Stato lasciato In Progress in attesa di APPROVED del parent.

## Verifica finale parent: CHANGES REQUESTED (4 finding)

Il parent ha rieseguito i 31 test (passano) e ha riprodotto quattro gap di provenance che bloccano AC2. Registrati qui prima della correzione.

**F1 - Gli artefatti non sono isolati per esperimento fin dalla prima run.** Stesso cell id sotto experiment='rev-A' e experiment='rev-B': entrambe le righe puntano a `<artifact_root>/same` e la riga A finisce per leggere il contenuto prodotto da B. Il namespace nuovo isola le righe del db ma non la directory artefatti, che resta derivata dal solo cell id. Il suffisso fingerprint introdotto per C5 copre solo il caso mismatch, quindi non interviene qui.

**F2 - Il ciclo A,B,A,B distrugge prove archiviate e non e differibile.** Avevo depositato questo in TASK-48 come residuo; il parent osserva correttamente che TASK-19 promette nessuna perdita di storico, quindi la perdita va chiusa adesso. Il fingerprint da solo non la chiude: alla terza run la fingerprint di A ritorna e la directory viene riusata mentre la riga archiviata della prima run la indica ancora.

**F3 - Il callback riceve il dict originale e puo mutarlo, e la definizione autorevole viene riserializzata dopo.** La fingerprint e calcolata prima del callback, `cell_json` dopo, quindi un callback che muta la cella scrive nel db una fingerprint che non corrisponde a `cell_fingerprint(json.loads(cell_json))`. Probe del parent: `cell={'id':'same','value':'before'}`, callback che imposta `value='after'`; ripassando la definizione originale la cella risulta skipped pur non essendo quella eseguita. Serve congelare la definizione autorevole prima del callback e impedire che mutazioni condivise tra celle alterino il piano.

**F4 - `matrix_markdown` misattribuisce con i namespace nuovi.** Due righe con lo stesso cell id sotto esperimenti diversi diventano due righe identiche senza identita esperimento. E misattribuzione introdotta dalla nuova API, non un refactor rinviabile.

**Ownership ampliata dal parent per questo giro:** `src/pyteman/runner/report.py` e i suoi test; `README.md` sola sezione Runner and sqlitekit (righe originarie 65-72), preservando ogni altra sezione. Nessun altro agente ha ownership su quelle righe. Resta escluso tutto il resto.

**Limiti di scope confermati dal parent:** correggere solo l'isolamento collision-free dei tentativi necessario a RUN-01, senza anticipare lease/claim concorrenti; TASK-48 va ridotto alle sole capacita residue davvero opzionali; TASK-42..45 non sono prerequisiti e non vanno implementati ora.

## Verifica per mutazione degli 8 nuovi test (F1-F4)

Un test verde prima e dopo una correzione non prova nulla. Ogni difetto corretto in questo giro e' stato reintrodotto uno alla volta su una copia in `/tmp` (mai nel checkout), dichiarando in anticipo quali test dovevano morire. Driver in `/tmp/mutate.py`, copia in `/tmp/pyteman-mut-VI5yaJ`; ogni sostituzione fallisce rumorosamente se non matcha esattamente una volta, e il driver esce in errore se pytest non riporta affatto risultati.

Primo giro: 8 mutazioni su 8 "sopravvissute", zero test uccisi. Uniformita' sospetta, non otto test inutili: l'harness azzerava `HOME`, pytest vive nel user site-packages sotto lo `HOME` reale, quindi ogni run moriva prima di collezionare un test e il parser leggeva "nessuna riga FAILED" come "test passato". Corretto passando l'ambiente reale piu' le due variabili necessarie, e aggiunto il controllo che l'output contenga davvero un esito.

Secondo giro, tutte le mutazioni uccidono i test dichiarati:

- M1 directory condivisa pre-fix con `exist_ok=True`: uccide i tre test di isolamento artefatti, piu' `test_superseding_run_does_not_overwrite_archived_artifacts` del primo lotto (copriva C5, ora coperto dallo stesso meccanismo).
- M2 esperimento tolto dal path, create esclusiva mantenuta: uccide solo `test_artifacts_are_isolated_between_experiments_from_the_first_run`.
- M3 create esclusiva tolta, namespace esperimento mantenuto: uccide solo i due test di collisione (`..._never_reuses_an_archived_directory`, `..._never_written_into`).
- M4 nessun freeze, callback riceve l'oggetto del chiamante e `cell_json` serializzato dopo: uccide entrambi i test F3.
- M5 report senza colonna experiment: uccide `test_rows_from_different_experiments_are_distinguishable`.
- M6 report che assume la colonna experiment ovunque: uccide `test_a_pre_provenance_database_still_renders`.
- M7 newline escapato senza escapare prima il backslash: uccide `test_text_that_would_break_the_table_is_escaped`.
- M8 nessun escaping: uccide lo stesso test.

M2 e M3 separano due proprieta' distinte che stavano per essere confuse. La create esclusiva da sola gia' impedisce la sovrascrittura, quindi il componente esperimento nel path non serve all'isolamento ma all'attribuzione. Il test F1 nella prima stesura non lo distingueva: verificato direttamente che, tolta l'asserzione `len(parents) == 2`, M2 passa verde (`1 passed`). L'asserzione e' stata aggiunta prima di questa verifica ed e' portante.

Suite completa dopo le correzioni: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /tmp/pyteman-audit-env-OOeElF/bin/python -m pytest -q` -> `272 passed in 3.17s`. File posseduti: `39 passed` (31 prima, piu' 5 in `test_matrix_identity.py` e 3 nel nuovo `tests/test_report.py`).

## Seconda code-review high effort: 9 finding, 8 corretti, 1 saltato con motivazione

2026-09-16. Review eseguita su copia read-only. Un avvertimento sul metodo prima dei finding: l'agente ha lavorato su un albero pre-fix (`/tmp/rev01/pyteman`), quindi il suo finding di severita' massima, la collisione di directory artefatti dopo un `rmtree(artifact_root)`, descriveva un difetto gia' chiuso. Le prove che porta lo dimostrano: il suffisso `.1` e il nome `same.683523615890` appartengono all'implementazione che sondava il disco per un nome libero, sostituita dal token minted. Non ricorretto. Ho pero' accolto la sua nota secondaria e corretto un overclaim nel docstring: una riga adottata e l'originale archiviato da cui e' stata timbrata puntano davvero alla stessa directory, perche' sono due registrazioni di un unico tentativo e non due tentativi, e il docstring prometteva invece che nessuna coppia di righe condivida mai gli artefatti.

**F2, un risultato non serializzabile abortiva l'intera matrice.** `json.dumps(result)` stava dentro la INSERT, cioe' fuori dal try/except che protegge il callback. Un callback che restituisce un oggetto non serializzabile sollevava TypeError dal punto della scrittura: la run moriva, l'esito della cella appena eseguita andava perso, e i suoi artefatti restavano su disco senza alcuna riga che li indicasse. Ora la serializzazione ha il proprio guard e produce una riga `failed` il cui errore nomina il problema di serializzazione, esattamente come per un'eccezione sollevata: la cella fallisce da sola e la matrice prosegue.

**F4, un cell id con separatore di path scriveva fuori da artifact_root.** L'id nomina la directory del tentativo, quindi un id come `../..` non e' un nome ma un percorso: risale fuori dalla radice, e un id assoluto la scarta del tutto portandosi via il namespace dell'esperimento. Rifiutato in `_check_cell_ids`, prima di qualunque connessione al database: il test verifica infatti che `os.listdir(tmp_path) == []`, cioe' che il rifiuto preceda anche la creazione del file db.

**F9a, una cella senza 'id' sollevava un KeyError nudo.** Stessa funzione, stesso momento: ora il rifiuto dice che l'id e' cio' che indirizza la riga nel database e che senza non esiste resume.

**F5, il rimedio falso sopravviveva ai conflitti misti.** C3 aveva gia' soppresso il suggerimento di aprire un nuovo `experiment` quando tutti i conflitti erano legacy. Restava scoperto il caso misto: un conflitto di mismatch e uno legacy insieme facevano ricadere nel ramo che offre la nuova identita', mandando il chiamante in un giro che finisce sullo stesso rifiuto, perche' le righe non namespaced sono visibili da ogni esperimento. Ora la soppressione scatta se anche un solo conflitto e' legacy, e il messaggio dice esplicitamente che una nuova identita' non lo risolvera'.

**F6, il report confondeva due assenze di identita' diverse.** Una riga scritta con `experiment=None` e una riga migrata da un database pre-provenance rileggono entrambe l'esperimento vuoto, ma dicono cose opposte: la prima e' una dichiarazione del chiamante, la seconda e' ignoranza genuina. `_read` non selezionava affatto la colonna `fingerprint`, quindi il discriminante era nella tabella e semplicemente non veniva letto. Ora le due rendono `(no experiment)` e `(pre-provenance)`. Nota di merito: avevo respinto la stessa segnalazione in un giro precedente, quando la review Altitude proponeva di stampare il letterale `null`. Respingere quella correzione era giusto, respingere il finding no.

**F7, schema_meta veniva creata prima di una migrazione che poteva rifiutarsi.** Il DDL autocommitta, quindi la CREATE sopravviveva al rollback della migrazione e un database che il runner rifiuta di migrare guadagnava comunque una tabella che solo il runner nuovo capisce. Entrambe le tabelle ausiliarie sono ora create dopo la migrazione, e `_stored_version` tollera l'assenza di schema_meta invece di presupporla.

**F8, la colonna status non era escapata nel report.** E' l'unica colonna che il chiamante non fornisce, quindi la piu' facile da dare per sicura. Non lo e': `_read` rende deliberatamente tabelle results che questo runner non ha scritto, e una di quelle puo' contenere qualsiasi cosa. Ora passa da `_text` come le altre.

**F9b, il controllo delle chiavi coercibili girava dopo il dump.** Una mappatura con chiavi di tipo misto fa sollevare a `sort_keys` un TypeError suo, quindi il chiamante si sentiva dire che la definizione non e' serializzabile invece di quale chiave due celle finirebbero per condividere. `_reject_coerced_keys` ora precede il dump.

**F9c saltato, con motivo.** La review chiedeva un tipo di eccezione dedicato per un database privo della tabella results in report.py. Il `sqlite3.OperationalError: no such table: results` grezzo nomina gia' esattamente la tabella mancante, e introdurre una gerarchia di errori in report.py e' piu' superficie di quanta il finding ne giustifichi.

## Batteria di mutazione estesa a 17, tutte conformi alla dichiarazione

Ogni correzione di questo giro ha una mutazione dedicata, perche' un test verde prima e dopo una correzione non prova nulla. Aggiunte M10 (serializzazione del risultato rimessa dentro la INSERT), M11 (controllo separatore tolto), M12 (soppressione del rimedio solo quando tutti i conflitti sono legacy, cioe' il bug del caso misto), M13 (status interpolato senza escaping), M14 (schema_meta creata prima della migrazione), M15 (una sola etichetta per entrambe le righe non namespaced), M16 (KeyError nudo per l'id mancante), M17 (controllo chiavi coercibili di nuovo dopo il dump). Tutte uccidono esattamente il test dichiarato.

Due mutazioni hanno smesso di applicarsi durante il giro, M4 e M5, perche' le correzioni sotto test avevano riscritto il testo che quelle mutazioni ancoravano. Sono guasti dell'harness, non test falliti, e il driver li ha segnalati rumorosamente invece di passarli in silenzio: la sostituzione che non matcha esattamente una volta e' un errore fatale. Riancorate al testo corrente e rieseguite.

Una mutazione e' un sopravvissuto documentato, non un difetto: M3b toglie l'esclusivita' della create in `_attempt_dir` lasciando il nome minted. Da quando il token e' coniato con `uuid4` invece di essere contato sondando il disco, `os.makedirs(d)` non risolve piu' nulla e puo' scattare solo se uuid4 si ripete: e' un'asserzione difensiva, non una guardia raggiungibile. Cancellare la mutazione nasconderebbe che quella riga non e' coperta; dichiararla sopravvissuta attesa lo dice. Il driver riporta comunque una "UNEXPECTED KILL" se un test dovesse dipendervi.

Esito: `/tmp/pyteman-audit-env-OOeElF/bin/python /tmp/mutate.py` -> `all mutations behaved as declared`, 17 su 17.

Suite completa dopo tutte le correzioni: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /tmp/pyteman-audit-env-OOeElF/bin/python -m pytest -q` -> `279 passed in 1.56s`. File posseduti: `tests/test_matrix.py` 2, `tests/test_matrix_identity.py` 40, `tests/test_report.py` 5.

Round di correzioni post code-review (2026-09-16, secondo giro). Sette difetti confermati corretti, ciascuno con un test di regressione e una mutazione che lo uccide.

1. Id di cella non validato come componente di percorso. Un id contenente / o \\ scriveva fuori da artifact_root e fuori dal namespace del proprio esperimento; un NUL non e nemmeno passabile al filesystem. Ora _check_cell_ids rifiuta entrambi i separatori su ogni piattaforma, perche il nome registrato sopravvive alla macchina che lo ha scritto, piu un limite di 200 byte che lascia spazio al suffisso del tentativo dentro i 255 di ext4, APFS e NTFS. Il rifiuto sta nel pre-pass e non a os.makedirs: rifiutare la' romperebbe la promessa del pre-pass, perche a quel punto celle precedenti hanno gia scritto.
2. Definizione ciclica. _canonical catturava solo (TypeError, ValueError), quindi una definizione auto-referenziale terminava la run con RecursionError invece del rifiuto per identita.
3. Risultato non serializzabile a qualunque profondita. La guardia del risultato catturava le stesse due eccezioni: un risultato annidato a fondo costava l'intera matrice invece della sola cella. Verificato empiricamente che l'encoder C misura lo stack residuo e non sys.getrecursionlimit(): 20000 livelli passano, 100000 danno RecursionError.
4. artifact_root registrato come lo scriveva il chiamante. Un percorso relativo rendeva la riga leggibile solo da chi avesse la stessa cwd. Ora abspath prima dell'uso.
5. PERDITA DATI. Un passo per una cella senza riga memorizzata ereditava source dallo stratum legacy: una run con nome cancellava cosi la riga experiment=None omonima, e _lookup(legacy_only=True) filtra fingerprint IS NULL, quindi non la vedeva mai per segnalarla come conflitto. Ora il passo porta experiment_key.
6. INSERT con lista colonne esplicita da _RESULT_COLUMNS, un solo punto di definizione: INSERT ... SELECT con arieta coincidente e la forma che perde dati in silenzio.
7. report.py etichettava allo stesso modo due righe diverse. _experiment_label usa ora fingerprint is None, lo stesso discriminante del runner.

Altro: _check_duplicate_ids scorporato (unico controllo sull'insieme); _changed_keys collassato; _plan ristrutturato con il commento sul perche ogni ramo sceglie quel source; docstring di run_matrix corretta sulla relazione fra experiment=None e righe migrate; sezione README Runner and sqlitekit allineata, nessun'altra sezione toccata.

Verifica finale del giro, comandi rieseguiti adesso e non citati da esecuzioni precedenti.

Suite completa: PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /tmp/pyteman-audit-env-OOeElF/bin/python -m pytest -q -> 284 passed in 8.16s. Erano 279 prima di questo giro: cinque test nuovi, uno cancellato, uno aggiunto in coda.

Batteria di mutazione, ora 24 mutazioni: /tmp/pyteman-audit-env-OOeElF/bin/python /tmp/mutate.py -> all mutations behaved as declared. Nuove in questo giro M11b (solo il separatore locale rifiutato, come lo riporta os.sep), M18 (limite di lunghezza tolto), M19 (guardia del risultato ristretta a TypeError e ValueError), M20 (abspath tolto), M21 (il passo senza riga memorizzata eredita lo stratum legacy), M22 (guardia canonica ristretta), M23 (rifiuto preciso delle chiavi ri-avvolto in quello generico). Unico sopravvissuto e M3b, documentato: toglie l'esclusivita della create in _attempt_dir lasciando il nome coniato con uuid4, che e un'asserzione difensiva non raggiungibile.

M23 merita una nota perche ha trovato qualcosa che le review non avevano visto. MatrixIdentityError deriva da RuntimeError, quindi un except Exception la cattura, e la clausola except MatrixIdentityError: raise dentro _canonical esiste per lasciar passare il rifiuto preciso prima del wrapper generico. Cancellandola i due test sulle chiavi restavano verdi lo stesso, perche il messaggio generico interpola {exc!r} e il repr dell'errore avvolto contiene ancora la sottostringa che i test cercavano. Un'asserzione di sottostringa non distingue un rifiuto da quello stesso rifiuto annidato di un livello. Corretto asserendo anche l'assenza del messaggio generico: con quella riga M23 uccide entrambi i test.

Raccomandazioni di questo giro depositate nel tracker nello stesso turno in cui sono state lette: TASK-42 AC5-AC7 (predicato pre-provenance duplicato fra report.py e matrix.py, sentinella dello stratum riscritta a mano in report.py, decisione su schema_meta contro lo sniffing della forma), TASK-43 AC5 (_check_duplicate_ids ora scorporato e pronto per l'unificazione con rules.py), TASK-45 AC4 (LEGACY_SCHEMA e legacy_db da promuovere a conftest quando il lavoro concorrente su tests/ e chiuso), TASK-50 nuovo (RUN-07, lo stratum non namespacizzato confonde riga deliberata e riga migrata, con il percorso di perdita dati gia toccato una volta descritto per intero).

Stato lasciato In Progress in attesa di APPROVED del parent.

Correzione della nota precedente: il task nuovo e TASK-50 con prefisso RUN-10, non RUN-07. RUN-07 era gia occupato da TASK-44 (strumenti espliciti per lo strato legacy) e RUN-08/RUN-09 da TASK-48/TASK-49. TASK-44 non e duplicato da TASK-50 ma ne dipende: il suo AC2 elenca le righe dello stratum non namespacizzato, e senza la distinzione di TASK-50 quell'elenco mescolerebbe le righe deliberate con le migrate, e l'adozione in blocco del suo AC3 timbrerebbe un'identita sopra una dichiarazione esplicita del chiamante. Riferimento incrociato aggiunto come AC5 di TASK-44.

Richiesta parent (secondo giro CHANGES REQUESTED, 2026-09-16). Il parent ha verificato in proprio i 50 test runner/report, la separazione namespace+artifact/report, il ciclo A/B/A/B con 4 directory e contenuti preservati, e il fingerprint coerente con la definizione congelata. Resta un blocco circoscritto, oggi in TASK-49: due callback interrotti con KeyboardInterrupt prima del rimpiazzo producono 2 righe results_superseded pur con 0 supersessioni completate e la riga viva A invariata. Il parent lo classifica come difetto della nuova scrittura di archivio, non richiedente lease/claim concorrente e non escluso dal vincolo di scope RUN-04. Fix minimo richiesto dentro TASK-19: per action=='run' rinviare _archive alla stessa transazione di INSERT/rimozione legacy, dopo callback e serializzazione; mantenere archive+UPDATE atomici per adopt; nessuna transazione DB tenuta aperta sul callback. Test di ripetizione delle interruzioni: 0 nuove righe di archivio prima del replacement, 1 dopo un successivo replacement riuscito, nessuna perdita di storico. TASK-49 va aggiornata conservando solo il lifecycle delle directory interrotte e gli altri residui fuori scope, senza retro-deduplicare i dati. I follow-up architetturali TASK-42..45/48/50 restano opzionali e non bloccanti.

Gate ripetuti sullo stato finale dopo la correzione della transazione di archiviazione.

`/simplify` ha prodotto sei rilievi. Applicati: la duplicazione del commento fra `_adopt_stored_rows` e il punto di `_archive` nel ciclo (la copia nella docstring documentava codice non piu presente li), la clausola che dichiara perche la guardia della DELETE legacy e piu stretta di quella dell'archiviazione invece che indipendente da essa, l'estrazione della callback di interruzione duplicata alla lettera in due test, e l'asserzione mancante sulla lista `calls` del nuovo test. Non applicato e tracciato come TASK-51: la classe di un passo si rilegge dal testo del motivo di archiviazione invece che da `_Step.action`; e un rischio di manutenzione, non di comportamento, e la ristrutturazione eccede il perimetro minimo chiesto per questo round. Scartato il rilievo sul commit vuoto di `_adopt_stored_rows`, giudicato debole dal simplifier stesso.

La code review (Opus, effort alto) ha confermato tutte e sei le invarianti della correzione, incluse la non detenzione di transazioni attraverso la callback e l'ordine di lettura dell'archivio sui tre percorsi, e ha riportato un rilievo: il nuovo test non distingueva la correzione applicata da una forma piu debole che archivia al momento del piano e rinvia soltanto il commit. Quella forma lascia lo stato del database identico, quindi nessuna asserzione sulle righe puo separarle; cio che non puo fare e lasciar scrivere qualcun altro, perche terrebbe l'unico slot di scrittura per tutta la durata di `run_cell`. Aggiunta quindi alla callback di interruzione una sonda che apre una seconda connessione con timeout breve e pretende di riuscire a scrivere, sollevando `WriterSlotHeld` (derivata da `BaseException`, altrimenti la guardia per cella del runner la trasformerebbe nel fallimento della cella). Il potere discriminante della sonda e dimostrato dalla nuova mutazione M25, che riproduce esattamente quella forma debole: uccisa con `database is locked`.

Corretta infine la riga della docstring di `run_matrix` su `rerun`, che descriveva ancora l'ordinamento precedente.

Prove: file di competenza `51 passed`; suite intera `290 passed`; batteria di mutazioni a 25 voci `all mutations behaved as declared`, con M24 e M25 entrambe uccise dai due test di interruzione. Stato congelato per la verifica finale.

2026-09-16, APPROVED finale dall'orchestrator. Verifica indipendente eseguita sullo stato congelato: 51 test runner e report passati, suite completa 290 passed, diff-check pulito. Sonda indipendente sul difetto di archiviazione: due KeyboardInterrupt lasciano viva la riga A e zero righe di archivio; la callback riesce a scrivere da una seconda connessione, quindi nessun writer lock e tenuto attraverso il callback; il successivo B riuscito produce esattamente una riga di archivio per A. TASK-49 giudicato ridimensionato correttamente.

2026-09-16, gate di completamento rieseguiti sullo stato finale prima della chiusura, perche il taglio di contesto aveva reso non piu verificabile nella trascrizione il passaggio /simplify precedente. Il gate controlla l'evidenza e non la promessa, quindi e stato rifatto invece che aggirato.

Esiti misurati in questo giro: test dei file di competenza 51 passed; suite completa 290 passed; batteria di mutazione a 25 voci 'all mutations behaved as declared', con M24 e M25 entrambe uccise dai due test di interruzione.

/simplify rieseguito con quattro reviewer indipendenti in sola lettura. Efficiency ha dichiarato il diff pulito senza rilievi classificabili, avendo anche misurato l'unica alternativa sospetta (str.translate contro le replace concatenate in _text: la forma attuale risulta circa due volte piu veloce, quindi confermata). Reuse, Simplification e Altitude hanno prodotto sedici rilievi, nessuno dei quali un difetto di comportamento.

Nessun rilievo e stato applicato al codice. Ragione: lo stato era congelato e gia verificato dall'orchestrator, e una modifica anche cosmetica dopo l'approvazione avrebbe invalidato quella verifica senza che nulla lo segnalasse. Tutti i rilievi sono stati depositati nel tracker nello stesso turno in cui sono stati letti.

Destinazioni: predicato pre-provenance duplicato fra matrix.py e report.py, gia coperto da TASK-42 AC5 e AC6 e da TASK-50 AC2; rilevazione duplicati doppia con rules.py, gia coperta da TASK-43 AC2 e AC5, quindi la promessa di sollevamento scritta nel commento a _check_duplicate_ids ha effettivamente un proprietario; allargamento del perimetro di TASK-51, che era formulato su una sola codifica implicita mentre le codifiche sono tre, piu il verdetto sull'asimmetria adozione e supersessione; opzione nuova e smontaggio della ragione della conflazione su TASK-50; tre task nuovi, TASK-52 (RUN-12, il limite di lunghezza di un id non e derivato dal formato del nome che deve contenerlo), TASK-53 (RUN-13, ripuliture di matrix.py) e TASK-54 (RUN-14, duplicazioni nei test nuovi).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
RUN-01 lega il resume all'identita di cio che ha prodotto una riga, non al solo id della cella.

**Meccanismo.** Ogni cella porta un fingerprint SHA-256 della propria definizione serializzata canonicamente (`sort_keys=True`, separatori compatti), e ogni run porta un'identita `experiment` esplicita e obbligatoria, conservata come JSON canonico leggibile invece che hashata, perche per l'esperimento non esiste una seconda copia ispezionabile nel database. La tabella `results` ha PRIMARY KEY (experiment, cell_id) e uno schema versionato v1 verso v2, migrato in posto alla prima apertura dentro un BEGIN esplicito che rende applicabile il DDL transazionale di SQLite: un'interruzione a meta migrazione lascia il database esattamente com'era, non una forma che si presenta come corrente nascondendo ogni riga storica. Una cella viene saltata solo se la riga memorizzata porta il fingerprint della definizione sottomessa sotto la stessa identita; altrimenti `on_mismatch` e `on_legacy` (`error` di default, piu `rerun` e, per il solo legacy, `adopt`) decidono esplicitamente, e nessuna riga registrata come done viene soppiantata senza che una policy lo dica.

**Provenienza e prove.** Ogni tentativo scrive in una directory propria, `<artifact_root>/exp-<digest>/<cell_id>.<prefisso fingerprint>.<token coniato>`, quindi due esperimenti che condividono la radice non si sovrascrivono, una definizione che ritorna dopo essere stata soppiantata non riusa la directory che una riga archiviata indica ancora, e una run successiva a un `rmtree` della radice non rinomina se stessa sopra una directory archiviata, perche il token e coniato e non letto dal disco. Le righe soppiantate sono copiate in `results_superseded`, mai cancellate senza rimpiazzo. `run_cell` riceve la definizione ricongelata dal testo canonico che il fingerprint attesta, non l'oggetto del chiamante: cio che il callback fa a quell'oggetto non puo cambiare ne cio che la run registra, ne come vengono eseguite le altre celle della matrice.

**Ordine delle scritture.** La copia d'archivio di una supersessione e scritta nella stessa transazione che installa il rimpiazzo, dopo il callback e dopo la serializzazione, e prima sia della INSERT sia della DELETE legacy perche legge la riga che quelle spostano. Una riga di archivio afferma che una supersessione e avvenuta, non che era stata pianificata: un'interruzione prima di quel punto lascia la riga viva e non archiviata, che e cio che e realmente accaduto, e un ritentativo archivia una volta sola quando finalmente riesce. L'adozione fa eccezione deliberata e mantiene archive e UPDATE atomici nella transazione pre-run, perche non ha un passo successivo che possa fallire. Nessuna transazione resta aperta attraverso il callback, proprieta non solo asserita ma vincolata: la callback di interruzione apre una seconda connessione con timeout breve e pretende di riuscire a scrivere.

**Perimetro.** Corretti in tre giri di review 7 piu 9 piu 7 difetti confermati, fra cui una perdita di dati (una run con nome cancellava la riga `experiment=None` omonima senza mai vederla come conflitto), la non atomicita della migrazione, la collisione dei fingerprint sulle chiavi non stringa, gli id di cella non validati come componenti di percorso, e la misattribuzione nel report fra una riga scritta con `experiment=None` (dichiarazione) e una riga migrata (ignoranza).

**Prove finali, rieseguite sullo stato consegnato.** File di competenza `51 passed`; suite completa `290 passed`; batteria di mutazione a 25 voci `all mutations behaved as declared`, con un solo sopravvissuto dichiarato (M3b, un'asserzione difensiva non raggiungibile). Ogni correzione ha una mutazione che reintroduce il difetto e uccide il test dichiarato: un test verde prima e dopo una correzione non prova nulla. In particolare M25 modella la forma debole indistinguibile dallo stato del database (archivio al tempo del piano con il solo commit differito) e muore sulla sonda del writer slot, non su un'asserzione di stato. Verifica indipendente dell'orchestrator: 51 test runner e report, suite 290, diff-check pulito, sonda sulle interruzioni conforme. APPROVED il 2026-09-16.

**File modificati**, tutti entro la ownership assegnata: `src/pyteman/runner/matrix.py`, `src/pyteman/runner/report.py`, `tests/test_matrix.py`, `tests/test_matrix_identity.py` (nuovo), `tests/test_report.py` (nuovo), e la sola sezione README "Runner and sqlitekit". Follow-up non bloccanti depositati nel tracker: TASK-42, TASK-43, TASK-44, TASK-45, TASK-48, TASK-49, TASK-50, TASK-51 (RUN-11), TASK-52 (RUN-12), TASK-53 (RUN-13), TASK-54 (RUN-14).
<!-- SECTION:FINAL_SUMMARY:END -->
