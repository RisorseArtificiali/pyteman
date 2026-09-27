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

The verdict is a mapping of six keys: ``status``, ``classes``,
``unclassified``, ``databases``, ``diagnosis`` and ``raw``. docs/integrity.md states that
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
classify_integrity, which splits on ``\\n`` alone for that reason. The
measurement behind all of this lives in docs/integrity.md rather than being
restated here, and so does the live reproduction it now runs from.

The canonical needles are fragments and cannot be held to a start:
``out of order`` sits at the end of ``Tree 2 page 2 cell 0: Rowid 2 out of
order``, and ``wrong # of entries in index`` is followed by a name. For these
the rule is applied through the interpolated-name slots instead: an occurrence
inside a slot SQLite filled with an object's name does not fire, whatever it
spells. docs/integrity.md states the bound on that slot family.

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


def _header_database(line):
    """The attached database's name, out of the header that carries it.

    The line is a header by the time this is called; the name is whatever
    sits between the two markers, unquoted, because SQLite prints schema
    names that way and an attached name is an identifier the operator
    chose. `main` arrives here the same way `aux1` does, and a capture
    with no header at all is that same database checked alone: lines
    before any header are attributed to "main" on exactly that basis,
    which is the name SQLite gives the pragma's own database whenever
    it names it at all.
    """
    return line[len(_HEADER_PREFIX):len(line) - len(_HEADER_SUFFIX)]

# How a needle is compared against a finding line. Both names are private, and
# deliberately: tests/test_docs_integrity.py derives the documented statuses by
# harvesting every PUBLIC uppercase string in this module, so a public constant
# here would be demanded of the document as a sixth status it is not.
#
# _ANCHORED requires the needle to BEGIN the message, once the sqlite3
# shell's own wrapper is off the front. _CONTAINED accepts it anywhere in
# the message except inside an interpolated object name (see _slot_cut). The mode is carried per row rather than expressed by splitting the
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


# The contexts in which SQLite interpolates an OBJECT NAME into a finding
# line, as the tails those lines end with once the name is printed. SQLite
# prints names unquoted and runs them to the end of the message, so the
# pattern captures the whole rest of the line as the name slot, and the
# leftmost tail is the only one that matters: everything to its right is
# inside a name. They are the fragment needles' share of the rule the
# anchored needles get from their position: a needle counts only where
# SQLite wrote, never inside a slot SQLite filled with what someone chose
# to call an object. The four literals are SQLite's own, enumerated from
# pragma.c and btree.c at 3.51.2/3.53.4 (`in index`, `from index`,
# `of index`, `table`).
#
# The family is deliberately this list and not a grammar of every finding
# format string. The bound is stated in docs/integrity.md and is present
# tense: a name interpolated after some other literal than these four is
# exposed today, `NULL value in %s.%s` among them, and a message that puts
# literal text after a name tail can mask a genuine fragment at the cost
# of one UNKNOWN rather than a wrong class.
_SLOT_TAILS = re.compile(r"\b(?:(?:from|in|of) index|table) (.+)$")


def _slot_cut(message):
    """Where the interpolated-name tail begins, or the end of the line.

    Both the cut and the containment search work on the wrapper-stripped
    message, so their offsets share one frame. The wrapper itself is not
    neutral text: its `near line N of <path>` locator interpolates a
    user-chosen path, and a path containing `table ` or an index literal
    would otherwise manufacture a slot out of the locator and swallow, or
    donate, a needle through text SQLite never wrote as a finding.
    """
    m = _SLOT_TAILS.search(message)
    return m.start(1) if m else len(message)


def _matches(needle, mode, line, message):
    """Does ``needle`` fire on this finding, under its own matching mode?

    ``line`` is the finding folded to lower case and ``message`` is that line
    with the shell wrapper removed. Both are passed in rather than recomputed
    because the wrapper is stripped once per line and asked about once per
    needle.

    A _CONTAINED needle fires only before the interpolated-name tail, as
    _slot_cut marks it on the same stripped text: an occurrence inside a
    name SQLite interpolated is text someone chose, not a finding SQLite
    wrote, however exactly it spells a needle (TASK-99). One find is enough
    because every tail runs to the end of the line, so any occurrence to
    the right of an in-slot one is inside the same slot too.

    An unrecognised mode raises instead of returning False, for the reason the
    raise in _diagnose exists: a mode misspelled in the table would otherwise
    disable that signature silently, and a signature that never fires reports
    UNKNOWN on damage while every other test in this suite stays green.
    """
    if mode == _ANCHORED:
        return message.startswith(needle)
    if mode == _CONTAINED:
        return needle in message and needle in message[:_slot_cut(message)]
    raise ValueError(
        f"the signature {needle!r} declares matching mode {mode!r}, which is "
        f"not {_ANCHORED!r} or {_CONTAINED!r}. Give it one rather than leaving "
        "it unable to match anything.")

