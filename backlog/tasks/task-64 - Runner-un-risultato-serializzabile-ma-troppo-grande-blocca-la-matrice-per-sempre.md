---
id: TASK-64
title: >-
  Runner: un risultato serializzabile ma troppo grande blocca la matrice per
  sempre
status: Done
assignee: []
created_date: '2026-09-16 18:22'
updated_date: '2026-09-21 16:48'
labels:
  - audit-2026-09-16
  - run
  - confirmed
  - from-code-review
milestone: m-3
dependencies:
  - TASK-21
references:
  - 'src/pyteman/runner/matrix.py:797'
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Trovato dalla code review high di RUN-03 (TASK-21), confidenza 82, riprodotto end-to-end dal reviewer. In RUN-03 il confine e stato **documentato** nel docstring di `run_matrix`, non cambiato: il cambio di comportamento e una decisione di contratto e non va presa dopo il gate di review senza verifica del parent.

**File:** `src/pyteman/runner/matrix.py:797` (la guardia `except sqlite3.Error`).

**Difetto:** `sqlite3.DataError` ("string or blob too big", alzato quando la riga supera `SQLITE_MAX_LENGTH`, default 1e9 byte) e sottoclasse di `sqlite3.Error`. Verificato direttamente: `issubclass(sqlite3.DataError, sqlite3.Error)` e True. Quindi un risultato perfettamente serializzabile ma troppo grande alza `MatrixStorageError` e ferma il run. Il database e sano; il contenuto della riga e la causa.

**Conseguenza peggiore del singolo fallimento:** poiche nessuna riga viene scritta, la cella e ripianificata come "run" a ogni invocazione successiva e fallisce identicamente, quindi ogni cella in coda dietro di lei resta irraggiungibile per sempre. Riproduzione del reviewer, con il limite abbassato via `setlimit` al posto del default di 1GB:

    attempt 1 MatrixStorageError: cell 'big' ran and finished done, but its row could not be written...
    attempt 2 MatrixStorageError: cell 'big' ran and finished done, but its row could not be written...
    cells run: ['big', 'big']        # 'later' non e mai partita, due volte
    rows: []

**La domanda di contratto:** RUN-03 ha tracciato la linea fra "un risultato che non serializza e colpa della cella, registrato" e "un db che rifiuta la riga non e colpa della cella, alzato". Una riga rifiutata *per cio che la cella ci ha messo dentro* cade dalla parte sbagliata di quella linea cosi come e scritta. Le due direzioni:

(a) catturare `sqlite3.DataError` separatamente e registrarla come fallimento della cella, coerente con il trattamento di un risultato non serializzabile. La riga failed che ne risulta e piccola, quindi la sua scrittura riesce.

(b) tenere il comportamento attuale e considerare sufficiente la documentazione gia aggiunta in RUN-03.

**Cautela per chi esegue:** `DataError` potrebbe in linea di principio arrivare anche da `cell_json` oltre che da `result_json`. Verificare quali valori della INSERT possono superare il limite prima di decidere che la diagnosi "colpa della cella" e sempre corretta.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Decisione esplicita fra registrare DataError come fallimento di cella e mantenere l'arresto, con la ragione scritta nel codice.
- [x] #2 Se si registra: la cella successiva parte e il run non si blocca sulle invocazioni seguenti, con test che usa setlimit per rendere il caso raggiungibile.
- [ ] #3 Se si mantiene l'arresto: il messaggio di MatrixStorageError distingue una riga rifiutata per dimensione da un guasto del supporto, perche il rimedio e diverso.
- [x] #4 Verificato quali colonne della INSERT possono superare SQLITE_MAX_LENGTH, non solo result_json.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Utente ha scelto esplicitamente 'Fallback verificato (Recommended)'. Implementare solo final-write SQLITE_TOOBIG riconosciuto tramite codice SQLite: rollback intera transazione, un singolo tentativo di finalizzazione con status failed e result JSON breve/bounded. Riutilizzare l'intera unità archive/results/legacy-delete/attempt-update/commit, non ritentare il callback. Continua solo se commit fallback riesce. Se fallback fallisce, rollback e MatrixStorageError con causa reale, nessuna row dichiarata scritta. Nessun fallback su begin-attempt o planning, nessun catch generico DataError o string matching.

