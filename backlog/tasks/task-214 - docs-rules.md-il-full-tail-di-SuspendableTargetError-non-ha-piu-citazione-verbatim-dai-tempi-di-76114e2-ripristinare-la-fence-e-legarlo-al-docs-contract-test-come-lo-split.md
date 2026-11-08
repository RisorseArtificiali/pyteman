---
id: TASK-214
title: >-
  docs/rules.md: il full-tail di SuspendableTargetError non ha piu' citazione
  verbatim dai tempi di 76114e2; ripristinare la fence e legarlo al
  docs-contract test come lo split
status: To Do
assignee: []
created_date: '2026-11-07 22:14'
updated_date: '2026-11-08 17:15'
labels:
  - docs
  - refusal-wording
dependencies: []
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Emerso dall'ALTITUDE della /simplify sul set TASK-151 (2026-11-07). Il commento nuovo su _SUSPENDABLE_TAIL dichiarava "docs/rules.md quotes this verbatim" ed era falso: grep whitespace-flattened su tutto docs/ da zero occorrenze di "so entry and exit cannot be timed". La causa e' storica e verificata in git: rules.md citava davvero il full-tail in una fence fino a 9e9ae4f, poi 76114e2 (TASK-141, entry events su coroutine function) sostitui' la fence con la citazione dello split, e 97c71ce aggiunse il docs-contract test legando SOLO lo split. Da allora il full-tail non ha piu' citazione nei docs: la sua unica enforcement e' la substring assertion in tests/test_activation_atomic.py.

Il problema vero: l'asimmetria e' invisibile. Chi riscrive _SUSPENDABLE_TAIL cerca la citazione in rules.md, non la trova, e puo' concludere che il docs-contract test copra anche questo wording mentre copre solo lo split.

Direzione raccomandata dalla review (il set T151 corregge il commento allo stato vero; questo task fa il passo in piu'):
1. Ripristinare in docs/rules.md una fence verbatim con il messaggio full-tail accanto alla frase "with the original message" (rules.md:757).
2. Estendere tests/test_docs_rules.py (il test esistente e' test_the_documented_split_refusal_is_the_built_one, riga 71) con il caso full-tail costruito tramite _SUSPENDABLE_TAIL, esattamente come il test dello split costruisce tramite _coroutine_exit_refusal.
3. A quel punto il contratto del full-tail ha lo stesso binding docs+builder+test che ha gia' lo split, e il commento sulla costante ridiventava citabile alla lettera (aggiornarlo in consegna).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 docs/rules.md contiene di nuovo una fence verbatim con il messaggio full-tail di SuspendableTargetError, collocata accanto alla frase che oggi dice solo with the original message
- [ ] #2 tests/test_docs_rules.py estende il binding docs-contract al full-tail costruendo il messaggio tramite _SUSPENDABLE_TAIL, con whitespace collapsed su entrambi i lati, nello stile di test_the_documented_split_refusal_is_the_built_one
- [ ] #3 I commenti su _SUSPENDABLE_TAIL in patcher.py e sulla guardia del pin in tests/test_activation_atomic.py, che dal set T151 in poi non asseriscono lo stato delle citazioni nei docs, restano veri senza edit oppure vengono aggiornati nello stesso change
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Scope addition 2026-11-08 (from T149's code review): the SPLIT refusal door still names its rule twice (in-message suffix plus the installer note), and TASK-149 AC2's live evidence was filed against exactly that door. T149 deliberately excluded it because the split text is the one docs/rules.md quotes verbatim, so deduplicating it means changing the documented example output and its fence test together. That decision belongs here, where the docs binding of the suspendable texts is already the subject: while restoring the full-tail fence, also decide whether the split keeps its in-message description or moves to notes-only with the docs quote updated in the same change.

2026-11-08 frontmatter completion (from the whole-project code review): this file lacked the updated_date and priority fields its sibling review-finding tasks carry; both added via this edit (priority Low to match the family). No content change.
<!-- SECTION:NOTES:END -->
