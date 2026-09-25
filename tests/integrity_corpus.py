"""Labelled samples of ``PRAGMA integrity_check`` output, with their origin.

TASK-25 / SQL-02, acceptance criterion 1, extended by TASK-24 / SQL-01 with the
FTS samples and their near misses. Each sample says where its text came
from, because the two origins carry different authority and a test that cannot
tell them apart will eventually assert that SQLite guarantees something no one
ever observed.

``OBSERVED`` means the text was captured from a real SQLite run against a
database damaged or known to be damaged. Where a sample is an excerpt
of a longer capture rather than the whole of one, its note says so and
says what the full output classifies as, because an excerpt can satisfy
a criterion the capture it came from does not. ``SYNTHETIC`` means the
text was written here to exercise a branch, and nothing says SQLite
emits it in that shape; a synthetic sample pins what this parser does
with such input, never what SQLite promises.

The ORDER of the lines in an observed sample is part of the record and not part
of the promise. ``PRAGMA integrity_check`` reports a set of findings, and the
sequence it prints them in is an artifact of how one build walked the database:
the samples here were recorded on a Fedora workstation, and a GitHub runner
emits the same findings in a different order. A test comparing a live capture
against a sample must therefore compare them as collections of lines, which
tests/test_integrity_classification.py does. Asserting the sequence makes the
suite fail on a machine where nothing is wrong.

The samples are text. No corrupt database file is versioned: the procedure that
produced each one is recorded in docs/integrity.md, which is what makes the
observed samples reproducible, and a binary would age into a file no one can
re-derive. Tool versions used for the capture are recorded there too.
"""

from typing import NamedTuple

OBSERVED = "observed"
SYNTHETIC = "synthetic"


class Sample(NamedTuple):
    """One captured or constructed integrity_check output.

    ``note`` says what the sample is for, and for an observed one how the
    damage was produced; the full procedure lives in docs/integrity.md.
    """

    name: str
    origin: str
    text: str
    note: str


_INCIDENT_TEXT = (
    "*** in database main ***\n"
    "Tree 22 page 67350 cell 100: "
    "Rowid 343597390982 out of order\n"
    "wrong # of entries in index idx_messages_session_id"
)

