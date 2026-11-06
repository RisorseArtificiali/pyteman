---
id: TASK-1
title: >-
  RT-01. Fallire in modo chiuso e atomico quando l'attivazione richiesta non
  riesce
status: Done
assignee:
  - '@pyteman-rules-opus5'
created_date: '2026-09-16 12:20'
updated_date: '2026-09-17 00:13'
labels:
  - audit-2026-09-16
  - opus-5
  - rt
  - confirmed
milestone: m-0
dependencies:
  - TASK-7
references:
  - 'src/pyteman/sitecustomize.py:17-25'
  - 'src/pyteman/patcher.py:40-49,101-112'
documentation:
  - doc-1
  - doc-2
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P1, CONFIRMED, aperto.

**File:** `src/pyteman/sitecustomize.py:17-25`, `src/pyteman/patcher.py:40-49,101-112`.

**Evidenza:** subprocess con YAML privo di id, espressione `when: "("` o directory del log inesistente stampa un errore di sitecustomize ma esegue `WORKLOAD_RAN` con exit code zero. Il marker mancante è già fail-closed; gli altri errori non lo sono. L'installazione può inoltre modificare import hook e primi target prima del fallimento di una regola successiva.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 subprocess per YAML mancante/malformato, log non apribile, espressione invalida su prima o seconda regola e setup valido.
- [x] #2 Nei casi invalidi il corpo del programma non parte, non restano patch parziali nella API programmatica e la diagnostica identifica regola/fase.
- [x] #3 Il caso senza PYTEMAN_RULES resta inerte.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Proposta iniziale da verificare sul codice corrente, non una correzione già applicata.

preflight e compilazione di tutto il ruleset prima dell'installazione; rollback delle mutazioni se una patch fallisce; quando PYTEMAN_RULES richiede attivazione, diagnostica chiara e uscita nonzero stabile per qualsiasi fallimento iniziale. Non utilizzare semplicemente SystemExit dentro sitecustomize.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: CFG-01 per validazione; lavorare in sequenza sul codice condiviso.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.

Nota di coordinamento da TASK-7 (CFG-01), 2026-09-16. NON e' lavoro svolto su questo task.

CFG-01 ha alzato l'urgenza di questo task invece di ridurla. Verificato attraverso il percorso di avvio reale (PYTHONPATH su `src/pyteman`, variabile PYTEMAN_RULES, sitecustomize importato all'avvio): quando `load_rules` alza RuleError, l'errore arriva PRIMA di `install()`, quindi `sys._pyteman` non esiste, nessun import hook viene installato e nessun target viene patchato. Fin qui e' il comportamento voluto dal criterio #2 di CFG-01.

Il problema e' cosa succede dopo: il processo continua e termina con exit code 0. Il workload gira quindi SENZA strumentazione, e l'operatore riceve un run apparentemente riuscito che non ha iniettato niente. Prima di CFG-01 un ruleset malformato veniva in gran parte accettato e falliva al firing, cosa rumorosa; adesso viene rifiutato al load e il run diventa silenzioso.

Il numero di ruleset che imboccano questa strada e' cresciuto molto: CFG-01 rifiuta ora dieci classi di errore che prima passavano, fra cui countdown senza n, once_per senza key, chiavi sconosciute per refuso, e `when: false`. Il criterio "fallire in modo chiuso e atomico" di RT-01 e' quindi l'unica cosa che separa un rifiuto corretto da un esperimento nullo non segnalato.

Da notare per l'implementazione: `sitecustomize.py:16` mostra gia' il pattern corretto per questo caso, `os._exit(2)` con commento sul perche' `sys.exit` non sopravvive dentro `init_import_site`.

Evidenza aggiuntiva dal gate di TASK-7 (2026-09-16), trasferita qui da TASK-51 prima di archiviarlo come duplicato di questo task. NON e' lavoro svolto qui: e' la misura del MECCANISMO dietro l'exit 0 gia' descritto nella nota di coordinamento precedente.

Il punto in cui l'errore si perde e' `site.execsitecustomize`, che importa sitecustomize dentro un `try/except Exception` (in 3.14.7 sta a `<frozen site>:661`). Il RuleError e' una `Exception`, quindi viene catturato li': una riga va su stderr e l'avvio prosegue.

Misurato con due sitecustomize minimi su PYTHONPATH, per separare i due rami che il commento alle righe 13-15 distingue gia':

    sitecustomize che alza RuntimeError (Exception)
      stderr: Error in sitecustomize; set PYTHONVERBOSE for traceback:
      stdout: WORKLOAD_RAN
      exit code: 0

    sitecustomize che chiama sys.exit(2) (SystemExit, BaseException)
      stderr: Fatal Python error: init_import_site: Failed to import the site module
              ... SystemExit: 2
      stdout: (niente, il workload NON parte)
      exit code: 1

Due conseguenze per questo task.

1. **Il commento a `sitecustomize.py:13-15` e' ACCURATO e va lasciato stare.** Dice che `sys.exit(2)` viene ingoiato, che un'eccezione che sfugge durante l'avvio finisce in `init_import_site`, e che si esce 1 a prescindere dal codice richiesto. La misura sopra lo conferma parola per parola: il codice 2 e' perduto e arriva 1. In una versione precedente della segnalazione avevo scritto che quel commento era fuorviante; era una conclusione sbagliata, tratta da una sonda sul ramo `Exception` che non tocca affatto il percorso `SystemExit` di cui il commento parla. `SystemExit` deriva da `BaseException`, quindi il `except Exception` non lo intercetta e i due rami non sono confrontabili.

2. **Sostiene la riga del piano che dice di non usare semplicemente SystemExit dentro sitecustomize.** Ora c'e' la misura del perche': SystemExit ferma davvero il processo, quindi fallisce chiuso, ma lo fa con un errore fatale dell'interprete e con il codice di uscita sostituito da 1. Chi cerca un codice stabile e distinguibile non lo ottiene per quella strada. E' esattamente il motivo per cui la riga 16 usa gia' `os._exit(2)` sul percorso del marker, che resta il modello da seguire per il criterio #2.

Questo non cambia la sostanza del task: il caso da chiudere resta il ramo `Exception`, dove oggi si esce 0 con il workload non strumentato.

## Claim RT-01 (2026-09-16), Opus 5

Preso in carico su via libera dell'orchestrator dopo l'APPROVED finale di TASK-7, che era la dipendenza dichiarata. Il refuso segnalato nelle note precedenti e' corretto: l'evidenza sitecustomize arriva da TASK-51, non da TASK-52.

Perimetro di proprieta' esclusiva concesso per questo task, piu' stretto del file intero dove indicato:

- `src/pyteman/sitecustomize.py`
- `src/pyteman/patcher.py`, SOLO per il preflight e il rollback che RT-01 richiede
- `tests/test_sitecustomize.py` e i nuovi test atomici
- `docs/rules.md`, per aggiornare il limite noto sull'attivazione
- `README.md`, SOLO la sezione Activation contract

Fuori perimetro e non toccati: `src/pyteman/runner/` e i suoi test, `pyproject.toml`, i workflow. RT-02 e RT-05 non vengono anticipati salvo il minimo che RT-01 richiede per stare in piedi.

Punto di partenza gia' stabilito e da non ri-derivare: il meccanismo dell'exit 0 e' misurato e sta nelle note sopra. `site.execsitecustomize` importa sitecustomize dentro `try/except Exception`, il RuleError e' una Exception e viene inghiottito li'; il workload prosegue non strumentato e il processo esce 0. Il ramo SystemExit ferma davvero il processo ma con errore fatale dell'interprete e codice sostituito da 1, quindi non e' la strada per un codice stabile: `sitecustomize.py:16` usa gia' `os._exit(2)` sul percorso del marker ed e' il modello da seguire.

Primo passo, prima di scrivere qualunque correzione: riprodurre sullo stato corrente tutti i casi del criterio #1 (YAML mancante, YAML malformato, log non apribile, espressione invalida sulla prima e sulla seconda regola, setup valido, e il caso senza PYTEMAN_RULES) come sottoprocessi reali, non come chiamate in-process, e registrare exit code e stdout di ciascuno. Il caso dell'espressione invalida sulla SECONDA regola e' quello che decide se serve il rollback o basta il preflight.

## Riproduzione sullo stato corrente (criterio #1), fatta prima di scrivere codice

Sette sottoprocessi reali, avvio via PYTHONPATH su `src/pyteman`, interprete dell'audit env. Non chiamate in-process: il comportamento sotto esame vive dentro `site.execsitecustomize`, che esiste soltanto all'avvio dell'interprete.

```
no-env             exit=0  WORKLOAD_RAN 42  INSTRUMENTED False
yaml-missing       exit=0  WORKLOAD_RAN 42  INSTRUMENTED False   FileNotFoundError
yaml-malformed     exit=0  WORKLOAD_RAN 42  INSTRUMENTED False   yaml scanner error
log-unopenable     exit=0  WORKLOAD_RAN 42  INSTRUMENTED False   FileNotFoundError
expr-bad-rule-1    exit=0  WORKLOAD_RAN 42  INSTRUMENTED False   RuleError rule #0 (id 'r1')
expr-bad-rule-2    exit=0  WORKLOAD_RAN 42  INSTRUMENTED False   RuleError rule #1 (id 'r2')
valid              exit=0  WORKLOAD_RAN 42  INSTRUMENTED True
```

