---
id: TASK-61
title: >-
  Il blocco di persistenza guardato in run_matrix andrebbe estratto in una
  funzione con nome
status: Done
assignee: []
created_date: '2026-09-16 18:04'
updated_date: '2026-09-25 17:58'
labels:
  - audit-2026-09-16
  - run
  - spun-off
milestone: m-3
dependencies:
  - TASK-21
references:
  - src/pyteman/runner/matrix.py
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Scorporato da TASK-21 (RUN-03) il 2026-09-16, nel turno in cui la review di semplificazione lo ha segnalato, per non lasciare la frase "merita un task a se" senza il task corrispondente.

**Stato.** RUN-03 ha avvolto il blocco di persistenza di `run_matrix` in un `try/except sqlite3.Error` che solleva `MatrixStorageError`. Il blocco guardato e lungo circa trenta righe e contiene la chiamata a `_archive`, la INSERT nella tabella `results`, la DELETE dello stratum legacy e il commit, ciascuna con il proprio commento esplicativo di RUN-01 e RUN-02.

**Il costo segnalato.** L'estensione della regione guardata si deduce solo dall'indentazione. Ogni riga che verra aggiunta dentro quel blocco eredita in silenzio il contratto "un fallimento qui e un fallimento di persistenza e ferma il run", senza che nulla lo dichiari nel punto in cui si scrive. Una funzione con un nome, chiamata dentro un `try` corto, direbbe dove finisce la regione e cosa significa starci dentro.

**Perche non in RUN-03.** Il dispatch del turno esclude esplicitamente l'estrazione di helper e qualunque refactor. L'estrazione non corregge un difetto: il comportamento attuale e corretto e coperto dai test, quindi e un miglioramento di leggibilita che non ha motivo di viaggiare insieme a una correzione di contratto.

**Avvertenza per chi lo prende.** La funzione estratta avrebbe bisogno di parecchi parametri (connessione, step, chiave esperimento, status, result_json, directory degli artefatti, percorso del db), e se il numero di argomenti rende la chiamata meno leggibile del blocco che sostituisce, la conclusione corretta e chiudere questo task come non fatto con quella motivazione, non forzare l'estrazione.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Il corpo del ciclo di run_matrix non contiene piu un blocco guardato di trenta righe la cui estensione va dedotta dall'indentazione
- [x] #2 Il confine fra cio che e coperto dalla guardia di persistenza e cio che non lo e resta identico in comportamento, verificato dai test di TASK-21 che devono passare invariati
- [x] #3 La modifica non cambia alcun messaggio di errore osservabile
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Already done by commit a672d3c (TASK-64, oversized outcome fallback). That commit extracted the persistence block (archive, INSERT, DELETE, attempt UPDATE, commit) into `_finalise()`, called at line 1156. The loop body now has a 3-line function call instead of the ~30-line inline block. All error messages and the behavior boundary are preserved. No additional changes needed.
<!-- SECTION:FINAL_SUMMARY:END -->
