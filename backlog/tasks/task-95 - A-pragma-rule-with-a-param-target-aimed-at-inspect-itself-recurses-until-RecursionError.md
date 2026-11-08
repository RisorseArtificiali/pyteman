---
id: TASK-95
title: >-
  A pragma rule with a param: target aimed at inspect itself recurses until
  RecursionError
status: Done
assignee: []
created_date: '2026-09-16 21:36'
updated_date: '2026-11-08 06:20'
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
- [x] #1 A rule with point: inspect.<callable> and a pragma action carrying a param: target either activates cleanly or is refused with a diagnostic naming the rule, rather than dying of RecursionError
- [x] #2 docs/rules.md's re-entry paragraph is corrected or qualified: it currently describes the nesting as one extra level, which holds only because the param: rule normally lives outside inspect
- [x] #3 A test covers the self-referential case, since every existing re-entry test has the param: rule in a victim module and so can never nest more than once
- [x] #4 Whatever the fix is, the lazy import stays outside the try in _make_wrapper, because moving it back inside makes a different rule's refused setattr indistinguishable from an unintrospectable callable
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #139. Added lines already present on master per PR: #139 0/56=0%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge.

Verified 2026-09-30 on current master: the recursion TASK-95 named is dead. A rule with point: inspect.signature and a param: target activates through Patcher construction without RecursionError (probed in a daemon thread with a 20s deadline; it finishes). The vector died when the build path's signature import was removed (the binding path reads __code__ and imports nothing), the same removal the #139 worktree commit 997c6e9 documented. What that commit carries beyond the fix: the stale re-entry claims in patcher.py were rewritten by TASK-121/#195, and the stale rules.md passages were rewritten in the same set. The one unlanded piece is the commit's regression test (a param: rule targeting inspect.signature activating cleanly), which survives only on refs/review/pr139 and the worktree branch; the next revival of this task should start from that test rather than from the stale diff.

Closure note (2026-11-08): closed on evidence after the overlap probe. The T146 test is strictly stronger than the branch's test_param_target_on_inspect_itself_does_not_recurse (activate-level without observable-landing asserts); the branch's docs/comment rewrites were overtaken by the TASK-121 and T152 rewrites; the recursion itself died with the binding-path __code__ change. Same-turn mechanical evidence: test re-run green on origin/master content; docs paragraph read and named.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed as already satisfied on master; no push of the branch's content; supersedes and closes #139. The recursion TASK-95 named is dead on master: the vector was the per-slot lazy import inspect in the wrapper build, and the binding path now reads __code__ and imports nothing (the removal the 2026-09-30 note verified live in a daemon thread with a 20s deadline, and every battery run since re-verifies). AC1: a rule with point inspect.signature and a param: target activates cleanly, proven by test_param_rule_on_inspect_does_not_recurse in tests/test_binding_reach.py (landed with the T146 set, master 0d798c5), which asserts the dispatcher really takes the attribute, the ledger records the landing, and uninstall restores the original; the T146 skeptic proved the test's teeth in both directions (a reintroduced per-call import on either signature-path site kills it). Re-run this turn on origin/master content for same-turn evidence: 1 passed. AC2: the re-entry paragraph in docs/rules.md is the corrected general form (the walk and the write run target code) and names the removed import explicitly in the parenthetical about the dispatcher's former param: signature import. AC3: the self-referential test is exactly the T146 test; every pre-existing re-entry test had the param: rule in a victim module, and this one aims it at inspect itself. AC4: moot in the strongest form: the lazy per-slot import no longer exists anywhere, and the module-level inspect import sits before activate() installs the hook, so it costs no re-entry at all. The #139 branch's own diff was stale twice over: its comment rewrites predate the TASK-121-era re-entry rewrites, and its rules.md passages were rewritten by the T152 consolidation; its one live piece, the self-referential regression test, was superseded by the T146 test which is strictly stronger (observable landing and restoration asserts, both-direction mutation proofs).
<!-- SECTION:FINAL_SUMMARY:END -->
