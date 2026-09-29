"""Hostile rendering inputs shared by the activation and sitecustomize tests.

`_typename` and `_text` exist twice, once in patcher.py and once in
sitecustomize.py, because sitecustomize must not import pyteman while it is
inert. The argument for keeping two copies is that they behave identically,
and that is only shown while both are driven by the same inputs. Two local
definitions of each input are how the inputs would drift apart unnoticed, so
they live here once. Test-side only: sitecustomize itself never imports this.
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
