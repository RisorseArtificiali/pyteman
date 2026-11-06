---
id: TASK-20
title: RUN-02. Confinare gli artefatti nella radice assegnata
status: To Do
assignee:
  - '@opus-5-run02'
created_date: '2026-09-16 12:20'
updated_date: '2026-09-28 18:16'
labels:
  - audit-2026-09-16
  - opus-5
  - run
  - confirmed
milestone: m-3
dependencies:
  - TASK-19
references:
  - 'src/pyteman/runner/matrix.py:27-28'
documentation:
  - doc-1
  - doc-2
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P1, CONFIRMED, aperto.

**File:** `src/pyteman/runner/matrix.py:27-28`.

**Evidenza:** id `../escape` consegna al callback una directory esterna ad artifact_root. os.path.join accetta anche path assoluti; il runner usa id senza validazione. Non si assume input ostile: anche un id costruito da parametri può scrivere fuori dall'area del test.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 `../`, path assoluti, separatori, id vuoto, Unicode e collisioni di sanitizzazione.
- [ ] #2 Il callback non riceve mai un path fuori root; verificare anche un symlink preesistente nella root secondo il modello di trust scelto.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Proposta iniziale da verificare sul codice corrente, non una correzione già applicata.

id logico separato dal nome di directory, mapping sicuro e collision-resistant; controllo di confinamento sui path risolti, con policy esplicita per symlink e id assoluti. Non eliminare o migrare artefatti esistenti senza ispezione.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: RUN-01 per identità stabile.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.

2026-09-16, riferimento incrociato da TASK-19 (RUN-01), non un claim su questo task. RUN-01 introduce una seconda dimensione di identita: run_matrix accetta ora experiment= e la tabella results ha PRIMARY KEY (experiment, cell_id). Il mapping verso la directory artefatti e rimasto os.path.join(artifact_root, cell['id']), quindi due esperimenti distinti che condividono artifact_root ricevono la stessa directory. Verificato sullo stato corrente: due chiamate con experiment={'ruleset':'aaa'} e {'ruleset':'bbb'} producono entrambe .../art/same. Non corretto in RUN-01 per non invadere il confine di questo task. Il mapping collision-resistant previsto dal piano di RUN-02 deve quindi tenere conto della coppia (experiment, cell_id), non del solo id.

2026-09-16, claim da agente Herdr implementatore (modello copilot/claude-opus-5), su indicazione dell'orchestrator dopo la chiusura di TASK-19. Ownership file dichiarata: src/pyteman/runner/matrix.py, tests/test_matrix_identity.py e i nuovi test di confinamento; src/pyteman/runner/report.py solo se necessario e previo coordinamento; README solo la sezione 'Runner and sqlitekit'. Fuori perimetro per ordine esplicito: RUN-04 e la concorrenza, e i refactor TASK-42, TASK-43, TASK-44, TASK-45, TASK-48, TASK-50, TASK-51.

Correzione della nota di riferimento incrociato del 2026-09-16 scritta durante TASK-19. Quella nota dice che il mapping verso la directory artefatti e rimasto os.path.join(artifact_root, cell['id']) e che due esperimenti che condividono artifact_root ricevono la stessa directory. Era vero quando e stata scritta, non lo e piu: RUN-01 ha chiuso quel punto nei giri successivi. Il mapping corrente e <artifact_root>/exp-<digest dell'identita>/<cell_id>.<primi 12 del fingerprint>.<token coniato per il tentativo>, con os.makedirs esclusiva, e l'isolamento fra esperimenti dalla prima run e sotto test (test_artifacts_are_isolated_between_experiments_from_the_first_run, piu la mutazione M2 che toglie il componente esperimento dal path e lo uccide). La clausola del piano di RUN-02 che chiede un mapping che tenga conto della coppia (experiment, cell_id) e quindi gia soddisfatta e non va rifatta.

Perimetro residuo, dalla lettura del codice corrente e non ancora riprodotto: quanto segue e una lettura da verificare per misura prima di qualunque correzione, come chiede la descrizione del task.

