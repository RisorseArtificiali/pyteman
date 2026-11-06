---
id: TASK-194
title: Opt-in strict mode that refuses a run when a rule never lands
status: To Do
assignee: []
created_date: '2026-09-29 06:01'
labels:
  - audit-2026-09-16
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by the /simplify altitude review on TASK-161, 2026-09-29. A rule still pending at exit only writes 'pyteman: never landed: <rule>' to stderr (src/pyteman/sitecustomize.py:215-237) and never changes the exit code, as docs/rules.md:460-461 promises. Every startup control in the suite therefore proves landing on its own terms (a manual stderr check in test_coroutine_entry.py, test_lazy_walk.py, test_unreadable_point.py and test_activation_suspendable_startup.py), and a new control that forgets the check passes vacuously. Operators have the same exposure. Options: a PYTEMAN_STRICT_LANDING=1 mode following the PYTEMAN_STRICT_PRAGMA and PYTEMAN_STRICT_BARRIER pattern that makes the pending report exit non-zero, or a narrower opt-in expect_all_landed flag on tests/startup_harness.run_py. This is a product decision because the docs promise the exit code is unchanged.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The choice between a runtime strict mode, a harness-only assertion, or no change is recorded with its reasons
- [ ] #2 If a mode is added, a run with a pending rule exits non-zero under it and unchanged without it, and docs/rules.md describes both
<!-- AC:END -->
