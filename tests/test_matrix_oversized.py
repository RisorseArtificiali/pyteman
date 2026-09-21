"""A result sqlite refuses for its size, rather than for the database's health.

Reached with ``SQLITE_LIMIT_LENGTH`` lowered on the connection the runner opens
for itself. The real ceiling is a billion bytes, so the honest alternative is
allocating a payload that large; the limit is a property of the connection and
not of the statement, so lowering it exercises the same sqlite code path at a
size a test can afford. It bounds the assembled record as well as each value in
it, which is what lets a row fit when the attempt starts and not when it is
finalised. Every check below asks sqlite what went wrong by error code rather
than by reading its message.

The last two checks are the exception, and they do not lower the limit at all.
Which of sqlite's three signals the runner reads cannot be asked with a
payload, because a real refusal sets all three at once and they agree; those
two hand the runner an error whose signals disagree, and say so where they do
it.
"""

import json
import sqlite3

import pytest

from pyteman.runner.matrix import (
    _OVERSIZED_OUTCOME, _OVERSIZED_OUTCOME_JSON, MatrixStorageError,
    run_matrix)

LIMIT = 20000
BIG = "y" * (LIMIT * 2)

# sqlite's own connect, captured at import and so never one of the patched ones
# below. Every check reads committed rows back through it, at the real limit
# and through no fixture's interference: what the fixtures change is what the
# runner writes with, not what the test reads with.
_CONNECT = sqlite3.connect


@pytest.fixture
def small_limit(monkeypatch):
    """Lower the length limit on every connection this run opens.

    Patched at ``sqlite3.connect`` rather than handed in, because the runner
    opens its own connection and a test that supplied one would be testing a
    connection no caller can produce.
    """
    def connect(*args, **kwargs):
        con = _CONNECT(*args, **kwargs)
        con.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, LIMIT)
        return con

    monkeypatch.setattr(sqlite3, "connect", connect)


@pytest.fixture
def traced_limit(monkeypatch):
    """The same lowered limit, with every statement sqlite runs recorded.

    The recording is sqlite's own trace callback rather than a wrapper around
    ``execute``, so what is counted is what the database was asked to do and
    not what the test arranged to observe.
    """
    statements = []

    def connect(*args, **kwargs):
        con = _CONNECT(*args, **kwargs)
        con.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, LIMIT)
        con.set_trace_callback(statements.append)
        return con

    monkeypatch.setattr(sqlite3, "connect", connect)
    return statements


def _connect_failing_once(marker, error):
    """``sqlite3.connect``, with one statement rigged to raise ``error`` once.

    For the two checks that are about the shape of an error rather than about
    a payload. Real sqlite pairs an oversized row with ``DataError`` and with
    its own wording every single time, so no payload that a test could build
    asks the runner whether it reads the error code, the exception class or
    the message text: all three answer alike. Handing it an error whose three
    signals disagree is the only way to find out, and it is injected at the
    connection because that is where the runner's own writes go through.
    """
    armed = [True]

    class Failing(sqlite3.Connection):
        def execute(self, sql, *args):
            if armed[0] and marker in sql:
                armed[0] = False
                raise error
            return super().execute(sql, *args)

    def connect(*args, **kwargs):
        kwargs["factory"] = Failing
        return _CONNECT(*args, **kwargs)

    return connect


def _connect_failing_on_the_stand_in(base, error):
    """``base``, rigged to raise ``error`` at the finalisation that stands in.

    ``_connect_failing_once`` arms on the statement text, which cannot say
    "the second finalisation": both calls run the same fixed statements, and
    what tells them apart is the payload bound to them. Arming on the
    stand-in's own outcome fires on the retry and on nothing before it,
    whichever statement the first, real refusal happened to land on.

    It wraps the connect already in place rather than sqlite's own, so the
    lowered limit that produces that first refusal survives underneath. It
    composes with a connect that sets that limit on the connection it returns,
    which is what ``small_limit`` does; it takes the factory slot itself, so a
    base that wanted one would lose it, and would fail the first-refusal
    assertion loudly rather than pass on the wrong connection.
    """
    class Failing(sqlite3.Connection):
        def execute(self, sql, *args):
            bound = args[0] if args else ()
            if (isinstance(bound, (tuple, list))
                    and _OVERSIZED_OUTCOME_JSON in bound):
                raise error
            return super().execute(sql, *args)

    def connect(*args, **kwargs):
        kwargs["factory"] = Failing
        return base(*args, **kwargs)

    return connect