Non diagnosticare esclusivamente result_json se limite riguarda riga composta: descrivere outcome non registrabile e sostituito con fallimento. Preservare storico precedente e atomicità attempts/results, dimensione metadata può impedire anche fallback. Test setlimit real basso per result grande/exception text grande, nextcell e retry, nonTOOBIG stop, fallback impossibile rollback, archive mismatch/legacy e attemptupdate. Nessuna prova1GB necessaria o promessa soglia universale. Scope matrix/test/docs, helper finalizzazione piccolo se necessario per non duplicare transazione, nessuno schema/framework. Base7286f69 copia isolata, simplify mirato e reviewer indipendente finale su hash.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
TASK98 non scelto perché scout conferma solo input sintetico già escluso, non difetto da output SQLite genuino. Si passa a TASK64 come caso funzionale più ampio già previsto qualora non emerga piccolo valido. Implementer incaricato solo assessment e prove in copia, no fix/cambi di contratto ancora. Prerequisito TASK21 Done già verificato negli scout runner.

Assessment peer su7286f69 in ~/pyteman-evidence/task64-assess-1789937269/probes: setlimit20000, oversized result finale provoca SQLITE_TOOBIG18 e due retry eseguono solo big, lasciando attempts running. Peer distingue cell_json oversized fallimento prima callback e errore callback oversized alla finalizzazione. Riga fallback con definizione oversized non scrivibile: claim originale 'failed è sempre piccola' non vale in generale. Risultati per ora attribuiti al peer, riproduzione coordinator in corso.
Finding adiacente registrato QUI senza perdita né nuovo task non verificato: experiment oversized causa DataError grezza in _lookup/_plan SELECT prima delle guardie storage; scout la riporta misurata, coordinator non ancora verificata. Non assorbire automaticamente nella correzione result payload; predisporre errore dimensione in fase pianificazione richiede verifica/decisione propria. Nessuna implementazione ancora approvata.

Conferma indipendente coordinator: due invocazioni run_matrix a limit20000 falliscono MatrixStorageError con causa DataError SQLITE_TOOBIG, calls=['big','big'], results=[], attempts running2; evidenza ~/pyteman-evidence/task64-coordinator-qxmfmwu9. Decisione utente raccolta via AskUserQuestion: fallback verificato. Autorizzata implementazione con rollback prima retry e solo commit fallback come condizione per continuare; nessun callback retry interno. Finding _plan DataError resta annotato ma non assorbito nella patch del finalwrite.

Checkpoint implementer1184/2skip non ancora candidato. Respinta claim 'fallback non scrivibile impossibile da run_matrix': begin-attempt scrive result_json e finished_at NULL, UPDATE finale accresce record; inoltre archive/trigger/limite connessione possono fallire senza writer concorrente. Test proposto chiamava _finalise due volte manualmente, quindi non copriva MatrixStorageError del secondo except del runner, conteggio retry o callback.
Richiesto test run_matrix reale con SQLite trigger o strumentazione connessione che esegue SQL vero: first TOO_BIG, fallback errore, arrivo ramo asserito, tentativo unico, rollback e attempts/result/history intatti, nextcell non invocata. Nessun allargamento runtime, solo prova del contratto già richiesto. Correggere distinzione SQLITE_LIMIT_LENGTH (string/blob/record) vs SQLITE_LIMIT_SQL_LENGTH (testo SQL); DDL sotto limite piccolo non dimostra che siano stesso limite. Review finale attende artefatto corretto.

2026-09-21: consegnato candidato immutabile task64-candidate-final.patch sha256 48be2bbe8cea1ad69f9457d1b49c6af119ff7aa1cc57d4b7f990babf6f75599d, base7286f69, tre file. Coordinator ha verificato hash e git apply --check, non ancora integrato. Manifest sha25691a13865e7120c54ac93c3b45c462514a7a4f3fd2cf65a85a79f8c43dad0af7f. Peer dichiara1186pass/2skip prima freeze e otto mutanti uccisi; conteggi da verificare indipendentemente. La copia frozen produce sette errori packaging per permessi preservati nelle copie; per prova usare export proprio scrivibile, non scongelare originale.

