---
id: TASK-212
title: Strict-mode and run-id PYTEMAN_* variables still propagate into test children
status: To Do
assignee: []
created_date: '2026-11-07 18:29'
updated_date: '2026-11-08 17:15'
labels:
  - tests
  - review-finding
dependencies: []
references:
  - tests/startup_harness.py
  - src/pyteman/pragmas.py
  - src/pyteman/barriers.py
  - src/pyteman/firing.py
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Filed from the TASK-144 review chain (2026-11-07): startup_harness.CLEARED_IN_CHILD covers the three activation variables (PYTEMAN_RULES, PYTEMAN_LOG, PYTEMAN_REQUIRE_MARKER), but the package reads three more PYTEMAN_* variables that still propagate into test children: PYTEMAN_STRICT_PRAGMA (src/pyteman/pragmas.py:291), PYTEMAN_STRICT_BARRIER (src/pyteman/barriers.py:82), PYTEMAN_RUN_ID (src/pyteman/firing.py:147). They cannot activate instrumentation alone, but a developer who exports one still alters the behavior of children the tests activate via env_extra (strict refusals and run attribution can become environment-dependent). Fix: add them to CLEARED_IN_CHILD (or a second tuple with its own rationale for the behavior-vs-activation boundary) and extend the discriminating test; the merge-after-filter route keeps deliberate supply working.
<!-- SECTION:DESCRIPTION:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-11-08 frontmatter completion (from the whole-project code review): this file lacked the updated_date and priority fields its sibling review-finding tasks carry; both added via this edit (priority Low to match the family). No content change.
<!-- SECTION:NOTES:END -->
