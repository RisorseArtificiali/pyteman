---
id: TASK-220
title: >-
  Install path reads rule.action live at four separate sites; a flapping
  property can split the door verdict from the bound snapshot (TASK-85
  follow-up)
status: To Do
assignee: []
created_date: '2026-11-08 23:11'
updated_date: '2026-11-09 00:28'
labels:
  - patcher
  - review-finding
  - correctness
dependencies: []
references:
  - 'src/pyteman/patcher.py:2800'
  - 'src/pyteman/patcher.py:3427'
  - 'src/pyteman/patcher.py:2145'
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found 2026-11-09 by the TASK-85 code-review round (finding 3 of 7 on candidate b008071). The firing path now reads only the bind-time action snapshot (TASK-85), but the install path still performs independent live reads of spec.rule.action: the async-sleep refusal doors (patcher.py:2800 install, :3427 extend), the signature decision (_needs_signature, patcher.py:2145-2147), and the snapshot build itself (_new_state, ~1014). A programmatic rule whose action is a flapping property can return a non-async mapping to the door and an async one to the snapshot: the door admits the rule on a sync slot, the state binds awaits_loop=True, and the first firing runs a blocking sleep inside a plain-def dispatcher, the exact degradation the doors exist to refuse. The same split can mis-answer _needs_signature (the ctx._signature seeding decided from a different invocation than the action that fires). The read-ONCE guarantee currently holds only inside _new_state. Fix direction: read each rule's action mapping once per install path (door, signature decision, and state build sharing one read, the same way the firing path now shares the snapshot), or have the doors consult the snapshot the state is about to take. The flap refusal test in test_activation_atomic.py (test_an_action_property_that_flaps_between_install_reads_refuses_the_patch) already pins that a flap refuses the patch; this task closes the door-vs-snapshot disagreement rather than the refusal. Note: _republish_state's driver flag was already moved onto the stored flags in the same round (has_async_sleep derives from state awaits_loop, patcher.py:564), so the rebind-plus-extend split is closed; what remains is the install-window split only.
<!-- SECTION:DESCRIPTION:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Live probe by the TASK-85 round-two code-review (2026-11-09) on candidate 7040f41: the silent-change flavor of this window is confirmed end to end. A property returning {"kind":"sleep","ms":1200} to the door read (patcher.py:2808) and {"kind":"sleep","ms":1200,"async":True} to _new_state's snapshot read (patcher.py:1022) on a synchronous target installs successfully (applied non-empty, stored awaits_loop True, has_async_sleep True) and the call blocks the full 1.2s in time.sleep: the exact degradation the door exists to refuse, produced by the install-window split alone. The raising flavor is NOT part of this window: any raising install-path read refuses the patch (door, signature decision, and snapshot read are all in the install scope), pinned by the TASK-85 refusal tests.

Note 2026-11-09: the refusal test this task's description cites was renamed in the final TASK-85 candidate to test_an_action_read_that_raises_on_a_later_install_read_refuses_the_patch (the old name said flap generically while the pinned claim is raises-only; the value-flap window is exactly this task).
<!-- SECTION:NOTES:END -->
