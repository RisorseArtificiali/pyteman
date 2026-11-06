---
id: TASK-32
title: PKG-01. Includere una suite eseguibile e i documenti referenziati nella sdist
status: Done
assignee:
  - '@opus-5-pkg01'
created_date: '2026-09-16 12:20'
updated_date: '2026-09-17 03:59'
labels:
  - audit-2026-09-16
  - opus-5
  - pkg
  - confirmed
milestone: m-5
dependencies: []
references:
  - 'pyproject.toml:27-35'
  - tests/conftest.py
  - tests/target_mod.py
  - 'README.md:53,110'
documentation:
  - doc-1
  - doc-2
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P2, CONFIRMED su artefatto costruito, aperto.

**File:** `pyproject.toml:27-35`, `tests/conftest.py`, `tests/target_mod.py`, `README.md:53,110`.

**Evidenza:** la sdist contiene `tests/test_*.py` ma omette `tests/conftest.py` e `tests/target_mod.py`; pytest dalla sdist termina con `ModuleNotFoundError: No module named 'target_mod'`. Mancano anche `docs/targeting.md` e gli esempi citati dalla documentazione. Wheel con modulo di attivazione annidato e `py.typed` invece corretti.

**Riproduzione sullo stato corrente (2026-09-17).** L'evidenza regge e il quadro misurato è più ampio di quello registrato. La sdist ometteva anche `tests/integrity_corpus.py`, e non conteneva `docs/` affatto, quindi nessuno dei tre documenti. La suite eseguita dall'archivio estratto dava cinque errori di collection: tre `ModuleNotFoundError: No module named 'integrity_corpus'`, un `ModuleNotFoundError: No module named 'target_mod'`, un `FileNotFoundError` su `docs/rules.md`.

**Meccanismo, misurato e non dedotto.** Il difetto non è in `pyproject.toml`. In assenza di `MANIFEST.in` setuptools ricade su un default ereditato da distutils, il glob opzionale `tests/test*.py`, che prende `test_*.py` e nient'altro. Non esiste alcun entry point `setuptools.file_finders` installato e git non partecipa alla selezione. L'inclusione che funzionava era quindi un effetto collaterale di un default, non una scelta.

**Correzione della giustificazione sugli esempi (misurata 2026-09-17).** L'evidenza sopra attribuisce l'inclusione degli esempi a citazioni nella documentazione. Verificato sullo stato corrente: né `README.md` né alcun file sotto `docs/` cita `examples/` per path. Gli esempi entrano nella sdist perché sono sorgente del progetto, una distribuzione sorgente di un toolkit di fault injection che omette i suoi guasti lavorati è incompleta, non perché un documento li referenzi. La giustificazione scritta in `MANIFEST.in` è questa. Inclusione confermata dal parent come parte esplicita del piano PKG-01.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 estrarre la sdist in directory nuova, installarla in ambiente isolato e lanciare la suite da lì; collection e test passano senza import dal checkout originale.
- [x] #2 Link/documenti del README distribuito risolvibili o URL assoluti verificati.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Proposta iniziale da verificare sul codice corrente, non una correzione già applicata.

manifest esplicito per test completi, documentazione ed esempi pertinenti; non installare i test nel namespace runtime e non spostare `sitecustomize.py` top-level. Verificare l'artefatto finale, non soltanto il checkout.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: nessuna.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.

## Implementazione (2026-09-17)

Tre file, tutti nuovi. `pyproject.toml` lasciato byte-identical a HEAD per istruzione esplicita del parent: `MANIFEST.in` da solo e' sufficiente, misurato. Nessun backup necessario perche' nessuna modifica.

- `MANIFEST.in` sha256 c69612faac49a0a570bf531d28cb74fda888fc9fecce766a7d7acea140fda337
- `tests/test_packaging.py` sha256 14bfcab9076d088bd7568ba39d5066e42c6604dd2e251cef3b55b3d11b9a9ba1
- `docs/packaging.md` sha256 f2d0eab97896a70722f5fbbaa35782e72b2117186b066ccb69323754c62abf8b
- `pyproject.toml` sha256 f7dcdd5518af1ee416013b27f7eef20a49688d5ec847c75a383be4e04ff0edab, invariato

Le concessioni in `MANIFEST.in` sono per directory (`recursive-include tests *`) e non per estensione. Motivo misurato: una concessione filtrata per suffisso, difesa da un test che deriva l'attesa con lo stesso predicato, nasconde un fixture non-.py da entrambi i lati insieme. Con `recursive-include tests *.py` e un `tests/fixtures.json` aggiunto, il vecchio predicato (sottoinsieme, solo .py) riporta PASS su un archivio che non contiene il file, mentre l'uguaglianza non filtrata FALLISCE nominandolo.