Triage report peer, nessuna osservazione persa. Nuova segnalazione NON ANCORA verificata coordinator: report.py:80 commento sostiene che DatabaseError escluda errori SELECT del lettore, ma peer osserva OperationalError/ProgrammingError sottoclassi DatabaseError; diagnosi file anziché errore del lettore. Fuori patch64, valutazione separata registrata qui. Carried: raw DataError _plan/_lookup già annotato; confronto extended sqlite_errorcode==18 potrebbe non cogliere futura variante inesistente oggi (non bug corrente); rollback rowcount guard _finalise preesistente senza test specifico; _OVERSIZED_OUTCOME dict mutabile; fallback causato dalla sola crescita attempts accettato e documentato dal peer, da controllare nella review.

Simplify sotto cap, tutti registrati con decisione preliminare di non allargare candidato: (1) JSON constant duplica informazione dict ma evita serializzazione in error path; (2) wrapping import cosmetico; (3) variabile step in range(40) migliorabile a probe/shrink; (4) parametro at terse per scratch directory; (5) return None esplicito ridondante ma coerente docstring; (6) due SELECT results consolidabili, lasciati separati per whole-mapping assertions. Non richiesti refactor cosmetici prima review finale; nessuna promessa implicita di futura implementazione.

Quattro cut items delta reviewer, tutti registrati: (1) frase 'no row for this cell can be written' sovraestende dalla rappresentazione runner alla minima teorica, da verificare in final review; (2) test access __cause__.sqlite_errorcode non guarded sicuro nel test; (3) marker in sql del test connector potrebbe collidere con un futuro INSERT OR REPLACE results_superseded oggi inesistente; (4) test code/class/text asserisce results non attempts, altri test coprono attempts. Sono segnalazioni peer, non bug confermati coordinator. Richiesto verdict finale indipendente e /code-review high su hash finale.

Review finale assegnata a pyteman-release-review nella sessione5aec9468 DOPO /clear effettivo verificato in terminale. Coordinator avvia suite indipendente su export scrivibile /home/pantinor/pyteman-evidence/task64-integration-1MXnd9rZ con venv nuovo e import/bytecode identity verificata. Git apply segnala blank line extra EOF nel nuovo test (whitespace, nessun fix al frozen). Ipotesi coordinator da verificare reviewer: secondo except cattura ogni sqlite.Error ma diagnostica sempre excess/metadata smaller, potenzialmente falsa se fallback fallisce SQLITE_FULL/constraint/lock. Assegnata riproduzione SQL reale al reviewer; non dichiarata confermata.

Verifica indipendente coordinator completata su candidato48be2bbe con Python3.14.7: 1186 passed, 2 skipped, pytest exit0; log /home/pantinor/pyteman-evidence/task64-integration-1MXnd9rZ/pytest-with-backend.log. Skip: percorso pre3.14 Placeholder e secondo renderer opzionale. Confronto byte-per-byte dei tre file dopo test contro frozen delivery riuscito. Primo run conservato in pytest.log: 1failed1178passed9skip per setuptools assente nel venv coordinator, confermato find_spec None; installato backend e rieseguita intera suite senza cambiare codice. Primo wrapper aveva erroneamente terminato0 pur con testfailed; rerun Python subprocess propaga returncode e stampa PYTEST_EXIT_CODE0. Review indipendente ancora in corso; nessuna approvazione o pubblicazione dedotta dalla suite.

Review finale NON APPROVATO su48be2bbe. Report /home/pantinor/pyteman-evidence/task64-review-opus5-1789986231/REVIEW-TASK64-opus5.md sha2565708039639fba2d94aea2b5e3f9d5dad056d4087c93a2788cbe3de567858274a. F1 medio, matrix1221-1241: dopo TOOBIG il secondo errore BUSY o CONSTRAINT_TRIGGER viene diagnosticato falsamente come size e richiede riduzione metadata; reviewer riproduce con SQL reale, no eccezioni iniettate. Correzione assegnata nel medesimo TASK64: messaggio secondo fallimento fedele al codice e test coppia TOOBIG/nonTOOBIG. F2 basso, docstring_finalise568: afferma impossibile decidere dopo rollback ma caller rollback prima decisione; correggere ragione ownership caller. Suite reviewer1186/2skip indipendente, integrità dati non contestata.

