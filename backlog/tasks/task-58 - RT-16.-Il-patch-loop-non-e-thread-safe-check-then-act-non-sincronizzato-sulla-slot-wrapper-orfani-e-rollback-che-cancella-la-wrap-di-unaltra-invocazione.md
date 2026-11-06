---
id: TASK-58
title: >-
  RT-16. Il patch loop non e' thread-safe: check-then-act non sincronizzato
  sulla slot, wrapper orfani e rollback che cancella la wrap di un'altra
  invocazione
status: Done
assignee: []
created_date: '2026-09-16 17:56'
updated_date: '2026-09-27 16:43'
labels:
  - rt
  - opus-5
  - confirmed
  - review-rt-01
dependencies: []
references:
  - src/pyteman/patcher.py
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Trovato durante RT-01 (TASK-1), review high del 2026-09-16, sul lavoro di rollback atomico del patch loop. Non e' un duplicato: TASK-5 riguarda ordine e ownership di install/uninstall (evidenza tutta monothread), TASK-13 riguarda lo stato del gate di firing (once_per/countdown). Questo riguarda il patch loop stesso sotto thread.

**Priorita' / stato:** CONFIRMED con riproduttori deterministici (skeptic run del 2026-09-16, scratch in /tmp/skep/race.py e /tmp/skep/race2.py, interleaving forzato con un `__setattr__` bloccante su metaclass).

**File:** `src/pyteman/patcher.py`, `Patcher._patch`, `Patcher.uninstall`, `install_hook.hooked`.

