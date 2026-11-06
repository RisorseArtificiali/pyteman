---
id: TASK-47
title: >-
  CFG-07. Validare al load tutti i nomi liberi delle espressioni contro il
  namespace di valutazione
status: Done
assignee: []
created_date: '2026-09-16 14:02'
updated_date: '2026-09-26 09:01'
labels:
  - audit-2026-09-16
  - cfg
  - follow-up
dependencies:
  - TASK-7
  - TASK-8
references:
  - src/pyteman/rules.py
  - src/pyteman/conditions.py
  - src/pyteman/patcher.py
  - docs/rules.md
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Aperto da TASK-7 (CFG-01) il 2026-09-16 su segnalazione del code review. AGGIORNATO il 2026-09-16 dopo la verifica indipendente dell'orchestrator, che ha cambiato la premessa del task.

**Lo stato descritto qui prima non esiste piu'.** La versione originale diceva che CFG-01 aveva aggiunto `_free_names` e ne usava l'output per un solo controllo. Quella funzione, insieme a `_reject_exit_only`, e' stata RIMOSSA da `src/pyteman/rules.py`. Oggi il loader compila le espressioni ma non risolve nessuno dei nomi che leggono: la validazione del namespace e' interamente di competenza di questo task.

**Perche' e' stata rimossa, misurato e non dedotto.** `symtable.symtable(code, '<pyteman>', 'eval').get_symbols()` non ricorre negli scope figli, quindi `(lambda: result)()` produce una tabella di primo livello VUOTA; e un walrus marca il proprio target come assegnato, quindi `result or (result := 1)` risulta `is_assigned() == True` benche' la lettura preceda l'assegnazione. Il predicato `is_global() and not is_assigned()` scartava entrambi. Sotto `eval` entrambi alzano `NameError: name 'result' is not defined`: erano falsi negativi reali, non teorici. Nel frattempo il controllo rifiutava `False and result`, che va in corto circuito e non viene mai valutato. Rifiutare la forma piatta mentre si lasciano passare due NameError e' una garanzia che inganna.

**Questo task e' ESPLICITAMENTE OPZIONALE.** Non e' un debito da saldare: e' una proposta da progettare, e chiuderlo con "il namespace resta non validato al load" e' un esito accettabile. La condizione posta dall'orchestrator e' che, se lo si implementa, la validazione sia COMPLETA. Una seconda versione parziale ricrea esattamente il difetto appena tolto.

**Il namespace da validare**, se si procede: `conditions._SAFE` (len, str, int, float, bool, abs, min, max, sorted, isinstance) piu' le chiavi che `patcher.py` mette nel contesto (args, kwargs, fires, e sul ramo exit anche result ed exc), con `__builtins__` svuotato.

**Nota che resta valida dal review originale:** un allowlist generale NON coprirebbe i casi di TASK-8 (CFG-02). `max(x < kwargs['limit'] for x in args)` usa solo nomi noti, e il suo NameError nasce dal fatto che lo scope della comprehension non vede `ctx` come globals, non da un nome sconosciuto. I due controlli sono complementari, non sostituti.

Esempio concreto oggi non intercettato: `any(result for result in args)` si carica senza errori e poi fallisce al firing, perche' `any` non e' in `_SAFE`.

Fino ad allora il contratto e' documentato invece che imposto: `docs/rules.md`, sezione "Where each check happens", dice quali nomi esistono, su quale evento, e che un `entry` che nomina `result` alza NameError dentro la chiamata strumentata. Il docstring di modulo di `rules.py` porta la stessa motivazione, dove la legge chi riapre il file.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Il task e' ESPLICITAMENTE OPZIONALE: e' legittimo chiuderlo decidendo che il namespace resta non validato al load e che il contratto vive in docs/rules.md. Va deciso, non lasciato implicito.
- [ ] #2 Se si implementa: la validazione e' COMPLETA o non esiste. symtable da solo non basta, va percorsa la ricorsione su get_children() e trattata la lettura che precede un walrus; una copertura parziale e' peggio di nessuna copertura ed e' il motivo per cui il controllo precedente e' stato rimosso.
- [x] #3 La decisione e' presa dopo TASK-8, non prima: CFG-02 cambia cosa vedono gli scope annidati, quindi un allowlist scritto oggi sarebbe sbagliato domani.
- [ ] #4 Regressioni sui falsi negativi misurati: '(lambda: result)()' e 'result or (result := 1)' devono essere rifiutati su un evento entry, perche' entrambi danno NameError al firing oggi.
- [ ] #5 Regressioni sui falsi positivi noti: accesso ad attributo, nome come keyword argument, chiave stringa in un subscript, nome legato da comprehension inlined (PEP 709), parametro di lambda.
- [ ] #6 Il caso che il controllo non puo' decidere staticamente, la raggiungibilita' (es. 'False and result'), e' documentato esplicitamente invece di essere indovinato.
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Decided: the expression namespace stays unvalidated at load. The contract lives in docs/rules.md, section "Where each check happens", which documents which names exist on which event and that a NameError surfaces inside the instrumented callable at firing time.

Reasoning: the previous partial implementation (symtable-based _free_names in rules.py) was removed during TASK-7 after the orchestrator's independent verification showed two false negatives: symtable.get_symbols() does not recurse into nested scopes, so (lambda: result)() produced an empty top-level table; and a walrus expression marks its target as assigned, so result or (result := 1) appeared assigned despite the read preceding the assignment. Both raise NameError at firing time and were silently accepted. Meanwhile, the check rejected False and result, which short-circuits and never evaluates result.

A partial validation is worse than none: it creates false confidence while leaving the real gaps open, which is exactly the defect that led to the removal. A complete implementation (recursive scope walking, walrus-before-read detection, short-circuit reachability analysis, full namespace including conditions._SAFE and all patcher context keys) would require changes to conditions.py, rules.py, patcher.py, and docs/rules.md, most of which currently have open PRs.

The existing documentation is the correct mitigation for this case: a rule that names an unavailable variable fails loudly at firing time, and docs/rules.md tells the operator exactly which names exist on which event.

Decision taken after TASK-8 (Done), as AC #3 requires: CFG-02's namespace changes (eval_expr now uses a fresh namespace for globals/locals) are the baseline this decision rests on.
<!-- SECTION:FINAL_SUMMARY:END -->
