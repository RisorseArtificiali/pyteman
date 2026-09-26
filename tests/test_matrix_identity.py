"""Resume identity: a stored result answers for a definition, not for an id.

RUN-01. These tests pin the rule that run_matrix may only skip a cell when the
stored row was produced by the same cell definition under the same experiment
identity, and that no historical row is destroyed without a record.
"""

import json
import ntpath
import os
import shutil
import sqlite3
import unicodedata

import pytest

from pyteman.runner import matrix as matrix_module
from pyteman.runner.matrix import (MatrixArtifactError, MatrixIdentityError,
                                   cell_fingerprint, run_matrix,
                                   superseded_rows)

EXPERIMENT = {"harness": "1.0", "ruleset": "aaa"}


def collecting_cell(calls):
    def run_cell(cell, adir):
        calls.append(cell["params"]["x"])
        return {"x": cell["params"]["x"]}
    return run_cell


def id_collecting_cell(calls):
    """Records which cells ran, for tests whose cells carry no parameters.

    A refusal is only worth as much as the point it happens at, so the tests
    that expect one need to say which cells had already run when it came.
    """
    def run_cell(cell, adir):
        calls.append(cell["id"])
        return {}
    return run_cell


class WriterSlotHeld(BaseException):
    """A lock complaint shaped so the runner's per-cell guard cannot eat it.

    ``run_matrix`` turns any ``Exception`` out of a callback into that cell's
    failure, which is right for a callback but wrong for a statement about the
    runner itself: reported that way this would surface as a run that finished
    normally when the test expected an interrupt, naming nothing.
    """


def interrupting_cell(db):
    """Check no writer is shut out, then die partway through the cell.

    The probe is the discriminating half. An implementation that archived at
    planning time and merely deferred its commit would satisfy every later
    assertion about ``results_superseded``: the interrupt discards the open
    transaction, and the next successful run flushes exactly one archive row
    holding the right payload. What that shape could not do is let anybody
    else write, because its plan-time INSERT would hold the database's single
    writer slot for the whole of ``run_cell``, however long the cell runs.
    Taking that slot here, under a timeout short enough to fail rather than
    hang, makes "no transaction is held open across the callback" a property
    this suite can lose rather than one the source layout merely happens to
    have.
    """
    def run_cell(cell, adir):
        probe = sqlite3.connect(db, timeout=0.5)
        try:
            probe.execute("CREATE TABLE IF NOT EXISTS writer_probe(n)")
            probe.execute("INSERT INTO writer_probe VALUES (1)")
            probe.commit()
        except sqlite3.OperationalError as e:
            raise WriterSlotHeld(
                "run_cell was entered with a write transaction open on the "
                f"results db, so no other writer can proceed: {e}") from e
        finally:
            probe.close()
        raise KeyboardInterrupt("power cut mid-cell")
    return run_cell


def query(db, sql):
    con = sqlite3.connect(db)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def rows(db):
    return query(db, "SELECT experiment, cell_id, fingerprint, status, result_json, cell_json "
                     "FROM results ORDER BY experiment, cell_id")


def superseded(db):
    return query(db, "SELECT cell_id, fingerprint, status, result_json, reason "
                     "FROM results_superseded ORDER BY superseded_at, cell_id")


def test_identical_definition_still_skips(tmp_path):
    """The resume that must keep working, pinned where the invariant lives."""
    calls = []
    cells = [{"id": "same", "params": {"x": 1}}]
    db = str(tmp_path / "r.db")

    run_matrix(cells, collecting_cell(calls), db, str(tmp_path / "art"), experiment=EXPERIMENT)
    out = run_matrix(cells, collecting_cell(calls), db, str(tmp_path / "art"),
                     experiment=EXPERIMENT)

    assert calls == [1]
    assert out == [{"cell_id": "same", "status": "skipped"}]


def test_key_order_does_not_change_the_fingerprint(tmp_path):
    """Canonical form: the same mapping written differently is the same cell."""
    calls = []
    db = str(tmp_path / "r.db")

    run_matrix([{"id": "same", "params": {"x": 1, "y": 2}}],
               collecting_cell(calls), db, str(tmp_path / "art"), experiment=EXPERIMENT)
    out = run_matrix([{"params": {"y": 2, "x": 1}, "id": "same"}],
                     collecting_cell(calls), db, str(tmp_path / "art"),
                     experiment={"ruleset": "aaa", "harness": "1.0"})

    assert calls == [1]
    assert out[0]["status"] == "skipped"


def test_changed_definition_is_refused_and_history_survives(tmp_path):
    calls = []
    db = str(tmp_path / "r.db")
    run_matrix([{"id": "same", "params": {"x": 1}}],
               collecting_cell(calls), db, str(tmp_path / "art"), experiment=EXPERIMENT)

    with pytest.raises(MatrixIdentityError) as excinfo:
        run_matrix([{"id": "same", "params": {"x": 2}}],
                   collecting_cell(calls), db, str(tmp_path / "art"), experiment=EXPERIMENT)

    assert "same" in str(excinfo.value)
    assert "differs in params" in str(excinfo.value), "the refusal must say what changed"
    assert calls == [1], "the changed definition must not run under the refusing policy"
    stored = rows(db)
    assert len(stored) == 1
    assert json.loads(stored[0][4]) == {"x": 1}, "historical result must be untouched"


def test_changed_definition_is_refused_before_any_cell_runs(tmp_path):
    """The mismatch check is a pre-pass, not a check inside the run loop.

    The conflicting cell is second on purpose: with it first, a runner that
    only noticed the conflict on reaching that cell would pass this test too.
    """
    calls = []
    db = str(tmp_path / "r.db")
    run_matrix([{"id": "a", "params": {"x": 1}}],
               collecting_cell(calls), db, str(tmp_path / "art"), experiment=EXPERIMENT)

    with pytest.raises(MatrixIdentityError):
        run_matrix([{"id": "fresh", "params": {"x": 3}}, {"id": "a", "params": {"x": 9}}],
                   collecting_cell(calls), db, str(tmp_path / "art"), experiment=EXPERIMENT)

    assert calls == [1], "no cell may run once the matrix is known to conflict"
    assert [r[1] for r in rows(db)] == ["a"]


def test_changed_definition_reruns_under_policy_and_archives_the_old_row(tmp_path):
    calls = []
    db = str(tmp_path / "r.db")
    run_matrix([{"id": "same", "params": {"x": 1}}],
               collecting_cell(calls), db, str(tmp_path / "art"), experiment=EXPERIMENT)

    out = run_matrix([{"id": "same", "params": {"x": 2}}],
                     collecting_cell(calls), db, str(tmp_path / "art"),
                     experiment=EXPERIMENT, on_mismatch="rerun")

    assert calls == [1, 2]
    assert out[0]["status"] == "done"
    assert json.loads(rows(db)[0][4]) == {"x": 2}

    archived = superseded(db)
    assert len(archived) == 1
    assert json.loads(archived[0][3]) == {"x": 1}
    assert archived[0][4] == "mismatch"


def test_mismatched_failed_row_is_archived_before_it_is_overwritten(tmp_path):
    """A failed row from another definition is history too, not scratch space.

    It does not gate the run (a failure is not evidence anyone resumes from),
    but it is the only durable trace that the older definition was attempted,
    so it may not vanish under INSERT OR REPLACE.
    """
    db = str(tmp_path / "r.db")

    def failing(cell, adir):
        raise RuntimeError("boom")

    run_matrix([{"id": "same", "params": {"x": 1}}], failing, db,
               str(tmp_path / "art"), experiment=EXPERIMENT)
    assert rows(db)[0][3] == "failed"

    calls = []
    out = run_matrix([{"id": "same", "params": {"x": 2}}],
                     collecting_cell(calls), db, str(tmp_path / "art"),
                     experiment=EXPERIMENT)

    assert calls == [2], "a failed row does not gate a changed definition"
    assert out[0]["status"] == "done"
    archived = superseded(db)
    assert len(archived) == 1, "the failed row from the old definition must survive"
    assert archived[0][2] == "failed"
    assert json.loads(archived[0][3])["error"].startswith("RuntimeError")
    assert archived[0][4] == "mismatch"


def test_same_definition_retry_is_not_archived(tmp_path):
    """Retrying our own failed row is resume, not supersession."""
    db = str(tmp_path / "r.db")
    attempts = []

    def flaky(cell, adir):
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("first attempt fails")
        return {"x": 1}

    run_matrix([{"id": "same", "params": {"x": 1}}], flaky, db,
               str(tmp_path / "art"), experiment=EXPERIMENT)
    out = run_matrix([{"id": "same", "params": {"x": 1}}], flaky, db,
                     str(tmp_path / "art"), experiment=EXPERIMENT)

    assert out[0]["status"] == "done"
    assert superseded(db) == [], "an unchanged retry supersedes nothing"


