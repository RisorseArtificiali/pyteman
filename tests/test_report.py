"""The results table names both halves of a row's identity.

RUN-01. A cell id is unique only within an experiment, so a table keyed on the
id alone renders two different runs of one cell as two rows that cannot be told
apart. These tests pin the disambiguation and the rendering that carries it.
"""

import sqlite3

import pytest

from conftest import LEGACY_SCHEMA
from pyteman.runner.matrix import run_matrix
from pyteman.runner.report import (_NO_EXPERIMENT, _PRE_PROVENANCE,
                                   MatrixReportError, _text, matrix_markdown)


# The labels below are compared through ``_text`` rather than spelled out in
# their escaped form. These tests are about which label a row earns, and the
# report escapes its own labels exactly as it escapes stored data, so writing
# "\\(pre\\-provenance\\)" here would couple a test of label *selection* to the
# escape scheme and break it on every future change. What the escape does is
# pinned in test_report_escaping.py, which is where a mutation to it must fail.
def body_rows(path):
    """The data rows: the first two lines are the header and its separator.

    Split on ``\\n`` rather than with ``splitlines``, which also breaks on
    \\x0b, \\x0c, \\x85, \\u2028 and \\u2029. Markdown ends a line on none of
    those, so a stored one would add a row here that no renderer sees, and the
    escape would be reported as broken for a character it handles correctly.
    """
    return [line for line in path.read_text().split("\n")[2:] if line]


def test_rows_from_different_experiments_are_distinguishable(tmp_path):
    db = str(tmp_path / "r.db")
    art = str(tmp_path / "art")
    cells = [{"id": "same", "params": {"x": 1}}]
    run_matrix(cells, lambda cell, adir: {"signature": "CLEAN"}, db, art,
               experiment="rev-A")
    run_matrix(cells, lambda cell, adir: {"signature": "NOTADB"}, db, art,
               experiment="rev-B")

    out = tmp_path / "m.md"
    matrix_markdown(db, str(out))

    rows = body_rows(out)
    assert len(rows) == 2
    assert len(set(rows)) == 2, "two runs of one cell id must not render alike"
    assert _text('"rev-A"') in rows[0] and "CLEAN" in rows[0]
    assert _text('"rev-B"') in rows[1] and "NOTADB" in rows[1]


def test_a_pre_provenance_database_still_renders(tmp_path):
    """The report reads databases older than the experiment column.

    Those rows say that what produced them is unknown, which is the honest
    rendering: the runner cannot tell which run produced them either.
    """
    db = str(tmp_path / "old.db")
    con = sqlite3.connect(db)
    con.execute(LEGACY_SCHEMA)
    con.execute("INSERT INTO results VALUES ('c1', 'done', ?, '/tmp/a')",
                ('{"signature": "CLEAN"}',))
    con.commit()
    con.close()

    out = tmp_path / "m.md"
    matrix_markdown(db, str(out))

    text = out.read_text()
    assert _text(_PRE_PROVENANCE) in text and "| c1 |" in text and "CLEAN" in text


def test_a_deliberate_absence_of_identity_reads_apart_from_an_unknown_one(tmp_path):
    """``experiment=None`` is a statement; a migrated row is a gap.

    Both land in the unnamespaced stratum, so the experiment column alone
    cannot separate them. The fingerprint can: the ``None`` row carries one
    because a run computed it, and the migrated row has none because no run
    ever did. Rendering them alike would print the migrated row's ignorance
    over the other row's claim, which is the misattribution this table exists
    to prevent.
    """
    db = str(tmp_path / "r.db")
    art = str(tmp_path / "art")
    run_matrix([{"id": "deliberate"}], lambda cell, adir: {"signature": "CLEAN"},
               db, art, experiment=None)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO results(experiment, cell_id, fingerprint, cell_json, "
                "status, result_json, artifact_dir) "
                "VALUES ('', 'migrated', NULL, NULL, 'done', ?, '/tmp/a')",
                ('{"signature": "CLEAN"}',))
    con.commit()
    con.close()

    out = tmp_path / "m.md"
    matrix_markdown(db, str(out))

    rendered = {row.split("|")[2].strip(): row.split("|")[1].strip()
                for row in body_rows(out)}
    assert rendered["deliberate"] == _text(_NO_EXPERIMENT)
    assert rendered["migrated"] == _text(_PRE_PROVENANCE)