def _rows(db, table, columns):
    con = _CONNECT(db)
    try:
        return con.execute(f"SELECT {columns} FROM {table}").fetchall()
    finally:
        con.close()


def _row_bytes(db, table, cell_id):
    """This row's stored values, added up.

    A proxy for the record the length limit is applied to rather than that
    record itself: sqlite's own per-value header bytes are not counted here,
    so this undercounts, by the same amount for every row of one shape. What
    it does count byte for byte is the artifact path, which is the part that
    varies from one machine to the next. So a size derived from this sits a
    constant distance from the real threshold, in the direction of being
    slightly too small, and travels with the path.
    """
    con = _CONNECT(db)
    try:
        row = con.execute(f"SELECT * FROM {table} WHERE cell_id=?",
                          (cell_id,)).fetchone()
    finally:
        con.close()
    return sum(len(str(value).encode()) for value in row if value is not None)


def test_an_oversized_result_is_failed_and_the_next_cell_still_runs(
        small_limit, tmp_path):
    """The headline case: the cell is charged for its own payload.

    Before this, the row could not be written, so nothing recorded that the
    cell had run and every later cell in the matrix was unreachable on this
    and on every subsequent invocation. The three places the outcome lives are
    asserted together, because a fallback that satisfied one of them and not
    the others would leave the run disagreeing with its own database.
    """
    calls = []

    def run_cell(cell, adir):
        calls.append(cell["id"])
        return {"blob": BIG} if cell["id"] == "big" else {"ok": 1}

    db = str(tmp_path / "r.db")
    out = run_matrix([{"id": "big"}, {"id": "later"}], run_cell, db,
                     str(tmp_path / "art"), experiment="x")

    assert calls == ["big", "later"]
    assert [r["status"] for r in out] == ["failed", "done"]

    stored = dict(_rows(db, "results", "cell_id, status"))
    assert stored == {"big": "failed", "later": "done"}

    attempts = dict(_rows(db, "attempts", "cell_id, status"))
    assert attempts == {"big": "failed", "later": "done"}

    # The same failure in all three, not merely a failure in each.
    returned = out[0]["result"]
    row = dict(_rows(db, "results", "cell_id, result_json"))["big"]
    attempt = dict(_rows(db, "attempts",
                         "cell_id, result_json"))["big"]
    assert json.loads(row) == returned
    assert json.loads(attempt) == returned
    assert returned["error"]


def test_the_replacement_names_no_column_it_has_not_measured(
        small_limit, tmp_path):
    """What the stored failure is allowed to say.

    The oversized value can be the result, the error text the callback raised,
    or the definition travelling in ``cell_json``, and the fallback does not
    find out which: it succeeds when a small row is writable, which is evidence
    about the row and not a diagnosis of a column. So the recorded text says an
    outcome was too large and stops there. Asserted rather than left to the
    reader because the tempting improvement is to name the result field, and
    that sentence would be a claim nothing here establishes.
    """
    def run_cell(cell, adir):
        raise RuntimeError(BIG)

    db = str(tmp_path / "r.db")
    out = run_matrix([{"id": "boom"}], run_cell, db, str(tmp_path / "art"),
                     experiment="x")

    assert out[0]["status"] == "failed"
    text = out[0]["result"]["error"]
    assert text == "original outcome too large to record, replaced with failure"
    # Not a fragment of what failed: quoting any of it is how the refusal gets
    # reproduced inside the row meant to survive it.
    assert "y" * 100 not in json.dumps(out[0]["result"])


