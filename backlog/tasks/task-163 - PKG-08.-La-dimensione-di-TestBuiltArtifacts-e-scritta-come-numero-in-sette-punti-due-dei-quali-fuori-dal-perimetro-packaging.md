---
id: TASK-163
title: >-
  PKG-08. La dimensione di TestBuiltArtifacts e' scritta come numero in sette
  punti, due dei quali fuori dal perimetro packaging
status: Done
assignee: []
created_date: '2026-09-17 12:40'
updated_date: '2026-11-08 20:23'
labels:
  - pkg
  - audit-2026-09-16
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Trovato durante TASK-137, misurando le conseguenze di un test aggiunto e non leggendo il codice.

**Il difetto.** `TestBuiltArtifacts` in `tests/test_packaging.py` contiene oggi sette check. Quel sette e' scritto a mano, come parola o come cifra, in sette punti sparsi su quattro file:

    .github/workflows/tests.yml:32       "the seven packaging build checks skip"
    scripts/verify_artifacts.py:310      "-rs because seven artifact-build checks skip here"
    docs/packaging.md:265                "all seven TestBuiltArtifacts checks skip"
    docs/packaging.md:296                "seven build checks skip"
    docs/packaging.md:302                "713 passed, 7 skipped ... The seven are the build checks"
    docs/packaging.md:339                "a silent hole of seven checks in a green run"
    tests/test_packaging.py:165          "Seven checks that quietly do not run"

Nessuno dei sette e' derivato dalla classe. Aggiungere un ottavo check alla classe li rende falsi tutti e sette in un colpo solo, e nulla va rosso: sono prose e commenti, non asserzioni.

**Perche' e' piu' della solita prosa che invecchia.** Due dei sette stanno in `.github/workflows/tests.yml` e `scripts/verify_artifacts.py`. Chi aggiunge un test alla classe sta lavorando dentro `tests/test_packaging.py` e non ha nessun motivo di aprire il workflow o lo script CI: la falsificazione avviene in file che non sono sotto gli occhi di chi la provoca. In TASK-137 e' successo esattamente questo, e l'ottavo check e' stato poi riassorbito per altre ragioni di progetto, quindi i sette numeri sono tornati veri per caso e non perche' qualcuno li avesse corretti.

**Non e' una richiesta di rimuovere i numeri.** Il numero in `docs/packaging.md:302` sta accanto a `713 passed, 7 skipped`, che e' una misura datata e va letta come tale: una misura si cita col suo numero, altrimenti non e' piu' una misura. Il problema e' l'assenza di qualunque cosa che colleghi i sette punti alla classe.

**Direzioni possibili, da scegliere motivando invece che per comodita'.**
1. Un check che legge la dimensione della classe e la confronta con un valore atteso dichiarato una volta sola, cosi' che il sette abbia una sola sorgente e cambiarlo sia un atto deliberato.
2. Riscrivere i punti non datati come relazione invece che come numero, per esempio "l'intera classe", lasciando il numero solo dove accompagna una misura datata. Piu' economico, ma non impedisce a nessuno di riscrivere un numero domani.
3. Accettare il rischio e registrarlo, se si giudica che una classe che cambia dimensione una volta all'anno non meriti un meccanismo.

La 1 e la 2 non si escludono. Quello che va evitato e' chiudere il task lasciando i due punti fuori perimetro senza nessun collegamento alla classe che descrivono.

**Fuori perimetro.** La forma dei check dentro `TestBuiltArtifacts`, che appartiene a una tranche gia' revisionata.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 I sette punti che citano la dimensione di TestBuiltArtifacts sono collegati alla classe o riscritti come relazione, con la scelta motivata invece che presa per comodita'.
- [ ] #2 Dimostrato per misura che aggiungere un check alla classe produce un segnale, oppure registrato esplicitamente che si e' scelto di non produrne e perche'.
- [ ] #3 I due punti in .github/workflows/tests.yml e scripts/verify_artifacts.py sono trattati insieme agli altri cinque, non lasciati indietro perche' stanno fuori dal perimetro packaging.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #37. Added lines already present on master per PR: #37 0/26=0%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closure restored 2026-11-08 (tracker repair): the day-3 Done marker was lost to a working-tree revert; the work had landed. Landed by direct push cd34e08 (superseded PR #37 closed with a pointer). Full chain in the durable handoff, set forty-eighth.
<!-- SECTION:FINAL_SUMMARY:END -->
