---
id: TASK-14
title: 'LOG-01. Identificare univocamente run, processo e firing'
status: To Do
assignee: []
created_date: '2026-09-16 12:20'
updated_date: '2026-09-29 19:52'
labels:
  - audit-2026-09-16
  - opus-5
  - log
  - confirmed
milestone: m-2
dependencies: []
references:
  - 'src/pyteman/firing.py:6-29'
  - 'README.md:9-11'
documentation:
  - doc-1
  - doc-2
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P1, CONFIRMED, aperto.

**File:** `src/pyteman/firing.py:6-29`, `README.md:9-11`.

**Evidenza:** due istanze consecutive di FiringLog sullo stesso file in append producono sequenze `[1, 1]`. I record non contengono PID né run id; thread name non distingue processi. Timestamp a secondi senza timezone e sequenze per istanza non consentono un ordine globale tra writer.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 reopen nello stesso processo, due processi e più thread; ogni evento ha chiave univoca e provenienza recuperabile, le righe restano JSON valide.
- [ ] #2 Il vecchio formato è gestito dai consumer o migrazione documentata.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Proposta iniziale da verificare sul codice corrente, non una correzione già applicata.

dichiarare la portata del contatore e introdurre identità di sessione/processo/istanza, indice di visita, point e timestamp ad alta risoluzione con timezone; separare wall clock da monotonic per misure locali. Scegliere log separati per writer o protocollo di append/coordinamento documentato. Non promettere ordine totale con timestamp non coordinati.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: nessuna. Definire lo schema condiviso con LOG-02, poi aggiornare i parser degli esempi in EX-01/EX-05.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.

Correction from peer's parent review (2026-09-18), verified against write(2)/pipe(7): PIPE_BUF atomicity is a pipe/FIFO guarantee, not a regular-file guarantee. O_APPEND gives atomic offset-assignment per write(2) call, but a regular-file write can still short-write, so no payload-size threshold may be presented as a POSIX atomicity guarantee for JSON-line integrity. Design corrected to: fd opened O_APPEND, per-instance threading.Lock for same-process ordering, plus fcntl.flock(LOCK_EX) held for the full write-until-complete loop (retrying on short writes, raising on error or a 0-byte write) for cross-process safety. fcntl absence (Windows) is a hard error at construction, not a silent fallback.

Correction: no new 'visit' counter in FiringLog. ctx['fires'] (set by _gate in patcher.py, line ~2064, before the action runs) is already the real per-rule visit ticket, and outcome annotations for a firing share the same ctx, hence the same ticket. A record written by log.record() is not a 1:1 stand-in for a visit: counting records would give a firing and its later outcome annotation different visit numbers, breaking exactly the attempt/outcome correlation TASK-15 needs. Schema field 'visit' is populated from ctx.get('fires') (None when absent, e.g. a direct run_action call outside the normal gate path), not a new counter.

Implementation authorized by peer (2026-09-18) with full contract: schema=1, run_id (env PYTEMAN_RUN_ID or fresh uuid4 per instance, no reopen aggregation), instance (uuid4 per FiringLog()), pid, seq (monotonic per instance only, no global order promised), point (rule.module+'.'+rule.symbol), visit (ctx.get('fires')), thread, time (UTC isoformat), monotonic_ns. Unique key is (instance, pid, seq). Fork: record() must refuse with a clear error if pid != creator pid, checked before the lock (deadlock avoidance on a fork mid-write); spawn is the supported multiprocess path, no atfork machinery. close()/context-manager added to the fd-backed handle; idempotent close, record()-after-close raises. Scope: firing.py, test_firing.py, new test_firing_multiprocess.py, test_targets.py (private _fh.close() to public close()), new docs/firing.md, README log-schema mention. actions.py/sitecustomize.py untouched (not indispensable). Working in the isolated work/firing-provenance branch (based on af561507, not shared); this session does not commit/push, only prepares the candidate and gate evidence for the parent session.

