---
id: TASK-147
title: >-
  Il passo __call__ salta un caso decidibile: __call__ che e' un partial o uno
  staticmethod
status: Done
assignee: []
created_date: '2026-09-17 11:02'
updated_date: '2026-09-25 10:56'
labels:
  - opus-5
  - deferred-from-task-3
dependencies: []
references:
  - src/pyteman/patcher.py
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Trovato durante TASK-3 (2026-09-17) e non applicato: allargare qui sconfina in RT-06 (supporto generico ai descrittori), escluso dall'assegnazione.

`_suspendable_reason` segue il `__call__` del tipo solo quando `inspect.isfunction(call)` e' vero. Se `__call__` e' un `functools.partial`, uno `staticmethod` o un altro callable non-funzione che avvolge un `async def`, la natura e' comunque decidibile staticamente ma il cammino si ferma e il punto viene instrumentato.

Non e' il caso indecidibile (una def ordinaria che restituisce un awaitable): qui l'informazione c'e' e non viene letta.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Un'istanza il cui __call__ del tipo e' un functools.partial su un async def e' rifiutata.
- [x] #2 Un'istanza il cui __call__ del tipo e' uno staticmethod su un async def e' rifiutata.
- [x] #3 Il fix non introduce supporto generico ai descrittori: resta fuori scope RT-06.
- [x] #4 Un'istanza di una sottoclasse di functools.partial con __call__ async def e' rifiutata: oggi il ramo partial precede la lettura di __call__ e la nasconde.
- [x] #5 La promessa e' coerente in TRE punti, non due: docs/rules.md, e anche il docstring di _suspendable_reason a patcher.py:615-616.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
GATE FRAMING, altitude and simplification gates, 2026-09-17.

The altitude gate reframed this defect in a way worth keeping. It is not a missing deep case, it is the loop failing to be a fixpoint over the edges it already has. _suspendable_reason follows functools.partial at patcher.py:624, but the __call__ step at :628 accepts only inspect.isfunction(call), so a __call__ that is itself a partial over an async def stops the walk even though the loop knows how to follow that edge four lines above. The fix is to express the step as an edge rather than a per-edge type test.

The tests pin exactly one composition direction. partial_instance at tests/test_activation_atomic.py:4122 covers partial, then instance, then __call__. The reverse, instance then __call__ then partial, is unsupported and invisible to a reader.

Simplification gate probes, confirming the gap is live:

  class B: __call__ = functools.partial(coro)   # coro is async def
  _suspendable_reason(B())  -> (None, None)     # instrumented, not refused
  class C: __call__ = staticmethod(coro)
  _suspendable_reason(C())  -> (None, None)

DOCS OVER-PROMISE, same defect, second location. Filed here rather than separately because fixing the code without this line still leaves the documentation wrong today.

docs/rules.md:570-573 describes the surface as including, for a callable instance, the type's __call__, 'which is read and not invoked', with no restriction stated. The code follows that edge only when inspect.isfunction(call). The code comment at patcher.py:630-632 states the restriction correctly; only the docs sentence promises the whole shape.

So this task now has two ends. Either narrow the docs sentence to what the code does, or widen the code to what the docs say and keep the sentence. Widening is the better direction given the framing above, but whichever is chosen, both ends move in the same change.

SEVERITY RAISED TO HIGH, 2026-09-17, on the code review gate's end-to-end reproduction. What was filed as a decidable case the walk declines to read is in fact a DOCUMENTED guarantee that is false, and the damage it lets through is verbatim the damage the refusal was written to prevent.

Reproduced against the real src/pyteman/patcher.py:

  class S:
      __call__ = staticmethod(fetch)      # async def fetch(a): return a
  mod.sm = S()                             # rule: exit, return_value 1

  uninstrumented sm(1) -> coroutine
  applied: ['gapmod:sm']
  instrumented   sm(1) -> 1
  warnings: ["coroutine 'fetch' was never awaited"]

The coroutine is discarded, the body never runs, the caller gets an int, and the only evidence is a GC-time RuntimeWarning. That is word for word the case SuspendableTargetError.__doc__:535-539 names as the reason the refusal exists. __call__ = functools.partial(fetch) behaves identically.

