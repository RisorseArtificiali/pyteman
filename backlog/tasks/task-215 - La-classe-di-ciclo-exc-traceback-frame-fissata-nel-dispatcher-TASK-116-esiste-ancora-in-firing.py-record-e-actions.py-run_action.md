---
id: TASK-215
title: >-
  La classe di ciclo exc-traceback-frame fissata nel dispatcher (TASK-116)
  esiste ancora in firing.py record() e actions.py run_action()
status: Done
assignee: []
created_date: '2026-11-08 01:41'
updated_date: '2026-11-20 18:29'
labels:
  - memory
  - patcher
  - firing
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Depositato dalla code-review high del set T116 (2026-11-08), su indicazione del reviewer: la stessa classe di difetto fissata nel dispatcher esiste in altri due siti di raise dello stesso pacchetto, su path di errore dello strumento (freddi, non caldi come il dispatcher, quindi il perimetro del set T116 era giusto, ma i fratelli noti non devono restare da nessuna parte).

Siti:
1. src/pyteman/firing.py:354 circa, `raise primary` in record(): i locali primary/unlock_exc/close_exc trattengono l'eccezione innalzata e le peer annotate, piu' la riga serializzata; ciclo locale -> traceback -> frame -> locali -> eccezione, liberato solo dal gc generazionale.
2. src/pyteman/actions.py:172 circa, `raise done.to_raise` in run_action(): il locale done tiene l'istanza che trasporta l'eccezione, stesso ciclo.

Carico: un workload che cattura e scarta un rifiuto strict-mode di run_action, o una FiringLogError di record, lascia quei frame vivi fino al pass del collector: lo stesso carico sul processo sotto test che un fault-injection tool non dovrebbe aggiungere.

Direzione: la stessa tecnica del set T116 (azzera i locali coinvolti in un finally annidato, o non legare nomi longevi), precedute dalla misura (weakref con gc disabilitato, rosso prima del fix) come chiede la disciplina del repo. I path sono freddi: valutare se il fix e' dovuto o se registrare la scelta di non farlo, con la misura a supporto.
<!-- SECTION:DESCRIPTION:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-11-08 frontmatter completion (from the whole-project code review): this file lacked the updated_date and priority fields its sibling review-finding tasks carry; both added via this edit (priority Low to match the family). No content change.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Landed on master as a5f2a72 (2026-11-20, set 82, resumed across an 11-day session gap). The exception-traceback-frame cycle class the dispatcher fix TASK-116 closed existed at the package's two other raise sites: firing.py record()'s failure raise (locals primary/unlock_exc/close_exc holding the composed FiringLogError and its annotated peers) and actions.py run_action()'s refusal raise (local done transporting the very exception raised). Both fixed with TASK-116's technique (raise under try, nested finally clears the locals after the traceback captured the frame), measured FIRST per the discipline: two weakref-with-gc-disabled probes, both red before the fix, green after; every clear now pinned at per-local granularity (the firing probe drives write+unlock+close failures in one round via a weakref-able OSError subclass, weakrefing the primary from the catch and both peers through the stubs' side channel, with the stubs clearing their own raise locals so the harness measures record()'s cycles, not its own). The probe skeleton the TASK-116 probe introduced and the two new probes copied was unified into tests/cycle_probe.py, assert_dies_by_refcount (a plain module per the suite's shared-helper precedent, a real vacuity guard failing by name when a round measures nothing, list flattening for multi-object rounds): the unification closed a real hole, since the three-copy form passed silently green on never-raised paths, which the skeptic demonstrated live before the helper existed. Diagnostics byte-identical (skeptic-verified across write/unlock+close/raise scenarios; the PEP 667 locals-view qualifier stated at the clear). Attribution complete by the skeptic's mutation probes: done's two payload routes (to_raise field and the message lambda's __defaults__), primary as the sole holder in the probed path, and the cause web dies with the primary on CPython 3.15.2, an interpreter-specific empirical fact recorded as such. Gates: /simplify (skill form, four angles: dead setup and redundant import from efficiency; helper extraction from reuse and simplification, convergent; altitude CLEAN with an independent red reproduction on a base worktree), /code-review high (seven findings all applied: per-local pins, the _builtins swap moved inside each round's try, instances-not-classes wording, the real vacuity guard, the dead import, the PEP 667 qualifier, plain-module placement), skeptic CONFIRMED with fix-reversion and attribution mutations. Batteries green on every candidate (final hl__tqwz, floor 1627); touched suites 239 green; ruff clean.
<!-- SECTION:FINAL_SUMMARY:END -->
