---
id: TASK-15
title: LOG-02. Correlare tentativi e outcome senza scambiare firing per successo
status: Done
assignee: []
created_date: '2026-09-16 12:20'
updated_date: '2026-09-18 20:42'
labels:
  - audit-2026-09-16
  - opus-5
  - log
  - confirmed
  - proposal
milestone: m-2
dependencies:
  - TASK-14
references:
  - 'src/pyteman/actions.py:17-19,68-84'
  - 'src/pyteman/firing.py:13-29'
documentation:
  - doc-1
  - doc-2
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P1, CONFIRMED nel flusso del codice; PROPOSTA di schema, aperto.

**File:** `src/pyteman/actions.py:17-19,68-84`, `src/pyteman/firing.py:13-29`, parser log negli esempi.

**Evidenza:** il record di firing precede l'azione, quindi prova il tentativo, non la sua riuscita. Gli outcome hanno un nuovo seq ma nessun riferimento al tentativo; la deduplicazione per (rule, message) sopprime errori ripetuti. Con thread concorrenti l'adiacenza nel file non è una correlazione affidabile.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 due firing intrecciati, errore ripetuto, target miss e kill in subprocess: numero di tentativi e loro esito ricostruibile, nessuna attribuzione errata tra regole/thread.
- [x] #2 Tutti gli esempi aggiornati.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Schema 2 con record start/end correlati tramite identità del record iniziale, status per outcome osservabili e nessuna deduplicazione. Conservare eccezione primaria dell'azione, distinguere raise intenzionale da failure, rendere visibile timeout e non promettere readback PRAGMA o override effettivo. Aggiornare tutti i consumer e i riferimenti documentali al vecchio dedup. Verificare suite, concorrenti, identità, kill e coverage; review indipendente finale e CI prima del merge.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: LOG-01; CFG-04 e EX-01 consumano questo contratto.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.

Review gate (high effort, targeted) on the LOG-02 change. Verdict: contract holds. The reviewer probed the seq/attempt splice with an adversarial rule id and note (embedded quotes, braces, a literal `}{"seq": 999`, non-ASCII) and found no duplicate-key or truncation defect; ran 8 threads x 200 firings against a real FiringLog and got 3200 records in exactly 1600 correctly-paired attempt groups with zero cross-attribution; confirmed serialization stays outside both locks and that the RecordId is returned only after write and unlock; and confirmed a spawned child killed by a kill action leaves a start record with no terminal. Six mutants (terminal attempt=None, raised->failed, reintroduced dedup, start record moved after the action, swallowed terminal failure) were each caught by tests/test_log_actions.py, so the new tests discriminate rather than merely pass.

Three review findings, all fixed this turn, plus two lower-confidence notes also fixed rather than deferred.

1. A failed terminal write from an EXIT rule displaces the workload's own exception, because the patcher runs exit rules inside the patched call's finally block (patcher.py:1797) where any raise replaces the in-flight exception. Pre-existing mechanism, but new in DEGREE: before LOG-02 only a pragma miss wrote a second record, now every action writes a terminal, so every exit-rule firing is an opportunity. Decision: keep raising, because the alternative is a firing log that can lose records silently, which is the exact failure this schema exists to prevent. The trade is now stated explicitly in docs/firing.md, noting the original stays reachable as __context__.

2. KeyboardInterrupt/SystemExit out of the terminal write were swallowed and demoted to a note whenever the action was already raising, contradicting the posture firing.py takes around its own locking. Narrowed the handler to `except Exception`; async interruptions now propagate with their identity. Pinned by test_a_ctrl_c_during_the_terminal_write_is_not_demoted_to_a_note.

3. run_action hard-required a RecordId and a log shim written against the old signature produced `AttributeError: 'NoneType' object has no attribute 'attempt'` inside the workload under test. Now raises a TypeError naming the missing contract. Pinned by test_a_log_that_returns_no_attempt_id_is_named_not_an_attribute_error.

