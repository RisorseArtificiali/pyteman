---
id: TASK-216
title: Hoist the shared alias-road subprocess prefix in test_coroutine_entry.py
status: Done
assignee: []
created_date: '2026-11-08 08:43'
updated_date: '2026-11-20 19:43'
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

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Landed on master as a84c78c (2026-11-20, set 83). The four copies of the alias-road subprocess prefix (import coropkg.submod, import aliaspkg, alias assignment, import sys) in tests/test_coroutine_entry.py, plus the fifth near-copy of the same shape for the eager sync road that the code review found, now derive from one parameterized builder, _alias_road(pkg, leaf, alias), placed after _split_refusal (the first draft's constant had spliced _split_refusal's documenting comment from its function; three review angles converged on the placement). The four extend-door tests compose the derived _ALIAS_ROAD constant; the eager road calls the builder directly, reconciling the code review's incident-class argument (a shape change missed on one road reproduces the child-side AttributeError the task cites) with the altitude angle's N=1 objection (a flat constant would erase the roads' distinction): the shape is single-sourced, the package and attribute names and the force-or-bind tails stay at the call sites because they are each test's semantics, and the builder's comment states exactly that division rather than overclaiming single-edit coverage of the registry key or force signature (which live in the tails). Verified: all 20 tests assert exact child stdout so the refactor is behavior-identical by the suite, and a mutation of the shape (sys to os in the builder) flips 6 tests across both roads, proving one edit now serves every road. Gates: /simplify (skill form; reuse and efficiency CLEAN, the placement and comment findings applied), /code-review high (both findings applied: the eager road via the builder, the placement; the reviewer verified byte-level equivalence statically through the classifier outage), battery tzrn7ye5 green (floor 1627).
<!-- SECTION:FINAL_SUMMARY:END -->
