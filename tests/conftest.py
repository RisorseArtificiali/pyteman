import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))


class BoomStr(str):
    """A str that passes every isinstance check and then refuses to render.

    The subtler half of the same defect. ``str()`` returns whatever __str__
    gave it as long as that is a str INSTANCE, and a subclass carries its own
    __repr__ and __format__, so a value that looks like plain text to every
    guard still runs user code the moment a caller interpolates it.
    """

    def __repr__(self):
        raise RuntimeError("no repr for you")

    def __format__(self, spec):
        raise RuntimeError("no format for you")


class Hostile(Exception):
    """An exception that will not say what it is."""

    def __str__(self):
        raise RuntimeError("boom from __str__")
