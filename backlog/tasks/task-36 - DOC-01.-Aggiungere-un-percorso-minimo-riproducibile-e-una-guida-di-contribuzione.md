---
id: TASK-36
title: >-
  DOC-01. Aggiungere un percorso minimo riproducibile e una guida di
  contribuzione
status: Done
assignee: []
created_date: '2026-09-16 12:20'
updated_date: '2026-09-27 20:45'
labels:
  - audit-2026-09-16
  - opus-5
  - doc
  - proposal
milestone: m-5
dependencies:
  - TASK-4
  - TASK-6
  - TASK-10
  - TASK-11
  - TASK-12
  - TASK-13
  - TASK-18
  - TASK-16
  - TASK-22
  - TASK-23
  - TASK-24
  - TASK-32
references:
  - 'README.md:13-25,28-42,65-72'
  - pyproject.toml
documentation:
  - doc-1
  - doc-2
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P2, PROPOSTA, aperto.

**File:** `README.md:13-25,28-42,65-72`, `pyproject.toml`.

**Evidenza:** il README parte dal contratto di attivazione e da regole Hermes, senza una demo autonoma completa, comando end-to-end con marker e guida allo sviluppo. I dettagli del runner sono limitati alle firme delle funzioni.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 eseguire la guida in ambiente nuovo usando il wheel e verificare ogni output dichiarato; una persona non deve dover conoscere il layout editable per attivare il package installato.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Proposta iniziale da verificare sul codice corrente, non una correzione già applicata.

esempio senza upstream esterni: target, YAML, installazione, marker, PYTHONPATH ricavato dal package installato, lancio, log atteso e verifica disattivazione. Documentare formato Cell/result, resume, report, limiti di concorrenza, ciclo install/uninstall e schema delle regole. Dipendenze di sviluppo e comandi di test in un percorso unico.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: consolidamento dei contratti M1 fino a M4, PKG-01.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Chiuso con il merge a7f29ab (PR #174, squash di 9f87eb4 su master 640a49e). docs/quickstart.md: percorso completo wheel-to-workload (venv fresca, install del wheel, PYTHONPATH derivato dal package installato e non dal layout editable, YAML a due regole su target a due funzioni, run col marker, log di firing con legend di elisione precisa, e le direzioni non-strumentate: inerte senza PYTEMAN_RULES, rifiuto fail-closed exit 2 senza marker, point errato che costa solo la sua regola, e il puntatore allo shadowing di sitecustomize che non ha comando da mostrare), piu' sezione README che linka. AC #1 eseguita DUE volte: la prima catturando ogni output dichiarato, la seconda in clean-room seguendo il doc come scritto, output byte-matching; la revisione indipendente l'ha eseguita una terza volta (tabella comando->dichiarato->osservato) prima di APPROVED. Gate: /simplify combinato 6 finding applicati (legend delle elisioni che nomina anche la coppia omessa al seq 3-4, undercount 'three ways' corretto contro la quarta direzione del README, provenienza del wheel linkata al primo uso, claim di cattura qualificato una volta, invariante unknown-result lasciato al link di firing.md, marker glossato al primo uso, doppia derivazione collassata); belt ESENTE con giustificazione (documentation-only, nessun cambiamento eseguibile); revisione indipendente APPROVED a 6f4ef7d con una finding LOW (chatter di uv non marcato) fissata e delta APPROVED a 9f87eb4; CI verde 7 check; batteria 1319 passed 2 skipped.
<!-- SECTION:FINAL_SUMMARY:END -->
