"""Simulated ui-tui / tui_gateway.entry descendant for the #111912 repro.

Holds state.db plus its -wal/-shm sidecars open. On SIGTERM it would normally
close and exit within milliseconds; the pyteman rule pinned by this example's
ruleset delays graceful_shutdown() deterministically, which is the race window
the update's SIGTERM -> SIGKILL sequence can land inside.
"""
import os
import signal
import sqlite3
import sys
import time

_conn = None
_stopping = False


def graceful_shutdown():
    """The teardown path pyteman pins (entry sleep per the active ruleset)."""
    global _conn
    _conn.close()
    _conn = None


def _on_term(signum, frame):
    global _stopping
    if _stopping:
        return
    _stopping = True
    if _conn is not None:
        graceful_shutdown()
    os._exit(0)


def main():
    global _conn
    db_path, ready_marker = sys.argv[1], sys.argv[2]
    signal.signal(signal.SIGTERM, _on_term)  # BEFORE the marker: no default-disposition window
    _conn = sqlite3.connect(db_path)
    _conn.execute("CREATE TABLE IF NOT EXISTS heartbeat (tick INTEGER)")
    _conn.execute("INSERT INTO heartbeat VALUES (1)")
    _conn.commit()  # forces -wal and -shm into existence; fds stay open while parked
    tmp_marker = ready_marker + ".tmp"
    with open(tmp_marker, "w", encoding="utf-8") as fh:
        fh.write(str(os.getpid()))
    os.replace(tmp_marker, ready_marker)  # readers never see an empty marker
    while True:
        time.sleep(0.5)  # park, holding db + -wal + -shm open
