---
id: TASK-143
title: >-
  Record the duck-typed Patcher door as a decision that was made, not one that
  was inherited
status: To Do
assignee: []
created_date: '2026-09-17 09:44'
updated_date: '2026-09-28 18:16'
labels:
  - patcher
  - rules
  - design-decision
  - review-2026-09-17
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Raised by the altitude angle of the /simplify gate on the TASK-2 final snapshot (2026-09-17) as the premise under the new id gate rather than a defect in it.

`Patcher` never checks the type of what it is handed. Any attribute of a rule may therefore be user code, and the package pays for that with a guard at five separate sites. The new id gate is the fifth. The reviewer did not recommend requiring `isinstance(r, Rule)` at the door and neither do I, because the costs are real: the gate's own tests deliberately pass non-`Rule` objects (`UnreadableIdRule`, `HostileId`, `Interrupting`, `UncompilableUnreadableIdRule`), and a `Rule` SUBCLASS can still define `id` as a property, so the type check would not even close the hazard it looks like it closes.

The finding is that this has never been recorded as a decision. It reads as inherited. Every future raw read will re-argue it in a comment, which is how patcher.py arrived at seventy comment lines defending one twenty-statement loop.

This also sharpens TASK-138. Its AC #1 presents "freeze `Rule`" and "snapshot the id at plan time" as two routes to the same place. They are not equivalent in coverage. Because the door is duck-typed, freezing the dataclass closes the hole only for actual `Rule` instances and leaves it open for exactly the hand-built objects the gate's own tests use. Snapshotting covers both. That difference should be in TASK-138 rather than discovered during its implementation.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The decision is written down once, in the place a reader meets the programmatic door first, and says whether Patcher accepts duck-typed rule objects on purpose
- [ ] #2 If the answer is yes, it names the cost it buys and the guards it obliges, so a future raw read has something to cite instead of re-arguing it
- [ ] #3 If the answer is no, the isinstance check lands together with the fixture migration it forces, since the gate's own tests pass non-Rule objects
- [ ] #4 The decision record names the shapes an isinstance check would still NOT cover: a Rule subclass can define id as a property, so the type check is not equivalent to freezing the field
- [ ] #5 TASK-138 AC #1 is updated to say the two candidate fixes differ in COVERAGE and not only in cost
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #92. Added lines already present on master per PR: #92 0/30=0%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.
<!-- SECTION:NOTES:END -->
