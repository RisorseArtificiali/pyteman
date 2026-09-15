"""Simulated manually-run dashboard for the #111912 repro.

Spawns the ui-tui descendant; on SIGTERM it forwards the signal, waits for the
child to finish its teardown, then exits 0. That graceful wait is what the
updater's 3.0s (base) or 10-12s (fix PRs) SIGKILL deadline races against.
"""
import os
import signal
import subprocess
import sys
import time


def main():
    db_path, ready_marker = sys.argv[1], sys.argv[2]
    child = subprocess.Popen(
        [sys.executable, "-c", "import tui_child; tui_child.main()", db_path, ready_marker],
    )

    def _on_term(signum, frame):
        child.terminate()
        child.wait()  # graceful: outlasts a 3s deadline when pyteman pins a longer teardown
        os._exit(0)

    signal.signal(signal.SIGTERM, _on_term)
    while child.poll() is None:
        time.sleep(0.2)
    os._exit(0)
