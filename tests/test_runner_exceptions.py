"""The runner's exception family, pinned to its common base (TASK-60).

A caller must be able to intercept any runner failure without naming six
classes across three modules, and the only broad alternative available before
the base existed was ``except RuntimeError``, which hides ``RecursionError``
(the one failure the runner deliberately attributes to a cell rather than
to the run). The base is the contract; these tests keep the family from
silently losing a new member, because an exception added outside it passes
every other test in the suite.
"""
import pytest

import pyteman.runner
from pyteman.runner import MatrixError
from pyteman.runner.lock import MatrixLockError
from pyteman.runner.matrix import (
    MatrixArtifactError,
    MatrixIdentityError,
    MatrixResultError,
    MatrixStorageError,
)
from pyteman.runner.report import MatrixReportError

#: Every exception the runner raises. Written by hand, and held complete
#: by the package walk below: a seventh exception added flat under
#: RuntimeError is found by the walk and fails the set equality, which a
#: walk over MatrixError's subclasses could never catch.
RUNNER_FAILURES = [
    MatrixLockError,
    MatrixIdentityError,
    MatrixArtifactError,
    MatrixResultError,
    MatrixStorageError,
    MatrixReportError,
]


@pytest.mark.parametrize("cls", RUNNER_FAILURES)
def test_every_runner_failure_is_catchable_as_matrix_error(cls):
    """One name intercepts the failure, and keeps the old net working.

    The ``raises`` proves the subclass relation behaviourally, in the
    direction a caller relies on; the explicit ``issubclass`` keeps the
    pre-base contract alive for callers written when these were flat
    ``RuntimeError`` subclasses.
    """
    assert issubclass(cls, RuntimeError)
    with pytest.raises(MatrixError):
        raise cls("boom")


def _runner_runtime_errors():
    """Every RuntimeError subclass the runner package defines, at any depth.

    Walked from the package rather than from MatrixError, because a flat
    exception never joins the base's subclass set and would otherwise
    pass every test in this file.
    """
    import importlib
    import pkgutil

    found = set()
    modules = [pyteman.runner]
    modules.extend(
        importlib.import_module(f"pyteman.runner.{info.name}")
        for info in pkgutil.iter_modules(pyteman.runner.__path__))
    for module in modules:
        for value in vars(module).values():
            if (isinstance(value, type)
                    and issubclass(value, RuntimeError)
                    and value is not MatrixError
                    and value.__module__.startswith("pyteman.runner")):
                found.add(value)
    return found


def test_every_runner_runtime_error_is_listed_in_the_family():
    """The hand list is complete, or the omission is a failure.

    A passing suite otherwise shows nothing: the walk makes the flat
    seventh exception the module docstring describes fail here instead
    of waiting for a reader to re-count the list.
    """
    assert _runner_runtime_errors() == set(RUNNER_FAILURES)
