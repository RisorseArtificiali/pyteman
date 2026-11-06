---
id: TASK-82
title: >-
  Patcher.rules and _plan hold the same ruleset twice, and only the constructor
  keeps them in step
status: Done
assignee: []
created_date: '2026-09-16 19:58'
updated_date: '2026-09-29 21:46'
labels:
  - rt-01
  - review-followup
  - api
  - maintainability
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Raised by the simplification and altitude passes of the RT-01 /simplify review, then rewritten later the same day because a fix landed in the same tranche that falsified the original framing. See the note below for what changed and why.

`Patcher.__init__` keeps the ruleset in two shapes. `self.rules` is a tuple of the rules, and `self._plan` is a list of `(rule, when_code, key_code, described)` built from it, so every rule is stored twice: once on its own and once as element 0 of its plan entry. The patch loop reads only `_plan`; nothing outside the constructor reads `self.rules`, and grep finds no reference to it anywhere else in the repository.

The constructor is what keeps the two in step, and it does so by construction rather than by enforcement: `self.rules = tuple(rules)` is materialised first and the plan comprehension iterates `self.rules` rather than the caller's argument. That ordering is load-bearing and is now pinned by test_a_ruleset_handed_over_as_an_iterator_is_read_exactly_once, because building the plan from the argument instead consumed a caller-supplied iterable twice and produced a full plan alongside an empty `self.rules`.

What remains unguarded is everything after construction. A tuple blocks `p.rules.append(...)` and does not block `p.rules = [...]`, so the two representations can still be made to disagree by the other spelling, and nothing would notice: the patch loop would go on using `_plan` while `p.rules` reported a different ruleset to anyone who asked.

The complete fix is to stop storing the ruleset twice. Either drop the attribute, or expose it as a read-only property derived from `_plan` (`tuple(entry[0] for entry in self._plan)`), which makes disagreement unrepresentable rather than merely inconvenient. Note the direction: `_plan` is now built FROM `self.rules`, so a fix must not reintroduce a second iteration of the caller's iterable. That is a public-API decision rather than an RT-01 guarantee, which is why it was not taken inside a tranche the orchestrator scoped to completing the RT-01 guarantees exactly.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Patcher.rules is either removed or reimplemented as a read-only property derived from _plan, so the ruleset has one representation rather than two
- [x] #2 The chosen fix reads the caller's iterable exactly once, and test_a_ruleset_handed_over_as_an_iterator_is_read_exactly_once still passes against it
- [ ] #3 If removed, the removal is checked against any external caller and recorded as an API change in the README or docs
- [x] #4 A test pins whichever behaviour is chosen, including that a post-construction rebind cannot make the attribute disagree with _plan
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Rewritten 2026-09-16 after verifying the task against the code rather than against the note that created it.

The original framing said Patcher.rules was WRITE-ONLY and that nothing read it. That was true when this was filed at 19:58 and stopped being true minutes later, inside the same tranche: the generator-desync fix made self.rules the materialised source that _plan is built from, so the constructor now reads it. The finding itself survives, because the ruleset is still stored twice, but the title, the evidence and acceptance criterion #1 all described code that no longer exists.

The correction matters beyond tidiness. The old criterion #1 said to reimplement Patcher.rules as a property derived from _plan without saying anything about how _plan is built, and implementing it literally against the current code would have meant building _plan from the caller's argument again. That is exactly the double-iteration bug the tranche had just fixed: a generator produced a full plan and an empty rules tuple. Criterion #2 now pins the single-read requirement so the fix cannot undo it.

Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #72 #74 #121 #126. Added lines already present on master per PR: #72 1/15=6%  #74 0/20=0%  #121 0/22=0%  #126 3/16=18%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.

Set closed 2026-09-29 without a revival: master already carried the content, so the honest close is the pointer, not a duplicate PR through the chain.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed against master with no new PR: the change TASK-82 asked for landed 2026-09-29 through PR #186 (TASK-100's AC2 was this same finding). AC1: Patcher.rules is a read-only property derived from _plan (patcher.py on master, the stored second copy is gone, no assignment site remains). AC2: the caller's iterable is materialised once in __init__ and both loops walk the local; test_a_ruleset_handed_over_as_an_iterator_is_read_exactly_once passes on master and asserts p.rules equals the caller's tuple. AC3: not applicable, the property was kept rather than removed. AC4: the chosen behaviour is pinned by the iterator test's equality assertion; the rebind half (assignment refused, the property has no setter) is verified but unpinned, filed on TASK-198 the same turn. Open PRs #72 and #126, both implementing this change, closed with pointers to #186.
<!-- SECTION:FINAL_SUMMARY:END -->
