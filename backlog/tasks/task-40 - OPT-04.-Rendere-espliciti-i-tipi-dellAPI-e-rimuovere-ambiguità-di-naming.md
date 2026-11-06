---
id: TASK-40
title: OPT-04. Rendere espliciti i tipi dell'API e rimuovere ambiguità di naming
status: To Do
assignee: []
created_date: '2026-09-16 12:20'
updated_date: '2026-09-22 10:52'
labels:
  - audit-2026-09-16
  - opus-5
  - opt
  - proposal
milestone: m-6
dependencies:
  - TASK-7
  - TASK-2
  - TASK-21
  - TASK-15
references:
  - src/pyteman/py.typed
  - 'src/pyteman/rules.py:15-34'
  - 'src/pyteman/runner/matrix.py:5'
  - 'src/pyteman/runner/report.py:4'
  - .basedpyright/baseline.json
  - /home/pantinor/pyteman-evidence/task173/types-before.json
documentation:
  - doc-1
  - doc-2
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P3, PROPOSTA, aperto.

**File:** `src/pyteman/py.typed`, `src/pyteman/rules.py:15-34`, `src/pyteman/runner/matrix.py:5`, `src/pyteman/runner/report.py:4`, contesti in patcher/actions/targets.

**Evidenza di opportunità:** il package distribuisce py.typed ma molte API sono dict/list senza schema o annotazioni specifiche. `parse_point` divide all'ultimo punto mentre load_rules divide al primo; il contrasto è intenzionale e documentato nel sorgente, ma è facile riutilizzare l'helper sbagliato.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 esempi di uso passano un type checker configurato; input errati rilevati; API compatibile o migrazione documentata; test espliciti per exit su successo/errore e parse point.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Proposta iniziale da verificare sul codice corrente, non una correzione già applicata.

TypedDict/Protocol o dataclass minime per Rule, context, Cell, result e record, senza introdurre un framework di validazione sproporzionato. Rinominare/documentare i due contratti di point, con deprecazione se pubblici. Definire comportamento delle exit action quando la funzione originale solleva, inclusa priorità fra eccezione originale e iniettata; il fatto che return_value non sopprima automaticamente l'eccezione originale non è stato classificato come bug.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: CFG-01, RT-02, RUN-03, LOG-02.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.

Misura a supporto dal gate di TASK-7 (2026-09-16), trasferita qui da TASK-52 prima di archiviarlo. NON e' lavoro svolto su questo task: alimenta la riga del piano che chiede di definire il comportamento delle exit action quando la funzione originale solleva.

Questo task dice gia' che il fatto che `return_value` non sopprima automaticamente l'eccezione originale NON e' classificato come bug. La misura qui sotto non cambia quella classificazione: documenta il comportamento corrente perche' la decisione si prenda su dati invece che a memoria.

**Meccanismo.** In `patcher.py:84-96` il gate di exit gira nel `finally` di un `try/except BaseException: raise`. Quando il corpo alza, `_gate` passa, `run_action` imposta `ctx['_override']` e scrive il record, ma il `raise` nudo della riga 88 ha gia' rilanciato e la riga 96 (`return override if ...`) non viene mai raggiunta. L'override esiste e non viene letto.

**Misura, con il ruleset IDENTICO sui due corpi** (`boom` alza ValueError, `ok(a)` ritorna `a`, chiamate con 7):

    ruleset {event: exit, action: {kind: return_none}}, nessun when
      corpo ALZA    -> RAISED ValueError: body failed    firings=1
      corpo RITORNA -> returned None                     firings=1

    stesso ruleset piu' when: 'exc is not None'
      corpo ALZA    -> RAISED ValueError: body failed    firings=1
      corpo RITORNA -> returned 7                        firings=0

Il primo blocco e' quello che dimostra il punto: stesso ruleset, stessa azione, un firing per parte, e l'override applicato solo dove il corpo e' tornato. Il secondo e' il controllo che conferma il gate.

**Correzione di un resoconto precedente.** La prima stesura di questa segnalazione (su TASK-52) presentava le due righe come provenienti da un unico ruleset con `when: 'exc is not None'`. Era falso: la sonda usava `when` diversi sui due rami, e come l'orchestrator ha fatto notare con quel `when` il corpo che ritorna non puo' produrre un firing. Le cifre sopra vengono dalla riesecuzione con il ruleset davvero identico. La sostanza regge, il resoconto no.

**Sul record di firing, in coordinamento con TASK-15.** Avevo scritto che il log 'afferma che la regola ha agito'. Non e' il contratto di questo progetto: TASK-15 stabilisce che il record precede l'azione e prova il TENTATIVO, non la riuscita. Il record non mente quindi. Resta che tentativo-senza-effetto e tentativo-con-effetto oggi sono indistinguibili a valle, che e' esattamente cio' che lo schema con attempt id e stati applicato/skipped/failed di TASK-15 renderebbe leggibile. Nessuna richiesta aggiuntiva qui: il caso e' un consumatore della decisione di TASK-15.

