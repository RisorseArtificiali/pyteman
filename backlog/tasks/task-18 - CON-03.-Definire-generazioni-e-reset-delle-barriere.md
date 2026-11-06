---
id: TASK-18
title: CON-03. Definire generazioni e reset delle barriere
status: Done
assignee: []
created_date: '2026-09-16 12:20'
updated_date: '2026-09-30 08:25'
labels:
  - audit-2026-09-16
  - opus-5
  - con
  - confirmed
  - proposal
milestone: m-2
dependencies:
  - TASK-17
  - TASK-15
references:
  - 'src/pyteman/barriers.py:7-21'
documentation:
  - doc-1
  - doc-2
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P2, CONFIRMED per comportamento; PROPOSTA per contratto, aperto.

**File:** `src/pyteman/barriers.py:7-21`.

**Evidenza:** reset_all sostituisce il dizionario mentre un waiter conserva il vecchio Event; open sullo stesso nome apre un altro Event e il waiter va in timeout. Una volta aperto, un Event rimane aperto: questa primitiva è un latch one-shot, non una barriera ciclica. La persistenza dei nomi dura fino al reset.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 reset con e senza waiter, open-before-wait, riuso del nome e più cicli.
- [x] #2 Nessun waiter viene perso in silenzio; documentata la mancata sincronizzazione fra processi.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Proposta iniziale da verificare sul codice corrente, non una correzione già applicata.

documentare esplicitamente latch solo-thread e vietare reset con waiter attivi, oppure cancellare/risvegliare la generazione precedente con esito distinguibile. Eventuale riuso per cicli richiede generation id, non reset indiscriminato.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: CON-02 e LOG-02.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.

Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #106. Added lines already present on master per PR: #106 6/45=13%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.

Reviewer's corrected probe results (VERDICT-18.md F1, 2026-09-30), recorded with the task: the shipped open() shape (set under the lock) deadlocks on a re-entrant set() in all three scenarios probed (an Event whose set calls reset_all, open or wait), while the outside-lock shape does not deadlock in any; the handoff's inverted analysis (set-under-lock safe, set-outside-lock dangerous) was wrong. The behaviour decision stands (master's unchanged shape, kept deliberately, no regression since production Events never re-enter), and the residual constraint (nothing may re-enter barriers from a set() call) is documented accurately in the module docstring.

Merged 2026-09-30 via #199 (4e5f2a3). Evidence under /home/pantinor/pyteman-evidence/t191/: diff18.patch sha256 b83cff75, tree18-hold3.sha256, mutants-18.log, VERDICT-18*.md in t191rev.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by PR #199, squash-merged as 4e5f2a3 on master at 2026-09-30 08:23Z. AC1: reset with a waiter wakes it (budget dwarfing the honoured timeout, the original 5/5 equality making an orphan indistinguishable from a timeout inside the join window, which the battery's first mutant proved); reset without a waiter, open-before-wait and name reuse across two generations are pinned by the other tests. AC2: no waiter is lost silently (reset_all sets the old generation's events and wait checks the generation on both the already-set and the woken path, so the reset's own set never reads as a legitimate open, with the set-path window pinned by a hostile is_set that fires the reset); the cross-process scope is documented in the module docstring. The _lock discipline is documented accurately: wait() calls is_set and wait outside the lock (re-entry safe there), open() keeps master's under-lock set, and nothing may re-enter barriers from a set() call; the reviewer's probes are recorded on this task with the handoff's inverted analysis corrected. Supersedes #106, closed with a pointer. Gates at 0982e25: suite 1535 passed 2 skipped, check green, delivery 41, battery 4/4, code-review high five findings applied or answered by documentation after probing rejected the code change, independent verdicts APPROVED at df9e9af and reissued at 0982e25.
<!-- SECTION:FINAL_SUMMARY:END -->
