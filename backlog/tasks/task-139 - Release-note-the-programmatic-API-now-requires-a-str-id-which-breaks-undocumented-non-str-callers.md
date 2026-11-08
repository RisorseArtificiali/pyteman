---
id: TASK-139
title: >-
  Release note: the programmatic API now requires a str id, which breaks
  undocumented non-str callers
status: Done
assignee: []
created_date: '2026-09-17 08:57'
updated_date: '2026-11-08 20:22'
labels:
  - docs
  - release
  - patcher
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The preflight gate in `Patcher.__init__` refuses an `id` that is not a `str`. For anything documented or in-repo this is not a breaking change: docs/rules.md already stated the contract as a non-empty string, unique in the ruleset, and every in-repo construction site passes a str (`load_rules` at rules.py:355, sitecustomize.py:210 which goes through `load_rules`, and both test `make_rule` helpers).

The honest caveat, raised by the high-effort review of the gate, is that an undocumented external caller using a hashable non-str id did work end to end before. `id=5` survived the whole path: `json.dumps` accepts an int for the firing record, and `actions.py:81` only needs hashability for the outcome dedup key. Such a caller now fails at construction with `RuleError: id must be a string, got int`.

That trade is worth taking, because the gate closes a latent crash in the user's workload and the only published contract already said str. It is not worth shipping silently.

No code change is expected from this task. It exists so the caveat reaches the release notes instead of being remembered.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The release notes for the version carrying the preflight id gate state that `Patcher` now refuses a non-str `id` at construction, and name the error text so a caller hitting it can search for it.
- [ ] #2 The note says what previously worked, specifically a hashable non-str id such as `id=5`, so an affected caller recognises their own case.
- [ ] #3 The note points at the documented contract in docs/rules.md rather than restating it.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #39. Added lines already present on master per PR: #39 0/8=0% absentfiles=1. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closure restored 2026-11-08 (tracker repair): the day-3 Done marker was lost to a working-tree revert; the work had landed. Landed by direct push 5159497 (superseded PR #39 closed with a pointer). Full chain in the durable handoff and TASK-191 notes.
<!-- SECTION:FINAL_SUMMARY:END -->
