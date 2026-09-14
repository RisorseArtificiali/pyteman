# src/pyteman/firing.py
import json
import threading
import time

class FiringLog:
    def __init__(self, path):
        self.path = path
        self._seq = 0
        self._lock = threading.Lock()
        self._fh = open(path, "a")

    def record(self, rule, ctx, note=None, outcome=None):
        # "outcome" marks action-outcome annotations (skips, execute
        # failures) so log consumers can tell them from firing records,
        # which carry the action dump in "note".
        rec = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "rule": rule.id,
            "event": rule.event,
            "thread": threading.current_thread().name,
            "note": note}
        if outcome is not None:
            rec["outcome"] = outcome
        with self._lock:
            self._seq += 1
            rec["seq"] = self._seq
            self._fh.write(json.dumps(rec) + "\n")
            self._fh.flush()

def open_log(path):
    return FiringLog(path) if path else None
