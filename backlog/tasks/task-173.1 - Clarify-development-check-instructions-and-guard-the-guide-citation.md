---
id: TASK-173.1
title: Clarify development-check instructions and guard the guide citation
status: Done
assignee:
  - pyteman-coordinator
created_date: '2026-09-22 14:55'
updated_date: '2026-09-28 20:52'
labels: []
dependencies: []
references:
  - >-
    /home/pantinor/pyteman-evidence/task173-review-ind9360af/FINDINGS-AND-VERDICT.md
  - docs/development.md
  - .pre-commit-config.yaml
  - 'tests/test_packaging.py:104'
parent_task_id: TASK-173
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Follow-up to TASK-173 independent review F1 and F3. The documented prek workflow works, but repo: builtin makes .pre-commit-config.yaml incompatible with upstream pre-commit. Add an explicit documentation statement. README now cites docs/development.md, which exists and ships in the sdist, but tests/test_packaging.py CITED_BY_THE_README does not include it. Extend that existing presence check without changing packaging grants or runtime behavior. Both mechanisms confirmed from configuration, official prek docs and source; reviewer reproduced pre-commit rejection and a missing-guide case with a passing control. Do not include F2: the guide already says to use a Git checkout and accurately lists what release archives omit.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Developer instructions explicitly identify the hook configuration as prek-only without claiming upstream pre-commit compatibility.
- [x] #2 Removing docs/development.md makes the existing README-citation presence check fail, while the complete checkout passes.
- [x] #3 Packaging directory-equality assertions, runtime behavior and archive contents are preserved.
- [x] #4 Baseline cleanup instructions state that new diagnostics prevent pruning obsolete entries and require a clean rerun before lock-mode validation.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Final gate F7, independently reproduced by reviewer, not yet remeasured by coordinator: basedpyright1.40.1 default local mode removes obsolete baseline entries only when no new diagnostics remain. Obsolete-only control shrinks15to14 and exits0; obsolete plus new type error exits1 and stays15, then lock mode refuses stale entry at exit3. Add a sentence instructing contributors to resolve new errors, rerun the cleanup command and inspect baseline diff before lock-mode check. Evidence updated TASK-173 final review F7. Nonblocking documentation follow-up, no change to frozen delivery.

On master since 161d201 (#182, squash of #29 cherry-picked onto f2a4ea3 plus a wording fix after code review: basedpyright 1.40.1 keeps obsolete entries while any new error or warning remains, and a warning-only run exits 0 under the standard mode). Independent zai review APPROVED at f5a4f28, CI 7/7 green. #29 closed with a pointer to #182. (TASK-191, 2026-09-28)
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Three changes across two files. (1) Added prek-only compatibility note for .pre-commit-config.yaml in docs/development.md. (2) Added docs/development.md to CITED_BY_THE_README in test_packaging.py so the presence check catches its removal. (3) Added baseline cleanup caveat about new diagnostics preventing obsolete entry pruning. Suite: 1191 passed, 2 skipped. PR#29.
<!-- SECTION:FINAL_SUMMARY:END -->
