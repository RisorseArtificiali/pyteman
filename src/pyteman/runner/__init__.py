class MatrixError(RuntimeError):
    """Common base for runner exceptions, so callers can catch any runner
    failure without resorting to ``except RuntimeError``."""
