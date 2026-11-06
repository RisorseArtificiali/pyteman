---
id: TASK-181
title: >-
  Async-aware sleep action on coroutine targets (loop stays alive, worker wedged
  on await)
status: Done
assignee: []
created_date: '2026-09-26 21:54'
updated_date: '2026-09-27 15:32'
labels:
  - patcher
  - feature
  - async
  - filed-by-ccgram
dependencies: []
references:
  - src/pyteman/actions.py
  - src/pyteman/patcher.py
  - 'https://github.com/RisorseArtificiali/pyteman/pull/141'
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Feature request from the ccgram session (2026-09-27, after verifying TASK-178 on master 76114e2 in their exact embedding). Their TASK-43 incident signature requires a fault shape where a worker is wedged on an await while the event loop stays alive (their monitor kept servicing other sessions through a 7-hour freeze). On a coroutine target, an entry rule with a sleep action runs the action synchronously at the first await (src/pyteman/actions.py ~151, time.sleep), which blocks the whole loop: a different, coarser fault. Useful for freeze-style tests and the only correct semantics for sync targets, but it cannot express the wedged-worker shape.

Suggested shape: the coroutine entry wrapper is already async, so an async-aware variant of the sleep action can await asyncio.sleep(ms) on coroutine targets while sync targets keep time.sleep. Decisions to make at design time: whether the split rides the dispatcher kind (like the extend guard) or the rule declares it; what fire.once_per means while suspended; interaction with cancellation during the async sleep (the record is already written; the cancel should propagate like it does through the original); and the docs for both vocabularies (a blocking stall versus a suspended target).

Until this exists the reporter keeps a direct monkeypatch for the hang shape and uses rulesets for entry tracing around it, so nothing is lost; priority is ours. Natural companion of TASK-178 (an async fault vocabulary for the targets it opened); TASK-37 remains the umbrella.
<!-- SECTION:DESCRIPTION:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
IMPLEMENTAZIONE (2026-09-27): la dichiarazione viaggia sulla REGOLA (action.async: boolean, loader _boolean rifiuta le stringhe; yes/no nudi sono bool per il loader YAML 1.1 e restano spelling validi). Su target coroutine il dispatcher sceglie per chiamata la strada: comp.has_async_sleep (slot nuovo su _Composite, default False, ricalcolato da _republish_state, il single writer TASK-130, a ogni rebind di entries) seleziona il gemello asincrono _serve_entries_async, che e' _serve_entries istruzione per istruzione e diverge solo sulla chiamata await_sleep per la regola che la dichiara. Su target sincrono la dichiarazione e' rifiutata su ENTRAMBE le porte (armo fresh-install in _patch e guardia speculare in _extend_dispatcher accanto al rifiuto exit, stesso testo via _async_sleep_refusal). asyncio e' importato DENTRO await_sleep: la catena sitecustomize di un'attivazione sync-only non lo paga (misurato dall'agente efficiency: import di classe 100ms; a runtime e' un lookup perche' il loop esiste gia'). Estratti _record_attempt, _fail_attempt, _sleep_seconds condivisi da run_action e await_sleep.

DECISIONI DI DISEGNO (le quattro domande del task): (1) split sulla regola e non sul kind del dispatcher: il kind rimuoverebbe silenziosamente il vocabolario blocking dai target coroutine (comportamento documentato), il test plain-sleep-blocks pinnaria la regressione; (2) fire.once_per/countdown durante la sospensione: il gate conta PRIMA dell'azione su entrambi i vocabolari (verificato: il lock di _gate chiude in tre sezioni prima del ritorno, l'azione corre fuori da ogni sezione critica, la prenotazione e' di install-scope); una cancellazione a meta' sospensione lascia la chiave spesa e l'attempt 'failed', coerente col contratto count-before-action; (3) cancellazione: viaggia sulla porta BaseException, status failed con CancelledError nell'outcome, il record era gia' scritto: come un cancel ai punti di await dell'originale; (4) documentati entrambi i vocaboli in docs/rules.md (paragrafo target coroutine + riga sleep della tabella) e README.

