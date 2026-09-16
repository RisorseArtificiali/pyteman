"""Gateway-restart-shaped sibling for the #109966 confirmation.

Each cycle waits for firing record n in the shared firing log, then opens its
own SessionDB, writes one message, and closes: the last-close WAL-reset path
that, before #109841/#110544, could unlink a live generation out from under
the holder. Gating on the firing records asserts the close lands inside the
pinned write window instead of inferring it from timing.
"""
import json
import sys
import time
from pathlib import Path

from hermes_state import SessionDB


def _fired_count(firing_log: str) -> int:
    n = 0
    try:
        lines = open(firing_log, encoding="utf-8", errors="replace").readlines()
    except OSError:
        return 0
    for line in lines:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("rule") == "hold-write-window" and "outcome" not in rec:
            n += 1
    return n


def main():
    db_path, cycles, firing_log = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    for i in range(cycles):
        deadline = time.monotonic() + 30
        while _fired_count(firing_log) < i + 1 and time.monotonic() < deadline:
            time.sleep(0.02)
        sibling = SessionDB(db_path=Path(db_path))
        sibling.append_message("restarter", role="user", content=f"cycle {i}")
        sibling.close()


if __name__ == "__main__":
    main()
