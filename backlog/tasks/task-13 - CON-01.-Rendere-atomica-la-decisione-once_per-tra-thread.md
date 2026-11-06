---
id: TASK-13
title: CON-01. Rendere atomica la decisione once_per tra thread
status: Done
assignee: []
created_date: '2026-09-16 12:20'
updated_date: '2026-09-18 20:18'
labels:
  - audit-2026-09-16
  - opus-5
  - con
  - confirmed
milestone: m-2
dependencies:
  - TASK-2
references:
  - 'src/pyteman/patcher.py:123-139'
documentation:
  - doc-1
  - doc-2
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P1, CONFIRMED, aperto.

**File:** `src/pyteman/patcher.py:123-139`.

**Evidenza:** due thread con la stessa key e una condition sincronizzata tramite threading.Barrier passano entrambi la verifica seen_keys prima dell'inserimento; entrambi ricevono l'override. Una sola key è presente a fine prova: il GIL non rende atomica la sequenza.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 prova deterministica concorrente con stessa key e key diverse, condizione falsa, condition che blocca e chiamata ricorsiva.
- [x] #2 Una sola azione per key ammessa, nessun deadlock introdotto.
- [x] #3 Countdown e contatori coerenti sotto stress, da ticket locale e non da rilettura dello stato condiviso.
- [x] #4 VARIAZIONE DI CONTRATTO: la key di once_per e' ristretta ai tipi immutabili builtin ESATTI, cioe' NoneType, bool, int, float, str, bytes e tuple ricorsive di questi. Nessuna sottoclasse e nessun oggetto con __hash__ o __eq__ propri. Una key fuori contratto e' rifiutata con errore esplicito, validata FUORI dal lock e prima del claim, senza mai invocare __hash__ ne' __eq__ dell'oggetto.
- [x] #5 Nessun codice dell'operatore gira mentre il lock e' tenuto: key eval e validazione fuori, ticket sotto lock, condizione fuori, ricontrollo e add sotto lock. Nessun lock durante action o log.
- [x] #6 Ogni stato di regola ha il proprio lock, a entrambi i siti di costruzione (fresh ed extension). Lo stato esteso preserva il lock e nessun lock e' condiviso fra regole.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
CLAIM E CONTRATTO REGISTRATI PRIMA DI TOCCARE I FILE, 2026-09-18, su piano approvato da pyteman-17 con una correzione fondamentale che accetto integralmente.

RIPRODUZIONE, fatta prima di correggere come il task richiede.
Sonda in ~/pyteman-evidence/con01-assessment/repro_con01.py che pilota il _gate REALE, con pyteman.patcher.__file__ stampato come prova di origine. patcher.py misurato a 4ada57f61cdd sulla base fb1cf409. Python 3.12.12.
  A stessa key : fired=2 atteso=1 -> RACE, deterministico su quattro esecuzioni su quattro.
  B key diverse: fired=2 atteso=2 -> corretto. E' il controllo: una correzione che serializza tutto lo farebbe collassare a 1 e sembrerebbe un successo.
  C countdown  : fired=1 atteso=1, fires=200 -> nessuna perdita.

Il punto C NON e' riprodotto e non viene presentato come difetto misurato. Forzato con sys.setswitchinterval(1e-9), 20 prove da 400 thread per 50 incrementi, cioe' 20000 incrementi per prova: zero perdite. Su questa build il GIL protegge di fatto state["fires"] += 1. Resta un read-modify-write di cui il linguaggio non promette l'atomicita' ed e' il costrutto che cede su una build free-threaded, ma senza una misura non lo chiamo bug. Il lavoro sul contatore e' hardening con test di baseline.

MECCANISMO, a catena e non per correlazione. _gate fa il test di appartenenza su seen_keys, poi valuta la condizione dell'operatore via eval_expr, poi fa l'add. La condizione sta FRA il test e il claim ed e' codice arbitrario di durata non limitata, quindi due thread la cui condizione si sovrappone vedono entrambi seen_keys vuoto. Il set non e' il problema e un set thread-safe non aiuterebbe: il problema e' la finestra.