**Meccanismo reale.** `_patch` esegue un check-then-act non sincronizzato su ogni slot: legge `original = getattr(container, name)`, testa `getattr(original, "_pyteman_state", None)`, costruisce il wrapper e solo dopo fa `setattr`. Nessun lock copre i quattro passi, e `_make_wrapper` sta dentro il buco facendo lavoro non banale (`parse_target_spec`, e per le regole `pragma` con `param:` anche `import inspect` piu' `inspect.signature`), quindi la finestra e' ampia e non un singolo confine di bytecode. `_patch` gira dentro `hooked()` DOPO che `orig(...)` e' tornato, quindi dopo il rilascio del lock di import, che da CPython 3.3 e' per-modulo: due thread che importano lo stesso modulo strumentato ci arrivano insieme, e cosi' pure `force_patch_module` in corsa con l'hook.

**CORREZIONE a una descrizione precedente di questo task.** NON si verifica un doppio wrap, e i fire NON vengono contati due volte. Se un thread ha gia' fatto `setattr`, l'altro rilegge quel wrapper, la guardia `_pyteman_state` scatta e la regola viene saltata: la guardia il wrapper-su-wrapper lo previene davvero. La corsa reale e' un'altra: entrambi i thread leggono lo STESSO original non wrappato e passano entrambi la guardia.

**Tre conseguenze, tutte osservate.**
1. Ultimo scrittore vince: un wrapper resta orfano e la sua regola e' silenziosamente non strumentata, mentre `self.applied` continua a elencarla.
2. `self._wrapped` e `self.applied` prendono una entry duplicata per una sola wrap viva; in race.py `applied` era `['skep_race:C.f', 'skep_race:C.f']` con due triple IDENTICHE, entrambe con l'original non wrappato salvato.
3. Se una delle due invocazioni fallisce dopo, il suo rollback riscrive l'original salvato sopra il wrapper dell'ALTRA, cancellando una wrap che quella aveva completato e pubblicato e lasciando in `self._wrapped` una entry pubblicata ma morta. In race2.py: T2 completa e pubblica `skep_race2:C.f`, T1 scrive il proprio wrapper, fallisce su una regola successiva e ripristina; stato finale `live C.f is the UNWRAPPED original: True`.

**Seconda corsa distinta, stessa famiglia.** `uninstall()` chiama `_restore(self._wrapped)` e poi `self._wrapped.clear()` senza tenere nulla. `reversed()` fissa l'indice di partenza alla creazione, quindi le entry che un `_patch` concorrente pubblica durante il loop di restore non vengono mai ripristinate, e il `clear()` successivo ne butta i record in modo permanente: wrap persa per sempre. Raggiungibile quando un thread e' gia' dentro `_patch` mentre un altro chiama `uninstall()`.

Ripristinare l'original salvato e' idempotente, quindi nulla di tutto questo corrompe lo stato che `uninstall()` sa ripristinare; semplicemente non puo' recuperare la strumentazione persa.

**Cosa ha chiuso RT-01 e cosa no.** RT-01 ha reso corretto l'INSIEME di slot che un rollback tocca: le wrap di ogni invocazione sono raccolte in una lista locale e pubblicate solo a successo, quindi una invocazione non cancella piu' le wrap di un'altra per errore di indice (verificato: la vecchia variante a mark perdeva la wrap annidata, /tmp/skep/marks.py). Questo NON e' proprieta' esclusiva della slot, e sotto thread la differenza conta: vedi conseguenza 3. Il resto della corsa resta aperto e non va dichiarato risolto. Il limite e' dichiarato in docs/rules.md, sezione "Where each check happens".

**Finestra minore, stesso file.** Fra `self._wrapped.extend(wrapped)` e `self.applied.extend(applied)` c'e' una finestra per un'eccezione asincrona: `_wrapped` risulta pubblicata e `applied` no, quindi `uninstall()` ripristina comunque ma il report sotto-conta. L'ordine attuale e' quello giusto (invertirlo perderebbe una wrap non ripristinabile) e `list.extend` su tuple non fallisce se non per MemoryError, quindi va annotato, non necessariamente chiuso.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Riproduttore deterministico con threading.Barrier per la corsa sulla stessa slot: due invocazioni leggono lo stesso original non wrappato, una vince, l'altra resta orfana pur comparendo in applied
- [x] #2 Riproduttore deterministico per il rollback distruttivo: l'invocazione che fallisce ripristina l'original sopra il wrapper pubblicato da un'altra invocazione (forma di /tmp/skep/race2.py)
- [x] #3 Il controllo di ownership e il setattr sulla stessa slot sono atomici rispetto alle altre invocazioni; un wrapper costruito e mai installato non compare in applied
- [x] #4 self._wrapped non contiene mai due entry per lo stesso (container, name), e uninstall ripristina l'original vero
- [x] #5 uninstall non puo' perdere una wrap pubblicata da un _patch concorrente: niente entry saltate dal reversed() e poi scartate dal clear()
- [x] #6 Nessun deadlock: il lock non copre mai l'esecuzione di condition o action arbitrarie, ne' il corpo del callable originale (vedi la nota di TASK-13 sulla condition che attende un altro thread)
- [x] #7 docs/rules.md dichiara il limite noto finche' non e' chiuso, e lo dichiara con il meccanismo REALE, che RT-02 ha cambiato: dal 2026-09-17 un doppio wrap E' possibile nella finestra fra il setattr e la riga che registra il dispatcher in _inflight, e in quel caso i fire delle regole sottostanti SONO contati due volte. La vecchia formulazione di questo AC ('niente doppio wrap, niente fire contati due volte') era vera prima di RT-02 e non va ripristinata
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Aggiornamento dalla review /simplify di RT-02 (TASK-2), 2026-09-17. Il meccanismo della corsa e' CAMBIATO e questo task va letto con la nuova forma, non con quella registrata nella descrizione sopra.

RT-02 ha introdotto in _patch due passate: la prima risolve ogni regola, la seconda installa. La seconda RILEGGE l'attributo invece di fidarsi di quello che la prima aveva memorizzato, perche' costruire il dispatcher di uno slot precedente importa inspect mentre l'hook e' vivo e quindi _patch rientra. L'ownership non si legge piu' da _pyteman_state ma da _pyteman_owner piu' una mappa _inflight sul Patcher, consultata prima del ledger.

Conseguenza sulla corsa, misurata leggendo il codice e non ipotizzata: la finestra non sincronizzata non e' piu' 'read, test, build, setattr' ma una singola istruzione, fra il setattr che installa il dispatcher e la riga successiva che lo registra in self._inflight. Una seconda invocazione che atterri esattamente li' legge un dispatcher VIVO, riceve owner None perche' ne' _inflight ne' il ledger lo conoscono ancora, e lo AVVOLGE. Questo e' il doppio wrap che la descrizione di questo task dichiarava impossibile, e le regole sotto sparano due volte per chiamata.

In compenso la finestra e' molto piu' stretta di prima e la modalita' di guasto e' cambiata di natura: prima si PERDEVA una wrap (ultimo scrittore vince), ora se ne puo' ANNIDARE una. Nessuna delle due e' prevenuta.

AC #7 e' stato riscritto di conseguenza nello stesso turno. docs/rules.md e il commento lungo in cima a _patch sono gia' stati allineati al meccanismo nuovo da TASK-2; chi eseguira' questo task non deve riportarli alla vecchia formulazione.

Secondo aggiornamento da TASK-2, 2026-09-17, dopo la code review high su RT-02. Il quadro precedente resta valido ma era INCOMPLETO: ora le finestre sotto thread sono DUE, non una, e falliscono in direzioni opposte.

Cosa e' stato CHIUSO. Pass 2 ora rilegge l'attributo una SECONDA volta, subito prima del setattr, e non solo in cima al loop. Serviva perche' `_make_dispatcher` gira fra le due letture e rientra in `_patch` a ogni chiamata: importa inspect mentre l'hook e' vivo (l'hook avvolge `builtins.__import__`, quindi il rientro non dipende da inspect essere freddo) e `inspect.signature` esegue il `__signature__` della vittima. La chiamata annidata poteva prendere proprio lo slot per cui il dispatcher era in costruzione, e il setattr successivo lasciava DUE entry nel ledger per lo stesso slot, la piu' vecchia con un wrapper non piu' presente, e `applied` che nominava una regola che non sparava piu'. Riproduttore /tmp/probe_same_slot.py: prima 2 entry di cui 1 morta, dopo 1 entry e 0 morte. La seconda lettura discrimina sul proprietario: se in slot c'e' un dispatcher di QUESTO Patcher la chiamata si ritira (i due dispatcher sono intercambiabili quando il rientro ha risolto le stesse regole), se c'e' quello di un estraneo solleva SlotOwnershipError e fa rollback. Questo chiude il buco MONOTHREAD, che era raggiungibile senza thread affatto. Fissato da `test_a_reentrant_patch_that_takes_the_slot_being_built_leaves_one_entry`, mutation proof: disabilitata la guardia, 1 failed / 71 passed.

