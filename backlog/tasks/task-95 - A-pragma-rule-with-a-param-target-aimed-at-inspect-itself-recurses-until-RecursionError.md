---
id: TASK-95
title: >-
  A pragma rule with a param: target aimed at inspect itself recurses until
  RecursionError
status: To Do
assignee: []
created_date: '2026-09-16 21:36'
updated_date: '2026-09-30 19:03'
labels:
  - rt-01
  - review-followup
  - audit-2026-09-16
  - patcher
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Raised by the high-effort code review gate on RT-01. Pre-existing behaviour, not introduced by that tranche, so it was filed rather than fixed.

`_make_wrapper` performs a lazy `import inspect` when a rule has a `pragma` action with a `param:` target, in order to read the wrapped callable's signature. That import runs while the import hook is live, so it is served by the hook, which patches module `inspect` against the whole ruleset. docs/rules.md lines 41-51 document this re-entry and describe it as one extra level.

It is one level only because the `param:` rule normally names a module other than `inspect`. With `point: inspect.signature` and a `pragma` action carrying `target: param:x`, the recursion has no floor: `_patch("inspect")` reaches the rule, `_make_wrapper` runs `import inspect` BEFORE the `setattr`, the hook serves it, the nested `_patch("inspect")` sees the still-unwrapped original, passes the already-wrapped test (which is keyed on `_pyteman_state` and so cannot see a wrapper that has not been installed yet), and calls `_make_wrapper` again, until `RecursionError`.

It fails closed, which is why this is not urgent: exit 2, phase `installing instrumentation`. The operator experience is poor, because the `RecursionError` carries up to two notes per stack level and `_describe` joins all of them onto a single stderr line.

Two candidate fixes, neither obviously right: install the `setattr` before the wrapper is built for this case, which changes the ordering the rollback bookkeeping depends on; or add a re-entry guard keyed on `(id(self), modname)`, which is more code but leaves the ordering alone.

Explicitly NOT a fix: moving the `import inspect` back inside the `try`. That placement is load-bearing for a separate guarantee. See TASK-86, which tracks the decision about that import, and note that the two tasks constrain each other.

Related: TASK-86 (whether the lazy import stays at all).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A rule with point: inspect.<callable> and a pragma action carrying a param: target either activates cleanly or is refused with a diagnostic naming the rule, rather than dying of RecursionError
- [ ] #2 docs/rules.md's re-entry paragraph is corrected or qualified: it currently describes the nesting as one extra level, which holds only because the param: rule normally lives outside inspect
- [ ] #3 A test covers the self-referential case, since every existing re-entry test has the param: rule in a victim module and so can never nest more than once
- [ ] #4 Whatever the fix is, the lazy import stays outside the try in _make_wrapper, because moving it back inside makes a different rule's refused setattr indistinguishable from an unintrospectable callable
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #139. Added lines already present on master per PR: #139 0/56=0%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge.

Verified 2026-09-30 on current master: the recursion TASK-95 named is dead. A rule with point: inspect.signature and a param: target activates through Patcher construction without RecursionError (probed in a daemon thread with a 20s deadline; it finishes). The vector died when the build path's signature import was removed (the binding path reads __code__ and imports nothing), the same removal the #139 worktree commit 997c6e9 documented. What that commit carries beyond the fix: the stale re-entry claims in patcher.py were rewritten by TASK-121/#195, and the stale rules.md passages were rewritten in the same set. The one unlanded piece is the commit's regression test (a param: rule targeting inspect.signature activating cleanly), which survives only on refs/review/pr139 and the worktree branch; the next revival of this task should start from that test rather than from the stale diff.
<!-- SECTION:NOTES:END -->
