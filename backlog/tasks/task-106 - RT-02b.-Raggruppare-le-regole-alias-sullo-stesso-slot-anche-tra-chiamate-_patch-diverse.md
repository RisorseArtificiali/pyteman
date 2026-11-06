---
id: TASK-106
title: >-
  RT-02b. Raggruppare le regole alias sullo stesso slot anche tra chiamate
  _patch diverse
status: Done
assignee: []
created_date: '2026-09-17 02:32'
updated_date: '2026-09-27 00:10'
labels:
  - rules
  - patcher
  - composition
  - silent-failure
dependencies:
  - TASK-2
references:
  - src/pyteman/patcher.py
  - tests/test_activation_atomic.py
  - docs/rules.md
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
RT-02 raggruppa correttamente due regole che risolvono sullo stesso attributo DENTRO una singola chiamata `_patch` (pass 1 costruisce `index`/`slots`, pass 2 installa un dispatcher per slot). Quello stesso raggruppamento non sopravvive alla chiamata: `index` e `slots` sono locali, quindi una regola che raggiunge uno slot gia' posseduto da un nostro dispatcher installato da una chiamata PRECEDENTE cade nel ramo `owner is self: continue` e viene scartata in silenzio.

Riprodotto (code review high effort, 2026-09-17), due rotte:

1. Cross-module, un solo oggetto classe legato a due moduli (`xmodA.Shared is xmodB.Shared`, la forma ordinaria `from x import C`). Regole `ruleA` su `xmodA.Shared.m` e `ruleB` su `xmodB.Shared.m`, poi `force_patch_module("xmodA")` e `force_patch_module("xmodB")`. Risultato: `applied == ['xmodA:Shared.m']`, ledger 1, fired `['ruleA']`. `ruleB` perduta senza messaggio, senza voce in `applied`, senza rifiuto.
2. Rientranza: costruire il dispatcher di uno slot importa `inspect` mentre l'hook e' vivo, la chiamata rientrante installa su uno slot che il pass 2 esterno non ha ancora raggiunto, e la regola esterna su quello slot viene scartata allo stesso modo.

`os.path is posixpath` e' vero su questo interprete, quindi un ruleset che tocca `os.path.join` e `posixpath.join` incontra il caso 1 senza alcun artificio.

Il contratto TASK-2 chiede esplicitamente che le risoluzioni alias sullo stesso slot raggruppino TUTTE le regole e non perdano la seconda, e `docs/rules.md` (sezione "More than one rule on one point") afferma che due regole che raggiungono lo stesso attributo per percorsi diversi si applicano entrambe. Il comportamento attuale contraddice entrambi.

Non e' una regressione della tranche RT-02: il ramo `continue` sostituisce il vecchio skip basato sul marker e conserva lo stesso esito su questa rotta. E' pero' esattamente il modo di fallire che RT-02 esiste per eliminare, un livello piu' in basso.

Il motivo per cui e' un task separato e non una correzione dentro TASK-2: risolverlo richiede che l'identita' dello slot sopravviva alla singola chiamata `_patch`. Il dispatcher deve poter dire quali regole serve gia', ed essere ESTESO in ordine di ruleset con le regole non ancora servite, oppure rifiutare con diagnostica. Questo tocca il corpo del dispatcher (le liste `entries`/`exits` e la `sig` sono locali di chiusura), l'ordinamento globale delle regole e il rollback della sola chiamata corrente. E' progettazione nuova sul percorso caldo, non la riparazione di un difetto.

Vincolo di compatibilita' da preservare: lo stesso ruleset ripatchato piu' volte dallo stesso Patcher non deve aggiungere regole, wrapper o firings. La distinzione esatta e' per id di regola gia' servita, non per contenuto.

Stato del codice al momento del deposito: il difetto vicino (pass 2 che scrive SOPRA un dispatcher installato da una chiamata rientrante, leggendo `slot.original` invece dell'attributo vivo) e' gia' corretto dentro TASK-2 e coperto da `test_pass_two_asks_about_the_value_that_is_there_not_the_one_it_remembered`. Quel che resta qui e' solo lo scarto silenzioso.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Due regole in un solo ruleset che risolvono sullo stesso attributo partendo da rule.module diversi si applicano entrambe, in ordine di ruleset, anche quando i due moduli sono patchati da chiamate _patch distinte
- [x] #2 Una regola che raggiunge uno slot gia' posseduto da un nostro dispatcher non viene mai scartata in silenzio: o estende quel dispatcher, o produce un rifiuto esplicito con diagnostica
- [x] #3 Ripatchare lo stesso ruleset piu' volte con lo stesso Patcher continua a non aggiungere regole, wrapper ne' firings; la distinzione e' per id di regola gia' servita, non per contenuto
- [x] #4 Le regole aggiunte per estensione rispettano l'ordine di ruleset globale, non l'ordine di arrivo delle chiamate _patch
- [x] #5 Una regola aggiunta per estensione che porta un target param: ottiene la signature anche se nessuna regola gia' legata a quello slot la richiedeva
- [x] #6 Il fallimento di una chiamata che ha esteso un dispatcher esistente annulla solo le proprie aggiunte e lascia il dispatcher come lo ha trovato
- [x] #7 Test di regressione per entrambe le rotte riprodotte: cross-module su oggetto condiviso, e rientranza via lettura della signature
- [x] #8 docs/rules.md e README descrivono il comportamento effettivo su questo punto
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed as already satisfied, with per-AC verification run on 2026-09-27 against master content 97c71ce rather than by a dedicated change. The extend mechanism this task asked to be designed was built as the dispatcher manifest (_pyteman_composite with served-by-rule-id, _extend_dispatcher, unextend rollback) during the TASK-2 follow-up era and hardened by TASK-176/177 and pinned by TASK-179. Evidence per AC: (1) reproduced with two modules sharing one class object, two force_patch_module calls: applied names both spellings, one dispatcher, ruleset-order override (probe task106rev); (2) the owner-is-self branch extends or raises, never silently drops, and a failure now also leaves the rule pending for the exit report (TASK-177); (3) idempotence by rule id pinned by test_dotted_first_no_double_patch and the served manifest; (4) ordinal ordering pinned by test_a_later_patch_call_reaching_a_slot_we_already_own_extends_it asserting [late, early]; (5) reproduced with a pragma param rule arriving through the second module: the extension computes the binding signature (probe: sig present, param-rule fires with pragma_applied); (6) pinned by test_a_failed_call_that_extended_a_dispatcher_takes_back_only_its_own_rules and test_extend_rollback_restores_the_plan_identity; (7) cross-module route reproduced tonight, re-entry route covered by the re-entry extend branch tests; (8) docs' 'More than one rule on one point' claim now matches behavior. Probe note for whoever reads the evidence: two module attributes importing the same function are TWO slots by design and correctly get two dispatchers; the AC probes must use one shared attribute reached via two modules.
<!-- SECTION:FINAL_SUMMARY:END -->
