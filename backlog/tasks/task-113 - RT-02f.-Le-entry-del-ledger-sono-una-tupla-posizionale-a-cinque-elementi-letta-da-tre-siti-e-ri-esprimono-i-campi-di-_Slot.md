---
id: TASK-113
title: >-
  RT-02f. Le entry del ledger sono una tupla posizionale a cinque elementi letta
  da tre siti e ri-esprimono i campi di _Slot
status: Done
assignee: []
created_date: '2026-09-17 03:10'
updated_date: '2026-11-08 10:37'
labels:
  - rt
  - opus-5
  - review-rt-02
  - manutenibilita
dependencies:
  - TASK-2
references:
  - src/pyteman/patcher.py
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Trovato indipendentemente dagli agenti reuse e simplification della review /simplify su RT-02 (TASK-2), 2026-09-17. Due angoli, stesso reperto, quindi un solo task.

**Angolo simplification.** RT-02 ha portato le entry di `self._wrapped` da tre a cinque elementi. Ci sono ora tre siti che le leggono per POSIZIONE: `_live_dispatcher_owner` (riga ~245), `_undo_one` (riga ~285), e il codice di rollback in `_patch` (righe ~687-688). Con tre elementi lo spacchettamento posizionale era leggibile; con cinque chi legge deve contare, e chi aggiunge un sesto campo deve trovare tutti e tre i siti a mano. Questo e' esattamente la forma di bug "ne ho mancato uno" che la regola di progetto sui dispatch paralleli avverte di prevenire, con la differenza che qui il compilatore non aiuta: uno spacchettamento a cinque contro una tupla a sei fallisce a runtime.

**Angolo reuse.** La stessa tupla ri-esprime tre campi che `_Slot` gia' possiede: `container`, `name` e l'originale. Esistono cosi' due rappresentazioni parallele della stessa relazione, una viva durante `_patch` e una che sopravvive nel ledger, e nulla nel codice dice che sono la stessa cosa vista in due momenti.

**Direzione suggerita, non imposta.** O estendere `_Slot` con i campi che oggi vivono solo nel ledger (`dispatcher`, e il flag che dice se lo slot era gia' nostro) e conservare `_Slot` direttamente, oppure introdurre un `NamedTuple` per la entry del ledger, che e' il cambiamento piu' piccolo e mantiene lo spacchettamento dove serve. La prima opzione elimina la duplicazione, la seconda elimina solo il conteggio posizionale. Chi esegue scelga e motivi.

Precedente utile: `_ROLLBACK` in questo stesso file esiste per il MATCHING (un `startswith`), non per la deduplicazione, quindi non e' un precedente diretto per estrarre una costante qui; lo e' invece `_RETRY_AFTER_UNINSTALL`, introdotto da RT-02 proprio per non riscrivere una frase due volte.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Le entry del ledger sono una struttura con campi nominati, non una tupla posizionale a cinque elementi
- [x] #2 _undo_one, _live_dispatcher_owner e il codice di rollback leggono per nome; nessun sito deve sapere che il wrapper e' il quarto elemento
- [x] #3 container, name e original non sono piu' ripetuti in due posti: la relazione fra _Slot e la entry del ledger e' esplicita nel codice, non ricostruita mentalmente da chi legge
- [x] #4 Nessun cambio di comportamento: l'ordine di rollback, il contratto di applied e i rifiuti di uninstall restano identici, dimostrato dalla suite invariata
- [x] #5 La suite completa passa senza modifiche ai test, salvo quelli che leggono direttamente la forma delle entry di _wrapped, adattati alla nuova forma
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-09-25: Code complete. All changes written:

**patcher.py (4 edits):**
1. `import collections` added (line 1)
2. `_LedgerEntry = collections.namedtuple(...)` defined after `_Slot` (line 1247), with comment linking fields to `_Slot`
3. `_live_dispatcher_owner` (line 279): `for entry in owner._wrapped: if entry.wrapper is fn:` (was positional unpacking with 5 underscores)
4. `_undo_one` (line 318): all access via `entry.container`, `entry.name`, `entry.original`, `entry.wrapper`, `entry.owned` (was positional tuple unpacking)
5. Creation site in `_patch` (line 2308): `wrapped.append(_LedgerEntry(...))` (was raw tuple)

**test_activation_atomic.py (3 edits):**
1. `_LedgerEntry` added to imports from `pyteman.patcher`
2. `_entry` helper returns `_LedgerEntry(...)` instead of raw tuple (line 74)
3. Hand-built entry at line 1645 changed from raw tuple to `_LedgerEntry(...)`

Design choice: `collections.namedtuple` over `typing.NamedTuple` because patcher.py uses no type annotations. NamedTuple is a tuple subclass, so all test list comprehensions using positional unpacking (lines 400, 1480, 2959, 3091, 3291, 3297) continue working unchanged.

Blocked on: bash OOM prevents running tests and completion gates.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by direct push 9f2b87a on master (base 0613029); PR #100 closed with a pointer. AC1: the ledger holds _LedgerEntry (container, name, original, wrapper, owned), a namedtuple so the sort in _undo, identity comparisons and positional test unpacks keep tuple semantics. AC2: every reader is by name, in src (_undo_one, the creation site, the mirror bookkeeping in _undo and _publish, displaced()'s composite walk, wrapper set and held comparison; _live_dispatcher_owner no longer reads the ledger at all since master's wrapped-by-id mirror answers it) AND in tests: the eleven sites that unpacked positionally are converted, so a field reorder reddens them instead of passing on tuple affinity; the skeptic's census closed the LEDGER class empty across the whole worktree over three rounds, with the OTHER class (plan and pending records, refusal triples, spec structures) documented and untouched. AC3: the entry's comment names the _Slot it restates; the simplify altitude review judged the two structures deliberate (per-call resolution state vs install-time record with different lifecycles), matching the file's own _ResolvedSpec/_BoundSpec precedent. AC4: behavior unchanged, proven by the field-swap mutation reddening 73 tests, the rename probe failing loudly at the first forgotten use, the mirror-pairing probe reddening exactly the retired-dispatcher test, and the full suite green. AC5: only the shape-reading tests were adapted. Gate chain: /simplify 4/4 CLEAN, /code-review high with all dispositions verified (its sweep independently flagged the same two missed test reads the skeptic found), skeptic rounds CONFIRMED with the census CLOSED and sha verified, battery green (h7wgmq2b: 1606 collected, 1603 passed, 3 declared skips; the first run was refused by a load-induced kill-race flake in test_matrix_attempts, filed as TASK-218 with the reasoning that the delta cannot reach it, green in isolation and on the identical-sha re-run). The plan-and-pending sibling refactor found in review is filed as TASK-217.
<!-- SECTION:FINAL_SUMMARY:END -->
