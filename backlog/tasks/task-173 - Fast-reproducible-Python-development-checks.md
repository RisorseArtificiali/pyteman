---
id: TASK-173
title: Fast reproducible Python development checks
status: Done
assignee:
  - pyteman-coordinator
created_date: '2026-09-22 10:44'
updated_date: '2026-09-25 10:58'
labels: []
dependencies: []
references:
  - /home/pantinor/.cc-mirror/zai/config/plans/eager-dreaming-petal.md
  - 'https://github.com/RisorseArtificiali/pyteman/pull/20'
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Deploy the approved minimal Python toolchain so local mechanical checks catch failures before agent review. Keep runtime behavior, existing release jobs and TASK-172 artifacts unchanged. Research and rollout approved in plans/eager-dreaming-petal.md. One focused tooling delivery, not a runtime modernization.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A fresh checkout can provision locked development dependencies without changing runtime package requirements.
- [x] #2 One documented local command runs lint, incremental type checks and metadata validation with meaningful failure exits.
- [x] #3 Targeted tests run with intended import identity and clean environment; full serial tests remain available.
- [x] #4 Repository-local hooks and CI run applicable checks without overwriting existing enforcement.
- [x] #5 Synthetic bad inputs prove lint, types, metadata and workflow validators fail; existing release validations remain intact.
- [x] #6 Research sources, measured timings, baseline limitations and daily commands are documented.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Consegna principale completata e integrata con PR20, merge1c2ae7c7ca1e0082e3b18d6310ac0d7d26f97dc5. Tooling uv/Ruff/basedpyright/prek/metadata/actionlint, dispatcher, documentazione e quality CI attivi. Runtime e precedenti job release preservati. Tutti i gate richiesti completati, APPROVED riferito alla patch pubblicata764003e4. I sotto-task173.1 e173.2 sono follow-up non bloccanti separati dalla consegna principale; il contenitore resta In Progress finché questi restano aperti. TASK-172 non fa parte del rollout pubblicato.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Configured pinned dev tools in pyproject and uv.lock on work/fast-python-tooling, .venv local only. Fresh env setup2.002s with existing uv cache; warm sync0.125s. Ruff E9/F green after removing3 unused imports and retaining intentional colliding-key fixture with line-specific noqa. Native basedpyright baseline14 entries, ordinary lock-mode check green and bytes unchanged; debt linked to TASK-40. Configured prek/actionlint and parallel quality CI; original test/artifact/coverage job bodies and runtime source verified unchanged. Hooks not installed yet; no commit/push.

Proving commands coordinator: full serial locked-env suite1190pass2skip in42.961s wall. Existing artifact driver returned1184pass8skip for each wheel/sdist with correct installed provenance; packaging self-build skips explicit. Coverage driver1189pass2skip1deselected and both child-only os._exit sentinels measured. Controlled validator probes reject undefined name(F821), malformed project.name, new type assignment, obsolete baseline(exit3), unknown action workflow key. All controls pass; baseline bytes unchanged. Evidence task173/validator-proof-2zu4oyzi and full-suite/artifacts/coverage.log. Warm checks lint0.018s types1.673s metadata0.392s all-file hooks0.329s. Dispatcher worker owns scripts/dev.py and scripts/tests/test_dev.py only, after real /clear5a2adda1; waiting on its permission prompts, coordinator did not approve or change permissions. Final dispatcher integration/review still pending.

Python3.11 minimum-version proof finished, task b9xy2ve0d exit0. Separate env at task173/env-311 provisioned from same lock; full suite1190pass2skip in21.33s; basedpyright lock-mode0errors. Main .venv remains Python3.14. Evidence python311-results.json and python311-*.log. Final dispatcher and complete-diff gates still pending.

Read-only comment review completed on added configuration/test comments by agent a394d2a6dcce8b71e. No actionable findings and no edits. Reviewer verified the deliberate F601 suppression with a counterfactual and retained the action version labels beside SHA pins. Cosmetic separator difference in the noqa comment accepted without churn; no behavior change warranted. This review excludes scripts/dev.py and scripts/tests/test_dev.py and does not substitute for their pending gates or the complete-diff final review.

