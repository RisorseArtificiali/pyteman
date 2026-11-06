---
id: TASK-76
title: >-
  Report: i controlli di formattazione bidirezionali attraversano l'escape non
  alterati
status: Done
assignee: []
created_date: '2026-09-16 19:33'
updated_date: '2026-09-30 15:18'
labels:
  - audit-2026-09-16
  - run
  - proposta
  - report
dependencies: []
references:
  - src/pyteman/runner/report.py
  - tests/test_report_escaping.py
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Emerso dalla review altitude del gate di TASK-23 (RUN-05), non da un difetto introdotto da quel task.

`_text` rende letterale la punteggiatura ASCII e trasforma i due fine riga in control picture. I caratteri di controllo bidirezionali non appartengono a nessuna delle due classi e passano inalterati fino all'HTML del renderer.

Conseguenza misurata: un valore memorizzato `sig‮DEKAF` viene mostrato come `sigFAKED`, perche U+202E non e terminato da U+202C e il suo effetto arriva a fine cella. Il campione HOSTILE contiene gia il caso (`unicode-rtl-override`) e la suite lo certifica come sicuro, perche l'oracolo confronta i caratteri estratti dall'HTML con quelli memorizzati: il confronto vede caratteri, mentre il danno sta nei glifi e nel loro ordine.

Non e un difetto di TASK-23: quel task promette che i caratteri mostrati siano quelli memorizzati, e quella promessa regge. E il livello visivo a non essere coperto, e la formulazione del contratto e stata ristretta in TASK-23 proprio per non promettere piu di quanto il codice faccia.

Costo di chiudere: cambia l'output prodotto, quindi va fatto come tranche a se con i suoi gate.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Decidere se i controlli bidi (U+202A..U+202E, U+2066..U+2069) rientrano nel dominio dell'escape o restano fuori contratto per scelta esplicita
- [x] #2 Se rientrano: renderli come i due fine riga, con test su renderer reale e aggiornamento di README e docstring
- [ ] #3 Se restano fuori: dichiararlo nel contratto invece di lasciarlo implicito, con un test che fissa il limite come gia fatto per spazi e control picture
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #65. Added lines already present on master per PR: #65 3/61=4%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.

Merged 2026-09-30 via #208 (8b24cf3). Evidence under /home/pantinor/pyteman-evidence/t191/: diff76.patch sha256 294f35d6, tree76-hold1.sha256, mutants-76.log, VERDICT-76.md in t191rev.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by PR #208, squash-merged as 8b24cf3 on master at 2026-09-30 15:17Z. AC1: the decision is recorded; bidi formatting controls are brought into the escape's domain. AC2: they render as their standard Unicode abbreviations in backslash-escaped brackets, neutralising the reordering a stored U+202E performs; verified inert in both renderer families; the _text docstring states the rationale and the README names the escape instead of the old traveling-hazard limit. Supersedes #65 (README paragraph folded in), closed with a pointer. Gates at 4582e53: suite 1547 passed 3 skipped, check green, delivery 41, battery 2/2, independent verdict APPROVED (VERDICT-76.md). One CI flake (TASK-201's lock, sixth occurrence) rerun green.
<!-- SECTION:FINAL_SUMMARY:END -->