def test_interrupted_supersessions_do_not_accumulate_archive_rows(tmp_path):
    """An archive row says a supersession happened, not that one was planned.

    The row being superseded stays live until its replacement has been
    written, so an interrupt inside ``run_cell`` leaves the old row still the
    one on record and nothing superseded at all. Archiving when the plan was
    made recorded the intent rather than the event: every interrupted attempt
    left another copy behind, identical in every column but the timestamp, and
    a reader asking how many times the cell had been displaced got the number
    of attempts instead.
    """
    db = str(tmp_path / "r.db")
    art = str(tmp_path / "art")
    a = [{"id": "same", "params": {"x": 1}}]
    b = [{"id": "same", "params": {"x": 2}}]
    calls = []

    run_matrix(a, collecting_cell(calls), db, art, experiment=EXPERIMENT)

    for attempt in (1, 2):
        with pytest.raises(KeyboardInterrupt):
            run_matrix(b, interrupting_cell(db), db, art, experiment=EXPERIMENT,
                       on_mismatch="rerun")
        assert superseded(db) == [], (
            f"attempt {attempt} superseded nothing, so it may archive nothing")
        assert json.loads(rows(db)[0][4]) == {"x": 1}, "the old row is still the live one"

    out = run_matrix(b, collecting_cell(calls), db, art, experiment=EXPERIMENT,
                     on_mismatch="rerun")

    assert out[0]["status"] == "done"
    assert calls == [1, 2], "the interrupted attempts recorded nothing to resume from"
    assert json.loads(rows(db)[0][4]) == {"x": 2}
    archived = superseded(db)
    assert len(archived) == 1, "one supersession happened, so one archived row"
    assert json.loads(archived[0][3]) == {"x": 1}, "the superseded evidence is intact"
    assert archived[0][4] == "mismatch"


def test_duplicate_ids_are_detected_before_execution(tmp_path):
    calls = []
    db = str(tmp_path / "r.db")
    art = str(tmp_path / "art")

    for matrix in ([{"id": "dup", "params": {"x": 1}}, {"id": "dup", "params": {"x": 2}}],
                   [{"id": "dup", "params": {"x": 1}}, {"id": "dup", "params": {"x": 1}}]):
        with pytest.raises(MatrixIdentityError) as excinfo:
            run_matrix(matrix, collecting_cell(calls), db, art, experiment=EXPERIMENT)
        assert "dup" in str(excinfo.value)

    assert calls == [], "duplicate ids are an input error, no cell may run"


def test_distinct_experiments_do_not_collide(tmp_path):
    calls = []
    db = str(tmp_path / "r.db")
    cell = [{"id": "same", "params": {"x": 1}}]

    run_matrix(cell, collecting_cell(calls), db, str(tmp_path / "art"),
               experiment={"ruleset": "aaa", "harness": "1.0"})
    out = run_matrix(cell, collecting_cell(calls), db, str(tmp_path / "art"),
                     experiment={"ruleset": "bbb", "harness": "1.0"})

    assert calls == [1, 1], "a new experiment identity is a new run, not a resume"
    assert out[0]["status"] == "done"
    assert len(rows(db)) == 2, "the earlier experiment's evidence must survive"


def test_experiment_identity_is_required(tmp_path):
    """The audited defect lived outside the cells, so it cannot be opt-in.

    A caller who bumps the ruleset or the harness and leaves the cells alone
    must say so; the runner has no way to notice on its own.
    """
    with pytest.raises(TypeError):
        run_matrix([{"id": "c", "params": {}}], lambda cell, adir: {},
                   str(tmp_path / "r.db"), str(tmp_path / "art"))


def test_unserialisable_cell_fails_explicitly(tmp_path):
    with pytest.raises(MatrixIdentityError) as excinfo:
        run_matrix([{"id": "bad", "params": {"x": {1, 2}}}],
                   lambda cell, adir: {}, str(tmp_path / "r.db"), str(tmp_path / "art"),
                   experiment=EXPERIMENT)
    assert "bad" in str(excinfo.value)


def test_fingerprint_is_a_frozen_value():
    """Golden value: changing the canonicalisation invalidates every stored db.

    Every behavioural test here builds a fresh database, so a change to the
    hashed payload would leave them all green while making each existing
    results db report a mismatch on every cell. Only a frozen value catches it.
    """
    assert cell_fingerprint({"id": "c", "params": {"x": 1, "y": 2}}) == (
        "e6eed195ec16882ffbe918c04441c2bf9f3e90bbf119def02b02d6c98a70199c")


def test_non_string_mapping_keys_are_refused():
    """JSON rewrites 1 as "1", so hashing it would collide two definitions.

    This is the defect the whole feature exists to prevent, reached through
    the canonicalisation rather than through the stored row.
    """
    with pytest.raises(MatrixIdentityError) as excinfo:
        cell_fingerprint({"id": "c", "params": {1: "a"}})
    assert "non-string mapping key" in str(excinfo.value)
    # Substring alone cannot tell the precise refusal from a precise refusal
    # caught and re-raised inside the generic one, because the wrapper prints
    # the repr of what it wrapped. The caller reads the first line, so what
    # matters is that the generic message is not the one in front.
    assert "not canonically serialisable" not in str(excinfo.value), (
        "the key refusal was re-wrapped in the generic serialisation refusal")

    # The collision it stands in for, stated so the intent cannot be lost.
    with pytest.raises(MatrixIdentityError):
        cell_fingerprint({"id": "c", "params": {True: "a"}})
    # The form the refusal asks for is accepted. Stating it as a plain call
    # says exactly that and nothing more; asserting on the digest would only
    # assert that a hex string is truthy.
    cell_fingerprint({"id": "c", "params": {"1": "a"}})


def test_non_string_cell_id_is_refused(tmp_path):
    """cell_id has TEXT affinity, so 1 and '1' would address one row."""
    with pytest.raises(MatrixIdentityError) as excinfo:
        run_matrix([{"id": 1, "params": {}}], lambda cell, adir: {},
                   str(tmp_path / "r.db"), str(tmp_path / "art"), experiment=EXPERIMENT)
    assert "not a string" in str(excinfo.value)


def test_superseding_run_does_not_overwrite_archived_artifacts(tmp_path):
    """The archived row must keep pointing at the evidence it came from.

    Deriving the artifact directory from the cell id alone would have the
    rerun write over the superseded run's artifacts, leaving the archived row
    describing another definition's output: the misattribution this feature
    removes, reintroduced one layer down.
    """
    db = str(tmp_path / "r.db")
    art = str(tmp_path / "art")

    def writing(cell, adir):
        with open(os.path.join(adir, "trace.txt"), "w") as fh:
            fh.write(str(cell["params"]["x"]))
        return {"x": cell["params"]["x"]}

    run_matrix([{"id": "same", "params": {"x": 1}}], writing, db, art, experiment=EXPERIMENT)
    run_matrix([{"id": "same", "params": {"x": 2}}], writing, db, art,
               experiment=EXPERIMENT, on_mismatch="rerun")

    archived_dir = query(db, "SELECT artifact_dir FROM results_superseded")[0][0]
    current_dir = query(db, "SELECT artifact_dir FROM results")[0][0]
    assert archived_dir != current_dir, "the rerun must not reuse the superseded dir"
    with open(os.path.join(archived_dir, "trace.txt")) as fh:
        assert fh.read() == "1", "the superseded run's artifacts must survive"
    with open(os.path.join(current_dir, "trace.txt")) as fh:
        assert fh.read() == "2"


def evidence_writer(tag):
    def run_cell(cell, adir):
        with open(os.path.join(adir, "evidence.txt"), "w") as fh:
            fh.write(tag)
        return {"tag": tag}
    return run_cell


def evidence_of(path):
    with open(os.path.join(path, "evidence.txt")) as fh:
        return fh.read()


def test_artifacts_are_isolated_between_experiments_from_the_first_run(tmp_path):
    """Two experiments sharing an artifact root must not share evidence.

    Nothing has gone wrong in this scenario: no mismatch, no supersession,
    just one cell id run under two identities. A directory derived from the
    cell id alone let the second run write over the first one's artifacts, so
    a row naming one experiment pointed at another experiment's output.
    """
    db = str(tmp_path / "r.db")
    art = str(tmp_path / "art")
    cells = [{"id": "same", "params": {"x": 1}}]

    run_matrix(cells, evidence_writer("A"), db, art, experiment="rev-A")
    run_matrix(cells, evidence_writer("B"), db, art, experiment="rev-B")

    found = {experiment: evidence_of(adir) for experiment, adir
             in query(db, "SELECT experiment, artifact_dir FROM results")}
    assert found == {'"rev-A"': "A", '"rev-B"': "B"}
    parents = {os.path.dirname(adir) for (adir,)
               in query(db, "SELECT artifact_dir FROM results")}
    assert len(parents) == 2, "each experiment needs an artifact namespace of its own"


