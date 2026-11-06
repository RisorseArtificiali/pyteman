---
id: TASK-155
title: Exception pair rendering is spelled out in four places
status: Done
assignee: []
created_date: '2026-09-17 11:13'
updated_date: '2026-09-25 13:28'
labels:
  - audit-2026-09-16
  - opus-5
  - reuse-gate
  - task-3-followup
dependencies: []
references:
  - 'src/pyteman/patcher.py:640-641'
  - 'src/pyteman/patcher.py:456'
  - 'src/pyteman/patcher.py:1773'
  - 'src/pyteman/sitecustomize.py:138'
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Reuse gate on TASK-3, 2026-09-17.

src/pyteman/patcher.py lines 640-641 render an exception as _typename(exc) + ": " + _text(exc). That is the fourth copy of the idiom: patcher.py line 456, patcher.py line 1773, and sitecustomize.py line 138 are the others. There is no named helper being bypassed, so this is a repeated idiom rather than a missed call.

Filed because four is the count at which this codebase has historically extracted one. _typename, _owner_name, _text and _rule_id all exist for that reason. If exception rendering ever has to carry notes the way sitecustomize._describe does, four sites have to be found first.

Lowest priority of the reuse batch. The gate itself rated it low and flagged it only on the count.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Esiste un solo punto che rende la coppia tipo e testo di un'eccezione, e i quattro siti attuali lo chiamano.
- [x] #2 L'output prodotto resta identico in tutti e quattro i siti; nessun test che cita quei messaggi cambia.
- [x] #3 L'helper sta dove gli altri helper di rendering gia' stanno, accanto a _typename e _text, non in un modulo nuovo.
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
PR #48, commit e2d9966 on branch `work/exc-pair-helper`. Extracted `_exc_pair(exc)` in both patcher.py and sitecustomize.py (duplicate by design; sitecustomize cannot import from patcher). Replaced all four inline `_typename(exc) + ": " + _text(exc)` sites. Helper placed next to `_text`, following the existing convention. Full suite: 1190 passed, 2 skipped; output unchanged.
<!-- SECTION:FINAL_SUMMARY:END -->
