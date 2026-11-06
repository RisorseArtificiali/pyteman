---
id: TASK-5
title: RT-05. Rendere install/uninstall idempotenti e rispettosi di patch altrui
status: Done
assignee: []
created_date: '2026-09-16 12:20'
updated_date: '2026-09-17 01:18'
labels:
  - audit-2026-09-16
  - opus-5
  - rt
  - confirmed
milestone: m-0
dependencies:
  - TASK-1
references:
  - 'src/pyteman/patcher.py:37-42,101-120'
documentation:
  - doc-1
  - doc-2
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P1, CONFIRMED, aperto.

**File:** `src/pyteman/patcher.py:37-42,101-120`.

**Evidenza:** install_hook due volte seguito da uninstall lascia il primo hook attivo. Due patcher disinstallati fuori ordine rimuovono il secondo hook e poi resuscitano il primo. Una sostituzione del callable fatta dopo pyteman viene sovrascritta da uninstall. Patchare un metodo ereditato e disinstallarlo lascia un attributo sulla sottoclasse: modifiche successive alla classe base non si propagano più.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Regressioni per ogni sequenza dell'evidenza: doppio install_hook, due patcher disinstallati fuori ordine, libreria che sostituisce il callable dopo pyteman, attributo ereditato, reinstallazione dopo uninstall.
- [x] #2 Uninstall riporta alla semantica originale senza eliminare modifiche estranee e senza lasciare attivo un hook pyteman.
- [x] #3 Il rifiuto dell'uninstall fuori ordine e' un esito SUPPORTATO: solleva prima di ogni mutazione, non tocca ne' hook ne' wrap, ed e' coperto da test; dopo la rimozione del patcher interno quello esterno torna disinstallabile.
- [x] #4 Un hook estraneo installato dopo pyteman viene preservato; se delega all'hook pyteman disattivato, quest'ultimo non applica nuove patch. Testati sia il fake hook che delega sia il replacement semplice.
- [x] #5 Uno slot non piu' posseduto e' un rilascio riuscito dell'ownership: oggetto estraneo preservato, entry rimossa dal ledger, nessun refusal e nessun allargamento di _disclose; lo skip e' documentato e testato.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Stato VERIFICATO sul codice corrente il 2026-09-17 (patcher.py a 673 righe, sha256 314e1133..., origine provata via `__file__` in una sonda in /tmp). I riferimenti del campo References (`patcher.py:37-42,101-120`) sono numeri di riga di HEAD a 146 righe e NON mappano sul file attuale: le funzioni interessate sono `install_hook` (562-573), `uninstall` (575-604), `_restore` (163-252) e l'append al ledger in `_patch` (439-449).

Tutte e quattro le sequenze dell'evidenza si riproducono ancora. Una quinta, non nominata dal task, e' l'occorrenza storica duplicata in `applied` dopo uninstall e nuovo patch: per decisione dell'orchestrator NON e' un bug e va tracciata su TASK-62, non corretta qui.

CONTRATTO SCELTO, registrato prima del codice.

1. `install_hook` idempotente. Se `_orig_import` non e' None l'hook e' gia' installato: la chiamata ritorna senza agganciare e senza registrare eventi.

2. Nesting supportato ESCLUSIVAMENTE LIFO. `uninstall` classifica l'hook vivo PRIMA di qualunque mutazione, in tre casi:
   - l'hook vivo e' il mio: ripristino `_orig_import` e procedo ai wrap;
   - l'hook vivo e' quello di un ALTRO Patcher, riconosciuto da un marcatore sulla closure: uninstall fuori ordine, RIFIUTO esplicito prima di ogni mutazione, ne' hook ne' wrap toccati; dopo la rimozione del patcher interno questo torna disinstallabile;
   - l'hook vivo e' ESTRANEO, installato dopo di noi da terzi: preservo l'hook estraneo, non scrivo `builtins.__import__`, e procedo comunque ai wrap.

   Il solo test "l'hook vivo e' il mio" NON basta e la ragione va scritta nel codice: p1 declina perche' vede h2, poi p2 ripristina il proprio `_orig_import`, che e' h1, e resuscita l'hook di p1. Serve il rifiuto, non solo l'astensione.

