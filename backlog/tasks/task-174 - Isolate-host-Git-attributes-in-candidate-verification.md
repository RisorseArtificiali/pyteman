---
id: TASK-174
title: Isolate host Git attributes in candidate verification
status: Done
assignee:
  - pyteman-coordinator
created_date: '2026-09-22 20:01'
updated_date: '2026-09-26 23:19'
labels: []
dependencies: []
references:
  - >-
    /home/pantinor/pyteman-evidence/task172-integration-review-k8w3p2qn/PROBE-EVIDENCE.md
  - .claude/skills/pyteman-delivery/verify_candidate.py
  - .claude/skills/pyteman-delivery/SKILL.md
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Follow-up from TASK-172 final integration review I1/I2. Setting GIT_CONFIG_GLOBAL and GIT_CONFIG_SYSTEM to os.devnull does not suppress global attributes files under HOME or XDG. Reviewer reproduced CRLF rewriting and export-ignore omitting a tracked file. These are reviewer-verified probes; coordinator has read the evidence but has not independently repeated these new probes. Runner hashes only exported files, so an omitted non-test file is not necessarily caught. Scope a minimal isolation policy and precise documentation, retaining repository-local attributes as explicitly trusted or explicitly rejecting them. Do not present current runner as full Git isolation.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A host global attributes file cannot rewrite candidate bytes or omit tracked files from the export; a control demonstrates those effects without the guard.
- [x] #2 HOME and XDG discovery routes are exercised without changing actual user or system files.
- [x] #3 The skill accurately states which repository and host attributes remain trusted and what is not isolated.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
High-effort in-session review of the final delta (2026-09-27): verdict CLEAN, nothing blocks merge; every suspicion probed against git 2.55.0 and cleared (sweep-before-injection order proven, so the diff's own GIT_CONFIG_* keys survive and hostile inherited collisions are overwritten; env-config precedence over repo-local core.attributesFile confirmed by a three-arm probe; XDG route-table choice confirmed word-for-word against gitattributes(5); no missed attribute route exists beyond the trusted repo-local ones; committed_repo ambient leaks neutralized; no vacuous pass in either outcome test; main suite never invokes git; master drift conflict-free). Three note-level observations, filed: (1) no runtime guard for pre-2.31 git, documented floor, hardening option recorded (a one-line git config functional check in verify()); (2) ATTR_ISOLATION_KEYS duplicates clean_env internals, self-diagnosing because the host arms assert hostile attributes DO fire; (3) data.txt is committed but unasserted, doing real work keeping the host archive non-degenerate; do not simplify it away.

Merged-state note: commit 98930bd on branch work/task174-git-attr-isolation (rebased onto ad0a8ee), PR #143, delivery skill suite on the rebased tree 35 passed 47 subtests.

Independent review (2026-09-27, task174impl/review/FINDINGS-AND-VERDICT.md): APPROVED at 98930bd. 12 invariants traced, 0 broken; probes covered export-ignore and CRLF with live controls on both routes, hostile inherited GIT_CONFIG_COUNT/GIT_ATTR_SOURCE swept before the isolation keys are set, export-subst via host attributes, and stale documentation of the old boundary (none found). One info observation: the GIT_ATTR_NOSYSTEM arm has no live control anywhere (placing a system attributes file needs root and no env var redirects its path); verification rests on the attr.c source mechanism plus the absence of /etc/gitattributes on this host; inherent to the arm, no action recommended.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Merged as 9831da9 via PR #143 (squash of 98930bd, byte-identical content confirmed by the post-merge code-reviewer pass), master CI green, local master fast-forwarded. Gates: /simplify 4-angle findings applied; in-session high review CLEAN; independent review APPROVED at 98930bd (12 invariants); post-merge belt CLEAN with live git 2.55.0 probes on both discovery routes and the repo-local precedence scoping; all observations filed in these notes.
<!-- SECTION:FINAL_SUMMARY:END -->
