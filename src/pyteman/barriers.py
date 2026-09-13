# src/pyteman/barriers.py
import threading

_lock = threading.Lock()
_state = {}

def wait(name, timeout_s=30.0):
    with _lock:
        ev = _state.setdefault(name, threading.Event())
    if ev.is_set():
        return True
    return ev.wait(timeout_s)

def open(name):
    with _lock:
        _state.setdefault(name, threading.Event()).set()

def reset_all():
    global _state
    with _lock:
        _state = {}
