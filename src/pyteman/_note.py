def safe_add_note(exc, text):
    """Attach context to an exception without any chance of replacing it.

    add_note is available on every interpreter this project supports (3.11+)
    and accepts any exception instance, including builtins. The guard is for the
    one shape that rejects it: a subclass shadowing __notes__ with something
    that is not a list, where add_note raises from inside an except block. That
    is the substitution the rollback path is written to avoid, so it cannot be
    allowed in by the code doing the avoiding.
    """
    try:
        exc.add_note(text)
    except BaseException:
        pass
