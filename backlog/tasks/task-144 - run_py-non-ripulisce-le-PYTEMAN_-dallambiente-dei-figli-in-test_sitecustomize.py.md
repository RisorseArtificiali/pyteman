---
id: TASK-144
title: >-
  run_py non ripulisce le PYTEMAN_* dall'ambiente dei figli in
  test_sitecustomize.py
status: Done
assignee: []
created_date: '2026-09-17 10:48'
updated_date: '2026-11-08 20:22'
labels:
  - pkg
  - test-hygiene
  - audit-2026-09-16
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Trovato durante il gate di code review di TASK-34.2 e riportato come sotto soglia, quindi fuori dalle due classi di difetto di quel task e non correggibile li' senza uscire dal perimetro autorizzato.

`run_py` in `tests/test_sitecustomize.py` (riga 79 allo stato attuale) costruisce l'ambiente del figlio come `{**os.environ, "PYTHONPATH": ..., **env_extra}`. Riversa quindi nel figlio l'intero ambiente ambientale senza mai ripulire le variabili `PYTEMAN_*`.

Conseguenza: uno sviluppatore che abbia `PYTEMAN_RULES` esportato nella propria shell, cioe' esattamente il meccanismo di attivazione documentato del pacchetto, propaga quella variabile a OGNI figlio lanciato da questo helper. `test_inert_without_env` verifica che senza attivazione non succeda nulla, e con `PYTEMAN_RULES` ereditata quella premessa e' falsa. Diversi test di rifiuto asseriscono inoltre sulla fase raggiunta, e la fase cambia se il figlio si attiva.

Che la fixture `shim` nello stesso file faccia gia' `monkeypatch.delenv("PYTEMAN_RULES", raising=False)` dimostra che il rischio era stato riconosciuto per il percorso in-process e non per quello a subprocess.

Severita': fallisce rumorosamente e non passa falsamente, il che lo tiene sotto la soglia di riporto. Resta un test che passa o fallisce in funzione dell'ambiente di chi lo esegue invece che del codice.

Perche' non corretto in TASK-34.2: la consegna di quel task autorizzava sul file il SOLO helper `run_py` limitatamente ai timeout, e vietava esplicitamente modifiche semantiche ai test. Ripulire l'ambiente del figlio cambia cio' che i test esercitano davvero, quindi e' una decisione che spetta a chi possiede il file.

Nota di contesto: questo non e' un task creato per rinviare l'imbuto dei timeout di `run_py`, che e' stato chiuso dentro TASK-34.2 con `timeout=60` e la nota su `exc.timeout`. E' un pericolo pre-esistente e indipendente.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Le variabili PYTEMAN_* sono rimosse dall'ambiente passato ai figli da run_py, oppure la loro propagazione e' resa esplicita e motivata per iscritto sul posto.
- [ ] #2 Esiste una prova che con PYTEMAN_RULES esportata nell'ambiente chiamante la suite di test_sitecustomize.py da' lo stesso esito che senza, eseguita in entrambe le condizioni.
- [ ] #3 La fixture shim e run_py sono coerenti sul trattamento dell'ambiente, oppure la differenza e' motivata.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #34. Added lines already present on master per PR: #34 0/5=0%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closure restored 2026-11-08 (tracker repair): the day-3 Done marker was lost to a working-tree revert; the work had landed. Landed by direct push e0df168 (the fix moved to the shared startup_harness CLEARED_IN_CHILD helper created by the #196 consolidation, with a discriminating three-variable test and an APPROVED base-emulation proof; superseded PR #34 closed with a pointer). Full chain in the PR #34 close comment and the durable handoff.
<!-- SECTION:FINAL_SUMMARY:END -->
