---
id: TASK-175
title: Define candidate verification for foreign-owned repositories
status: Done
assignee:
  - pyteman-coordinator
created_date: '2026-09-22 20:01'
updated_date: '2026-09-28 23:47'
labels: []
dependencies: []
references:
  - >-
    /home/pantinor/pyteman-evidence/task172-integration-review-k8w3p2qn/PROBE-EVIDENCE.md
  - .claude/skills/pyteman-delivery/verify_candidate.py
priority: low
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Follow-up from TASK-172 integration review I3. Removing user/system Git config also removes protected-scope safe.directory allowlists. The runner therefore refuses foreign-owned repositories at rev-parse even when an operator whitelist allowed them. This is fail-closed, not false certification. Reviewer verified with Git's different-owner test mode and controls; do not imply an actual foreign owner was reproduced by coordinator. Decide whether to keep the restriction with clear documentation or support an explicitly authorized exact repository. Never inject safe.directory=* or accept repo-local self-grants as a convenience fix.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The supported ownership policy is explicit in the runner documentation and failure message.
- [x] #2 If an opt-in is introduced, it is limited to the explicitly selected repository and does not accept arbitrary foreign-owned repositories or repo-local self-grants.
- [x] #3 Controls verify normal same-owner operation and fail-closed behavior outside the chosen policy.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Reopened by TASK-191 (2026-09-28): PR #124 never merged. It now conflicts with #143 in SKILL.md, and it adds --trust-repo to the canonical verify command, which turns the opt-in on for everyone who copies that command. Plan: rebase #124 onto master, resolve SKILL.md, keep the flag out of the canonical command and document it as a separate opt-in, then run the gate chain.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Merged as PR #184 (squash 10f0f12 on master), which replaces #124 (closed with a pointer). --trust-repo appends one safe.directory entry for the resolved --repo path through GIT_CONFIG_COUNT, never the wildcard, and stays out of the canonical command. Without the flag a foreign-owned repository is refused before any evidence is created, with a message naming the flag; with the flag and a refused grant the message says it was not honored (git older than 2.38, or --repo not the root) and keeps git's text. The preflight rev-parse runs under LC_ALL=C so a translated refusal is still recognized. Gates at 1bc0fe9: 41 delivery tests, full suite 1436 passed plus 2 known skips, dev.py check, 12 of 12 mutants killed, /simplify, high-effort code review (3 findings fixed), independent reviewer APPROVED at 1bc0fe9 (VERDICT175.md; F2 filed as TASK-193, F3 withdrawn), CI green on all six jobs. Foreign ownership simulated with GIT_TEST_ASSUME_DIFFERENT_OWNER, no real second OS user; the 2.38 floor rests on git docs at v2.37.0/v2.38.0, no old git run.
<!-- SECTION:FINAL_SUMMARY:END -->
