# src/pyteman/sqlitekit/integrity.py
"""Read captured ``PRAGMA integrity_check`` output into an explicit verdict.

What this parses is not simply "the output of integrity_check", because the
failures that matter most never arrive as output at all. Measured against
SQLite 3.51.2 and 3.53.4: a file that is not a database, a schema that will not
parse, and a file truncated below its page count all make the PRAGMA *raise*,
so through Python they reach a caller as the message of a ``DatabaseError``,
and through the ``sqlite3`` shell they go to stderr with an empty stdout. The
exit status is not the reliable half of that: measured on shell 3.53.4, a file
of random bytes reports ``file is not a database`` and exits 1, while a file of
ASCII text is read as a SQL script instead and exits 0, both with nothing on
stdout. Only a database that opens and parses produces rows to read.

So the input is whatever the caller managed to capture, from whichever channel
it arrived on, and the empty string is a real and common value: it is precisely
what a caller that redirects stdout gets from a destroyed file. That is the
distinction this module exists to keep. An empty capture says the attempt
produced nothing, ``ok`` says the check passed, and an unfamiliar line says
only that the text was not read. That last one stops there on purpose. The
error channel also carries messages from databases that are perfectly healthy:
the PRAGMA raises ``OperationalError('database is locked')`` when another
connection holds an EXCLUSIVE lock, and ``OperationalError`` is a
``DatabaseError``, so it arrives by the same route as ``file is not a
database``. Folding any of these into the others reports a healthy database to
someone whose data is gone, or a disaster to someone who has none.

The verdict is a mapping of five keys: ``status``, ``classes``,
``unclassified``, ``diagnosis`` and ``raw``. docs/integrity.md states that
schema; what belongs here is the obligation it places on this code.
``unclassified`` holds every finding line that no signature matched, in the
order SQLite printed them, and it is never discarded and never summarised
away, because a line this parser cannot read is still evidence and the next
person to look at an incident needs it more than this one did. Those lines are
normalised rather than reproduced: every line is stripped of surrounding
whitespace before classification, so what is kept is the finding and not the
layout it arrived in. ``raw`` is the integral copy, and it comes back untouched
whatever the verdict.

``raw`` keeps the meaning and the type it has always had. ``classes`` keeps its
type and loses a member: ``CLEAN`` used to appear in it and now lives in
``status``, because a list of damage signatures that also carried the absence of
damage made the empty list mean two opposite things. The other three keys are
additions. Which signatures the classifier produces is a separate question from
the shape of this mapping, and TASK-24 changes the first without touching the
second.

One naming caveat lives in docs/integrity.md rather than being restated here:
the ``CANONICAL_*`` names are specific to the original incident rather than a
general taxonomy. The other caveat this docstring used to carry is gone,
because the thing it warned about is gone. ``FTS_CORRUPTION`` replaces a
criterion that read a name: it fired when no other signature matched and every
finding line contained ``_fts``, which is a string a user chooses. Measured on
SQLite 3.51.2, that was wrong in both directions at once. An ordinary
expression index called ``idx_fts`` prints ``row 1 missing from index idx_fts``
and was reported as FTS damage, and so was ``unable to validate the inverted
index for FTS5 table main.messages_fts``, a message whose whole content is that
the check could not run. Meanwhile a database carrying real FTS5 corruption
next to an ordinary damaged index never fired it at all, because another
signature had matched first, so the one line SQLite's own FTS code wrote came
back as a line nobody read.

So what SQLite calls FTS is now read from what SQLite wrote. Having been
written by the FTS module is necessary and not sufficient. The ``fts5:`` prefix
is not a needle by itself, because the same prefix carries syntax errors from
ordinary queries, and a message that reports a fault is not enough either,
because some of them do not establish that there is one.

Reading what SQLite wrote also means reading it WHERE SQLite wrote it, and that
is the second half of the same rule rather than a separate precaution. SQLite
interpolates user-chosen object names into its findings, so every finding line
contains a region where arbitrary text arrives, and a needle looked for
anywhere in the line is eventually found in one. That is the criterion above
making the same mistake in a new place: a name is read as evidence again, only
this time the name is a whole FTS message instead of a substring of one. So the
FTS needles are matched at the START of the message. A genuine FTS diagnostic is
a complete message and begins one; an object name is never the first thing on a
line SQLITE EMITTED. That last qualification is exact and was learned the hard
way: this module splits the capture itself, so a boundary it invents is one the
user controls, and the anchor is only as trustworthy as the split. See
classify_integrity, which splits on ``\\n`` alone for that reason.
``classify_integrity_rows`` closes the last case by reading PRAGMA rows
individually, so a name holding a real ``\\n`` stays inside its own row; the
text-based function cannot distinguish it from a row boundary and never will.
The measurement behind all of this lives in docs/integrity.md rather than being
restated here, and so does the live reproduction it now runs from.

The canonical needles keep matching anywhere, and the reason is a difference in
the text rather than a difference in care. ``out of order`` is a fragment inside
a longer finding, ``Tree 2 page 2 cell 0: Rowid 2 out of order``, so it has no
start of its own to be held to and needs a mechanism this one cannot supply.
TASK-99 holds that residue together with the capture that shows it is real.

``fts5: missing row %lld from content table %s`` is the case that settles that
rule, and it was a needle here until it was measured. A database merely out of
step with its content and a database with a shadow-table row deleted out of it
raise the same sentence, differing only in a rowid and in a table name, so
telling them apart means deciding whether that name belongs to a shadow table.
That takes a schema this function is not given, and it is the name-reading this
task exists to remove. So the needle is gone and that text reports UNKNOWN,
which costs nothing on the damaged side: the same database is reported by
``integrity_check`` as ``malformed inverted index for FTS5 table
main.messages_fts``, and the first FTS needle reads it. The transcripts that
settle it are in docs/integrity.md.

The converse is not covered and cannot be. Some damage to an FTS table's own
shadow tables is printed as ordinary b-tree damage naming no FTS at all, since
those shadow tables are ordinary b-trees: a rowid disorder in one was observed
here reported as exactly that. Only some of it, though, and which form arrives
depends on the damage rather than on the table. Deleting a row out of that same
``messages_fts_content`` reaches FTS5's own code instead and prints ``malformed
inverted index for FTS5 table main.messages_fts``, which the first needle above
reads. So the absence of this class is not evidence that FTS is healthy.

docs/integrity.md also holds the corpus provenance and the procedure each
observed sample was captured by.
"""