def test_an_oversized_error_is_charged_to_the_cell_that_raised_it(
        small_limit, tmp_path):
    """The payload need not be a result to be too large.

    A callback that fails with a very long message reaches the same write with
    the same refusal, and for the same reason: the cell ran, so whatever the
    row now cannot hold is the cell's doing. Kept separate from the oversized
    result above because the two arrive by different branches of the runner,
    and a fallback wired into only one of them passes the other test.
    """
    calls = []

    def run_cell(cell, adir):
        calls.append(cell["id"])
        if cell["id"] == "boom":
            raise RuntimeError(BIG)
        return {"ok": 1}

    db = str(tmp_path / "r.db")
    out = run_matrix([{"id": "boom"}, {"id": "later"}], run_cell, db,
                     str(tmp_path / "art"), experiment="x")

    assert calls == ["boom", "later"]
    assert [r["status"] for r in out] == ["failed", "done"]
    assert dict(_rows(db, "results", "cell_id, status")) == {
        "boom": "failed", "later": "done"}


def test_a_later_run_retries_the_failed_cell_without_stranding_the_rest(
        small_limit, tmp_path):
    """The recorded failure is a failure, not a completion.

    Recording the cell as failed is what unblocks the matrix, so the risk the
    fix introduces is recording it too firmly: a row the resume logic reads as
    finished would trade an unreachable ``later`` for a ``big`` that never runs
    again. Both halves are asserted on the second invocation, because either
    one alone is satisfied by a policy that is wrong about the other.
    """
    seen = []

    def run_cell(cell, adir):
        seen.append(cell["id"])
        return {"blob": BIG} if cell["id"] == "big" else {"ok": 1}

    db = str(tmp_path / "r.db")
    art = str(tmp_path / "art")
    cells = [{"id": "big"}, {"id": "later"}]
    run_matrix(cells, run_cell, db, art, experiment="x")
    seen.clear()
    out = run_matrix(cells, run_cell, db, art, experiment="x")

    assert seen == ["big"]
    assert [r["status"] for r in out] == ["failed", "skipped"]
    # Two attempts at the oversized cell and one at the cell it used to block,
    # none of them left mid-flight.
    statuses = sorted(r[0] for r in _rows(db, "attempts",
                                          "status"))
    assert statuses == ["done", "failed", "failed"]


def test_a_run_that_fits_is_untouched_by_any_of_this(small_limit, tmp_path):
    """The limit is lowered and nothing goes near it.

    The fallback sits in the path every successful cell takes, so the control
    is not optional: a guard that fired on outcomes sqlite would have accepted
    would replace real results with the stand-in and still pass every test
    above.
    """
    db = str(tmp_path / "r.db")
    out = run_matrix([{"id": "a"}, {"id": "b"}],
                     lambda cell, adir: {"value": cell["id"]}, db,
                     str(tmp_path / "art"), experiment="x")

    assert [r["status"] for r in out] == ["done", "done"]
    stored = dict(_rows(db, "results", "cell_id, result_json"))
    assert json.loads(stored["a"]) == {"value": "a"}
    assert json.loads(stored["b"]) == {"value": "b"}


def test_a_refusal_that_is_not_about_size_still_stops_the_run(
        small_limit, tmp_path):
    """Only SQLITE_TOOBIG earns the second attempt.

    Every other sqlite failure at this write means recording is broken rather
    than the payload being impossible, and a ``failed`` row written into a
    database in that state is exactly the row nobody can believe. The table is
    removed from a second connection while the cell runs, which is the shape a
    concurrent reset has; what matters is that sqlite reports it under a
    different code, so the branch is chosen by the code and not by the story.
    """
    calls = []

    def run_cell(cell, adir):
        calls.append(cell["id"])
        con = _CONNECT(db)
        try:
            con.execute("DROP TABLE results")
            con.commit()
        finally:
            con.close()
        return {"ok": 1}

    db = str(tmp_path / "r.db")
    with pytest.raises(MatrixStorageError) as caught:
        run_matrix([{"id": "one"}, {"id": "later"}], run_cell, db,
                   str(tmp_path / "art"), experiment="x")

    assert calls == ["one"]
    assert caught.value.__cause__.sqlite_errorcode != sqlite3.SQLITE_TOOBIG
    # Reported as the single failed write it was. A guard that tried the
    # stand-in anyway would fail here too and raise from that second attempt
    # instead, which is the same outcome told as a different story; the message
    # is what distinguishes the two, so it is what is asserted.
    assert "unfinalised rather than asserting a result that was never saved" \
        in str(caught.value)
    assert "refused" not in str(caught.value)
    # No stand-in row, and no second call: the run stopped where it broke.
    assert dict(_rows(db, "attempts", "cell_id, status")) == {
        "one": "running"}