Lower-confidence notes, also fixed: the 111912 consumer refuted attempts by matching a status SUFFIX, coupling it to a shape docs/firing.md does not version, now an explicit set of refuting statuses; and the README claimed flatly that every firing is 'logged twice', which the kill action contradicts by construction, now reworded.

Both new tests were mutation-checked: each fails against the mutant that removes its fix, and src/pyteman/actions.py was restored byte-exact afterwards (sha256 e70f48c4f449942860b8a8d1f333c65ab1855c838fb912998f269e82da0e98ab before and after), with the pyteman __pycache__ cleared so no stale .pyc could mask the restore.

Simplify gate: two structural changes, suite 913 passed / 1 skipped before and after. (1) _dispatch returned a bare 4-tuple that ten return sites padded with positional Nones, so a reader had to count slots to tell the return value from the deliberate exception; it now returns a _Dispatched namedtuple with defaults, matching how firing.py already defines RecordId, and _dispatch is module-private so there is no external surface. (2) The tail accumulation inside the lock collapsed back to a single splice expression, same work and same position relative to the lock. Hard constraints held: os.write/os.close snapshots, the narrow `except Exception`, start-before-action ordering, the raised/failed split and the primary= identity paths are all unchanged, and no dedup, lock or cache was added. Serialization is still outside both locks (json.dumps at firing.py:254, splice at :260 inside the threading.Lock, flock at :277).

Final verification, __pycache__ cleared first: 913 passed / 1 skipped on Python 3.14.7 and on Python 3.11.14, the latter with provenance rechecked by importing pyteman and confirming it resolves to the export copy rather than a stale editable install. A recursive diff against the shared tree shows exactly the 12 authorised files differing, 10 modified and 2 new. Patch at /home/pantinor/pyteman-evidence/task15-log02-20260918-171838/task15-log02.patch, 907 insertions / 68 deletions, validated with `git apply --check` against the shared tree (read-only). Evidence at ~/pyteman-evidence/task15-log02-evidence.md with per-file sha256. Nothing committed, pushed or published; the shared working tree was never modified.

Optional follow-up, noted here rather than filed as a new task: the status vocabulary in docs/firing.md is documented but not versioned independently of `schema`, so a consumer cannot tell a status added later from one it simply does not recognise. The 111912 driver is written to fail loudly in that case rather than skip, so nothing is broken today; a future LOG task could either bump `schema` on a vocabulary change or publish the set. Pyright's `exc_info` unread warning at firing.py:182 is the standard __exit__(self, *exc_info) signature, byte-identical to the baseline, not a finding.

Delta review (high effort) closed with two findings, both reproduced by my own probe before the fix, both mutation-checked after it.

1. A pragma target whose RESOLUTION raises still propagated. `targets.py:57` builds its miss reason from workload-owned objects (`type(obj).__name__`), so a metaclass whose `__name__` is a raising property makes the resolver itself raise: the probe gave `PROPAGATED RuntimeError hostile type name`, recorded as `status: "failed"`. That was the single path where a pragma became a failure of the run, contradicting the documented promise. Fixed in `actions.py` by wrapping the resolution call and reporting `pragma_skipped`.

2. `pytest.raises(KeyboardInterrupt)` does not make a test fail: pytest treats an escaping KeyboardInterrupt as a session interrupt, so the mutant gave `17 passed` with zero FAILED lines and every later test unrun. Fixed with a `raises_exactly` helper catching `BaseException` and asserting on `type(...)`; the same mutant now gives `5 failed, 27 passed`. Three tests were affected, not the two the reviewer named.

Suite: 926 passed, 1 skipped on Python 3.14.7 and 3.11.14, caches cleared, both importing the export copy.

CORREZIONE della nota precedente sulla delta review. Il punto 1 di quella nota era sbagliato e il cambiamento che descriveva e' stato RIMOSSO prima del merge.

Quella nota presentava la propagazione di un'eccezione dal resolver come un difetto introdotto o coperto da LOG-02, e il fix come un ripristino. Non lo era: su HEAD un RuntimeError dal resolver PROPAGA, e quello e' il contratto esistente. Avvolgere la risoluzione in `except Exception` e restituire `pragma_skipped` cambiava la policy RUNTIME rispetto a HEAD, dentro un task di logging, e classificava un bug del getter come skip. Rimosso; la risoluzione e' di nuovo non protetta, con un commento che spiega perche'.

