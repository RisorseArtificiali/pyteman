---
id: TASK-96
title: >-
  Derive the reproduction procedures from the corpus instead of parsing them
  back out of the document
status: To Do
assignee: []
created_date: '2026-09-16 23:43'
updated_date: '2026-09-28 18:16'
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
- [ ] #1 docs/integrity.md reproduction section is generated from the corpus rather than parsed back by tests
- [ ] #2 the markdown-shape tests in test_docs_integrity.py are removed along with the parser they pin
- [ ] #3 an observed sample cannot be added without a procedure and a test proves that
- [ ] #4 no change to classify_integrity behaviour or to the response schema
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #140. Added lines already present on master per PR: #140 2/225=0%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Moved reproduction procedures from docs/integrity.md into the corpus (tests/integrity_corpus.py), making each observed sample carry its own `procedure` field. Replaced the markdown parser (`_entries`) and its edge-case tests with a generation+comparison pattern. PR #140: https://github.com/RisorseArtificiali/pyteman/pull/140
<!-- SECTION:FINAL_SUMMARY:END -->
