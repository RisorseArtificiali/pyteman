---
id: TASK-160
title: >-
  _suspendable_reason reads one co_flags word through three separate unwrap
  walks
status: Done
assignee: []
created_date: '2026-09-17 11:25'
updated_date: '2026-09-27 01:02'
labels:
  - audit-2026-09-16
  - opus-5
  - efficiency-gate
  - task-3-followup
  - performance
dependencies: []
references:
  - 'src/pyteman/patcher.py:616-634'
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Efficiency gate on TASK-3, 2026-09-17. Filed rather than applied, because the win is real in ratio and small in absolute startup terms, and buying it means duplicating CPython predicate semantics by hand.

src/pyteman/patcher.py:616-634. inspect.iscoroutinefunction, isasyncgenfunction and isgeneratorfunction each call inspect._has_code_flag, which redoes functools._unwrap_partialmethod, the ismethod loop, _unwrap_partial and isfunction before reading __code__.co_flags. cProfile confirms _has_code_flag entered 3 times per invocation (60000 calls for 20000 invocations), _unwrap_partialmethod at 60000, _unwrap_partial at 140000. Three walks of the same chain to read three bits of one word.

After those, inspect.getattr_static(type(current), "__call__", None) runs for ordinary functions too, where the answer is always the function slot wrapper and isfunction of it is always False. Built-in types cannot be reassigned, so that is always true, not merely usually.

Measured on Python 3.14.7 with /tmp/pyteman-audit-env-OOeElF/bin/python:
  _suspendable_reason(plain function)      15.05 us
  callable instance, two links             23.4 us
  async def                                3.2 us
  activating 50 plain points, best of 7    41.2 us per point with the gate
  same, gate stubbed to (None, None)       29.3 us per point

So the gate is 29 percent of per-point activation cost: 0.59 ms for a 50-point ruleset, roughly 6 ms for a 500-point one, paid at interpreter startup by every process that sets PYTEMAN_RULES.

The gate prototyped a per-call fast path, not a cache, so a rebound slot is unaffected: at the top of the loop, when type(current) is types.FunctionType and neither "__partialmethod__" nor "_is_coroutine_marker" is in current.__dict__, read co_flags once and test 0x80, 0x200 and 0x20, then return (None, None) without getattr_static. The two dict probes are exactly what _has_code_flag and _has_coroutine_mark could otherwise find. Anything failing the guard falls through to the existing chain unchanged. Verdict equality was checked against the current function on 15 shapes, including all six refused fixtures, markcoroutinefunction, a partialmethod bound and unbound, the hostile __class__, contextlib.contextmanager, and both functools.wraps adapters: zero mismatches. Prototype cost 1.37 us for a plain function, down from 15.05, and 1.26 us for async def, down from 3.2.

Worth doing if large rulesets become a target. Not worth hand-copying predicate semantics otherwise, since a future CPython change to _has_code_flag would silently desynchronise the fast path from the slow one. Whoever takes this should decide that question first.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Prima di scrivere codice, e' decisa e scritta la domanda vera: se duplicare a mano la semantica dei predicati inspect e' accettabile, dato che un cambio futuro in CPython desincronizzerebbe in silenzio il percorso veloce da quello lento.
- [ ] #2 Se il fast path viene adottato, un test confronta il verdetto del percorso veloce e di quello lento sulle stesse forme, incluse tutte le fixture rifiutate, markcoroutinefunction, partialmethod legato e non legato, e i due adapter functools.wraps.
- [ ] #3 Il fast path e' per chiamata e non una cache: uno slot riassegnato non puo' ereditare un verdetto vecchio, e un test lo mostra.
- [ ] #4 Il guadagno e' misurato sul costo di attivazione end-to-end, non solo sulla funzione isolata, con output reale registrato prima e dopo.
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Decided 2026-09-27 (AC #1): not now. No large-ruleset consumer exists today; the live consumers (the ccgram TASK-43 harness and the test suite) activate single-digit points, where the measured 0.59 ms per 50 points is noise at startup. The cost of adopting the fast path is unchanged and is the decisive term: the fast path hand-copies _has_code_flag's semantics, and a future CPython change to that private helper would silently desynchronise the fast answer from the slow one on the exact shapes (refused fixtures, markers, partialmethods) the gate exists to classify, turning an efficiency win into a correctness risk with no test that can catch the drift except AC #2's shape table, which only covers the shapes known today. The design stays recorded here for whoever takes it: per-call guard (type is FunctionType, no __partialmethod__/__is_coroutine_marker__ in __dict__), read co_flags once, test 0x80/0x200/0x20, fall through to the full chain otherwise; per-call and never cached so a rebound slot cannot inherit a verdict; AC #2's equality test over the full shape table and AC #4's end-to-end measurement apply unchanged if it is ever adopted. Note the line references are stale after TASK-178: _suspendable_reason now returns (reason, cause, kind) triples and the split refusal sites moved.
<!-- SECTION:FINAL_SUMMARY:END -->
