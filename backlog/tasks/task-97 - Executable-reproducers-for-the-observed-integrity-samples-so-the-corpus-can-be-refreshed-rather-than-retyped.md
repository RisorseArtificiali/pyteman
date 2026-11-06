---
id: TASK-97
title: >-
  Executable reproducers for the observed integrity samples so the corpus can be
  refreshed rather than retyped
status: To Do
assignee: []
created_date: '2026-09-16 23:43'
updated_date: '2026-09-28 18:16'
labels:
  - audit-2026-09-16
  - sqlitekit
  - tests
  - tooling
  - deferred-from-task-24
milestone: m-3
dependencies:
  - TASK-24
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The observed samples in tests/integrity_corpus.py are captures, and no corrupt database is versioned, so docs/integrity.md prose is the only route back to them. That is deliberate and was the right call for TASK-25, but it leaves the claim "reproduced here" resting on a procedure a human has to follow by hand, on a SQLite whose version is not pinned. A wording change in a future SQLite would be discovered by someone reading an incident report rather than by the repository.

Proposed direction: an executable reproducer per observed sample, following the shape already established by examples/hermes-111912 and examples/hermes-109966, which build their damaged state from scratch and report what they observed. Each one damages a scratch database, captures the integrity_check output, and diffs it against the corpus text. The output is a table of sample name, host SQLite version, and matched or diverged.

This is deliberately NOT a suite gate. The messages are SQLite's and the host version is whatever is installed, so a divergence is news about SQLite rather than a defect in this repository, and turning it into a red test would make the suite fail on an upgrade nobody made here.

Raised by the altitude review of TASK-24 and deferred: it is new tooling rather than a correction, and TASK-24's perimeter is the classifier.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 a runnable script reproduces each observed corpus sample from an empty database on the host SQLite
- [ ] #2 the script reports per-sample whether the captured text matched the corpus byte for byte
- [ ] #3 the document's reproduced-here column is derived from that run rather than asserted in prose
- [ ] #4 a sample that no longer reproduces is reported as such instead of failing the suite, because the host SQLite version is not pinned
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #130. Added lines already present on master per PR: #130 0/480=0% absentfiles=2. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
PR #130: `examples/integrity-corpus/run_repro.py` reproduces all 22 observed corpus samples from fresh databases. Output is a table of sample name, SQLite version, and match result. Normalizers handle version-dependent addresses and wording. `docs/integrity.md` references the script. Not a test gate; divergence is informational. Gates: /simplify (3 agents, applied), tests 1191 passed, /pa:reflect READY.
<!-- SECTION:FINAL_SUMMARY:END -->
