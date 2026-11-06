---
id: TASK-121
title: >-
  RT-02n. Il meccanismo di rientranza e' derivato quattro volte in patcher.py e
  una in docs/rules.md
status: Done
assignee: []
created_date: '2026-09-17 03:58'
updated_date: '2026-09-30 00:41'
labels:
  - patcher
  - docs
  - comments
  - rt-02
dependencies: []
references:
  - src/pyteman/patcher.py
  - docs/rules.md
  - tests/test_activation_atomic.py
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Trovato dal gate /simplify sulla tranche RT-02 (2026-09-17). Nessun difetto di comportamento, solo costo di manutenzione e rischio di deriva.

Punto 1, la catena di rientranza. Quattro punti in patcher.py piu' uno in docs derivano lo stesso fatto meccanico, cioe' che costruire un dispatcher importa `inspect`, che `inspect.signature` esegue il `__signature__` del callable, e che quindi `_patch` rientra e la chiamata annidata puo' raggiungere quello stesso attributo: patcher.py:771-781 (il blocco nuovo sopra la seconda rilettura), patcher.py:729-742, patcher.py:487-494 (docstring di `SlotOwnershipError`), docs/rules.md:300-313. La conseguenza e' poi ripetuta in due docstring di test, tests/test_activation_atomic.py:2667-2669 e :2484-2486.

Il contenuto davvero nuovo del blocco a :771-781 sono due proposizioni: che la lettura in cima al loop e' avvenuta PRIMA che il dispatcher esistesse e quindi non puo' strutturalmente vederlo, e che scrivere comunque e' cio' che costa al ledger la sua forma. Quelle righe si guadagnano il posto. Le cinque che ri-derivano la catena import/`__signature__` no, perche' :729-742 la deriva gia' e passa esplicitamente la mano dicendo che c'e' una seconda lettura contro lo stesso pericolo appena prima della scrittura.

Forma suggerita dal gate: tenere una sola derivazione canonica a :729-742, che e' la prima che il lettore incontra, e far aprire il blocco nuovo direttamente su "la lettura in cima al loop non puo' coprire questo intervallo, e' avvenuta prima che il dispatcher esistesse". La docstring a :487-494 e' quella che derivera' per prima, perche' nessun test la lega al codice.

Stessa famiglia, piu' piccolo: "adding it to that dispatcher is the fix and is tracked separately" (:759-761), "which is the drop the re-patch branch above makes and is tracked with it" (:790-792) e la docstring di test a :2671-2673 sono tre enunciati dello stesso follow-up tracciato.

Punto 2, altitudine del commento su `ctx["exc"]`. Il blocco di 16 righe a patcher.py:994-1008 e il nuovo elenco a docs/rules.md:502-515 si sovrappongono quasi punto per punto: `ctx` passato a `eval` come mapping dei locals, l'assignment expression che ci scrive dentro, `result` ri-seminato perche' gli override si concatenano e `exc` perche' ogni exit raggiunta ha promessa l'eccezione del corpo, `args`/`kwargs` seminati una volta per chiamata che restano corrotti, e la valutazione contro una copia dentro `eval_expr` tracciata a parte in TASK-115. Sono coerenti oggi perche' scritti nella stessa passata, e non c'e' nessun meccanismo che li tenga tali.

Divisione suggerita: il commento locale possiede la ragione per cui QUESTA istruzione sta dentro il loop invece che sopra, che e' un fatto su questo codice e su nient'altro, all'incirca la prima meta' fino a "the seed belongs where every exit passes". Le ultime quattro righe, su `args`, `kwargs`, `_signature` e il piano della copia in `eval_expr`, sono un enunciato sull'intero canale del contesto e su lavoro non fatto qui, che e' l'altitudine sbagliata per un commento dentro il loop di uscita del dispatcher ed e' gia' scritto meglio in docs/rules.md:510-515. La versione in docs e' anche l'unica che tests/test_docs_rules.py puo' sorvegliare.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 La catena import inspect / __signature__ / rientranza e' derivata per esteso in un solo punto di patcher.py, e gli altri vi rimandano invece di riderivarla
- [x] #2 Il blocco sopra la seconda rilettura conserva solo cio' che aggiunge, cioe' perche' la lettura in cima al loop non puo' coprire l'intervallo e cosa costa scrivere comunque
- [x] #3 La docstring di SlotOwnershipError non rideriva il meccanismo
- [x] #4 Il commento su ctx[exc] conserva la ragione locale della posizione dentro il loop e lascia a docs/rules.md l'enunciato generale sul canale del contesto
- [x] #5 Nessun enunciato rimosso sparisce del tutto: se non e' in un commento e' in docs/rules.md
- [x] #6 Suite verde dopo la potatura, incluso tests/test_docs_rules.py
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #95 #128. Added lines already present on master per PR: #95 0/14=0%  #128 0/19=0%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.

Merged 2026-09-30 via #195 (281dfd3). The first consolidation entrenched a stale chain; the code review caught it (the build's signature import had been removed) and the canonical derivation was rewritten on the true mechanism. Evidence under /home/pantinor/pyteman-evidence/t191/: diff121.patch sha256 4049d71c, tree121-hold2.sha256, VERDICT-121.md in t191rev.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by PR #195, squash-merged as 281dfd3 on master at 2026-09-30 00:41Z. The re-entry chain is derived in full exactly once, in the comment block opening _patch, and rewritten on the mechanism that remains true: the walk and the write run target code, an import in it is served by the live hook on every __import__ (cached modules included), the build's former signature import is named as removed (it ran nothing the target controls since that change), and concurrency is the other road. AC1: every other site points there (SlotOwnershipError's docstring, the per-slot re-read, the second re-read; the in-flight-map site names the target-code route, with the reviewer noting a parenthetical would name the derivation's home too, recorded here). AC2: the second re-read keeps only its own interval and cost, justified by what is still open (target code in the store, other threads). AC3: SlotOwnershipError keeps the impasse, not the mechanism. AC4: the exc-seed comment keeps the local obligation inline (every exit reached sees the body's own exception, not resting on how conditions happen to be evaluated) and defers the channel to rules.md. AC5: rules.md's identity-stability passage and its condition-cannot-write passage cover everything removed; the re-entry test's docstring now labels its staging synthetic. AC6: suite 1528 passed 2 skipped including the docs tests. Supersedes #95 and #128, both cut against text the intervening merges rewrote; both closed with pointers. Comments-only diff: no battery, /simplify claimed under the documentation-only exemption. Gates at 43c5448: code-review high seven findings drove the truthful rewrite and were all applied, independent verdict APPROVED (VERDICT-121.md). One CI flake (a sqlite lock in a subprocess driver on 3.13) was rerun green; unrelated to the diff.
<!-- SECTION:FINAL_SUMMARY:END -->
