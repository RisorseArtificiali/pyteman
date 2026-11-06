---
id: TASK-141
title: >-
  The preflight id rationale overstates what the gate protects, in the patcher
  comment and in docs/rules.md
status: To Do
assignee: []
created_date: '2026-09-17 09:43'
updated_date: '2026-09-28 18:16'
labels:
  - patcher
  - docs
  - accuracy
  - review-2026-09-17
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Two separate factual defects in prose I wrote for TASK-2, both found by the /simplify gate on the final snapshot (2026-09-17) and both left unfixed because the approving reviewer's instruction was no code change after approval. Filed rather than applied. Neither changes behaviour; both make a reader who works forward from the code believe something false.

DEFECT 1, the reads are conditional and the prose says they are not.

patcher.py:722-724 states that "firing.py and actions.py read `rule.id` raw, inside the instrumented callable, to key the firing record and the outcome dedup". docs/rules.md:501-505 makes the same claim in prose: "The firing record and the outcome dedup read `id` directly, inside the instrumented call, where no degradation applies".

Both reads sit behind a log guard. actions.py:18 is `if log is not None:` before `log.record(rule, ctx, note=str(rule.action))`, and `_note` returns early at actions.py:76-77 with `if log is None: / return` before it builds `key = (rule.id, message)` at actions.py:81. A run with no firing log configured never reaches either read, so the run-time hazard the paragraph describes does not exist for that run. The refusal is still right, on the grounds the reviewer settled (unique preflight ids are the contract for the programmatic door), but the justification as written claims more coverage than the code has.

DEFECT 2, the gate comment claims an invariant the rest of the codebase documents as false.

patcher.py:726-730 says "Refusing here is what protects those two reads, and preflight is the only place that can do it without a guard at each one". Both halves are wrong. It does not protect those reads: TASK-138 carries a verified end-to-end reproduction where a rule that passed the gate with id="good" was rebound to None afterwards and wrote {"rule": null} to the firing log. And preflight is not the only place: snapshotting the id into the plan does it without a guard at each read, and does it durably, which is the option TASK-138's own AC #1 lists as the alternative.

The rest of the codebase gets this right. The `_Composite` docstring at patcher.py:544-554 says a preflight check can only speak for the moment it runs, and docs/rules.md:510-517 says the same. The gate comment is the single place that overstates, 180 lines from the docstring that corrects it.

DEFECT 3, lower priority, same family.

docs/rules.md:495 opens "The rest of the contract is enforced through both doors as well, and for the same reason". Under the `### Ids` heading this means the rest of the ID contract, and every sentence after it discusses only `id`, so it is defensible in context. Read cold it claims parity on the whole rule contract, which is false: only `id` is checked through both doors, and every other field reaching the programmatic door is whatever the caller put there. The planning paragraph near docs/rules.md:41 states that honestly, so the two paragraphs pull against each other. One word settles it: "the rest of the id contract".

CITATION CORRECTION, 2026-09-17. This task originally cited the `_note` early return as actions.py:78. Verified by reading the file: the guard is at 76-77 and line 78 is `noted = getattr(log, "_pyteman_noted", None)`. Corrected above and in the patcher comment that carried the same citation. Nothing else in the finding changes.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The patcher gate comment and docs/rules.md both state that the raw firing-time reads happen only when a firing log is configured, or drop the conditional framing and rest the refusal on the identity contract instead
- [ ] #2 The claim that refusing in preflight protects the firing-time reads is qualified or removed, and points at TASK-138 for the hole it leaves open
- [ ] #3 The claim that preflight is the only place that can protect those reads is removed, since snapshotting the id into the plan is the tracked alternative
- [ ] #4 docs/rules.md:495 says 'the rest of the id contract' so it cannot be read as claiming both-door parity for the whole rule contract
- [ ] #5 No new claim in the replacement prose is stronger than what the code does, checked by reading the guard at actions.py:18 and actions.py:76
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #43. Added lines already present on master per PR: #43 0/5=0%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Commit 4bce36f on branch work/preflight-id-rationale, PR #43.\n\nAC#1: Already satisfied in the current code; patcher.py:1747-1752 and docs/rules.md:593-595 both acknowledge the firing-log guards.\nAC#2: Replaced \"Refusing here is what protects those two reads\" with \"Refusing here catches a bad id while nothing has been patched; it cannot follow a rebind after construction (TASK-138), so it speaks for the moment it runs, not for every firing.\"\nAC#3: Removed the claim that preflight is \"the only place that can do it without a guard at each one\"; the replacement acknowledges the gap.\nAC#4: docs/rules.md:584 now reads \"The rest of the id contract\" instead of \"The rest of the contract\".\nAC#5: Verified guards at actions.py:102 (if log is not None) and actions.py:306 (if log is None: return). No new claim in the replacement is stronger than what the code does.\n\nGate evidence: /simplify 3 agents clean; code-review launched (comment-only change); 1190 passed 2 skipped; ruff clean.
<!-- SECTION:FINAL_SUMMARY:END -->
