---
id: TASK-26
title: >-
  EX-01. Sostituire l'inferenza temporale del caso #109966 con un handshake
  verificato
status: Done
assignee: []
created_date: '2026-09-16 12:20'
updated_date: '2026-09-27 22:59'
labels:
  - audit-2026-09-16
  - opus-5
  - ex
  - confirmed
milestone: m-4
dependencies:
  - TASK-15
references:
  - 'examples/hermes-109966/restarter.py:33-41'
  - 'examples/hermes-109966/run_repro.py:118-146'
  - 'examples/hermes-109966/README.md:45-46'
documentation:
  - doc-1
  - doc-2
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P1, CONFIRMED, aperto.

**File:** `examples/hermes-109966/restarter.py:33-41`, `run_repro.py:118-146`, `README.md:45-46`, `rules-hold-write-window.yaml:9-13` nella stessa directory.

**Evidenza:** in `restarter.main`, simulando zero firing e un orologio oltre il timeout, il sibling esegue comunque `open`, `write`, `close`. Con tutti i record già presenti prima della partenza esegue immediatamente tutti i cicli. Il driver controlla il totale dei firing, non che ogni close preceda la fine della corrispondente pausa. Il record dimostra l'inizio del fault, non la contemporaneità del close.

**Impatto:** scheduler lento o startup costoso possono trasformare una prova concorrente in sequenziale mantenendo un risultato accettabile. Il README promette una garanzia non imposta dal codice.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 test con firing assente, log già completo, sibling ritardato oltre la finestra e ciclo corretto.
- [x] #2 Solo l'ultimo prova la coreografia; gli altri falliscono senza effettuare un close fuori finestra presentato come valido.
- [x] #3 Documentazione aggiornata al protocollo reale.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Proposta iniziale da verificare sul codice corrente, non una correzione già applicata.

timeout esplicito come errore; handshake interprocesso per ogni finestra, con acknowledgement del close prima del rilascio. Se si mantiene un timeout di sicurezza, il suo scadere produce INCONCLUSIVE, mai CLEAN. Non basta allungare lo sleep.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: contratto dei record M3; eventuale handshake specifico dell'esempio non richiede un nuovo backend pubblico di barriere.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.

IMPLEMENTAZIONE (2026-09-28, PR #176, head 3e20a5d): riprodotto prima (log completo, niente holder: tre close in 0.10s, exit 0, esattamente l'evidenza dell'audit), poi il protocollo: il firing log porta ENTRAMBI i bordi di ogni finestra (record phase:start scritto dal sleep prima di stallare, phase:end scritto al rilascio, entrambi con monotonic_ns), quindi l'handshake e' il log stesso. Ogni ciclo: attende start(i), rifiuta se end(i) e' gia' su disco (exit 3, NESSUNA close eseguita), rifiuta se la finestra non apre entro il budget (exit 2), poi open/write/close, ri-legge e prova che end(i) non ha preceduto la close (confronto monotonic跨-processo, ora documentato come eccezione deliberata sia in firing.py sia in docs/firing.md). Il driver mappa exit non-zero su INCONCLUSIVE mai CLEAN; il conteggio totale e' degradato a what it can honestly say (harness fault). Quattro test col modulo restarter reale su log sintetici (dead log rifiuta prima di ogni close; finestra mai aperta scade come errore; finestra viva chiude e stampa la prova; end che ha battuto la close rifiuta a meta' ciclo). README e commento del driver aggiornati al protocollo reale.

GATE (2026-09-28): /simplify combinato (1 finding medium: l'affidamento cross-process su monotonic_ns reso LOUDO dove vive il contratto, in firing.py e docs/firing.md, perche' il docstring del produttore lo vietava; plus S1 pop morto, S2 docstring/discard, R1/S3/R2 judged noise o polish) APPLICATO; belt high CHANGES-REQUIRED con 1 finding Important (firing.md alle righe 18 e 154 ancora vietava cio' che firing.py ora permette: allineato con l'eccezione in entrambi i punti + blocco output di esempio nel README aggiornato alle righe per-ciclo) APPLICATO; nota di solidita' PLAUSIBLE non bloccante (visibilita' del record end nel microsecondo fra stamp e write: finestra irraggiungibile nella coreografia spedita, pre-check presence-based airtight la prende). Belt ha anche ESEGUITO il driver completo due volte contro il tip verificato 2cfb655d52 del repo hermes (VERDICT: CLEAN entrambe, tutte e tre le finestre), e la riproduzione pre-fix (0.10s, exit 0) e post-fix (exit 3, zero close). Mutazioni che uccidono: pre-close check cancellato (il test dead-log fallisce sull'assertione CLOSES==[], la discriminante giusta), post-close comparison disattivato (il test mid-cycle fallisce con DID NOT RAISE e il codice mutato stampa la close fuori finestra come valida: esattamente la falsa prova che il check previene). Batteria 1344 passed 2 skipped.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Chiuso con il merge 623933d (PR #176, squash di 3e20a5d su master fc7f934). Riprodotta l'evidenza dell'audit prima della correzione (log completo, niente holder: tre close in 0.10s, exit 0) e poi sostituita l'inferenza temporale con un handshake verificato che vive nel firing log stesso: ogni ciclo attende lo start della propria finestra, rifiuta di chiudere se l'end e' gia' su disco (exit 3, nessuna close eseguita), rifiuta se la finestra non apre (exit 2), e dopo la close ri-legge e prova che l'end non l'ha preceduta. Il driver mappa le uscite non-zero su INCONCLUSIVE mai CLEAN; il conteggio totale resta solo come harness-fault check. AC1: quattro test (dead log senza close; timeout come errore; finestra viva con prova stampata; end che batte la close rifiutata a meta' ciclo). AC2: la mutazione che disattiva il post-close comparison fallisce per DID NOT RAISE mentre il codice mutato stamperebbe la close fuori finestra come valida: la falsa prova e' prevenuta. AC3: README, commento del driver, firing.py e docs/firing.md allineati al protocollo reale, inclusa l'eccezione cross-process su monotonic_ns resa esplicita dove vive il contratto. Gate: /simplify 1 medium + 2 minor applicati; belt high CHANGES-REQUIRED (firing.md vietava cioe' che il codice fa) applicato e riprovato, piu' il driver completo eseguito due volte contro il tip hermes verificato (CLEAN entrambe) e la riproduzione pre/post-fix; revisione indipendente APPROVED a 3e20a5d con due finding informativi (wording dell'absence-proof, IndexError fail-safe) registrati nel verdetto; CI verde 7 check; batteria 1344 passed 2 skipped.
<!-- SECTION:FINAL_SUMMARY:END -->
