---
id: TASK-89
title: >-
  The wrapper's signature-context guard is the disjunction of the two guards
  inside it
status: Done
assignee: []
created_date: '2026-09-16 21:17'
updated_date: '2026-09-30 17:39'
labels:
  - rt-01
  - review-followup
  - audit-2026-09-16
  - patcher
  - cleanup
dependencies: []
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Raised by the simplification angle of the RT-01 simplify gate. Pre-existing code, not part of the RT-01 change, so it was filed rather than fixed inside a tranche whose ownership perimeter does not cover gratuitous edits.

In `patcher._make_wrapper`, the per-call wrapper currently reads:

    if sig is not None or sig_unparseable:
        # Only param:-targeted rules pay for the ctx entry.
        if sig is not None:
            ctx["_signature"] = sig
        if sig_unparseable:
            ctx["_signature_unparseable"] = True

The outer condition is exactly the disjunction of the two inner ones, so it decides nothing the inner guards do not decide again. It is also true that the two flags are mutually exclusive by construction: `sig_unparseable` is set only in the `except` that also sets `sig = None`, so they can never both hold.

Both facts collapse the block to:

    if sig is not None:
        ctx["_signature"] = sig
    elif sig_unparseable:
        ctx["_signature_unparseable"] = True

This is on the per-call hot path of every wrapped callable, so the outer test runs once per invocation of every instrumented function, including the overwhelmingly common case where the rule has no `param:` target and both flags are falsy. The saving per call is small; the readability gain is that the mutual exclusivity becomes visible in the control flow instead of being a property a reader has to reconstruct from the assignment site thirty lines up.

Worth stating explicitly so the next reader does not undo it: the outer guard reads like an optimisation that skips two tests, and it is not, because falling through it costs the same two tests it was trying to avoid.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The wrapper's signature-context block is a single two-branch conditional rather than an outer guard wrapping two inner ones
- [x] #2 The mutual exclusivity of sig and sig_unparseable is stated where a reader can see it, in a comment at the point they are assigned in _make_wrapper
- [x] #3 Every existing param: target test still passes, including the one covering an unintrospectable callable, with no change to what lands in ctx
- [x] #4 The change is measured on the per-call path and is not slower than what it replaces
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #44. Added lines already present on master per PR: #44 0/2=0%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.

Merged 2026-09-30 via #212 (9c661fd). Evidence under /home/pantinor/pyteman-evidence/t191/: diff89.patch sha256 3428afce, tree89-hold1.sha256, bench89.py, VERDICT-89.md in t191rev.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by PR #212, squash-merged as 9c661fd on master at 2026-09-30 17:38Z. AC1: _seed_ctx's signature-context block is a single two-branch conditional; the disjunction is structural. AC2: the mutual exclusivity is stated at the assignment site in _bind_specs and at the seed site. AC3: every param: test passes unchanged, the unintrospectable-callable coverage included. AC4: measured interleaved on the per-call path, the elif and the two-if shapes are within noise. Supersedes #44 in design, applied at the current locations after the seeding moved; #44 closed with a pointer. Gates at 677b9cd: suite 1552 passed 3 skipped, check green, delivery 41, no battery (the two shapes are behaviour-identical by the documented exclusivity; the interleaved measurement is the AC4 evidence), independent verdict APPROVED (VERDICT-89.md).
<!-- SECTION:FINAL_SUMMARY:END -->
