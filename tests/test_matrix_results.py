"""What ``run_cell`` may return, and what happens when the row cannot be kept.

RUN-03. Two failures used to be invisible. A callback that returned ``0`` or
``[]`` instead of a mapping was folded into ``{}`` by a bare ``or {}`` and
recorded as a cell that succeeded and reported nothing, which is exactly what a
correct cell looks like. And a db that refused the row raised out of the run
with nothing said about which cell had been lost. These tests pin the contract
that separates the first case from a genuine empty result, and the boundary
that keeps the second from being reported as the cell's own fault.
"""

import json
import sqlite3

import pytest

from pyteman.runner.matrix import (MatrixIdentityError, MatrixStorageError,
                                   _coerced_keys, run_matrix)


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


# --------------------------------------------------------------------------
# Mapping keys JSON would rewrite.
# --------------------------------------------------------------------------
#
# TASK-66. A result is read back by key, and ``json.dumps`` coerces int, float,
# bool and None keys to strings. Stored unchecked, the object handed to the
# caller and the row left behind disagree about what the keys are: a reader
# indexing the returned mapping by ``1`` finds the entry, and the same reader
# indexing the stored row finds nothing. The row is the durable half, so the
# disagreement outlives the run that produced it.
#
# The same coercion is already fatal in a cell definition, where
# ``_reject_coerced_keys`` refuses it because two definitions would otherwise
# share a fingerprint. These tests hold the result side to the same answer for
# a different reason: no fingerprint is involved here, only the contradiction
# between the two records of one result.

COERCED = [("int", 1), ("bool", True), ("float", 1.5), ("none", None)]


@pytest.mark.parametrize("name,key", COERCED, ids=[c[0] for c in COERCED])
def test_a_key_json_would_rewrite_is_refused_rather_than_stored(tmp_path, name, key):
    """Each key type ``json.dumps`` coerces, refused at the top level.

    The repr of the key is asserted, not merely the failure: a refusal that
    does not name the key leaves the caller to find it, and a test that checks
    only the status passes for a fixture error too.
    """
    db = str(tmp_path / "r.db")
    out = run_matrix([{"id": "c"}], lambda cell, adir: {key: "v"}, db,
                     str(tmp_path / "art"), experiment="x")

    assert out[0]["status"] == "failed"
    error = out[0]["result"]["error"]
    assert repr(key) in error, f"the refusal did not name the key: {error!r}"
    status, stored = stored_rows(db)["c"]
    assert status == "failed"
    assert '"v"' not in stored, "the coerced mapping was stored anyway"


NESTED = [
    ("under a key", lambda bad: {"outer": bad}),
    ("inside a list", lambda bad: {"outer": [bad]}),
    ("inside a tuple", lambda bad: {"outer": (bad,)}),
    ("two levels down", lambda bad: {"a": {"b": [bad]}}),
]


@pytest.mark.parametrize("label,wrap", NESTED, ids=[n[0] for n in NESTED])
def test_a_coerced_key_below_the_top_level_is_refused_too(tmp_path, label, wrap):
    """Depth does not launder the key.

    A result is a tree, and ``json.dumps`` rewrites a coerced key wherever it
    sits. Checking only the top level would leave the contradiction intact one
    level down, which is where a result of any size actually keeps its data.
    Lists and tuples are walked because JSON flattens both to arrays, so a
    mapping reached through either is stored exactly as one reached directly.
    """
    db = str(tmp_path / "r.db")
    out = run_matrix([{"id": "c"}], lambda cell, adir: wrap({7: "v"}), db,
                     str(tmp_path / "art"), experiment="x")

    assert out[0]["status"] == "failed"
    assert "7" in out[0]["result"]["error"]
    assert stored_rows(db)["c"][0] == "failed"


VALID = [
    ("flat", {"a": 1}),
    ("nested mapping", {"a": {"b": "c"}}),
    ("through a list", {"a": [{"b": "c"}]}),
    ("through a tuple", {"a": ({"b": "c"},)}),
    ("empty", {}),
    ("no mappings at all", {"a": [1, 2, 3]}),
]


