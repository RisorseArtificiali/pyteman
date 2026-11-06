---
id: TASK-31
title: >-
  EX-06. Rendere riproducibili le integrazioni Hermes e documentarne i
  prerequisiti
status: Done
assignee: []
created_date: '2026-09-16 12:20'
updated_date: '2026-09-28 15:13'
labels:
  - audit-2026-09-16
  - opus-5
  - ex
  - proposal
milestone: m-4
dependencies:
  - TASK-26
  - TASK-27
  - TASK-28
  - TASK-29
  - TASK-30
references:
  - examples/
  - '.github/workflows/tests.yml:24-27'
  - 'examples/hermes-109966/pyproject.toml:9'
documentation:
  - doc-1
  - doc-2
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P2, PROPOSTA sostenuta da lacuna verificata, aperto.

**File:** entrambi i README sotto `examples/`, `.github/workflows/tests.yml:24-27`, `pyproject.toml:9`.

**Evidenza:** la CI esegue solo `tests/`; le istruzioni degli esempi indicano `pip install pyteman` e un checkout Hermes, ma non una procedura di installazione delle dipendenze upstream o un preflight delle API richieste. Il checkout locale dell'audit non espone tali API. Le affermazioni sulle PR sono storiche, non contratti universali per qualsiasi tip.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 un percorso documentato riproduce i casi attesi su revisioni effettivamente testate; un checkout incompatibile termina subito e chiaramente; i test unitari dei driver non richiedono download upstream.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Proposta iniziale da verificare sul codice corrente, non una correzione già applicata.

fixture/unit test locali del driver più job di integrazione Linux separato e opt-in su revisioni upstream fissate. Registrare provenienza e prerequisiti; rilevare API mancanti con errore azionabile prima di creare processi. Rendere i riferimenti a grace/PR esplicitamente legati alla revisione, senza aggiornare i risultati storici per deduzione.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: EX-01 fino a EX-05 per attribuire valore ai risultati integrati.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.

Code review follow-up (2026-09-28, belt on the final fix diff, confidence about 40, SKIPPED deliberately): the README from-nothing recipes chain only their first line on mktemp success (E=$PWD W=$(mktemp -d) && cd "$W"); pasted line by line, later lines would still run in the examples dir if mktemp failed. Not fixed because the only stopper that works when pasted is '|| exit', which closes the reader's interactive shell; mktemp failure is rare and the scripted path (examples/verify_hermes_legs.sh) is set -e with an ERR trap armed first.

Chiuso 2026-09-28. PR #181 squash-merged come f2a4ea3 (albero identico all'head approvato 4df2028). Gate: suite 1390 passed 2 skipped rc 0 su 4df2028 (~/pyteman-evidence/t31/suite4.log); check all passed; CI PR tutta verde (quality, test 3.11-3.14, coverage, artifact); review indipendente APPROVED a 4df2028 (~/pyteman-evidence/task123-review/FINDINGS-31-VERDICT.md): legs 5/5 da zero con pyteman del checkout e con pyteman==0.2.0, rifiuti end-to-end rc 2 senza home residua, test unitari verdi sotto unshare -rn, mutazioni M1-M4 tutte uccise. Workflow hermes-legs lanciato su master f2a4ea3, run 36441445864: LEGS: all matched. Percorso documentato: examples/verify_hermes_legs.sh [pyteman-spec] [workdir] e le ricette nei README. Osservazioni info della review: KeyboardInterrupt esce 130 (azione dell'operatore, voluto); la preflight controlla nomi, non firme (il wrapper copre il resto con exit 2); la frase sui PR del 2026-09-15 e' datata e non verificata; docstring _run stantia pre-esistente archiviata come TASK-190. Il riferimento examples/hermes-109966/pyproject.toml:9 nella descrizione e' stantio: il file non esiste.
<!-- SECTION:NOTES:END -->
