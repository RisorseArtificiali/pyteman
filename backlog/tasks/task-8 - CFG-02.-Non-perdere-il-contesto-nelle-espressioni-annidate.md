---
id: TASK-8
title: CFG-02. Non perdere il contesto nelle espressioni annidate
status: Done
assignee: []
created_date: '2026-09-16 12:20'
updated_date: '2026-09-18 23:00'
labels:
  - audit-2026-09-16
  - opus-5
  - cfg
  - confirmed
milestone: m-1
dependencies:
  - TASK-7
references:
  - 'src/pyteman/conditions.py:2-7'
documentation:
  - doc-1
  - doc-2
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P2, CONFIRMED, aperto.

**File:** `src/pyteman/conditions.py:2-7`.

**Evidenza:** `args[0] < kwargs['limit']` funziona; `max(x < kwargs['limit'] for x in args)` e `(lambda: fires)()` sollevano NameError perché il contesto è solo locals, non globals delle espressioni annidate.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 generator expression, comprehension, lambda, once_per key annidata e chiamate concorrenti con contesti distinti; nessuna variabile passa da una valutazione all'altra.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Adottare un namespace fresco per ogni eval_expr: ns={**_SAFE, **ctx, '__builtins__': {}} e eval(code,ns,ns). La stessa mappa deve rendere coerenti scope piatti, comprehension, lambda e genexp su Python 3.11–3.14. Le assegnazioni di nomi non scrivono più nel ctx del chiamante; cambiamento intenzionale senza shim. Oggetti referenziati restano condivisi, non è isolamento deep né sandbox. Generator e closure restituiti possono trattenere ns oltre eval, quindi documentare snapshot shallow e lifetime senza promesse di consumo da bool. Aggiornare test storico del walrus e fake di log a LOG02. Verificare contaminazione process-global contro HEAD e split namespace contro variante A, suite e review finale prima della pubblicazione separata.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: CFG-01 per diagnostica di compilazione.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.

## Sotto-requisito arrivato da CFG-01 (TASK-7), 2026-09-16, RISCRITTO lo stesso giorno

Non e' lavoro svolto su questo task. E' un vincolo che CFG-02 deve rispettare quando verra' fatto, registrato qui perche' altrimenti si perde.

**Attenzione: la prima versione di questa nota e' superata e diceva il contrario.** Chiedeva di estendere `_free_names` in `rules.py` a unione ricorsiva su `get_children()`. Quella funzione, insieme a `_reject_exit_only`, e' stata RIMOSSA da CFG-01 nello stesso giorno, su direttiva dell'orchestrator, dopo che una verifica indipendente ne ha mostrato due falsi negativi: `symtable` non vede il nome libero dentro uno scope annidato e considera assegnato il target di un walrus letto prima dell'assegnazione. Non c'e' piu' niente da estendere.

**Lo stato attuale.** Il loader compila le espressioni ma non risolve i nomi che leggono. Una regola `event: entry` il cui `when` nomina `result` o `exc` si carica senza obiezioni e alza `NameError` dentro la chiamata strumentata quando spara. Il contratto e' documentato in `docs/rules.md`, sezione "Where each check happens", non imposto.

**Perche' riguarda comunque questo task.** Oggi il difetto che CFG-02 deve riparare maschera una parte del problema: finche' gli scope annidati non vedono il contesto di valutazione, `any(x == result for x in args)` e `(lambda: result)()` falliscono comunque, sia in entry sia in exit. Quando CFG-02 fa arrivare il contesto dentro comprehension e lambda, la forma exit inizia a funzionare e la forma entry resta un NameError, ma diventa un NameError che nessuno intercetta prima del workload. L'insieme delle espressioni che si caricano e poi esplodono cambia: e' un cambiamento di superficie che va misurato qui, non scoperto dopo.