@pytest.mark.parametrize("label,result", VALID, ids=[v[0] for v in VALID])
def test_string_keys_at_every_depth_are_still_accepted(tmp_path, label, result):
    """The controls, and the reason the tests above are not vacuous.

    A refusal that fired on every result would satisfy each rejection test in
    this section while making the runner useless. These are the shapes that
    must keep passing, at the same depths the refusals are checked at.
    """
    db = str(tmp_path / "r.db")
    out = run_matrix([{"id": "c"}], lambda cell, adir: result, db,
                     str(tmp_path / "art"), experiment="x")

    assert out[0]["status"] == "done", out[0]["result"]
    assert stored_rows(db)["c"][0] == "done"


def test_two_keys_that_collapse_before_the_runner_sees_them_are_refused(tmp_path):
    """The case from the report, and what can honestly be asserted about it.

    ``{1: 'a', True: 'b'}`` never reaches the runner as two entries: ``True``
    and ``1`` are equal and hash alike, so Python has already collapsed them to
    the single entry ``{1: 'b'}`` while the literal is being built, and ``'a'``
    is gone before any code here runs. Nothing downstream can recover it or
    report that a key was lost, so what this test holds is the part that is
    still in reach: one key survives, it is a key JSON would rewrite, and it is
    refused rather than written down as ``{"1": "b"}``.
    """
    collapsed = {1: "a", True: "b"}
    assert collapsed == {1: "b"}, "the premise of this test no longer holds"

    db = str(tmp_path / "r.db")
    out = run_matrix([{"id": "c"}], lambda cell, adir: dict(collapsed), db,
                     str(tmp_path / "art"), experiment="x")

    assert out[0]["status"] == "failed"
    assert stored_rows(db)["c"][1] != '{"1": "b"}', (
        "the coerced key was stored as the record of this cell")


def test_the_returned_result_and_the_stored_row_agree_about_keys(tmp_path):
    """The defect stated directly: two records of one result, one contract.

    Before the refusal these disagreed. The callback's mapping was handed back
    with the key ``1`` and written down with the key ``"1"``, so a reader
    indexing the returned object found the entry and the same reader indexing
    the stored row did not. Asserted over both a refused result and an accepted
    one, because agreement that only held for failures would be satisfied by a
    runner that refused everything.
    """
    db = str(tmp_path / "r.db")
    art = str(tmp_path / "art")
    out = run_matrix([{"id": "bad"}, {"id": "good"}],
                     lambda cell, adir: {1: "v"} if cell["id"] == "bad"
                     else {"1": "v"},
                     db, art, experiment="x")

    written = stored_rows(db)
    for returned in out:
        stored = json.loads(written[returned["cell_id"]][1])
        assert set(stored) == {str(k) for k in returned["result"]}, (
            "the returned object and the stored row disagree about the keys")
        assert list(returned["result"]) == list(stored), (
            "a key was rewritten on its way into the row")


def test_a_refused_key_costs_its_own_cell_and_not_the_matrix(tmp_path):
    """The same boundary every other result fault sits on.

    A key the callback chose is that callback's bug, so it is charged to its
    cell and the queue behind it still runs. The attempts row is asserted as
    well as the results row: the attempt is the record that the cell was tried,
    and a refusal that skipped it would leave the run with no evidence the
    cell had been reached at all.
    """
    db = str(tmp_path / "r.db")
    ran = []

    def run_cell(cell, adir):
        ran.append(cell["id"])
        return {1: "v"} if cell["id"] == "c1" else {"signature": "CLEAN"}

    out = run_matrix([{"id": "c1"}, {"id": "c2"}], run_cell, db,
                     str(tmp_path / "art"), experiment="x")

    assert ran == ["c1", "c2"], "a refused key stopped the cells behind it"
    assert [r["status"] for r in out] == ["failed", "done"]
    con = sqlite3.connect(db)
    try:
        attempts = dict(con.execute("SELECT cell_id, status FROM attempts"))
    finally:
        con.close()
    assert attempts == {"c1": "failed", "c2": "done"}