def test_a_returning_definition_never_reuses_an_archived_directory(tmp_path):
    """Run A, B, A, B: the fourth run comes back to a fingerprint already used.

    A directory named after the fingerprint is unique among the definitions of
    one run, not over time. The second run's archived row still points at the
    B directory, so the fourth run writing there destroys the very evidence
    the archive exists to preserve.
    """
    db = str(tmp_path / "r.db")
    art = str(tmp_path / "art")
    a = [{"id": "same", "params": {"x": 1}}]
    b = [{"id": "same", "params": {"x": 2}}]

    for cells, tag in ((a, "A1"), (b, "B1"), (a, "A2"), (b, "B2")):
        run_matrix(cells, evidence_writer(tag), db, art,
                   experiment=EXPERIMENT, on_mismatch="rerun")

    dirs = query(db, "SELECT artifact_dir FROM results_superseded") \
        + query(db, "SELECT artifact_dir FROM results")
    found = {adir: evidence_of(adir) for (adir,) in dirs}
    assert len(found) == 4, "each of the four attempts needs evidence of its own"
    assert sorted(found.values()) == ["A1", "A2", "B1", "B2"]


def test_an_existing_directory_is_never_written_into(tmp_path):
    """The attempt is named, not fitted into what the db happens to remember.

    Artifacts outlive the database that indexed them: a results db can be
    rebuilt, or pointed at a root that already holds evidence. Naming the
    attempt is what keeps a run out of artifacts it knows nothing about,
    rather than only out of those its own db remembers.
    """
    db = str(tmp_path / "r.db")
    art = str(tmp_path / "art")
    cells = [{"id": "same", "params": {"x": 1}}]

    run_matrix(cells, evidence_writer("first"), db, art, experiment=EXPERIMENT)
    first = query(db, "SELECT artifact_dir FROM results")[0][0]
    os.remove(db)
    run_matrix(cells, evidence_writer("second"), db, art, experiment=EXPERIMENT)
    second = query(db, "SELECT artifact_dir FROM results")[0][0]

    assert second != first
    assert evidence_of(first) == "first", "the forgotten run's artifacts must survive"
    assert evidence_of(second) == "second"


def test_a_cleanup_of_the_artifact_root_cannot_rename_a_later_run_onto_an_archived_one(tmp_path):
    """Clearing the artifact tree must not make a new run answer to an old row.

    Artifacts and results have separate lifetimes, and clearing the tree is an
    ordinary thing to do. If the attempt's name were chosen by looking for a
    free one on disk, that cleanup would reset the search and hand the next
    run the exact name an archived row still carries. Losing the evidence is
    survivable; the archived row silently pointing at a later run's evidence
    is the misattribution this whole task exists to prevent.
    """
    db = str(tmp_path / "r.db")
    art = str(tmp_path / "art")
    a = [{"id": "c1", "params": {"v": "A"}}]
    b = [{"id": "c1", "params": {"v": "B"}}]

    run_matrix(a, evidence_writer("A1"), db, art, experiment=EXPERIMENT, on_mismatch="rerun")
    run_matrix(b, evidence_writer("B1"), db, art, experiment=EXPERIMENT, on_mismatch="rerun")
    archived = {d for (d,) in query(db, "SELECT artifact_dir FROM results_superseded")}

    shutil.rmtree(art)
    run_matrix(a, evidence_writer("A2"), db, art, experiment=EXPERIMENT, on_mismatch="rerun")
    live = {d for (d,) in query(db, "SELECT artifact_dir FROM results")}

    assert archived and live, "neither set may be empty, or disjointness proves nothing"
    assert not archived & live, "a later run took the name of an archived run"


# --- the definition on record is the one that ran ---------------------------


def test_a_mutating_callback_cannot_rewrite_the_definition_on_record(tmp_path):
    """What the row says was run must be what the fingerprint attests.

    The fingerprint was taken before the callback and the stored definition
    serialised after it, so a callback that mutated the cell it was handed
    left the two describing different things. Passing the original definition
    again then matched the fingerprint and skipped, reporting a result for a
    definition that had never been run.
    """
    db = str(tmp_path / "r.db")
    cell = {"id": "same", "value": "before"}
    expected = cell_fingerprint({"id": "same", "value": "before"})

    def mutating(handed, adir):
        handed["value"] = "after"
        return {"saw": handed["value"]}

    run_matrix([cell], mutating, db, str(tmp_path / "art"), experiment=EXPERIMENT)

    (_, _, fingerprint, _, _, cell_json), = rows(db)
    assert fingerprint == expected
    assert cell_fingerprint(json.loads(cell_json)) == fingerprint, \
        "the stored definition must be the one the fingerprint attests"
    assert cell == {"id": "same", "value": "before"}, \
        "the caller's own cell must come back unchanged"


def test_one_cells_callback_cannot_alter_another_cells_definition(tmp_path):
    """Cells sharing a nested object must still run as planned.

    The plan is fixed before the first cell runs, so a callback reaching a
    later cell's definition through a shared object would leave that cell
    executed as one thing and recorded as another.
    """
    db = str(tmp_path / "r.db")
    shared = {"x": 1}
    cells = [{"id": "first", "params": shared}, {"id": "second", "params": shared}]
    seen = {}

    def mutating(cell, adir):
        seen[cell["id"]] = cell["params"]["x"]
        cell["params"]["x"] = 99
        return {}

    run_matrix(cells, mutating, db, str(tmp_path / "art"), experiment=EXPERIMENT)

    assert seen == {"first": 1, "second": 1}, "the second cell must run as planned"
    for _, _, fingerprint, _, _, cell_json in rows(db):
        assert json.loads(cell_json)["params"]["x"] == 1
        assert cell_fingerprint(json.loads(cell_json)) == fingerprint


# --- conservative migration of pre-provenance databases ---------------------

LEGACY_SCHEMA = ("CREATE TABLE results("
                 "cell_id TEXT PRIMARY KEY, status TEXT, result_json TEXT, artifact_dir TEXT)")


def legacy_db(path, cell_id="same", status="done", result=None):
    con = sqlite3.connect(path)
    con.execute(LEGACY_SCHEMA)
    con.execute("INSERT INTO results VALUES (?,?,?,?)",
                (cell_id, status, json.dumps(result if result is not None else {"x": 1}),
                 "/old/art"))
    con.commit()
    con.close()


def test_legacy_row_is_not_silently_reused(tmp_path):
    """A migrated row cannot be shown to describe the definition being run.

    The experiment here is a named one, which is the same path any caller who
    has adopted an identity takes: migrated rows are unnamespaced, so taking
    an identity cannot hide them. Without that visibility the legacy stratum
    would become unreachable the moment callers started passing an experiment,
    and would accumulate forever.
    """
    db = str(tmp_path / "r.db")
    legacy_db(db)
    calls = []

    with pytest.raises(MatrixIdentityError) as excinfo:
        run_matrix([{"id": "same", "params": {"x": 1}}],
                   collecting_cell(calls), db, str(tmp_path / "art"), experiment=EXPERIMENT)

    assert "provenance" in str(excinfo.value).lower()
    assert calls == []
    stored = rows(db)
    assert len(stored) == 1, "migration must not drop the pre-existing row"
    assert json.loads(stored[0][4]) == {"x": 1}
    assert stored[0][2] is None, "a legacy row keeps a null fingerprint until adopted"


def test_adopting_from_a_named_experiment_drains_the_legacy_stratum(tmp_path):
    db = str(tmp_path / "r.db")
    legacy_db(db)
    calls = []

    out = run_matrix([{"id": "same", "params": {"x": 1}}],
                     collecting_cell(calls), db, str(tmp_path / "art"),
                     experiment={"ruleset": "zzz"}, on_legacy="adopt")

    assert calls == []
    assert out[0]["status"] == "skipped"
    stored = rows(db)
    assert len(stored) == 1, "adoption moves the row, it does not copy it"
    assert stored[0][0] == '{"ruleset":"zzz"}'
    assert stored[0][2] == cell_fingerprint({"id": "same", "params": {"x": 1}})
    assert json.loads(stored[0][4]) == {"x": 1}, "the adopted evidence is preserved"


