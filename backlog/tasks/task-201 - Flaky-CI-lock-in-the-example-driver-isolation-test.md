---
id: TASK-201
title: Flaky CI lock in the example driver isolation test
status: To Do
assignee: []
created_date: '2026-09-30 01:25'
updated_date: '2026-11-09 03:28'
labels:
  - flaky
  - test
dependencies: []
priority: medium
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Observed twice within an hour (PR #195 on 3.13, PR #196 on 3.11, 2026-09-30): tests/test_example_driver_isolation.py around line 548 intermittently fails on hosted CI runners with DRIVER-ERROR: unhandled OperationalError: database is locked, from conn.execute("PRAGMA wal_checkpoint(TRUNCATE)") in the run_repro driver. The rerun goes green both times. Both failing PRs were comments/test-only diffs, so it is unrelated to any recent change. The lock is between the driver's checkpoint and whatever else holds the database; worth either a busy_timeout/retry around the checkpoint or a serialization of the driver's connections, whichever matches the test's intent.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The wal_checkpoint TRUNCATE in the driver no longer intermittently deadlocks on CI
- [ ] #2 A comment or retry documents why the checkpoint can contend and what the recovery is
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Third occurrence 2026-09-30 (PR #197 on 3.12, after #195 on 3.13 and #196 on 3.11): the flake is hitting roughly every other PR, always the same wal_checkpoint(TRUNCATE) lock in the run_repro driver, always green on rerun. The frequency raises the priority of the retry or serialization fix.

Fourth occurrence 2026-09-30 (PR #204 on 3.11): same wal_checkpoint(TRUNCATE) lock, green on rerun. The flake is now hitting roughly every other PR across 3.11/3.12/3.13; the retry/serialization fix is overdue.

Fifth occurrence 2026-09-30 (PR #207 on 3.13, a different assertion site in the same driver family): same wal_checkpoint(TRUNCATE) lock, rerun pending. The flake now fires on roughly every PR; the fix (busy_timeout around the checkpoint, or serialising the driver's connections) is the top candidate for the next non-revival set.

2026-11-06: seventh occurrence found, and this one is on master's own tip. Check-run on 9d1314f (#214 merge, run 36762487415, job 110048303721, 2026-09-30 19:00-19:03Z): test (3.12) failed at tests/test_example_driver_isolation.py:230, driver exited rc=2 with DRIVER-ERROR 'unhandled OperationalError: database is locked' from PRAGMA wal_checkpoint(TRUNCATE) in run_repro.py main() line 307. Other matrix legs (3.11, 3.13, 3.14, quality) green; artifact and coverage skipped on that run. master has stayed in this state for five weeks because nothing ran the workflow since (no branch protection, no pushes). The old run cannot be rerun (>1 month limit); the first new PR's CI doubles as the freshness probe for whether the 3.12 leg is deterministically red or flaky.

2026-11-06 probe outcome: on PR #215 (head 4b9500a, workflow run 42269813568) test (3.12) PASSED together with 3.11/3.13/3.14, artifact and coverage. So the 2026-09-30 failure on master's tip is not a deterministic 3.12 break; it matches the flake's always-green-on-rerun signature. The fix remains wanted: the flake fires roughly every other CI matrix across all legs.

2026-11-08 occurrence 7: CI run 42487747728 (the TASK-203 push d06a14a, a refusal-naming delta that cannot reach sqlite), test (3.14) leg only, tests/test_example_driver_isolation.py:170: the hermes-111912 driver exited rc=2 with sqlite3.OperationalError: database is locked at run_repro.py:307 executing PRAGMA wal_checkpoint(TRUNCATE); the other three interpreter legs were green and the local 3.13 battery at the same sha was green. Same site as occurrences 1-6 (the driver's checkpoint under a still-held connection); failed job rerun requested to confirm transience.

2026-11-08 occurrence 7 outcome: the failed-job rerun went green (run 42487747728 completed/success, test (3.14) success), matching the flake's always-green-on-rerun signature across all seven occurrences. The fix (busy_timeout or retry around the driver's wal_checkpoint(TRUNCATE), or serialising its connections) remains wanted; the flake now fires on direct master pushes too, not only PR matrices.

2026-11-08 numbering correction (from the whole-project code review): the 2026-11-08 entries below were recorded as 'occurrence 7' but that number was already taken by the 2026-11-06 master-tip entry (occurrences 1-5 on 2026-09-30 PRs, 6 = the coverage-job hit recorded in TASK-191's set-23 notes, 7 = the 2026-11-06 master-tip run 36762487415). The 2026-11-08 run 42487747728 on d06a14a is OCCURRENCE 8; read the two 2026-11-08 entries with that number. Eight distinct failures recorded, every one green on rerun or on re-run of the identical push.

2026-11-08 candidate fix landed, task stays OPEN as a CI soak watch: commit 9f128ca changes the hermes-111912 rotation checkpoint to PRAGMA wal_checkpoint(PASSIVE), prints the result row at capture time and records it in the evidence manifest as checkpoint_row, so occurrence 9 (wherever it raises) reports its own state instead of a bare rc=2. The change is filed as a CANDIDATE, not a proven fix: the original causal story (TRUNCATE exclusivity raising despite the busy timeout) was refuted by the code-review's SQLite source reading (OP_Checkpoint converts SQLITE_BUSY to the result row in every mode; FULL/RESTART/TRUNCATE demote to passive after busy-handler exhaustion), so the surviving raise paths (extended busy codes from the wal-index read/recovery, mode-independent) remain possible on PASSIVE; the in-code comment says exactly this and names the falsification event. What the swap verifiably buys: PASSIVE never invokes the busy handler, so no stall at the checkpoint line where TRUNCATE could wait the full timeout for the exclusive writer lock and the reader drain; the copy invariant (nothing writes between the orphan's last commit and the rotation; a later commit would be lost by the sidecar unlink) is recorded at the site. Verdict rule for the soak: if the next runs stay green across several matrices, check AC1 and close; if occurrence 9 fires on PASSIVE, the swap is falsified as the fix and the investigation moves to the wal-index recovery path, with the printed checkpoint_row as the first datum.

2026-11-08 soak point 1: the first full CI matrix on a commit containing the fix (run 42513764442 on 2b306ac, which includes 9f128ca) is 7/7 green across all four interpreter legs, quality, artifact and coverage. The driver's checkpoint_row print does not appear in a green log because pytest captures the subprocess stdout and surfaces it only in a failing assertion's message, which is by design: the datum self-reports exactly on occurrence 9. More soak points needed before AC1 can be checked (the flake's historical rate was roughly one failure per two matrices).

Soak point 2 (2026-11-08 20:25Z): run 42520019870 green 7/7 (test 3.11/3.12/3.13/3.14, quality, artifact, coverage), master at 6c3cf1e with the PASSIVE checkpoint fix live. No occurrence 9. The next soak observations land on 70d0ea8 (TASK-85, test-only delta for this driver) and later heads.

Soak point 3 (2026-11-09): run 42544820313 on 3817ffe green 7/7 (all four interpreter legs, quality, artifact, coverage). This is the first completed matrix carrying the TASK-85 landing content (70d0ea8 plus markdown-only commits; the 70d0ea8 and e98a7e0 runs were cancelled as superseded by the rapid successive pushes, not failed). No occurrence 9. Soak points on the PASSIVE fix: 1 (42513764442), 2 (42520019870), 3 (42544820313), all green; the historical flake rate was roughly one failure per two matrices, so three clean matrices is approaching the threshold where AC1 can be checked; one or two more green matrices should settle it.

Soak point 4 (2026-11-09): run 42549329358 on cfa7fe0 (carrying the T211 landing cde29b7 plus tracker commits) green; conclusion success at the run level with the matrix completing. No occurrence 9. Four clean soak points on the PASSIVE fix (1: 42513764442, 2: 42520019870, 3: 42544820313, 4: 42549329358) against a historical flake rate of roughly one failure per two matrices: the candidate fix is holding well past the expected first failure. Next soak observations come with the T212 push and after.

OCCURRENCE 9 (2026-11-09T03:26Z, run 42556079855, job test 3.11, commit 0e80a41 which carries the T212 landing ec63fd1): sqlite3.OperationalError database is locked RAISED from run_repro.py:325, which IS the PASSIVE checkpoint line (the fix's own unpacking ckpt_busy, ckpt_log, ckpt_done), rc=2 through the __main__ wrapper, failing test_example_driver_isolation.py:170 and :529 in that leg. The pre-registered verdict rule FIRES: the PASSIVE swap is falsified as the fix. Two facts sharpen the investigation. First, the checkpoint_row datum the fix planted is ABSENT because the execute raised before any row existed, so the self-reporting instrument never got to report. Second, the RAISE itself contradicts the round-one model (OP_Checkpoint converts SQLITE_BUSY to the result row in every mode), which means the exception is probably not from the checkpoint op's busy conversion at all but from an adjacent step on the same line: statement preparation or the wal-index read under another process's shm contention, paths that return before OP_Checkpoint's conversion applies. T212 is exonerated by evidence: the local full suite ran green twice on this content (batteries mnx8wrgk..5ivdulv4 include test_example_driver_isolation), the delta touches no sqlite path, and the failure is the flake's signature (single leg, hosted runner only). Rerun of the failed job requested; every prior occurrence was green on rerun. Next per the task's own plan: the wal-index recovery path, and the instrument needs a rethink because the raise happens BEFORE the row exists: the try/except around the checkpoint itself, recording which adjacent step raised, is the fix direction for the instrument; whether PASSIVE should stay is now an open question rather than a claim.
<!-- SECTION:NOTES:END -->
