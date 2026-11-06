---
id: TASK-137
title: 'PKG-06. global-exclude non copre i file di backup, che finiscono nella sdist'
status: Done
assignee: []
created_date: '2026-09-17 08:47'
updated_date: '2026-09-17 12:45'
labels:
  - pkg
  - audit-2026-09-16
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Trovato misurando, non leggendo: un file `*.bak.*` lasciato in una directory concessa da `MANIFEST.in` viene pubblicato nella sdist, e nessun test se ne accorge.

**Evidenza.** Durante TASK-34.1 avevo lasciato due backup in `docs/`, creati dalla regola che impone il backup prima di sovrascrivere. Costruita la sdist da una copia pulita:

    pyteman-0.1.0/docs/coverage.md.bak.1789632119
    pyteman-0.1.0/docs/coverage.md.bak.1789633929

78 voci nell'archivio. Rimossi i due file, 76 voci. I due backup fuori da `docs/` (`pyproject.toml.bak.*` alla radice e `.github/workflows/tests.yml.bak.*`) NON finiscono nell'archivio, e il motivo e' diverso per ciascuno: la radice e' concessa solo per `include` espliciti, e `.github` non e' concesso affatto. Quindi il problema riguarda esattamente le tre directory concesse in blocco, `tests`, `docs`, `examples`.

**Causa.** `recursive-include docs *` concede tutto, e l'unica cosa che ripulisce e' `global-exclude *.py[cod] *.so *.log *.swp *~ .DS_Store`. Nessuno di quei pattern copre `.bak.*`. `docs/packaging.md` chiama quella riga "load-bearing rather than decorative", ed e' esatto: e' la meta' del progetto che permette alle concessioni di restare larghe. Manca solo una voce.

**Perche' i test non lo vedono, che e' la parte piu' interessante.** La suite packaging passa 16/16 sia con i backup sia senza, misurato e non dedotto. La causa NON e' che il confronto per eguaglianza usa l'albero come ingresso e come oracolo: quel confronto qui regge onestamente. E' che `_is_residue` classifica con `endswith` su `RESIDUE_SUFFIXES` e non conosce la forma `.bak`, quindi `docs/x.md.bak.1789617984` entra nell'archivio e contemporaneamente nell'attesa costruita da `_files_under`, e i due lati si cancellano a ragione. A non vedere il file e' il rivelatore, non l'oracolo. La distinzione dice dove va la correzione: nel predicato, non nella derivazione.

**Lavoro.** Aggiungere `*.bak.*` (e valutare `*.orig`, `*.rej`, `*.bak`) alla riga `global-exclude`, e aggiungere un test che pianta un file di residuo per ciascun pattern nella copia prima di costruire, esattamente come `docs/packaging.md` descrive gia' per i pattern esistenti. Il test va scritto in modo che NON derivi l'attesa dall'albero, altrimenti riproduce la stessa vacuita'.

**Fuori perimetro.** Nessuna modifica alle concessioni `recursive-include`, che sono una decisione gia' presa e motivata.

Segnalato da TASK-34.1, che ha bonificato il proprio residuo spostando i due file in `/tmp/covrun/docs-backups/` invece di cancellarli. L'albero oggi e' pulito, quindi questo non e' urgente: e' una trappola che scatta al prossimo backup lasciato in una directory concessa.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 La riga global-exclude di MANIFEST.in copre i file di backup, e la scelta dei pattern e' motivata invece che copiata.
- [x] #2 Un test pianta un file di residuo per ciascun pattern escluso PRIMA di costruire e verifica che non arrivi nell'archivio, senza derivare l'attesa dall'albero.
- [x] #3 Dimostrato che il test fallisce se il pattern viene tolto da MANIFEST.in, cioe' che non e' vacuo.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
**Assessment read-only del 2026-09-17. Nessun file modificato, nessun codice scritto.**

