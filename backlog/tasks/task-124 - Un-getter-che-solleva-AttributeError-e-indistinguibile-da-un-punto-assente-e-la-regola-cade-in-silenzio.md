---
id: TASK-124
title: >-
  Un getter che solleva AttributeError e' indistinguibile da un punto assente, e
  la regola cade in silenzio
status: Done
assignee: []
created_date: '2026-09-17 04:34'
updated_date: '2026-09-27 01:01'
labels:
  - patcher
  - diagnostics
  - silent-drop
dependencies: []
references:
  - src/pyteman/patcher.py
  - README.md
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Trovato durante il code-review della tranche RT-02 (2026-09-17) e deliberatamente NON corretto li', perche' non e' una regressione della tranche: il comportamento e' preesistente e coerente fra le due letture. Filato come task propria invece che sepolto in una nota, perche' e' indipendente da RT-02 e ha un contratto osservabile tutto suo.

IL FATTO. `_patch` interroga lo slot con `getattr(container, name, _ABSENT)` in pass 2 (due punti: la rilettura in cima al loop e quella immediatamente prima della scrittura) e con `hasattr(container, name)` in pass 1. Tutte e tre le forme trattano una `AttributeError` SOLLEVATA DA DENTRO come "attributo assente". Sono equivalenti per costruzione: `getattr` con default cattura `AttributeError` da qualunque origine, e `hasattr` e' definito come `getattr` con default.

PERCHE' NON E' UN DETTAGLIO. Il container puo' essere una classe o un'istanza, e quindi l'attributo puo' essere una property. Una property il cui getter solleva `AttributeError` per una ragione qualunque, anche del tutto scorrelata (una dipendenza non inizializzata, una config mancante, un `self._x` non ancora impostato), viene letta da pyteman come "questo punto non esiste". La regola che lo nomina viene saltata in SILENZIO, non compare in `applied`, non compare nel ledger, e il processo esce 0 avendo iniettato meno di quanto scritto nel ruleset.

E' esattamente la classe di fallimento che README.md:35-44 documenta per il punto assente ("un typo in un `point:` ti costa quella regola in silenzio, controlla il log dei firing e non il codice di uscita"), ma per una causa che NON e' un typo e che il ruleset author non ha alcun modo di sospettare: il punto esiste, il nome e' scritto giusto, e il ruleset e' corretto. Il messaggio operativo del README, "controlla il log dei firing", resta l'unico appiglio, ma la diagnosi a valle e' molto piu' difficile perche' non c'e' niente di sbagliato da trovare nel ruleset.

DA DECIDERE, e la decisione precede il codice. Tre opzioni, non equivalenti:

1. Lasciare com'e' e DOCUMENTARLO. Un getter che solleva AttributeError sta dicendo, nel protocollo Python, che l'attributo non c'e': trattarlo come assente e' semanticamente difendibile e non richiede codice. Costo: il silenzio resta, e resta indistinguibile dal typo.

2. Distinguere assenza da errore. Un `try: v = getattr(...) except AttributeError: ...` che ispeziona se il nome risulta comunque presente nel container (per esempio via `type(container).__dict__` o `vars(container)`) separa "non c'e'" da "c'e' ma il suo getter e' esploso". Il secondo caso puo' allora essere segnalato invece che saltato. Costo: complessita' in tre punti caldi, e la distinzione non e' totale (un `__getattr__` di modulo che solleva e' indistinguibile da uno che non definisce il nome).

3. Lasciare il salto ma renderlo RUMOROSO, cioe' registrare nel log dei firing che quel punto e' stato saltato e perche'. Costo minimo, risolve il problema vero che e' la diagnosticabilita' e non la policy. Probabilmente la risposta giusta, ma va confermata guardando cosa il log dei firing accetta oggi.

Da riprodurre sullo stato corrente prima di correggere, con una property il cui getter solleva AttributeError, verificando dove finisce la regola.
<!-- SECTION:DESCRIPTION:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Simplify-pass skips, filed rather than dropped: (1) the subprocess test harness (_run/_records plus HERE/SRC) is now a third token-identical copy across test_coroutine_entry.py, test_lazy_walk.py, and the new test_unreadable_point.py; a conftest-level run/records pair is warranted but touches two existing files, out of this diff's scope, noted on TASK-128 which already tracks hand-rolled test scaffolding. (2) The container-kind dispatch in _name_is_present duplicates _unsupported_reason's line for line; a shared value-returning lookup could serve both, a pre-existing-adjacent refactor, left to the RT-02 batch (TASK-111/130 family). (3) The walk site (parts[:-1] intermediate segment whose property raises) stays a walk miss with no record by design: the skip there is per-retry and the rule may still land, so a terminal record would carry a finality the leaf sites only tolerate for the same reason; documented as the bound in docs/rules.md, wiring it is a future option via the same helpers.

Behavior notes from the reviews: leaf skips are retried on every later import of a rule module (cache hits re-enter the hook), so a transiently broken getter that recovers still lands, and a still-broken rule accumulates one point_unreadable record per re-patch, the same per-retry staleness the absent-name path already has; the record is the package's first uncorrelated end record not written by run_action, named in docs/firing.md's status row.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Decided option 3 (loud skip) over refusal, per the task's own analysis and the altitude review's confirmation: a refusal would hard-fail installs that today succeed after a transient getter failure, and the record is the advisory signal the diagnosticability gap needs. Merged as c368b04 via PR #146 (head 5643d6e). The record is scoped to the leaf gates (a raising intermediate segment stays a walk miss, no record) and the module-__getattr__ indistinguishability is stated as the bound. Gates: /simplify 4-angle findings applied (read-and-capture helper killing the double getter run, _terminal reuse with the deferred message, MRO hoist, docs scope and firing.md status row); code-reviewer-typed high review with its should-fix applied (hostile __str__ escape, pinned by test); mutation kill; battery check clean, 1255 passed 2 skipped; independent review APPROVED at 5643d6e; master CI green.
<!-- SECTION:FINAL_SUMMARY:END -->