def test_adoption_is_recorded_so_it_stays_distinguishable(tmp_path):
    """An asserted attribution must not become indistinguishable from a measured one."""
    db = str(tmp_path / "r.db")
    legacy_db(db)

    run_matrix([{"id": "same", "params": {"x": 1}}], collecting_cell([]), db,
               str(tmp_path / "art"), experiment=EXPERIMENT, on_legacy="adopt")

    archived = superseded(db)
    assert len(archived) == 1
    assert archived[0][1] is None, "the archive keeps the unstamped original"
    assert archived[0][4] == "adopted"


def test_adopt_on_a_failed_legacy_row_reruns_it(tmp_path):
    """Adoption asserts that stored evidence describes a definition.

    A failed row is not evidence, so there is nothing to assert: the cell runs
    rather than being reported as a skip that would never be retried.
    """
    db = str(tmp_path / "r.db")
    legacy_db(db, status="failed", result={"error": "boom"})
    calls = []

    out = run_matrix([{"id": "same", "params": {"x": 1}}],
                     collecting_cell(calls), db, str(tmp_path / "art"),
                     experiment=EXPERIMENT, on_legacy="adopt")

    assert calls == [1], "a failed row cannot be adopted as a result"
    assert out[0]["status"] == "done"
    assert json.loads(rows(db)[0][4]) == {"x": 1}


def test_legacy_conflict_does_not_offer_a_new_experiment(tmp_path):
    """The remediation has to be one that works.

    Unnamespaced rows are visible from every experiment, so telling the caller
    to pass a distinct identity would send them straight back to this refusal.
    """
    db = str(tmp_path / "r.db")
    legacy_db(db)

    with pytest.raises(MatrixIdentityError) as excinfo:
        run_matrix([{"id": "same", "params": {"x": 1}}], collecting_cell([]), db,
                   str(tmp_path / "art"), experiment=EXPERIMENT)

    message = str(excinfo.value)
    assert "will not clear this" in message
    assert "or pass a distinct experiment= identity" not in message


def test_a_legacy_table_carrying_an_unknown_column_is_refused_intact(tmp_path):
    """Migration copies four named columns, so a fifth would be destroyed.

    The widened table is filled by an INSERT..SELECT naming the columns this
    runner knows about, and the original is then dropped. A pre-provenance
    table that someone had added a column to would therefore lose that column,
    and every value in it, with no copy kept anywhere and nothing said about
    it. The run is refused before the rename instead, so the table and its
    data are still exactly what they were afterwards.
    """
    db = str(tmp_path / "r.db")
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE results(cell_id TEXT PRIMARY KEY, status TEXT, "
                "result_json TEXT, artifact_dir TEXT, operator_note TEXT)")
    con.execute("INSERT INTO results VALUES ('same','done','{\"x\":1}','/old/art','KEEP_ME')")
    con.commit()
    con.close()
    calls = []

    with pytest.raises(MatrixIdentityError) as excinfo:
        run_matrix([{"id": "same", "params": {"x": 1}}], collecting_cell(calls), db,
                   str(tmp_path / "art"), experiment=EXPERIMENT)

    assert calls == [], "nothing may run against a db the runner will not migrate"

    # The intactness assertions come first on purpose. Without the guard this
    # run still refuses, on the ordinary legacy policy, but only after the
    # migration has already dropped the column; checking the message first
    # would report a wording difference where the fault is the loss.
    columns = [r[1] for r in query(db, "PRAGMA table_info(results)")]
    assert columns == ["cell_id", "status", "result_json", "artifact_dir", "operator_note"], \
        "the unknown column must still be on the table"
    assert query(db, "SELECT cell_id, status, result_json, artifact_dir, operator_note "
                     "FROM results") == [
        ("same", "done", '{"x":1}', "/old/art", "KEEP_ME")], \
        "the row and the value in the unknown column must both survive"
    tables = [r[0] for r in query(db, "SELECT name FROM sqlite_master WHERE type='table'")]
    assert tables == ["results"], (
        "nothing may be renamed, created or dropped by a refused migration: "
        f"{tables}")
    assert "operator_note" in str(excinfo.value), "the refusal must name the column at risk"


def test_a_standard_legacy_table_still_migrates(tmp_path):
    """The refusal above must not cost the migration it guards.

    A table holding exactly the four pre-provenance columns is the one shape
    this runner can widen without losing anything, so it still is widened: the
    historical row lands in the unnamespaced stratum with a null fingerprint,
    and results_v1 does not outlive the migration. A cell id the legacy row
    does not carry is used, so no policy fires and what is observed is the
    migration alone.
    """
    db = str(tmp_path / "r.db")
    legacy_db(db)
    calls = []

    out = run_matrix([{"id": "fresh", "params": {"x": 5}}],
                     collecting_cell(calls), db, str(tmp_path / "art"),
                     experiment=EXPERIMENT)

    assert calls == [5]
    assert out[0]["status"] == "done"

    tables = [r[0] for r in query(db, "SELECT name FROM sqlite_master WHERE type='table'")]
    assert "results_v1" not in tables, "the rename must not outlive the migration"
    assert "fingerprint" in [r[1] for r in query(db, "PRAGMA table_info(results)")]

    stored = {row[1]: row for row in rows(db)}
    assert set(stored) == {"same", "fresh"}, "the historical row must survive the widening"
    assert stored["same"][0] == "", "a migrated row is unnamespaced"
    assert stored["same"][2] is None, "a migrated row keeps a null fingerprint"
    assert json.loads(stored["same"][4]) == {"x": 1}, "its evidence is carried over"


def test_interrupted_migration_leaves_the_original_table(tmp_path, monkeypatch):
    """A half-migrated db reads as current and hides every historical row.

    sqlite3 autocommits DDL outside an explicit transaction, so without one
    the rename would survive an interrupt that the widened table did not,
    stranding every row in results_v1 where nothing looks for it. An
    interrupt is used deliberately: it is the failure no except clause sees.
    """
    db = str(tmp_path / "r.db")
    legacy_db(db)

    def interrupt(con):
        raise KeyboardInterrupt("power cut mid-migration")

    monkeypatch.setattr(matrix_module, "_create_results", interrupt)
    with pytest.raises(KeyboardInterrupt):
        run_matrix([{"id": "same", "params": {"x": 1}}], collecting_cell([]), db,
                   str(tmp_path / "art"), experiment=EXPERIMENT)

    tables = [r[0] for r in query(db, "SELECT name FROM sqlite_master WHERE type='table'")]
    assert "results_v1" not in tables, "the rename must not outlive the migration"
    assert "results" in tables
    assert query(db, "SELECT cell_id, status FROM results") == [("same", "done")]


def test_legacy_row_survives_an_interrupt_during_its_replacement(tmp_path):
    """Nothing is deleted before its replacement exists.

    Clearing the superseded row up front would leave this cell with no row
    under any experiment: the run that was meant to replace it never wrote
    one, and the archive is not somewhere the runner reads back.
    """
    db = str(tmp_path / "r.db")
    legacy_db(db)

    with pytest.raises(KeyboardInterrupt):
        run_matrix([{"id": "same", "params": {"x": 7}}], interrupting_cell(db), db,
                   str(tmp_path / "art"), experiment=EXPERIMENT, on_legacy="rerun")

    stored = rows(db)
    assert len(stored) == 1, "the row being superseded must still be there"
    assert json.loads(stored[0][4]) == {"x": 1}
    assert superseded(db) == [], "nothing was superseded, so nothing may be archived"


def test_legacy_row_can_be_rerun_by_explicit_policy(tmp_path):
    db = str(tmp_path / "r.db")
    legacy_db(db)
    calls = []

    out = run_matrix([{"id": "same", "params": {"x": 7}}],
                     collecting_cell(calls), db, str(tmp_path / "art"),
                     experiment=EXPERIMENT, on_legacy="rerun")

    assert calls == [7]
    assert out[0]["status"] == "done"
    stored = rows(db)
    assert len(stored) == 1, "the superseded legacy row is not left behind"
    assert json.loads(stored[0][4]) == {"x": 7}

    archived = superseded(db)
    assert len(archived) == 1
    assert json.loads(archived[0][3]) == {"x": 1}
    assert archived[0][4] == "legacy"


def test_legacy_failed_row_reruns_without_policy(tmp_path):
    """A failed row is not evidence, so migration never has to arbitrate it."""
    db = str(tmp_path / "r.db")
    legacy_db(db, status="failed", result={"error": "boom"})
    calls = []

    out = run_matrix([{"id": "same", "params": {"x": 1}}],
                     collecting_cell(calls), db, str(tmp_path / "art"), experiment=EXPERIMENT)

    assert calls == [1]
    assert out[0]["status"] == "done"
    assert superseded(db)[0][4] == "legacy", "the failed row is still archived"


