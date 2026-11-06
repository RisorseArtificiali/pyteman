---
id: TASK-75
title: >-
  RT-21: the "never render in a call argument" rule on the refusal path is
  enforced by comments only
status: Done
assignee: []
created_date: '2026-09-16 19:12'
updated_date: '2026-09-30 14:35'
labels:
  - rt-01-followup
  - hardening
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The whole RT-01 refusal/rollback path depends on a rule that exists nowhere in the code: rendering must never happen in an ARGUMENT to a guarded function, because arguments are evaluated before the callee's try/finally is entered.

Today the rule is written down in three comments (src/pyteman/patcher.py in _patch's except block and in _disclose, src/pyteman/sitecustomize.py in _refuse's docstring) and enforced by nothing. Both defects found in the TASK-1 review rounds were instances of it:
- `_refuse(phase, _describe(exc))` rendered outside the try/finally that guarantees os._exit. Fixed by passing the exception.
- `_note(exc, f"... {_text(current.id)!r} ...")` rendered outside _note's guard. Fixed indirectly, by making _text return an exact str so the interpolation cannot run user code.

The second fix closes the concrete hole but not the class: the f-string is still evaluated as an argument. It is inert only because every value in it is now an exact str. A future edit adding a fourth interpolation, or a value that does not go through _text, reopens it silently.

The reviewer's suggestion was a variadic `_note(exc, *parts)` that joins and renders inside its own guard, making the invariant an API shape rather than a convention. Declined for the TASK-1 round because the helper normalisation already closes every reachable trigger (Rule is a plain dataclass, so attribute access cannot raise; only a hand-written Rule SUBCLASS with a raising property could, which is the operator sabotaging themselves), and RT-01 was scoped to completing exactly its stated guarantees.

Worth doing as hardening, not as a bug fix.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 _note renders its message inside its own guard rather than accepting a pre-rendered string
- [x] #2 Every call site on the refusal and rollback paths passes unrendered parts
- [x] #3 Existing note wording, which docs/rules.md quotes and the tests match on, is unchanged
- [x] #4 Full battery still passes
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #60. Added lines already present on master per PR: #60 0/28=0%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.

Merged 2026-09-30 via #207 (a55b279). Evidence under /home/pantinor/pyteman-evidence/t191/: diff75.patch sha256 cbe35b1d, tree75-hold1.sha256, mutants-75.log, VERDICT-75.md in t191rev.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by PR #207, squash-merged as a55b279 on master at 2026-09-30 14:34Z. AC1: the note renders inside its own guard; safe_add_note takes *parts and joins them inside its try, so a part whose __str__ raises drops the note instead of replacing the exception being annotated. AC2: all five refusal and rollback sites pass unrendered parts; the firing leaf's caller passes its already-guarded text as a single part unchanged. AC3: the note wording is byte-identical. AC4: the suite is green (1545 passed, 3 skipped) and the battery kills three coupling shapes: the join moved outside the guard, the planning site reverting to in-argument concatenation, and the rollback site reverting to an f-string argument. A structural pin over the five call sites replaces comments-only enforcement. Supersedes #60 in design, applied to the leaf TASK-14.2 put in place; #60 closed with a pointer. Gates at ac258a2: suite, check, delivery, battery, code-review high (one finding: the leaf normalisation dead by join construction, measured and simplified), independent verdict APPROVED (VERDICT-75.md).
<!-- SECTION:FINAL_SUMMARY:END -->
