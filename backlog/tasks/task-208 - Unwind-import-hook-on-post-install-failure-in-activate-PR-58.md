---
id: TASK-208
title: 'Unwind import hook on post-install failure in activate() (PR #58)'
status: Done
assignee: []
created_date: '2026-11-06 17:57'
updated_date: '2026-11-08 15:23'
labels:
  - pr-reconciliation
dependencies: []
references:
  - 'https://github.com/RisorseArtificiali/pyteman/pull/58'
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
PR #58 (open, CONFLICTING, presence 16%) unwinds the installed import hook when a post-install step fails inside activate(), so a failed activation does not leave a live hook with a half-built dispatcher (RT-01 fail-closed family). Real robustness fix, not cosmetics: verify current activate() still leaks the hook on post-install failure, then revive through the gate chain.
<!-- SECTION:DESCRIPTION:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by direct push 8cba2a8 on master (base d06a14a); PR #58 closed with a pointer, deepened past the PR's shape by the review. Premise verified with precision: the strand gap is structural (install() called outside activate's try) but unreachable in-tree today (install_hook's last two statements are the two assignments), which is why the fix went to the root cause the review's F2 identified: install() itself wraps install_hook in try/except BaseException, unwinding the hook (p.uninstall()) before re-raising on any post-swap failure, and running the same uninstall on a never-installed Patcher (returns empty, the same nothing-to-undo a caller's finally manages) on a pre-swap failure. That carries the guarantee to every install() caller present and future and lets activate() return to master's shape (install() outside its try; the loop try covers only what activate adds). The deliberately unguarded uninstall inside install()'s except is documented as living inside the thread-unsafety envelope (a re-entrant window could hand it another Patcher's hook). docs/rules.md names the install-step unwind. Three tests pin the promise at the doors: post-swap failure through activate and through install() directly, and a pre-swap failure leaving __import__ untouched; the code-review's mutation checks proved the try is pinned by both post-swap tests and that the pre-swap test's real load is uninstall() becoming strict. Gate chain: /simplify (S1 contract sentence, R1 handle argument, S2 paragraph merge, E302 applied), /code-review high over three rounds with a clean final verdict and two mutation checks, batteries green at every shipping sha (last: 1621 collected, 1618 passed, 3 declared skips).
<!-- SECTION:FINAL_SUMMARY:END -->
