---
id: TASK-22.1
title: RUN-04a. Esclusione single-runner con lock flock DB-wide
status: Done
assignee: []
created_date: '2026-09-18 06:13'
updated_date: '2026-09-18 09:30'
labels:
  - run
  - opus-5
  - audit-2026-09-16
  - confirmed
milestone: m-3
dependencies: []
parent_task_id: TASK-22
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Tranche 1 di TASK-22. Impedire che due runner concorrenti eseguano la stessa cella, con un lock advisory flock a livello di database, non bloccante, preso prima di qualunque effetto collaterale della run.

Non copre la provenienza per-tentativo, che e' TASK-22.2. Non introduce la tabella attempts ne' lo schema v3.

Contesto e misure nelle note di TASK-22: il difetto e' riprodotto su fb1cf40, e il rilascio del flock su SIGKILL e' misurato, non assunto.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Due runner concorrenti sulla stessa results db non entrano entrambi nel callback: il secondo viene rifiutato subito con un errore dedicato che nomina la db e il file di lock
- [x] #2 Il lock e' preso prima di migrazione, pianificazione, creazione della directory di experiment e callback; un runner rifiutato non lascia effetti collaterali oltre il lockfile e le sue directory parent
- [x] #3 Il percorso della db e' canonicalizzato con realpath, cosi' percorso relativo, assoluto e symlink verso la stessa db condividono lo stesso lock; gli alias per hardlink non sono rilevati e il limite e' documentato
- [x] #4 Il lockfile e' persistente: non viene mai unlinkato all'uscita, non viene troncato all'apertura, e non esiste alcuna rimozione di lock 'stale' basata su PID
- [x] #5 Il descrittore e' chiuso su qualunque uscita, compresa un'eccezione del callback e un errore di scrittura sullo storage, e il lock torna disponibile
- [x] #6 Dopo un SIGKILL del detentore un runner nuovo acquisisce il lock e completa la cella, senza intervento manuale
- [x] #7 Una seconda acquisizione dallo stesso processo fallisce rapidamente con l'errore dedicato invece di andare in deadlock
- [x] #8 fcntl e' importato lazy, quindi pyteman resta importabile dove fcntl non esiste; in sua assenza il runner rifiuta esplicitamente e non esegue mai senza protezione
- [x] #9 La policy per una db :memory: e' decisa esplicitamente e documentata, e non viene mai creato un lockfile con percorso letterale :memory:
- [x] #10 I test sono in tests/test_matrix_concurrency.py, usano processi spawn ed Event per l'ordinamento, mai sleep come prova, e ripuliscono i processi con timeout
- [x] #11 Il test di esclusione e' non vacuo: fallisce se il lock viene rimosso, e asserisce che il primo runner ha davvero completato e scritto la sua riga
- [x] #12 Il percorso sequenziale non regredisce: un run dopo l'altro sulla stessa db continua a fare skip della cella gia' done
- [x] #13 Supporto dichiarato nella documentazione: Linux su filesystem locale verificato, macOS non verificato, NFS fuori garanzia, lock advisory e vincolante solo per chi passa da run_matrix
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Review read-only mirata sulla delta delle sei findings, prima del commit. Tre reperti, nessun commit fatto.

1. IMPORTANTE, prosa del contratto falsa come scritta. matrix.py righe 770-776 e README righe 191-194 dicono 'il lock e' preso prima di ogni controllo che questa run fa' e 'nessun controllo e' fatto fuori dall'esclusione'. Falso: quattro controlli girano prima di entrare in _lock.held, cioe' le due appartenenze di on_mismatch e on_legacy, _check_cell_ids e _check_duplicate_ids. Provato con lo stesso db in una directory fresca: artifact root da NotADirectoryError e lascia results.db.lock, mentre on_mismatch invalido, on_legacy invalido, id duplicato e id inusabile danno tutti il loro errore senza creare la directory padre. La tesi sostanziale della delta, cioe' che nessun controllo sull'albero o sul db avviene fuori dall'esclusione, e' vera; e' la frase che generalizza oltre. Seconda imprecisione nella stessa frase: 'lascia il lockfile e la directory che lo contiene' e' vero solo se il padre non esisteva gia'. Con il padre preesistente una run rifiutata lascia solo il lockfile, e una seconda run rifiutata non lascia niente di nuovo. Il codice e' giusto, e' la prosa che eccede.

