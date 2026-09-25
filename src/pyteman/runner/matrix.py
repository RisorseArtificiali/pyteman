import collections
import hashlib
import json
import ntpath
import os
import sqlite3
import time
import uuid

from . import lock as _lock
from .lock import MatrixLockError  # noqa: F401  re-exported for callers

SCHEMA_VERSION = 3

_MISMATCH_POLICIES = ("error", "rerun")
_LEGACY_POLICIES = ("error", "rerun", "adopt")

# The unnamespaced stratum. Rows migrated from a pre-provenance database land
# here because their experiment is genuinely unknown, and they stay visible
# from every experiment until a policy resolves them, so the migration has a
# way to finish instead of stranding rows nobody can reach.
_LEGACY_EXPERIMENT = ""

# The results columns, named once. The archive copies rows with INSERT..SELECT,
# where two column lists that have drifted apart still have matching arity: the
# statement runs clean and silently drops the new column from every superseded
# row. The archive is the only durable trace of superseded evidence, so that
# loss is both unrecoverable and invisible until someone reads history.
_RESULT_COLUMNS = ("experiment", "cell_id", "fingerprint", "cell_json",
                   "status", "result_json", "artifact_dir")
_RESULT_COLUMN_LIST = ", ".join(_RESULT_COLUMNS)

# Stands in for an outcome sqlite refused to store for its size. Fixed text
# rather than a description built from what failed: everything to hand at that
# point is either the payload that was already too large or an exception whose
# message quotes it, so interpolating any of it reproduces the refusal inside
# the row meant to survive it. It says an outcome was too large without naming
# which part of the row carried the excess, because the code has not measured
# that: the result, the callback's own error text and the cell definition all
# travel in the same row and any of them can be the one over the limit.
_OVERSIZED_OUTCOME = {
    "error": "original outcome too large to record, replaced with failure",
}
_OVERSIZED_OUTCOME_JSON = json.dumps(_OVERSIZED_OUTCOME)

# The whole of the attempts table this runner writes. CREATE TABLE IF NOT
# EXISTS is a no-op against a table that already exists under this name with
# a different shape, so an unrelated or foreign table by this name would
# otherwise sit there unnoticed while every attempt insert against it fails.
_ATTEMPTS_COLUMNS = frozenset((
    "attempt_id", "experiment", "cell_id", "fingerprint", "cell_json",
    "artifact_dir", "status", "result_json", "started_at", "finished_at"))

# The whole of a pre-provenance results table. The migration copies these four
# by name and then drops the original, so a table carrying any other column
# would have it destroyed with no copy kept anywhere. This is the set the
# migration is allowed to claim it understands.
_LEGACY_RESULT_COLUMNS = frozenset(("cell_id", "status", "result_json", "artifact_dir"))

# The attempt directory name is "{id}.{fingerprint_slice}.{token}".
# Both slices are fixed-width hex drawn from the same [:N] used here.
_FINGERPRINT_SLICE = 12
_TOKEN_SLICE = 12

# ext4, APFS and NTFS each allow 255 bytes per single path component.
_COMPONENT_LIMIT = 255

# Derived from the suffix _attempt_dir appends, so widening either
# slice or adding a third field moves the budget automatically.
_ATTEMPT_SUFFIX_LEN = 1 + _FINGERPRINT_SLICE + 1 + _TOKEN_SLICE
_MAX_ID_BYTES = _COMPONENT_LIMIT - _ATTEMPT_SUFFIX_LEN

# The definition a run is held to, captured before anything can change it, and
# the identity derived from that exact text rather than from a live object.
_Cell = collections.namedtuple("_Cell", "id definition fingerprint")

_Step = collections.namedtuple("_Step", "cell action archive source")


class MatrixIdentityError(RuntimeError):
    """A stored result cannot be attributed to the cell definition being run.

    Raised for duplicate cell ids inside one matrix, for a resume whose stored
    fingerprint disagrees with the current definition, for pre-provenance rows
    that no policy has authorised the runner to reuse, and for a results db
    this runner is too old to understand.
    """


class MatrixArtifactError(RuntimeError):
    """The place the artifacts would be written is not the place it names.

    Distinct from ``MatrixIdentityError`` because it says something about the
    filesystem rather than about the matrix: the cells, their ids and their
    definitions may all be perfectly well formed, and the caller's remedy is
    to look at ``artifact_root`` rather than at the code that built the cells.
    """


class MatrixResultError(RuntimeError):
    """``run_cell`` handed back something that is not a result.

    Raised inside the guard that already covers the callback, so it costs the
    cell rather than the matrix: returning the wrong shape is a bug in that
    one cell's code, and the cells around it have nothing to do with it. A
    class rather than a bare message because the row it produces outlives the
    run, and a reader months later needs it to name the fault.

    It never escapes ``run_matrix``. That same guard converts it to the failed
    row's ``error`` text, which is the only place a caller ever sees it, so
    ``except MatrixResultError`` around a run is a handler that cannot fire.
    The class exists for the name ``repr`` puts in the stored row, not for a
    caller to catch.
    """


class MatrixStorageError(RuntimeError):
    """A cell ran and its outcome could not be written down.

    Distinct from ``MatrixResultError`` because the cell is not at fault and
    the run cannot carry on as though it were. A result that will not
    serialise is recorded as that cell's failure and the matrix continues; a
    db that will not accept the row has lost the evidence the run exists to
    produce, and every later cell would be writing into the same hole. Raised
    rather than recorded, because recording is what failed.
    """


def _coerced_keys(obj):
    """Every mapping key ``json.dumps`` would rewrite, in the order met.

    Screens results. Definitions are screened by ``_reject_coerced_keys``,
    which walks separately and reports differently, and the duplication is
    deliberate: that walk decides whether a fingerprint may exist at all, so
    the key it names first and the error a hostile definition earns are part
    of a contract older than this one. Sharing a walk would have made both
    fall out of whichever traversal happened to suit the newer caller.

    Detection only: the walk that finds a key carries no explanation, because
    the two callers refuse for unrelated reasons and with unrelated error
    types. Lists and tuples are descended because JSON flattens both to
    arrays, which puts a mapping reached through either on exactly the same
    footing as one reached directly.

    Walked with an explicit stack rather than by recursion, because a recursive
    walk is the more fragile of the two and this one has to be at least as
    sturdy as the serialiser it screens for. Measured on CPython 3.14: a
    recursive version of this function raises ``RecursionError`` on a structure
    nested about 800 deep, while ``json.dumps`` serialises the same structure
    without complaint. Screening with the fragile walk would therefore have
    failed perfectly good results that used to be stored, and, worse, would
    have had to let the deep ones past to avoid that, which is the coerced key
    reaching the row by another route.

    ``seen`` makes a cycle finite rather than fatal, and that is also what
    leaves the circular case to ``json.dumps``, which names it exactly. A
    container visited twice is not walked twice, which costs nothing here: a
    key this walk is looking for would have been found on the first visit.
    """
    seen = set()
    stack = [obj]
    while stack:
        node = stack.pop()
        if not isinstance(node, (dict, list, tuple)):
            continue
        if id(node) in seen:
            continue
        seen.add(id(node))
        if isinstance(node, dict):
            for key in node:
                if not isinstance(key, str):
                    yield key
            stack.extend(reversed(list(node.values())))
        else:
            stack.extend(reversed(node))


