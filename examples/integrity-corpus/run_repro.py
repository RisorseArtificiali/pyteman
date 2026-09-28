#!/usr/bin/env python3
"""Reproduce each observed integrity corpus sample from a fresh database.

Usage (from the repository root):

    python3 examples/integrity-corpus/run_repro.py [sample-name ...]

If no sample names are given, every OBSERVED sample is reproduced. The output
is a table of sample name, host SQLite version, and whether the captured text
matched the corpus byte for byte (or as a set of lines, since line order varies
across builds).

This is NOT a test suite. A divergence means the host SQLite changed the
wording of a message, which is news about SQLite rather than a defect in this
repository; the exit code is always 0 unless a reproducer itself errors out.
"""

import os
import re
import shutil
import sqlite3
import struct
import subprocess
import sys
import tempfile


_here = os.path.dirname(os.path.abspath(__file__))
_repo = os.path.dirname(os.path.dirname(_here))
sys.path.insert(0, os.path.join(_repo, "tests"))

from integrity_corpus import CORPUS, OBSERVED


def _capture(con):
    return "\n".join(row[0] for row in con.execute("PRAGMA integrity_check"))


def _sorted_lines(text):
    return sorted(text.split("\n"))


def _check_fts(version):
    con = sqlite3.connect(":memory:")
    try:
        con.execute(f"CREATE VIRTUAL TABLE _probe USING fts{version}(body)")
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        con.close()


_HAS_FTS5 = _check_fts(5)
_HAS_FTS4 = _check_fts(4)


def _read_page_size(path):
    with open(path, "rb") as f:
        f.seek(16)
        raw = f.read(2)
        page_size = struct.unpack(">H", raw)[0]
        return 65536 if page_size == 1 else page_size


# ---------------------------------------------------------------------------
# Reproducers. Each returns the text to diff against the corpus sample.
# ---------------------------------------------------------------------------

def _reproduce_clean(tmp):
    con = sqlite3.connect(os.path.join(tmp, "clean.db"))
    con.execute("CREATE TABLE t(x)")
    con.executemany("INSERT INTO t(x) VALUES (?)", [(i,) for i in range(3)])
    con.commit()
    text = _capture(con)
    con.close()
    return text


def _reproduce_empty_file_is_clean(tmp):
    path = os.path.join(tmp, "empty.db")
    with open(path, "wb"):
        pass
    con = sqlite3.connect(path)
    text = _capture(con)
    con.close()
    return text


def _reproduce_rowid_disorder(tmp):
    path = os.path.join(tmp, "rowid.db")
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE t(x)")
    con.executemany("INSERT INTO t(x) VALUES (?)", [(i,) for i in range(2)])
    con.commit()
    rootpage = con.execute(
        "SELECT rootpage FROM sqlite_master WHERE name='t'"
    ).fetchone()[0]
    con.close()

    page_size = _read_page_size(path)
    page_offset = (rootpage - 1) * page_size
    hdr = 100 if rootpage == 1 else 0
    cell_ptr_offset = page_offset + hdr + 8

    with open(path, "r+b") as f:
        f.seek(cell_ptr_offset)
        ptr1 = f.read(2)
        ptr2 = f.read(2)
        f.seek(cell_ptr_offset)
        f.write(ptr2 + ptr1)

    con = sqlite3.connect(path)
    text = _capture(con)
    con.close()
    return text


def _hide_index_insert_restore(path, table, index_name, initial_rows,
                               extra_rows, values_fn):
    """Hide an index from sqlite_master, insert rows, then restore it.

    The index is hidden by deleting its row under writable_schema, then
    restored with the original rootpage after new rows have been inserted
    (so the index missed those inserts and reports the count mismatch).
    """
    con = sqlite3.connect(path)
    con.execute(f"CREATE TABLE {table}(x)")
    con.execute(f'CREATE INDEX "{index_name}" ON {table}(x)')
    con.executemany(
        f"INSERT INTO {table}(x) VALUES (?)",
        [(values_fn(i),) for i in range(initial_rows)],
    )
    con.commit()
    sql_row, rootpage = con.execute(
        "SELECT sql, rootpage FROM sqlite_master "
        "WHERE type='index' AND name=?",
        (index_name,),
    ).fetchone()
    con.close()

    con = sqlite3.connect(path)
    con.execute("PRAGMA writable_schema=ON")
    con.execute(
        "DELETE FROM sqlite_master WHERE type='index' AND name=?",
        (index_name,),
    )
    con.commit()
    con.close()

    con = sqlite3.connect(path)
    con.executemany(
        f"INSERT INTO {table}(x) VALUES (?)",
        [(values_fn(i),) for i in range(initial_rows, initial_rows + extra_rows)],
    )
    con.commit()
    con.close()

    con = sqlite3.connect(path)
    con.execute("PRAGMA writable_schema=ON")
    con.execute(
        "INSERT INTO sqlite_master(type, name, tbl_name, rootpage, sql) "
        "VALUES('index', ?, ?, ?, ?)",
        (index_name, table, rootpage, sql_row),
    )
    con.commit()
    con.close()


