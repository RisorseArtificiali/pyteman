---
id: TASK-29
title: EX-04. Distinguere i guasti generici del holder dalle firme dell'incidente
status: Done
assignee: []
created_date: '2026-09-16 12:20'
updated_date: '2026-09-28 03:13'
labels:
  - audit-2026-09-16
  - opus-5
  - ex
  - confirmed
milestone: m-4
dependencies: []
references:
  - 'examples/hermes-109966/holder.py:25-30'
  - 'examples/hermes-109966/run_repro.py:149-176'
documentation:
  - doc-1
  - doc-2
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P1, CONFIRMED nel flusso del codice, aperto.

**File:** `examples/hermes-109966/holder.py:25-30`, `run_repro.py:149-176`.

**Evidenza:** qualunque `Exception` nell'append produce `holder.failed`; il driver attribuisce quel flag a REPRODUCED. Un errore estraneo alla generazione WAL viene quindi classificato come incidente se raggiunge il verdetto. Se l'errore precede il primo heartbeat, le letture non protette possono invece terminare con `FileNotFoundError` senza verdetto.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 append che solleva un errore generico, rifiuto WAL riconosciuto, holder morto prima del heartbeat e heartbeat parzialmente scritto.
- [x] #2 Verdetti distinti e sempre accompagnati da motivo diagnostico.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Proposta iniziale da verificare sul codice corrente, non una correzione già applicata.

evidenza strutturata del holder con tipo di errore e fase; classificare solo firme esplicite come REPRODUCED e i fault del test come INCONCLUSIVE. Gestire heartbeat assente, vuoto e non leggibile. Pubblicare heartbeat atomicamente, non tramite truncate/write osservabile a metà.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: nessuna.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Chiuso con il merge 0cc34c8 (PR #179, squash di 36dcc0a su master feaded9). Riprodotte entrambe le gambe dell'audit prima del fix con stub steering: un fault generico nell'append (RuntimeError disk-full) veniva classificato REPRODUCED, e un holder morto prima del primo heartbeat terminava il driver con traceback e NESSUN verdetto. Fix: holder.py scrive evidenza strutturata JSON (phase/error_type/error_repr/tick), pubblica heartbeat e marker atomicamente (tmp+os.replace) e scrive un heartbeat baseline prima del primo append; run_repro.py guadagna _read_heartbeat (assente/vuoto/illeggibile, inclusi byte non decodificabili -> (None, motivo)) e _holder_failure (solo la WAL-generation refusal alimenta REPRODUCED, SUBCLASS-AWARE per risoluzione del nome contro l'hermes_state del driver; JSON non-oggetto e non parsabile sono fault nominati), il verdetto stampa SEMPRE con una riga REASON: separata (token VERDICT: stabile per il grep CI), e la lista faults si costruisce prima del ramo che la consuma. Sei test (tre gambe end-to-end: generico -> INCONCLUSIVE col tipo nominato, wal -> REPRODUCED con la firma, before -> INCONCLUSIVE dal heartbeat baseline; pin del classificatore su cinque forme incluso subclass e non-oggetto; pin dei quattro stati dell'heartbeat). Gate: /simplify 4 angoli (agente combinato, 4 finding applicati e verificati nei byte del merge 0cc34c8 per grep: riuso di _run col timeout, stub morto, faults prima del ramo, loader spec-based); belt CHANGES-REQUIRED con 3 guardie strette quanto le proprie promesse (AttributeError su JSON non-oggetto, UnicodeDecodeError sui byte, disaccordo delle due porte sui subclass) APPLICATE e pinnate; revisione indipendente APPROVED a 36dcc0a con 2 finding non bloccanti registrati su TASK-187 (error_type non-stringa: introdotto dal diff, parita' di robustezza; sys.modules senza restore nei test: igiene); belt ha anche verificato l'atomicita' con 5922 letture concorrenti senza troncamenti. CI verde 7 check sullo stesso head; batteria 1363 passed 2 skipped; mutazioni che uccidono (ramo WAL, risoluzione subclass, guardia non-oggetto, guardia absent, esistenza del flag come REPRODUCED: il difetto originale).
<!-- SECTION:FINAL_SUMMARY:END -->