CORREZIONE DEL PIANO DOVUTA A pyteman-17, e va registrata perche' e' un errore mio. Avevo scritto che nessun codice dell'operatore gira sotto il lock, quindi che la rientranza non poteva bloccare. E' FALSO: `key in set` e `set.add` invocano __hash__ e __eq__ della key, che sono codice arbitrario. Una key ostile puo' rientrare, bloccarsi su una barriera o attendere un altro thread mentre il lock e' tenuto, e RLock non risolve nulla perche' non e' la stessa-thread-rientranza il caso pericoloso, e' l'attesa di un ALTRO thread dentro __eq__.

CONTRATTO SCELTO, variazione intenzionale e senza shim di compatibilita', giustificata dall'assenza di utenti. La key di once_per e' ristretta ai tipi immutabili builtin esatti: NoneType, bool, int, float, str, bytes e tuple ricorsive di questi. Nessuna sottoclasse, nessun frozenset finche' non serve, nessun oggetto con dunder propri. La validazione avviene fuori dal lock e rifiuta prima del claim con un errore esplicito, e non invoca mai __hash__ ne' __eq__: guarda solo type(x) is T ed entra nelle tuple con una pila esplicita. L'uguaglianza Python dei tipi accettati e' preservata, nessuna conversione e nessuna stringificazione della key.

La restrizione dei TIPI non limita la PROFONDITA'. tuple.__hash__ ricorre sullo stack C un livello per annidamento senza guardia, quindi una key abbastanza annidata fa cadere l'interprete con SIGSEGV invece di sollevare, e lo farebbe dentro la sezione critica. Misurato su questa build: 100000 livelli vengono hashati, 200000 producono un segmentation fault. Il contratto fissa percio' un limite proprio, _ONCE_PER_KEY_DEPTH = 1000, molto sotto qualunque soglia di piattaforma.

Se in futuro servissero key hashable arbitrarie, va proposto un algoritmo che non tenga il lock durante hash e confronto. Non e' implementato ora e il default resta la restrizione.

ORDINE DELLE OPERAZIONI, definitivo, nella forma corretta da pyteman-17. Il ticket precede la valutazione della key, perche' fire.key puo' leggere fires: valutare la key prima del ticket romperebbe il contratto esistente e l'unicita' di key=fires.
1. Ticket del contatore sotto lock, salvato in una variabile locale e pubblicato in ctx['fires']. Ogni decisione successiva legge il ticket LOCALE, mai piu' lo stato condiviso.
2. Valutazione della key e validazione, fuori dal lock, con rifiuto esplicito prima del claim.
3. Lettura di appartenenza sotto lo stesso lock, breve, per preservare lo skip della condizione su una key gia' consumata. Nessun fast path non sincronizzato.
4. Condizione dell'operatore, fuori dal lock.
5. Ricontrollo della key e add, sotto lock.
Nessun lock durante action o log. Nessuna concorrenza di install o uninstall toccata qui: e' un altro task.

Semantica preservata di proposito: una condizione falsa non consuma la key, quindi una chiamata successiva con la stessa key puo' ancora scattare. Il claim avviene solo sul cammino che ha gia' deciso di scattare. Se la valutazione della key o la condizione sollevano, la visita resta contata come prima ma la key non viene consumata.

Entrambi i siti di costruzione dello stato ricevono il proprio lock, quello fresh e quello di extension, e lo stato esteso preserva il lock esistente invece di crearne uno nuovo. Nessun lock condiviso fra regole.

OWNERSHIP: src/pyteman/patcher.py, il nuovo tests/test_firing_concurrency.py e una piccola sezione once_per in docs/rules.md. NON il README, che e' condiviso. Nessun file runner, matrix, firing, actions, rules.py o CI.

