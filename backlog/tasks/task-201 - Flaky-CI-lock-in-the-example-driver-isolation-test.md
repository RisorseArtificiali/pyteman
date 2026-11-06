---
id: TASK-201
title: Flaky CI lock in the example driver isolation test
status: To Do
assignee: []
created_date: '2026-09-30 01:25'
updated_date: '2026-11-06 18:32'
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
<!-- SECTION:NOTES:END -->
