---
id: TASK-84
title: >-
  The documented PYTHONPATH puts every pyteman module on the workload's
  top-level namespace
status: Done
assignee: []
created_date: '2026-09-16 20:51'
updated_date: '2026-09-27 05:10'
labels:
  - rt-01
  - review-followup
  - audit-2026-09-16
  - docs
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found during the RT-01 review, alongside the fail-closed findings. Filed rather than fixed because it changes the documented activation layout, which is beyond "complete exactly the RT-01 guarantees".

README's activation contract says:

> Put the directory containing `sitecustomize.py` on the PYTHONPATH of TEST runs only; that is `src/pyteman`, not `src`.

That directory is the package itself, so putting it on sys.path makes every module inside it importable under its BARE name in the workload's process:

    actions.py  barriers.py  conditions.py  firing.py
    patcher.py  rules.py  sitecustomize.py  targets.py

`rules`, `targets`, `actions`, `conditions` and `firing` are ordinary names for a workload to have used itself. Whichever entry comes first on sys.path wins, so the instrumented run can silently import pyteman's `rules.py` where the uninstrumented run imported the workload's, or the reverse. Either way the program under test is not the program that was tested, which defeats the purpose of a fault-injection harness: the difference between the two runs is supposed to be the ruleset.

The collision is a consequence of the layout rather than of the shim. `sitecustomize` has to be top-level because that is how the interpreter finds it, but nothing requires its NEIGHBOURS to be. A directory holding only `sitecustomize.py` (a shim that does nothing but import the real one) would give the interpreter what it needs and expose exactly one name.

Not urgent and not silent in the dangerous direction: a collision produces an ImportError or obviously wrong behaviour rather than a fail-open run. But it is a documented instruction that can corrupt an experiment, so it should be either fixed or stated.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The collision is documented: README states exactly which top-level names the instruction claims (nine modules plus runner and sqlitekit), splits the claims in kind, and names the sitecustomize sharp edge with its silent-fail-open tell
- [x] #2 If a shim directory is adopted later instead, it holds sitecustomize.py alone and the activation contract in README points at it
- [x] #3 A test pins whichever claim the README makes: under the documented layout, a bare import with no local provider resolves into pyteman and a workload module in the process's own import root wins through the interpreter's prepend alone (PYTHONPATH narrowed to the package entry so the win is not overdetermined); under a future shim layout the first half fails and forces the README to move
- [x] #4 tests/test_sitecustomize.py's own PYTHONPATH construction is unchanged because it models the documented layout, which this decision keeps
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Decision recorded (2026-09-27): document rather than restructure. The shim directory holding sitecustomize.py alone would ripple through the packaging contents tests (wheel/sdist exact-contents assertions), the delivery skill's identity checks, and every test harness's PYTHONPATH construction (startup_harness SRC plus the per-file _run copies), a scope far beyond a review-followup docs task; the collision is real but bounded, and the README now states exactly which top-level names the instruction claims. ACs reworded to the two-disjunct form this decision satisfies; the AC #3 test pins the documented claim (bare names DO resolve into pyteman with no local provider), which fails the day the shim lands and forces the README to move with it.

Four-angle review findings, all applied: (1) the first draft's closing guarantee (collisions never silent) was FALSE for sitecustomize, the one name the interpreter imports itself; a probe showed a workload sitecustomize.py silently shadowing pyteman's activation with exit 0 and no firing log. The README now names sitecustomize as the sharp edge with the firing log's absence as the only tell, and scopes the never-silent claim to the other names. (2) The two mitigations were wrongly interchangeable: pyteman imports its internals package-qualified, depending on exactly one bare name, and the ordering advice is now attached to the case it solves (the default interpreter ordering already protects workload modules in the process's own import root). (3) The first README list omitted pragmas, runner and sqlitekit; corrected to the exact directory listing. Test nits applied: the resolution assertion pins this tree's SRC, the code strings are inlined consistently, and the docstring's overstated parenthetical is gone.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Merged as 9ba035f via PR #153 (head 1a6c58a after the review fixup amend). Review cycle: first verdict CHANGES-REQUIRED at 1432155 on one blocking finding (the sharp-edge paragraph covered only the branch where the workload's sitecustomize wins, while the default documented shape manifests the opposite: the package entry comes first at site-import time, so the WORKLOAD's sitecustomize is silently skipped with the firing log present, making the log check a false all-clear); fixed in the README and PR body with both branches stated, re-approved at 1a6c58a. Two earlier review rounds shaped the whole paragraph: the four-angle pass falsified the never-silent guarantee for sitecustomize by probe, corrected the mitigation ordering (pyteman imports package-qualified, depending on exactly one bare name), and completed the name list (nine modules plus runner and sqlitekit); the code-review belt reconciled the task ACs to the documentation decision and isolated the test's second half (PYTHONPATH narrowed to the package entry so the workload module's win comes from the interpreter's prepend alone). Gates: /simplify four-angle findings applied; code-reviewer-typed high review with both rounds' findings applied; mutation kills; battery check clean, 1264 passed 2 skipped; PR CI green; master CI green.
<!-- SECTION:FINAL_SUMMARY:END -->
