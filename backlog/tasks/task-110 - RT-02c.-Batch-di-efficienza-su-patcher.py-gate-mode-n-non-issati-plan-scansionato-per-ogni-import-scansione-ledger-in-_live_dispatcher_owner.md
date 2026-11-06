---
id: TASK-110
title: >-
  RT-02c. Batch di efficienza su patcher.py: gate mode/n non issati, plan
  scansionato per ogni import, scansione ledger in _live_dispatcher_owner
status: Done
assignee: []
created_date: '2026-09-17 03:08'
updated_date: '2026-09-27 10:15'
labels:
  - rt
  - opus-5
  - review-rt-02
  - performance
dependencies:
  - TASK-2
references:
  - src/pyteman/patcher.py
  - src/pyteman/actions.py
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Trovato dall'agente efficiency della review /simplify su RT-02 (TASK-2), 2026-09-17. Sei reperti della stessa famiglia, raggruppati perche' toccano tutti lo stesso file e la stessa struttura dati e separarli produrrebbe sei diff che si pestano i piedi. NON sono bug: il comportamento e' corretto, e' il costo a essere evitabile.

1. **_gate rilegge rule.fire a ogni chiamata.** `_gate` fa `rule.fire.get("mode")` e, per countdown, `rule.fire.get("n")` a ogni singolo raggiungimento della regola, piu' l'`int()` su `n`. Sono valori immutabili dal load in poi. Vanno issati nella tupla gia' costruita una volta sola in `_make_dispatcher` (quella che oggi porta `(rule, when_code, key_code, state)`).
   Attenzione a DUE delta semantici, entrambi voluti ma da dichiarare: (a) mutare `rule.fire` DOPO l'install smetterebbe di avere effetto, cosa che oggi funziona per accidente e che nessun test pinna; (b) una `n` non convertibile a int fallirebbe al momento della patch invece che al primo firing, il che e' un MIGLIORAMENTO (fail-fast) ma sposta il messaggio d'errore di fase e potrebbe toccare un test.

2. **_patch scandisce l'intero piano a ogni import.** Il loop su `self._plan` filtra per modulo dentro il corpo, quindi un ruleset di N regole costa N iterazioni per OGNI modulo importato che l'hook intercetta, anche quando zero regole lo riguardano. Un indice `self._by_module` costruito una volta in `__init__` (dict da nome modulo a lista di spec) rende il costo proporzionale alle regole che riguardano davvero quel modulo.

3. **_live_dispatcher_owner scandisce ancora il ledger.** RT-02 ha aggiunto `_inflight`, consultato per primo, che copre il caso caldo. Il fallback resta una scansione lineare di `owner._wrapped` per ogni slot e per ogni Patcher noto. Un dict specchio con chiave `id(wrapper)` mantenuto insieme al ledger lo rende O(1). Da fare INSIEME al punto 4 di questo elenco e al task sulla tupla del ledger, perche' toccano la stessa struttura.

4. **Il preflight sui duplicati legge r.id due volte.** Una volta per il test di appartenenza al set e una per l'add. Un solo `rid = r.id` basta. Micro, ma il preflight gira su ogni costruzione di Patcher.

5. **seen_keys e' allocato per ogni regola anche se solo once_per lo legge.** Questo e' uno SKIP DELIBERATO della review, registrato qui perche' la regola di progetto vuole che ogni raccomandazione atterri da qualche parte, non perche' vada fatto. Il costo e' un set vuoto per regola al momento della patch, non per firing, quindi non e' su un percorso caldo; renderlo condizionale renderebbe la forma dello stato NON uniforme fra le regole, e ogni lettore di `state` dovrebbe poi difendersi da una chiave che c'e' o non c'e'. Il costo di manutenzione supera il guadagno. Chi riprende questo task valuti di CHIUDERE questo punto come wontfix invece di implementarlo.