Tutti e cinque i fallimenti sono fail-OPEN: una riga su stderr, il workload gira non strumentato, exit 0. Il caso inerte (criterio #3) e' gia' corretto e va preservato: nessun effetto, nessuna diagnostica, exit 0.

## Il caso della SECONDA regola non e' quello che decide il rollback

Avevo scritto nella nota di presa in carico che `expr-bad-rule-2` avrebbe deciso tra preflight e rollback. La misura dice di no: `load_rules` valida l'INTERA lista prima di ritornare, quindi una regola invalida in qualunque posizione fallisce prima che `install()` venga chiamato. Nessuna mutazione, nessun rollback necessario da quel percorso. Le due regole nel fixture erano entrambe presenti e la seconda ha fallito con `sys._pyteman` assente, come le altre.

## La finestra di mutazione parziale sta altrove, ed e' reale

E' in `install()` piu' il ciclo di patch, non nel caricamento. Sonda in-process con due regole sullo stesso modulo, la prima su una funzione normale e la seconda su un attributo di un tipo C (setattr rifiutato):

```
hook installed after install(): True
force_patch_module raised: TypeError: cannot set 'bit_length' attribute of immutable type 'int'
victim.ok still wrapped   : True
import hook still installed: True
ledger self._wrapped       : [('victim', 'ok')]
-- after uninstall() --
victim.ok restored         : True
import restored            : True
```

Due conseguenze per l'implementazione:

1. `install()` chiama `p.install_hook()` come prima cosa (patcher.py:143-146), quindi l'hook su `builtins.__import__` e' gia' installato quando il primo target viene patchato. Se una patch successiva alza, restano sia l'hook sia i wrap gia' applicati. Questo e' esattamente il residuo che il criterio #2 vieta nella API programmatica.
2. **La primitiva di rollback esiste gia' e funziona.** `Patcher.uninstall()` (patcher.py:114-120) ripristina `builtins.__import__` e poi disfa ogni wrap in ordine LIFO dal ledger `self._wrapped`. La sonda lo conferma: dopo `uninstall()` sia il modulo sia l'import sono tornati agli originali. Quello che manca non e' il meccanismo, e' che nessuno lo chiama sul percorso di fallimento.

Quindi il lavoro di RT-01 e': preflight di tutto il ruleset prima di toccare qualunque cosa, un `try/except` attorno al ciclo di patch che invochi `uninstall()` e rialzi, e una diagnostica che nomini fase e regola prima di un `os._exit` con codice stabile.

## La API programmatica lascia patch parziali anche senza tipi immutabili

La sonda precedente usava un tipo C per far fallire `setattr`, che e' un caso di nicchia. Questa usa due funzioni normali e una `Rule` costruita a mano, cioe' il percorso che il criterio #2 nomina esplicitamente: `install()` accetta oggetti `Rule` che non sono mai passati da `load_rules`, quindi le loro espressioni non sono mai state compilate.

```
raised at PATCH time: SyntaxError: invalid syntax (<pyteman:b:when>, line 1)
victim2.ok wrapped : True
victim2.also wrapped: False
hook installed      : True
after uninstall, clean: True
```

`_make_wrapper` compila `when` e `fire.key` al momento della patch (patcher.py:47-49), quindi la prima regola viene applicata e la seconda alza. Restano un wrap e l'hook. Questo e' il caso centrale del criterio #2, e non richiede nessun tipo esotico per riprodursi.

## Direzione di implementazione, decisa sulla misura

Servono entrambe le meta' del piano, e per ragioni diverse:

- **Preflight**: compilare ogni `when` e ogni `fire.key` dell'intero ruleset PRIMA di qualunque mutazione. Sposta la classe di fallimento qui sopra da meta' patch a pre-patch, dove non c'e' niente da disfare, e permette un messaggio che nomina la regola.
- **Rollback**: il preflight non copre tutto. `setattr` puo' rifiutare per motivi che nessuna analisi statica vede (tipo immutabile, descrittore, `__slots__`), quindi il ciclo di patch va comunque avvolto in un `try/except` che chiami `uninstall()` e rialzi. `uninstall()` esiste gia' ed e' verificato: entrambe le sonde tornano allo stato pristino.

Vincolo da rispettare sul confine: oggi `install()` installa solo l'hook e il ciclo `force_patch_module` e' guidato dal chiamante, ed e' un comportamento documentato altrove (nota di TASK-4: `install()` da solo non applica patch ai moduli gia' caricati). Renderlo atomico cambiando `install()` per forzare sempre le patch romperebbe quel contratto. L'intenzione e' quindi un punto di ingresso atomico aggiuntivo, non una modifica della semantica di `install()` esistente, cosi' che i chiamanti attuali vedano lo stesso comportamento di prima.

## Implementazione RT-01 (2026-09-16, Opus 5): evidenza sullo stato corretto

Stessa batteria di sottoprocessi reali della riproduzione iniziale, rieseguita dopo la correzione, piu' due casi nuovi (marker e punto non patchabile). Interprete dell'audit env, avvio via PYTHONPATH su `src/pyteman`.

```
no-env               exit=0   workload_ran=True
valid                exit=0   workload_ran=True
yaml-missing         exit=2   workload_ran=False  loading rules: <path>: FileNotFoundError
yaml-malformed       exit=2   workload_ran=False  loading rules: <path>: ParserError
log-unopenable       exit=2   workload_ran=False  opening the firing log: FileNotFoundError
expr-bad-rule-1      exit=2   workload_ran=False  loading rules: <path>: RuleError: rule #0 (id 'r1')
expr-bad-rule-2      exit=2   workload_ran=False  loading rules: <path>: RuleError: rule #1 (id 'r2')
marker-missing       exit=2   workload_ran=False  marker check: marker file missing
unpatchable-point    exit=2   workload_ran=False  installing instrumentation: TypeError: cannot set 'bit_length' ...
```

