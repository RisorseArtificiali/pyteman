---
id: TASK-145
title: >-
  La sonda locale di test_report_escaping.py non controlla il returncode e
  degrada a skip silenzioso
status: Done
assignee: []
created_date: '2026-09-17 10:48'
updated_date: '2026-11-06 21:38'
labels:
  - test-hygiene
  - audit-2026-09-16
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Trovato dal gate di mutazione di TASK-34.2 come reperto secondario, fuori dal perimetro autorizzato di quel task.

In `tests/test_report_escaping.py`, intorno alla riga 408, la sonda che interroga `locale.getpreferredencoding` in un figlio legge soltanto `.stdout.strip()` e non verifica mai il `returncode`. La guardia successiva tratta la tupla `("utf8", "")` come "nessun locale non-UTF-8 disponibile", quindi lo stdout VUOTO di un figlio morto e' indistinguibile dalla risposta legittima "niente da testare".

Misurato dal revisore: facendo uscire quel figlio con codice 3 e stdout vuoto, il test diventa uno skip silenzioso e la suite resta verde, `15 passed, 1 skipped`. La stringa di motivo riporta `got ''`, quindi sotto `-rs` e' diagnosticabile, ma una sonda morta converte un'asserzione reale in uno skip invece che in un fallimento.

Asimmetria che rende il reperto specifico di questo solo call site: gli altri due dello stesso albero controllano gia'. `assert_refused` in `test_sitecustomize.py` verifica `returncode == 2` prima di guardare lo stdout, e la build in `test_packaging.py` verifica `returncode == 0` e poi solleva `KeyError` se i marcatori del figlio mancano. Nessuno dei due puo' passare su un figlio che non ha fatto nulla.

Perche' non corretto in TASK-34.2: il perimetro autorizzato su questo file era limitato ai tre call site `subprocess.run` per i SOLI timeout e ai loro commenti. Aggiungere un controllo sul returncode cambia la logica del test, non il suo confinamento temporale.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Il returncode della sonda locale e' verificato prima di interpretarne lo stdout, oppure il fallimento della sonda produce un fallimento del test e non uno skip.
- [x] #2 Esiste una prova che una sonda che esce con codice diverso da zero e stdout vuoto NON produce piu' uno skip silenzioso, ottenuta mutando la sonda.
- [x] #3 Gli altri due call site dello stesso file restano invariati, avendo gia' il controllo: assert_refused verifica returncode == 2 e la build verifica returncode == 0.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #33. Added lines already present on master per PR: #33 0/4=0%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Merged by direct push b90ba65, supersedes #33 (closed with a pointer). The locale probe in test_the_report_writes_where_the_locale_is_not_utf_8 now asserts returncode 0, with rc and stderr in the message, before stdout is interpreted; a probe whose child dies fails the test instead of degrading to the skip that lied about the environment. Mutation proof, run independently at both levels: a PYTHONHOME-killing plugin makes the candidate FAIL with the child's full stderr while the base silently skips with "got ''"; the same discrimination holds for mocked CompletedProcess shapes. The legitimate skip (a working probe reporting a UTF-8 encoding) is byte-identical in behavior. Disposition recorded per the code review: the skip arm's empty-string case now means only a live child that reported an empty codeset (a dead probe is ruled out by the assert); it stays a skip with got '' shown, accepted as pre-existing behavior rather than redesigned in this task. The review chain also swept the suite for the same disease and filed TASK-211 (the ps probe in _tree_processes passes vacuously). Gates: battery on 3.13.15 at the exact artifact (candidate-59q43y55, 1576 collected, 1573 passed, 3 skips declared; the locale test itself ran, not skipped, on that host), /simplify 3/3 CLEAN, /code-review high one finding fixed (rc in the message) and one dispositioned, independent APPROVED at b90ba65.
<!-- SECTION:FINAL_SUMMARY:END -->
