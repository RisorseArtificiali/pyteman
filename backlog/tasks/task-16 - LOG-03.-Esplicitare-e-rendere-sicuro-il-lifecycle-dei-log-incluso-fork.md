---
id: TASK-16
title: 'LOG-03. Esplicitare e rendere sicuro il lifecycle dei log, incluso fork'
status: Done
assignee: []
created_date: '2026-09-16 12:20'
updated_date: '2026-09-26 09:23'
labels:
  - audit-2026-09-16
  - opus-5
  - log
  - confirmed
milestone: m-2
dependencies:
  - TASK-1
  - TASK-14
references:
  - 'src/pyteman/firing.py:7-29'
  - 'src/pyteman/barriers.py:4-20'
  - 'src/pyteman/patcher.py:114-120'
documentation:
  - doc-1
  - doc-2
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P2, CONFIRMED, aperto.

**File:** `src/pyteman/firing.py:7-29`, `src/pyteman/barriers.py:4-20`, `src/pyteman/patcher.py:114-120`.

**Evidenza:** manca un metodo pubblico close/context manager; i test chiudono `_fh`. In un processo con thread che possiede log._lock, un fork eredita il lock chiuso e il child si blocca in record. Il probe ha terminato e atteso solo il proprio child. Python segnala esplicitamente che fork multithread può causare deadlock: non attribuire a pyteman la sicurezza generale di quel pattern.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 repeated open/close senza descrittori residui, log del chiamante non chiuso a sorpresa, subprocess spawn; se fork dichiarato supportato, test deterministico di lock ereditato senza hangs.
- [x] #2 Non promettere di correggere lock di librerie altrui.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Proposta iniziale da verificare sul codice corrente, non una correzione già applicata.

chiusura idempotente e ownership dei log, cleanup su installazione fallita, comportamento record-after-close. Documentare fork non supportato e preferire spawn, oppure usare at-fork per ricreare solo lo stato controllato da pyteman e riaprire writer separati; stessa decisione per lock/barriere ereditati.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: RT-01, LOG-01.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
LOG-03 chiuso come completamento amministrativo: tutti i requisiti sono stati implementati da TASK-14 (LOG-01, PR #4, merge b1a886d). Nessuna modifica di codice necessaria.

AC#1 verificato meccanicamente (32 test passati, test_firing.py + test_firing_multiprocess.py):
- repeated open/close senza descrittori residui: test_reopen_gives_a_fresh_instance (riga 102), test_a_dropped_instance_without_close_does_not_leak_its_fd (riga 632), test_close_disarms_the_finalizer (riga 651)
- log del chiamante non chiuso a sorpresa: test_close_is_idempotent_and_record_after_close_raises (riga 132), test_context_manager_closes_on_exit (riga 140), test_the_logger_does_not_instrument_its_own_io (riga 604, asserisce fd_state=="closed")
- subprocess spawn: 4 test in test_firing_multiprocess.py (concurrent append riga 116, large payload riga 133, flock short-write riga 151, SIGKILL escalation riga 168)
- fork: non dichiarato supportato; test_a_forked_child_is_refused (riga 149) e test_a_forked_child_calling_close_is_refused_not_deadlocked (riga 176) con _waitpid_bounded che garantisce hang -> red, non hang -> suite bloccata

AC#2 verificato nel docstring firing.py:35: "This poisoning protects only this instance." Nessuna promessa su lock di terze parti; scope esplicito su fd e lock di pyteman.

gate-exempt: chiusura amministrativa di codice gia pubblicato e testato; nessuna modifica di codice in questa transizione. /pa:reflect READY.
<!-- SECTION:FINAL_SUMMARY:END -->
