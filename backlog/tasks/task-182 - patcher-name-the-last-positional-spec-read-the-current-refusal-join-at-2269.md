---
id: TASK-182
title: 'patcher: name the last positional spec read (the current-refusal join at 2269)'
status: Done
assignee: []
created_date: '2026-09-27 07:09'
updated_date: '2026-09-27 07:12'
labels:
  - cleanup
dependencies: []
references:
  - src/pyteman/patcher.py
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From the TASK-129 final review (work/task129-named-specs). The named-specs sweep left one positional fourth-field read outside the two hot loops and the two construction comprehensions: src/pyteman/patcher.py line 2269 builds the refusal string with:

current = "; ".join(d for _, _, _, d, _ in slot.specs)

Not a bug: behavior is identical today, it runs once per slot per patch (not a hot loop), and it incidentally doubles as the loud TypeError tripwire for a bound-spec-swapped-into-slot.specs (a state dict cannot join into a string). But the task's stated invariant was that every positional read converts to a named one, and this one was not in the four-angle review's fix set. Completing it costs nothing:

current = "; ".join(spec.described for spec in slot.specs)

That also makes the read survive a field reorder of _ResolvedSpec instead of silently reading whatever lands in slot 4. The hot loops (lines 1423 and 2747) and the two bound comprehensions (2694 and 2920) stay positional by design.
<!-- SECTION:DESCRIPTION:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Applied in the same TASK-129 diff rather than as a separate cycle: the join at patcher.py:2269 now reads spec.described, the one-line completion this task named, verified with the atomic and coroutine suites green (171 passed) and check clean before the TASK-129 commit. The TypeError tripwire note stays true in spirit: a state dict in slot.specs still fails loudly at the join (a dict cannot join into a string), so the loud failure the reviewer valued survives the naming.
<!-- SECTION:FINAL_SUMMARY:END -->
