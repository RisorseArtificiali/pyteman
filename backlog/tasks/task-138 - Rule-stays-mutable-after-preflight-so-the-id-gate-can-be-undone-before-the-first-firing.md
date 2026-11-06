---
id: TASK-138
title: >-
  Rule stays mutable after preflight, so the id gate can be undone before the
  first firing
status: Done
assignee: []
created_date: '2026-09-17 08:57'
updated_date: '2026-09-27 17:51'
labels:
  - patcher
  - rules
  - cross-runtime
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`Patcher.__init__` now refuses a rule whose `id` cannot be read, is not a str, is blank, or repeats an earlier one. That check speaks only for the moment it runs.

`Rule` is a plain dataclass and is not frozen (src/pyteman/rules.py:39), so the caller still holds the object the plan holds. `firing.py:19` (`"rule": rule.id`) and `actions.py:81` (`key = (rule.id, message)`) read `id` again on every firing, inside the instrumented callable, where no degradation applies.

Two shapes put the refused hazard back after preflight has passed. Rebinding the attribute (`r.id = None` once the Patcher exists) and an `id` property that answers once and then stops, which the codebase already calls ordinary: `UnreadableIdRule`'s own docstring describes a lazily-resolved id whose backing store has gone away.

Demonstrated by the high-effort reviewer end to end: a rule that passed the gate with `id="good"`, rebound to None afterwards, wrote `{"ts": ..., "rule": null, "event": "entry", ...}` to the firing log.

This is a limit of preflight rather than a defect in the gate, and it cannot be closed from the patcher. Both candidate fixes reach files that are currently out of scope: freezing `Rule` touches src/pyteman/rules.py, which is frozen under TASK-7 (APPROVED), and snapshotting the id into the plan so the firing record reads the snapshot touches firing.py and actions.py, which belong to another runtime.

Documented in the meantime, in docs/rules.md under Ids: a rule should be treated as frozen once it has been handed to a Patcher. Documentation is the mitigation, not the fix.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Decide between the two fixes: freeze `Rule` (or make `id` read-only) so the attribute cannot be rebound, or snapshot the id at plan time and have the firing record and the outcome dedup read the snapshot rather than `rule.id`. The two differ in COVERAGE, not only in cost: the programmatic door is duck-typed on purpose (see TASK-143 and the `Patcher.__init__` docstring), so freezing the dataclass closes the hole only for actual `Rule` instances and leaves it open for the hand-built objects the gate's own tests use; a `Rule` subclass can also define `id` as a property, which freezing the base does not prevent. Snapshotting covers every shape because it stops reading the attribute at firing time.
- [x] #2 Whichever is chosen, a rule that passed preflight cannot cause a firing record to carry a non-str or unreadable id, including through an `id` property that answers once and then raises.
- [x] #3 A regression test builds a Patcher with a legal id, mutates the id afterwards, fires, and asserts the recorded identity is the one preflight accepted.
- [x] #4 The scope conflict is resolved explicitly rather than worked around: rules.py is frozen under TASK-7 and firing.py/actions.py belong to another runtime, so this needs the owners' agreement before any edit.
- [x] #5 The docs/rules.md mitigation paragraph under Ids is updated or removed once the real fix lands, so the docs do not keep advising a workaround for a closed hole.
- [x] #6 `rule.event` is covered by whichever fix is chosen, not just `rule.id`: firing.record reads both raw on adjacent lines (firing.py:19-20) and only `id` is preflighted today
- [x] #7 The docs cleanup in AC #5 covers all three places the preflight limit is now asserted: docs/rules.md under Ids, the `_Composite` docstring at patcher.py:544-554, and the gate comment block at patcher.py:699-781
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Three sharpenings from the /simplify altitude review of the TASK-2 final snapshot (2026-09-17). None of them change this task's verdict that tracking is the right call; they change its scope and its cost estimate.

ONE. The gate protects `rule.id` and leaves `rule.event`, which is read raw on the very next line of the same dict literal.

