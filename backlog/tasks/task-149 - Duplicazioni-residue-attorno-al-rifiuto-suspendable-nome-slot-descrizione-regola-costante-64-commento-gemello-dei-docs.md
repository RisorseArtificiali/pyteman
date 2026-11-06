---
id: TASK-149
title: >-
  Duplicazioni residue attorno al rifiuto suspendable: nome slot, descrizione
  regola, costante 64, commento gemello dei docs
status: To Do
assignee: []
created_date: '2026-09-17 11:02'
updated_date: '2026-09-28 18:16'
labels:
  - opus-5
  - deferred-from-task-3
dependencies: []
references:
  - src/pyteman/patcher.py
  - docs/rules.md
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Quattro segnalazioni minori dai gate simplify e reuse durante TASK-3 (2026-09-17), lasciate fuori dal task perche' toccano codice e prose fuori dalla superficie assegnata.

1. Terza copia della resa del nome dello slot come `modname + ":" + slot.name`. Gia' presente in SlotOwnershipError e nel sito di rifiuto di TASK-3.

2. Il messaggio di SuspendableTargetError concatena `current` (la descrizione della regola) proprio dove `_note` rende gia' la stessa cosa, quindi la descrizione compare due volte nello stderr di startup.

3. `docs/rules.md` scrive 64 a mano dove il codice ha `_WRAPPER_CHAIN_LIMIT`. Verificato che `tests/test_docs_rules.py` oggi non aggancia quel numero, quindi un cambio della costante lascerebbe la documentazione a mentire in silenzio.

4. Il commento in `src/pyteman/patcher.py` intorno alle righe 825-892 ripete quasi parola per parola `docs/rules.md` righe 495-522.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Esiste un solo punto che rende modname:slotname e i tre siti lo chiamano.
- [ ] #2 Il messaggio di SuspendableTargetError non duplica la descrizione della regola gia' resa da _note o da __init__.
- [ ] #3 docs/rules.md non contiene il numero 64 scritto a mano: o cita il nome della costante, o il valore e' verificato da un test.
- [ ] #4 Il commento in patcher.py che ripete docs/rules.md e' ridotto a un rimando.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
ALTITUDE GATE OBSERVATION, 2026-09-17, relevant to how this is fixed rather than a new defect.

_suspendable_reason decides which of three kinds it found at patcher.py:619-623 and then immediately discards that decision into an English phrase. Returning a kind token and rendering the phrase at the raise site would remove the message duplication this task already files, and would also give TASK-37 the kind as data instead of forcing it to re-walk the same chain or string-match the phrase to select a dispatcher.

The gate flagged this as an observation, not a recommendation, on the grounds that it is speculative generality if TASK-37 never lands. Recorded here because if this task is done anyway, the token form costs nothing extra and closes both.

Confirmed live stderr showing the duplication this task is about:

  pyteman: refusing to start: installing instrumentation: SuspendableTargetError: pyteman: _collections_abc:asend is a coroutine function, so entry and exit cannot be timed on it; refused rather than installed for rule 'suspendable' at _collections_abc:AsyncGenerator.asend | pyteman: while patching rule 'suspendable' at _collections_abc:AsyncGenerator.asend

The rule description appears twice and the 'pyteman:' prefix three times in one line.

Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #59. Added lines already present on master per PR: #59 3/34=8%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.
<!-- SECTION:NOTES:END -->