def test_a_stand_in_that_is_itself_refused_is_reported_not_faked(
        traced_limit, tmp_path):
    """When the stand-in is refused for its size as well.

    The fallback is one attempt and its commit is what authorises the run to
    continue, so the case that matters is the one where it does not commit.
    Reached with a large cell definition and no external writer at all:
    ``SQLITE_LIMIT_LENGTH`` bounds the assembled record and not only each value
    in it, so a definition that fits in the attempts row written before the
    cell runs can still put the finalised row over the limit once an outcome
    and a finish time are added to it. The stand-in is small, but the
    definition travels in every row for this cell and the stand-in cannot shed
    it, so the second write is refused as well.

    The padding is calibrated rather than written down. The window between a
    definition the attempts row still accepts and one the finalised row does
    not is about as wide as the stand-in itself, and every row also carries the
    artifact path, whose length depends on where the test happens to be run. A
    literal picked here would therefore pass on one machine and land on the
    begin-attempt guard on another, which is a different branch reporting a
    different thing. So the size is searched for, from a starting point
    measured on this machine rather than written down here, and a search that
    finds nothing fails rather than testing whatever it found.

    Transactions are read from sqlite's own trace callback rather than by
    standing in front of the connection, because a wrapper counting calls would
    be counting what the test arranged. Only the transaction boundaries are
    read: a statement sqlite refuses is not always traced, so the writes cannot
    be counted, while every BEGIN and every ROLLBACK is.
    """
    statements = traced_limit
    calls = []

    def run_cell(cell, adir):
        calls.append(cell["id"])
        return {"blob": BIG}

    def attempt(pad, at):
        """One run at this definition size, in a database of its own.

        Returns the storage refusal, or ``None`` when the run got through,
        which it does once the definition is small enough for the stand-in to
        fit beside it.
        """
        calls.clear()
        statements.clear()
        try:
            run_matrix([{"id": "c", "pad": "p" * pad}, {"id": "later"}],
                       run_cell, str(at / "r.db"), str(at / "art"),
                       experiment="x")
        except MatrixStorageError as e:
            return e
        return None

    def workspace(index):
        """A run directory whose name is the same length for every run.

        The artifact path is one of the values in the row being measured, so a
        probe run from a directory a byte longer than the anchor's would be
        calibrated against a row it is not going to write.
        """
        at = tmp_path / f"run{index:02d}"
        at.mkdir()
        return at

    # Where that window sits is set by the artifact path, which every row
    # carries and whose length is a property of the machine rather than of
    # this test, so the search is anchored to a row the runner wrote here
    # instead of to a literal. The unpadded run goes all the way through: its
    # outcome is refused for its size and the stand-in is what commits, so the
    # row it leaves behind is the same row the search has to push back over
    # the limit, measured in this database and with this artifact path.
    # Padding adds to that row byte for byte, so what is left under the limit
    # is the padding that reaches it.
    anchor_dir = workspace(0)
    if attempt(0, anchor_dir) is not None:
        pytest.fail("the unpadded run was refused as well, so there is no "
                    "committed row to calibrate the search against")
    anchor = LIMIT - _row_bytes(str(anchor_dir / "r.db"), "results", "c")

    # Outward from the anchor, nearest first, because the anchor is a
    # measurement of where this machine's window is and the first probe is
    # expected to land inside it. Both directions are walked because the
    # measurement is a proxy that undercounts, which puts the real threshold
    # a little below the anchor: a walk that only climbed would miss the part
    # of the window that lies underneath. Bounded, and reaching further either
    # way than the window is wide, so a change that moved it is still found
    # and a change that closed this branch off reports that instead of
    # searching forever.
    for index, offset in enumerate(sorted(range(-80, 81, 8), key=abs), 1):
        scratch = workspace(index)
        error = attempt(anchor + offset, scratch)
        if error is not None and "for its size as well" in str(error):
            break
    else:
        pytest.fail("no definition size reached the stand-in write")

    # The refusal reported is the one that ended the run, and the refusal that
    # started it is named in the message rather than replaced by it.
    assert error.__cause__.sqlite_errorcode == sqlite3.SQLITE_TOOBIG
    assert "was refused by" in str(error)

    # The size branch is the one the removed clauses used to live on, so it is
    # the one that has to be held to their absence. Asserting only that this
    # branch still says "for its size as well" would leave it free to reacquire
    # them: two refusals for size are still no measurement of which column
    # carries the excess, and still no proof about rows never attempted.
    text = str(error)
    assert "the excess is not the outcome" not in text
    assert "no row for this cell can be written" not in text
    assert "until whatever else it carries is smaller" not in text

    # One call, and the cell after this one never reached.
    assert calls == ["c"]

    # Two finalisation transactions, both discarded: the stand-in was tried
    # once and not in a loop, and nothing after the attempt's own insert was
    # kept. Counted rather than matched at the tail, because a loop that tried
    # again and again would end in the same two statements as one that stopped.
    # The two commits are the schema write and that insert.
    txn = [s.strip() for s in statements
           if s.strip() in ("BEGIN", "COMMIT", "ROLLBACK")]
    assert txn[-4:] == ["BEGIN", "ROLLBACK", "BEGIN", "ROLLBACK"]
    assert txn.count("ROLLBACK") == 2
    assert txn.count("COMMIT") == 2

    # Nothing committed: no row for this cell, no history claiming one was
    # superseded, and the attempt left where every unrecordable outcome leaves
    # it.
    db = str(scratch / "r.db")
    assert _rows(db, "results", "cell_id") == []
    assert _rows(db, "results_superseded", "cell_id") == []
    assert dict(_rows(db, "attempts", "cell_id, status")) == {
        "c": "running"}