**Stato dell'arte, letto e non dedotto.** `MANIFEST.in` sha256 `c69612fa...`, invariato rispetto a TASK-32. La pulizia e' una riga sola, la 49: `global-exclude *.py[cod] *.so *.log *.swp *~ .DS_Store`, otto pattern, nessuno dei quali copre la forma `.bak`.

`tests/test_packaging.py` sha256 `94679519...`, 16 test. Qui l'assessment corregge la descrizione del task: **l'infrastruttura che l'AC2 chiede esiste gia' e non va costruita da zero.**
- `PLANTED_RESIDUE` (riga 69) pianta un file per pattern dentro `tests/` nella copia da cui si costruisce, PRIMA della build. Quindi il controllo misura per costruzione e non la pulizia di chi ha lanciato la suite, che e' esattamente cio' che l'AC2 chiede.
- `test_every_excluded_pattern_is_exercised_by_a_planted_file` (riga 169) legge la riga `global-exclude` dal manifest e verifica in fnmatch che ogni pattern abbia un nome piantato. Un pattern aggiunto senza il suo file va rosso qui.
- `test_the_sdist_carries_no_residue` (riga 328) e' l'asserzione sull'archivio.

Conseguenza pratica: l'AC2 non richiede un test nuovo. Richiede due nomi in `PLANTED_RESIDUE` e l'estensione del predicato rivelatore.

**Correzione al meccanismo scritto nella descrizione del task.** La descrizione attribuisce il 16/16 al fatto che l'uguaglianza confronta l'archivio con un glob dell'albero, rendendo l'albero insieme ingresso e oracolo. Misurato leggendo il codice, la causa e' piu' stretta e sta altrove: `_is_residue` (riga 104) classifica con `endswith` su `RESIDUE_SUFFIXES` e non conosce `.bak`. Un file `docs/x.md.bak.1789617984` entra quindi nell'archivio e contemporaneamente nell'attesa costruita da `_files_under`, e l'uguaglianza regge legittimamente. Non e' l'oracolo derivato dall'albero a nascondere il difetto, e' il rivelatore che non classifica quella forma. La distinzione conta perche' dice dove va la correzione: nel predicato, non nella derivazione.

**Semantica dei pattern, misurata e non assunta.** `global-exclude` passa da `FileList.exclude_pattern(pattern, anchor=False)` e `translate_pattern` compila con `\z` finale: il match e' libero all'inizio del percorso e ANCORATO ALLA FINE, non libero da entrambi i lati. Verificato con setuptools 80.10.2 compilando i regex reali di `setuptools._distutils.filelist` e cercandoli su percorsi plausibili, invece di fidarmi della documentazione del formato.

Esito, X uguale escluso dall'archivio:

| pattern | `x.md.bak.1789617984` | `notes.bak` | `notes.bakery.md` |
|---|---|---|---|
| `*.bak` | . | X | . |
| `*.bak.*` | X | . | . |
| `*.bak*` | X | X | X |

Tre conseguenze, tutte operative.

1. **`*.bak` da solo NON copre la convenzione che ha prodotto i residui veri.** Il manuale prescrive `cp file file.bak.$(date +%s)`, e i tre backup presenti oggi nell'albero hanno tutti quella forma: `pyproject.toml.bak.1789618608`, `pyproject.toml.bak.1789622596`, `.github/workflows/tests.yml.bak.1789617984`. Nessuno dei tre sta in una directory concessa, quindi l'albero e' pulito oggi, come gia' registrato nella descrizione.
2. **`*.bak*` copre tutto con un pattern solo ma spazza anche `notes.bakery.md`**, perche' `[^/]*?\.bak` seguito da `[^/]*` fino a fine nome accetta qualunque parola che contenga `.bak`. E' una sovra esclusione silenziosa, cioe' il modo esatto in cui un file sparisce da una release senza che nulla vada rosso: l'opposto del difetto che questo task corregge, non un suo caso peggiore.
3. **La coppia `*.bak` piu' `*.bak.*` copre entrambe le forme reali e non tocca nessun quasi omonimo.**

