"""Gateway-restart-shaped sibling for the #109966 confirmation.

Each cycle rides one pinned write window, and proves it did: the firing
log carries both edges of every window (the ``phase: start`` record the
sleep writes before stalling and the ``phase: end`` terminal it writes
on release, each with a monotonic timestamp), so the choreography is
ASSERTED per cycle rather than inferred from counts. A cycle only closes
after its window's start is on disk and before its end is, and a window
that never opened, or closed before the sibling got there, refuses the
cycle instead of performing an out-of-window close and presenting it as
valid.
"""
import json
import sys
import time
from pathlib import Path

from hermes_state import SessionDB

# Exit codes the driver maps to INCONCLUSIVE, never CLEAN: the harness
# could not prove the choreography, which is a fault of this run, not a
# durable answer about the bug under test.
EXIT_WINDOW_TIMEOUT = 2
EXIT_OUT_OF_WINDOW = 3


def _windows(firing_log):
    """Every window's two edges, as ``(start_rec, end_rec)`` by ordinal.

    A window is one firing of the rule: its ``phase: start`` record and
    the ``phase: end`` terminal that same firing writes when the sleep
    releases. Counting them together would double the windows, and
    counting starts alone cannot say whether a window is still open.
    """
    starts, ends = [], []
    try:
        lines = open(firing_log, encoding="utf-8", errors="replace").readlines()
    except OSError:
        lines = []
    pending = []
    for line in lines:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("rule") != "hold-write-window":
            continue
        phase = rec.get("phase")
        if phase == "start":
            pending.append(rec)
        elif phase == "end" and pending:
            starts.append(pending.pop(0))
            ends.append(rec)
    return list(zip(starts, ends)) + [(s, None) for s in pending]


def _fired_count(firing_log: str) -> int:
    """Count the write windows opened so far, one per firing of the rule.

    A firing is its ``phase: start`` record; the matching ``phase: end``
    terminal is that same firing finishing, so counting both would make the
    restarter believe it had twice as many windows to ride.
    """
    n = 0
    for _start, _end in _windows(firing_log):
        n += 1
    return n


def _ride_cycle(firing_log, i):
    """Prove window ``i`` straddles this moment, or refuse the cycle.

    Returns the window's start record, its end still absent. Refuses,
    with the exit codes above, when the window never opened inside the
    wait budget or when its end is already on disk: closing then would
    land outside the window, and performing that close while presenting
    the cycle as valid is exactly the false proof this exists to prevent.
    """
    deadline = time.monotonic() + 30
    while True:
        windows = _windows(firing_log)
        if i <= len(windows):
            start, end = windows[i - 1]
            if end is not None:
                print(
                    f"restarter: window {i} already closed (end seq "
                    f"{end.get('seq')}); refusing to close outside it",
                    file=sys.stderr,
                )
                sys.exit(EXIT_OUT_OF_WINDOW)
            return start
        if time.monotonic() >= deadline:
            print(
                f"restarter: window {i} never opened within 30s; refusing",
                file=sys.stderr,
            )
            sys.exit(EXIT_WINDOW_TIMEOUT)
        time.sleep(0.02)


def main():
    db_path, cycles, firing_log = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    for i in range(1, cycles + 1):
        start = _ride_cycle(firing_log, i)
        sibling = SessionDB(db_path=Path(db_path))
        sibling.append_message("restarter", role="user", content=f"cycle {i}")
        sibling.close()
        # The close completed; the proof needs its end to have been
        # written after the close finished. An end still absent settles
        # it, and an end that IS on disk settles it by monotonic
        # comparison, which the two processes share on one machine.
        close_ns = time.monotonic_ns()
        _end = _windows(firing_log)[i - 1][1]
        if _end is not None and _end.get("monotonic_ns", 0) <= close_ns:
            print(
                f"restarter: cycle {i} closed after its window ended "
                f"(close at {close_ns}, end at {_end.get('monotonic_ns')})",
                file=sys.stderr,
            )
            sys.exit(EXIT_OUT_OF_WINDOW)
        print(
            f"cycle {i}: close inside window "
            f"(start seq {start.get('seq')}, "
            f"end {_end['seq'] if _end else 'not yet written'})"
        )


if __name__ == "__main__":
    main()
