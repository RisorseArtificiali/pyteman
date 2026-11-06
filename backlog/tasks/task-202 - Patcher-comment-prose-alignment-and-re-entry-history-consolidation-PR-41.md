---
id: TASK-202
title: 'Patcher comment prose alignment and re-entry history consolidation (PR #41)'
status: To Do
assignee: []
created_date: '2026-11-06 17:57'
updated_date: '2026-11-06 18:21'
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