The promise is in two places, not one. docs/rules.md:570-573 says the type's __call__ is read for a callable instance, with no restriction. docs/rules.md:601-602 goes further and says a shape in the list above is refused and never quietly instrumented. Both are false for a __call__ that is not itself a Python function.

The gate confirmed the boundary is exactly 'the type's __call__ is not itself a Python function': the inherited __call__, async metaclass __call__ and bound __call__ variants are all correctly refused today.

Interim mitigation applied in TASK-3, 2026-09-17: the two docs sentences are narrowed to a Python-level __call__, so the documentation stops promising what the code does not do. This task remains open for the real fix, which is widening the edge to unwrap staticmethod.__func__ and re-enter the partial branch, and restoring the broader promise in the same change.

TERZA COPIA DELLA PROMESSA, trovata dal code review gate di TASK-3 il 2026-09-17 e verificata direttamente.

La nota sopra dice che la promessa troppo ampia vive in due punti, entrambi in docs/rules.md, entrambi ristretti in TASK-3. Sono tre. Il docstring di _suspendable_reason chiude a patcher.py:615-616 con:

  'The promise kept here is that a recognised shape is refused and never quietly instrumented.'

Regge solo leggendo 'recognised' come autoreferenziale, cioe' 'cio' che questo cammino per caso legge'. E' una difesa piu' debole delle due frasi che in TASK-3 sono state giudicate insufficienti e riscritte. Le tre copie vanno spostate insieme quando il bordo viene allargato, altrimenti il codice resta allineato ai docs e disallineato al proprio docstring.

QUARTO CASO DECIDIBILE NON LETTO, e questo e' un problema di PRECEDENZA, non di bordo mancante. Trovato dal code review gate di TASK-3 il 2026-09-17, verificato con probe diretto sul file reale.

Una sottoclasse di functools.partial che definisce __call__ come async def e' instrumentata invece che rifiutata, e questo accade per una forma che i docs elencano esplicitamente.

Probe, ORIGIN /home/pantinor/data/repo/personal/pyteman/src/pyteman/patcher.py:

  def plain_func(a): return a
  class P(functools.partial):
      async def __call__(self, *a, **k): return 1
  p = P(plain_func)
  p()                          -> coroutine, iscoroutine True
  _suspendable_reason(p)       -> (None, None)      INSTRUMENTATO

  controllo, la forma che i docs promettono:
  class Q:
      async def __call__(self, a): return a
  _suspendable_reason(Q())     -> ('a coroutine function', None)   RIFIUTATO

Meccanismo, tracciato riga per riga nel loop a patcher.py:619-634. I tre predicati srotolano il partial da soli e leggono plain_func, che e' sincrono, quindi rispondono tutti False. Poi isinstance(current, functools.partial) a :627 e' vero anche per la sottoclasse, quindi current viene ridiretto su func e il loop fa continue. La lettura di __call__ del tipo a :630 non viene mai raggiunta.

Definire __call__ su una sottoclasse di partial sovrascrive davvero lo slot di chiamata, quindi l'oggetto e' realmente coroutine-returning: il probe sopra lo misura, non lo assume.

E' la stessa radice che l'altitude gate ha gia' nominato in questa task: il loop non e' un punto fisso sugli archi che possiede. Qui pero' non manca un arco, ce ne sono due applicabili e quello sbagliato vince perche' viene prima. Un fix che si limita a srotolare staticmethod.__func__ NON copre questo caso. Serve che la lettura di __call__ del tipo sia tentata prima di seguire partial.func, oppure che entrambi gli esiti vengano considerati invece di uscire al primo arco che combacia.

Caso esotico, e non giustifica da solo un allargamento. Vale come vincolo di progetto sul fix di questa task: qualunque forma prenda, va verificata anche su questa composizione, altrimenti la promessa ripristinata sarebbe falsa il giorno stesso in cui viene riscritta.