Final correctness review (2026-09-18), round 4 candidate: APPROVED, no verified blockers. Model provenance, stated exactly: the earlier review round on this task was declared Sonnet; THIS final review was performed by Opus 5 (session `pyteman-opus5-verified`), banner-verified, read-only, no writes to src or shared state and no commits. Status deliberately stays In Progress: not Done until CI is green.

What was reviewed: the isolated candidate worktree `.claude/worktrees/firing-provenance-candidate` at base af561507, delta 815 insertions / 11 deletions over four tracked files plus two new untracked files (docs/firing.md, tests/test_firing_multiprocess.py). All six file sha256 values and the round4.patch sha256 matched the handoff brief byte-for-byte.

Evidence actually run, not inferred:
- Full suite in the evidence venv: 878 passed, 1 skipped in 16.90s, independently reproducing the parent session's count.
- Provenance of the running code was verified beyond the source hash, because a matching .py hash proves nothing about the loaded bytecode: the firing.cpython-314.pyc header's timestamp and source-size fields both match the source (1789738372, 13254), and a forced fresh compile under an isolated PYTHONPYCACHEPREFIX behaved identically. Not a stale pyc.
- Ten independent adversarial probes, all on freshly created mktemp -d data, no monkeypatching of real files, no source mutation. All ten pass. The three highest-value ones: (G) after poisoning, close(), __exit__ and gc against a deliberately recycled fd, the victim fd was reissued the SAME number (3) and stayed writable, which is an observation of no double close rather than an argument for it; (E) a note containing `}`, a newline, a forged `"seq": 999`, a backslash-quote and a NUL yields exactly one line, round-trips byte-exact and still reports seq 1, so the `body[:-1]` splice cannot be forged through; (A) two FiringLog handles in one process, 120 threads, 3 KB notes on a shared path, gives 120 lines and 120 unique (instance, pid, seq) keys with no corruption, with probe J confirming record() blocked on a foreign flock from a second OFD blocks and then completes without deadlock.
- One documentation claim was checked rather than assumed: docs/firing.md states `point` is byte-identical to the YAML `point:` string, and load_rules splits at the FIRST dot (rules.py:352) while parse_point splits at the LAST. Verified empirically with a.b.c, giving module="a", symbol="b.c" and a logged point of a.b.c. Lossless because both split sites are single splits.
- No consumer breakage from the schema change: nothing outside firing.py reads the removed `ts` field, and the single former use of the removed private `_fh` is migrated in tests/test_targets.py (`log._fh.close()` becomes `log.close()`). The `outcome` key is preserved, so the EX-01/EX-05 example parsers keep the field they rely on.

Disposition of the five review findings (2026-09-18 Opus 5 final review). None is a bug; all five were skipped, with the limit each one represents recorded here rather than left in a transcript.

1. Fork and duplicate-OFD precision. Both the record() comment and docs/firing.md say that closing the fd is what releases the flock. Strictly, flock releases only when ALL duplicate fds referring to the same open file description are closed, so a forked child holding an inherited fd would keep the lock alive past the parent's close. Skipped as a documented limit, not a defect: no supported path creates a duplicate OFD, since each instance does its own os.open (separate OFDs, which flock treats independently), dup is never used, spawn children open their own instance, and fork is refused outright by _refuse_if_wrong_process. The statement holds inside the documented scope. This belongs to the existing TASK-16 (LOG-03, log lifecycle including fork), whose AC #1 already covers repeated open/close without residual descriptors and inherited-lock behaviour under fork. Recorded here as a pointer only; no new task was created.

