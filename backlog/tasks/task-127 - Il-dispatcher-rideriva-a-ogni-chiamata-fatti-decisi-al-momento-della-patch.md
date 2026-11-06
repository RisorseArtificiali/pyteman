---
id: TASK-127
title: Il dispatcher rideriva a ogni chiamata fatti decisi al momento della patch
status: Done
assignee: []
created_date: '2026-09-17 04:40'
updated_date: '2026-09-27 10:18'
labels:
  - patcher
  - performance
dependencies:
  - TASK-2
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Segnalato dal gate di efficienza del 2026-09-17, e la sua rilevanza cresce proprio con TASK-2: quando un solo dispatcher servira' N regole raggruppate, questo lavoro ripetuto si moltiplica per N sul cammino caldo.

1. `_gate` ricava `rule.fire.get("mode", "always")` a ogni chiamata, e nel ramo countdown anche la conversione a intero del conteggio. Sono fatti fissati quando la regola e' stata compilata e non cambiano mai per la vita del dispatcher. La forma proposta e' allargare le tuple di `bound` a patcher.py:942 perche' portino gia' il modo e il conteggio gia' convertito.

2. I due test sul ramo della firma sono anch'essi fatti del momento della patch, valutati a ogni chiamata. Il revisore stesso ha classificato questo come il punto piu' debole dei suoi rilievi, perche' si tratta di due test di identita' su valori gia' in cella di chiusura e il guadagno potrebbe non esistere.

Nessuno dei due si tocca prima che TASK-2 abbia fissato la forma definitiva delle tuple di `bound`, altrimenti si riscrive due volte la stessa struttura. Serve una misura, non una stima, per giustificare il secondo punto.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Il modo di fire e il conteggio convertito viaggiano nelle tuple di bound invece di essere riderivati per chiamata
- [x] #2 La semantica di countdown, once_per e always e' invariata, provata dalla suite esistente sui gate
- [x] #3 Il secondo punto e' applicato solo se una misura lo giustifica, altrimenti e' scartato con la misura allegata
- [x] #4 La suite resta verde
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed 2026-09-27 with both halves resolved by measurement and by TASK-110's landing. Item 1 (mode/n per call) is DONE, implemented by TASK-110 as part of its efficiency batch (PR #160, merged as 17fa3b4): mode and the converted countdown n now ride in the per-rule state built once at bind, which rides in the bound spec, exactly the 'per-bind not per-call derivation' this task asked for; the AC's literal 'in the bound tuples' is satisfied by the state being the bound spec's fourth field, and the gate semantics are unchanged, proven by the existing gate suite plus the two new pins (post-install rule.fire edits inert; unconvertible n fails at bind). Item 2 (the two signature identity tests per call) is REJECTED ON MEASUREMENT (AC #3's disjunct): the two tests cost 47.5-58.9 ns per call, which is 1.6 percent of a one-rule firing (3001 ns) and 0.5 percent of a five-rule firing (12511 ns), and the flag-gated alternative measured 33.6 ns, saving ~14-25 ns per call against a firing that costs thousands; a rebind mid-call window (an extension can rebind comp.sig between this call and the next) means a precomputed flag would also need a rebind-aware write site, adding a divergence risk to save well under one percent. Measurement commands and outputs recorded in this session's evidence (task127 branch, worktree venv, CPython 3.14.7). No code change was needed on the task127 branch beyond the measurement; the branch carries no diff and will be discarded.
<!-- SECTION:FINAL_SUMMARY:END -->
