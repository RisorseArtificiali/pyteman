---
id: TASK-128
title: >-
  I test reimplementano a mano il modulo vittima in circa dieci punti invece di
  usare l'helper che gia' esiste
status: Wontfix
assignee: []
created_date: '2026-09-17 04:40'
updated_date: '2026-09-27 02:18'
labels:
  - tests
  - cleanup
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Segnalato dal gate di riuso del 2026-09-17.

`tests/test_activation_atomic.py:34` definisce `_victim_module`, e circa dieci casi successivi ricostruiscono la stessa impalcatura a mano: creazione del ModuleType, setattr del contenitore, inserimento in sys.modules e pulizia finale. Ogni copia e' una occasione in cui la pulizia di sys.modules puo' essere dimenticata, e una modifica alla forma della vittima va inseguita in dieci posti.

Va verificato caso per caso prima di accorpare: alcune copie divergono di proposito, perche' il caso ha bisogno di una vittima con una forma particolare. Quelle restano come sono, con una riga che dica perche' divergono.

Segnalazione correlata dallo stesso gate, tracciata qui perche' non ha un posto migliore: `_compile` ripete la formulazione dell'errore di `rules.py:79 _expression`. Non si tocca, perche' rules.py e' congelato e approvato sotto TASK-7.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 I casi che costruiscono una vittima standard passano per _victim_module
- [ ] #2 I casi che divergono di proposito restano espliciti e portano una riga che dice perche'
- [ ] #3 Nessun test perde la pulizia di sys.modules
- [ ] #4 La suite resta verde con lo stesso numero di test passati
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
From the TASK-148 harness extraction (2026-09-27): one more copy to fold when this task runs, tests/test_targets.py:170 carries its own _rules_file. The new tests/startup_harness.py (rules_file + run_py, timeout note included) is the destination for the remaining _run copies in test_lazy_walk.py, test_coroutine_entry.py and test_unreadable_point.py; each reduces mechanically and gains the TimeoutExpired diagnostic note they currently lack. Their shapes differ (env defaults baked in), so migrating them changes behavior slightly and belongs here, not as a drive-by.
<!-- SECTION:NOTES:END -->
