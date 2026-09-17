import json
import sqlite3
import string

# Built once and applied with str.translate, which walks the value a single
# time and leaves every character not named here alone. The mapping is the
# whole escape: ASCII punctuation becomes itself behind a backslash, and the
# two line endings become the Unicode control pictures that stand for them.
# _text explains why each half is shaped the way it is.
_ESCAPES = {ord(c): "\\" + c for c in string.punctuation}
_ESCAPES[ord("\n")] = "␊"
_ESCAPES[ord("\r")] = "␍"

# Two very different rows read back as the empty experiment, and the fingerprint
# is what separates them. A row written with experiment=None carries one: the
# caller stated that this matrix has no identity beyond its cells. A row
# migrated from a database older than provenance tracking carries none, and what
# produced it is genuinely unknown. One label for both would print the second
# claim over the first.
_NO_EXPERIMENT = "(no experiment)"
_PRE_PROVENANCE = "(pre-provenance)"


class MatrixReportError(RuntimeError):
    """The database handed to the report is not one it can report on.

    The report is the step where a wrong path is most likely to surface,
    because it is the step a person runs by hand, and sqlite hides that
    mistake better than most: it opens any name it is given and invents an
    empty file for the ones that do not exist. Raised so the failure names the
    file and says what was wrong with it, rather than arriving as a bare
    ``no such table: results`` from three frames down.
    """


def _read(results_db):
    try:
        con = sqlite3.connect(results_db)
    except sqlite3.Error as e:
        # Broader than the DatabaseError below, and deliberately so: at open
        # time every sqlite failure means the same thing to a caller, that this
        # name could not be opened. Reached by a path whose directory does not
        # exist, one that is a directory, and one that cannot be read. sqlite is
        # lazy about parsing the header, not about the open itself, so a file
        # that is not a database gets past here and fails in the PRAGMA.
        raise MatrixReportError(
            f"{results_db!r} could not be opened as a results database: {e}") from e
    try:
        columns = {row[1] for row in con.execute("PRAGMA table_info(results)")}
        if not columns:
            # An empty set means there is no such table, not a table with no
            # columns: sqlite cannot hold the latter. Caught here rather than
            # left to the query below, which would report a missing table for
            # what is nearly always a mistyped path or a database belonging to
            # something else.
            raise MatrixReportError(
                f"{results_db!r} has no 'results' table, so there is nothing to "
                "report. Check the path: run_matrix writes the table, and "
                "sqlite creates an empty database for any name it is handed")
        if not {"experiment", "fingerprint"} <= columns:
            # Older than provenance tracking: no experiment and no fingerprint
            # to read, which is itself what the row has to say for itself.
            #
            # The shape is sniffed rather than read off schema_meta, so this
            # renders any results table, including ones written by something
            # other than this runner. Both columns are required because both
            # are selected below: a half-migrated table would otherwise pass
            # the check and fail in the query.
            return [(None, None) + row for row in con.execute(
                "SELECT cell_id, status, result_json FROM results ORDER BY cell_id")]
        return con.execute(
            "SELECT experiment, fingerprint, cell_id, status, result_json FROM results "
            "ORDER BY experiment, cell_id").fetchall()
    except sqlite3.DatabaseError as e:
        # Catches the file that is not a database at all, where even the
        # PRAGMA above fails, and any table named 'results' whose columns
        # cannot be selected the way this reader selects them. Narrower than
        # the sqlite3.Error above: here a mistake in these lines would be an
        # InterfaceError, and that should surface as itself rather than be
        # reported to the caller as a problem with their file.
        raise MatrixReportError(
            f"{results_db!r} could not be read as a results database: {e}") from e
    finally:
        con.close()

def _experiment_label(experiment, fingerprint):
    if experiment:
        return experiment
    # ``is None``, not falsiness, and the same test the runner itself uses to
    # tell a migrated row from a written one. A fingerprint the runner did not
    # produce is still a fingerprint: it says a run claimed this row, which is
    # the opposite of the gap _PRE_PROVENANCE reports.
    return _PRE_PROVENANCE if fingerprint is None else _NO_EXPERIMENT