Coordinator ran actual dispatcher chain on current draft: check succeeded, scripts/tests 53 passed in1.34s, both new files passed format-check; background bkajqwtow exit0 and full output read. Worker reports no permission blocker and its gates are running. Two coordinator test concerns sent for reconciliation within those gates, not a duplicate review: test_the_probe_matches_the_pytest_call replaces production identity function with a reimplementation; required-variable tests derive exclusively from the implementation tuple so removal may be invisible. These are review concerns awaiting disposition, not final verified defects. Complete-diff independent review still awaits stable file hashes.

Hash reconciliation after worker corrections: coordinator mechanically confirmed scripts/dev.py remains4ac64e107be91ca230ae26d32a471dd160812373ebc0124c38feaa150037bbf7, while test_dev.py changed from acceptance-run b969c3b51240d5f16ce60ab7035f6db270ad688e0d25ad68dda7e7816f61e6a2 to38a45dad0b81f99161bec1c9e7cd0ba4886aa8261f241e4c6d3f62562d5b9290. Prior53-test result is historical, not final acceptance. Worker reports both coordinator concerns confirmed by mutations, tests repaired,54 tests passing and15 original mutants plus3 targeted mutants caught. These are peer-reported results pending independent verification. Simplify still running, hashes explicitly not final. Coordinator will rerun once after frozen delivery rather than repeatedly against moving files. No hook installation or publication yet.

Worker interim post-simplify hashes4c67cd3a/fc5de98c,57 tests and17 mutants are not final; code-review high still running. Coordinator independently confirmed local lint scope gap with disposable fixture in task173/lint-scope-ao48_mjp/results.json: old src/tests/scripts command returned0 despite undefined name in examples; adding examples returned1 with F821; corrected control returned0. Decision: worker adds examples to DEFAULT_PATHS and explicit test expectations within owned files before freezing, and includes change in final reviewed state. Prek and CI already covered tracked examples, so no CI escape claimed.

Type checker src-only scope accepted as the deliberate approved gradual rollout, not a new defect requiring another typing migration. docs/development.md now explicitly distinguishes Ruff's code scope from basedpyright's src-only scope. Test/script/example types are not certified by a green check. Reported test-file typing errors were fixed by worker; no broadened baseline or runtime refactor authorized.

Worker frozen handoff received, hashes independently confirmed before integration: dev.py43275a56 and tests4b03dfde. Full dispositions read from task173-dispatcher/delivery-evidence.md. Simplify seven items: applied shared tool stubs, required cleaned env, simpler path.parts access, stripped Ruff output; declined guard hoist, two symlink setup unifications and trivial fixture extractions with recorded reasons. Code review seven items: applied four missing coverage-variable tests, resolved installed-package predicate and expectations, executable Ruff skip predicate; declined unconfirmed sibling-resolving venv layout, environment omission already fixed; Windows handling deferred to coordinator. The review snapshot was old, so complete-current-state review is mandatory before approval.

Coordinator dispositions: no generalization of existing run_coverage.py/verify_artifacts.py environment triples in this scoped tooling task. New dispatcher POSIX limitation explicit in docs, no claim that CI platform alone establishes runtime support. Worker reported source-only LSP scope accepted by plan, and example lint gap closed with config-driven Ruff dot scope. Coordinator found user-facing error incorrectly suggested format-check for linting; corrected to uv run --locked ruff check <paths> before freezing final artifact. New untracked .coverage* files observed and left untouched pending worker provenance confirmation. No hook activation or publication yet.

Final coordinator acceptance completed exit0 on frozen complete14-file patch e4b958ad0aae33943d0771cbe6278a9e474922d2bb9ec1f4b89d6c14f2e2b2e8. Full bc3pnt9x3 output read: check green; tooling78pass0skip on Python3.14 and3.11; both new files format-clean; full package1190pass2declaredskip; hooks on all14explicit delivery files green. Before/after hashes unchanged for every command. Evidence task173-final-wlcx9lwg/acceptance.json and command logs. Independent final review assigned after verified /clear9360af96, still pending. Hook activation, commit and publication remain gated.

Coverage residue provenance resolved without changing delivery: worker attributes .coverage plus29 .coverage.bird.* files to its own and gate-agent probes. Coordinator inspected all30 SQLite files read-only; plain file lists only scripts/dev.py, other29 each list16 source files. Transcript/timestamp attribution remains peer evidence, not independently re-derived. No files deleted or moved. Suggestion to change .gitignore declined for this frozen delivery: hiding probe residue is not required to deploy the checks. Keep environment guarantee narrow: child_env cleans child processes but cannot undo coverage that was activated before dispatcher startup. No additional review cycle or code edits requested.

