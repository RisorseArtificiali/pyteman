---
id: TASK-205
title: 'Make tests'' Interrupting subclass UnreadableIdRule (PR #49)'
status: Done
assignee: []
created_date: '2026-11-06 17:57'
updated_date: '2026-11-08 11:14'
labels:
  - pr-reconciliation
dependencies: []
references:
  - 'https://github.com/RisorseArtificiali/pyteman/pull/49'
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR #49 (open, MERGEABLE, presence 0%) makes the tests' Interrupting exception subclass UnreadableIdRule so hostile-rule tests share one family. Test-only change; tiny candidate for the next reconciliation batch.
<!-- SECTION:DESCRIPTION:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by direct push abe62ab on master (base 9f2b87a); PR #49 closed with a pointer. The Interrupting stand-in in test_an_interrupt_while_reading_an_id_is_not_reported_as_a_bad_rule now subclasses UnreadableIdRule, replacing four hand-declared attribute lines with the two overrides that matter: the id property that raises KeyboardInterrupt on every read, and module/symbol, which the skeptic proved are rendered into the refusal note. The class docstring carries the real two-read mechanism, verified empirically: the first id read is swallowed by _rule_id's except BaseException placeholder, and it is the admission gate's re-read behind its Exception-shaped guard that the interrupt must escape; an id that raised only once would let the construction complete, so the every-read property is load-bearing and the test fails outright (DID NOT RAISE) without it. Gate chain: /simplify (one skip that the skeptic's evidence then vindicated), /code-review high over three rounds (five latent findings: two applied, two skips accepted by the reviewer, one folded; its empirical probe caught an inverted rationale sentence in the first docstring, corrected to the reviewer's pre-approved wording), skeptic 3/3 CONFIRMED with a source-mutation probe (widening _admitted_identity to BaseException reddens the test with exactly the regression its docstring describes), batteries green at every shipping sha (last: 1606 collected, 1603 passed, 3 declared skips).
<!-- SECTION:FINAL_SUMMARY:END -->
