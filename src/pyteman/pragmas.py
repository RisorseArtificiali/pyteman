"""Readback verification for the `pragma` action.

SQLite does not report a pragma that did not take effect. Its own
documentation is explicit: "No error messages are generated if an unknown
pragma is issued. Unknown pragmas are simply ignored. This means if there is a
typo in a pragma statement the library does not inform the user of the fact."
A value the pragma does not recognise is equally silent, though not equally
inert: SQLite parses it, fails to match it, and falls back to a default, so an
unrecognised VALUE can overwrite a setting that was already correct while an
unrecognised NAME does nothing at all. So `execute` returning without raising
says nothing at all about whether the setting the rule asked for is now in
force, and until this module existed the firing log recorded that silence as
`pragma_executed` for four materially different outcomes: applied, ignored
inside a transaction, misspelled beyond verification, and a correct setting
silently overwritten.

Verification here means comparing the value read back against a NORMALISED
expectation, not merely reading it. Reading alone fails in both directions: a
baseline that already matches makes an applied pragma look inert, and
`synchronous=banana` reads back exactly what `on`, `true` and `NORMAL` read
back, because SQLite fell through to the default.

Three properties keep that comparison honest.

The expectation vocabulary is CLOSED and taken from the documented grammar
rather than from observed behaviour. `synchronous=4` does land as 4 and
`synchronous=-1` does land as 1, but neither appears in the grammar, so an
"applied" verdict on them would rest on an accident of the implementation.
They are reported as unverifiable instead.

Normalisation is PARTIAL. A total `str -> int` would have to return something
for `banana`, and returning the default would make `banana` indistinguishable
from `true` and certify it as applied. `UNKNOWN` is a first-class result: no
expectation exists, so no claim is made in either direction.

The perimeter is CLOSED, and that is a correctness requirement rather than
caution. The read form of a pragma is not always a read: `PRAGMA
wal_checkpoint` checkpoints, and `PRAGMA optimize` runs ANALYZE and can create
`sqlite_stat1`. A pragma outside the whitelist is never read back at all, so
this module cannot mutate the database under test by inspecting it.
"""
import os

#: No expectation could be derived: the pragma is outside the perimeter, or
#: the value is outside its documented vocabulary. Distinct from "the
#: expectation is zero", which is why this is a sentinel and not `None`.
UNKNOWN = object()

#: The readback produced nothing this module is willing to compare. Distinct
#: from `UNKNOWN`, which is about the expectation rather than the observation.
UNREADABLE = object()

# https://sqlite.org/pragma.html: "The boolean can be one of: 1 yes true on
# 0 no false off". Keys are lowercased before lookup; quotes are stripped by
# the loader, so what arrives here is the bare token.
_BOOLEAN = {"1": 1, "yes": 1, "true": 1, "on": 1,
            "0": 0, "no": 0, "false": 0, "off": 0}

# "PRAGMA synchronous = 0 | OFF | 1 | NORMAL | 2 | FULL | 3 | EXTRA". The
# boolean aliases are documented to apply here too, which is why `off` and
# `true` appear alongside the named levels. `4` and `-1` are deliberately
# absent: both are accepted by SQLite and neither is in the grammar.
_SYNCHRONOUS = dict(_BOOLEAN, normal=1, full=2, extra=3)
_SYNCHRONOUS["2"] = 2
_SYNCHRONOUS["3"] = 3

# "PRAGMA journal_mode = DELETE | TRUNCATE | PERSIST | MEMORY | WAL | OFF".
# Compared as text, so `1`, `on` and `banana` are all outside it: a quoted
# "ON" loads, runs, and leaves the mode exactly where it was.
_JOURNAL_MODE = {m: m for m in
                 ("delete", "truncate", "persist", "memory", "wal", "off")}

#: The supported perimeter. Schema-qualified names are deliberately absent:
#: the TEMP schema "always has synchronous=OFF" and "attempts to change the
#: synchronous setting for TEMP are silently ignored", so a verdict on
#: `temp.synchronous` would be wrong in a way this module cannot detect.
_PERIMETER = {
    "foreign_keys": _BOOLEAN,
    "ignore_check_constraints": _BOOLEAN,
    "synchronous": _SYNCHRONOUS,
    "journal_mode": _JOURNAL_MODE,
}

#: Every status this module can produce, and whether it means the rule's
#: request is in force. Exported so a log consumer can classify an outcome
#: without re-deriving the vocabulary, which is how the existing example
#: driver came to under-report a pragma that never applied.
APPLIED = "pragma_applied"
ALREADY = "pragma_already"
MISMATCH = "pragma_mismatch"
UNVERIFIED = "pragma_unknown"

