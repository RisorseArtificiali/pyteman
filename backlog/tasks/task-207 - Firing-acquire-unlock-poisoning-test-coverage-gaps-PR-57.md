---
id: TASK-207
title: 'Firing acquire/unlock poisoning test coverage gaps (PR #57)'
status: Done
assignee: []
created_date: '2026-11-06 17:57'
updated_date: '2026-11-08 15:42'
labels:
  - pr-reconciliation
dependencies: []
references:
  - 'https://github.com/RisorseArtificiali/pyteman/pull/57'
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR #57 (open, CONFLICTING, presence 64%) closes coverage gaps in the acquire/unlock poisoning tests of the firing module. The 64% presence suggests part of the coverage landed via intervening merges; enumerate which gaps remain uncovered on master before reviving, and close with a pointer if none remain.
<!-- SECTION:DESCRIPTION:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by direct push 26b5b2d on master (base 8cba2a8); PR #57 closed with a pointer. Gap survey against today's master (not the PR's stale base, whose anchors had drifted): three of the PR's gaps remained open and all landed. The acquire-lock failure test now pins poisoning (_closed), the closed-refusal on a second record, the empty file (the write never happened), and its stub gates on LOCK_EX with a real_flock passthrough, so removing the acquire branch's poisoning goes red instead of being masked by the unlock arm. The unlock-failure test pins the lock release through a second instance taking LOCK_EX|LOCK_NB via the shared _assert_flock_released helper (used by all six probe sites; the PR would have added a seventh inline copy). A new test pins the unlock failure surviving a close failure, the unlock-promotion twin of the existing write-failure variant: the stubbed close runs the real os.close before raising, matching Linux semantics where a failing close has already released the fd's locks, so its release probe is meaningful. Gate chain: /simplify (two minors: header comment on the new test, idiom consistency), /code-review high over two rounds with a clean final verdict (its three test-strength findings drove the strengthening), delivery battery green at every shipping sha (last: 1622 collected, 1619 passed, 3 declared skips). Edit-script incident, no evidence lost: three anchor mismatches (comment prefix, message text, p variable) all caught by per-edit pytest runs before amends, applying the stored lesson.
<!-- SECTION:FINAL_SUMMARY:END -->
