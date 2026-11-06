---
id: TASK-86
title: >-
  Decide whether the patcher's lazy inspect import stays, since a documented
  contract rests on its placement
status: Done
assignee: []
created_date: '2026-09-16 21:14'
updated_date: '2026-09-30 03:48'
labels:
  - rt-01
  - review-followup
  - audit-2026-09-16
  - patcher
  - design-decision
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Raised by the altitude angle of the RT-01 simplify gate. Not a defect in the current code, and the agent said so; it is a coupling that should not persist undecided.

`_make_wrapper` imports `inspect` lazily, only for `param:` pragma rules. That import runs while pyteman's own import hook is live, so it is served by the hook and triggers a nested `_patch` pass that patches `inspect` against the whole ruleset before the outer rule has finished. This tranche fixed a real bug caused by it (a different rule's refused setattr was being relabelled "this signature would not parse", because the `except (TypeError, ValueError)` covered the import as well as `signature()`), by hoisting the import above the `try`. That fix is correct and narrow: a guard must not be wider than the operation it claims to describe.

But the re-entrancy it now reports on legibly is self-inflicted. Moving `import inspect` to module scope in `patcher.py` would remove the class outright: `pyteman.patcher` is imported before `activate()` runs, so the import lands before the hook exists. This is the only self-re-entry in the patch path; ordinary nested workload imports do not nest `_patch` inside itself, because the inner `hooked()` completes during `orig()` and before the outer `_patch` begins.

Cost, measured by the efficiency angle rather than estimated, and it corrects an earlier assumption of mine that the hoist would be expensive:

- `inspect` is ALREADY in sys.modules by the time `patcher` is imported, arriving via `pyteman.rules` -> `dataclasses` -> `inspect`. So a module-scope hoist imports nothing new.
- The lazy import with the hook live costs 7.54us against 0.66us unhooked; the ~6.9us delta is exactly the re-entrant _patch scan. Five `param:` rules cost about 35us for a whole activation.

So the trade is nearly free in both directions, which is precisely why it needs deciding on design grounds rather than performance ones. Three artefacts currently depend on the lazy placement:

1. The re-entrancy half of the `_patch` comment at patcher.py:241-242, which justifies collecting wraps in a local list.
2. The note-stack paragraph in docs/rules.md, which documents that a failure arrives carrying one `pyteman: while patching <rule>` note per level, innermost first.
3. test_a_refused_patch_is_not_reported_as_an_unparseable_signature, whose premise is the nesting.

The paragraph was narrowed in this tranche to read as a consequence of the `param:` implementation rather than as a general property of patching, which is honest but does not resolve the coupling. What should not persist is the current state, where a one-line import placement is load-bearing for a documented user-facing contract.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A decision is recorded either way: hoist the import and delete the documented behaviour, or keep it lazy and keep the docs
- [x] #2 If hoisted: import inspect moves to module scope in patcher.py, the re-entrancy clause of the _patch comment (patcher.py:241-242) is removed, and the note-stack paragraph in docs/rules.md goes with it in the same change
- [x] #3 If hoisted: test_a_refused_patch_is_not_reported_as_an_unparseable_signature is re-examined, since its premise is that the import is served by the live hook
- [x] #4 The threading argument for the local wrapped/applied lists (patcher.py:248-259) is confirmed to stand on its own, because it becomes the sole justification
- [x] #5 Measured before/after of activation cost is recorded in the task, not estimated
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #138. Added lines already present on master per PR: #138 0/15=0%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge.

Reviewer's informational note (VERDICT-86.md, 2026-09-30): the paragraph's 'while patching' shorthand can read 'while resolving' when the outer failure surfaces during the resolution pass; pre-existing wording, the contract holds in both phases, one clause would make it exact.

Merged 2026-09-30 via #198 (347d36c). Evidence under /home/pantinor/pyteman-evidence/t191/: diff86.patch sha256 7ede2e81, tree86-hold1.sha256, VERDICT-86.md in t191rev.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
The decision is recorded: hoisted. The substance landed on master before this set closed (the intervening merges put import inspect at module scope, removed every local import from the patch path, made _binding_signature read __code__ and import nothing, and pinned the structural half with test_building_a_param_dispatcher_imports_nothing), and PR #198 (squash 347d36c, merged 2026-09-30 03:47Z) landed the one piece left behind, the stale note-stack paragraph in docs/rules.md that still named the removed param: import as the cause: the stack survives via target-code imports in the walk and the write, the contract unchanged. AC1: decided and recorded. AC2: hoisted, the re-entrancy clause rewritten (not merely removed: target-code re-entry remains real) and the rules.md paragraph rewritten in the same change. AC3: the premised test was rewritten on master to say the re-entry no longer exists and its count is 1, with the structural test named as what makes the depth drop legitimate. AC4: the threading argument stands alone in _patch's comment, which leads with concurrency as its own road. AC5: the measurement is the one recorded in this task's description (7.54us hooked against 0.66us unhooked, the delta the re-entrant scan), taken by the efficiency angle. Supersedes #138, closed with a pointer. Gates at d716594: suite 1532 passed 2 skipped, check green, delivery 41, independent verdict APPROVED (VERDICT-86.md); the reviewer's informational shorthand note (while resolving vs while patching) is recorded on this task. TASK-85, which shared #138 in the inventory but of which #138 carried nothing, remains open.
<!-- SECTION:FINAL_SUMMARY:END -->