def test_the_mapping_the_callback_returned_is_not_altered(tmp_path):
    """Detection reads the result; it does not repair it.

    Normalising the keys instead of refusing them would make the two records
    agree by rewriting one of them, which is the coercion this contract exists
    to stop rather than a fix for it. The callback still holds a reference to
    what it returned, so the check has to leave that object exactly as it was.
    """
    returned = {1: "v", "nested": [{2: "w"}]}
    before = repr(returned)

    run_matrix([{"id": "c"}], lambda cell, adir: returned, str(tmp_path / "r.db"),
               str(tmp_path / "art"), experiment="x")

    assert repr(returned) == before, "the result the callback returned was rewritten"


def test_a_coerced_key_in_a_definition_is_still_the_matrix_s_fault(tmp_path):
    """The definition side keeps its own, stricter answer, and its own error.

    Both sides now refuse the same coercion, which makes it easy to collapse
    them into one mechanism and lose the distinction: a definition is refused
    before any cell runs, because its fingerprint would be shared, and a result
    is refused after its cell has run, because only that cell is at fault. The
    types differ for that reason, and so does the moment.
    """
    ran = []
    with pytest.raises(MatrixIdentityError):
        run_matrix([{"id": "c", "params": {1: "a"}}],
                   lambda cell, adir: ran.append(cell["id"]),
                   str(tmp_path / "r.db"), str(tmp_path / "art"), experiment="x")

    assert ran == [], "a refused definition still ran its cell"


def test_a_result_too_tangled_to_walk_is_still_one_cell_s_failure(tmp_path):
    """A cycle and a very deep result are faults of the cell, not of the run.

    Both were already cell failures, because neither can be serialised, and the
    key check walks the same structure the serialiser does, so both now reach
    the walk first. What must not change is where the cost lands: the cell
    fails, the diagnostic says so, and the cell behind it still runs.
    """
    db = str(tmp_path / "r.db")
    ran = []

    def run_cell(cell, adir):
        ran.append(cell["id"])
        if cell["id"] == "cyclic":
            result = {}
            result["self"] = result
            return result
        return {"signature": "CLEAN"}

    out = run_matrix([{"id": "cyclic"}, {"id": "after"}], run_cell, db,
                     str(tmp_path / "art"), experiment="x")

    assert ran == ["cyclic", "after"], "a tangled result stopped the run"
    assert [r["status"] for r in out] == ["failed", "done"]
    assert out[0]["result"]["error"], "the failure was recorded without a reason"


def _nest(depth, leaf):
    """`leaf` buried `depth` mappings down, reached through a list each time."""
    obj = leaf
    for _ in range(depth):
        obj = {"a": [obj]}
    return obj


