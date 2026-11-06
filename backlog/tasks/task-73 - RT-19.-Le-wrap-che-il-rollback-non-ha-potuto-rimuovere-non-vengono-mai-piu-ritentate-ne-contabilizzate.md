---
id: TASK-73
title: >-
  RT-19. Le wrap che il rollback non ha potuto rimuovere non vengono mai piu'
  ritentate ne' contabilizzate
status: Done
assignee: []
created_date: '2026-09-16 18:46'
updated_date: '2026-09-27 04:16'
labels:
  - rt
  - opus-5
  - from-review
  - audit-2026-09-16
dependencies:
  - TASK-1
references:
  - src/pyteman/patcher.py
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Emerso dalla review Altitude del finale RT-01 (2026-09-16), come seconda meta' di un finding la cui prima meta' e' stata invece applicata (la deduplicazione del messaggio di rollback in `_disclose`). Questa meta' e' stata declinata perche' e' una feature nuova, e l'orchestratore aveva vincolato il tranche a "niente nuove feature, solo completare esattamente le garanzie RT-01".

**Cosa succede oggi.** `_restore` tenta ogni voce separatamente e restituisce quelle rifiutate. `_patch` e `activate` le espongono come nota sull'eccezione, poi le lasciano andare. `uninstall()` svuota `self._wrapped` incondizionatamente. Una wrap che un container ha rifiutato di rimuovere resta quindi installata e pyteman smette di sapere che esiste: la disclosure e' stata fatta una volta sola, all'operatore, nel momento del guasto.

**La proposta della review.** Trattenere le voci rifiutate sul Patcher (per esempio `self.leaked`) in modo che una `uninstall()` successiva le ritenti. Il caso che rende la proposta sensata e' il container che rifiuta transitoriamente: un proxy che e' in uno stato particolare durante il guasto e torna scrivibile dopo.

**Perche' non e' ovvio che sia giusta.** Il caso dominante e' il rifiuto permanente, cioe' un tipo immutabile o un `__setattr__` che rifiuta per progetto: li' `leaked` cresce e non si svuota mai, e un Patcher che tiene riferimenti a container e originali impedisce la garbage collection di entrambi per la vita del processo. Va deciso se il ritentativo e' un servizio reale o solo una ritenzione mascherata da garanzia.

**Nota di perimetro.** RT-01 garantisce che l'unwind finisca e che cio' che resta indietro sia dichiarato. Non ha mai promesso di riuscire a rimuoverlo. Questo task riguarda un contratto piu' forte, non un buco in quello attuale.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Una decisione scritta: o uninstall() ritenta i restore rifiutati e il contratto lo dice, oppure il contratto dice esplicitamente che non lo fa e perche'
- [x] #2 Se il ritentativo viene implementato, un secondo uninstall() su un container che nel frattempo ha smesso di rifiutare rimette a posto la wrap, con un test
- [x] #3 In nessun caso una wrap rifiutata sparisce dalla contabilita' senza essere stata ripristinata
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Due rilievi dal gate di code review di TASK-5 (2026-09-17), depositati qui invece di aprire task separati, su disposizione dell'orchestrator. NON sono lavoro svolto su questo task. Alimentano il criterio #3, che chiede che nessuna wrap sparisca dalla contabilita' senza essere stata ripristinata: il primo caso e' l'opposto speculare (una voce che resta in contabilita' per sempre senza che ci sia piu' nulla da ripristinare), il secondo e' proprio il criterio #3 in un caso che TASK-5 ha reso raggiungibile.

Il contesto e' cambiato da quando questo task e' stato scritto. TASK-5 ha sostituito lo svuotamento incondizionato di `self._wrapped` con la ritenzione delle voci rifiutate, quindi la premessa "uninstall() svuota self._wrapped incondizionatamente" non vale piu': il ritentativo descritto nella proposta della review ESISTE gia' per il percorso dei rifiuti. Quello che questo task deve ancora decidere e' se la ritenzione sia un servizio o una perdita, e i due casi sotto sono i due estremi di quella decisione.

