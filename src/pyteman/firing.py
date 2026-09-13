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

    def record(self, rule, ctx, note=None):
        with self._lock:
            self._seq += 1
            self._fh.write(json.dumps({
                "seq": self._seq,
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "rule": rule.id,
                "event": rule.event,
                "thread": threading.current_thread().name,
                "note": note}) + "\n")
            self._fh.flush()

def open_log(path):
    return FiringLog(path) if path else None
