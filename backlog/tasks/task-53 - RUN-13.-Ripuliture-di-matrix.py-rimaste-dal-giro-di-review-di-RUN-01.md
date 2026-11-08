---
id: TASK-53
title: RUN-13. Ripuliture di matrix.py rimaste dal giro di review di RUN-01
status: Done
assignee: []
created_date: '2026-09-16 16:22'
updated_date: '2026-11-08 09:53'
labels:
  - runner
  - refactor
  - simplify
  - review-followup
  - audit-2026-09-16
milestone: m-3
dependencies: []
references:
  - src/pyteman/runner/matrix.py
  - 'TASK-19 (RUN-01): origine'
  - 'TASK-42 (RUN-06): sovrapposizione sul punto 5'
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Raccolta degli esiti del passaggio `/simplify` sullo stato finale di RUN-01 (TASK-19), 2026-09-16, piu i due elementi sotto soglia della review Efficiency dello stesso giro. Nessuno e un difetto: il comportamento e corretto e coperto. Nessuno e stato applicato perche lo stato di TASK-19 era congelato e gia verificato dall'orchestrator quando le review sono rientrate, e una modifica anche cosmetica dopo l'approvazione avrebbe invalidato quella verifica in silenzio.

1. `_RESULT_COLUMNS` promette una sola sede per i nomi di colonna, ma gli stessi sette nomi sono riscritti in `_create_results`, nella DDL di `results_superseded`, posizionalmente nella SELECT di migrazione, e la loro arita ancora in `"VALUES (?,?,?,?,?,?,?)"`. Aggiungere una colonna significa toccare cinque punti; mancare la DDL dell'archivio fa fallire a runtime l'INSERT..SELECT di `_archive`, cioe proprio il modo di fallire che la costante esiste per chiudere. Due dei cinque sono pure riscritture eliminabili: la tabella d'archivio non ha vincoli, quindi accetta `f"CREATE TABLE IF NOT EXISTS results_superseded({_RESULT_COLUMN_LIST}, reason TEXT, superseded_at REAL)"` perche SQLite ammette colonne senza tipo, e i segnaposto diventano `",".join("?" * len(_RESULT_COLUMNS))`. Restano `_create_results`, che ha bisogno dei tipi e della primary key, e la SELECT di migrazione, che ha bisogno dei NULL letterali: quelle due sono legittime.

2. Il flag `legacy` e stato derivato e propagato: calcolato in `_plan` come `stored_fingerprint is None`, passato a `_conflict` accanto a `stored_fingerprint` da cui si ricava, e poi conservato per conflitto in tuple `(text, legacy)` che obbligano a spacchettare in entrambi i consumatori. Il flag per elemento non e mai letto per elemento: `any(legacy for _, legacy in conflicts)` lo collassa subito. Forma piu semplice: `_conflict` testa `stored_fingerprint is None` da se, `conflicts` torna a essere una lista di stringhe, e il ciclo accumula un `legacy_conflict` booleano.

3. Il paragrafo finale del docstring di `run_matrix` ripete la regola sullo stratum non namespacizzato gia enunciata due volte piu in alto nello stesso file, e in forma quasi identica nel commento a `_LEGACY_EXPERIMENT`. Tre copie di una regola in un file: chi la cambia deve trovarle tutte e chi ne nota una discrepanza non puo sapere quale sia autorevole.

4. Il docstring di `_remedies` spiega, per il manutentore, esattamente cio che il messaggio prodotto quattro righe dopo dice all'utente. La copia che nessun test controlla e il docstring.

5. `_stored_version` restituisce un valore usato solo per `if stored_version != SCHEMA_VERSION`. L'istruzione protetta e una INSERT OR REPLACE idempotente dentro una transazione che committa comunque, quindi la guardia evita una scrittura di riga e nessuna semantica. Il lavoro vero di quella funzione sono i due rifiuti che alza. Nota di coordinamento: TASK-42 riscrive questa zona estraendo il versioning in sqlitekit, quindi questo punto va fatto li o non fatto affatto.

