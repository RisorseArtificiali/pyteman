---
id: TASK-171
title: >-
  Prevent param targets from binding caller arguments against a misleading
  wrapped signature
status: Done
assignee: []
created_date: '2026-09-19 17:34'
updated_date: '2026-09-25 10:57'
labels:
  - targets
  - signature
  - confirmed
dependencies: []
references:
  - src/pyteman/patcher.py
  - src/pyteman/targets.py
  - docs/targeting.md
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Confirmed on b769bf9 through real Patcher, run_action and FiringLog. A functools.wraps decorator injects REAL before forwarding caller args to an inner function declared query(conn, audit_conn). Caller supplies DECOY. inspect.signature follows __wrapped__, so param:conn binds DECOY instead of the injected REAL; foreign_keys is enabled on DECOY and logged pragma_applied while the body uses REAL with foreign_keys still disabled.

The resolver cannot infer injected inner arguments from caller args. A transparent pass-through wrapper currently benefits from following __wrapped__, so a blanket change needs an explicit documented parameter-binding contract and tests, not merely a flag flip. No backward compatibility shims required, but preserve correctly supported call shapes where demonstrably safe. Scope is signature acquisition and param binding, not PRAGMA readback or arbitrary decorator execution.

Independent real JSONL evidence: ~/pyteman-evidence/signature-probe-at69g14g/log.jsonl. Scout evidence: ~/pyteman-evidence/scout-b769bf9-1789838182/. Existing searches for signature/wrapped found related cleanup tasks but no task covering this misbinding.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A real decorated target that injects a connection never applies a param-targeted action to a different caller-supplied connection while claiming it resolved the injected parameter.
- [x] #2 Tests cover undecorated functions, transparent wrappers and argument-transforming wrappers through Patcher and real actions, with correct-binding positive controls.
- [x] #3 Unknown or untrustworthy parameter bindings yield an explicit miss or refusal under a documented policy, not guessed positional attribution.
- [x] #4 Initial dispatcher creation and later extension use the same parameter-signature contract, with tests for both.
- [x] #5 Documentation states which callable parameter namespace param targets name and what explicit __signature__ or __wrapped__ metadata can and cannot guarantee.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
REDESIGN AUTORIZZATO DALL'UTENTE: risposta esplicita 'Sì, firma dal codice (Recommended)' ignora __signature__ anche non decorata per SOLO binding param. Supera precedente fiducia metadata non decorati; introspezione pubblica dispatcher resta invariata. Ripartire da exportb769bf9 pulito, preservare candidati refutati senza riusarli come base.

Risoluzione bounded di forme callable esatte a FunctionType reale e routing argomenti, letture base descriptors/MRO e type identity. Costruire Parameter/Signature dai code slots e bind_partial; nessun inspect.signature su target/clone, niente __wrapped__/__signature__/__text_signature__/__partialmethod__ come fonte di binding. Niente annotations/apply_defaults, param dichiarato ma non passato resta miss. Supportare plain function, bound method, callable instance con plain __call__, classi semplici type+object.__new__+Python init. Forme non verificabili unavailable con costo esplicito, non congetture.

Partial richiede accounting reale di positional prelegati e keyword sovrascrivibili, nesting/bound forms e Python3.14 Placeholder supportato con prova oppure unavailable documentato. Subclass partial __call__ override non ridotta al func. Receiver di metodo con *args richiede trattamento reale, non drop-first cieco. Spike rischi prima scaffolding, niente framework universale.

Test end-to-end Patcher/actions/FiringLog sia creazione sia extension, REAL e DECOY untouched negli attacchi, positivi per forme supportate e parameter kinds, override partial, public signature introspection invariata. Mutanti discriminanti e cache isolata. Un simplify mirato, reviewer finale persistente indipendente, nessuna modifica shared/Git/forge/tracker/config/memory degli agenti.

Partial accounting preserva semantica caller-only già documentata: argomenti positional prelegati non sono più dichiarati sulla chiamata intercettata; keyword prelegati restano sovrascrivibili ma non vengono risolti se omessi dal caller, nessun apply_defaults. Non esporre i valori catturati come se fossero argomenti del firing. Placeholder3.14 richiede posizioni distinte e fill per posizione; forme non accertabili devono risultare unavailable/miss. Test duplicate positional/keyword, receiver *args, nested partial e subclass override insieme alle versioni senza Placeholder. Lo spike14forme del peer dimostra solo quelle forme, non equivalenza universale a inspect.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Assessment source inspect3.14.7 letto dal peer: follow_wrapped=False non disabilita __signature__. Coordinatore riproduce independently wraps(inner con explicit Signature): signature false resta(conn,audit_conn), bind conn->decoy mentre corpo usa real. Utente ha scelto rifiuto dell'ambiguità, non fiducia esplicita nei metadata decorati. Nessuna supposizione che follow_wrapped da solo chiuda quel caso. Corretto wording diagnostica proposto: una firma può nominare altri parametri, quindi il reason nomina soltanto il parametro richiesto assente, non 'nessun parametro nominato'. Implementazione autorizzata secondo scelta user; nessun cambiamento condiviso ancora.

