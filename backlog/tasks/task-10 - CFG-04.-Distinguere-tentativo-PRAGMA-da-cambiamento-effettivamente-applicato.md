---
id: TASK-10
title: CFG-04. Distinguere tentativo PRAGMA da cambiamento effettivamente applicato
status: Done
assignee: []
created_date: '2026-09-16 12:20'
updated_date: '2026-09-18 23:18'
labels:
  - audit-2026-09-16
  - opus-5
  - cfg
  - confirmed
milestone: m-1
dependencies:
  - TASK-9
  - TASK-15
references:
  - 'src/pyteman/actions.py:36-47'
  - 'docs/targeting.md:37-56'
documentation:
  - doc-1
  - doc-2
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P1, CONFIRMED, aperto.

**File:** `src/pyteman/actions.py:36-47`, `docs/targeting.md:37-56`.

**Evidenza:** `foreign_keys=ON` durante una transazione lascia foreign_keys a zero senza eccezione/outcome; il refuso `syncronous` viene ignorato da SQLite, sempre senza outcome. L'assenza di eccezione non prova l'effetto del PRAGMA.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 SQLite reale, foreign_keys dentro/fuori transazione, journal_mode, synchronous, nome invalido e target non utilizzabile.
- [x] #2 Log con esito esplicito e test che la modalità strict non lasci proseguire esperimenti invalidi.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Implementare in copia isolata da 8dc374b. Whitelist readback journal_mode, synchronous (0..3 e alias documentati), foreign_keys, ignore_check_constraints. Aspettativa partial normalizzata, valore ignoto -> pragma_unknown. Leggere before senza sopprimere execute se la lettura fallisce con Exception; eseguire sempre statement originale; leggere after solo dentro whitelist sulla stessa connessione. Confrontare scalari builtin esatti, non __eq__ arbitrario. Risultati applied/already/mismatch/unknown oltre failed/skipped; applied descrive postcondizione osservata, non causalità esclusiva. Diagnostici nuovi differiti e protetti, dati before/after/expected nel testo senza framework/schema extra.

PYTEMAN_STRICT_PRAGMA=1 controllato al firing: failed/skipped/unknown/mismatch producono PragmaVerificationError dedicato, terminale semantico prima di raise tramite precedenza primaria LOG02, senza doppio end/failed. Nessun os._exit. Messaggio eccezione sicuro anche con readback ostile. Interruzioni BaseException non demote a errore osservativo. Garanzia: entry body non prosegue se errore non catturato; run_matrix registra failed quando esce dal callback. Workload che cattura l'errore può continuare e il runner non analizza automaticamente il log; non promettere il contrario. Un terminale è disponibile solo se log configurato e scrittura riuscita.

Aggiornare README, docs/firing, docs/targeting, docs/rules, actions docstring, consumer Hermes e relativi test. Test SQLite reale dentro/fuori transazione, whitelist, valori ignoti, target inutilizzabile, readback ostile, strict caught/uncaught/no-log/logfailure, esito runner reale. Mutazione normalizzatore e reader, simplify, review high indipendente e suite prima di integrazione. Nessun commit/push/shared write da implementatore.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: CFG-03, LOG-02.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.

INPUT DA TASK-9 (CFG-03), 2026-09-17. Evidenza misurata li' e trasferita qui perche' la correzione appartiene a questo task. NON e' lavoro svolto su TASK-10, che resta aperto.

L'evidenza di questo task nomina il guasto al livello del NOME del pragma: il refuso `syncronous` viene ignorato da SQLite, sempre senza outcome. La misura di TASK-9 mostra lo stesso guasto un livello sotto, sul VALORE, e in una forma peggiore della semplice inerzia.

MISURA, sqlite 3.51.2 su python 3.14.7, database su file nuovo per ogni caso.
synchronous a baseline 0, scritto `banana`: passa a 1.
foreign_keys a baseline 0, scritto `banana`: resta 0.
Su un pragma a valore booleano una parola non riconosciuta non viene ignorata, viene risolta al default del pragma. Quando il default e' diverso dall'impostazione corrente, il valore precedente e CORRETTO viene distrutto in silenzio.

INQUADRAMENTO, deciso con pyteman-89. Non e' un bug di sintassi: SQLite e' permissivo per scelta di progetto e la sua tabella di parole booleane si comporta come documentato. Il difetto e' del toolkit ed e' la mancata verifica dell'effetto. actions.py:44 interpola il valore e non legge mai indietro, e actions.py:45 non aiuta: nessun valore fa sollevare con.execute, quindi l'assenza di eccezione non e' un segnale debole, e' nessun segnale.

CONSEGUENZA PER IL READBACK DI QUESTO TASK. Confrontare il valore letto dopo con quello scritto non basta come criterio, perche' su journal_mode i valori accettati "ON", "true", "1" e ogni intero lasciano il modo invariato senza che nulla sia andato storto dal punto di vista di SQLite. Servono due esiti distinti: applicato, e accettato ma senza effetto. Il secondo copre sia il valore ignorato sia quello che ha sovrascritto in direzione diversa da quella richiesta, e il modo di distinguerli e' leggere il pragma prima e dopo invece che solo dopo.

CONFINE. TASK-9 misura e dichiara quale effetto ha un valore accettato, e fissa quella matrice in tests/test_actions.py. TASK-10 decide cosa il sistema registra quando quell'effetto non avviene. Il caso della sovrascrittura resta interamente qui.

Ripresa autonoma autorizzata dall'utente dopo merge TASK15/PR5. Assessment assegnato tramite herdr a pyteman-release-review, modello esplicito copilot/claude-opus-5, launcher zai. Solo lettura/probe in copia durevole prima dell'implementazione; richiesti readback su SQLite reale, normalizzazione attesa e modalità strict come da AC. Nessun vincolo di backward compatibility. Branch preparato work/pragma-verification su merge 8dc374b, nessun codice TASK10 scritto nel checkout. TASK8 prosegue separatamente con assessment della semantica eval e dei candidati storici.

