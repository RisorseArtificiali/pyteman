---
id: TASK-80
title: >-
  Validate rule expressions in Rule.__post_init__ so there is one compile site,
  not two
status: Done
assignee: []
created_date: '2026-09-16 19:57'
updated_date: '2026-09-29 21:44'
labels:
  - rt-01
  - review-followup
  - refactor
  - blocked-by-frozen-code
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Raised independently by the reuse and altitude passes of the RT-01 /simplify review, and deferred because the clean fix lives in frozen code.

`rules._expression` (src/pyteman/rules.py) and `patcher._compile` (src/pyteman/patcher.py:13) both compile a rule's `when` and `fire.key`, and both raise RuleError with DIFFERENT wording for the same defect: "rule #0 ('r1'): ..." from the loader against "rule 'bad': ... is not a valid expression: ..." from the patcher. The tests now pin both wordings separately, so the divergence is load-bearing rather than incidental.

The second compile site is correct for RT-01 and must not simply be deleted: compiling in Patcher.__init__ is what makes activation atomic, because __init__ is the only phase that mutates nothing, so a ruleset that cannot compile dies before the import hook is installed and before the first callable is replaced. The duplication is the symptom; the root cause is that a Rule can be constructed at all while carrying an expression that will not compile. Validating in Rule.__post_init__ means no unvalidated Rule exists, after which the patcher re-check becomes redundant rather than necessary.

Out of scope for the RT-01 tranche: src/pyteman/rules.py is frozen under TASK-7 (APPROVED), and the orchestrator scoped the tranche to completing the RT-01 guarantees exactly.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Rule.__post_init__ compiles when and fire.key and raises RuleError on a bad expression, so no Rule instance can carry an uncompilable expression
- [x] #2 A single error wording covers both entry points, and the tests that currently pin two different wordings are reconciled to it
- [x] #3 Patcher.__init__ still fails before install_hook for any ruleset it cannot use, with a test proving activation remains atomic
- [x] #4 load_rules error messages keep naming the rule index and id, so operator-facing diagnostics do not regress
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #115 #118. Added lines already present on master per PR: #115 6/76=7%  #118 14/137=10%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge.

Merged 2026-09-29 via #191 (e27723f). The branch was rebuilt by hand after the rebase stacked conflicts onto the TASK-56 core region. Evidence under /home/pantinor/pyteman-evidence/t191/: diff80.patch sha256 3aef5cfd, tree80-hold3.sha256, mutants-80*.log, VERDICT-80*.md in t191rev.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by PR #191, squash-merged as e27723f on master at 2026-09-29 21:44Z. AC1: Rule.__post_init__ compiles when and fire.key (type checks, non-empty checks, once_per-needs-key), so no Rule instance carries an uncompilable expression whatever door built it. AC2: one core text via a shared _invalid_expression helper, the loader prefixing index and id and firing first at load, construction naming the id through an inert render (a BoomStr id constructs and refuses cleanly); the shared-compile test's programmatic door moved from Patcher to construction. AC3: Patcher.__init__ still dies before the hook for rulesets it cannot use; duck-typed rules without stashes still compile at planning, pinned by test_activation_compiles_for_duck_typed_rules. AC4: load_rules keeps naming the index and id; the deliberate cost is one extra compile per expression on the load path, declined in review with that reason. The stash is provenance-checked by identity, not equality, so a rule mutated after construction (or mutated to a lying comparer) is compiled from what it now says. Supersedes #115 and #118, both closed with pointers. Gates at e86dd21: suite 1523 passed 2 skipped, check green, delivery 41, battery 10/10 (mutants-80f.log), code-review high eight findings applied or declined with reason, independent verdicts APPROVED at ccd636a and reissued at e86dd21 (VERDICT-80.md, VERDICT-80b.md).
<!-- SECTION:FINAL_SUMMARY:END -->