Triage finale sotto cap: blank EOF cosmetico verrà tolto nel delta; accesso cause.sqlite_errorcode test può produrre AttributeError sotto regressione, test comunque rosso, non difetto runtime e nessuna modifica richiesta. Collisione marker archivio non live, _archive usa INSERT INTO diverso; dict mutabile non live tramite risultato restituito che è copiato (non giustifica mutazione diretta costante privata). Ipotesi rollback primo handler assente refutata da codice/probe. TOOBIG poi FULL non riprodotto, non claim confermata. Probe attempts-update-only positivo del reviewer resta evidenza durevole, suggerisce copertura specifica ma non allargamento richiesto. Il report si autoidentifica erroneamente pyteman-outcomes-opus5: messaggio consegna chiarisce autore pyteman-release-review; preservata discrepanza senza alterare artefatto.

Consegnata v2, hash completo9e3686b84d0078a592a27e9917e6cdd44d2fabe6684490fcf1d8fadb82e0b45c, delta6fb46852c00f7cec5b70d5197592240ea6eda309c0024b2aa316d6ce27fdf675 in /home/pantinor/pyteman-evidence/task64-impl-v2-1789987785. Hash e git apply --check verificati coordinator. Suite1188/2skip ancora claim peer da verificare. Report completo letto e disposition registrate qui; F1/F2 dichiarati corretti, richiesta nuova review indipendente.

Triage tutte raccomandazioni simplify v2: applicate dedup frase comune, riuso JSON constant test, rinomina refusal_clause, docstring ownership; tre proposte helper _is_size_refusal declinate per minimo scope e test code-less aggiunto. Motivazione peer di preservare specifico co_consts NON vincolo architetturale valido: prova install identity va adattata a refactor legittimi, non viceversa. Non impone comunque estrazione per due letture. Eliminazione assert negativi respinta a favore code-review che richiedeva copertura di entrambi rami; dedup trace assertions e midrun SQL boilerplate declinate per scenari autosufficienti e sole due occorrenze. Efficiency nessun finding, no nuovi structured exception fields. Tutte decisioni tracciate, nessun refactor futuro implicitamente promesso.

Triage code-review high v2 sei item: #1 copertura frasi vietate doubleTOOBIG applicata con mutante; #2 commento no-code corretto, parola refused anziché could-not-write lasciata LOW e da valutare finale; #3 docstring ordine rollback corretto; #4 LOW finalisation refused for its size anziché row lasciato, valutazione finale; #5 factory override test helper documentato (assert primo errore fa fallire composizioni incompatibili); #6 rollback che solleva prima wrapper potrebbe perdere contesto attempt, preesistente fuori delta, registrato non introdotto. Accesso cause non guarded dei test deliberatamente mantenuto, produce test rosso ugualmente. Tre failure regression su vecchio candidato non equivalgono a tre detector indipendenti: una è pytest.fail driven wording, peer riporta mutazione separata per assert. Report completo REPORT-TASK64-v2.md conserva attributi e spiegazioni.

Coordinator verifica indipendente v2 9e3686b8 completata: nuovo export /home/pantinor/pyteman-evidence/task64-v2-integration-qgz04_yg, Python3.14.7 con venv editable proprio e setuptools presente. Suite 1188 passed, 2 skipped in27.28s, PYTEST_EXIT_CODE0; log pytest.log nella copia. Tre file candidato confrontati byte-per-byte col frozen dopo suite: identici. Skip previsti pre3.14 Placeholder e secondo renderer opzionale. Nessun commit/merge: review indipendente v2 ancora in corso, notifica completion sottoscritta.

Review2 /home/pantinor/pyteman-evidence/task64-review2-opus5-1789992735/REVIEW2-TASK64-opus5.md dichiara APPROVED su9e3686b8 e conferma1188/2skip; distingue delta da patch completa. Due finding LOW reali: F1 rowcount guard nel replay descrive callback normale come finished failed (status del segnaposto); F5 test calibrazione esaurisce finestra312byte su TMPDIR187+ caratteri, a186 passa. ENTRAMBI preesistono al delta v2 ma sono introdotti dalla patch TASK64 non ancora pubblicata: non chiamarli preesistenti al progetto. Decisione coordinator: correzione minima stessa task prima pubblicazione, per evitare nuovo test dipendente da path. Evidenze probe_guard_status.py/log e f5-calibration-window.log nella directory review2. Nuovo delta dovrà mantenere comportamento e aggiornare soltanto wording guard e ricerca test indipendente dalla lunghezza percorso.