Candidato29cccdd7e413fdfa06082e0070f32bf53522837ff0402608664e9f4fa195f1e9 ricostruito da coordinator su exportb769bf9, NON approvato. Refutazione indipendente reale: istanza callable con __call__ decorato tramite wraps e __signature__ copiata conserva firma(conn,audit_conn); wrapper inject REAL, caller DECOY, param:conn su Patcher vero produce pragma_applied e FK cambia su DECOY1 mentre REAL0. Log ~/pyteman-evidence/t171-callable-bn7pyl7l/log.jsonl. Questo non è limite accettato dall'utente: policy richiesta rifiuta ambiguity sul callable effettivo, non solo funzione/partial.
Richiesto delta piano minimo per __call__ effettivo o conservative unavailable se opaque, senza ricopiare inspect. Helper attuale segue partial tramite obj.func e isinstance (override target possibile) e depth exhausted ritorna intermedio lasciando inspect proseguire; richiedere base reads e unavailable al limite, niente 'wrong answer' come degrado sicuro. Reviewer finale informato di non approvare candidato con bug noto. Nessun shared edit.

Peer conferma riproduzione __call__ e property partial.func eseguita dal vecchio helper. Sul depth ha confermato fall-through da lettura ma NON riprodotto misbind: non viene registrato come misbind misurato. Nuova proposta 'guard __init__ due righe per classi' respinta come incompleta; policy conservativa per class target binding e nessuna modifica del supporto non-param. Non autorizzata riduzione del test a REAL untouched, perché DECOY errata era il difetto reale.

Reviewer ha segnalato costo concreto del rifiuto indiscriminato classi: costruttore semplice funzionante diventerebbe miss. Coordinator ha chiesto decisione distinta all'utente, che ha scelto mantenere classi semplici. Non accettata scorciatoia 'due righe su __init__' per tutte le classi: metaclass/__new__/metadata possono decidere firma. Mandato aggiornato a entrambi i peer, resto delta invariato.

Checkpoint terminale implementer: candidato intermedio2100222a/patcher4552df98 NON finale. Peer riporta blocker forged metaclass MRO: nuovi helper leggono __mro__/__dict__ dinamici invece di _CLASS_MRO/_CLASS_NAMESPACE già disponibili, permettendo al target di alterare firma giudicata. Risultato ancora attribuito al peer, richiesta prova/path e correzione sole letture base con regressione no wrong-connection.
Fermati ulteriori cleanup opzionali helper/fastpath e nuovi fanout high: reviewer finale già assegnato pyteman-release-review. Reviewer interno aggiuntivo appena concluso, richiesto elenco findings subito senza attendere altra consegna. Nuovo supporto classmethod/staticmethod __call__ non entra per sola simmetria: richiede prova call/binding e assenza false certification, non ampliamento automatico. Shared invariato, nessuna approvazione candidato intermedio.

Blocco implementer in ~/pyteman-evidence/BLOCKER-TASK171-perimeter.md letto: candidato2100222a/patcher4552df98 riporta cinque false certifications riprodotte dal peer (__partialmethod__, __text_signature__, duck functionlike, inherited signature None, forged MRO), più demozioni classi non dichiarate. Non confermate tutte da coordinator; NON sono cinque bug pubblicati, perché il candidato non è mai integrato. Review intermedia e suite1119 verde non sufficiente. Implementer fermato; decision review affidata all'altro peer senza fanout/suite duplicate, per evitare quarto ciclo blocklist metadata.

Assessment indipendente in ~/pyteman-evidence/t171rev/ASSESSMENT-TASK171-redesign.md raccomanda firma da code e spike su otto forme/kinds, metadati non letti. Utente ha autorizzato ritiro __signature__ non decorata dopo domanda specifica, quindi non dedotto dalle scelte precedenti. Decisione mantenere classi semplici resta. Coordinator ha precisato rischi partial/receiver variadico/Placeholder e perdita C-callable come costo reale, non ha adottato indiscriminatamente ogni affermazione dell'assessment. Implementazione redesign autorizzata, candidati precedenti restano NOT APPROVED.

Ricevuto spike peer3.14.7 su accounting partial code-derived14/14 senza differenze nelle forme provate. Confermata la raccomandazione di mantenere param sui soli argomenti forniti nella chiamata corrente, senza nuova decisione utente perché preserva contratto esistente. Implementazione prosegue da export pulito, snapshot2100222a preservato. Nessun risultato spike presentato come prova del candidato finale ancora inesistente.

Checkpoint redesign in ~/pyteman-evidence/scout-t171redesign-1789847567, CHANGES-TASK171-redesign.md letto:11test falliti residui, nessun candidato/hash. Triggers __signature__ e import locale inspect rimossi dalla nuova policy; fallimenti non equivalgono da soli a successo del fix. Autorizzato riarmare fixture preservando invarianti e traiettoria, non cancellare test o spostare callback a fase non equivalente. Per finestre mid-build/cache non più raggiungibili via metadata, wrapper test-only del helper reale può innescare reentry e delegare, documentato come controllo interno; almeno scenario reale import/getter/setter resta. Ogni adattamento deve avere mutante guard discriminante. Test storico TASK131 mantiene nested publish+fire, primary identity e status. No review prematura o suite parziale dichiarata completa.