**Proposta, due pattern e non uno.** Aggiungere `*.bak *.bak.*` DENTRO la riga 49 esistente, non in una riga nuova in fondo al file. Il motivo e' scritto nel commento alle righe 44-48 di `MANIFEST.in`: questi pattern spazzano solo le concessioni che stanno SOPRA di loro, quindi un `global-exclude` appeso in fondo dopo una futura `recursive-include` cambierebbe significato senza che nulla lo segnali.

Motivazione per pattern, che e' cio' che l'AC1 chiede quando dice motivata invece che copiata:
- `*.bak.*` e' il pattern portante. Copre la convenzione con timestamp, l'unica che abbia prodotto residui misurati in questo repository.
- `*.bak` copre la forma semplice a costo zero di sovra esclusione, misurato sopra.
- `*.bak*` SCARTATO, per la sovra esclusione misurata su `notes.bakery.md`.
- `*.orig` e `*.rej` NON proposti. Nessun residuo di quella forma e' mai comparso in questo albero, e l'AC1 chiede pattern motivati invece che copiati da una lista altrui: aggiungerli sarebbe esattamente copiare. Se il parent li vuole comunque, vanno con il loro file piantato ciascuno, altrimenti il cross check va rosso.

**Accoppiamento obbligatorio, tre punti.** Chi implementa deve toccare tre posti insieme, e due di questi non sono nominati nella descrizione del task:
1. `PLANTED_RESIDUE` serve DUE nomi distinti, perche' un nome solo non esercita entrambi i pattern. Verificato in fnmatch: `planted.bak` corrisponde a `*.bak` e non a `*.bak.*`; `planted.bak.1` il contrario.
2. `_is_residue` deve imparare la forma. Il predicato attuale e' `endswith` su una tupla, e `.bak.<epoch>` ha coda variabile, quindi `endswith` da solo non basta e serve un predicato diverso per quel ramo.
3. `RESIDUE_SUFFIXES` va tenuta A MANO e NON derivata dal manifest. Il commento alla riga 58 lo dice gia' e va rispettato: quella riga rileva, la riga del manifest impone, e derivare il rivelatore dall'imposizione lo renderebbe incapace di accorgersi di un manifest sbagliato. Sarebbe la stessa vacuita' che l'uguaglianza evita altrove, spostata di un livello.

Dimenticare il punto 2 non e' silenzioso, ed e' bene saperlo prima: il file piantato resta nell'attesa costruita da `_files_under`, l'archivio non lo ha, e `test_the_sdist_carries_a_granted_directory_exactly` va rosso nominandolo. L'accoppiamento si sorveglia da solo in quella direzione.

**AC3, forma della prova di non vacuita'.** Stessa tecnica gia' documentata in `docs/packaging.md` alla sezione Confirming the checks are not vacuous: copia l'albero fuori dal repository, togli i due pattern dalla riga 49 della SOLA copia, lancia `tests/test_packaging.py` da li'. Previsione da confermare con la misura e non da dichiarare come fatto: due rossi, `test_the_sdist_carries_no_residue` che nomina i file piantati, e l'uguaglianza su `tests` che li trova di troppo nell'archivio. Se ne va rosso uno solo, la previsione era sbagliata e va capito perche' prima di chiudere.

**Perimetro proposto per la tranche.** Dentro: `MANIFEST.in` riga 49, e in `tests/test_packaging.py` le sole `PLANTED_RESIDUE`, `RESIDUE_SUFFIXES` e `_is_residue`. Fuori: le concessioni `recursive-include`, che sono una decisione gia' presa e motivata; le righe `prune`; `scripts/`; ogni altro test del file, che appartiene a una tranche gia' revisionata e congelata.

**Punto aperto che va deciso adesso e non dopo.** `docs/packaging.md` ha una sezione Known residue che elenca le lacune tracciate altrove, TASK-105, TASK-108, TASK-109, e non cita questa. Se la tranche deve allinearla e' una riga in piu' nel perimetro. Lo segnalo ora perche' accorgersene a lavoro finito produce o una modifica fuori perimetro o un documento che resta indietro.

