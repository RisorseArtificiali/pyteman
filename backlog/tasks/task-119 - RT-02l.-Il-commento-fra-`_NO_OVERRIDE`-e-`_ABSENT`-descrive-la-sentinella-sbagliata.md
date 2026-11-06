---
id: TASK-119
title: >-
  RT-02l. Il commento fra `_NO_OVERRIDE` e `_ABSENT` descrive la sentinella
  sbagliata
status: Done
assignee: []
created_date: '2026-09-17 03:43'
updated_date: '2026-11-06 20:02'
labels:
  - rt-02
  - patcher
  - cleanup
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
In testa a patcher.py il commento che spiega una delle due sentinelle si trova fra `_NO_OVERRIDE` e `_ABSENT`, quindi si legge come se riguardasse la seconda mentre descrive la prima. Le due sentinelle fanno cose diverse e vicine fra loro, che e' la situazione in cui un commento fuori posto costa di piu'.

Spostamento di due righe, nessun cambiamento di comportamento.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Il commento sta sopra la sentinella che descrive
- [x] #2 Nessuna delle due sentinelle resta senza la spiegazione che aveva
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #28. Added lines already present on master per PR: #28 0/3=0%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Merged as PR #217, squash 8f61fa4, supersedes #28 (closed with a pointer). Each sentinel now carries its own comment directly above it: _NO_OVERRIDE for the return-value channel (a rule that legitimately returns None), _ABSENT for the attribute channel (an attribute whose value is None). The old combined comment implied both sentinels faced both confusions; the reviewers proved the channels never cross, so the split loses no true information. Both comments are self-contained declarative sentences: a code-review round on the first candidate found its "same reason" anaphora recreated the position-dependent ambiguity the task exists to fix, and the merged wording fixed that before the PR was opened. Gates: battery on 3.13.15 at the exact artifact (candidate-1esz_2hc, 1570 passed, 3 skips declared), /simplify 3/3 CLEAN, /code-review high one finding fixed pre-merge, independent APPROVED at 9ce00a9 with AST-identity and site-by-site channel verification, CI 7/7.
<!-- SECTION:FINAL_SUMMARY:END -->
