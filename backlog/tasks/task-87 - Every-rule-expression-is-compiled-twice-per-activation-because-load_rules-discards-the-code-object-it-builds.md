---
id: TASK-87
title: >-
  Every rule expression is compiled twice per activation, because load_rules
  discards the code object it builds
status: Done
assignee: []
created_date: '2026-09-16 21:14'
updated_date: '2026-09-29 21:44'
labels:
  - rt-01
  - review-followup
  - audit-2026-09-16
  - performance
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Raised by the efficiency angle of the RT-01 simplify gate. Requires editing src/pyteman/rules.py, which is frozen and APPROVED under TASK-7, so it was filed rather than applied.

`rules._expression` (rules.py:79-90) already calls `compile()` on `when` and on `fire.key` to validate them at load time, then DISCARDS the resulting code object and returns only the source string. `patcher._compile` then compiles the identical source a second time when `Patcher.__init__` builds its plan.

Measured, 40 rules each carrying both expressions, min of 200 runs with GC disabled: `Patcher.__init__` costs 2.64ms total, of which 1.84ms is `compile()`. That same 1.84ms was already spent inside `load_rules`. On the sitecustomize path the doubling is paid at every instrumented interpreter start, which is once per test process in a matrix run.

The fix is to have `_expression` keep what it built and have `_compile` prefer it, falling back to compiling only for rules constructed through the programmatic API. That fallback is not an edge case bolted on: it is exactly the situation `_compile`'s own docstring names, "rules built by hand through the programmatic API have not [been through load_rules]", and it is what makes activation atomic for those rules.

Explicitly NOT a finding, recorded so it is not mistaken for one later: moving the compile from `_make_wrapper` into `__init__` does mean that rules whose module never loads are now compiled where previously they were not. That extra work is the deliberate price of atomicity (a ruleset that cannot compile must die before the hook is installed), not waste.

Related: TASK-80 already tracks that `patcher._compile` and `rules._expression` compile the same two fields with divergent RuleError wording. The two should probably be resolved together, since sharing the code object and sharing the error wording are the same seam.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 rules._expression returns or stashes the code object it already compiles, instead of discarding it
- [x] #2 patcher._compile uses the stashed code object when present and compiles only for rules built through the programmatic API, which is the case its docstring already names
- [x] #3 Activation of a loaded ruleset performs zero redundant compile() calls, demonstrated by a counter or a timing comparison
- [ ] #4 A rule built by hand through the programmatic API still gets its expressions compiled in Patcher.__init__, so activation atomicity is unchanged
- [ ] #5 The RuleError wording for an invalid expression stays consistent between the load path and the programmatic path, or TASK-80 is resolved in the same change
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #118. Added lines already present on master per PR: #118 14/137=10%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge.

Merged 2026-09-29 via #191 (e27723f). AC1 left unchecked with the reviewer's judgment on file (VERDICT-80.md F2).
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by PR #191 (squash e27723f), together with TASK-80 whose construction gate is this task's completion. AC2 met: patcher._compile returns the stashed code object when the field still says the source it was compiled from (identity check) and compiles only for duck-typed programmatic rules, exactly the case its docstring names. AC3 met: activation of a loaded ruleset performs zero compiles, pinned by object identity in test_activation_reuses_precompiled_code_from_rule. AC1 stays unchecked by the letter (it asked _expression itself to return or stash the code object); the independent reviewer's F2 records that the spirit is met with the stash coming from Rule.__post_init__, which runs on the load path inside load_rules, and that only the literal sentence is unmet.
<!-- SECTION:FINAL_SUMMARY:END -->
