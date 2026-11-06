---
id: TASK-33
title: >-
  PKG-02. Condizionare la pubblicazione ai test e alla corrispondenza
  tag/versione
status: Done
assignee:
  - '@tree-28'
created_date: '2026-09-16 12:20'
updated_date: '2026-09-30 10:42'
labels:
  - audit-2026-09-16
  - opus-5
  - pkg
  - confirmed
milestone: m-5
dependencies:
  - TASK-32
  - TASK-34
references:
  - '.github/workflows/publish.yml:8-25'
  - '.github/workflows/tests.yml:3-6'
  - 'pyproject.toml:3'
documentation:
  - doc-1
  - doc-2
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P1, CONFIRMED come assenza di gate nel workflow; non afferma che siano già state pubblicate release difettose, aperto.

**File:** `.github/workflows/publish.yml:8-25`, `.github/workflows/tests.yml:3-6`, `pyproject.toml:3`.

**Evidenza:** publish su `v*` esegue build, `twine check` e upload senza test né confronto tra tag e versione package. Il workflow tests non è una dipendenza del job publish. `twine check` non viene usato qui come test funzionale.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 un test fallito, un tag incoerente e uno smoke test del wheel fallito impediscono l'upload; il percorso corretto produce e pubblica lo stesso artefatto verificato.
- [x] #2 Non pubblicare pacchetti reali come parte del test del workflow senza autorizzazione.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Proposta iniziale da verificare sul codice corrente, non una correzione già applicata.

riusare un job di test come dipendenza obbligatoria del publish; verificare tag/versione e installazione del wheel generato. Ridurre il permesso OIDC al solo job di upload; verificare prima le impostazioni reali del trusted publisher, non presumere che manchino protezioni remote.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: PKG-01 per l'artefatto completo; coordinare PKG-03.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.

**Evidenza trasferita da TASK-108, archiviato come duplicato il 2026-09-17.** Qui sotto c'e' solo cio' che NON era gia' in questo task. L'AC1 esistente non e' stato toccato e nessun AC nuovo e' stato aggiunto: la frase che gia' porta, il percorso corretto produce e pubblica lo stesso artefatto verificato, e' esattamente il requisito centrale di TASK-108 e non va scritta due volte.

**Stato di publish.yml letto oggi, non dedotto.** Il file e' di 26 righe e i passi del job sono tre: `uv build`, `uvx twine check dist/*`, `pypa/gh-action-pypi-publish@release/v1`. Nessuno step di test sul percorso di rilascio, e il workflow `tests` non e' una dipendenza di questo job. `twine check` convalida i metadati e il rendering della long description; non apre l'archivio e non sa nulla di quali file siano finiti dentro. L'artefatto pubblicato e' quindi oggi l'unico che nessun controllo di contenuto abbia mai esaminato. File NON modificato: l'istruzione vieta di toccarlo e non l'ho toccato.

**Il residuo che vale la pena portarsi dietro: stesso artefatto testato e poi caricato.** Non basta che il gate costruisca e controlli. Deve controllare l'archivio CHE VIENE CARICATO, non una ricostruzione fatta in un altro step o in un altro job: due `uv build` successivi non danno nessuna garanzia di identita', e un gate che ricostruisce verifica un artefatto e ne pubblica un altro. E' la stessa distinzione che l'AC1 gia' porta, e la registro qui perche' e' il punto in cui un'implementazione ragionevole sbaglia per prima.

**La trappola dello skip, nella forma che sopravvive.** TASK-108 temeva uno skip silenzioso dei controlli sugli artefatti in CI. Quella forma non esiste piu': `test_the_build_checks_cannot_be_disabled_silently` in tests/test_packaging.py trasforma in fallimento sia un PKG-INFO bugiardo sia un interprete senza setuptools, e non salta mai. Resta pero' un caso che quel guard PERMETTE per costruzione, e che riguarda direttamente questo task: dentro una sdist estratta, dove PKG-INFO esiste e i marcatori di checkout no, il guard esce subito e i sette check di `TestBuiltArtifacts` saltano legittimamente. Misurato in TASK-34: 713 passed, 7 skipped da dentro la sdist.

Conseguenza operativa per il gate di release, ed e' il motivo per cui questa nota esiste: far girare la suite da dentro la sdist estratta NON e' un controllo di contenuto dell'archivio. Prova che la suite spedita gira, che e' un'altra affermazione. Il controllo di contenuto richiede di costruire da un checkout e misurare l'archivio dall'esterno, che e' cio' che `scripts/verify_artifacts.py` fa gia'.

**Una previsione di TASK-108 e' smentita e va letta come ritirata.** Quel task prevedeva che in CI l'intera classe `TestBuiltArtifacts` saltasse in silenzio, perche' `pip install -e . pytest` lascia setuptools nell'ambiente isolato di build. La meta' meccanica e' vera, la conseguenza no. Misurato in TASK-34 con il vecchio step di install: 1 failed, 711 passed, 8 skipped, exit 1. Il rosso e' il guard. Il verde silenzioso non si produce, e l'AC3 di TASK-108 e' quindi gia' risposto e non trasferito come lavoro.

Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #78. Added lines already present on master per PR: #78 2/37=5%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.

Merged 2026-09-30 via #201 (977f995). Evidence under /home/pantinor/pyteman-evidence/t191/: diff33.patch sha256 a5c3b36b, pins33.py, mutants-33.log, VERDICT-33.md in t191rev.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by PR #201, squash-merged as 977f995 on master at 2026-09-30 10:41Z. AC1: a failed test blocks the upload (the check job runs the full suite, and tests.yml does not fire on tags), an incoherent tag blocks it (the tag must match pyproject's package version), and a failed wheel smoke test blocks it (install plus import plus version print in a fresh uv venv); the verified bytes are the published bytes (built once in check, handed to publish via upload/download-artifact). AC2: no real package is published as part of testing (the workflow fires only on v* tag pushes); the OIDC id-token permission is scoped to the publish job alone, default contents: read, and the evidence pins assert the check job's segment holds no id-token. Structural pins and a five-mutant battery back the claims; the reviewer's informational residuals are on TASK-198. Supersedes #78, closed with a pointer. Gates at 646a6ed: suite 1537 passed 2 skipped, check green with the Actions lint, independent verdict APPROVED (VERDICT-33.md).
<!-- SECTION:FINAL_SUMMARY:END -->
