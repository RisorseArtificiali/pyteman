# Confirmation: WAL handoff survives a pinned concurrent restart cycle (#109966)

Independent confirmation for
[NousResearch/hermes-agent#109966](https://github.com/NousResearch/hermes-agent/issues/109966):
after #109841 and #110544, does the lost-WAL-generation chain still reproduce
on a current tip? The reporter's own update (verified on `743140cd8`) says no;
this example re-answers the question on any checkout with a concurrent,
pyteman-pinned interleaving instead of the sequential one
`tests/hermes_state/test_wal_lock_guard.py` pins.

## Mechanism under test

A long-lived holder writes through a real `SessionDB` forever; a pyteman rule
stalls its first three `append_message` calls at entry for 3s each, so the
gateway-restart-shaped sibling (its own `SessionDB`, one write, close; the
last-close WAL-reset path) always closes INSIDE a live write window. After the
windows pass, the driver checks the incident's signatures with real upstream
code: `iter_deleted_sqlite_sidecar_holders` (the /proc scan), a fresh
`SessionDB` opener, and the holder's own survival.

## Prerequisites

- Linux (the driver refuses anything else).
- A Python the upstream supports: hermes-agent declares
  `requires-python = ">=3.11,<3.14"`. Verified on 3.13.15.
- pyteman in that interpreter: `pip install pyteman==0.2.0` (verified), or
  `pip install <this checkout>` for the version the example ships with.
- The upstream's import-time dependencies. At the verified revision the
  driver's imports need only PyYAML, pinned there as `pyyaml==6.0.3`; a
  full `pip install -e <checkout>` works too but pulls the whole agent.
- A hermes-agent checkout at a revision exposing
  `hermes_state.DeletedWalGenerationError`, `hermes_state.SessionDB` and
  `hermes_state_dbfile.iter_deleted_sqlite_sidecar_holders`.

The driver checks every one of those names before it seeds or spawns
anything. A checkout lacking one, a dependency the upstream cannot
import, or a name resolving outside the checkout (an installed hermes
shadowing the tree under test) ends the run at once with a
`DRIVER-ERROR` naming the problem, the checkout's revision and the
tested one, and exits 2.

The verified leg from nothing (GitHub serves a commit by its full SHA):

    git init hermes && cd hermes
    git fetch --depth 1 https://github.com/NousResearch/hermes-agent 2cfb655d52e7e482523236c4012b61fcb54b37ce
    git checkout --detach FETCH_HEAD && cd ..
    python3.13 -m venv venv && venv/bin/pip install pyteman==0.2.0 pyyaml==6.0.3
    venv/bin/python run_repro.py hermes CLEAN

`../verify_hermes_legs.sh [pyteman-spec] [workdir]` does the same for
every verified leg of this example and of `hermes-111912`, each against
its expected verdict; the opt-in `hermes-legs` workflow runs it on
GitHub Actions.

## Run (Linux only, enforced)

    python3 run_repro.py <hermes-agent checkout> CLEAN

CLEAN: no deleted-generation holder (the real /proc scanner), the fresh opener
is not refused (the refusal happens at SessionDB construction), and the holder
kept writing (heartbeat advanced). REPRODUCED: any of those incident
signatures. INCONCLUSIVE: a harness fault (pin count, choreography, process
health), never counted as either answer. The expected verdict as an argument
makes a future regression exit nonzero instead of reading as a pass; the
scratch home (firing log, fail flag, database) is preserved on any non-CLEAN
outcome for postmortem. Every verdict carries a `REASON:` line naming
which incident signature fired or which harness fault answered, and only
explicit signatures feed REPRODUCED: the deleted-sidecar holders, the
fresh opener's WAL refusal, or the holder failing WITH the
WAL-generation refusal; a holder fault of any other kind, and an
unparsable fail flag, read as INCONCLUSIVE with the error type named.
The temp home pins `database.journal_mode: wal` and
isolates `HERMES_HOME`, so an ambient operator config cannot produce a vacuous
run. The isolation covers the DRIVER process too: the scratch home is built
and exported as this process's `HERMES_HOME` before the first upstream
import, so seeding reads and writes the scratch profile, never the
operator's (before that ordering, a run with `HERMES_HOME` pointing at an
operator profile created the profile's whole tree there). Ambient
`PYTEMAN_RULES` or `PYTEMAN_LOG` is refused: an instrumented driver is not
this scenario.

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
everything it found.

Verified: `2cfb655d52` (2026-09-16, main including #109841, #110544, #112266;
re-run 2026-09-28 with pyteman 0.2.0 from PyPI on Python 3.13.15, same
verdict, exit 0). The claim is bound to that revision; a later tip is
unverified until it is run:

```
cycle 1: close inside window (start seq 1, end not yet written)
cycle 2: close inside window (start seq 3, end not yet written)
cycle 3: close inside window (start seq 5, end not yet written)
restarter_rc=0 windows_fired=3/3 holder_alive=True holder_writing=True
deleted_sidecar_holders=0 fresh_opener_refused=False
VERDICT: CLEAN
```

Each sibling close is asserted against BOTH edges of its window, read from
the firing log the rule itself writes: the `phase: start` record the sleep
writes before stalling and the `phase: end` terminal it writes on release,
each carrying a monotonic timestamp. A cycle closes only after its window's
start is on disk, re-reads the log after the close, and refuses the whole
run when the end record preceded the close or the window never opened
inside its wait budget. A refusal exits nonzero and the driver maps that to
INCONCLUSIVE, never CLEAN, so a slow scheduler or a pre-populated log
cannot turn a sequential run into a concurrent-looking one. One firing
window per call for the first three calls comes from the `when: fires <= 3`
gate; a `countdown` rule fires once at call n+1, which is one window, not
three.