def _reject_coerced_keys(obj, what):
    """Refuse mappings whose keys JSON would silently rewrite.

    ``json.dumps`` coerces int, float, bool and None keys to strings, so
    ``{1: 'a'}`` and ``{'1': 'a'}`` serialise identically and would share a
    fingerprint. That is exactly the misattribution this identity exists to
    prevent, so the coercion is refused rather than hashed.

    Runs before ``json.dumps`` rather than after, so nothing has screened the
    structure first: a cyclic definition recurses here until the interpreter
    stops it. ``_canonical`` is what turns that into a refusal, which is why
    this walk is called from inside its guard.
    """
    if isinstance(obj, dict):
        for key, value in obj.items():
            if not isinstance(key, str):
                raise MatrixIdentityError(
                    f"{what} has the non-string mapping key {key!r}, which JSON "
                    f"would rewrite as {str(key)!r}; two different definitions "
                    "would then share one fingerprint, so give the key as a string")
            _reject_coerced_keys(value, what)
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            _reject_coerced_keys(value, what)


def _canonical(obj, what):
    """Canonical JSON: key order and whitespace never change the fingerprint.

    A tuple and a list of the same values are deliberately one value here.
    The definition is persisted as this very text and reloaded as a list, so
    the equivalence is a property of the record rather than a weakness of the
    hash; a caller who needs the two distinguished has to encode that.
    """
    # The key check runs before the dump, not after: a mapping mixing key
    # types makes sort_keys raise a TypeError of its own, so the caller would
    # be told the definition is unserialisable rather than which key two cells
    # would end up sharing. Both are inside one guard because that ordering
    # leaves the key walk unscreened, and a cyclic definition exhausts the
    # stack there instead of reaching the circular-reference check.
    try:
        _reject_coerced_keys(obj, what)
        text = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    except MatrixIdentityError:
        # Already the precise refusal; re-wrapping it would replace the name
        # of the offending key with the generic message.
        raise
    except Exception as exc:
        raise MatrixIdentityError(
            f"{what} is not canonically serialisable, so no stable identity "
            f"can be derived for it: {exc!r}") from exc
    return text


def cell_definition(cell):
    """Canonical text of one cell definition, as persisted alongside its result."""
    return _canonical(cell, f"cell {cell.get('id')!r}")


def cell_fingerprint(cell):
    """Identity of one cell definition.

    Deliberately independent of the experiment: the experiment is the row's
    namespace (the leading primary-key column), so folding it in here would
    only re-test something the lookup has already constrained, while making
    the same definition unrecognisable across experiments.
    """
    return _fingerprint(cell_definition(cell))


def _fingerprint(definition):
    return hashlib.sha256(definition.encode("utf-8")).hexdigest()


def _freeze(cell):
    """Capture the definition this run will be held to, once and for all.

    Everything downstream reads this text rather than the caller's object. A
    ``run_cell`` that mutates the cell it is handed, or two cells sharing a
    nested object, would otherwise leave the stored ``cell_json`` describing
    something other than what the fingerprint attests and what actually ran.
    """
    definition = cell_definition(cell)
    return _Cell(cell["id"], definition, _fingerprint(definition))


def _experiment_key(experiment):
    """Canonical form of the caller-supplied experiment identity."""
    if experiment is None:
        return _LEGACY_EXPERIMENT
    return _canonical(experiment, "experiment identity")


def _attempt_dir(experiment_dir, cell, token):
    """Name, but do not create, the directory this attempt's artifacts go in.

    The name carries the whole identity of the attempt, because the artifacts
    are the evidence a row points at and two rows that share a directory are
    two rows with one body of evidence between them.

    Identity alone does not name the attempt, though. A cell run as A, then B,
    then A again comes back to a fingerprint it has already used, and the
    directory from the first A is what the archived row still points at. So
    the name ends in a token minted for this attempt and nothing else.

    The token is a parameter rather than minted here because ``_begin_attempt``
    has to record it in ``attempts`` before this directory exists: the row and
    the name it names have to agree, and the row comes first.

    ``experiment_dir`` is the directory ``_prepare_experiment_dir`` resolved
    and pinned inside the root, passed in rather than rebuilt here so that the
    directory being written into is the one that was checked.
    """
    fp = cell.fingerprint[:_FINGERPRINT_SLICE]
    return os.path.join(experiment_dir, f"{cell.id}.{fp}.{token}")


def _begin_attempt(con, experiment_dir, experiment_key, cell):
    """Record an attempt before anything it might do to the filesystem.

    The token is minted here, and the row naming it is inserted and committed
    before the caller so much as calls ``os.makedirs``. A process killed after
    this returns leaves a row that says an attempt was going to happen and
    where; nothing before this point could leave less than that, because
    nothing before this point has decided the attempt's name yet. The token is
    minted rather than counted for the same reason ``_attempt_dir`` always
    named one: the register of past attempts is ``attempts``, not the artifact
    tree, so a name has to come from somewhere a cleanup of that tree cannot
    reset.

    A plain ``INSERT``, not ``OR REPLACE``: the token is fresh from ``uuid4``,
    so a collision is not a name this run has ever used before, and papering
    over one by replacing whatever row already held it would silently discard
    that row's history. If sqlite raises here, that is exactly what should
    happen instead.

    This is its own commit, distinct from and well before the transaction
    ``run_matrix`` opens once the cell has run. Two short transactions instead
    of one long one held across the callback: the callback runs with nothing
    of this connection's held open, which is the same property the results
    write downstream already depends on.
    """
    token = uuid.uuid4().hex[:_TOKEN_SLICE]
    adir = _attempt_dir(experiment_dir, cell, token)
    now = time.time()
    con.execute(
        "INSERT INTO attempts(attempt_id, experiment, cell_id, fingerprint, "
        "cell_json, artifact_dir, status, result_json, started_at, finished_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (token, experiment_key, cell.id, cell.fingerprint, cell.definition,
         adir, "running", None, now, None))
    con.commit()
    return token, adir


