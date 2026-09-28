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
- `rules-slow-teardown.yaml` (scenario A, 5s pin): between base's 3.0s grace and the 10-12s grace of the fix PRs open on 2026-09-15, so it discriminates base from fix.
- `rules-wedged-teardown.yaml` (scenario B, 30s pin): past every proposed grace, so it shows a grace bump narrows the window but never closes it.
- `run_repro.py`: the driver; verdict lines are machine-greppable.

## Prerequisites

- Linux (the driver refuses anything else).
- A Python the upstream supports: hermes-agent declares
  `requires-python = ">=3.11,<3.14"`. Verified on 3.13.15.
- pyteman in that interpreter: `pip install pyteman==0.2.0` (verified), or
  `pip install <this checkout>` for the version the example ships with.
- The upstream's import-time dependencies. At both verified revisions the
  driver's imports need only PyYAML, pinned there as `pyyaml==6.0.3`; a
  full `pip install -e <checkout>` works too but pulls the whole agent.
- A hermes-agent checkout at a revision exposing
  `hermes_cli.dashboard_procs._kill_pids_posix`,
  `hermes_state.DeletedWalGenerationError`,
  `hermes_state_dbfile.iter_deleted_sqlite_sidecar_holders` and
  `hermes_state_dbfile.refuse_deleted_wal_generation`.

The driver checks every one of those names before it seeds or spawns
anything. A checkout lacking one, a dependency the upstream cannot
import, or a name resolving outside the checkout (an installed hermes
shadowing the tree under test) ends the run at once with a
`DRIVER-ERROR` naming the problem, the checkout's revision and the
tested ones, and exits 2.

The verified legs from nothing, started in this directory; the
checkouts and the venv go to a temp dir outside the tree (GitHub serves
a commit by its full SHA, including a pull request head):

    E=$PWD W=$(mktemp -d) && cd "$W"
    B=5910de20bc9839fdd36e791a9d72ba2c2e722f66 F=6602939a4f50570b437e7ced4b043a5986bb7717
    for rev in $B $F; do
        git init hermes-$rev && git -C hermes-$rev fetch --depth 1 https://github.com/NousResearch/hermes-agent $rev
        git -C hermes-$rev checkout --detach FETCH_HEAD
    done
    python3.13 -m venv venv && venv/bin/pip install pyteman==0.2.0 pyyaml==6.0.3
    venv/bin/python "$E"/run_repro.py hermes-$B "$E"/rules-slow-teardown.yaml REPRODUCED
    venv/bin/python "$E"/run_repro.py hermes-$F "$E"/rules-slow-teardown.yaml CLEAN
    venv/bin/python "$E"/run_repro.py hermes-$B "$E"/rules-wedged-teardown.yaml REPRODUCED
    venv/bin/python "$E"/run_repro.py hermes-$F "$E"/rules-wedged-teardown.yaml REPRODUCED

`../verify_hermes_legs.sh [pyteman-spec] [workdir]` does the same for
these four legs and the `hermes-109966` one, each against its expected
verdict; the opt-in `hermes-legs` workflow runs it on GitHub Actions.

## Run (Linux only, enforced)

    python3 run_repro.py <hermes-agent checkout under test> rules-slow-teardown.yaml REPRODUCED

The third argument is the expected verdict (REPRODUCED or CLEAN); the driver
exits nonzero on mismatch, so a scenario that stops discriminating after an
upstream change (for example a grace raised past scenario A's 5s pin) fails
loudly instead of reading as a pass. The scratch home the driver builds is
its own `HERMES_HOME` and the children's, set before the first upstream
import, so neither the driver nor the tree it spawns touches the
operator's profile; ambient `PYTEMAN_RULES` or `PYTEMAN_LOG` is refused,
because an instrumented driver is not this scenario.

Exit codes: 0 a verdict was reached and matched (or none was asked);
1 an expectation mismatch; 2 a driver error (`DRIVER-ERROR`, also
for an unplanned crash, whose traceback goes to stderr); 3
`INCONCLUSIVE`, which is never a success. The expectation is validated
before anything runs. Every outcome except an unambiguous matched CLEAN
preserves the scratch home, and a run that reached a verdict also
leaves a `manifest.json` in it carrying the verdict, its reason, the
evidence fields and the provenance (ruleset digest, upstream revision,
Python and SQLite versions, argv), written before the preservation
decision is taken; a driver error before any verdict keeps the home
without one, except the incompatible-checkout refusal, which removes
its home because nothing of the run is in it yet: the error line names
everything it found. The
process tree the driver spawns is killed as one unit on every exit,
including crashes: the parent is spawned as its own process group,
cleanup signals only that captured group, and a cleanup failure of its own prints a `CLEANUP-ERROR:` line beside whatever
else the run reports, alongside `VERDICT:` and `DRIVER-ERROR:` as the
machine-greppable tokens. The driver also hard-fails off Linux (the
upstream holder scan is a no-op there, which would otherwise print a vacuous
CLEAN), refuses to report a verdict when the pyteman pin did not engage (the
firing log must show the rule fired), freezes the orphan with SIGSTOP before
the WAL rotation so the fd-hold never races the teardown tail, and takes its
holder evidence from the same upstream scanner the guard uses. Firing logs and
the scratch database land in a throwaway temp directory (`PYTEMAN_LOG` is
pointed there by the driver), never in this repo.

Verified legs (2026-09-15, hermes-agent `5910de20bc` base vs PR #112069 head
`6602939a4f`; all four re-run 2026-09-28 with pyteman 0.2.0 from PyPI on
Python 3.13.15, same verdicts, each exit 0, elapsed 3.12/5.13/3.04/12.10s in
table order A-base, A-fix, B-base, B-fix):

| scenario | base (3.0s grace) | fix #112069 (12s grace) |
|---|---|---|
| A, 5s teardown | `kill_elapsed_s=3.13 parent_rc=-9` REPRODUCED (orphan holds deleted sidecars, guard FATAL) | `kill_elapsed_s=5.09 parent_rc=0` CLEAN (no orphan, no holders) |
| B, 30s wedged | `kill_elapsed_s=3.12 parent_rc=-9` REPRODUCED | `kill_elapsed_s=12.26 parent_rc=-9` REPRODUCED |

The table describes those two revisions and nothing later: the graces are
the deadlines their `_kill_pids_posix` sets (a literal `3.0` at the base,
`_POSIX_TERM_GRACE_SECONDS = 12.0` at the fix head), and a newer tip
with a different grace or kill sequence is unverified until its legs are
run. Reading, as of 2026-09-15: scenario A confirms the mechanism and that
extending the grace fixes the transient case. Scenario B is the incident's
own shape (descendants that stay wedged); every fix PR open on that date
was a grace bump (10s, 10s, 12s), so all of them still SIGKILL
mid-teardown and orphan the holder. Closing that window
needs the kill sequence to account for descendants (wait for the process tree,
or reap/stop orphans after a forced kill), not a larger constant.

Scaling note: to track this matrix over time (re-verify legs against new
commits, regenerate the table, keep expected verdicts durable), express the
legs as cells of pyteman's own runner (`pyteman.runner.matrix.run_matrix` plus
`matrix_markdown`) instead of invoking this driver by hand; the driver stays
single-leg on purpose so the example reads top to bottom.
