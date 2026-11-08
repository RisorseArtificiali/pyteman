---
id: TASK-96
title: >-
  Derive the reproduction procedures from the corpus instead of parsing them
  back out of the document
status: Done
assignee: []
created_date: '2026-09-16 23:43'
updated_date: '2026-11-08 08:04'
labels:
  - audit-2026-09-16
  - sqlitekit
  - tests
  - docs
  - deferred-from-task-24
milestone: m-3
dependencies:
  - TASK-24
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
tests/test_docs_integrity.py currently reads docs/integrity.md back with a small markdown parser (`_entries`) to recover which sample each reproduction procedure belongs to, and then checks that mapping against the corpus in both directions. The checks are live and correct today, but the dependency runs the wrong way: the document is the source of truth for a fact the corpus already knows, so the test has to understand the section's bullet formatting, its house use of bold, indented sub-steps, and continuation blocks. Three tests exist only to pin that parser (a bolded word inside an entry, an entry rewritten as steps, an unnamed bullet), and none of them is about integrity classification.

Proposed direction: give `Sample` in tests/integrity_corpus.py a `procedure` field holding the reproduction steps next to the text they reproduce, and generate the document section from it rather than parsing it back. The forward and reverse checks then collapse into an identity, the markdown parser and its three tests go away, and a sample can no longer be captured without its procedure because the field sits on the dataclass.

Raised by the altitude review of TASK-24 and deferred deliberately: the current checks are not defective, and rewriting approved TASK-25 structure inside a TASK-24 tranche would be a refactor with no defect behind it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 docs/integrity.md reproduction section is generated from the corpus rather than parsed back by tests
- [x] #2 the markdown-shape tests in test_docs_integrity.py are removed along with the parser they pin
- [x] #3 an observed sample cannot be added without a procedure and a test proves that
- [x] #4 no change to classify_integrity behaviour or to the response schema
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #140. Added lines already present on master per PR: #140 2/225=0%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Landed directly on master as c633045 (base 06aadb7), superseding PR #140 which is closed with a pointer. Sample now carries a procedure field in tests/integrity_corpus.py; the reproduction section of docs/integrity.md is generated from the corpus by _generate_procedure_section and verified by an identity test; the markdown parser and its three shape tests are gone. Gate chain at the shipping hash: /simplify (4 angles), /code-review high over three rounds with every finding resolved (the corpus prose was reconciled with run_repro.py: btree values and insertion order corrected, count_fault values stated arbitrary with the script's v0020..v0059, incident_root's unattested table claim dropped, header names the two _NO_REPRODUCER_WHY exceptions, synthetic-procedure invariant re-established, guarded regeneration entry point), skeptic CONFIRMED twice (round 1 all claims at 347d29d, round 2 six claims at 939d04a), battery green (candidate-vmuedf1c: 1597 collected, 1594 passed, 3 declared skips, sha 9222547 matched).
<!-- SECTION:FINAL_SUMMARY:END -->
