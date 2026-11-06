---
id: TASK-148
title: >-
  Harness di startup duplicato fra test_activation_suspendable_startup e
  test_sitecustomize
status: Done
assignee: []
created_date: '2026-09-17 11:02'
updated_date: '2026-09-27 02:38'
labels:
  - opus-5
  - deferred-from-task-3
  - blocked-on-ownership
dependencies: []
references:
  - tests/test_activation_suspendable_startup.py
  - tests/test_sitecustomize.py
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Trovato dal gate reuse durante TASK-3 (2026-09-17). Non applicato: il consolidamento richiede di toccare `tests/test_sitecustomize.py`, di proprieta' dell'agente pyteman-runner-opus5 e riservato a TASK-34.2.

`tests/test_activation_suspendable_startup.py` contiene `rules_file` e `run_py` quasi identici a quelli in `tests/test_sitecustomize.py`. La copia e' stata fatta apposta per non toccare il file altrui.

Da risolvere quando l'ownership si libera: estrarre l'helper in un modulo condiviso (o in conftest.py) e farlo usare a entrambi.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 rules_file e run_py esistono in un unico posto condiviso dai due file di test.
- [x] #2 Il timeout e la add_note diagnostica restano.
- [x] #3 Il proprietario di tests/test_sitecustomize.py ha acconsentito alla modifica prima che venga fatta.
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Merged as 840ba59 via PR #149 (head 3723d67). rules_file and run_py live once in tests/startup_harness.py; the timeout and the diagnostic add_note moved whole; AC #3 satisfied because TASK-34.2 (the owner of the reservation on tests/test_sitecustomize.py) is Done. The reuse reviews' additions: sitecustomize's local SRC fed the assertions about what run_py installed, so importing it from the harness closes a silent-divergence blind spot; the remaining _run copies in three other files plus test_targets.py's _rules_file are recorded on TASK-128 as the harness-migration follow-up. Gates: /simplify combined-angle findings applied (dead anchors and noqa removed, wrapper dropped, docstring de-ticketed); code-reviewer-typed high review CLEAN with every hunted item verified; battery check clean, 1263 passed 2 skipped; independent review APPROVED at 3723d67; master CI green.
<!-- SECTION:FINAL_SUMMARY:END -->
