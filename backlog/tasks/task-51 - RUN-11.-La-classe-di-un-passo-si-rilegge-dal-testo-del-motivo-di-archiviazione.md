---
id: TASK-51
title: RUN-11. La classe di un passo si rilegge dal testo del motivo di archiviazione
status: Done
assignee: []
created_date: '2026-09-16 16:07'
updated_date: '2026-09-27 08:12'
labels:
  - runner
  - refactor
  - simplify
milestone: m-3
dependencies: []
references:
  - 'src/pyteman/runner/matrix.py:418'
  - 'src/pyteman/runner/matrix.py:470'
  - 'src/pyteman/runner/matrix.py:575'
  - 'src/pyteman/runner/matrix.py:603'
  - 'TASK-19 (RUN-01): correzione di origine'
  - >-
    backlog/archive/tasks/task-51 - sitecustomize... (omonimo archiviato,
    duplicato di RT-01, non correlato)
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`_plan` assegna gia la classe di ogni passo, ma due punti di `matrix.py` la ri-derivano dalla stringa del motivo invece che dal campo `action`.

`_adopt_stored_rows` filtra con `step.archive != "adopted"` e il ciclo di esecuzione archivia con `step.archive is not None`. I due filtri devono restare esattamente complementari e nulla nella struttura lo impone: un quarto motivo aggiunto a `_plan` cadrebbe attraverso il primo filtro e verrebbe archiviato dal ciclo come una normale supersessione, cioe nella transazione sbagliata. Il valore passato ad `_archive` dentro `_adopt_stored_rows` e inoltre dimostrabilmente la costante `"adopted"`, scritta li come se fosse una variabile.

Oggi l'accoppiamento e innocuo: i tre motivi esistenti (`adopted`, `legacy`, `mismatch`) nascono tutti dentro dieci righe di `_plan`. Il rischio e di manutenzione, non di comportamento, e per questo la correzione non e stata inclusa in TASK-19, il cui perimetro era la correzione minima del difetto di archiviazione.

Forma piu semplice proposta dal simplifier: far emettere a `_plan` un passo `_Step(cell, "adopt", None, source)`, filtrare su `step.action != "adopt"`, scrivere la costante nell'unico punto che la produce, e allargare il ramo `if step.action == "skip"` del ciclo a `if step.action != "run"` perche un'adozione continui a riportarsi come `skipped`.

Origine: finding 1 e 1b del passaggio `/simplify` su TASK-19.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 La classe di un passo si legge da `_Step.action` e non dal testo del motivo di archiviazione, in entrambi i punti
- [x] #2 Aggiungere un quarto motivo di archiviazione a `_plan` non puo far archiviare un passo nella transazione sbagliata senza che un test lo riveli
- [x] #3 Il motivo `"adopted"` compare come costante nel solo punto che lo produce
- [x] #4 Un'adozione continua a riportarsi con stato `skipped` nel risultato di `run_matrix`
- [ ] #5 La mutazione M24 della batteria resta ancorata e continua a essere uccisa dai due test di interruzione
- [ ] #6 L'intera suite resta verde
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-09-16, avvertenza di identita: l'id TASK-51 e riusato. La CLI lo ha riassegnato a questo task (RUN-11) alle 16:07, dopo che alle 16:00 era stato archiviato un task omonimo per numero ma non per contenuto, `sitecustomize: un ruleset invalido non ferma il run, il workload gira non strumentato e esce 0`, che era un duplicato di RT-01 (TASK-1, fallimento chiuso e atomico dell'attivazione). Quel file resta in `backlog/archive/tasks/` e non va toccato. Ogni riferimento a TASK-51 in commit, note o messaggi deve quindi nominare anche il prefisso: TASK-51 senza qualificazione e ambiguo fra RUN-11 e l'archiviato. In questo tracker TASK-51 significa RUN-11.

Origine: questo task nasce dal passaggio `/simplify` sul round finale di TASK-19 (RUN-01), che ha spostato `_archive` nella transazione del rimpiazzo; l'accoppiamento fra i due filtri complementari e stato introdotto da quella correzione. Milestone corretta da un titolo inglese, che creava una milestone distinta senza file, all'id nativo m-3.

