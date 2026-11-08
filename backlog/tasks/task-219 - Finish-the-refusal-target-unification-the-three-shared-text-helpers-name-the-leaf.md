---
id: TASK-219
title: >-
  Finish the refusal-target unification: the three shared-text helpers name the
  leaf
status: To Do
assignee: []
created_date: '2026-11-08 13:18'
labels:
  - patcher
  - refactor
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From the TASK-203 review chain (simplify altitude, 2026-11-08): TASK-203's _slot_target unification covered the six slot-naming refusals built inline in the _patch loop, but three shared-text refusal helpers still build the target name from the bare leaf, called from the same loop and from the extend door: _refuse_unsupported (patcher.py ~1448, called at ~2656 with the slot in hand and at ~2591 in pass 1 where no slot exists yet but the rule's symbol is a full spelling), _async_sleep_refusal (~527, called at ~2769 and at the extend door ~3395), _coroutine_exit_refusal (~1460, called at ~2792 and at the extend door ~3379, the one text docs/rules.md quotes verbatim at line 751). Cost: a rule reaching mod.Inner.fn gets the diagnosable full spelling from the ownership, not-callable and suspendable refusals but only "fn" from the unsupported-shape, async-sleep and coroutine-exit refusals on the same target. Remedy per the review: change the two shared-text helpers to take the already-built target string (or the slot), pass _slot_target at the three loop call sites, thread the target through _extend_dispatcher to the two extend-door sites, and pass the rule's own symbol at the pass-1 site. Constraint: both shared texts must stay identical across the install and extend doors (their docstrings say docs/rules.md holds them to that), so the docs contract test travels with this change.
<!-- SECTION:DESCRIPTION:END -->
