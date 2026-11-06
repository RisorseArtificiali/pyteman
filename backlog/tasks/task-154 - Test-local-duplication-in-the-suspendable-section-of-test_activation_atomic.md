---
id: TASK-154
title: Test-local duplication in the suspendable section of test_activation_atomic
status: To Do
assignee: []
created_date: '2026-09-17 11:13'
updated_date: '2026-09-28 18:16'
labels:
  - audit-2026-09-16
  - opus-5
  - reuse-gate
  - task-3-followup
  - tests
dependencies: []
references:
  - 'tests/test_activation_atomic.py:4134-4143'
  - 'tests/test_activation_atomic.py:35-47'
  - 'tests/test_activation_atomic.py:4182-4302'
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Reuse gate on TASK-3, 2026-09-17. Two findings in one file, both cheap and both local.

FIXTURE. tests/test_activation_atomic.py lines 4134-4143. The suspendable fixture writes a second copy of the register-yield-delete module lifecycle that _victim_module(name) at lines 35-47 of the same file already is. The victim and victim2 fixtures at 68-81 consume that generator with yield from. _suspendable_module() returns instead of yielding, so it cannot be consumed the established way, and it hardcodes MODNAME30 rather than taking a name. A second suspendable-shaped module would need a third copy of the block rather than another yield from.

BODY. Lines 4182-4205, 4250-4278 and 4281-4302. All three tests read `before`, call activate([make_rule(symbol, "r", module=MODNAME30)], log=None, modules=[MODNAME30]), assert p.applied inside a try, uninstall in the finally, then assert the slot is `before` again. Only the assertions inside the try differ. The restored-on-uninstall postcondition is therefore written three times across 75 lines, so a change to the install and restore protocol lands in three places.

The gate suggested either a small patched(symbol) context manager or merging two parametrize lists behind a flag. Prefer the context manager. Merging the two lists behind a flag would put a conditional in the test body and make each case prove a different thing depending on a parameter, which is the shape that produced the two vacuous tests already repaired in this work.

Cost: roughly 18 lines, and one protocol change touching three sites instead of one. No behaviour at risk.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 _suspendable_module diventa consumabile come _victim_module, cioe' la fixture usa yield from invece di riscrivere il ciclo register-yield-delete.
- [ ] #2 Il nome del modulo e' un parametro, non MODNAME30 cablato dentro la funzione.
- [ ] #3 Il corpo install-assert-uninstall condiviso dai tre test passa per un solo punto, preferibilmente un context manager patched(symbol); nessun flag di parametrizzazione che faccia provare cose diverse a casi diversi.
- [ ] #4 I tre test continuano a fallire sulle stesse mutazioni di prima: rimozione del rifiuto, ripristino della camminata __wrapped__, e classificatore che chiama il target.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
SIMPLIFICATION GATE, 2026-09-17, a third instance of the same duplication, with a concrete merge and one thing the merge would gain.

test_provenance_alone_does_not_refuse_and_is_never_read (2 params, lines 4182-4205) and test_ordinary_synchronous_callables_are_still_patched (4 params, lines 4250-4278) have byte-identical bodies except that the second adds `assert getattr(suspendable, symbol) is not before`.

Merging them into one test over all six params with the stronger assertion set deletes roughly twelve duplicated lines AND gives the cyclic and property_wrapped cases the 'the slot really was replaced' assertion their twin already makes, which they currently lack. That is a coverage gain, not just a tidy-up: today those two cases assert a dispatcher was installed via p.applied but never check the slot actually changed.

The per-case comments now sitting in the two param lists should become test ids so they survive the merge. The two docstrings merge into one stating both claims, since a single dispatcher-installed outcome is what both assert.

This does not conflict with the note above rejecting a parametrize flag. There is no flag here: all six cases get the same, stronger, assertions.

Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #40. Added lines already present on master per PR: #40 13/29=44%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason. Checked on master: the suspendable fixture in tests/test_activation_atomic.py still writes its own register-yield-delete lifecycle around _suspendable_module(), with MODNAME30 wired in.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Converted `_suspendable_module` from a factory returning a module to a generator taking a `name` parameter; the `suspendable` fixture is now `yield from _suspendable_module(MODNAME30)`, matching the `_victim_module(name)` pattern.

Extracted the common install-assert-uninstall body into `_patched(suspendable, symbol)`, a context manager used by both `test_provenance_alone_does_not_refuse_and_is_never_read` and `test_ordinary_synchronous_callables_are_still_patched`. The `cyclic` and `property_wrapped` cases gained the `is not before` assertion they previously lacked. Parametrize lists now use `pytest.param` with named ids.

Net: 41 insertions, 52 deletions. All 159 tests pass.

Branch: `work/suspendable-test-dedup`, commit `e84c5f9`, PR#40.
<!-- SECTION:FINAL_SUMMARY:END -->
