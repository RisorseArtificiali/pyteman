---
id: TASK-60
title: >-
  Cinque eccezioni del runner senza base comune: l'unico gestore ampio nasconde
  RecursionError
status: In Progress
assignee: []
created_date: '2026-09-16 18:04'
updated_date: '2026-09-25 18:51'
labels:
  - audit-2026-09-16
  - run
  - confirmed
  - spun-off
milestone: m-3
dependencies:
  - TASK-21
references:
  - src/pyteman/runner/matrix.py
  - src/pyteman/runner/report.py
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Scorporato da TASK-21 (RUN-03) il 2026-09-16, nel turno in cui il punto e stato sollevato dalla review di altitudine.

**Stato misurato.** RUN-03 porta la famiglia da due classi a cinque, su due moduli, tutte sottoclassi dirette e piatte di `RuntimeError`: `MatrixIdentityError` e `MatrixArtifactError` (preesistenti, matrix.py), `MatrixResultError` e `MatrixStorageError` (nuove, matrix.py), `MatrixReportError` (nuova, report.py). Nessuna base comune.

**Il costo.** A due classi un chiamante poteva nominarle entrambe. A cinque, su due moduli, "intercetta qualunque fallimento della matrice" non ha piu espressione se non `except RuntimeError`, che pero cattura anche `RecursionError`. E `RecursionError` e proprio un caso che questo codice tratta deliberatamente: il docstring di `_canonical` lo nomina come esito possibile di una definizione annidata troppo in profondita, e RUN-03 lo attribuisce alla cella. L'unico gestore ampio disponibile a un chiamante e quindi quello che nasconde il fallimento che il codice si sforza di attribuire correttamente.

**Nota sul confine fra i moduli.** `report.py` non importa nulla da `matrix.py`, e questo e deliberato: `_read` rende tabelle scritte da altri, e un lettore di db estranei non deve dipendere dal vocabolario di errori di chi li scrive. Una base condivisa fra i due moduli romperebbe quella indipendenza; una base per sole le classi del runner la lascerebbe intatta, ma lascerebbe `MatrixReportError` fuori dalla famiglia. La scelta va fatta, non ereditata.

**Perche non in RUN-03.** Richiede di modificare la dichiarazione di `MatrixIdentityError` e `MatrixArtifactError`, che sono codice RUN-01/RUN-02 gia approvato, e il perimetro assegnato esclude esplicitamente refactor ed estrazione di elementi condivisi.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Esiste una base comune per le eccezioni del runner e tutte e cinque le classi ne derivano
- [ ] #2 Un chiamante puo intercettare qualunque fallimento del runner senza nominare cinque classi e senza ricorrere a except RuntimeError
- [ ] #3 I test esistenti che intercettano MatrixIdentityError e MatrixArtifactError per nome continuano a passare senza modifiche
- [ ] #4 La relazione fra report.py e matrix.py resta quella attuale, oppure la scelta di non condividere la base fra i due moduli e motivata esplicitamente
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-09-25: Implementation complete, pending test verification (bash blocked by OOM).

Design decisions:

1. Base class location: runner/__init__.py (empty before this change). This is neutral ground that both matrix.py and report.py can import from without creating a dependency between them. runner/__init__.py is the package's public entry point, so `from pyteman.runner import MatrixError` is the canonical import path.

2. MatrixReportError included in the family: report.py imports MatrixError from the package root (`from . import MatrixError`), not from matrix.py. The architectural boundary (report.py does not depend on matrix.py internals) is fully preserved; what they share is a category, not an implementation detail.

3. MatrixLockError also included: the task describes five exceptions but AC#2 says 'qualunque fallimento del runner.' MatrixLockError is a runner exception (re-exported through matrix.py); excluding it would leave a gap where `except MatrixError` misses one runner failure. The change is one line in lock.py.

4. No circular import risk: __init__.py defines MatrixError with no local imports. lock.py and matrix.py both import from __init__.py, which has already executed by the time either module loads.

Files changed:
- src/pyteman/runner/__init__.py: MatrixError(RuntimeError) definition (was empty)
- src/pyteman/runner/matrix.py: import + 4 base class changes
- src/pyteman/runner/report.py: import + 1 base class change
- src/pyteman/runner/lock.py: import + 1 base class change
<!-- SECTION:NOTES:END -->