Review2 altri item tracciati: F2 clause no-code non-size giudicata corretta dal reviewer e non blocker, F3 risultato restituito sostituito scelta necessaria per coerenza durable/returned, F4 rollback results se attempts too big proprietà atomica intenzionale, non defect. No extended TOOBIG corrente gap refutato. Razionali helper co_consts e test substrings come vincolo respinti (correttamente); no refactor helper richiesto. Wording finalisation vs row accettato. Nessun altro finding sotto cap nuovo; report fonte preservato.

V3 ricevuta hash4eb213546ed6bd3eb7d1295df71cca920340df22251f33335f9f95e52138d886 e deltada1fcc3eb1b0e30071803ae98603c48595237ade2d1f551d4c0eb8417e65eb52 verificati. Artefatti /home/pantinor/pyteman-evidence/task64-impl-v3-1789996537. F1 wording guard e F5 ricerca path-relative dichiarati corretti,1190/2skip claim peer da verificare. Cinque rilievi peer tutti registrati: #1/#2 extended TOOBIG ipotetico senza variante esistente oggi, già refutato come difetto corrente review2, no cambio; #3 attempts overflow risultato scartato proprietà atomica deliberata; #4 risultato ritornato segnaposto coerente contract, no modifica; #5 'cell ran' se makedirs fallisce wording preesistente anche nella base secondo peer, valutazione reviewer finale con base reale, non nuovo ciclo automatico. Simplify skip helper_rows/refuse_writes crossfile e wording originale accettati come no refactor scope. verify_artifacts driver non eseguito per backend base assente, non green: peer build+wheel hash non sostituisce artifact smoke.

Review3 consegnata /home/pantinor/pyteman-evidence/task64-review3-opus5-1790001676/REVIEW3-TASK64-opus5.md sha25617e8fbd5f2575ef928f008bfd4d7c9a70ab60393f778504a832f7553fee0e448. Artifact4eb213 INCOMPLETO: generato con pathspec src tests, manca README che pure è nel tree. NON usare. Reviewer ricostruisce remedy/task64-candidate-v3-COMPLETE.patch hashfddfe61697b42731c2d3efbb51dd8c2d874a1e37c52b9f172b5e2f91707d34b4 e lo dichiara esplicitamente APPROVED come stato completo. Coordinator verificherà tutti i file da base+patch vs delivery, non soltanto hash elenco. Runtime/test v3 approvati,1190/2skip reviewer; sul remedy intero suite ancora da rerun coordinator.

Review3 cut item nuovo matrix1253-1259 'the row' può indirizzare operatore verso results invece di attempts. Tracciato come precisione wording LOW non blocker, decisione no ulteriore ciclo cosmetico: risultati atomici invariati, errore chained conserva codice. Findings extendedTOOBIG refutati corrente, attempts/return scelte deliberate, 'cell ran' su makedirs confermato nella BASE7286f69 fuori scope. Review source report contiene tabella F5 con186FAIL ma prose dice threshold186/187 identica: non ripetere soglia numerica come nuova misura, prove path187/399 bastano al criterio. Reviewer ammette git lock transitorio cambiato mtime .git nel frozen senza cambi contenuto; nessun file hash alterato dichiarato, originale non verrà scritto coordinator.

Coordinator complete patch fddfe616: ricostruzione confrontata come INSIEME e contenuto con tutti81file tracked delivery, nessuna differenza. Suite indipendente1190pass2skip exit0 su /home/pantinor/pyteman-evidence/task64-complete-integration-s8isg0ub, hash/source equality anche post-test. Integrata stessa patch in shared branch nuovo work/oversized-outcome-fallback, tre hash approvati verificati e git diff --check pulito. Avviata suite shared con venv esterno editable proprio prima commit. TASK172 skill untracked separata, non da includere. AC3 condizionale opzione arresto non scelta, lasciata unchecked per ora con N/A motivato anziché fingere prova di policy non scelta. APPROVED finale fddfe616 reviewer indipendente presente; simplify/code-review high documentati nei report e dispatch, nessun bypass richiesto.

