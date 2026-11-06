---
id: TASK-164
title: >-
  Suspendable gate: a nested staticmethod/classmethod in __call__ is a silent
  false negative
status: Done
assignee: []
created_date: '2026-09-17 13:38'
updated_date: '2026-09-25 10:57'
labels:
  - rt
  - opus-5
  - confirmed
  - audit-2026-09-16
dependencies: []
references:
  - src/pyteman/patcher.py
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Found by my own adversarial probe while fixing TASK-3, measured on all four supported interpreters. NOT caused by the TASK-3 change: the single-level unwrap predates it. Filed rather than fixed because the RT03 freeze was released only for the two accepted TASK-3 defects, and this is outside that scope. It needs an explicit decision from pyteman-89.

`_call_slot` unwraps a `staticmethod` or a `classmethod` found in `__call__` exactly ONE level, through `__func__`. If what comes out is itself a descriptor of the same kind, it is neither a function nor a partial, so `_call_slot` answers None, the walk treats the object as opaque, and a suspendable target is instrumented in silence. Silent instrumentation is the exact failure the gate exists to prevent, so this is the dangerous direction rather than the annoying one.

Measured with `async def coro(a)` and `class C: __call__ = staticmethod(staticmethod(coro))`:

| interpreter | `C()(5)` returns | gate verdict |
| --- | --- | --- |
| 3.11.14 | coroutine | None |
| 3.12.12 | coroutine | None |
| 3.13.15 | coroutine | None |
| 3.14.7 | coroutine | None |

`classmethod(staticmethod(coro))` is the same hole where the object is callable at all: coroutine and None on 3.11.14 and 3.12.12, TypeError on 3.13.15 and 3.14.7, where the shape stops being constructible into a working call.

The docstring's stated gap is a `__call__` that is "none of the recognised forms". This one IS a recognised form at the outer level, so a reader of that promise would expect it caught. Either the code catches it or the promise has to name the nesting, and leaving it as-is means the written guarantee is wider than the implementation.

Cheapest fix is turning the single `if` into a bounded loop over the same two forms, which is not a descriptor framework and adds no new recognised spelling. It must be BOUNDED rather than a bare `while`: a `staticmethod` subclass can define `__func__` as a property returning itself, and an unbounded unwrap would hang the interpreter during startup, which is precisely what `_WRAPPER_CHAIN_LIMIT` exists to prevent. Reusing that constant keeps one bound for one walk.

The alternative, if the nesting is judged not worth code, is to narrow the prose in both `_call_slot` and the "What is recognised" section of docs/rules.md so the promise stops covering it. That is cheaper but leaves a real silent-instrumentation hole open.

Tests would go next to `classmethod_call` and `static_call` in tests/test_activation_atomic.py, and must assert against what calling the object actually returns rather than a fixed verdict, since the callability differs by version.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Un staticmethod o classmethod annidato nello slot __call__ produce lo stesso verdetto del caso a un livello, misurato su 3.11, 3.12, 3.13 e 3.14 con le versioni reali registrate
- [x] #2 L'unwrap resta limitato: nessun percorso puo' ciclare all'infinito, incluso un sottotipo di staticmethod il cui __func__ e' una property che restituisce se stessa
- [x] #3 Il testo di _call_slot e la sezione 'What is recognised' di docs/rules.md descrivono esattamente cio' che il codice riconosce, senza promettere piu' di quanto implementato
- [x] #4 Test negativi e positivi accanto a static_call e classmethod_call, con l'attesa derivata da cosa restituisce davvero la chiamata
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Correggere nella copia isolata da5ba4c37 il falso negativo di descriptor annidati nello slot __call__. Riutilizzare il walker _suspendable_reason già presente con budget _WRAPPER_CHAIN_LIMIT e priorità override, non aggiungere unwrap illimitato né saltare __call__ effettivi delle sottoclassi. Prima opzione da verificare: _call_slot restituisce anche descriptor residuo dopo un singolo hop, che il walker può seguire. Mantenere lettura __func__ tramite descriptor base senza eseguire property del workload. Test coroutine/generator/async-generator, nested sync positivo, override sync/async e shape callable secondo interprete reale; bounded/cyclic/hostile property. Scope patcher.py, tests/test_activation_atomic.py, docs/rules.md. Mutanti, matrice3.11–3.14, simplify e review high fino ad APPROVED, poi pubblicazione separata.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Difetto confermato indipendentemente dal coordinatore su HEAD5ba4c37: async coro; C.__call__=staticmethod(staticmethod(coro)); originale C()(5) è coroutine (chiusa nella sonda), _call_slot restituisce None, _suspendable_reason=(None,None), dopo Patcher con entry return_value1 la chiamata restituisce1. Scout conferma due sonde in copia ~/pyteman-evidence/scout-1789775000. Incarico implementazione a herdr pyteman-backlog-audit Opus5/zai, no shared/tracker/Git/forge writes. Non accettato automaticamente loop interno: il walker descriptor override-first già esiste e va preservato, verificare fix al punto di handoff. TASK131 resta candidato distinto non riprodotto dal nuovo scout; non viene promosso a certezza né avviato insieme.