2. BASSO, il nuovo wrapper OSError non ha test. lock.py 91-107. Nessun test cerca 'cannot open the lock file' ne' 'cannot lock'. I due rami funzionano, verificati a mano: padre che e' un file da Errno 17, padre in sola lettura da Errno 13, entrambi riportati come MatrixLockError. E' il ramo il cui unico scopo e' convertire una classe di errore, ed e' non pinnato. Il test economico e' chmod 0o555 sulla directory padre, con lo stesso skip da root del test di storage.

3. BASSO, il child collassato inghiotte il proprio fallimento. test_matrix_concurrency.py 72-108, la guardia if out is not None sul ramo except. L'entrypoint che ha sostituito per il test SIGKILL chiamava run_matrix nudo, quindi un fallimento propagava e il child usciva diverso da zero. Adesso con out None l'eccezione viene catturata e buttata, e il child esce 0 senza diagnostica. Oggi le due assert sul victim lo prendono comunque, quindi non si perde copertura; il costo e' che una regressione futura che rompe il victim prima dello sleep si presenta come timeout invece che come testo dell'eccezione.

Verificato meccanicamente dalla review: la reindentazione e' equivalente per AST, sei statement identici nello stesso ordine, con con.close() ancora finally interno e il rilascio del lock esterno; la non vacuita' resta 12 failed su 15 senza lock con i tre sopravvissuti giusti; os.fstat contro os.stat e' un confronto di identita' valido perche' stat_result confronta la tupla a dieci campi incluso st_dev e st_ino; il ramo EACCES di flock resta raggiungibile e distinguibile; nessun descrittore puo' sfuggire da acquire.

Nota su un cambio di comportamento deliberato che la review segnala: un results_db con un path impossibile adesso da MatrixLockError invece di NotADirectoryError, ed e' coperto dalla docstring di acquire.

Commit locale eseguito: 8d2e42d9ace03b010f716aeefaf236453676126a su work/concurrency-safety, parent fb1cf409. Quattro file, 831 insertions 108 deletions. Blob nel commit: 1f5af05 lock.py, 3565e63 matrix.py, a06be8e test_matrix_concurrency.py, a8479f6 README.md, uguali a git hash-object dei candidati. Indice vuoto dopo il commit; manifest dell'intero working tree identico a prima dello stage (355 file), quindi il working tree resta ai byte vecchi per scelta e i tre file di CON-01 sono intatti. Backup pre-commit dei quattro path condivisi piu' manifest in ~/pyteman-evidence/precommit-1789716xxx (percorso in ~/pyteman-evidence/precommit-final.path). Patch canonica: ~/pyteman-evidence/patchgen-final-1789715437/candidate.patch.

Verifiche prima del commit. Review delta read-only finale ha refutato una frase del README: 'may therefore leave the lock file and that directory behind, and leaves nothing else' era falsa, perche' una run che fallisce dopo la presa del lock lascia anche artifact root, directory esperimento, directory tentativo e results db. Corretta in posto: i due elementi sono ora dichiarati come il totale di cio' che il lock ha aggiunto, con esplicito che una run che fallisce piu' tardi lascia il resto come prima. Seconda correzione: le asserzioni aggiunte al test leave-behind confrontavano solo i nomi; ora confrontano inode, mode e size dei figli piu' inode e mode della directory, e la mutazione che cancella e ricrea il lockfile fa fallire la forma nuova mentre la vecchia passava. Suite: modulo 17 passed, candidato intero 805 passed 1 skipped, rebuild senza lock 14 failed 3 passed con superstiti control arm, path types, sequential resume.

