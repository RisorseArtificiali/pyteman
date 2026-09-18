"""What ``run_cell`` may return, and what happens when the row cannot be kept.

RUN-03. Two failures used to be invisible. A callback that returned ``0`` or
``[]`` instead of a mapping was folded into ``{}`` by a bare ``or {}`` and
recorded as a cell that succeeded and reported nothing, which is exactly what a
correct cell looks like. And a db that refused the row raised out of the run
with nothing said about which cell had been lost. These tests pin the contract
that separates the first case from a genuine empty result, and the boundary
that keeps the second from being reported as the cell's own fault.
"""

import sqlite3

import pytest

from pyteman.runner.matrix import MatrixStorageError, run_matrix


def stored_rows(db):
    """The rows as written, keyed by cell id.

    Named apart from ``rows`` in tests/test_matrix_identity.py, which is a
    different shape: that one returns a list of full provenance tuples, this
    one a dict of the three columns these tests assert on.
    """
    con = sqlite3.connect(db)
    try:
        return {r[0]: r[1:] for r in con.execute(
            "SELECT cell_id, status, result_json FROM results")}
    finally:
        con.close()


def refuse_writes(db):
    """Make every later INSERT fail while leaving the table readable.

    Stands in for a full disk or a revoked permission, deterministically. A
    trigger rather than a dropped table because the rows have to stay
    selectable: showing that nothing was recorded means reading the table that
    refused the write.
    """
    con = sqlite3.connect(db)
    try:
        con.execute("CREATE TRIGGER refuse BEFORE INSERT ON results "
                    "BEGIN SELECT RAISE(ABORT, 'database or disk is full'); END")
        con.commit()
    finally:
        con.close()


@pytest.mark.parametrize("returned,name", [
    (0, "int"), (False, "bool"), ("", "str"), ([], "list"),
])
def test_a_falsy_return_is_not_an_empty_result(tmp_path, returned, name):
    """The four values the old ``or {}`` erased, and the reason for the contract.

    Each of these is almost certainly a callback bug: a function that fell
    through to a default, or returned a count or a list where a mapping was
    meant. Folded into ``{}`` they were indistinguishable from a cell that ran
    correctly and had nothing to report, so the bug was recorded as a success
    and the run said nothing. The type is named in the message because that is
    the one fact that points at the line to fix.
    """
    db = str(tmp_path / "r.db")
    out = run_matrix([{"id": "c"}], lambda cell, adir: returned, db,
                     str(tmp_path / "art"), experiment="x")

    assert out[0]["status"] == "failed"
    assert name in out[0]["result"]["error"]
    status, stored = stored_rows(db)["c"]
    assert status == "failed"
    assert stored != "{}", "a falsy return was stored as an empty result"


def test_none_and_an_empty_mapping_both_mean_nothing_to_report(tmp_path):
    """The two returns the contract keeps, and keeps equal.

    ``None`` is what a callback returns when it never wrote a return statement
    at all, which is the ordinary way to say a cell did its work and produced
    no signature. Refusing it would make the contract cost more than the bug it
    prevents, so it is the one falsy value that stays.
    """
    db = str(tmp_path / "r.db")
    art = str(tmp_path / "art")
    out = run_matrix([{"id": "implicit"}, {"id": "explicit"}],
                     lambda cell, adir: None if cell["id"] == "implicit" else {},
                     db, art, experiment="x")

    assert [r["status"] for r in out] == ["done", "done"]
    assert [r["result"] for r in out] == [{}, {}]
    written = stored_rows(db)
    assert written["implicit"] == ("done", "{}")
    assert written["explicit"] == ("done", "{}")


def test_a_non_mapping_return_costs_its_own_cell_and_not_the_matrix(tmp_path):
    """A wrong return type is one cell's bug, so it is charged to that cell.

    The alternative, raising out of the run, would throw away the outcome of
    every cell queued behind the broken one, and the matrix exists to run cells
    that do not depend on each other. So the check sits inside the guard that
    already covers the callback, and arrives as an ordinary failed row.
    """
    db = str(tmp_path / "r.db")
    ran = []

    def run_cell(cell, adir):
        ran.append(cell["id"])
        return [1, 2] if cell["id"] == "c1" else {"signature": "CLEAN"}

    out = run_matrix([{"id": "c1"}, {"id": "c2"}], run_cell, db,
                     str(tmp_path / "art"), experiment="x")

    assert ran == ["c1", "c2"], "a bad return stopped the cells behind it"
    assert [r["status"] for r in out] == ["failed", "done"]
    stored = stored_rows(db)
    assert stored["c1"][0] == "failed" and stored["c2"][0] == "done"