**Caso 1: un nome CANCELLATO dal container dopo il wrap resta in contabilita' per sempre.** Riprodotto il 2026-09-17 con `/tmp/review_probe_task5.py` sullo stato di lavoro di `patcher.py`. Se dopo il patch qualcuno fa `del mod.fn`, la lettura che apre `_undo_one` (`getattr(container, name)`) alza `AttributeError`, che finisce nel `except BaseException` e diventa una tripla di rifiuto. La voce viene quindi RITENUTA e ri-segnalata a ogni uninstall successiva, per uno slot dove non c'e' piu' nulla di wrappato: la wrap e' sparita insieme al nome, e pyteman continua a dire che e' installata. Un secondo `uninstall()` rifiuta di nuovo, identico, all'infinito.

La scelta e' fra due letture dello stesso evento, ed e' un contratto, non un bug da correggere di slancio. Instradare `AttributeError`-in-lettura sul percorso di rilascio (la stessa uscita del caso "lo slot non e' piu' nostro") pulisce la contabilita', ma rilascia silenziosamente anche il container ostile il cui `__getattr__` alza per scelta e che potrebbe avere ancora il wrapper vivo. Tenerlo sul percorso di rifiuto, come oggi, e' onesto ma produce esattamente lo strand che non si svuota mai di cui parla la sezione "Perche' non e' ovvio che sia giusta" sopra. `docs/rules.md` e' stato qualificato nella stessa tranche per dichiarare l'eccezione invece di affermare una corrispondenza che il codice non ha.

**Caso 2: un container il cui getattr non restituisce cio' che il setattr ha messo produce un rilascio falso.** Informativo, non un difetto: e' il contratto di rilascio introdotto da TASK-5 applicato correttamente a un caso dove l'osservazione inganna. `_undo_one` decide con `getattr(container, name) is not wrapper`, cioe' sull'identita' OSSERVATA. Una property il cui getter trasforma, o un proxy che restituisce un oggetto diverso da quello memorizzato, fa fallire quel confronto anche quando il wrapper e' ancora perfettamente vivo dietro. La voce viene allora scartata senza rifiuto, e quindi senza comparire in nessuna disclosure: pyteman smette di sapere che esiste, che e' il criterio #3 al contrario. Il rilascio e' cio' che il contratto ordina (lo slot non risponde piu' con il nostro wrapper, e sovrascriverlo calpesterebbe chi c'e' adesso), quindi non c'e' niente da correggere finche' il contratto non cambia. Va tenuto presente quando si decide il caso 1, perche' le due uscite sono la stessa uscita.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Merged as 5820eb3 via PR #151 (head 19f1edd, docs-only). TASK-73 was substantially already satisfied: the retry behavior was implemented by TASK-5's retained ledger, documented in uninstall()'s docstring, and tested by two tests in test_activation_atomic.py; what this change adds is the operator-facing decision AC #1 demanded. Two review rounds shaped the sentence: the four-angle pass corrected the holder attribution (the entry belongs to the Patcher, not uninstall() or the container), and the code-review belt's probes falsified the first closing clause on both halves (the wrap pins the Patcher through the dispatcher's _pyteman_owner marker, and _live_dispatcher_owner still answers for a refused wrap, so a second Patcher is refused the slot); the final wording states the true coupling: the record lives exactly as long as the wrap, and dropping your Patcher reference loses only the handle on the retry, not the accounting. Coupling re-confirmed by probe before commit. Gates: /simplify four-angle findings applied; code-reviewer-typed high review with its critical finding applied; battery check clean, 1263 passed 2 skipped; independent review APPROVED at 19f1edd with zero findings; PR CI all green; master CI green.
<!-- SECTION:FINAL_SUMMARY:END -->
