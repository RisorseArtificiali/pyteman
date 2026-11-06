---
id: TASK-136
title: >-
  Un container che memorizza e poi solleva da __setattr__ lascia il dispatcher
  installato e fuori dal ledger
status: Done
assignee: []
created_date: '2026-09-17 07:50'
updated_date: '2026-09-25 10:58'
labels:
  - audit-2026-09-16
  - opus-5
  - rt
  - confirmed
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Trovato durante la verifica adversarial del riordino `_inflight`/`setattr` di TASK-2 (2026-09-17). NON e' una regressione di quella tranche: il difetto e' identico nei due ordinamenti, perche' dipende solo dalla posizione di `wrapped.append` rispetto al `setattr`.

**Meccanica, letta nel codice e poi misurata.** In `_patch`, `setattr(slot.container, slot.name, dispatcher)` sta a patcher.py:1022 e `wrapped.append((slot.container, slot.name, live, dispatcher, owned))` a :1029. Un container il cui `__setattr__` chiama `super()` e POI solleva commissiona la scrittura e fa uscire l'eccezione prima che la voce di ledger esista. Il gestore a :1033 chiama `_restore(wrapped)`, che per quello slot non ha nulla da disfare.

**Esito osservato.** L'attributo conserva il dispatcher, `_wrapped` e' vuoto, `applied` non e' pubblicato, `_inflight` viene ripulito correttamente dal finally. Il punto continua a sparare, e `uninstall()` risponde `[]` su un callable ancora strumentato che resta strumentato anche dopo.

**Riproduttore:** /tmp/probe_setattr_commits_then_raises.py, eseguito con /tmp/pyteman-audit-env-OOeElF/bin/python e PYTHONPATH=src. Stampa:

```
patch raised: RuntimeError: container refuses after storing
slot still instrumented: True
ledger entries:          0
applied:                 []
_inflight:               {}
one call -> real fired ['r']
uninstall refusals:      []
instrumented AFTER uninstall: True

LEAK: True
```

**Perche' non e' stato corretto in TASK-2.** La correzione tocca il rapporto fra la scrittura e la registrazione, cioe' lo stesso punto che TASK-131 deve rivedere per la pubblicazione di `applied` sul percorso di fallimento. Le due modifiche vivono nello stesso blocco except e vanno decise insieme, altrimenti la seconda riscrive la prima.

**Vincolo da rispettare nella correzione.** Registrare PRIMA del setattr e togliere la voce se la scrittura fallisce non e' equivalente: un `setattr` rifiutato senza aver scritto nulla lascerebbe una voce da rimuovere, e `_restore` consuma la lista, quindi la rimozione va fatta per identita' e non per indice. Va inoltre distinto il rifiuto puro (nulla scritto) dal commit parziale (scritto e poi sollevato), che dall'esterno del `setattr` non sono distinguibili senza rileggere lo slot.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Un container che scrive e poi solleva da __setattr__ non lascia lo slot strumentato: o la patch disfa la scrittura commissionata, o la registra in modo che uninstall possa rilasciarla e la nomini fra i rifiuti
- [x] #2 uninstall() non risponde mai [] su un callable che resta strumentato dopo la chiamata
- [x] #3 Il rifiuto puro (setattr che solleva senza aver scritto) continua a non produrre voci di ledger fantasma: la distinzione fra i due casi e' fatta rileggendo lo slot, non assunta
- [x] #4 Test di regressione con il container che commissiona e poi solleva, dimostrato mordente via mutation testing su copia temporanea con prova di origine __file__
- [x] #5 La correzione e' coordinata con TASK-131, che riscrive lo stesso blocco except
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Spike approvato per consegna: spostare wrapped.append prima di setattr, sempre dopo _inflight registration. Nessun nuovo handler/readback/ledger: _undo_one legge già lo slot e distingue per identità rifiuto senza scrittura da wrapper presente. Conservare ordine reentry, primary e applied storico.