import re

# SQLite prints a header above its findings on some paths and omits it on
# others: the rowid and page-level samples in the corpus carry one and the
# index sample does not. It names the database being checked rather than
# reporting anything about it, so it is removed before classification and is
# never a finding.
#
# It is matched by shape rather than against the literal
# "*** in database main ***", because the word in the middle is the attached
# database's name. Checking a file through ATTACH prints "*** in database aux1
# ***", which was observed on SQLite 3.51.2 and is in the corpus. Matching only
# main would file that line as damage, running the count in the diagnosis one
# high and leaving INCONCLUSIVE unreachable for any database not called main.
# That is what substituting the literal comparison and re-running produces, not
# a fault some released version shipped: neither field existed before this task.
_HEADER_PREFIX = "*** in database "
_HEADER_SUFFIX = " ***"


def _is_header(line):
    return line.startswith(_HEADER_PREFIX) and line.endswith(_HEADER_SUFFIX)

# How a needle is compared against a finding line. Both names are private, and
# deliberately: tests/test_docs_integrity.py derives the documented statuses by
# harvesting every PUBLIC uppercase string in this module, so a public constant
# here would be demanded of the document as a sixth status it is not.
#
# _ANCHORED requires the needle to BEGIN the message, once the sqlite3 shell's
# own wrapper is off the front. _CONTAINED accepts it anywhere in the line as it
# arrived. The mode is carried per row rather than expressed by splitting the
# table in two, so that adding a needle forces the question to be answered
# instead of being settled by which half it was pasted into, and so that the
# single ordering below stays literally true.
_ANCHORED = "anchored"
_CONTAINED = "contained"

