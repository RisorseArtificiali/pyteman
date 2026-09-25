__version__ = "0.2.0"


def __getattr__(name):
    if name == "PatchRefusalError":
        from pyteman.patcher import PatchRefusalError
        return PatchRefusalError
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