Mappa11fail ricevuta: un fallimento era accesso stale sig_unparseable dopo rename sig_reason, non mera osservabilità perduta. Coordinator ha letto test takes_the_slot_being_built: trigger pass1 non equivalente, deve restare mid-build per verificare last reread/merge; autorizzato wrapper test-only helper reale anche qui, senza limite artificiale al numero di fixture. Cache9/10 necessitano mutanti opposti (undo mancante vs undo che cancella cache del nested); storia11 mutante applied, non generico cache undo.
Callable __call__ come classmethod builtin esatto verso plain function può restare supportato se routing cls è provato, test receiver variadico e metadata decoy; non è ampliamento rispetto al master se solo candidato refutato lo rifiutava. Richiesta baseline pubblicata b769bf9 come riferimento, non2100222a. Sottoclassi descriptor con override non accertabile unavailable, nessun framework generico. Implementazione ancora non candidata.

Checkpoint20settembre: implementer ha completato riarmo fixture e riportato1095/1skip, patch1b5ab647f85bcf9935230ef25f00bbd52d133f18e71ea7c58d6aad68dbc95326. NON CANDIDATO FINALE: ha lasciato fuori reach table/withdrawal docs, getter-not-invoked, cinque vettori end-to-end e parameter-kind tests, interpretando erroneamente no-scope-change come facoltà di omettere deliverable già autorizzati. Coordinator ha fermato review prematura e riattivato completamento sullo stesso tree, nessun nuovo design o fanout. Handoff erroneamente inviato a planner-76, altro progetto, anziché coordinator; destinatario avvisato di ignorare e protocollo nome/cwd ribadito. Shared invariato, nessuna pubblicazione171.

Candidato redesignv2 cf46c0d84e494eef2906b55977be9a63f99921aef42a34c1805bc63e147f5bad ricevuto e hash verificato, sette file controb769bf9; suite indipendente da fresh export avviata. Peer riporta1141pass2skip e copertura reach/metadata/kinds/partial iniziale+extension; reviewer finale incaricato ora sul candidato completo, senza fanout. Controlli riarmo preservati.
Nessuna nuova decisione aperta sul partial keyword omesso: miss è caller-only già concordato, non falso negativo da nuovo task. Reason deve essere preciso su argomenti del firing, non negare valore prebound esistente. Reach ABC/namedtuple/str/Exception/C da confrontare con tabella deliberata, niente allargamento automatico. Claim partial flattening va limitato alle forme/versioni realmente provate, non universale. Nessuna modifica shared o pubblicazione171 ancora.

Review finale cf46c0d8: CHANGES REQUESTED per due gap di test, nessun difetto produzione sopravvissuto agli attacchi del reviewer. M4 (base MRO/namespace reads -> attributi dinamici) e M9 (exact FunctionType -> isinstance) introducono falsa attribuzione ma suite1141/2skip resta verde. Report ~/pyteman-evidence/t171v2/VERDICT-TASK171-v2.md letto. Autorizzati due detector reali+hookcount e mutazioni esatte, insieme ai tre wording già approvati; nessun nuovo runtime/refactor/fanout. Delta stesso reviewer poi candidato finale.
Optional receiver accounting failure usa reason _PREBOUND_SHAPE indistinguibile da partial prebind overflow: comportamento conservativo senza misbind, dichiarato dal reviewer non bloccante. Rinviato nello stesso task come limite diagnostico, NON applicato in questo delta né trasformato in task nuovo. Mutanti M6 equivalente e partial override corretto non sono findings.

PR16 MERGED2b3f1d7fee17bff88778adb0ed57ac4e8bf59396, commite41573c315b31fa85b06ec2a458cae4b1579cca1; CI35498428640 sei job success, review/commenti/discussion vuoti al controllo finale. Review persistente APPROVED32b5bdbd e suite indipendente/shared1145pass2skip attesi. Hash/settefile confronto byte-exact, backup/provenienza ~/pyteman-evidence/task171-v4-integration-20260920-095003/. Nessun candidato refutato pubblicato.
Tutte scelte user applicate: code-derived binding ignorando metadata espliciti, preservazione classi semplici, rifiuto conservativo forme non verificabili; caller-only partial omesso resta miss deliberato. Public introspection intatta. Receiver reason non bloccante registrato nelle note precedenti.
Done respinto dal hook per marker simplify/code-review assenti nel transcript coordinator, gate svolti delegati. Nessun bypass/retry identico o risultati inventati; tracker resta In Progress amministrativo benché consegna pubblicata e AC verificati.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed 2026-09-25 by backlog audit. PR#16 merged as commit e41573c (derive parameter binding from callable code), CI green. Administratively stuck In Progress. Code published in v0.2.0.
<!-- SECTION:FINAL_SUMMARY:END -->