**Cosa fare quando si affronta questo task.** Dopo aver riparato il contesto, ri-misurare quali espressioni entry che nominano `result` o `exc` si caricano e falliscono al firing, e aggiornare di conseguenza `docs/rules.md`. Se a quel punto si vuole un controllo al load, e' TASK-47 (CFG-07) e va fatto COMPLETO: la condizione posta dall'orchestrator e' che una seconda versione parziale ricrea esattamente il difetto appena tolto, cioe' rifiuta le forme piatte e lascia passare quelle annidate, creando falsa sicurezza mentre rompe condizioni funzionanti.

Origine: seconda minor finding della code review indipendente ad alto sforzo sullo stato finale di CFG-01, poi superata dalla verifica indipendente dell'orchestrator che ha portato alla rimozione del controllo.

2026-09-18. Candidate implemented and self-verified in an isolated archive export of d8bcfd70f7f5ff9ecb330469c9c3f81737e8daa1 (src/pyteman/conditions.py, tests/test_conditions.py, docs/rules.md only): eval_expr builds ns={**_SAFE, **ctx, '__builtins__': {}} fresh per call and evaluates with eval(code, ns, ctx), so nested lambdas/genexps/comprehensions resolve args/kwargs/fires/result/exc via ns while ctx stays the real locals object, preserving the pre-existing top-level-walrus-writes-through-to-ctx contract pinned by test_activation_atomic.py's clobber/reader test. Full local suite (4 Python interpreters, code-simplifier + high-effort code-review gates) passed against this design; not yet applied to the shared checkout, not yet approved by peer review.

2026-09-18. Peer review (session pyteman-17) disputes the design and proposed eval(code, ns, ns) with ns as a copy of ctx for both globals and locals. I ran that variant against the full local test files: it breaks the pre-existing test_one_exits_condition_cannot_hide_the_body_error_from_the_next (assert saw['clobber'] is None fails, since clobber's own top-level walrus no longer touches the real ctx) and my own test_top_level_walrus_still_writes_through_to_ctx. Checked TASK-115 directly (status To Do, unimplemented): it documents args/kwargs/_signature corruption across DIFFERENT rules on the same call as a known, separate, tracked limitation, explicitly scoped OUT of this task ('il lavoro e' separato'), and notes the exc case is already closed via a different mechanism (patcher.py re-seeding ctx['exc'] in the exit loop), not via an eval_expr copy. TASK-115's own AC2 says the eventual fix belongs at the point ctx is passed to eval, which is exactly TASK-115's job, not TASK-8's. Restored the candidate to the originally verified design immediately after the experiment (conditions.py sha256 34c0440747341c52079be4f79b210f8b7c0b5e76e4d4b6988f0b600a7847737c unchanged). Disposition: disagreement not resolved between peer and me; candidate stands as reported; not implementing the ns-copy redesign under this task without the user's direct sign-off, since it would take on TASK-115's scope and reverse a currently-passing, pre-existing test.

Assessment candidato B approvato tecnicamente dal coordinatore, non ancora per pubblicazione. Patch iniziale ebf89cbe5944fc87ad3857d8463dda52bc5e0f8f8c279f259b9eb588c47d0477 applicabile a 8dc374b (git apply --check eseguito). Probe indipendente conferma _EVAL_GLOBALS contaminato da genexp walrus e nome risolto nella valutazione successiva; variante A genera NameError su nome appena associato poi letto in lambda, variante B restituisce il valore atteso. Refutata la frase del report secondo cui truthiness consumerebbe un generator: bool(g) lascia ancora tutti gli elementi da iterare. Richiesta correzione dei claim di lifetime e test diretto su generator restituito. Agente pyteman-backlog-audit incaricato di gate e prove in copia isolata, nessuna scrittura shared autorizzata. Misure del peer sulle suite restano attribuite al report, non replicate qui finora.

Pacchetto TASK8+115 ricevuto: ~/pyteman-evidence/task8-115-1789765934/cfg02-task8-115.patch, sha256 c56dec309d090aeb845c068cbd1d5c7904bb1fbc1302b263e3f70c426b757b4a verificato e git apply --check su 8dc374b riuscito. Non ancora integrato: CHANGES REQUESTED su claim documentale di lifetime. Probe indipendente con Patcher reale nel venv candidato e condizione kwargs['saved'].append(lambda: args[0]) is None: dopo m.f(42,saved=list), saved[0]() restituisce42. Quindi 'No ruleset can arrange retention' è falso anche se when scarta il valore restituito e once_per rifiuta chiavi generator/function. Nessun difetto runtime: correggere solo promesse di lifetime, mantenendo shallow/no-sandbox. Richieste reference effettive gate e nuova approvazione finale, senza refactor o allargamenti. Risultati matrice 947 passati e mutazioni restano report del peer finché riletti/verificati.