**Stato.** Nessun codice scritto, nessun file dell'albero modificato, task lasciato in To Do. In attesa di via libera sul perimetro e sulla scelta dei due pattern.

**Implementazione del 2026-09-17. Tre file modificati, nessun commit, nessun push.**

File toccati e sha256 finali, misurati dopo l'ultima modifica e non copiati da una misura precedente:

    MANIFEST.in             affb1623b4d9125ac197630a3c6a727bae1fd0b872514f168ca9b9e403c05324
    tests/test_packaging.py e20498b2e10afbd75477d73f046910a7b1007a84918fbd5bce964265866aefb8
    docs/packaging.md       3e60826357218a7b097d0f5ac1381999188cb5c7bd64ec9285b29cea8a05cb43

Copie pre modifica conservate fuori dall'albero in `/tmp/t137_backup/`, con i nomi `*.bak.1789645801`. Non sono state cancellate e non sono state messe dentro il repository, dove sarebbero finite nella sdist, che e' il difetto che questo task chiude.

**MANIFEST.in.** La riga `global-exclude` porta ora `*.bak *.bak.*` in coda ai pattern preesistenti, dentro la riga esistente e non in una riga nuova in fondo al file, per la ragione gia' scritta nel commento sopra di essa: questi pattern spazzano solo le concessioni che stanno sopra. Il commento e' stato esteso per spiegare perche' i pattern sono due e non il singolo `*.bak*`, con il rimando alla misura in `docs/packaging.md` invece della ripetizione della tabella.

**tests/test_packaging.py.** `.bak` aggiunto a `RESIDUE_SUFFIXES`; `planted.bak` e `planted.bak.1` aggiunti a `PLANTED_RESIDUE`; `_is_residue` ha un ramo nuovo `".bak." in name` per la forma con timestamp, che nessun suffisso puo' esprimere perche' la coda e' un epoch; introdotto `PLANTED_KEEPER = "notes.bakery.md"`, piantato nella copia insieme ai residui ma atteso nell'archivio.

**docs/packaging.md.** Sezione nuova sui pattern di backup con la tabella dei regex compilati, il motivo per cui la coppia batte il pattern unico, e il motivo per cui `*.orig` e `*.rej` restano fuori. Nessuna voce aggiunta a Known residue: quella sezione elenca lacune tracciate altrove e aperte, e questa si chiude qui. TASK-105, TASK-108 e TASK-109 restano come erano.

**La verifica della sovra esclusione e' dentro `test_the_sdist_carries_no_residue`, non in un test suo.**

La prima stesura aveva un test separato, `test_the_sdist_still_carries_a_name_that_only_looks_like_residue`. E' stato riassorbito come seconda asserzione del check sui residui, con il suo commento inline, seguendo l'idioma che il file gia' usa in `test_the_sdist_carries_no_top_level_entry_that_was_not_granted`, dove la direzione opposta sta come seconda asserzione commentata e non come test a parte.

**Il motivo decisivo non e' estetico.** `TestBuiltArtifacts` conteneva sette check, e quel sette e' scritto a mano in sette punti su quattro file. Due di quei punti stanno in `.github/workflows/tests.yml` e `scripts/verify_artifacts.py`, cioe' fuori dal perimetro che questa tranche ha il permesso di toccare. Il test separato portava la classe a otto e rendeva falsi tutti e sette i punti, compresi i due che non posso correggere: avrei chiuso il task lasciando due file fuori perimetro con un'affermazione falsa dentro. La forma riassorbita tiene la classe a sette e lascia veri tutti e sette i punti senza modificare nulla fuori perimetro.