**Copertura di test.** `tests/test_patcher.py` ha solo `test_exit_event_can_override` su un corpo che ritorna; il corpo che alza non e' coperto. Rientra nel criterio #1 di questo task, che chiede gia' test espliciti per exit su successo ed errore.

**Documentazione.** `docs/rules.md` descrive il caso come comportamento corrente con decisione pendente e rimanda qui, senza proporre la soppressione come esito atteso. Va riletto quando questo task decide; annotato anche su TASK-46.

Finding dal gate /simplify di TASK-7 (2026-09-16), trasferito qui invece di aprire un task duplicato. NON e' lavoro svolto su questo task: alimenta il criterio #1, che chiede API tipizzate e senza ambiguita'.

**`parse_target_spec` restituisce una tupla che i chiamanti leggono per indice.** La firma e' `(kind, name, dotted) | None, reason`, e i due consumatori fuori da `targets.py` la aprono posizionalmente:

- `src/pyteman/rules.py:341`: `parsed, _ = parse_target_spec(action['target'])` poi `parsed[0] == 'result'`
- `src/pyteman/patcher.py:84-86`: stessa forma, `parsed[0] == 'param'`

`parsed[0]` non dice al lettore che si tratta del KIND, e un riordino dei campi della tupla resta muto in entrambi i call site invece di rompere: e' esattamente la classe di guasto che questo task esiste per chiudere. Un NamedTuple (o un TypedDict per la coppia esito/motivo) darebbe `parsed.kind` e farebbe fallire il type checker su un riordino.

Da coordinare con la nota gia' presente su `parse_point`: sono due facce dello stesso punto, cioe' contratti di parsing che si leggono correttamente solo con il sorgente aperto accanto.

Vincolo da preservare in qualunque riscrittura, registrato nelle note di TASK-7 come "Simplify, proposta 8" e li' motivato: la guardia `parsed is not None` prima di `parsed[0]` va tenuta anche se a runtime e' irraggiungibile, perche' il tipo di ritorno e' opzionale (senza, Pyright segnala `reportOptionalSubscript`) e l'alternativa con `assert` sparirebbe sotto `-O`, cioe' proprio nell'interprete di chi carica il ruleset.

Osservazione raccolta durante TASK-1 (RT-01), 2026-09-16. Non e' lavoro svolto qui e non e' una regressione introdotta da RT-01: e' preesistente, verificata con `git diff HEAD -- src/pyteman/patcher.py`, dove la riga in questione non compare.

Pyright segnala `reportAttributeAccessIssue` su `wrapped._pyteman_state = state` in `Patcher._make_wrapper` (`src/pyteman/patcher.py`): "Cannot assign to attribute for class `_Wrapped[...]`". La causa e' il tipo che `functools.wraps` da' al wrapper: `_Wrapped` non dichiara attributi arbitrari, e lo stato per-regola viene appeso al callable come attributo. Il codice funziona, il checker no.

E' rilevante per questo task perche' quell'attributo NON e' un dettaglio interno accidentale: `_patch` lo legge (`getattr(original, "_pyteman_state", None)`) per riconoscere i callable che ha gia' wrappato e non wrapparli due volte. E' quindi parte del contratto fra patcher e wrapper, ed e' espresso oggi come un attributo non tipizzato appiccicato a un oggetto di libreria.

Seconda osservazione dallo stesso giro, stessa natura: `sys._pyteman = {...}` in `src/pyteman/sitecustomize.py` produce lo stesso genere di diagnostica ("_pyteman is not a known attribute of module sys"). Anche questo e' deliberato e anche questo e' un canale fra componenti che non ha un tipo.

Chi esegue OPT-04 valuti se entrambi vadano espressi come una struttura dichiarata invece che come attributi appesi. Non serve un task separato: rientrano in "rendere espliciti i tipi dell'API".

TASK-173 deploys basedpyright1.40.1 standard mode targeting Python3.11 with a frozen initial baseline. Measured 14 diagnostics:13 in patcher.py concerning descriptor/function typing and runtime wrapper attributes;1 in sitecustomize.py sys._pyteman. This is recorded type debt, not verified runtime defects or work completed under TASK-40. Routine check uses --baselinemode=lock and does not update baseline. Fixes to these contracts belong here; do not widen baseline to silence new diagnostics. Original diagnostic JSON in /home/pantinor/pyteman-evidence/task173/types-before.json.
<!-- SECTION:NOTES:END -->