# The sqlite3 shell wraps a message it reports as an error, and it is the same
# wrapper whatever the message: a kind, a locator, then a colon and a space.
# Measured on shell 3.53.4, the kinds are `Parse error` before the statement
# runs and `Error` once it has, and the locators are `in Nth command line
# argument`, `near line N`, and `near line N of <path>`. Rows returned by
# integrity_check itself arrive with no wrapper at all.
#
# Stripping it is what lets the FTS needles be held to the start of a message
# without the shell capture path losing them, which is the objection that made
# an earlier note here conclude anchoring could not be the fix. The conclusion
# was wrong and the premise was right: the wrapper is real, and it is also a
# closed family that can be taken off first.
#
# The path in `near line 1 of x.sql` is matched non-greedily, so it ends at the
# first colon FOLLOWED BY A SPACE rather than at the first colon: a path like
# `/tmp/a:b.sql` is consumed whole, and it takes a space after the colon to end
# the match early and leave part of the wrapper on the front of the message.
# That direction is deliberate. A leftover prefix can only stop an anchored
# needle from matching, which costs UNKNOWN, while matching to the LAST
# colon-space would cut into the message itself: `something: malformed inverted
# index for FTS5 table main.t` would be reduced to the needle and reported as
# FTS corruption, which is this module's own fabrication rather than SQLite's
# finding.
_SHELL_WRAPPER = re.compile(
    r"^(?:parse error|error) "
    r"(?:in \d+(?:st|nd|rd|th) command line argument|near line \d+(?: of .*?)?)"
    r": ")


def _strip_shell_wrapper(low):
    """Return ``low`` without the sqlite3 shell's error wrapper, if it has one.

    Used for matching only. What lands in ``unclassified`` and in ``raw`` is
    what arrived, because those two keys are the record of the capture rather
    than of how it was read.
    """
    return _SHELL_WRAPPER.sub("", low)


def _matches(needle, mode, line, message):
    """Does ``needle`` fire on this finding, under its own matching mode?

    ``line`` is the finding folded to lower case and ``message`` is that line
    with the shell wrapper removed. Both are passed in rather than recomputed
    because the wrapper is stripped once per line and asked about once per
    needle.

    An unrecognised mode raises instead of returning False, for the reason the
    raise in _diagnose exists: a mode misspelled in the table would otherwise
    disable that signature silently, and a signature that never fires reports
    UNKNOWN on damage while every other test in this suite stays green.
    """
    if mode == _ANCHORED:
        return message.startswith(needle)
    if mode == _CONTAINED:
        return needle in line
    raise ValueError(
        f"the signature {needle!r} declares matching mode {mode!r}, which is "
        f"not {_ANCHORED!r} or {_CONTAINED!r}. Give it one rather than leaving "
        "it unable to match anything.")

