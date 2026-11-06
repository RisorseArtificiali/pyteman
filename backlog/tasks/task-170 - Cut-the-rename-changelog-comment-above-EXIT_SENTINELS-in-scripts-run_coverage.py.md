---
id: TASK-170
title: >-
  Cut the rename changelog comment above EXIT_SENTINELS in
  scripts/run_coverage.py
status: Done
assignee: []
created_date: '2026-09-18 17:04'
updated_date: '2026-11-06 18:32'
labels:
  - log
  - proposal
  - opus-5
dependencies:
  - TASK-15
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Proposta del gate simplify di TASK-15 (LOG-02), non applicata perche' i 15 file erano congelati in attesa del commit del parent. Registrata qui invece di essere persa.

Il gate ha prodotto una sola proposta strutturale sopravvissuta, ed e' sul volume dei commenti, non sul flusso di controllo. In `scripts/run_coverage.py` righe 78-83, sopra `EXIT_SENTINELS`, sei righe di commento spiegano che il testimone si chiamava `run_action` finche' i corpi delle azioni non sono stati estratti in `_dispatch`.

Quattro di quelle sei righe sono una voce di changelog. Un changelog dentro un commento sorgente e' una seconda storia non versionata che invecchia per conto suo, e la rassicurazione che "il contratto sopra e' intatto" ha senso solo per chi ha visto la revisione precedente; ogni lettore futuro la legge come rumore su un simbolo che nell'albero non esiste piu'. Il rename appartiene al messaggio di commit.

La frase realmente portante e' l'ultima, quella che spiega un vincolo che la tupla non puo' esprimere: perche' nominare un simbolo module-private sia un bersaglio accettabile. Quella resta.

Sostituzione proposta dal gate, righe 78-83:

    # `_dispatch` is module-private on purpose: this is a claim about a line in
    # THIS package, not about a public surface.
    EXIT_SENTINELS = (

Il paragrafo alle righe 65-76, che porta l'argomento dei due ASSI di creazione di un figlio, NON e' toccato dalla proposta e deve restare.

Nessun effetto sul comportamento: e' solo commento. Il gate ha verificato la suite verde sull'albero congelato (926 passed, 1 skipped) prima di proporre.

Vincolo aggiuntivo dal gate di review, che ha esaminato gli stessi file: la parentetica in `docs/coverage.md:62`, "(the action bodies behind `run_action`, where the kill action's `os._exit` sits)", NON va tagliata insieme a questa. E' l'unico punto che dice al lettore come il testimone privato si rapporta al punto di ingresso pubblico, cioe' proprio l'orientamento che il rename ha tolto dal nome del simbolo.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Le righe 78-83 di scripts/run_coverage.py sono sostituite dalle due righe proposte dal gate
- [x] #2 Il paragrafo sui due ASSI di creazione di un figlio (righe 65-76) resta invariato
- [x] #3 La parentetica di docs/coverage.md:62 sui corpi delle azioni dietro run_action resta invariata
- [x] #4 Nessun riferimento residuo a run_action come luogo dove muore il figlio in scripts/run_coverage.py
- [x] #5 Suite verde e scripts/run_coverage.py esce 0 con entrambi i sentinelle ok, con output reale riportato
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #32. Added lines already present on master per PR: #32 0/2=0%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Merged as PR #215, squash b3d15f1, supersedes #32 (closed with a pointer). AC1 deviation, judged correct by both the code review and the independent reviewer: the shipped two lines read "Both entries name module-private symbols on purpose" instead of the gate's original _dispatch-only wording, because the review found the narrowing dropped the coverage the old generic sentence gave to the second sentinel (_refuse). AC2 and AC3 verified untouched (docs/coverage.md sha256-identical to base). AC4 verified, zero run_action references remain. AC5: suite green on 3.13.15 and 3.14.10 batteries (1570 passed each, every skip declared); the script leg is proven by the CI coverage job (workflow run 42269813568) executing scripts/run_coverage.py to success at the merged head 4b9500a, with the 7/7 check rollup recorded in the TASK-191 notes.
<!-- SECTION:FINAL_SUMMARY:END -->
