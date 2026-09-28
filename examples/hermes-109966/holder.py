"""Long-lived gateway-shaped writer for the #109966 confirmation.

Keeps a real SessionDB open and appends forever; the pyteman rule stalls its
first three append_message calls at entry, which is the live write window the
sibling's close must land inside. Each tick updates the heartbeat file so the
driver can prove the holder kept writing; a write failure lands in the flag
file as STRUCTURED evidence the driver can classify: the WAL-generation
refusal is the incident under test, any other error is a fault of this run
and must not read as the incident.
"""
import json
import os
import sys
import time
from pathlib import Path

from hermes_state import SessionDB


def _atomic_write(path, text):
    """Publish a file whole: readers never observe a truncated write."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


def main():
    db_path, marker, heartbeat, fail_flag = sys.argv[1:5]
    db = SessionDB(db_path=Path(db_path))
    n = 0
    _atomic_write(marker, str(os.getpid()))
    # The baseline heartbeat exists BEFORE the first append: a holder that
    # dies on its very first write still leaves the driver a readable
    # heartbeat to compare, rather than a FileNotFoundError.
    _atomic_write(heartbeat, "0")
    while True:
        n += 1
        try:
            db.append_message("holder", role="user", content=f"tick {n}")
        except Exception as exc:
            _atomic_write(fail_flag, json.dumps({
                "phase": "append",
                "error_type": type(exc).__name__,
                "error_repr": repr(exc),
                "tick": n,
            }))
            raise
        _atomic_write(heartbeat, str(n))
        time.sleep(0.2)


if __name__ == "__main__":
    main()
