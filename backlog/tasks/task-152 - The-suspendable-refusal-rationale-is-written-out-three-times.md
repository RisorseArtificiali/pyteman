---
id: TASK-152
title: The suspendable-refusal rationale is written out three times
status: Done
assignee:
  - tree-28
created_date: '2026-09-17 11:11'
updated_date: '2026-11-08 20:21'
labels:
  - audit-2026-09-16
  - opus-5
  - reuse-gate
  - task-3-followup
  - docs
dependencies: []
references:
  - 'src/pyteman/patcher.py:524-613'
  - 'docs/rules.md:524-607'
  - 'tests/test_activation_atomic.py:4011-4033'
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Reuse gate on TASK-3, 2026-09-17.

Roughly 183 lines carry one argument three times, paragraph for paragraph and in places sentence for sentence, across src/pyteman/patcher.py 524-560 and 575-613, docs/rules.md 524-607, and the section comment in tests/test_activation_atomic.py 4011-4033.

Measured overlaps reported by the gate:
- patcher 535-539 against docs 535-539, the discarded-coroutine sentence, differing only in "the caller gets an int" against "Your caller gets the value you configured".
- patcher 541-547 against docs 561-566, the refused-not-skipped argument.
- patcher 549-555 against docs 550-559, the startup against import-hook reach including the `except Exception` swallow.
- patcher 582-590 against docs 575-582 against the test comment 4023-4033, the __wrapped__-is-provenance argument, with the same two examples and the same closing appeal to CPython's own iscoroutinefunction.
- patcher 592-598 against docs 584-588, the partial step being narrower than it looks.
- patcher 607-613 against docs 595-602, what the gate does not promise.

The codebase already has the cross-reference idiom for this, at patcher.py:369, patcher.py:1001 and patcher.py:1765, all of which point at a named section of docs/rules.md rather than restating it. The SlotOwnershipError section at docs/rules.md 473-485 is the counter-example done right: thirteen lines stating the contract without re-deriving the rollback machinery.

Within docs/rules.md itself there is a fourth copy: lines 550-559 restate what the section "Where each check happens" at lines 9-39 already says, namely the exit-2 behaviour with the workload never started (line 13), the site.execsitecustomize `except Exception` swallow (lines 18-22), and the atomic-rollback guarantee (lines 27-30).

Cost: any correction to the reasoning has to land in three files and nothing ties them mechanically. tests/test_docs_rules.py only loads the yaml blocks and pins two numeric constants, so this prose is unchecked by the suite. This is the same defect class as the already-filed prose-duplication item but roughly six times larger.

Not to be resolved by deleting the argument. The three audiences are different: the docstring serves a maintainer reading the classifier, the doc serves an operator writing rules, the test comment serves someone deciding whether a case is still needed. The work is to pick one canonical home per claim and leave pointers, the way patcher.py:369 already does.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Ogni affermazione del razionale ha una sola casa canonica; le altre due sedi puntano alla sezione per nome, secondo l'idioma gia' presente a patcher.py:369 e 1001.
- [ ] #2 La correzione su __wrapped__ richiesta dal revisore resta leggibile in docs/rules.md e nel piano di TASK-3 dopo il consolidamento; non viene persa nella deduplicazione.
- [ ] #3 docs/rules.md 550-559 non ripete l'exit 2, lo swallow di except Exception e il rollback gia' descritti in 'Where each check happens'; rinvia a quella sezione.
- [ ] #4 La suite continua a passare e nessun test che cita il testo di docs/rules.md smette di trovare cio' che cita.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #71. Added lines already present on master per PR: #71 0/50=0%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closure restored 2026-11-08 (tracker repair): the day-3 Done marker was lost to a working-tree revert; the work had landed. Landed by direct push 85958fa after three review rounds (simplify eight findings, code-review high, skeptic with source-level SQLite reading); superseded PR #71 closed with a pointer. Full chain in the durable handoff, set fifty-fifth.
<!-- SECTION:FINAL_SUMMARY:END -->