CORPUS = (
    Sample(
        "clean", OBSERVED, "ok",
        "An undamaged database. The whole output is one line: SQLite emits no "
        "header when it has nothing to report.",
    ),
    Sample(
        "empty_file_is_clean", OBSERVED, "ok",
        "A zero-byte file, which SQLite opens as a valid empty database and "
        "reports ok. An empty FILE and an empty CAPTURE are opposite verdicts, "
        "and this sample exists so that stays written down.",
    ),
    Sample(
        "rowid_disorder", OBSERVED,
        "*** in database main ***\n"
        "Tree 2 page 2 cell 0: Rowid 2 out of order",
        "Two cell pointers swapped on a table leaf page. The signature the "
        "original incident was found by, reproduced from scratch.",
    ),
    Sample(
        "index_count_with_residue", OBSERVED,
        "wrong # of entries in index idx_messages_session_id\n"
        + "\n".join(f"row {n} missing from index idx_messages_session_id"
                    for n in range(201, 261)),
        "An index hidden from the schema while rows were inserted, then "
        "restored. One recognised line and sixty that no rule here reads: the "
        "mixed case, and it is what the real tool actually prints. Note the "
        "absent header, which SQLite omits on this path.",
    ),
    Sample(
        "orphan_pages", OBSERVED,
        "*** in database main ***\n"
        + "\n".join(f"Page {n}: never used" for n in (3, 4, 5, 9, 11)),
        "An index dropped from the schema, orphaning its pages. Page-level "
        "damage, recognised by no rule here, and the reason the unknown state "
        "has to exist: this is real output that carries a real fault.",
    ),
    Sample(
        "attached_database_header", OBSERVED,
        "*** in database aux1 ***\n"
        "Page 3: never used",
        "Orphaned-page damage of the same kind as orphan_pages, reached through "
        "ATTACH, which is what proves the header names the database rather than "
        "always saying main. A different instance, not the same one: the "
        "indexed values here are short, so the index occupies one page instead "
        "of five. SQLite returned the header and the finding as a single row "
        "with an embedded newline: the header is prefixed to the b-tree "
        "check's own findings and emitted with them, which is why it never "
        "arrives in a row by itself. Matching the header literally would file "
        "this line as damage, running the count one high and leaving no "
        "database except main able to be reported inconclusive.",
    ),
    Sample(
        "fts5_corruption", OBSERVED,
        'fts5: corruption found reading blob 137438953474 from table "messages_fts"',
        "An FTS5 shadow-table block zeroed, on a database that really held one. "
        "Which samples back which needles is mapped in docs/integrity.md, where "
        "a test resolves every sample name the prose cites; repeating that map "
        "here would be a cross-reference nothing checks. What this sample "
        "carries on its own is that the message is real FTS5 output, and that "
        "having been written by the module maintaining the index is necessary "
        "and not sufficient, which is why the fts5: near misses below are "
        "matched by nothing.",
    ),
    Sample(
        "fts5_checksum_mismatch", SYNTHETIC,
        'fts5: checksum mismatch for table "messages_fts"',
        "The format string is genuine, enumerated from the library in use, and "
        "the needle matching it is kept. The capture is not: FTS5 emits this "
        "from its own 'integrity-check' command, and running that against a "
        "content table edited behind FTS5's back raised 'database disk image "
        "is malformed' here instead. So the sample is marked for what it is. "
        "A format string proves the message exists; only a capture proves how "
        "it arrives.",
    ),
    Sample(
        "fts5_malformed_inverted_index", OBSERVED,
        "malformed inverted index for FTS5 table main.messages_fts",
        "The wrapper integrity_check puts around an FTS corruption it could "
        "not describe further, and the message tests/test_integrity.py has "
        "carried since the original incident. It is now reproduced rather than "
        "quoted from memory: deleting a row from the content shadow table "
        "prints exactly this.",
    ),
    Sample(
        "fts4_malformed_inverted_index", OBSERVED,
        "malformed inverted index for FTS4 table main.m4",
        "The same wrapper from FTS4, which differs only in the digit. Held "
        "because a needle narrowed to FTS5 would silently stop reading the "
        "older modules, and nothing in the message would announce it.",
    ),
    Sample(
        "fts5_missing_content_row_message", OBSERVED,
        "fts5: missing row 2 from content table 'main'.'messages_fts_content'",
        "The same damage as fts5_malformed_inverted_index seen from a query "
        "rather than from the check: a MATCH over the damaged table raises "
        "this. Held as a NEAR MISS rather than as a matched signature, which "
        "it was until it was measured. Read the sample below it: the same "
        "sentence comes back from a database with nothing wrong. The two "
        "differ in a rowid and in the name of the table printed at the end, "
        "and the name is the only one of the two that could decide anything: "
        "this one names a shadow table and that one names the user's own, so "
        "separating them takes the schema rather than the text. Nothing is "
        "lost by declining it, because this database is also reported by "
        "integrity_check as fts5_malformed_inverted_index, which is matched.",
    ),
    Sample(
        "fts5_missing_row_from_healthy_index", OBSERVED,
        "fts5: missing row 1 from content table 'main'.'notes'",
        "An UNDAMAGED database, and the capture that removed the "
        "`fts5: missing row` needle. An external-content FTS5 index over a "
        "table whose rows were never inserted is out of step with its content "
        "rather than corrupt, and SQLite agrees: integrity_check, quick_check "
        "and FTS5's own integrity-check all returned ok on this database while "
        "an ordinary MATCH raised this. Matching the text would have reported "
        "confirmed FTS corruption for a database three separate SQLite checks "
        "called healthy.",
    ),
    Sample(
        "invalid_fts5_file_format_message", SYNTHETIC,
        "invalid fts5 file format (found 99, expected 4 or 5) - run 'rebuild'",
        "One of the four near misses, and the one easiest to mistake for "
        "damage, "
        "since FTS5 writes it from its own code and tells you to rebuild. The "
        "format string is genuine, enumerated from the library in use; the "
        "numbers are chosen, which is why this is marked synthetic. What it "
        "reports is that this build cannot read the index format it found, "
        "which is what a database written by a NEWER FTS5 produces with "
        "nothing wrong with it. Unmatched for the same reason as "
        "unable_to_validate_fts_message: it says the index was not read, not "
        "that it is broken.",
    ),
    Sample(
        "fts5_syntax_error_message", OBSERVED,
        'fts5: syntax error near ""',
        "An fts5: message that reports no damage at all, from an undamaged "
        "database: a MATCH query whose expression does not parse. This is why "
        "the prefix is not a needle on its own, though it would be shorter "
        "than three of the ones used. The prefix says which module spoke, not "
        "what it said.",
    ),
    Sample(
        "unable_to_validate_fts_message", SYNTHETIC,
        "unable to validate the inverted index for FTS5 table main.messages_fts: "
        "out of memory",
        "Not observed, and the origin label is doing real work here. The "
        "format string is genuine, enumerated from the library in use, but it "
        "is emitted when the check fails for a reason that is not corruption, "
        "and no damage contrived here produced one. Held because the old "
        "criterion read it as confirmed FTS damage on the strength of the "
        "_fts in the table name, when what it says is that nothing was "
        "checked.",
    ),
    Sample(
        "mixed_fts_and_index_count", OBSERVED,
        "wrong # of entries in index idx_messages_session_id\n"
        + "\n".join(f"row {n} missing from index idx_messages_session_id"
                    for n in range(21, 26))
        + "\nmalformed inverted index for FTS5 table main.messages_fts",
        "One database damaged in both ways at once, and the shape the old "
        "criterion was blindest to: a signature matched, so the FTS test never "
        "ran, and the one line SQLite's own FTS code wrote came back as a line "
        "nobody read. Real output, seven rows, FTS reported last.",
    ),
    Sample(
        "fts5_shadow_table_btree_damage", OBSERVED,
        "*** in database main ***\n"
        "Tree 4 page 4 cell 0: Rowid 2 out of order",
        "Real damage to a real FTS5 shadow table, printed without the word FTS "
        "anywhere in it: the content table is an ordinary b-tree and reports "
        "as one. The sample this corpus needs in order to say what the text "
        "cannot do. FTS is damaged and the capture does not know it, so the "
        "absence of FTS_CORRUPTION is not evidence that FTS is healthy.",
    ),
    Sample(
        "expression_index_named_fts", OBSERVED,
        "\n".join(f"row {n} missing from index idx_fts" for n in (1, 2, 3, 4)),
        "The whole reason this criterion was rewritten, reproduced from "
        "scratch: an ordinary expression index that merely has _fts in its "
        "name, over a table with no FTS in it anywhere. Every line contains "
        "_fts and none of them is about FTS, which the old criterion read as "
        "confirmed FTS damage. Unlike btree_index_named_fts this is a whole "
        "capture rather than an excerpt, and what makes it one is that the "
        "index holds the RIGHT NUMBER of entries and the wrong entries: the "
        "rows were updated rather than inserted while the index was hidden, so "
        "the count check passes and prints nothing, and there is no recognised "
        "line anywhere in the output to mask the misreading.",
    ),
    Sample(
        "btree_index_named_fts", OBSERVED,
        "\n".join(f"row {n} missing from index idx_fts" for n in range(201, 206)),
        "An ORDINARY b-tree index that merely has _fts in its name, damaged the "
        "same way as index_count_with_residue. This is an EXCERPT, and the "
        "distinction matters: the full 61-line capture opens with 'wrong # of "
        "entries in index idx_fts', which a signature matches, so the whole "
        "capture classifies as CANONICAL_INDEX_COUNT. These are the first five "
        "of the sixty lines under it, the ones no signature reads, "
        "which is the shape of a capture that lost its opening lines rather "
        "than its end: truncate this output at the tail and the recognised "
        "first line is still there. Every line "
        "contains _fts and not one of them is about FTS. Held alongside "
        "expression_index_named_fts because the two reach the same name by "
        "different routes, and because the excerpt is what the old criterion "
        "needed in order to fire: the whole capture never did.",
    ),
    Sample(
        "index_named_fts_message", OBSERVED,
        "\n".join(f"row {n} missing from index fts5: corrupt" for n in (1, 2, 3)),
        "An ordinary expression index whose NAME IS AN FTS MESSAGE, over a "
        "table in a database that holds no FTS of any kind. The sample that "
        "refuted the first rewrite of this criterion. Abolishing the `_fts` "
        "test removed a needle that read a substring of a name and replaced it "
        "with needles that read a whole name, which is the same mistake with a "
        "longer string: SQLite prints an object's name UNQUOTED into its "
        "findings, so an index called `fts5: corrupt` reproduces that needle "
        "exactly rather than merely containing it. Every FTS needle was "
        "reachable this way, `malformed inverted index for fts` and "
        "`fts5: checksum mismatch` included, by naming the index after the one "
        "wanted. This is a whole capture and not an excerpt: the index holds "
        "the right NUMBER of entries and the wrong entries, so no count line "
        "precedes these three. It classifies UNKNOWN, which is the fix: the "
        "needles are now held to the START of the message, and a finding line "
        "begins with what SQLite chose to say rather than with what someone "
        "chose to call an object.",
    ),
    Sample(
        "index_named_fts_message_beside_real_fts_damage", OBSERVED,
        "\n".join(f"row {n} missing from index fts5: corrupt" for n in (1, 2, 3))
        + "\nmalformed inverted index for FTS5 table main.messages_fts",
        "ONE database carrying both at once, and the sample that shows what the "
        "verdict is for. Three lines where `fts5: corrupt` is an index name and "
        "one where SQLite's own FTS code reported corruption. Before the "
        "positional rule the two were indistinguishable: this capture and the "
        "one above it both returned damaged FTS_CORRUPTION with nothing "
        "unclassified, so the class carried no information and nothing in the "
        "output marked the misreading. Now the genuine line is the only one "
        "that produces the class and the three names are reported as unread, "
        "which is the difference the parser is supposed to be able to state.",
    ),
    Sample(
        "not_a_database_via_stdout", OBSERVED, "",
        "What a caller that captures stdout gets from `sqlite3 <file> 'PRAGMA "
        "integrity_check;'` on a file that is not a database: nothing. The "
        "message goes to stderr and stdout stays empty. The exit status does "
        "not make up for it: a binary file exits 1, while a file of ASCII text "
        "is read as a SQL script and exits 0, so a caller can be handed an "
        "empty capture and a successful exit on a file that is not a database "
        "at all. This is why an empty "
        "capture cannot be read as an absence of damage.",
    ),
    Sample(
        "not_a_database_message", OBSERVED, "file is not a database",
        "The same failure seen through the error channel, which is the only "
        "channel it ever arrives on: in Python it is the message of the "
        "DatabaseError the PRAGMA raises.",
    ),
    Sample(
        "malformed_schema_message", OBSERVED,
        'malformed database schema (t) - near "(": syntax error',
        "Also an exception message rather than output. The database opens; the "
        "schema will not parse, so integrity_check never runs at all.",
    ),
    Sample(
        "disk_image_malformed_message", OBSERVED,
        "database disk image is malformed",
        "A file truncated below its page count, again raised rather than "
        "returned. No rule here recognises it, which is honest: it names "
        "damage without saying where.",
    ),
    Sample(
        "empty", SYNTHETIC, "",
        "Nothing captured at all. Indistinguishable as text from the observed "
        "stdout case above, which is the point.",
    ),
    Sample(
        "whitespace_only", SYNTHETIC, "   \n\t\n  ",
        "A capture that holds only layout. Same verdict as empty: no output.",
    ),
    Sample(
        "header_only", SYNTHETIC, "*** in database main ***",
        "The header with nothing under it. Not observed from SQLite, and no run "
        "here produced it: the header is prefixed to the b-tree check's "
        "findings and comes back with them, so a read cut off between the two "
        "is not a shape any measurement supports. Written to pin what this "
        "parser does with it, and to claim nothing further.",
    ),
    Sample(
        "header_then_ok", SYNTHETIC, "*** in database main ***\nok",
        "Never observed. SQLite printed a bare ok for every clean database "
        "tried and a header only when it had findings. Kept as a synthetic "
        "sample precisely so no test can claim SQLite guarantees this shape.",
    ),
    Sample(
        "unrecognised_damage", SYNTHETIC,
        "freelist count wrong: expected 7 got 9",
        "Plausible damage that no rule here reads. Whether SQLite "
        "words it this way is not the point: the parser must not "
        "report a clean database because a line was unfamiliar.",
    ),
    Sample(
        "incident_root", OBSERVED, _INCIDENT_TEXT,
        "The shape the original incident arrived in: both canonical "
        "signatures together on a production database. The page "
        "numbers and rowid are the incident's own, not reproduced. "
        "mixed_known_and_unknown extends this with two residue "
        "lines.",
    ),
    Sample(
        "mixed_known_and_unknown", SYNTHETIC,
        _INCIDENT_TEXT + "\n"
        "freelist count wrong: expected 7 got 9\n"
        "Page 41: never used",
        "Both canonical signatures alongside two lines nothing "
        "recognises. Built by extending incident_root with residue "
        "rather than restating the text.",
    ),
)

BY_NAME = {s.name: s for s in CORPUS}