@pytest.mark.parametrize("oversized, recorded", [(False, "done"),
                                                 (True, "failed")])
def test_the_vanished_attempt_guard_names_the_write_and_not_the_cell(
        small_limit, tmp_path, oversized, recorded):
    """One guard, two finalisations, and no contradiction between them.

    ``_finalise`` runs twice for an oversized outcome, and the second call
    carries the stand-in's ``'failed'`` for a callback that returned normally.
    Its rowcount guard is reachable on both calls, so wording that read as the
    cell's own status would report the same normally-returning cell as ``done``
    on one path and ``failed`` on the other. What the guard can actually attest
    to is which outcome the write it was making carried, and that is what it
    says.

    The attempt row is removed by a trigger inside the database rather than by
    a second connection, because the removal has to land between the results
    write and the attempt's finalisation, which are one transaction on one
    connection: a rival connection cannot reach inside it, and sqlite runs a
    trigger there by definition.

    Asserted on the message text, unusually for this file, because the text is
    the whole defect: every other observable is identical on the two paths.
    The ordinary case is the control, and it is deliberately the same run with
    one value changed, so that any difference between the two messages is the
    handler's and not the cell's. That the callback returns normally is checked
    in both. ``test_matrix_attempts.py`` reaches this same guard on the
    ordinary path by a different mechanism; that test is about the guard
    firing, this one about what it then says, and the control here has to share
    the replay's mechanism to be one.
    """
    db = str(tmp_path / "r.db")
    returned = []

    def run_cell(cell, adir):
        # Created here rather than up front: the schema does not exist until
        # the runner has built it, and by now the attempt's own row is
        # inserted and committed.
        con = _CONNECT(db)
        try:
            con.execute("CREATE TRIGGER drop_attempts AFTER INSERT ON "
                        "results BEGIN DELETE FROM attempts; END")
            con.commit()
        finally:
            con.close()
        returned.append(cell["id"])
        return {"blob": BIG} if oversized else {"ok": True}

    with pytest.raises(MatrixStorageError) as caught:
        run_matrix([{"id": "c"}], run_cell, db, str(tmp_path / "art"),
                   experiment="x")
    assert returned == ["c"], "the callback did not return normally"
    message = str(caught.value)

    # The guard fired, and it names the outcome its own write carried.
    assert "vanished" in message
    assert "the finalisation recording it as" in message
    assert f"{recorded!r}" in message

    # And it does not claim that outcome as how the cell ended. This is the
    # sentence the finding was about: it reported a cell that returned
    # normally as having finished failed, on the replay path only.
    assert "ran and finished" not in message

    # Rolled back, so the guard left no row behind claiming the outcome it
    # could not record. The trigger's own DELETE is inside the transaction
    # being discarded, so the rollback brings the attempt row back and the
    # database ends where every unrecordable outcome leaves it. That also
    # means the end state cannot tell a guard that fired from one that never
    # ran, which is why the raise and its message above are what this test is
    # anchored on and this part only confirms nothing was kept.
    assert _rows(db, "results", "cell_id") == []
    assert dict(_rows(db, "attempts", "cell_id, status")) == {"c": "running"}


