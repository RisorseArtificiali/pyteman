---
id: TASK-11
title: CFG-05. Far rispettare la grammatica target e il contratto no-throw del parser
status: Done
assignee: []
created_date: '2026-09-16 12:20'
updated_date: '2026-11-08 20:18'
labels:
  - audit-2026-09-16
  - opus-5
  - cfg
  - confirmed
milestone: m-1
dependencies:
  - TASK-7
references:
  - 'src/pyteman/targets.py:69-108'
  - 'docs/targeting.md:41-46,68-71'
documentation:
  - doc-1
  - doc-2
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P2, CONFIRMED, aperto.

**File:** `src/pyteman/targets.py:69-108`, `docs/targeting.md:41-46,68-71`.

**Evidenza:** accettati `self.`, `param:x.`, `self.map["k"]`, `self.factory()` e `param:x-y`. I primi diventano un target più corto, gli altri vengono trattati come nomi di attributi letterali nonostante il contratto escluda mapping e call. `parse_target_spec([])` alza TypeError dal decorator lru_cache nonostante la docstring "Raises nothing"; il wrapper privato _parse intercetta invece l'errore.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 round-trip di tutti i target validi, invalidi sopra rifiutati al load, input non hashable restituisce errore strutturato senza eccezione non documentata; stesso parser usato in load e runtime.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Proposta iniziale da verificare sul codice corrente, non una correzione già applicata.

parser pubblico validante prima della cache, cache solo della rappresentazione valida; distinguere delimitatore assente da componente vuota e imporre la grammatica dichiarata per nomi e passi. Se si vuole consentire nomi Python non identificatori creati con setattr, documentare la scelta invece di promettere una grammatica diversa.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: CFG-01.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.

2026-09-25: Code complete. All changes written:

**targets.py (restructured):**
1. `parse_target_spec` is now the public non-cached entry point; type guard and strip happen before the cache, making the docstring 'Raises nothing' actually true
2. New `_cached_parse` (with `@lru_cache`) contains the parsing logic; only validated stripped strings reach the cache
3. `_parse` wrapper removed (no longer needed; both `resolve_target` and `validate_target_spec` call `parse_target_spec` directly)
4. `_steps`: added `isidentifier()` check per step; rejects `map["k"]`, `factory()`, non-identifier names
5. `_cached_parse` param branch: added `isidentifier()` check; rejects `param:x-y`

**test_targets.py (7 new tests):**
- `test_parse_rejects_non_identifier_param_name` (param:x-y)
- `test_parse_rejects_subscript_in_walk` (self.map["k"])
- `test_parse_rejects_call_syntax_in_walk` (self.factory())
- `test_parse_returns_error_for_unhashable_input` ([])
- `test_parse_returns_error_for_none_input` (None)
- `test_valid_targets_round_trip` (6 valid specs)
- `test_load_rejects_non_identifier_walk_step` (full pipeline)

**docs/targeting.md:**
- Line 89: added non-identifier parameter names and attribute steps to the validation list

Blocked on: bash OOM prevents running tests and completion gates.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closure restored 2026-11-08 (tracker repair): the Done marker set on 2026-11-07 was lost to a git reset during the marathon; the work had landed. Landed by direct push 2d6b0ee (the richer #101 half of the pair, three files, seven new tests, full gate chain per the durable handoff at ~/pyteman-evidence/t191rev/HANDOFF-2026-11-06.md); PRs #98 and #101 closed with pointers 2026-11-07T18:01.
<!-- SECTION:FINAL_SUMMARY:END -->