def test_a_status_that_would_break_the_table_is_escaped(tmp_path):
    """No column is trusted, because the report reads foreign databases.

    The status is the one column a caller never supplies, so it is the easiest
    to assume safe. It is not: ``_read`` deliberately renders results tables
    this runner did not write, and one of those can hold anything at all.
    """
    db = str(tmp_path / "r.db")
    con = sqlite3.connect(db)
    con.execute(LEGACY_SCHEMA)
    con.execute("INSERT INTO results VALUES ('c1', 'do|ne', '{}', '/tmp/a')")
    con.commit()
    con.close()

    out = tmp_path / "m.md"
    matrix_markdown(db, str(out))

    row = body_rows(out)[0]
    delimiters = row.replace("\\|", "").count("|")
    assert delimiters == 5, f"the status split the row into extra cells: {row!r}"
    assert "do\\|ne" in row


def test_text_that_would_break_the_table_is_escaped(tmp_path):
    """A pipe or a newline in an id would split or merge rows.

    The three ids here differ only in characters the table itself uses. They
    have to stay three distinct rows: a rendering that collapses them is the
    same misattribution as a table with no experiment column at all.

    The runner refuses a backslash in a cell id, because the id also names a
    directory, so the third one is written straight into the table. That is
    not a contrivance to reach the branch: ``_read`` renders results tables
    this runner did not write, and the backslash is exactly what makes a
    literal ``\\n`` and a real newline print alike if it is not escaped first.
    """
    db = str(tmp_path / "r.db")
    art = str(tmp_path / "art")
    for cell_id in ("a|b", "a\nb"):
        run_matrix([{"id": cell_id}], lambda cell, adir: {}, db, art, experiment="x")
    con = sqlite3.connect(db)
    con.execute("INSERT INTO results(experiment, cell_id, fingerprint, cell_json, "
                "status, result_json, artifact_dir) "
                "VALUES ('\"x\"', 'a\\nb', 'ff', NULL, 'done', '{}', '/tmp/a')")
    con.commit()
    con.close()

    out = tmp_path / "m.md"
    matrix_markdown(db, str(out))

    rows = body_rows(out)
    assert len(rows) == 3, "three cells must render as exactly three rows"
    assert len(set(rows)) == 3, "ids that differ must render differently"


def test_a_file_with_no_results_table_says_so(tmp_path):
    """RUN-03. The report is where a wrong path surfaces, so it has to name it.

    sqlite opens any name it is handed and invents an empty database for the
    ones that do not exist, so a typo in the path produces a file rather than
    an error. Left to the query, that arrived as ``no such table: results``
    from three frames down, which reads as a corrupt results db rather than as
    the mistyped path it almost always is.
    """
    db = str(tmp_path / "empty.db")
    sqlite3.connect(db).close()

    with pytest.raises(MatrixReportError) as excinfo:
        matrix_markdown(db, str(tmp_path / "m.md"))

    message = str(excinfo.value)
    assert "empty.db" in message, "the failure did not name the file"
    # The guidance, not just the type: a bare "no such table" is already a
    # MatrixReportError by the time it reaches the caller, so asserting the
    # type alone would pass with this branch deleted.
    assert "Check the path" in message


def test_a_file_that_is_not_a_database_says_so(tmp_path):
    """The other half of the same mistake, which fails one step earlier.

    A path that points at something real but unrelated fails in the PRAGMA
    rather than in the query, so it cannot be caught by the table check above.
    It reaches the caller as the same error type, because from where the caller
    stands the two are one mistake: this is not the results db.
    """
    db = tmp_path / "not.db"
    db.write_text("this is not a database\n")

    with pytest.raises(MatrixReportError) as excinfo:
        matrix_markdown(str(db), str(tmp_path / "m.md"))

    assert "not.db" in str(excinfo.value), "the failure did not name the file"