`FiringLog.record` builds `{"rule": rule.id, "event": rule.event, ...}` at firing.py:19-20, per firing, inside the instrumented callable. This task's stated invariant is that attributes read raw at firing time must be preflighted, because a hand-built rule's attribute access is user code. That invariant covers `event` exactly as much as it covers `id`, and nothing preflights `event` on the programmatic door.

The exposure is narrower, and the reason is worth stating so the fix is not over-scoped: a rule only fires at all if its `event` compared equal to "entry" or "exit" at patch time, so an `event` that never matches never reaches the read. It is the same SHAPE nonetheless. The `_Composite` docstring already says so in as many words: the event vocabulary is checked in the YAML loader and nowhere else, and `Rule` is a plain dataclass, so a Patcher built in process can carry any event string. The two live shapes are the one that answers once and then stops, which docs/rules.md names as the ordinary way a lazily-resolved field goes bad and which would raise from firing.py:20 inside the workload, and a non-serialisable `event` that compares equal to "entry" and then takes down `json.dumps` at firing.py:27.

Folded in here rather than filed separately so that whichever fix is chosen covers the whole firing record rather than one field of it.

TWO. The patcher half of the snapshot option is cheaper than this task implies, and the negotiation is the whole cost.

`rid` is already computed in the gate loop at patcher.py:771 and discarded at the end of the loop body. The file already carries exactly this kind of value in the plan: `_describe_rule`'s docstring states the principle, which is to render the identity once in `__init__` where a failure to render costs nothing, and to carry it in the plan rather than re-deriving it at a moment that cannot afford to fail. The plan tuple already holds `described` on that reasoning, and `_patch` unpacks it at patcher.py:876.

So option B is not "rewrite the plan". It is one more tuple slot holding a value that is already in hand, plus the consumer side: `firing.record(rule, ...)` and `_note` at actions.py:81 both take the rule object and re-read the attribute, so they would need to take the snapshot instead. That is two call sites in files belonging to another runtime, which is the negotiation AC #4 already requires. The cost estimate in this task's description should say that, because "touches firing.py and actions.py" reads as larger than it is.

THREE. AC #1 presents the two fixes as equivalent alternatives and they are not.

`Patcher` never checks the type of what it is handed, so freezing the dataclass closes the hole only for actual `Rule` instances and leaves it open for exactly the hand-built objects the gate's own tests use (`UnreadableIdRule`, `Interrupting`, `HostileId`). A `Rule` subclass can also define `id` as a property, which freezing the base does not prevent. Snapshotting covers every shape because it stops reading the attribute at all. AC #2 and AC #3 do discriminate between the two if read strictly, but AC #1 should say the options differ in COVERAGE rather than only in cost. Tracked more broadly in TASK-143, which asks for the duck-typed door to be recorded as a decision rather than an inheritance.

Two new acceptance criteria added for ONE and for the widened docs cleanup. The AC #1 wording change is left to whoever picks this up, since rewording an existing criterion through the tracker clears the check marks on all of them.

RISOLUZIONE AC #4 (2026-09-27, registrata come TASK-140 registro' il lapse del freeze): l'opzione scelta e' lo SNAPSHOT (copertura totale: la porta programmatica e' duck-typed di proposito, un Rule congelato non chiude nulla per gli oggetti hand-built che quella porta esiste per servire, e una property di sottoclasse scavalca una base congelata). filing.py resta INTOCCATO (il record legge i quattro campi da qualunque oggetto riceva; sono i dispatcher a passare lo snapshot). Il freeze TASK-7 su rules.py e' venuto meno col ciclo di review di TASK-140 (precedente citato dal PR #163). actions.py e' sempre stato sotto i gate di questo repo: la nota 'altro runtime' del 2026-09-17 descriveva un confine di scope che non esiste piu'. Implementazione: _RuleIdentity namedtuple (immutabilita' reale, non solo dichiarata: il carrier hand-rolled della prima stesura era mutabile e /simplify l'ha convertito), costruita in _new_state come state['identity'] accanto ad action_repr (TASK-130 rese _bind_fresh l'unico seme: la nota del task che suggeriva lo slot nella plan tuple e' stata respinta dall'agente altitude con l'argomento del profilo di errore misto).

