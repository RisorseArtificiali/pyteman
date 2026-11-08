---
id: TASK-213
title: >-
  patcher: la clausola condivisa " refused rather than installed for " e'
  scritta a mano in quattro punti, e il commento 2791-2793 promette ai docs una
  citazione che non c'e'
status: To Do
assignee: []
created_date: '2026-11-07 22:12'
updated_date: '2026-11-08 17:15'
labels:
  - cleanup
  - refusal-wording
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Emerso dalla /simplify REUSE sul set TASK-151 (e84f725, 2026-11-07), livello basso, non bloccante per quel set.

La clausola condivisa " refused rather than installed for " e' scritta a mano in quattro punti di src/pyteman/patcher.py dopo il set T151:

    548          _SUSPENDABLE_TAIL (nuovo, set T151)
    1454-1455    _refuse_unsupported
    1468-1469    _coroutine_exit_refusal
    2755         inline nel not-callable UnsupportedTargetError

La clausola e' un contratto verbatim pinnato dai test (tests/test_unsupported_targets.py:652-653, tests/test_coroutine_entry.py:317, tests/test_activation_atomic.py:5028), quindi oggi una modifica di wording richiede quattro edit coordinati e un drift spezza silenziosamente il contratto di un MESSAGGIO DIVERSO da quello che si stava editando.

Il file ha gia' il precedente giusto: _COROUTINE_PHRASE (1458-1460) single-sources una frase verbatim condivisa, col commento esplicito "one constant, because the refusal text is quoted verbatim in docs/rules.md". La direzione naturale e' una costante propria per la clausola, da cui comporre _SUSPENDABLE_TAIL e gli altri tre siti.

Insieme, va disambiguato il commento pre-esistente a patcher.py:2791-2793 ("Every other kind keeps the original wording in full, clause included: docs/rules.md promises that message verbatim"): docs/rules.md NON cita il full-tail da nessuna parte, cita verbatim solo lo split (rules.md:750-753) e chiama il full-tail "the original message" (rules.md:757); "that message" nel commento e' ambiguo e va riscritto per dire quale dei due la promessa copre davvero.
<!-- SECTION:DESCRIPTION:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Update 2026-11-08 (set T149): the _SUSPENDABLE_TAIL instance of the shared clause is GONE. The set's design moved the rule description of the generic suspendable refusal out of the message and into the installer's __notes__, so the full-tail message now ends at 'timed on it' and _SUSPENDABLE_TAIL no longer contains the clause. The handwritten copies are now THREE: _refuse_unsupported (~1454), _coroutine_exit_refusal (~1467), and the inline not-callable UnsupportedTargetError (~2754). The comment disambiguation at the raise site (original AC part 2) was also resolved by the same set: the comment now states which text the docs quote verbatim (only the split) and where the generic message names its rule.

2026-11-08 frontmatter completion (from the whole-project code review): this file lacked the updated_date and priority fields its sibling review-finding tasks carry; both added via this edit (priority Low to match the family). No content change.
<!-- SECTION:NOTES:END -->