def test_a_foreign_result_that_is_not_a_mapping_is_labelled_not_guessed(tmp_path):
    """Two different faults used to print as the same bare ``?``.

    The runner's own contract now refuses both before they reach a row, so
    these can only arrive from a database something else wrote, which is
    precisely the case the report promises to render. A result that is not JSON
    and a result that is JSON but not a mapping need different fixes, and one
    shared ``?`` told the reader neither.
    """
    db = str(tmp_path / "foreign.db")
    con = sqlite3.connect(db)
    con.execute(LEGACY_SCHEMA)
    con.execute("INSERT INTO results VALUES ('listy', 'done', '[1, 2]', '/tmp/a')")
    con.execute("INSERT INTO results VALUES ('broken', 'done', 'not json', '/tmp/a')")
    con.commit()
    con.close()

    out = tmp_path / "m.md"
    matrix_markdown(db, str(out))

    signature = {row.split("|")[2].strip(): row.split("|")[4].strip()
                 for row in body_rows(out)}
    assert signature["listy"] == _text("(result is not a mapping)")
    assert signature["broken"] == _text("(unreadable result)")


def test_a_result_column_that_never_held_text_is_labelled_too(tmp_path):
    """The same rendering, reached by the route sqlite affinity leaves open.

    This runner declares ``result_json TEXT``, and TEXT affinity quietly turns
    a stored ``42`` back into ``'42'``, which parses. A foreign table need not
    declare the column at all, and without affinity the integer survives the
    round trip intact. ``json.loads`` raises ``TypeError`` on it rather than
    the ``ValueError`` every textual fault raises, so a handler written for
    unreadable text alone lets this one escape the report entirely.
    """
    db = str(tmp_path / "untyped.db")
    con = sqlite3.connect(db)
    # No declared type: BLOB affinity, so nothing is coerced on the way in.
    con.execute("CREATE TABLE results(cell_id, status, result_json, artifact_dir)")
    con.execute("INSERT INTO results VALUES ('numeric', 'done', 42, '/tmp/a')")
    con.commit()
    con.close()

    out = tmp_path / "m.md"
    matrix_markdown(db, str(out))

    assert body_rows(out)[0].split("|")[4].strip() == _text("(unreadable result)")


def test_a_path_that_cannot_be_opened_at_all_says_so(tmp_path):
    """The third way to hand the report the wrong file, and the earliest.

    A name under a directory that does not exist never gets as far as a
    database: sqlite fails in the open rather than inventing the file, because
    it is lazy about parsing the header and not about the open. The report
    creates no directories, unlike ``run_matrix``, which makes the parent
    before it connects, so this is reachable here and not there.
    """
    missing = tmp_path / "no-such-dir" / "r.db"

    with pytest.raises(MatrixReportError) as excinfo:
        matrix_markdown(str(missing), str(tmp_path / "m.md"))

    message = str(excinfo.value)
    assert "r.db" in message, "the failure did not name the file"
    assert "could not be opened" in message, (
        "an open failure was reported as a read failure")


def test_a_falsy_stored_result_is_not_read_as_an_empty_one(tmp_path):
    """The falsy fold again, on the read side, where a foreign row still has it.

    The runner's own contract now refuses ``0`` and ``False`` before they can
    reach a row, and that fix is what makes this one visible: a reader that
    folds the same values into ``{}`` undoes it for every row the runner did
    not write. ``0`` and ``b''`` here rendered as a blank signature, which is
    what a cell that ran and reported nothing renders as, while ``42`` in the
    very same untyped column was labelled unreadable. Only NULL means nothing
    was recorded, so only NULL gets the empty default.
    """
    db = str(tmp_path / "falsy.db")
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE results(cell_id, status, result_json, artifact_dir)")
    for cid, stored in (("zero", 0), ("emptyblob", b""), ("emptytext", ""),
                        ("nothing", None)):
        con.execute("INSERT INTO results VALUES (?, 'done', ?, '/tmp/a')",
                    (cid, stored))
    con.commit()
    con.close()

    out = tmp_path / "m.md"
    matrix_markdown(db, str(out))

    signature = {row.split("|")[2].strip(): row.split("|")[4].strip()
                 for row in body_rows(out)}
    assert signature["zero"] == _text("(unreadable result)")
    assert signature["emptyblob"] == _text("(unreadable result)")
    assert signature["emptytext"] == _text("(unreadable result)")
    # The one value that genuinely says nothing was recorded, and so the one
    # that must keep rendering as the empty result it is.
    assert signature["nothing"] == ""