# Matched in order, first hit wins. Among the lines SQLite itself writes, one
# pair overlaps, and it is the pair the order exists for: a line naming an
# out-of-order rowid inside an index satisfies both CANONICAL needles, so the
# rowid entry is placed first and the incident's own root signature cannot
# change class with how the table is read.
#
# The FTS needles come first, and here the order is load-bearing in the other
# direction. They are the anchored ones, so a line they fire on is a line whose
# START is an FTS diagnostic, and anything a CONTAINED needle finds further
# along such a line is inside text SQLite interpolated rather than wrote: an FTS
# table called `out of order` is possible and is not a rowid disorder. Putting
# them first means the positionally grounded reading wins over the positionally
# free one wherever both apply.
#
# That ordering also repairs a suppression the CONTAINED form caused on its own.
# `wrong # of entries in index fts5: corrupt` is one finding about one ordinary
# index whose name happens to be an FTS message; under the previous table the
# FTS needle matched it and `break` hid CANONICAL_INDEX_COUNT, so the capture
# reported the wrong class rather than an extra one.
_SIGNATURES = (
    # The messages SQLite's own FTS code writes when it reports corruption,
    # enumerated from the format strings in the library in use (3.51.2). They
    # name FTS because FTS code ran, which is the entire difference from the
    # criterion this replaced: `idx_fts` is a name a user chose, while the
    # `FTS5` in these was printed by the module that maintains the index. The
    # first needle covers FTS3 and FTS4 as well, whose message differs from
    # FTS5's only in the digit, and `fts5: corrupt` covers four format strings
    # at once, since the library writes both `corrupt` and `corruption` across
    # the same family of faults.
    #
    # All three are _ANCHORED, and the reason is that all three are whole
    # messages: each is the entire text SQLite emitted, so it begins the line it
    # arrives on. Held anywhere instead, each was reachable from an ordinary
    # index named after it, measured on 3.51.2 and in the corpus as
    # index_named_fts_message. `row 1 missing from index fts5: corrupt` is a
    # b-tree finding about a b-tree index, and it does not begin with any of
    # these needles, because a line SQLite emitted begins with what SQLite chose
    # to say rather than with what someone chose to call an object. The anchor
    # is therefore only as good as the split that produced the line, which is
    # why classify_integrity splits on \n alone.
    #
    # Two of the three were also produced here from a database damaged for the
    # purpose and are in the corpus as observed captures. The checksum one was
    # not: FTS5 emits it from its own `integrity-check` command, which raised
    # `database disk image is malformed` on every damaged database tried here.
    # Its needle rests on the format string alone, which is why the corpus
    # holds that sample as synthetic and says so.
    #
    # Four near misses are excluded deliberately, and each is in the corpus
    # with the measurement behind it. The bare `fts5: ` prefix marks the module
    # that spoke rather than what it said, and arrives on syntax errors from
    # undamaged databases. `unable to validate the inverted index for FTS%d
    # table %s.%s` reports that the check could not run. `invalid fts5 file
    # format (found %d, expected %d or %d) - run 'rebuild'` says this build
    # cannot read the index, which is what a database written by a newer FTS5
    # produces with nothing wrong with it. And `fts5: missing row %lld from
    # content table %s`, which was a needle here until it was measured, is
    # raised by a healthy out-of-step external-content index and by a damaged
    # shadow table alike; the docstring above carries that measurement.
    ("malformed inverted index for fts", "FTS_CORRUPTION", _ANCHORED),
    ("fts5: corrupt", "FTS_CORRUPTION", _ANCHORED),
    ("fts5: checksum mismatch", "FTS_CORRUPTION", _ANCHORED),
    # The remaining four are _CONTAINED, and that is a statement about their
    # text rather than a lower standard. NOTADB and SCHEMA are whole messages
    # and could be anchored; they are left as they are because they were
    # approved in this form and this task's mandate is the FTS half. The two
    # CANONICAL needles cannot be anchored at all: `out of order` is a fragment
    # at the END of `Tree 2 page 2 cell 0: Rowid 2 out of order`, and
    # `wrong # of entries in index` is followed by a name rather than preceded
    # by one. So the same exposure remains on these four, an index named
    # `out of order` still carries its needle into a line about something else,
    # and TASK-99 holds it with the capture that shows it is real. What is
    # fixed here is that the FTS names are no longer attributed to FTS.
    ("file is not a database", "NOTADB", _CONTAINED),
    ("malformed database schema", "SCHEMA", _CONTAINED),
    ("out of order", "CANONICAL_ROWID_DISORDER", _CONTAINED),
    ("wrong # of entries in index", "CANONICAL_INDEX_COUNT", _CONTAINED),
)

#: The check ran and reported the one output that means it passed.
CLEAN = "clean"
#: At least one finding was recognised. ``classes`` says which.
DAMAGED = "damaged"
#: Text arrived and no signature matched any of it. This is not a pass, because
#: the one output that means a pass is ``ok`` and this is not it. What it does
#: mean is not established: it may be damage this parser cannot name, or a
#: message from the error channel, where the check never ran at all.
UNKNOWN = "unknown"
#: Text arrived but carries no verdict, such as a header with nothing under it.
#: A capture that was cut short reads this way.
INCONCLUSIVE = "inconclusive"
#: Nothing was captured. Kept apart from INCONCLUSIVE because the two send an
#: operator to different places: here, to the channel the output failed to
#: arrive on, which for a destroyed file is stderr and the exit code.
NO_OUTPUT = "no_output"


