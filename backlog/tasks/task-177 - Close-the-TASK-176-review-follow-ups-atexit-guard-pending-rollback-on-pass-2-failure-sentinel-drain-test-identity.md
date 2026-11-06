---
id: TASK-177
title: >-
  Close the TASK-176 review follow-ups: atexit guard, pending rollback on pass-2
  failure, sentinel, drain, test identity
status: Done
assignee:
  - pyteman-coordinator
created_date: '2026-09-26 14:03'
updated_date: '2026-09-26 22:41'
labels:
  - patcher
  - follow-up
  - confirmed
dependencies: []
references:
  - /home/pantinor/pyteman-evidence/task176-review-r2/FINDINGS-AND-VERDICT.md
  - src/pyteman/patcher.py
  - src/pyteman/sitecustomize.py
  - tests/test_lazy_walk.py
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Non-blocking findings from the TASK-176 independent review (task176-review-r2/FINDINGS-AND-VERDICT.md, CR-1..CR-6, all dispositioned accepted/informational) plus the coordinator's delta round. CR-1: sitecustomize.py:218 getattr(sys, "_pyteman", {}).get("patcher") sits outside the try; a non-dict sys._pyteman prints an ignored-exception traceback at exit. CR-2: patcher.py pending pop happens before pass 2; a pass-2 failure (unsupported target, hostile setattr) rolls back wraps but not the pending entry, so the rule is in neither applied nor pending and the exit report omits it (reviewer reproduced with a FrozenMeta fixture). The coordinator's delta moved the pop after the leaf hasattr gate, which closes the leaf-typo hole but leaves this pass-2 window open, recorded in the new comment at the pop site. CR-5: the pending walk uses getattr(..., None) where pass 2 uses the _ABSENT sentinel, misclassifying a real None attribute as an absent segment; reviewer reproduced with nonepkg.backend = None. CR-4: the hook's pending-drain block is unreachable by construction now that prefix processing runs first (any pending key starts with a rule module, which is in _rule_modules); keep as documented safety net or remove. CR-6: tests/test_lazy_walk.py:250 uses a substring check where an exact applied identity is unambiguous. Evidence: break_tests/ in task176-review-r2 and follow-up-issues.md there.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Atexit handler in sitecustomize reads sys._pyteman defensively inside its try block; a non-dict assignment produces no traceback.
- [x] #2 A walk that succeeds but fails in pass 2 either restores or re-registers its pending entry, so the exit report still names the rule.
- [x] #3 The None-vs-_ABSENT sentinel mismatch in the pending walk is resolved or explicitly justified next to the code, with a test pinning the chosen behavior.
- [x] #4 The unreachable pending-drain block is either removed or carries the construction argument as a comment, with the reviewer's reasoning preserved.
- [x] #5 The substring assertion in test_lazy_walk is tightened to an exact applied identity.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Delta-round additions from the coordinator code-review of the total-pending change: (1) the pass-2 silent _ABSENT skip paths (slot re-read finds the attribute gone, ~2089 live and ~2229 settled in the current tree) also drop an already-popped entry without an exception, so a PEP 562 __getattr__ that deletes another rule's segment during the same _patch window leaves that rule fully silent; same restore-or-re-register fix as CR-2 covers it. (2) The pass-2 failure disposition (comment at the pop site) explicitly includes the swallowed-import pattern: a workload wrapping `import pkg` in try/except sees neither the raised refusal nor any exit report for the dropped rule. (3) Efficiency: with total seeding the hook's matched scan is O(pending) per import including None-keyed entries that can never match, and a pkey-matching never-landing rule re-runs _patch on every import statement of that name (drain retry plus prefix loop, 2x the already-accepted CR-3 prefix cost); the proper fix is a pkey-to-ordinals re-arm index consulted by a single dict lookup instead of scanning _pending. Accepted for now with the CR-3 precedent. (4) Fixed in this round, not deferred: the unconditional re-key could resurrect a landed rule into a false 'never landed' report after attribute deletion plus a later prefixed import; the re-key is now guarded by pending membership, with regression test test_landed_rule_not_resurrected_by_later_miss.

Code-review high (2026-09-27, in-session, final delta): verdict FINDINGS, nothing blocking. Should-fix applied: the pending-drain block's 'unreachable by construction' comment stated false premises. The block is reachable and load-bearing: a pending key can name a module outside the rule's own tree (mypkg re-exports other.util; rule mypkg.util.fn.work keys itself on other.util.fn; the prefix loop patches nothing on that import), and the drain scan is then the only retry. Reproduced independently by both the reviewer and the coordinator; pinned by test_foreign_module_key_rearms_through_the_drain_scan. Consequence for the deferred re-arm index: it must answer non-prefix keys, not only rule-module prefixes. For prefix-shaped keys the scan is merely redundant (retry already driven by the prefix loop), which the repo's own leaf-typo retry test walks.

Code-review notes, report-only, no action for this merge: (3a) two _patch calls for one module can land the same ordinal on two different slots (path changed mid-window); the failing call's setdefault then re-adds an ordinal the other call's dispatcher still serves, so the exit report can name a firing rule. (3b) a hostile __setattr__ that stores the dispatcher and then raises leaves the wrap live (stranded ledger entry) while the ordinal returns to pending. Both sit inside the alias-race class the file documents as open (TASK-123); the old code lost these rules silently instead of reporting.

Code-review note 4: uninstall's _pending.clear() can be repopulated by an in-flight _patch on another thread whose handler setdefault runs after the clear, so the exit report may name rules after an explicit uninstall. Single-threaded this is unreachable (hook deactivated before the clear, and uninstall's own restore is guarded); cross-thread _patch is documented unsynchronised. Old code dropped these silently. Note 2: the atexit exact-type guard deliberately loses dict subclasses of sys._pyteman, consistent with the module's type(x) is convention. Note 6: the white-box _pending pkey pin breaks by design under the deferred re-arm index; acknowledged in the test comment. Note 5 (docs overclaim on None as last intermediate segment) fixed in this change.

Independent review (2026-09-27, fresh context, task177impl/review/FINDINGS-AND-VERDICT.md): APPROVED at 3982763. 15 invariants traced, 0 broken; 6 mutations (M1-M6) all killed by the new tests; re-entrancy probed in both directions. Three non-blocking observations: F1 the refused-unwind corner names a rule 'never landed' while its dispatcher still fires (probe task177rev2-probe3; loud, _disclose rides the exception, conservative direction; wording only); F2 exact-type atexit guard deliberately drops dict subclasses (behavioral narrowing, accepted convention); F3 pre-existing: a rule published by a nested successful call can stop firing when the outer unwind removes the dispatcher it extended (applied-but-not-firing-not-pending; exists identically on base, inside the documented best-effort unwind caveat at patcher.py:1951-1956; candidate to fold into TASK-123's alias-race class).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Merged as ad0a8ee via PR #142 (squash of the rebased 928aa9d; rebase onto #141 proven content-identical, 451 changed lines byte-equal, re-verified mechanically by the post-merge code-reviewer pass), master CI green, local master fast-forwarded. Review APPROVED at 3982763 (15 invariants, 6 mutations killed, re-entrancy probed both directions); /simplify 4-angle findings applied; code-review high should-fix applied with coordinator-verified falsification of the drain comment; final belt on the merged bytes CLEAN, #141 work verified intact; remaining observations filed in these notes.
<!-- SECTION:FINAL_SUMMARY:END -->