6. `_LEGACY_POLICIES` respella i membri di `_MISMATCH_POLICIES`: le due tuple stanno in relazione (legacy accetta tutto cio che accetta mismatch, piu l'adozione) e la relazione e invisibile alla definizione.

Sotto soglia, dalla review Efficiency, che sull'angolo proprio ha dichiarato il diff pulito senza rilievi classificabili:

7. `_experiment_dir(experiment_key)` e valutata una volta per cella dentro `_attempt_dir`, rifacendo SHA-256 sulla stessa chiave costante per tutta la run. Costo nell'ordine del microsecondo per cella, quindi non un rilievo; segnalato solo perche la correzione e gratuita (calcolare la directory accanto a `experiment_key` in `run_matrix` e passarla) e toglie il rischio che l'hoist venga dimenticato se le identita di esperimento crescono.

8. `_lookup` seleziona `cell_json` per ogni cella ma lo usa solo sul percorso di rifiuto, attraverso `_changed_keys` raggiunta solo da `_conflict`. La definizione memorizzata viene quindi letta e materializzata in Python per ogni cella del piano e scartata per tutte quelle che non confliggono. Lo spreco scala con la dimensione delle definizioni invece che con una costante per cella, ma resta nei millisecondi contro celle che durano secondi. Forma piu economica: `SELECT fingerprint, status` in `_lookup`, piu una seconda SELECT mirata di `cell_json` per le sole celle finite in `conflicts`, che sono limitate dalla dimensione di un messaggio d'errore.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 La DDL di results_superseded e l'elenco di segnaposto dell'INSERT non respellano piu i nomi e l'arita delle colonne: entrambi derivano da _RESULT_COLUMNS
- [x] #2 _LEGACY_POLICIES e espresso come estensione di _MISMATCH_POLICIES invece che come letterale indipendente
- [x] #3 Il flag legacy non e piu propagato per elemento in una lista di tuple che viene subito collassata da any(): _conflict lo ricava da stored_fingerprint e il chiamante accumula un solo booleano
- [x] #4 _stored_version non restituisce piu un valore usato solo per saltare una INSERT OR REPLACE idempotente dentro una transazione che committa comunque
- [x] #5 Le tre copie della regola sullo stratum non namespacizzato nel docstring di run_matrix, nel commento a _LEGACY_EXPERIMENT e nel docstring di _remedies sono ridotte a una sola sede autorevole
- [x] #6 Comportamento osservabile invariato: 51 test dei file di competenza e suite completa verdi, batteria di mutazione senza sopravvissuti nuovi
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Giro /simplify del 2026-09-16 sul candidato B2 (runner matrix + report, otto file), eseguito READ-ONLY con quattro reviewer indipendenti. Verdetto bug: nessuno, da quattro passaggi indipendenti. Un solo difetto fattuale trovato e corretto nel candidato prima del commit: il docstring di _check_duplicate_ids affermava che rules.py applica la stessa regola di unicita ai propri id, cosa falsa (rules.py pretende la CHIAVE id fra le chiavi obbligatorie e non confronta mai gli id fra regole, verificato da me nel sorgente). Tutte le altre proposte estetiche e di efficienza sono SCARTATE per questa tranche per decisione dell'orchestrator: non sono pendenze implementative, e questa nota e la loro unica registrazione richiesta. Nessun task nuovo aperto.

Gia coperti altrove, quindi qui solo rinvio e non duplicazione: la triplicazione dei nomi di colonna dei results e il punto 1 di questo stesso task; il flag legacy derivabile e il punto 2 con la sua AC#3; l'estrazione di versioning e migrazione e TASK-42; la base comune delle eccezioni e TASK-43 con TASK-60; l'helper condiviso per le query sqlite nei test e TASK-45; le duplicazioni nei test nuovi di RUN-01 sono TASK-54; body_rows definita due volte e TASK-78.

Rilievi su codice di produzione non ancora scritti altrove. Primo: in _plan la variabile source e assegnata prima della lookup legacy, quindi sul percorso senza riga memorizzata non descrive piu nulla, e il codice quattro righe sotto deve scrivere experiment_key con un commento che spiega perche. Il comportamento e corretto oggi ed e fissato da un test; il rilievo e che la modifica che un manutentore farebbe per uniformita reintroduce proprio il difetto che quel test esiste per prendere, quindi la correttezza poggia su un commento invece che sulla struttura. Secondo: cell_definition e pubblica ma non ha utilizzatori fuori dal proprio modulo, ne test ne riga di README, quindi e una promessa di compatibilita che nessuno verifica. Terzo: nulla impedisce strutturalmente che una colonna futura venga concatenata grezza nella f-string di riga a report.py:199, e il test che lo prenderebbe usa una tupla di colonne mantenuta a mano; rimedio suggerito un punto di strozzatura unico per il rendering di riga. Quarto: la nozione di provenienza sconosciuta e scritta come SQL fingerprint IS NULL, come stored_fingerprint is None, e di nuovo in report.py; la raccomandazione era unificare le due sedi dentro matrix.py e lasciare report.py indipendente, cosi resta capace di rendere un database estraneo senza importare il runner.

Considerato e RESPINTO, non pendente: la doppia lettura di PRAGMA table_info sul percorso di migrazione. Entrambi i reviewer che l'hanno sollevata hanno raccomandato di non toccarla, perche la rilettura e cio che rende la migrazione autosufficiente e costa microsecondi una volta per run.

Dettaglio dei rilievi sui test e sull'efficienza dello stesso giro, tenuto qui per non moltiplicare le sedi. Appartiene per materia a TASK-54 e va letto quando quel task viene lavorato; nessuna AC di TASK-54 e stata toccata.

Test. body_rows e definita carattere per carattere in test_report.py e in test_report_escaping.py, ciascuna con una propria formulazione dello stesso argomento su split rispetto a splitlines (gia TASK-78). test_report.py costruisce un results database inline cinque volte, tre delle quali con una CREATE identica, mentre legacy_db in test_matrix_identity.py e _signature_db in test_report_escaping.py fanno gia quel lavoro. AVVERTENZA che chiunque fattorizzi deve conoscere: la variante tipizzata e quella non tipizzata NON sono intercambiabili, perche due test dipendono dall'affinita BLOB, quindi un builder condiviso ha bisogno di un flag di affinita e una fusione ingenua romperebbe quei due test. La comprehension che estrae la colonna N di ogni riga del corpo indicizzata per cell id compare cinque volte, due delle quali identiche, con gli indici di colonna scritti a mano in ogni sito. unescaped_pipes e inlinata in test_report.py senza la motivazione che l'helper con nome in test_report_escaping.py porta con se. Un test in test_matrix_identity.py riscrive a mano lo scrittore di artefatti che evidence_writer fornisce e che cinque test fratelli usano. L'helper di sola lettura query ha tre copie ad hoc, ma la sua sede naturale e tests/conftest.py, che sta fuori dagli otto file di questa tranche.

Efficienza, un solo rilievo, a report.py:199. L'etichetta di esperimento viene ricalcolata e riescapata per ogni riga benche _read restituisca le righe ordinate per esperimento, quindi righe consecutive condividono la coppia (experiment, fingerprint). Un memo dict locale alla chiamata ha dato, misurato end to end, 50 per cento a 500 e a 2000 righe e 39 per cento a 10000 righe, con output identico byte per byte a ogni dimensione; in assoluto si tratta di decine di millisecondi. Queste sono misure del reviewer, non riprodotte da me, e vanno riverificate prima di agire. Entrambe le funzioni coinvolte sono pure e la tabella di escape e stato di modulo immutabile costruito una volta all'import, quindi il memo non cede alcuna garanzia e non puo diventare stale. Sullo stesso angolo tutto il resto e risultato pulito: nessuna regex compilata per riga, nessuna connessione aperta dentro un ciclo, una sola coppia di realpath per run, nessuna closure che catturi piu di quanto usa.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by direct push 0613029 on master (base 64210b9); PR #99 closed with a pointer. AC1: the archive DDL interpolates _RESULT_COLUMN_DECLS and the INSERT uses _RESULT_PLACEHOLDERS, both derived from _RESULT_COLUMNS; a fresh database's declared schema is byte-identical to master's (skeptic proof: PRAGMA table_info plus sqlite_master DDL diff empty), an improvement on both this branch's bare-name form and the task's own suggestion, which would have created untyped columns. AC2: _LEGACY_POLICIES = _MISMATCH_POLICIES + ("adopt",), with the validation message byte-identical to master's (executed on both sides). AC3: _conflict derives the legacy predicate from stored_fingerprint is None and _plan accumulates one legacy_conflict boolean; rendered refusal messages are byte-identical to master across mismatch, legacy and mixed scenarios (skeptic, side by side), and both rewiring directions were mutation-proven (inverted accumulation and flipped _conflict each redden their carriers). AC4: moot by the TASK-42 extraction, with evidence: src/pyteman/sqlitekit/versioning.py has stored_version feed the newer-version refusal and the setup gating, and no seat returns a value used only to skip an idempotent stamp. AC5: the run_matrix paragraph is gone and _remedies points at _LEGACY_EXPERIMENT, the single authoritative seat. AC6: full suite green at every round; battery green at the shipping hash (1606 collected, 1603 passed, 3 declared skips); both reviewers' discriminating mutations reddened their carriers, no survivors. The pure-mismatch remedies branch the rewiring left unpinned is now asserted by test_a_pure_mismatch_still_offers_a_new_experiment. Gate chain: /simplify (ALT applied, one skip with reason), /code-review high two rounds plus clean final verification with live injection probes, skeptic 6/6 CONFIRMED. Non-blocking note from the final review, recorded here: the family walk's docstring says "at any depth" while pkgutil.iter_modules is non-recursive; true for the package's three flat modules today, worth a word if the runner ever grows a subpackage.
<!-- SECTION:FINAL_SUMMARY:END -->
