---
id: TASK-153
title: Startup refusal test re-implements assert_refused from test_sitecustomize
status: Done
assignee: []
created_date: '2026-09-17 11:12'
updated_date: '2026-09-30 01:36'
labels:
  - audit-2026-09-16
  - opus-5
  - reuse-gate
  - task-3-followup
  - tests
dependencies: []
references:
  - 'tests/test_activation_suspendable_startup.py:96-109'
  - 'tests/test_sitecustomize.py:94-103'
  - 'tests/test_sitecustomize.py:215'
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Reuse gate on TASK-3, 2026-09-17.

tests/test_activation_suspendable_startup.py lines 96-99 and 106-109 hand-write what tests/test_sitecustomize.py line 103 already provides. assert_refused(r, phase, *needles) carries exactly these three assertions with the same failure messages, plus a needle loop that lines 106-109 unroll into three separate `assert x in r.stderr` calls. Line 94 of that file also defines refused(tmp, env_extra), the run-expecting-failure wrapper re-spelled here.

The direct precedent is test_sitecustomize.py line 215, test_unpatchable_point_refuses, the same test shape for the same phase. Cross-module import inside tests/ is established: tests/conftest.py puts the directory on sys.path and three files already import from integrity_corpus.

Cost: the invariant that exit 2 and a silent stdout must hold together now has two copies, and only the test_sitecustomize.py one carries the reasoning for why they are asserted together. The documented prefix at docs/rules.md line 12 now needs edits in two test files.

OWNERSHIP CAVEAT, decisive for how this is done. tests/test_sitecustomize.py belongs to agent pyteman-runner-opus5. Importing a helper out of a file another agent owns creates a coupling neither side can see: a rename there breaks this file with no local signal. Either the helper moves to a shared location both owners agree on, or this stays duplicated on purpose with a comment saying why. Do not resolve by importing across the ownership line without that agreement.

Not the same as the already-filed rules_file and run_py duplication, which names only those two functions. assert_refused and refused are the higher-value helpers and are separate.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 La duplicazione e' risolta senza importare da tests/test_sitecustomize.py senza accordo esplicito con pyteman-runner-opus5: o l'helper si sposta in una sede condivisa, o resta duplicato con un commento che dice perche'.
- [x] #2 Se resta duplicato, il commento cita il file proprietario e il motivo, cosi' il prossimo lettore non lo rifattorizza a sua insaputa.
- [ ] #3 Il prefisso documentato 'pyteman: refusing to start: <phase>:' resta asserito in entrambi i file oppure in una sola sede raggiungibile da entrambi.
- [ ] #4 La suite passa e l'invariante exit 2 con stdout silenzioso continua a essere asserita insieme, non separatamente.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened 2026-09-28 (TASK-191): the tracker said Done, but the change never reached master (f2a4ea3). Open, unmerged PRs: #90 #122. Added lines already present on master per PR: #90 0/6=0%  #122 2/22=9%. No merged PR names this task and the master log does not mention it, so any Final Summary above describes an unmerged PR, not a merge. Acceptance criteria unchecked for the same reason.

Code review of the revival (2026-09-30): the deeper follow-up, needing the owner agreement TASK-153's caveat requires before it can displace the local copy, is placing the refusal helper in tests/startup_harness.py, the shared module this very file already imports and that #149 created to retire near-identical copies kept apart by the same ownership reservation. That would give the exit-2-plus-silent-stdout invariant a mechanical link instead of a prose one, so a contract change cannot drift between the two suites unnoticed.

Merged 2026-09-30 via #196 (8ac507e). The soft-reset squash lesson: the prek hook's unstaged-changes notice is load-bearing; an amend after add is the recovery. Evidence under /home/pantinor/pyteman-evidence/t191/: diff153.patch sha256 7b13d081, tree153-hold3.sha256, VERDICT-153*.md in t191rev.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed by PR #196, squash-merged as 8ac507e on master at 2026-09-30 01:35Z. AC1: the duplication is resolved without importing across the ownership line, by a local _assert_startup_refusal helper carrying the exit-2-plus-silent-stdout-plus-phase-prefix protocol and the needle loop; master's two subset needles are folded in and the names-the-rule test gains the phase-prefix assertion. AC2: the helper's comment names the owner file (test_sitecustomize.py), the ownership-line reason, TASK-153 and the driver-isolation namesake with its different protocol, so the next reader copies the right helper; the fail-open rationale lives once, at the helper. The deeper follow-up (the helper's natural home being startup_harness.py, which needs the owner agreement the caveat requires) is recorded on this task. Supersedes #90 (comment-only) and #122 (this content, rebased); both closed with pointers. Gates at 1d9930b: suite 1528 passed 2 skipped, check green, delivery 41, no battery (test-only refactor with one suite-certified addition), code-review high six findings applied, independent verdict REJECTED at the first head for a wrong-artifact defect my squash introduced (the commit carried the pre-fix index; the reviewer demonstrated the patch/hold split), then APPROVED after the amend (VERDICT-153.md, VERDICT-153b.md). One CI flake (the same sqlite wal_checkpoint lock filed as TASK-201) was rerun green.
<!-- SECTION:FINAL_SUMMARY:END -->
