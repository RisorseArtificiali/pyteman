---
id: TASK-100
title: >-
  Il wrapper trattiene l'intero Patcher per leggere solo self.log, piu' due
  ridondanze strutturali dallo stesso giro di review
status: Done
assignee: []
created_date: '2026-09-17 00:23'
updated_date: '2026-09-29 10:22'
labels:
  - review-rt-01
  - opus-5
  - follow-up
  - confirmed
dependencies: []
references:
  - 'src/pyteman/patcher.py:529-560'
  - 'src/pyteman/patcher.py:371'
  - tests/test_activation_atomic.py
  - tests/test_sitecustomize.py
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Rilievi strutturali e di efficienza dal gate /simplify di TASK-1 (RT-01), rieseguito in sola lettura il 2026-09-17 sullo stato finale approvato. Raccolti a codice congelato: nulla e' stato applicato. Nessuno e' un difetto di correttezza, per questo sono un follow-up e non una correzione dentro RT-01.

Aperto come task UNICO, non come tre, su disposizione dell'orchestrator: i rilievi di prosa dello stesso giro sono stati depositati su TASK-46 e la precisazione su `applied` su TASK-62. Esplicitamente FUORI dal perimetro di TASK-5 (RT-05), che tocca le stesse funzioni ma ha ordine di non fare cleanup ne' ottimizzazioni di closure.

**1. Il wrapper trattiene l'intero Patcher, e la ragione e' una sola lettura.**

`src/pyteman/patcher.py:529-560`. La closure `wrapped` cattura `self` e lo usa soltanto per leggere `self.log`, alle righe 539 e 555. Verificato direttamente: `self` compare in `wrapped.__code__.co_freevars` e la cella corrispondente e' l'istanza del Patcher. Ogni callable wrappato tiene quindi in vita il Patcher, e con lui `self._plan`, che dopo RT-01 porta per ogni regola un oggetto Rule, due code object compilati e la stringa di identita' pre-renderizzata.

Il wrap in se' e' preesistente e identico a HEAD; cio' che e' cambiato con RT-01 e' il PESO di cio' che resta appeso. Il caso in cui morde e' proprio quello che RT-01 ha reso ritentabile: uno strand che ha rifiutato il restore resta installato, e il suo wrapper trattiene il piano di un Patcher per il resto disinstallato, per tutta la vita del processo.

Correzione candidata, una riga: `log = self.log` prima del `def`, cosi' la closure cattura il logger invece dell'istanza. Da verificare che non cambi la semantica se qualcuno riassegna `self.log` dopo il patch, che oggi sarebbe visibile al wrapper e dopo la modifica no.

**2. `self.rules` e' derivabile da `self._plan`.**

Dopo l'assegnamento in `__init__`, l'unico lettore di produzione di `self.rules` e' la riga 371, piu' un test. `self._plan` porta gia' la regola in ogni tupla. Due campi che descrivono lo stesso insieme sono due campi che possono divergere.

**3. Le fixture ostili sono duplicate fra i due file di test che esistono per confrontarsi.**

`BoomStr` / `Boom`, due varianti di metaclasse e `Hostile` / `Unrenderable` sono definite sia in `tests/test_activation_atomic.py` sia in `tests/test_sitecustomize.py`. La duplicazione conta piu' del solito qui: quei due file esistono per guidare le DUE copie deliberate di `_typename` e `_text` (una in `patcher.py`, una in `sitecustomize.py`, separate perche' sitecustomize non puo' importare nulla da pyteman mentre e' inerte) con input identici. Fixture duplicate sono esattamente il meccanismo con cui quegli input smettono di essere identici, cioe' con cui le due copie divergono senza che la suite se ne accorga.

Da valutare insieme al vincolo che ha creato le due copie: una fixture condivisa non deve reintrodurre l'import che sitecustomize non puo' avere. Un modulo di test comune va bene, un import di pyteman dentro sitecustomize no.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Il wrapper di _make_wrapper non trattiene piu' il Patcher: verificato che `self` non compaia in `wrapped.__code__.co_freevars` e che il comportamento di logging sia invariato.
- [x] #2 self.rules e self._plan non descrivono piu' la stessa cosa due volte: o il campo ridondante sparisce, o e' documentato perche' entrambi esistono e chi legge quale.
- [x] #3 Le fixture ostili condivise fra tests/test_activation_atomic.py e tests/test_sitecustomize.py hanno una sola definizione, oppure la duplicazione e' dichiarata deliberata e motivata nel punto in cui si trova.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #74 #86 #121. Added lines already present on master per PR: #74 0/20=0%  #86 5/35=14%  #121 0/22=0%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason. AC1 is on master: the dispatcher captures log = self.log (patcher.py, from 76114e2 via #141), so it stays checked. AC2 and AC3 are not: self.rules and self._plan still coexist, and the hostile fixtures are still defined separately in tests/test_activation_atomic.py and tests/test_sitecustomize.py.

Merged 2026-09-29 via #186 (600a199). Evidence under /home/pantinor/pyteman-evidence/t191/: diff100b.patch sha256 109993b8, tree100-hold5.sha256, mutants-100b/c/d.log, VERDICT-100b/100c.md, BRIEF4-impl.md sibling for the TASK-4 unit.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by PR #186, squash-merged as 600a199 on master at 2026-09-29 10:20Z. AC2: Patcher.rules is a read-only property derived from self._plan (assigned once, never structurally mutated, verified by the independent reviewer); the ruleset is materialised once in __init__ and both loops walk the local. AC3: the hostile rendering fixtures live once in tests/hostile_fixtures.py, with a PARITY_INPUTS tuple of seven labelled inputs and a parametrized parity test asserting the patcher and sitecustomize copies of _typename/_text agree and return exact str on every entry; the Unrenderable copy inside FAKE_RULES stays commented as deliberate. AC1 was on master since #141; its unpinned invariant gained tests folded from superseded PR #86 and strengthened on review (closure-cell pin on sync and async dispatchers, FiringLog end-to-end on entry and exit roads, exactly-two-records assertions). Supersedes #74, #86 and #121, all closed with pointers. Gates: suite 1447 passed 2 skipped, dev.py check green, delivery 41 passed, mutation battery 13 mutants all killed with byte-exact restores (mutants-100d.log), /simplify four angles applied, code-review high on the branch plus a scoped pass on the final increment, independent verdicts APPROVED at 1a31861 and 5499db7 (VERDICT-100b.md, VERDICT-100c.md). Review leftovers filed: TASK-197 (named plan entries, third fixture copies in test_log_actions), TASK-198 (three informational test tightenings).
<!-- SECTION:FINAL_SUMMARY:END -->
