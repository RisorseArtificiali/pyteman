---
id: TASK-41
title: OPT-05. Esprimere i casi Hermes come matrice di esperimenti riprendibile
status: To Do
assignee: []
created_date: '2026-09-16 12:20'
updated_date: '2026-09-16 12:20'
labels:
  - audit-2026-09-16
  - opus-5
  - opt
  - proposal
milestone: m-6
dependencies:
  - TASK-19
  - TASK-20
  - TASK-21
  - TASK-22
  - TASK-23
  - TASK-30
  - TASK-31
references:
  - 'examples/hermes-111912/README.md:56-60'
  - src/pyteman/runner/
documentation:
  - doc-1
  - doc-2
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P3, PROPOSTA, aperto.

**File:** `examples/hermes-111912/README.md:56-60`, `src/pyteman/runner/` e manifest prodotti da EX-05.

**Motivazione:** il README suggerisce già di rendere durevoli le combinazioni scenario/revisione. Un'integrazione piccola eserciterebbe realmente il runner senza appesantire il driver single-leg.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 interruzione e resume della matrice non riutilizzano risultati di revisioni diverse; ogni riga punta al manifest e distingue REPRODUCED, CLEAN, INCONCLUSIVE e failure harness.
- [ ] #2 Il driver resta eseguibile singolarmente.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Proposta iniziale da verificare sul codice corrente, non una correzione già applicata.

adapter separato per scenario, revisioni fissate ed expected verdict, con fingerprint completo e generazione del report dai risultati salvati. Nessuna tabella aggiornata a mano con risultati non rieseguiti.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: RUN-01 fino a RUN-05, EX-05, EX-06.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.
<!-- SECTION:NOTES:END -->
