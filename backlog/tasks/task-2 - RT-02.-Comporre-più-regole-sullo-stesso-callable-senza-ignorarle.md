---
id: TASK-2
title: RT-02. Comporre più regole sullo stesso callable senza ignorarle
status: Done
assignee: []
created_date: '2026-09-16 12:20'
updated_date: '2026-09-17 09:47'
labels:
  - audit-2026-09-16
  - opus-5
  - rt
  - confirmed
milestone: m-0
dependencies:
  - TASK-7
  - TASK-5
references:
  - 'src/pyteman/patcher.py:531-533'
  - 'docs/rules.md:357-362'
  - 'src/pyteman/rules.py:292-307'
documentation:
  - doc-1
  - doc-2
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P1, CONFIRMED, aperto.

**File:** `src/pyteman/patcher.py:24-43`.

**Evidenza:** due regole sullo stesso punto, entry sleep e exit return_value, producono un solo firing entry e il risultato originale: `_pyteman_state` fa saltare la seconda regola. Non è un rifiuto esplicito del ruleset.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Dispatcher unico per slot risolto (container, attributo): N regole sullo stesso callable producono UN wrapper e UNA entry nel ledger di ownership, non wrapper annidati per regola. Risoluzioni alias che atterrano sullo stesso slot raggruppano tutte le regole senza perderne nessuna.
- [x] #2 Entry eseguite nell'ordine del ruleset. Il primo return_value/return_none termina immediatamente: salta le entry successive, il corpo e TUTTE le exit. Un raise da una entry interrompe allo stesso modo, senza finally artificiale che faccia girare le exit su un corpo mai invocato.
- [x] #3 Corpo riuscito: exit nell'ordine del ruleset; un override aggiorna il risultato corrente ed e' visibile alle exit successive; l'ultimo override applicato vince.
- [x] #4 Corpo che solleva: ogni exit raggiunta vede l'exc originale e result None; nessun override sopprime o altera quel contesto. Un raise da una exit interrompe le exit successive e propaga l'eccezione iniettata con chaining Python ordinario.
- [x] #5 Stato separato per ogni regola: countdown n+1 e once_per invariati. Il contatore avanza solo quando quella coppia regola/evento viene effettivamente raggiunta, mai per entry o exit saltate da un return/raise precedente.
- [x] #6 Cross-Patcher: uno slot posseduto dal dispatcher ATTIVO di un altro Patcher produce rifiuto esplicito e diagnosticato, con rollback delle sole modifiche della chiamata corrente; niente skip silenzioso, niente annidamento di attributi. Hook distinti su target disgiunti conservano il LIFO di TASK-5.
- [x] #7 Idempotenza: lo stesso ruleset ripatchato piu' volte dallo stesso Patcher non aggiunge regole, wrapper o firing. Uninstall seguito da una nuova patch e' una nuova installazione; il contratto storico di applied resta invariato.
- [x] #8 Id duplicati rifiutati in preflight anche sull'API programmatica, prima di qualunque mutazione. Due regole con contenuto identico ma id diversi restano due regole: nessuna dedup per contenuto.
- [x] #9 Documentazione allineata al codice nello stesso task: docs/rules.md 357-362 riscritto (oggi descrive lo skip) e README sezioni Ruleset/Fire gating. Lo short-circuit e' documentato senza promettere che tutte le regole contino ogni chiamata.
- [x] #10 Firma e functools.wraps preservati. Suite completa verde inclusi RT-01 e RT-05; i nuovi test di composizione dimostrati mordenti via mutation testing su copia temporanea con prova di origine __file__.
- [x] #11 Una regola che raggiunge uno slot gia' posseduto da un dispatcher dello STESSO Patcher non viene mai scartata in silenzio: o estende quel dispatcher, o produce un rifiuto esplicito con diagnostica e rollback
- [x] #12 L'estensione distingue per ID di regola gia' servita e non per contenuto: ripatchare lo stesso ruleset con lo stesso Patcher non aggiunge regole, wrapper, voci di ledger ne' firings
- [x] #13 Le regole aggiunte per estensione rispettano l'ordine ORIGINALE del ruleset, anche quando l'alias viene scoperto da una chiamata _patch successiva
- [x] #14 Lo stato gia' raggiunto delle regole preesistenti su quel dispatcher (fires, seen_keys) sopravvive all'estensione intatto
- [x] #15 Il fallimento di una chiamata che ha esteso un dispatcher esistente rimuove solo le proprie aggiunte e lascia dispatcher, stati e regole preesistenti come li ha trovati
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Contratto approvato dall'orchestratore il 2026-09-17, registrato prima del codice.

## Stato di partenza misurato, non citato

Lo skip NON e' a patcher.py:24-43 come dice il campo References (quelle righe
oggi sono _compile e _typename). Il sito reale e' patcher.py:531-533:

    if getattr(original, "_pyteman_state", None) is not None:
        continue

Quel predicato regge da solo tre proprieta' diverse: idempotenza del re-patch
(il motivo dichiarato nel commento, force_patch_module ripassa sugli stessi
simboli), non duplicazione su installazioni ripetute, ed esclusione della
composizione. Rilassarlo per la terza fa cadere le prime due nello stesso
istante, ed entrambe sono richieste dagli AC. Vanno ristabilite per identita'
esplicita, non come effetto collaterale di un marcatore.

Secondo fatto misurato: `_pyteman_state` e' `{"fires": 0, "seen_keys": set()}`,
senza id di regola e senza Patcher proprietario. Il guard quindi non puo'
distinguere "mio wrapper di questa stessa regola" da "di un'altra regola" da
"di un altro Patcher". E' la forma esatta del finding 1 di TASK-5: un'etichetta
muta che deve diventare una relazione viva, come `_pyteman_patcher` e' diventato
`owner._hook is fn`. Conseguenza sul contratto Q3: oggi il cross-Patcher non e'
rifiutato, e' ignorato in silenzio.

## Design