def _prepare_experiment_dir(artifact_root, experiment_key):
    """Pin the experiment's directory inside the root before anything runs.

    Namespacing by experiment matters from the very first run: without it, two
    experiments running the same cell id write over each other before any
    mismatch has occurred. This is the only place that joins that component,
    so the path that is checked here is the path attempts are created under.

    ``_check_cell_ids`` reads an id as a string, and a string cannot tell you
    where the filesystem will send it: a component that is lexically inside
    ``artifact_root`` still leaves it if something on the way is a symlink
    pointing out. So the containment is decided here, against the resolved
    path, once per run and before the db is opened, because a run that cannot
    write its evidence where it says should not leave a half-populated db
    behind. Nothing is created before the check either, so a refused run does
    not leave a root the caller never asked for. A run refused later, on its
    cells or its identities, does leave this directory empty: it is inside the
    root the caller named, which is the point.

    The root the caller named is trusted even when it is itself a symlink:
    parking evidence on another disk is an operator's decision, and refusing
    it would refuse the deployment rather than an attack. What is refused is
    redirection the caller did not choose, from inside the root outwards.

    Creating the directory straight after the check is what turns "this name
    resolved inside the root a moment ago" into "a real directory occupies
    that name", which cannot then be replaced by simply creating a symlink.
    That is weaker than a lock and is not one: this reads the filesystem as it
    is now, and a path handed to a callback can be replaced after it is
    resolved. The callback receives a path rather than an open directory, so a
    hostile substitution concurrent with the run is outside what this can
    promise.
    """
    d = os.path.join(artifact_root, _experiment_dir_name(experiment_key))
    real_root = os.path.realpath(artifact_root)
    real_d = os.path.realpath(d)
    # A path relation rather than a string prefix: '/x/artevil' starts with
    # '/x/art' and is no more inside it than any other directory on the disk.
    # commonpath also raises when the two cannot be compared at all, which on
    # Windows means separate drives, and separate drives is not containment.
    try:
        contained = os.path.commonpath((real_root, real_d)) == real_root
    except ValueError:
        contained = False
    if not contained:
        raise MatrixArtifactError(
            f"the experiment directory {d!r} resolves outside its artifact "
            f"root: {real_d!r} is not under {real_root!r}. Something on that "
            "path redirects elsewhere, so the attempts would be written "
            "outside the area the caller set aside for this matrix's evidence")
    os.makedirs(d, exist_ok=True)
    return d


def _experiment_dir_name(experiment_key):
    """A filesystem-safe name for an identity that is arbitrary JSON text.

    Hashed, unlike the db column, because a path component cannot hold the
    raw identity: it may be long, and it may contain separators. The db keeps
    the readable form, and the report prints it, so nothing is lost here.
    """
    return "exp-" + _fingerprint(experiment_key)[:12]


def _create_results(con):
    con.execute("CREATE TABLE results("
                "experiment TEXT NOT NULL, cell_id TEXT NOT NULL, "
                "fingerprint TEXT, cell_json TEXT, "
                "status TEXT, result_json TEXT, artifact_dir TEXT, "
                "PRIMARY KEY (experiment, cell_id))")


def _migrate_v1_to_v2(con):
    """Widen a pre-provenance results table, or leave it untouched.

    The old rows are renamed aside and copied into the wider table with a null
    fingerprint and null definition: their provenance is genuinely unknown,
    and inventing one would be the very attribution this schema removes.

    Only the four columns this runner knows a pre-provenance table to hold are
    copied, and the original is then dropped, so a table carrying any other
    column would have that column destroyed with no copy of it left anywhere.
    The actual schema is therefore read first and required to be exactly the
    expected one. A table that does not match refuses the run instead, before
    the rename, so nothing is renamed, copied or dropped and no row and no
    column is lost. Refusing is the conservative half of the same rule the rest
    of this module follows: what cannot be shown to mean what the runner would
    read into it is not migrated.

    The whole sequence runs inside an explicit transaction because sqlite3
    autocommits DDL outside one, and a half-migrated database is worse than an
    unmigrated one: it carries a fingerprint column, so the next run would
    read it as current and never see the rows still sitting in results_v1.
    The explicit BEGIN is what makes SQLite's transactional DDL apply, so any
    failure, including an interrupt that never reaches an except clause,
    leaves the original table as it was.
    """
    columns = [row[1] for row in con.execute("PRAGMA table_info(results)")]
    if set(columns) != _LEGACY_RESULT_COLUMNS:
        unknown = sorted(set(columns) - _LEGACY_RESULT_COLUMNS)
        missing = sorted(_LEGACY_RESULT_COLUMNS - set(columns))
        raise MatrixIdentityError(
            "results db predates provenance tracking but its results table is "
            f"not the one this runner knows how to migrate (columns {columns!r}"
            + (f"; unexpected {unknown!r}" if unknown else "")
            + (f"; missing {missing!r}" if missing else "")
            + "). Migrating copies only the expected columns and drops the "
            "original, so an unexpected one would be destroyed with no copy of "
            "it kept; nothing has been migrated and the table is exactly as it "
            "was")
    con.execute("BEGIN")
    try:
        con.execute("ALTER TABLE results RENAME TO results_v1")
        _create_results(con)
        con.execute(
            f"INSERT INTO results({_RESULT_COLUMN_LIST}) "
            "SELECT ?, cell_id, NULL, NULL, status, result_json, artifact_dir "
            "FROM results_v1", (_LEGACY_EXPERIMENT,))
        con.execute("DROP TABLE results_v1")
    except Exception as exc:
        con.rollback()
        raise MatrixIdentityError(
            "results db predates provenance tracking and could not be migrated; "
            f"its results table has been left exactly as it was: {exc!r}") from exc
    con.commit()


def _ensure_schema(con):
    stored_version = _stored_version(con)
    # Checked before any of the migration or DDL below, all of which either
    # autocommits or writes rows a rollback cannot undo: a foreign attempts
    # table must be refused before anything else in this database changes,
    # or "Nothing has been changed" below would be false.
    attempts_schema = con.execute("PRAGMA table_info(attempts)").fetchall()
    if attempts_schema:
        attempts_columns = frozenset(row[1] for row in attempts_schema)
        if attempts_columns != _ATTEMPTS_COLUMNS:
            unknown = sorted(attempts_columns - _ATTEMPTS_COLUMNS)
            missing = sorted(_ATTEMPTS_COLUMNS - attempts_columns)
            raise MatrixIdentityError(
                f"results db already has a table named 'attempts' with columns "
                f"{sorted(attempts_columns)!r}, not the ones this runner writes "
                f"({sorted(_ATTEMPTS_COLUMNS)!r})"
                + (f"; unexpected {unknown!r}" if unknown else "")
                + (f"; missing {missing!r}" if missing else "")
                + "; refusing to record attempt provenance into a table it "
                "does not recognise. Nothing has been changed")
        # Column names alone would accept a table where attempt_id shares its
        # primary key with another column (or carries no uniqueness
        # constraint at all): either way a colliding INSERT would land a
        # second row silently instead of being refused, defeating the whole
        # point of minting a fresh token per attempt. ``pk`` is the column's
        # 1-based position within the primary key, 0 if it is not in it, so
        # this demands attempt_id be the *only* column in that key.
        pk_members = sorted((row[5], row[1]) for row in attempts_schema if row[5])
        if pk_members != [(1, "attempt_id")]:
            raise MatrixIdentityError(
                "results db already has a table named 'attempts' with the "
                "columns this runner writes, but 'attempt_id' alone is not "
                "its primary key; a duplicate attempt_id would then insert "
                "silently rather than being refused. Refusing to record "
                "attempt provenance into a table it does not recognise. "
                "Nothing has been changed")
    columns = [row[1] for row in con.execute("PRAGMA table_info(results)")]
    if not columns:
        _create_results(con)
    elif "fingerprint" not in columns:
        _migrate_v1_to_v2(con)
    # Both tables are created after the migration, so that a database this
    # runner refuses to migrate keeps the shape the old pyteman wrote rather
    # than gaining tables only the new one understands. DDL autocommits, so
    # creating either one earlier would outlive the rollback.
    con.execute("CREATE TABLE IF NOT EXISTS schema_meta(key TEXT PRIMARY KEY, value TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS results_superseded("
                "experiment TEXT, cell_id TEXT, fingerprint TEXT, cell_json TEXT, "
                "status TEXT, result_json TEXT, artifact_dir TEXT, "
                "reason TEXT, superseded_at REAL)")
    # One row per attempt, from the moment its name is minted rather than from
    # the moment it finishes. A row stuck at status='running' after a crash is
    # exactly that: incomplete, and left saying so. Nothing here infers "dead"
    # from it, and nothing sweeps it, because the only thing that knows what
    # happened to that process is the process, and it did not get to say.
    con.execute("CREATE TABLE IF NOT EXISTS attempts("
                "attempt_id TEXT PRIMARY KEY, experiment TEXT NOT NULL, "
                "cell_id TEXT NOT NULL, fingerprint TEXT NOT NULL, "
                "cell_json TEXT NOT NULL, artifact_dir TEXT NOT NULL, "
                "status TEXT NOT NULL, result_json TEXT, "
                "started_at REAL NOT NULL, finished_at REAL)")
    if stored_version != SCHEMA_VERSION:
        con.execute("INSERT OR REPLACE INTO schema_meta VALUES ('schema_version', ?)",
                    (str(SCHEMA_VERSION),))
    con.commit()