def test_failed_migration_leaves_the_database_exactly_as_it_was(tmp_path):
    """A half-migrated db would look current to the next run and hide every row.

    SQLite permits NULL in a TEXT primary key, so a legacy table can hold a row
    the wider schema rejects. The migration must then roll all the way back.
    """
    db = str(tmp_path / "r.db")
    con = sqlite3.connect(db)
    con.execute(LEGACY_SCHEMA)
    con.execute("INSERT INTO results VALUES (NULL,'done','{\"x\":1}','/old')")
    con.execute("INSERT INTO results VALUES ('ok','done','{\"x\":2}','/old')")
    con.commit()
    con.close()

    with pytest.raises(MatrixIdentityError) as excinfo:
        run_matrix([{"id": "ok", "params": {}}], lambda cell, adir: {}, db,
                   str(tmp_path / "art"), experiment=EXPERIMENT)
    assert "left exactly as it was" in str(excinfo.value)

    tables = [r[0] for r in query(db, "SELECT name FROM sqlite_master WHERE type='table'")]
    assert tables == ["results"], (
        "a db this runner refuses to migrate keeps the shape the old one wrote, "
        f"gaining no table that only the new one understands: {tables}")
    assert sorted(query(db, "SELECT cell_id, status FROM results"),
                  key=lambda r: (r[0] is None, r[0])) == [
        ("ok", "done"), (None, "done")], "both original rows must still be in results"


def test_a_foreign_attempts_table_is_refused_intact(tmp_path):
    """A pre-existing 'attempts' table of a different shape must be refused.

    ``CREATE TABLE IF NOT EXISTS`` is a no-op against a table already there
    under that name, so without a shape check the schema_version would be
    bumped to current on this very call, and every later cell would fail
    against a table this runner never actually got to create.
    """
    db = str(tmp_path / "r.db")
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE attempts(id INTEGER PRIMARY KEY, note TEXT)")
    con.execute("INSERT INTO attempts VALUES (1, 'not ours')")
    con.commit()
    con.close()

    with pytest.raises(MatrixIdentityError) as excinfo:
        run_matrix([{"id": "c", "params": {}}], lambda cell, adir: {}, db,
                   str(tmp_path / "art"), experiment=EXPERIMENT)
    assert "table named 'attempts'" in str(excinfo.value)

    assert query(db, "SELECT name FROM sqlite_master WHERE type='table'") == [
        ("attempts",)], "nothing else may be created before this refusal fires"
    assert query(db, "SELECT id, note FROM attempts") == [(1, "not ours")], (
        "the foreign table must be left exactly as it was"
    )

    # The refusal is stable, not a one-time failure that clears itself: every
    # later call meets the same foreign table and refuses it the same way.
    with pytest.raises(MatrixIdentityError):
        run_matrix([{"id": "c", "params": {}}], lambda cell, adir: {}, db,
                   str(tmp_path / "art"), experiment=EXPERIMENT)


def test_an_attempts_table_with_the_right_columns_but_no_primary_key_is_refused(
        tmp_path):
    """Column names alone are not enough: attempt_id must be the primary key.

    Without that constraint, a token collision would insert a second row
    silently instead of raising, defeating the guarantee that a fresh attempt
    never overwrites or duplicates one already recorded.
    """
    db = str(tmp_path / "r.db")
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE attempts(attempt_id TEXT, experiment TEXT, cell_id TEXT, "
        "fingerprint TEXT, cell_json TEXT, artifact_dir TEXT, status TEXT, "
        "result_json TEXT, started_at REAL, finished_at REAL)")
    con.commit()
    con.close()

    with pytest.raises(MatrixIdentityError) as excinfo:
        run_matrix([{"id": "c", "params": {}}], lambda cell, adir: {}, db,
                   str(tmp_path / "art"), experiment=EXPERIMENT)
    assert "not its primary key" in str(excinfo.value)
    assert query(db, "SELECT name FROM sqlite_master WHERE type='table'") == [
        ("attempts",)], "nothing else may be created before this refusal fires"


def test_a_composite_primary_key_sharing_attempt_id_is_also_refused(tmp_path):
    """attempt_id must be the *only* column in the primary key, not just in it.

    ``PRAGMA table_info``'s ``pk`` column is a column's 1-based position
    within the primary key, not a yes/no flag; a naive ``pk == 1`` check
    passes for ``PRIMARY KEY(attempt_id, experiment)`` too, since attempt_id
    is still first. That composite key lets two rows share one attempt_id as
    long as they disagree on experiment, exactly the silent duplicate this
    table exists to rule out.
    """
    db = str(tmp_path / "r.db")
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE attempts(attempt_id TEXT, experiment TEXT, cell_id TEXT, "
        "fingerprint TEXT, cell_json TEXT, artifact_dir TEXT, status TEXT, "
        "result_json TEXT, started_at REAL, finished_at REAL, "
        "PRIMARY KEY(attempt_id, experiment))")
    con.commit()
    con.close()

    with pytest.raises(MatrixIdentityError) as excinfo:
        run_matrix([{"id": "c", "params": {}}], lambda cell, adir: {}, db,
                   str(tmp_path / "art"), experiment=EXPERIMENT)
    assert "not its primary key" in str(excinfo.value)
    assert query(db, "SELECT name FROM sqlite_master WHERE type='table'") == [
        ("attempts",)], "nothing else may be created before this refusal fires"


def test_newer_schema_is_refused_rather_than_misread(tmp_path):
    db = str(tmp_path / "r.db")
    run_matrix([{"id": "c", "params": {}}], lambda cell, adir: {}, db,
               str(tmp_path / "art"), experiment=EXPERIMENT)

    con = sqlite3.connect(db)
    con.execute("INSERT OR REPLACE INTO schema_meta VALUES ('schema_version', '99')")
    con.commit()
    con.close()

    with pytest.raises(MatrixIdentityError) as excinfo:
        run_matrix([{"id": "c", "params": {}}], lambda cell, adir: {}, db,
                   str(tmp_path / "art"), experiment=EXPERIMENT)
    assert "newer version" in str(excinfo.value)


def test_schema_version_is_recorded(tmp_path):
    db = str(tmp_path / "r.db")
    run_matrix([{"id": "c", "params": {}}], lambda cell, adir: {}, db,
               str(tmp_path / "art"), experiment=EXPERIMENT)

    assert query(db, "SELECT value FROM schema_meta WHERE key='schema_version'") == [("4",)]


def test_unknown_policy_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        run_matrix([{"id": "c", "params": {}}], lambda cell, adir: {},
                   str(tmp_path / "r.db"), str(tmp_path / "art"),
                   experiment=EXPERIMENT, on_mismatch="ignore")


def test_a_result_that_cannot_be_stored_fails_only_its_own_cell(tmp_path):
    """An unrecordable result is one cell's failure, not the matrix's.

    The callback returned rather than raised, so the cell did run; what it
    handed back simply cannot be written down. Serialising it at the insert,
    outside the guard that catches the callback, makes that the whole run's
    failure instead: the outcome of the cell that just ran is lost, its
    artifacts are left with no row of any kind pointing at them, and the cells
    behind it never run at all.
    """
    db = str(tmp_path / "r.db")
    art = str(tmp_path / "art")
    calls = []

    def run(cell, adir):
        calls.append(cell["id"])
        return {"obj": {1, 2}} if cell["id"] == "c1" else {"signature": "CLEAN"}

    out = run_matrix([{"id": "c1"}, {"id": "c2"}], run, db, art, experiment=EXPERIMENT)

    assert calls == ["c1", "c2"], "the matrix must not stop at the unstorable result"
    assert [o["status"] for o in out] == ["failed", "done"]
    stored = dict(query(db, "SELECT cell_id, status FROM results"))
    assert stored == {"c1": "failed", "c2": "done"}, (
        "the cell that ran must be recorded, whatever it returned")
    recorded = dict(query(db, "SELECT cell_id, result_json FROM results"))
    assert "not JSON-serialisable" in recorded["c1"]
    for (adir,) in query(db, "SELECT artifact_dir FROM results"):
        assert os.path.isdir(adir), "every row must still point at real evidence"