def _reproduce_index_count_with_residue(tmp):
    path = os.path.join(tmp, "idx_count.db")
    _hide_index_insert_restore(
        path, "messages", "idx_messages_session_id",
        initial_rows=200, extra_rows=60,
        values_fn=lambda i: f"s{i:06d}",
    )
    con = sqlite3.connect(path)
    text = _capture(con)
    con.close()
    return text


def _orphan_pages(path, table, index_name, row_count, values_fn):
    """Drop an index from sqlite_master, orphaning its pages."""
    con = sqlite3.connect(path)
    con.execute(f"CREATE TABLE {table}(x)")
    con.execute(f'CREATE INDEX "{index_name}" ON {table}(x)')
    con.executemany(
        f"INSERT INTO {table}(x) VALUES (?)",
        [(values_fn(i),) for i in range(row_count)],
    )
    con.commit()
    con.close()

    con = sqlite3.connect(path)
    con.execute("PRAGMA writable_schema=ON")
    con.execute(
        "DELETE FROM sqlite_master WHERE type='index' AND name=?",
        (index_name,),
    )
    con.commit()
    con.close()


def _reproduce_orphan_pages(tmp):
    path = os.path.join(tmp, "orphan.db")
    _orphan_pages(
        path, "messages", "idx_messages_session_id",
        row_count=200,
        values_fn=lambda i: ("s%06d" % i) * 10,
    )
    con = sqlite3.connect(path)
    text = _capture(con)
    con.close()
    return text


def _reproduce_attached_database_header(tmp):
    path = os.path.join(tmp, "attach.db")
    _orphan_pages(
        path, "t", "idx_t",
        row_count=200,
        values_fn=lambda i: i,
    )
    main_path = os.path.join(tmp, "main.db")
    con = sqlite3.connect(main_path)
    con.execute("ATTACH DATABASE ? AS aux1", (path,))
    text = _capture(con)
    con.close()
    return text


def _reproduce_fts5_corruption(tmp):
    if not _HAS_FTS5:
        return None
    path = os.path.join(tmp, "fts5_corrupt.db")
    con = sqlite3.connect(path)
    con.execute("CREATE VIRTUAL TABLE messages_fts USING fts5(body)")
    for text in ("alpha beta sqlite", "gamma delta sqlite",
                 "epsilon zeta sqlite"):
        con.execute("INSERT INTO messages_fts(body) VALUES (?)", (text,))
    con.commit()
    row = con.execute(
        "SELECT rowid FROM messages_fts_data "
        "WHERE rowid > 10 ORDER BY rowid LIMIT 1"
    ).fetchone()
    if row is None:
        text = _capture(con)
        con.close()
        return text
    con.execute(
        "UPDATE messages_fts_data "
        "SET block = zeroblob(length(block)) WHERE rowid = ?",
        (row[0],),
    )
    con.commit()
    text = _capture(con)
    con.close()
    return text


def _fts5_with_deleted_content_row(path):
    con = sqlite3.connect(path)
    con.execute("CREATE VIRTUAL TABLE messages_fts USING fts5(body)")
    for text in ("alpha beta sqlite", "gamma delta sqlite",
                 "epsilon zeta sqlite"):
        con.execute("INSERT INTO messages_fts(body) VALUES (?)", (text,))
    con.commit()
    con.execute("DELETE FROM messages_fts_content WHERE id = 2")
    con.commit()
    return con


def _reproduce_fts5_malformed_inverted_index(tmp):
    if not _HAS_FTS5:
        return None
    path = os.path.join(tmp, "fts5_malformed.db")
    con = _fts5_with_deleted_content_row(path)
    text = _capture(con)
    con.close()
    return text


