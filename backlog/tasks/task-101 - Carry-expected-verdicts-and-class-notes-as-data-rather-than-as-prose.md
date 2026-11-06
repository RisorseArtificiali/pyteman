---
id: TASK-101
title: Carry expected verdicts and class notes as data rather than as prose
status: In Progress
assignee: []
created_date: '2026-09-17 00:31'
updated_date: '2026-09-26 13:10'
labels:
  - audit-2026-09-16
  - sql
  - cleanup
  - deferred-from-task-24
milestone: m-3
dependencies:
  - TASK-24
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Three structural proposals raised by the TASK-24 simplify reviewers against code that was already approved under TASK-25, deferred rather than applied because each changes a shape the approved tranche settled.

1. `Sample` in tests/integrity_corpus.py carries name, origin, text and note, so what a sample is expected to classify as lives only in whichever test happens to name it. Several samples are pinned in more than one test and at least one was pinned nowhere until TASK-24 noticed. An expected-verdict field would make the corpus self-checking: one parametrized test over the whole corpus would replace a scattering of hand-written pins, and a sample added without a stated expectation would fail rather than pass silently.

2. `_diagnose` in src/pyteman/sqlitekit/integrity.py appends a caveat sentence for FTS_CORRUPTION and for no other class. The other four classes have caveats worth stating and state them only in docs/integrity.md. A `_CLASS_NOTES` mapping from class name to caveat would give every class the treatment one class gets today and would remove the special case.

3. The argument that removing the `fts5: missing row` needle costs no coverage rests on two samples being two views of the same damaged database. Nothing in the corpus records that relationship, so a pairing field would make it checkable instead of leaving it to prose.

Raised by the reuse and simplification reviewers during TASK-24. Not applied there: TASK-24 owns the classification criterion and these change the corpus and diagnosis shape.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Sample records the verdict each sample is expected to classify as and a whole-corpus test enforces it so a sample added without an expectation fails
- [ ] #2 _diagnose derives its per-class caveat from a mapping so no class is special-cased and every class either has a caveat or is recorded as having none deliberately
- [ ] #3 The relationship between samples that are two views of one damaged database is recorded in the corpus rather than only in prose
- [ ] #4 The existing tests that these changes make redundant are removed rather than left alongside the new mechanism
<!-- AC:END -->
