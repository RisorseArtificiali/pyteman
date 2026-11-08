---
id: TASK-166
title: docs/integrity.md cita SQLite 3.51.2 che nessuna macchina esegue
status: Done
assignee:
  - '@tree-28'
created_date: '2026-09-17 21:12'
updated_date: '2026-11-08 20:23'
labels:
  - docs
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
docs/integrity.md registra il corpus come misurato su SQLite 3.51.2 in circa sei punti, mentre nessuna macchina attualmente in uso esegue quella build: l'interprete di lavoro e su 3.53.4 e la suite passa. Il fatto che il contratto a livello di collezione regga tra build diverse e incoraggiante, ma la provenienza documentata cita una versione che nessuno sta eseguendo. Emerso dalla revisione altitude del fix di ordinamento (commit ac3400d). Solo documentazione, nessuna modifica al codice. Attenzione: la versione originale e parte del record osservativo, quindi va chiarita e non sovrascritta.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Ogni occorrenza di 3.51.2 in docs/integrity.md verificata contro la macchina che ha davvero prodotto quel campione
- [ ] #2 Il documento distingue la build su cui un campione fu registrato dalle build su cui il contratto e stato poi riverificato
- [ ] #3 Nessun numero di versione nel documento resta non attribuito a una osservazione reale
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Precisazione 2026-09-18, dopo il primo run remoto del workflow (run 35309543689, SHA ac3400d).

Lo step di logging aggiunto in quel commit stampa la versione SQLite del runner: **3.45.1 su tutte e quattro le gambe**, cioe' cinque release minori SOTTO l'intero campione locale, che va da 3.50.4 a 3.53.4. Questo e' il fatto nuovo disponibile a questo task.

Cosa NON va fatto con questo fatto, dichiarato prima di cosa va fatto perche' e' la parte che si perde:

1. **La provenienza storica 3.51.2 non va riscritta.** Il corpus registrato in docs/integrity.md fu misurato su quella build, e quel campione resta quello che fu. Il criterio 2 di questo task dice esattamente questo: distinguere la build su cui un campione fu REGISTRATO dalle build su cui il contratto e' stato poi RIVERIFICATO. Una nuova esecuzione aggiunge righe alla seconda categoria, non corregge la prima.

2. **Passare su 3.45.1 e su 3.53.4 non prova ogni release dell'intervallo.** Due estremi verdi sono due osservazioni, non una copertura continua. Questa formulazione mi era gia' sfuggita una volta come 'regge da 3.45.1 a 3.53.4' ed e' un'inferenza che i dati non contengono.

3. **Non isola versione da opzioni di build come causa dell'ordine.** Il runner differisce dalla macchina locale per versione E per come SQLite e' compilato e per la piattaforma. Il logging nomina la variabile candidata piu' ovvia; non la separa dalle altre. La sezione 'What the variable is NOT' della diagnosi originale resta valida e non va ritirata.

Cio' che il fatto AGGIUNGE davvero: il contratto a livello di collezione, cioe' le stesse findings in ordine diverso, e' ora osservato su una build molto piu' vecchia di tutte quelle campionate in locale. E' una riverifica utile del criterio 2 e va scritta come tale, con la versione attribuita all'osservazione che la produce (run 35309543689) come chiede il criterio 3.

Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #79. Added lines already present on master per PR: #79 0/12=0%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closure restored 2026-11-08 (tracker repair): the day-3 Done marker was lost to a working-tree revert; the work had landed. Landed by direct push 6d0c1e1 (superseded PR #88 closed with a pointer; the #79/#88 pair over docs/integrity.md was resolved with both halves' content landed). Full chain in the durable handoff, day-two pair resolution.
<!-- SECTION:FINAL_SUMMARY:END -->
