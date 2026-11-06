---
id: TASK-130
title: >-
  Un solo binder per le regole servite: _make_dispatcher e _extend_dispatcher
  duplicano seed di stato, signature e split entry/exit
status: Done
assignee: []
created_date: '2026-09-17 05:14'
updated_date: '2026-09-27 11:16'
labels:
  - audit-2026-09-17
  - simplify-gate
  - opus-5
  - rt
dependencies:
  - TASK-2
references:
  - 'src/pyteman/patcher.py:1072'
  - 'src/pyteman/patcher.py:1266'
  - 'src/pyteman/patcher.py:1213'
  - 'src/pyteman/patcher.py:1285'
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Rilievo del gate /simplify del 2026-09-17. NON e' un bug: il codice attuale e' corretto e la suite lo dimostra. E' un rischio di manutenzione della classe "ne ho mancato uno", che si manifesta solo a runtime.

**La duplicazione.** `_make_dispatcher` e `_extend_dispatcher` in `src/pyteman/patcher.py` costruiscono la stessa cosa in due modi:

- la comprehension che lega le spec, :1072-1074 contro :1266-1268, identiche fino al letterale `{"fires": 0, "seen_keys": set()}` e al segnaposto `_`;
- il calcolo della signature, :1085-1102 contro :1258-1264;
- lo split entry/exit, :1113-1115 contro :1269-1270 e :1279-1280.

**Sono equivalenti, non solo simili.** Su un composite appena creato: `comp.served` e' vuoto quindi `fresh` coincide con `slot.specs`; `sig is None and not sig_unparseable` riduce la guardia a `_needs_signature(slot.specs)`; e `slot.specs` e' gia' in ordine di ordinale perche' viene accodato sotto `enumerate(self._plan)`, quindi il `sorted(comp.entries + entries, key=ordinal)` e' l'identita'. `_make_dispatcher` potrebbe costruire un `_Composite` vuoto e chiamare lo stesso binder.

**Costo concreto.** Il seed di stato per regola, l'insieme `(TypeError, ValueError)` e il predicato entry/exit vivono in due posti. Aggiungere un terzo contatore allo stato compila pulito dopo averlo applicato a uno solo dei due, e produce regole il cui gating dipende da QUANDO sono arrivate: presto o tardi. E' esattamente la classe di difetto che questa tranche esiste per chiudere.

**Stessa forma, secondo sito.** La ricostruzione di `_pyteman_state` e' scritta tre volte, a :610, :1213 e :1285, e il costruttore la scrive in modo diverso dagli altri due (da `bound` invece che da `comp.rank()`). L'invariante "lo stato rispecchia rank()" e' quindi asserito indipendentemente da costruttore, estensore e rollback. Un `_republish_state(dispatcher)` lo mette in un posto solo.

**Terza, minore.** Il formato dei nomi in `applied`, `f"{modname}:{spec[0].symbol}"`, e' scritto a :897, :959 e :985.

**Perche' non applicato nella tranche.** Il vincolo di coordinamento in vigore limita le modifiche al core alias a bug e criteri di accettazione, e questa non e' ne' l'uno ne' l'altro. La dedup dei due rami `owner is self` resta invece deliberatamente NON fatta, per la ragione gia' registrata nel piano di TASK-2: i due rami dicono cose diverse nei commenti e servono entrambi l'innesto.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Il seed di stato per regola, il calcolo della signature e lo split entry/exit esistono in UN solo posto, chiamato sia dalla costruzione sia dall'estensione
- [x] #2 La ricostruzione di _pyteman_state esiste in un solo posto e i tre siti attuali la chiamano, cosi' l'invariante 'lo stato rispecchia rank()' e' asserito una volta
- [x] #3 La formattazione dei nomi in applied esiste in un solo posto e i tre siti attuali la chiamano
- [x] #4 I due rami owner is self restano separati con i loro commenti: la dedup riguarda il binder, non i rami
- [x] #5 Suite completa verde e l'armamentario di mutation testing della tranche RT-02 rieseguito senza sopravvissuti
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Merged as ebc9fba via PR #161 (head e6863b7, on top of the re-applied consolidation after the first attempt's edits were lost in a branch-switch and the review correctly blocked on the baseline-only commit). Review cycle: first verdict CHANGES-REQUIRED at ac6882e (F1 the rationale was duplicated, not moved; F2 the task file unrecorded), re-review APPROVED at e6863b7 with the runtime probe showing the state marker mirroring rank() and the mirror matching the ledger across install, extension, rollback, refusal and uninstall. Consolidation now single-homes: _bind_fresh (the only state seed), _split_events (the only entry/exit split), _republish_state (the only _pyteman_state writer, called from construction, coroutine construction, extension and rollback; construction is the identity case where rank() of a fresh composite is the bound list). Gates: battery check clean, 1271 passed 2 skipped; PR CI green; master CI green. The owner-is-self branches remain separate per AC #4.
<!-- SECTION:FINAL_SUMMARY:END -->
