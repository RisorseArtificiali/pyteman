# Reproducer: premature SIGKILL during `hermes update` orphans WAL holders (#111912)

Deterministic reproducer for [NousResearch/hermes-agent#111912](https://github.com/NousResearch/hermes-agent/issues/111912):
a manually-run dashboard is SIGKILLed by the update's stop sequence while its
ui-tui descendant is still tearing down, the descendant is orphaned holding the
`state.db-wal` inode, and the next startup raises the guard
`FATAL DeletedWalGenerationError`.

The race window (descendant teardown duration vs the SIGTERM-to-SIGKILL grace)
is pinned by pyteman instead of being timing luck: a rule sleeps at
`tui_child.graceful_shutdown` entry for a fixed time, and the driver runs the
REAL upstream functions, not mocks:

- `hermes_cli.dashboard_procs._kill_pids_posix` (the actual SIGTERM, grace, SIGKILL sequence)
- `hermes_state_dbfile.refuse_deleted_wal_generation` (the actual /proc holder scan and refusal)

## Files

- `tui_child.py`, `dashboard_sim.py`: the process tree (ui-tui descendant holding the sidecars; parent forwarding SIGTERM and waiting).
- `rules-slow-teardown.yaml` (scenario A, 5s pin): between base's 3.0s grace and the 10-12s grace of the open fix PRs, so it discriminates base from fix.
- `rules-wedged-teardown.yaml` (scenario B, 30s pin): past every proposed grace, so it shows a grace bump narrows the window but never closes it.
- `run_repro.py`: the driver; verdict lines are machine-greppable.

## Run (Linux only, enforced)

    pip install pyteman
    python3 run_repro.py <hermes-agent checkout under test> rules-slow-teardown.yaml REPRODUCED

The third argument is the expected verdict (REPRODUCED or CLEAN); the driver
exits nonzero on mismatch, so a scenario that stops discriminating after an
upstream change (for example a grace raised past scenario A's 5s pin) fails
loudly instead of reading as a pass. The driver also hard-fails off Linux (the
upstream holder scan is a no-op there, which would otherwise print a vacuous
CLEAN), refuses to report a verdict when the pyteman pin did not engage (the
firing log must show the rule fired), freezes the orphan with SIGSTOP before
the WAL rotation so the fd-hold never races the teardown tail, and takes its
<<<<<<< HEAD
holder evidence from the same upstream scanner the guard uses. The entire
process tree runs in its own session (`start_new_session=True`), and a
`try/finally` guard calls `os.killpg` on every exit path (including readiness
timeout, upstream kill failure, SQLite errors during WAL rotation, and scanner
exceptions), so no descendant can outlive the driver. The driver isolates
`HERMES_HOME` to the scratch directory before importing any hermes module, so
the operator's ambient profile cannot influence the run. Firing logs and the
scratch database land in a throwaway temp directory (`PYTEMAN_LOG` is pointed
there by the driver), never in this repo.

Verified legs (2026-09-15, hermes-agent `5910de20bc` base vs PR #112069 head
`6602939a4f`):

| scenario | base (3.0s grace) | fix #112069 (12s grace) |
|---|---|---|
| A, 5s teardown | `kill_elapsed_s=3.13 parent_rc=-9` REPRODUCED (orphan holds deleted sidecars, guard FATAL) | `kill_elapsed_s=5.09 parent_rc=0` CLEAN (no orphan, no holders) |
| B, 30s wedged | `kill_elapsed_s=3.12 parent_rc=-9` REPRODUCED | `kill_elapsed_s=12.26 parent_rc=-9` REPRODUCED |

Reading: scenario A confirms the mechanism and that extending the grace fixes
the transient case. Scenario B is the incident's own shape (descendants that
stay wedged); every open fix PR is a grace bump (10s, 10s, 12s), so all of
them still SIGKILL mid-teardown and orphan the holder. Closing that window
needs the kill sequence to account for descendants (wait for the process tree,
or reap/stop orphans after a forced kill), not a larger constant.

Scaling note: to track this matrix over time (re-verify legs against new
commits, regenerate the table, keep expected verdicts durable), express the
legs as cells of pyteman's own runner (`pyteman.runner.matrix.run_matrix` plus
`matrix_markdown`) instead of invoking this driver by hand; the driver stays
single-leg on purpose so the example reads top to bottom.
