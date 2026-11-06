---
id: TASK-122
title: >-
  RT-02o. La finestra fra seconda rilettura e scrittura e' raggiungibile con UN
  SOLO thread
status: Done
assignee: []
created_date: '2026-09-17 04:13'
updated_date: '2026-09-25 10:58'
labels:
  - patcher
  - concurrency
  - rt-02
  - docs
dependencies: []
references:
  - src/pyteman/patcher.py
  - docs/rules.md
  - tests/test_activation_atomic.py
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Trovato dal gate code-review sulla tranche RT-02 (2026-09-17), nel rilievo sulla frase assoluta "A single thread cannot get past it" in docs/rules.md. La frase e' stata corretta nella stessa sessione; il DIFETTO che la falsifica resta aperto ed e' questo.

Pass 2 di `Patcher._patch` legge lo slot una seconda volta e poi scrive. Sono due statement distinti, e in mezzo non c'e' nulla. La documentazione trattava quella finestra come raggiungibile solo da un secondo thread. Non e' vero: sia il `getattr` della seconda rilettura sia la `setattr` della scrittura possono ESEGUIRE CODICE DEL PROGRAMMA TARGET.

Le forme che lo fanno sono gia' tutte esercitate altrove nella suite:
- un container che e' una `property`, il cui getter gira sul getattr;
- una metaclasse con `__setattr__`, che gira sulla scrittura;
- una sottoclasse di `ModuleType` con `__getattr__`;
- un setter di property sul container.

Se quel codice importa un modulo strumentato, la chiamata rientrante di `_patch` installa il proprio dispatcher tra le due, e la chiamata esterna scrive sopra. Il risultato e' quello gia' descritto per la corsa a due thread: il dispatcher perdente resta orfano, la sua entry nel ledger nomina un wrapper che non e' piu' nello slot, e le regole che serviva smettono di sparare mentre `applied` continua a nominarle. Con un solo thread.

Da valutare prima di scrivere codice: se la finestra sia chiudibile senza lock, per esempio scrivendo e poi RILEGGENDO per confermare che il valore atterrato sia il nostro dispatcher, trattando la smentita come il caso "qualcun altro ha preso lo slot" che il guard sa gia' gestire. Una conferma dopo la scrittura e' piu' economica di una sincronizzazione e vive nello stesso ramo. Verificare pero' che la rilettura di conferma non riapra lo stesso problema su container ostili.

Nota di contesto (aggiornata 2026-09-17): questa e' ORA L'UNICA finestra rimasta. L'altra, quella fra la `setattr` e la registrazione in `_inflight`, e' CHIUSA: la registrazione e' stata spostata PRIMA della scrittura. Falliva nella direzione opposta, annidando un wrap invece di perderlo, e una nota precedente di questo task la dava per multi-thread. Era sbagliato su entrambi i punti: una sottoclasse di `ModuleType` il cui `__setattr__` rientra dopo aver chiamato `super()` la raggiungeva con un solo thread, ed e' esattamente cosi' che e' stata riprodotta. Vedi il test `test_a_dispatcher_is_answerable_as_ours_before_the_write_not_after` in tests/test_activation_atomic.py. Resta quindi una sola finestra da chiudere, questa.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Test raggiunge la finestra tramite import reale strumentato eseguito dal getter/setter su un solo thread; una prenotazione impedisce l'installazione competing senza sovrascrittura silenziosa.
- [x] #2 docs/rules.md descrive finestra e protezione effettiva, distinguendo reentry single-thread, installazioni fra thread e limiti residui.
- [x] #3 Lock breve autorizzato esplicitamente dall'utente protegge soltanto il registro delle prenotazioni; nessun getter/setter/callback del workload viene eseguito mentre è tenuto.
- [x] #4 Test deterministici con Event coprono stale ownership read e concorrente stesso Patcher su altro thread; la reentry stesso owner sullo stesso thread resta supportata.
- [x] #5 Prenotazioni rilasciate per token anche su errori read/write e rollback, senza leak di owner e senza sostituire eccezione primaria; nessuna promessa di thread-safety generale su extension/uninstall.
- [x] #6 Mutanti che rimuovono la prenotazione o la spostano dopo la lettura fanno fallire i test pertinenti; default rollback136 e callable bindings restano coperti.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Scelta utente esplicita 'Lock breve (Recommended)' sostituisce precedente divieto di nuovi lock. Implementare registry process-wide per identità slot con owner/thread/token, acquisizione prima della lettura ownership decisiva e rilascio nel finally. Lock soltanto su operazioni registry, mai sul codice target o intero _patch. Key exact builtin fuori lock, identity owner/token, riferimenti rilasciati fuori lock se possono attivare finalizer. Tracking cleanup prima della write registry. Rifiuto competing owner o thread diverso durante install; stesso owner/thread non rilascia token esterno.

Perimetro install-write, non thread-safety globale: primo ramo extend preesistente e uninstall non magicamente serializzati. Test import reale caught/uncaught refusal, stale-read due thread Event, same-owner thread diverso, same-thread reentry, rollback/write/read error, registry empty/no owner leak. Mutation no-reservation/acquisition-after-read e suite. Baseb391a2b, copia isolata, simplify mirato, review finale indipendente pyteman-release-review su hash immutabile; coordinator integra/pubblica. Nessun TASK123 o framework transazioni.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
## Limite dell'evidenza che chiude la finestra gemella (2026-09-17)

