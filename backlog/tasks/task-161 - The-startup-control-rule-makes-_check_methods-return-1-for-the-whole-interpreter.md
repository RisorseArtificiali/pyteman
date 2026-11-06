---
id: TASK-161
title: >-
  The startup control rule makes _check_methods return 1 for the whole
  interpreter
status: Done
assignee: []
created_date: '2026-09-17 11:39'
updated_date: '2026-09-29 06:31'
labels:
  - audit-2026-09-16
  - opus-5
  - task-3-followup
  - code-review-gate
dependencies: []
references:
  - 'tests/test_activation_suspendable_startup.py:36-41'
  - 'tests/test_activation_suspendable_startup.py:31'
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by the code review gate on TASK-3, 2026-09-17. Latent fragility in the control test, not a live failure.

tests/test_activation_suspendable_startup.py:36-41 patches `_collections_abc._check_methods` with an entry action returning 1. That function is the shared implementation behind every abstract base class `__subclasshook__` in `_collections_abc`. Forcing it to return 1 makes `issubclass` answer truthy for every ABC in that module, interpreter-wide, for the whole life of the controlled subprocess.

The control survives only because its workload is `print('WORKLOAD_RAN')`, which performs no `isinstance` or `issubclass` check against a `collections.abc` type. Any future edit to WORKLOAD that touches a container protocol, or any import added to the subprocess that does so during startup, changes the meaning of the control without changing its assertions. It would still exit 0 and still print, for a reason that has nothing to do with the point being patchable.

The control itself is necessary and must not be removed: without it every refusal assertion in the file passes vacuously, and its claim cannot be made in-process because the deciding frame is `site.execsitecustomize`.

The fix is to choose a control point with the same startup timing and the same patchability, but no interpreter-wide semantic effect, or to keep the point and pin the workload so a later edit cannot silently widen it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Il punto di controllo a startup non altera la semantica di un protocollo condiviso per l'intero interprete, oppure il workload e' vincolato in modo che una modifica successiva non possa dipendere da quel protocollo senza fallire visibilmente.
- [x] #2 Il controllo resta presente e non vacuo: senza di esso le asserzioni di rifiuto nello stesso file passerebbero per costruzione, e la sua affermazione continua a essere misurata in un interprete reale.
- [x] #3 La ragione della scelta del punto e' scritta accanto alla regola, cosi' che un lettore successivo sappia quali proprieta' deve conservare un punto sostitutivo.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #80 #82 #83 #123. Added lines already present on master per PR: #80 0/7=0%  #82 0/8=0%  #83 0/17=0%  #123 0/10=0%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Merged as #185 (squash 1e8a88c). The startup control point moved from _collections_abc._check_methods to _collections_abc.Generator.close (from #123), with a rationale next to the rule, and the control now asserts the rule landed (no 'pyteman: never landed' on stderr). Gates: full suite 1436 passed + 2 known skips, dev.py check, delivery tests 41 passed, mutation battery (never-landing point killed), /simplify, code-review high (one wrong rationale sentence fixed), independent reviewer APPROVED at f40464f (VERDICT161.md), CI 7/7 green. Reviewer Low finding F1 filed as TASK-195. Duplicates #80 #82 #83 #123 closed with a pointer.
<!-- SECTION:FINAL_SUMMARY:END -->