Tutti e cinque i casi che nella riproduzione iniziale erano exit=0 con WORKLOAD_RAN sono ora exit=2 con il workload mai partito. Le due righe che NON devono cambiare non sono cambiate: `no-env` resta inerte (criterio #3) e `valid` resta funzionante, che e' la meta' che i soli test di rifiuto non proverebbero.

Le fasi diagnostiche sono cinque e sono tutte raggiungibili: `marker check`, `importing pyteman`, `loading rules`, `opening the firing log`, `installing instrumentation`.

## Il rifiuto nomina la regola, non solo la fase

Un `setattr` rifiutato arriva come `TypeError: cannot set 'bit_length' attribute of immutable type 'int'`, che nomina un attributo e non la regola che lo ha chiesto: inutile per un operatore con quaranta regole in un file. Il patch loop attacca la regola come nota PEP 678 sull'eccezione originale, invece di alzare sopra di essa, e sitecustomize la rende esplicitamente perche' `str(exc)` non mostra le note e su questo percorso nessun traceback viene mai stampato, dato che si esce con `os._exit`. Riga reale su stderr:

```
pyteman: refusing to start: installing instrumentation: TypeError: cannot set 'bit_length' attribute of immutable type 'int' | pyteman: while patching rule 'frozen' at builtins:int.bit_length
```

## Verifica indipendente del rollback (skeptic, 2026-09-16): REFUTED in senso stretto

Dopo i fix di review ho spedito un agente di refutazione con UNA sola claim: che `Patcher._patch` riscritto ripristini esattamente le wrap fatte da QUELLA invocazione, mai quelle di un'altra invocazione rientrante o concorrente, e pubblichi su `self._wrapped`/`self.applied` solo a modulo completato. Vincoli: sola lettura sul repo, scratch in /tmp, nessun subagente. Verificato a posteriori che il repo non e' stato toccato.

**Verdetto: REFUTED**, ma solo sulla clausola concorrente. Le altre due reggono, con riproduttori.

**Regge, la rientranza.** Un `_patch` annidato reale (import servito dall'hook mentre l'hook e' vivo) pubblica la sua wrap; il chiamante esterno fallisce dopo e ripristina solo la propria. Stato finale: esterno ripristinato, annidato ancora wrappato e funzionante, `_wrapped` e `applied` allineati, `uninstall()` successivo pulito con `refused == []`. L'ordine in `_wrapped` (annidato prima dell'esterno) coincide con l'ordine cronologico reale, quindi l'unwind `reversed()` e' corretto.

**Regge, la pubblicazione a successo.** Nessun percorso di eccezione ordinario fra i due `extend`. Resta una finestra per eccezione asincrona fra le due righe, con raggio limitato: `_wrapped` pubblicata e `applied` no, quindi `uninstall()` ripristina comunque e solo il report sotto-conta. L'ordine attuale e' quello giusto; invertirlo lascerebbe una wrap non ripristinabile. Annotata su TASK-58.

**Il difetto che dicevo di avere corretto era reale.** La variante a indice (`mark = len(self._wrapped)` piu' `del self._wrapped[mark:]`) reimplementata su una sottoclasse e messa nello stesso scenario perde la wrap annidata: `inner still wrapped? False`, `_wrapped: []`, mentre `applied` continuava a elencarla. La riscrittura chiude questo.

**Cade, la clausola concorrente.** T2 completa e pubblica la sua wrap sulla slot; T1, che aveva letto lo stesso original PRIMA, scrive il proprio wrapper, fallisce su una regola successiva e ripristina l'original salvato: la strumentazione che T2 aveva completato e pubblicato sparisce. Il rollback ha scelto le slot giuste e ha comunque distrutto il lavoro di un'altra invocazione. La lista locale da' l'INSIEME corretto di slot, non la proprieta' esclusiva della slot.

## Cosa e' cambiato in risposta al REFUTED

Nessun cambiamento di comportamento: la riscrittura di `_patch` resta, perche' il difetto che chiude e' verificato reale e le due clausole che reggono sono quelle per cui e' stata fatta. Quello che era sbagliato era cosa AFFERMAVO, in tre punti, tutti corretti.

1. **Commento in `_patch`.** Spiegava perche' lo schema a indice era rotto e si fermava li', lasciando il lettore concludere che la lista locale chiudesse anche il caso concorrente. Aggiunto il confine esplicito: la lista locale da' l'insieme giusto di slot da disfare, non la proprieta' esclusiva della slot, e sotto thread un rollback corretto puo' comunque cancellare la wrap di un'altra invocazione.

2. **`docs/rules.md`, limite noto.** Diceva "cio' che e' atomico sotto thread e' il ROLLBACK": falso come scritto, e descriveva per giunta un meccanismo che il codice previene davvero. Avevo scritto che due thread producono un wrapper che ne wrappa un altro con i fire contati due volte. Non succede: se un thread ha gia' fatto `setattr`, l'altro rilegge quel wrapper, la guardia `_pyteman_state` scatta e salta la regola. La corsa reale e' che entrambi leggono lo STESSO original non wrappato e passano entrambi la guardia, con un wrapper orfano e l'ultimo scrittore che vince. Paragrafo riscritto sul meccanismo misurato, inclusa la riga che dice esplicitamente che il conteggio dei fire NON e' fra le conseguenze.

3. **TASK-58.** Titolo e descrizione riscritti sullo stesso errore: non e' "doppio wrap", e' check-then-act non sincronizzato sulla slot. Tre conseguenze osservate, piu' la seconda corsa distinta trovata dalla verifica: `uninstall()` fa `reversed()` (che fissa l'indice di partenza alla creazione) e poi `clear()`, quindi una wrap pubblicata da un `_patch` concorrente durante il restore non viene ne' ripristinata ne' ricordata. Criteri di accettazione portati da 5 a 7.

Filato inoltre **TASK-62** (Low): `uninstall()` svuota `_wrapped` ma non `applied`, quindi dopo un uninstall il patcher elenca strumentazione non piu' installata. Verificato pre-esistente con `git show HEAD:src/pyteman/patcher.py`, non introdotto da RT-01, e fuori perimetro di questo task.

## Criteri di accettazione

Tutti e tre soddisfatti, con un confine dichiarato sul #2.

- **#1**: nove sottoprocessi reali nella tabella sopra, che coprono YAML mancante e malformato, log non apribile, espressione invalida su prima e su seconda regola, e il setup valido.
- **#2**: nei casi invalidi il workload non parte (exit 2, `WORKLOAD_RAN` assente), la API programmatica non lascia patch parziali, e la diagnostica nomina fase e regola. **Confine**: questo vale sul percorso monothread, che e' quello che il task riproduce e che l'attivazione usa davvero, dato che avviene durante lo startup. Sotto thread concorrenti il residuo parziale e' possibile per la corsa di TASK-58, che e' pre-esistente, ora dichiarata in `docs/rules.md` e tracciata. Non e' dichiarata coperta.
- **#3**: `no-env` resta inerte, exit 0, niente su stderr, e un test separato verifica che ne' `typing` ne' alcun modulo `pyteman` finisca in `sys.modules`.

Batteria di test di proprieta': 252 passed. Comando: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 <audit-env>/bin/python -m pytest -q` con `--ignore` sui quattro file dell'altro agente (`test_matrix.py`, `test_matrix_identity.py`, `test_matrix_results.py`, `test_report.py`).

## Round CHANGES REQUESTED (2026-09-16, Opus 5): i due percorsi di fallimento riprodotti, piu' un terzo trovato riproducendoli

Entrambi i rilievi dell'orchestrator sono stati riprodotti prima di correggere, come chiesto. Nel riprodurli e' emerso un terzo difetto della stessa famiglia che nessuno dei due nominava e che era la causa REALE del primo: le due correzioni ovvie non lo avrebbero chiuso.

### (1) Il ramo except di `_patch` perdeva i refusal locali

Riprodotto: modulo `ModuleType` sottoclassato con `f` patchabile ma restore dell'originale rifiutato, piu' una seconda regola su `int.bit_length` (tipo immutabile). `activate` alzava TypeError con la sola nota 'while patching', `f` restava wrappata e nessuna nota diceva che era rimasta. E' il terzo esito che sia README sia docs/rules.md escludono.

Corretto: `_restore` ritorna i refusal, `_patch` li passa a `_disclose` che li attacca all'eccezione ORIGINALE. Garanzia dichiarata per quello che e': non 'leave nothing behind' ma 'o niente residuo, o una nota che dice esattamente cosa'. `docs/rules.md` corretto da 'ogni voce rimanente e' comunque RIPRISTINATA' a 'comunque TENTATA', che e' quello che il codice fa davvero.

### (2) Il fail-closed era bucato PRIMA di `_refuse`, per ordine di valutazione

Riprodotto con moduli pyteman sintetici e un `load_rules` che alza un'eccezione il cui `__str__` alza RuntimeError: `exit=0`, `WORKLOAD_RAN` su stdout, una riga 'Error in sitecustomize' su stderr. Fail-OPEN, cioe' esattamente la classe che questo task esiste per chiudere.

La causa non era `_describe` in se': era che veniva valutato come ARGOMENTO di `_refuse`, quindi prima che il `try/finally` che garantisce `os._exit` fosse entrato. Corretto passando l'eccezione a `_refuse`, che la rende dentro la propria guardia. Questa regola governa tutto il percorso di rifiuto e non e' imposta da niente nel codice: filata come TASK-75.

### (3) Il difetto che i due rilievi non nominavano: `__str__` che ritorna una SOTTOCLASSE di str

Trovato riproducendo (1). `str(x)` accetta qualunque risultato che passi `PyUnicode_Check`, e quel check passa per le sottoclassi. Quindi `_text` restituiva sottoclassi di `str` intatte, e una sottoclasse porta con se' `__repr__` e `__format__`: il primo f-string del chiamante eseguiva di nuovo codice utente, DENTRO gli helper scritti per assorbirlo. `isinstance(name, str)` e' il predicato sbagliato perche' ammette proprio gli oggetti che lo sconfiggono.

Evidenza end-to-end, con gli helper vecchi rimessi al loro posto per monkeypatch sui globals del modulo (`/tmp/rt01probe/antivacuity.py`), quindi il codice vecchio era davvero nel percorso di `_patch`:

```
helper VECCHI: activate alza RuntimeError (il fallimento del REPORTING, al posto del TypeError dell'operatore), note: 0
helper NUOVI : activate alza TypeError   (il fallimento vero dell'operatore),                                 note: 1
```

Zero note significa che il wrap rimasto non veniva menzionato: di nuovo il terzo esito escluso dai documenti. Corretto normalizzando nei due helper (`type(x) is str`, e `str.__str__(s)` per le sottoclassi), non nei call site: cosi' la proprieta' e' del VALORE invece che una regola che ogni chiamante deve ricordarsi. Tutte e tre le asserzioni dei nuovi test falliscono contro gli helper vecchi, quindi i test non sono vacui.

### Degradazione stretta invece che larga

`_describe`: guardia sulla sola `join` sui `__notes__`, non sull'intera funzione. Una sottoclasse di `list` passa sia il try sull'attributo sia il type check e poi rifiuta di iterare; il fallimento e' nel CONTENITORE, non in una nota. Guardando solo la join, `text` (tipo e messaggio dell'eccezione) sopravvive e si perdono le sole note. Una guardia sull'intera funzione avrebbe buttato via piu' di quanto al reporting fosse chiesto di perdere.

### Un rilievo del reviewer REFUTATO, non corretto

Era stato segnalato che `compile()` puo' alzare `ValueError` su sorgente contenente NUL, non coperto dall'`except SyntaxError` di `_compile`. Verificato sull'interprete reale: `compile("\x00", "<t>", "eval")` alza `SyntaxError`, non `ValueError`. Il ramo esistente lo copre gia'. Niente da correggere e niente da filare. Registrato qui perche' un rilievo non riproducibile che sparisce in silenzio torna al prossimo giro.

Il reviewer di quel round non aveva lo strumento Bash e aveva marcato ogni rilievo come non riprodotto, dichiarandolo. Ogni rilievo e' stato quindi verificato a mano prima di agire: tre confermati e corretti, uno refutato.

### Composizione dei test: risposta alla domanda sul 252

Il 252 e' ESATTAMENTE i sette moduli, senza nessun altro modulo dentro. Contato per modulo, non stimato:

```
test_rules 183, test_targets 20, test_sitecustomize 17, test_activation_atomic 14,
test_rule_contracts 6, test_patcher 6, test_docs_rules 6                    = 252 passed
```

La batteria completa e' 282 passed. I 30 restanti stanno in sei moduli fuori da questo perimetro: test_report_escaping 15, test_actions 6, test_integrity 5, test_barriers 2, test_kill 1, test_firing 1.

Il totale di batteria e' un bersaglio mobile: l'altro agente sta aggiungendo test a `test_report_escaping.py` mentre questo lavoro procede, ed e' passato da 14 a 15 nel giro di poche ore. Il numero stabile da confrontare fra un round e l'altro e' quello dei sette moduli, non il totale.

Sulla misura di 237 riportata dall'orchestrator: e' anteriore ai 4 test aggiunti in questo round (2 in `test_sitecustomize.py`, 2 in `test_activation_atomic.py`). Gli 11 di differenza restanti non li so ricostruire senza la riga di comando esatta usata per ottenerli, e non li invento. Se il numero deve tornare, serve quel comando.

### Filati in tracker nello stesso turno in cui sono stati letti

Due rilievi del reviewer non sono stati corretti in questo round. Nessuno dei due e' un bug presente; entrambi sono esposizioni strutturali, e valgono come hardening, non come correzione.

- **TASK-74**: `activate()` chiama `p = install(rules, log)` FUORI dal proprio `try`. Verificato non essere un bug presente: dentro `install()` non viene eseguito niente dopo `install_hook()`, e `Patcher.__init__`, che puo' alzare perche' compila ogni espressione, gira PRIMA che l'hook sia installato. L'esposizione e' che una riga aggiunta in futuro dopo `install_hook()` lascerebbe l'hook installato senza handle per rimuoverlo, cioe' un fail-open che nessun test intercetterebbe.
- **TASK-75**: la regola 'mai rendere dentro un argomento di chiamata' e' scritta in tre commenti e imposta da niente. Entrambi i difetti trovati nei due round di review ne erano istanze. La correzione (2) ha chiuso il buco concreto passando l'eccezione; la correzione (3) ha chiuso l'altro rendendo il VALORE inerte, ma l'f-string resta valutato come argomento ed e' innocuo solo finche' ogni valore dentro passa da `_text`. Il suggerimento del reviewer era un `_note(exc, *parts)` variadico che renda dentro la propria guardia, trasformando la convenzione in una forma di API.

### Due suggerimenti del reviewer risolti con un meccanismo diverso

Registrati perche' la differenza e' deliberata e non una svista.

1. **`_note` variadico**: declinato in favore della normalizzazione negli helper. Il variadico avrebbe protetto UN call site; far tornare a `_text` uno `str` esatto rende inerte il risultato per TUTTI i chiamanti, presenti e futuri, perche' la garanzia diventa una proprieta' del valore invece di una regola da ricordare a ogni interpolazione.
2. **Guardia sull'intera `_describe`**: declinata in favore della guardia sulla sola `join`. Avvolgere tutta la funzione avrebbe degradato anche tipo e messaggio dell'eccezione, cioe' avrebbe buttato via piu' di quanto al reporting fosse chiesto di perdere. Il test `test_describe_survives_a_notes_container_that_will_not_iterate` asserisce entrambe le meta': `ValueError: real message` presente E `<notes unavailable>` presente.

## Round 2 di CHANGES REQUESTED (2026-09-16, Opus 5): tre rilievi riprodotti, tutti confermati

Il reviewer di questo round era di nuovo senza Bash e ha dichiarato ogni rilievo come analisi statica non riprodotta. Nessuno e' stato accettato su quella base: tutti e tre riprodotti sull'interprete reale prima di toccare il codice. Tutti e tre confermati.

### (1) `isinstance` non e' un test di tipo, e la guardia era essa stessa codice utente

La correzione del round precedente aveva convertito `_typename` e `_text` a `type(x) is str`. Era rimasto indietro un `isinstance(notes, list)` in `_describe`: stesso meccanismo, forma diversa (`list` invece di `str`), quindi nessuna delle ricerche fatte lo trovava.

Il meccanismo, misurato. `object_isinstance` in CPython, contro un oggetto il cui tipo non e' sottotipo del target, ricade a leggere `x.__class__` via `PyObject_GetOptionalAttr`, che sopprime `AttributeError` e propaga tutto il resto. Un `__class__` implementato come property che alza fa quindi alzare `isinstance` stesso:

```
isinstance(NoClass(), list)  -> RuntimeError: no class for you
type(NoClass()) is list      -> False
```

Quella riga stava fuori da OGNI guardia dentro `_describe`. End-to-end, prima della correzione:

```
stderr: pyteman: refusing to start: loading rules: /tmp/f1probe/work/r.yaml:
exit=2
```

Dopo:

```
stderr: pyteman: refusing to start: loading rules: ...: Sneaky:  | <notes unavailable>
exit=2
```

**Severita', dichiarata con precisione**: il fail-closed NON era riaperto. Il `finally` di `_refuse` e' incondizionato, quindi exit 2 e stdout silenzioso reggevano in entrambi i casi. Cio' che era rotto e' la promessa documentata che un input ostile costi le note e mai il tipo e il messaggio dell'eccezione davanti a esse. Degradazione, non fail-open.

Corretto a `type(notes) is not list`. Sweep successivo: era l'ULTIMO `isinstance` rimasto nei due file di proprieta'.

### (2) Un test che provava meno di quanto dichiarava

`test_refusal_holds_when_the_error_cannot_be_rendered` diceva di provare la correzione strutturale del round precedente, cioe' che la resa avviene DENTRO `_refuse` e non come argomento. Non la provava: `_describe` assorbe quell'input e ritorna senza alzare, quindi le sue asserzioni reggevano anche con la resa rimessa nell'argomento.

Misurato: `_describe(Unrenderable())` ritorna `'Unrenderable: <unprintable Unrenderable>'`, nessuna eccezione.

Il reviewer proponeva di dare al test un contenitore `__notes__` ostile. Quella proposta sarebbe diventata vacua a sua volta: quell'input sconfigge `_describe` SOLO a causa del bug (1), quindi appena `type(notes) is not list` e' atterrato avrebbe smesso di alzare. Le due correzioni si sarebbero annullate a vicenda in silenzio.

Sostituito con un test che inietta il fallimento invece di cercarlo: il `load_rules` finto sostituisce `_describe` con una funzione che alza, poi alza a sua volta. La garanzia sotto esame non e' 'nessun input sconfigge `_describe`' (affermazione su `_describe`) ma '`_refuse` esce 2 qualunque cosa faccia `_describe`' (affermazione su `_refuse`), e resta valida per quanto totale diventi la resa reale.

Non vacuita' provata per esperimento diretto. Con il call site temporaneamente rimesso a `_refuse("loading rules", f"{rules_path}: {_describe(exc)}")`, in un solo run:

```
VECCHIO test: passa
NUOVO   test: FAILED, expected exit 2, got 0
              stderr: Error in sitecustomize ... RuntimeError: describing the failure blew up
              stdout: WORKLOAD_RAN 1
```

Backup preso PRIMA del revert, file ripristinato e sha256 verificato identico dopo.

### (3) La prosa prometteva piu' di quanto il codice garantisse

Sia README sia `docs/rules.md` dicevano che l'esito e' 'o niente residuo, o un resoconto esplicito di cosa e' rimasto'. Esiste una terza forma.

Riprodotta per intero con un `HostileNotesModule` che rifiuta il `setattr` dell'attributo `g` e rifiuta qualunque restore di un non-wrapper:

```
raised: NoNotes : refuses to accept a wrapper for g
notes on it: 'not a list'
is f STILL WRAPPED? True
>>> something left behind: True
>>> any account of it:    False
```

Un'eccezione che ombreggia `__notes__` con un non-list fa alzare `add_note`, e `_note` lascia cadere la nota invece di sostituire il fallimento su cui l'operatore deve agire.

**Corretta la PROSA, non il codice.** Che `_note` ingoi e' il comportamento giusto: l'alternativa e' che il reporting alzi sopra l'errore vero. L'orchestrator ha vietato nuove feature, quindi la correzione e' dire la verita' in entrambi i documenti invece di inventare un canale di ripiego.

### Lacuna di copertura chiusa: quale regola nomina la nota

`current = rule` e' la prima istruzione del corpo del ciclo in `_patch`. Ogni test esistente fallisce AL `setattr`, l'ultima istruzione che puo' fallire, dove `current` e' corretto ovunque sia assegnato. Nessuno distingueva le posizioni.

Nuovo test con `symbol` non-str, che fallisce a `rule.symbol.split(".")`, il primo punto di fallimento del corpo. Due revert, con backup preso prima e sha256 verificato dopo ciascuno:

```
current = rule in fondo al corpo        -> 3 failed, 12 passed
current = rule appena prima di _make_wrapper -> 1 failed, 14 passed  (solo il nuovo test)
```

Il secondo e' quello che conta: il reviewer sosteneva che qualunque posizione fra la cima del corpo e la riga 225 fosse osservazionalmente identica. Non lo e', e il nuovo test e' l'unica asserzione della suite che lo vede. Con la posizione sbagliata la nota diceva `while patching rule 'first'`, nominando la regola che aveva funzionato: una diagnosi sbagliata, peggiore di nessuna diagnosi perche' si legge come una diagnosi.

### Filato nello stesso turno

**TASK-79** (Low): `_text(rule.id)` nel filename sintetico di `_compile` (patcher.py:24) non e' coperto; sostituirlo con `{rule.id}` lascia la suite verde. Difesa in profondita', non portante: il risultato e' solo un filename dentro un code object mai reso sul percorso di rifiuto. L'uso portante dello stesso helper e' il `!r` a patcher.py:244, che E' coperto.

Registrato e non filato: il hoist di `p.uninstall()` in `activate` e' non testabile per costruzione e non e' una lacuna.

Round 3 (/simplify Phase 2, four agents: reuse, simplification, efficiency, altitude).

Three defects found and fixed, each reproduced independently before any code was touched and each proved covered by mutation afterwards.

1. Coverage gap in sitecustomize._typename. The existing test drove a __name__ that SUCCEEDS and returns a hostile value; nothing reached the branch where the lookup itself raises, which is the branch the try exists for. Added test_typename_survives_a_type_whose_name_cannot_be_read to tests/test_sitecustomize.py, covering the raising metaclass property alone and composed through _text. Proof: deleting the try/except gives 1 failed, 19 passed with that test as the sole failure; restored gives 20 passed and sha256 f5e72aae8224525b61a450652a2c586e51d46bd02d7ab46b6dc9bb401ef2fe97 unchanged. sitecustomize.py has no net edit from this round.

2. Fail-open hole in the patcher rollback note (was patcher.py:244). The note was an f-string over rule fields evaluated as the ARGUMENT to _note, so the attribute access happened outside every guard. A rule whose id is a property that raises took the reporting down and the rollback disclosure below it never ran, which is the exact substitution _restore exists to prevent. Probe before: RAISED RuntimeError 'this id refuses to be read', NOTES None. Probe after: RAISED AttributeError (the real failure), NOTES ['pyteman: while patching a rule whose identity could not be read']. Fixed at depth rather than locally: _describe_rule renders each rule's identity in Patcher.__init__, where nothing is patched and no exception is unwinding, and the string travels in the plan. The handler now concatenates a value that is already a str. The shallow fix (wrap the f-string in a try) was rejected because it leaves the trap armed for the next note written in that handler. Degrades to 'a rule whose identity could not be read' rather than omitting the note, since silence reads as 'the loop never reached a rule'.

3. Generator desync introduced by this tranche itself. Patcher.__init__ built _plan by iterating the rules argument and then set self.rules = tuple(rules), consuming a caller-supplied iterable twice. Probe: plan entries 1, p.rules (), AGREE False. That is the alignment failure the plan was introduced to rule out, arriving through the code that builds the plan. Fixed by materialising self.rules first and building the plan from it. Covered by test_a_ruleset_handed_over_as_an_iterator_is_read_exactly_once; the one-token revert gives 1 failed, 360 passed with that test as the sole failure.

Also applied: a 91-column line rewrapped, the self.rules comment rewritten to state why the tuple is load bearing, one duplicated section banner in tests/test_sitecustomize.py deduped against the docstring 280 lines below it that told the same history, and the new degraded form added to the enumerations in docs/rules.md and the README Activation contract.

Skipped with reasons: efficiency F1 (group _plan by module in a dict) measures 6 microseconds at 100 rules per import and is not worth restructuring the patch loop inside an RT-01 tranche; efficiency F2 (merge two subprocesses in the shim tests) the agent itself declined to press, and separate failure attribution is worth 35 milliseconds; reuse agent's proposal to consolidate hostile fixtures into tests/hostile.py is outside this tranche. The simplification agent's 'six restatements of the evaluation-order rule' finding did not survive checking: grep found eight sites, six of which justify a different function signature or statement order, so they are local justification rather than duplication. Only the two test-side ones genuinely duplicated and those were deduped.

Deferred findings filed the same turn they were read: TASK-80, TASK-81, TASK-82. TASK-79 updated because the fix moved its patcher.py:244 reference to patcher.py:108.

Suite at the end of Phase 2: 361 passed (359 before this round plus the two new tests here; test_sitecustomize.py 20, test_activation_atomic.py 17). The count also moved by one from concurrent work in tests/test_report_escaping.py, which is outside this perimeter.

## Round 2 (orchestrator CHANGES REQUESTED) - findings reproduced

Both items were probed against the running code before any edit; neither was taken on report alone.

**Item (2), fail-closed holed before _refuse: NOT REPRODUCIBLE, already closed.** `_refuse` takes the exception (`exc=exc`), not a rendered string, and calls `_describe(exc)` at sitecustomize.py:62, inside the `try:` at :53 whose `finally:` at :66 runs `os._exit(2)`. A hostile `__str__` or `__notes__` therefore costs the message and never the exit. All four call sites (:198 importing pyteman, :202 loading rules, :206 opening the firing log, :212 installing instrumentation) pass `exc=exc`. Verified by reading the current bytes, not the docstring's claim about them.

**Item (1), first half, `_patch` ignores `refused`: already closed.** patcher.py:325 captures `refused = _restore(wrapped)` and :351 surfaces it via `_disclose(exc, refused)`.

**Item (1), second half, "poi perde il ledger locale": CONFIRMED.** Reproducer /tmp/ledgerprobe.py, a container sealed after exactly one setattr so the wrap succeeds and the undo refuses. Before the fix it printed `patcher._wrapped: []` and `C.m restored after uninstall? False` while `C.m` was demonstrably still wrapped. Causal chain, each link read in the source: `wrapped` is a local (:301); `_restore` returned `(container, name, exc)`, dropping `original`; `raise` (:352) skipped `self._wrapped.extend(wrapped)` (:353). Net effect: a callable stayed instrumented, recorded nowhere, and `uninstall()` - the only API that removes it - reported success with nothing to do even after the container stopped refusing.

**Second site, not in the report, found by checking whether the fix generalised.** `uninstall()` had the same shape: `_restore(self._wrapped)` followed by an unconditional `self._wrapped.clear()`, so a refused restore was reported in the return value and erased from the ledger in the same breath. A caller that handled the refusal had nothing to retry from.

## Round 2 - fix, regression, docs

**Fix placed at the mechanism rather than the two call sites.** `_restore` now CONSUMES its argument: descending index, `del entries[i]` only when the `setattr` returned normally, so what survives the call is exactly what is still wrapped. `_patch` publishes the remainder with `self._wrapped.extend(wrapped)` before re-raising (`applied` deliberately not extended: a rolled-back experiment must not read as one that ran). `uninstall()` drops the `clear()` and returns `_restore(self._wrapped)`. The ledger is correct by construction at every call site, present and future, because the only thing that shrinks it is a setattr that actually returned.

**Regression the fix caused, caught by the suite and fixed.** Three tests failed: with the strand correctly retained, `activate()`'s unwind retries it, re-refuses, and disclosed an identical note twice, so one stranded callable read as two. Closed in `_disclose`, which its own docstring already names as the single owner of that wording: a note already on the exception is not added again. The membership test is guarded because `in` falls back to the other operand's `__eq__` and `__notes__` holds whatever the exception's author put there. Known cost, stated in docs/rules.md: two distinct strands that render identically are reported once.

**Docs corrected where the fix falsified them.** docs/rules.md said a refused restore keeps the wrap "and nothing pyteman can do will remove it" - now false, so it states the retry contract instead. The thread-safety paragraph said a concurrent `uninstall` leaves a racing wrap "neither restored nor remembered"; with the clear() gone it is missed but kept. That claim was verified empirically (/tmp/concurrentprobe.py) rather than reasoned: an entry appended mid-walk is skipped by that pass, retained, restored by the next, and newest-first order is preserved (visit order third, second, first).

**Tests added/strengthened** in tests/test_activation_atomic.py: `test_a_wrap_the_rollback_could_not_undo_stays_in_the_ledger` and `test_uninstall_keeps_what_it_could_not_restore_so_a_retry_can_work` (both fail against the old code: the probe showed the exact assertions flipping), the consumption contract asserted in `test_restore_completes_the_unwind_when_one_entry_refuses`, and a comment on `test_activate_reports_a_rollback_it_could_not_complete` recording that its `== 1` now pins the dedup where it previously passed because the ledger reaching uninstall() was empty.

Simplify gate triage (agent findings A-F), all six resolved this turn.

APPLIED A. patcher.py _patch published its ledger from two copies of `self._wrapped.extend(wrapped)`, one per exit. Replaced by a single `finally:`, with `self.applied.extend(applied)` left after the try statement so it stays success-path only. Two reasons beyond deduplication. First, the bug this whole tranche exists to fix WAS an exit that forgot to publish, so two copies left that exact shape standing for a third exit to get wrong. Second, it closes a gap neither copy covered: `_restore(wrapped)` is the FIRST statement in the handler and _restore can raise (proven, see the IndexError below), which with the publish further down would discard the frame holding the only record of the strands. Ordering verified: on the success path `finally` runs when the try statement completes and BEFORE the following statement, so _wrapped is still extended before applied, which is the order an earlier round established as load-bearing. Full suite 516 passed, exactly as predicted.

APPLIED D. uninstall()'s third docstring paragraph re-derived _restore's consumption semantics. Trimmed to a pointer at _restore, keeping the caller-facing retry contract, which is unique to the public method and has a test named after it. The distinction used: delete the re-derivation, keep the promise, because a promise stated only in a private helper is one callers never read.

APPLIED E. Wrote the direct dedup test the agent correctly identified as missing; it was the only _disclose behaviour with no test of its own, and the one I had just rewritten. Three cases: the superset case (a strand disclosed, then disclosed again inside a larger set, appears exactly once overall), a repeat disclosure attaching no note at all rather than an empty one, and a refusal message containing the `; ` separator being disclosed TWICE. The last pins the direction rather than the mechanism: when the matching has to be wrong it must be wrong toward a visible duplicate, never toward a silently suppressed strand.

SKIPPED B, false positive. _HostileActionRule and UnreadableModuleRule fail at DIFFERENT PHASES: the former raises on `action` and so fails inside _make_wrapper with an earlier rule already wrapped, the latter raises on `module` and so fails at the module filter before the body. The substitution passes only because both happen to reach the handler. This module exists to tell phases apart, and there is already a dedicated test for the unreadable-module phase, so substituting would collapse two coverages into one.

SKIPPED C, false positive. _Sealable's budget cannot become _RefusingModule's name predicate. The wrap and the undo set the SAME name on the SAME container, so no name predicate can distinguish them; ordinality is the only thing that can. `_seal(Victim, 1)` is not an incidental count, it is precisely 'allow the wrap, refuse the undo', and both the metaclass docstring and the test docstring say so.

SKIPPED F, evaluated and load-bearing. The flagged line resolves, after the +24 shift from inserting _owner_name, to the `Descending index rather than reversed` paragraph in _restore. It does restate 'newest-first' from the docstring's opening line, but it does so to assert an EQUIVALENCE (same order as reversed) and then the mutation-safety property that motivates the choice. Removing the restatement removes the equivalence claim, which is the point of the paragraph.

Code-review round (reviewer without Bash, all four findings declared unreproduced). Each reproduced against running code before any edit; all four confirmed.

(1) ORDER-DEPENDENT TEST, confirmed. `test_uninstall_keeps_what_it_could_not_restore_so_a_retry_can_work` passed only after its neighbour ran. Alone: `TypeError: cannot set 'm' on a sealed container`, because its setup `setattr(Victim, "m", "WRAPPER")` ran against a budget of 0 and depended on the other test's teardown leaking a budget of 99. Fixed at the root, not by adding the missing line: `_Sealable` kept ONE counter on the metaclass, shared by every container in the module, so each result depended on execution order. Moved to per-container state written through `type.__setattr__` into `cls.__dict__` (the write must bypass `__setattr__` or it recurses into the guard it is configuring). Verified alone, alone-with-neighbour, and whole-module.

(2) DEDUP MATCHED WHOLE NOTES, confirmed end-to-end. Two disclosures, `Refuses.b` named in both, two strands reading as three. Composite-key dedup degrades silently to NO dedup: it only works when both writers see identical inputs, and they do not. `_patch` names the module it was working on; `activate()` names everything still wrapped, which is a SUPERSET whenever an earlier module stranded something too. Two different strings, both attached. Fixed to match per STRAND, splitting prior notes on the `"; "` separator `_disclose` itself wrote, so the comparison is exact rather than a substring search. A message containing the separator splits wrongly and double-discloses; that direction is deliberate and now tested, because a duplicated strand is visible to whoever reads the notes and a suppressed one is not.

(3) `uninstall()` CAN RAISE, confirmed. Reproducer: a container whose `__setattr__` re-enters `uninstall`. Real output `IndexError: list assignment index out of range`. Correction to the reviewer's prediction: the message identifies `del entries[i]` as the raiser, not the unpack `entries[i]`; both sit outside the per-entry guard, so the conclusion stands. `_restore` walks `range(len(entries)-1, -1, -1)`, computed ONCE, so a ledger that SHRINKS under it hands back an index the list no longer has. (`reversed(lst)` and that range are not interchangeable under mutation: the list iterator rechecks the bound each step and stops.) Fixed at `activate`, NOT at `_restore`. A bounds check in `_restore` was rejected because it would make the 'cannot raise' comment look true again while the index-shift race persisted. `activate` now calls `p.uninstall()` inside its own try/except and attaches whatever the unwind raises as a `pyteman: the rollback did not finish` note on the original, because the guarantee `activate` makes is 'the reason activation failed is what the operator has to act on', and that must not depend on `uninstall()` being infallible.

Side effect caught by the suite: breaking `uninstall()` in the new test also broke the only thing that removes the import hook, so the hook leaked into `test_a_refused_patch_is_not_reported_as_an_unparseable_signature`. A test that disables a cleanup mechanism inherits its responsibility; closed with `monkeypatch.setattr(builtins, "__import__", builtins.__import__)`, a no-op set that registers the current value for teardown.

(4) `activate()` DISCARDS THE PATCHER ON FAILURE, confirmed by reading. `p = install(rules, log)` is bound to a local and the failure path re-raises without returning it, so docs/rules.md's 'The entry stays on the Patcher, so uninstall() attempts it again' was not the general guarantee it read as. Corrected in the docs rather than the code (see the next note).

Defect found by my own probing, not by any review: the rollback note named the container's TYPE. `_disclose` interpolated `_typename(container)`, and `_typename` is `type(obj).__name__`, which is the right question about an exception and the wrong one about a container. A rule's container comes from walking `rule.symbol.split(".")`, so it is the CLASS for `C.m` and the MODULE for a bare `f`; the type of a class is `type` and the type of a module is `module`. Every note therefore read `type.m` or `module.f`, the same answer for every rule in a ruleset, and the single fact the note exists to carry (WHICH callable is still wrapped) was the part it dropped. Reproduced at /tmp/containernameprobe.py before touching anything.

Why no test caught it: an INSTANCE container is the one shape that renders usefully under `_typename`, and it is the shape every pre-existing test happened to build. Fixed with a new `_owner_name` helper at the point the name is CHOSEN, not at each call site: ask the object for its own `__name__`, fall back to `_typename` for an instance, which has none. Guarded exactly like `_typename` and for its reasons: the attribute access is user code, and a `__name__` that is a str SUBCLASS would run its own `__format__` where the caller interpolates it, so the result is returned only when `type(name) is str`. The safety property survives the fix: `_owner_name` reads an attribute and never calls `str`/`repr` on the container, so pyteman still does not render a container at the moment it has just demonstrated it is hostile.

Judged IN perimeter rather than a new feature: RT-01's guarantee is that a refused rollback discloses which callable is stranded, and `type.m` discloses nothing, so this completes the stated guarantee.

Regression it exposed, kept as evidence rather than papered over: `test_activate_reports_a_rollback_it_could_not_complete` asserted `"_RefusingModule.f" in notes[0]` and now fails, because the fixture is a `types.ModuleType` SUBCLASS and the note correctly reads `pyteman_atomic_victim_refusing.f`. The old assertion encoded the defect: it pinned a private test class name the operator has no way to connect to the `module:` in their own ruleset. Assertion corrected to the module name with a comment recording why.

Docs owed by code changes, all three landed in docs/rules.md: (a) the note format now says the container is named by its own `__name__` and by its type only when it has none; (b) the retry paragraph now qualifies that the retry belongs to whoever HOLDS the Patcher, meaning callers of `install()` and `force_patch_module()`, and that `activate()` is the exception because it raises rather than returning and its Patcher is a local, so the notes on the exception are all that survive; the same paragraph now describes the per-strand dedup and states the `"; "` double-disclosure as the deliberate direction; (c) the thread-safety limit now names the SHRINKING-list direction as the worse one, the `IndexError` it produces, and `activate()`'s guard. README needs no change: its only relevant sentence, "a note saying which attribute and why", was already accurate and is now more so.

Gate state: /simplify run and all six findings triaged the same turn (previous note). High-effort read-only code review dispatched on the final diff; result not yet in. Counts at this point, per module because the full-suite total is not comparable between rounds in this shared checkout: test_activation_atomic 33, test_sitecustomize 25, test_rules 183, test_targets 20, test_rule_contracts 6, test_docs_rules 6. Full suite 520, having moved 516 -> 521 -> 520 across the tranche; the movement is the OTHER agent editing tests/test_docs_integrity.py (+2) and tests/test_integrity_classification.py (100 -> 99) mid-session, both outside my perimeter and both confirmed by mtime. My own modules account for none of it.

High-effort code-review gate on the final diff (read-only reviewer, no Bash, every finding labelled reasoned-from-source). Verdict: no critical findings, and the four changes I asked it to attack hardest (the `finally` publish, activate()'s cleanup guard, `_owner_name`, the per-strand dedup) came back clean with arguments I checked and accept. Three findings, all reproduced or verified by me before any edit, all landed this turn.

(1) IMPORTANT, code + docs. `_restore` deleted by an index captured BEFORE user code ran. The descending walk was chosen so a delete could not shift an index still to be visited, and that argument only ever covered the loop's OWN deletes. `setattr` is user code; it can remove entries BELOW the cursor, which re-seats every index from the cursor up, so `del entries[i]` reached a different entry than the one just restored. RT-01 is what made it reachable: while every attempt succeeded the list shrank in step with the walk and nothing above the cursor could be mis-addressed, and a RETAINED refusal is exactly what breaks that lockstep, so the fix and the bug arrived together.

Reproduced at /tmp/staleindexprobe.py, and the outcome is WORSE than the reviewer described. It does not stop at one wrong delete: after the refused entry is removed the walk revisits the restored entry at its new index and carries on, and the ledger ends EMPTY. Measured final state: the refused callable still wrapped, its original recorded nowhere, and a second `_restore` returning `[]`. That is verbatim the state `_restore`'s own docstring says the consume-on-success rule exists to prevent, 'a wrap nobody records is a wrap nobody can remove, and uninstall() then reports success with nothing to do while an instrumented callable stays in the process'.

Fixed by capturing the tuple and deleting only `if i < len(entries) and entries[i] is entry`. `is` and not `==`: comparing the tuples compares their elements, and a container's `__eq__` is the same user code this loop is written to survive, so equality would put it straight back inside. Deliberately NOT a bounds check inside `_restore` making it re-entrancy-safe; that is the documented thread-safety limit and out of perimeter. The residual cost of a shift is now a restored entry lingering and a later uninstall writing an original over itself, which is idempotent.

Two regression tests added. `test_restore_deletes_what_it_restored_and_not_whatever_index_it_held` was verified to FAIL without the guard (`Ledger: []`) and pass with it, by temporarily reverting the guard and restoring it byte-for-byte, confirmed by sha256 f0914ec5178448cd132498f9c43ac01c97f02f70bb246db88636a3d0e8058fe2. `test_restore_does_not_compare_entries_with_equality` passes either way by design and is recorded as such: it pins the SHAPE of the fix, not the bug.

(2) IMPORTANT, docs only, and the choice is deliberate. When `p.uninstall()` raises inside activate()'s cleanup handler, the refusals `_restore` had already gathered die with the raising frame, so `activate` sets `refused = []` and discloses nothing about what is still wrapped. Confirmed by reading patcher.py:608-625 together with `uninstall` being exactly `return _restore(self._wrapped)`. NOT fixed in code: the only fix threads a caller-owned accumulator through `_restore` -> `uninstall` -> `activate`, and `uninstall` is public API, which 'niente nuove features, solo completare esattamente le garanzie RT-01' puts out of scope. Resolved in prose instead: the disclosure-contract paragraph previously enumerated exactly ONE hole (an exception whose `__notes__` is not a list) and now enumerates two, so the contract no longer reads as covering a path it does not. The thread-safety paragraph points at it as the source of the second hole.

(3) MINOR, docs only. `_owner_name` returns the container's real `__name__`, which is not always the spelling the rule used. Confirmed against the real fixture at tests/test_activation_atomic.py:38, `setattr(mod, "Frozen", int)` with rules written `symbol: Frozen.bit_length`, which reports `int.bit_length`; a multi-level path reports only the last container walked to. The sentence claiming the container is named by 'the name a rule's module: or symbol: already uses' was narrowed, both divergences named, and the reader pointed at the rule note for the rule's own spelling.

Also landed although the reviewer explicitly declined to file it: the dedup paragraph enumerated two ways the matching can be wrong, and a refusal message that VARIES between attempts, carrying a clock reading or a retry count, is a third. One sentence, same safe direction.

Not re-filed, already tracked: the check-then-act race and the destructive cross-invocation rollback (TASK-58), `applied` semantics across uninstall (TASK-62, TASK-94). The reviewer confirmed `applied` has no production reader, so its failure-path omission of a strand is a latent contract question belonging to TASK-94's live-state-versus-cumulative-record decision rather than a new finding.

Also worth recording from the review, because it is stronger than what the code claims for itself: the per-strand dedup cannot lose information at all. Suppression requires a strand's exact rendering to be a member of `already`, and every member of `already` is by construction a substring of a `_ROLLBACK` note already attached to the same exception, so a suppressed strand's text is still present verbatim where the operator reads it. That holds for both ways `already` can be seeded from outside `_disclose` (a note attached before pyteman saw the exception, and a singleton exception reused across activations).

Tests after all of the above: 534 passed, which was the prediction (520 + my 2 new + 12 from the other agent taking tests/test_docs_integrity.py from 39 to 51 at 00:29). My perimeter: test_activation_atomic 35 (was 33), test_sitecustomize 25, test_rules 183, test_targets 20, test_rule_contracts 6, test_docs_rules 6. A verification review of the delta is dispatched; hashes to follow once it settles.

Review round 3 (delta review of the finding-1/2/3 fixes): six findings, all reproduced against running code before fixing, all resolved.

(1) EXCLUSIVITY CLAIM WAS FALSE. The _restore docstring and docs/rules.md said the stale-index bug was reachable only because refusals are now kept. A concurrent _patch reaching `finally: self._wrapped.extend(wrapped)` (patcher.py:466) publishes entries above the cursor and creates the same slack. Replaying the pre-fix loop with ZERO refusals destroyed the record of a published wrap. Both passages now name both routes, and the sibling test docstring was amended to stop claiming the fix and the bug arrived together.

(2) 'IDEMPOTENT' WAS AN OVERSTATEMENT, and the truth is worse than the reviewer framed it. A removal below the cursor slides the restored entry DOWN onto an index the descending walk has yet to visit, so it is found again and restored a SECOND time inside the same walk; it does not linger for a later uninstall. A probe put a re-wrap in the window between the two writes and the second write took that wrapper off. So the residual cost is a destructive double write under the same race that shifts the index, not an idempotent no-op. patcher.py docstring and the thread-safety paragraph both rewritten to say so, and to say why it is still the better of the two outcomes (a forgotten strand is unrecoverable, this is not).

(3) UNREACHABLE DOCS EXAMPLE. docs/rules.md illustrated container naming with `Frozen.bit_length` against `Frozen = int`. setattr on an immutable type raises TypeError at patch time, so there is no ledger entry and no rollback note to misname. Replaced with a mutable alias plus a sentence saying why a built-in cannot serve as the example.

Review round 3, continued.

(4) UNSCOPED LEDGER CLAIM. docs/rules.md said flatly that what the Patcher holds is what is still wrapped, on the failure path as much as the successful one. True only while one thread writes to the ledger. Scoped, with a pointer to the concurrency limit below it.

(5) A REGRESSION TEST THAT COULD NOT FAIL. test_restore_does_not_compare_entries_with_equality handed `==` the entry that had just been restored. CPython's PyObject_RichCompareBool short-circuits on IDENTITY before dispatching __eq__ for Py_EQ, so that comparison never reaches user code and the test passed under both implementations, pinning nothing. Probed and confirmed: `==` reaches __eq__ only when index i holds a DIFFERENT entry. Rewritten so a mutation re-seats i onto a published entry whose container raises on comparison, arranged via the concurrent-publish route so the test does not depend on refusal retention either. Mutation-verified: is->== fails exactly this test; removing the guard fails the sibling test.

(6) A COMMENT WITH A WRONG REASON. It justified `len(entries) == 0` over `== []` by saying the latter would compare tuples. list.__eq__ short-circuits on LENGTH first, so it never reaches an element. Removed with the rewrite.

PROCESS FINDING, worth more than any of the above. The mutation test that proved the earlier fix used sed to swap `is` for `==` and back, then verified the source by sha256. `is` and `==` are the same byte length, both seds ran inside one second, and .pyc validation keys on source mtime (integer seconds) plus size. So the cache compiled from the MUTATED source was considered valid after the restore, and every test run for the next several minutes executed `==` bytecode while the source on disk read `is`. It surfaced as a regression test failing with __eq__ raised from a line containing no `==`, and a micro-probe proving `is` cannot call __eq__. sha256 of the source is not evidence about what is executing. Mutation tests now delete the .pyc after every swap and confirm the loaded bytecode by disassembly (IS_OP present) before trusting a result.

GATES after the fixes, on verified-correct bytecode: perimeter all green, test_activation_atomic 35, test_sitecustomize 25, test_rules 183, test_targets 20, test_rule_contracts 6, test_docs_rules 6. The full-suite total remains unusable as a metric here: it moved 20 -> 17 -> 15 failures across three consecutive runs in which I changed nothing, all of them in tests/test_docs_integrity.py, tests/test_integrity.py and tests/test_integrity_classification.py, which are the other agent's live edits. None of those modules reference rules.md, patcher or sitecustomize.

Round 2 of review-driven fixes (confirming reviewer on the final diff). Five findings, all reproduced against running code before any edit, plus four sub-threshold notes taken and one finding I generated myself.

F1 recoverability overclaim. The old text ranked the double restore as strictly better than a forgotten strand. The second write is setattr(container, name, original) with no test of what the slot holds, so it clobbers whatever is there; another actor's wrap is recoverable from the ledger that installed it, but a plain rebind nobody records (hot swap, hand-installed double) is lost as finally as a strand. Rewritten in patcher.py and docs/rules.md to justify the trade by REACH rather than severity: the double write harms only when something wrote to that slot between the two restores, where the mis-addressed delete stranded a wrap every time the shift happened at all.

F2 unscoped invariant in the _restore docstring. 'what survives the call is exactly what is still wrapped' was contradicted twenty lines lower by the shifted-index paragraph. Scoped to 'exactly while this call is the only writer', with a pointer to where it weakens to a superset. This is the same claim the docs already scoped last round; the source of truth had kept the stronger version.

F3 sibling test docstring credited the publish alone with stranding an entry. The range is built once, so an appended entry is simply never visited and stays recorded. Stranding needs the publish AND a removal below the cursor. Corrected.

F4 the bounds half of 'i < len(entries) and entries[i] is entry' was pinned by no test. Verified by mutation with the cache busted: deleting the bounds half leaves the entire 275-test perimeter green. Added test_restore_survives_a_ledger_that_shrank_to_the_cursor; under the mutation it is the only failure (275 passed, 1 failed), and the traceback shows the mutated line text, confirming the loaded bytecode.

F5 two prose lines pushed past the file's 80-column wrap by last round's appends. Rewrapped. The reviewer's stated premise that every other line wraps at or under 80 is false as measured: 13 lines exceed it, all Markdown table rows or one code-block line, which cannot wrap. One further 81-char prose line (rules.md:36) was rewrapped as well.

SELF-GENERATED finding, from probing F4 rather than from the review. The inline comment claimed the bounds test is 'for a list that shrank past i entirely'. That describes the case the guard CANNOT save: the loop opens each iteration with an unguarded entries[i], so a shrink leaving len < i raises IndexError on the next pass regardless. The guard is decisive for exactly one shape, len == i, where index i is one past the end and i-1 is still valid. Measured both shapes in /tmp/boundsprobe.py; comment corrected.

Sub-threshold notes also taken: the concurrent-publish route needs entries to be the shared ledger, since _patch passes a local list no other actor holds (confirmed at the finally that publishes via self._wrapped.extend); the docs scoping now names a re-entrant uninstall alongside another thread, because the test suite itself simulates the race re-entrantly and the old 'only thread' wording would have been false in its own scenario; the alias example now requires a container that accepts the wrap AND refuses the restore, since the note exists only on refusal; the residual 'idempotent' wording replaced; the equality test's final list assertion rewritten as a length check plus an identity check, so a future failure reports the ledger instead of tripping RaisesOnCompare while building its own message.

Perimeter after the fixes: test_sitecustomize 25, test_activation_atomic 36, test_rules 183, test_targets 20, test_rule_contracts 6, test_docs_rules 6. Predicted 276 before running and measured 276.

Round 3 of review-driven fixes. Three findings plus four sub-threshold notes, all prose; the reviewer confirmed the executable part of the change introduces nothing and hand-traced the new test as sound. Two of the three were claims I had written in round 2, both measured before correcting (/tmp/reachprobe.py).

R3-1 the reach argument named the wrong mechanism. I had written that a mis-addressed delete stranded a wrap 'every time the shift happened at all'. Measured by replaying the pre-guard loop: with an entry surviving above the cursor the shift mis-addressed the delete and left the ledger empty; with nothing surviving above, the walk was in lockstep, len equalled the cursor, and the unguarded delete raised IndexError instead. So every shift did cost something, by TWO mechanisms, and my sentence credited one of them with universal reach. The reach comparison itself survives and is now stated with both mechanisms named. This is also the same IndexError route the new bounds test pins, which the old sentence implicitly denied existed.

R3-2 the new test's docstring blamed activate() for losing the rule failure to an IndexError. It does not: activate() wraps p.uninstall() in its own try and attaches 'pyteman: the rollback did not finish' as a note on the original exception, and tests/test_activation_atomic.py:386-397 already pins exactly that ('TypeError and not IndexError: the failure outlives its own cleanup'). The displacement is real at other sites: _patch calls _restore from inside its except block, so an IndexError there propagates over the failure being handled, and direct callers of install()/force_patch_module() see uninstall() raise. What activate() actually pays is an empty refusal list, so its disclosure never names what is still wrapped, which the docs already call the second hole in the disclosure. Docstring re-aimed at the real sites and the real cost.

R3-3 off-by-one. 'cannot run at all once the list is shorter than i' is wrong: the subscript raises iff len <= i, and the shape this test produces, len == i, is not shorter than i. Changed to 'no longer than i'. The same docstring had been using one phrase for two different conditions.

Sub-threshold notes taken: 'caught by the read that opens the next iteration' changed to 'raises at', since nothing below activate() handles it; the second restore re-enters the container, so one that has stopped accepting turns that write into a refusal which is reported and kept for an attribute that IS restored, measured and now stated (a strand named that is not one, over-reporting rather than data loss); 'the slot still holds what the ledger says' inverted its referent, since the ledger records the original while the slot holds the wrapper; and the recoverability claim about another actor's wrap is now scoped, because if that actor wrapped OUR wrapper its ledger records our wrapper as the original.

SELF-CAUGHT while checking widths: my round-2 edit to the CONSUMED paragraph prepended words to an existing line and left it at 89 characters, the identical mistake round 2's finding 5 was about. Rewrapped.

Verification at the final hashes. Mutation re-run with the bytecode cache busted: deleting the bounds half gives 606 passed, 1 failed, the single failure being test_restore_survives_a_ledger_that_shrank_to_the_cursor. patcher.py restored byte-for-byte to 68b6ea21. Perimeter 25/36/183/20/6/6 = 276. Full suite 608 passed, 0 failed.

The full-suite total remains unusable as a cross-round metric in this shared checkout, now in the other direction: it read 607 and then 608 within this session with no change from me, the other agent having added a test in between. Earlier in the tranche it drifted 20 to 17 to 15 failures across three consecutive runs, also with no change from me.

Round 4 of review-driven fixes, prose only, plus one self-caught code comment. Five findings, two of them critical, all reproduced against running code before editing; two needed execution because the reviewer reasoned them by hand.

R4-1 CRITICAL, the new test's docstring named an unreachable call site. It said _patch calls _restore from inside its own except block, so an IndexError there displaces the rule failure, and that activate() is written against exactly that. Both halves are wrong and the file already contains the refutation. _patch builds `wrapped` as a method-local at patcher.py:422 and publishes it only in the `finally`, so no user code can hold a reference to shrink it; _restore's own docstring makes that argument for the publish route and I failed to apply it to the shrink route. And activate() guards only p.uninstall(), not p.force_patch_module(), so an IndexError escaping _patch's handler would arrive as the exception itself, already having replaced the rule failure inside _patch. Re-aimed at uninstall()'s call site on the shared ledger, which is the only route that reaches the guard.

R4-2 CRITICAL, docs/rules.md described pre-guard behaviour in the present tense. Lines 216-219 still said a removal 'leaves the walk indexing past the end and an IndexError comes out of the unwind itself'. My own guard falsifies that for a shrink to exactly the cursor, which is now survived, and the test asserts it. Rewritten to separate the two shapes: a shrink to the cursor is survived, a deeper one raises at the unguarded read opening the next pass rather than at the delete.

SELF-CAUGHT while confirming R4-2: activate()'s inline comment carried the identical stale claim ('indexes past the end'). Corrected and rewrapped. Found only because the finding sent me to read the handler rather than trusting the docs sentence about it.

R4-3 the doubled write's precondition contradicted the paragraph above it. 'Needs the shift AND another writer' is wrong now that the same passage also names a container that stops accepting between the two writes, which needs no other writer at all. The write needs only the shift; the harm needs either.

R4-4 the two-mechanism dichotomy was neither exhaustive nor correctly bounded. Executed (/tmp/thirdmech.py) rather than accepted, since the reviewer flagged it as hand-traced. Two corrections. A shift landing during a REFUSING setattr never reaches the delete, since the except branch skips it: it strands nothing and raises nothing, and costs a duplicate refusal, identical before and after this change; _disclose dedupes only against notes already on the exception (patcher.py:326), never within one batch, so that duplicate does reach the operator as one strand named twice in a single note. And the boundary is not 'an entry survives above the cursor' but survivors versus removals: measured k=1,s=0 IndexError; k=1,s=1 and k=1,s=2 mis-address; k=2,s=0 and k=2,s=1 IndexError; k=2,s=2 mis-address. So k=2,s=1 has an entry surviving above the cursor and still raises, which my stated condition got wrong.

R4-5 'a single concurrent removal below the cursor produces len == i' is contradicted two lines later by 'neither sibling reaches this'. The first sibling does exactly one removal below the cursor and leaves len 3 with i 2, because the retained refusal above holds the length up. Corrected to name lockstep as the condition.

INCIDENT, self-inflicted and recovered. Re-running the mutation check I reverted the mutated line with `git checkout -- src/pyteman/patcher.py`. HEAD's patcher.py is 146 lines and the working tree's is 673, so that wiped the whole uncommitted tranche, RT-01 and the APPROVED TASK-7 work both. Recovered in full from the timestamped backup the same command had taken before mutating, and proved exact by the pre-mutation sha256 the script printed: restored file is byte-identical at 314e1133. Nothing was lost and nothing outside patcher.py was touched. The lesson is recorded: undo a deliberate mutation from the backup copy, never from git, because HEAD is never the state to return to while a tranche is uncommitted.

Verification at the final hashes. Perimeter 25/36/183/20/6/6 = 276, all passing, re-collected as 276. Full suite 606 passed, 0 failed. Mutation re-run with the cache busted: deleting the bounds half gives 1 failed, 605 passed, the single failure being test_restore_survives_a_ledger_that_shrank_to_the_cursor. Widths clean; no edited line exceeds its limit.

The full-suite total moved again, 608 to 606, and it is again not mine: the other agent touched tests/test_integrity.py at 01:43, tests/test_docs_integrity.py and src/pyteman/sqlitekit/integrity.py at 01:38, and tests/test_integrity_classification.py at 01:37, all after the 608 reading, while my perimeter re-collects at exactly 276.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
RT-01 chiuso: l'attivazione richiesta ora fallisce in modo chiuso e atomico.

Fail-closed. sitecustomize non lascia piu' partire il workload quando la configurazione richiesta non e' utilizzabile: YAML mancante o malformato, log non apribile, espressione `when` non compilabile. Il caso senza PYTEMAN_RULES resta inerte come prima. La diagnostica identifica regola e fase e sopravvive a oggetti ostili: `_typename`/`_text` rendono inerti `__str__`, `__repr__` e `__notes__` dell'utente, cosi' un errore che rifiuta di essere descritto non puo' convertire un rifiuto in un avvio. Gli helper sono duplicati in sitecustomize e patcher di proposito, perche' sitecustomize non deve importare nulla di pyteman quando e' inerte e la sua prima fase di fallimento e' proprio "import di pyteman".

Atomicita'. `_restore` disfa i wrap dal piu' recente, non si ferma al primo rifiuto, e RIPORTA cosa ha rifiutato invece di ingoiarlo; ogni restore ha il proprio handler perche' gira durante l'unwind di un'altra eccezione, e cattura BaseException perche' un KeyboardInterrupt tra due setattr lascerebbe il modulo mezzo ripristinato, che e' esattamente cio' che questa funzione esiste per evitare. Niente viene RESO dentro il loop: le refusal tornano come oggetti e `_disclose` le descrive a loop finito, cosi' un oggetto ostile non puo' abortire l'unwind a meta'. `entries` e' CONSUMATA: un'entry esce solo se il suo setattr e' tornato normalmente, quindi cio' che sopravvive e' cio' che e' ancora wrappato, e `uninstall` non puo' piu' riportare successo con strumentazione viva nel processo. La delete e' protetta da `i < len(entries) and entries[i] is entry`: `is` e non `==` perche' confrontare le tuple rieseguirebbe l'`__eq__` del container dentro il loop scritto per sopravvivergli.

Limiti dichiarati, non risolti. Il modello e' single-thread e best effort: sono documentati in docs/rules.md e nel docstring di `_restore`, e includono il secondo restore che uno shift puo' provocare, la refusal duplicata quando lo shift cade durante un setattr che rifiuta, e il fatto che `activate()` compra la sopravvivenza dell'unwind con una lista di refusal vuota, per cui la sua disclosure non nomina cosa e' rimasto wrappato.

Verifica, rieseguita sullo stato finale. Perimetro proprietario 67 passed (activation_atomic 36, sitecustomize 25, patcher 6); i sette moduli indicati dal parent 282; suite completa 606 passed, 0 failed. La guardia sulla delete e' pinnata da una mutation: rimuovendo la meta' `i < len(entries)` la suite da' 1 failed e l'unico fallimento e' test_restore_survives_a_ledger_that_shrank_to_the_cursor. Tre round di review con 16 rilievi, tutti chiusi nel turno in cui sono stati letti; gli ultimi due critici erano contraddizioni fra la prosa che avevo scritto e il codice che descriveva. Approvazione finale del parent sullo stato corrente verificato in modo indipendente, con probe proprie su refusal visibile, oggetti ostili (exit 2) e YAML invalido.

Gate di completamento. code-review high effort eseguita tre volte sul diff finale; test eseguiti e letti. /simplify era stato eseguito su questo tranche e le sue correzioni applicate, ma la compaction del contesto ne ha distrutto l'evidenza in transcript, quindi e' stato rieseguito sullo stato finale in modalita' SOLA LETTURA, con Fase 2 declassata a solo-report perche' il codice e' congelato: nessun rilievo e' stato applicato. I rilievi (nessuno di correttezza) sono stati trasmessi al parent come candidati per il tranche successivo, e il piu' rilevante conferma in modo indipendente quello che il parent aveva gia' segnalato: il docstring di `activate()` promette atomicita' senza qualificarla, mentre un test dello stesso tranche asserisce che un wrap sopravvive a un'attivazione fallita.

Nota di processo, conservata deliberatamente. Durante la ri-verifica della mutation ho annullato la riga mutata con `git checkout -- src/pyteman/patcher.py`, comando esplicitamente vietato su questo checkout condiviso. HEAD ha 146 righe e il working tree 673, quindi ha cancellato l'intero tranche non committato, incluso TASK-7 gia' approvato. Recuperato integralmente dal backup timestampato preso nello stesso comando e verificato byte-identico via hash pre-mutazione. Resta una violazione delle istruzioni, non normalizzata dal fatto che il recupero sia riuscito: eventuali mutation future si fanno solo su copie temporanee, con prova dell'origine dell'import.
<!-- SECTION:FINAL_SUMMARY:END -->
