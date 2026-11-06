---
id: TASK-30
title: 'EX-05. Rendere durevoli verdetti, errori e prove dei driver'
status: Done
assignee: []
created_date: '2026-09-16 12:20'
updated_date: '2026-09-28 04:53'
labels:
  - audit-2026-09-16
  - opus-5
  - ex
  - confirmed
  - proposal
milestone: m-4
dependencies:
  - TASK-27
  - TASK-29
references:
  - 'examples/hermes-111912/run_repro.py:146-160'
  - 'examples/hermes-109966/run_repro.py:173-194'
documentation:
  - doc-1
  - doc-2
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P2, CONFIRMED nel codice per cleanup e exit status; PROPOSTA per il formato, aperto.

**File:** `examples/hermes-111912/run_repro.py:146-160`, `examples/hermes-109966/run_repro.py:173-194`.

**Evidenza:** senza expected verdict, INCONCLUSIVE può terminare con exit code zero. #111912 rimuove lo scratch prima di segnalare un mismatch, anche per esiti non conclusivi; #109966 preserva lo scratch solo in base a CLEAN, non al mismatch. I verdetti non sono salvati come oggetto strutturato con provenienza.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 tabella di tutti i verdetti con/senza aspettativa; INCONCLUSIVE non deve apparire come successo automatico.
- [x] #2 Dopo un mismatch l'artefatto indicato esiste e contiene la diagnosi.
- [x] #3 La conservazione dei file non deve impedire EX-02.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Proposta iniziale da verificare sul codice corrente, non una correzione già applicata.

definire exit code distinti per esecuzione valida, mismatch e guasto harness; validare expected verdict prima di partire. Salvare un manifest JSON con motivazioni, firing log, stdout/stderr, revisioni, hash del ruleset, Python/SQLite e parametri. Conservare prove su INCONCLUSIVE e mismatch, con opzione esplicita per cleanup.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: EX-02 e EX-04.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Chiuso con il merge d3b6470 (PR #180, squash di 7185536 su master 0cc34c8). Entrambi i driver espongono la tabella di uscita 0/1/2/3 (verdetto raggiunto e corrisposto / mismatch / DRIVER-ERROR / INCONCLUSIVE mai successo; prima INCONCLUSIVE senza aspettativa cadeva da main con exit 0); l'aspettativa e' validata prima che qualsiasi cosa giri; un manifest.json (verdetto, motivo, evidenza, provenienza con digest del ruleset, revisione upstream col marker not-a-git-checkout piegato dall'output vuoto di rev-parse, versioni Python/SQLite, argv) viene scritto nella home PRIMA della decisione di conservazione (AC2); la home sopravvive a ogni esito tranne un CLEAN corrisposto non ambiguo (l'111912 cancellava prima del mismatch; il 109966 cancellava sul mismatch a verdetto CLEAN); il kill dell'albero precede ogni tocco della home (AC3 verificato dalla belt anche con crash a meta' manifest). L'111912 guadagna la riga REASON e matched e' legato prima del try nel 109966 cosi' un crash durante la scrittura del manifest non maschera l'errore originale. Sei nuovi test percorrono la tabella e il manifest (il mismatch asserisce esattamente 'not-a-git-checkout'). Gate: /simplify 5 finding applicati; belt CHANGES-REQUIRED con 2 difetti reali (il marker irraggiungibile del non-repo; la UnboundLocalError nella finestra crash) fissati e pinnati, matrice di conservazione percorsa su tutte e quattro le celle di entrambi i driver, TASK-188/189 aperte per i residui sotto soglia; revisione indipendente APPROVED a 7185536 (finding minori: conteggio test in prosa, assist 111 exit-code non documentato). CI verde 7 check; batteria 1369 passed 2 skipped; mutazioni che uccidono (rmtree-before-mismatch, exit 0 su INCONCLUSIVE, manifest drop, fold del marker).
<!-- SECTION:FINAL_SUMMARY:END -->
