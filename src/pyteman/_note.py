def safe_add_note(exc, text):
    """Attach context to an exception without any chance of replacing it.

    add_note is available on every interpreter this project supports (3.11+)
    and accepts any exception instance, including builtins. The guard is for the
    one shape that rejects it: a subclass shadowing __notes__ with something
    that is not a list, where add_note raises from inside an except block whose
    job is preserving a primary exception. Both consumers, the patcher's
    rollback and the firing log's cleanup, are exactly that.

    The guard covers the add_note CALL, not the evaluation of `text`: the
    argument must already be an exact str, built under the caller's own
    format guard or through the exact-str helpers.
    """
    try:
        exc.add_note(text)
    except BaseException:
        pass