**Cosa si perde, detto esplicitamente.** La seconda asserzione viene eseguita solo se la prima passa. Un manifest sbagliato in entrambe le direzioni insieme, troppo stretto e troppo largo, riporta prima la direzione stretta; sistemata quella e rilanciato, riporta l'altra. E' lo stesso compromesso gia' accettato nel check sul livello superiore, quindi non introduce una regola nuova nel file.

**Cosa non si perde, misurato e non dedotto.** Il messaggio di fallimento e' lo stesso identico, e il caso `*.bak*` lo stampa per intero: `notes.bakery.md was planted in a directory granted whole and did not ship, so a residue pattern is matching a name that merely contains one of their prefixes`. Il numero di rossi nella ricetta di non vacuita' resta sei, perche' il check sui residui va rosso comunque, solo sulla seconda meta' invece che come test a se'.

Per la trappola di fondo, cioe' i sette numeri scritti a mano che nulla collega alla classe, e' stato aperto TASK-163. La coppia di pattern e' tornata vera per come e' finita la tranche, non perche' qualcuno abbia corretto quei numeri, e questo va tracciato invece che lasciato alla fortuna.

**Misure del 2026-09-17, ciascuna con la previsione dichiarata prima della corsa.**

**Suite.** `tests/test_packaging.py` 16 passed. Suite intera 756 passed, 0 failed, 11.33s. Previsione 756, corrisponde: la corsa verde precedente era 757 con diciassette test packaging, e il riassorbimento ne toglie uno. `TestBuiltArtifacts` conta 7 check, misurato con `--collect-only -q | grep -c`.

**AC3, non vacuita', tre controlli negativi su copie fuori dal repository.** Ogni controllo toglie un solo pattern dalla riga `global-exclude` della sola copia e lancia il file da li'.

1. Tolto `*.bak`, resta `*.bak.*`: 2 failed. `test_the_sdist_carries_no_residue` nomina `['tests/planted.bak'] == []`, cioe' la forma semplice sfugge. L'uguaglianza su `tests` va rossa insieme.
2. Tolto `*.bak.*`, resta `*.bak`: 2 failed. Stessa coppia, e il file nominato e' `['tests/planted.bak.1']`, cioe' la forma con timestamp sfugge.
3. Sostituiti entrambi con il singolo `*.bak*`: 2 failed, e il messaggio e' quello della sovra esclusione su `notes.bakery.md`. E' la misura che scarta il pattern unico invece di argomentarlo.

Con entrambi i pattern al loro posto: 16 passed. Ogni pattern e' quindi portante in una direzione diversa, e nessuno dei tre e' ridondante.

**Nota su un controllo rifatto.** La prima esecuzione del controllo 1 aveva un errore mio nel comando `sed`: la riga scritta era `*.bak.` invece di `*.bak.*`, cioe' un pattern che accetta solo nomi che finiscono con un punto. Quel controllo andava rosso, ma non era il controllo richiesto. Rifatto correttamente scrivendo il file in Python invece che con `sed`, con il risultato riportato sopra. Registrato perche' un controllo negativo che fallisce per la ragione sbagliata e' peggio di un controllo mancante: sembra una prova.

**Ricetta di non vacuita' della documentazione, rimisurata.** Copia dell'albero, cancellato `MANIFEST.in`, lanciato il file: 6 failed, 10 passed. I sei sono le tre directory concesse, il check sul livello superiore, il cross check che cerca il manifest che non puo' piu' leggere, e il check sui residui, che passa la prima meta' e fallisce la seconda perche' senza manifest nemmeno il keeper viene spedito. Verificato che il rosso e' sulla seconda asserzione leggendo la riga riportata, 367, e non dedotto dal nome del test.

**La documentazione diceva tre.** Il numero scritto in `docs/packaging.md` era gia' sbagliato prima di questa tranche: misurato sull'albero pre tranche da' cinque rossi, non tre. Corretto a sei con l'elenco di quali sono, che e' la parte che permette di accorgersi la prossima volta che il numero cambia.

**Gate e revisioni, con cosa e' stato applicato e cosa no.**

