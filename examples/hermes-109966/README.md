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
signatures, or a holder failure whose exception type is a known WAL-incident
signature (`DeletedWalGenerationError`, `OperationalError`). INCONCLUSIVE: a
harness fault (pin count, choreography, process health) or a holder failure
with a non-incident exception type (disk full, permission error, or any other
generic fault); never counted as either answer. Every verdict carries a
diagnostic reason. The holder writes its failure evidence as structured JSON
(exception type, module, message, phase, tick count) so the driver can
distinguish incident signatures from test infrastructure faults. Heartbeats
are published atomically (write to a temp file, then `os.replace`), so a
concurrent reader never sees a truncated or empty value. The expected verdict
as an argument makes a future regression exit nonzero instead of reading as a
pass; the scratch home (firing log, fail flag, database) is preserved on any
non-CLEAN outcome for postmortem. The temp home pins
`database.journal_mode: wal` and isolates `HERMES_HOME`, so an ambient
operator config cannot produce a vacuous run.

Verified: `2cfb655d52` (2026-09-16, main including #109841, #110544, #112266):

```
restarter_rc=0 windows_started=3/3 windows_ended=3/3 holder_alive=True holder_writing=True
deleted_sidecar_holders=0 fresh_opener_refused=False
VERDICT: CLEAN
```

Each sibling close is gated on the window being OPEN: the restarter waits for
window i's `phase: start` record AND checks that no corresponding `phase: end`
record has been written yet. If the window has already closed (the end record
exists), the restarter exits with a nonzero code instead of performing a
sequential close that would be presented as concurrent. The driver counts both
start and end records independently; a mismatch between them yields
INCONCLUSIVE. One firing window per call for the first three calls comes from
the `when: fires <= 3` gate; a `countdown` rule fires once at call n+1, which
is one window, not three.
