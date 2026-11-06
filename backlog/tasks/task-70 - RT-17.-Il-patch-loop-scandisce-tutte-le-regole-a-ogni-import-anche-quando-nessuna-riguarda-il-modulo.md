---
id: TASK-70
title: >-
  RT-17. Il patch loop scandisce tutte le regole a ogni import, anche quando
  nessuna riguarda il modulo
status: Done
assignee: []
created_date: '2026-09-16 18:45'
updated_date: '2026-09-30 03:21'
labels:
  - rt
  - opus-5
  - from-review
  - performance
  - audit-2026-09-16
dependencies:
  - TASK-1
references:
  - src/pyteman/patcher.py
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Emerso dalla review Efficiency del finale RT-01 (2026-09-16). Declinato dentro RT-01 perche' e' una ottimizzazione di prestazioni, non una garanzia RT-01, e l'orchestratore aveva vincolato il tranche a "niente nuove feature, solo completare esattamente le garanzie RT-01".

**Il costo preesistente.** `Patcher._patch` e' chiamato dall'import hook a OGNI import del processo strumentato, e per ogni chiamata itera l'intero `_plan` per scartare le regole il cui `rule.module` non corrisponde. E' O(regole) per import, e il caso dominante e' quello in cui nessuna regola riguarda il modulo appena importato.

**La quota aggiunta da RT-01.** Misurata su un modulo che non corrisponde: da 0.33 a 0.57 microsecondi a 10 regole, da 1.98 a 3.10 microsecondi a 100 regole, circa +57%. La differenza sono due allocazioni di lista (`wrapped`, `applied`), due `extend` su liste vuote, e lo spacchettamento di 3-tuple invece dell'iterazione di una lista piatta. Il blocco `try` in se' e' gratuito su 3.11+. A 100 regole e un workload che fa 500 import, circa 0.56 ms, e scala come regole x import.

**La correzione proposta dalla review, che assorbe entrambi.** Raggruppare `_plan` per nome di modulo in un `dict[str, list]` dentro `__init__`, uscire subito quando il modulo non ha un bucket, e allocare `wrapped`/`applied` solo quando un bucket esiste. Misurato dalla review a 0.063 microsecondi costanti indipendentemente dal numero di regole: 8 volte piu' veloce a 10 regole, 49 volte a 100.

**Da verificare prima di eseguire.** Il raggruppamento cambia l'ordine di patch da "ordine del ruleset" a "ordine del ruleset dentro il bucket", che e' lo stesso ordine per ogni singolo modulo ma non piu' l'ordine globale. RT-01 non dipende dall'ordine globale, ma va confermato prima, non dopo. Vanno anche riconfermate le garanzie di atomicita' sotto re-entry descritte nel commento lungo di `_patch`, che dipendono dal fatto che le liste siano locali alla chiamata.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Il costo di _patch su un modulo senza regole corrispondenti non cresce con il numero di regole, misurato prima e dopo
- [x] #2 L'atomicita' e il rollback di RT-01 restano invariati, provati dalla batteria esistente di test_activation_atomic.py senza modifiche ai test
- [x] #3 L'ordine di patch delle regole all'interno di uno stesso modulo resta l'ordine del ruleset, con un test che lo fissa se oggi non esiste
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #132. Added lines already present on master per PR: #132 16/31=51%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.

Merged 2026-09-30 via #197 (b13b535). Evidence under /home/pantinor/pyteman-evidence/t191/: diff70.patch sha256 0a98eb67, tree70-hold5.sha256, VERDICT-70*.md in t191rev.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by PR #197, squash-merged as b13b535 on master at 2026-09-30 03:20Z. AC1: measured same-conditions, _patch of a module with no matching rules goes from linear 1.4/7.7/83.3 microseconds at 10/200/2000 rules to flat around 1-3, the flatness being the property and the absolute number moving with machine load. AC2: the existing test_activation_atomic battery passes unmodified, with new pins for the arms the index introduced: a bucketed rule whose module read turns hostile after construction refuses with the note naming it, a drifting module keeps the construction-time name with its never landing reported through pending (the one declared behaviour change), a lying-eq module decides for itself on the slow path (pinned against an isinstance widening by driving it onto a second module), and a slot mixing bucketed and unindexed rules stays in ruleset order (pinned through applied's visit order with distinct symbols, after the reviewer proved the first pin vacuous). The index is built in the plan loop by one guarded module read taken before _describe_rule, feeding both the buckets and _rule_modules derived from the bucket keys; only an exact str is a bucket key; the bucketed and unindexed ordinals merge ascending. Supersedes #132, closed with a pointer. Gates at eb64637: suite 1532 passed 2 skipped, check green, delivery 41, /simplify four angles applied, code-review high five findings applied or declared, independent verdicts APPROVED at 84d80d2 and reissued at eb64637. One CI flake (TASK-201's lock, third occurrence) rerun green.
<!-- SECTION:FINAL_SUMMARY:END -->
