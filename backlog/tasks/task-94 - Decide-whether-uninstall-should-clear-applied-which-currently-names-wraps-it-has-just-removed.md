---
id: TASK-94
title: >-
  Decide whether uninstall() should clear applied, which currently names wraps
  it has just removed
status: Done
assignee: []
created_date: '2026-09-16 21:36'
updated_date: '2026-09-29 22:58'
labels:
  - rt-01
  - review-followup
  - audit-2026-09-16
  - patcher
  - design-decision
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Raised by the high-effort code review gate on RT-01 and labelled uncertain by the reviewer. Verified: `applied` has no production reader anywhere in the package. `grep -rn '\.applied' --include=*.py` returns only the two assignments in patcher.py and three test assertions.

`_patch` maintains a careful invariant: a name is appended to `self.applied` only after the whole module is wrapped successfully, so a rolled-back module never leaves a name behind. `tests/test_activation_atomic.py:137` asserts exactly that, with the comment "a name left here for a wrap that was rolled back would describe an experiment that never ran".

`uninstall()` does not maintain it. In the `test_activate_rolls_back_a_module_it_had_already_finished` shape, module one publishes `pyteman_atomic_victim:ok` into `applied`, module two fails, `activate` calls `uninstall()`, which restores the wrap and clears `_wrapped` but leaves `applied` naming a callable that is no longer wrapped.

There is no operator-visible impact today, because `activate` re-raises and the `Patcher` is unreachable afterwards. It becomes visible the moment anything inspects a `Patcher` after a failed `activate`, or `uninstall` grows a caller that reports afterwards.

TASK-1 added a paragraph to `uninstall`'s docstring stating the current semantics (cumulative record, scoped invariant, read `_wrapped` for live state) rather than changing behaviour, because clearing `applied` is a behaviour change outside the RT-01 guarantee and the runner is owned by another agent. This task is to make that a decision rather than a description.

Recommendation: clear it. The name `applied` reads as present tense at every call site, and a cumulative record that looks like live state is the kind of thing that is correct until the first reader assumes otherwise. The docstring paragraph is then replaced by the clearing, not kept alongside it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A decision is recorded: either uninstall() clears applied alongside _wrapped, or applied is confirmed as a cumulative record and the docstring wording added under TASK-1 stands as the contract
- [x] #2 If applied is cleared, tests/test_patcher.py still passes, since both of its assertions read applied while the patcher is live
- [x] #3 Whichever way it goes, a test pins the chosen behaviour across a successful _patch followed by uninstall, which no test covers today
- [ ] #4 If the runner ever grows a reader of applied, that reader is checked against the chosen semantics in the same change
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #84 #127. Added lines already present on master per PR: #84 6/40=15%  #127 6/21=28%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.

Merged 2026-09-29 via #193 (352f418). Evidence under /home/pantinor/pyteman-evidence/t191/: diff94.patch sha256 789d3d87, tree94-hold2.sha256, mutants-94*.log, VERDICT-94.md in t191rev.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by PR #193, squash-merged as 352f418 on master at 2026-09-29 22:57Z. AC1: the decision is recorded and implemented, uninstall() clears applied (alongside _pending, before the restore walk); the TASK-1 docstring paragraph is replaced by the clearing and its honest contract. AC2: tests/test_patcher.py passes, both live-state assertions untouched, plus a new force-route pin in try/finally. AC3: the behaviour is pinned on both routes (activate in test_activation_atomic, install+force_patch_module in test_patcher) and on the refused-restore divergence (ledger keeps the entry for the retry, applied clears anyway; the refusing fixture), and the user-facing rules.md contract teaches the new semantics including the two corners that keep a populated list from being a live view and the refused-restore reading. AC4: the runner still has no reader of applied (re-verified during the revival); the reviewer's two informational notes are recorded here with the decision: the mid-restore window (a re-entrant reader sees applied empty while its own wrap is torn down, a wash against the old behaviour's opposite lie) and the clear's before-the-walk position being deliberate, because a post-walk clear would wipe a raced publication's name while its wrap stays live, pinnable only by a threaded test the suite rightly avoids. Supersedes #84 and #127, both closed with pointers. Gates at 82ed9a9: suite 1527 passed 2 skipped, check green, delivery 41, battery 3/3 (mutants-94c.log), code-review high five findings applied, independent verdict APPROVED (VERDICT-94.md).
<!-- SECTION:FINAL_SUMMARY:END -->