def _stored_version(con):
    """Refuse a database a newer pyteman wrote, rather than misreading it.

    Reading the version is what makes it load-bearing: a newer schema still
    has a fingerprint column, so column sniffing alone would conclude the db
    is current and then write rows that ignore whatever the newer version
    added.

    The table may legitimately be absent: it is created only once a migration
    has been allowed to proceed, so a database older than provenance tracking
    reaches this point without one and simply has no version to state.
    """
    if not list(con.execute("PRAGMA table_info(schema_meta)")):
        return None
    row = con.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()
    if row is None:
        return None
    try:
        version = int(row[0])
    except (TypeError, ValueError):
        raise MatrixIdentityError(
            f"results db carries an unreadable schema_version {row[0]!r}") from None
    if version > SCHEMA_VERSION:
        raise MatrixIdentityError(
            f"results db was written by a newer pyteman (schema v{version}; this "
            f"runner understands v{SCHEMA_VERSION}), so its rows cannot be shown "
            "to mean what this runner would read into them")
    return version


def _archive(con, experiment_key, cell_id, reason):
    """Copy a row into the archive server-side, so it never enters Python."""
    con.execute(
        f"INSERT INTO results_superseded({_RESULT_COLUMN_LIST}, reason, superseded_at) "
        f"SELECT {_RESULT_COLUMN_LIST}, ?, ? "
        "FROM results WHERE experiment=? AND cell_id=?",
        (reason, time.time(), experiment_key, cell_id))


def _finalise(con, step, experiment_key, attempt_id, adir, status, result_json,
              results_db):
    """Write this attempt's outcome, as one whole transaction or as none of it.

    Called at most twice for a single attempt: once with what the cell
    produced, and once more with a failure standing in for a payload sqlite
    refused for its size. It is a function so that the second call replays the
    entire transaction rather than the statement that happened to raise. The
    archive copy, the results write, the legacy delete and the attempt's
    finalisation are one fact about one attempt, so a retry redoing only the
    INSERT would commit a results row whose archive copy had been rolled back,
    which no reader could tell from a supersession that never happened.

    Nothing is rolled back on the sqlite path: the caller rolls back each
    refusal before it decides what that refusal was, so on this path the
    discarding stays on the caller's side of the boundary rather than half
    here and half there. The rowcount guard below is a different path and does
    roll back here, for the reason given there.
    """
    if step.archive is not None:
        # The copy of the row being superseded, written here rather than at
        # planning time and in the same transaction as the replacement. An
        # archive row states that a supersession happened, so it comes into
        # being exactly when the supersession does: an interrupt before this
        # point leaves the stored row live and unarchived, which is what
        # actually occurred, and a retry archives it once when it finally
        # succeeds rather than once per attempt. It comes before both writes
        # below because it reads the row they displace: the INSERT overwrites
        # it on the mismatch path, the DELETE removes it on the legacy one.
        _archive(con, step.source, step.cell.id, step.archive)
    con.execute(
        f"INSERT OR REPLACE INTO results({_RESULT_COLUMN_LIST}) "
        "VALUES (?,?,?,?,?,?,?)",
        (experiment_key, step.cell.id, step.cell.fingerprint,
         step.cell.definition, status, result_json, adir))
    if step.source != experiment_key:
        # The superseded legacy row lived in the unnamespaced stratum, so the
        # INSERT above did not replace it. Dropping it in the same transaction
        # as its replacement is what drains that stratum without ever leaving
        # the cell unrepresented. This guard is narrower than the archive's
        # above rather than independent of it: a source differing from the
        # run's own key can only have come from the legacy lookup, so a step
        # reaching here always carries an archive reason as well.
        con.execute("DELETE FROM results WHERE experiment=? AND cell_id=?",
                    (step.source, step.cell.id))
    # Finalising the attempt lives in the same transaction as the row it is
    # evidence for: the two are one fact, that this attempt produced this
    # outcome, and a rollback that kept one half would assert an outcome the
    # results table does not have, or a result the attempts table cannot
    # attribute to anything still running.
    cur = con.execute(
        "UPDATE attempts SET status=?, result_json=?, finished_at=? "
        "WHERE attempt_id=?", (status, result_json, time.time(), attempt_id))
    if cur.rowcount != 1:
        # The row this attempt started with is gone, so committing the results
        # write above would assert provenance for an attempt nothing now
        # attests. Same concurrent-writer guard as _adopt_stored_rows. Rolled
        # back here rather than left to the caller because this is not a
        # refusal a smaller payload could answer: no size of row brings back
        # the attempt it would have to be attributed to.
        #
        # The message names the status this write carried, not how the cell
        # ended: _finalise is not told that, and on the stand-in's call the
        # two differ.
        con.rollback()
        raise MatrixStorageError(
            f"cell {step.cell.id!r} ran, but the finalisation recording it "
            f"as {status!r} could not be applied: attempt {attempt_id!r} "
            f"vanished from {results_db!r} before that outcome could be "
            "written against it; nothing has been written for this cell")
    con.commit()


