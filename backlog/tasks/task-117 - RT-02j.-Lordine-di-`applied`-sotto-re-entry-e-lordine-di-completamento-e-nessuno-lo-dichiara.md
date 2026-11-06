---
id: TASK-117
title: >-
  RT-02j. L'ordine di `applied` sotto re-entry e' l'ordine di completamento, e
  nessuno lo dichiara
status: Done
assignee: []
created_date: '2026-09-17 03:43'
updated_date: '2026-09-29 23:56'
labels:
  - rt-02
  - patcher
  - diagnostics
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`applied` viene riempito man mano che pass 2 pubblica gli slot. Costruire un dispatcher rientra in `_patch` (importa inspect con l'hook vivo e valuta `__signature__` del callable), quindi una chiamata annidata puo' pubblicare i propri slot PRIMA che la chiamata esterna arrivi alla propria publish. L'ordine di `applied` diventa allora l'ordine di completamento, non l'ordine del ruleset ne' quello di risoluzione.

Nessun contratto pubblico promette un ordine per `applied`, e i test esistenti confrontano per lo piu' insiemi o singoli elementi, quindi al momento non e' un guasto osservato. Il costo e' che la lista e' usata come traccia diagnostica ed e' esattamente nei casi di re-entry, cioe' quelli difficili da leggere, che l'ordine smette di corrispondere a quello che l'operatore ha scritto.

Due esiti accettabili: documentare che l'ordine e' quello di installazione e non significa altro, oppure ordinare la lista sul ruleset prima di restituirla. La scelta va fatta, non lasciata implicita.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 L'ordine di `applied` e' documentato esplicitamente come ordine di installazione oppure reso deterministico rispetto al ruleset
- [x] #2 Esiste un test che installa sotto re-entry e fissa l'ordine atteso, qualunque dei due sia scelto
- [x] #3 Nessun chiamante nel repo dipende da un ordine diverso da quello documentato
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #87 #129. Added lines already present on master per PR: #87 9/64=14%  #129 0/3=0%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.

Merged 2026-09-29 via #194 (58b46fb). The rebase needed hand resolution twice; basedpyright caught the resulting duplicate test block. Evidence under /home/pantinor/pyteman-evidence/t191/: diff117.patch sha256 cd46b513, tree117-hold3.sha256, mutants-117*.log, VERDICT-117.md in t191rev.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by PR #194, squash-merged as 58b46fb on master at 2026-09-29 23:56Z. AC1: the order is documented explicitly as the completion order of _patch calls, no sort, told consistently in four places (the __init__ comment, the extend-site comment, the test docstring, and rules.md, which contrasts completion order with both ruleset order and the temporal order of the imports; the pass-2 parenthetical that mispredicted the mid-module shape was dropped). AC2: the re-entry test (param: target driving _binding_signature through the live hook) pins applied == [inner, outer] against ruleset order, with both rules functional (the inner overrides its return, the outer passes through its pragma with the dispatcher serving it by name, the original restored after uninstall). AC3: no caller in the repo depends on a different order (the existing tests compare sets or single elements; re-verified during the revival). The reviewer confirmed the mid-module shape obeys the contract and its informational note (fixture names sorting coincidentally in completion order) is filed on TASK-198. Supersedes #87 and #129, both closed with pointers. Gates at 03976e9: suite 1528 passed 2 skipped, check green, delivery 41, battery 1/1 (mutants-117c.log), code-review high three findings applied, independent verdict APPROVED (VERDICT-117.md).
<!-- SECTION:FINAL_SUMMARY:END -->
