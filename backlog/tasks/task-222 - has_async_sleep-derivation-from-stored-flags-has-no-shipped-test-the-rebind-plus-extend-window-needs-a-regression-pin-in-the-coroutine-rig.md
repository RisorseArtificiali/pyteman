---
id: TASK-222
title: >-
  has_async_sleep derivation from stored flags has no shipped test; the
  rebind-plus-extend window needs a regression pin in the coroutine rig
status: To Do
assignee: []
created_date: '2026-11-08 23:18'
updated_date: '2026-11-09 00:28'
labels:
  - tests
  - patcher
  - coverage-gap
dependencies:
  - TASK-221
references:
  - 'src/pyteman/patcher.py:564'
  - tests/test_coroutine_entry.py
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found 2026-11-09 by the TASK-85 code-review round (finding 1) and its skeptic. The driver-road flag comp.has_async_sleep (patcher.py, _republish_state) now derives from the stored per-entry state flags (state["awaits_loop"]), so the road choice and the awaiting driver answer from the same bind-time snapshot; the fix shipped with TASK-85 but has NO shipped regression test: the reviewer's scenario (async-sleep rule bound on a coroutine slot, rule.action rebound after install, a later patch call reaching the same slot extends the dispatcher and republishes the flag, then the next firing must still take the awaiting road and suspend rather than block) is verified only by the skeptic's ad-hoc mutation probes, which die with its /tmp rig. The natural home is the subprocess coroutine rig in tests/test_coroutine_entry.py, which is exactly the rig TASK-221 shows can silently test the wrong tree; do this after TASK-221 makes the child fail closed on a mis-pathed candidate, or the new test can itself pass vacuously. The observation shape already exists there: test_an_async_sleep_suspends_one_chain_while_the_loop_lives observes loop responsiveness during the sleep; extend that shape with rebind plus a second force_patch_module reaching the owned slot (the extend idiom from test_a_later_patch_call_reaching_a_slot_we_already_own_extends_it).
<!-- SECTION:DESCRIPTION:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Update 2026-11-09: the flag-VALUE half of this gap landed with TASK-85 itself (candidate 4c986ea): test_the_driver_flag_answers_the_stored_flags_across_a_rebind_and_extend pins that the derivation answers the stored flags across a rebind plus two rank-pinned extends, and flips red under the live-read mutation (verified on a scratch copy). What remains open here is the BEHAVIORAL half only: observing the road actually taken (loop responsiveness during the slept chain) in the subprocess rig, which still requires the TASK-221 isolation fix first. A regression that ignores the flag at the dispatcher's road choice would pass the new pin, so the behavioral observation is still worth landing with the rig fix.
<!-- SECTION:NOTES:END -->