3. Disattivazione della closure invece della sua rimozione. Non si promette la rimozione fisica del nostro hook dalla catena di un terzo: se l'estraneo delega al nostro, il nostro resta raggiungibile. Il nostro hook porta quindi uno stato di attivita' e, una volta disinstallato, diventa pass-through: delega e NON applica nuove patch. E' questo che rende onesto il caso 2c.

4. Ledger a cinque elementi `(container, name, original, wrapper, owned)`. `wrapper` e' l'oggetto ESATTO installato; `owned` dice se `name` era in `container.__dict__` al momento del patch, cioe' distingue posseduto da ereditato.

5. Ripristino solo su identita' OSSERVATA:
   - live e' il nostro wrapper e `owned`: `setattr(container, name, original)`;
   - live e' il nostro wrapper e non `owned`: `delattr(container, name)`, cosi' l'ereditarieta' torna viva e una modifica successiva alla classe base si propaga di nuovo;
   - live NON e' il nostro wrapper: RILASCIO RIUSCITO dell'ownership. Oggetto estraneo preservato, entry rimossa dal ledger, nessun refusal, nessun nuovo prefisso o canale, `_disclose` invariato. Skip intenzionale, documentato e testato;
   - la LETTURA di live solleva: refusal sul canale esistente, perche' non si puo' ne' confermare il rilascio ne' ripristinare.

6. `applied` resta storico compatibile e non viene ridefinito qui. Install idempotente non aggiunge eventi; uninstall seguito da un vero nuovo patch puo' aggiungere una nuova occorrenza storica. Precisazione e regression su TASK-62.

7. Nessuna nuova concorrenza cross-thread. I limiti gia' dichiarati restano quelli di TASK-58 e di docs/rules.md; best effort e dettagli esistenti invariati.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: RT-02 e RT-04 vanno coordinati, stesso file.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.
Implementare il contratto di ownership prima di RT-02/RT-04; questi ultimi sono consumer da coordinare, non prerequisiti.

IMPLEMENTAZIONE COMPLETATA 2026-09-17. Contratto applicato esattamente come registrato nell'Implementation Plan sopra, nessuna deviazione. Gate di review ancora in corso al momento di questa nota; i loro esiti vengono aggiunti sotto quando rientrano.

**Cosa e' cambiato, in `src/pyteman/patcher.py`.**

1. Nuova `UninstallOrderError(RuntimeError)`, definita prima di `class Patcher`. Segue la convenzione del pacchetto (`Matrix*Error(RuntimeError)` in `runner/`), non introduce una gerarchia nuova.
2. `Patcher.__init__` guadagna `self._hook = None` accanto a `self._orig_import`.
3. `install_hook` esce subito se `_orig_import` non e' None. La closure porta `hooked._pyteman_patcher = self` per il riconoscimento cross-Patcher, e il corpo e' gated da `if self._hook is hooked`. La guardia e' su IDENTITA' e non su un booleano di proposito: una reinstallazione ritira definitivamente la vecchia closure, perche' `_hook` da quel momento nomina un'altra.
4. `uninstall` classifica `builtins.__import__` in tre casi prima di qualunque mutazione, esattamente nell'ordine del contratto, e solleva nel caso (b) senza avere toccato niente.
5. Ledger a cinque elementi in `_patch`; `owned` calcolato da un nuovo `_owns_name(container, name)` che chiede `name in vars(container)` invece di `hasattr`.
6. `_restore` delega a un nuovo `_undo_one(entry)` che ritorna una tripla di refusal oppure None. Tre esiti, uno solo dei quali e' un fallimento: restore, release, refuse. La guardia di cancellazione nel chiamante resta larga un solo ramo e il `entries[i] is entry` pinned dal mutation test resta intatto.
7. Nuovo `_is_pyteman_hook(fn)`, guardato con `except BaseException`, perche' un `__getattr__` che solleva non deve trasformare la domanda nel fallimento.