2. Firing-log write self-reentry. _write_all runs under a non-reentrant threading.Lock, so a rule that targets os.write and logs its own firing would block forever. Skipped because it is pre-existing and not introduced by this delta: the base at af561507 also held a non-reentrant threading.Lock across self._fh.write, so the hazard is byte-for-byte identical before and after. Explicitly noted for the parent: this one does NOT fit TASK-15 (attempt/outcome correlation) or TASK-16 (lifecycle and fork), so it currently has no owning task. It is recorded here so it is not lost; per the parent's instruction no new task was opened for it, and whether it deserves one is the parent's call.

3. A non-serializable `note` raises TypeError rather than FiringLogError. Skipped as unreachable from production: both call sites pass strings (actions.py:19 `note=str(rule.action)`, actions.py:84 `outcome=message`). Probe B additionally shows the failure is clean, happening before the lock, so no seq is consumed and the instance stays usable. That is better behaviour than wrapping, not a defect.

4. The literal "record() called on a closed FiringLog" appears twice (lines 174 and 198, the deliberate outside-lock and inside-lock double check). Skipped as cosmetic.

5. Irreducible async-interrupt window between self._finalizer.detach() and os.close(self._fd), in both the poison path and close(). A signal landing exactly there leaks the fd. Skipped as not closable in pure CPython without atomic primitives; probe F (30 poisoned instances, fd count 4 to 4) shows no leak in practice.

Read-only /simplify pass: no changes proposed. The primary/unlock_exc/close_exc triage in record() is long but every branch is load-bearing and individually pinned by a test. The closing `assert primary is not None` was checked and is sound rather than decorative: when primary is None the elif/else pair always assigns from an unlock_exc that the early return guarantees non-None, so `raise primary` cannot become `raise None` even under python -O.

Durable pre-patch backup of the MAIN checkout (not the candidate worktree), taken before any patch application: /home/pantinor/pyteman-evidence/2026-09-18-task14-mainckout-prepatch-155907/ with files/ (cp -a, byte-exactness verified with cmp for all six) and MANIFEST-pre-state.md recording per-file sha256, byte sizes, branch, HEAD and git status at capture. IMPORTANT for whoever applies the patch: the main checkout is NOT at the reviewed state. Four of the six files differ from the candidate (firing.py 5448 bytes in main versus 13254 in the candidate, plus test_firing.py, test_firing_multiprocess.py and docs/firing.md), while README.md and tests/test_targets.py already match. Applying round4.patch to main will overwrite an earlier working round in those four files, which is exactly what this backup preserves.

RECTIFICATION 1 of 2 (2026-09-18, Opus 5 session pyteman-opus5-verified): the refuted claim and the evidence that refuted it.

My verdict changes from APPROVED to CHANGES REQUESTED on exactly one point. Finding 3 in my earlier disposition (firing-log write self-reentry) was dismissed there as 'pre-existing, not introduced here; the base at af56150 also held a non-reentrant threading.Lock across self._fh.write, so the hazard is identical before and after'. That claim is REFUTED. The earlier note stays in place unedited so both the original reasoning and the evidence overturning it remain readable. Everything else in that disposition still stands.

Why the claim was wrong. I reasoned from the fact that both versions hold a non-reentrant threading.Lock across their write, and concluded the hazard was unchanged. That skipped the question that actually discriminates: whether the base's write path is REACHABLE by the patcher at all. It is not. The base wrote through self._fh.write on a TextIOWrapper, whose write and flush are implemented in C and reach the fd without ever performing a Python-level lookup of os.write. The candidate's _write_all (firing.py:77) calls os.write(fd, view) as an ordinary module-global lookup, which IS interceptable. A lock held across an unreachable call site cannot deadlock; a lock held across a patchable one can.

