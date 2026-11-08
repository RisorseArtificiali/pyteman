---
id: TASK-209
title: 'Pin split choice in report body_rows (PR #66)'
status: Done
assignee: []
created_date: '2026-11-06 17:57'
updated_date: '2026-11-08 12:38'
labels:
  - pr-reconciliation
dependencies: []
references:
  - 'https://github.com/RisorseArtificiali/pyteman/pull/66'
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR #66 (open, CONFLICTING, presence 10%) pins the split choice in body_rows so a value containing both newline forms cannot depend on which split runs first. Overlap check against merged #206 (TASK-68 whitespace contract) required: that merge may already state and pin the contract this test wanted.
<!-- SECTION:DESCRIPTION:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by direct push e6b99a2 on master (base bcf8d92); PR #66 closed with a pointer. The split choice both body_rows copies document (split on "\n" because splitlines also breaks on characters markdown does not count as line endings) is now pinned behaviourally in BOTH copies: the escaping file's test stores one character per row from the module constant SPLITLINES_EXTRAS and asserts one row per result, and tests/test_report.py carries a mirror over the same imported constant storing the characters in the signature column the report actually renders. The non-vacuity guard compares splitlines and split counts on the rstripped body, curing the raw-text form's trailing-empty artifact that cancels the disagreement at exactly one split character; the property is verified empirically at k=5, k=1 (the case both earlier forms failed spuriously) and k=0 (fails on the intended message). Both pins fail loudly on a per-file body_rows switch to splitlines (skeptic mutation probes, "assert 10 == 5"). The overlap check the task required found TASK-68's whitespace contract pins different semantics, so the split choice had been prose-only. Docstrings claim no completeness for the five-character list. Gate chain: /simplify (findings applied: escapes, shared constant, mirror), /code-review high over three rounds (six findings closed; the round-2 disposition of the guard falsely claimed a property the code lacked, caught by the reviewer's arithmetic, retracted and replaced by the rstrip cure it recommended), skeptic 4/4 CONFIRMED with per-file mutations and raw-character byte checks, battery green (wi1fzf5c: 1608 collected, 1605 passed, 3 declared skips).
<!-- SECTION:FINAL_SUMMARY:END -->