Assessment ricevuto da pyteman-release-review, documento ~/pyteman-evidence/task10-cfg04-assess-1789764212/ASSESSMENT-task10-cfg04.md. Non approvato nella prima versione: banana privo di expected non può essere classificato come mismatch; gli interi synchronous non passano tutti invariati (-1 osservato come 1); os._exit non è appropriato al runtime di libreria e strict limitato a unknown/mismatch ignorerebbe failed/skipped. Correzioni richieste inline al peer, nessun codice autorizzato ancora. Probe indipendente coordinatore SQLite 3.53.4 conferma foreign_keys ON in transazione resta 0; banana da foreign_keys 1 porta a 0; synchronous banana e -1 danno 1, 4 dà 4, false dà 0; nome syncronous rilegge []. Queste sono misure del caso, non un contratto universale della whitelist.

Approvata implementazione dopo correzioni del piano e verifica del runner: matrix.py:974-979 marca done se callback ritorna e failed solo se solleva; NON legge firing log. La claim del peer 'strict garantito al runner via log anche se catch' è respinta. Non si allarga il task con monitor del log: contratto esplicito di eccezione intercettabile e test sul percorso non catturato. Accolta diagnostica differita dei readback; richiesto inoltre controllo tipi builtin per evitare confronto/rendering ostile prima della diagnostica. Incarico attivo a pyteman-release-review tramite herdr/zai Opus5, copia isolata.

Checkpoint implementatore pyteman-release-review: candidato nella copia ~/pyteman-evidence/task10-cfg04-assess-1789764212, base 8dc374b, non integrato. Report del peer, non ancora verifica indipendente del coordinatore: suite 989 passed, 1 skipped; nuovo modulo pragmas.py con normalizzatore parziale e readback limitato, gate strict unico _pragma_result, consumer che importa REFUTING. Diff dichiarato task10.diff sha256 30b830c35e000367a5c3416a60b02c9be5ca8e0524ba3655886e552812c90cc7. Gate ancora in corso: nessuna approvazione finale o pubblicazione. Richieste evidenze finali con nuovi file inclusi, packaging pragmas.py, mutazioni e mantenimento dello status generico failed nel consumer oltre agli status PRAGMA.

Candidato aggiornato ricevuto, task10.diff sha256 9c39d36fa3cdc9b8b1222b72a4e6d6af8fdca817dbb823cc6a10d1a22cbba08e verificato e git apply --check riuscito. Il peer riporta fix di readback row-shape dentro try e lookup case-insensitive, sette cleanup e suite 992 passed/1 skipped su 3.13 e 3.14; risultati ancora attribuiti al peer. Avviata suite indipendente del coordinatore in fresh export 8dc374b con patch e venv editable. Prima di integrazione richiesti APPROVED sullo stato post-fix/post-cleanup del medesimo reviewer, rettifica docstring su valore ignoto non sempre inerte e su to_raise ora usato anche da strict. Richiesta verifica concreta del cursore SET journal_mode ignorato rispetto al piano, non dichiarato difetto finché non provato. Shared resta invariato.

Checkpoint candidato e6126a8e1f8a840b711edf44d1f3c46ab0b9b01a8fbd154ca35e057508b63be8 riportato dal peer: SET cursor chiuso esplicitamente con cleanup protetto; sonde deterministiche mostrano lock se cursor journal_mode trattenuto, non dimostrato lock nel normale CPython che lo libera per refcount. Non presentare questo come regressione CPython misurata. Suite peer 994/1 skip su3.13/3.14, approvazione finale ancora pendente; suite indipendente9c39 non copre nuovo stato.

Decisione read-close (questione creata fuori mandato dal peer come TASK171): mantenere UNREADABLE se cleanup del cursor di osservazione fallisce. Scelta conservativa documentata, non refactoring necessario: non certificare come riuscita una procedura osservativa che fallisce; diverso dal SET, già eseguito e non da sopprimere per cleanup. Richiesta frase nel docstring e delta review stesso reviewer. TASK171 incorporato qui e archiviato come duplicato di decisione nel perimetro TASK10. Riaffermato agli agenti divieto di scritture tracker.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Pubblicato e unito con PR7 https://github.com/RisorseArtificiali/pyteman/pull/7, commit c2475f65065b4274de43eb72a6c436bb3fc452a1, merge5ba4c3753e70c4a013e6933e11a3874e9c4aa73e. Readback limitato a quattro PRAGMA con aspettativa normalizzata, esiti applied/already/mismatch/unknown e strict opt-in via PYTEMAN_STRICT_PRAGMA=1. Eccezione dedicata dopo tentativo di log terminale, senza exit forzato. Consumer e documentazione aggiornati; cursori SET chiusi esplicitamente e read-close failure non certificato.

Reviewer persistente APPROVED su bc477746 dopo regressioni e mutazioni. Suite indipendente su base mergePR6 e suite shared: 1016 passed, 1 skipped opzionale. CI35404889430 conclusa success prima del merge; PR verificata MERGED, review e commenti vuoti. Packaging del nuovo modulo verificato dai test e CI artifact.

Limiti: whitelist chiusa, valore ignoto non certificato, nessuna promessa di causalità esclusiva su connessione condivisa. Workload può catturare PragmaVerificationError; runner marca failed solo se eccezione esce dal callback. Log presente solo se configurato e scritto con successo. Nessun compatibility shim.
<!-- SECTION:FINAL_SUMMARY:END -->
