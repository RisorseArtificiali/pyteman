---
id: TASK-158
title: The three patch-time refusals share no base and none is exported
status: To Do
assignee: []
created_date: '2026-09-17 11:20'
updated_date: '2026-09-28 18:16'
labels:
  - audit-2026-09-16
  - opus-5
  - altitude-gate
  - task-3-followup
dependencies: []
references:
  - 'src/pyteman/patcher.py:477'
  - 'src/pyteman/patcher.py:495'
  - 'src/pyteman/patcher.py:524'
  - src/pyteman/__init__.py
  - 'docs/rules.md:542'
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Altitude gate on TASK-3, 2026-09-17.

The three patch-time refusals at src/pyteman/patcher.py:477, :495 and :524 each subclass RuntimeError directly. That base is correct and consistent, and rules.RuleError(Exception) is correctly in a different category as a load-time input error. The gap is one level up: the three share no common base, and none of them is exported from the package, which contains only __version__.

docs/rules.md:542 and :558 name SuspendableTargetError to operators, and the class docstring tells them in so many words that the RuntimeError base is what lets an `except Exception` around an import swallow it. That advice is not actionable today. An operator who wants to catch "pyteman refused to install" must either import pyteman.patcher directly and name three classes, or catch RuntimeError, which is far broader than the thing they mean.

The fix is one base class subclassing RuntimeError, the three refusals subclassing it, and re-exports at package level. It breaks no existing `except RuntimeError` and no existing `except Exception`, because the new base sits between.

Out of scope for TASK-3, which did not create this shape and only added the third member. Filed because the documentation written in TASK-3 is what makes the gap visible to operators.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Esiste una base comune per i rifiuti a tempo di patch, sottoclasse di RuntimeError, e i tre rifiuti esistenti la ereditano.
- [ ] #2 La base e' esportata a livello di pacchetto, cosi' un operatore puo' catturarla senza importare pyteman.patcher.
- [ ] #3 Nessun except RuntimeError o except Exception esistente cambia comportamento: la nuova base sta in mezzo.
- [ ] #4 docs/rules.md indica la base come il modo di catturare 'pyteman ha rifiutato di installare', invece di lasciare l'operatore a nominare tre classi.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #55. Added lines already present on master per PR: #55 0/32=0%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
PR #55: https://github.com/RisorseArtificiali/pyteman/pull/55\nBranch: work/patch-refusal-base (commit b5eb307 on master at 3a38482).\n\nAdded PatchRefusalError(RuntimeError) as a common base for SlotOwnershipError, SuspendableTargetError, and UnsupportedTargetError. Exported lazily from the package via __getattr__ (PEP 562), so `import pyteman` still loads only __init__.py. docs/rules.md names PatchRefusalError as the catch-all with a code example. No existing except handler changes behavior.\n\nGate evidence: /simplify (3 agents, no findings), code-review high (pending), 1190 passed 2 skipped.
<!-- SECTION:FINAL_SUMMARY:END -->