Comportamento finale, uguale a HEAD: un'eccezione dal resolver prende il percorso generico di `run_action`, produce un record terminale `status: "failed"` con la diagnostica, e l'eccezione originale propaga con identita' invariata. `pragma_skipped` resta riservato al miss che il resolver RIPORTA (`con is None`). Il test e' stato riscritto per fissare questo: `test_a_target_whose_resolution_raises_is_a_failure_not_a_skip`.

La domanda di policy appartiene a TASK-12 (CFG-06), che la copre gia' ed e' CONFIRMED. L'evidenza del probe e' stata annotata la'. TASK-170, che avevo aperto come task separato, era un duplicato di TASK-12 ed e' stato archiviato.

Il punto 2 della nota precedente (pytest.raises e KeyboardInterrupt) resta valido e invariato.

Gate finali sulle tre ultime modifiche (resolver non protetto, rename del sentinella, docstring di test_kill), che i gate precedenti NON coprivano perche' sono successive. Eseguiti ora, non dichiarati esenti.

Review high effort, mirata a quelle tre sole modifiche piu' il test nuovo. Verdetto: nessun finding sostanziale. Il reviewer ha verificato che la chiamata di risoluzione e' fuori da ogni `try`, quindi l'eccezione lascia `_dispatch` e viene presa dall'`except BaseException` di `run_action:76`, che chiama `_terminal(..., "failed", ..., primary=exc)` e rilancia con `raise` nudo; il ramo `primary=` di `_terminal` aggiunge solo una nota e non rilancia mai sopra il primario, nemmeno per una BaseException dal log, quindi la meta' "propaga invariata" del commento regge anche quando la scrittura del terminale fallisce. `_safe_message` non puo' sovvertirlo: la lambda differita viene resa dentro il suo `try`, e il fallback rende il tipo del fallimento di RENDERING, non quello del primario, quindi un'eccezione con `__name__` ostile degrada a `<diagnostic unavailable: ...>` invece di sfuggire. `con is None` resta l'unico percorso verso `pragma_skipped`.

Sul rename del sentinella il reviewer ha stabilito che non e' una trappola di manutenzione: `resolve_exit_line` risolve via AST, quindi un nome module-private non e' piu' debole di uno pubblico, ed e' autocontrollante nei due sensi, perche' fallisce con SystemExit se il def nominato manca o e' duplicato e se la funzione non contiene esattamente un `os._exit` nel proprio scope. Un refactor futuro che sposta di nuovo l'uscita produce un errore rumoroso e spiegato, non un `ok` falso. Verificato dal vivo: la coppia risolve a src/pyteman/actions.py:149 e src/pyteman/sitecustomize.py:67.