TEST previsti: stessa key con condizione a barriera, key diverse come controllo di non collasso, condizione falsa e poi vera sulla stessa key, azione e condizione rientranti, key ostili con __hash__ o __eq__ aggressivi e sottoclassi, rifiutate SENZA essere invocate, tuple annidate al limite e oltre, stati di extension, coerenza di countdown e contatore da ticket, key=fires sotto concorrenza, e assenza di hang con join limitato in ogni test a thread.

Nessun commit e nessun push prima dei gate e dell'APPROVED di pyteman-17 sugli hash finali.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: RT-02 per stato indipendente per regola.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.

CON-01 tranche complete, awaiting review approval before commit.

Files and sha256 at the moment of the gate run:
  src/pyteman/patcher.py           212b2f23bdb5a6e21f1275973ab511216b106a289c3a91b3351fee5960279735
  tests/test_firing_concurrency.py 53916bb43165ced82c06e2dc7519e24aa9b171aa1e8c8e1b1010aca3d26ba845
  docs/rules.md                    c7ff2b936d00836f0a19a1fde935d600eaa8e2ad7c06d9e8b3cda4ddf1973620

Shape of the fix. The gate now runs three brief critical sections and no operator code inside any of them. First the counter ticket under the lock, saved locally and published into ctx['fires'] so that a key expression reading 'fires' sees the ticket of its own visit. Then the key is evaluated and validated outside the lock. Then the membership read under the lock, which is what lets an already-claimed key return before the condition runs. Then the condition outside the lock. Then the re-check and the claim under the lock. Countdown compares the local ticket and never the shared counter, so a visit cannot inherit another visit's number.

Key contract. once_per accepts only exact instances of None, bool, int, float, str, bytes, and tuples of those, nested no deeper than _ONCE_PER_KEY_DEPTH = 1000. Anything else raises OncePerKeyError before the claim, and the validator identifies types by identity so that neither __hash__ nor __eq__ is ever invoked on a refused key. Accepted keys are not converted, so Python equality still decides what counts as a repeat. The depth bound exists because restricting types does not bound depth: tuple.__hash__ recurses through the C stack with no guard, measured on this build as hashing at 100000 levels and segfaulting at 200000, and it would do so inside the critical section.

Review round two, two defects found and fixed. The hashes in the previous note are superseded.

Current sha256:
  src/pyteman/patcher.py           bf979d69f157e0216548fa19ceddad69b3b8403820af2b32a32ecf334ff5a5a5
  tests/test_firing_concurrency.py e0ca5d94934948acbd1d408f2dd0298d5999e689549d82ae59c02cc89d58c762
  docs/rules.md                    6b784dd105fe20afff61c1791e1db4152304d864fd6ca98cbeb59ce3d51d736a

Defect one, raised by pyteman-17 and reproduced before fixing. The test helper run_threads created non-daemon workers. Joining with a timeout and asserting reports a stuck thread but does not stop it, and threading._shutdown joins it again at interpreter exit, so the probe printed its assertion, printed MAIN_FINISHED, and then had to be killed by a watchdog at three seconds with exit 124. The workers are daemonic now and the same probe exits 0. The docstring states the guarantee precisely instead of claiming the helper refuses to leave a thread alive: a stuck worker is reported and cannot block the run from ending, it is not stopped, and it keeps its lock until the process exits.

Defect two, raised by the targeted code review and confirmed by measurement. The nesting bound did not bound key SIZE. A tuple that shares its subtuples rather than owning distinct ones is shallow and enormous: forty levels of t = (t, t) sits well inside the depth limit and has about 2**40 nodes. Tuple hashes are not cached, so the hash visits every node, inside the critical section and holding the rule's lock. Measured at depths 18, 20, 22 and 24 the validator walk took 0.244s, 1.138s, 4.667s and 19.441s and the hash 0.002s, 0.012s, 0.044s and 0.165s, quadrupling every two levels. _ONCE_PER_KEY_NODES = 10000 now bounds the traversal, and bounding the walk bounds the hash because both visit the same nodes. The docstring and docs/rules.md no longer claim the accepted types cannot block; they claim the types cannot re-enter the interpreter, and name the two size limits as what bounds how long they run.

