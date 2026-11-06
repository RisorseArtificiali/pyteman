---
id: TASK-68
title: 'Report Markdown: valori che differiscono solo per spazi collassano'
status: Done
assignee: []
created_date: '2026-09-16 18:43'
updated_date: '2026-09-30 13:55'
labels:
  - audit-2026-09-16
  - run-05-residue
  - report
dependencies: []
references:
  - 'src/pyteman/runner/report.py:85-97'
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Scoperto durante RUN-05 (TASK-23), misurato, non corretto. Distinto da TASK-67 perche nessun escape di punteggiatura lo risolve.

Markdown normalizza gli spazi dentro una cella di tabella come ovunque: elimina quelli iniziali e finali e riduce le sequenze. Valori che differiscono solo per spaziatura arrivano identici al lettore.

Misurato con pandoc e python-markdown. Entrambi i renderer: "lead", " lead" e "  lead" rendono "lead"; "trail" e "trail  " rendono "trail". Solo pandoc: "a b", "a<TAB>b" e "a  b" rendono "a b", mentre python-markdown conserva il tab.

Il disaccordo fra i due renderer sul tab e significativo: un contratto puo promettere solo cio che ogni renderer conforme fa, quindi la promessa deve escludere le differenze di sola spaziatura comunque sia scritto l'escape.

Via d'uscita nota, costosa: rendere ogni cella come code span conserva gli spazi interni ma cambia radicalmente l'aspetto del report e introduce l'escaping dei backtick stessi. Da valutare solo insieme a TASK-67.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Decidere se il report deve distinguere valori che differiscono solo per spazi, o dichiarare esplicitamente che non lo fa
- [x] #2 Il comportamento scelto e coperto da un test con almeno due renderer indipendenti
- [x] #3 Il contratto risultante e scritto nel docstring di _text e nella sezione Runner del README
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #116. Added lines already present on master per PR: #116 4/45=8%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.

Merged 2026-09-30 via #206 (1c9fbfb). Evidence under /home/pantinor/pyteman-evidence/t191/: diff68.patch sha256 cb6808e6, tree68-hold2.sha256, mutants-68.log, VERDICT-68.md in t191rev.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by PR #206, squash-merged as 1c9fbfb on master at 2026-09-30 13:54Z. AC1: the decision is explicit; the report promises only what both renderer families do (leading and trailing whitespace not preserved), declares interior whitespace renderer-dependent, and does not promise to distinguish whitespace-only differences. AC2: the contract is covered through two independent renderers; pandoc drives the full limits test (its masking .strip() removed) and python-markdown drives the portable half with interior cases excluded and the case list pinned by count. AC3: the contract is in _text's docstring, the pandoc test's docstring and the README's Runner section, all stating the measured truth after the reviewer's probes corrected the first cut's false tab claim (python-markdown expands tabs positionally; the README was already accurate). Supersedes #116, closed with a pointer. Gates at a8f2961: suite 1544 passed 1 skipped, check green, delivery 41, battery 2/2, independent verdicts APPROVED at 0be637a and reissued at a8f2961 (VERDICT-68.md).
<!-- SECTION:FINAL_SUMMARY:END -->
