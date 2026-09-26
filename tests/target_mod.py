def plain(a, b=0):
    return a + b

class Calc:
    def add(self, x):
        return x + 1

calls = []

def record_len():
    calls.append(1)
    return len(calls)


# --- targeting fixtures (attribute-held state) ----------------------------

import sqlite3

class SessionDB:
    """The hermes shape: the connection is an attribute, never an argument."""

    def __init__(self, path):
        self._conn = sqlite3.connect(path)
        self.absent = None  # attribute-held None (resolved-to-None tests)

    def append(self, who, msg):
        self._conn.execute("CREATE TABLE IF NOT EXISTS m (who TEXT, msg TEXT)")
        self._conn.execute("INSERT INTO m VALUES (?, ?)", (who, msg))
        self._conn.commit()

    def close(self):
        self._conn.close()


class HostileSession(SessionDB):
    """Session whose property raises during target resolution (CFG-06)."""

    @property
    def broken_conn(self):
        raise RuntimeError("pool closed")

    @property
    def fatal_conn(self):
        raise KeyboardInterrupt("stop")


def save(session, msg):
    session.append("user", msg)

def save_kw(msg, db):
    pass  # only the signature matters to the param: targeting tests

def open_conn(path):
    return sqlite3.connect(path)
