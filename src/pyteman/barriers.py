# src/pyteman/barriers.py
"""Thread-level latch for barrier actions.

These barriers synchronize threads within a single process. They provide
no cross-process synchronization: each process holds its own state dict
and generation counter, so an ``open()`` in one process has no effect on
a ``wait()`` in another.

Each name is a one-shot latch: once opened it stays open until
``reset_all()`` starts a new generation. ``reset_all()`` sets the old
generation's events, so an active waiter is woken with a ``False``
return rather than stranded on an orphaned Event, and the generation
counter is what keeps that set from reading as a legitimate open.

_lock discipline: ``wait()`` calls the Event's ``is_set`` and ``wait``
outside ``_lock``, so a hostile Event can re-enter barriers from those
two methods without deadlocking. ``open()`` sets under the lock, which
is master's unchanged shape; nothing may re-enter barriers from a
``set()`` call, where it would deadlock, which is the one residual
constraint.
"""
import os
import threading

_lock = threading.Lock()
_state = {}
_generation = 0

def wait(name, timeout_s=30.0):
    with _lock:
        gen = _generation
        ev = _state.setdefault(name, threading.Event())
    # The Event's own methods run outside _lock (see the module docstring);
    # a reset landing between the generation read and is_set() would make
    # this set read as a legitimate open, which the locked check below
    # refuses.
    if ev.is_set():
        with _lock:
            return _generation == gen
    if not ev.wait(timeout_s):
        return False
    with _lock:
        return _generation == gen

def open(name):
    with _lock:
        _state.setdefault(name, threading.Event()).set()

def reset_all():
    global _state, _generation
    with _lock:
        old_events = list(_state.values())
        _generation += 1
        _state = {}
    # Set outside _lock, per the discipline at the top of the module; a
    # woken waiter reads the new generation under the lock and answers
    # False.
    for ev in old_events:
        ev.set()


def refusal(name, timeout_s):
    """The exception strict mode refuses a timed-out barrier with, or None.

    The whole strict-mode policy is here: whether the switch is on and what
    the refusal says, so that this module states the rule on its own and the
    generic action dispatcher carries no barrier-specific environment
    variable. This mirrors `pragmas.refusal`, for the same reasons.

    The environment is read at firing time, not at import. A matrix cell sets
    the variable for the run it is about to execute, and a value frozen when
    this module was first imported would apply the previous cell's setting to
    this one.

    The caller carries this as `to_raise` rather than raising it, which is
    what keeps the terminal record's status semantic: the deliberate branch
    of `run_action` writes ONE record under `barrier_timeout` and then raises,
    while raising from inside the dispatcher would take the generic handler
    and record the attempt as `failed`, indistinguishable from a rule that
    named an action kind nobody implements.
    """
    if os.environ.get("PYTEMAN_STRICT_BARRIER") != "1":
        return None
    return BarrierTimeoutError(
        f"barrier {name!r} timed out after {timeout_s}s; "
        "PYTEMAN_STRICT_BARRIER is set, so this experiment is refused rather "
        "than run with its synchronisation unmet. The firing log's terminal "
        "record carries the same outcome")


class BarrierTimeoutError(AssertionError):
    """Raised by the `barrier` action under strict mode, and only there.

    Strict mode exists because a choreography whose barrier never opened is
    not the experiment the operator described: the body runs at a moment
    nothing coordinated, and a log nobody reads will not stop it from
    reporting a result. Raising is what stops it.

    What this guarantees is narrow, deliberately so, and it is narrower on an
    exit rule than on an entry rule. On entry the exception leaves the patched
    call before the body runs, so the body does not run at all. On an exit rule
    the body has ALREADY run and nothing here can undo it, and the refusal is
    not merely late: it is raised inside the patcher's `finally`, so it becomes
    the propagating exception, demotes an exception the body raised to
    `__context__`, and stops every exit rule after it on that slot. A barrier
    that only failed to synchronise can therefore mask the very failure the
    experiment was measuring, which is a reason to put the strict barrier on
    entry rules by preference. If the workload catches the exception it is
    swallowed like any other, and the terminal record written before the raise
    is the only surviving evidence.

    Like `PragmaVerificationError` this is deliberately not a class any
    `raise` action can name, so an injected exception can never be mistaken
    for a refusal by the tool itself.
    """
