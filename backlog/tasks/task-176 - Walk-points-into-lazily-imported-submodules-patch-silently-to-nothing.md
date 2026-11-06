---
id: TASK-176
title: Walk points into lazily-imported submodules patch silently to nothing
status: Done
assignee:
  - pyteman-coordinator
  - pyteman-backlog-audit
created_date: '2026-09-25 10:13'
updated_date: '2026-09-26 15:18'
labels:
  - patcher
  - fail-closed-breach
  - confirmed
dependencies: []
references:
  - src/pyteman/rules.py
  - src/pyteman/patcher.py
  - src/pyteman/sitecustomize.py
  - README.md
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Filed by the ccgram session (user-delegated) after a three-experiment discrimination on 2026-09-25. A rule whose point walks into a submodule that imports AFTER activation loads fine, activation reports success, and the callable is never wrapped: zero firing records on direct calls, no __wrapped__ on the leaf, no refusal, no log line. Point specs are module-first-dot plus attribute walk (rules.py documents this as the way to reach anything inside a package), so every dotted point into a lazily-structured package hits the silent path.

Repro matrix, all via sitecustomize activation with PYTEMAN_RULES set and the log opened, no refusal printed: shutil.rmtree (flat) fires with start and end records; os.path.join (nested walk, submodule eagerly present when os imports) fires; ccgram.window_state_ports.identity_state.accepts_provider_observation and ccgram.session_map._creation_in_flight (module ccgram, walk through submodules the package does not import eagerly) produce zero firings with the leaf unwrapped, called directly after explicitly importing the leaf module.

Mechanism hypothesis to verify in patcher.py and sitecustomize.py: the import hook attempts the attribute walk when the rule's module first imports; the lazy submodule is not there yet; the miss is dropped, or re-armed only against the top module's own later imports, instead of being re-armed for the submodule's import; nothing reconciles still-pending rules. This breaches the README's bold fail-closed activation contract: a requested rule that wrapped nothing is a failure that went quiet.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Discriminating tests reproduce the three matrix rows: a flat point fires, an eagerly-imported nested walk fires, and a lazily-imported nested walk fires once the submodule imports after activation.
- [x] #2 A rule whose walk target never lands is reported loudly, at minimum a stderr line in the refuse-phase style, at interpreter exit or via an explicit pyteman status surface.
- [x] #3 A walk miss at patch time is re-armed against the first attribute segment's own module import, not only against the top-level module's later imports.
- [x] #4 README and rules documentation updated wherever the fix changes the documented skip-silently carve-out for absent attributes, with no promise the code does not keep.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Coordinator reproduction completed 2026-09-25, evidence /home/pantinor/pyteman-evidence/task176-repro/. Own fixture victimpkg (submod lazy, eager imported by __init__), sitecustomize activation via PYTHONPATH src:src/pyteman, PYTEMAN_RULES, PYTEMAN_LOG. Results: flat shutil.rmtree FIRES (2 records); eager-nested victimpkg.eager.eager_fn FIRES (2 records, return overridden to 0); lazy-nested victimpkg.submod.leaf: call 1 after explicit submodule import returns ORIGINAL 7, ZERO firing records, no refusal, no stderr line (defect reproduced); after a SECOND top-level `import victimpkg` by name the same rule suddenly fires (2 records). The rule is not dropped permanently: it is silently skipped and reconciles only if a module named exactly rule.module imports again after the submodule exists.

Root cause verified statically: patcher.py _patch lines ~1963-1970, the symbol walk miss does a bare `continue` with no pending record; install_hook's closure (~2680-2686) retries only when a module named exactly rule.module imports, so the lazy submodule import never matches. README documents the skip carve-out (README.md:44-49) and docs/rules.md 'Checked later, by design' carries the deferral set; both must change with the fix (AC4).