GATE (2026-09-27): /simplify 4 angoli in parallelo + belt high. APPLICATI: rifiuto sulla porta extend (trovato indipendentemente da altitude per lettura e provato dalla belt con due probe: alias-extend su dispatcher sync serviva il sonno async come time.sleep bloccante, 0.3s misurati; fix: guardia speculare + builder condiviso + test parametrizzato entry/exit + probe della belt rieseguiti sull'albero fissato: entrambi ora rifiutano); import asyncio dentro la funzione (efficiency, misurato); flag composito via _republish_state al posto della scansione any() per chiamata (efficiency: la scansione costava piu' di un intero passaggio di _gate su ogni firing coroutine, 2.6us vs 1.67us a N=1; il flag costa 50ns ed e' corretto sotto extension perche' ogni rebind passa dal single writer); estrazioni _fail_attempt e _sleep_seconds (reuse: il contratto di uscita-fallita viveva in due posti e il gemello porta proprio le CancelledError). DICHIARATO SKIP: eliminare il ramo fast-path (simplification lo proponeva; rifiutato: il percorso byte-identico per i ruleset senza il vocabolario e' l'intento, ora dichiarato nel commento; il flag a 50ns disarma comunque l'argomento costo); builder per l'impalcatura watchdog dei test (reuse F3, sotto soglia, convenzione inline del file).

VERIFICA FINALE: check pulito; 1295 passed 2 skipped (1292 + 3 test nuovi dopo i fix del gate: extend entry/exit parametrizzato conta doppio + twin-road override); mutazioni: flag inchiodato a False -> feature+extension falliscono; porta extend rimossa -> test extend fallisce; porta install rimossa -> test install fallisce; _boolean neutralizzato -> righe loader falliscono; albero ripristinato byte-exact dopo ogni mutazione (sha256 b0cbc061/14fdf4cd). Probe della belt (extend entry e exit) rieseguiti sull'albero finale: entrambi rifiutano con il testo condiviso.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Chiuso con il merge ea9a378 (PR #169, squash di 5daeb71 su master da5b43d). Un sonno puo' dichiarare async: true; su target coroutine il dispatcher serve la regola col gemello asincrono della fase di entrata e la catena si sospende su asyncio.sleep mentre il loop resta vivo (la forma wedged-worker dell'incidente TASK-43 di ccgram); il sonno semplice mantiene il vocabolario blocking sullo stesso target, pinnato dal suo test. Ogni target sincrono rifiuta la dichiarazione su entrambe le porte (install e extend, un solo testo condiviso _async_sleep_refusal) invece di degradarla nello stallo. Scelte: dichiarazione sulla regola (non sul kind del dispatcher), gate count-before-action invariato sui due vocaboli, cancellazione sulla porta BaseException con record gia' scritto, entrambi i vocaboli documentati (docs/rules.md e README). Meccanica: _seed_ctx condiviso, gemello speculare con divergenza confinata alla chiamata attesa, flag comp.has_async_sleep riletto per chiamata e ricalcolato dal single writer _republish_state, asyncio importato dentro await_sleep (la catena sitecustomize di un'attivazione sync-only non lo paga). Gate: /simplify 4 angoli (4 finding applicati: rifiuto extend, import asyncio, flag composito, estrazioni _fail_attempt/_sleep_seconds; 2 skip dichiarati nelle note), belt high CHANGES-REQUIRED per la porta extend (provata con due probe propri, fix e probe rieseguiti a rifiutare), revisione indipendente APPROVED a 5daeb71 (5 invarianti HOLDS; una nota INFO registrata: il flag legge solo entries, coupling con le due porte oggi irraggiungibile), CI verde 7 check, batteria 1295 passed 2 skipped, mutazioni che uccidono (flag, ciascuna porta, validatore booleano).
<!-- SECTION:FINAL_SUMMARY:END -->
