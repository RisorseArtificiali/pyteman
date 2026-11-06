---
id: TASK-179
title: >-
  Test discrimination gaps in the TASK-178 coroutine-entry suite: mixed
  entry+exit install, extend-site guard, message pinning, RAN marker
status: Done
assignee: []
created_date: '2026-09-27 00:15'
updated_date: '2026-09-27 00:04'
labels:
  - review-followup
  - task-178
  - tests
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
From the TASK-178 post-verdict code review (2026-09-26/27 night, high effort,
independent re-review of 8b2562e). The implementation itself probed correct on
every adversarial scenario (install-site refusal, extend-site refusal via the
alias road, entry merge, override, cancellation, exception); the gaps are all
in what the SUITE would fail to notice, plus one docs contradiction split out
as TASK-180.

1. **The install-site `all(spec[0].event == "entry")` guard has no mutation
   discriminator** (patcher.py:2238). No test activates a mixed entry+exit
   ruleset on ONE coroutine target. Mutating `all()` to `any()` keeps the whole
   battery green while a mixed ruleset installs the coroutine dispatcher with
   an exit rule in `comp.exits` that never fires (the silent-drop class the
   guard exists to prevent). Add a test: ruleset [entry e1, exit x1] on one
   coroutine target raises SuspendableTargetError with the split message.
2. **The extend-site guard has zero coverage** (patcher.py:2719). No test makes
   a second `_patch` reach an already-installed coroutine dispatcher (alias
   road: `modB.afn = modA.afn` after install, then re-patch). Deleting the
   guard keeps the suite green. Add a test that merges an exit rule through
   that road and asserts the refusal (and that the live dispatcher is
   unchanged), plus an entry-merge case.
3. **The extend-site copy of the split refusal message is pinned by no test**
   (patcher.py:2721 hardcodes the phrase the install site interpolates at
   2255). The two can drift; docs/rules.md quotes the message verbatim. Either
   pin both by test or extract one shared message builder.
4. **`test_entry_override_on_a_coroutine_target_is_returned` cannot detect the
   original body running before the override is returned**
   (tests/test_coroutine_entry.py:98). The fixture `afn` is pure, so
   `await original()` before `return override` still passes. Add an observable
   side effect (a RAN marker like the sync-path tests use).
5. **Design note to carry into any tier-2 work**: the extend guard discriminates
   on `inspect.iscoroutinefunction(dispatcher)`, an implicit property of the
   wrapper's spelling rather than an explicit marker set at build time; the
   coupling is spread across three comments (2180-2184, 2681-2685, 2713-2717).
   If a future dispatcher kind is also an `async def`, revisit toward one
   explicit marker.

Related: the pre-existing comment at patcher.py:2199 ("an ordinary synchronous
function") is now false for coroutine dispatchers; fold its rewording into
whichever task touches that loop next (covered by TASK-180's docs pass or this
one, whichever goes first).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A mixed entry+exit ruleset on one coroutine target is refused by a test that fails when `all()` becomes `any()`
- [x] #2 The extend-site refusal and entry-merge are covered through the alias (or equivalent second-patch) road
- [x] #3 Both copies of the split message cannot drift silently (shared builder or both pinned)
- [x] #4 The override test fails if the original body runs
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Merged-state: commit 7eef59e on branch work/task178-followups (rebased onto ce9a350), PR #145. Independent review (task179impl/review/FINDINGS-AND-VERDICT.md): APPROVED at 7eef59e, every pinned contract point verified with mutation kills (any(), guard deletion, override-await) and the builder unification checked byte-exact against both base literals. Three filed findings: F1 (info, procedural) mutation runs on this subprocess-real suite need a fresh editable venv in the throwaway copy, because sitecustomize's `import pyteman` resolves through the venv .pth to the original tree; recorded in the project memory editable-install-pins-one-src-path. F2 (nit) the docs-fence tie asserts containment, not equality; direction is right. F3 (nit) the closing paragraph's 'awaits on your behalf' summarizes the no-override path; the override's discarded coroutine is documented earlier in the section.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Merged as 97c71ce via PR #145 (squash of the rebased 7eef59e). Review APPROVED at 7eef59e with mutation kills verified under fresh-venv runs (any(), guard deletion, override-await), the builder checked byte-exact against both base literals, and all five pinned contract points confirmed. Gates: /simplify 4-angle findings applied; code-reviewer-typed high review with its one note applied (await-or-iterate verb); battery check clean, 1251 passed 2 skipped at the rebased head; PR CI all seven jobs green; master CI green.
<!-- SECTION:FINAL_SUMMARY:END -->