def _reproduce_fts5_missing_content_row_message(tmp):
    if not _HAS_FTS5:
        return None
    path = os.path.join(tmp, "fts5_missing_row.db")
    con = _fts5_with_deleted_content_row(path)
    try:
        con.execute(
            "SELECT * FROM messages_fts WHERE messages_fts MATCH 'sqlite'"
        ).fetchall()
        return ""
    except sqlite3.DatabaseError as exc:
        return str(exc)
    finally:
        con.close()


def _reproduce_fts5_missing_row_from_healthy_index(tmp):
    if not _HAS_FTS5:
        return None
    path = os.path.join(tmp, "fts5_healthy.db")
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE notes(id INTEGER PRIMARY KEY, body TEXT)")
    con.execute(
        "CREATE VIRTUAL TABLE notes_fts USING fts5("
        "body, content='notes', content_rowid='id')"
    )
    con.execute(
        "INSERT INTO notes_fts(rowid, body) VALUES (1, 'alpha beta')"
    )
    con.commit()
    try:
        con.execute(
            "SELECT * FROM notes_fts WHERE notes_fts MATCH 'alpha'"
        ).fetchall()
        return ""
    except sqlite3.DatabaseError as exc:
        return str(exc)
    finally:
        con.close()


def _reproduce_fts4_malformed_inverted_index(tmp):
    if not _HAS_FTS4:
        return None
    path = os.path.join(tmp, "fts4_malformed.db")
    con = sqlite3.connect(path)
    con.execute("CREATE VIRTUAL TABLE m4 USING fts4(body)")
    for text in ("alpha beta", "gamma delta", "epsilon zeta"):
        con.execute("INSERT INTO m4(body) VALUES (?)", (text,))
    con.commit()
    con.execute("DELETE FROM m4_segdir")
    con.commit()
    text = _capture(con)
    con.close()
    return text


def _reproduce_fts5_syntax_error_message(_tmp):
    if not _HAS_FTS5:
        return None
    con = sqlite3.connect(":memory:")
    con.execute("CREATE VIRTUAL TABLE t USING fts5(body)")
    con.execute("INSERT INTO t(body) VALUES ('hello world')")
    con.commit()
    try:
        con.execute("SELECT * FROM t WHERE t MATCH '('").fetchall()
        con.close()
        return ""
    except sqlite3.DatabaseError as exc:
        con.close()
        return str(exc)


def _reproduce_fts5_shadow_table_btree_damage(tmp):
    if not _HAS_FTS5:
        return None
    path = os.path.join(tmp, "fts5_shadow_btree.db")
    con = sqlite3.connect(path)
    con.execute("CREATE VIRTUAL TABLE messages_fts USING fts5(body)")
    for text in ("alpha beta", "gamma delta", "epsilon zeta"):
        con.execute("INSERT INTO messages_fts(body) VALUES (?)", (text,))
    con.commit()
    rootpage = con.execute(
        "SELECT rootpage FROM sqlite_master WHERE name='messages_fts_content'"
    ).fetchone()[0]
    con.close()

    page_size = _read_page_size(path)
    page_offset = (rootpage - 1) * page_size
    hdr = 100 if rootpage == 1 else 0
    cell_ptr_offset = page_offset + hdr + 8

    with open(path, "r+b") as f:
        f.seek(cell_ptr_offset)
        ptr1 = f.read(2)
        ptr2 = f.read(2)
        if ptr1 == ptr2:
            con = sqlite3.connect(path)
            text = _capture(con)
            con.close()
            return text
        f.seek(cell_ptr_offset)
        f.write(ptr2 + ptr1)

    con = sqlite3.connect(path)
    text = _capture(con)
    con.close()
    return text


