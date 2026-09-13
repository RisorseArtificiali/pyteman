# src/pyteman/barriers.py
import threading

_lock = threading.Lock()
_state = {}

def wait(name, timeout_s=30.0):
    with _lock:
        st = _state.setdefault(name, {"event": threading.Event(), "opened": False})
        if st["opened"]:
            return True
        ev = st["event"]
    return ev.wait(timeout_s)

def open(name):
    with _lock:
        st = _state.setdefault(name, {"event": threading.Event(), "opened": False})
        st["opened"] = True
        st["event"].set()

def reset_all():
    global _state
    with _lock:
        _state = {}