Contropartita: cio' che sta in una directory concessa viene spedito, quindi `global-exclude` e i `prune` sono portanti. Verificato inoltre che i `prune` non rimuovono nulla oggi (lista file byte-identica con e senza), perche' nessuna concessione arriva a quelle directory; restano contro un allargamento futuro.

## Verifiche eseguite, tutte offline

Suite completa nel checkout: 713 passed. Il perimetro mio e' `tests/test_packaging.py`, 15 test; gli altri 698 appartengono al resto della suite, inclusi test di un agente concorrente che li sta modificando.

AC1, camera pulita: sdist e wheel costruiti da una copia che esclude `.git`, `*.egg-info`, `build`, `dist`; venv senza editable install; `pip install --no-index --no-deps --no-build-isolation`; suite lanciata dall'archivio estratto. Risultato 706 passed, 7 skipped, totale 713 identico al checkout, quindi l'archivio trasporta la suite completa senza omissioni. `pyteman.__file__` dentro il venv, nessun path del checkout in `sys.path`. I 7 skip sono i controlli sugli artefatti, ciascuno con motivo stampato.

Artefatti reali ispezionati direttamente: sdist 64 file (6 root, 20 src, 23 tests, 4 docs, 11 examples), assenti `backlog/`, `.claude/`, `.pytest_cache/`, `.github/`, nessun `.pyc` o `.so`. Wheel 20 file, solo `pyteman/` e `dist-info`, `sitecustomize.py` annidato e mai top-level, `py.typed` presente, zero test/doc/esempi.

## Mutation check, la meta' rossa

- senza `MANIFEST.in`: 3 failed, 12 passed, uno per directory concessa
- manifest filtrato per estensione piu' `tests/fixtures.json`: 1 failed che nomina il file
- riga `global-exclude` rimossa: 2 failed, il controllo residui piu' l'uguaglianza che intercetta i file piantati come sovra-inclusione
- interprete senza setuptools: 1 failed che nomina l'interprete. Prima della correzione era 8 passed, 7 skipped, verde

## Fuori perimetro, tracciato

TASK-108 (la release pubblica un artefatto che i controlli non hanno mai misurato) e TASK-109 (la sdist spedisce la suite ma non ne dichiara i requisiti), entrambi verificati leggendo i file.

Nota per chi possiede il tracker: il commit dcabe5e cita TASK-108 per lavoro su targets che non ha alcun file task. Nessuna collisione su disco, ma l'identificatore si legge in due modi nella storia.

## Seconda review high e correzioni (2026-09-17)

La re-review ha confermato risolte tutte le correzioni del giro precedente (C1, C2, I1, I3, I4, I5, M1, M2, M3) riproducendo ciascuno scenario, e ha aperto tre punti nuovi. Tutti e tre chiusi qui, piu' uno trovato da me eseguendo la documentazione.

**I2 residuo, `docs/packaging.md`.** Un paragrafo diceva ancora che le righe `prune` sono load-bearing, in contraddizione con la sezione piu' avanti nello stesso documento che dice correttamente il contrario. Riscritto: load-bearing e' soltanto `global-exclude`, i `prune` sono tenuti contro una concessione futura allargata verso la radice.

**R1, buco nella guardia.** Il return anticipato scattava su `not LOOKS_LIKE_A_CHECKOUT` da solo, ma il commento lo giustificava con una condizione diversa. Un albero sorgente spogliato dei dot-entry (build in container con `.dockerignore` che scarta i dotfile) prendeva quell'uscita pur avendo tutto per costruire. Ora servono entrambe le condizioni. Misurato su una copia con `.github`, `.gitignore` e `backlog` rimossi, senza `PKG-INFO`, interprete senza setuptools: con la guardia vecchia 9 passed, 7 skipped, verde; con quella nuova fallisce nominando l'interprete. Verificato che in quell'albero i tre flag valgono False, quindi lo scenario e' davvero quello e non la ripetizione di C2.

**R2, obbligo di sincronizzazione senza controllo.** `PLANTED_RESIDUE` doveva tenere un nome per ogni pattern di `global-exclude`, e nulla lo imponeva: un nono pattern aggiunto al manifest non sarebbe mai stato esercitato e il controllo residui si sarebbe ristretto in silenzio. E' la stessa forma del difetto originale un livello sopra. Ora `test_every_excluded_pattern_is_exercised_by_a_planted_file` legge la riga da `MANIFEST.in` e verifica in fnmatch che ogni pattern abbia un file piantato. Misurato aggiungendo `*.bak` al manifest di una copia: 1 failed, 15 passed, che nomina `['*.bak']`.