def _reproduce_expression_index_named_fts(tmp):
    path = os.path.join(tmp, "expr_idx_fts.db")
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE t(body TEXT)")
    con.execute("CREATE INDEX idx_fts ON t(lower(body))")
    con.executemany(
        "INSERT INTO t(body) VALUES (?)",
        [(f"value_{i}",) for i in range(1, 5)],
    )
    con.commit()
    sql_row, rootpage = con.execute(
        "SELECT sql, rootpage FROM sqlite_master "
        "WHERE type='index' AND name='idx_fts'"
    ).fetchone()
    con.close()

    con = sqlite3.connect(path)
    con.execute("PRAGMA writable_schema=ON")
    con.execute(
        "DELETE FROM sqlite_master WHERE type='index' AND name='idx_fts'"
    )
    con.commit()
    con.close()

    con = sqlite3.connect(path)
    con.executemany(
        "UPDATE t SET body = ? WHERE rowid = ?",
        [(f"updated_{i}", i) for i in range(1, 5)],
    )
    con.commit()
    con.close()

    con = sqlite3.connect(path)
    con.execute("PRAGMA writable_schema=ON")
    con.execute(
        "INSERT INTO sqlite_master(type, name, tbl_name, rootpage, sql) "
        "VALUES('index', 'idx_fts', 't', ?, ?)",
        (rootpage, sql_row),
    )
    con.commit()
    con.close()

    con = sqlite3.connect(path)
    text = _capture(con)
    con.close()
    return text


def _reproduce_mixed_fts_and_index_count(tmp):
    if not _HAS_FTS5:
        return None
    path = os.path.join(tmp, "mixed.db")
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE messages(x)")
    con.execute("CREATE INDEX idx_messages_session_id ON messages(x)")
    con.execute("CREATE VIRTUAL TABLE messages_fts USING fts5(body)")
    con.executemany(
        "INSERT INTO messages(x) VALUES (?)",
        [(i,) for i in range(20)],
    )
    for text in ("alpha beta", "gamma delta", "epsilon zeta",
                 "eta theta", "iota kappa", "lambda mu",
                 "nu xi", "omicron pi"):
        con.execute("INSERT INTO messages_fts(body) VALUES (?)", (text,))
    con.commit()
    sql_row, rootpage = con.execute(
        "SELECT sql, rootpage FROM sqlite_master "
        "WHERE type='index' AND name='idx_messages_session_id'"
    ).fetchone()
    con.close()

    con = sqlite3.connect(path)
    con.execute("PRAGMA writable_schema=ON")
    con.execute(
        "DELETE FROM sqlite_master "
        "WHERE type='index' AND name='idx_messages_session_id'"
    )
    con.commit()
    con.close()

    con = sqlite3.connect(path)
    con.executemany(
        "INSERT INTO messages(x) VALUES (?)",
        [(i,) for i in range(20, 25)],
    )
    con.commit()
    con.close()

    con = sqlite3.connect(path)
    con.execute("PRAGMA writable_schema=ON")
    con.execute(
        "INSERT INTO sqlite_master(type, name, tbl_name, rootpage, sql) "
        "VALUES('index', 'idx_messages_session_id', 'messages', ?, ?)",
        (rootpage, sql_row),
    )
    con.commit()
    con.close()

    con = sqlite3.connect(path)
    con.execute("DELETE FROM messages_fts_content WHERE id = 2")
    con.commit()
    text = _capture(con)
    con.close()
    return text


def _index_out_of_step_with_expression(path, name, rows):
    """Build an expression index and break its determinism promise."""
    con = sqlite3.connect(path)
    con.create_function("identity", 1, lambda x: x, deterministic=True)
    con.execute("CREATE TABLE ordinary(x)")
    con.executemany("INSERT INTO ordinary(x) VALUES (?)",
                    [(n,) for n in rows])
    con.execute(f'CREATE INDEX "{name}" ON ordinary(identity(x))')
    con.commit()
    con.close()

    con = sqlite3.connect(path)
    con.create_function("identity", 1, lambda x: x + 1, deterministic=True)
    return con


def _reproduce_index_named_fts_message(tmp):
    path = os.path.join(tmp, "idx_named_fts.db")
    con = _index_out_of_step_with_expression(
        path, "fts5: corrupt", (1, 2, 3))
    text = _capture(con)
    con.close()
    return text


def _reproduce_index_named_fts_message_beside_real_fts_damage(tmp):
    if not _HAS_FTS5:
        return None
    path = os.path.join(tmp, "idx_named_fts_with_real.db")
    con = sqlite3.connect(path)
    con.create_function("identity", 1, lambda x: x, deterministic=True)
    con.execute("CREATE TABLE ordinary(x)")
    con.executemany("INSERT INTO ordinary(x) VALUES (?)",
                    [(n,) for n in (1, 2, 3)])
    con.execute('CREATE INDEX "fts5: corrupt" ON ordinary(identity(x))')
    con.execute("CREATE VIRTUAL TABLE messages_fts USING fts5(body)")
    for text in ("alpha beta", "gamma delta", "epsilon zeta"):
        con.execute("INSERT INTO messages_fts(body) VALUES (?)", (text,))
    con.commit()
    con.execute("DELETE FROM messages_fts_content WHERE id = 2")
    con.commit()
    con.close()

    con = sqlite3.connect(path)
    con.create_function("identity", 1, lambda x: x + 1, deterministic=True)
    text = _capture(con)
    con.close()
    return text


