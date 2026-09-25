# src/pyteman/sitecustomize.py
import os
import sys

# `from typing import NoReturn` at module scope would cost every inert
# interpreter in the venv the price of importing typing, measured here at about
# 12ms on top of a 30ms bare start, and would put typing in sys.modules for
# programs that never asked for pyteman, which is the one thing this module
# promises not to do. The guard is never true at runtime and the annotation
# below is a string, so the import is a type-checker fiction: nothing here
# evaluates either one.
TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import NoReturn


def _refuse(phase, detail="", exc=None) -> "NoReturn":
    """Report which phase failed and stop the process before the workload runs.

    os._exit rather than sys.exit or a bare raise, and the reason is the same
    for every failure phase. CPython imports this module from
    site.execsitecustomize, which wraps the import in `try/except Exception`:
    a RuleError or an OSError raised here is swallowed there, leaving one line
    on stderr while the workload runs UNINSTRUMENTED and the process exits 0.
    An operator reading that exit code sees a successful run of an experiment
    that injected nothing. SystemExit escapes the handler, being a
    BaseException, but startup then fails with `Fatal Python error:
    init_import_site` and substitutes exit code 1 for the one requested, so it
    buys a stop at the price of the status. os._exit gives both: the workload
    never starts and the code survives.

    The exit sits in `finally` because the two halves are not equally
    negotiable. Telling the operator why is best effort: sys.stderr is None
    under pythonw, and is a closed pipe under any harness that went away while
    we were starting. Not running the workload is the whole contract, so a
    stderr that refuses must not turn a refusal back into a fail-open start.

    The EXCEPTION is taken rather than a rendered string, and that is the same
    argument one level down. Describing an exception runs user code, so a
    caller writing `_refuse(phase, _describe(exc))` would render it as an
    argument, before this function is entered and outside the try/finally
    below; anything raised there escapes into the `except Exception` above and
    fails open at exit 0. Rendering inside costs a failed render the message
    and nothing else. For the same reason the phase is written before the
    detail: a detail that cannot be rendered still leaves the operator the line
    saying where to look.

    Requested activation therefore fails CLOSED. Activation is only requested
    when PYTEMAN_RULES is set; without it this module does nothing at all, which
    is also why every import below _main is deferred: a process that did not ask
    for pyteman should not pay for it, nor find it in sys.modules.
    """
    try:
        head = f"pyteman: refusing to start: {phase}:"
        if detail:
            # Plain strings from the environment, so this cannot fail; the
            # colon is only earned when an exception follows it.
            head += f" {detail}" + (":" if exc is not None else "")
        sys.stderr.write(head)
        try:
            if exc is not None:
                sys.stderr.write(f" {_describe(exc)}")
        finally:
            sys.stderr.write("\n")
            sys.stderr.flush()
    finally:
        os._exit(2)


def _typename(obj):
    """The type name of anything. See _text; this exists for the same reason.

    Takes the object, not the name, because `_text(type(obj).__name__)` would
    do the attribute access as an argument, before the protection is entered.

    The type check is not defensive padding. A metaclass is free to expose
    __name__ as a property, so the lookup can SUCCEED and hand back an object
    hostile to being rendered, which would then raise from inside the f-string
    of whichever caller asked, up to and including _text's own last-resort
    branch. Guarding the lookup and not the result left the fail open reachable
    through the code closing it. `type(name) is str` rather than isinstance,
    since a str SUBCLASS passes isinstance and still carries its own __repr__
    and __format__ into the caller's f-string.
    """
    try:
        name = type(obj).__name__
    except BaseException:
        return "<unknown type>"
    return name if type(name) is str else "<unknown type>"


def _text(obj):
    """str() that cannot raise, returning an EXACT str.

    Not raising is only half of it. str() accepts a str subclass from __str__
    and returns it unchanged, and a subclass brings its own __repr__ and
    __format__, so interpolating the result would run user code after all. The
    normalisation below makes the returned value inert, which is what lets
    _describe and _refuse interpolate it without thinking about it again.

    A near-copy of the pair in pyteman.patcher, and deliberately not imported
    from there. This module promises that a process without PYTEMAN_RULES
    imports no pyteman module at all, and the first failure phase below is
    `importing pyteman`, where by definition the package is not available to
    import from. The duplicated lines are the price of both.
    """
    try:
        s = str(obj)
    except BaseException:
        # Concatenation, not an f-string: safe by construction rather than by
        # _typename keeping its own promise.
        return "<unprintable " + _typename(obj) + ">"
    return s if type(s) is str else str.__str__(s)