Sweep dei riferimenti pulito. Le uniche occorrenze residue di `run_action` sono corrette: docs/firing.md:76,80 (cosa osserva e quando ritorna), docs/coverage.md:44 ("the other callers of run_action in tests/test_actions.py", che e' un'affermazione sui CHIAMANTI, non su dove sta l'uscita) e le docstring dentro actions.py. docs/coverage.md:62 e tests/test_kill.py:33 nominano entrambi `_dispatch`.

Il test nuovo discrimina davvero: il metaclass ostile fa sollevare `type(obj).__name__` dentro `resolve_target` a targets.py:58, cioe' esattamente dove stava la guardia rimossa. Reintroducendo la guardia la chiamata ritorna `pragma_skipped`, non propaga nulla, e `raises_exactly` fallisce con "expected RuntimeError, nothing was raised". Il test fissa entrambe le meta': lo status del record terminale e la propagazione con `type(exc) is expected`.

Gate simplify sulle stesse tre modifiche. Una sola proposta strutturale sopravvissuta, ed e' sul volume dei commenti: le sei righe sopra `EXIT_SENTINELS` in scripts/run_coverage.py contengono un changelog del rename, di cui solo l'ultima frase e' portante. NON applicata, perche' i 15 file erano congelati su richiesta del parent in attesa del commit. Depositata come TASK-170 con criteri di accettazione, invece di restare una frase in un messaggio.

Il resto e' stato esaminato e respinto dal gate stesso, non lasciato correre. Il commento sul ramo pragma (actions.py:120-126) resta esattamente com'e': e' il caso canonico che la convenzione del progetto protegge, un commento che registra perche' una guardia e' deliberatamente assente, per una guardia che un lettore futuro riaggiungerebbe a vista dato che il ramo attorno e' altrimenti difensivo. La quasi-duplicazione con il commento nel test non va collassata, perche' i due servono lettori diversi: quello nel sorgente ferma una modifica, quello nel test spiega cosa fissano le asserzioni.

Un vincolo emerso dalla review e' stato riportato su TASK-170 perche' non venga violato piu' tardi: la parentetica di docs/coverage.md:62 non va tagliata, e' l'unico punto che lega il testimone privato al punto di ingresso pubblico.

Backup pre-applicazione e manifest, durevoli, per il commit del parent.

Directory: ~/pyteman-evidence/task15-pre-apply-backup-1789750895/

- files/: copia `cp -a` dei 13 file condivisi che la patch modifica, nel loro stato PRE-applicazione. I 2 file nuovi (tests/test_log_actions.py, tests/test_example_log_consumers.py) sono registrati come ABSENT-AT-BASELINE nel manifest, e la loro assenza a b1a886d e' stata verificata con `git show`, non assunta.
- PRE-manifest.txt: sha256 dei 13, piu' le due righe di assenza.
- POST-manifest.txt: sha256 dei 15 file candidati piu' la patch.
- scope-files.txt: l'elenco dei 15.
- shared-state-manifest.txt: stato dell'albero condiviso al momento del backup.

Il backup e' verificato byte-esatto in due modi, non solo copiato: `sha256sum -c` contro l'albero condiviso passa su tutti e 13, e ciascuno degli stessi 13 hash coincide con `git show b1a886d:<file>`, quindi il backup e' identico sia al worktree sia a HEAD.

Stato condiviso registrato: HEAD b1a886d892bc020f3b7be545faa37449445a00bd su work/firing-outcomes, worktree contro index CLEAN, index contro HEAD CLEAN, nessuno stash. Untracked preservati e non toccati: .github/workflows/tests.yml.bak.1789617984, backlog/ (189 file), pyproject.toml.bak.1789618608, pyproject.toml.bak.1789622596, pyteman.log.

Un fatto da sapere prima del push: `refs/remotes/origin/work/firing-outcomes` NON esiste. Il branch e' solo locale, e origin/HEAD e origin/master puntano entrambi a b1a886d.

Deriva verificata, non assunta: un diff ricorsivo fra albero condiviso e copia candidata riporta esattamente 15 voci, quindi nessun file fuori dai 15 autorizzati e' cambiato. La patch resta applicabile su questa base con `git apply --check --stat`: 15 file, 1138 inserzioni, 74 delezioni.

Niente applicato, staged o committato da me. Lo stato Done non e' stato toccato: resta In Progress finche' la CI non e' verde, come da indicazione del parent.

Disambiguazione su TASK-170, perche' l'id e' stato riusato e due note qui sopra lo nominano con significati diversi.

Il TASK-170 archiviato, citato nella nota CORREZIONE, era il duplicato di TASK-12 (CFG-06) sulla policy delle eccezioni dal resolver. Quello resta archiviato.

Il TASK-170 vivo, citato nella nota sul gate simplify, e' un task DIVERSO che ha ereditato lo stesso numero dal generatore di id dopo l'archiviazione: riguarda il taglio del commento di changelog sopra EXIT_SENTINELS in scripts/run_coverage.py. Titolo attuale del file, per distinguerli senza ambiguita': 'Cut the rename changelog comment above EXIT_SENTINELS in scripts/run_coverage.py'.

Da tenere presente in generale: archiviare un task libera il suo numero, quindi un id in una nota storica non identifica un task da solo. Verificare sempre il titolo insieme al numero.

Review indipendente finale di pyteman-release-review, sessione 8bd30838-357e-45c4-adf2-fe981dce5e5e: CHANGES REQUESTED, non APPROVED. Confermati leggendo i file: docs/targeting.md promette ancora outcome deduplicati, mentre LOG-02 li registra per tentativo; examples/hermes-111912/run_repro.py:185-188 descrive come fail-loud il conteggio permissivo di status sconosciuti, ma pin_engaged=True permette CLEAN/REPRODUCED e False forza INCONCLUSIVE. Da correggere nella stessa unità, insieme ai riferimenti obsoleti al dedup in patcher.py, rules.py e docs/rules.md. Nessuna modifica runtime richiesta da questi rilievi. Estensione dello scope limitata alla coerenza della documentazione e dei commenti.

Proposte opzionali del revisore registrate qui, non in nuovi task: riuso di firing._annotate tra moduli (respinto per questa unità, evitato import privato e refactoring non necessario); accorpamento dei due rami _terminal (rinviato, nessun difetto); docstring sulla costruzione lazy dei diagnostici troppo universale per Rule costruite manualmente (verificare e precisare il contratto, senza ampliare runtime); reader condiviso e vocabolario status esportato per i tre esempi (futuro miglioramento, nessuna API aggiunta ora); factory parametrica per i fake dei log (non necessario alla pubblicazione); campi RecordId non letti dai consumer attuali (mantenuti perché documentano identità e correlazione). Le misure aggiuntive del revisore restano attribuite al suo report finché non confronto i log; non sono prova di CI futura.

Pubblicato commit 3ac7bc6daba7a445f180c4532107399af5be2601 su work/firing-outcomes, PR https://github.com/RisorseArtificiali/pyteman/pull/5. Venti file: i quindici originari più cinque file con sole correzioni documentali/commenti. Nessuna modifica runtime nelle rettifiche finali, provato tramite AST normalizzato contro candidato iniziale. Reviewer persistente Opus5 APPROVED sugli hash final-manifest.json; record ~/pyteman-evidence/task15-final-review-opus5-1789763173/opus5-logs/final-review-verdict-opus5.md. Suite coordinatore final-tests.log: 926 passed, 1 skipped opzionale; final-coverage.log: 925 passed, 1 skipped, 1 deselected, entrambi i sentinella ok. /simplify delegato: quattro angolazioni eseguite, fase review soltanto; opzionali valutati e non applicati per evitare refactor fuori obiettivo. Nessun gate disabilitato. CI 35392593455 avviata, non ancora dichiarata riuscita. Stato resta In Progress fino al completamento remoto.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Pubblicato e unito nella PR #5: https://github.com/RisorseArtificiali/pyteman/pull/5. Commit 3ac7bc6daba7a445f180c4532107399af5be2601, merge 8dc374b50e170c8eb3da838f95907d7a5c7bb4b9. Schema 2 correla ogni tentativo ai propri outcome senza confondere firing e successo; i consumer leggono phase e attempt e il log conserva gli esiti ripetuti. Rettificati i riferimenti al vecchio dedup e il commento permissivo del consumer Hermes. Venti file, nessun compatibility shim.

Review indipendente Opus5 APPROVED sugli hash finali. Suite locale 926 passed, uno skip opzionale; suite coverage 925 passed, uno skip e un deselect deliberato, due sentinella ok. CI PR 35392593455 conclusa success in tutti i sei job, test 3.11–3.14, artifact e coverage. PR verificata MERGED con nessuna review o commento pendente. Il run post-merge 35392817923 era ancora in corso al momento della chiusura; non è presentato come verde.

Limiti: outcome assente significa sconosciuto, nessun ordine globale, PRAGMA eseguito non equivale a valore verificato. Readback e strict mode sono TASK-10. Proposte simplify opzionali registrate nelle note, non applicate come refactor fuori obiettivo.
<!-- SECTION:FINAL_SUMMARY:END -->