Checkpoint letto direttamente dal terminale herdr: reviewer high ha approvato lo stato pre-cleanup; l'agente sta applicando consolidamento del test property __func__ annidata e helper per derivare aspettative dalla chiamata reale. Quell'APPROVED non copre gli edit successivi: richiesta delta review allo stesso reviewer sul pacchetto finale, con suite e mutanti aggiornati. Simplify: riuso dei terminali tramite spostamento di definizioni declinato perché fuori beneficio funzionale; consolidamento che elimina stato globale nei test accettato; prose solo coerenza del paragrafo. Due gap di copertura e una forma fuori scope citati dal reviewer non ancora descritti nel handoff: richiesti dettagli/prove. La forma fuori scope non va implementata né convertita autonomamente in nuovo task dall'agente. Nessun nuovo giro di pulizia opzionale.

Report checkpoint ~/pyteman-evidence/task164-1789774626/REPORT-task164.md letto. Proposte fuori scope registrate qui, non implementate: (1) callable-instance residuo nello slot, ad esempio staticmethod(AsyncInst()), dichiarato gap nella forma riconosciuta attuale; peer ha reproducer oos-callable-instance-proof.py, da verificare prima di lavoro successivo. (2) isinstance può eseguire property __class__ del target, preesistente secondo reviewer e non verificato indipendentemente qui; non confondere lettura getattr_static con garanzia assoluta di nessun codice del target. (3) puro classmethod residuo non chiamabile sulle versioni provate, tenuto per coerenza col walker e testato come introspezione, non come comportamento reale chiamabile. Nessun ampliamento runtime in questa unità.

Delta review in corso ha inoltre segnalato test partial che resta verde sulla base; chiesta verifica e correzione solo del detector se deve rilevare il fix. Non ogni controllo positivo deve fallire sulla base: distinguere esplicitamente la finalità del test. Attesa patch finale e APPROVED dopo questo delta, niente nuovo simplify.

PR8 pubblicata e MERGED e731463b10f516bd556705db67970160ee586fc8, commit e229ccd944e884d8338c88fa978b8e0d30c7238d. CI35409917582 tutti sei job success; endpoint review/comments/discussion vuoti al controllo finale. Reviewer high persistente APPROVED sul patch75e39889 come riferito nel handoff e verifiche indipendenti eseguite dal coordinatore; suite fresh export e shared1032 passed/1skip opzionale. shared-suite.log include versione e import path, in ~/pyteman-evidence/task164-integration-20260919-023101/.

Transizione Done BLOCCATA dal dod-completion-gate: richiede chiamata code-review nel transcript del coordinatore e non riconosce review delegata. Nessun hook disabilitato; stato lasciato In Progress per questa limitazione amministrativa, non perché codice/CI siano incompleti. Occorre rendere disponibile la prova effettiva della review delegata tramite meccanismo supportato, non fingere nuovo gate eseguito.

Gate aggiuntivo /code-review nella sessione coordinatrice terminato INCOMPLETO per consegna mancante dei risultati di sei angoli su otto. Ricevuti C senza finding e Altitude con quattro candidati dichiarati preesistenti/non verificati, dettagli richiesti senza nuove esecuzioni. Non viene presentato come approvazione né sostituisce la review persistente indipendente già APPROVED prima di PR8. Il gate aggiuntivo ha eseguito suite1032 passed/1skip e activation147 su3.11–3.14, ma test verdi non equivalgono a review completata. Nessun rilancio di agenti o suite. Stato amministrativo del tracker resta da riconciliare usando prova della review originale, non un clean inventato.

Candidati del solo angolo Altitude del gate aggiuntivo incompleto. TUTTI NON VERIFICATI dal coordinatore e dichiarati preesistenti dal finder; non sono blocker confermati della PR8 né nuove implementazioni autorizzate.
1. patcher.py target796-797: callable-instance residuo scartato, forme __call__=AsyncCallable() o staticmethod(AsyncCallable()); duplica limite già registrato nelle note e nel report TASK164. Nessun task duplicato.
2. patcher.py target795 e docs/rules.md circa684: sottoclasse staticmethod con __get__ personalizzato potrebbe avere semantica diversa dal callable letto via __func__ base; scenario stored coroutine ma getter restituisce sync, possibile rifiuto eccessivo. Suggerimento del finder: qualificare docs/test SneakyGet, NON eseguire getter nel gate. Da riprodurre prima di qualunque cambio.
3. patcher.py target792: getattr_static(type(obj), '__call__') potrebbe leggere metaclasse anziché MRO della classe nel caso object.__new__ su tipo con metaclass async __call__, istanza non callable ma classificata coroutine. Esotico/fail-closed secondo finder, non verificato.
4. patcher.py target798: __call__ property che restituisce coro è opaco e può produrre falso negativo. Getter fuori perimetro documentato e non analizzabile senza esecuzione; nessuna espansione generica ai descriptor decisa.
Disposizione: mantenere qui come input non verificati per eventuale task futuro; niente nuove analisi o fanout per l'unità già pubblicata.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed 2026-09-25 by backlog audit. PR#8 merged as commit e229ccd (recognize nested descriptors in call slots), CI green. Administratively stuck In Progress due to dod-completion-gate transcript mismatch. Code published in v0.2.0.
<!-- SECTION:FINAL_SUMMARY:END -->
