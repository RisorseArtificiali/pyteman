---
id: TASK-206
title: 'Extract _column_mismatch helper in runner matrix.py (PR #50)'
status: Done
assignee: []
created_date: '2026-11-06 17:57'
updated_date: '2026-11-08 11:50'
labels:
  - pr-reconciliation
dependencies: []
references:
  - 'https://github.com/RisorseArtificiali/pyteman/pull/50'
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR #50 (open, CONFLICTING, presence 0%) extracts a _column_mismatch helper in runner/matrix.py to consolidate the repeated column-validation error construction. Overlap check needed against merged #203/#205 (runner cell-id and report naming work) before revival.
<!-- SECTION:DESCRIPTION:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by direct push 9dca1b5 on master (base abe62ab); PR #50 closed with a pointer. _column_mismatch(actual, expected) renders the column-set mismatch tail for the two validation refusals (pre-provenance migration and attempts table), seated immediately before _migrate_v1_to_v2 with a docstring stating the shape directly ("; unexpected [...]" before "; missing [...]", each arm omitted when its set is empty). The overlap the task flagged materialized as a merge conflict against master's derived fingerprint/Windows-naming constants and was resolved in master's favour. Byte-identity of both rendered refusals was proven mechanically by two independent verifiers across six mismatch shapes (unknown-only, missing-only, both, at both sites), driving master and candidate modules side by side. The chain's strongest find: the tail was pinned by nothing (the skeptic's full-suite mutation runs proved an arm swap and a dropped tail both shipped 1603 green), so both refusal tests now pin the tail bytes, with the code-review bite-check (arm swap) reddening exactly those two tests. Gate chain: /simplify (two minors applied: f-string form, better seat), /code-review high over two rounds with a clean final verdict, skeptic 3 CONFIRMED plus the productive refutation, batteries green at every shipping sha (last: 1606 collected, 1603 passed, 3 declared skips).
<!-- SECTION:FINAL_SUMMARY:END -->