2026-09-16, review Altitude sullo stato finale di RUN-01. Il perimetro di questo task e' piu' stretto del problema. Era formulato come un solo confronto con la stringa letterale "adopted" in _adopt_stored_rows; la review ne trova tre codifiche implicite della stessa nozione, non una.

1. `step.archive != "adopted"` in _adopt_stored_rows (~riga 472): la codifica gia' descritta qui.
2. `step.archive is not None` nel run loop (~riga 603): decide se archiviare.
3. `step.source != experiment_key` nel run loop (~riga 621): decide se drenare la riga di origine. Questa NON era coperta. Il suo stesso commento ammette la dipendenza ("This guard is narrower than the archive's above rather than independent of it: a source differing from the run's own key can only have come from the legacy lookup"): quella frase e' l'invariante che rende corretto il codice, e vive solo come prosa.

Inoltre il test `status == "done"`, che decide se una riga memorizzata sia evidenza o no, e' scritto tre volte dentro _plan (~righe 400, 406, 412) con accoppiamenti leggermente diversi ogni volta.

Conseguenza operativa: correggere soltanto il letterale "adopted" lascia in piedi le altre due derivazioni, quindi non chiude la classe di difetti. Il costo e' che aggiungere una policy o una classe di riga obbliga a toccare _plan, _remedies, _adopt_stored_rows e i due rami del run loop, senza che nulla fallisca se ne manca uno: l'omissione compila pulita e si manifesta come riga orfana o voce di archivio persa.

Cambio piu' profondo proposto dalla review: portare la classe sul passo, `_Step(cell, kind, ...)` con kind fra fresh, resume, retry, adopt, supersede_mismatch, supersede_legacy, e derivare action, il testo del motivo di archiviazione e il "drena la riga di origine" da kind in una sola tabella. _plan conterrebbe la decisione e nessun altro punto ne conterrebbe un pezzo.

Seconda review dello stesso giro, sull'asimmetria fra adozione e supersessione. Verdetto: principiata a livello di invariante, caso speciale a livello di implementazione. L'invariante unico e' che la riga di archivio si scrive nella stessa transazione della scrittura che rende vera la supersessione; per l'adozione quella scrittura e' l'UPDATE, per la supersessione e' l'INSERT OR REPLACE, che non puo' avvenire prima che la cella abbia girato. Non sono due regole ma una regola applicata in due momenti, perche' la scrittura che fa verita' accade in due momenti. Quella regola pero' non compare da nessuna parte nel codice: e' enunciata in prosa due volte ed e' fatta rispettare da tre letterali che cooperano fra due funzioni e che, per proprieta' non dichiarata, partizionano lo spazio dei passi. Cambio proposto: un solo helper `_commit_step(con, step, writes)` che archivia se il passo porta un motivo, poi esegue le scritture, poi committa, chiamato una volta dal percorso di adozione e una volta dal run loop. L'invariante esisterebbe in un punto solo e la divisione in fasi si ridurrebbe a un fatto sul kind.

Nessuna di queste modifiche e' stata applicata: lo stato di RUN-01 era congelato e gia' verificato dall'orchestrator al momento della review.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Merged as fbf9d7a via PR #157 (head 5ce335c). Gates: /simplify four-angle review clean with the consumer sweep exhaustive and one style nit applied (import style unified); code-reviewer-typed high review CLEAN with both mutations run (the text-filter restore fails the new test; the narrow-branch restore fails the existing adoption test), the unknown-class default probed fail-closed (reported skipped, nothing written, nothing run), and the editable-wheel cache trap caught and documented; battery check clean, 1265 passed 2 skipped; independent review APPROVED at 5ce335c with two info findings (a brief-side base-sha slip producing a phantom diff; the widened-branch default change recorded as the settled design); PR CI green; master CI green.
<!-- SECTION:FINAL_SUMMARY:END -->