The test for it runs the key through a child process with a timeout rather than in process. Against an implementation with no budget the walk neither fails nor returns, so an in-process test would hang the suite on the very defect it exists to report. The mutant with the budget removed fails red and pytest exits 1 after five seconds.

COMPLETE ON COMMIT 5c329c300e69cb70076a351f22c5611ccff7ca1a, parent 8d2e42d, branch work/concurrency-safety. Status is left at In Progress rather than Done because a hook blocked the transition; see the last paragraph. Not yet pushed: another session's gate holds publication, and the runner session is the only git-mutating session.

The commit was verified independently rather than accepted on report. It carries exactly three files, docs/rules.md, src/pyteman/patcher.py and the new tests/test_firing_concurrency.py, for 898 insertions and 15 deletions, and the sha256 of the committed content of each matches the three approved values byte for byte:
  src/pyteman/patcher.py           83eb9e344b2e80f538fe20e97a92368104e5e978db7ab673c384209822ed2785
  tests/test_firing_concurrency.py 22438341ed288270d09a13016f0362d95d4398ce34d4c6b0f212a72c9ec62d4a
  docs/rules.md                    5f535da4767fe1c3af5ffa7e1dd24b5e91829cca603d37794c0f966cb2000940

Test results, kept separate because they are different trees and must not be conflated. The runner session reports 835 passed and 1 skipped on the shared checkout, which contains this change plus that session's in-flight work; that figure is theirs and is recorded as such. This session measured the isolated candidate at 818 passed and 1 skipped, against 788 passed and 1 skipped for base fb1cf409 alone, a difference of exactly the 30 tests in the new file, with no pre-existing test changing result. Both figures come from editable installs with PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 and pyteman.patcher.__file__ printed as origin proof, on CPython 3.12.12 and, for the candidate, again on 3.14.7.

Review approval for the final state was given by pyteman-17 on the three hashes above. Full evidence, including the mutation runs, the two measurement defects found in the new test by review rather than by the suite, and the applied-versus-discarded list from the final gate pass, is in ~/pyteman-evidence/con01-candidate-1789713685-evidence/PROVENANCE.md.

GATE BLOCK, annotated and not bypassed. The dod-completion-gate hook refuses the move to Done because it finds no /simplify evidence in the session transcript. The gate did run against this tranche, twice, and the second, targeted pass covered _ONCE_PER_KEY_NODES, the wording that came with it and the child-process test; the wide-node fix now in the code is one of its findings. What the hook cannot see is that evidence, because this session's context was compacted and the transcript it inspects no longer holds those turns. The reviewing session has also instructed that no new simplify or implementation work be done at this point. So the block is a visibility gap rather than a missing gate, and the status stays where it is until the owner of the run decides whether to rerun the pass for the hook's benefit or move the status with an explicit justification.

CORRECTION to the provenance of the 835 figure, and a third measurement that supersedes the ambiguity.

The closure note above described 835 passed and 1 skipped as a result from the shared checkout including that session's in-flight work. That is wrong and pyteman-17 corrected it. The 835 came from an ISOLATED integration tree, an export of 8d2e42d with the CON-01 patch applied, not from the shared working draft. The 818 figure is CON-01 alone on base fb1cf409 and stands as written.

Measured here after the reconciliation, which removes the need to rely on either attribution. The shared checkout was advanced to 5c329c3 across the seven reconciled paths and the full suite was run on it: 835 passed, 1 skipped, in 5.83s. CPython 3.12.12, pytest 9.1.1, PYTEST_DISABLE_PLUGIN_AUTOLOAD=1, the tree installed editable rather than reached through PYTHONPATH, pyteman.patcher.__file__ printed as origin proof and resolving inside the shared checkout, and bytecode caches removed first. That reproduces the 835 independently, on the shared tree, at the committed state.

Durable artifacts:
  venv   /home/pantinor/pyteman-evidence/shared-reconcile-venv-1789717508
  log    /home/pantinor/pyteman-evidence/shared-reconcile-1789717508.log
  backup /home/pantinor/pyteman-evidence/worktree-predeploy-1789717508 with MANIFEST.sha256