BELT HIGH (2026-09-27): CHANGES-REQUIRED con una finding CRITICAL confermata da probe: la finestra planning-to-bind restava aperta (il gate valida l'id ma lo scarta; _new_state lo rileggeva SENZA validare), quindi un rebind a None o a un oggetto non serializzabile nella finestra snapshot-ava il rischio (V1: record con rule null; V2: TypeError da json.dentaps dentro il workload). FIX: la lettura di bind ora VALIDA (id di nuovo attraverso _rule_identity, event attraverso il nuovo _bound_event col type-before-comparison del gate di planning), quindi il rebind in finestra rifiuta il patch con i testi di ammissione. Probe della belt rieseguito sull'albero fissato su tutti e tre gli scenari: V1/V2 REFUSED, V3 (post-bind) registra 'good'. Due test di regressione aggiunti per la finestra (id None+object, event fuori vocabolario); mutazione 'validazione rimossa' li uccide entrambi. Residuo NOMINATO non chiuso: due regole rebind-ate sulla stessa stringa nella finestra bindano entrambe quella stringa (il seen-set del gate non segue oltre il suo istante); ogni record resta ben formato, le etichette collidono. Findings docs 2 e 3 applicati: il paragrafo SOPRA quello riscritto in rules.md asseriva ancora il comportamento pre-snapshot come fatto corrente (riscritto); le affermazioni forti scoped al percorso record e alle mutazioni post-bind (le letture degradate dei testi di rifiuto non raggiungono un record e non possono alzare; module/symbol restano letture semplici perche' nominano lo slot su cui la regola e' atterrata).

GATE /simplify combinato: 4 finding APPLICATI (coda stale del commento del gate che contraddiceva la riscrittura; paragrafo _Composite riportato alla sua giustificazione manifesta con la lettura live di _split_events; namedtuple; rename rule->named nei due helper privati). Mutazioni verificate: identity ignorato in run_action e state['identity']=rule uccidono i test di regressione; validazione di bind rimossa uccide i test di finestra. Batteria finale: check pulito, 1303 passed 2 skipped (1299 + 4 test nuovi).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Chiuso con il merge e734671 (PR #171, squash di 62f6173 su master 34a8c88, delta 47f4e82/62f6173 sui finding della revisione). Scelta: SNAPSHOT, non freeze (copertura totale sulla porta duck-typed). _RuleIdentity (namedtuple, immutabile davvero) costruita in _new_state come state['identity']: la lettura di bind VALIDA id (di nuovo attraverso _rule_identity) ed event (nuovo _bound_event, type-before-comparison), quindi un rebind nella finestra planning-to-bind rifiuta il patch con i testi di ammissione invece di snapshot-are il rischio (la belt aveva provato che la prima stesura lasciava passare None e oggetti non serializzabili in quella finestra; fix e probe riusati su tutti e tre gli scenari). I tre dispatcher passano identity= a run_action/await_sleep che filano un oggetto 'named' a _record_attempt/_terminal/_fail_attempt: log.record riceve lo snapshot; il chiamante diretto senza identity tiene la regola (comportamento precedente, firme compatibili). Quattro test di regressione (rebind post-install, property che smette di rispondere, id in finestra None+object, event in finestra), mutazioni che uccidono (identity ignorata, regola snapshot-ata, validazione di bind rimossa). Residuo NOMINATO in codice e docs: due regole rebind-ate sulla stessa stringa in finestra bindano entrambe (per-value, niente seen-set a bind); e l'annotazione install-time point_unreadable legge la regola viva nel suo unico record, di proposito, fail-closed. Gate: /simplify 4 finding applicati; belt CHANGES-QUIRED (finestra) fissata e riprovata; revisione indipendente CHANGES-REQUIRED due round docs (commento che invertiva il residuo duplicato; rules.md che sottostimava le letture fuori garanzia) fissati, APPROVED al terzo round su 62f6173; CI verde 7 check sullo stesso head; batteria 1303 passed 2 skipped. AC #4 registrato nelle note: firing.py intoccato, freeze TASK-7 lapsed col precedente TASK-140, actions.py da sempre sotto i gate di questo repo.
<!-- SECTION:FINAL_SUMMARY:END -->
