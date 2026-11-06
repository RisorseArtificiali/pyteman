---
id: TASK-115
title: >-
  RT-02h. Una condizione puo' riscrivere il ctx condiviso: args e kwargs restano
  corrotti per ogni regola successiva
status: Done
assignee: []
created_date: '2026-09-17 03:42'
updated_date: '2026-09-18 23:00'
labels:
  - rt-02
  - conditions
  - patcher
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`eval_expr` in conditions.py chiama `eval(code, _EVAL_GLOBALS, ctx)`, quindi il ctx per-chiamata e' la mappa LOCALS della eval. Una assignment expression dentro `when` scrive direttamente in quel dict, che e' lo stesso per tutte le regole sullo slot: `(exc := None) is None` e' una condizione valida che lascia il nome rebindato per ogni regola valutata dopo.

Il caso su `exc` era una violazione del contratto 4 (ogni exit raggiunta vede l'eccezione del corpo) ed e' gia' chiuso in patcher.py ri-seminando `ctx["exc"]` dentro il loop exit accanto a `ctx["result"]`, con regressione `test_one_exits_condition_cannot_hide_the_body_error_from_the_next` e mutation proof. `fires` era gia' salvo perche' `_gate` lo riscrive dallo stato della regola prima di ogni eval.

Restano scoperti `args`, `kwargs` e le chiavi interne `_signature` / `_signature_unparseable`, seminate una sola volta per chiamata: una regola che le rebinda consegna il valore rebindato a ogni regola sotto di lei, su entry e su exit. Il ri-seeding per-regola chiude i casi uno per uno; il fix completo e' valutare ogni condizione contro una copia dentro `eval_expr`, che elimina la classe intera.

conditions.py e' fuori dalla ownership autorizzata di TASK-2, per questo il lavoro e' separato. Il comportamento attuale e' documentato in docs/rules.md nella lista dei limiti delle condizioni.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Una assignment expression in `when` che rebinda `args` o `kwargs` non cambia il valore visto dalle regole successive sulla stessa chiamata
- [x] #2 Il fix e' nel punto in cui il ctx viene passato alla eval, non un ri-seeding aggiunto per ogni nome
- [x] #3 Una regola che scrive nel proprio ctx continua a rileggere quello che ha scritto dentro la stessa espressione, cioe' il walrus resta utilizzabile come variabile temporanea
- [x] #4 Esiste un test di regressione per `args` e uno per `kwargs`, entrambi uccisi da una mutazione che rimuove il fix
- [x] #5 docs/rules.md perde la nota che rinvia questo lavoro e descrive il comportamento finale
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Consegna con TASK8 in una sola unità logica: namespace fresco condiviso come globals e locals della singola eval. Nessun ri-seeding per nome, rebinding confinato alla valutazione, oggetti referenziati non copiati in profondità. Aggiungere regressioni args e kwargs sulle regole successive e controlli di mutazione con locals=ctx. Mantenere walrus temporaneo leggibile nello stesso scope/espressione e documentare lifetime di generator/closure. Nessun compatibility shim.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Il confine precedente era di ownership rispetto a TASK2, non un requisito tecnico per tenere separati due fix dello stesso eval_expr. L'utente ha autorizzato ripresa autonoma per unità logiche senza retrocompatibilità. TASK8 e TASK115 ora procedono insieme; agente herdr pyteman-backlog-audit incaricato in copia isolata, nessuna applicazione shared finché review/gate non sono completi. AC4 ancora da verificare; non dichiarato Done per sola conseguenza apparente del fix.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Chiuso con TASK8 nella PR6, merge f1ce0d2df747ee7762df793e244e1d77d21c8f0e. Il fix è in eval_expr: namespace fresco come globals e locals, senza ulteriori ri-seeding nel patcher. Rebinding args/kwargs resta locale alla valutazione, walrus temporaneo resta utilizzabile dentro l'espressione. Due regressioni args/kwargs falliscono sotto mutante split-ns; reviewer delta ha riprodotto indipendentemente kill set e approvato patch444342cd.

Suite indipendente e shared: 946 passed, 1 skipped opzionale. CI PR35403781421 success sui sei job, incluse quattro versioni Python, artifact e coverage. PR verificata MERGED senza review/commenti pendenti. Nessuna promessa deep-copy/sandbox: gli oggetti referenziati restano condivisi, limite documentato.
<!-- SECTION:FINAL_SUMMARY:END -->