def _serialisable_depth(ceiling=4000):
    """A nesting this interpreter's ``json.dumps`` demonstrably accepts.

    Measured here rather than written down, because the depth a serialiser
    reaches is a property of the build and not of the library, and a literal
    picked on one build is a test that fails on another. Half of the first
    accepted depth is returned rather than that depth itself: acceptance here
    is measured with an empty stack, while the run calls the serialiser from
    under the cell's own frames and needs room left for them.
    """
    depth = ceiling
    while depth > 1:
        try:
            json.dumps(_nest(depth, {"ok": 1}))
            return max(1, depth // 2)
        except RecursionError:
            depth //= 2
    return 1


def test_the_key_walk_survives_a_nesting_that_would_end_a_recursive_one():
    """The walk itself, with no serialiser in the picture.

    This is the guarantee the screen rests on, so it is asserted directly
    rather than inferred from a stored row: the walk is bounded by the
    recursion limit and nothing else, so a depth well past what a recursive
    walk survives is a live detector on every build rather than on whichever
    one is handy.

    Both outcomes are asserted, because only one of them is hard. Finding
    nothing in a deep clean structure is what a walk that quietly gave up would
    also report, so the coerced half is what distinguishes a walk that reached
    the bottom from one that merely returned.
    """
    deep = 5000

    assert list(_coerced_keys(_nest(deep, {"ok": 1}))) == []
    assert list(_coerced_keys(_nest(deep, {7: "v"}))) == [7]


def test_the_key_screen_is_not_more_fragile_than_the_serialiser(tmp_path):
    """A result the serialiser can store must not be failed by the check on it.

    The screen sits in front of ``json.dumps``, so anything it cannot get
    through is a result that never reaches the row. The depth is whatever this
    interpreter has just been shown to serialise, which is the only depth the
    claim is meaningful at: asking for a row the serialiser itself would refuse
    tests the interpreter's recursion handling rather than this code.

    The second half is the trap the first one sets. Made sturdy by letting a
    walk failure through to the serialiser instead, the same structure with a
    coerced key at the bottom would have been stored coerced, which is the
    defect this section exists to close, reappearing below the depth the check
    can reach. So both halves are asserted together: deep and clean is stored,
    deep and coerced is refused. How deep that is varies by build, so the walk
    is also tested directly above, where the depth does not depend on one.
    """
    depth = _serialisable_depth()
    # The premise, stated as an assertion rather than assumed: everything below
    # is about what the screen does with a result the serialiser would accept.
    json.dumps(_nest(depth, {"ok": 1}))

    db = str(tmp_path / "r.db")
    out = run_matrix([{"id": "clean"}, {"id": "coerced"}],
                     lambda cell, adir: _nest(depth, {"ok": 1})
                     if cell["id"] == "clean" else _nest(depth, {7: "v"}),
                     db, str(tmp_path / "art"), experiment="x")

    assert out[0]["status"] == "done", out[0]["result"]
    assert out[1]["status"] == "failed"
    assert "7" in out[1]["result"]["error"]


def test_a_cycle_is_still_named_as_a_cycle(tmp_path):
    """The screen must not take the serialiser's better diagnosis away.

    A self-referential result is reported as a circular reference, which says
    what is wrong with it. A walk that recursed into the cycle would have
    replaced that with a bare ``RecursionError``, describing the walker rather
    than the result.
    """
    db = str(tmp_path / "r.db")

    def run_cell(cell, adir):
        result = {}
        result["self"] = result
        return result

    out = run_matrix([{"id": "c"}], run_cell, db, str(tmp_path / "art"),
                     experiment="x")

    assert out[0]["status"] == "failed"
    assert "Circular reference" in out[0]["result"]["error"], out[0]["result"]


# The rule above is about results, and the definition screen that predates it
# must come through untouched. These two pin the parts of it that a shared
# traversal would have quietly rewritten: which key is named when a definition
# holds more than one, and what a definition too hostile to walk earns. Both
# were measured on the base revision and both changed under a first attempt
# that served definitions and results from one walk, which is why they are
# written down here rather than trusted to review.

def test_a_definition_still_names_the_key_the_old_walk_named_first(tmp_path):
    """Depth first, so the nested key is reported before the later root key.

    The order is not decoration. The message names one key, on the argument
    that a caller who can fix that key can fix the rest, so the key it picks
    is the whole of what the caller is told. A traversal that drained the root
    before descending would name ``2`` here and send someone to a different
    part of their definition than every previous release did.
    """
    db = str(tmp_path / "r.db")
    cell = {"id": "c", "params": {"a": {1: "x"}, 2: "y"}}

    with pytest.raises(MatrixIdentityError) as excinfo:
        run_matrix([cell], lambda c, adir: {}, db, str(tmp_path / "art"),
                   experiment="x")

    assert "mapping key 1" in str(excinfo.value), str(excinfo.value)


def test_a_cyclic_definition_is_still_stopped_by_the_interpreter(tmp_path):
    """The definition walk recurses, and that is the behaviour being kept.

    A cycle exhausts the stack there rather than reaching the serialiser, so
    the refusal quotes a ``RecursionError``. The result screen deliberately
    behaves the other way, reporting the circular reference by name, and the
    difference between the two is the point: making them agree means changing
    what a definition earns, which is a contract this task does not open.
    """
    db = str(tmp_path / "r.db")
    cell = {"id": "c", "params": {}}
    cell["params"]["self"] = cell["params"]

    with pytest.raises(MatrixIdentityError) as excinfo:
        run_matrix([cell], lambda c, adir: {}, db, str(tmp_path / "art"),
                   experiment="x")

    assert "RecursionError" in str(excinfo.value), str(excinfo.value)
