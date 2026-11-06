---
id: TASK-66
title: >-
  Runner: chiavi non stringa nel risultato, oggetto restituito e riga
  memorizzata si contraddicono
status: Done
assignee: []
created_date: '2026-09-16 18:23'
updated_date: '2026-09-25 10:58'
labels:
  - audit-2026-09-16
  - run
  - confirmed
  - from-code-review
milestone: m-3
dependencies:
  - TASK-21
references:
  - 'src/pyteman/runner/matrix.py:_cell_result'
  - 'src/pyteman/runner/matrix.py:_reject_coerced_keys'
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Trovato dalla code review high di RUN-03 (TASK-21). Il reviewer lo ha esplicitamente segnalato per il registro e non come richiesta di modifica; tracciato qui perche un rilievo non diventi una nota senza proprietario.

**File:** `src/pyteman/runner/matrix.py:634-640` (`_cell_result`).

**Difetto:** `{1: "a", True: "b"}` supera il controllo `isinstance(value, dict)` e viene memorizzato come `{"1": "b"}`, mentre al chiamante viene restituito `{1: "b"}`. Due asimmetrie in una: le chiavi intere diventano stringhe passando da `json.dumps`, e `1` e `True` collassano sulla stessa chiave gia in Python.

**Perche non e urgente:** i risultati non entrano nel fingerprint, quindi nulla viene attribuito alla cella sbagliata e nessuna decisione di resume dipende da questo.

**Perche non e nulla:** l'oggetto restituito e la riga registrata si contraddicono sul tipo delle chiavi, e la riga e il record durevole. Un lettore che indicizza il risultato per chiave intera trova la chiave in memoria e non la trova nel database.

**Incoerenza interna da valutare:** `_reject_coerced_keys` tratta esattamente la stessa coercizione come fatale quando avviene in una definizione di cella. Delle due politiche una sola puo essere quella giusta, o va detto perche il risultato merita un trattamento piu permissivo della definizione.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Decisione esplicita fra rifiutare le chiavi non stringa nel risultato e accettarle documentando la coercizione.
- [x] #2 L'oggetto restituito al chiamante e la riga memorizzata non si contraddicono piu sul tipo delle chiavi, o la differenza e dichiarata nel contratto.
- [x] #3 Coerenza verificata rispetto a _reject_coerced_keys, che tratta la stessa coercizione come fatale per le definizioni.
- [x] #4 Test sul caso {1: 'a', True: 'b'}, dove due chiavi distinte collassano in una.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Decisione esplicita nel lavoro autonomo autorizzato: rifiutare chiavi risultato non-stringa ricorsivamente, senza normalizzarle in silenzio. Callback invalido diventa cell failed con errore serializzabile e matrice continua, come gli altri risultati non validi. Riusare traversal esistente ove possibile separando diagnostica result da politica fingerprint, senza schema/migrazione o refactor del runner. None->{} e controlli dict esistenti invariati.

Test top/nested chiavi int/bool/float/None, mapping string validi e contenitori list/tuple annidati, status restituito/durable/attempt coerenti, cella successiva eseguita e input non mutato. Caso{1:'a',True:'b'} ha già perso 'a' prima del runner: rifiutare key risultante, non ricostruire storia Python. Definizioni restano rifiutate con MatrixIdentityError, cicli e serializzazione result restano cell-failure. Docs sul contratto callback e mutant validation no-op. Base61a5b55 in copia, simplify mirato, review indipendente finale e PR separata.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Coordinatore riproduce con run_matrix reale: returned status done result{1:'b'}, stored JSON{"1":"b"}, tipi chiave int vs str. Evidenza ~/pyteman-evidence/task66-repro-1bfpeqsh. Prerequisito TASK21 Done secondo scout e record precedente. TASK65 non assegnato: testo could-not-be-read non prova da solo invalid database e discriminazione SQLite non necessariamente richiede string matching; eventuale assessment separato. Nessun codice shared modificato.