Gate simplify locale, pass REUSE completato su41d4ca0: nessun finding azionabile. Due note sotto cap registrate e declinate: tally transazioni duplicato due volte nel test, costo marginale mantenendo scenari autosufficienti; frase attempt running duplicata in due messaggi storage specifici, coerente stile per ramo. Nessun refactor richiesto e nessuna modifica candidato. Altri pass e code-review locale ancora pendenti, push resta sospeso dal gate.

Simplify locale ALTITUDE: livello soluzione corretto. Due suggerimenti accettati come non bloccanti ma non applicati: ridurre commenti rationale ripetuti in handler (coerenti stile circostante, nessun difetto comportamento, no ulteriore ciclo solo prosa); helper assert transazione duplicati in due test (già triage REUSE, locality pytest e scenari autosufficienti scelti). Cut items: mantenere JSON constant usata trigger e dict copy; no message-tail helper frammentario, no fusione connector che richiederebbe predicate framework, size-search calibrata necessaria, wrappingREADME cosmetico no action, wording row già tracciato. Report agente dice fino41sonde ma range(-80,81,8) ha21 valori: non adottare quel numero senza misura, non rilievo codice. Nessun cambiamento del commit41d4ca0.

Simplify locale EFFICIENCY completato: nessun finding azionabile, modulo14test passati dal reviewer. Sotto cap registrati: primo traceback trattiene payload oversize durante breve retry (nessuna azione); eccezione finale chained conserva primo traceback/payload finché caller conserva errore (tradeoff diagnostica documentata, no strip traceback non richiesto); ricerca calibrazione fino22run incluso baseline misurata dal reviewer costo trascurabile, no ottimizzazione. Nessun cambiamento del commit. Restano simplify semplicita e code-review locale.

Code-review locale recuperati8report reali in /home/pantinor/pyteman-evidence/task64-41d4ca0-review-handoff.json, zero mancanti ma verifica candidati pendente. A wording 'the row' DUPLICATO del cut6a già tracciato, no nuovo finding. Simplification propone (S1) sostituire calibrazione realSQLite con errore fabbricato e (S2) eliminare assert frasi errate del draft: entrambi toccano prove deliberate richieste, verifica indipendente prima eventuale decisione, nessuna modifica automatica. Extra nota binding count OperationalError contraddice prove precedenti ProgrammingError, da riprodurre con statement valido; non adottata come fatto. Altri sei angoli nessun candidato nuovo. La dichiarazione 'test verde quindi fake equivalente' non dimostra equivalenza copertura.

Code-review locale HIGH su41d4ca0 APPROVED, artifact finale /home/pantinor/pyteman-evidence/task64-41d4ca0-review-final.json, findings[]. Tutti8finder e4verifier conclusi, nessun report mancante. A wording row duplicato già tracciato e non nuovo; S1 errore iniettato refutato perché non riproduce trace/mutante; S2 refutato red/green1fail13pass->14pass; binding SQL valido tabella esistente ProgrammingError confermato. Simplify 4/4 complete: reuse/altitude/efficiency/simplification nessun cambiamento obbligatorio; triage note sotto cap registrate. Test integrati1190/2skip, build wheel+sdist exit0 e matrix.py artifact identico. Deploy gate comandi bash confermato filtra commento commit; pre-push-hook marker '# Gates:' appariva come commento commit. Tenta marker in first trailer con testo Gates marker attraversabile.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
PR #19 merged into master at 21d2bab7da843fb43d8c6a1536d848c58626b2a1. The runner now records an oversized cell outcome as one bounded failure after a full atomic finalisation retry, without rerunning the callback. Final code state is the independently approved complete artifact. Verification: complete patch reconstructs all 81 tracked delivery files; local and integrated suites 1190 passed with 2 expected skips; wheel and sdist built with matching matrix.py; /simplify all four passes completed; final /code-review high APPROVED at task64-41d4ca0-review-final.json; independent review APPROVED the complete patch fddfe61697b42731c2d3efbb51dd8c2d874a1e37c52b9f172b5e2f91707d34b4. GitHub CI was green for Python 3.11, 3.12, 3.13, 3.14, artifact and coverage; PR had no comments or reviews before merge. AC3 remains unchecked because it was conditional on the halt policy, which the user explicitly did not choose. Minor wording notes are recorded in notes, not left as promises.
<!-- SECTION:FINAL_SUMMARY:END -->
