def safe_add_note(exc, *parts):
    """Attach context to an exception without any chance of replacing it.

    Accepts parts rather than a pre-rendered string so the join happens
    inside the guard: a caller that builds a message as an f-string
    argument evaluates it before the guard is entered, and a hostile
    __str__ in the argument list replaces the exception being annotated
    with its own failure, which is the substitution both consumers exist
    to prevent.

    add_note is available on every interpreter this project supports
    (3.11+) and accepts any exception instance, including builtins. The
    guard covers two shapes: a subclass shadowing __notes__ with
    something that is not a list (where add_note raises from inside an
    except block whose job is preserving a primary exception), and a
    part whose join raises. Either way the note is silently dropped
    rather than replacing the primary. Both consumers, the patcher's
    rollback and the firing log's cleanup, are exactly that.

    The join returns an exact str by construction (str.join concatenates
    the character data and builds a plain str, measured), so a part that
    is a str subclass cannot carry its own __format__ into a later
    interpolation through the note.
    """
    try:
        exc.add_note("".join(parts))
    except BaseException:
        pass