Disposizione finale simplify sul candidato faa480ff: nessuna proposta opzionale applicata. Test walrus duplicato rispetto al clobber test in test_activation_atomic mantenuto: ridondanza limitata accettata, non bug. Test dictcomp mantenuto come sintassi distinta, sebbene condivida il confine PEP709 col listcomp. Frase sul lifetime/closure mantenuta perché delimita correttamente il contratto. Tightening e rinomina test respinti come non necessari alla pubblicazione. Niente nuovi task cosmetici né altro ciclo matrice per queste proposte. Attesa solo correctness verdict sugli hash congelati; eventuali bug reali seguiranno verifica e delta review. Peer dichiara matrice finale 948 passed/1 skipped su tutte 3.11–3.14 e mutanti split-ns/shared-ns rispettivamente 5/4 test falliti; evidenze da controllare al handoff finale.

Correctness review sul candidato: CHANGES REQUESTED per prosa con isolamento assoluto falso e due test di nested walrus che sopravvivono ai mutanti. Decisione coordinatore: eliminare solo test_nested_walrus_does_not_leak_into_ctx_or_a_later_rule e test_nested_walrus_in_a_bare_genexp_does_not_leak_into_ctx; il detector della contaminazione globals resta. Nessuna riscrittura test o pulizia aggiuntiva. Correzione prosa già applicata dal peer come comment-only: namespace fresco non significa inaccessibile ad altre valutazioni/thread se una closure è condivisa tramite oggetti del workload. Richiesti full suite finale 3.14, mutanti mirati e delta review dallo stesso reviewer fino ad APPROVED sugli hash finali. Matrice precedente 948 non sarà ricopiata come misura della versione con due test rimossi.

Tre note sotto il cap registrate e non bloccanti: precedenza ctx su _SAFE non testata per collisioni oggi non prodotte dal patcher; list/dict comprehension distinguono il fix su3.11, già coperto da CI; allocazione dict per eval è costo necessario alla separazione dei namespace, non ottimizzazione da fare qui. Nessun task nuovo.

Delta reviewer APPROVED su patch444342cd, ricevuto e letto dal terminale herdr. Integrati esattamente cinque file confrontati byte-exact con fresh export già testato; suite shared appena eseguita: 946 passed, 1 skipped opzionale. Commit10489052425ee4e12a328f6fc7335e35be1ccce9 pubblicato con PR6 https://github.com/RisorseArtificiali/pyteman/pull/6. CI35403781421 in corso, nessuna review/commento pendente al controllo iniziale. Stato non Done finché CI/merge conclusi.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Pubblicato insieme a TASK115 nella PR6 https://github.com/RisorseArtificiali/pyteman/pull/6. Commit10489052425ee4e12a328f6fc7335e35be1ccce9, merge f1ce0d2df747ee7762df793e244e1d77d21c8f0e. eval_expr usa namespace fresco unico per globals/locals, risolve contesto negli scope annidati e impedisce rebinding involontario del ctx e contaminazione della mappa globals fra valutazioni.

Review high con delta APPROVED sul patch444342cd; simplify completato, opzionali respinti e due test non discriminanti eliminati. Suite indipendente da patch e suite shared: 946 passed, 1 skipped opzionale. CI35403781421 success in tutti i sei job, incluse Python3.11–3.14, artifact e coverage; PR MERGED e nessuna review/commento pendente al controllo finale.

Limiti espliciti: copia shallow, oggetti del workload mutabili e closure conservabili; non sandbox né isolamento contro condivisione esplicita. Cambiamento intenzionale del walrus senza compatibility shim.
<!-- SECTION:FINAL_SUMMARY:END -->
