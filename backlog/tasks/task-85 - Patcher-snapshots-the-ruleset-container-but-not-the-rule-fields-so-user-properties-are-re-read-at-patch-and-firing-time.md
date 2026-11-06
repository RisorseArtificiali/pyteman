---
id: TASK-85
title: >-
  Patcher snapshots the ruleset container but not the rule fields, so user
  properties are re-read at patch and firing time
status: To Do
assignee: []
created_date: '2026-09-16 21:14'
updated_date: '2026-09-28 18:16'
labels:
  - rt-01
  - review-followup
  - audit-2026-09-16
  - patcher
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Raised by the altitude angle of the RT-01 simplify gate, and independently supported by the efficiency angle's measurements. Filed rather than fixed: it changes the firing hot path and the activation failure point, which is beyond "complete exactly the RT-01 guarantees".

`Patcher.__init__` already embodies the right principle for two fields. It materialises the ruleset container once (`self.rules = tuple(rules)`), compiles both expressions, and pre-renders each rule's identity, all in the one step of an activation that mutates nothing. The stated reason is that a failure there costs nothing: no hook installed, no callable replaced, nothing to unwind.

The plan stops short of the remaining fields, so they are re-read later, from a caller-supplied object, in places where a read is a failure:

    rule.module   patcher.py:264
    rule.symbol   patcher.py:266, :282
    rule.action   patcher.py:315-316
    rule.event    patcher.py:344, :357   <- inside the wrapper, per call
    rule.fire     patcher.py:401, :404   <- inside _gate, per call

Two consequences. First, `_describe_rule` has ALREADY read `id`, `module` and `symbol` in `__init__`; `_patch` reads two of them a second time, which is both a second chance to raise and a chance to disagree, since a property may return a different value on each read. Second, and worse, `rule.event` and `rule.fire` are read inside the instrumented callable on every call, with no pyteman guard between them and the workload's own stack. docs/rules.md states the project's doctrine that a rule failing at firing is the worst class of failure "which is why validation is deliberately strict"; these are firing-time reads of user-supplied properties that validation does not reach.

The tell that this is a class rather than an incident: two of the tests added in this tranche (test_the_note_degrades_when_the_rule_cannot_say_which_module_it_is_for, test_the_note_names_the_rule_that_failed_not_the_one_before_it) are each a point defence for one more field read in the same loop. The next field added will need a third.

Proposed shape: make the plan entry a complete frozen snapshot taken in `__init__`, and have everything downstream read only the snapshot. Every attribute access against caller-supplied input then happens exactly once, where a failure is free. A rule whose `module` property raises would fail BEFORE the hook is installed rather than mid-patch with a degraded note, which is strictly more atomic and is the RT-01 thesis itself. `_typename`/`_text` stay: the objects they guard (containers, exceptions from setattr) arrive at runtime and cannot be snapshotted.

Measured context, so the cost is known rather than guessed. The efficiency angle timed `_patch` on the all-non-matching path, which runs on every `__import__` call and not merely every module load, since IMPORT_NAME calls `builtins.__import__` even for cached modules: 2.92us -> 5.83us at 40 rules, 0.75us -> 1.60us at 5 rules, comparing the pre-RT-01 shape with the current one. At 40 rules and ~1000 imports that is roughly 3ms per run, so it is not itself a reason to act. It is recorded because a snapshot keyed by module name would remove the O(rules) scan per import as well, and because the constant matters if rulesets grow or a workload imports inside a hot function.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Patcher.__init__ builds a per-rule frozen snapshot holding id, module, symbol, event, action, fire, the two code objects and the rendered description
- [ ] #2 _patch, _make_wrapper, the wrapper closure and _gate read only the snapshot; no rule attribute is read after __init__
- [ ] #3 A rule whose module, symbol, event or fire property raises is refused by __init__, before install_hook and before the first setattr
- [ ] #4 A test covers a raising .event and a raising .fire, which today fail inside the instrumented callable at call time with no pyteman guard above them
- [ ] #5 The existing degradation tests still pass or are updated to the earlier failure point, and docs/rules.md is updated if the note wording moves
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #138. Added lines already present on master per PR: #138 0/15=0%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Partly overtaken by a different design: master snapshots id/module/symbol/event at bind in _RuleIdentity (TASK-138, #171) and reads fire/n once at bind in _new_state (TASK-110, #160), refusing at bind rather than in __init__. The ACs as written (a per-rule snapshot built by __init__, refusal before install_hook) are not what master does; decide whether they still stand or should be rewritten to the bind-time design.
<!-- SECTION:NOTES:END -->