# --------------------------------------------------------------------------
# Foreign tables carrying only one of the two provenance columns.
# --------------------------------------------------------------------------
#
# Rendering tables this runner did not write is a promised capability, so a
# table can arrive with either provenance column alone. Each column is read on
# its own: what a table can say about a row is rendered, and only what it
# cannot say is reported as unknown.

def _foreign_results(path, provenance, rows):
    """A results table holding the required columns plus `provenance`.

    `rows` are (experiment, fingerprint, cell_id) triples; the value for a
    column this shape does not have is dropped rather than stored.
    """
    order = [name for name in ("experiment", "fingerprint") if name in provenance]
    declarations = ", ".join(
        f"{name} TEXT" for name in order + ["cell_id", "status", "result_json"])
    con = sqlite3.connect(path)
    con.execute(f"CREATE TABLE results({declarations})")
    for experiment, fingerprint, cell_id in rows:
        present = {"experiment": experiment, "fingerprint": fingerprint}
        values = [present[name] for name in order] + [cell_id, "done",
                                                      '{"signature": "CLEAN"}']
        placeholders = ", ".join("?" * len(values))
        con.execute(f"INSERT INTO results VALUES ({placeholders})", values)
    con.commit()
    con.close()


def test_an_experiment_column_without_a_fingerprint_is_still_rendered(tmp_path):
    """The regression: a half-provenance table keeps the half it has.

    Rows are inserted in reverse, so the assertion on their order fails if the
    experiment stops reaching the ORDER BY as well as if it stops reaching the
    table. Discarding the column collapses these two rows into duplicates that
    are identical byte for byte, and labels both as though what produced them
    were unknown, over rows that name it.
    """
    db = str(tmp_path / "half.db")
    _foreign_results(db, ("experiment",),
                     [("rev-B", None, "same"), ("rev-A", None, "same")])

    out = tmp_path / "m.md"
    matrix_markdown(db, str(out))

    rows = body_rows(out)
    assert len(set(rows)) == 2, "two experiments of one cell rendered alike"
    assert _text("rev-A") in rows[0], "the experiment the table holds was discarded"
    assert _text("rev-B") in rows[1]
    assert _text(_PRE_PROVENANCE) not in out.read_text(), \
        "a row that names its experiment was reported as unknown"


SHAPES = [
    ("both columns", ("experiment", "fingerprint"), "rev-A"),
    ("experiment only", ("experiment",), "rev-A"),
    # No experiment column, but a fingerprint says a run claimed this row, so
    # the gap is a missing name and not a missing origin.
    ("fingerprint only", ("fingerprint",), _NO_EXPERIMENT),
    # Neither column: nothing claims the row, which is what the label reports.
    ("neither column", (), _PRE_PROVENANCE),
]


@pytest.mark.parametrize("label,provenance,expected", SHAPES,
                         ids=[shape[0] for shape in SHAPES])
def test_each_provenance_shape_earns_the_label_its_columns_support(
        tmp_path, label, provenance, expected):
    db = str(tmp_path / "shape.db")
    _foreign_results(db, provenance, [("rev-A", "fp-1", "c1")])

    out = tmp_path / "m.md"
    matrix_markdown(db, str(out))

    rows = body_rows(out)
    assert len(rows) == 1
    assert rows[0].split("|")[1].strip() == _text(expected)
    assert "CLEAN" in rows[0], "the row itself stopped rendering"


def test_a_results_table_missing_a_required_column_is_still_refused(tmp_path):
    """Reading a column a table does not have stays an error about the file.

    Provenance is optional and the three columns the report projects are not,
    so widening the first must not quietly widen the second.
    """
    db = str(tmp_path / "short.db")
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE results(experiment TEXT, cell_id TEXT)")
    con.commit()
    con.close()

    with pytest.raises(MatrixReportError) as excinfo:
        matrix_markdown(db, str(tmp_path / "m.md"))
    assert "could not be read" in str(excinfo.value)