Digest-history correction independently proved: worker's latest claim that43275a56 was a transcription error is REFUTED. That digest was correct at handoff. Coordinator's recorded one-message correction from format-check to actual ruff check guidance produced68eafa4f before freezing. Reversing only that edit in memory reproduces43275a56f3cffaa255ed0e0c4d036abbde80ac98a30e2dfef9b3eeaa535bc0ac exactly. Current repo and frozen tree match final manifest68eafa4f/4b03dfde. Acceptance and reviewer already use the correct current hashes; no re-pin or test rerun needed. Matching copies and mtimes do not prove absence of prior edits. Worker notified to correct evidence; no code files modified in this reconciliation.

Independent final review report read at task173-review-ind9360af/FINDINGS-AND-VERDICT.md: APPROVED on e4b958ad and exact14hashes, but mandatory code-review high child still pending. Approval alone does not satisfy gate; no hook install, commit or publication. Reviewer instructed to relay actual child completion event, no restart/duplicate reviewers/polling. All recommendations dispositioned: F1/F3 tracked TASK-173.1; F6 tracked TASK-173.2 with timing labeled reviewer-only; F2 contradiction REFUTED from frozen docs5-8 already explicitly limited to Git checkout, does not claim guide itself omitted; reviewer notified; F4 check --help refusal accepted; F5 uv-from-PATH documented launcher trust accepted. Reviewer acknowledged all operational workflow commands and boundaries.

Mandatory code-review high returned on e4b958ad; updated final report read. Four nonblocking findings dispositioned: F1/F6 duplicates tracked; new F7 baseline cleanup precondition added to TASK-173.1; F6 dangling-symlink copy failure added to TASK-173.2; F8 noqa separator accepted as harmless. Fresh coordinator check78tooling1190project2skip passed. Local prek hook installed after verifying no prior hook or hooksPath; all14sample hook hashes preserved. All-file hooks pass. Staged14file patch exactly matched e4b958ad.

Precommit git diff --cached --check refused extra terminal blank lines in research report; no commit created. Removed only2extra newline bytes, preserving13other file hashes. New publication patch764003e4232b30e3a693f456f0925b6ab297cf51a9393e5fba63056f4e9c04be; updated manifest in task173-final-wlcx9lwg/publication/. Old frozen evidence unchanged. Reviewer asked only for mechanical approval extension, no new gate or agents. All source code unchanged. Hook active locally; publication not yet done.

Publication complete as open PR20 https://github.com/RisorseArtificiali/pyteman/pull/20, branch work/fast-python-tooling, commit3b9120dd16851fe7be2a8989f3fc06e8fffe5488. Reviewer mechanical approval extension to publication patch764003e4 read from actual terminal,14file reconstruction verified. Installed local hook invoked successfully by real commit, unchanged14sample hooks and hooksPath. Fresh prepush check and78tooling tests passed. GitHub PR prose audited with /pstack:unslop, hook-required declaration satisfied without bypass. CI completion/merge pending; do not mark rollout fully landed yet.

Verifica finale dopo merge: PR20 MERGED, head approvato3b9120d integrato a1c2ae7c. CI della PR35751295475 e CI master35751799761 entrambe SUCCESS su quality, test3.11/3.12/3.13/3.14, artifact e coverage. Risultati recuperati da GitHub e output watcher letto. Checkout locale master uguale al merge,14hashes corrispondono alla consegna pubblicata e untracked preservati. uv sync --locked, dev.py check,78tooling tests e prek --all-files passano sul master integrato. Hook locale attivo, configurazione globale non modificata. Istruzioni operative consegnate e confermate dai due coding agent. Consegna principale terminata; nessun lavoro ulteriore avviato sui follow-up.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Closed 2026-09-25 by backlog audit. PR#20 (locked Python tooling and fast checks) and PR#21 (local candidate delivery workflow) both merged, CI green. Sub-tasks TASK-173.1 and TASK-173.2 remain open as separate items. Code published in v0.2.0.
<!-- SECTION:FINAL_SUMMARY:END -->