def _check_cell_ids(cells):
    """Ids must be strings usable as a single path component.

    The type check is the same concern as the fingerprint's: ``cell_id`` has
    TEXT affinity, so SQLite would store the id ``1`` as ``'1'`` and let the
    two address one row.

    The rest is the same concern one layer out. The id also names the
    attempt's artifact directory, so an id that is not a legal component is
    not a name but a fault: ``../..`` climbs out of ``artifact_root``, an
    absolute id discards it along with the experiment namespace, an over-long
    one exhausts the component limit, and an embedded NUL cannot reach the
    kernel at all. All four are refused here rather than at ``os.makedirs``,
    because that call happens inside the run loop: by then the earlier cells
    of the matrix have run and committed, and the refusal this pre-pass
    promises has already been broken.

    Both separators are refused on every platform, not only the local one.
    The db records the directory name and outlives the machine that wrote it,
    so an id that is one component here and two elsewhere would make the
    stored evidence pointer mean different things in different places.

    A drive specifier is refused for the same reason and on every platform
    too, though it carries no separator at all. ``ntpath.join`` treats a
    component that opens with a drive as a fresh start and returns it alone,
    discarding ``artifact_root``, so on a Windows host such an id would send
    the attempt wherever that drive currently points. The check has to sit
    here rather than under a platform test, because the id travels with the
    matrix definition and the refusal has to be the same wherever it is read.
    """
    for cell in cells:
        if "id" not in cell:
            raise MatrixIdentityError(
                f"cell {cell!r} has no 'id'; the id is what addresses the cell's "
                "row in the results db, so without one it cannot be resumed")
        cell_id = cell["id"]
        if not isinstance(cell_id, str):
            raise MatrixIdentityError(
                f"cell id {cell_id!r} is not a string; the results db would "
                f"store it as {str(cell_id)!r} and let the two share a row")
        if "/" in cell_id or "\\" in cell_id or "\x00" in cell_id:
            raise MatrixIdentityError(
                f"cell id {cell_id!r} is not a usable path component; the id names "
                "the attempt's artifact directory, so a separator would write "
                "outside artifact_root and outside its experiment's namespace, "
                "and a NUL cannot be given to the filesystem at all")
        drive, _ = ntpath.splitdrive(cell_id)
        if drive:
            raise MatrixIdentityError(
                f"cell id {cell_id!r} opens with the drive specifier {drive!r}; "
                "joining a drive-relative component discards artifact_root "
                "rather than appending to it, so on a Windows host the attempt "
                "would be written wherever that drive is currently pointed, "
                "outside the root and outside its experiment's namespace")
        size = len(cell_id.encode("utf-8"))
        if size > _MAX_ID_BYTES:
            raise MatrixIdentityError(
                f"cell id {cell_id[:40]!r}... is {size} bytes; the id names a "
                f"directory, so it has to stay within {_MAX_ID_BYTES} to leave the "
                "attempt suffix room inside the filesystem's component limit")


def _check_duplicate_ids(cells):
    """Ids must be distinct across the matrix, because they address rows.

    Set-wide, unlike the checks above, which judge one id on its own.
    """
    counts = collections.Counter(cell["id"] for cell in cells)
    duplicated = [cid for cid, n in counts.items() if n > 1]
    if duplicated:
        raise MatrixIdentityError(
            "duplicate cell ids in one matrix: " + ", ".join(repr(c) for c in duplicated)
            + "; ids address rows in the results db, so a repeated id would make "
              "the later definition report as a resume of the earlier one")


def _changed_keys(stored_json, cell):
    """Top-level fields that differ, so a mismatch says what changed.

    ``None`` when the stored text cannot be compared, which covers a row with
    no definition at all as much as one holding something other than a
    mapping: the caller falls back to naming the two fingerprints.
    """
    try:
        stored = json.loads(stored_json)
    except (TypeError, ValueError):
        return None
    if not isinstance(stored, dict):
        return None
    return [key for key in sorted(set(stored) | set(cell))
            if stored.get(key) != cell.get(key)]


def _lookup(con, experiment_key, cell_id, legacy_only=False):
    sql = ("SELECT fingerprint, cell_json, status FROM results "
           "WHERE experiment=? AND cell_id=?")
    if legacy_only:
        sql += " AND fingerprint IS NULL"
    return con.execute(sql, (experiment_key, cell_id)).fetchone()


def _plan(con, cells, experiment_key, on_mismatch, on_legacy):
    """Decide every cell's fate before any of them runs.

    Deciding up front keeps a refusal from landing halfway through a matrix,
    where some cells would already have been executed against a results db the
    runner is about to declare unusable.

    Two rules separate the gate from the archive. The gate (refusing) applies
    only to a stored ``done`` row, because only a completed row is evidence
    someone may be relying on. The archive applies to every row this run is
    about to overwrite but cannot claim as its own, whatever its status, so no
    historical row is destroyed without a record.
    """
    steps, conflicts = [], []
    for cell in cells:
        source = experiment_key
        row = _lookup(con, experiment_key, cell.id)
        if row is None and experiment_key != _LEGACY_EXPERIMENT:
            # Unnamespaced rows are visible from every experiment until a
            # policy resolves them; without this the migrated stratum could
            # never be reached again once callers adopted an identity.
            source = _LEGACY_EXPERIMENT
            row = _lookup(con, _LEGACY_EXPERIMENT, cell.id, legacy_only=True)
        if row is None:
            # No stored row, so nothing lives anywhere but where this run
            # writes: the source is this experiment, the same as for a row
            # already found under it.
            steps.append(_Step(cell, "run", None, experiment_key))
            continue

        stored_fingerprint, stored_cell, status = row
        if stored_fingerprint == cell.fingerprint:
            action = "skip" if status == "done" else "run"
            steps.append(_Step(cell, action, None, source))
            continue

        legacy = stored_fingerprint is None
        policy = on_legacy if legacy else on_mismatch
        if status == "done" and policy == "error":
            # The matrix is about to be refused, so no step recorded for this
            # cell could ever run.
            conflicts.append((_conflict(cell, stored_fingerprint, stored_cell, legacy),
                              legacy))
            continue
        if legacy and policy == "adopt" and status == "done":
            # Adoption asserts the stored evidence describes this definition.
            # A failed row is not evidence, so there is nothing to assert and
            # the cell is simply re-run. The step skips like any other cell
            # holding a usable result; what makes it an adoption is the
            # archive reason, which is also what _adopt_stored_rows reads.
            steps.append(_Step(cell, "skip", "adopted", source))
        else:
            steps.append(_Step(cell, "run", "legacy" if legacy else "mismatch", source))
    if conflicts:
        raise MatrixIdentityError(
            "results db does not match this matrix:\n  "
            + "\n  ".join(text for text, _ in conflicts)
            + "\n" + "\n".join(_remedies(conflicts)))
    return steps


def _remedies(conflicts):
    """What the caller can actually do, given which conflicts occurred.

    Opening a new ``experiment`` is only a way out of a mismatch. Legacy rows
    are unnamespaced and therefore visible from every experiment, so offering
    it while even one of them is in the refusal would send the caller round a
    loop that ends at this same refusal: the mismatches would clear and the
    legacy rows would meet them again under the new identity.
    """
    yield "re-run under on_mismatch/on_legacy='rerun' to supersede the stored rows"
    if any(legacy for _, legacy in conflicts):
        yield ("use on_legacy='adopt' to assert the stored rows do describe these "
               "definitions")
        yield ("a distinct experiment= identity will not clear this: rows predating "
               "provenance are unnamespaced and stay visible from every experiment")
    else:
        yield "or pass a distinct experiment= identity to open a new run"