Implementer delivered on branch work/lazy-walk-rearm (PR #23, 923a2be, CI 7/7 green): pending registry keyed on the missing segment's module, hook drain by exact key match, pending() surface, atexit never-landed report, docs updated. Delivery report task176-impl/delivery-report.md with gate dispositions (6 findings: 4 fixed, 2 justified skips).

GAP ROUND (ccgram probe + coordinator reproduction, evidence task176-gap/): dotted-first import stays totally silent. `import victimpkg.submod` as the FIRST import of the package: 0 firing records, 0 stderr, original return value, in BOTH a PYTHONPATH shape and a real editable-install venv (so the resolution mechanism is a red herring). Control rows on the same tree: a later by-name `import victimpkg` reconciles (2 records), and `from victimpkg import submod` fires immediately because the fromlist form passes the TOP name to __import__.

Gap mechanism verified: builtins.__import__ receives only the full dotted name; parent packages load inside importlib._bootstrap without re-entering builtins.__import__, so _patch(top, top) never runs, the rule-module filter skips the rule, no pending entry is ever created, and the atexit report has an empty set. force_patch_module skips absent modules at activation (mod is None branch), so activation does not close it either.

Decision: fix under TASK-176 before merge; AC1 covers this row and it is the natural import shape of any src-layout consumer. Fix direction: hook prefix processing, _patch each parent prefix of a dotted import name (shortest first, filtered to rule modules and pending keys or justified otherwise), so the walk miss creates the pending entry and the existing drain on the child name lands it in the same import. PR #23 stays open, additive commits.

STATUS REVERTED to In Progress by coordinator: the Done marking and Final Summary were recorded before the gap round. AC1 and AC2 are falsified in the dotted-first import shape (first import of the package is `import pkg.submod`, no by-name top import): the rule never fires AND the never-landed exit report stays silent because no pending entry is ever created. Evidence task176-gap/, both PYTHONPATH and editable-install shapes. The branch work/lazy-walk-rearm remains open as PR #23; the gap fix lands as additive commits on the same branch before any merge.

MERGED: PR23 fa6ac68, post-merge CI 7/7 success, local master ff'd and verified (suite 1206/1 with the pandoc skip absent on this host; total collected unchanged at 1207). Stale coordinator-delta.diff regenerated as git diff 217f342..aea6805 (220 lines) per r3 informational finding 1; my worktree removed, branch deleted. Local checkout had been left on branch work/task-101-verdict-data by another agent (commit 837f0be, untouched, branch preserved); master was clean to ff. Suite verification initially failed with Disk quota exceeded: the packaging fixture copied five sibling worktree venvs (337MB each, another agent's parallel backlog work) into tmp; relieved by clearing pytest/artifact residue; root cause is TASK-173.2's scope, noted there. ccgram pane w1E:p1 notified with install guidance and follow-up pointers.

Downstream verification by the ccgram session on merged master fa6ac68, against the real ccgram tree in its own venv, no by-name import anywhere: both walk shapes fire with start+end records purely from submodule imports (one-level ccgram.session_map._creation_in_flight, two-level ccgram.window_state_ports.identity_state.accepts_provider_observation), flat control fires, and a rule on a nonexistent module is named on stderr at exit with exit code 0 while the three live rules fire. External confirmation of AC1/AC2/AC3 on the consumer that filed the task. The original motivating incident was fixed independently upstream (ccgram PR #283), so the instrumentation capability is banked for their next use: reproducing a 7-hour per-user delivery queue freeze with zero log lines, a barrier/kill interleaving case. No action owed until they return with a ruleset.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Fixed the fail-closed breach where a rule whose point walks into a lazily-imported submodule patched silently to nothing. Merged as PR #23, squash commit fa6ac68d3579bbb6e64b43fcddc85fdd3ed334e9; post-merge CI green on all seven jobs; local master fast-forwarded and re-verified (check clean, suite 1206 passed 1 host-dependent skip on the merged bytes).

Three rounds on branch work/lazy-walk-rearm. Round 1 (923a2be): pending registry keyed on the missing segment's module, hook drain, pending() surface, atexit never-landed report in sitecustomize, docs. Round 2 (217f342): parent-prefix processing so a dotted-first import patches rule modules; closed the ccgram-reported gap where editable-install consumers never imported the top module by name. Round 3 (aea6805): pending made total (seeded at construction, popped only at existing-leaf confirmation, guarded re-key, drain retries without deleting), after the coordinator falsified the r2 review's own leaf-typo reproduction and two in-session gate rounds found the drain-deletion and resurrection holes; four subprocess-real regression tests added.

Verification: independent r2 APPROVED on 217f342 (six non-blocking findings filed as TASK-177) and independent r3 delta APPROVED on aea6805 with 14 invariants traced, mutation testing proving each of the four new tests discriminates, and a structural no-false-positive/no-false-negative argument; coordinator reproduced all rows in both PYTHONPATH and editable shapes. Final suite 1205 passed 2 declared skips at aea6805; 1206/1 on merged master (pandoc skip is host-dependent). Reports: task176-review-r2/ and task176-review-r3/FINDINGS-AND-VERDICT.md.

Residual limits, all filed and non-blocking: TASK-177 (pass-2 pop-without-apply windows including the two _ABSENT skips and the swallowed-import shape, None-vs-_ABSENT sentinel, atexit guard, O(pending) matched scan and per-import retry cost), TASK-173.2 (packaging fixture copies nested worktree venvs, amplified to a tmp quota failure during this verification). The ccgram session was notified and will rerun its instrumentation probe; its use case (dotted-first points into lazily-structured packages under an editable install) is the shape now covered end to end.
<!-- SECTION:FINAL_SUMMARY:END -->
