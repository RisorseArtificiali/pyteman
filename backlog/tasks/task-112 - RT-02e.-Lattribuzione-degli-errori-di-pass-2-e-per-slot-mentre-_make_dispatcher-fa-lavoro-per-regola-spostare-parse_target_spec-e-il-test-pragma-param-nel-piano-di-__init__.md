---
id: TASK-112
title: >-
  RT-02e. L'attribuzione degli errori di pass 2 e' per slot mentre
  _make_dispatcher fa lavoro per regola: spostare parse_target_spec e il test
  pragma/param nel piano di __init__
status: Done
assignee: []
created_date: '2026-09-17 03:09'
updated_date: '2026-09-27 12:18'
labels:
  - rt
  - opus-5
  - review-rt-02
  - diagnostica
dependencies:
  - TASK-2
references:
  - src/pyteman/patcher.py
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Trovato dall'agente altitude della review /simplify su RT-02 (TASK-2), 2026-09-17. Registrato come lavoro separato perche' la correzione giusta e' strutturale e non entrava nel contratto di TASK-2.

**Il sintomo.** Il messaggio di errore che un operatore legge quando pass 2 fallisce nomina il GRUPPO di slot, non la regola. RT-02 ha gia' migliorato questo fronte introducendo il flag di fase ("resolving" contro "patching"), ma l'attribuzione resta all'altitudine sbagliata: `current` viene impostato per slot, mentre dentro `_make_dispatcher` si continua a fare lavoro PER REGOLA che puo' fallire.

**Perche' succede.** `_make_dispatcher` esegue, per ogni regola dello slot, `parse_target_spec(rule.action.get("target"))` e il test sul kind pragma/param. Sono operazioni per-regola eseguite in un contesto che sa solo dire quale slot sta trattando. Quando una di esse solleva, la nota dice "while patching <modulo>:<attributo>", e l'operatore deve indovinare quale delle tre regole su quell'attributo ha il `target:` rotto.

**La correzione al livello giusto.** `__init__` ha gia' un loop per-regola con un `except` per-regola intorno a riga 574, che e' esattamente il posto dove un errore sa nominare la regola. `parse_target_spec`, il test pragma/param e la lettura di `rule.event` vanno spostati li', e il risultato (lo spec risolto, il flag needs_sig, l'evento) va portato nella tupla del piano. Cosi' `_make_dispatcher` non parsa piu' nulla: consuma decisioni gia' prese. Un `target:` malformato diventa un errore di costruzione del Patcher che nomina la regola, invece di un errore di patch che nomina uno slot.

**Effetto collaterale utile:** questo sposta anche il lavoro fuori dal percorso di patch, il che si somma al punto 1 del task sull'efficienza. E risolve alla radice il reperto per cui la nota di pass 2 e' meno precisa di quella di pass 1.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 parse_target_spec, il test pragma/param e la lettura di rule.event avvengono in __init__, una volta per regola, dentro la copertura dell'except per-regola esistente
- [ ] #2 Un target: malformato o una regola con event ignoto fanno fallire la costruzione del Patcher nominando QUELLA regola, non un gruppo di slot al momento della patch
- [ ] #3 _make_dispatcher consuma il piano gia' calcolato e non rifa' parsing; needs_sig e' un valore del piano, non un'aggregazione ricalcolata alla patch
- [ ] #4 La nota su un errore in pass 2 nomina la regola quando la causa e' per-regola, e nomina lo slot quando la causa e' davvero dello slot (un setattr rifiutato dal container)
- [ ] #5 Un test copre l'attribuzione: una regola su uno slot condiviso con altre due produce una nota che nomina lei e non le altre
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Falsification round (2026-09-27, branch work/task112-plan-attribution, since reverted to master state): the prescribed fix, moving parse_target_spec and the pragma/param test into __init__'s per-rule except, was implemented and killed three contract tests, each load-bearing. (1) Reading rule.action during construction fires before the hook and the manifest exist: the reentrancy test (an action property that calls force_patch_module during its read) hit 'NoneType has no attribute force_patch_module' because patcher attributes are not yet set. (2) The hostile-action fixture's own docstring states the contract: planning reads when and fire, resolution reads module and symbol, and the dispatcher build is the FIRST step that reads action; reading action in pass 1 resolution made the wrap never install, so the rollback tests' target state (an earlier slot already wrapped when a later rule fails) became unreachable and _refusal_notes came back empty. (3) A fallback move of the parse to pass 1 kept test (2) failing for the same reason: pass 1 must complete for every rule before any wrap exists, so any action read there precedes all wrapping. Conclusion recorded: the action-read placement is a documented, tested contract, and the mis-attribution symptom it protects against is bounded by the fact that parse_target_spec never raises (a malformed target returns None plus a reason and simply means no param binding, silently, at BOTH doors' bind time). The per-rule attribution goal for genuinely raising per-rule work was already narrowed by tonight's TASK-110/TASK-130 rounds (the state seed and the event split consume flags, not parses). The branch carries no diff against master and will be discarded; the task closes falsified rather than shipped.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed 2026-09-27 as falsified by implementation attempt. The prescribed fix (move parse_target_spec and the pragma/param test into __init__'s per-rule except) was implemented on branch work/task112-plan-attribution and reverted after three load-bearing contract tests failed: the reentrancy contract (action properties that call force_patch_module during their read fire before the hook and manifest exist), the hostile-action contract (the dispatcher build is the FIRST action read; reading action in resolution made the rollback tests' target state unreachable), and the falsification note that pass 1 completes before any wrap exists, so any action read there precedes all wrapping. The symptom the task targets is bounded in practice: parse_target_spec never raises, so a malformed target silently means no param binding at bind time rather than producing a mis-attributed error, and the genuinely raising per-rule work at bind was already narrowed by TASK-110 and TASK-130. Full falsification evidence in the implementation notes.
<!-- SECTION:FINAL_SUMMARY:END -->