def _diagnose(status, classes, unclassified):
    """One sentence per verdict, stating what is known and no more.

    Written out per status rather than assembled from fragments because the
    whole job of this function is to not overstate, and a sentence built from
    parts is one whose final claim nobody reads.

    The statuses are compared with ``==`` and the set is closed by a raise at
    the end. Both guard one hazard: comparing with ``is`` and letting anything
    unrecognised fall through would send an unmodelled status to the DAMAGED
    sentence, which then answers "Recognised signature(s): ." and claims
    recognised damage while naming none. That is the one thing this field
    exists not to do. ``==`` is the right test because a status that has been
    through JSON is equal to a constant here without being the same object.
    """
    if status == CLEAN:
        return ("The check reported ok and nothing else, which is the only "
                "output that means the database passed.")
    if status == NO_OUTPUT:
        return ("No integrity_check output was captured, which is not a "
                "verdict of any kind. A file that is not a database, a schema "
                "that will not parse and a truncated file all fail before any "
                "output is produced: the message goes to the error channel, so "
                "look at stderr and the exit status rather than reading this "
                "as an absence of damage.")
    if status == INCONCLUSIVE:
        return ("The output carries the integrity_check header and no findings "
                "under it, so it says nothing about the database either way. "
                "No run observed here produced that shape, because the header "
                "is prefixed to the b-tree check's findings and comes back in "
                "the same row as them, so suspect the capture rather than the "
                "database and re-read the full output.")
    if status == UNKNOWN:
        return (f"{len(unclassified)} line(s) matched no known signature, so "
                "this text is not a pass and what it does mean is not "
                "established. It may be damage this parser cannot name, or a "
                "message from the error channel, where the check never ran at "
                "all: 'database is locked' reads exactly like this. The lines "
                "are in 'unclassified', stripped of surrounding whitespace; "
                "'raw' holds the capture exactly as it arrived.")
    if status != DAMAGED:
        raise ValueError(
            f"no diagnosis is written for status {status!r}. Add one here "
            "rather than letting it fall through to a sentence about damage.")
    named = ", ".join(classes)
    sentence = f"Recognised signature(s): {named}."
    if "FTS_CORRUPTION" in classes:
        sentence += (" FTS_CORRUPTION is what SQLite's own FTS code wrote "
                     "rather than an inference from an index name: it reports "
                     "the FTS index as corrupt and says nothing about the rest "
                     "of the database.")
    if unclassified:
        sentence += (f" {len(unclassified)} further line(s) matched no "
                     "signature and are in 'unclassified', stripped of "
                     "surrounding whitespace; 'raw' holds the capture exactly "
                     "as it arrived.")
    return sentence


def classify_integrity(text) -> dict:
    """Classify captured integrity_check text. See the module docstring.

    ``text`` is a ``str``, and the parameter is left unannotated for the reason
    the check below exists: annotating it ``str`` states that no other type
    arrives, which is the very claim this function refuses to make about its
    callers. rules.py and targets.py leave their validated arguments bare for
    the same reason.

    Raises ``TypeError`` for anything that is not a ``str``. The empty string
    is a meaningful input here and reports NO_OUTPUT, so a caller that never
    performed the capture, or that passes on a ``None`` from somewhere, needs
    to be told apart from one that captured nothing; left to itself the
    ``None`` would fail on ``.split()`` below, with an ``AttributeError``
    that names the type and neither this function nor the argument.
    """
    if not isinstance(text, str):
        raise TypeError(
            "classify_integrity() expects the captured integrity_check output "
            f"as str, got {type(text).__name__}. Pass '' if nothing was "
            "captured; that reports status NO_OUTPUT.")

    # split("\n") rather than splitlines(), and the difference is load bearing
    # rather than stylistic. splitlines() also breaks on \v, \f, \r, \x1c, \x1d,
    # \x1e, \x85, U+2028 and U+2029, none of which SQLite ever emits as a line
    # break. An object NAME may contain them, and SQLite prints names unquoted,
    # so splitlines() manufactured a line boundary out of a character the user
    # chose and put the rest of that name at the start of a line, where an
    # anchored needle then matched it. Measured on SQLite 3.51.2: an index named
    # "x<U+2028>fts5: corrupt", written with the character itself rather than
    # that notation, produced one row that split into two findings and
    # reported FTS_CORRUPTION for a database holding no FTS at all. Only \n is a
    # boundary SQLite writes. A name holding a real \n reaches the same result
    # and cannot be told apart from text alone; classify_integrity_rows closes
    # that for in-process callers, and this function cannot.
    lines = [s for s in map(str.strip, text.split("\n")) if s]
    if not lines:
        return _verdict(NO_OUTPUT, text)
    if lines == ["ok"]:
        return _verdict(CLEAN, text)

    findings = [l for l in lines if not _is_header(l)]
    if not findings:
        return _verdict(INCONCLUSIVE, text)

    classes = set()
    unclassified = []
    for line in findings:
        low = line.lower()
        message = _strip_shell_wrapper(low)
        for needle, name, mode in _SIGNATURES:
            if _matches(needle, mode, low, message):
                classes.add(name)
                break
        else:
            unclassified.append(line)

    return _verdict(DAMAGED if classes else UNKNOWN, text, classes, unclassified)


