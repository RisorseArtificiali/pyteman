---
id: TASK-135
title: 'CI: repin actions off node20 ahead of the 2026-09-23 runner removal'
status: To Do
assignee: []
created_date: '2026-09-17 07:47'
updated_date: '2026-09-28 18:16'
labels:
  - ci
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
All three jobs in .github/workflows/tests.yml (test, artifact, coverage) pin actions whose action.yml still declares `using: node20`. This is maintenance hygiene with a known date attached. It is NOT a hard breakage, and an earlier version of this task said it was. That claim is withdrawn below, with the evidence that refutes it.

Verified on 2026-09-17 by reading action.yml at the pinned ref rather than trusting the tag number:

    gh api repos/actions/checkout/contents/action.yml?ref=v4      -> runs: using: node20
    gh api repos/actions/setup-python/contents/action.yml?ref=v5  -> runs: using: 'node20'
    actions/checkout latest release     -> v7.0.1
    actions/setup-python latest release -> v7.0.0

**Withdrawn claim.** The first version of this task said the steps would fail from 2026-09-23 and take all jobs red, with no fallback and no automigration. That is not supported. It was written from the removal date alone without reading how the runner resolves the version, and it was corrected after a peer session challenged the source.

**What the primary sources actually say.** The changelog at
https://github.blog/changelog/2025-09-19-deprecation-of-node-20-on-github-actions-runners/
records three dates and an escape hatch: runners default to Node24 from 2026-06-16, `ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION=true` opts back to Node20 after that, and Node20 is removed from the runner on 2026-09-23, at which point the opt-out stops working. That already describes substitution rather than a stop.

The runner source confirms it and is the stronger evidence, read at tag v2.337.0, the current release. `HandlerFactory.Create` intercepts an action declaring node20, calls `NodeUtil.DetermineActionsNodeVersion`, and records the result as an upgrade:

    // Action was upgraded from node20 to node24
    executionContext.Global.UpgradedToNode24Actions?.Add(actionName);

And the branch that the 2026-09-23 flag flips is the first statement of that function:

    // Phase 3: Always use Node 24 regardless of environment variables
    if (requireNode24)
    {
        return (Constants.Runner.NodeMigration.Node24, null);
    }

So a node20-declaring action is rewritten to Node24 and run. There is no failure path for the declaration itself. The only failure branch in that region is the unrelated ARM32 kill switch.

Corroborating: today is already past 2026-06-16, so these two actions are being run on Node24 right now. If the substitution broke them the breakage would already be visible rather than pending.

**What is actually left.** Deprecation annotations in the log while `warnOnNode20` is set, a runtime the pinned majors do not declare and are therefore not tested against by their own maintainers, and four majors of drift on both actions. Repinning is worth doing and is not urgent.

**Scope note.** Found while reviewing the coverage job added under TASK-34.1. The same pins sit in the test and artifact jobs, which are a previously reviewed and frozen tranche, so repinning only the coverage job would leave the file inconsistent. The change belongs to whoever owns the workflow as a whole. publish.yml was not examined and may carry the same pins.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every `uses:` in .github/workflows/tests.yml resolves to an action major whose action.yml declares a runtime later than node20, verified by reading action.yml at the pinned ref rather than by the tag number
- [ ] #2 .github/workflows/publish.yml is checked for the same pins and repinned or explicitly recorded as clear
- [ ] #3 The three jobs still pass on the repinned actions, confirmed by an actual run rather than by inspection
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
CI PR20 del2026-09-22, run35751295475, conferma ancora avvisi Node20 forzato aNode24 per checkout@v4/setup-python@v5 ma tutti7job SUCCESS. TASK-173 aggiunge quality con checkout@v4 e setup-uv SHA v9.0.0, quindi includere anche quality nel successivo audit dei pin. Nessun repin eseguito nella consegna tooling. Runner annuncia inoltre migrazione ubuntu-latest aUbuntu26 dal2026-10-19; trattare come avviso di piattaforma, non prova di rottura.

Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #24. Added lines already present on master per PR: #24 0/9=0%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
PR#24 (work/ci-repin-node24, commit acb9d01) opened and CI run 36127657789 all 7 jobs SUCCESS. checkout v4->v7, setup-python v5->v7, setup-uv v5->v7 (publish.yml). Every pin verified by reading action.yml at the pinned ref: all declare node24 or composite. pypa/gh-action-pypi-publish@release/v1 is composite, no node. Gate-exempt: configuration-only change.
<!-- SECTION:FINAL_SUMMARY:END -->