**Superficie di falso positivo sulla wheel**, segnalata dalla review a confidenza 75 e non difetto oggi: un sottopacchetto `pyteman/examples/` deliberato fallirebbe. Non cambio il predicato, che e' il compromesso giusto, ma il messaggio ora distingue i due casi e dice cosa fare.

**Aggiunta mia, lato radice.** Il controllo top level era solo sottoinsieme: un file di radice che smette di essere spedito non lo notava nessuno. Aggiunta l'asserzione opposta sui quattro file che `MANIFEST.in` nomina. Deliberatamente non uguaglianza sull'insieme intero: `PKG-INFO` e `setup.cfg` li scrive il backend, non il manifest, e pretenderli farebbe riportare un errore di manifest il giorno in cui una release di setuptools smettesse di emetterne uno.

**Difetto nella documentazione trovato eseguendola.** La ricetta di installazione falliva: `BackendUnavailable: Cannot import 'setuptools.build_meta'`. pip chiama l'hook di metadata del backend anche con `--no-build-isolation`, quindi il venv di installazione ha bisogno di setuptools, non solo l'interprete che costruisce. Il documento diceva la seconda cosa e non la prima, e il comando usava un `python` nudo che sulla macchina risolve all'interprete senza setuptools. Corretto con la spiegazione e l'interprete nominato per path, poi la ricetta e' stata eseguita verbatim dall'inizio alla fine.

## Stato finale misurato

- perimetro `tests/test_packaging.py`: 16 test, 16 passed
- suite completa nel checkout: 715 passed
- suite dalla sdist estratta: 708 passed, 7 skipped, totale 715 identico
- `pyteman.__file__` dentro il venv, nessun path del checkout in `sys.path`
- sdist 64 file (6 root, 20 src, 23 tests, 4 docs, 11 examples), zero file proibiti
- wheel 20 file, hook annidato presente, hook top-level assente, `py.typed` presente
- sdist sha256 7ee7199230e1e8b8de4f10cede63726f56693726c24efdb36957cbcfea67e0a7
- wheel sha256 fb91a393b59e2bb032da8ebc665b7b499e01e82e89ecf882745a370e06d97f49
- `MANIFEST.in` c69612faac49a0a570bf531d28cb74fda888fc9fecce766a7d7acea140fda337
- `tests/test_packaging.py` 0e0f2ec61ff6548fc5c751632787fe523ae5e08012c86cdbf5afadc09bb08bcd
- `docs/packaging.md` e7d6c8765af52a796309d8d9a8017ecfa2c8359fb6d19933b3142f4adacfa7f8
- `pyproject.toml` f7dcdd5518af1ee416013b27f7eef20a49688d5ec847c75a383be4e04ff0edab, identico a HEAD
- checkout condiviso: nessun `build/` o `dist/`, `SOURCES.txt` ancora fermo al 2026-09-16 10:27

CORREZIONE ALLO STANDARD DI PROVA (rilievo del parent, formulazione da conservare)

Le due note precedenti affermano che il totale dei test identico fra checkout e archivio dimostra che la sdist trasporta la suite completa senza omissioni. Questa affermazione e' debole e va sostituita.

Formulazione corretta: l'uguaglianza dei conteggi NON prova l'assenza di omissioni. Il conteggio e' un proxy soggetto a coincidenze, misurato per giunta su due esecuzioni separate di un checkout in movimento: due run possono concordare sul numero e differire sul contenuto. Il run del parent lo dimostra concretamente, avendo ottenuto 1 failed 707 passed 7 skipped dove il mio aveva ottenuto 708 passed 7 skipped sullo stesso archivio.

La prova effettiva e' duplice e nessuna delle due meta' e' un conteggio:
1. Il manifest content test, cioe' test_the_sdist_carries_a_granted_directory_exactly, che confronta per UGUAGLIANZA l'insieme dei nomi file presenti nell'archivio contro l'insieme derivato dall'albero, non filtrato per estensione. Cattura l'omissione in una direzione e l'inclusione spuria nell'altra, file per file.
2. La provenienza dell'import, cioe' pyteman.__file__ che punta dentro il venv e nessun percorso del checkout in sys.path, che prova che il run ha effettivamente esercitato il pacchetto installato e non la copia sorgente.

Il conteggio resta utile come segnale di fumo, mai come prova. Nei report futuri va presentato come tale.

CONFERMA DIRETTA DELL'ATTRIBUZIONE RT-02

Il fallimento segnalato dal parent e' stato verificato alla fonte anziche' ereditato:
  tests/test_activation_atomic.py::test_a_reentrant_patch_does_not_wrap_a_slot_this_call_already_took