ASSORBITO IN TASK-3, 2026-09-17, su decisione del reviewer pyteman-89. Nessun criterio viene cancellato qui: restano scritti come richiesta originale, e questa nota dice dove ognuno e' stato soddisfatto. Lo stato del task NON viene cambiato da me: la chiusura e' una chiamata del reviewer.

Il reviewer ha respinto il routing di questi casi fuori da TASK-3. La sua osservazione, che accetto: il limite 'solo funzione Python' sul bordo __call__ non era un requisito di TASK-3, era una restrizione che avevo introdotto io per evitare RT-06, e il caso della sottoclasse di partial non e' un gap di lettura ma un errore di precedenza dentro la superficie che TASK-3 dichiara.

DOVE OGNI CRITERIO E' ORA SODDISFATTO, tutto in TASK-3, misurato e non dedotto.

#1 __call__ = functools.partial(async def)  -> rifiutato. Regressione: parametro 'partial_call' in test_a_suspendable_target_is_refused_with_its_slot_untouched.
#2 __call__ = staticmethod(async def)      -> rifiutato. Regressione: parametro 'static_call' nello stesso test.
#4 sottoclasse di partial con __call__ async def -> rifiutata. Regressioni 'subclass_async', 'subclass_gen', 'subclass_agen', piu' il positivo 'subclass_sync' che prova la direzione opposta.
#3 rispettato: nessun supporto generico ai descrittori. Il lettore dello slot e' una funzione di otto righe che riconosce due sole forme note, staticmethod via __func__ e functools.partial che rientra nel walk. Non c'e' protocollo descrittore, non si invoca nulla, non si segue __wrapped__.
#5 le tre copie della promessa sono ora allineate: docs/rules.md nella sezione 'What is recognised', la frase finale della stessa sezione, e il docstring di _suspendable_reason, che non dice piu' 'a recognised shape' in senso autoreferenziale ma nomina le forme lette.

PROVA DI NON VACUITA' DEI NUOVI TEST, perche' una regressione che non uccide nulla non chiude un criterio.

Due mutanti costruiti su copie temporanee sotto /tmp, mai sul file reale, con PYTHONPATH puntato alla copia.

MUTANTE A, precedenza rimossa: il ramo che legge lo slot __call__ prima dei predicati viene disattivato, cioe' il comportamento precedente in cui isinstance(current, functools.partial) vince e spacchetta func.
  risultato: 4 failed, 112 passed
  uccisi: subclass_async, subclass_gen, subclass_agen, subclass_sync

MUTANTE B, bordo ristretto: _call_slot torna a seguire solo inspect.isfunction(call), cioe' la restrizione che questo task contestava.
  risultato: 2 failed, 114 passed
  uccisi: static_call, partial_call

Le due partizioni sono disgiunte e insieme coprono tutti e sei i nuovi casi. Nessuna meta' del fix e' priva di guardia, e nessun nuovo test passa a vuoto.

Nota sul mutante A: il test ucciso che conta di piu' e' 'subclass_sync', il POSITIVO. Sotto il mutante la suite non fallisce perche' qualcosa non viene rifiutato, fallisce con SuspendableTargetError su un callable che restituisce un int. E' il falso positivo, la stessa classe di difetto per cui il walk di __wrapped__ era stato rimosso, e senza quel test il fix avrebbe potuto essere 'rifiuta tutto cio' che e' una sottoclasse di partial' senza che nulla protestasse.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
All five acceptance criteria were satisfied in TASK-3, as documented in this task's own implementation notes under "ASSORBITO IN TASK-3" and "DOVE OGNI CRITERIO E' ORA SODDISFATTO". Closing per that record.

AC #1: __call__ = functools.partial(async def) refused. Regression: parametro 'partial_call'.
AC #2: __call__ = staticmethod(async def) refused. Regression: parametro 'static_call'.
AC #3: No generic descriptor support introduced; _call_slot recognizes two forms only.
AC #4: Partial subclass with async __call__ refused. Regressions: 'subclass_async', 'subclass_gen', 'subclass_agen', plus positive 'subclass_sync'.
AC #5: All three copies of the promise aligned (docs/rules.md section, its closing sentence, and _suspendable_reason docstring).
<!-- SECTION:FINAL_SUMMARY:END -->