Avvertenza operativa. Dal commit in poi i quattro path risultano modificati nel working tree, perche' il commit porta i byte nuovi e il working tree conserva quelli vecchi per congelamento voluto. Un commit -a o un add di quei path reintrodurrebbe la versione senza lock: la riconciliazione del working tree va fatta esplicitamente con un checkout mirato dei quattro path quando il parent lo autorizza. Push non eseguito; il branch traccia origin/master, quindi il push dovra' essere esplicito git push -u origin work/concurrency-safety.

CI proof cross-reference, 2026-09-18, verified independently (gh run view/gh pr view/git ls-remote): CI run 35329055954 on commit e91b65f05db42929beb7662dcb213561d1fd7a02 (branch work/concurrency-safety, PR #2) is all 6 jobs green, and this run covers the full reconciled chain 8d2e42d -> 5c329c3 -> e91b65f, so it reconfirms this task's own commit 8d2e42d unchanged inside that chain. Full CI detail and the depth-64 correction that produced e91b65f are recorded on TASK-13, whose ownership scope (patcher.py, tests/test_firing_concurrency.py, docs/rules.md) covers that commit; this task's scope (lock.py, matrix.py, test_matrix_concurrency.py, README.md) is untouched by it. No status change here; this task remains Done as already recorded. PR #2 stays frozen, no merge authorized.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Esclusione single runner per results db, con lock advisory flock a livello di database, non bloccante.

Commit 8d2e42d9ace03b010f716aeefaf236453676126a su work/concurrency-safety, parent fb1cf409, quattro file, 831 insertions 108 deletions. Blob verificati uguali ai candidati: 1f5af05 src/pyteman/runner/lock.py, 3565e63 src/pyteman/runner/matrix.py, a06be8e tests/test_matrix_concurrency.py, a8479f6 README.md.

Cosa cambia. run_matrix tiene un flock su <results_db>.lock da prima di leggere o toccare qualunque cosa fuori dai propri argomenti fino al ritorno, e un secondo runner che trova il lock occupato riceve subito MatrixLockError invece di aspettare. Il lock e' a livello di database e non per esperimento, perche' lo strato legacy non namespaced e' visibile a ogni esperimento ed e' mutato da on_legacy. Sta nel filesystem e non in tabella perche' il kernel lo rilascia quando muore il detentore, misurato con SIGKILL, quindi un runner ucciso non lascia niente da recuperare.

Limiti dichiarati, misurati e non assunti: verificato su Linux con filesystem locale, macOS non verificato, flock su NFS fuori garanzia, piattaforma senza fcntl rifiutata invece che eseguita senza protezione; lock advisory, quindi vincola chi passa da run_matrix e non chi scrive la db per conto proprio; chiave sul path canonico, quindi relativo, assoluto e symlink contendono mentre due hardlink no; un run_cell che forka un figlio che sopravvive alla run tiene il lock, perche' il figlio eredita la open file description, mentre un figlio che fa exec no; ":memory:" e "" rifiutati perche' nessuna run successiva puo' riprenderli.

Prove. Suite intera 805 passed 1 skipped. Il nuovo modulo sono 17 test che guidano processi reali ordinati con Event e mai con sleep. Non vacuita' misurata ricostruendo il pacchetto senza lock in un venv separato con il suo editable install: 14 dei 17 falliscono e i 3 verdi sono il braccio di controllo, il test sui tipi di path e il resume sequenziale.

Due difetti trovati dai gate e corretti prima del commit, nessuno dei due visibile da una suite verde: una frase di contratto nel README che prometteva piu' di quanto il codice faccia, cioe' che una run fallita non lasci nient'altro oltre lockfile e directory, smentita da una run che fallisce dopo la presa del lock e lascia anche artifact root, directory esperimento e results db; e due asserzioni che confrontavano il contenuto di una directory per soli nomi, ora per inode, mode e size, con mutation check che mostra la forma nuova rossa e la vecchia verde sulla stessa mutazione.

Il working tree condiviso resta volutamente ai byte precedenti: il commit e' stato costruito index only con git apply --cached da una patch canonica generata su export fresco. Riconciliare il working tree richiede un checkout mirato dei quattro path. Push non ancora eseguito.
<!-- SECTION:FINAL_SUMMARY:END -->