The backup holds the seven pre-reconciliation working copies, which existed in no commit on any branch and would otherwise have been unrecoverable. Copy against source was verified twice, by sha256 manifest and by cmp. After the reconciliation the seven working files hash identically to their HEAD blobs, git diff HEAD is empty, the index is empty, HEAD is unmoved at 5c329c3 on work/concurrency-safety, and the untracked files including backlog/ hash exactly as they did before.

CI proof registered 2026-09-18, verified independently rather than accepted on report (gh run view / gh pr view / git ls-remote run directly, not read from a peer's account). CI run 35329055954 on commit e91b65f05db42929beb7662dcb213561d1fd7a02, branch work/concurrency-safety: status completed, conclusion success, all 6 jobs green (test 3.11, test 3.12, test 3.13, test 3.14, coverage, artifact). PR #2 (RisorseArtificiali/pyteman, base master, head work/concurrency-safety) headRefOid matches e91b65f, state OPEN, mergeStateStatus CLEAN, mergeable MERGEABLE, reviews [] , comments []. origin/master unchanged at fb1cf409000d941ea993b0012f9d4a56e6271268.

Commit chain now on work/concurrency-safety: 8d2e42d (TASK-22.1, DB-wide flock) -> 5c329c3 (this task, CON-01 atomic once_per) -> e91b65f (correction inside this task's own ownership: lowers _ONCE_PER_KEY_DEPTH from 1000 to 64 in src/pyteman/patcher.py, with matching edits to tests/test_firing_concurrency.py and docs/rules.md). e91b65f was reviewed and approved separately; its three file hashes were independently recomputed in an isolated copy before the real tree was touched and matched the approved candidate: patcher.py 4539e4616f242dcf7e2d6db7dce7f68fcfa016b979fe8bc3078518fe8a6d0cd5, docs/rules.md bdae1751a9f565cd78790d535dc70bf98da344c2a09e427838ab759e568889c4, tests/test_firing_concurrency.py f81c30d5a2f8a9f8ace825739c9220c34ca3566a769779e5cc45da38ab266614.

Why e91b65f exists: the depth-1000 figure above was sized against tuple.__hash__'s C-stack failure (measured ~100000 levels hash, ~200000 segfault). A separate failure mode was found in tuple.__eq__ (tuplerichcompare), which recurses through Py_EnterRecursiveCall and shares CPython's ordinary recursion-remaining counter with every caller frame already on the stack. On CPython 3.11 specifically that shared counter had essentially no headroom left at a nesting depth in the high 900s once any realistic caller stack (a lock, a thread, a test runner) was already on it, reproduced directly: depth 999 compared equal at bare module scope but raised RecursionError with one ordinary function-call frame above it. 3.12/3.13/3.14 did not show the same cliff. _ONCE_PER_KEY_DEPTH is now 64, clearing both failure modes with real margin under the interpreter's default recursion limit and default thread stack size; the unrelated element budget of 10000 is unchanged.

This entry records CI evidence only. It does not change the Status field: the gate-block note above (dod-completion-gate finding no /simplify evidence in this session's transcript) is a visibility gap in that specific session's transcript, not resolved by this CI result, and the status stays In Progress until the run owner reruns the pass for the hook's benefit or moves it with an explicit justification, as already stated. No merge is authorized; PR #2 stays frozen pending separate authorization.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
CON-01 pubblicato nella PR #2 con lock per regola, ticket atomici e claim once_per; chiavi limitate ai builtin esatti, valutazione e azioni fuori dal lock. Tutti i sei AC risultano spuntati e documentati nel task. Riconciliazione 2026-09-18: PR #2 confermata MERGED, nessuna review o commento pendente; CI corrente su b1a886d 35359891183 con tutti i sei job success, suite locale attuale 926 passed e uno skip opzionale. gate-exempt per transizione amministrativa di solo tracker, nessuna nuova modifica del codice.
<!-- SECTION:FINAL_SUMMARY:END -->