6. **actions.py:19 costruisce str(rule.action) a ogni firing quando c'e' un log attaccato.** La rappresentazione dell'azione e' immutabile dal load; renderla una volta e conservarla. Nello stesso giro: `Recorder.record` nei test ignora il parametro `note`, quindi nessun test puo' oggi asserire su cosa un'azione ha annotato.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 mode e n sono letti una volta sola alla costruzione del dispatcher e non a ogni raggiungimento della regola; i due delta semantici (mutazione post-install di rule.fire, n invalida che fallisce al patch time) sono dichiarati in docs/rules.md o in un commento, non scoperti da chi legge dopo
- [x] #2 Un indice per modulo costruito in __init__ sostituisce il filtro dentro il loop di _patch; un import di un modulo che nessuna regola nomina non itera sulle regole altrui (done in TASK-126, PR #132)
- [x] #3 _live_dispatcher_owner non scandisce piu' linearmente il ledger nel percorso di fallback; la mappa specchio e il ledger non possono divergere (un solo punto di scrittura per entrambi)
- [x] #4 Il preflight sui duplicati legge r.id una volta sola
- [x] #5 Il punto 5 (seen_keys) e' chiuso esplicitamente, come implementazione o come wontfix motivato; non resta aperto in silenzio
- [x] #6 str(rule.action) e' reso una volta sola e non a ogni firing; Recorder.record nei test registra anche note, cosi' un test puo' asserire su cosa un'azione ha annotato
- [x] #7 La suite completa passa senza modifiche ai test esistenti, salvo quelli che pinnano deliberatamente la fase di un errore su n invalida
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Item dispositions (2026-09-27): item 2 already done by TASK-126 (AC checkbox marked); item 4 already fixed by TASK-140's single raw_id read in _admitted_identity (verified in this tree); item 5 closed WONTFIX per the task's own recorded rationale (an empty set per rule at patch time, not per firing; conditional presence would make the state's shape non-uniform, and the maintenance cost exceeds the gain) and AC #5 will be checked with a pointer here; items 1, 3, 6 implemented this round: gate mode/n hoisted into the state at bind with all THREE semantic deltas declared in _new_state's docstring (post-install rule.fire edits inert, unconvertible n fails at bind, the action dump renders unconditionally at bind including on never-logged rulesets), the owner fallback O(1) via an id-keyed mirror with a single-writer pairing (_publish writes ledger+mirror together, _restore settles both), and the action dump rendered once per rule handed to run_action with the str fallback kept for direct callers. Measured by the four-angle review: gate 42ns->25ns per visit, owner lookup ~48x at 200 wraps, str 1.26us saved per firing on the logging path. Mutations kill: per-visit gate reads, mirror.pop dropped, dispatcher seam reverted to no action_repr (the seam test fires through a dispatcher with a duck log and asserts the note across a post-install action edit). One process incident, honestly recorded: an intermediate edit truncated tests/test_activation_atomic.py to 461 lines; the next suite run caught it (1129 passed vs the expected ~1269), the file was restored from HEAD and the two intended edits re-applied, and the count verified back to full.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Merged as 17fa3b4 via PR #160 (head a1ef4c9). Gates: /simplify four-angle findings applied (the seam connection so the dispatcher path is pinned, not just the fallback; the dead import; the third declared delta in the docstring; the _publish wording); code-reviewer-typed high review CLEAN with the mirror invariant probed through refused uninstall, retry, and third-Patcher ownership, and the gate-inertness confirmed at runtime; three mutations kill (per-visit gate reads, mirror.pop dropped, dispatcher seam reverted); battery check clean, 1271 passed 2 skipped; independent review APPROVED at a1ef4c9 with two info findings (the mirror invariant pinned indirectly rather than by a direct suite assertion, the probe script recorded in the evidence dir; a Log/ListLog naming nit); PR CI green; master CI green. Item dispositions in the implementation notes: items 2 and 4 landed in earlier tasks (TASK-126, TASK-140), item 5 closed wontfix by its recorded rationale, items 1, 3, 6 implemented here with the measured savings.
<!-- SECTION:FINAL_SUMMARY:END -->