def _describe(exc):
    """Render an exception the way a traceback would, notes included.

    The patcher says WHICH rule it was patching by attaching a note, and that
    is the half the operator needs: `TypeError: cannot set 'bit_length' of
    immutable type 'int'` names an attribute, not the rule that asked for it.
    str(exc) does not show notes; only the traceback machinery does, and no
    traceback is ever printed on this path, because _refuse leaves through
    os._exit.

    Everything rendered here is user code and is treated as hostile: __str__,
    the __notes__ getter, each note's own __str__, and the __notes__ container
    itself. Since _refuse calls this from inside the try/finally that
    guarantees the exit, a failure here costs the message and never the
    refusal; the care below is about keeping the message, not about keeping the
    guarantee.

    `text` is built first and is inert once built, both helpers returning an
    exact str, so every failure below degrades the NOTES and still leaves the
    operator the exception type and its message. Losing those to a hostile
    container would be the reporting throwing away more than it was asked to.
    """
    text = f"{_typename(exc)}: {_text(exc)}"
    # Bound once, for a string with four readers: docs/rules.md quotes it and
    # three tests assert it, so three spellings of one contract are three
    # chances for a reworded degradation to land in two of them and go quiet.
    # _disclose in the patcher holds the rollback wording to the same standard.
    # Building it eagerly cannot fail: `text` is inert the moment it exists,
    # both helpers returning an exact str.
    lost = f"{text} | <notes unavailable>"
    try:
        notes = exc.__notes__
    except AttributeError:
        return text  # the ordinary case: an exception nobody annotated
    except BaseException:
        # Said out loud rather than dropped: the note is where the rule id
        # lives, so its absence would otherwise look like a rule that never
        # named itself.
        return lost
    if type(notes) is not list:
        # Shadowed with something that is not a list. The notes are lost the
        # same way, so they are announced the same way rather than passed off
        # as an exception that simply had none.
        #
        # `type(x) is list` rather than isinstance for the same reason the two
        # helpers above use it, and it is the more important of the two uses:
        # isinstance is not a type test. Against a non-list it falls back to
        # reading x.__class__, which is an ordinary attribute lookup a property
        # can define, so a __notes__ whose __class__ raises makes the CHECK
        # raise. That lands outside every guard in this function and costs the
        # whole line, exception type and message included, which is the one
        # thing the degradations below are written to keep. add_note only ever
        # builds an exact list, so narrowing here gives up nothing pyteman
        # produces; an exotic list subclass loses its notes and is told so.
        return lost
    try:
        return text + "".join(f" | {_text(note)}" for note in notes)
    except BaseException:
        # Unreachable as written, and kept anyway. `notes` is an exact list by
        # the check above, so iterating it cannot raise, and _text returns an
        # exact str, so neither can the f-string. Both of those are properties
        # of code that could be edited; this is the branch that keeps such an
        # edit costing the notes rather than the exit.
        return lost


def _main():
    rules_path = os.environ.get("PYTEMAN_RULES", "").strip()
    if not rules_path:
        return  # INERT: no env, no effects
    marker = os.environ.get("PYTEMAN_REQUIRE_MARKER", "").strip()
    if marker and not os.path.isfile(marker):
        _refuse("marker check", f"marker file missing: {marker}")
    # BaseException, not Exception, in all four handlers below. An activation
    # interrupted by Ctrl-C has not happened either, and letting KeyboardInterrupt
    # past here buys the worst of both: the workload still never starts, but
    # through init_import_site, which reports exit 1 and names no phase.
    try:
        from pyteman.rules import load_rules
        from pyteman.patcher import activate
        from pyteman.firing import open_log
    except BaseException as exc:
        _refuse("importing pyteman", exc=exc)
    try:
        rules = load_rules(rules_path)
    except BaseException as exc:
        _refuse("loading rules", rules_path, exc)
    try:
        log = open_log(os.environ.get("PYTEMAN_LOG", "pyteman.log"))
    except BaseException as exc:
        _refuse("opening the firing log", exc=exc)
    try:
        # activate rather than install plus a patch loop of our own: it is the
        # entry point that unwinds the hook and every module patched so far.
        patcher = activate(rules, log, sorted({r.module for r in rules}))
    except BaseException as exc:
        _refuse("installing instrumentation", exc=exc)
    sys._pyteman = {"patcher": patcher, "log": log}


# Only auto-run when imported as top-level sitecustomize (the direct
# PYTHONPATH=src/pyteman activation path). When loaded through the
# activation shim at src/activate/ or imported as pyteman.sitecustomize,
# __name__ differs and the caller is responsible for invoking _main().
if __name__ == "sitecustomize":
    _main()