#: The two outcomes that never reached a verdict at all: the action found no
#: connection to act on, or the connection refused the statement. They are
#: produced in `actions.py` rather than here, but they are named here so that
#: `REFUTING` is not a hand-written list of string literals maintained at a
#: distance from the code that emits them. That is precisely the drift this
#: change exists to remove from the example driver.
SKIPPED = "pragma_skipped"
FAILED = "pragma_failed"

#: The statuses that do NOT attest the requested setting. `pragma_already` is
#: absent because the postcondition does hold; `pragma_unknown` is present
#: because an unverifiable experiment is not a successful one.
REFUTING = frozenset({MISMATCH, UNVERIFIED, FAILED, SKIPPED})


def _vocabulary(name):
    """The accepted values for `name`, or None if it is outside the perimeter.

    Case-folded, because SQLite is: `PRAGMA FOREIGN_KEYS=ON` applies exactly
    as `PRAGMA foreign_keys=ON` does. Matching case-sensitively would report a
    pragma that really did take effect as unverifiable, which is a false
    statement in the message and, under strict mode, a refusal of a sound
    experiment. Schema-qualified names still miss, as intended: they carry a
    dot and so match no entry.
    """
    return _PERIMETER.get(str(name).strip().lower())


def normalise(name, value):
    """The value the readback must show, or `UNKNOWN`.

    Partial by design: an unrecognised token has no expectation at all rather
    than being mapped to a default, which is what stops `foreign_keys=banana`
    from being certified as applied after SQLite ignored it.
    """
    vocabulary = _vocabulary(name)
    if vocabulary is None:
        return UNKNOWN
    # `value` is a str or an int by the time the loader is done with it, so
    # this runs no workload code. `str(1)` is `"1"`, which the documented
    # vocabularies already contain.
    return vocabulary.get(str(value).strip().lower(), UNKNOWN)


def read(con, name):
    """Read `name` back on `con`, or return `UNREADABLE`.

    Never raises for an observational failure, because a diagnostic must not
    decide what propagates. `BaseException` is deliberately not caught, so an
    interruption still interrupts.

    A cursor whose `close` fails therefore costs the value already fetched:
    the cleanup raises inside this `try` and the observation becomes
    `UNREADABLE`. That is deliberate and not the same contract as the SET
    statement in `actions.py`, which must be executed whatever happens around
    it; a verification whose own acquisition or cleanup failed is not one this
    module is willing to certify.

    Only whitelisted names are queried. That is what keeps the side-effecting
    read forms out of reach: no generic `PRAGMA <name>` is ever issued for a
    pragma this module does not understand.
    """
    if _vocabulary(name) is None:
        return UNREADABLE
    try:
        cur = con.execute(f"PRAGMA {name}")
        try:
            row = cur.fetchone()
        finally:
            # Closing a cursor does not touch the transaction, so a readback
            # cannot commit, roll back, or otherwise move the workload's state
            # underneath the very experiment it is verifying.
            close = getattr(cur, "close", None)
            if close is not None:
                close()
        # An unknown pragma name yields no row at all, which is how a
        # misspelling reaches us. Shape is checked before content, and INSIDE
        # the `try`: `row` is whatever the connection's cursor returned, so a
        # `tuple` subclass can raise from `__len__` or `__getitem__`, and
        # inspecting it is workload code exactly like rendering the value in
        # it. Checking outside would make this function raise, and since the
        # baseline read runs before the execute, it would also cancel the
        # injection instead of merely failing to describe it.
        if not isinstance(row, tuple) or len(row) != 1:
            return UNREADABLE
        observed = row[0]
    except Exception:
        return UNREADABLE
    # Exact types, not `isinstance`. The value arrives from an object the
    # workload controls, and an `int` subclass may override `__eq__` to
    # compare equal to anything, which would let a workload declare its own
    # pragma applied. For the same reason nothing here renders `observed`:
    # `__str__` is workload code too, and it runs later, deferred, or not at
    # all. See `_safe_message` in actions.py.
    if type(observed) is int or type(observed) is str:
        return observed
    return UNREADABLE


