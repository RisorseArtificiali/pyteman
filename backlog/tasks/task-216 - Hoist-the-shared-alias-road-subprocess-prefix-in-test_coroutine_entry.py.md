---
id: TASK-216
title: Hoist the shared alias-road subprocess prefix in test_coroutine_entry.py
status: To Do
assignee: []
created_date: '2026-11-08 08:43'
labels:
  - tests
  - cleanup
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From the TASK-150 review chain (code-review high, 2026-11-08): tests/test_coroutine_entry.py now carries four copies of the same subprocess road prefix (import coropkg / import aliaspkg / alias assignment / import sys / force_patch_module('aliaspkg')) at the exit-alias, merge-alias, async-sleep-extension and judges-the-original tests. A change to the road (fixture package rename, force_patch_module signature, sys._pyteman registry key) needs four synchronized edits, and a missed one fails as a child-side AttributeError in exactly one test. The TASK-150 simplify pass judged the inline prefix the file's established idiom and did not flag it; the code-review pass flagged the fourth copy the new test added. Collapsing all four into a small builder, the way the atomic suite shares crule/MODNAME helpers, is a mechanical refactor that belongs to the whole file rather than to any single delivery, which is why it was not folded into the TASK-150 delta.
<!-- SECTION:DESCRIPTION:END -->
