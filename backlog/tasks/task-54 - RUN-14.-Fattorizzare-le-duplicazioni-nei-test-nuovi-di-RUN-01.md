---
id: TASK-54
title: RUN-14. Fattorizzare le duplicazioni nei test nuovi di RUN-01
status: Done
assignee:
  - '@tree-28'
created_date: '2026-09-16 16:23'
updated_date: '2026-09-29 20:50'
labels:
  - runner
  - test
  - simplify
  - review-followup
  - audit-2026-09-16
milestone: m-3
dependencies: []
references:
  - tests/test_matrix_identity.py
  - tests/test_report.py
  - tests/conftest.py
  - 'TASK-19 (RUN-01): origine'
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Raccolta degli esiti delle review Reuse e Simplification sullo stato finale di RUN-01 (TASK-19), 2026-09-16, limitatamente ai file di test. Nessun difetto: i test sono corretti e ancorati da mutazione. Nessuno applicato perche lo stato di TASK-19 era congelato e gia verificato dall'orchestrator quando le review sono rientrate.

1. `tests/test_report.py` ricostruisce a mano, in due punti, la DDL dello schema v1 con la sua riga seed, mentre il file fratello `tests/test_matrix_identity.py` ha gia fattorizzato esattamente quella cosa in `LEGACY_SCHEMA` e `legacy_db(path, cell_id, status, result)`. Entrambi i siti sono coperti dall'helper senza estensioni. Il risultato sono tre grafie della forma v1 nei due file nuovi. La forma v1 e il contratto che entrambe le suite verificano: quando viene riscritta, i test del report continuano a costruire la vecchia e continuano a passare mentre asseriscono su una forma che il runner non produce piu. E lo stesso modo di fallire in silenzio che `_RESULT_COLUMNS` esiste per impedire, uno strato piu in fuori. `tests/conftest.py` mette gia `tests/` sul sys.path, quindi l'helper si importa direttamente oppure si sposta in conftest.py, che e la sede piu pulita ora che lo vogliono due file.

2. `test_a_result_that_cannot_be_stored_fails_only_its_own_cell` e `test_a_result_that_cannot_be_serialised_at_any_depth_fails_only_its_own_cell` condividono l'impalcatura riga per riga e differiscono solo nel payload non serializzabile; le asserzioni del secondo sono un sottoinsieme stretto di quelle del primo. Una modifica al messaggio di registrazione del fallimento o al contratto sugli status va fatta due volte. Forma piu semplice: un solo test parametrizzato sul costruttore del payload, con ids `set` e `deep`, che tiene l'unione delle asserzioni. Il docstring lungo del secondo sopravvive come commento del parametro: e l'unica parte non duplicata.

3. L'asserzione anti-wrapping `"not canonically serialisable" not in str(excinfo.value)` compare con lo stesso messaggio di fallimento in `test_non_string_mapping_keys_are_refused` e in `test_a_mapping_of_mixed_key_types_is_refused_for_the_right_reason`, con nel primo un commento di quattro righe che spiega perche il match per sottostringa non basta. Entrambi esercitano la stessa clausola `except MatrixIdentityError: raise` di `_canonical`. I due test non sono ridondanti fra loro e vanno tenuti entrambi, perche il caso a chiavi miste e l'unico che fallisce sotto un'implementazione che serializza prima di controllare; a essere duplicata e la sola asserzione, che va lasciata nel test il cui nome e il cui docstring parlano gia esattamente di quella proprieta.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 La costruzione di un database con schema v1 e la sua riga seed esistono in una sola sede condivisa fra tests/test_matrix_identity.py e tests/test_report.py, preferibilmente conftest.py
- [x] #2 I due test sui risultati non serializzabili sono un solo test parametrizzato sul payload, con l'unione delle asserzioni dei due originali e ids che distinguono i due casi
- [x] #3 L'asserzione anti-wrapping resta nel solo test che ne porta il nome, test_a_mapping_of_mixed_key_types_is_refused_for_the_right_reason, con il commento che la spiega
- [x] #4 Nessuna asserzione indebolita: la batteria di mutazione continua a uccidere esattamente le stesse mutazioni di oggi, in particolare M10, M19, M22 e M23
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #70 #91. Added lines already present on master per PR: #70 9/36=25%  #91 10/46=21%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.

Merged 2026-09-29 via #190 (2065063). Evidence under /home/pantinor/pyteman-evidence/t191/: diff54.patch sha256 450a71b2, tree54-hold4.sha256, mutants-54*.log, VERDICT-54.md in t191rev.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by PR #190, squash-merged as 2065063 on master at 2026-09-29 20:49Z. AC1: the v1 DDL has one spelling, tests/sqlite_harness.py's LEGACY_SCHEMA, used by test_report.py (the criterion's conftest preference yielded to the seat the reuse audit had already blessed, where the helpers lived at base; the independent reviewer recorded it as a judgment call). Three report sites keep hand-written foreign rows on purpose: legacy_db is the migration fixture's canonical row, and those tables are deliberately degenerate shapes a foreign writer produced, one carrying a raw not-json value. AC2: the two unstorable-result tests are one parametrized test over set, cyclic and deep payloads (TypeError, ValueError, RecursionError), asserting the union of the originals' assertions in a single SELECT, with the full taxonomy in the docstring; the cyclic payload makes the previously guarded-but-unexercised ValueError shape executable. AC3: the anti-wrapping assertion lives only in test_a_mapping_of_mixed_key_types_is_refused_for_the_right_reason with its comment. AC4: the original M-numbered battery script was not recoverable, so the four named behaviours were reconstructed from their descriptions (canonical wrapping, unstorable guard breadth, adopt-only-done, cell-id refusal) and all four are killed at the merged head; the deep-payload comment names the encoder's recursion ceiling version-honestly. Supersedes #70 and #91, both closed with pointers. Gates at 38bd6e8: suite 1503 passed 2 skipped, check green, delivery 41, /simplify four angles applied, code-review high four cleanups applied, independent verdict APPROVED (VERDICT-54.md).
<!-- SECTION:FINAL_SUMMARY:END -->
