---
id: TASK-156
title: >-
  Nessun test copre il ramo di creazione di barriers.open(): open-prima-di-wait
  sopravvive a tutta la suite
status: Done
assignee: []
created_date: '2026-09-17 11:19'
updated_date: '2026-11-08 20:21'
labels:
  - test-coverage
  - barriers
  - audit-2026-09-16
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Reperto del gate di correttezza su TASK-34.2, fuori dal mandato di quel task e quindi filato qui invece di essere corretto sul posto. TASK-34.2 copre determinismo e timeout dei test che lanciano figli; questo non e' ne' un timeout ne' un'attesa non limitata, e' una lacuna di copertura.

Meccanismo. tests/test_barriers.py:61 pre-semina lo stato con `barriers._state["b1"] = watched` prima che wait() o open() vengano mai chiamate. Di conseguenza entrambe le funzioni esercitano solo la meta' di RECUPERO del loro setdefault. La meta' di CREAZIONE di open(), cioe' il caso in cui open() e' la prima a nominare quella barriera, non viene eseguita da nessun test del repository.

Mutazione che resta verde, misurata dal revisore su copia con guardia di import provata:

    def open(name):
        with _lock:
            if name in _state:
                _state[name].set()

Sonda diretta contro il modulo mutato: `barriers.open('x')` seguito da `barriers.wait('x', timeout_s=0.2)` ritorna False invece di True, perche' wait() crea allora un Event nuovo e non settato. E' una rottura di comportamento vera, non teorica.

Portata della cecita', misurata sull'intero albero tests/: 749 passed, 6 failed con la mutazione, e 749 passed, 6 failed identici con barriers.py integro. I sei sono artefatti della copia di scratch priva di LICENSE ed examples/, non rilevazioni. Nessun test dell'intero repository intercetta la mutazione.

Perche' conta in produzione e non solo in teoria: l'ordinamento open-prima-di-wait e' raggiungibile, perche' actions.py:53-56 lo rende possibile ogni volta che una regola di ruolo open scatta su un hook prima che una regola di ruolo wait scatti su un altro.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Esiste un test che chiama open() su una barriera mai nominata prima, senza pre-seminare _state, e poi verifica che una wait() successiva ritorni True entro un budget finito
- [ ] #2 Il nuovo test e' provato rosso contro la mutazione che rende open() un no-op quando la chiave e' assente, e verde contro il runtime integro, con guardia di import che dimostra quale file e' stato caricato
- [ ] #3 Il test non modifica src/pyteman/barriers.py e non richiede strumentazione: nessuna sottoclasse di Event e nessun accesso agli internals della condition variable
- [ ] #4 L'attesa del nuovo test e' limitata: nessuna wait, join o get senza scadenza su alcun percorso, compreso quello di fallimento
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
PRECISAZIONE SULLA FORZA DELLA PROVA, scritta prima che qualcuno la usi come gate chiuso. La misura dei 749 passed / 6 failed non e' stata presa su una baseline pulita: i sei fallimenti sono presenti IDENTICI nei due bracci, con barriers.py mutato e con barriers.py integro, e sono artefatti della copia di scratch, che non ha LICENSE ne' examples/. Cio' che quella misura dimostra e' quindi un DIFFERENZIALE nullo, cioe' che nessun test cambia esito passando dal runtime integro a quello mutato, ed e' esattamente l'affermazione che serve per sostenere la lacuna di copertura. Cio' che NON dimostra e' che l'albero sia verde, e nessuno deve citarla come tale. Conseguenza operativa: questo task resta APERTO come copertura separata, e la sua mutazione non va presentata come un gate superato ne' come prova che il perimetro di TASK-34.2 fosse incompleto. La prova puntuale che regge davvero e' la sonda diretta descritta sopra, open('x') seguita da wait('x', timeout_s=0.2) che ritorna False contro il modulo mutato, perche' quella non dipende da alcuna baseline. AC2 chiede in modo esplicito rosso e verde con guardia di import proprio per rimediare a questo: chi lavora il task rifa' la misura su un albero pulito e non riusa questi numeri.

Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #53. Added lines already present on master per PR: #53 0/16=0%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closure restored 2026-11-08 (tracker repair): the day-3 Done marker was lost to a working-tree revert; the verdict had been recorded. Closed with NO push: the gap was already on master (the barrier's open-before-wait creation branch had landed via intervening merges; the full disposition is in the durable handoff, set fifty-first).
<!-- SECTION:FINAL_SUMMARY:END -->