def test_a_db_that_refuses_the_row_stops_the_run_and_names_the_cell(tmp_path):
    """Persistence failure is the one failure that cannot be written down.

    Recording it as a failed row would require the write that just failed, so
    the only honest outcome is to raise. The run stops rather than spending the
    remaining cells writing into the same hole, and the message carries the
    cell id and the attempt directory, because those artifacts are the only
    evidence of the cell that did run.

    The trigger stands in for a full disk or a revoked permission: it is the
    deterministic way to make the INSERT fail while leaving the table readable,
    which is what lets this test assert that nothing was recorded.
    """
    db = str(tmp_path / "r.db")
    art = str(tmp_path / "art")
    run_matrix([{"id": "seed"}], lambda cell, adir: {}, db, art, experiment="x")
    refuse_writes(db)

    ran = []

    def run_cell(cell, adir):
        ran.append(cell["id"])
        return {"signature": "CLEAN"}

    with pytest.raises(MatrixStorageError) as excinfo:
        run_matrix([{"id": "c1"}, {"id": "c2"}], run_cell, db, art, experiment="x")

    message = str(excinfo.value)
    assert "'c1'" in message, f"the failure did not name the cell: {message!r}"
    assert "c1." in message, f"the failure did not name the artifacts: {message!r}"
    assert ran == ["c1"], "the run carried on writing into a db that refuses rows"
    assert "c1" not in stored_rows(db), "a row was reported stored when it was not"


def test_a_broken_cell_and_a_broken_db_do_not_arrive_as_the_same_thing(tmp_path):
    """The two failure kinds must be told apart by what they do, not just named.

    A cell that returns the wrong shape is at fault and its neighbours are not,
    so it is recorded and the matrix goes on. A db that will not take the row
    says nothing about the cell, and going on would produce results nothing is
    keeping, so it is raised and the run stops. Recorded-versus-raised is the
    whole distinction, and neither half states it alone: this is the one test
    that puts both against the same db and asserts they diverge.
    """
    db = str(tmp_path / "r.db")
    art = str(tmp_path / "art")

    contract = run_matrix([{"id": "bad"}], lambda cell, adir: 0, db, art,
                          experiment="x")

    # Returning at all is half the claim: a contract breach must not raise.
    # The other half is the attribution, and it is read off the stored row
    # rather than the returned dict because the row is what survives the run.
    # Without it, a MatrixStorageError raised from _cell_result would satisfy
    # every other test in this file, since the callback guard would record it
    # as a failed row all the same.
    assert contract[0]["status"] == "failed"
    stored_status, stored_result = stored_rows(db)["bad"]
    assert stored_status == "failed"
    assert "MatrixResultError" in stored_result, (
        "a cell's own fault was attributed to storage")

    refuse_writes(db)

    with pytest.raises(MatrixStorageError):
        run_matrix([{"id": "good"}], lambda cell, adir: {"signature": "CLEAN"},
                   db, art, experiment="x")


def test_a_supersession_that_could_not_be_written_archives_nothing(tmp_path):
    """A run that fails to replace a row must not claim it replaced it.

    Superseding is two writes: the old row is copied into results_superseded
    and the new one replaces it, and they are one transaction precisely so that
    half of it cannot survive. This is the storage-failure half of that
    guarantee. tests/test_matrix_identity.py covers the interrupted-run half,
    where the process dies mid-cell; here the cell finishes and the db refuses
    the replacement, which reaches the archive through a different path: the
    row is already pending when the failure arrives.

    What is pinned is the property, not the line that currently delivers it.
    The ``con.rollback()`` in that guard can be deleted without failing this
    test, because the ``finally: con.close()`` discards the same pending row.
    That is a statement about today's control flow rather than about the
    contract, and the contract is what a test should hold: a stored archive row
    asserts that a supersession happened, and none did.
    """
    db = str(tmp_path / "r.db")
    art = str(tmp_path / "art")
    original = [{"id": "c", "params": {"n": 1}}]
    run_matrix(original, lambda cell, adir: {"signature": "CLEAN"}, db, art,
               experiment="x")
    refuse_writes(db)

    changed = [{"id": "c", "params": {"n": 2}}]
    with pytest.raises(MatrixStorageError):
        run_matrix(changed, lambda cell, adir: {"signature": "CLEAN"}, db, art,
                   experiment="x", on_mismatch="rerun")

    con = sqlite3.connect(db)
    try:
        archived = con.execute("SELECT COUNT(*) FROM results_superseded").fetchone()[0]
        live = con.execute("SELECT result_json FROM results WHERE cell_id='c'").fetchone()
    finally:
        con.close()
    assert archived == 0, "a supersession that never happened left a record saying it did"
    assert live is not None, "the row that was not replaced was lost anyway"