Gia atterrato in RUN-01 e da non duplicare: rifiuto di entrambi i separatori su ogni piattaforma, rifiuto del NUL, rifiuto degli id non stringa, limite di 200 byte, rifiuto della cella senza 'id', abspath di artifact_root, e namespace per esperimento. Il rifiuto dei separatori copre gia sia il letterale '../' sia gli id assoluti in forma POSIX.

Residuo apparente su AC1. Primo, l'id vuoto non e rifiutato da nessun controllo: produce un componente '.<fingerprint>.<token>', cioe un nome legale, mentre l'id vuoto non e un nome e indirizza comunque una riga. Secondo, l'id '..' da solo non contiene separatori e quindi passa la validazione: il confinamento regge, ma soltanto perche il suffisso del tentativo lo trasforma in '...<fingerprint>.<token>'. E una proprieta accidentale, non dichiarata, e appartiene alla stessa famiglia gia isolata in TASK-52 (RUN-12), dove il limite di lunghezza dipende dal formato del suffisso invece che esserne indipendente. Terzo, un id che inizia con una lettera di unita seguita da due punti resta da verificare: ntpath.join tratta un componente con drive come drive-relative e scarta la radice, quindi su Windows potrebbe uscire da artifact_root nonostante il controllo dei separatori. Coerente con la posizione gia presa dal docstring di _check_cell_ids, che rifiuta entrambi i separatori su ogni piattaforma perche il nome registrato sopravvive alla macchina che lo ha scritto.

Clausola di AC1 che risulta invece gia chiusa e da non trattare come lavoro: le collisioni di sanitizzazione e quelle di normalizzazione Unicode non possono piu causare sovrascrittura, perche il nome della directory termina con un token coniato per il singolo tentativo e due tentativi non condividono mai una foglia, qualunque sia la normalizzazione o la case-sensitivity del filesystem. Da confermare per misura, non da assumere.

AC2 e il vero residuo e non ha alcuna copertura. Non esiste in nessun punto un controllo di confinamento sul path risolto: _check_cell_ids valida il nome, e un controllo sul nome non puo vedere un symlink. Se artifact_root o la directory exp-<digest> al suo interno sono un symlink preesistente, os.makedirs lo segue e il callback riceve una directory fuori dalla radice assegnata, che e esattamente cio che AC2 vieta. Serve quindi il modello di trust esplicito che il piano chiede piu un controllo sul path risolto, e la scelta fra rifiutare il symlink e accettarlo come delega deliberata dell'operatore va dichiarata invece che lasciata implicita al comportamento di makedirs.

Prossimo passo: riproduzione per misura di ciascun punto sopra sullo stato corrente, prima di scrivere qualunque correzione.

## Gate review high-effort sullo stato finale (RUN-02)

