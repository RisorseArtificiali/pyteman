---
id: TASK-44
title: RUN-07. Strumenti espliciti per lo strato legacy dei risultati
status: To Do
assignee: []
created_date: '2026-09-16 13:46'
updated_date: '2026-09-16 15:47'
labels:
  - audit-2026-09-16
  - review-followup
  - run
  - altitude
milestone: m-3
dependencies: []
references:
  - src/pyteman/runner/matrix.py
  - tests/test_matrix_identity.py
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Emersa dalla review Altitude del lavoro RUN-01 (TASK-19), 2026-09-16. Riguarda l'ergonomia dell'API, non la correttezza: quanto implementato in RUN-01 e corretto e coperto da test.

RUN-01 migra i database pre-provenance in uno strato non namespacizzato (experiment stringa vuota, fingerprint NULL) visibile da ogni esperimento, e lo fa drenare tramite le policy on_legacy adopt (la riga viene spostata sotto l'identita corrente e l'originale non timbrato finisce in results_superseded) oppure rerun (archivia e riesegue).

Due limiti restano, entrambi deliberati per non allargare RUN-01.

Primo: l'adozione si esprime solo come effetto collaterale di una esecuzione di matrice. Un operatore che voglia solo dichiarare le righe storiche appartenenti a una definizione deve invocare run_matrix con un callback che non verra mai chiamato. Un punto di ingresso dedicato renderebbe l'intento esplicito.

Secondo: lo strato legacy drena solo per le celle che qualcuno rilancia. Righe orfane, cioe con un cell_id che nessuna matrice corrente contiene piu, restano indefinitamente a experiment stringa vuota senza alcun modo di elencarle, adottarle in blocco o ritirarle. Non e una perdita di dati (le righe ci sono e sono leggibili) ma non c'e strumento che le mostri.

Verificato il 2026-09-16 sullo stato corrente: le righe orfane sopravvivono alla migrazione e restano interrogabili solo via sqlite a mano.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Esiste un punto di ingresso dedicato che adotta righe legacy senza richiedere un callback di esecuzione fittizio, con la stessa traccia in results_superseded prodotta oggi dalla policy adopt
- [ ] #2 Un operatore puo elencare le righe rimaste nello strato non namespacizzato, incluse quelle orfane che nessuna matrice corrente contiene
- [ ] #3 Le righe orfane possono essere adottate in blocco sotto una identita esplicita oppure ritirate, e in entrambi i casi l'originale resta archiviato
- [ ] #4 Il comportamento delle policy on_legacy esistenti resta invariato e i test RUN-01 continuano a passare
- [ ] #5 L'elenco di AC2 distingue le due popolazioni che convivono oggi nello stratum non namespacizzato, cioe le righe scritte deliberatamente con experiment=None (che portano un fingerprint) e le righe migrate da un database pre-provenance (fingerprint NULL). Solo le seconde sono orfane nel senso di questo task: adottare in blocco senza distinguerle timbrerebbe un'identita sopra una dichiarazione esplicita del chiamante. Vedi TASK-50 (RUN-10), che tratta la rappresentazione stessa
<!-- AC:END -->
