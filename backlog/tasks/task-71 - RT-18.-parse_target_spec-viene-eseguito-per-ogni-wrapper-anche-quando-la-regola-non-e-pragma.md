---
id: TASK-71
title: >-
  RT-18. parse_target_spec viene eseguito per ogni wrapper anche quando la
  regola non e' pragma
status: Done
assignee: []
created_date: '2026-09-16 18:45'
updated_date: '2026-09-27 08:38'
labels:
  - rt
  - opus-5
  - from-review
  - performance
  - audit-2026-09-16
dependencies:
  - TASK-1
references:
  - src/pyteman/patcher.py
  - src/pyteman/targets.py
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Emerso dalla review Efficiency del finale RT-01 (2026-09-16). Preesistente a RT-01: il tranche ha riscritto solo il commento sopra e la riga `def`, non l'espressione. Declinato dentro RT-01 perche' fuori dal perimetro dichiarato.

**Il problema.** In `Patcher._make_wrapper`, la riga `parsed, _ = parse_target_spec(str(rule.action.get("target", "")))` viene valutata incondizionatamente, e il risultato viene usato solo dentro `if rule.action.get("kind") == "pragma" and parsed is not None and parsed[0] == "param"`. Ogni regola non-pragma paga una `str()` e un parse completo il cui risultato viene scartato.

**Il costo.** Una parse piu' una `str()` per ogni callable strumentato, sul percorso di install, non su quello di firing. Non e' un hot path: e' lavoro sprecato allo startup, proporzionale al numero di regole che effettivamente patchano qualcosa.

**La correzione.** Testare `rule.action.get("kind") == "pragma"` per primo e cortocircuitare. La condizione composta esiste gia', va solo riordinata in modo che il termine che decide stia prima del termine costoso.

**Perche' vale comunque un task.** Non per i microsecondi. La forma attuale fa sembrare che il parse serva sempre, e chi legge deve arrivare alla fine della condizione per scoprire che non e' cosi'. Un giorno qualcuno aggiungera' un secondo consumatore di `parsed` sopra la condizione e la spesa diventera' reale.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 parse_target_spec non viene chiamato per una regola il cui kind non e' pragma, provato da un test che conta le chiamate
- [x] #2 Il comportamento dei target param: resta invariato, inclusa la nota-e-salta quando la firma non e' ispezionabile
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Merged as 1536c0f via PR #158 (head 1339b5c, test-only). The unconditional parse TASK-71 named no longer exists at HEAD: the parse lives in _needs_signature behind the kind-first check (the exact short-circuit the task prescribed), reached by the later RT-02 refactors rather than a dedicated change; a probe counting calls through the whole install path confirmed zero parses for a non-pragma rule and exactly one for a param-target pragma before any test was written. This change pins the shape with that counting test (spy on the patcher-module binding), so a future edit cannot silently move the parse back in front of the kind check. Gates: test-only (gate-exempt for simplify; the independent review still ran); battery check clean, 1268 passed 2 skipped; independent review APPROVED at 1339b5c; PR CI green; master CI green.
<!-- SECTION:FINAL_SUMMARY:END -->
