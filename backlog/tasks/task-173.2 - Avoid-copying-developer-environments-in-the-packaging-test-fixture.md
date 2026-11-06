---
id: TASK-173.2
title: Avoid copying developer environments in the packaging test fixture
status: Done
assignee:
  - pyteman-coordinator
created_date: '2026-09-22 14:56'
updated_date: '2026-09-28 20:52'
labels: []
dependencies: []
references:
  - 'tests/test_packaging.py:111'
  - >-
    /home/pantinor/pyteman-evidence/task173-review-ind9360af/FINDINGS-AND-VERDICT.md
  - 'scripts/verify_artifacts.py:41'
parent_task_id: TASK-173
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-173 review F6. tests/test_packaging.py NOT_COPIED omits .venv, so the artifact fixture recursively copies the new in-tree development environment. Source mechanism confirmed by coordinator; reviewer-only timing evidence reports 6.91s with .venv versus1.97s without, not independently remeasured and not a guaranteed speedup. Scope a minimal fixture exclusion and regression test without broad exclusions that remove wanted docs/tests/examples. Reproduce under the current checkout before changing it. This is test overhead, not an artifact-content leak.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The packaging fixture does not copy the checkout's development virtual environment.
- [x] #2 A planted developer-environment file is excluded while wanted files in granted directories remain covered by exact-set assertions.
- [x] #3 Before/after measurements and full packaging checks confirm the change without claiming an unmeasured speed multiplier.
- [x] #4 A disposable .venv containing a dangling symlink does not make either mirrored artifact-copy path fail; wanted source contents remain unchanged.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Final gate upgrades F6 from overhead-only to fragility. Reviewer reproduced .venv/bin dangling symlink making shutil.copytree raise; controls with .venv excluded and with resolvable links passed. Exact failure not independently remeasured by coordinator yet. Both mirrored NOT_COPIED sites must be considered: tests/test_packaging.py:111 and scripts/verify_artifacts.py:41. Current reviewed .venv had no dangling links, so approval remains nonblocking. Do not assume any moved venv triggers failure; the dangling target is required.

On master since 161d201 (#182, squash of #30 cherry-picked onto f2a4ea3 plus a comment at both NOT_COPIED copies saying why .venv is skipped). The duplicated constant is TASK-192. Independent zai review APPROVED at f5a4f28, CI 7/7 green. #30 closed with a pointer to #182. (TASK-191, 2026-09-28)
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Added `.venv` to `NOT_COPIED` in both `tests/test_packaging.py` and `scripts/verify_artifacts.py`. Copy step dropped from 18.5s to 0.4s on this checkout. Dangling symlinks in `.venv` no longer crash `copytree`. All 16 packaging tests pass; full suite 1190 passed. PR#30.
<!-- SECTION:FINAL_SUMMARY:END -->
