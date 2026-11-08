---
id: TASK-204
title: 'Extract _exc_pair helper for exception rendering in patcher (PR #48)'
status: Done
assignee: []
created_date: '2026-11-06 17:57'
updated_date: '2026-11-08 12:12'
labels:
  - pr-reconciliation
dependencies: []
references:
  - 'https://github.com/RisorseArtificiali/pyteman/pull/48'
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR #48 (open, MERGEABLE, presence 9%) extracts a shared _exc_pair helper for exception rendering in patcher.py. Check overlap with merged #212 (TASK-89: wrapper signature guard is the disjunction of two guards) and #204 (substrate fault naming) before revival; those touched nearby rendering code.
<!-- SECTION:DESCRIPTION:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by direct push bcf8d92 on master (base 9dca1b5); PR #48 closed with a pointer. _exc_pair(exc) renders the "TypeName: message" pair from the two inert renderers, defined once per module beside the _text/_typename twins it composes (the per-module duplication family this codebase maintains deliberately; sitecustomize imports nothing from pyteman, so its copy is mandatory, judged the right depth against moving it to _note.py). Four sites render through it: the _disclose list, _suspendable_reason's unreadable arm (keeping master's kind-label triple), activate's rollback safe_add_note (the pair as one inert part, the join still inside the guard), and sitecustomize's _describe, whose degradation string docs/rules.md quotes. Rendered text byte-identical to master at every site, verified independently. The chain added what the branch lacked: both copies' docstrings cross-reference their twin and the parity mechanism, the parity test drives _exc_pair across the hostile input set, and the composed degradation is pinned in both copies against the Nameless shape ("<unknown type>: <unprintable <unknown type>>", type str). The review's census of six sibling inline spellings outside this extraction's four sites (patcher.py:1377 terminal record, firing.py 163/215/286, actions.py 121/440) is recorded on TASK-200, which owns that consolidation by title. Gate chain: /simplify (REUSE/EFFICIENCY/ALTITUDE clean; two minors applied), /code-review high over three rounds with a clean final verdict, skeptic byte-identity verification at the prior hashes with the final delta confined to prose plus one test leg, battery green (nmi8mp95: 1606 collected, 1603 passed, 3 declared skips).
<!-- SECTION:FINAL_SUMMARY:END -->
