---
id: TASK-38
title: OPT-02. Fornire preflight e diagnostica senza eseguire il workload
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
  - TASK-7
  - TASK-4
  - TASK-14
  - TASK-15
references:
  - rules.py
  - patcher.py
  - firing.py
documentation:
  - doc-1
  - doc-2
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P3, PROPOSTA, aperto.

**File:** nuovo modulo CLI opzionale; riuso di `rules.py`, `patcher.py`, `firing.py`.

**Motivazione:** oggi le funzioni di load/install sono l'unico percorso operativo; target mancanti o import non supportati sono difficili da distinguere da condizioni non soddisfatte.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 exit code e output JSON stabili, side effect degli import espliciti, nessuna attivazione sul solo validate, errore azionabile per target mancanti e ambiente non corretto.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Proposta iniziale da verificare sul codice corrente, non una correzione già applicata.

comando validate per schema senza import arbitrari, comando di ispezione target in subprocess opt-in perché importare moduli esegue codice, riepilogo regole applicate/non viste ed errori di action. Nessuna seconda implementazione del parser.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: CFG-01, RT-04, LOG-01, LOG-02.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.
<!-- SECTION:NOTES:END -->