def _conflict(cell, stored_fingerprint, stored_cell, legacy):
    if legacy:
        return (f"{cell.id!r}: stored result predates provenance tracking and "
                "cannot be shown to belong to this definition")
    changed = _changed_keys(stored_cell, json.loads(cell.definition))
    detail = (f"differs in {', '.join(changed)}" if changed else
              f"stored {stored_fingerprint[:12]}, current {cell.fingerprint[:12]}")
    return (f"{cell.id!r}: stored result was produced by a different "
            f"definition ({detail})")


def _adopt_stored_rows(con, steps, experiment_key):
    """Stamp every adopted row, beside its archived original, before anything runs.

    Only adoptions are resolved here, and each one's archive copy travels with
    its own UPDATE: an adoption is complete the moment it is taken, so there is
    no later step that could fail and leave the stamp attesting an attempt that
    never happened. One commit covers them all, rather than one fsync per cell.

    A row a cell is about to supersede is left entirely alone, archive
    included; that copy is written in the transaction that installs the
    replacement, for the reasons given at the ``_archive`` call there.
    """
    for step in steps:
        if step.archive != "adopted":
            continue
        _archive(con, step.source, step.cell.id, step.archive)
        cur = con.execute(
            "UPDATE results SET experiment=?, fingerprint=?, cell_json=? "
            "WHERE experiment=? AND cell_id=?",
            (experiment_key, step.cell.fingerprint, step.cell.definition,
             step.source, step.cell.id))
        if cur.rowcount != 1:
            # The row was planned against, so its disappearance means a
            # concurrent writer. Reporting "skipped" now would claim a
            # result that no longer exists.
            con.rollback()
            raise MatrixIdentityError(
                f"{step.cell.id!r}: the row being adopted changed underneath "
                "this run, so the adoption cannot be shown to have applied to "
                "the evidence it was planned against")
    con.commit()


def _cell_result(value):
    """What ``run_cell`` is allowed to hand back.

    A ``dict``, or ``None`` from a callback that has nothing to report and so
    never wrote a return statement. Everything else is refused rather than
    stored, because the rest of the system reads a result by key: a list or a
    number is not a thinner result but a different kind of object, and storing
    one buys a row no reader can interpret.

    ``dict`` rather than the wider ``Mapping`` on purpose, and narrower than
    what the row below could physically hold: ``json.dumps`` serialises lists,
    strings and scalars perfectly well, so this refuses values storage would
    have taken. The reason is the paragraph above, not serialisability. What
    the check does buy on that front is one class of confusing report: a
    ``MappingProxyType`` or a ``UserDict`` reads like a mapping at the call
    site but is rejected by ``json.dumps``, so a wider test would admit it here
    only for it to fail at serialisation, naming the same bug with a worse
    message.

    ``0``, ``False``, ``''`` and ``[]`` are refused on the same grounds, and
    they are the reason this function exists. Folded into an empty mapping, as
    a bare ``or {}`` folded them before, they recorded a cell that succeeded
    and reported nothing, which is exactly what a correct cell looks like. A
    callback that returned the wrong thing was therefore indistinguishable
    from one that worked.

    Keys must be strings, at every depth. That is the one rule here that is
    about the row rather than about the call: a coerced key made the returned
    mapping and the stored row disagree, and the row is what a reader has
    months later. Refusing rather than rewriting is the point, since rewriting
    the keys to match would perform the very coercion the rule exists to stop.
    A cyclic or unserialisably deep result is still reported by the serialiser
    rather than here, because the walk above survives both.
    """
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise MatrixResultError(
            "run_cell must return a dict of results, or None to report "
            f"nothing, but this cell returned {type(value).__name__}")
    # A result is read back by key, and ``json.dumps`` rewrites int, float,
    # bool and None keys as strings. Stored unchecked, the mapping handed back
    # to the caller and the row left behind disagree about what the keys are,
    # and the row is the half that outlives the run. The key is named but not
    # the string JSON would turn it into: that string is 'true' for ``True``
    # and 'null' for ``None``, not ``str(key)``, and a message that guessed it
    # would send the caller looking for a key that is not there.
    for key in _coerced_keys(value):
        raise MatrixResultError(
            f"run_cell returned the non-string mapping key {key!r} of type "
            f"{type(key).__name__}; JSON stores every key as a string, so the "
            "returned result and the stored row would disagree about this "
            "key. Give it as a string")
    return value


