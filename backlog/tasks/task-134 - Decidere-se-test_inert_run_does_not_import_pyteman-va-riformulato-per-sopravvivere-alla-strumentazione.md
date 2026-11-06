---
id: TASK-134
title: >-
  Decidere se test_inert_run_does_not_import_pyteman va riformulato per
  sopravvivere alla strumentazione
status: Done
assignee: []
created_date: '2026-09-17 06:13'
updated_date: '2026-09-25 12:04'
labels:
  - pkg
  - test
milestone: m-5
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Emerso da /simplify sulla tranche TASK-34.1 e rimandato: il file appartiene a un altro agente e in quella tranche non andava toccato. Filed nello stesso turno dello skip.

**Stato attuale, misurato.** Sotto `coverage run` il test `tests/test_sitecustomize.py::test_inert_run_does_not_import_pyteman` fallisce con `['typing']` al posto di `[]`, ed e' l'unico. La catena e' tracciata per intero nelle note di TASK-34.1: `patch = ["subprocess"]` esporta `COVERAGE_PROCESS_CONFIG`, il figlio la eredita, il `.pth` di coverage importa coverage, e coverage importa `typing`. Il `typing` arriva dall'apparato di misura, non dal prodotto. Il job coverage deseleziona quel solo node id; la matrice non strumentata continua a eseguirlo a piena forza su 3.11-3.14.

**La cosa da valutare, senza prescriverla.** Il test gemello `test_inert_run_adds_nothing_to_sys_modules_but_the_shim` resta verde sotto strumentazione, perche' differenzia due figli entrambi strumentati e `typing` si cancella da solo. Riformulare il primo nello stesso modo differenziale lo farebbe sopravvivere alla misura e toglierebbe la deselezione, la sua guardia e il relativo commento da `scripts/run_coverage.py`.

**Il rovescio, che e' la ragione per cui questo e' un task e non una correzione ovvia.** I due test non misurano la stessa cosa. La forma assoluta nomina gli import proibiti e vede un baseline che importasse `typing` per ragioni sue; la forma differenziale, per costruzione, non lo vedrebbe. Il docstring del gemello argomenta gia' il contrario, cioe' che nominare gli import e' piu' fragile. La decisione e' fra due segnali diversi, e va presa guardando cosa si perde, non cosa fa passare il job.

**Non fa parte di questo task** indebolire il test per far tornare verde la misura. Se la conclusione e' che la forma assoluta vale piu' della deselezione, la risposta corretta e' lasciare tutto com'e' e chiudere il task con quella motivazione scritta.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 La decisione fra riformulare il test e tenere la deselezione e' presa sulla base di cosa i due test misurano davvero, non sulla comodita' del job coverage, ed e' scritta.
- [ ] #2 Se il test viene riformulato: passa sia strumentato sia non strumentato, dimostrato eseguendolo in entrambi i modi, e la deselezione piu' la sua guardia spariscono da scripts/run_coverage.py.
- [x] #3 Se la deselezione resta: resta anche la guardia check_the_deselections_still_resolve, perche' pytest accetta un --deselect che non combacia con nulla uscendo 0.
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Decision: keep the absolute test and the deselection.

The two tests measure different things and both are worth having. The absolute test (`test_inert_run_does_not_import_pyteman`) names the two specific imports it cares about: `typing` and `pyteman.*`. It says directly "the shim does not import these". The differential test (`test_inert_run_adds_nothing_to_sys_modules_but_the_shim`) catches any import the shim adds, named or not. Reformulating the absolute test differentially would make it a near-duplicate of the differential test, adding no new signal while losing the named-imports statement.

The deselection cost is one entry in `DESELECTED_UNDER_COVERAGE`, already guarded by `check_the_deselections_still_resolve` which verifies the node id still matches exactly one test. That guard stays in place (AC#3). The matrix job runs the test uninstrumented on 3.11 through 3.14 at full strength.

No code changes; the current arrangement is the right one.
<!-- SECTION:FINAL_SUMMARY:END -->