def test_a_second_refusal_that_is_not_about_size_is_reported_as_what_it_was(
        traced_limit, tmp_path):
    """The stand-in's refusal is diagnosed on its own code, not on the first's.

    The pairing no other check produces: a first write refused for its size
    and a second refused for something else entirely. Both refusals are real
    sqlite's. The first is the lowered ``SQLITE_LIMIT_LENGTH`` used
    everywhere above; the second is a trigger armed while the cell runs,
    raising ``SQLITE_CONSTRAINT_TRIGGER`` against the stand-in payload alone,
    so the first write is still refused for its size and only the second
    meets the trigger. No exception is injected and no method is patched to
    raise.

    What is asserted about the message is that the first refusal's diagnosis
    is not carried over to the second. A constraint is not answered by making
    anything smaller, and an operator told to shrink a payload would be
    working on the wrong problem while the run is halted.
    """
    statements = traced_limit
    calls = []
    db = str(tmp_path / "r.db")
    stand_in = _OVERSIZED_OUTCOME_JSON
    # The runner's own serialisation, imported rather than rebuilt here. A
    # local json.dumps would match today and stop matching the day the module
    # tightens its separators, and a trigger whose WHEN clause no longer
    # matches simply never fires: this check would pass without reaching the
    # branch it exists for.
    #
    # sqlite stores a trigger's text as written, so a bound '?' in the WHEN
    # clause is bound once at CREATE time and read as NULL every time the
    # trigger is considered afterwards. It would never fire either. Inlined
    # instead, which is exact because the stand-in carries no quote.
    assert "'" not in stand_in

    def run_cell(cell, adir):
        calls.append(cell["id"])
        # Armed from outside the runner while the cell runs, the same shape
        # the non-size check above uses to reach the database mid-run.
        con = _CONNECT(db)
        try:
            con.execute(
                "CREATE TRIGGER refuse_the_stand_in BEFORE INSERT ON results "
                f"WHEN NEW.result_json = '{stand_in}' "
                "BEGIN SELECT RAISE(ABORT, 'no stand-in here'); END")
            con.commit()
        finally:
            con.close()
        return {"blob": BIG}

    with pytest.raises(MatrixStorageError) as caught:
        run_matrix([{"id": "c"}, {"id": "later"}], run_cell, db,
                   str(tmp_path / "art"), experiment="x")

    # The pairing itself, read by code at both ends rather than taken from the
    # arrangement. Asserting only the second refusal would leave this passing
    # on a run whose first refusal was not about size either, which is the
    # first handler's branch and a different thing entirely.
    second = caught.value.__cause__
    assert second.sqlite_errorcode == sqlite3.SQLITE_CONSTRAINT_TRIGGER
    assert second.__context__.sqlite_errorcode == sqlite3.SQLITE_TOOBIG

    text = str(caught.value)
    # The first refusal survives in the message: it is why a stand-in was
    # tried at all.
    assert "was refused by" in text and "for its size" in text
    # The second does not inherit it. This is the load-bearing one: it names
    # the branch the code actually took, and it is absent both from the
    # rejected message and from the size branch beside it.
    assert "was refused for something other than its size" in text
    assert "for its size as well" not in text
    # What did refuse it, in sqlite's own words rather than the runner's.
    assert "no stand-in here" in text
    # The inference drawn from two refusals, and the remedy prescribed from
    # it. The second is the clause an operator would have acted on.
    assert "the excess is not the outcome" not in text
    assert "until whatever else it carries is smaller" not in text

    # One call for the cell, and the cell behind it never reached: the retry
    # is one more finalisation and never one more run of the callback.
    assert calls == ["c"]

    # Two finalisation transactions, both discarded. Counted rather than
    # matched at the tail, because a loop that retried until it gave up would
    # end in the same two statements as the one attempt this is. The two
    # commits are the schema write and the attempt's own insert.
    txn = [s.strip() for s in statements
           if s.strip() in ("BEGIN", "COMMIT", "ROLLBACK")]
    assert txn[-4:] == ["BEGIN", "ROLLBACK", "BEGIN", "ROLLBACK"]
    assert txn.count("ROLLBACK") == 2
    assert txn.count("COMMIT") == 2

    # Nothing committed and nothing fabricated: no row for this cell, no
    # history claiming one was superseded, and the attempt left where every
    # unrecordable outcome leaves it.
    assert _rows(db, "results", "cell_id") == []
    assert _rows(db, "results_superseded", "cell_id") == []
    assert dict(_rows(db, "attempts", "cell_id, status")) == {"c": "running"}