Test permanenti per write-then-raise con undo-ok, undo-refused (entry conservata, uninstall refusal), undo che scrive originale poi raises (entry conservativa e retry consuma). Pure-refusal no ghost come controllo esistente o nuovo se mancante. Asserire primary `is`, _inflight vuoto e applied invariato. Rientranza/foreign replacement controllati per non regressione, senza risolvere doppio wrapping preesistente. Mutante ordine inverso uccide detector, non controlli; cache isolata e restore da backup. Simplify mirato una volta, review indipendente finale pyteman-release-review, hash immutabile e suite coordinator prima PR. No shared/tracker/Git/forge/config/memory writes da implementer.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Scout raccomanda TASK136; coordinatore ha eseguito probe136.py sul runtime shared820c5a2: patch RuntimeError, slot wrapper=True, ledger0, applied[], _inflight{}, uninstall[], ancora wrapper; LEAK True. Chiusura funzionale TASK131 già pubblicata come contratto storico PR9, nessun conflitto pending nel suo except. Non assumere che il fix richieda nuovo read-back: _undo_one già legge slot e consuma ownership non nostra, quindi provare prima entry-before-write con percorso undo esistente. TASK124 alternativo non assegnato. TASK138 nota proprietari/freeze è storica, non motivo attuale verificato per bloccare dipendenza; non viene affrontato in questa unità.

SPIKE.md letto da ~/pyteman-evidence/task136-1789831029/: reorder puro e probe4 quattro traiettorie mostrano controllo pure-refusal invariato e tre casi fix verdi; risultati ancora attribuiti al peer, non run coordinator candidato. Suite peer1082/1skip include solo test undo-ok. Richiesto promuovere undo-refused/retry a regressioni permanenti perché sono criteri di accettazione, non solo evidenza di spike. Nessun ulteriore allargamento codice. Probe reentry due entry/uno slot dichiarato preesistente su entrambi, non corretto né falsamente attribuito al nuovo ordine.

Candidato904d50afec4787a8bb4c10ae76ad7a6997b92b062d8679302769c85300b10950 ricevuto e hash verificato; applicato a fresh export820c5a2 per suite indipendente in corso. Patcher a26d881f confermato. Due file, reorder più commento/test, nessun handler nuovo. Peer dichiara quattro test permanenti: pure-refusal controllo e tre detector undo-ok/refused/write-then-raise, mutant inverso3fail1pass, suite1085/1skip. Review finale assegnata al peer disponibile sullo stesso hash.
Simplify singolo implementer: tolto parametro helper inutilizzato e blank line, corrette due motivazioni test/commenti, mutant rieseguito sullo stato finale. Nessun optional pendente né fanout high aggiuntivo. Casi reentry/foreign coperti preesistenti, doppio ledger non dichiarato risolto.

Reviewer finale APPROVED904d50af/a26d881f/f42a14e6; suite indipendente e shared1085 passed/1skip opzionale, traiettorie e mutant inverso3fail1controlpass provati anche dal reviewer. Integrati soltanto due file byte-exact, backup/provenienza ~/pyteman-evidence/task136-integration-20260919-174403/. Commit300efb5302d7085ac8f4616e84c406b7552f8fe6 pubblicato PR14 https://github.com/RisorseArtificiali/pyteman/pull/14; CI35453181657 in corso, non merged ancora.
Osservazione reviewer non bloccante conservata: read del container che solleva dopo pure-refusal può causare conservativamente una refusal e ledger retained per slot mai scritto. Nessun clobber perché read precede write, retry può consumare. Non nuovo task: limite best-effort esplicitato nella PR. AC2 applicato agli slot gestiti, non reachability globale degli alias (TASK131 storico).

PR14 MERGED b391a2b0a28a5dc740ab9199c862f4f9a3dd6abc, commit300efb5302d7085ac8f4616e84c406b7552f8fe6, CI35453181657 sei job success. Endpoint review/commenti/discussion vuoti prima merge. Review indipendente APPROVED904d50af e simplify mirato implementer, suite indipendente/shared1085/1skip opzionale; tutti AC verificati. Consegna codice conclusa.
Done respinto dal hook per mancato riconoscimento simplify/code-review delegati nel transcript coordinator. Nessun bypass/retry identico o marker inventato, tracker resta In Progress amministrativo. Evidenza ~/pyteman-evidence/task136-integration-20260919-174403/.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed 2026-09-25 by backlog audit. PR#14 merged as commit 300efb5 (record rollback entry before attribute write), CI green. Administratively stuck In Progress. Code published in v0.2.0.
<!-- SECTION:FINAL_SUMMARY:END -->
