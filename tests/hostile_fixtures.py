"""Hostile rendering inputs shared by the activation and sitecustomize tests.

`_typename` and `_text` exist twice, once in patcher.py and once in
sitecustomize.py, because sitecustomize must not import pyteman while it is
inert. The argument for keeping two copies is that they behave identically,
and that is only shown while both are driven by the same inputs. Two local
definitions of each input are how the inputs would drift apart unnoticed, so
they live here once, and `PARITY_INPUTS` drives every guarded copy with all
of them: the `_typename` pair in patcher and sitecustomize, and
`type_name` in targets, each through its own parity leg. Test-side only:
sitecustomize itself never imports this.
"""


class Hostile(Exception):
    """An exception that will not say what it is."""

    def __str__(self):
        raise RuntimeError("boom from __str__")


class BoomStr(str):
    """A str that passes every isinstance check and then refuses to render.

    `str()` returns whatever __str__ gave it as long as that is a str INSTANCE,
    and a subclass carries its own __repr__ and __format__, so a value that
    looks like plain text to every guard still runs user code the moment a
    caller interpolates it.
    """

    def __repr__(self):
        raise RuntimeError("no repr for you")

    def __format__(self, spec):
        raise RuntimeError("no format for you")


class _SubclassNameMeta(type):
    @property
    def __name__(cls):  # type: ignore[override]
        return BoomStr("Victim")


class SubclassName(metaclass=_SubclassNameMeta):
    """A type whose name lookup succeeds and returns a BoomStr."""


class _HostileNameMeta(type):
    """Serves __name__ from a property, which is ordinary metaclass practice.

    ORM models, plugin registries and generic-alias shims all synthesise
    __name__ this way. What makes it interesting here is only that the property
    may return something other than a string, and the attribute lookup still
    SUCCEEDS: a try/except around it sees nothing wrong and passes the value on.
    """

    @property
    def __name__(cls):  # type: ignore[override]
        class Unrenderable:
            def __str__(self):
                raise RuntimeError("this name refuses to render")

            __repr__ = __str__

        return Unrenderable()


class HostileName(metaclass=_HostileNameMeta):
    # Hostile to str() as well, so one object exercises both helpers: _text
    # falls through to its last-resort branch, and that branch renders a type
    # name, which is exactly where the metaclass above is waiting.
    def __str__(self):
        raise RuntimeError("this object refuses to render")


class _NoNameMeta(type):
    @property
    def __name__(cls):  # type: ignore[override]
        raise RuntimeError("no name for you")


class Nameless(metaclass=_NoNameMeta):
    """A type whose name lookup raises, on an object that will not render."""

    def __str__(self):
        raise RuntimeError("no str either")


class HostileId:
    """A rule id that renders as a str subclass rather than as a str.

    Not a contrived shape for a hand-built Rule: an id carried over from an
    enum, a path-like wrapper or a lazily-interpolated template class is an
    ordinary thing to pass, and Rule is a plain dataclass that checks nothing.
    """

    def __str__(self):
        return BoomStr("hostile-id")


class _InterruptNameMeta(type):
    @property
    def __name__(cls):  # type: ignore[override]
        raise KeyboardInterrupt


class InterruptName(metaclass=_InterruptNameMeta):
    """A type whose name lookup interrupts the process."""


class _ExcNameMeta(type):
    @property
    def __name__(cls):  # type: ignore[override]
        raise RuntimeError("no name for this exception")


class UnnameableError(RuntimeError, metaclass=_ExcNameMeta):
    """An exception whose own type refuses to name itself."""


class BoomStrError(RuntimeError):
    """An exception whose __str__ succeeds and returns a str subclass."""

    def __str__(self):
        return BoomStr("boom-msg")


PARITY_INPUTS = (
    ("hostile-str", Hostile()),
    ("str-subclass", BoomStr("boom")),
    ("name-not-a-str", HostileName()),
    ("name-raises", Nameless()),
    ("name-raises-interrupt", InterruptName()),
    ("str-returns-subclass", HostileId()),
    ("name-is-str-subclass", SubclassName()),
    ("ordinary", ValueError("plain")),
)
