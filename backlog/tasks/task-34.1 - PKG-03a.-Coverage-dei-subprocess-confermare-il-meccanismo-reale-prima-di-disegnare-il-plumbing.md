---
id: TASK-34.1
title: >-
  PKG-03a. Coverage dei subprocess: confermare il meccanismo reale prima di
  disegnare il plumbing
status: Done
assignee:
  - pyteman-runner-opus5
created_date: '2026-09-17 04:05'
updated_date: '2026-09-17 09:00'
labels:
  - pkg
  - opus-5
  - audit-2026-09-16
milestone: m-5
dependencies: []
parent_task_id: TASK-34
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Scorporato dall'AC monolitico di TASK-34 (criterio 3). Non cancellato: TASK-34 non va a Done finche' questo non e' soddisfatto o esplicitamente ridiscusso.

**Requisito.** I test che usano subprocess o multiprocessing devono essere inclusi nella misura di coverage. Superficie misurata sullo stato corrente: 5 file di test lanciano figli (`tests/test_packaging.py`, `tests/test_report_escaping.py`, `tests/test_sitecustomize.py`, piu' i multiprocessing di `tests/test_kill.py`).

**Vincolo di metodo, esplicito.** Prima di disegnare qualunque plumbing occorre CERCARE la documentazione ATTUALE di coverage sulla misura dei sottoprocessi e confermare il meccanismo reale sullo strumento installato. Non cristallizzare un meccanismo ricordato. Quanto segue e' memoria non verificata e va trattata come ipotesi da confutare, non come progetto.

**Ipotesi da verificare, non conclusione.** Il meccanismo tradizionalmente citato aggancia l'avvio dell'interprete con un file `.pth` che chiama `coverage.process_startup()`, attivato dalla variabile `COVERAGE_PROCESS_START` che punta alla configurazione. Se e' ancora cosi', qui ha un attrito specifico e concreto: i figli vengono lanciati con `sys.executable -c`, e `tests/test_sitecustomize.py` manipola deliberatamente `PYTHONPATH` per rendere il modulo importabile come top-level. Un test che passa un dizionario `env=` completo invece di derivarlo dall'ambiente corrente perde la variabile, e quel figlio non viene misurato senza che nulla lo segnali. Se l'ipotesi regge, il lavoro non e' una riga di configurazione ma plumbing per ogni call site, piu' un controllo che renda rilevabile il figlio non misurato.

**Attrito aggiuntivo da valutare.** Il pacchetto spedisce un proprio `pyteman/sitecustomize.py` come meccanismo di attivazione, gated su `PYTEMAN_RULES`. Se il meccanismo di coverage usa `.pth` i due non collidono, ma vanno verificati insieme e non assunti indipendenti.

**Fuori perimetro.** Nessuna nuova soglia di coverage. Aggiungere coverage come strumento e' parte di questo task e va dichiarato, non introdotto di straforo.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 La documentazione coverage attuale sulla misura dei sottoprocessi e' stata cercata e citata, e il meccanismo e' stato confermato sullo strumento realmente installato anziche' assunto.
- [x] #2 I figli lanciati dai test sono inclusi nella misura, dimostrato con un confronto prima/dopo su un file che viene eseguito solo in un sottoprocesso.
- [x] #3 I due canali che rendono misurabili i figli, propagazione config via subprocess e flush prima di os._exit, sono verificati da un controllo che FALLISCE rumorosamente quando uno dei due manca, su righe eseguite solo da un figlio e non sulla percentuale. Portata: e' un test di esistenza per riga, soddisfatto da almeno un figlio che la raggiunge. Garantisce i canali testati, NON ogni nuovo call site, NON i figli non-Python, NON la presenza di tutti i test che attraversano quella riga.
- [x] #4 Nessuna soglia di coverage introdotta.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
## Ricerca del meccanismo reale (criterio 1), 2026-09-17

**Fonte cercata e citata:** changelog ufficiale `https://coverage.readthedocs.io/en/latest/changes.html`, letto il 2026-09-17, piu' la documentazione 7.15.2 su subprocess e `[run] patch`.

**Strumento realmente installato, su cui il meccanismo e' stato confermato leggendo il sorgente ed eseguendolo:** coverage 7.14.1 e pytest_cov 7.1.0 su `/usr/bin/python3.14`. Nel repository non esiste oggi nessuna configurazione coverage: niente `.coveragerc`, niente `setup.cfg`, niente `tox.ini`, nessuna chiave coverage in `pyproject.toml`.

### L'ipotesi registrata nella descrizione e' superata, e va scartata

La descrizione ipotizzava `.pth` scritto da noi piu' `COVERAGE_PROCESS_START`, e ne deduceva "plumbing per ogni call site". Entrambe le meta' sono false sullo strumento installato.

Storia delle versioni, ricavata dal changelog e non dalla memoria:

    7.10.0  2025-07-24  introduce l'opzione [run] patch con _exit, subprocess, execv
    7.10.1  2025-07-27  cambia dove vengono scritti i .pth per patch = subprocess
    7.10.3  2025-08-10  correzioni a patch = subprocess, aggiunge debug = patch
    7.10.4  2025-08-16  aggiunge patch = fork; patch = execv eredita l'intera config
    7.12.1  2025-11-30  il .pth diventa PERMANENTE e viene installato col pacchetto
                        (issue 2084: falliva dove site-packages non e' scrivibile)

Verificato sul disco, non dedotto: coverage 7.14.1 installa `a1_coverage.pth` dentro site-packages ed e' elencato nel RECORD del wheel. Il suo contenuto e' inerte per costruzione, perche' si autolimita alle due variabili d'ambiente:

    if os.getenv("COVERAGE_PROCESS_START") or os.getenv("COVERAGE_PROCESS_CONFIG"):
        try: import coverage
        except: pass
        else: coverage.process_startup(slug="pth")

Quindi **il progetto non scrive nessun .pth**. Quel plumbing non esiste piu' come nostro lavoro.

Seconda meta' dell'ipotesi, altrettanto superata: `_patch_subprocess` in `coverage/patch.py:114` non fa altro che impostare `os.environ["COVERAGE_PROCESS_CONFIG"]` nel processo padre. La variabile raggiunge i figli per eredita' normale. Ho verificato tutti e cinque i call site che lanciano figli e **ognuno costruisce l'ambiente come `{**os.environ, ...}`**, per esempio `tests/test_sitecustomize.py:79` e `tests/test_report_escaping.py:398`. Nessuno passa un dizionario pulito. L'attrito temuto nella descrizione oggi non si verifica in nessun punto.

### Perche' funziona anche sotto pytest-cov e non solo sotto `coverage run`

`apply_patches` e' chiamato da `coverage/control.py:719`, che sta dentro `Coverage.start()`, cioe' l'API pubblica. pytest-cov chiama `Coverage.start()`. Di conseguenza `[run] patch` e' onorato dalla sola configurazione, senza nessun flag da riga di comando e senza nessuna modifica ai test.

### Misura, non ragionamento: quali valori di patch sono portanti

Progetto sintetico in `/tmp/covprobe` con tre funzioni in `work.py`: una raggiunta solo da un figlio `subprocess` che esce con `os._exit(71)`, una raggiunta solo da un figlio `mp.Process` che esce con `os._exit(70)`, una mai chiamata. Il terzo caso e' il controllo che tiene onesto il numero: se la copertura arrivasse al 100% la misura sarebbe rotta.

Base: 6 statement. Con entrambi i figli misurati la copertura e' 83% (manca solo la funzione mai chiamata). Con entrambi i figli persi e' 50%.

    patch = subprocess, _exit, fork   ->  83%
    patch = subprocess, fork          ->  50%
    patch = subprocess                ->  50%
    patch = _exit                     ->  50%
    patch = (nessuno)                 ->  50%

Lettura: `subprocess` e `_exit` sono **entrambi necessari e nessuno dei due basta da solo**. Senza `subprocess` coverage non parte nel figlio; senza `_exit` parte ma non salva, perche' `os._exit` scavalca `atexit` ed e' esattamente cosi' che coverage scrive il file dati.

Secondo esperimento, per stabilire se `fork` serve. Ho forzato il metodo di avvio invece di dedurlo dalla versione:

    start=fork        patch=[subprocess, _exit, fork]  ->  83%
    start=fork        patch=[subprocess, _exit]        ->  83%
    start=forkserver  patch=[subprocess, _exit, fork]  ->  83%
    start=forkserver  patch=[subprocess, _exit]        ->  83%
    start=spawn       patch=[subprocess, _exit, fork]  ->  83%
    start=spawn       patch=[subprocess, _exit]        ->  83%

`fork` non cambia nulla per la forma di figlio che questo progetto ha davvero, cioe' un figlio che corre e poi esce. Va quindi lasciato fuori finche' qualcosa non lo giustifica, non aggiunto per simmetria.

Dettaglio che conta sulla matrice: su Python 3.14.7 il metodo di avvio predefinito misurato e' **forkserver**, non `fork`. Su 3.11 e 3.12 e' ancora `fork`. Ragionare come se `fork` fosse il default ovunque sarebbe stato sbagliato proprio sul leg piu' nuovo.

### L'attrito con il sitecustomize di pyteman, misurato

La descrizione chiedeva di non assumere i due meccanismi indipendenti. Ordine di esecuzione verificato piantando un `.pth` che stampa e un `sitecustomize` che stampa:

    PTH ran
    SITECUSTOMIZE ran
    MAIN ran

Tutti i `.pth` girano **prima** di `sitecustomize`, perche' `site.py` processa le directory prima di `execsitecustomize()`. Conseguenza concreta e favorevole: coverage e' gia' avviato quando l'hook di attivazione di pyteman parte, quindi l'hook stesso e' misurato, e soprattutto il suo `os._exit(2)` di rifiuto (`src/pyteman/sitecustomize.py:67`) trova `os._exit` gia' patchato e salva invece di perdere il dato.

Correzione a un mio conteggio precedente, perche' cambia dove sta il rischio: in `tests/` non esiste nessuna chiamata a `os._exit`. Le tre occorrenze sono prosa dentro docstring. Le chiamate vere sono nel codice di produzione, `src/pyteman/actions.py:49` e `src/pyteman/sitecustomize.py:67`, cioe' esattamente le righe che senza `patch = _exit` resterebbero non misurate mentre i test le eseguono.

### Il canale di match: source_pkgs non può vedere sitecustomize

Misurato, non dedotto. Con la config candidata iniziale (`source_pkgs = ["pyteman"]`) la suite completa sotto coverage produce per `src/pyteman/sitecustomize.py` **zero righe eseguite**, mentre `actions.py` ne porta 52. Il sentinella #2 non era misurato.

Causa, tracciata fino al sorgente di coverage 7.14.1. `inorout.py:462` passa il **nome del modulo** a `ModuleMatcher.match`, e `files.py:300-311` confronta quel nome con i prefissi dichiarati. Il file `src/pyteman/sitecustomize.py` viene eseguito dai figli come modulo top-level `sitecustomize`, perché i test mettono `src/pyteman` sul PYTHONPATH: il nome non inizia per `pyteman`, quindi non combacia mai, per quanto il percorso stia dentro il pacchetto. `actions.py` invece è importato come `pyteman.actions` e combacia.

`inorout.py:468` mostra il secondo canale, indipendente e path-based: `source` alimenta un `TreeMatcher` che confronta il percorso. Aggiungendo `source = ["src/pyteman"]` accanto a `source_pkgs`, la riga 67 di sitecustomize risulta eseguita. I due canali sono in OR, quindi tenerli entrambi copre sia il caso per percorso sia quello per nome di modulo, che resta utile se il pacchetto fosse installato non editable fuori da `src/`.

### Un source relativo si risolve sul cwd del genitore, e fallisce vuoto

Questa è la ragione per cui prima avevo scelto `source_pkgs`, e va corretta con la misura giusta. Il percorso relativo non è risolto contro il file di config, ma contro il cwd del processo che avvia coverage. Lanciando lo stesso comando con lo stesso `--rcfile` assoluto da `/tmp/covsent` invece che dalla radice del checkout, coverage degrada `src/pyteman` a nome di modulo, emette `CoverageWarning: Module src/pyteman was never imported` e misura **zero file**. È un fallimento vuoto: nessun errore, dati vuoti.

Il cwd dei figli invece non conta. Nel test il genitore girava nel checkout e i figli con cwd `/tmp/covsent`, e il sentinella è stato comunque raccolto: la risoluzione avviene una volta nel genitore e viaggia serializzata in `COVERAGE_PROCESS_CONFIG`.

Conseguenza di progetto: il driver deve imporre il cwd e il controllo contrattuale sui sentinella è anche la guardia contro la misura vuota, perché da un cwd sbagliato i file misurati sono zero e il controllo fallisce rumorosamente.

### Effetto osservatore: un test della suite non sopravvive alla strumentazione

Segnalazione, non modifica. Sotto `coverage run` la suite non è più verde: fallisce `tests/test_sitecustomize.py::test_inert_run_does_not_import_pyteman`, con `['typing']` al posto di `[]`. È l'unico fallimento, e il totale resta 723.

Catena causale, ogni anello misurato e non correlato:

1. `patch = ["subprocess"]` fa impostare a `coverage/patch.py:114` la variabile `COVERAGE_PROCESS_CONFIG` nell'ambiente del processo pytest.
2. `tests/test_sitecustomize.py:79` costruisce l'ambiente del figlio come `{**os.environ, ...}`, quindi la variabile viene ereditata.
3. All'avvio del figlio `a1_coverage.pth` vede la variabile non vuota e chiama `coverage.process_startup()`, che importa `coverage.control`, che importa `typing`.
4. Il test asserisce che né `typing` né `pyteman*` siano in `sys.modules` del figlio, e trova `typing`.

Esperimento discriminante, stesso interprete e stesso codice, sola variabile cambiata: senza `COVERAGE_PROCESS_CONFIG` il figlio stampa `[]`, con la variabile impostata stampa `['typing']`. La variabile da sola basta. Da notare che l'import di `typing` avviene anche quando il valore della variabile è malformato e `process_startup` solleva: il `.pth` importa prima di fallire.

Il `typing` non arriva dallo shim di pyteman ma dall'apparato di misura. Il test misura una proprietà vera del prodotto e la strumentazione gliela sporca.

Da notare che il test gemello `test_inert_run_adds_nothing_to_sys_modules_but_the_shim` resta verde, perché differenzia due figli entrambi strumentati e `typing` si cancella da solo. È una conferma empirica dell'argomento già scritto nel suo docstring: nominare gli import proibiti è più fragile che differenziare contro una baseline.

Non è riconciliabile con una configurazione: i figli di rifiuto, che sono quelli che eseguono il sentinella #2, e questo figlio inerte nascono dallo stesso helper `run_py`, quindi nessuna config li distingue. Il file appartiene a un altro agente e **non l'ho toccato**. La mitigazione sta interamente in un file mio: il job coverage deseleziona quel solo node id, mentre la matrice normale non strumentata continua a eseguirlo a piena forza su tutti e quattro i leg. Il test non viene indebolito, viene escluso dal solo job di misura.

### Controllo negativo sulla config reale, suite intera

Il requisito era dimostrare che la verifica FALLISCE, non che una percentuale scende. Quattro varianti, config reale, suite intera, sentinella risolti via AST:

    patch = ["subprocess", "_exit"]   19 file combinati   actions:49 True   sitecustomize:67 True
    patch = ["subprocess"]             5 file combinati   actions:49 False  sitecustomize:67 False
    patch = ["_exit"]                  1 file combinato   actions:49 False  sitecustomize:67 False
    patch = []                         1 file combinato   actions:49 False  sitecustomize:67 False

Entrambi i valori sono portanti e nessuno dei due basta da solo. Con il solo `subprocess` i figli avviano coverage ma perdono i dati a `os._exit`, e infatti i file combinati scendono da 19 a 5.

### Costo della strumentazione, rimisurato a carico basso

Una misura precedente dava 10.47s contro 15.87s, ma era sporcata dal carico della macchina. Rimisurate di seguito nella stessa sessione: baseline non strumentata 723 passed in 4.42s, sotto coverage 722 passed e 1 deselected in 7.35s. Circa +66% di wall clock, suite verde.

Nessun file `.coverage*` è comparso dentro il checkout in nessuna delle esecuzioni, perché `COVERAGE_FILE` punta a una directory temporanea esterna. Verificato con `find`, non con `ls`.

## Gate /simplify, quattro angoli in parallelo, 2026-09-17

Angoli: reuse, simplification, efficiency, altitude, sul perimetro delle sole quattro path della tranche.

**Correzione applicata perche' un commento era smentito dalla mia stessa misura.** Il commento sui sentinella sosteneva che `actions.py:49` fosse raggiunta "in-process e nei figli" e che fosse "l'unica riga che richiede entrambe le meta' della configurazione insieme". Verificato: la riga sta dentro `if kind == "kill":` e termina il processo dove si trova, quindi non e' in-process; e il controllo negativo a quattro varianti mostra che **entrambi** i sentinella vanno a MISS insieme sotto ogni lista patch rotta, quindi nessuno dei due e' piu' robusto e nessuno dei due dice QUALE impostazione e' saltata. Un commento contraddetto dall'evidenza e' un difetto vero, non una questione di stile.

La motivazione sostitutiva, verificata contro `tests/test_kill.py:16` e `tests/test_sitecustomize.py:80`: i due sentinella coprono un asse diverso, cioe' **il modo in cui il figlio viene creato**. `run_action` si raggiunge via `multiprocessing.Process` (forkserver su 3.14, fork prima); `_refuse` si raggiunge via exec di un interprete nuovo. Una terza voce si guadagna con un terzo modo di creare un figlio, non con un terzo `os._exit`.

**Altre correzioni:** rinominati `SENTINELS` in `EXIT_SENTINELS` e `resolve_sentinel` in `resolve_exit_line`; import di `CoverageData` dal nome pubblico `coverage` invece che da `coverage.sqldata`; deduplicata la stringa di versione in `check_the_tool_is_here`; appiattito il loop dei sentinella; tolte tre ripetizioni di prosa fra docstring e messaggi di errore. Costo della strumentazione e costo della guardia di deselezione rimisurati da me invece che citati dall'agente: 0.19s contro 2.5s sulla spawn di preflight.

**Skip motivati, non rimandati in silenzio.** Due hanno prodotto un task nello stesso turno, come richiesto: TASK-133 (helper di sottoprocesso duplicati fra i due script in `scripts/`, la meta' del lavoro cade sul file congelato `verify_artifacts.py`) e TASK-134 (se riformulare il test deselezionato sotto strumentazione, il file appartiene a un altro agente). Gli altri sono rifiuti ragionati e restano tali: la misura su `source_pkgs` resta nel commento di `pyproject.toml` perche' nessuno ha il documento aperto mentre modifica la config; i commenti del workflow restano perche' la CI si legge senza il repository davanti; il ramo `capture` dentro `run()` resta perche' due righe sono un'assicurazione a buon mercato contro la perdita silenziosa dell'output.

### Dettaglio trovato rimisurando, che cambia una riga del documento

Il comando non strumentato documentato aveva smesso di funzionare: nessuno dei due interpreti di sistema riesce a importare il pacchetto, e da' 18 errori di collection. Non esiste nessun finder `__editable__.pyteman*` in `~/.local/lib/python3.*/site-packages` per nessuna versione, mentre i finder di altri tre progetti ci sono. Solo il venv `/tmp/covrun/venv` ha il pacchetto, via `__editable__.pyteman-0.1.0.pth`. Rieseguito li': **726 passed in 4.68s su Python 3.14.7**, che riproduce la cifra gia' documentata. La correzione quindi e' stata nominare l'interprete nel documento, non cambiare un numero.

Una rimisurazione dei tempi e' stata **scartata** invece che pubblicata: il carico della macchina e' salito a 18 a meta' misura e i due giri davano 6.18/18.41 e 23.82/38.82. E' esattamente la trappola contro cui il documento mette in guardia, quindi restano le cifre prese a carico vicino a 2.

### Stato riverificato dopo le modifiche

Driver: exit 0, output identico byte per byte alla baseline pre-modifica, 19 file combinati, TOTAL 1185 stmts / 52 miss / 440 branch / 26 partial / 95%, entrambi i sentinella `ok`. Controllo negativo a quattro varianti riprodotto esattamente. Suite packaging 16 passed. Residuo coverage dentro il checkout: 0 file.

### AC3 riformulato

Su indicazione esplicita del parent: il criterio ora dichiara la portata reale (i due canali testati) invece di promettere il rilevamento di qualunque figlio sfugga alla misura. Il segnale richiesto non e' indebolito, perche' il criterio continua a esigere che il controllo FALLISCA rumorosamente su righe eseguite, non che una percentuale scenda. AC4 verificato meccanicamente: nessun `fail_under`, `fail-under`, `--cov-fail` o `precision` in nessuna delle quattro path.

## Version floor corrected to 7.13.0, read off the wheels

The dispatch named `coverage>=7.12.1` as the tool requirement. That release
does not exist. `pip index versions coverage` lists 7.12.0 followed by
7.13.0, and `pip install coverage==7.12.1` answers `No matching distribution
found`. The correction is not cosmetic, because the number that does exist
nearby is a prerelease whose `version_info[:3]` is exactly `(7, 12, 1)`, so a
floor written at that tuple would have admitted it.

Downloaded the wheels and listed them rather than reading the changelog,
because this is precisely the range where the prose and the artifact
disagree:

    7.12.0     no .pth anywhere in the wheel
    7.12.1b1   coverage-7.12.1b1.data/data/lib/python3.14/site-packages/
               zzz_coverage.pth
    7.13.0     a1_coverage.pth at the archive root
    7.14.1     unchanged from 7.13.0 in this respect

The middle row is the trap. That prefix is the wheel data scheme with an
interpreter version baked into the path, so an installer does not place it in
site-packages the way it places a root-level `.pth`. The release therefore
ships something that looks like the subprocess fix and does not measure
children. 7.13.0 is the first release carrying the hook where it lands.

The floor now reads 7.13.0 in three places, all inside this tranche's
ownership: `MINIMUM_COVERAGE` in scripts/run_coverage.py, the comment on the
`[tool.coverage.run]` block in pyproject.toml, and the install step of the
coverage job in .github/workflows/tests.yml.

No upper bound, stated as a decision in the workflow comment rather than left
as an omission. What the job asserts is a contract on two named lines, not a
percentage, so a coverage release that broke child measurement would fail
loudly instead of drifting a number. A ceiling would buy a reproducible
report nobody reads and cost a red job on a release that is fine.

Reported to the dispatching session, since it corrects that session's own
instruction.

## Negative control re-run against the rewritten driver

The earlier four-variant control predated the `--rcfile` flag, so it was
re-measured rather than carried forward. Three broken patch lists, each
written into a copy of the configuration and run end to end:

    patch = ["_exit"]        730 passed, 87 missed, both sentinels MISS, exit 1
    patch = ["subprocess"]   730 passed, 74 missed, both sentinels MISS, exit 1
    patch = []               730 passed, 87 missed, both sentinels MISS, exit 1

Green half, same driver, real configuration: exit 0, 730 passed plus 1
deselected, 19 data files combined plus 5 skipped, TOTAL 1188 statements / 52
missed / 440 branches / 26 partial / 95 percent, both sentinels `ok`.

The suite stays green in every broken variant, which is the whole argument
for a contract check over a threshold. The missed-line counts make the same
point quantitatively. Against 52 missed in a healthy run, dropping `_exit`
while keeping `subprocess` loses 22 lines and lands at 93 percent, because
children that exit normally still flush at `atexit` and only the ones ending
in `os._exit` vanish. The other two variants lose 35 and land at 92 percent.
A reviewer watching a percentage would see a two-point drop and attribute it
to a deleted test. The sentinel check fails identically in all three cases.

The uninstrumented suite on the same interpreter is 731 passed, and the
difference from 730 is exactly the one test deselected under instrumentation.
Packaging suite 16 passed, 0 skipped.

## A child whose data never arrived

Added `check_combine_left_nothing_behind`, run between `combine` and
`report`. The reasoning is an accounting property of combine rather than a
guess: it deletes every file it consumed, including duplicates it skips, and
keeps only the ones that raised while reading, and it exits 0 either way. So
a surviving `.coverage.*` in the work directory after combine is by
construction a file combine could not read and discarded, which is what a
child killed mid-write leaves. The check re-reads each leftover through
`CoverageData` and reports what happened, so the failure names the cause
instead of asserting a count.

This is the check an implicit combine inside `report` would have made
impossible to write, which is why the explicit combine step stays.

## What the local counts do and do not predict

Every number above is a ceiling rather than a CI prediction, because this
machine satisfies four optional conditions that gate tests. Measured by
removing them one at a time rather than asserted:

    pandoc absent from PATH        724 passed, 7 skipped
    `markdown` not importable      730 passed, 1 skipped
    no non-UTF-8 locale available  one further test skips

The locale row is read from the skip condition and labelled as read, not
measured. fts5 is available here. `markdown` is not a dependency of the
package and is named in no install step, so its presence in CI would be an
accident. Documented in docs/coverage.md as the scope of the counts. No test
was touched.

## A measurement trap that produced a false red

Worth recording because it will catch anyone writing a harness around this
suite. Measuring the `markdown`-absent case from a `python - <<'PY'` heredoc
gave `1 failed, 729 passed, 1 skipped`. That failure was mine, not the
project's.

The chain, traced rather than guessed. Python 3.14 defaults multiprocessing
to forkserver where 3.11 through 3.13 default to fork. A forkserver child
rebuilds `__main__` by importing the main module by path, in
`spawn.import_main_path`. Driven from a heredoc, `__main__.__file__`
resolves to the literal `<stdin>` under the working directory, that file does
not exist, the forkserver dies with `FileNotFoundError`, and the parent sees
`ConnectionResetError: [Errno 104] Connection reset by peer`.

The identical code written to a real file at /tmp/covrun/hide_markdown.py
gives a clean `730 passed, 1 skipped`. Nothing in the project changed. The
trap is documented in docs/coverage.md as a warning.

This is also the reason the CI job pins `python-version: "3.14"` as a
literal rather than deriving it from the matrix. How a child is started is
exactly what this job depends on, and 3.14 is the only version the
arrangement has been measured on end to end.

## docs/coverage.md rewritten

Backed up first at docs/coverage.md.bak.1789632119, because the file is
untracked and git cannot restore it. New sections: the named configuration
and the cleared environment, the version floor with the wheel table above,
the post-combine leftover check, and the scope of the local counts. The
sentinel section now covers both failure modes that defeat line numbers, the
duplicate definition and the nested scope. Checked mechanically for the
prose constraints: no em-dash, no spaced-hyphen parenthetical, no line over
81 columns.

## Filed separately

TASK-135, priority High, label ci and blocker: GitHub removes Node20 from the
runners on 2026-09-23 with no fallback, and `actions/checkout@v4` and
`actions/setup-python@v5` both declare it. It hits both workflows. Not fixed
here, because publish.yml is outside this tranche's ownership and the repin
should be decided across both files at once.

## Correction to the note above: the Node20 claim was wrong

The block ending this file said TASK-135 was filed because GitHub removes
Node20 on 2026-09-23 "with no fallback", implying the jobs go red. That is
withdrawn. A peer session challenged the source, I read the primary artifact,
and the peer is right.

The runner does not fail an action that declares `using: node20`. It rewrites
it. Read at tag v2.337.0, the current release, `HandlerFactory.Create`
intercepts the node20 declaration, calls `NodeUtil.DetermineActionsNodeVersion`,
and records the outcome as `UpgradedToNode24Actions`. The branch that the
2026-09-23 flag flips is the first statement of that function:

    // Phase 3: Always use Node 24 regardless of environment variables
    if (requireNode24)
    {
        return (Constants.Runner.NodeMigration.Node24, null);
    }

No failure path for the declaration. The only failure branch nearby is the
unrelated ARM32 kill switch. Corroborating, and the part I should have noticed
unaided: runners have defaulted to Node24 since 2026-06-16, which is three
months ago, so these actions are already running on Node24 rather than about
to.

What I did wrong is worth recording because it is a repeatable mistake. I read
a removal date and inferred a failure mode from it instead of reading how the
consumer resolves the version. A date is not a mechanism. The tracker entry
now carries the withdrawal explicitly rather than a quietly edited claim, the
`blocker` label is gone, and the priority is Medium. The repin is still worth
doing and it is not urgent.

This changes nothing about the coverage tranche. TASK-135 was always out of
scope here and the workflow was not repinned.

## Review mirata: tre correzioni, ciascuna verificata sul sorgente di coverage

Non accettate sulla parola dell'agente di review. Ogni affermazione e' stata
riletta nel sorgente installato prima di toccare il codice.

**1. Un buco da falso PASS nella lista delle variabili ripulite.** La lista
nominava tre variabili e il commento sosteneva che nominare la configurazione
sulla riga di comando facesse da rete per le altre. Falso per due di esse.
`coverage/pth_file.py:10` arma l'hook di avvio con `if
os.getenv("COVERAGE_PROCESS_START") or os.getenv("COVERAGE_PROCESS_CONFIG")`,
cioe' **due nomi, non uno**, e quell'hook gira all'avvio dell'interprete prima
che argv sia analizzato, quindi `--rcfile` non puo' scavalcarlo. Peggio,
`COVERAGE_FORCE_CONFIG` e' applicata in `read_coverage_config` come passo 5,
dopo il file nominato (passo 2) e dopo gli argomenti del costruttore (passo 4,
dove atterra `--rcfile`), quindi **scavalca il file nominato in pieno**. La
lista ora ne conta cinque e il commento dichiara una portata stretta e vera.

`COVERAGE_CORE` NON e' stata aggiunta, ed e' una decisione. Il criterio della
lista e' la ridefinizione SILENZIOSA: uno scambio del tracer si presenterebbe
come un sentinella MISS rumoroso, che e' esattamente il segnale che questo
script esiste per produrre.

**2. Una corsa fra `report` e la lettura dei sentinella.** `coverage report`
non e' il passo di sola lettura che sembra. `coverage/cmdline.py:876-877`
esegue `load()` seguito da `combine(strict=False, keep=False)` e, a differenza
dell'azione combine esplicita alle righe 857-860, **non salva mai**; combine
cancella ogni file che consuma. Quindi un nipote sopravvissuto alla suite che
avesse scaricato i dati dopo il controllo sarebbe stato assorbito nella
percentuale stampata, cancellato dal disco e assente da una riapertura
successiva. Se avesse portato un sentinella, il fallimento avrebbe accusato la
lista patch e il file che lo smentiva sarebbe gia' stato rimosso. I dati ora si
leggono PRIMA di `report` e la funzione riceve le righe misurate invece del
percorso del file.

**3. Un invariante di packaging affermato e mai controllato.** Puntare
`COVERAGE_FILE` a una tmpdir assoluta vale solo per i processi che ereditano
quella variabile e la onorano. Aggiunto
`check_no_data_landed_in_the_checkout`, che gira fra combine e report. Il
predicato e' `p.name == ".coverage"` oppure inizia per `".coverage."`, non il
glob ovvio `.coverage*`: quello avrebbe intercettato anche `.coveragerc`, che
e' configurazione e non dati, e avrebbe fatto fallire un albero sano. Provato
non vacuo piantando `tests/.coverage.fakehost.999.111`, che lo fa scattare col
messaggio intero, mentre il solo `.coveragerc` lo lascia in silenzio. I file
trovati vengono lasciati sul posto di proposito: un file che questo script non
ha scritto e' evidenza su quale processo ha ignorato l'impostazione.

## Due errori miei, trovati verificando invece che assumendo

**Un controllo negativo che non era mai partito, e sembrava riuscito.** Avevo
invocato le tre varianti come `--rcfile=/tmp/negctl/$v.toml`. Tutte e tre
uscivano con 1 e il mio filtro grep non mostrava righe, che e' esattamente
l'aspetto del successo atteso. Sospettando che il codice di uscita da solo non
fosse una diagnosi, ne ho rieseguita una con l'output intero: `usage:
run_coverage.py [--rcfile PATH]`. Lo script vuole il flag separato da spazio,
quindi la suite non era mai stata eseguita e stavo per riportare come
controllo negativo un errore di sintassi.

La lezione e' generale e vale la pena scriverla: un codice di uscita non e' una
diagnosi, e un grep che filtra via il messaggio d'errore nasconde un
fallimento di utilizzo dietro quello atteso. Il fallimento atteso e quello
accidentale hanno lo stesso colore.

**Un'affermazione falsa sulla semantica dei sentinella, corretta dal parent.**
Avevo scritto che deselezionando anche un solo test di rifiuto il sentinella
sarebbe andato a MISS. E' falso: piu' test attraversano la stessa riga
`_refuse`, quindi perderne uno lascia il sentinella a `ok`. Il controllo e' un
test di ESISTENZA per riga, soddisfatto da almeno un figlio.

Verificandolo ho trovato un risultato piu' preciso della correzione stessa, e
asimmetrico. Misurato il 2026-09-17: **dieci** test in
`tests/test_sitecustomize.py` spingono un processo dentro `_refuse`, uno dei
quali parametrizzato e aggiunto da un agente concorrente mentre scrivevo. Ma
l'uscita di kill a `src/pyteman/actions.py:49` e' raggiunta da **esattamente
uno**, `test_kill_uses_os_exit_not_systemexit`; gli altri chiamanti di
`run_action` in `tests/test_actions.py` esercitano sleep, raise e pragma e non
attraversano mai quella riga.

Quindi oggi un sentinella e' sensibile alla perdita di un test e l'altro no, e
nessuna delle due sensibilita' e' promessa: basta aggiungere un secondo test di
kill domani perche' anche il primo diventi insensibile come il secondo. E' un
fatto sulla suite, non una proprieta' del controllo. La portata e' ora scritta
in AC3 e in una sezione dedicata di `docs/coverage.md`.

Nel documento ho corretto anche una mia prima stesura di quel paragrafo, che
diceva "nove test" e "parecchi test di kill". Entrambe le cifre erano
sbagliate e le ho sostituite contando, non ricordando.

**Numeri aggiornati in tutto il documento** dopo queste rimisurazioni: 735
passed non strumentata e 734 strumentata (erano 731 e 730), TOTAL 1192
statement e 442 branch (erano 1185 e 440). Aggiunta una cornice esplicita sul
perche' quei totali vanno letti come rilevazione di un giorno e non come cifra
che la CI deve riprodurre: il checkout e' lavorato da piu' agenti insieme e nel
corso della stesura il totale si e' mosso 1185, 1188, 1192 mentre i 52 missed
restavano fermi. Le cifre delle dipendenze opzionali sono invece state
ANNOTATE come prese su un albero da 731 test invece che riscritte, perche' una
rimisurazione non e' stata fatta e inventare la differenza avrebbe distrutto il
motivo per cui sono registrate.

## Un residuo mio che sarebbe stato pubblicato, trovato e bonificato

La regola che impone il backup prima di sovrascrivere mi aveva lasciato due
file in `docs/`. `MANIFEST.in` concede `recursive-include docs *` e l'unica
cosa che ripulisce e' `global-exclude *.py[cod] *.so *.log *.swp *~
.DS_Store`, che non copre `.bak.*`. Ho sospettato l'esito leggendo il manifest
e poi l'ho **misurato invece di assumerlo**, costruendo la sdist da una copia
pulita:

    pyteman-0.1.0/docs/coverage.md.bak.1789632119
    pyteman-0.1.0/docs/coverage.md.bak.1789633929

78 voci nell'archivio. Lo stesso grep su tutte le voci conferma in un colpo
solo anche l'altra meta' della mia lettura: i tre backup fuori da `docs/`
(`pyproject.toml.bak.*` alla radice, `.github/workflows/tests.yml.bak.*`) NON
ci sono, per due motivi diversi, cioe' la radice concessa solo per `include`
espliciti e `.github` non concesso affatto.

I due file sono stati **spostati** in `/tmp/covrun/docs-backups/` e non
cancellati, cosi' il percorso di rollback sopravvive senza un file che
verrebbe spedito. Ricostruita la sdist: 76 voci, zero corrispondenze su `bak`.
La differenza di 2 e' esattamente i due file. Nota correttiva a un blocco
precedente di queste note: il percorso `docs/coverage.md.bak.1789632119` li'
citato oggi non esiste piu' nel checkout, sta in `/tmp/covrun/docs-backups/`.

**La parte che vale piu' del residuo stesso.** La suite packaging passa 16/16
sia prima sia dopo lo spostamento, quindi non poteva vederlo. Il confronto e'
per EGUAGLIANZA fra l'archivio e un glob sull'albero, cioe' l'albero e'
insieme l'ingresso e l'oracolo: un file presente su entrambi i lati si
cancella. Quel controllo rileva una DIVERGENZA fra manifest e albero, mai
un'assunzione sbagliata condivisa dai due. E' lo stesso meccanismo che
`docs/packaging.md` gia' documenta per il filtro di estensione `*.py`,
ricomparso un pattern piu' in la'.

Non corretto qui: `MANIFEST.in` non e' nel perimetro di questa tranche.
Aperto **TASK-137** nello stesso turno in cui l'ho trovato, con l'evidenza
sopra e il requisito che il test futuro pianti il residuo prima di costruire
invece di derivare l'attesa dall'albero, altrimenti riproduce la stessa
vacuita'.

## Consegna congelata, 2026-09-17

    sha256  scripts/run_coverage.py
            aed206738a8167f7786e0e03b48f49b8354c4adb0f514f47865b9ab96a7900c7
    sha256  docs/coverage.md
            04134497e8a62020c8d2d8f43be977ad7aceefc7d015390e7215c3a0c21fa539
    sha256  pyproject.toml
            ab6944959388c903ac1c6c343d4143df0e298d002e5f5af09f676f2448f5c705
    sha256  .github/workflows/tests.yml
            d2e47e1aa4d41ec311230bfb8de860bf13f113f570c81efa1b3a267995285331
    sha256  dei quattro concatenati in quest'ordine
            7128d63fc92910787104c5d1d1da1c36e4a2752ebe4a8090459b4d239e77a2f3

**Verde**, `/tmp/covrun/venv/bin/python scripts/run_coverage.py`: exit 0, 19
file combinati e 5 saltati come duplicati, TOTAL 1192 stmts / 52 miss / 442
branch / 26 partial / 95%, entrambi i sentinella `ok`. Suite non strumentata
735 passed, packaging 16 passed.

**Rosso**, stesso driver con `--rcfile /tmp/negctl/<v>.toml` (flag separato da
spazio, non con `=`), rieseguito contro questi hash:

    patch = ["_exit"]        734 passed, 87 miss, 92%, entrambi MISS, exit 1
    patch = ["subprocess"]   734 passed, 74 miss, 93%, entrambi MISS, exit 1
    patch = []               734 passed, 87 miss, 92%, entrambi MISS, exit 1

La suite resta verde in tutte e tre, che e' l'intero argomento a favore di un
controllo contrattuale invece di una soglia: chi guardasse la percentuale
vedrebbe due o tre punti e li attribuirebbe a un test cancellato.

## Verifica indipendente del parent, 2026-09-17: APPROVED

Non una rilettura delle mie cifre. Il parent ha confrontato gli hash dei
quattro file prima e dopo, ha eseguito il driver positivo, e soprattutto ha
**costruito da se' le tre config temporanee** invece di riusare le mie,
invocandole con la sintassi corretta. Esito:

    positivo     exit 0, combine 19 / skipped 5, due sentinella OK, 95%,
                 nessuna soglia, 736 passed + 1 deselected
    _exit only   exit 1, DUE MISS, 736 passed + 1 deselected, nessun usage error
    subproc only exit 1, DUE MISS, 736 passed + 1 deselected, nessun usage error
    patch = []   exit 1, DUE MISS, 736 passed + 1 deselected, nessun usage error
    non strum.   737 passed

La parte che conta e' `nessun usage error`: e' la conferma esplicita che i
controlli negativi sono davvero PARTITI questa volta, cioe' che l'exit 1 viene
dalla verifica e non dal parsing degli argomenti. E' il difetto che avevo
introdotto io e che il parent ha ricontrollato invece di fidarsi della
correzione.

**Una differenza fra le due misure, registrata invece che appianata.** Io ho
misurato 734 strumentata e 735 non strumentata; il parent 736 e 737, a poche
ore di distanza sullo stesso albero. Il delta interno pero' e' 1 in entrambe le
rilevazioni, cioe' esattamente il test deselezionato sotto strumentazione. Le
due misure quindi non si contraddicono: concordano sull'unica quantita' che
questo task afferma, e differiscono di 2 sul totale assoluto perche' altri
agenti hanno aggiunto test nel frattempo. E' la conferma empirica, da un
osservatore indipendente, della cornice gia' scritta in docs/coverage.md: quei
totali sono una rilevazione datata, non una cifra che la CI debba riprodurre.
Per questo il documento non viene riallineato a 736/737, che invecchierebbero
alla stessa velocita'.

Confermata anche dal parent la portata dichiarata in AC3, cioe' canali testati
e non tutti i figli. TASK-137 giudicato reale ma non bloccante per coverage:
andra' in una tranche packaging distinta e non va anticipato qui.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Coverage dei sottoprocessi, misurata e resa verificabile senza introdurre nessuna soglia.

**Il problema.** Quasi tutto il codice interessante di questo pacchetto gira in un figlio, e due righe di produzione terminano con `os._exit`, che scavalca `atexit` ed e' proprio il meccanismo con cui coverage scrive i dati. Entrambe le rotture sono SILENZIOSE: la suite resta verde e la percentuale si muove di due punti, indistinguibili da un test cancellato.

**La consegna.** Quattro path: `pyproject.toml` (blocco `[tool.coverage.run]` con `source`, `branch`, `parallel`, `patch = ["subprocess", "_exit"]`), `scripts/run_coverage.py` (driver che impone cwd e ambiente, combina, controlla, riporta), `.github/workflows/tests.yml` (job `coverage` accanto alla matrice non strumentata, pinnato a 3.14 come letterale), `docs/coverage.md`. Il controllo non e' una soglia ma un contratto su due righe raggiungibili solo da un figlio, risolte via AST per simbolo e mai per numero di riga.

**Prova che il controllo non e' vacuo.** Con `patch` rotto in tre modi diversi la suite resta VERDE e il driver esce 1 con entrambi i sentinella MISS. Verificato due volte in modo indipendente: da me e dal parent, che ha costruito da se' le config temporanee e ha confermato l'assenza di usage error.

**Correzioni sostanziali emerse strada facendo:** il floor di coverage e' 7.13.0 e non 7.12.1, che non esiste sull'indice, letto dai wheel perche' 7.12.1b1 spedisce l'hook sotto un percorso data-scheme che non atterra; `source` per percorso e non `source_pkgs` per nome, perche' `sitecustomize` gira come modulo top-level e nessun prefisso `pyteman` lo vede mai; lettura dei dati PRIMA di `report`, perche' `report` esegue un combine implicito che cancella i file; cinque variabili d'ambiente ripulite e non tre, perche' l'hook di avvio e' armato da due nomi e `COVERAGE_FORCE_CONFIG` scavalca il file nominato.

**Portata dichiarata, non promessa in eccesso.** Test di esistenza per riga, soddisfatto da almeno un figlio. Provato end to end solo su 3.14, nessuna affermazione sui leg 3.11/3.12/3.13. Misurato: dieci test raggiungono `_refuse`, esattamente uno raggiunge `actions.py:49`.

**Aperti altrove:** TASK-133 (helper duplicati fra i due script), TASK-134 (il test deselezionato sotto strumentazione), TASK-137 (`global-exclude` non copre i backup, che finivano nella sdist). Nessun commit, nessun test di altri agenti toccato.
<!-- SECTION:FINAL_SUMMARY:END -->
