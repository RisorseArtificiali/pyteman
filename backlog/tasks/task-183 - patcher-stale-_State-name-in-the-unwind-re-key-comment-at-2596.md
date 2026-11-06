---
id: TASK-183
title: 'patcher: stale _State name in the unwind re-key comment at 2596'
status: Done
assignee: []
created_date: '2026-09-27 07:10'
updated_date: '2026-09-27 08:48'
labels:
  - cleanup
dependencies: []
references:
  - src/pyteman/patcher.py
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From the TASK-129 final review (work/task129-named-specs). The comment above the unwind re-key loop in src/pyteman/patcher.py (line 2596) says "added specs carry a fresh _State at index 3 where a plan entry carries the described identity pending() reports". No class or factory named _State exists anywhere in the codebase; the fourth field of a bound spec is the plain dict returned by _new_state() at line 769 (fires, seen_keys, lock). The name is presumably a historical holdover. Pre-existing, not introduced or worsened by TASK-129 (index 3 is still literally true under the namedtuples), which is why it was not fixed in that task. Minimal fix when the file is next touched: s/_State/state dict/ in that comment.
<!-- SECTION:DESCRIPTION:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Merged as b9c5c8b via PR #159 (head 60d2cce, comment-only, gate-exempt). The unwind re-key comment now says 'state dict at index 3' instead of the _State class that never existed. Battery check clean, 1268 passed 2 skipped; PR CI green; master CI green.
<!-- SECTION:FINAL_SUMMARY:END -->