def run_matrix(cells, run_cell, results_db, artifact_root, *, experiment,
               on_mismatch="error", on_legacy="error"):
    """Run every cell once, persisting each outcome to the results db.

    Returned status reflects execution outcome: done, failed (run_cell
    raised) or skipped (a previous run already recorded done for this same
    cell definition). The results db is the durable record; failed cells
    re-run on the next invocation.

    A cell is skipped only when the stored row carries the fingerprint of the
    definition being run, under the same ``experiment`` identity, so a changed
    cell never inherits the evidence of the old one. ``experiment`` is
    required because the runner cannot see what lies outside the cells: pass
    the ruleset hash, workload revision and harness version that the run
    depends on, so changing one of them opens a new run instead of silently
    resuming the old one. Pass ``None`` to state deliberately that this matrix
    has no identity beyond its cells. Such a run writes into the same
    unnamespaced stratum the migration uses, but its rows carry a fingerprint,
    and that is what keeps the two apart: a named experiment reaches into the
    stratum only for rows without one, so it can never resume a ``None`` run's
    result. The reverse does not hold. A ``None`` run meets migrated rows on
    its ordinary lookup and resolves them through ``on_legacy`` like any other
    caller, and since one cell id holds one row per experiment, a ``None``
    result and a migrated row for that id cannot both exist.

    ``on_mismatch`` governs a stored row from a different definition and
    ``on_legacy`` a row written before provenance was tracked. Both default to
    ``error``: nothing recorded as done is superseded unless a policy says so.
    ``rerun`` runs again and copies the stored row into
    ``results_superseded`` in the transaction that installs the replacement,
    so a run interrupted before that point supersedes nothing and leaves no
    record saying it did; ``on_legacy='adopt'`` instead stamps the stored row
    with the current definition, asserting it does describe this cell, and
    archives the unstamped original so the assertion stays distinguishable
    from a measurement. ``adopt`` stamps only a stored row whose status is
    ``done``, because adoption asserts that stored evidence describes this
    definition. A legacy row recorded as ``failed`` is not evidence, so there
    is nothing to assert about it and the cell is re-run like any other, which
    is also what it does under the default ``error``.

    Both non-error legacy policies consume the unnamespaced row rather than
    leaving it where it was: ``rerun`` deletes it in the transaction that
    installs the replacement, and ``adopt`` re-stamps it with this run's
    experiment. Either way that cell holds nothing in the unnamespaced stratum
    afterwards, so a later experiment meeting the same cell id finds no legacy
    row to resolve and runs it as new. The first run to apply a non-error
    policy therefore settles that row on behalf of every experiment, and what
    it settled stays readable: the original is copied into
    ``results_superseded`` before either policy touches it.

    Each attempt writes its artifacts to a directory of its own, named
    ``<artifact_root>/exp-<experiment digest>/<cell_id>.<fingerprint prefix>.<attempt token>``.
    Artifacts are the evidence a row points at, so no two attempts ever share
    them: not two experiments running one cell id, not a definition that comes
    back round after being superseded, and not a later run that follows a
    cleanup of ``artifact_root``, since the name is minted rather than read
    off the tree. An adopted row and the archived original it was stamped from
    do point at one directory, because they are two records of a single
    attempt rather than two attempts.

    Before an attempt's directory is created, and before ``run_cell`` is
    called, a row for it is written to ``attempts`` and committed: its token,
    the cell and experiment it belongs to, the directory it is about to claim,
    and a status of ``running``. A process killed at any point after that
    leaves this row exactly as it was, because nothing later in the attempt
    has run to change it. That is not this row being wrong; a status of
    ``running`` that outlives its process is what an interrupted attempt looks
    like, and nothing in this module infers a cause for one, sweeps it, or
    turns it into anything else. Retrying the cell mints a fresh token and a
    fresh row, so a killed attempt's row is not overwritten, reused, or
    required to be resolved before its cell can run again.

    Creating the directory itself can still fail, most plausibly a token
    collision, though ``uuid4`` makes that vanishingly unlikely. Unlike a
    killed process, this failure is caught in the same run that produced it,
    so it is recorded like any other cell failure: as a ``failed`` row against
    the very attempt that could not get its directory, rather than left
    unresolved or allowed to end the matrix.

    ``run_cell`` is handed the frozen definition, decoded from the canonical
    text its fingerprint attests, rather than the caller's own object. What it
    does to that object cannot change what this run records, nor what the other
    cells of the matrix are run as.

    It returns a mapping of results, or ``None`` if it has nothing to report.
    Anything else is that cell's own failure, recorded as a ``failed`` row
    carrying the reason and leaving the rest of the matrix to run; so is a
    mapping that will not serialise. Writing the row down is not: a db that
    refuses it raises ``MatrixStorageError`` and stops the run, because the
    alternative is to carry on producing evidence that is not being kept. The
    same transaction that writes ``results`` also stamps the attempt's row
    with its outcome; a storage failure rolls both back together, leaving the
    attempt at ``running`` rather than asserting a result that was never kept.

    That boundary is drawn at the write, not at the blame, with one exception.
    A result that serialises but is too large for sqlite to store, which the
    row refuses with ``SQLITE_TOOBIG`` past a default of a gigabyte, is the
    cell's own doing and is charged to it: the whole finalisation is replayed
    once with a fixed stand-in outcome recorded as a ``failed`` row, and the
    cells queued behind it still run. The size that matters is the size of
    every row the finalisation writes, the attempt's row included, which is
    wider than the results row for the same outcome. A ``failed`` row is not a
    completion, so the cell is planned again on the next invocation. If the
    stand-in is refused too, nothing is written and ``MatrixStorageError`` is
    raised as above.

    Rows migrated from a pre-provenance database are unnamespaced and stay
    visible from every ``experiment`` until one of those policies resolves
    them.

    Runs on one results db are exclusive. The run holds an advisory lock on
    ``<results_db>.lock`` from before it touches the tree or the db until it
    returns, and a second runner meeting a held lock raises
    ``MatrixLockError`` immediately rather than waiting: how long another
    matrix will take is not something this one can guess. So this function can
    now refuse to run, which is the one change to its contract.

    Everything this run reads or changes on the filesystem, in the db, and
    through the callback happens while the lock is held. The one thing that
    does not is what taking the lock itself needs: the lock file, and the
    directory it goes in, which is the directory the results db goes in. The
    argument checks above are pure, so they precede the lock and a run refused
    by one of them touches nothing at all.

    So a run that fails once the lock is taken, including one that fails on its
    artifact root, may leave behind the lock file and that directory. May,
    rather than does: a directory that was already there is left as it was, and
    a lock file from an earlier run is reused rather than replaced. That is the
    whole of what a failed run can leave that it could not leave before the
    lock existed. The ordering is deliberate, because a check made outside
    exclusion is made against a tree another runner is free to be changing.

    The lock is released by the kernel, so a runner killed outright leaves
    nothing to clear away and the next run acquires it. The one exception is a
    ``run_cell`` that forks a child which outlives the run, since the child
    inherits the descriptor the lock belongs to and keeps holding it; a child
    that is exec'd does not, because the descriptor is not inheritable.

    The lock is keyed on the canonical path, so a relative path, an absolute
    one and a symlink to one db all contend. Two hard links to it do not: they
    are separate paths that resolve to themselves, and this does not detect
    that they are one file. The lock is advisory, which binds every runner that
    comes through here and nothing that writes to the db by itself. Verified on
    Linux on a local filesystem; macOS is unverified, flock over NFS is outside
    any guarantee, and a platform with no ``fcntl`` is refused rather than run
    unprotected. ``results_db`` must name a file: ``":memory:"`` and ``""`` are
    refused because sqlite gives each connection its own such database, which
    the next run cannot resume from.
    """
    if on_mismatch not in _MISMATCH_POLICIES:
        raise ValueError(f"on_mismatch must be one of {_MISMATCH_POLICIES}, got {on_mismatch!r}")
    if on_legacy not in _LEGACY_POLICIES:
        raise ValueError(f"on_legacy must be one of {_LEGACY_POLICIES}, got {on_legacy!r}")

    cells = list(cells)
    _check_cell_ids(cells)
    _check_duplicate_ids(cells)
    experiment_key = _experiment_key(experiment)
    cells = [_freeze(cell) for cell in cells]

    # Both paths are resolved against the cwd of the run that created them,
    # not of whoever reads the db later. The artifact directory is recorded in
    # every row as the pointer to that attempt's evidence, so a relative one
    # would resolve somewhere else, or nowhere, the moment it is followed from
    # another directory.
    artifact_root = os.path.abspath(artifact_root)
    # Held from before this run reads or changes anything outside its own
    # arguments until it returns. A runner that is refused has migrated no
    # schema, planned nothing, created no experiment directory and run no cell.
    # What it can leave behind is the lock file and the directory holding it,
    # including when the run goes on to fail on its artifact root: that check
    # reads the filesystem, so it belongs under the lock, and the file taking
    # the lock needs is created by taking it.
    with _lock.held(results_db):
        # Before the db exists, so that a root that cannot hold this
        # experiment's attempts fails the run outright instead of leaving a db
        # whose rows point at directories outside it.
        experiment_dir = _prepare_experiment_dir(artifact_root, experiment_key)
        con = sqlite3.connect(results_db)
        try:
            _ensure_schema(con)
            steps = _plan(con, cells, experiment_key, on_mismatch, on_legacy)
            _adopt_stored_rows(con, steps, experiment_key)

            out = []
            for step in steps:
                if step.action == "skip":
                    out.append({"cell_id": step.cell.id, "status": "skipped"})
                    continue
                try:
                    attempt_id, adir = _begin_attempt(
                        con, experiment_dir, experiment_key, step.cell)
                except sqlite3.Error as e:
                    # The same narrowing and the same rollback-then-raise as the
                    # finish transaction below, and for the same reason: nothing
                    # about this cell can be trusted to have happened once its
                    # own row failed to record it. Unlike that later failure,
                    # nothing has run yet and no directory exists, so there is
                    # no artifact path to point the message at.
                    con.rollback()
                    raise MatrixStorageError(
                        f"cell {step.cell.id!r} could not be recorded as a "
                        f"starting attempt in {results_db!r}: {e}. Nothing has "
                        "run for it yet, and nothing on disk names anything "
                        "that has") from e
                try:
                    os.makedirs(adir)
                except OSError as e:
                    # The row above is already committed and already names this
                    # directory, so there is nowhere else for this outcome to
                    # go: it is recorded exactly like a callback's own failure,
                    # against the same attempt_id, rather than left to make the
                    # whole matrix stop. Unlike a killed process, this is not an
                    # inferred cause: the exception was caught right here, in
                    # this run, so there is nothing speculative about it.
                    result = {"error": f"attempt directory could not be "
                                        f"created: {e!r}"}
                    status = "failed"
                else:
                    try:
                        # Decoded fresh from the frozen text, so that whatever the
                        # callback does to what it is handed, the definition stored
                        # beside the result stays the one the fingerprint attests.
                        result = _cell_result(
                            run_cell(json.loads(step.cell.definition), adir))
                        status = "done"
                    except Exception as e:
                        result = {"error": repr(e)}
                        status = "failed"
                try:
                    result_json = json.dumps(result)
                except Exception as e:
                    # A result that cannot be stored is this cell's failure, not
                    # the matrix's. Serialised at the insert instead, it would
                    # abort the run from outside the guard above, losing the
                    # outcome of the cell that just ran and leaving its artifacts
                    # with no row of any kind pointing at them. Every exception is
                    # caught for the same reason: a self-referential result raises
                    # ValueError but a deeply nested one raises RecursionError,
                    # and which of the two a callback happens to return is no
                    # reason for one to cost the matrix and the other one cell.
                    result = {"error": f"result is not JSON-serialisable: {e!r}"}
                    result_json = json.dumps(result)
                    status = "failed"
                try:
                    _finalise(con, step, experiment_key, attempt_id, adir,
                              status, result_json, results_db)
                except sqlite3.Error as e:
                    # Rolled back first, as _migrate_v1_to_v2 and
                    # _adopt_stored_rows do before their own failed writes. The
                    # close() below would discard the pending archive row anyway,
                    # but only as a side effect of an implicit property of close;
                    # saying it here is what keeps a row asserting a supersession
                    # that never happened from becoming live the day this
                    # connection outlives the call.
                    con.rollback()
                    # Recognised by error code, not by exception class and not
                    # by message. The class is CPython's projection of sqlite's
                    # result code onto the DB-API hierarchy, several codes
                    # share one class, and which code maps where is CPython's
                    # to change; the message is sqlite's own wording and is not
                    # fixed by anything here. The code is the part that names
                    # the refusal and stays put. Read with getattr because the
                    # attribute is set only on errors that came back from
                    # sqlite: the ones the sqlite3 module raises before
                    # reaching it carry none, and reading the attribute off
                    # those directly would replace the storage failure below
                    # with an AttributeError.
                    if getattr(e, "sqlite_errorcode", None) != sqlite3.SQLITE_TOOBIG:
                        # Deliberately not recorded as this cell's failure:
                        # recording is the thing that just failed, so a "failed"
                        # row is exactly what cannot be believed here. The run
                        # stops instead of going on to spend later cells writing
                        # into the same hole, and the message carries what a
                        # caller needs to find the evidence that does exist,
                        # which is the attempt directory. Narrowed to
                        # sqlite3.Error so a failure that is not sqlite's at all
                        # surfaces as itself. That narrowing does not separate a
                        # disk problem from a mistake in the statements above: a
                        # wrong binding count and a parameter sqlite3 cannot
                        # adapt are both sqlite3.ProgrammingError, itself a
                        # sqlite3.Error subclass, so either would be reported
                        # here as a row that could not be written. The wrapped
                        # exception is in the message because that is what tells
                        # the two apart.
                        #
                        # attempt_id's row exists and already names adir: it was
                        # inserted and committed by _begin_attempt before this
                        # cell ran at all. What failed just now is the UPDATE
                        # that would have finalised it, so the row is left at
                        # status='running', same as a killed process leaves it,
                        # rather than at "no row points at this directory".
                        raise MatrixStorageError(
                            f"cell {step.cell.id!r} ran and finished {status}, but that "
                            f"outcome could not be written to {results_db!r}: {e}. "
                            f"Attempt {attempt_id!r} still names {adir!r} and is left "
                            "at status='running', unfinalised rather than asserting a "
                            "result that was never saved"
                        ) from e
                    # SQLITE_TOOBIG says the row was refused for what it holds,
                    # which is the one storage failure that leaves the
                    # database's health out of the question, so it is the one
                    # this cell can be charged with.
                    #
                    # What is replaced is the whole outcome, not a field. The
                    # oversized value could be the result, the callback's own
                    # error text, or the definition travelling in cell_json, and
                    # this code has not measured which: the message says an
                    # outcome was too large to record and stops there rather
                    # than naming a column it has not proved.
                    status = "failed"
                    result = dict(_OVERSIZED_OUTCOME)
                    result_json = _OVERSIZED_OUTCOME_JSON
                    try:
                        _finalise(con, step, experiment_key, attempt_id, adir,
                                  status, result_json, results_db)
                    except sqlite3.Error as retry_error:
                        # One attempt, and its success is the only thing that
                        # authorises the run to go on. What refused the
                        # stand-in is read by error code, the same way and
                        # with the same getattr as the first refusal above:
                        # the first write being refused for its size is no
                        # evidence about what stopped the second, and a
                        # competing writer or a constraint answers to
                        # something other than a smaller row. Neither branch
                        # goes further than the code it read, and the second
                        # covers the case where there is none to read: an
                        # error the sqlite3 module raised before reaching
                        # sqlite carries no code, and a refusal for size is
                        # one only sqlite issues, so the size wording is
                        # withheld there rather than guessed at. Which column
                        # carries the excess, and whether some smaller row
                        # would be accepted, are not measured here and are
                        # not guessed at either. Reported rather than papered
                        # over: a fabricated failure row here would claim the
                        # cell was recorded when nothing about it was.
                        con.rollback()
                        if getattr(retry_error, "sqlite_errorcode",
                                   None) == sqlite3.SQLITE_TOOBIG:
                            refusal_clause = "for its size as well"
                        else:
                            refusal_clause = "for something other than its size"
                        raise MatrixStorageError(
                            f"cell {step.cell.id!r} ran and finished, but the "
                            f"row was refused by {results_db!r} for its size, "
                            "and the finalisation standing in for it, "
                            "carrying a fixed short outcome in place of the "
                            f"original, was refused {refusal_clause}: "
                            f"{retry_error}. Neither finalisation was "
                            f"committed. Attempt {attempt_id!r} still names "
                            f"{adir!r} and is left at status='running'"
                        ) from retry_error
                out.append({"cell_id": step.cell.id, "status": status,
                            "result": result})
            return out
        finally:
            con.close()