Due revisioni indipendenti hanno trovato lo stesso difetto senza sapere l'una dell'altra: il test aggiunto portava `TestBuiltArtifacts` a otto e falsificava i conteggi scritti a mano. La convergenza e' il motivo per cui e' stato trattato come reale invece che come opinione. Una delle due ha trovato in piu' i due punti fuori perimetro, che sono quelli che hanno deciso la forma finale.

**Applicato.**
1. Riassorbimento del test separato dentro il check sui residui, con il ragionamento scritto nel blocco precedente.
2. Correzione di un'affermazione troppo forte che avevo scritto io. Il commento diceva che l'uguaglianza su `tests/` riporta la sovra esclusione senza nominare il file. Misurato, la nomina: stampa `Extra items in the right set: 'tests/notes.bakery.md'`. Cio' che non da' e' la ragione, e ora il commento dice quello.
3. Rimossa la coda del commento su `_is_residue`, che ripeteva il meccanismo di cancellazione gia' spiegato nella docstring di `_files_under`. Sostituita da un rimando.
4. Corretto un riferimento penzolante: `docs/packaging.md` nominava il test riassorbito. Trovato con una ricerca sull'intero albero, non a memoria, perche' un nome di test cancellato non rompe niente e resta li' a invecchiare.

**Non applicato, con la ragione.** Nessuna proposta e' stata scartata come falso positivo. Le due segnalazioni sui punti in `.github/workflows/tests.yml` e `scripts/verify_artifacts.py` non sono state applicate perche' quei file sono esplicitamente fuori dal perimetro concesso: sono confluite in TASK-163 invece di essere modificate qui.

**Task aperti da questa tranche, entrambi nello stesso turno in cui la segnalazione e' stata letta.**
- TASK-162, PKG-07: il rivelatore confronta `.DS_Store` per uguaglianza mentre il manifest lo esclude per suffisso. Misurato: il regex compilato `(?s:\.DS_Store)\z` esclude anche `docs/foo.DS_Store`, che `_is_residue` non riconosce. Divergenza reale fra i due lati, senza sintomo oggi.
- TASK-163, PKG-08: i sette punti che scrivono a mano la dimensione della classe.

**Fuori perimetro, rispettato.** Non toccati `pyproject.toml`, `.github/workflows/publish.yml`, il workflow dei test, `scripts/verify_artifacts.py`, il runtime, le concessioni `recursive-include`, le righe `prune`. Non toccato il sito `timeout=300` nella fixture, che appartiene alla tranche TASK-34.2 gia' atterrata. Nessun commit e nessun push: i tre file restano non tracciati nell'albero condiviso, come da istruzione.

APPROVATO dal revisore peer, tranche chiusa lato tracker.

Verifica indipendente eseguita dal revisore, non da me: quattro sdist costruite da copie nuove, con backup e keeper piantati in tutte e tre le directory concesse (tests, docs, examples) invece che nella sola tests. Risultati riportati: la configurazione valida esclude .bak e .bak.123 e conserva notes.bakery.md; togliendo ciascuno dei due pattern sfugge esattamente la forma corrispondente; il singolo *.bak* elimina il keeper. Hash dei tre file invariati prima e dopo il controllo, 16 test packaging verdi, diff-check pulito, suite intera 763 passed sul suo albero.

La mia misura della suite intera era 756 e la sua e' 763. La differenza non e' in discussione qui: l'albero e' condiviso e altri agenti hanno lavorato in parallelo, quindi i due numeri sono stati presi su stati diversi dello stesso checkout. I tre hash sui file di questa tranche coincidono, ed e' quello il controllo che riguarda TASK-137.

L'asserzione del keeper dentro test_the_sdist_carries_no_residue e' accettata come consegnata. Nessuna guardia sui conteggi da implementare adesso: resta TASK-163 come follow-up opzionale.

Nessun commit, nessun push, nessun dispatch di Actions. I tre file restano non tracciati nell'albero condiviso.
<!-- SECTION:NOTES:END -->