Candidato20e85f24745d100ac628af6b24778b82bb33588d631ccda669a785d8e824fda5 letto: CHANGES REQUESTED coordinator prima review finale. Nuovo walker iterativo riusato da definizioni cambia precedenza diagnostica (chiavi root prima nested) e ciclo da RecursionError a ValueError, non semantica identica come dichiarato dal peer. Mandato è mantenere definizioni invariate; richiesto ripristino byte-exact _reject_coerced_keys e commento _canonical della base61a5b55, lasciando check result separato. Nessun nuovo refactor/simplify/fanout.
Limite preesistente non risolto: diagnostica definizione usa str(key), mentre JSON usa true/null per bool/None; registrato qui per non perderlo, fuori modifica corrente. Timing25/96/51s non attribuito a cache/carico sulla sola misura nuovi test0.02s: correlazione insufficiente, tenere misure grezze. Peer suite1173/2skip ancora risultato dichiarato su candidato fuori scope, non prova di consegna approvata.

Reviewer conferma indipendentemente sul candidato ritirato i due scostamenti: errore chiave annidata1 vs root2 e ciclo RecursionError vs ValueError. Ripristino definizioni esatto alla base confermato come scelta; walker iterativo resta solo sul risultato per non introdurre rifiuti di profondità serializzabili prima della modifica. Soglie misurate dal reviewer dipendono da build/frame e non sono garanzie; nessun limite numerico promesso, nessuna pretesa di profondità illimitata. Il limite ricorsivo preesistente delle definizioni resta fuori scope, senza nuova attività o ulteriori probe. Attesa nuovo hash per review finale.

PR18 già pubblicata https://github.com/RisorseArtificiali/pyteman/pull/18, commitfde31767f4bd396eb7780017fe2d108148fa1ca1; utente chiede retry. Controllo prima di ripetere: CI35529701775 failure SOLO Python3.11, suite1failed1167passed9skip remoti. Test tests/test_matrix_results.py494 usa nest(2000) e pretende done; json.dumps3.11 fallisce RecursionError, risultato failed corretto per serializzazione impossibile. Matrice3.12/3.13/3.14 success, artifact/coverage skipped. Nessun merge.
Assegnato delta minimo test-only a implementer in copia da commitPR: separare walker iterativo deep da end-to-end su profondità verificata serializzabile, invalid-key contrast; no skip3.11 o recursionlimit tuning, no runtime/definitions/CI change. Reviewer persistente attende delta con prove3.11+3.14 e mutazione necessaria. Non rilanciata CI identica perché failure deterministico di assunzione test, non outage.

Delta CI05621a2cad1e18eb35b0c8a603b71f1665135fa4de02191e5af0de9d5d5c77d7 APPROVED dal reviewer persistente su Python3.11 e3.14, con mutanti mirati eseguiti sul nuovo artifact. Applicato solo tests/test_matrix_results.py dopo backup, confronto byte-exact con export indipendente e nessun diff runtime. Suite shared3.14:1176 passed2skip previsti; log ~/pyteman-evidence/task66-ci-integration-20260920-222359/shared-suite.log.
Commit aggiuntivo6dd245556d5fb7815b7f2c9d78b8170fe8d9353d pushato sul branch PR18 senza rebase. CI nuova35536320812 in corso; run vecchio35529701775 resta failure documentata, non cancellata. Nessun merge finché nuova CI non conclude success.

PR18 MERGED7286f690639344c9bcdac9ec724e5b69bdccc0e6 dopo commit aggiuntivo6dd245556d5fb7815b7f2c9d78b8170fe8d9353d e CI35536320812 sei job success, inclusa3.11 prima fallita. Review/commenti/discussion vuoti al controllo finale. Suite independent/shared1176pass2skip; runtime invariato dal candidato4fc1082f, delta test05621a2c APPROVED con prove3.11/3.14 e mutanti. Primo run fallito resta documentato e non attribuito a flake.
Tutti AC verificati e consegna pubblicata. Done respinto dal hook per gate delegati non riconosciuti nel transcript coordinator. Nessun bypass/retry identico, tracker In Progress amministrativo. Prove finale ~/pyteman-evidence/task66-ci-integration-20260920-222359/ e verdetto ~/pyteman-evidence/t66/VERDICT-TASK66-CI-DELTA.md.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed 2026-09-25 by backlog audit. PR#18 merged as commit fde3176 (reject non-string keys in callback results), CI green. Administratively stuck In Progress. Code published in v0.2.0.
<!-- SECTION:FINAL_SUMMARY:END -->
