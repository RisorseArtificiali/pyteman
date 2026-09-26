"""Long-lived gateway-shaped writer for the #109966 confirmation.

Keeps a real SessionDB open and appends forever; the pyteman rule stalls its
first three append_message calls at entry, which is the live write window the
sibling's close must land inside. Each tick updates the heartbeat file so the
driver can prove the holder kept writing; a write failure lands in the flag
file as structured JSON so the driver can distinguish WAL-incident signatures
from generic test faults.
"""
import json
import os
import sys
import time
from pathlib import Path

from hermes_state import SessionDB


def main():
    db_path, marker, heartbeat, fail_flag = sys.argv[1:5]
    db = SessionDB(db_path=Path(db_path))
    n = 0
    with open(marker, "w", encoding="utf-8") as fh:
        fh.write(str(os.getpid()))
    while True:
        n += 1
        try:
            db.append_message("holder", role="user", content=f"tick {n}")
        except Exception as exc:
            info = {"type": type(exc).__qualname__,
                    "module": type(exc).__module__,
                    "message": str(exc),
                    "phase": "append",
                    "tick": n}
            with open(fail_flag, "w", encoding="utf-8") as fh:
                json.dump(info, fh)
            raise
        tmp = heartbeat + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(str(n))
        os.replace(tmp, heartbeat)
        time.sleep(0.2)


if __name__ == "__main__":
    main()
