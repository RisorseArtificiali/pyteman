import pathlib
import sqlite3
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from startup_harness import clear_ambient_pyteman


@pytest.fixture(autouse=True)
def _no_ambient_pyteman(monkeypatch):
    """Delete every PYTEMAN_* variable the runtime reads, for each test.

    The startup harness filters these from run_py children and the
    scripts filter them from their own children (TASK-212); this closes
    the remaining surface, the test process itself. Measured before it:
    a developer with PYTEMAN_STRICT_PRAGMA exported failed 43 tests in
    a bare pytest run on pragma refusals alone, and children spawned
    with a wholesale os.environ spread (the coroutine rig) inherited
    the variables with them. A test that needs one sets it itself.
    """
    clear_ambient_pyteman(monkeypatch)


def pytest_report_header():
    return [
        f"python {sys.version}",
        f"sqlite {sqlite3.sqlite_version}",
    ]