def _text(value):
    """Render a stored value as literal text in a table cell.

    Every column goes through this, including the status: the report renders
    databases this runner did not write, so no column is guaranteed to hold
    what this runner would have put there. A cell holds result data, and result
    data is not markup. The characters a report shows are therefore the
    characters the database holds, rather than whatever markdown would have
    made of them.

    Two separate jobs, and the second is the one that is easy to forget. The
    structural job keeps a value inside its own row and its own cell, which a
    pipe or a newline would otherwise break. The literal job keeps a value from
    being *interpreted*: without it ``*x*`` arrives emphasised, ``` `x` ```
    arrives as code, ``[a](u)`` arrives as a link, and ``<script>`` arrives as
    a script element rather than as the seven characters someone stored.
    Measured through pandoc before this was written: the structural escape
    alone left ten of the thirty sample values rendering as active elements.

    Every ASCII punctuation character is backslashed, which is the one rule
    that needs no per-character judgment, because CommonMark gives a backslash
    before ASCII punctuation the literal character and gives it no meaning
    anywhere else. That covers the pipe as a special case rather than as an
    exception: ``\\|`` is both what stops the table splitting the row and what
    renders a literal pipe. The set is not a wide guess at what is dangerous:
    ``string.punctuation`` is character for character the ASCII punctuation
    CommonMark names, so escaping all of it escapes exactly the domain the
    rule is defined over. Narrowing it to the characters that look dangerous
    today would trade that for per-character judgment, and a character missed
    by such a judgment is a value that lies about itself.

    The line endings cannot be rescued by a backslash, because a cell is one
    line by construction, so they become the Unicode control pictures for them.
    That is what keeps a stored ``\\n`` (two characters) and a stored newline
    apart, which the experiment column exists to rely on: escaping the newline
    as a backslash and an ``n`` instead would render both as ``\\n`` and lose
    the distinction at exactly the point a reader is looking for it.

    The literal half is stated against CommonMark and the GFM tables built on
    it, which is what this report is written for. A renderer outside that family
    honours its own, narrower set of escapes: measured against python-markdown
    3.10.3, nothing rendered as an active element and no two distinct values
    collapsed, but eight of thirty values arrived carrying a visible backslash
    where that renderer does not recognise the escape. So the safety half holds
    on both renderers measured, and exact text is a CommonMark promise.

    The database is not touched. This is a rendering escape, and the stored
    value stays whatever the run put there.

    What remains outside the promise is narrow and measured, not assumed. Two
    values that differ only in whitespace still arrive alike, because markdown
    strips and collapses spaces inside a cell and no escape reaches that;
    TASK-68 holds it. A stored U+240A or U+240D renders the same as a real
    newline or carriage return, which is the one collision this scheme keeps.
    It is not worth removing: escaping the control picture only moves the
    collision onto a stored backslash followed by a real newline, and closing
    it properly needs a doubling scheme that would cost every report its
    readability. And the promise is made about characters, not about glyphs: a
    bidi format control such as U+202E travels the escape untouched and
    reorders what a reader sees without altering a character of what is there,
    so a signature holding one can display as text it does not contain. TASK-76
    holds that, because closing it is a change of behaviour rather than of
    wording. tests/test_report_escaping.py pins all of it, the limits included,
    so a change of behaviour has to be a change of contract too.
    """
    return str(value).translate(_ESCAPES)

def matrix_markdown(results_db, out_path):
    """Render the results table, one row per (experiment, cell).

    The experiment is part of the row's identity, not decoration: cell ids are
    unique only within an experiment, so a table keyed on the id alone shows
    two runs of one cell as two rows that cannot be told apart.
    """
    rows = _read(results_db)
    lines = ["| experiment | cell | status | signature |", "|---|---|---|---|"]
    for experiment, fingerprint, cid, status, rj in rows:
        # Two different faults used to print as the same "?". A results_json
        # can fail to be JSON at all, or be JSON that is not a mapping, and
        # the remedy differs, so the cell says which. Both are reachable only
        # from a database this runner did not write: its own contract refuses
        # either before it can reach a row.
        #
        # TypeError is caught alongside ValueError because a foreign table need
        # not declare result_json as TEXT. Through a TEXT column sqlite's
        # affinity turns a stored 42 back into '42', which parses; through a
        # column declared INTEGER or not declared at all the integer survives
        # intact, and json.loads raises TypeError rather than ValueError on it.
        #
        # ``is None`` rather than falsiness, and for the reason this whole run
        # exists. NULL is the one value that means nothing was recorded, so it
        # is the one that earns the empty default. Testing truthiness instead
        # swept 0, 0.0, False, b'' and '' into that same default and rendered
        # them as a blank signature, indistinguishable from a cell that ran and
        # reported nothing, while 42 in the very same column was labelled
        # unreadable. That is the falsy fold the runner's own contract removed,
        # surviving on the read side where a foreign row can still carry it.
        try:
            r = json.loads("{}" if rj is None else rj)
        except (TypeError, ValueError):
            sig = "(unreadable result)"
        else:
            sig = (r.get("signature", r.get("error", "")) if isinstance(r, dict)
                   else "(result is not a mapping)")
        lines.append(f"| {_text(_experiment_label(experiment, fingerprint))} | "
                     f"{_text(cid)} | {_text(status)} | {_text(sig)} |")
    # Not the locale's encoding. The control pictures are the only characters
    # this report manufactures that are not ASCII, and it manufactures them
    # from a stored line ending, which is. Left to the locale, a results db
    # holding nothing more unusual than a newline produced a report that would
    # not write at all under, say, latin-1, and the escape added in this task
    # is what put that within reach of ordinary ASCII data.
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
