---
id: TASK-212
title: Strict-mode and run-id PYTEMAN_* variables still propagate into test children
status: Done
assignee: []
created_date: '2026-11-07 18:29'
updated_date: '2026-11-09 03:22'
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

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Landed on master as ec63fd1 (2026-11-09, set 77). The six PYTEMAN_* variables the runtime reads are cleared on every surface: run_py children through the harness's second tuple CLEARED_BEHAVIOR_IN_CHILD (the behavior-vs-activation boundary stated at the filter, union named once and shared), script children through scripts/_common.py whose child_env was REORDERED to clearing-first (a live probe exposed the old order silently clearing what extra supplied, so deliberate supply was impossible; no caller supplied a PYTEMAN_* name, and extra now beats also_clear too, documented and pinned), and the test process itself through a conftest autouse fixture sharing one harness helper (clear_ambient_pyteman). Acceptance measured both ways: 43 of 1633 suite tests failed under an exported strict pragma before the fix; the full suite runs 1632 passed, 3 skipped with all three behavior variables exported after. Defense in depth is shipped as pins: a drift pin scanning every literal PYTEMAN_ name under the package sources for exact set equality with the union (class admitting digits and lowercase; the runtime-assembled-name residual stated), a parity pin tying _common's tuples to the harness's, and a child_env contract test (ambient cleared with all six set, deliberate supply survives, extra beats also_clear). The escape leg derives per-index sentinels and child code from the tuple. docs/coverage.md names six. Gates: /simplify applied; /code-review high three rounds (6, 5, 2 findings, all applied or answered; the prefix-sweep alternative rejected with recorded reasons, its drift scenario answered by the literal pin; the coroutine rig's wholesale os.environ spread closed by the autouse, its refactor not taken); skeptic CONFIRMED all five claims with independent probes (fixture removal returning the 16 failures, both child_env orders reconstructed, the drift pin fired on a fake seventh read and restored byte-exact, the sentinel copy-paste mutation caught, byte identity including commit==patch). Batteries green on every candidate (final 5ivdulv4, floor 1627).
<!-- SECTION:FINAL_SUMMARY:END -->
