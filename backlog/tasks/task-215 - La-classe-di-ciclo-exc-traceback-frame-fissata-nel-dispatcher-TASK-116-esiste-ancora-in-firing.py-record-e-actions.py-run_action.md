---
id: TASK-215
title: >-
  La classe di ciclo exc-traceback-frame fissata nel dispatcher (TASK-116)
  esiste ancora in firing.py record() e actions.py run_action()
status: To Do
assignee: []
created_date: '2026-11-08 01:41'
updated_date: '2026-11-08 17:15'
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
