---
id: TASK-210
title: 'Load README YAML examples through load_rules in tests (PR #81)'
status: Done
assignee: []
created_date: '2026-11-06 17:57'
updated_date: '2026-11-08 13:09'
labels:
  - pr-reconciliation
dependencies: []
references:
  - 'https://github.com/RisorseArtificiali/pyteman/pull/81'
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR #81 (open, MERGEABLE, presence 27%) loads the README's YAML rule examples through load_rules in the test suite, so documentation examples cannot drift from the accepted schema. Overlap check against merged #211 (README degradation placeholders dedup) before revival; the README changed shape after this PR was cut.
<!-- SECTION:DESCRIPTION:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by direct push 84921c6 on master (base e6b99a2); PR #81 closed with a pointer. The README's yaml examples load through the real load_rules, mirroring the reference doc's existing bar via two shared helpers: _yaml_blocks (the one extractor deciding what counts as a loadable example) and _loaded (the one write-and-load materializer), so neither the regex nor the body exists twice. The quickstart walkthrough's block joined the bar (two independent measurements confirmed it loads as-is: ids fail-third-checkout, slow-notify), making the module docstring's claim true over all three yaml-bearing docs instead of narrowing the wording around an exclusion; the module docstring now names all three and why. The new guards pin EXACT counts (README == 2, quickstart == 1), because the review proved a floor lets a whole fenced example be removed silently after a doc legitimately grows; the pre-existing rules.md floor-3 guard (which a removal does trip) is left in its established shape. README.md and docs/quickstart.md joined READ_BY_THE_SUITE in the packaging tests (the parallel-dispatch registry my first version missed, caught by review), the CITED comment that the delta staled was corrected, and the new reads carry encoding="utf-8". Gate chain: /simplify (four copy-not-extract findings), /code-review high over two rounds clean with both record-only observations handled, skeptic 4/4 CONFIRMED (schema mutation names the failing block; fence deletion trips the guard; a blinded extractor trips both floors while the parametrizations silently skip, the exact loss mode the floors exist for), batteries green at every shipping sha (last: 1615 collected, 1612 passed, 3 declared skips).
<!-- SECTION:FINAL_SUMMARY:END -->
