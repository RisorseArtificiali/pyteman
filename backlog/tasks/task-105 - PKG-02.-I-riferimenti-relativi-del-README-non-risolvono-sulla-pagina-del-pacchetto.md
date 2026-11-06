---
id: TASK-105
title: >-
  PKG-02. I riferimenti relativi del README non risolvono sulla pagina del
  pacchetto
status: Done
assignee: []
created_date: '2026-09-17 02:22'
updated_date: '2026-11-06 21:13'
labels:
  - pkg
  - confirmed
  - audit-2026-09-16
milestone: m-5
dependencies:
  - TASK-32
references:
  - 'README.md:273'
  - 'pyproject.toml:21-24'
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Residuo misurato durante TASK-32 / PKG-01 e non correggibile in quel perimetro, perche' la correzione appartiene a README.md, che e' di proprieta' dell'agente concorrente e fuori dal perimetro packaging di TASK-32.

**Priorita' / stato:** P2, CONFIRMED su artefatto costruito, aperto.

**Evidenza.** `core_metadata` della wheel incorpora il README come `Description` con `Description-Content-Type: text/markdown`, cioe' esattamente il testo che PyPI rende sulla pagina del progetto. Misurato su `pyteman-0.1.0-py3-none-any.whl` costruito offline il 2026-09-17:

- `see [LICENSE](LICENSE)` (README.md:273) e' presente nel METADATA. E' l'unico vero link markdown relativo del README. Reso su `https://pypi.org/project/pyteman/` si risolve contro l'URL della pagina e non contro un archivio, quindi e' un link rotto.
- Otto citazioni testuali di percorsi sono incorporate allo stesso modo: `docs/rules.md` cinque volte, `docs/targeting.md` due, `docs/integrity.md` una. Non sono link, quindi non si rompono, ma indicano file che sulla pagina del pacchetto non esistono e che la wheel non contiene.
- Il README non contiene alcun URL assoluto: `grep -noE 'https?://[^ )>`]+' README.md` non restituisce nulla. Gli unici URL assoluti del progetto stanno in `[project.urls]` di pyproject.toml e puntano a `https://github.com/RisorseArtificiali/pyteman`.

**Cosa NON e' in difetto.** Nella sdist gli stessi riferimenti risolvono tutti, dopo TASK-32: `LICENSE` sta nella radice dell'archivio e `docs/rules.md`, `docs/integrity.md`, `docs/targeting.md` sono presenti. Verificato sull'archivio estratto. Quindi AC2 di TASK-32 e' soddisfatto per la sdist e questo task tiene soltanto la meta' wheel/PyPI.

**Perche' non e' stato corretto in TASK-32.** L'unica correzione possibile e' riscrivere i riferimenti del README come URL assoluti al repository. README.md non e' nel perimetro di TASK-32 (pyproject per packaging, MANIFEST.in, test packaging, docs packaging) ed era in modifica concorrente da un altro agente nello stesso checkout.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 I riferimenti del README che compaiono nel METADATA della wheel sono URL assoluti al repository, oppure e' documentato e verificato perche' un riferimento relativo e' accettabile li'.
- [x] #2 La verifica e' fatta sul METADATA dell'artefatto costruito, non sul solo README nel checkout, e riporta il comando usato.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Nota di localizzazione (2026-09-17). Il riferimento `README.md:273` nel campo References era esatto al momento della stesura e ora punta a 274: `README.md` ha 154 inserimenti non committati dell'agente concorrente e la riga si sposta a ogni sua modifica. Chi prende questo task cerchi il link per contenuto, non per numero di riga:

    grep -n -oE '\[[^]]+\]\([^)]+\)' README.md | grep -vE '\((https?|mailto):'

Misurato ora, quel comando restituisce due righe e una sola e' un link vero: `[LICENSE](LICENSE)`. L'altra, `[a](u)` a riga 164, e' dentro la prosa che descrive l'escaping dei caratteri in una cella e non e' un riferimento a un file. Un correttore automatico che riscrivesse i link relativi in URL assoluti la romperebbe: va esclusa esplicitamente.

Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #26. Added lines already present on master per PR: #26 0/2=0%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Merged by direct push 479a099 (maintainer ordered direct pushes; first of the new process), supersedes #26 (closed with a pointer). All three README markdown links (docs/quickstart.md, docs/development.md, LICENSE) are absolute repository URLs; the backticked [a](u) sample stays relative on purpose and test_every_readme_link_is_absolute now pins the invariant, so a future relative link fails the suite instead of shipping dead. CITED_BY_THE_README gained docs/quickstart.md and docs/firing.md, so every README-cited path is now guarded against silent deletion. AC2: verification run on the built wheel, command and complete output recorded at ~/pyteman-evidence/t105rev/AC2-METADATA.txt and independently reproduced by the reviewer (exactly the three absolute URLs plus the sample remain); the round-1 claim of this verification had been false while quickstart was still relative, which is why the gate demanded the real run. docs/packaging.md's Known residue section states the landed state anchored to the release after 0.2.0 (live PyPI 0.2.0 still renders relative links, verified against pypi.org JSON). Dispositions judged sound by the independent review: blob/master URLs rather than tag-pinned ones (tag pinning needs release machinery that does not exist; the publish-workflow gap lives on TASK-33, whose stale predecessor ID TASK-108 is cited in a pre-existing context line this change left alone), and the README keeps its hand-maintained hard-wrapped style (the unwrap directive targets generated files). Gates: battery on 3.13.15 at the exact artifact (candidate-5umoy57n, 1576 collected for the new tests, 1573 passed, 3 skips declared), /simplify 3/3 CLEAN, two /code-review high rounds with four findings fixed and two dispositioned, independent APPROVED at 479a099.
<!-- SECTION:FINAL_SUMMARY:END -->
