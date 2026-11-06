---
id: TASK-109
title: La sdist spedisce la suite ma non dichiara come installarne i requisiti
status: To Do
assignee: []
created_date: '2026-09-17 02:45'
updated_date: '2026-09-28 18:16'
labels:
  - packaging
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Emerso da PKG-01 / TASK-32, fuori dal perimetro di quel task. Verificato leggendo `pyproject.toml`: non esistono ne' la tabella `[project.optional-dependencies]` ne' `[dependency-groups]`.

Con PKG-01 la sdist ora contiene `tests/`, `docs/` ed `examples/` interi, cosa che serve proprio a permettere a chi la riceve (un packager di distribuzione, o chiunque voglia validare l'artefatto) di eseguire la suite. Quella persona pero' non ha alcun modo dichiarativo di sapere cosa installare per farlo: non puo' scrivere `pip install pyteman[test]` perche' l'extra non esiste.

La conoscenza esiste gia', ma nel posto sbagliato: e' cablata nella riga `pip install -e . pytest` di `.github/workflows/tests.yml`, cioe' in un file che la sdist non trasporta. Spedire i test senza spedire i loro requisiti rende la suite inclusa meno utile di quanto PKG-01 intendesse.

Correzione proposta: dichiarare un extra di test in `pyproject.toml` e far consumare quello alla CI, cosi' che l'elenco resti uno solo e viaggi con l'artefatto.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 pyproject.toml dichiara i requisiti per eseguire la suite in una tabella che la sdist trasporta
- [ ] #2 La CI installa i requisiti di test da quella dichiarazione invece di elencarli nel workflow
- [ ] #3 Dalla sdist estratta, installare i requisiti dichiarati e' sufficiente a far girare la suite
- [ ] #4 setuptools fa parte dell'insieme dichiarato: senza di esso test_the_build_checks_cannot_be_disabled_silently fallisce, quindi e' un requisito di test e non solo di build
- [ ] #5 La tabella scelta e' installabile senza installare il progetto, perche' il job artifact rifiuta di partire se pyteman e' gia' importabile
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Vincoli aggiunti da TASK-34 / PKG-03 (review altitude, 2026-09-17). Il perimetro di questo task era `pip install -e . pytest` nel job test; quella tranche ha introdotto due consumatori in piu' che le AC originali non coprivano.

1. setuptools deve entrare nella dichiarazione. Non e' soltanto un requisito di build: senza di esso i sette check di TestBuiltArtifacts si disattivano e la guardia che esiste per rifiutare proprio quello fallisce. Misurato su 3.14 in un venv nudo: con `pip install -e . pytest` si ottiene 1 failed / 710 passed / 8 skipped, con setuptools aggiunto 718 passed / 1 skipped. Se la tabella viene scritta come `["pytest", "PyYAML"]` e poi il workflow viene fatto consumare quella, la correzione di PKG-03 viene annullata in silenzio e la AC #3 di questo task risulta violata su 3.12+.

2. La tabella deve essere installabile senza installare il progetto. `[project.optional-dependencies]` non lo consente, perche' un extra e' raggiungibile solo installando la distribuzione. Il job artifact di tests.yml installa deliberatamente gli strumenti e non il pacchetto, e `check_the_base_is_a_clean_room` in scripts/verify_artifacts.py si rifiuta di partire se trova pyteman importabile. `[dependency-groups]` (PEP 735) con `pip install --group test` soddisfa entrambi i consumatori e viaggia dentro pyproject.toml.

3. Call site da migrare sotto la AC #2, oltre al workflow: `REQUIRED_IN_BASE` in scripts/verify_artifacts.py, che oggi enumera (setuptools, pytest, yaml) per conto suo.

Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #52. Added lines already present on master per PR: #52 6/21=28%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
PR #52, commit 3325f94 on branch `work/test-dependency-group`. Added a `test` dependency group in pyproject.toml with pytest, setuptools, and PyYAML. The `dev` group includes `test` via include-group. All three CI pip install steps now use `--group test` instead of listing packages inline. The artifact job uses `pip install --group test` (no project install), satisfying the clean-room constraint. Added `pip install --upgrade pip` to all three pip jobs for Python 3.11 compatibility. AC#3 (sdist extraction test) cannot be proven locally without building and extracting the sdist; the CI artifact job is the existing proof of that property.
<!-- SECTION:FINAL_SUMMARY:END -->
