---
id: TASK-4
title: RT-04. Rendere esplicita e verificabile la copertura dell'import hook
status: Done
assignee: []
created_date: '2026-09-16 12:20'
updated_date: '2026-09-29 17:50'
labels:
  - audit-2026-09-16
  - opus-5
  - rt
  - confirmed
milestone: m-0
dependencies:
  - TASK-1
  - TASK-2
references:
  - 'src/pyteman/patcher.py:19-35,101-109,143-146'
  - 'README.md:112-127'
documentation:
  - doc-1
  - doc-2
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P1 per diagnostica, P2 per ampliamento; CONFIRMED, aperto.

**File:** `src/pyteman/patcher.py:19-35,101-109,143-146`, `README.md:112-127`.

**Evidenza:** `importlib.import_module('audit_dynamic')` dopo installazione non patcha il target; un normale import successivo sì. `install()` da solo non applica patch ai moduli già caricati, mentre sitecustomize compensa con force_patch_module. `importlib.reload()` rimuove la patch. Un attributo inesistente viene ignorato senza diagnostica. Import relativi e submoduli sono già limiti documentati, non nuovi bug scoperti.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 matrice con import normale, from-import, relativo, dotted, import_module, precaricato e reload.
- [x] #2 Ogni forma supportata inietta; ogni forma non supportata è segnalata senza falsi successi.
- [x] #3 Non fallire prematuramente per moduli legittimamente ancora non importati.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Proposta iniziale da verificare sul codice corrente, non una correzione già applicata.

esporre stato per regola: in attesa del modulo, applicata, target assente/non supportato, errore. Definire policy strict per target richiesti e comportamento API per moduli precaricati/reload. Valutare un hook basato sul protocollo importlib per superare i limiti solo dopo test delle forme reali di import.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: RT-01, RT-02; DOC-01 deve descrivere il contratto deciso.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.

Misura trasferita da TASK-1 (RT-01), 2026-09-16. NON e' lavoro svolto qui: e' il confine di RT-01, che cade dentro il criterio #2 di questo task invece che in un task nuovo.

RT-01 rende l'attivazione atomica e fail-closed per i fallimenti che avvengono PRIMA che il workload parta: caricamento del ruleset, apertura del log, e il ciclo di patch dei moduli gia' presenti in `sys.modules`. Non copre, e per costruzione non puo' coprire, i fallimenti di patch serviti dall'import hook mentre il workload gira.

**Riproduzione.** Sottoprocesso reale, avvio via PYTHONPATH su `src/pyteman`, ruleset con due regole sullo stesso modulo: la prima su una funzione normale, la seconda su `target_mod.CInt.bit_length` dove `CInt` e' `builtins.int` importato nel modulo, cioe' un tipo immutabile su cui `setattr` viene rifiutato.

```
immutable      exit=1 stdout=''
               stderr=Traceback (most recent call last):
                 File "<string>", line 1, in <module>
                   import target_mod; print('WORKLOAD_RAN', ...)
```

Nessun `pyteman: refusing to start:`, nessun exit 2. Confrontato con gli altri cinque casi del criterio #1 di RT-01, che escono tutti 2 con la fase nominata.

**Meccanismo, tracciato link per link.** Al momento in cui `sitecustomize` chiama `activate()`, `target_mod` non e' ancora in `sys.modules`: lo importa il workload, dopo. Quindi `activate()` esegue `force_patch_module('target_mod')` che trova `None` ed e' un no-op, e il ciclo di patch termina senza toccare nulla. La patch avviene piu' tardi, dentro `hooked()` (patcher.py, `install_hook`), servita dall'import del workload. Il `TypeError` del `setattr` rifiutato risale quindi lungo lo stack dell'`import target_mod` dell'utente, non lungo quello di `activate()`, dove sta il `try/except BaseException` che chiama `uninstall()`.

**Il docstring di `activate()` nomina gia' questo confine** ("install() on its own hooks `__import__` and patches lazily, so a rule that fails while a later import is being served cannot be unwound from where the failure surfaces"). La misura sopra e' la conferma empirica di quella frase, non una scoperta contraria.

**Perche' appartiene a RT-04 e non a un task nuovo.** Il piano di questo task prevede gia' di "esporre stato per regola: in attesa del modulo, applicata, target assente/non supportato, errore". Un fallimento di patch al tempo dell'hook E' lo stato "errore" di quella lista, e oggi non ha nessuna rappresentazione: esce come traceback grezzo dall'import del workload. Il criterio #2 ("ogni forma non supportata e' segnalata senza falsi successi") e' il posto dove va chiuso. Le dipendenze sono gia' corrette: questo task dipende da TASK-1.