**Prosa assorbita, non rimandata.** I rilievi 1, 2, 3, 4 e 6 della review precedente sono stati assorbiti come prosa delle funzioni toccate, come richiesto: docstring di `activate` ("unwinding on failure" invece della promessa non mantenibile "leave nothing behind"), sommario di `_restore` ("best effort" invece di "always completing"), commento del `finally` in `_patch` (il ledger che si accorcia sotto e' quello condiviso di `uninstall`, non il locale), commento di apertura di `_make_wrapper` (analisi a PATCH-time, non a install-time), e taglio da 40 a 8 righe della derivazione duplicata dei costi, che ora rimanda a `docs/rules.md` come unica fonte.

**Test.** Sette regression nuove in `tests/test_activation_atomic.py`, sotto il banner `# --- uninstall really gives the process back ---`, piu' una fixture `inheriting` e un helper `_entry(...)` che costruisce una entry del ledger nella forma che `_patch` pubblica. Otto call site preesistenti migrati alla forma a cinque elementi, ognuno riletto con la sua fixture prima di toccarlo perche' pinnano comportamento load-bearing (guardia di bounds, guardia `is`-non-`==`, percorso KeyboardInterrupt).

Una asserzione preesistente e' cambiata DI PROPOSITO, ed e' un miglioramento osservato e non previsto: `test_restore_survives_a_ledger_that_shrank_to_the_cursor` ora asserisce `writes == ['ORIGINAL-M']` dove prima erano due. Registrare il wrapper nella entry ha ritirato la doppia scrittura documentata: alla seconda visita lo slot contiene l'originale e non il wrapper di quella entry, quindi si rilascia invece di scrivere. Il costo di uno shift e' ora una lettura sprecata.

**Evidenza, non asserzione.** Suite completa: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /tmp/pyteman-audit-env-OOeElF/bin/python -m pytest tests/ -q` -> **629 passed** (erano 622 prima delle sette nuove).

I test verdi non provano di mordere, quindi e' stato eseguito un mutation check su una COPIA dell'albero sotto `/tmp/mutcheck-task5`, mai sul repo. Origine provata (`patcher.__file__` sotto `/tmp`, PYTHONPATH che vince sul `.pth` editable), sha256 del file di repo identico prima e dopo la corsa. Otto mutazioni, una guardia rimossa per volta, ognuna asserita applicata esattamente una volta: controllo non mutato VERDE, **8/8 mutanti uccisi**. Le otto: idempotenza di `install_hook`; il raise fuori ordine sostituito da astensione; preservazione dell'hook estraneo sul percorso che delega; la stessa sul replacement semplice; la guardia di attivita' della closure; la guardia di identita' del wrapper; il ramo `delattr`; `applied` svuotato da `uninstall`.

**Documentazione.** `docs/rules.md` aggiornato in due punti, entrambi resi necessari da questa tranche e non cosmetici. Primo: la derivazione della doppia scrittura era diventata FALSA, ed e' proprio il passo che il docstring accorciato di `_restore` ora indica come unica fonte; riscritta per dire che il costo e' una lettura sprecata, che resta un solo duplicato sul ramo del refusal, e che registrare il wrapper rende impossibile una scrittura SBAGLIATA ma non una MANCATA. Secondo: la frase "only a `setattr` that actually returned drops an entry" era diventata incompleta, perche' ora un entry esce dal ledger su tre esiti e non uno; corretta, e aggiunti due paragrafi nuovi che documentano il rilascio come successo silenzioso e il contratto dell'hook (LIFO soltanto, `UninstallOrderError`, hook estraneo preservato, hook nostro ritirato e non rimosso).

**Fuori perimetro, rispettato.** Nessun cleanup di `sitecustomize`, nessun consolidamento di fixture condivise fra file, nessuna ottimizzazione di closure (TASK-100), nessuna ridefinizione di `applied` come stato vivo, nessuna nuova concorrenza cross-thread, nessuna nuova macchina di rollback per oggetti ostili. Nessun commit, push, checkout o reset: l'albero e' modificato e non committato, come richiesto.

ESITI DEI DUE GATE, 2026-09-17. Questa nota chiude la riserva lasciata sopra ("i loro esiti vengono aggiunti sotto quando rientrano"). Entrambi i gate sono rientrati, entrambi in sola lettura e senza agenti che scrivessero. La sostanza: il gate /simplify ha prodotto solo rilievi di qualita', mentre la code review ha trovato DUE REGRESSIONI REALI introdotte da questa stessa tranche, corrette qui perche' stanno nel codice nuovo di TASK-5 e non allargano il perimetro.

**Premessa metodologica, perche' cambia come vanno letti i rilievi.** La code review ha dichiarato di non avere eseguito nulla ("I have no shell in this thread"): ogni sua affermazione era quindi una deduzione dal sorgente, non una misura. Nessun rilievo e' stato accettato per fiducia. E' stata scritta una sonda in sola lettura, `/tmp/review_probe_task5.py`, con asserzione di origine (`patcher.__file__` sotto il `src/` del repo) e stampa dello sha256 del file letto, che riproduce i tre rilievi sullo stato di lavoro. Tutti e tre si sono riprodotti. Il rilievo 2 si e' rivelato il caso peggiore possibile: distruzione silenziosa di dati riportata come successo.

**Gate /simplify: sette rilievi, sei applicati, uno depositato.** Tutti di qualita' della prosa, nessuno di correttezza, coerentemente con il fatto che dal giro precedente erano cambiati solo docstring, commenti e documentazione. Applicati: due paragrafi del docstring di `_restore` spostati su `_undo_one`, dove il codice che descrivono adesso vive (il handler per-slot e la scelta di `BaseException`); il commento al call site del ledger in `_patch` ridotto al solo fatto non duplicato altrove; il paragrafo sul refusal come no-op ripiegato dentro il rimando incrociato di `uninstall`; due ritrattazioni auto-referenziali tolte dai docstring di `activate` e `_restore`; la guardia di `install_hook` allineata a quella di `uninstall` (`self._hook is not None` invece di `self._orig_import is not None`), verificata sicura prima della modifica censendo con grep tutte e sei le occorrenze dei due campi e confermando che i tre siti di scrittura scrivono sempre entrambi; e il riavvolgimento di riga di `docs/rules.md` rimesso a una colonna coerente. Skippato e depositato su **TASK-72**: la fixture `inheriting` riscrive a mano il ciclo di vita di `sys.modules` che `_victim_module` incapsula, perche' la correzione onesta e' spezzare in due una fixture condivisa da tutta la suite, cioe' esattamente il cleanup di fixture che l'orchestrator aveva messo fuori perimetro.

**Code review, rilievo 1: CORRETTO. Un hook pyteman RITIRATO incuneava il Patcher sottostante, in modo irreversibile.** `install_hook` marchia la closure con `hooked._pyteman_patcher = self` e `uninstall` non toglie mai quel marchio, perche' a quel punto la closure puo' essere raggiungibile solo da dentro la catena di un terzo. Il marchio sopravvive quindi all'hook. La prima stesura di `_is_pyteman_hook` classificava sul solo marchio, quindi un Patcher che aveva GIA' disinstallato continuava a rispondere, e il Patcher esterno rifiutava la propria uninstall per conto di uno che se n'era andato. Il rifiuto non era sollevabile da nessuno: il `_hook` del Patcher ritirato e' gia' `None`, quindi la sua `uninstall()` e' un no-op e non puo' ripulire niente. E poiche' il raise precede `_restore(self._wrapped)`, restavano bloccati anche i WRAP del Patcher esterno, non solo il suo hook. Correzione: chiedere al proprietario dichiarato se quello e' ancora il SUO hook (`owner._hook is fn`), cioe' trasformare un'etichetta permanente in una relazione viva. Effetto collaterale gratuito e verificato: un oggetto che sintetizza attributi a richiesta, come un `MagicMock` messo al posto di `__import__` da `mock.patch`, risponde al marchio con un mock figlio ma non supera il giro di ritorno, quindi viene classificato per l'estraneo che e' e lasciato al suo posto invece di essere cancellato.

**Code review, rilievo 2: CORRETTO. `delattr` svuotava lo storage di un data descriptor, distruggendo l'originale e riportando un restore pulito.** `_owns_name` risponde `name in vars(container)`, che distingue due casi su tre. Un membro di `__slots__` o una `property` sono storage PROPRIO del container e non compaiono mai nel suo `__dict__`. Registrare `owned=False` e poi chiamare `delattr` su uno di quelli SVUOTA lo slot: l'originale sparisce dal processo e `uninstall()` ritorna `[]`, cioe' dichiara di avere rimesso tutto a posto. Misurato dalla sonda, non dedotto: `svc.handler after uninstall: AttributeError`, `uninstall() reported: []`. La property senza deleter produce la variante piu' mite dello stesso difetto, un rifiuto permanente per uno slot che un `setattr` avrebbe ripristinato. Correzione: `if owned or not _owns_name(container, name)`, cioe' rifare la domanda al momento dell'undo invece di fidarsi della risposta registrata, cosi' che `delattr` giri soltanto mentre il nostro wrapper e' dimostrabilmente nel `__dict__`, che e' l'unico stato per cui e' corretto. La risposta registrata al patch-time resta necessaria, perche' l'MRO puo' cambiare nel frattempo; cio' che il secondo controllo aggiunge e' il vincolo sulla `delattr`. Aggiornati di conseguenza i docstring di `_owns_name` e di `_undo_one`, che affermavano entrambi qualcosa che il codice corretto non fa piu'.

**Code review, rilievo 3: NON corretto, depositato su TASK-73.** Un nome CANCELLATO dal container dopo il wrap fa sollevare `AttributeError` alla lettura che apre `_undo_one`, che finisce sul canale dei refusal: la entry resta e viene ri-segnalata per sempre per qualcosa che non e' piu' wrappato. Non e' un difetto di questa tranche ma una decisione di contratto, e la review stessa lo inquadra cosi'; instradarlo sul percorso di rilascio rilascerebbe silenziosamente anche il container ostile il cui `__getattr__` solleva per scelta. Fuori dal "niente nuova fan-out implementativa". Nello stesso giro e' stato depositato li' anche il sotto-rilievo sul rilascio falso quando il `getattr` di un container non restituisce cio' che il `setattr` ha memorizzato. `docs/rules.md` e' stato pero' CORRETTO nella stessa tranche invece di lasciarlo affermare una corrispondenza fra ledger e wrap che il codice non ha: la frase ora dichiara l'eccezione del nome cancellato.

**Nuova evidenza dopo le correzioni.** Quattro regression aggiunte, che pinnano le due correzioni: hook pyteman ritirato che non incunea il Patcher sotto; proxy che sintetizza attributi classificato come estraneo; membro di `__slots__` ripristinato da `setattr` invece che svuotato; property senza deleter ripristinata invece che rifiutata. Suite completa: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /tmp/pyteman-audit-env-OOeElF/bin/python -m pytest tests/ -q` -> **633 passed** (erano 629). Il mutation check e' passato da 8 a 12 mutazioni, sempre su copia sotto `/tmp/mutcheck-task5` e mai sul repo: controllo non mutato VERDE su 11 test, **12/12 mutanti uccisi**, origine provata, sha256 del file di repo identico prima e dopo la corsa. Le ultime due mutazioni riportano il codice ESATTAMENTE alla sua forma pre-correzione, quindi pinnano la correzione stessa e non solo il suo contorno.

**Hash di chiusura, 2026-09-17.** Modificati da questa tranche: `src/pyteman/patcher.py` `272b84d12cd00b9d` (819 righe), `tests/test_activation_atomic.py` `10cf431b44aa53ae` (1809 righe), `docs/rules.md` `c5948fa4766117c2` (528 righe). Invariati e verificati byte per byte contro il baseline, inclusi i due file congelati di TASK-7: `src/pyteman/rules.py` `4154bd896f457d97`, `src/pyteman/targets.py` `a766eebb45ee9db9`, `src/pyteman/sitecustomize.py` `9372b4cff2a58ece`, `tests/test_sitecustomize.py` `b1541d21b2e55113`, `tests/test_patcher.py` `c5d60404cdd1b498`, `README.md` `29ebcaca4507c2c6`. Nessun commit, push, checkout o reset; l'albero resta modificato e non committato.

**CHIUSO il 2026-09-17, APPROVED finale dall'orchestrator dopo verifica indipendente da entrambe le parti.**

L'orchestrator ha riprodotto autonomamente i vincoli di lifecycle con sonde proprie: doppia install idempotente, rifiuto fuori ordine senza mutazioni seguito da retry LIFO riuscito, replacement esterno preservato, metodo ereditato ripristinato con `delattr`, hook terzo delegante preservato con la vecchia closure disattivata. Ha poi verificato hash congelati e diff-check pulito.

Io ho verificato la prova di chiusura in modo indipendente prima di chiudere, invece di accettarla sulla parola: `patcher.py` `272b84d1...`, `test_activation_atomic.py` `10cf431b...`, `docs/rules.md` `c5948fa4...`, tutti identici allo stato congelato; i due file congelati da TASK-7 invariati (`rules.py` `4154bd89...`, `targets.py` `a766eebb...`); suite COMPLETA `662 passed in 5.41s`, zero fallimenti. I tre fallimenti su `tests/test_docs_integrity.py` presenti negli snapshot intermedi appartenevano a SQL-01 e sono stati chiusi dal proprietario; la serie collection error -> 4 failed -> 3 failed -> 0 failed ha convergito.

Nessuna modifica di codice in chiusura: solo operazione di tracker, come autorizzato. Nessun commit, push, checkout o reset in tutta la tranche.

Chiuso contestualmente TASK-62, che poggia sulla stessa decisione di contratto (`applied` come storico) e sulle stesse misure.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
`Patcher.uninstall` ora ha un contratto di lifecycle esplicito e provato, al posto di un ripristino che assumeva di essere l'unico attore sul processo.

**Cosa cambia per chi usa la libreria.** Disinstallare la strumentazione era finora sicuro solo nel caso semplice. Ora regge i casi che si incontrano davvero: un secondo Patcher annidato, un hook di terze parti che ha sostituito o incapsulato il nostro, un attributo che qualcun altro ha rimpiazzato dopo che lo avevamo avvolto, un metodo ereditato, uno slot `__slots__`, una `property` senza deleter. In ognuno di questi casi `uninstall()` o ripristina correttamente, o rifiuta in modo esplicito e riprovabile, e non distrugge mai il valore originale.

**Contratto.** Annidamento LIFO soltanto: un uninstall fuori ordine viene rifiutato PRIMA di qualsiasi mutazione, con `UninstallOrderError`, e il retry nell'ordine corretto riesce. Uno slot passato ad altri dopo il wrap e' un rilascio riuscito, non un rifiuto. Un hook estraneo viene preservato e la nostra closure diventa un pass-through invece di essere rimossa, perche' il codice di un terzo non e' modificabile. `applied` resta uno storico delle patch, non un inventario di cio' che e' vivo; `_wrapped` dice cosa e' vivo.

**Le due regressioni corrette in chiusura, entrambe introdotte da questa stessa tranche.** Il marker `_pyteman_patcher` sopravviveva all'uninstall, quindi un hook RITIRATO rispondeva ancora alla sonda e incastrava permanentemente il Patcher sottostante, wrap compresi, senza che nulla potesse sbloccarlo. Risolto chiedendo al proprietario dichiarato se quello e' ancora il suo hook (`owner._hook is fn`), che trasforma un'etichetta permanente in una relazione viva e come effetto collaterale smaschera un proxy che sintetizza attributi. Separatamente, `_owns_name` distingueva due casi su tre: un membro `__slots__` o una `property` sono storage PROPRIO del container e non compaiono in `__dict__`, quindi venivano registrati come non posseduti e il `delattr` SVUOTAVA lo slot, distruggendo l'originale mentre `uninstall()` riportava `[]`. Risolto richiedendo la proprieta' al momento dell'undo, cosi' il `delattr` gira solo mentre il nostro wrapper e' dimostrabilmente nel `__dict__`, che e' l'unico stato per cui e' corretto.

**Verifica.** Suite completa `662 passed`. Dodici mutazioni su dodici uccise su copia dell'albero sotto /tmp, con origine provata via `patcher.__file__`; le ultime due riportano il codice esattamente alla forma pre-fix, quindi fissano la correzione e non solo il contorno. Quattro regressioni nuove coprono hook ritirato, proxy che sintetizza attributi, slot e property senza deleter. Nessun commit, push o checkout.

**Cosa eredita chi prende in mano questo codice.** Tre follow-up espliciti, nessuno silenzioso: TASK-73 per il nome CANCELLATO dal container dopo il wrap, che oggi finisce sul canale dei rifiuti e viene ririportato per sempre; TASK-72 per la fixture `inheriting` che reimplementa il lifecycle di `_victim_module`; TASK-46 per la convenzione su dove vive una derivazione, docstring o `docs/rules.md`.
<!-- SECTION:FINAL_SUMMARY:END -->
