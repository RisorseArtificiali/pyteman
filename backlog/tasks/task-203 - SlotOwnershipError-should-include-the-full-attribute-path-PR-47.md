---
id: TASK-203
title: 'SlotOwnershipError should include the full attribute path (PR #47)'
status: Done
assignee: []
created_date: '2026-11-06 17:57'
updated_date: '2026-11-08 14:03'
labels:
  - pr-reconciliation
dependencies: []
references:
  - 'https://github.com/RisorseArtificiali/pyteman/pull/47'
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR #47 (open, CONFLICTING, presence 30%) makes SlotOwnershipError carry the full attribute path instead of the bare final attribute, so multi-segment walks name the exact point of loss. Revive through the standard gate chain or close if an intervening merge already names the path.
<!-- SECTION:DESCRIPTION:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by direct push d06a14a on master (base 84921c6); PR #47 closed with a pointer. Every refusal that names a slot now names it as its first rule spelled it: _slot_target(modname, slot) joins the module to slot.symbol, a plain string captured at walk time from the split that already succeeded (".".join(parts), byte-identical to rule.symbol) and stored on the _Slot beside its specs, so the six raise expressions (four SlotOwnershipError, the not-callable UnsupportedTargetError, the short SuspendableTargetError) read no rule field live; the review proved the live read could let a symbol that starts raising between the walk loop and the refusal loop replace the diagnostic with its own failure. The PR's three sites extended to all six because the simplify census found the same leaf-only defect in the siblings; single-segment rules render byte-identically (verified master-vs-candidate by the skeptic). Three deterministic multi-segment pins hold the property (ownership via a class attribute walk exercising the descriptor read, matching the two-classes rationale; not-callable via an instance container, the only shape that reaches the pass-2 gate; suspendable via a walked generator function); the three racy reservation-window sites keep phrase pins and share the identical helper expression. The three shared-text refusal helpers still naming the leaf (refuse_unsupported, async_sleep, coroutine_exit, with the extend door threading bare name) are filed as TASK-219. Gate chain: /simplify (three clean angles, the altitude finding filed), /code-review high over two rounds clean (F1 capture-at-walk, F2 pins, F3 guarded finally, F4 class fixture), skeptic 5/5 CONFIRMED at the prior hash (byte renders both sides, both leaf-revert mutations redden the walk test, no master test pins converted refusals leaf-only on multi-segment symbols) with the final delta confined to reviewer-verified findings, battery green (27is0f8p: 1618 collected, 1615 passed, 3 declared skips).
<!-- SECTION:FINAL_SUMMARY:END -->