Registrato qui perche' vale per QUESTA finestra e non per quella chiusa. La finestra fra scrittura e registrazione in `_inflight` e' stata chiusa in TASK-2 e ha due test di regressione, ma entrambi la raggiungono con un container rientrante su un solo thread: `ReentersFromSetattr`, che rientra dopo `super()`, e `LeaksBeforeSuper`, che pubblica il valore altrove e rientra prima. Nessuno dei due usa thread veri.

E' deliberato e sufficiente per quella finestra, perche' la rientranza single-thread e' un percorso reale e deterministico, mentre un test a thread sarebbe non deterministico senza punti di sincronizzazione dentro `_patch`. Non e' pero' sufficiente per la finestra di QUESTA task, che e' raggiungibile anche da due thread indipendenti senza alcun container ostile: due chiamate possono superare la seconda rilettura trovando lo stesso originale, e allora la seconda scrittura vince e il primo wrapper resta orfano.

Conseguenza operativa: quando questa task verra' eseguita, la prova non puo' limitarsi a un container rientrante. Serve o una sincronizzazione iniettabile nel punto fra la seconda rilettura e la scrittura, oppure una dimostrazione che il caso a due thread degenera esattamente in quello single-thread gia' coperto. La seconda strada va dimostrata, non assunta: il container rientrante serializza per costruzione, quindi non esercita mai due scritture concorrenti sullo stesso slot.

Scout baseb391a2b, probe122.py riprodotto direttamente dal coordinatore: outer p1 live, inner p2 applied/ledger presenti ma wrapper non più binding attuale, p2.uninstall0 refusals. Conferma finestra dentro setattr prima super e insufficienza conferma post-write. Non interpretare applied storico come promessa firing presente: TASK131 contratto pubblicato. Ultime righe probe usano served=None da attributo non valido, non provano firing; richiesto oracle reale tramite call/log. TASK123 adiacente non assegnato parallelamente. Spike ownership reservation da valutare, non implementazione autorizzata.

Spike prenotazione ricevuto in scout-b391a2b-1789833399/SPIKE122.md. Policy decisa: rifiuto esplicito tra Patchers mentre write in corso è accettabile; se l'eccezione nested esce dal setter e abortisce outer è fail-closed voluto, non errore di destinatario. Non ancora approvazione implementazione finale.
Revisione coordinator trova interleaving non coperto: prenotazione viene acquisita dopo ultima ownership read, quindi A legge originale, B installa e rilascia, A acquisisce reservation vuota e sovrascrive B. Atomicità setdefault non sana stale read. Richiesto spike Event-sincronizzato su due thread come note AC già chiedono; non separare scope unilateralmente. Ownership check deve essere coperto dalla prenotazione o rieseguito sotto di essa. Distinguere same-owner same-thread reentry da same-owner thread concorrenti. Richiesta verifica docs/source per assunzione dict atomic e gestione tracking/cleanup prima setdefault per evitare leak se append fallisce. Nessun codice candidato approvato ancora.

Spike v3 ammette soltanto stesso owner e stesso thread; stale-read con Events conferma v1 non risolve. Consultazione docs peer chiarisce atomic setdefault non garanzia portabile Python; utente ha scelto esplicitamente lock breve sul registry via AskUserQuestion. AC3 aggiornato con autorizzazione, vecchi check non marcati soddisfatti.
Coordinator ha rilevato che primo owner-is-self/extend branch resta prima dell'acquisizione, quindi non rivendicare tutte extension sincronizzate. Protezione riguarda sequenza d'installazione coperta e limiti documentati. Implementazione autorizzata dopo scelta utente, non prima.

Candidato finale a705eaad6b7734ebf627bcdfb0802878d9cc39c4f49798036c6138f525d7fe91 ricevuto e hash verificato, runtime885cab18 confermato su fresh exportb391a2b; suite indipendente in corso. Review finale assegnata a pyteman-release-review sullo stesso artifact. Peer riporta1094/1skip e mutanti no-acquire5fail, acquire-after-read2fail deterministici, no-release4fail+9error teardown registry nonvuoto; non ancora claim coordinator.
Simplify mirato implementer: corretto test read che prima falliva prima acquisizione, diagnostica refusal non richiede uninstall di oggetto mai installato, lifetime riferimenti spiegato dalla lista slot, esclusione tenuta fino fine intera _patch esplicitata nei docs, eliminato del locale morto nel release (held conserva tupla oltre lock). Optional commento ridondante e tuple unpack/index style registrati e non applicati, nessun nuovo task. Limiti first ownership/extend e uninstall non protetti confermati come scope, non promesse generali.

PR15 MERGED b769bf9d808345cb7997f2c9ff1c83bec5f7d51c, commit28ad4f3d025c18f1d49f63ab44983d78677bb876. CI35457268190 tutti sei job success; endpoint review/commenti/discussion vuoti prima merge. Reviewer APPROVEDa705eaad con probe lock/identity/token/BaseException/mutanti, simplify mirato implementer. Suite coordinator fresh retry e shared1094/1skip opzionale; run iniziale ucciso dal sistema per memoria bassa separato, non claim test failed. Prove ~/pyteman-evidence/task122-integration-20260919-185319/.
Done respinto dal hook che non riconosce gate delegati nel transcript coordinator. Nessun bypass/retry identico, tracker In Progress amministrativo ma codice pubblicato e AC verificati. Lock breve era esplicitamente autorizzato dall'utente; limiti first extend/uninstall e durata per-call dichiarati, non thread-safety globale.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed 2026-09-25 by backlog audit. PR#15 merged as commit 28ad4f3 (reserve slots across competing installation writes), CI green. Administratively stuck In Progress. Code published in v0.2.0.
<!-- SECTION:FINAL_SUMMARY:END -->