Nessun difetto di correttezza o sicurezza nel codice di produzione ha raggiunto la soglia di segnalazione. Il reviewer ha verificato in modo esplicito, leggendo l'implementazione CPython e non per sonda: che nessun percorso raggiunge `os.makedirs` o il callback senza passare dal controllo di contenimento (tre call site: matrix.py:187 sotto la directory gia' verificata, matrix.py:242 dopo il controllo, matrix.py:659 per il parent del db che non e' un percorso di artifact); che nessun id sopravvissuto a `_check_cell_ids` evade (`..` e `.` non possono produrre traversal perche' il leaf e' sempre `{id}.{12}.{12}` e quindi non e' mai letteralmente `.` o `..`; id assoluti, prefissi UNC e separatori muoiono sul controllo `/`, `\`, NUL; `ntpath.splitdrive` copre anche la forma same-drive `C:evil`; punti e spazi finali diventano caratteri interni una volta appeso il suffisso; il cap di 200 byte piu' 26 di suffisso resta sotto 255); che `commonpath((real_root, real_d)) == real_root` e' corretto in ogni caso raggiunto, inclusi `real_root == real_d`, root `/`, e case-sensitivity (sia `posixpath.commonpath` sia `ntpath.commonpath` ricostruiscono il prefisso restituito a partire da `paths[0]`, che qui e' `real_root`, quindi l'uguaglianza non e' sconfitta dalla normalizzazione del case); e che l'ordine tiene, con il rifiuto prima del `makedirs` del parent del db e prima di `sqlite3.connect`.

Limite dichiarato dal reviewer stesso: non aveva tool Bash, quindi le sue affermazioni vengono dalla lettura del sorgente CPython e non da sonde.

### Rilievo accolto e corretto

`test_ids_a_filesystem_might_fold_together_never_share_a_directory` non discriminava la proprieta' che la sua docstring nominava. La docstring accreditava il token uuid, ma i quattro id sono quattro definizioni distinte e quindi quattro fingerprint distinti: il segmento davanti al token separa gia' le directory, e togliere il token lascia il test verde. Misurato indipendentemente dalla batteria di mutazioni prima della review: M3 (token rimosso) non uccide questo test.

Corretto riscrivendo la docstring perche' dichiari il meccanismo reale (l'id fa parte della definizione, quindi quattro grafie sono quattro fingerprint) e rimandi ai test gia' esistenti alle righe 434-455 e 481-504 per il caso che il token effettivamente risolve, due tentativi della stessa cella. Aggiunta anche la asserzione di contenimento che mancava: era l'unico test con id non-ASCII e non verificava che le directory restassero sotto la root.

### Rilievo accolto sul messaggio di rifiuto

La clausola finale del messaggio di `MatrixArtifactError` diceva "where a later run of the same matrix would not look for them", che non segue: una run successiva ricostruisce lo stesso percorso lessicale e segue lo stesso link. Il danno reale e' che l'evidenza finisce fuori dall'area che il chiamante ha riservato. Clausola sostituita con "outside the area the caller set aside for this matrix's evidence".

### Rilievi non implementati, tutti dispositionati nello stesso turno

- Nomi di device riservati Windows e caratteri illegali su Windows (`< > " | ? *`, `a:b`) passano il pre-pass, non evadono la root, ma su un host Windows alzerebbero `OSError` a meta' run. Confidenza 50, Windows-only. Fuori dal requisito di TASK-20, che e' il confinamento, e questi id sono confinati. Aperto TASK-55 nello stesso turno.
- Una run rifiutata dopo il controllo (su celle o identita') lascia `exp-<digest>/` vuota. Comportamento voluto e ora dichiarato nella docstring di `_prepare_experiment_dir`: la directory e' dentro la root che il chiamante ha nominato, che e' il punto. Non ho toccato il control flow all'ultimo gate.
- Su filesystem case-insensitive, un link dentro la root il cui target e' scritto con case diverso da `artifact_root` viene rifiutato. Fallisce in sicurezza, impatta solo la disponibilita'. Non corretto.
- Un leaf pre-piantato emerge come `FileExistsError` nudo invece che come `MatrixArtifactError`. Il leaf porta un `uuid4` fresco, quindi il ramo e' irraggiungibile da un attaccante. Non corretto.

## Cambiamenti effettivi

`src/pyteman/runner/matrix.py`: aggiunto `import ntpath`; aggiunta `MatrixArtifactError`; estratta `_experiment_dir_name`; nuova `_prepare_experiment_dir(artifact_root, experiment_key)` che risolve root e directory esperimento con `os.path.realpath` e ne verifica la relazione con `os.path.commonpath`, con guardia `ValueError` (drive Windows distinti non sono contenimento), e solo dopo chiama `os.makedirs(d, exist_ok=True)`; `_attempt_dir` ora riceve la directory gia' verificata invece della root e crea la foglia con `os.makedirs(d)` esclusiva; in `_check_cell_ids` aggiunto il rifiuto del drive specifier via `ntpath.splitdrive`, non condizionato a `os.name`; in `run_matrix` la preparazione della directory avviene prima che il db esista, cosi' una root che non puo' ospitare i tentativi fa fallire la run invece di lasciare un db le cui righe puntano fuori.

`tests/test_matrix_identity.py`: aggiunti l'helper callback `id_collecting_cell`, gli helper `experiment_dir_name`, `assert_inside` e `redirected_root`, e sei test di confinamento. `assert_inside` usa deliberatamente `startswith` su realpath e non `commonpath`: un test che riusa il predicato di produzione concorda con esso per costruzione e resterebbe verde anche se quel predicato fosse sbagliato.

`README.md`, solo il paragrafo nella sezione 'Runner and sqlitekit': regola di confinamento, forma del path, cosa viene rifiutato e quando, policy symlink, e il limite TOCTOU dichiarato.

## Comandi e perimetri dei conteggi

Ambiente: `/tmp/pyteman-audit-env-OOeElF/bin/python` (3.14.7), nessuna installazione globale.

- Suite completa: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /tmp/pyteman-audit-env-OOeElF/bin/python -m pytest -q` -> 305 passed, exit 0. Perimetro: tutti i 15 moduli sotto `tests/` (test_rules 183, test_matrix_identity 50, test_targets 20, test_sitecustomize 8, test_rule_contracts 6, test_patcher 6, test_docs_rules 6, test_actions 6, test_report 5, test_integrity 5, test_activation_atomic 4, test_matrix 2, test_barriers 2, test_kill 1, test_firing 1). Il totale e' salito da 296 perche' un altro agente aggiunge test in parallelo su moduli non miei.
- Modulo di mia proprieta': `tests/test_matrix_identity.py` da solo, 50 test, di cui 44 di TASK-19 (congelati) e 6 nuovi di TASK-20.
- Batteria di mutazioni: `/tmp/pyteman-audit-env-OOeElF/bin/python /tmp/mutate.py` -> 35 mutazioni, exit 0, 'all mutations behaved as declared'. Perimetro dei test che la batteria esegue a ogni mutazione: 3 moduli, `tests/test_matrix.py` (2) + `tests/test_matrix_identity.py` (50) + `tests/test_report.py` (5) = 57 test. La batteria lavora su una copia `rsync -a --delete` in `/tmp/pyteman-mut-VI5yaJ`, mai sull'albero reale.

## Esito della batteria

Due sopravvissuti documentati: M3b (create esclusivo sostituito da `exist_ok=True`, il nome e' unico per costruzione quindi il create esclusivo lo asserisce soltanto) e M30b (il ramo `except ValueError` di `commonpath` scatta solo fra drive Windows distinti, che nessun test su questo host puo' produrre).

Cinque dei sei test nuovi sono uccisi da almeno una mutazione: M28/M29 uccidono entrambi i test di redirezione, M30 (commonpath sostituito da `startswith`) uccide esattamente e solo il test del sibling `artevil`, M26/M27 uccidono il test del drive specifier (M27 gate sulla piattaforma e fallisce comunque su Linux, che e' il punto: l'id viaggia con la definizione), M32 (confronto asimmetrico, `abspath` della root contro `realpath` del figlio) uccide esattamente e solo il test della root symlinkata, M1 uccide il test dell'id vuoto.

Il sesto, `test_ids_a_filesystem_might_fold_together_never_share_a_directory`, sopravvive a tutte e 35 su questo host, e non e' un difetto occultato: Linux e' case-sensitive e non normalizza, quindi i quattro id restano distinti per il solo testo. La proprieta' che il test presidia diventa portante su macOS o Windows. Dichiarato qui invece di lasciar credere che il test sia coperto da mutazione.

M32 e' stata aggiunta da me dopo aver misurato che `test_an_artifact_root_that_is_itself_a_symlink_is_trusted` non era ucciso da nessuna mutazione esistente.

## Policy symlink e TOCTOU, dichiarata

La root che il chiamante nomina e' fidata anche quando e' essa stessa un symlink: parcheggiare l'evidenza su un altro disco e' una decisione operativa dell'operatore, e rifiutarla rifiuterebbe il deployment invece che un attacco. Cio' che viene rifiutato e' la redirezione che il chiamante non ha scelto, cioe' un link da dentro la root che punta fuori. Questa e' la scelta esplicita che AC2 chiedeva di dichiarare invece di lasciare implicita al comportamento di `makedirs`.

Il contenimento e' una relazione fra percorsi, non un prefisso di stringa: `/x/artevil` inizia con `/x/art` e non e' dentro di esso piu' di qualunque altra directory sul disco. Espresso come `os.path.commonpath((real_root, real_d)) == real_root`. Il test del sibling e la mutazione M30 esistono esattamente per questo.

TOCTOU esplicitamente non promesso, ne' nel codice ne' nel README. Il contratto del callback consegna un percorso, non una directory aperta: chiudere la finestra richiederebbe `os.open(root, O_DIRECTORY|O_NOFOLLOW)` piu' `mkdirat`, che quel contratto rende impossibile. Una `realpath` per tentativo non tapperebbe alcun buco e accorcerebbe soltanto la finestra, perche' il create della foglia e' gia' esclusivo: `os.makedirs(d)` senza `exist_ok` alza `FileExistsError` su una foglia occupata da un symlink invece di seguirlo. Verificato da me per sonda diretta (`FileExistsError [Errno 17] File exists`, directory bersaglio rimasta vuota) e confermato indipendentemente dal reviewer sulla semantica di `os.mkdir`. E' questo che rende sufficiente il controllo sul solo parent.

## SHA256 dello stato finale

- `src/pyteman/runner/matrix.py` 97c550558b600220f8c0b15fb7352c889fb4e2af476753e9c55de25038a8ec5e
- `tests/test_matrix_identity.py` 4251ca6f6f1f729c44a610d4178aa977b6dc8198439d6772c8abc05992da9df9
- `README.md` 94953ba194dcd77095ab86bf24934b426f76f5224e1f9dc4b3d69770a493d5f3
- `/tmp/mutate.py` (harness fuori dal repo) c90fccb9a3f92075d9dfae2181b49481b162939d4686a6cfd1cf99d4413e5cad

Nessun commit, nessun push, nessun cambio di branch, nessuna modifica a hook o config. HEAD resta a28b126. Il task resta In Progress in attesa della verifica dell'orchestrator: dopo APPROVED nessuna modifica temporanea e nessun applica/revert.

## APPROVED finale dall'orchestrator, 2026-09-16

Hash verificati prima e dopo la verifica, identici a quelli del report: matrix.py 97c55055..., test_matrix_identity.py 4251ca6f..., README.md 94953ba1... Perimetro dei 57 test passato. Suite completa misurata dall'orchestrator: 307 passed, salita ancora rispetto ai 305 del mio report perche' l'altro agente continua ad aggiungere test su moduli non miei.

Sonde indipendenti eseguite dall'orchestrator, non dalle mie: il symlink exp -> artevil e' rifiutato senza che callback, db o file compaiano fuori dalla root; una root che e' essa stessa un symlink scelto dall'operatore e' ammessa; id Unicode e `..` restano confinati; drive specifier, separatori e NUL sono rifiutati prima che il db venga toccato. Nessun finding.

Annotato per onesta' del record, riportato dall'orchestrator stesso: la sua prima sonda assumeva erroneamente che l'id vuoto fosse invalido e la sua asserzione e' fallita. Dopo aver letto il test e il contratto ha corretto la sonda, senza modificare il codice, e ha verificato che id vuoto e `..` sono confinati e resumable. L'errore era nella sonda, non nell'implementazione.

AC #1 e #2 spuntati su questa verifica. Nessuna mutazione post-approval: lo stato consegnato e' quello approvato.

Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #64. Added lines already present on master per PR: #64 8/90=8%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.
<!-- SECTION:NOTES:END -->