def test_a_cell_id_that_is_not_a_usable_path_component_is_refused(tmp_path):
    """The id names a directory, so anything but a component is a fault.

    ``../..`` climbs out of ``artifact_root`` and an absolute id discards it
    altogether, taking the experiment component with it: the evidence lands
    where no reader of ``artifact_root`` would look, under a name that no
    longer says which run wrote it. A backslash does the same on Windows, and
    the recorded directory name outlives the machine that wrote it, so it is
    refused here too rather than left to mean one thing on one host and two on
    another. A NUL cannot be handed to the filesystem at all, and an id past
    the component limit cannot be either once the attempt suffix is appended.

    All four are checked against a matrix whose first cell is ordinary,
    because the failure they cause otherwise is not a refusal but a crash
    partway through: the first cell runs and commits, and only then does
    ``os.makedirs`` meet the id it cannot use. The whole purpose of validating
    up front is that no cell runs until the matrix is known to be runnable.
    """
    hostile = [
        ("../../escape-me", "usable path component"),
        (str(tmp_path / "ESCAPED"), "usable path component"),
        ("a\\b", "usable path component"),
        ("a\x00b", "usable path component"),
        ("x" * 300, "bytes"),
    ]
    for bad, expected in hostile:
        calls = []
        with pytest.raises(MatrixIdentityError) as excinfo:
            run_matrix([{"id": "first"}, {"id": bad}],
                       lambda cell, adir: calls.append(cell["id"]),
                       str(tmp_path / "r.db"), str(tmp_path / "art"),
                       experiment=EXPERIMENT)
        assert expected in str(excinfo.value), f"{bad!r} refused for the wrong reason"
        assert calls == [], f"{bad!r} was refused only after a cell had already run"

    assert os.listdir(tmp_path) == [], (
        "the refusal must come before anything at all is written")


def test_a_cyclic_definition_is_refused_rather_than_ending_the_run(tmp_path):
    """The identity walk runs unscreened, so a cycle recurses until the stack ends.

    Checking for coerced keys before ``json.dumps`` is what lets the refusal
    name the offending key, and it is also what removes the screening the dump
    used to do first: the walk now meets a self-referential definition before
    anything has rejected it, and raises ``RecursionError`` rather than the
    ``ValueError`` the dump would have raised. Escaping uncaught, that ends
    the whole matrix with a message about the interpreter instead of about the
    definition, which is the one thing the caller can act on.
    """
    cyclic = {"id": "c", "params": {}}
    cyclic["params"]["self"] = cyclic["params"]

    with pytest.raises(MatrixIdentityError) as excinfo:
        cell_fingerprint(cyclic)
    assert "not canonically serialisable" in str(excinfo.value)

    calls = []
    with pytest.raises(MatrixIdentityError):
        run_matrix([{"id": "ok", "params": {"x": 1}}, cyclic],
                   collecting_cell(calls), str(tmp_path / "r.db"),
                   str(tmp_path / "art"), experiment=EXPERIMENT)
    assert calls == [], "a definition that cannot be hashed must stop the matrix first"


def test_a_result_that_cannot_be_serialised_at_any_depth_fails_only_its_own_cell(tmp_path):
    """Which exception the dump raises is no reason for one cell to cost the matrix.

    A set raises ``TypeError`` and a self-referential result ``ValueError``,
    but a result deep enough to exhaust the encoder's stack raises
    ``RecursionError``, which is neither. Guarding only the first two lets the
    third escape into the run loop and abort every cell behind it, losing the
    outcome of the cell that just ran even though that cell returned normally.

    The depth is far past ``sys.getrecursionlimit()`` because the C encoder
    does not count frames against that limit; it measures the remaining C
    stack and raises when it runs out. A structure this deep is not what a
    sane callback returns, which is the point: the run loop's promise is that
    an unrecordable result is one cell's failure, and that promise cannot be
    conditional on which unrecordable shape the callback picked.
    """
    db = str(tmp_path / "r.db")
    calls = []

    def run(cell, adir):
        calls.append(cell["id"])
        if cell["id"] != "deep":
            return {"signature": "CLEAN"}
        deep = inner = []
        for _ in range(100_000):
            nxt = []
            inner.append(nxt)
            inner = nxt
        return {"obj": deep}

    out = run_matrix([{"id": "deep"}, {"id": "after"}], run, db,
                     str(tmp_path / "art"), experiment=EXPERIMENT)

    assert calls == ["deep", "after"], "the matrix must not stop at the unstorable result"
    assert [o["status"] for o in out] == ["failed", "done"]
    recorded = dict(query(db, "SELECT cell_id, result_json FROM results"))
    assert "not JSON-serialisable" in recorded["deep"]


def test_the_recorded_artifact_directory_does_not_depend_on_the_callers_cwd(
        tmp_path, monkeypatch):
    """``artifact_dir`` is the only durable link from a row to its evidence.

    Stored relative, it resolves against whatever directory happens to be
    current when someone follows it, which is not in general the one the run
    was launched from. ``results_db`` is already absolutised on the way in;
    the pointer that has to survive the process is not.
    """
    monkeypatch.chdir(tmp_path)
    run_matrix([{"id": "c", "params": {"x": 1}}], collecting_cell([]),
               "r.db", "art", experiment=EXPERIMENT)

    (stored,) = [row[0] for row in query("r.db", "SELECT artifact_dir FROM results")]
    assert os.path.isabs(stored), f"a relative evidence pointer was recorded: {stored!r}"
    assert os.path.isdir(stored)


def test_a_named_run_does_not_delete_a_deliberately_unnamespaced_row(tmp_path):
    """``experiment=None`` writes into the unnamespaced stratum and stays there.

    A named run that finds nothing under its own identity looks into that
    stratum, but only for rows with no fingerprint, which is what a migrated
    row is. It does not find the ``None`` run's row, so it must not carry the
    stratum forward as the source of its step either: the delete that drains
    the stratum after a supersession would then fire against a row this run
    never read, and take the other caller's evidence with it.
    """
    db = str(tmp_path / "r.db")
    art = str(tmp_path / "art")
    cells = [{"id": "c", "params": {"x": 1}}]
    run_matrix(cells, collecting_cell([]), db, art, experiment=None)
    run_matrix(cells, collecting_cell([]), db, art, experiment=EXPERIMENT)

    stored = {row[0] for row in
              query(db, "SELECT experiment FROM results WHERE cell_id='c'")}
    assert stored == {"", '{"harness":"1.0","ruleset":"aaa"}'}, (
        "the unnamespaced row was destroyed by a run that never read it")


def test_a_cell_without_an_id_is_refused_by_name(tmp_path):
    """The refusal has to say what is wrong with the matrix.

    A bare KeyError names a missing dict key and leaves the caller to work out
    that the id is what addresses a row, which is the one thing the error
    could have told them.
    """
    with pytest.raises(MatrixIdentityError) as excinfo:
        run_matrix([{"params": {"x": 1}}], lambda cell, adir: {},
                   str(tmp_path / "r.db"), str(tmp_path / "art"), experiment=EXPERIMENT)
    assert "has no 'id'" in str(excinfo.value)


def test_a_mapping_of_mixed_key_types_is_refused_for_the_right_reason():
    """The precise refusal must not be pre-empted by the generic one.

    ``sort_keys`` cannot order an int against a str, so dumping first makes
    every mixed mapping report as unserialisable. The caller is then told the
    definition cannot be hashed, rather than which key is about to make two
    cells share a fingerprint.
    """
    with pytest.raises(MatrixIdentityError) as excinfo:
        cell_fingerprint({"id": "c", "params": {1: "a", "b": 2}})
    assert "non-string mapping key" in str(excinfo.value)
    assert "not canonically serialisable" not in str(excinfo.value), (
        "the key refusal was re-wrapped in the generic serialisation refusal")


def test_a_mixed_conflict_does_not_offer_a_new_experiment_either(tmp_path):
    """One legacy row in a refusal is enough to make that advice unfollowable.

    A new identity clears the mismatches and then meets the legacy rows again
    underneath it, because unnamespaced rows stay visible from every
    experiment. Advice that resolves part of a refusal and silently leaves the
    rest is worse than none: the caller follows it and lands back here.
    """
    db = str(tmp_path / "r.db")
    art = str(tmp_path / "art")
    legacy_db(db)
    run_matrix([{"id": "fresh", "params": {"x": 1}}], lambda cell, adir: {},
               db, art, experiment=EXPERIMENT)

    with pytest.raises(MatrixIdentityError) as excinfo:
        run_matrix([{"id": "same", "params": {"x": 9}},
                    {"id": "fresh", "params": {"x": 2}}],
                   lambda cell, adir: {}, db, art, experiment=EXPERIMENT)

    message = str(excinfo.value)
    assert "predates provenance" in message and "different definition" in message, message
    assert "or pass a distinct experiment= identity" not in message
    assert "will not clear this" in message


def experiment_dir_name(experiment):
    """The directory component the runner derives from an identity."""
    return matrix_module._experiment_dir_name(
        matrix_module._experiment_key(experiment))


def assert_inside(path, root):
    """Containment, spelled out here rather than borrowed from the runner.

    Deliberately not ``commonpath``: a test that reuses the production
    predicate agrees with it by construction and would keep passing if that
    predicate were wrong.
    """
    real = os.path.realpath(path)
    assert real.startswith(os.path.realpath(root) + os.sep), (
        f"{real!r} is not under {os.path.realpath(root)!r}")


