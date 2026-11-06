---
id: TASK-180
title: >-
  docs/rules.md stale closing paragraph contradicts the shipped entry-on-
  coroutine support (TASK-178 tail)
status: Done
assignee: []
created_date: '2026-09-27 00:15'
updated_date: '2026-09-27 00:04'
labels:
  - review-followup
  - task-178
  - docs
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From the TASK-178 post-verdict review. The rewritten "Points whose work does
not happen during the call" section head (docs/rules.md:626-650) documents the
new entry-on-coroutine support, but the section's closing paragraph
(docs/rules.md around line 830, unchanged by 8b2562e) still says instrumenting
these points is a separate future feature that "needs the dispatcher to await
... on your behalf while preserving cancellation and throw()", which is exactly
what the shipped wrapper now does. An operator reading the section tail
concludes the feature does not exist.

While there: the same pass should reword the patcher.py:2199 comment ("the
attribute holds OUR dispatcher, an ordinary synchronous function") which is
false since 8b2562e can put an async-def dispatcher on the slot.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The closing paragraph no longer contradicts the section head; the future-feature framing is updated or removed
- [x] #2 The 2199 comment matches the two dispatcher kinds
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Merged in the same commit as TASK-179 (97c71ce via PR #145). The closing paragraph now states the split: entry-on-coroutine is the supported half whose wrapper awaits on your behalf, exit timing and generators remain separate and would need await or iterate with cancellation and throw() fidelity. The 2199-area comment names both dispatcher kinds (plain def and async def). Documentation-only plus one comment within a diff that also passed the full gate cycle; the docs fence is tied to the builder by test_documented_split_refusal check in tests/test_docs_rules.py.
<!-- SECTION:FINAL_SUMMARY:END -->