fallisce in modo identico ESEGUITO NEL CHECKOUT, con SlotOwnershipError sollevato da src/pyteman/patcher.py:785. Inoltre lo sha256 del file di test nell'archivio, 12f7ede97e2fe74475a08bc0ec0070ffd9f5f1add0351cc6d75028ad4eb86966, coincide con quello nell'albero. Un file trasportato byte per byte che fallisce identicamente alla sorgente non puo' avere il manifest come causa: il difetto appartiene a RT-02 in lavorazione. Il manifest e' scagionato da evidenza diretta, non per inferenza.

Nessuna modifica ai tre file in scope: il documento non conteneva l'affermazione debole, verificato con grep, quindi gli hash gia' verificati dal parent restano validi. Packaging congelato come richiesto, nessun gate rieseguito.

VERIFICA INDIPENDENTE DEL PARENT E APPROVED (2026-09-17)

Chiusura su prova costruita dal parent, non sulla mia. Snapshot congelato /tmp/pyteman-pkg-verified-r96z3dt6/source con gli hash packaging identici ai miei e gli hash RT-02 temporaneamente fermi, il che elimina il rumore del checkout in movimento che aveva prodotto il fallimento spurio nel run precedente.

Costruzione e ispezione fatte dal parent su quella copia, offline: sdist e wheel costruiti, helper di test, docs ed examples presenti, backlog e cache assenti, wheel con hook annidato e py.typed. Install della sdist con --no-index --no-deps --no-build-isolation in un venv NUOVO, /tmp/pyteman-pkg-verified-r96z3dt6/venv; pyteman.__file__ dentro il venv e sys.path privo sia del checkout sia della copia sorgente. Suite dall'archivio estratto: 710 passed, 7 skipped, 0 failed, dove i 7 skip sono esplicitamente i controlli artifact-build che non si applicano dentro una distribuzione costruita. I 16 test di packaging sul checkout gia' verificati in precedenza.

AC1 soddisfatto da questa esecuzione. AC2 soddisfatto nella lettura confermata dal parent, cioe' limitato alla sdist, dove i documenti e i link referenziati risolvono; la resa della pagina PyPI resta TASK-105 e non blocca la sdist.

Chiusura solo tracker per istruzione: nessun commit, nessun push, nessuna release. I tre file restano agli hash verificati e pyproject.toml invariato.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
La sdist non trasportava una suite eseguibile. In assenza di MANIFEST.in setuptools ricadeva sul default distutils `tests/test*.py`, che prende `test_*.py` e nient'altro: l'archivio conteneva 19 moduli di test e nessuno di conftest.py, target_mod.py, integrity_corpus.py, e docs/ era assente del tutto. Installata in un ambiente pulito, la suite dall'archivio dava cinque errori di collection.

Correzione con un `MANIFEST.in` scritto come whitelist, concessioni per directory e non per estensione. La scelta e' misurata, non stilistica: una concessione filtrata per suffisso e difesa da un test che deriva l'attesa con lo stesso predicato nasconde un fixture non-.py da entrambi i lati nello stesso istante, ricostruendo il difetto originale una estensione piu' in la'. Le concessioni larghe scaricano il peso su `global-exclude`, che diventa portante, mentre i `prune` non rimuovono nulla oggi e restano contro un allargamento futuro.

`tests/test_packaging.py` tiene ferma la correzione con 16 test che misurano artefatti reali costruiti da una copia dell'albero, mai il checkout. Il confronto e' per uguaglianza contro un insieme derivato non filtrato, cosi' cattura sia l'omissione sia l'inclusione spuria, quest'ultima un rischio concreto perche' setuptools unisce all'archivio il SOURCES.txt che trova in un egg-info stantio. Residui e directory di workspace sono piantati o copiati apposta, perche' asserire un'assenza mai creata e' vacuo. Una guardia che non salta mai impedisce ai sette controlli sugli artefatti di sparire in silenzio da un run verde.

`docs/packaging.md` registra il ragionamento e la ricetta offline, corretta dopo averla eseguita: pip chiama l'hook di metadata del backend anche con --no-build-isolation, quindi il venv di installazione ha bisogno di setuptools e l'interprete va nominato per path.

`pyproject.toml` lasciato byte-identical: MANIFEST.in da solo e' sufficiente, misurato.

Chiuso su verifica indipendente del parent da uno snapshot congelato: sdist installata in un venv nuovo, provenienza dell'import confermata, 710 passed 7 skipped 0 failed dall'archivio estratto. La prova dell'assenza di omissioni e' il confronto per uguaglianza dell'insieme dei file piu' la provenienza dell'import, non l'uguaglianza dei conteggi. AC2 limitato alla sdist; la resa della pagina PyPI resta TASK-105.
<!-- SECTION:FINAL_SUMMARY:END -->
