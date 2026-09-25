import sqlite3
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))


def pytest_report_header():
    return [
        f"python {sys.version}",
        f"sqlite {sqlite3.sqlite_version}",
    ]
