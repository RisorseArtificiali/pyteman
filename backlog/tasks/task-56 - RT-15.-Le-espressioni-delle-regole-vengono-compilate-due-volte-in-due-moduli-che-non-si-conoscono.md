---
id: TASK-56
title: >-
  RT-15. Le espressioni delle regole vengono compilate due volte, in due moduli
  che non si conoscono
status: Done
assignee: []
created_date: '2026-09-16 17:32'
updated_date: '2026-09-27 12:11'
labels:
  - rt
  - opus-5
  - from-review
  - audit-2026-09-16
dependencies:
  - TASK-1
references:
  - src/pyteman/patcher.py
  - src/pyteman/rules.py
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Emerso durante la review /simplify di TASK-1 (RT-01), 2026-09-16. Tre agenti di review indipendenti (Reuse, Efficiency, Altitude) hanno segnalato la stessa duplicazione e hanno tutti e tre declinato di correggerla, per la stessa ragione strutturale: la correzione non puo' stare dal lato che la renderebbe naturale.

**Cosa e' duplicato.** `rules.py` compila `when` e `fire.key` al load, dentro `_expression`, per validarle. `patcher.py` le ricompila in `Patcher.__init__`, dentro `_compile`, perche' ha bisogno degli oggetti code veri e perche' deve coprire anche le regole costruite a mano attraverso la API programmatica, che non sono mai passate da `load_rules`. Sul percorso YAML ogni espressione viene quindi compilata due volte.

**Perche' non e' stata corretta in RT-01.** `_expression` e' privata, restituisce una stringa e non un oggetto code, rifiuta `None`, e vive in `rules.py`, che era congelato e APPROVED come TASK-7. Nessuna delle tre forme del riuso funziona senza toccarlo.

**Perche' il costo non e' l'argomento principale.** Misurato durante la stessa review: circa 61 microsecondi per regola, contro `load_rules` a 2.5-18.4 ms e `import yaml` a circa 80 ms. Il costo e' trascurabile. Il problema e' che due moduli hanno ciascuno la propria idea di cosa significa compilare l'espressione di una regola, con due formati di messaggio d'errore diversi per lo stesso guasto, e niente che li tenga allineati quando uno dei due cambia.

**Perimetro.** Questo task esiste perche' la raccomandazione di review non resti senza proprietario, non perche' la duplicazione sia urgente. Chi lo esegue decida prima se il riuso e' davvero desiderabile: rendere `_expression` pubblica e farle restituire un oggetto code cambia il contratto di un modulo che oggi ha una responsabilita' sola.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Una sola definizione di cosa significa compilare l'espressione di una regola, o una motivazione scritta del perche' due sono corrette e come restano allineate.
- [x] #2 Il messaggio d'errore per un'espressione non valida nomina la regola e il campo con lo stesso formato su entrambi i percorsi, YAML e API programmatica.
- [x] #3 Le regole costruite a mano continuano a fallire prima di qualunque mutazione, come garantito da RT-01.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Seconda misurazione, review Efficiency del finale RT-01 (2026-09-16, dopo le correzioni della altitude review). Metodo diverso dalla prima e risultato coerente in ordine di grandezza, ma piu' specifico su dove cade il costo: 14.6 microsecondi per singola `compile()`, che diventano 134 microsecondi di `Patcher.__init__` a 10 regole e 1456 microsecondi a 100 regole, contro 0.5-0.6 microsecondi prima che RT-01 spostasse la compilazione in `__init__`. Il punto che la prima misura non diceva: questo costo sta interamente sul percorso di attivazione, quindi si paga allo startup di ogni processo strumentato, non una volta sola in fase di load. Resta trascurabile in assoluto e non cambia la priorita' Low; cambia solo dove guardare se qualcuno un giorno misura lo startup. La forma del riuso suggerita dalla review e' la stessa gia' descritta sopra: `_expression` restituisce l'oggetto code invece di buttarlo, `Rule` lo trasporta (e' una dataclass mutabile), `_compile` compila solo quando manca, che e' esattamente il caso delle regole costruite a mano. `fire.key` resta lavoro genuinamente nuovo, perche' `load_rules` non l'ha mai compilato.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Merged as 1149aa0 via PR #163 (head b82433a). AC #1 satisfied by one definition: the compile core is rules._compile_expression(code, filename), raising SyntaxError with only its message; the loader dresses the failure with its file location, the patcher names the rule and field, so AC #2's same-format claim holds on the shared core text (the prefixes differ by design, each naming its own context; the door-agreement test drives the same malformed expression through both doors and asserts the core text agrees, for an unclosed bracket and a keyword). AC #3 confirmed: programmatic rules still fail in Patcher.__init__ before any mutation, the RT-01 guarantee pinned by the existing suite. Gates: battery check clean, 1271 passed 2 skipped (the PR battery said 1273 with the two new door-agreement tests); independent review APPROVED at b82433a; PR CI green; master CI green. TASK-140's precedent covers the rules.py edit (the TASK-7 freeze lapsed with its review cycle).
<!-- SECTION:FINAL_SUMMARY:END -->