def test_a_second_refusal_carrying_no_sqlite_code_is_still_a_storage_failure(
        small_limit, monkeypatch, tmp_path):
    """The retry's handler reads the code through the same guarded getattr.

    The twin, at the second finalisation, of the check at the end of this file
    for the first. ``sqlite_errorcode`` is absent on the errors the ``sqlite3``
    module raises by itself, and reading it directly here would replace the
    ``MatrixStorageError`` naming the attempt directory with an
    ``AttributeError`` thrown from inside the handler written to report it.

    Only the second refusal is injected. The first is a real ``SQLITE_TOOBIG``
    from the lowered limit, so what this exercises is the retry's handler and
    not the fallback's entry, which the check below already covers.
    """
    broken = sqlite3.ProgrammingError("Incorrect number of bindings supplied")
    assert not hasattr(broken, "sqlite_errorcode")

    # Read before the patch lands, so what is wrapped is the lowered-limit
    # connect the fixture installed and not sqlite's own.
    monkeypatch.setattr(sqlite3, "connect", _connect_failing_on_the_stand_in(
        sqlite3.connect, broken))

    db = str(tmp_path / "r.db")
    with pytest.raises(MatrixStorageError) as caught:
        run_matrix([{"id": "c"}], lambda cell, adir: {"blob": BIG}, db,
                   str(tmp_path / "art"), experiment="x")

    # The pairing, a real size refusal first and the code-less one second.
    assert caught.value.__cause__ is broken
    assert caught.value.__cause__.__context__.sqlite_errorcode == \
        sqlite3.SQLITE_TOOBIG

    # No code to read, so the size wording is withheld rather than assumed.
    text = str(caught.value)
    assert "was refused for something other than its size" in text
    assert "for its size as well" not in text

    assert _rows(db, "results", "cell_id") == []
    assert dict(_rows(db, "attempts", "cell_id, status")) == {"c": "running"}


def test_the_stand_in_replaces_a_previous_result_whole_or_not_at_all(
        small_limit, tmp_path):
    """The fallback replays the transaction, not the statement that raised.

    A cell that succeeded once and is rerun with an oversized outcome has a
    stored row to supersede and an archive copy to write, and those happen in
    the transaction the refusal discarded. Retrying only the INSERT would
    commit a stand-in whose archive copy had been rolled back, leaving history
    claiming the earlier result was never superseded. Asserted on the archive
    rather than on the new row, because the new row is what both versions get
    right.
    """
    # One mutable dict rather than two callbacks: the same callback has to run
    # in both invocations, so what it returns is swapped between them.
    payload = {"small": 1}

    def run_cell(cell, adir):
        return dict(payload)

    db = str(tmp_path / "r.db")
    art = str(tmp_path / "art")
    run_matrix([{"id": "c"}], run_cell, db, art, experiment="x")

    payload.clear()
    payload["blob"] = BIG
    out = run_matrix([{"id": "c", "bump": 1}], run_cell, db, art,
                     experiment="x", on_mismatch="rerun")

    assert out[0]["status"] == "failed"
    archived = _rows(db, "results_superseded", "result_json")
    assert [json.loads(r[0]) for r in archived] == [{"small": 1}]
    stored = dict(_rows(db, "results", "cell_id, result_json"))
    assert json.loads(stored["c"]) == _OVERSIZED_OUTCOME


