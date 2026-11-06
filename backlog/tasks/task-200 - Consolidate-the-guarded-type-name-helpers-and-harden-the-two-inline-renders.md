---
id: TASK-200
title: Consolidate the guarded type-name helpers and harden the two inline renders
status: To Do
assignee: []
created_date: '2026-09-29 18:05'
updated_date: '2026-09-29 19:33'
labels:
  - follow-up
  - refactor
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Follow-ups filed the same turn the /simplify reports were read (2026-09-29, tree12 at 0c77f43). 1) pyteman now has three guarded type-name helpers with the same contract: patcher._typename, sitecustomize._typename (mandatory copy by the no-import promise) and targets._type_name (TASK-12). targets is the dependency floor and patcher.py already imports it, so patcher._typename could delegate to targets._type_name, leaving sitecustomize as the only deliberate copy; hostile_fixtures.PARITY_INPUTS plus the parity tests are the mechanism that keeps them honest and should grow a targets leg if the consolidation is declined. 2) Pre-existing, out of TASK-12's scope: the pragma execute-failure deferred diagnostic at actions.py ~293 renders type(con).__name__ inline and unguarded where con is a workload-resolved object; the same _type_name import would serve it. Blast radius today is contained by _safe_message collapsing to a diagnostic-unavailable record.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Either the three guarded helpers are two (patcher delegating to targets) or the parity tests explicitly cover all three
- [ ] #2 The execute-failure deferred render no longer renders a workload-controlled type name unguarded
- [ ] #3 Full suite and dev.py check green
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Added 2026-09-29 while reviving PR #77 (TASK-14.2): actions.py ~438 has a third guarded add_note shape (format plus add_note in one inline try, wording parallel to firing._annotate). If the leaf consolidation lands, this site can split like _annotate does or call a shared composer; left out of the TASK-14.2 revival to keep its diff at the two named sites.

Altitude review of the TASK-14.2 revival (2026-09-29): if a shared note composer ever lands for the parallel 'additionally, ... failed' renderings, it belongs in pyteman._note beside the guard, so the format contract rides with the attachment contract.

Code review of the TASK-14.2 revival (2026-09-29) confirmed the actions.py:_terminal site is the consolidation's missing third consumer and adds a second item for the same family: the two consumers' degradation philosophies diverge (firing._annotate drops the note silently on a hostile secondary; the patcher degrades to an informative note, and sitecustomize announces unavailable notes). Converging firing onto patcher's _text/_typename is blocked by the startup-weight contract (sitecustomize imports firing lazily to stay off the patcher chain), so any convergence must be local to firing, e.g. a degraded note built from the internally-built label.
<!-- SECTION:NOTES:END -->
