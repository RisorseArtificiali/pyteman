---
id: TASK-133
title: >-
  scripts/: consolidare gli helper di sottoprocesso duplicati fra
  run_coverage.py e verify_artifacts.py
status: Done
assignee:
  - '@tree-28'
created_date: '2026-09-17 06:13'
updated_date: '2026-11-08 20:21'
labels:
  - pkg
  - cleanup
milestone: m-5
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Emerso da /simplify sulla tranche TASK-34.1 e **rimandato deliberatamente**, perche' la meta' del lavoro cade su `scripts/verify_artifacts.py`, che in quella tranche era congelato e fuori perimetro. Filed nello stesso turno in cui lo skip e' stato deciso.

**La duplicazione, misurata e non stimata** (2026-09-17, `grep` sui due file piu' lettura delle definizioni):

    CLEARED_IN_CHILD   IDENTICA byte per byte nei due file
                       ("PYTEMAN_RULES", "PYTEMAN_LOG", "PYTEMAN_REQUIRE_MARKER")
    CHILD_ENV          differisce per UNA chiave: verify_artifacts aggiunge
                       PYTHONDONTWRITEBYTECODE, run_coverage no
    say()              stessa idea, stesso flush, docstring diverse
    run()              stessa forma, firma divergente: verify_artifacts prende
                       cwd/extra_env, controlla sempre e ritorna stdout strippato;
                       run_coverage prende data_file/check e ritorna il
                       CompletedProcess

**Perche' non e' un copia-incolla da cancellare a occhi chiusi.** La divergenza su `PYTHONDONTWRITEBYTECODE` e' voluta e documentata nel commento di `run_coverage.py`: li' lo script pianta residui in un albero copiato e confronta un archivio contro di esso, quindi il bytecode di troppo e' parte di cio' che e' sotto test; qui non si costruisce nulla e il residuo che conta sono i dati di coverage. Un consolidamento che appiattisce le due CHILD_ENV in una sola rompe una delle due verifiche in modo silenzioso. La forma corretta e' una base condivisa piu' un'aggiunta esplicita per chiamante, non un default unico.

**Vincolo di perimetro che non va perso.** `scripts/` non e' grant in `MANIFEST.in` e non deve finire in nessun artefatto. `test_the_sdist_carries_no_top_level_entry_that_was_not_granted` e' gia' la guardia di quel confine e va lasciata verde.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Le costanti e gli helper condivisi da scripts/run_coverage.py e scripts/verify_artifacts.py stanno in un solo posto, e la divergenza deliberata su PYTHONDONTWRITEBYTECODE resta esplicita invece di sparire in un default.
- [ ] #2 Entrambi gli script continuano a girare verdi dopo il consolidamento, dimostrato eseguendoli, non deducendolo dal fatto che importano.
- [ ] #3 scripts/ resta fuori dai grant di MANIFEST.in: il modulo condiviso non deve entrare in nessun artefatto, e il test che vigila quel confine resta verde.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #61. Added lines already present on master per PR: #61 0/38=0% absentfiles=1. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closure restored 2026-11-08 (tracker repair): the day-3 Done marker was lost to a working-tree revert; the work had landed. Landed by direct pushes b7370bb and 197cfef (the #61/#85 pair resolved); both PRs closed with pointers. Full chain in the durable handoff, day-two pair resolution.
<!-- SECTION:FINAL_SUMMARY:END -->
