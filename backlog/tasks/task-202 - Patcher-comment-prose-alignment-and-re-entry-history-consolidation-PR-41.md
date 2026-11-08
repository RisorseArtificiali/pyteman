---
id: TASK-202
title: 'Patcher comment prose alignment and re-entry history consolidation (PR #41)'
status: Done
assignee: []
created_date: '2026-11-06 17:57'
updated_date: '2026-11-08 15:56'
labels:
  - pr-reconciliation
dependencies: []
references:
  - 'https://github.com/RisorseArtificiali/pyteman/pull/41'
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR #41 (open, CONFLICTING, presence 9%) aligns patcher comment prose with code and consolidates the re-entry history narrative. Supersession check required before revival: merged #195 (TASK-121 set, "derive the re-entry chain once, on the mechanism that remains") and #189 already restructured the re-entry derivation docs; verify what of #41's content survives that design before deciding revive vs close-with-pointer.
<!-- SECTION:DESCRIPTION:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-11-06 supersession check done: NOT superseded. 58 of 64 added lines remain absent from master (README rollback-account prose, docs/rules.md exit-preservation rationale, patcher.py ownership/undo comments incl. the owned-vs-None and data-descriptor distinctions). Merged #189/#195 restructured the re-entry derivation only; this comment-alignment work is still wanted. #41 remains the carrier; revive through the gate chain when its turn comes (presence baseline in ~/pyteman-evidence/stalepr/presence-now.txt).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by direct push c89d1e4 on master (base 26b5b2d); PR #41 closed with a pointer, split per the supersession check: the re-entry history consolidation half was superseded by merged #195's derive-once narrative (the PR documented the inspect-import mechanism TASK-121 removed) and is absent from the delta, verified; the surviving prose-alignment half landed. The _ABSENT sentinel's comment now states what getattr distinguishes and the real constraint (the sentinel must be an object no target program can store into the attribute, which is why None cannot serve), the _owns_name docstring and _undo_one inline comment say the undo-time re-ask runs when the recorded answer was False (true against the gate's short-circuit, confirmed by the skeptic and conceded by the code-review on its own scenario), and the reference doc's degradation paragraph is rewrapped to the house width with content preserved word-for-word (whitespace-normalized diff empty). The README bullet was found already at target wording on master and needed nothing. Gate chain: /simplify (all four angles clean), /code-review high over two rounds clean (its F2 comment-precision finding applied and re-verified; F1 skip conceded; F3 recorded), skeptic 4/4 CONFIRMED, batteries green at every shipping sha (last: 1622 collected, 1619 passed, 3 declared skips).
<!-- SECTION:FINAL_SUMMARY:END -->