# Matched in order, first hit wins. Between the two CANONICAL needles the
# order is now inert: with in-slot occurrences not firing, no line SQLite
# writes can satisfy both outside a name, and the test that used to pin the
# order pins the slot behaviour instead. The order is kept for the reader
# as the incident's own root signature first.
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
    # NOTADB and SCHEMA are whole messages and are anchored like the FTS
    # three (TASK-99). Both reach this parser as exception text from the
    # library, which hands the message over bare, or as a shell-wrapped line
    # whose wrapper _SHELL_WRAPPER takes off; in every observed form the
    # message begins the text that is left, so the anchor holds and an index
    # named `file is not a database` no longer donates its name to a
    # NOTADB class.
    ("file is not a database", "NOTADB", _ANCHORED),
    ("malformed database schema", "SCHEMA", _ANCHORED),
    # The two CANONICAL needles cannot be anchored at all: `out of order` is
    # a fragment at the END of `Tree 2 page 2 cell 0: Rowid 2 out of order`,
    # and `wrong # of entries in index` is followed by a name rather than
    # preceded by one. They stay _CONTAINED and are protected by the slot
    # rule in _matches instead: an occurrence inside an interpolated name
    # does not fire, so the line naming an index `out of order` in a genuine
    # entry-count finding reaches CANONICAL_INDEX_COUNT, and a name-only
    # hit that no other needle answers lands in `unclassified` where the
    # misreading is visible instead of silently reclassified.
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
    # and cannot be told apart from text alone; that residue is TASK-104.
    lines = [s for s in map(str.strip, text.split("\n")) if s]
    if not lines:
        return _verdict(NO_OUTPUT, text)
    if lines == ["ok"]:
        return _verdict(CLEAN, text)

    # Headers only, nothing under any of them: the capture names
    # sections and reports no finding, which is inconclusive rather than
    # clean, because a clean database answers "ok" in its own section.
    if all(_is_header(l) for l in lines):
        return _verdict(INCONCLUSIVE, text)

    # The flat answer and the per-database attribution are built in ONE
    # pass over the same lines, so the two can never disagree about
    # which line matched what. The flat lists keep global row order;
    # each database's lists keep their own, and since a header switches
    # the attribution for everything after it, per-database order and
    # global order agree within every section. A capture that revisited
    # a database name would merge the sections under that name, which
    # SQLite does not do but a hand-built capture could: the flat lists
    # would still hold the true global order, the merged bucket the
    # visit order.
    classes = set()
    unclassified = []
    per_database = {}
    current = "main"
    for line in lines:
        if _is_header(line):
            current = _header_database(line)
            continue
        bucket = per_database.setdefault(
            current, {"classes": set(), "unclassified": []})
        low = line.lower()
        message = _strip_shell_wrapper(low)
        for needle, name, mode in _SIGNATURES:
            if _matches(needle, mode, low, message):
                classes.add(name)
                bucket["classes"].add(name)
                break
        else:
            unclassified.append(line)
            bucket["unclassified"].append(line)

    return _verdict(DAMAGED if classes else UNKNOWN, text, classes,
                    unclassified, per_database)


def _verdict(status, text, classes=(), unclassified=(), per_database=None):
    """The single constructor for a verdict, which is what keeps it consistent.

    Every return path goes through here, so "classes is non-empty exactly when
    status is DAMAGED" holds by construction rather than by discipline: the
    three early returns cannot name a signature, and the one remaining call
    derives the status from the classes in the same expression.

    ``databases`` is ADDITIVE to the shape every caller already reads
    (status, classes, unclassified, diagnosis, raw), which is how the
    schema stays backward compatible: a caller that ignores it sees
    exactly the verdict it always saw. It maps each header's database
    name to the classes and unclassified lines its section produced, in
    encounter order; the early returns carry an empty mapping because
    they have no findings to attribute.
    """
    classes = sorted(classes)
    unclassified = list(unclassified)
    databases = {}
    for name, bucket in (per_database or {}).items():
        databases[name] = {"classes": sorted(bucket["classes"]),
                           "unclassified": list(bucket["unclassified"])}
    diagnosis = _diagnose(status, classes, unclassified)
    if len(databases) > 1:
        diagnosis += (" The 'databases' field says which attached file "
                      "each class and line came from.")
    return {
        "status": status,
        "classes": classes,
        "unclassified": unclassified,
        "databases": databases,
        "diagnosis": diagnosis,
        "raw": text,
    }