**Nota sul perimetro, per chi eseguira' RT-04.** Non c'e' un requisito che il processo muoia per errori successivi all'avvio attraverso la API programmatica: un consumer che chiama `install()` e gestisce i propri import puo' legittimamente voler catturare l'errore. Quello che serve e' che lo stato per regola lo renda visibile, e che nessun documento descriva come atomica una copertura che si ferma all'avvio. La documentazione di RT-01 e' stata scritta di conseguenza: dichiara l'atomicita' per la fase di attivazione e nomina esplicitamente questo residuo come limite noto.

Aggiornamento del confine, 2026-09-16, durante l'esecuzione di TASK-1 (RT-01). La nota precedente qui sopra va letta come storica: descrive lo stato del codice PRIMA della modifica di RT-01, e una delle sue affermazioni non e' piu' vera.

**Cosa e' cambiato.** Il rollback e' stato spostato dal chiamante al sito della mutazione. `Patcher._patch` ora registra un savepoint all'ingresso (`mark = len(self._wrapped)`, `mark_applied = len(self.applied)`) e in `except BaseException` ripristina il suffisso prima di rilanciare. Questo vale su OGNI percorso che patcha, incluso `hooked()`, dove non esiste nessun handler esterno. `activate()` continua ad aggiungere cio' che il ciclo non puo' raggiungere dall'interno: la rimozione dell'import hook e i moduli patchati PRIMA di quello fallito.

**Quindi la frase 'non copre, e per costruzione non puo' coprire, i fallimenti di patch serviti dall'import hook' non e' piu' corretta come scritta.** Va divisa in due meta':

- *Nessuna patch parziale*: ORA COPERTA anche sul percorso hook. Un `setattr` rifiutato a meta' di un modulo non lascia piu' i wrap precedenti applicati. Test: `tests/test_activation_atomic.py::test_import_hook_rolls_back_the_module_it_was_patching`, che guida `builtins.__import__(MODNAME)` con l'hook vivo e verifica che il primo wrap sia tornato all'originale e che `applied` sia vuoto.
- *Diagnostica e stato per regola*: ANCORA SCOPERTA, ed e' il residuo reale che resta a RT-04. Il fallimento esce come traceback ordinario dall'`import` del workload, senza fase, senza exit 2 e senza nessuna rappresentazione nello stato per regola. La riproduzione registrata sopra (exit=1, traceback, nessun `pyteman: refusing to start:`) resta valida ed e' esattamente questa meta'.

**Asimmetria deliberata, da non trattare come bug in RT-04.** Su fallimento dal percorso hook `_patch` disfa i propri wrap ma NON rimuove l'import hook: non ne e' proprietario, e le regole sugli altri moduli sono ancora buone. Il test citato la fissa esplicitamente.

**Perimetro confermato.** Resta valido che non c'e' requisito di far morire il processo per errori successivi all'avvio attraverso la API programmatica. Quello che serve e' la visibilita' per regola del criterio #2. La documentazione di RT-01 e' stata riscritta di conseguenza: `docs/rules.md` ora dichiara atomico anche il percorso hook e nomina come limite noto solo COME il fallimento raggiunge l'operatore, non cosa lascia dietro.

Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #104 #133. Added lines already present on master per PR: #104 1/199=0% absentfiles=1  #133 0/263=0% absentfiles=3. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.

Merged 2026-09-29 via #187 (dd835e6). Evidence under /home/pantinor/pyteman-evidence/t191/: diff4.patch sha256 00d8b803, tree4-hold4.sha256, mutants-4-simplify/codereview/final.log, suite4-*.log, VERDICT-4.md in t191rev.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by PR #187, squash-merged as dd835e6 on master at 2026-09-29 17:49Z. Patcher.displaced() reports, in ruleset order and deduplicated, the rules that landed and whose point no longer reaches a dispatcher serving them (importlib.reload, third-party replacement); the point is walked from sys.modules with an absent-module slot fallback, each distinct point read once per call, and a mid-flight re-patch honoured through _inflight exactly as _patch's comments prescribe. The atexit report (renamed _report_dispositions) prints one 'replaced after landing' line per such rule after the never-landed lines, exit code unchanged. README's import-hook section rewritten to the measured matrix with the miss forms attributed to the hook layer and TASK-196 cited; docs/rules.md documents the contract. 34 tests in tests/test_import_hook_coverage.py pin the matrix, both read-once disciplines and the mid-flight window via a metaclass __setattr__ re-entry. Supersedes #104 and #133 (both rule_states()-based, closed with pointers; the design settled on pending+displaced+applied as the surface). Gates at 493fe23: suite 1481 passed 2 skipped, check green, delivery 41, mutation battery 15/15 with one equivalent mutant retired with reason (mutants-4-final.log), /simplify four angles applied, code-review high five findings applied, independent verdict APPROVED (VERDICT-4.md). Review leftovers: TASK-199 structural follow-ups, TASK-196 hook-layer note.
<!-- SECTION:FINAL_SUMMARY:END -->