def _reproduce_not_a_database_via_stdout(tmp):
    path = os.path.join(tmp, "notadb.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("this is not a database\n")
    shell = _find_sqlite3_shell()
    if shell is None:
        return None
    result = subprocess.run(
        [shell, path, "PRAGMA integrity_check;"],
        capture_output=True, timeout=10,
    )
    return result.stdout.decode("utf-8", errors="replace").rstrip("\n")


def _find_sqlite3_shell():
    return shutil.which("sqlite3")


def _reproduce_not_a_database_message(tmp):
    path = os.path.join(tmp, "notadb2.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("this is not a database\n")
    con = sqlite3.connect(path)
    try:
        _capture(con)
        return ""
    except sqlite3.DatabaseError as exc:
        return str(exc)
    finally:
        con.close()


def _reproduce_malformed_schema_message(tmp):
    path = os.path.join(tmp, "schema.db")
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE t(x)")
    con.execute("INSERT INTO t(x) VALUES (1)")
    con.commit()
    con.execute("PRAGMA writable_schema=ON")
    con.execute(
        "UPDATE sqlite_master SET sql='CREATE TABLE t(' WHERE name='t'"
    )
    con.commit()
    con.close()

    con = sqlite3.connect(path)
    try:
        _capture(con)
        return ""
    except sqlite3.DatabaseError as exc:
        return str(exc)
    finally:
        con.close()


def _reproduce_disk_image_malformed_message(tmp):
    path = os.path.join(tmp, "truncated.db")
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE t(x)")
    con.executemany("INSERT INTO t(x) VALUES (?)",
                    [(("x" * 200),) for _ in range(100)])
    con.commit()
    con.close()

    size = os.path.getsize(path)
    page_size = _read_page_size(path)
    truncated = size - page_size
    if truncated < page_size:
        truncated = page_size
    with open(path, "r+b") as f:
        f.truncate(truncated)

    con = sqlite3.connect(path)
    try:
        _capture(con)
        return ""
    except sqlite3.DatabaseError as exc:
        return str(exc)
    finally:
        con.close()


def _reproduce_btree_index_named_fts(tmp):
    path = os.path.join(tmp, "btree_idx_fts.db")
    _hide_index_insert_restore(
        path, "messages", "idx_fts",
        initial_rows=200, extra_rows=60,
        values_fn=lambda i: f"s{i:06d}",
    )
    con = sqlite3.connect(path)
    full_text = _capture(con)
    con.close()
    lines = full_text.split("\n")
    missing_lines = [l for l in lines
                     if l.startswith("row ") and "missing from index" in l]
    return "\n".join(missing_lines[:5])


# ---------------------------------------------------------------------------
# Registry and normalizers.
# ---------------------------------------------------------------------------

_REPRODUCERS = {
    "clean": _reproduce_clean,
    "empty_file_is_clean": _reproduce_empty_file_is_clean,
    "rowid_disorder": _reproduce_rowid_disorder,
    "index_count_with_residue": _reproduce_index_count_with_residue,
    "orphan_pages": _reproduce_orphan_pages,
    "attached_database_header": _reproduce_attached_database_header,
    "fts5_corruption": _reproduce_fts5_corruption,
    "fts5_malformed_inverted_index": _reproduce_fts5_malformed_inverted_index,
    "fts5_missing_content_row_message": _reproduce_fts5_missing_content_row_message,
    "fts5_missing_row_from_healthy_index": _reproduce_fts5_missing_row_from_healthy_index,
    "fts4_malformed_inverted_index": _reproduce_fts4_malformed_inverted_index,
    "fts5_syntax_error_message": _reproduce_fts5_syntax_error_message,
    "fts5_shadow_table_btree_damage": _reproduce_fts5_shadow_table_btree_damage,
    "expression_index_named_fts": _reproduce_expression_index_named_fts,
    "mixed_fts_and_index_count": _reproduce_mixed_fts_and_index_count,
    "index_named_fts_message": _reproduce_index_named_fts_message,
    "index_named_fts_message_beside_real_fts_damage": (
        _reproduce_index_named_fts_message_beside_real_fts_damage
    ),
    "not_a_database_via_stdout": _reproduce_not_a_database_via_stdout,
    "not_a_database_message": _reproduce_not_a_database_message,
    "malformed_schema_message": _reproduce_malformed_schema_message,
    "disk_image_malformed_message": _reproduce_disk_image_malformed_message,
    "btree_index_named_fts": _reproduce_btree_index_named_fts,
}

_NORMALIZERS = {
    "fts5_corruption": lambda t: re.sub(r"blob \d+", "blob NNN", t),
    "fts5_missing_content_row_message": lambda t: re.sub(
        r"missing row \d+", "missing row NNN", t),
    "fts5_missing_row_from_healthy_index": lambda t: re.sub(
        r"missing row \d+", "missing row NNN", t),
    "fts5_shadow_table_btree_damage": lambda t: re.sub(
        r"Tree \d+ page \d+ cell \d+: Rowid \d+",
        "Tree N page N cell N: Rowid N", t),
    "orphan_pages": lambda t: re.sub(r"Page \d+:", "Page N:", t),
    "attached_database_header": lambda t: re.sub(
        r"Page \d+:", "Page N:", t),
    "malformed_schema_message": lambda t: re.sub(
        r"(malformed database schema \(.*?\)) - .*",
        r"\1 - ...", t),
}


def _compare(name, actual, expected):
    """Compare captured text against corpus, returning (result, detail)."""
    if actual == expected:
        return "matched", None
    if _sorted_lines(actual) == _sorted_lines(expected):
        return "matched (reordered)", None

    normalizer = _NORMALIZERS.get(name)
    if normalizer is not None:
        if normalizer(actual) == normalizer(expected):
            return "matched (structural)", None
        if _sorted_lines(normalizer(actual)) == _sorted_lines(
                normalizer(expected)):
            return "matched (structural, reordered)", None

    return "diverged", _diff_summary(actual, expected)


def _diff_summary(actual, expected):
    actual_lines = set(actual.split("\n"))
    expected_lines = set(expected.split("\n"))
    only_actual = actual_lines - expected_lines
    only_expected = expected_lines - actual_lines
    parts = []
    if only_expected:
        parts.append(f"  missing: {len(only_expected)} line(s)")
    if only_actual:
        parts.append(f"  extra: {len(only_actual)} line(s)")
    return "\n".join(parts) if parts else "  (texts differ)"


def main():
    version = sqlite3.sqlite_version
    requested = sys.argv[1:] if len(sys.argv) > 1 else None

    observed = [s for s in CORPUS if s.origin == OBSERVED]
    if requested:
        observed = [s for s in observed if s.name in requested]
        unknown = set(requested) - {s.name for s in observed}
        if unknown:
            print(f"Unknown or non-observed samples: {', '.join(sorted(unknown))}",
                  file=sys.stderr)

    col_name = max(len(s.name) for s in observed) if observed else 20
    col_ver = max(len(version), 7)
    header = (f"{'sample':<{col_name}}  {'sqlite':<{col_ver}}  result")
    print(header)
    print("-" * len(header))

    diverged = 0
    errors = 0

    for s in observed:
        reproducer = _REPRODUCERS.get(s.name)
        if reproducer is None:
            print(f"{s.name:<{col_name}}  {version:<{col_ver}}  "
                  f"no reproducer")
            continue

        tmp = tempfile.mkdtemp(prefix=f"repro-{s.name}-")
        try:
            actual = reproducer(tmp)
        except Exception as exc:
            print(f"{s.name:<{col_name}}  {version:<{col_ver}}  "
                  f"error: {exc}")
            errors += 1
            continue
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

        if actual is None:
            print(f"{s.name:<{col_name}}  {version:<{col_ver}}  "
                  f"skipped (missing module)")
            continue

        result, detail = _compare(s.name, actual, s.text)
        print(f"{s.name:<{col_name}}  {version:<{col_ver}}  {result}")
        if detail:
            print(detail)
            diverged += 1

    print()
    total = len(observed)
    print(f"SQLite {version}  "
          f"{total} samples, {diverged} diverged, {errors} error(s)")

    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
