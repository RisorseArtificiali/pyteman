---
id: TASK-35
title: PKG-04. Aggiornare i metadati di licenza deprecati
status: Done
assignee: []
created_date: '2026-09-16 12:20'
updated_date: '2026-09-30 11:24'
labels:
  - audit-2026-09-16
  - opus-5
  - pkg
  - confirmed
milestone: m-5
dependencies: []
references:
  - 'pyproject.toml:6,14,28'
documentation:
  - doc-1
  - doc-2
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P3, CONFIRMED come warning di build, aperto.

**File:** `pyproject.toml:6,14,28`.

**Evidenza:** il build locale con setuptools 80.10.2 produce `SetuptoolsDeprecationWarning` per `project.license` come tabella e per il classifier di licenza. Il build riesce: non è un errore di rilascio già verificatosi.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 build con backend minimo dichiarato e backend corrente, metadati controllati con twine e licenza presente nell'artefatto, senza i warning oggetto del task.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Proposta iniziale da verificare sul codice corrente, non una correzione già applicata.

verificare la documentazione corrente del backend prima di migrare a espressione SPDX e license-files; adeguare il requisito minimo di setuptools alle sintassi effettivamente adottate. Conservare testo e inclusione della licenza MIT.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: nessuna.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.

Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #27. Added lines already present on master per PR: #27 0/4=0%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge.

Merged 2026-09-30 via #202 (a1ca79d). Evidence under /home/pantinor/pyteman-evidence/t191/: diff35.patch sha256 3221b9d4, tree35-hold2.sha256, VERDICT-35.md in t191rev.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by PR #202, squash-merged as a1ca79d on master at 2026-09-30 11:23Z. AC1: builds with the current backend and with the declared minimum, the independent reviewer probing per version that setuptools 69 and 75.8 refuse the PEP 639 string form outright and the 77 line is the first that accepts and emits it (the first cut pinned 69 on a factually wrong justification and was rejected for exactly this); at the declared floor of 77 the wheel and sdist build, twine check passes, the METADATA carries License-Expression: MIT and License-File: LICENSE, the deprecated license classifier is gone, and the LICENSE file ships in both artifacts. The migration: license = MIT SPDX expression plus license-files, the trove classifier dropped, setuptools>=77 in build-system requires, the dev group and the lock. Supersedes #27, closed with a pointer. Gates at 56d4f9a: suite 1537 passed 2 skipped, check green with lock freshness, delivery 41, independent verdict REJECTED at the first head then APPROVED at the amended one (VERDICT-35.md).
<!-- SECTION:FINAL_SUMMARY:END -->