Evidence, run independently in this session rather than accepted on the parent's word. Both arms use the SAME patcher; the only variable is which firing module is loaded.
1. Mechanism probe. With os.write replaced by a recording spy: a TextIOWrapper write plus flush produced 0 python-level os.write calls; the candidate's raw-fd write loop produced 1. Base not interceptable, candidate interceptable.
2. End-to-end probe. activate([Rule(id='selfref', module='os', symbol='write', event='entry', action={'kind':'sleep','seconds':0})], log=log, modules=('os',)), then log.record(...), bounded by signal.alarm(3). Base (af56150 module loaded via git show and exec'd into a types.ModuleType): prints PATCHED then RECORDED ok, exit 0. Candidate (1d7db0de): prints PATCHED, then hangs, killed by SIGALRM, exit 142 (128+14). A genuine hang, not an exception.

Severity: this is a NEW regression introduced by this delta, in a fault-injection tool whose own documented examples inject on I/O paths, so os.write is a plausible user target rather than an exotic one. The failure mode is the worst available: no error, no timeout, a silently frozen process. It blocks publication. Proposed fix and test impact are in RECTIFICATION 2 of 2.

RECTIFICATION 2 of 2 (2026-09-18, Opus 5 session pyteman-opus5-verified): proposed minimum fix, test impact and required proof for the regression described in RECTIFICATION 1 of 2. NOTHING IS IMPLEMENTED; the parent session holds publication and this is a proposal only.

Root cause. The logger performs late-bound module-global lookups of the very callables a rule can patch, which puts the measuring instrument inside its own injection surface. The module ALREADY establishes early binding as its idiom for exactly this class of problem: self._flock, self._lock_ex and self._lock_un are snapshotted in __init__ (firing.py:129-131) and the finalizer captures os.close at construction (firing.py:135). The fix extends that existing idiom to the two callables still looked up late, and does nothing else.

Minimum fix, three edits:
1. In __init__, alongside the fcntl bindings, snapshot self._write = os.write and self._close = os.close.
2. Give _write_all a write parameter and pass self._write from record() (firing.py:229). _write_all stays a module-level function rather than becoming a method, so the existing monkeypatch of firing_module._write_all in the interruption test (test_firing.py:369) keeps working unchanged.
3. Replace the two remaining late-bound os.close(self._fd) call sites, in close() (firing.py:164) and in the poison path (firing.py:260), with self._close(self._fd). os.close is currently only PARTIALLY bound: captured by the finalizer, late-bound at both direct call sites, and a rule on os.close re-entering while close() holds self._lock deadlocks the same way.
os.open is deliberately left alone. It runs once in the constructor before any lock is held, so it cannot contribute to the no-hang invariant.

Invariant to hold: no rule targeting any callable the logger itself uses can make record() or close() block. A patched os.write must still intercept application code normally; only the logger's own captured references are immune. That asymmetry is the point, not a side effect.

Test impact, stated rather than glossed. Exactly one existing test breaks and must move, verified by reading the file rather than from memory: test_a_short_write_is_retried_until_the_whole_line_lands constructs the FiringLog at test_firing.py:256 and only then monkeypatches firing_module.os at :266, so an early-bound self._write would capture the real os.write and the test's len(calls) > 1 assertion would fail. Its monkeypatch must move ahead of the construction. Every other patch of firing_module.os already precedes construction (test_firing.py:219, :239, :284, :342, :458) and is unaffected, as is the multiprocess _short_write_writer, which sets firing_module.os before FiringLog(path). The interruption tests patch module-level _write_all and are unaffected by edit 2.

Proof required before this can return to APPROVED: a bounded regression test pinning the invariant, shaped like the suite's existing bounded helpers (_waitpid_bounded in test_firing.py, _join_all_bounded in test_firing_multiprocess.py) so that a reintroduction fails RED instead of hanging the runner. It should activate a rule on os.write whose firing logs to the same FiringLog, assert record() completes inside a hard bound, and assert that the logger's own write was not intercepted while application-level os.write still is. The harness that currently discriminates the two arms (exit 0 for the base versus exit 142 for the candidate, under signal.alarm(3)) is the shape that test should take; today it is a throwaway probe on temporary data, and it needs to become a committed test.

CORRECTION to RECTIFICATION 2 of 2, plus fix artifact (2026-09-18, Opus 5 session pyteman-opus5-verified).

RECTIFICATION 2 of 2 states that a rule on os.close 'deadlocks the same way' as os.write. That is wrong, and the earlier text is left standing as the record of the claim. The two failure modes are different and only os.write hangs. Challenged by the pyteman-17 reviewer and then verified here directly rather than accepted on either account: in close() and in the poison path, self._closed is set and the finalizer detached BEFORE os.close runs, so a re-entering record() refuses at its pre-lock check (firing.py:173) instead of blocking. Measured on the unpatched candidate with a rule on os.close active: close() raised FiringLogError('record() called on a closed FiringLog'), and os.fstat(fd) afterwards still succeeded on fd 4. os.close never executed, so the fd leaks with its safety net already disarmed. A leak and a misleading error, not a hang. The proposed snapshot fix is unchanged; only the diagnosis and the wording in the module docstring and docs/firing.md are corrected, and the regression test pins the closed fd with an os.fstat check rather than accepting a clean return.

Fix artifact, produced without any repository write (built against a copy under /tmp/t14fix, git apply --check -p1 passes, worktree untouched): /home/pantinor/pyteman-evidence/task14-reentrancy-fix.patch, sha256 b1f923b1971bffce7a3f4c389564f3107366d54692d1e378d42bd3e029bb9d37, with task14-reentrancy-fix.README.md beside it. 147 added, 11 removed, three files: src/pyteman/firing.py (1d7db0de to f3d3f1c5), tests/test_firing.py (8cea64db to e7aed469), docs/firing.md (81d400e0 to cdb59ee8). Application is the parent session's call under its own permissions; this session did not commit, push or edit the repo.

Evidence for the fix, run in the review venv with PYTHONPATH confirmed to resolve pyteman.firing into the patched copy. Patched: test_firing.py plus test_firing_multiprocess.py, 32 passed in 13.42s. Patched whole suite: 872 passed, 1 skipped, plus 7 test_packaging failures that are environmental rather than caused by the change, discriminated rather than assumed since the identical 7 fail with the unpatched source in the same incomplete tree; 872 + 7 = 879 = the 878-test baseline plus the one new test. The new test test_the_logger_does_not_instrument_its_own_io is a genuine detector, not a passing decoration: against the unpatched source it goes red at its bound with 'Failed: the child hung for 30s' and the child reaped with -9. It runs a bounded child interpreter (activate patches os process-wide, so doing it in-process would instrument pytest's own I/O for the remainder of the session) and asserts three things, the second of which keeps the first from being vacuous: a record() under a patched os.write logs only the marker rule; the same rules still fire for an application-level os.write and os.close on a scratch fd; and after close() with os.close patched, os.fstat on the log fd raises.

FINAL VERDICT: APPROVED (2026-09-18, Opus 5 session pyteman-opus5-verified). Read-only review of the delta only, as scoped by the parent: the runtime snapshot fix plus the exact test text already written, and the two test bugs the parent raised. No new full review, no /simplify fan-out, no source edit, no git mutation by this session.

Authorship provenance, stated exactly because it was mixed. The round-4 candidate (schema 1, run_id/instance/pid/seq, flock design, fork refusal, poisoning, docs/firing.md, the multiprocess tests) was authored in earlier Sonnet sessions. The self-instrumentation regression fix (early binding of os.write and os.close), its regression test, and every review round recorded on this task from the 'Final correctness review' note onward were authored by Opus 5 in session pyteman-opus5-verified. The two test defects corrected in patch revision 2 were found by the parent session pyteman-17's reviewer, not by me; I verified both against the source before accepting them. My own earlier APPROVED verdict and my 'os.close deadlocks the same way' claim were both wrong and were retracted in the RECTIFICATION and CORRECTION notes above, which are left standing rather than edited away.

Both reported bugs are confirmed resolved, each checked against the source rather than accepted on report. (1) The sleep rule now passes {'kind': 'sleep', 'ms': 0}; actions.py:28 reads rule.action.get('ms', 0) and rules.py:242 declares sleep as requiring ms, and because the child builds Rule directly instead of through load_rules, the previous 'seconds' key was silently absorbed by the 0 default. Sleep duration was 0.0 either way, so the earlier evidence was not invalidated; the defect was depending on a silent default rather than writing the declared schema. Re-proven after the change: the unpatched negative control still goes red with 'the child hung for 30s', so the rule is firing under the schema it now declares. (2) The close probe imports errno and re-raises anything that is not errno.EBADF instead of counting any OSError as closure; the patched run passing proves the stricter form is not over-strict, since os.fstat on the closed fd does raise EBADF.

Independent kill of the close defect, which the combined test cannot provide. In the combined test the os.write hang aborts the child before the fd assertion runs, so that assertion pins close() going forward but is never red-proven there. A standalone probe with a rule on os.close ONLY (no rule on os.write, so nothing can hang first and mask the result), same patcher in both arms and only firing.py differing: unpatched gives close() raised FiringLogError('record() called on a closed FiringLog') and fd 3 LEAKED with fstat still succeeding; patched gives close() raised None and fd 3 CLOSED (EBADF). Probe kept at ~/pyteman-evidence/t14-closeprobe/probe.py.

Parent's durable candidate verified rather than trusted: all six files at ~/pyteman-evidence/task14-final-z_kxgeb_/tree are byte-identical to my t14fix2 by cmp. Runtime f3d3f1c5, test_firing 334fd3e9, docs cdb59ee8; patch revision 2 sha256 0067b973aab37eb4ef0967144ba9083339b1d8ca430b47248212fe7c5d7ebc8e (revision 1 b1f923b1 preserved as a .bak, not overwritten).

The 880 vs 879 count is confirmed not a discrepancy, checked by diffing collected test ids rather than comparing totals: both trees collect exactly 880 identical ids, comm shows no id on either side only. The difference is one optional-dependency test, tests/test_report_escaping.py:526, whose skip reason is 'second renderer; not a test dependency'. It runs and passes in the parent's venv (880 passed, 0 skipped) and skips in mine (879 passed, 1 skipped). Same test set, same result. My run's rootdir was confirmed to be the patched tree with the new test collected there, so the green full suite is genuinely the patched code and not the worktree's.

Status deliberately stays In Progress. Not Done until CI is green on the published branch; a green local suite in two venvs is not CI. Application of the six candidate files is the parent's to perform under its own permissions. This session is frozen on TASK-14.

Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #77. Added lines already present on master per PR: #77 1/16=6% absentfiles=1. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.

Sub-item 14.2 closed 2026-09-29 by PR #189 (squash bf2bb61): firing._annotate and patcher._note consolidate into the dependency-free leaf pyteman._note.safe_add_note; the question is answered YES (consolidate), and the document-and-decline alternative (PR #125) is closed as superseded. The leaf guards the add_note call; format guards stay local to each consumer; the seam (argument must already be an exact str) is documented in the leaf. Superseded PRs #77 (the consolidation, rebased through the gate chain) and #125 both closed with pointers. TASK-14's own LOG-01 scope (identifying run, process and firing) remains open and untouched by this sub-item.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
LOG-01 pubblicato nella PR #4, merge b1a886d892bc020f3b7be545faa37449445a00bd. Identità run/istanza/processo/seq, append protetto e contratto documentato. Il 2026-09-18 verificati direttamente PR MERGED, review e commenti vuoti, CI 35359891183 con tutti i sei job success. Chiusura amministrativa dello stato rimasto In Progress, non nuova implementazione. gate-exempt: sola riconciliazione tracker di codice già pubblicato e verificato; nessuna modifica di codice in questa transizione. LOG-02 resta distinto e In Progress.
<!-- SECTION:FINAL_SUMMARY:END -->