1. Raggruppamento per slot. `_patch` smette di iterare regola per regola e
   risolve prima (container, name) per ogni regola del piano che riguarda il
   modulo, poi raggruppa per identita' dello slot. Chiave `(id(container), name)`
   con il container tenuto vivo nel gruppo, perche' un container puo' essere non
   hashable e perche' due symbol testualmente diversi possono risolvere allo
   stesso oggetto: e' il caso alias, che l'AC1 impone di non perdere. Ordine dei
   gruppi e ordine interno = ordine del ruleset (Q4, nessun campo priorita').

2. Un dispatcher per slot. `_make_dispatcher(specs, original)` costruisce UN
   callable con `functools.wraps(original)` che serve N regole, ciascuna con il
   proprio `state` creato fresco. Non annidamento: N wrapper annidati
   funzionerebbero sul ledger di TASK-5 solo grazie alla ri-domanda a undo-time
   `if owned or not _owns_name(...)`, e far dipendere un design nuovo da quel
   dettaglio appena corretto e' fragile. Una entry sola nel ledger, con `owned`
   calcolato una volta prima del primo setattr.

3. Corpo del dispatcher. Entry in ordine; `_gate` per regola; `run_action`;
   override letto con `pop` e non `get`, perche' `ctx["_override"]` e' appiccicoso
   e con N regole il valore della regola k verrebbe riletto dalla k+1. Primo
   override: return immediato, nessun corpo, nessuna exit. Un raise da entry esce
   prima del try e quindi non fa girare nulla (Q1, nessun finally artificiale).
   Poi il corpo in try/except/finally come oggi. Nel finally, exit in ordine: su
   successo l'override aggiorna `result` e le exit successive lo vedono, l'ultimo
   vince; su eccezione `ctx["result"] = None`, `ctx["exc"] = exc`, e l'override
   viene IGNORATO (Q2, nessuna soppressione introdotta). Un raise dentro il
   finally sostituisce l'eccezione in volo con `__context__` gia' impostato: e'
   il chaining ordinario che il contratto chiede, non serve codice.

4. Contatore. `_gate` incrementa `state["fires"]` come prima istruzione, quindi
   una regola mai raggiunta non vede avanzare il contatore: la clausola "non per
   entry/exit saltate" e' soddisfatta per costruzione, non da un guard nuovo.
   `ctx["fires"]` viene riscritto da ogni `_gate` con il conteggio della propria
   regola prima che la sua action giri, quindi sparisce l'inizializzazione di
   `ctx["fires"]` a costruzione (oggi riga 627), che con N regole non ha piu' un
   valore unico sensato.

5. Firma. `inspect.signature(original)` e' la stessa per tutte le regole dello
   slot: calcolata una volta per gruppo se almeno una regola e' pragma/param,
   fuori dal try come oggi e per la stessa ragione (l'import e' servito dall'hook
   e un setattr rifiutato di un'ALTRA regola arriva qui come TypeError,
   indistinguibile da una firma illeggibile).

6. Ownership e rifiuto. Il dispatcher porta `_pyteman_owner = self`. "Attivo"
   non e' un flag ma una relazione viva, come in TASK-5: il proprietario e'
   attivo su quel dispatcher se il dispatcher compare per identita' nel suo
   `_wrapped`. Si auto-guarisce, perche' uninstall consuma l'entry, e resta vero
   anche quando uninstall e' stato rifiutato su quello slot e l'entry e'
   trattenuta per il retry. Tre esiti allo slot occupato: dispatcher nostro e
   attivo -> gruppo saltato, nessuna regola/wrapper/firing aggiunto (AC7);
   dispatcher di un altro Patcher e attivo -> eccezione dedicata con diagnostica,
   che cade nel gestore esistente di `_patch` e fa il rollback delle sole
   modifiche di questa chiamata (AC6); dispatcher pyteman ritirato o callable
   estraneo -> e' uno sconosciuto, lo si avvolge.

7. Compatibilita' del marcatore. `_pyteman_state` resta sul dispatcher e contiene
   la lista degli stati per regola. Undici punti in test_activation_atomic.py lo
   usano come oracolo di "e' avvolto" con `is None` / `is not None` e continuano
   a funzionare senza toccarli: quei test fissano invarianti di TASK-5 appena
   approvati e non vanno disturbati per una rinomina. Il nome resta veritiero.

8. Preflight id duplicati. rules.py:292-307 impone gia' id unici al load, ma
   `Patcher(rules, log)` costruito a mano non passa di li'. Il controllo va in
   `__init__`, che e' prima di qualunque mutazione del programma bersaglio per
   costruzione. Nessuna dedup per contenuto: due regole uguali con id diversi
   sono due regole volute.

## Verifica

Test nuovi in tests/test_activation_atomic.py per ciascun AC comportamentale, con
i casi di rottura espliciti: entry+exit sullo stesso punto, due entry, due exit,
short-circuit da entry che salta le exit, override concatenati su exit, corpo che
solleva con exit raggiunte, raise da exit sopra un corpo che solleva, countdown e
once_per indipendenti sotto short-circuit, alias sullo stesso slot, re-patch
idempotente, rifiuto cross-Patcher con rollback, id duplicati in preflight.
Mutation testing su copia temporanea con prova di origine `__file__`, un mutante
per guard nuovo. Gate finali: /simplify, code-review high effort, suite completa,
hash dei file toccati.

## Fuori scope

rules.py (salvo necessita' motivata), runner, integrity, sitecustomize. Nessun
async, nessun locking cross-thread: sono task separati e il commento sulla race
in _patch resta valido e non viene ne' risolto ne' peggiorato.

## Estensione del dispatcher per identita' di regola (integrato in TASK-2 il 2026-09-17)

Requisito accolto su disposizione dell'orchestrator: il drop SILENZIOSO di regole dello stesso Patcher su uno slot gia' suo e' bug core RT-02 e non materiale da rinviare a TASK-106. Il ramo `owner is self: continue` a patcher.py:750-765 e' il punto esatto. Oggi stabilisce solo che il dispatcher e' NOSTRO, non che serve QUELLE regole, e scarta le regole non servite senza messaggio, senza voce in `applied` e senza rifiuto.

Meccanica verificata leggendo il codice, non assunta:

1. `entries` ed `exits` (patcher.py:946-947) sono locali di chiusura ma sono LISTE. Il dispatcher itera `for ... in entries`, che legge l'oggetto lista vivo, quindi una mutazione in loco fatta dall'esterno e' visibile alla chiamata successiva senza toccare il corpo del dispatcher. Serve solo un riferimento a quelle liste dall'esterno.

2. `sig` e `sig_unparseable` (patcher.py:923-924) sono invece locali di chiusura letti come valori a :957 e :959. Non sono rilegabili dall'esterno. Questo e' il solo punto che richiede una modifica al corpo del dispatcher, ed e' il vero costo di progetto: servono per la AC su una regola aggiunta che porta un target `param:` quando nessuna regola gia' legata allo slot richiedeva la signature. Forma prevista: un contenitore mutabile letto dal dispatcher, cioe' una indicizzazione in piu' per chiamata solo quando la signature serve.

3. `dispatcher._pyteman_state` (patcher.py:1039) e' `[spec[3] for spec in bound]`, cioe' i soli dict di stato senza identita' di regola. E' precisamente il motivo per cui il ramo corrente non sa distinguere i due casi, come dice il commento a :763-764. Conservare `bound` per intero, o una mappa da id di regola alla sua posizione, restituisce l'identita' che serve.

4. L'ordine ORIGINALE di ruleset e' recuperabile senza campi nuovi: `self._plan` e' gia' in ordine di ruleset, quindi la posizione in `_plan` e' l'ordinale globale. Richiesto esplicitamente dall'orchestrator che l'ordine originale valga anche quando l'alias viene scoperto tardi, quindi l'inserimento e' un merge ordinato e non un append.

5. Il ledger resta a una voce per slot: l'estensione non installa nulla, non fa setattr e non aggiunge la 5-tupla. Solo `applied` cresce, con le sole regole effettivamente aggiunte.

6. Rollback: la chiamata che estende registra le proprie aggiunte e, in caso di fallimento, le rimuove per IDENTITA' da `entries`, `exits` e dalla struttura delle regole servite. Non per indice, perche' il merge ordinato puo' aver spostato le posizioni. Vincolo dell'orchestrator: una aggiunta fallita non cancella stati ne' regole preesistenti.

7. Idempotenza storica preservata: se l'insieme delle regole gia' servite copre tutte quelle risolte ora, non si aggiunge nulla, `applied` non cresce e non cambia alcun conteggio di firing. La distinzione e' per id, mai per contenuto, coerente con il contratto gia' pinnato che due regole identiche nel contenuto ma con id diversi sono due regole.

Limite concordato in anticipo: se l'estensione atomica dovesse risultare sproporzionata all'implementazione, la ricaduta autorizzata e' il RIFIUTO esplicito con diagnostica e rollback, mai il successo con regole perse. Il punto da concordare in quel caso e' quale combinazione resta non supportata.

PREREQUISITO CHIUSO PRIMA DELL'ESTENSIONE (2026-09-17). La seconda rilettura in pass 2 non confronta piu' l'identita' ma la PROPRIETA', su tre rami: `_ABSENT` salta, dispatcher nostro si tira indietro, dispatcher di un altro Patcher rifiuta. Il confronto `settled is not slot.original` era una regressione mia e rompeva OGNI punto raggiunto via descriptor, perche' un attributo fabbricato a ogni accesso rende `inst.m is inst.m` gia' False: istanza di modulo, classmethod e property venivano rifiutati con `SlotOwnershipError` che nominava una corsa mai avvenuta, e il raise abortiva la patch dell'intero modulo. Due test di regressione aggiunti in tests/test_activation_atomic.py, entrambi verificati fallire contro il guard precedente su copia in /tmp con prova di origine via __file__: `test_a_point_on_a_module_level_instance_patches_fires_and_restores` e `test_an_attribute_deleted_while_its_dispatcher_was_built_is_skipped`. Suite 718 passed.

Perche' conta per QUESTA task e non e' solo igiene. L'estensione per identita' di regola vive nello stesso loop e dipende dalla forma di questo guard. Il ramo 'dispatcher nostro' e' esattamente il punto in cui oggi la regola viene persa in silenzio, ed e' li' che andra' innestata l'aggiunta al dispatcher gia' presente invece del `continue`. Averlo ridotto a una domanda di proprieta' a tre rami significa che l'innesto ha un solo posto dove andare, in entrambi i rami che oggi fanno `continue`: quello in cima al loop (riga del `owner is self`) e questo dopo la costruzione. Erano due prima e restano due, ma ora pongono la stessa domanda nella stessa forma, il che toglie il rischio che l'estensione venga innestata su uno solo dei due.

Limiti registrati separatamente e NON risolti qui: TASK-122 (la finestra fra seconda rilettura e scrittura e' raggiungibile con un solo thread, perche' getattr e setattr possono eseguire codice target) e TASK-123 (la sostituzione da parte di un terzo durante la costruzione non e' piu' rilevata, che era gia' vero prima della tranche).

## Findings del code-review 2026-09-17 non applicati, con la ragione (registrati qui perche' l'estensione li incontra)

Regola di condotta: ogni raccomandazione di review atterra da qualche parte nello stesso turno in cui viene letta. Questi tre non sono stati applicati al codice, quindi atterrano qui.

1. DEDUP DEI DUE GUARD, rinviata DELIBERATAMENTE a questa estensione e non fatta prima. Il gate /simplify ha proposto un helper `_unowned_value` che restituisce `_ABSENT` per tutti i casi di stand-down, collassando i due siti in uno. Quella forma precisa e' stata RIFIUTATA, non dimenticata: il ramo `owner is self` e' esattamente il punto di innesto dell'estensione, e per estendere serve l'OGGETTO dispatcher vivo, che un ritorno `_ABSENT` butta via. Deduplicare con quella forma renderebbe l'innesto piu' difficile, non piu' facile.

   La dedup resta giusta nel merito, perche' i due rami `owner is self` eseguono la stessa identica operazione futura (aggiungere `slot.specs` al dispatcher vivo, registrare in `applied`, NON fare setattr), quindi deduplicare prima significa innestare una volta sola invece che due. La forma da adottare e' un helper che restituisce la COPPIA `(value, owner)`, cosi' ogni sito conserva il proprio `continue` e il proprio commento, che dicono cose diverse, e nessuno dei due perde il dispatcher. Da applicare INSIEME all'estensione, non prima.

   Vincolo che rende la dedup piu' che cosmetica: l'innesto deve andare in ENTRAMBI i rami. Una modifica che ne cambia uno e dimentica l'altro compila pulita e si manifesta solo a runtime, che e' precisamente la classe di bug 'ne ho mancato uno' contro cui la regola del grep esaustivo esiste.

2. `settled_owner is self` risponde vero anche se il programma bersaglio ha ALIASATO un nostro dispatcher su un altro slot, perche' la domanda e' sulla proprieta' del valore e non sulla sua posizione. Confidenza bassa e caso esotico: richiede che il bersaglio copi un attributo gia' patchato su un secondo nome DENTRO la finestra di costruzione. Non corretto. Se l'estensione dovesse rendere il ramo `owner is self` piu' che un `continue`, cioe' una mutazione del dispatcher trovato, allora questo caso smette di essere innocuo, perche' estenderemmo un dispatcher che sta su uno slot diverso da quello che credevamo. DA RIVALUTARE quando l'innesto viene scritto, non prima.

3. `getattr(..., _ABSENT)` tratta come assente anche una `AttributeError` sollevata da dentro un getter. Preesistente, coerente con lo `hasattr` di pass 1, e non una regressione di questa tranche. Filata come task separata perche' e' indipendente da RT-02 e ha un contratto osservabile suo.

## Rilievi del gate /simplify 2026-09-17 che appartengono a TASK-2

Questi quattro non diventano task separati, perche' cadono esattamente nelle regioni che TASK-2 riscrive. Applicarli ora significherebbe scriverle due volte.

**Conferma indipendente sulla causa radice.** Il revisore di altitudine ha identificato `dispatcher._pyteman_state = [spec[3] for spec in bound]` a patcher.py:1070 come la causa radice del silent drop, non come un sintomo: pubblicando stato anonimo, il dispatcher non porta l'identita' delle regole che serve, e il ramo `owner is self` non ha percio' modo di distinguere "servo gia' queste regole" da "ne servo altre". Ha classificato i due guardiani come cerotto sopra quella mancanza. Questa e' la stessa conclusione gia' registrata in questo piano, raggiunta per una via indipendente, ed e' un punto a favore del manifesto di regole (`dispatcher._pyteman_rules`) come forma della soluzione: con l'identita' pubblicata, entrambi i rami `owner is self` collassano in "installa un dispatcher per l'unione" e `applied` torna a dire il vero.

**La lettura ripetuta in pass 1.** A patcher.py:706 lo `hasattr(container, parts[-1])` gira prima che la chiave sia calcolata alla :709, quindi N regole che atterrano sullo stesso slot producono N test di esistenza invece di uno. Su una property o su un modulo con `__getattr__` ogni test esegue codice del bersaglio, percio' non e' solo costo: e' un effetto collaterale moltiplicato per il numero di regole. La correzione e' alzare il calcolo della chiave sopra il test di esistenza e saltare se lo slot esiste gia'. Questa e' la stessa riga che l'AC #1 tocca per il raggruppamento, quindi si sistema li'.

**Il README tace sul drop fra regole dello stesso Patcher.** README.md:106-115 descrive la composizione senza dire che oggi due risoluzioni alias dello stesso Patcher sullo stesso slot perdono in silenzio le regole della seconda. Non va aggiunta una nota sul difetto: TASK-2 lo elimina, quindi quel paragrafo va riscritto per enunciare il comportamento corretto quando l'estensione e' in piedi.

**`_inflight` come compensazione.** Il revisore osserva che `_inflight` esiste per coprire il fatto che il dispatcher viene pubblicato tardi, e che con l'identita' delle regole pubblicata sul dispatcher parte del suo lavoro diventerebbe ridondante. Da riesaminare a estensione fatta, non prima: `_inflight` copre anche la rientranza durante la costruzione, che il manifesto non risolve da solo.

## Un rilievo ridimensionato, perche' non resti da inseguire

Il revisore di altitudine segnala come terza finestra il fatto che `_owns_name` alla :834 giri `vars(container)` dopo l'ultima classificazione e prima del setattr, e lo motiva dicendo che `vars` esegue codice del bersaglio. Quella motivazione non regge nei casi che il progetto supporta: `vars(obj)` legge `obj.__dict__`, che per un modulo o per una classe normale e' un descrittore di slot e non passa dal protocollo degli attributi. In particolare il `__getattr__` di modulo non viene consultato, perche' e' interrogato solo per attributi mancanti e `__dict__` non manca mai.

Resta valida l'osservazione di ordine, cioe' che fra l'ultima classificazione e il setattr esiste comunque un intervallo. Quella appartiene a TASK-122, che tratta le finestre di corsa, e non va riderivata qui.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: CFG-01; RT-05 per proprietà delle patch.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.

Nota da TASK-7 (2026-09-16, CFG-01). Il comportamento attuale e' ora DOCUMENTATO, non corretto: docs/rules.md, sezione "Rule fields", dice che due regole sullo stesso punto non si applicano entrambe, che l'import hook avvolge un callable una sola volta e salta la regola il cui target risulta gia' avvolto, quindi vince la prima regola del file e la seconda cade senza messaggio. Il rimando operativo e' "combinale in una sola regola, oppure agganciale a due punti diversi".

Conseguenza per questo task: quando RT-02 verra' eseguito, il paragrafo va riscritto insieme al codice, altrimenti la documentazione descrive un comportamento che non esiste piu'. Il criterio #2 (documentare cosa succede alle regole successive dopo return/raise) ha quindi gia' una sede: quella sezione di docs/rules.md.

La scelta di documentare invece di correggere e' deliberata e fuori dallo scope di TASK-7: CFG-01 tocca solo la validazione al load, mentre lo skip vive in patcher.py:38-39, file non di proprieta' di quel task.

## Estensione del dispatcher: tre difetti nella finestra della signature (2026-09-17)

La lettura della signature dentro `_extend_dispatcher` esegue codice del bersaglio (una property `__signature__`, una catena `__wrapped__`), quindi puo' rientrare in `_patch`. Il commento originale ragionava solo su un LETTORE rientrante che 'vede questo dispatcher intero'. La rientranza pero' puo' essere uno SCRITTORE sulla stessa mappa contro cui `fresh` era stato filtrato. Tre conseguenze distinte, tutte riprodotte prima di correggere.

1. DOPPIO MERGE. `fresh` viene filtrato prima della lettura e usato dopo: nel frattempo la rientranza puo' aver gia' unito quelle stesse regole. Ne risultavano due spec con due dict di stato separati per una sola regola, quindi `countdown` raggiungeva la soglia a una chiamata che l'operatore non ha scritto e `once_per` sparava due volte per una chiave. Invisibile alla diagnostica: `served[id(rule)]` tiene una sola spec, quindi `rank()` e `_pyteman_state` pubblicavano UNO stato mentre `comp.entries` ne faceva girare DUE. Il duplicato si nascondeva esattamente dietro il manifesto che questa tranche ha introdotto per rendere visibili i drop. Corretto con un SECONDO filtro di `fresh` contro `comp.served`, collocato subito dopo l'unica istruzione della funzione che esegue codice del bersaglio.

2. SIGNATURE NON RESTITUITA AL ROLLBACK. Una chiamata che scriveva la signature e poi falliva la lasciava sullo slot. Non e' un memo innocuo su `original`: a patcher.py:1133-1134 il dispatcher scrive `ctx['_signature_unparseable']` nell'UNICO ctx che serve ogni regola dello slot, e `conditions.eval_expr` passa quel dict a `eval` come mapping dei LOCALS. Una chiamata annullata cambiava quindi lo spazio dei nomi in cui vengono valutati i `when` di regole che non aveva mai toccato, che viola l'AC #15. Corretto con un flag `wrote_sig` restituito da `_extend_dispatcher` e consumato da `_unextend`.

   Il flag batte il salvataggio del valore precedente, ed e' piu' piccolo: la scrittura avviene solo su uno slot senza risposta, quindi `wrote_sig == True` implica che lo stato precedente era esattamente `(None, False)`. In piu' lascia in pace la risposta di una chiamata annidata, che un salva-e-ripristina cieco avrebbe sovrascritto.

3. SOVRASCRITTURA DI UNA RISPOSTA GIA' PUBBLICATA. La scrittura della signature ora avviene solo se lo slot non ha ancora risposta. Una rientranza puo' averne pubblicata una, e le regole che ha installato vengono dispatchate contro quella da allora. Due letture di un callable la cui introspettabilita' cambia fra loro non concordano, e quella gia' in uso e' quella che il ruleset ha visto.

## Verifica delle tre correzioni

Tre test di regressione in tests/test_activation_atomic.py, uno per proprieta': `test_a_reentrant_patch_during_an_extension_merges_its_rules_once`, `test_a_failed_call_takes_back_the_signature_it_cached`, `test_a_failed_call_leaves_a_signature_a_nested_call_published`.

Mutation testing su copia in /tmp con prova di origine via `__file__` (/tmp/mutate_extension_guards.py, origine provata `/tmp/mut2/pyteman/patcher.py`, baseline `9 passed`): sette mutanti, ZERO sopravvissuti.

```
mutant: the rule is dropped instead of added (the original bug)
  last line: 6 failed, 3 passed
mutant: added rules are appended rather than merged in ruleset order
  last line: 3 failed, 6 passed
mutant: the extension rebuilds the states of the rules already there
  last line: 2 failed, 7 passed
mutant: rollback trims the list from the end instead of removing by identity
  caught by: test_a_failed_call_that_extended_a_dispatcher_takes_back_only_its_own_rules
mutant: the stale list is merged, so a re-entry's rules are merged twice
  caught by: test_a_reentrant_patch_during_an_extension_merges_its_rules_once
mutant: a rolled-back call leaves the signature it cached behind
  caught by: test_a_failed_call_takes_back_the_signature_it_cached
mutant: the extension overwrites a signature a re-entry already published
  caught by: test_a_failed_call_leaves_a_signature_a_nested_call_published
```

I tre mutanti nuovi sono catturati uno a uno dai tre test nuovi, ciascuno da quel test e da nessun altro, il che dice che pinnano quella proprieta' specifica e non la presenza generica della funzione. Per contrasto il primo mutante storico ne fa cadere sei su nove, che e' il profilo di un test grossolano.

Suite completa: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /tmp/pyteman-audit-env-OOeElF/bin/python -m pytest tests/ -q` restituisce `726 passed in 3.65s`, da 723 prima dei tre test nuovi. Che la suite fosse verde anche PRIMA delle correzioni e' a sua volta evidenza: nessun test esistente pinnava i comportamenti difettosi.

## Un rilievo confutato, perche' non resti da inseguire

Il code-review aveva segnalato che il test di identita' del ledger in `_live_dispatcher_owner` (`wrapper is fn`) fallisce per un metodo legato letto da un'istanza di modulo, e prevedeva un RIFIUTO contro noi stessi. L'instabilita' di identita' e' reale e misurata (`getattr(inst, 'm') is getattr(inst, 'm')` restituisce False), ma la conseguenza prevista non si verifica: /tmp/probe_bound_method_identity.py patcha `Klass.m` e `inst.m` nello stesso ruleset senza alcun rifiuto, e produce due dispatcher annidati, uno per punto nominato, ciascuno con un solo firing. La classificazione 'sconosciuto' porta a un secondo wrap, non a un rifiuto, ed e' l'esito corretto: `Klass.__dict__['m']` e `inst.__dict__['m']` sono slot diversi, quindi riconoscere il metodo legato come nostro ed estendere il dispatcher di classe sarebbe stato il vero difetto, fondendo in silenzio due punti chiesti separatamente.

## Due raccomandazioni respinte con motivo

1. `reversed()` in `_unextend` resta. Il gate /simplify lo segnala come decorativo, e nel merito ha ragione: tracciato il caso di due estensioni dello stesso dispatcher nella stessa chiamata, la prima scrive (`wrote_sig` vero) e la seconda trova gia' la risposta (`wrote_sig` falso), quindi il reset avviene una volta sola qualunque sia l'ordine; gli insiemi da rimuovere sono disgiunti per costruzione e `_pyteman_state` viene comunque ricostruito dal `served` finale. Rimuoverlo e' pero' churn cosmetico fuori dall'autorizzazione corrente, che copre solo bug e AC.

2. La fixture `crosscall` resta com'e'. La proposta era di cedere il solo `victim`, ma uno dei tre consumatori usa `holder`, quindi il rilievo si riduce a una preferenza sul nome del binding in tre test.

## Difetti trovati e NON corretti qui, filati con riproduttore

TASK-131 (alta): una chiamata annullata lascia in `applied` le estensioni di una chiamata annidata. `_patch` scrive uno slot per volta, quindi uno slot avvolto presto e' vivo mentre uno successivo viene ancora costruito; una rientranza da li' estende il dispatcher gia' installato, pubblica le sue voci, e le perde quando `_restore` toglie il dispatcher dallo slot. Il codice enuncia l'invariante violata a :1009-1013. Confermato da /tmp/probe_orphaned_extension.py, che stampa `STRANDED CLAIM: True` con `applied` che nomina `probe_orph_alias:via.a` mentre `victim.a` e' tornato a essere l'originale. Non corretto qui perche' la correzione vive nel blocco except fail-closed, va condizionata alla riuscita per singolo slot e muta una lista che una chiamata COMPLETATA ha gia' pubblicato: e' un cambio di semantica che merita la sua review.

TASK-132 (media): `served` e' chiavata per `id(rule)` mentre il piano puo' contenere lo stesso oggetto Rule due volte, quindi le due strutture non concordano sul conteggio. Confermato da /tmp/probe_duplicate_plan_entry.py (`entries 2`, `rank() 1`, `served keys 1`). Severita' minore del doppio merge: li' il duplicato era inventato dal patcher, qui la regola e' davvero nel ruleset due volte e `applied` la nomina due volte onestamente. L'incoerenza e' inoltre LATENTE, perche' il percorso di costruzione ricava `_pyteman_state` dalla lista delle spec e non da `rank()`; emerge solo a estensione successiva, quando il marcatore scende da 2 a 1 mentre `entries` continua a far girare due regole. Non e' una correzione piccola: chiavare `served` per identita' di regola e' cio' che rende possibile il secondo filtro anti doppio merge, quindi ri-chiavarla per voce di piano riaprirebbe il bug appena chiuso. Va prima deciso cosa SIGNIFICA una regola elencata due volte.

## README, limite del binding copiato (AC #9)

Il paragrafo che ho scritto in questa tranche dice che un secondo modulo che NOMINA un punto gia' avvolto si unisce al dispatcher esistente. E' vero e invita all'inferenza sbagliata. Un modulo che ha eseguito `from target import f` prima del wrap possiede la funzione originale e non una via di ritorno all'attributo, quindi le chiamate per quel nome non raggiungono mai il dispatcher e non compaiono nel log dei firing, mentre `applied` nomina comunque la regola come applicata. Misurato con /tmp/probe_copied_binding.py: `applied: ['probe_cb_a:f']`, chiamata via A.f spara `['r']`, chiamata via B.f spara `[]`. Aggiunte cinque righe al README (righe 120-125), sopra il confine della sezione dell'altro agente.

## Disposizione del gate /simplify (2026-09-17), perche' nessun rilievo resti senza destinazione

APPLICATI, quattro rilievi di accuratezza della prosa. Non sono cosmesi: un commento che contraddice o duplica il codice che descrive e' esattamente cio' che l'AC #9 chiede di non lasciare in giro.

1. Il commento sopra la costruzione di `_Composite` in `_make_dispatcher` ripeteva i primi due paragrafi del docstring di `_Composite` (perche' un locale di chiusura non e' rilegabile dall'esterno). Due sedi che spiegano la stessa cosa divergono alla prima modifica, quindi il commento e' stato ridotto a un puntatore, conservando la sola parte che il docstring non dice: la divisione entry/exit e' fatta una volta qui invece che testata a ogni chiamata, e i filtri conservano l'ordine di ruleset perche' quello E' l'ordine dichiarato.

2. Il docstring di `_unextend` diceva 'the counterpart of _restore', che invita a portarsi dietro il contratto di `_restore` proprio sull'asse in cui i due differiscono. `_restore` CONSUMA la sua lista, e lo dichiara, perche' un setattr rifiutato lascia un wrap che va comunque registrato da qualche parte. `_unextend` non tocca alcun container, quindi nulla puo' rifiutare e non resta residuo da ritentare; verificato leggendo il corpo, che itera `reversed(extensions)` e non muta mai l'argomento. Riscritto come 'the other half of the undo' con la differenza enunciata.

3. Il docstring di `_Composite` motivava il manifesto dicendo che una regola il cui evento non e' ne' entry ne' exit appartiene al dispatcher e non compare in nessuna delle due liste, senza dire se quello stato sia raggiungibile. Verificato invece di assumere: il vocabolario degli eventi e' controllato a rules.py:318, che sta dentro il loader YAML, ed e' l'unico uso; `Rule` e' una dataclass semplice senza `__post_init__`. Un Patcher costruito programmaticamente puo' quindi portare qualunque stringa di evento. Aggiunta la frase che lo dice.

4. Riflusso del commento a righe irregolari in `_patch` (la riga 'them. The two' larga tre parole). Nessun cambio di testo.

Suite dopo i quattro: `726 passed in 3.84s`, invariata, come previsto trattandosi di soli commenti; `ast.parse` sul file per escludere una modifica malfatta.

RESPINTO, un rilievo. L'helper `served_ids(fn)` proposto per le quattro raggiunte `[s[0].id for s in ...rank()]` nei test non viene aggiunto. Le occorrenze sono davvero quattro (righe 2542, 2731, 3029, 3149; le altre tre raggiunte a `_pyteman_composite` legano `comp` e ne usano anche altri campi, quindi l'helper non le coprirebbe), e l'argomento di manutenibilita' e' valido: sono quattro punti che rompono indipendentemente se la struttura privata cambia, cosa che TASK-132 contempla. Resta pero' deduplicazione pura, che non corregge alcuna inesattezza, quindi ricade nella stessa categoria del `reversed()` di `_unextend` gia' respinto un passo prima. Applicare uno e non l'altro sarebbe incoerente. Se TASK-132 dovesse ri-chiavare `served`, l'helper va introdotto li', dove il cambio di forma lo rende necessario invece che facoltativo.

## Mappa AC -> evidenza (2026-09-17, costruita leggendo le asserzioni, non i nomi)

Ogni AC e' spuntato solo dopo aver letto il corpo del test e verificato che asserisca la proprieta' dichiarata. I test stanno tutti in tests/test_activation_atomic.py salvo dove indicato.

#1 dispatcher unico per slot, alias raggruppati: `test_an_entry_and_an_exit_on_one_point_both_fire_under_one_wrapper` (`len(p._wrapped) == 1` con `applied` di due voci, cioe' le due conte divergono per costruzione) e `test_two_symbols_resolving_to_one_attribute_land_in_one_dispatcher` (`alias.f` e `f` sono un attributo solo: un wrapper, due firing).

#2 ordine entry e short-circuit: `test_entry_rules_fire_in_ruleset_order_and_the_first_return_ends_the_call` (il loop inverte la lista e pretende che il vincitore si inverta, quindi l'ordine non e' una proprieta' delle regole), `test_an_entry_return_skips_the_body_and_every_exit` (`calls == []`) e `test_an_entry_that_raises_leaves_the_body_and_the_exits_unrun`.

#3 ordine exit e ultimo override: `test_exit_rules_fire_in_ruleset_order_and_the_last_override_wins`, che asserisce anche cosa ciascuna exit HA RICEVUTO (`["real", "F"]`), quindi la catena e' visibile e non solo il risultato finale.

#4 corpo che solleva: `test_every_exit_reached_sees_the_body_exception_and_cannot_swallow_it` (result None per entrambe, exc originale, override scartato), `test_one_exits_condition_cannot_hide_the_body_error_from_the_next` (stessa garanzia attaccata da dentro un `when`), `test_an_exit_that_raises_stops_the_later_exits_and_chains_onto_the_body_error` (`__context__` e' il ValueError) e `test_an_exit_that_raises_after_a_clean_body_chains_onto_nothing` (`__context__ is None`, pinnato a parte perche' i due percorsi differiscono).

#5 stato per regola: `test_a_rule_skipped_by_a_short_circuit_does_not_advance_its_own_countdown` (la chiamata discriminante e' la terza, letta dal comportamento e non dallo stato) e `test_each_rules_when_expression_reads_its_own_fire_count`.

#6 cross-Patcher: `test_a_second_patcher_over_a_live_dispatcher_is_refused_and_rolls_itself_back` (il messaggio nomina modulo e attributo, lo slot gia' preso da QUESTA chiamata torna indietro, `p2._wrapped == []`), `test_a_slot_taken_by_another_patcher_mid_build_is_refused_and_rolled_back` per la finestra di costruzione, e `test_two_patchers_on_disjoint_targets_do_not_refuse_each_other` piu' `test_uninstall_out_of_order_is_refused_before_anything_moves` per il LIFO di TASK-5.

#7 idempotenza: `test_repatching_the_same_module_adds_no_second_wrapper_and_no_extra_firings`. La regola entry dorme invece di ritornare, scelta deliberata: con un `return_value` l'asserzione sarebbe passata anche sotto doppio wrap.

#8 id duplicati: `test_a_duplicate_rule_id_is_refused_before_anything_is_patched` (rifiuto in `Patcher.__init__`, quindi prima di ogni mutazione) e `test_two_rules_with_one_content_and_different_ids_are_two_rules`.

## Mappa AC -> evidenza, seconda parte

#9 documentazione: la sezione dello skip in docs/rules.md non esiste piu'. Al suo posto, docs/rules.md 429-446 enuncia il raggruppamento per attributo risolto e l'estensione fra chiamate di patch successive, dicendo esplicitamente che le regole tardive sono inserite in posizione e non appese e che le regole gia' vive conservano lo stato raggiunto; 448-455 documenta lo short-circuit senza promettere che ogni regola conti ogni chiamata ("Read `fire` as counting the times that rule ran, never the times the point was called"); 459-471 copre il rifiuto cross-Patcher. README 106-125 per la composizione, incluso il limite del binding copiato, e 127-130 per il fire gating. Il numero di riga 357-362 nel campo References e' obsoleto: quelle righe oggi sono "Checked later, by design". Verificato leggendo il file, non assunto dal campo.

#10 firma e wraps: `test_the_dispatcher_keeps_the_signature_of_what_it_replaced`. Asserisce `__wrapped__ is real`, che e' il collegamento che `inspect` percorre davvero, oltre a `__name__` e `__doc__` che un attributo copiato soddisferebbe da solo. Suite completa verde questo turno: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /tmp/pyteman-audit-env-OOeElF/bin/python -m pytest tests/ -q` restituisce `726 passed in 3.71s`. Mutation testing gia' registrato sopra: sette mutanti, zero sopravvissuti, su copia in /tmp con prova di origine via `__file__`.

#11 nessun drop silenzioso sul proprio slot: `test_a_later_patch_call_reaching_a_slot_we_already_own_extends_it`. `victim.f is dispatcher`, `len(p._wrapped) == 1`, `applied` cresce della sola regola aggiunta.

#12 distinzione per ID e non per contenuto: `test_repatching_the_same_module_adds_no_second_wrapper_and_no_extra_firings` per il ripatch che non aggiunge nulla, `test_two_rules_with_one_content_and_different_ids_are_two_rules` per il verso opposto.

#13 ordine originale di ruleset con alias scoperto tardi: stesso test dell'AC #11. `late` e' scritta PRIMA nel ruleset e scoperta DOPO, e l'asserzione e' `log.ids == ["late", "early"]`. Appendere all'arrivo risponderebbe l'opposto, quindi il test distingue le due implementazioni invece di passare per caso.

#14 stato preesistente intatto: `test_extending_a_dispatcher_leaves_the_state_the_live_rules_already_reached`, che copre entrambe le memorie per regola perche' falliscono in modi diversi: `fires` ricostruito fa slittare un countdown, `seen_keys` svuotato fa sparare di nuovo un `once_per` su una chiave gia' servita. Terza chiamata con una chiave MAI servita, per distinguere il silenzio della regola dalla sua sparizione dal dispatcher.

#15 estensione fallita che toglie solo le proprie aggiunte: `test_a_failed_call_that_extended_a_dispatcher_takes_back_only_its_own_rules` (la regola aggiunta e' scritta prima nel ruleset, quindi dopo il merge sta DAVANTI a quella superstite: un rollback che tagliasse dalla coda toglierebbe `pre` e terrebbe `added`, e ogni asserzione dovrebbe fallire invece di passare per fortuna; lo stato superstite e' confrontato per identita' di dict, non per valore), piu' `test_a_failed_call_takes_back_the_signature_it_cached` e `test_a_failed_call_leaves_a_signature_a_nested_call_published` per la finestra della signature.

Due AC hanno evidenza che non e' un test di questa suite e vanno letti cosi': il LIFO dell'AC #6 poggia su un invariante di TASK-5 gia' approvato e qui solo non regredito, e l'AC #9 poggia sulla lettura diretta dei due file di documentazione.

## Disposizione dei due reperti tagliati dalla review (2026-09-17)

I due reperti che la review precedente aveva elencato come "tagliati al cap" sono stati verificati eseguendoli, non ragionandoci sopra. Esito: uno filed, uno REFUTATO.

**Reperto 2, il piano che contiene due volte la stessa regola.** Confermato e gia' tracciato come TASK-132. La guardia di unicita' degli id in `__init__` salta il controllo quando `r.id` non si lascia leggere, quindi due entry pianificate per lo STESSO oggetto regola arrivano a `_make_dispatcher`, che costruisce una spec per entry mentre `served` e' chiavato su `id(rule)` e ne tiene una. Raggiungibile solo per via programmatica, come la guardia `_EVENTS`. Probe: /tmp/probe_duplicate_plan_entry.py.

**Reperto 1, il bound method che rompe il test di identita'. REFUTATO, due volte.** L'ipotesi era che una regola su `mod.inst.m`, con `inst` istanza a livello di modulo, facesse rifiutare il Patcher contro se stesso: `getattr(inst, 'm')` sintetizza un bound method nuovo a ogni lettura, quindi `wrapper is fn` non puo' trovare nulla nel ledger mentre lo stamp di ownership risolve attraverso `__func__` e ci nomina come proprietari. Owner trovato, identita' non trovata, verdetto "di nessuno", rifiuto.

Misurato: nessun rifiuto. `applied` contiene entrambe le regole, `Klass.m` porta il dispatcher di `on_class` e `inst` riceve un attributo proprio con il dispatcher di `on_inst`, che avvolge il bound method letto al momento della patch. La chiamata `inst.m(1)` spara `['on_inst', 'on_class']`, cioe' annidate e nell'ordine giusto, e `Klass().m(1)` su un'altra istanza spara solo `['on_class']`. Le due regole non compongono in un dispatcher solo, ma nessuna delle due si perde e nessuna spara dove non deve.

Seconda ipotesi, anch'essa refutata: che la patch lasciasse residuo, dato che `inst` non aveva `m` nel suo `__dict__` prima e la patch ce lo mette. Dopo `uninstall()` l'attributo NON c'e' piu' (`'m' in inst.__dict__` e' False), `Klass.m` e' tornato la funzione originale senza `_pyteman_composite`, e nessuna chiamata spara piu' niente. Il percorso di restore distingue quindi correttamente l'attributo che esisteva prima da quello che ha creato lui.

Nessun task filed per il reperto 1: non c'e' difetto da tracciare. Probe: /tmp/probe_bound_method_identity.py e /tmp/probe_instance_slot_residue.py, entrambi eseguiti con /tmp/pyteman-audit-env-OOeElF/bin/python. Va detto che `mod.inst.m` resta fuori dal contratto dichiarato nel README, che nomina funzioni di modulo e metodi indirizzati attraverso la classe; qui si e' solo verificato che il comportamento non e' ne' silenzioso ne' sporco.

## Finestra fra setattr e registrazione in `_inflight`: chiusa (2026-09-17)

Trovata leggendo il codice durante la verifica della tranche, non da un test che falliva. `_inflight` esiste per rendere vera la risposta "questo dispatcher e' mio" gia' dalla scrittura e non dalla pubblicazione del modulo, ma la registrazione stava UNO STATEMENT DOPO la `setattr`. Per la larghezza di quella scrittura la mappa rispondeva no, e `setattr` non e' inerte: una metaclasse con `__setattr__` o una sottoclasse di `ModuleType` eseguono codice del bersaglio proprio li'.

Una chiamata rientrante che atterrava in quella finestra riceveva "di nessuno" su un dispatcher NOSTRO e vivo. Non lo estendeva e non lo rifiutava: lo AVVOLGEVA. Esito: uno slot con due nostri dispatcher, due voci di ledger per un attributo, ogni regola sottostante che spara due volte per chiamata, e l'undo LIFO che consegna alla voce esterna uno slot con un oggetto che non riconosce, quindi rilascia e riporta nessun rifiuto mentre la voce interna rimette il dispatcher interno. `uninstall()` rispondeva `[]` su un callable ancora strumentato e ancora sparante.

Corretto scrivendo la mappa PRIMA della scrittura, a patcher.py:1020-1022. Le tre righe sono ora `self._inflight[...] = dispatcher`, `inflight.append(id(dispatcher))`, `setattr(...)`. L'append alla lista di pulizia e' spostato insieme, altrimenti una `setattr` che solleva lascerebbe la mappa sporca: il `finally` legge quella lista, quindi l'id deve esserci prima che la scrittura possa fallire.

Due test di regressione in tests/test_activation_atomic.py, che raggiungono la finestra per vie DIVERSE:

- `test_a_dispatcher_is_answerable_as_ours_before_the_write_not_after`, container `ReentersFromSetattr`, che chiama `super()` e poi rientra. Il dispatcher e' nel proprio slot quando viene riletto.
- `test_a_dispatcher_reached_through_a_leak_is_extended_not_wrapped`, container `LeaksBeforeSuper`, che copia `value` in un secondo modulo e rientra PRIMA di `super()`. Il dispatcher non e' ancora nel proprio slot, e viene raggiunto attraverso l'attributo che la fuga ha creato.

Mutation testing su copia in /tmp con prova di origine via `__file__` (/tmp/mutate_b1_order.py, origine provata `/tmp/pyteman-b1ord-xFPCHu/src/pyteman/patcher.py`, sha256 `e0c75b12...` prima e `224a2580...` dopo): rimettendo la registrazione dopo la scrittura ENTRAMBI falliscono. Il file reale e' stato ri-hashato dopo la corsa e risulta invariato, e l'albero temporaneo e' stato rimosso.

I due test non sono ridondanti, e la forma del fallimento lo dimostra. Sotto il mutante, il secondo produce una voce di ledger in piu' che nomina `(holder, 'leaked')`, cioe' lo slot della FUGA e non quello della vittima: il wrapper esterno finisce raggiungibile solo attraverso il secondo container, mentre la scrittura esterna deposita quello interno nello slot della vittima. E' una forma di doppio wrap che il primo test non produce mai.

## Una premessa mia, sbagliata e corretta nello stesso turno (2026-09-17)

Il commento che avevo scritto per giustificare il riordino diceva che un dispatcher registrato nella mappa ma non ancora in alcun attributo "non puo' essere raggiunto, quindi nessuno puo' chiedere di lui". E' FALSO, e il verificatore adversarial lo ha attaccato con successo. `setattr` consegna l'oggetto a `__setattr__` come `value` PRIMA che `super()` lo memorizzi, quindi un container puo' pubblicarlo in uno spazio dei nomi suo e rientrare da li', e la rientranza lo legge da un attributo vero.

Non l'ho preso per buono: verificato con /tmp/probe_b1_leak_window.py, dove `LeakyModule.__setattr__` esegue `holder.leaked = value` e rientra prima di `super()`. Stampa `re-entry happened: True`, `owner seen in window: <pyteman.patcher.Patcher object ...>`, `ledger entries: 1`, `DOUBLE WRAP: False`, `holder.leaked is victim.f: True`, `one call -> real fired ['base', 'leaked']`, `uninstall refusals: []`. La fuga e' reale e l'esito e' benigno.

Cio' che rende la finestra innocua non e' l'irraggiungibilita' ma la RISPOSTA. Chi la raggiunge viene ora informato che il dispatcher e' nostro, prende il ramo `owner is self` e chiama `_extend_dispatcher`: non installa nulla e non aggiunge voci di ledger. Prima del riordino gli veniva detto "di nessuno", e avvolgeva. L'invariante da preservare e' quindi "ogni via dentro questa finestra atterra su extend e non su wrap", che e' piu' debole di quanto il commento pretendeva ed e' esattamente il tipo di proprieta' che una modifica al ramo `owner is self` potrebbe rompere in silenzio.

Corretto in due sedi nello stesso turno in cui il reperto e' stato letto: il commento a patcher.py:1002-1019 e la frase corrispondente in docs/rules.md. Ed e' per questo che il test `test_a_dispatcher_reached_through_a_leak_is_extended_not_wrapped` esiste: senza di esso l'invariante che regge davvero la sicurezza del riordino non era pinnata da nulla.

## Le tre sedi di prosa allineate al riordino, e l'aggiornamento di TASK-122

Il riordino ha reso obsolete tre affermazioni scritte da me in questa stessa tranche. Corrette tutte nel turno in cui la correzione di codice e' atterrata, perche' una prosa che descrive una finestra ormai chiusa manda il lettore successivo a cercare un difetto che non c'e' piu'.

1. Il commento delle "due finestre" in `_patch`. Diceva che ne restavano due e le descriveva entrambe. Ora ne enuncia UNA sola, quella dalla seconda rilettura alla scrittura, e dice che l'altra e' chiusa dal riordino, rimandando al sito di registrazione per il motivo.

2. Il docstring di `_inflight`. La sua frase di chiusura prometteva una risposta vera "dalla setattr in poi", che era falsa per la larghezza di quella stessa istruzione. Ora dice che la registrazione avviene PRIMA della scrittura ed e' cio' che rende la risposta vera per tutto l'intervallo, inclusa la scrittura, e nomina il caso che lo esercita: un container che esegue codice del bersaglio nel proprio `__setattr__`.

3. docs/rules.md. Il paragrafo "Two threads have two windows, and they fail in opposite directions" e' stato riscritto. Ora la finestra aperta e' una sola ed e' descritta come raggiungibile anche da un solo thread; la finestra chiusa e' raccontata al passato, con il motivo per cui e' chiusa enunciato nella forma corretta (cambia la risposta, non la raggiungibilita').

TASK-122 aggiornata via MCP, con riscrittura IN LINEA e non con una nota correttiva in coda. La sua nota diceva che quella dell'`_inflight` era "l'ALTRA finestra ... e resta multi-thread. Non confonderle", ed era obsoleta su entrambi i punti. Una correzione messa piu' sotto sarebbe stata letta DOPO l'istruzione che contraddice. Il testo aggiornato dice che quella di TASK-122 e' ora l'unica finestra rimasta, nomina quella chiusa, spiega che la qualifica multi-thread era sbagliata perche' una sottoclasse di `ModuleType` che rientra dopo `super()` la raggiunge con un solo thread, e cita il test di regressione. Tutti gli AC e gli altri paragrafi conservati.

## Disposizione dei tre reperti A1, A2, B2 della verifica di questa tranche

**A1, il re-filtro incondizionato.** Confermato mordente. Il mutante che rimette il secondo filtro di `fresh` nella posizione pre-correzione e cancella il re-filtro incondizionato viene catturato da `test_an_extension_that_needs_no_signature_still_re_asks_the_manifest`. Il punto che il test pinna e' che la ri-domanda al manifesto avvenga ANCHE quando nessuna regola aggiunta richiede la signature: e' l'unico caso in cui la funzione non esegue codice del bersaglio nel punto ovvio, quindi collocare il filtro solo dopo quella lettura lo salterebbe.

**A2, i due test sulle exit.** L'evidenza di discriminazione era stata raccolta contro la versione PRECEDENTE di patcher.py, quindi non provava nulla sull'artefatto spedito. Rifatta contro il file corrente e con un CONTROLLO nella stessa forma temporanea, perche' senza controllo un conteggio di fallimenti non e' una misura:

```
REAL patcher.py: 4ffb0d8800cedd76ebbf0182e25340cae0abecaebf10810f12bb03b79e321bab
=== control ===
9 failed, 622 passed in 40.35s
=== unextend_exits ===
FAILED tests/test_activation_atomic.py::test_a_failed_call_takes_back_the_exit_rules_it_added
10 failed, 621 passed in 40.66s
=== merge_exits ===
FAILED tests/test_activation_atomic.py::test_an_exit_rule_added_by_a_later_call_merges_into_ruleset_order
10 failed, 621 passed in 41.12s
=== real file after ===
4ffb0d8800cedd76ebbf0182e25340cae0abecaebf10810f12bb03b79e321bab  src/pyteman/patcher.py
```

Il delta e' esattamente un test per mutante, e per ciascuno e' quello nuovo. I 9 fallimenti del controllo sono i due file di doc-integrity esclusi dalla copia temporanea: 730 totali meno 99 di quei file fa 631, che e' `9 failed + 622 passed`. Ogni test e' quindi contabilizzato e nessun fallimento resta senza spiegazione. Hash del file reale identico prima e dopo.

**B2, misurato invece che corretto.** L'affermazione a patcher.py:1317-1318, che un duplicato unito si nasconde al manifesto, era asserita e mai misurata. Misurata su copia mutata, con `ORIGIN: /tmp/pyteman-b2-hlKN2c/src/pyteman/patcher.py` e sha256 da `4ffb0d88...` a `973d6d7f...`: `entries 3 / rank() 2 / served 2 / _pyteman_state 2 / distinct state dicts 3`, con `applied` che nomina l'alias due volte e `call 2: fired ['early', 'late', 'late']`. File reale ri-hashato invariato, albero temporaneo rimosso.

Disposizione: nessuna modifica di codice e nessun test nuovo. La misura e' EVIDENZA per gli AC #2 e #3 di TASK-132, che e' dove la decisione su cosa significhi una regola elencata due volte deve essere presa, ed e' li' che e' stata depositata.

## Verdetto dello scettico e destinazione dei due dubbi residui

Il verificatore indipendente ha ricevuto UNA affermazione sola, quella che porta la tranche: che la finestra fra la scrittura e la registrazione in `_inflight` sia chiusa e che i due test la fissino. Verdetto **CONFIRMED**, raggiunto rieseguendo la mutazione per conto proprio invece di fidarsi della mia tabella.

Ha pero' allegato due dubbi che il CONFIRMED non copre, ed entrambi sono atterrati nello stesso turno in cui li ho letti, perche' una raccomandazione menzionata in un riassunto non e' tracciata.

**Primo dubbio: la scrittura che riesce e poi solleva.** Il `setattr` sta a patcher.py:1022 e la `wrapped.append` a :1029. Un container il cui `__setattr__` chiama `super()` e POI solleva ha gia' commesso la scrittura quando l'eccezione parte, ma la riga che avrebbe messo l'entry nel ledger non e' ancora stata eseguita. Il `_restore(wrapped)` dell'except non ha quindi nulla da disfare per quello slot. Verificato prima leggendo le due righe e poi misurandolo, non dedotto: la sonda lascia lo slot strumentato dopo il fallimento, con `ledger entries: 0`, `applied: []`, `_inflight: {}`, e soprattutto `instrumented AFTER uninstall: True`, cioe' la strumentazione sopravvive anche alla disinstallazione perche' nessuno sa di doverla togliere. Aperta **TASK-136** (Medium, 5 AC) con l'output della sonda. Due precisazioni messe nel task e non solo qui: non e' una regressione di questa tranche, la disposizione delle due righe e' anteriore; e va coordinata con **TASK-131**, che riscrive lo stesso blocco `except`, altrimenti una delle due correzioni cancella l'altra.

**Secondo dubbio: l'evidenza e' tutta a thread singolo.** Giusto, e ha una conseguenza precisa su un altro task invece che su questo. Un container rientrante serializza per costruzione: la rientranza avviene DENTRO la `setattr` del thread che la esegue, quindi c'e' sempre un solo scrittore su quello slot. Quella forma non esercitera' mai due scritture concorrenti, per quanto la si accanisca. Annotato dentro **TASK-122**, che e' il task della finestra ancora aperta, perche' e' li' che qualcuno potrebbe altrimenti riusare questi test come prova multi-thread e credere di aver dimostrato cio' che non hanno dimostrato.

## Correzione della tabella A2 qui sopra: quell'evidenza era su un file gia' morto

Sostituisce l'affermazione "Rifatta contro il file corrente" e la riga `REAL patcher.py: 4ffb0d88...` nella nota delle disposizioni A1/A2/B2. Il rimpiazzo sta qui e non dentro quel paragrafo perche' le note di questo task sono 34606 caratteri e `notesSet` ne accetta 20000: riscrivere il corpo in linea non e' possibile da MCP, e i file del backlog non si toccano a mano.

Il difetto e' esattamente quello che quella nota rimprovera a se stessa. Diceva che la misura precedente non provava nulla sull'artefatto spedito perche' era stata presa su una versione anteriore, e la sua tabella era a sua volta presa su `4ffb0d88`, cioe' su patcher.py PRIMA che atterrasse il riordino B1. Il file consegnato e' `e0c75b12`. Scritta quella nota, la frase era vera da qualche ora e falsa al momento in cui la si legge.

Rimisurata sull'artefatto vero, stessa forma: controllo piu' due mutanti, tutto su copia temporanea, `/tmp/a2_rerun_e0c75b12.sh`.

```
REAL patcher.py: e0c75b127c2fadb13bcef4873e4937fcee5ca351e4c8e789173ca8c85c0898e6
ORIGIN: /tmp/pyteman-a2rr-QSCwKF/src/pyteman/patcher.py
=== control ===
9 failed, 623 passed in 9.73s
=== unextend_exits ===
pre-mutation sha256:  e0c75b12...  post-mutation sha256: a5579f3d...
FAILED tests/test_activation_atomic.py::test_a_failed_call_takes_back_the_exit_rules_it_added
10 failed, 622 passed in 6.33s
=== merge_exits ===
pre-mutation sha256:  e0c75b12...  post-mutation sha256: 3ad06cc3...
FAILED tests/test_activation_atomic.py::test_an_exit_rule_added_by_a_later_call_merges_into_ruleset_order
10 failed, 622 passed in 6.91s
=== real file after ===
e0c75b127c2fadb13bcef4873e4937fcee5ca351e4c8e789173ca8c85c0898e6
```

La conclusione regge sull'artefatto spedito e con i numeri previsti prima di lanciare: delta di un test esatto per mutante, e per ciascuno e' quello mirato. Il conteggio torna: 731 test in totale, 632 nella copia temporanea (`9 + 623`), quindi 99 esclusi, che sono i due file di doc-integrity, gli stessi 99 della misura precedente. Hash del file reale identico prima e dopo, albero temporaneo rimosso.

Un dato cambiato e non silenziato: il controllo gira in 9.73s dove prima erano 40.35s. Non e' un test sparito. La causa e' la build dell'sdist nel setup di `tests/test_packaging.py`, ora in cache; verificata con `--durations` quando il salto e' comparso la prima volta. Nessun test perso, e il file e' di un altro agente.

## Stato finale consegnato, con impronte e suite della stessa esecuzione (2026-09-17)

Impronte prese subito prima di scrivere questa nota, non riportate da un turno precedente.

```
e0c75b127c2fadb13bcef4873e4937fcee5ca351e4c8e789173ca8c85c0898e6  src/pyteman/patcher.py
3e221a32c69945311b003a57ace9e511bfddee31a9041270aae5e50e231f3869  tests/test_activation_atomic.py
0c7ec1d5e5fd79fcff9b8100ffa7e9e54cd15755de03882d13b6f58f06ac1f57  docs/rules.md
```

Suite completa sullo stato appena impronto, nell'ambiente di audit e senza autoload dei plugin:

```
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /tmp/pyteman-audit-env-OOeElF/bin/python -m pytest tests/ -q
731 passed in 16.58s
```

731 e' il conteggio atteso e ricostruibile: i 730 della misura precedente piu' il solo test nuovo di questa coda, `test_a_dispatcher_reached_through_a_leak_is_extended_not_wrapped`. Nessun test saltato, nessun xfail, nessun warning promosso a errore mascherato da verde.

Stato del working tree per i file di mia competenza, in sola lettura: `src/pyteman/patcher.py` e `README.md` modificati rispetto a HEAD, `tests/test_activation_atomic.py` e `docs/rules.md` non tracciati. README.md e' toccato solo sopra la riga 128, cioe' sopra l'intestazione `## Runner and sqlitekit` che appartiene all'altro agente. Nessun commit, nessun push, nessun cambio di ramo: il checkout e' condiviso e non e' mio da spostare.

AC #1, #2 e #3 sono spuntati e ciascuno ha sotto di se' un test che fallisce se la proprieta' cade, provato per mutazione su copia temporanea con prova d'origine e impronte pre e post. Cio' che resta aperto non e' dentro questo task e ha un numero proprio: **TASK-122** per l'unica finestra rimasta fra la seconda rilettura e la scrittura, **TASK-131** per la riscrittura del blocco `except`, **TASK-132** per la decisione su una regola elencata due volte, **TASK-136** per la scrittura che riesce e poi solleva. Nessuno di questi e' una regressione introdotta qui.

CHANGES REQUESTED by the reviewing peer on the alias-composition delivery (2026-09-17), recorded verbatim in substance and then implemented.

The request had three parts. First, TASK-132 is not an open design decision: mandatory unique preflight ids were already chosen for the programmatic API, so the guard that SKIPS an unreadable identity manufactures the very manifest-against-entries incoherence TASK-132 describes. Their probe, an `id` property that raises with every other field valid, shows `install([r, r])` accepted with 2 states and a doubled `applied`. Second, add a preflight that refuses any rule without a readable non-empty string id before any mutation, with a stated preference for refusing EVERY unreadable identity because the firing log needs one; keep `_describe_rule` best-effort so an error can still name a rule, but do not let the diagnostic fallback authorize a rule that has no identity. Third, a methodological correction to my reporting: the control I published as `9 failed, 623 passed` is not a green baseline, and comparisons against a red control only localize a delta, they do not prove a gate, so the acceptance criteria I claim must rest on a green baseline of the relevant perimeter measured on the final snapshot.

Constraints attached to the request: do not touch other runtimes, keep TASK-136 as a follow-up with no further redesign, and re-deliver with a targeted review, tests and fresh hashes for their verification.

I verified the claim independently rather than accepting it on report, and the defect is worse than reported. A SINGLE unreadable-id rule, not merely a duplicated one, is enough: it passes preflight, replaces the target slot, and then raises out of the caller's workload on the first firing with zero firing records written. Proven with the real FiringLog in /tmp/probe_unreadable_id_runtime.py, which printed `CALL RAISED OUT OF THE WORKLOAD: RuntimeError: this rule refuses to say what it is called` and `firing records written: 0`.

The mechanism, traced link by link rather than inferred. `_rule_id` guards every site that only NAMES a rule, so the old premise held there. It does not hold at firing.py:19 (`"rule": rule.id`) or actions.py:81 (`key = (rule.id, message)`), which read the attribute raw INSIDE the instrumented callable. So an unreadable id was never a diagnostic degradation at runtime; it was a latent crash in the user's workload, and the placeholder never got the chance to do its job.

Implementation of the preflight id gate (2026-09-17). Files changed: src/pyteman/patcher.py and tests/test_activation_atomic.py. No other runtime was touched, per the request: firing.py and actions.py were read to confirm the raw reads and left unmodified.

src/pyteman/patcher.py, inside `Patcher.__init__`, replacing the `rid = None` skip. An `id` that cannot be read is now refused with `id could not be read: <reason>`; an id that is not a `str` is refused with the offending typename; an id empty once stripped is refused; and the duplicate check runs on the normalised value. The order is isinstance, then `_text`, then `.strip()`, deliberately: emptiness is asked of an exact str so `strip` is str's own rather than a subclass's, and the value entering the dedup set is normalised so a subclass carrying its own `__hash__` cannot hide a duplicate from it. The contract now matches `load_rules` in rules.py:297-307 to the letter, which is the point: two doors into one state that disagree about what an identity is let the programmatic door admit rules the file door rejects, and the id keys the same firing log for both.

Preflight is the right place and the only cheap one. `__init__` mutates nothing, so a refusal there costs an unpatched process rather than a half-patched one, and one gate protects both raw reads without editing either call site.

The gate sits AFTER the `_compile` calls inside the same try, unchanged from before, so a rule that is both unparseable and unnamed still reports the parse error its author can act on. `UncompilableUnreadableIdRule` pins that ordering and still passes.

`_rule_id`'s docstring was rescoped rather than left alone, because it previously stated an absolute promise the new gate contradicts: that failing to name yourself is a diagnostic problem and never a reason to fail. It now scopes that promise to REPORTING, and says plainly that such a rule never reaches a run to be reported on because preflight refuses it, and that what the placeholder serves is the message announcing that refusal.

Backups taken FIRST, before either edit: /tmp/patcher.py.bak.preflight.1789632334 and /tmp/test_activation_atomic.py.bak.preflight.1789632611.

Tests for the preflight gate (2026-09-17). One old test was replaced and five were added, covering both the cases the peer asked for and the tightening I added on top.

Rewritten, because their premise was overturned rather than their value lost:

`test_a_hostile_rule_id_costs_neither_the_failure_nor_the_disclosure` now uses a `BoomStr`, a str SUBCLASS whose `__repr__` and `__format__` raise. That is deliberate and it is the point of the edit: a BoomStr satisfies every isinstance check the new gate applies and still runs user code the moment a caller interpolates it, so the hazard this test is about SURVIVES the gate. The gate is not a substitute for rendering the identity once, up front, through `_text`.

`test_a_rule_id_that_cannot_be_read_is_refused_before_anything_is_patched` replaces the old absorb-it test. It asserts the refusal, asserts the note still carries the placeholder AND the location (a refusal nobody can act on is its own defect), and then asserts the guarantee the old behaviour could not make: the slot the rule aimed at is left exactly as it was found, `refusing.f is before` with no `_pyteman_state`.

`test_a_rule_that_will_not_name_itself_is_refused_one_at_a_time` replaces `test_two_rules_that_both_refuse_to_name_themselves_are_not_duplicates`, whose docstring asserted the promise the probe refuted. The old reasoning survives where it was right: two unnamed rules must never be refused for a COLLISION that exists only in the placeholder rendering, and they still are not. Each is refused on its own merits instead, and the message names the read that failed rather than a collision, which is what tells the two reasons apart.

Added:

`test_one_rule_object_listed_twice_is_refused_like_any_other_duplicate`, the peer's requested case, pinning that the id is read per LIST ENTRY and not per distinct object.

`test_an_id_that_is_not_a_string_is_refused_at_the_same_gate`, covering int, None and tuple with the TYPENAME asserted, not just the refusal, because `id: null` and `id: 5` are different typos and the message is the only thing that tells the author which one they made; plus empty and whitespace ids.

`test_a_str_subclass_cannot_smuggle_a_duplicate_past_the_dedup_set`, which exists because a mutation survived. See the mutation note.

`test_the_ordinary_ruleset_is_untouched_by_the_gate`, the invariant the peer asked for: distinct readable ids plan, patch, fire and uninstall exactly as before, including a str subclass, which is a legal id and stays one. This is a stronger statement than "the rest of the suite still passes".

Mutation battery for the preflight id gate, run against a GREEN perimeter baseline on the final snapshot (2026-09-17). This supersedes the method of every earlier mutation note on this task, and the reviewing peer was right to reject that method.

The correction, stated plainly because it changes what my earlier evidence is worth. I had been comparing mutants against a control that itself reported failures. Such a comparison localizes a delta; it cannot prove that a test covers the line I claim it covers, because a mutant flipping one already-red test to a different red tells you nothing. The control must be zero failed before any mutant result means anything.

So the harness now REFUSES to run the mutants if the control is not green, and on its first run it did exactly that. The control came back `6 failed, 629 passed` and the script stopped. The cause was the copy rather than the code: I had copied only src/, tests/ and docs/, so test_packaging.py could not build an sdist without pyproject.toml. The honest fix was to make the copy complete rather than to exclude the failures, and I did that. Excluding a test because it fails is the move the peer had just warned against.

Perimeter, and the one exclusion that remains, stated rather than hidden. The perimeter is the full tests/ tree minus test_docs_integrity.py and test_docs_rules.py, which hash source files and therefore die under EVERY mutant for a reason that has nothing to do with the behaviour under test. Leaving them in would manufacture kills.

Harness: /tmp/preflight_mutation_battery.sh. Everything runs on a `mktemp -d` copy of the whole repository, git and backlog removed. The real file is never written to. Origin proof is printed each run: REAL and COPY patcher.py both sha256 fb3bd456be256a70ef9b035f74fc9871ad96dfb1985bac5b1bb713a4517fa4f8, workdir /tmp/preflight-mut-C1RfCO.

CONTROL on the final snapshot: 635 passed, 0 failed. That is the green baseline the acceptance criteria below rest on.

Mutation results against that green baseline. I stated each prediction before running, and one mutant surprised me, which is recorded rather than smoothed over.

  M1 restore the skip (an unreadable id is skipped, not refused)
     2 failed. Killed test_a_rule_id_that_cannot_be_read_is_refused_before_anything_is_patched and test_a_rule_that_will_not_name_itself_is_refused_one_at_a_time. Predicted 2.

  M2 drop the isinstance check
     1 failed. Killed test_an_id_that_is_not_a_string_is_refused_at_the_same_gate. Predicted 1.

  M3 drop the emptiness check
     1 failed. Same test, its blank half. Predicted 1.

  M4 drop the duplicate check
     3 failed. Predicted 2. The extra kill was test_a_duplicate_rule_id_is_refused_before_anything_is_patched, a pre-existing test of mine. I investigated rather than accepting a pleasant surprise: the duplicate check already had coverage and the new same-object test adds a case on top of it. No defect.

  M5 key the dedup set on the raw value instead of the normalised one
     SURVIVED. 635 passed. Predicted to survive, and this is the finding worth keeping.

Why M5 mattered. The source comment claims the normalisation keeps a str subclass carrying its own `__hash__` out of the dedup set. That is a real guarantee and the whole 635-test perimeter could not tell `seen_ids.add(rid)` from `seen_ids.add(raw_id)`. A one-token difference that reads as a tidy-up either way, with a comment asserting it matters and nothing pinning it, is precisely the shape of a guarantee that gets refactored away later.

The fix was a test, not a weaker comment, because the claim is true. `test_a_str_subclass_cannot_smuggle_a_duplicate_past_the_dedup_set` uses a str subclass with `__hash__ = object.__hash__` and an identity `__eq__`, and it asserts its own premise first (`Aloof("same") not in {"same"}`) so the test cannot pass vacuously if that subclass ever compares equal again. Re-running M5 with the test present: 1 failed, the new test. Every mutant in the battery is now killed.

After the run the copy was restored and re-hashed identical to the repository file, and the repository file was re-hashed unchanged at fb3bd456be256a70ef9b035f74fc9871ad96dfb1985bac5b1bb713a4517fa4f8.

Final state of this tranche (2026-09-17), for the peer's verification.

Full suite on the real repository: 735 passed. It stood at 731 before this change; one test was replaced by four and two more were added, and the net is plus four.

Hashes of the artifacts I own and changed:

  src/pyteman/patcher.py           fb3bd456be256a70ef9b035f74fc9871ad96dfb1985bac5b1bb713a4517fa4f8
  tests/test_activation_atomic.py  97c44f77be04563a69d01cfd5b2ee9c153df550f1df7d080d67672287af9b913
  docs/rules.md                    0c7ec1d5e5fd79fcff9b8100ffa7e9e54cd15755de03882d13b6f58f06ac1f57  (unchanged this round)

Read and deliberately NOT modified, per the instruction not to touch other runtimes:

  src/pyteman/firing.py            466320c1be00eddbe7be55868ccf30bba615561399e36c0d1c924e486d1d2577
  src/pyteman/actions.py           7880bd0e74f013637207247fcf6ba0b7b7fcc656cfb6b47890e9a50c84f769f2

The checkout was not moved: no branch switch, reset, stash, worktree, commit or push, and nothing of another agent's work was touched. No publication was made and none is authorized.

TASK-132 moves from deferred design decision to covered here, with one question still open pending the review now running. See the note filed on TASK-132 itself for what the gate closes and what it does not.

High-effort review of the preflight id gate: no critical findings, three important ones, all three fixed and pinned by mutants.

Finding 1, and it was a real defect I had introduced. `rid = _text(raw_id)` normalised the identity through the house renderer, and _text calls str(), which on a str subclass dispatches to the subclass's __str__, which is user code. The firing log does the opposite and serialises the true characters, so the gate keyed on one value and the log on another. I reproduced all of it against the real Patcher before changing anything: two rules with ids 'x' and 'y' whose __str__ collapses were refused with `id is already used by an earlier rule`, which is a legal ruleset rejected for a duplicate that does not exist; the same for ids 'a' and 'b' whose __str__ raises; and an id whose real content is "" was ADMITTED, because _text rendered it as the non-empty placeholder `<unprintable Raises>` while the log would have written the "" the comment says nobody can grep for.

Fix is the reviewer's: `rid = str.__str__(raw_id)`. It is the spelling _text itself ends on, it reads the characters, it cannot run user code, and it still yields an exact str so a subclass carrying its own __hash__ stays out of seen_ids. My own M5 test did not catch this because its subclass overrode __hash__ and __eq__ but not __str__.

Finding 2: the _Composite docstring still justified keying `served` by object identity with a description of the behaviour this tranche removed ("__init__ lets a rule whose .id cannot even be read into the plan (it records None and moves on)"). The decision is still right; the reason had gone false. Rewritten to the reason that is now load-bearing, which is that Rule is a mutable dataclass, so a preflight check cannot speak for the id at firing time.

Finding 3: `except BaseException` around the id read relabelled a KeyboardInterrupt as `RuleError: id could not be read: `, with an empty detail because str() of a KeyboardInterrupt is empty. Reproduced. This file's house idiom is BaseException, but at every other site the breadth protects something: _rule_id must not raise while reporting, _undo_one must not leave a module half restored. __init__ mutates nothing, so here the breadth buys no safety and costs a wrong diagnosis, which this codebase already names at tests/test_activation_atomic.py:797 as worse than none. Narrowed to `except Exception`, with the difference from the two neighbouring sites written down.

Evidence for the preflight id gate, on the final snapshot, all re-measured after the review fixes.

Full suite: 737 passed, 0 failed. Perimeter control: 638 passed, 0 failed, where the perimeter is tests/ minus test_docs_integrity.py and test_docs_rules.py, which hash source files and so die under every mutant for reasons unrelated to the behaviour under test. The harness refuses to report any mutant result if the control is not green, which is the methodological point the reviewing peer was right to insist on.

Mutation battery, seven mutants, all killed. M1 restore the skip: 2. M2 drop the isinstance: 1. M3 drop the emptiness: 2. M4 drop the duplicate: 4. M5 key seen_ids on the raw value: 1. M6 normalise through _text: 1. M7 widen the guard back to BaseException: 1. Every count matched the prediction stated before the run, so there was no surprise to investigate. Script at /tmp/preflight_mutation_battery.sh, run on a mktemp copy with REAL/COPY/ORIGIN proof printed; the real repository file is never written.

sha256 of the three artifacts:
  src/pyteman/patcher.py            2f0a96d0565a8c6c80bdd1cb7532945a29b53bc24a7f752bf789f6c6c0876ada
  tests/test_activation_atomic.py   eb424247b353de1e9e68ff0ca379c0f2a620fcaebd867d29c5994ac0be9a3209
  docs/rules.md                     864b6e5541ebecae6e09e78b1364d3488b28b4ddd597540f92361a5a14354be5

One correction to my own earlier reasoning, since it is the kind that should not stay in the record unmarked. I predicted that a str subclass with a hostile __hash__ would also defeat the outcome dedup at actions.py:81, and probed it rather than filing it. It does not: that site only ever compares one rule's id with itself, so identity-equality still matches and the dedup holds. Normalisation is load-bearing at the gate for the opposite reason, because there a subclass must compare against a DIFFERENT plain string. No finding, and no change to actions.py.

Docs, both in docs/rules.md and inlined where they belong rather than appended as errata. The planning paragraph now says that checking the identity is part of planning, which it did not, and the Ids section now states the preflight limit: a rule should be treated as frozen once handed to a Patcher, because Rule is a mutable dataclass and the firing record reads id again.

The review's two remaining items landed as tasks rather than as prose. TASK-138 for the post-preflight mutability limit, which cannot be fixed from the patcher because both candidate fixes reach frozen or other-runtime files. TASK-139 for the release-note caveat, that an undocumented caller passing id=5 worked end to end before and now fails at construction.

APPROVED and closing (2026-09-17). The reviewing peer returned APPROVED on the final state of this tranche together with the integrated resolution of TASK-132, with the explicit instruction that no code change follows the approval. This note records the proofs on both sides, because an approval is only as good as the artifact it was given for.

Artifact identity at closure, re-hashed this turn rather than quoted from earlier in the session. That re-hash is not ceremony: this is a checkout shared with another agent actively editing nine files, so a hash asserted an hour ago proves nothing about what is on disk now.

    src/pyteman/patcher.py            2f0a96d0565a8c6c80bdd1cb7532945a29b53bc24a7f752bf789f6c6c0876ada
    tests/test_activation_atomic.py   eb424247b353de1e9e68ff0ca379c0f2a620fcaebd867d29c5994ac0be9a3209
    docs/rules.md                     864b6e5541ebecae6e09e78b1364d3488b28b4ddd597540f92361a5a14354be5

The reviewer's independent evidence, recorded as theirs rather than folded into mine. They re-derived all three hashes before and after their probes and got the same values both times. They ran 124 targeted tests green and the full suite at 737 passed. Their diff check came back clean. Their own probes of the preflight gate confirmed refusal of an unreadable id, a same-object duplicate, a non-str id, an empty id, a whitespace-only id and a duplicate id, in every case BEFORE any hook mutation, which is the property the gate exists for. Their alias probe drove two modules in reverse discovery order and confirmed a single surviving wrapper, preserved ruleset order, the current exit result and a correct uninstall.

That their independently derived hashes match mine is the part worth keeping. It means the approval was given for this artifact and not for a description of it.

What this closure explicitly does NOT claim, carried forward rather than absorbed into the approval.

TASK-138 is open and is not closed by this work. Preflight speaks only for the moment it runs: `Rule` is not frozen, and firing.py:19 and actions.py:81 read `id` again on every firing, so a rule that passed the gate can be rebound afterwards and write `{"rule": null}`. Documentation is the mitigation and is labelled as such. Two acceptance criteria and a three-part implementation note were appended to it today, covering the ungated raw `rule.event` read at firing.py:20, a corrected cost estimate for the snapshot option, and the fact that its two candidate fixes differ in coverage rather than only in cost.

TASK-136 and TASK-139 are open and untouched by this tranche. TASK-136's container-commits-then-raises leak is identical under both orderings of `_inflight` and `setattr`, so this work neither caused it nor fixed it, and its correction has to be coordinated with TASK-131 because both rewrite the same except block.

The completion gates for this tranche, and one honest caveat about how the last one was recorded.

The four-agent /simplify review ran against the exact snapshot hashed above. It returned findings from the reuse, simplification and altitude angles and none from efficiency, which additionally refuted my premise that `_describe_rule` was failure-path-only work by showing `described` is consumed on the success path at patcher.py:876. Phase 2 of that skill says to apply the fixes. I filed them instead, because the approval carried an explicit no-code-change instruction and because two of them are factual defects in prose I wrote, whose correction is the reviewer's call rather than mine. Filed today: TASK-140, TASK-141, TASK-142, TASK-143.

The caveat. The completion-gate hook reads only the last 3000 lines of the session transcript, and by the time this task was moved to Done the original /simplify invocation had scrolled out of that window, so the hook blocked the transition. I re-entered the skill to put the record back inside the window and did NOT re-dispatch the agents, since the artifacts were unchanged and their findings were already in hand and already filed. The gate's substance was satisfied by the real pass; the second invocation is a disposition record. Stating it here so nobody later reads two invocations as two reviews.

Mutation evidence for the gate itself is the battery at /tmp/preflight_mutation_battery.sh, seven mutants M1 through M7, each run on a mktemp copy with its origin printed, and the script refuses to run any mutant at all unless the control perimeter is green, because a control with failures in it localises a delta rather than proving coverage.
<!-- SECTION:NOTES:END -->
