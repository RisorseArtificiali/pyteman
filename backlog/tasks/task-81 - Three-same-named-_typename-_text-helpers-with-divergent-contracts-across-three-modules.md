---
id: TASK-81
title: >-
  Three same-named _typename/_text helpers with divergent contracts across three
  modules
status: Done
assignee: []
created_date: '2026-09-16 19:58'
updated_date: '2026-11-08 20:19'
labels:
  - rt-01
  - review-followup
  - maintainability
  - blocked-by-frozen-code
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Raised by the reuse and altitude passes of the RT-01 /simplify review.

Three functions named `_typename` and two named `_text` now exist across src/pyteman/rules.py, src/pyteman/patcher.py and src/pyteman/sitecustomize.py, and they do NOT share a contract. `patcher._typename` and `sitecustomize._typename` are guarded: they absorb a raising `__name__` lookup and a non-str result, returning "<unknown type>". `rules._typename` is the plain unguarded `type(value).__name__`.

No hole exists today, because a raise inside load_rules is caught by sitecustomize's "loading rules" phase handler. The cost is a maintenance trap with a silent failure mode: code moved or copied between these modules keeps compiling and quietly changes which contract it gets, and the one it can lose is the guarded one on the fail-closed path.

The patcher/sitecustomize duplication itself is deliberate and must NOT be removed by importing one from the other: sitecustomize must import no pyteman module when inert, and its first failure phase is literally "importing pyteman", where the package is by definition unavailable. That constraint is what makes naming, rather than consolidation, the likely fix for at least one of the three.

Deferred from the RT-01 tranche: rules.py is frozen under TASK-7 (APPROVED), and the orchestrator scoped the tranche to completing the RT-01 guarantees exactly.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The three modules' _typename/_text helpers are either renamed to reflect their differing contracts, or the guarded pair is given one canonical home that patcher.py imports
- [ ] #2 sitecustomize.py still imports no pyteman module when inert, proven by the existing sys.modules assertions
- [ ] #3 rules._typename's unguarded contract is either documented at its definition or the function is renamed so it cannot be mistaken for the guarded one
- [ ] #4 A comment or test records that the sitecustomize copy cannot import from the package, since its first failure phase is importing pyteman
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Merge blocked on a GitHub Actions dispatch outage (2026-09-27 ~05:00 CEST): the push of f7d7f92 and a PR close/reopen both produced no workflow run (last run on the branch is 3723d67's). All other gates are complete: /simplify two-agent findings applied (the first docstring draft claimed every call sits inside load_rules, false since TASK-140 made _rule_identity two-door; corrected to name both doors, and the first-failure-phase overclaim scoped to first package-touching phase); code-reviewer-typed high review CLEAN with every claim traced mechanically (byte-identical refusal messages proven by name-substitution diff); battery check clean, 1263 passed 2 skipped on the exact tree; independent review APPROVED at f7d7f92 (task81impl/review/FINDINGS-AND-VERDICT.md). PR #150 is open and waits for a green run for f7d7f92 before the squash merge; a session-scheduled check re-examines CI recovery and completes the merge when green.

Dispatch-outcome update (2026-09-27 ~05:25 CEST): GitHub's pull_request dispatch for this repository died again after completing PR #153's runs. Three PRs now carry this change: #150 (webhook died in the first outage window), #152 (replacement branch work/task140-id-validator + empty commit; its pull_request events stayed dead through close/reopen, a title edit, and a second empty commit, all while other branches dispatched), and #154 (current, open from the fresh branch work/task81-typename-contracts which carries the reviewed head f7d7f92 commit for commit; its opened event also produced no run). All gates remain complete and the review APPROVED at f7d7f92 stands; the merge waits for a green run on f7d7f92, with a session-scheduled check re-examining recovery. Push events to master still dispatch, so the post-merge validation will run once the pre-merge run does.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closure restored 2026-11-08 (tracker repair): the day-3 Done marker was lost to a working-tree revert; the work had landed. Landed by direct push a341833 (rules._typename renamed to _plain_typename with two-direction pins on the shim fixture, after three review deltas; superseded PR #168 closed with a pointer). Full chain in the durable handoff, sets fifty-seventh to fifty-eighth.
<!-- SECTION:FINAL_SUMMARY:END -->
