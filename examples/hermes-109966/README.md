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

## Run (Linux only, enforced)

    pip install pyteman
    python3 run_repro.py <hermes-agent checkout> CLEAN

CLEAN: no deleted-generation holder (the real /proc scanner), the fresh opener
is not refused (the refusal happens at SessionDB construction), and the holder
kept writing (heartbeat advanced). REPRODUCED: any of those incident
signatures. INCONCLUSIVE: a harness fault (pin count, choreography, process
health), never counted as either answer. The expected verdict as an argument
makes a future regression exit nonzero instead of reading as a pass; the
scratch home (firing log, fail flag, database) is preserved on any non-CLEAN
outcome for postmortem. The temp home pins `database.journal_mode: wal` and
isolates `HERMES_HOME`, so an ambient operator config cannot produce a vacuous
run. The isolation covers the DRIVER process too: the scratch home is built
and exported as this process's `HERMES_HOME` before the first upstream
import, so seeding reads and writes the scratch profile, never the
operator's (before that ordering, a run with `HERMES_HOME` pointing at an
operator profile created the profile's whole tree there). Ambient
`PYTEMAN_RULES` or `PYTEMAN_LOG` is refused: an instrumented driver is not
this scenario.

Verified: `2cfb655d52` (2026-09-16, main including #109841, #110544, #112266):

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
