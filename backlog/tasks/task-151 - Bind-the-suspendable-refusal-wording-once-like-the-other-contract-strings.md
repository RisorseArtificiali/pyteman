---
id: TASK-151
title: 'Bind the suspendable refusal wording once, like the other contract strings'
status: To Do
assignee: []
created_date: '2026-09-17 11:11'
updated_date: '2026-09-28 18:16'
labels:
  - audit-2026-09-16
  - opus-5
  - reuse-gate
  - task-3-followup
dependencies: []
references:
  - 'src/pyteman/patcher.py:1161-1165'
  - 'src/pyteman/patcher.py:403-422'
  - 'docs/rules.md:545-547'
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Reuse gate on TASK-3, 2026-09-17, against patcher.py sha256 1a4d1cd4e8513bd80cde328eded77421bed9093b3c2edaa921d7e0363a3fe08c.

The SuspendableTargetError message tail is built inline at the raise site in src/pyteman/patcher.py around lines 1161-1165: " is " + reason + ", so entry and exit cannot be timed on it; refused rather than installed for ".

patcher.py already states the opposite policy twice and provides the mechanism. Line 403 above _ROLLBACK says "The wording is a contract: docs/rules.md quotes it and the tests match on it." Line 422 in _disclose says the same and adds "two copies would be two things to keep in step with three readers". _RETRY_AFTER_UNINSTALL at line 414 is the bound constant, used by the sibling SlotOwnershipError raise at line 1132. sitecustomize.py line 139 binds `lost` as a constant for a string with a single call site, on the reader count alone.

This wording has exactly the three readers those comments cite: docs/rules.md lines 545-547 quotes it verbatim, tests/test_activation_atomic.py line 4175 matches the reason half, tests/test_activation_suspendable_startup.py line 107 matches "is a coroutine function".

Cost: a reword at the raise site leaves the docs example wrong and only one of the two test assertions catches it, because the atomic test matches `reason` alone and survives a reword of the tail.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Il testo di coda del messaggio SuspendableTargetError e' legato a una costante di modulo accanto a _RETRY_AFTER_UNINSTALL, e il sito di raise la usa invece di costruirlo inline.
- [ ] #2 Almeno un test fallisce se la coda viene riscritta senza aggiornare docs/rules.md, cioe' l'asserzione non si limita alla meta' reason.
- [ ] #3 Nessun cambiamento al testo prodotto: l'output osservato dai tre lettori esistenti resta byte-identico.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #35. Added lines already present on master per PR: #35 0/6=0%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Extracted SuspendableTargetError message tail to `_SUSPENDABLE_TAIL` constant at patcher.py:425, next to the three existing contract-string constants. Raise site at line 2135 uses it. Added tail assertion in test_activation_atomic.py:4748 so a reword without updating docs/rules.md breaks a test. Branch `work/suspendable-tail-constant`, commit 86e3bb8, PR#35. Full suite: 1174 passed, 2 skipped.
<!-- SECTION:FINAL_SUMMARY:END -->
