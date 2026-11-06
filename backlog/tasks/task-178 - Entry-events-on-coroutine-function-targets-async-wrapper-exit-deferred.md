---
id: TASK-178
title: 'Entry events on coroutine function targets (async wrapper, exit deferred)'
status: Done
assignee:
  - pyteman-coordinator
created_date: '2026-09-26 18:42'
updated_date: '2026-09-26 21:49'
labels:
  - patcher
  - feature
  - async
  - filed-by-ccgram
dependencies: []
references:
  - src/pyteman/patcher.py
  - docs/rules.md
  - /home/pantinor/pyteman-evidence/task178-verify/
  - 'https://github.com/RisorseArtificiali/pyteman/pull/23'
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Feature request from the ccgram session (their TASK-43, filed here with coordinator verification). Rule points cannot target coroutine functions: pointing a rule at an async def (their case aiolimiter.AsyncLimiter.acquire, entry + sleep action) is refused at patch time with SuspendableTargetError "is a coroutine function, so entry and exit cannot be timed on it; refused rather than installed". Coordinator reproduced on master fa6ac68 with point asyncio.sleep: identical refusal, evidence /home/pantinor/pyteman-evidence/task178-verify/ (rules.yaml, err.txt, exit 1).

Why it matters: hangs in asyncio systems live exactly on async def seams (rate-limiter token acquire, dispatch entry, the send itself). The reporter is diagnosing a 7-hour delivery-queue wedge with zero log lines, candidate a never-resolving await in dispatch or a per-user lock leak, and every seam they need to stall is a coroutine function. Today they monkeypatch the seams directly, which reproduces but loses the firing log, run/instance identity, and re-arm semantics pyteman gives on sync targets.

Suggested shape from the reporter (take or leave): entry-only as a first-class for coroutine targets, an async wrapper that runs the action then awaits the original coroutine; exit coverage deferred (needs wrapping the returned awaitable, cancellation and GeneratorExit paths). Detection already exists (the refusal proves it); split the refuse message into entry-only-available versus exit-unsupported.

Existing context: docs/rules.md ~631-650 documents why BOTH records were refused: calling a coroutine function builds a coroutine and runs none of the body, and a discarded coroutine leaves a RuntimeWarning. Entry-only must reconcile that rationale (the record describes the first await, not the call). Broad umbrella: TASK-37 (OPT-01, async and descriptor support with dedicated contracts); this task is its first concrete slice with a live consumer.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A rule with event entry on a coroutine function target installs and fires: an async wrapper replaces the attribute, callers keep awaiting it, and the entry record reaches the firing log with run/instance identity exactly as on sync targets.
- [ ] #2 The entry timing contract is explicit and tested: the record fires at the first await of the wrapper (body start), not at call time, and the docs state which; a wrapper coroutine that is never awaited produces no silent record (reconciles the RuntimeWarning rationale in docs/rules.md ~631-650).
- [ ] #3 exit and combined entry/exit events on coroutine targets are still refused, with the message split to say entry-only is available and exit is the unsupported part; async generator functions remain refused as a distinct shape.
- [ ] #4 Cancellation and exception paths of the wrapper are tested: cancelling the awaiting task, an exception raised before the original call, and an exception from the original coroutine each leave the log and the original semantics intact.
- [ ] #5 Subprocess-real tests under a real event loop cover the firing path end to end, plus the existing sync behaviors unchanged (full suite green).
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Merged as 76114e2 via PR #141 (squash of dd0ab3f + 8b2562e), master CI green, local master fast-forwarded, ccgram pane w1E:p1 prompted to swap harness stubs. Independent review APPROVED bound to 8b2562e (10 invariants, adversarial probes). Gates: /simplify 4-angle findings applied; code-review high returned 5 findings (2 fixed, 3 filed); post-verdict addendum gaps filed as TASK-179 (test discrimination) and TASK-180 (docs tail).
<!-- SECTION:FINAL_SUMMARY:END -->