Finestra 1, INVARIATA e ancora aperta: fra il setattr che installa il dispatcher e la riga che lo registra in `self._inflight`. Verificato che la seconda rilettura NON la copre: l'invocazione che atterra li' legge il dispatcher vivo alla PRIMA lettura, riceve owner None, e assegna quel dispatcher a `slot.original`; la seconda rilettura confronta quindi uguale e non scatta. Doppio wrap, fire contati due volte. Resta come descritto nella nota precedente.

Finestra 2, NUOVA, introdotta dalla seconda rilettura stessa: fra la seconda lettura e il setattr. Due invocazioni possono superarle entrambe tenendo lo stesso original; l'ultimo setattr vince e il primo wrapper resta orfano. E' la vecchia modalita' last-writer-wins, non piu' su tutto l'intervallo 'read, test, build, setattr' ma solo su questo tratto, che comprende la chiamata a `_owns_name` e la scrittura.

Quindi: una finestra ANNIDA una wrap, l'altra ne PERDE una. Chi chiude questo task deve coprirle entrambe; chiudere solo la prima lascia viva la seconda e viceversa. docs/rules.md, sezione sulla ownership, descrive ora entrambe ed e' gia' allineato: non riportarlo a una formulazione con una sola finestra.

AUDIT DI CHIUSURA (2026-09-27, sessione notturna, master ea9a378): le finestre registrate in questo task sono tutte chiuse dal meccanismo attuale e la chiusura e' ora difesa da test committed (PR #170, quattro test nuovi in test_slot_reservation.py). Mappa AC per AC: #1/#2 (orfanizzato in applied, rollback distruttivo): chiusi dalla prenotazione dello slot, presa PRIMA della lettura decisiva e rilasciata nel finally a fine chiamata; il secondo installatore e' rifiutato prima di costruire (i test di coreografia park sono i riproduttori deterministici richiesti; stress 150 round per variante: two-patchers sempre (refused, ok), one-patcher sempre (ok, ok) via la via di extend documentata, invarianti di ledger-dedup e ripristino-originale verificate a ogni round). #3 (ownership+setattr atomici): stessa prenotazione, copre decisione-scrittura; il wrapper mai installato non compare in applied per costruzione publish-on-success. #4 (niente duplicati in _wrapped, uninstall ripristina l'originale vero): stress + test. #5 (uninstall non perde wrap pubblicati da _patch concorrente): il consuming restore chiude entrambe le forme d'arrivo, e ora e' PINNATO: publish dopo il ritorno dell'uninstall (recuperabile dal secondo uninstall), publish a meta' camminata su ALTRO ledger (sopravvive sul proprio Patcher), e la forma che il testo del task nomina davvero, publish a meta' camminata sullo STESSO ledger (il setattr del restore rientra nello stesso Patcher; l'entry resta sopra l'indice fisso del camminamento e sopravvive). #6 (niente deadlock): verificato lock per lock (_RESERVATION_LOCK solo operazioni dict; lock di regola tre sezioni brevi con condizione e chiave fuori; barrier lock solo lookup; FiringLog serializza prima di prendere il lock). #7 (docs col meccanismo reale): il paragrafo concurrent-uninstall di docs/rules.md (missed-not-forgotten, indice fisso, next-uninstall) corrisponde esattamente a cio' che i test pinnano.