def redirected_root(tmp_path, target_name):
    """An artifact root whose experiment directory is a link to elsewhere.

    Returns the root and the directory it has been pointed at, so a test can
    check both that the run was refused and that nothing was written where the
    link led.
    """
    target = tmp_path / target_name
    target.mkdir()
    art = tmp_path / "art"
    art.mkdir()
    (art / experiment_dir_name(EXPERIMENT)).symlink_to(target)
    return art, target


def test_a_symlink_inside_the_artifact_root_cannot_redirect_the_callback(tmp_path):
    """A name inside the root can still resolve outside it.

    Every check the runner had was on the id as a string, and a string check
    cannot see a symlink: the id is a legal component, the path it builds is
    lexically under ``artifact_root``, and the directory the callback is handed
    still resolves somewhere else entirely. The evidence then lands outside the
    area the caller set aside for it, while every row in the db points at a
    path that reads as if it were inside.

    Refused before any cell runs, because the experiment directory is the same
    for the whole matrix: there is nothing cell-specific to wait for, and
    finding out at cell five would mean four cells had already written.
    """
    art, outside = redirected_root(tmp_path, "outside")

    calls = []
    db = tmp_path / "r.db"
    with pytest.raises(MatrixArtifactError) as excinfo:
        run_matrix([{"id": "first"}, {"id": "second"}],
                   id_collecting_cell(calls),
                   str(db), str(art), experiment=EXPERIMENT)
    assert "resolves outside" in str(excinfo.value), excinfo.value
    assert calls == []
    assert list(outside.iterdir()) == []
    assert not db.exists(), (
        "a run that cannot write its evidence left a results db behind")


def test_a_sibling_of_the_artifact_root_is_outside_it(tmp_path):
    """Containment is a path relation, not a string prefix.

    ``/x/artevil`` starts with ``/x/art`` and is no more inside it than any
    other directory on the disk. Tested apart from the plain redirection case
    because it is the one arrangement where the cheap check and the correct
    one disagree, and an attacker choosing where to point a link chooses the
    name too.
    """
    art, sibling = redirected_root(tmp_path, "artevil")

    calls = []
    with pytest.raises(MatrixArtifactError) as excinfo:
        run_matrix([{"id": "first"}], id_collecting_cell(calls),
                   str(tmp_path / "r.db"), str(art), experiment=EXPERIMENT)

    assert "resolves outside" in str(excinfo.value), excinfo.value
    assert calls == []
    assert list(sibling.iterdir()) == []


def test_an_artifact_root_that_is_itself_a_symlink_is_trusted(tmp_path):
    """The boundary is the root the caller named, symlink or not.

    The caller chose ``artifact_root``, so pointing it at another disk is a
    decision, not a redirection: refusing it would break the ordinary case of
    an operator parking evidence somewhere with room for it. What the caller
    did not choose is what a link *inside* that root points at, which is why
    the two are treated differently rather than by one blanket rule.
    """
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)

    run_matrix([{"id": "cell"}], evidence_writer("A"),
               str(tmp_path / "r.db"), str(link), experiment=EXPERIMENT)

    (adir,) = [row[0] for row in query(str(tmp_path / "r.db"),
                                       "SELECT artifact_dir FROM results")]
    assert evidence_of(adir) == "A"
    assert_inside(adir, real)


def test_a_drive_relative_id_cannot_discard_the_artifact_root(tmp_path):
    """An id carrying a drive letter is not a component anywhere.

    Composition proof rather than an end-to-end Windows run: joining a
    drive-relative component throws the root away instead of appending to it,
    so the attempt would be written to whatever that drive's working directory
    happens to be, outside ``artifact_root`` and outside the experiment
    namespace. The separators are already refused on every platform for the
    same reason, that the recorded directory name outlives the machine that
    wrote it; this is the same fault wearing a different character.
    """
    leaf = "D:evil.0123456789ab.0123456789ab"
    assert ntpath.join(r"C:\root\art", "exp-0123456789ab", leaf) == leaf

    calls = []
    with pytest.raises(MatrixIdentityError) as excinfo:
        run_matrix([{"id": "first"}, {"id": "D:evil"}],
                   id_collecting_cell(calls),
                   str(tmp_path / "r.db"), str(tmp_path / "art"),
                   experiment=EXPERIMENT)

    assert "drive" in str(excinfo.value), excinfo.value
    assert calls == []


def test_an_empty_id_names_a_confined_directory_and_still_resumes(tmp_path):
    """An empty id is unusual, not unsafe, so it is not refused.

    It stays inside the root and addresses its row as consistently as any
    other id, which is the whole of what is asked of it. Refusing it would be
    a judgement about taste dressed up as a safety check, and the run it would
    break is a legitimate one.
    """
    db = str(tmp_path / "r.db")
    art = str(tmp_path / "art")
    cells = [{"id": "", "params": {"x": 1}}]

    run_matrix(cells, evidence_writer("A"), db, art, experiment=EXPERIMENT)
    (adir,) = [row[0] for row in query(db, "SELECT artifact_dir FROM results")]
    assert_inside(adir, art)

    second = run_matrix(cells, evidence_writer("B"), db, art, experiment=EXPERIMENT)
    assert [row["status"] for row in second] == ["skipped"]
    assert evidence_of(adir) == "A"


def test_ids_a_filesystem_might_fold_together_never_share_a_directory(tmp_path):
    """Ids that a filesystem may conflate still address separate evidence.

    The two spellings of the accented name are distinct keys in the db and one
    name on a filesystem that normalises, and the two spellings of the case
    differ only where the filesystem folds case. Neither can cost the other its
    evidence, and not because of the attempt token: the id is part of the
    definition, so four spellings are four fingerprints, and the leaf carries
    the fingerprint in front of the token. Two attempts of one cell are the
    case the token answers, and they are covered separately above.

    Non-ASCII is also the shape most likely to be mangled on its way to the
    filesystem, so this is where the directories are checked to still be inside
    the root rather than somewhere a normalising layer put them.
    """
    nfc = unicodedata.normalize("NFC", "caf\u00e9")
    nfd = unicodedata.normalize("NFD", "caf\u00e9")
    assert nfc != nfd
    db = str(tmp_path / "r.db")
    art = str(tmp_path / "art")

    seen = []

    def run_cell(cell, adir):
        seen.append(adir)
        return {}

    run_matrix([{"id": nfc}, {"id": nfd}, {"id": "Cell"}, {"id": "cell"}],
               run_cell, db, art, experiment=EXPERIMENT)

    assert len({os.path.basename(d) for d in seen}) == 4, seen
    for d in seen:
        assert_inside(d, art)

    stored = dict(query(db, "SELECT cell_id, artifact_dir FROM results"))
    assert set(stored) == {nfc, nfd, "Cell", "cell"}
    assert stored[nfc] != stored[nfd]
    assert stored["Cell"] != stored["cell"]


# --- RUN-08: supersession identity and archive ordering ---


def test_superseding_run_records_its_identity_on_the_archived_row(tmp_path):
    db = str(tmp_path / "r.db")
    art = str(tmp_path / "art")
    run_matrix([{"id": "c", "params": {"x": 1}}], lambda cell, adir: {"x": 1},
               db, art, experiment=EXPERIMENT)
    run_matrix([{"id": "c", "params": {"x": 2}}], lambda cell, adir: {"x": 2},
               db, art, experiment=EXPERIMENT, on_mismatch="rerun")

    archived = superseded_rows(db)
    assert len(archived) == 1
    assert archived[0]["displaced_by"] is not None, (
        "the run that displaced this row must record its identity")
    assert len(archived[0]["displaced_by"]) == 32, "expected a hex UUID"


def test_two_superseding_runs_carry_distinct_identities(tmp_path):
    db = str(tmp_path / "r.db")
    art = str(tmp_path / "art")
    run_matrix([{"id": "c", "params": {"x": 1}}], lambda cell, adir: {"x": 1},
               db, art, experiment=EXPERIMENT)
    run_matrix([{"id": "c", "params": {"x": 2}}], lambda cell, adir: {"x": 2},
               db, art, experiment=EXPERIMENT, on_mismatch="rerun")
    run_matrix([{"id": "c", "params": {"x": 3}}], lambda cell, adir: {"x": 3},
               db, art, experiment=EXPERIMENT, on_mismatch="rerun")

    archived = superseded_rows(db)
    assert len(archived) == 2
    ids = {row["displaced_by"] for row in archived}
    assert len(ids) == 2, (
        "two separate run_matrix calls must produce distinct displaced_by values")