def test_the_fallback_is_chosen_by_the_error_code_and_not_by_class_or_text(
        monkeypatch, tmp_path):
    """Which of the three signals sqlite offers the runner actually reads.

    Real sqlite makes this unaskable: an oversized row comes back as a
    ``DataError`` whose message says "string or blob too big" and whose code is
    ``SQLITE_TOOBIG``, every time, so reading the class, reading the text and
    reading the code are the same test against any payload. Every other check
    in this file is therefore passed just as happily by a runner that matches
    on the message, and that runner breaks the day sqlite rewords itself and
    fires wrongly on any unrelated error whose text happens to contain the
    phrase.

    So the error is built here rather than provoked: an ``OperationalError``,
    which is not a ``DataError``, saying nothing about size, carrying the code
    that says the row was too large. A runner reading the code recognises it
    and stands in for the outcome; a runner reading the class or the text does
    not, and stops the run.
    """
    refusal = sqlite3.OperationalError("statement aborted")
    refusal.sqlite_errorcode = sqlite3.SQLITE_TOOBIG
    # The two properties that give this error its power, asserted so that a
    # later edit cannot quietly turn it back into an ordinary refusal.
    assert not isinstance(refusal, sqlite3.DataError)
    assert "too big" not in str(refusal)

    monkeypatch.setattr(sqlite3, "connect", _connect_failing_once(
        "INSERT OR REPLACE INTO results", refusal))

    calls = []

    def run_cell(cell, adir):
        calls.append(cell["id"])
        return {"ok": cell["id"]}

    db = str(tmp_path / "r.db")
    out = run_matrix([{"id": "c"}, {"id": "later"}], run_cell, db,
                     str(tmp_path / "art"), experiment="x")

    # The cell ran once and the matrix carried on: the stand-in is a second
    # write, never a second call.
    assert calls == ["c", "later"]
    assert [r["status"] for r in out] == ["failed", "done"]
    assert out[0]["result"] == _OVERSIZED_OUTCOME
    assert dict(_rows(db, "results", "cell_id, status")) == {
        "c": "failed", "later": "done"}


def test_an_error_carrying_no_sqlite_code_is_still_a_storage_failure(
        monkeypatch, tmp_path):
    """The attribute the branch reads is not on every ``sqlite3.Error``.

    ``sqlite_errorcode`` is set only on errors that came back from the sqlite
    library. The ones the ``sqlite3`` module raises by itself, a wrong binding
    count and a parameter it cannot adapt among them, are ``sqlite3.Error``
    subclasses with no code attached, and reading the attribute off one of
    those directly raises ``AttributeError`` from inside the handler. That
    would replace the documented ``MatrixStorageError``, and with it the
    message naming the attempt directory, with a crash that says nothing about
    where the evidence is.

    No payload reaches this today: the statements are fixed and every value
    bound is a string or a float. It is asserted anyway because the handler's
    own comment promises these cases are reported here, and a promise about an
    error path is worth exactly what proves it.
    """
    broken = sqlite3.ProgrammingError(
        "Incorrect number of bindings supplied")
    assert not hasattr(broken, "sqlite_errorcode")

    monkeypatch.setattr(sqlite3, "connect", _connect_failing_once(
        "UPDATE attempts SET status=?", broken))

    db = str(tmp_path / "r.db")
    with pytest.raises(MatrixStorageError) as caught:
        run_matrix([{"id": "c"}], lambda cell, adir: {"ok": 1}, db,
                   str(tmp_path / "art"), experiment="x")

    assert caught.value.__cause__ is broken
    assert "unfinalised rather than asserting a result that was never saved" \
        in str(caught.value)
    # Nothing recorded, and the attempt left where every unwritable outcome
    # leaves it.
    assert _rows(db, "results", "cell_id") == []
    assert dict(_rows(db, "attempts", "cell_id, status")) == {"c": "running"}