def classify_integrity_rows(rows) -> dict:
    """Classify PRAGMA integrity_check output from its rows directly.

    Each element of ``rows`` is one string returned by the PRAGMA, as in
    ``[row[0] for row in con.execute("PRAGMA integrity_check")]``.
    Unlike ``classify_integrity``, which splits a text on ``\\n``, this
    function preserves the row boundaries sqlite3 provides, so a name
    that contains a real newline stays inside its own row rather than
    manufacturing a line boundary the anchored needles then match.

    This is the in-process path: a caller with a ``sqlite3.Connection``
    passes the rows it read. The shell-capture path has no rows, only
    text, and uses ``classify_integrity`` instead; a real newline inside
    an object name is indistinguishable from a row boundary in text, so
    that function is exposed to this ambiguity and always will be.

    A row from the b-tree check carries the header and its findings
    joined by ``\\n`` inside a single string. That row is recognised by
    the header prefix at its start and split internally, which is safe
    because the header is prefixed by SQLite to a non-empty body and is
    never the text of an index finding. A row from the index check is
    one finding and is never split, even when its name contains ``\\n``.

    Raises ``TypeError`` when handed a bare ``str``, which is the
    mistake ``classify_integrity`` would silently answer.
    """
    if isinstance(rows, str):
        raise TypeError(
            "classify_integrity_rows() expects an iterable of row "
            "strings, not a single str. Use classify_integrity() for "
            "a text capture, or pass [text] for a single row.")
    if not isinstance(rows, (list, tuple)):
        rows = list(rows)

    raw = "\n".join(rows)

    findings = []
    saw_content = False
    for row in rows:
        stripped = row.strip()
        if not stripped:
            continue
        saw_content = True
        if stripped.startswith(_HEADER_PREFIX):
            for sub in stripped.split("\n"):
                sub = sub.strip()
                if sub and not _is_header(sub):
                    findings.append(sub)
        else:
            findings.append(stripped)

    if not saw_content:
        return _verdict(NO_OUTPUT, raw)
    if findings == ["ok"]:
        return _verdict(CLEAN, raw)
    if not findings:
        return _verdict(INCONCLUSIVE, raw)

    classes = set()
    unclassified = []
    for finding in findings:
        low = finding.lower()
        message = _strip_shell_wrapper(low)
        for needle, name, mode in _SIGNATURES:
            if _matches(needle, mode, low, message):
                classes.add(name)
                break
        else:
            unclassified.append(finding)

    return _verdict(
        DAMAGED if classes else UNKNOWN, raw, classes, unclassified)


def _verdict(status, text, classes=(), unclassified=()):
    """The single constructor for a verdict, which is what keeps it consistent.

    Every return path goes through here, so "classes is non-empty exactly when
    status is DAMAGED" holds by construction rather than by discipline: the
    three early returns cannot name a signature, and the one remaining call
    derives the status from the classes in the same expression.
    """
    classes = sorted(classes)
    unclassified = list(unclassified)
    return {
        "status": status,
        "classes": classes,
        "unclassified": unclassified,
        "diagnosis": _diagnose(status, classes, unclassified),
        "raw": text,
    }