def classify(name, value, before, after):
    """Return `(status, message)` for one pragma attempt.

    `message` is a zero-arg callable in every case. Building it eagerly would
    interpolate `before` and `after`, which are values an arbitrary connection
    returned, so rendering them can raise from inside the action and turn a
    reported no-op into a failure of the workload under test.
    """
    expected = normalise(name, value)
    asked = f"PRAGMA {name}={value}"

    if expected is UNKNOWN:
        return UNVERIFIED, lambda: (
            f"{asked}: no verifiable expectation. {_vocabulary_note(name)} "
            f"SQLite ignores what it does not recognise without raising, so "
            f"this is not a claim that it was applied, nor that it was not. "
            f"{_observed(before, after)}")

    if after is UNREADABLE:
        return UNVERIFIED, lambda: (
            f"{asked}: the value could not be read back, so the setting is "
            f"unverified. {_observed(before, after)}")

    if not _matches(expected, after):
        return MISMATCH, lambda: (
            f"{asked}: accepted without raising, but the value read back is "
            f"not the one asked for, so the setting is NOT in force. "
            f"{_observed(before, after)}")

    if before is UNREADABLE:
        # The postcondition holds, but with no baseline there is no way to
        # say whether this attempt established it. Fail closed rather than
        # claim the stronger of the two readings.
        return UNVERIFIED, lambda: (
            f"{asked}: the value is now as asked, but the baseline could not "
            f"be read, so whether this attempt changed anything is unknown. "
            f"{_observed(before, after)}")

    if _matches(expected, before):
        return ALREADY, lambda: (
            f"{asked}: already in force before this attempt, which therefore "
            f"proved nothing about its own effect. {_observed(before, after)}")

    return APPLIED, lambda: (
        f"{asked}: the value read back is the one asked for, and it changed. "
        f"This is the postcondition observed, not a claim of exclusive "
        f"causality: the connection may be shared. {_observed(before, after)}")


def _matches(expected, observed):
    """Compare without letting the observed value define equality.

    `read` has already restricted `observed` to an exact `int` or `str`, so
    the only comparison reachable here is between two built-ins.
    """
    if isinstance(expected, str):
        return type(observed) is str and observed.strip().lower() == expected
    return type(observed) is int and observed == expected


def _observed(before, after):
    return f"Read back: before={_show(before)}, after={_show(after)}."


def _show(v):
    return "<unreadable>" if v is UNREADABLE else repr(v)


def _vocabulary_note(name):
    vocabulary = _vocabulary(name)
    if vocabulary is None:
        return (f"{name!r} is outside the verified perimeter "
                f"({', '.join(sorted(_PERIMETER))}), so it was executed but "
                f"not read back.")
    return f"{name!r} accepts only {', '.join(sorted(vocabulary))}."


def refusal(name, value, status):
    """The exception strict mode refuses this attempt with, or None.

    The whole strict-mode policy is here: which statuses refuse, whether the
    switch is on, and what the refusal says. Splitting it across this module
    and the dispatcher left neither file able to state the rule on its own,
    and put a pragma-specific environment variable in the generic action
    dispatcher.

    The environment is read at firing time, not at import. A matrix cell sets
    the variable for the run it is about to execute, and a value frozen when
    this module was first imported would apply the previous cell's setting to
    this one.

    The caller carries this as `to_raise` rather than raising it, which is
    what keeps the terminal record's status semantic: the deliberate branch of
    `run_action` writes ONE record under `status` and then raises, while
    raising from inside the dispatcher would take the generic handler and
    record the attempt as `failed`, losing which verdict refused it. The
    message names only the rule's own request, never a value read back from a
    connection the workload controls.
    """
    if status not in REFUTING or os.environ.get("PYTEMAN_STRICT_PRAGMA") != "1":
        return None
    return PragmaVerificationError(
        f"PRAGMA {name}={value} was not verified ({status}); "
        "PYTEMAN_STRICT_PRAGMA is set, so this experiment is refused "
        "rather than allowed to report a result. The firing log's "
        "terminal record carries what was observed")


class PragmaVerificationError(AssertionError):
    """Raised by the `pragma` action under strict mode, and only there.

    Strict mode exists because a pragma that did not apply invalidates the
    experiment built on top of it, and a log nobody reads will not stop that
    experiment from reporting a result. Raising is what stops it.

    What this guarantees is narrow, and the narrowness is the point. The
    exception leaves the patched call, so the instrumented body does not
    continue past the pragma. If nothing in the workload catches it, it
    reaches the matrix runner, whose `except Exception` around the cell
    callback records the cell as `failed`. If the workload DOES catch it, the
    cell continues and may be recorded as `done`: an ordinary `except
    Exception` swallows it like any other, and no analyser reconciles the
    firing log against the results database. The terminal record written
    before the raise is then the only surviving evidence, and it survives only
    if there is a log configured and its write succeeds.

    It derives from `AssertionError` because that is what it is: an assertion
    about the state of the database that did not hold. It is deliberately not
    a class any `raise` action can name, so it is never mistaken for an
    injected fault.
    """