CORREZIONE REGISTRATA: la prima stesura della verifica dichiarava 'nessuna mutazione una riga reintroduce il bug storico perche' il suo codice e' strutturalmente sparito'. La belt high l'ha CONFUTATA: aggiungere self._wrapped.clear() dopo il camminamento reintroduce la perdita esatta (probe proprio: WRAP_LOST True) e passava sia i due test nuovi sia l'intero file reservation; inoltre il riordino del finally (release prima del publish, tre istruzioni) passava l'intera suite riaprendo il doppio wrap. Entrambe le lacune sono state chiuse con i test suggeriti dalla belt (same-ledger sync e finally-order frozen-at-publish) e le mutazioni M1/M5 ora uccidono i rispettivi test. Lezione: 'il codice del bug non esiste piu'' non e' una prova; la mutazione una-riga e' il discriminator.

PROBE E MUTAZIONI preservate sotto /home/pantinor/pyteman-evidence/task58impl/ (probe_uninstall_race, probe_midrestore_publish, probe_install_stress, probe_samedger_midwalk, probe_samedger_sync, probe_finally_order, mut/edit_m1..m6 con run_mutations.sh, tutti rieseguibili).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Chiuso con il merge 34a8c88 (PR #170, squash di 01bd5fc su master ea9a378). Tutte e sette le AC verificate e spuntate: le tre corse d'installazione e le due finestre sono chiuse dalla prenotazione dello slot e dall'ordine del finally, l'uninstall non puo' perdere una wrap perche' il restore consuma invece di cancellare, nessun lock copre condizioni o azioni, i docs dichiarano il meccanismo reale. La chiusura e' difesa da quattro test committed (le due forme d'arrivo della wrap dispersa, la forma same-ledger che il testo del task nomina, e l'ordine del finally congelato al publish) con mutazioni M1 (clear storico reintrodotto) e M5 (finally riordinato) che uccidono i rispettivi test. Revisione indipendente APPROVED a 01bd5fc con due finding non bloccanti registrati qui: (LOW, igiene del solo cammino di fallimento del test 4: il finally non fa gate.set/join se un assert dentro il try fallisce; il worker parcheggiato trattiene la prenotazione fino a 10s oltre il test; da piegare nella prossima tornata che tocca il file) e (INFO: la lettera dell'AC 1 chiedeva threading.Barrier, i test committed usano la coreografia park; il riproduttore a barriera esiste come probe preservato e rieseguibile in task58impl/probe_install_stress.py e la sostanza e' soddisfatta perche' la perdita che il riproduttore doveva mostrare e' ora prevenuta e i test pinnano il rifiuto).
<!-- SECTION:FINAL_SUMMARY:END -->