def test_archive_seq_is_monotonic_and_independent_of_wall_clock(tmp_path):
    db = str(tmp_path / "r.db")
    art = str(tmp_path / "art")
    run_matrix([{"id": "c", "params": {"x": 1}}], lambda cell, adir: {"x": 1},
               db, art, experiment=EXPERIMENT)
    run_matrix([{"id": "c", "params": {"x": 2}}], lambda cell, adir: {"x": 2},
               db, art, experiment=EXPERIMENT, on_mismatch="rerun")
    run_matrix([{"id": "c", "params": {"x": 3}}], lambda cell, adir: {"x": 3},
               db, art, experiment=EXPERIMENT, on_mismatch="rerun")

    archived = superseded_rows(db)
    seqs = [row["seq"] for row in archived]
    assert seqs == sorted(seqs, reverse=True), (
        "superseded_rows returns rows in descending seq order")
    assert len(set(seqs)) == len(seqs), "seq values must be unique"
    assert all(isinstance(s, int) and s >= 1 for s in seqs), (
        "seq must be a positive integer")


def test_superseded_rows_reader_filters_by_cell_id(tmp_path):
    db = str(tmp_path / "r.db")
    art = str(tmp_path / "art")
    run_matrix([{"id": "a", "params": {"x": 1}}, {"id": "b", "params": {"y": 1}}],
               lambda cell, adir: cell, db, art, experiment=EXPERIMENT)
    run_matrix([{"id": "a", "params": {"x": 2}}, {"id": "b", "params": {"y": 2}}],
               lambda cell, adir: cell, db, art, experiment=EXPERIMENT,
               on_mismatch="rerun")

    all_rows = superseded_rows(db)
    assert len(all_rows) == 2

    a_rows = superseded_rows(db, cell_id="a")
    assert len(a_rows) == 1
    assert a_rows[0]["cell_id"] == "a"

    b_rows = superseded_rows(db, cell_id="b")
    assert len(b_rows) == 1
    assert b_rows[0]["cell_id"] == "b"

    assert superseded_rows(db, cell_id="missing") == []


def test_superseded_rows_reader_returns_all_archive_fields(tmp_path):
    db = str(tmp_path / "r.db")
    art = str(tmp_path / "art")
    run_matrix([{"id": "c", "params": {"x": 1}}], lambda cell, adir: {"x": 1},
               db, art, experiment=EXPERIMENT)
    run_matrix([{"id": "c", "params": {"x": 2}}], lambda cell, adir: {"x": 2},
               db, art, experiment=EXPERIMENT, on_mismatch="rerun")

    row = superseded_rows(db)[0]
    expected_keys = {"experiment", "cell_id", "fingerprint", "cell_json",
                     "status", "result_json", "artifact_dir", "reason",
                     "superseded_at", "displaced_by", "seq"}
    assert set(row.keys()) == expected_keys
    assert row["cell_id"] == "c"
    assert row["reason"] == "mismatch"
    assert row["status"] == "done"
    assert json.loads(row["result_json"]) == {"x": 1}


def test_v3_database_migrates_without_losing_archived_rows(tmp_path):
    """A database written at schema v3 gains the new columns on first access."""
    db = str(tmp_path / "r.db")
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE results("
                "experiment TEXT, cell_id TEXT, fingerprint TEXT, cell_json TEXT, "
                "status TEXT, result_json TEXT, artifact_dir TEXT, "
                "PRIMARY KEY (experiment, cell_id))")
    con.execute("CREATE TABLE results_superseded("
                "experiment TEXT, cell_id TEXT, fingerprint TEXT, cell_json TEXT, "
                "status TEXT, result_json TEXT, artifact_dir TEXT, "
                "reason TEXT, superseded_at REAL)")
    con.execute("CREATE TABLE schema_meta(key TEXT PRIMARY KEY, value TEXT)")
    con.execute("INSERT INTO schema_meta VALUES ('schema_version', '3')")
    con.execute(
        "INSERT INTO results_superseded VALUES "
        "(?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("exp", "c", "fp1", '{"x":1}', "done", '{"x":1}', "/art/old",
         "mismatch", 1000.0))
    con.execute(
        "INSERT INTO results VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("exp", "c", "fp2", '{"x":2}', "done", '{"x":2}', "/art/new"))
    con.commit()
    con.close()

    run_matrix([{"id": "c", "params": {"x": 2}}], lambda cell, adir: {"x": 2},
               db, str(tmp_path / "art"), experiment={"harness": "1.0"})

    archived = superseded_rows(db)
    old_row = [r for r in archived if r["fingerprint"] == "fp1"]
    assert len(old_row) == 1, "the pre-existing archived row must survive migration"
    assert old_row[0]["displaced_by"] is None, (
        "migrated rows have no displaced_by, which is honest, not a gap")
    assert old_row[0]["seq"] is not None, "migrated rows get a seq value"
    assert query(db, "SELECT value FROM schema_meta WHERE key='schema_version'") == [("4",)]


def test_adoption_records_run_identity_on_the_archived_original(tmp_path):
    db = str(tmp_path / "r.db")
    art = str(tmp_path / "art")
    legacy_db(db)

    run_matrix([{"id": "same", "params": {"x": 1}}], lambda cell, adir: {"x": 1},
               db, art, experiment=EXPERIMENT, on_legacy="adopt")

    archived = superseded_rows(db)
    assert len(archived) == 1
    assert archived[0]["reason"] == "adopted"
    assert archived[0]["displaced_by"] is not None, (
        "adoption must record which run took it")


# --- TASK-57: superseded_rows reader covers all reasons and missing table ---


def test_superseded_rows_on_database_without_the_table(tmp_path):
    """A database written before RUN-01 has no results_superseded table.

    The reader must return an empty list rather than raising
    sqlite3.OperationalError, because to the caller the absence of the table
    and the absence of archived rows mean the same thing.
    """
    db = str(tmp_path / "r.db")
    con = sqlite3.connect(db)
    con.execute(LEGACY_SCHEMA)
    con.execute("INSERT INTO results VALUES (?,?,?,?)",
                ("c", "done", '{"x": 1}', "/art"))
    con.commit()
    con.close()

    assert superseded_rows(db) == []
    assert superseded_rows(db, cell_id="c") == []


def test_superseded_rows_on_empty_database(tmp_path):
    """A fresh database file with no tables at all must not raise."""
    db = str(tmp_path / "empty.db")
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE dummy(x)")
    con.commit()
    con.close()

    assert superseded_rows(db) == []


def test_superseded_rows_covers_mismatch_reason(tmp_path):
    """A changed definition under on_mismatch='rerun' archives with reason 'mismatch'."""
    db = str(tmp_path / "r.db")
    art = str(tmp_path / "art")
    run_matrix([{"id": "c", "params": {"x": 1}}], lambda cell, adir: {"x": 1},
               db, art, experiment=EXPERIMENT)
    run_matrix([{"id": "c", "params": {"x": 2}}], lambda cell, adir: {"x": 2},
               db, art, experiment=EXPERIMENT, on_mismatch="rerun")

    archived = superseded_rows(db)
    assert len(archived) == 1
    row = archived[0]
    assert row["reason"] == "mismatch"
    assert row["cell_id"] == "c"
    assert json.loads(row["result_json"]) == {"x": 1}
    assert row["superseded_at"] is not None


def test_superseded_rows_covers_legacy_reason(tmp_path):
    """A pre-provenance row superseded by on_legacy='rerun' archives with reason 'legacy'."""
    db = str(tmp_path / "r.db")
    art = str(tmp_path / "art")
    legacy_db(db)

    run_matrix([{"id": "same", "params": {"x": 1}}], lambda cell, adir: {"x": 1},
               db, art, experiment=EXPERIMENT, on_legacy="rerun")

    archived = superseded_rows(db)
    assert len(archived) == 1
    row = archived[0]
    assert row["reason"] == "legacy"
    assert row["cell_id"] == "same"
    assert json.loads(row["result_json"]) == {"x": 1}
    assert row["superseded_at"] is not None


def test_superseded_rows_covers_adopted_reason(tmp_path):
    """A legacy row claimed by on_legacy='adopt' archives with reason 'adopted'."""
    db = str(tmp_path / "r.db")
    art = str(tmp_path / "art")
    legacy_db(db)

    run_matrix([{"id": "same", "params": {"x": 1}}], lambda cell, adir: {"x": 1},
               db, art, experiment=EXPERIMENT, on_legacy="adopt")

    archived = superseded_rows(db)
    assert len(archived) == 1
    row = archived[0]
    assert row["reason"] == "adopted"
    assert row["cell_id"] == "same"
    assert json.loads(row["result_json"]) == {"x": 1}
    assert row["superseded_at"] is not None
