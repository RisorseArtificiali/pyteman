---
id: TASK-167
title: Rendere isolante l'asserzione changed-text nella guardia di ordinamento
status: Done
assignee: []
created_date: '2026-09-17 21:12'
updated_date: '2026-11-06 19:23'
labels:
  - tests
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
In test_the_unordered_comparison_forgives_order_and_nothing_else la riga sostitutiva del caso changed-text e "row 9 missing", di lunghezza diversa dalla riga che sostituisce, quindi l'asserzione non separa mai un cambio di testo da un cambio di lunghezza. Una sostituzione della stessa lunghezza, per esempio "row 9 missing from index i", darebbe a quella asserzione una uccisione unica contro un comparatore basato sulla lunghezza. Emerso dalla revisione simplification del fix di ordinamento (commit ac3400d); non applicato perche i tre file erano congelati e la modifica non era un bug. L'asserzione resta comunque l'unico testimone di uno dei tre modi di fallimento promessi dal docstring, quindi non va rimossa.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 La riga sostitutiva nel caso changed-text ha la stessa lunghezza della riga che sostituisce
- [x] #2 Una matrice di mutazione mostra almeno un mutante ucciso solo da quella asserzione
- [x] #3 Se nessun mutante isolante esiste, il task si chiude documentando perche l'asserzione resta come testimone del contratto e non come killer
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #31. Added lines already present on master per PR: #31 0/1=0%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Merged as PR #216, squash dfe5cd0, supersedes #31 (closed with a pointer). Shipped mechanism is the derived form, one step past the original literal: the changed-text guard replaces the dropped row with rows[-1].replace("row 2", "row 9", 1), which produces exactly the task's example string on the current fixture, keeps length and token shape by construction, and fails loudly if the fixture rows are ever renumbered (the derivation becomes a no-op and the capture compares equal to itself). AC1 measured 26 == 26; AC2 satisfied by the reviewer-reproduced mutation matrix (a length-comparator mutant survives every assertion under the old 13-character literal and is killed by this assertion alone); AC3 moot because an isolating mutant exists. Battery on 3.13.15 at the exact artifact (candidate-p7mfqnv0, 1570 passed, 3 skips declared), /simplify 3/3 CLEAN, /code-review high one finding (the unpinned same-length property) fixed before the PR by the derivation itself, independent APPROVED at 8bb9dcf, CI 7/7 (workflow run 42277208127).
<!-- SECTION:FINAL_SUMMARY:END -->
