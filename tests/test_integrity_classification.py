"""TASK-25 / SQL-02: an empty capture, unnamed damage and CLEAN are three things.

The classifier used to answer ``classes: []`` to all of: nothing captured, a
header with no findings under it, real page-level damage it could not read, and
a mixed output whose unrecognised half it discarded. Four different situations,
one answer, and the answer looked most like "no signatures found" at exactly
the moment someone needed to hear "your database is damaged".

These tests drive the corpus in tests/integrity_corpus.py, which labels each
sample as observed from a real SQLite run or written synthetically. Where a
test rests on what SQLite actually does, it uses an observed sample and says
so; where it rests only on what this parser does with a given shape, it uses a
synthetic one and claims nothing further.

The last section is the exception and says so there: four tests build a real
database, damage it and read the pragma in process, so that the two captures
TASK-24 turns on are re-derived rather than only recalled.
"""

import json
import re
import sqlite3

import pytest

from pyteman.sqlitekit import integrity
from pyteman.sqlitekit.integrity import classify_integrity

from integrity_corpus import BY_NAME, CORPUS, OBSERVED, SYNTHETIC

STATUSES = {integrity.CLEAN, integrity.DAMAGED, integrity.UNKNOWN,
            integrity.INCONCLUSIVE, integrity.NO_OUTPUT}

#: Hoisted because four tests parametrize over the whole corpus, and a list
#: rebuilt at each one drifts silently if a sample is ever renamed in only some.
CORPUS_IDS = [s.name for s in CORPUS]


def sample(name):
    return BY_NAME[name].text


@pytest.mark.parametrize("s", CORPUS, ids=CORPUS_IDS)
def test_every_sample_gets_a_status_and_keeps_its_text(s):
    """The two invariants that hold whatever the verdict.

    ``raw`` is compared by identity rather than by value, and never after
    stripping: a caller reaching for ``raw`` is reaching past this parser's
    reading of the output to the output itself, and a parser that trims or
    rebuilds what it hands back has quietly become the only account of what the
    tool said. Identity is the exact promise the module makes, so it is the one
    tested.

    For the two empty samples the identity check proves nothing on CPython,
    where ``""`` is a single interned object, so a parser that returned a fresh
    empty string would pass here. The samples that carry text are what give
    this assertion its teeth.
    """
    res = classify_integrity(s.text)
    assert res["status"] in STATUSES
    assert res["raw"] is s.text
    assert set(res) == {"status", "classes", "unclassified", "diagnosis", "raw"}


@pytest.mark.parametrize("s", CORPUS, ids=CORPUS_IDS)
def test_every_output_carries_a_diagnosis(s):
    """AC 2. Every verdict says something about itself, pass included.

    A blank diagnosis is the silence this task is removing: it renders in a
    report as an empty cell, which reads as nothing to worry about.

    The second half of that criterion is no false precision, which is checked
    here across every sample rather than at the one verdict it is easiest to
    overstate. Nothing this parser does confirms anything: it reads text. A
    diagnosis that called a verdict verified or confirmed would be promising
    that something was checked against the database, when what was checked is a
    string against a line SQLite happened to print.
    """
    res = classify_integrity(s.text)
    assert res["diagnosis"].strip(), f"{s.name} produced an empty diagnosis"

    lowered = res["diagnosis"].lower()
    for word in ("verified", "confirms that", "definitely", "guaranteed"):
        assert word not in lowered, (
            f"the diagnosis for {s.name} claims more than a text match gives")


@pytest.mark.parametrize("s", CORPUS, ids=CORPUS_IDS)
def test_classes_are_populated_exactly_when_damage_was_recognised(s):
    """The invariant that makes ``status`` safe to branch on alone."""
    res = classify_integrity(s.text)
    assert bool(res["classes"]) is (res["status"] == integrity.DAMAGED)


def test_the_three_empty_looking_inputs_are_three_verdicts():
    """The task in one assertion: these used to be indistinguishable.

    Nothing captured, a capture carrying only the header, and a capture
    carrying damage no rule reads. An operator does something different in each
    case, and the old ``classes: []`` sent all three to the same place.
    """
    verdicts = {name: classify_integrity(sample(name))["status"]
                for name in ("empty", "whitespace_only", "header_only",
                             "unrecognised_damage", "orphan_pages")}
    assert verdicts["empty"] == integrity.NO_OUTPUT
    assert verdicts["whitespace_only"] == integrity.NO_OUTPUT
    assert verdicts["header_only"] == integrity.INCONCLUSIVE
    assert verdicts["unrecognised_damage"] == integrity.UNKNOWN
    assert verdicts["orphan_pages"] == integrity.UNKNOWN


def test_the_header_is_recognised_by_shape_whatever_database_it_names():
    """Observed: the word in the middle of the header is not always ``main``.

    A file checked through ATTACH is reported under ``*** in database aux1
    ***``. Matching the header literally would file that line as a finding,
    with two consequences: the diagnosis would count one unread line more than
    arrived, and INCONCLUSIVE would be unreachable for any database not called
    main, because a header-only capture would always hold a "finding". That is
    what the rejected alternative does when substituted, not a fault any
    released version of this module shipped.
    """
    s = BY_NAME["attached_database_header"]
    assert s.origin == OBSERVED
    res = classify_integrity(s.text)

    assert res["status"] == integrity.UNKNOWN
    assert res["unclassified"] == ["Page 3: never used"]

    # The same header alone, taken from the observed text rather than invented,
    # reaches the verdict that header_only pins for main.
    header = s.text.splitlines()[0]
    assert classify_integrity(header)["status"] == integrity.INCONCLUSIVE


def test_a_line_shaped_like_the_header_but_not_one_stays_a_finding():
    """The shape match is a prefix and a suffix, not a substring search.

    A finding that happens to mention the header's wording is still a finding.
    This is what keeps the loosened match from swallowing evidence.
    """
    res = classify_integrity("in database main is where the damage is")
    assert res["status"] == integrity.UNKNOWN
    assert res["unclassified"] == ["in database main is where the damage is"]


@pytest.mark.parametrize("line", [
    # Ends with the suffix, and holds the whole prefix without starting with
    # it. Only ``startswith`` fails this one; ``_HEADER_PREFIX in line`` does
    # not, which is the substring search the docstring above rules out.
    "damage found: *** in database main ***",
    # Starts with the prefix and holds the whole suffix without ending with it.
    "*** in database main *** extra",
])
def test_each_half_of_the_header_shape_is_required(line):
    """Both conjuncts, and both as position rather than presence.

    The test above fails a line that has neither half. These two each hold both
    halves as text while satisfying only one of them in place, so they fail
    four ways of loosening the match: dropping either conjunct, and weakening
    either one from a position test to ``in``. A header wrongly recognised
    costs the line itself, which leaves ``unclassified`` without evidence that
    did arrive.
    """
    res = classify_integrity(line)
    assert res["status"] == integrity.UNKNOWN
    assert res["unclassified"] == [line]


def test_an_empty_capture_and_an_empty_file_are_opposite_verdicts():
    """Both observed, and the trap the whole module is shaped around.

    A zero-byte file is a valid empty database and passes the check. A file
    that is not a database produces no stdout at all, because the message goes
    to stderr. The exit status does not separate them either: a file of ASCII
    text that is not a database is read as a SQL script and exits 0, so the
    caller is handed an empty capture and a success. The emptier input is the
    healthy one, and a parser that reads "nothing came back" as "nothing is
    wrong" gets the destroyed database exactly backwards.
    """
    assert BY_NAME["empty_file_is_clean"].origin == OBSERVED
    assert BY_NAME["not_a_database_via_stdout"].origin == OBSERVED

    assert classify_integrity(
        sample("empty_file_is_clean"))["status"] == integrity.CLEAN
    assert classify_integrity(
        sample("not_a_database_via_stdout"))["status"] == integrity.NO_OUTPUT


def test_clean_is_reported_only_for_the_expected_positive_output():
    """CLEAN is earned by one exact output and never inferred.

    Anything else that happens to carry no recognised signature is not a pass:
    it is an absence of recognition, which is what UNKNOWN and INCONCLUSIVE are
    for.
    """
    assert classify_integrity("ok")["status"] == integrity.CLEAN
    assert classify_integrity("  ok  \n")["status"] == integrity.CLEAN
    for name in ("header_only", "header_then_ok", "unrecognised_damage",
                 "empty", "orphan_pages"):
        assert classify_integrity(sample(name))["status"] != integrity.CLEAN


def test_header_and_ok_together_is_not_claimed_to_be_clean_or_damaged():
    """A shape nobody observed, so this pins the parser and not SQLite.

    Every clean database tried printed a bare ``ok``, and the header appeared
    only above real findings. Reporting this shape as CLEAN would be inventing
    a guarantee; reporting it as UNKNOWN with the line kept says what is true,
    that something arrived which was not recognised.
    """
    assert BY_NAME["header_then_ok"].origin == SYNTHETIC
    res = classify_integrity(sample("header_then_ok"))
    assert res["status"] == integrity.UNKNOWN
    assert res["unclassified"] == ["ok"]


def test_unrecognised_lines_are_all_kept_and_in_order():
    """Observed output: one line read, sixty kept.

    The sixty ``row N missing`` lines are the bulk of what SQLite said and the
    old parser dropped every one of them. They are the part an investigation
    actually needs: which rows, and how many.

    What is pinned is that every line survives and keeps its position, not that
    it survives byte for byte. These lines carry no surrounding whitespace, so
    the two are indistinguishable here; the test below is where the difference
    is stated, on input where it shows.
    """
    s = BY_NAME["index_count_with_residue"]
    assert s.origin == OBSERVED
    res = classify_integrity(s.text)

    assert res["status"] == integrity.DAMAGED
    assert res["classes"] == ["CANONICAL_INDEX_COUNT"]
    assert len(res["unclassified"]) == 60
    assert res["unclassified"][0] == "row 201 missing from index idx_messages_session_id"
    assert res["unclassified"][-1] == "row 260 missing from index idx_messages_session_id"
    # The three above are entailed by the comparison below and are kept anyway,
    # because they run first and a failure reports the one line that differs
    # rather than sixty. Ordering is not what they pin: these rows are equal in
    # length with the numeral at a fixed offset, so lexicographic order is
    # numeric order here and a parser that sorted would satisfy all four. The
    # test below, on a sample whose lines do reorder, is what pins that.
    assert res["unclassified"] == s.text.splitlines()[1:]


def test_unclassified_holds_normalised_lines_while_raw_holds_the_capture():
    """The two fields make different promises, and only one of them is integral.

    Classification strips each line before reading it, and it is the stripped
    line that is kept, so ``unclassified`` is normalised rather than
    reproduced: what survives is the finding and not the layout it arrived in.
    ``raw`` is the integral copy and is the field to reach for when the layout
    itself is the question.

    This is pinned because the difference is invisible on real SQLite output,
    where the lines carry no surrounding whitespace, and a document is the only
    other place it was written down. The documents said ``verbatim`` of
    ``unclassified`` until TASK-24; the semantics are the ones measured here
    and were not changed to suit the prose.
    """
    text = "  mystery  \n\t\tsecond finding \n"
    res = classify_integrity(text)

    assert res["unclassified"] == ["mystery", "second finding"]
    assert res["raw"] is text

    # Blank lines are dropped rather than kept as empty findings, which is what
    # keeps a trailing newline from being counted in the diagnosis.
    assert "2 line(s)" in res["diagnosis"]


def test_a_mixed_output_reports_both_halves():
    """Recognised signatures and unread lines are not exclusive.

    A verdict that named the signatures and said nothing about the remaining
    lines would be the old discard with a status field bolted on.
    """
    res = classify_integrity(sample("mixed_known_and_unknown"))
    assert res["status"] == integrity.DAMAGED
    assert res["classes"] == ["CANONICAL_INDEX_COUNT", "CANONICAL_ROWID_DISORDER"]
    # This is also where SQLite's order is pinned, rather than in the sixty-row
    # sample above: "Page" sorts ahead of "freelist", so a parser that sorted
    # the unread lines fails here and only here.
    assert res["unclassified"] == ["freelist count wrong: expected 7 got 9",
                                   "Page 41: never used"]
    assert "2 further line(s)" in res["diagnosis"]


def test_the_incident_signature_still_classifies_as_it_did():
    """Observed reproduction of the original incident's root signature.

    TASK-25 changes the response shape, not the classification. This is the
    regression guard for that claim on the one output the CANONICAL_* names
    were coined for.
    """
    s = BY_NAME["rowid_disorder"]
    assert s.origin == OBSERVED
    res = classify_integrity(s.text)
    assert res["classes"] == ["CANONICAL_ROWID_DISORDER"]
    assert res["status"] == integrity.DAMAGED


def test_error_channel_messages_classify_as_they_did():
    """The two signatures that only ever arrive as exception text.

    Observed: both make the PRAGMA raise, so they reach this parser only
    because a caller caught the error and passed its message on.
    """
    for name, expected in (("not_a_database_message", "NOTADB"),
                           ("malformed_schema_message", "SCHEMA")):
        assert BY_NAME[name].origin == OBSERVED
        res = classify_integrity(sample(name))
        assert res["classes"] == [expected]
        assert res["status"] == integrity.DAMAGED


def test_a_malformed_disk_image_is_unknown_rather_than_unremarkable():
    """Observed, and named by no signature: damage stated without a location.

    It has to land somewhere that is not silence. UNKNOWN is the honest place:
    the database is broken and this parser cannot say how.
    """
    assert BY_NAME["disk_image_malformed_message"].origin == OBSERVED
    res = classify_integrity(sample("disk_image_malformed_message"))
    assert res["status"] == integrity.UNKNOWN
    assert res["unclassified"] == ["database disk image is malformed"]


#: The three observed captures in which SQLite's FTS code reported corruption.
#: Parametrized rather than asserted one by one so that a sample this parser
#: stops reading fails by name rather than inside a loop.
#:
#: The list is not a needle-by-needle map and should not be read as one. Two of
#: the three are read by the same needle, which is deliberate: they differ only
#: in the module digit, and holding both is what keeps a needle narrowed to
#: FTS5 from silently dropping the older modules. The remaining needle,
#: `fts5: checksum mismatch`, is absent here because its only sample is
#: synthetic while this test asserts its samples are observed captures; it is
#: exercised on its own below, so that it cannot be deleted as dead code with
#: the suite green.
FTS_CORRUPTION_SAMPLES = [
    "fts5_corruption",
    "fts5_malformed_inverted_index",
    "fts4_malformed_inverted_index",
]


@pytest.mark.parametrize("name", FTS_CORRUPTION_SAMPLES)
def test_a_message_the_fts_module_wrote_is_read_as_fts_damage(name):
    """TASK-24 AC 1, the half that has to keep working.

    Each of these is an observed capture in which the FTS module itself
    reported corruption, so FTS_CORRUPTION is a reading of what SQLite wrote
    rather than an inference from a table name. The FTS4 sample is here because
    the needle spans the module digit: narrowed to FTS5 it would stop reading
    the older modules, and nothing in the message would announce it.
    """
    assert BY_NAME[name].origin == OBSERVED
    res = classify_integrity(sample(name))
    assert res["status"] == integrity.DAMAGED
    assert "FTS_CORRUPTION" in res["classes"], (
        f"{name} is a message SQLite's FTS code wrote and is no longer read")


def test_the_needle_no_capture_backs_is_still_exercised_by_its_format_string():
    """The one needle of the three that nothing here reproduced.

    FTS5 emits this from its own ``integrity-check`` command, which raised
    ``database disk image is malformed`` on every damaged database tried here,
    so the sample carries the format string read out of the library and is
    labelled SYNTHETIC for exactly that reason. The needle is kept anyway,
    because the input contract is whatever the caller captured and a caller
    running that command is inside it.

    Kept out of the parametrized test above, which asserts its samples are
    observed captures, and written separately rather than left out: a needle
    that no test exercises can be deleted as dead code with the suite green,
    and the other three needles keep FTS_CORRUPTION in every derived list, so
    nothing else notices its absence.
    """
    s = BY_NAME["fts5_checksum_mismatch"]
    assert s.origin == SYNTHETIC
    res = classify_integrity(s.text)
    assert res["status"] == integrity.DAMAGED
    assert res["classes"] == ["FTS_CORRUPTION"]


@pytest.mark.parametrize(
    "name", ["expression_index_named_fts", "btree_index_named_fts"])
def test_an_ordinary_index_named_fts_is_not_reported_as_fts_damage(name):
    """TASK-24 AC 1, and the defect this task exists for.

    The old criterion fired when no other signature matched and every finding
    line contained ``_fts``, which decided a class from a property of the whole
    capture where every other class is decided by reading one line. ``_fts`` is
    a string a user chooses, so the criterion reported confirmed FTS damage for
    an ordinary index over a table with no FTS in it anywhere.

    Both samples reach that name by different routes, and how each relates to
    the capture it came from is worth keeping in view. The expression index is
    a whole capture: the rows were updated rather than inserted while the index
    was hidden, so the index kept the right number of entries, the count check
    printed nothing, and there is no recognised line anywhere in the output to
    mask the misreading. The b-tree index is an excerpt, and had to be, because
    its full capture opens with ``wrong # of entries in index idx_fts``, which
    a signature matches; the excerpt is the shape the old criterion needed in
    order to fire at all, since the whole capture never did.

    The verdict for both is now UNKNOWN, which is the cautious answer AC 2 asks
    for: the text did not establish FTS damage, and it did not establish
    anything else either.
    """
    s = BY_NAME[name]
    assert s.origin == OBSERVED
    res = classify_integrity(s.text)

    assert res["status"] == integrity.UNKNOWN
    assert res["classes"] == [], (
        "a class was derived from an index name, which is what TASK-24 removed")
    assert res["unclassified"] == s.text.splitlines()
    assert "fts" not in res["diagnosis"].lower(), (
        "the diagnosis volunteers FTS for a capture that only names an index")


def test_a_message_saying_the_check_could_not_run_is_not_a_finding():
    """TASK-24 AC 2, at the sharpest point on the scale.

    ``unable to validate the inverted index for FTS5 table main.messages_fts``
    names FTS5 twice and reports nothing: its entire content is that the check
    did not complete. The old criterion read it as confirmed FTS damage,
    because the table name contains ``_fts``.

    The sample is synthetic and that is load-bearing. The format string is
    genuine, enumerated from the library in use, but it is emitted when the
    check fails for a reason that is not corruption and nothing here produced
    one, so this pins what the parser does with the shape and claims nothing
    about how often SQLite emits it.
    """
    s = BY_NAME["unable_to_validate_fts_message"]
    assert s.origin == SYNTHETIC
    res = classify_integrity(s.text)
    assert res["status"] == integrity.UNKNOWN
    assert res["classes"] == [], (
        "a message reporting that nothing was checked is being read as damage")


def test_the_fts5_prefix_alone_is_not_read_as_damage():
    """Why ``fts5: `` is not a needle, though it is shorter than three needles.

    The prefix marks which module spoke, not what it said. This capture is an
    observed ``fts5:`` message from an UNDAMAGED database, reached by running a
    MATCH whose expression does not parse, so a parser that matched the prefix
    would report corruption for a typo in a query.
    """
    s = BY_NAME["fts5_syntax_error_message"]
    assert s.origin == OBSERVED
    assert classify_integrity(s.text)["status"] == integrity.UNKNOWN


def _skeleton(text):
    """A capture with its rowid and quoted names blanked out.

    What is left is the sentence SQLite's format string produced. Two captures
    with the same skeleton differ only in the values interpolated into it.

    The two slots of ``fts5: missing row %lld from content table %s`` are
    blanked, and nothing else is. Blanking every run of digits would be shorter
    and would reach one digit too many: the module number in ``fts5:`` is part
    of the sentence rather than a value interpolated into it, so the looser
    form equates an FTS5 message with the FTS4 spelling of it, and the one
    assertion whose job is to prove two sentences identical would pass on a
    pair that differs in which module wrote them.
    """
    return re.sub(r"row \d+|'[^']*'", "?", text)


def test_the_missing_row_sentence_arrives_from_a_healthy_and_a_damaged_database():
    """TASK-24 AC 2, and the needle this task removed after measuring it.

    ``fts5: missing row %lld from content table %s`` was matched as
    FTS_CORRUPTION until both halves of this pair were captured. One is a
    database with a row deleted out of a shadow table. The other has nothing
    wrong with it: an external-content index out of step with its content, on
    which ``integrity_check``, ``quick_check`` and FTS5's own
    ``integrity-check`` all returned ok while an ordinary MATCH raised this.

    The ambiguity is asserted rather than described. Blank the rowid and the
    quoted table name and the two captures are the same sentence, so the only
    thing that could separate them is whether that name belongs to a shadow
    table. That takes the schema this parser is not given, and reading it off
    the name is what TASK-24 exists to remove, so both report UNKNOWN.
    """
    damaged = BY_NAME["fts5_missing_content_row_message"]
    healthy = BY_NAME["fts5_missing_row_from_healthy_index"]
    assert damaged.origin == OBSERVED and healthy.origin == OBSERVED

    assert _skeleton(damaged.text) == _skeleton(healthy.text), (
        "the pair no longer shows the ambiguity the needle was removed for, so "
        "one of the two captures was edited and the argument no longer holds")

    for s in (damaged, healthy):
        res = classify_integrity(s.text)
        assert res["status"] == integrity.UNKNOWN, (
            f"{s.name} is read as damage by text that does not establish it")
        assert res["unclassified"] == [s.text]


def test_declining_that_sentence_costs_no_coverage_of_the_damaged_database():
    """Removing a needle is only safe if the damage is still named elsewhere.

    The database behind the damaged half of the pair above is reported by
    ``integrity_check`` as ``malformed inverted index for FTS5 table
    main.messages_fts``, which the first FTS needle reads. The corruption is
    still classified; what changed is that it is named from the check that
    examined the index rather than from a query a healthy database can also
    fail.
    """
    res = classify_integrity(sample("fts5_malformed_inverted_index"))
    assert res["status"] == integrity.DAMAGED
    assert res["classes"] == ["FTS_CORRUPTION"]


def test_a_format_this_build_cannot_read_is_not_read_as_damage():
    """The third near miss, and the one that most resembles a finding.

    ``invalid fts5 file format (found 99, expected 4 or 5) - run 'rebuild'`` is
    written by FTS5's own code and ends in an instruction to rebuild, which
    reads like a repair order. What it reports is that this build does not
    recognise the index format it found, which a database written by a NEWER
    FTS5 produces with nothing wrong with it. Matching it would report
    corruption for ordinary version skew.

    Synthetic, and the label is doing its usual work: the format string is
    enumerated from the library in use and the numbers in it are chosen, so
    this pins what the parser does with the shape and claims nothing about how
    the message arrives.
    """
    s = BY_NAME["invalid_fts5_file_format_message"]
    assert s.origin == SYNTHETIC
    assert classify_integrity(s.text)["status"] == integrity.UNKNOWN


def test_real_fts_corruption_is_read_even_when_another_signature_matched():
    """TASK-24 AC 1, the mixed case, and the failure that actually mattered.

    The old criterion required that NO other signature had matched, so a
    database damaged in two ways at once classified as CANONICAL_INDEX_COUNT
    and the one line SQLite's FTS code wrote was filed under ``unclassified``.
    That is the dangerous direction: a criterion that reports FTS damage on a
    name is embarrassing, while one that goes quiet on FTS damage precisely
    when the database has more than one fault fails where nobody is looking.

    Both classes are now reported from the same capture, because each line is
    read on its own. The five lines no signature reads stay in ``unclassified``
    where they belong.
    """
    s = BY_NAME["mixed_fts_and_index_count"]
    assert s.origin == OBSERVED
    res = classify_integrity(s.text)

    assert res["classes"] == ["CANONICAL_INDEX_COUNT", "FTS_CORRUPTION"]
    assert len(res["unclassified"]) == 5
    assert all("missing from index" in l for l in res["unclassified"])


def test_one_unrelated_line_no_longer_suppresses_real_fts_corruption():
    """The other half of the old criterion's conjunction, pinned separately.

    ``all("_fts" in l for l in findings)`` meant a single line without ``_fts``
    was enough to silence it. Here the FTS5 message arrives next to page-level
    damage that no signature reads, which under the old criterion produced an
    empty ``classes`` and said nothing about FTS at all.
    """
    res = classify_integrity(
        "Page 3: never used\n"
        + sample("fts5_malformed_inverted_index"))
    assert res["classes"] == ["FTS_CORRUPTION"]
    assert res["unclassified"] == ["Page 3: never used"]


def test_fts_damage_can_arrive_with_no_fts_anywhere_in_the_text():
    """TASK-24 AC 2. The converse is not covered and cannot be.

    An FTS5 table's shadow tables are ordinary b-trees, so some damage to them
    prints as ordinary b-tree damage. Only some, and the corpus holds both
    halves for one table: a rowid disorder in the content table of
    ``messages_fts`` printed this capture, while deleting a row out of that same
    table printed ``malformed inverted index``, which a needle reads. So this
    capture is real FTS damage whose text names no FTS at all, and it
    classifies as CANONICAL_ROWID_DISORDER, which is exactly what the text
    supports and is not the whole truth about the database.

    So the absence of FTS_CORRUPTION is not evidence that FTS is healthy.
    Nothing in the capture distinguishes this from the same damage to an
    ordinary table: telling them apart needs the schema, which this function is
    not given, and deciding it from the message is the mistake this task
    removed. The claim is therefore narrowed rather than the input widened.
    """
    s = BY_NAME["fts5_shadow_table_btree_damage"]
    assert s.origin == OBSERVED
    res = classify_integrity(s.text)

    assert res["classes"] == ["CANONICAL_ROWID_DISORDER"]
    assert "FTS_CORRUPTION" not in res["classes"]


def test_an_fts_verdict_scopes_its_claim_to_the_index():
    """No false precision, now that the class is a reading rather than a guess.

    The sentence has to do two things at once: say that this came from SQLite's
    own FTS code rather than from a name, which is the whole content of the
    change, and stop there, because FTS corruption is a statement about the
    index and not about the rest of the database.

    The sentence is also required NOT to appear when the class is absent, which
    is what keeps it a statement about this verdict rather than a standing
    caveat the reader learns to skip.
    """
    diagnosis = classify_integrity(sample("fts5_corruption"))["diagnosis"]
    assert "FTS_CORRUPTION" in diagnosis
    assert "index name" in diagnosis
    assert "says nothing about the rest" in diagnosis

    other = classify_integrity(sample("rowid_disorder"))["diagnosis"]
    assert "FTS_CORRUPTION" not in other


@pytest.mark.parametrize("bad", [None, b"ok", 0, ["ok"], object()])
def test_a_non_string_input_raises_a_typeerror_that_names_the_alternative(bad):
    """Kept apart from the empty string, which is a legitimate input.

    ``None`` is the likely accident: a capture helper that returned nothing.
    Left alone it fails on ``.splitlines()`` inside this function, with an
    ``AttributeError`` naming neither the function nor the argument, and the
    caller had no way to tell that from damage. The error says what to pass
    instead, because the right value is not obvious: '' means something
    specific here.
    """
    with pytest.raises(TypeError) as excinfo:
        classify_integrity(bad)
    message = str(excinfo.value)
    assert "classify_integrity" in message
    # The phrase, not the bare type name: "int" is a substring of
    # "classify_integrity" itself, so the loose form passes on a message that
    # never interpolated anything.
    assert f"got {type(bad).__name__}." in message
    assert "NO_OUTPUT" in message, "the error did not say what to pass instead"


def test_the_empty_string_is_accepted_rather_than_rejected():
    """The other side of the TypeError: '' is data, not a mistake."""
    res = classify_integrity("")
    assert res["status"] == integrity.NO_OUTPUT
    assert res["raw"] == ""


def test_the_no_output_diagnosis_sends_the_reader_to_the_error_channel():
    """The remedy differs from INCONCLUSIVE, which is why they are separate.

    Nothing came back: look where the message actually went. Observed, for a
    file that is not a database, that is stderr and a non-zero exit.

    Asserting only that the two sentences differ would pass on any two strings,
    so each is pinned to the thing it actually tells an operator to do. That is
    the whole justification for keeping the statuses apart: if both sentences
    said the same thing, one status would do. The pins are the nouns each
    remedy turns on rather than the wording around them, so that rephrasing
    either sentence stays free and dropping a remedy does not.
    """
    no_output = classify_integrity(sample("empty"))["diagnosis"]
    inconclusive = classify_integrity(sample("header_only"))["diagnosis"]

    # NO_OUTPUT: the message went somewhere this capture did not look.
    assert "stderr" in no_output
    assert "exit status" in no_output
    assert "stderr" not in inconclusive

    # INCONCLUSIVE: the text arrived and carries no verdict, so it names what
    # did arrive and sends the reader back to the capture, not to the database.
    assert "header" in inconclusive
    assert "header" not in no_output
    assert "capture" in inconclusive


def test_an_unknown_verdict_does_not_claim_the_database_is_damaged():
    """UNKNOWN means unread, and unread is not the same as broken.

    The error channel is the reason this matters rather than being a nicety.
    ``PRAGMA integrity_check`` raises ``OperationalError('database is locked')``
    when another connection holds an EXCLUSIVE lock, and OperationalError is a
    DatabaseError, so that message arrives through exactly the route the two
    real error-channel signatures arrive through. The database is healthy and
    the check simply never ran. A diagnosis that read "the database is damaged
    in a way this parser cannot name" would be this module's own stated failure
    mode inverted: reporting a disaster to someone who has none, having spent
    the whole design avoiding the reverse.
    """
    for text in ("database is locked",
                 "unable to open database file",
                 "attempt to write a readonly database"):
        res = classify_integrity(text)
        assert res["status"] == integrity.UNKNOWN
        assert res["unclassified"] == [text]

        diagnosis = res["diagnosis"].lower()
        for claim in ("is damaged", "is corrupt", "the database is"):
            assert claim not in diagnosis, (
                f"the unknown diagnosis asserts {claim!r} about a database "
                "whose check never ran")
        assert "error channel" in diagnosis


def test_the_class_list_is_ordered_deterministically():
    """``classes`` is sorted, and a set alone does not make it so.

    Every multi-class verdict reachable from the corpus has two members, and a
    two-element set of short strings iterates in whichever order the hashes
    fall, which is stable for a given PYTHONHASHSEED and is a coin flip across
    seeds: one such pair came out sorted under 27 of PYTHONHASHSEED 1 to 60 and
    unsorted under the other 33. The corpus holds two of these pairs since
    TASK-24 added the mixed FTS one, and a second coin flip is not a check on
    the first. So the corpus cannot tell a sorted list from an unsorted one,
    and would not reliably fail either way. Feeding the constructor a list
    instead removes the coin flip: a list's order is its own, and only sorting
    changes it.
    """
    res = integrity._verdict(integrity.DAMAGED, "", ["ZZZ", "AAA"])
    assert res["classes"] == ["AAA", "ZZZ"]
    assert "Recognised signature(s): AAA, ZZZ." in res["diagnosis"]


def test_a_status_that_is_equal_without_being_identical_is_still_diagnosed():
    """``_diagnose`` compares with ``==`` rather than ``is``, deliberately.

    A verdict that has been through JSON, or any transport that rebuilds its
    strings, comes back holding a status equal to the constant without being
    the same object. Under ``is`` it would match no branch, and what happens
    then is decided by the closing raise the test below pins: a transported
    verdict raises ValueError, so a status this module produced itself becomes
    a crash on the way back in. Without that raise it would instead reach the
    DAMAGED sentence, which answers "Recognised signature(s): ." and claims
    recognised damage while naming none. The two guards are written as a pair
    and only make sense read as one.

    The non-identity is asserted first. Without it this test passes vacuously
    the moment the interpreter happens to hand back the interned constant.
    """
    rebuilt = json.loads(json.dumps(integrity.UNKNOWN))
    if rebuilt is integrity.UNKNOWN:  # pragma: no cover - interning detail
        rebuilt = "".join(["unk", "nown"])
    assert rebuilt is not integrity.UNKNOWN
    assert rebuilt == integrity.UNKNOWN

    assert (integrity._diagnose(rebuilt, [], ["a line"])
            == integrity._diagnose(integrity.UNKNOWN, [], ["a line"]))


def test_an_unmodelled_status_is_refused_rather_than_described_as_damage():
    """The closing raise, which is what makes the ``==`` chain safe.

    A sixth status added without a sentence must stop here. Falling through to
    the DAMAGED text is the one outcome this field exists to prevent, so the
    guard is pinned rather than trusted, and the error names the status it
    could not describe.
    """
    with pytest.raises(ValueError) as excinfo:
        integrity._diagnose("corrupted_beyond_repair", [], [])
    message = str(excinfo.value)
    assert "corrupted_beyond_repair" in message


def test_signature_matching_is_first_hit_wins_in_the_declared_order():
    """One line, two needles, one class: the ordering decides which.

    ``out of order`` precedes ``wrong # of entries in index`` in _SIGNATURES,
    and a line naming an out-of-order rowid inside an index satisfies both. The
    comment on that tuple says the order is deliberate; this is what makes
    reordering it fail rather than silently reclassify the incident's own root
    signature.
    """
    both = "wrong # of entries in index idx_x: Rowid 5 out of order"
    res = classify_integrity(both)
    assert res["classes"] == ["CANONICAL_ROWID_DISORDER"]
    assert res["unclassified"] == [], "a matched line must not also be unread"


def test_every_needle_is_lowercase_because_matching_folds_the_line():
    """An invariant the table cannot state and a capital letter would break.

    Matching is ``needle in line.lower()``, so a needle carrying one uppercase
    character matches nothing and fails silently: the class simply stops being
    produced, with nothing in the tuple looking wrong.

    TASK-24 is what makes that worth pinning. The messages these needles read
    are mixed case on the wire, ``malformed inverted index for FTS5 table``
    among them, so pasting a newly observed message straight into the tuple is
    the natural next edit and is the one that breaks.
    """
    shouting = [n for n, _, _ in integrity._SIGNATURES if n != n.lower()]
    assert not shouting, (
        f"{shouting} can never match, because each line is lowercased before "
        "the needles are tried")


#: The needles held to the start of a message, derived rather than listed so
#: that a fourth one added to the table is carried into the tests below without
#: anyone remembering to add it here.
ANCHORED_NEEDLES = [n for n, _, mode in integrity._SIGNATURES
                    if mode == integrity._ANCHORED]


def test_the_table_declares_both_matching_modes_and_nothing_else():
    # The floor for the two parametrized tests below: both derive their cases
    # by filtering on a mode, so a mode renamed in the table empties the list
    # and every case passes by not existing. Set equality is what closes that
    # hazard, since it cannot hold unless some row still declares each mode.
    assert {m for _, _, m in integrity._SIGNATURES} == {
        integrity._ANCHORED, integrity._CONTAINED}, (
            "a mode renamed in the table empties a derived list and lets its "
            "parametrized cases pass by not existing")


@pytest.mark.parametrize("needle", ANCHORED_NEEDLES)
def test_an_index_named_after_an_fts_message_is_not_read_as_fts_damage(needle):
    """The defect that survived the first rewrite, pinned needle by needle.

    Abolishing the ``_fts`` criterion removed a rule that read a substring of a
    name and put in its place rules that read a whole name. SQLite prints an
    index name UNQUOTED into ``row N missing from index ...``, so an index
    called after one of these messages reproduces the needle exactly rather
    than merely containing it, and the line is then a b-tree finding reported
    as confirmed FTS corruption. Measured on SQLite 3.51.2 against a database
    holding no FTS at all: each of these needles was reachable this way, and
    the capture for `fts5: corrupt` is in the corpus as index_named_fts_message.

    Every needle is tried rather than the one that was captured, because the
    defect is a property of the matching rule and not of any single message. A
    needle added to the table without a thought for position fails here.
    """
    line = f"row 1 missing from index {needle}"
    assert needle in line, "the case no longer contains the needle it is about"
    res = classify_integrity(line)
    assert res["status"] == integrity.UNKNOWN, (
        f"an ordinary index named {needle!r} was read as {res['classes']}")
    assert res["classes"] == []
    assert res["unclassified"] == [line], (
        "the line has to come back unread rather than be dropped")


def test_a_genuine_fts_diagnostic_is_told_apart_from_an_index_named_after_one():
    """One real database, both shapes, and the discrimination that was absent.

    Before the positional rule these two captures returned the same verdict,
    damaged with FTS_CORRUPTION and nothing unclassified, so the class carried
    no information on either and no part of the output marked the misreading.
    Asserting the two verdicts DIFFER is what pins that, because each of them
    read alone can be satisfied by a rule that answers the same thing to
    everything.
    """
    names_only = classify_integrity(sample("index_named_fts_message"))
    both = classify_integrity(
        sample("index_named_fts_message_beside_real_fts_damage"))

    assert both["status"] == integrity.DAMAGED
    assert both["classes"] == ["FTS_CORRUPTION"]
    assert both["unclassified"] == sample(
        "index_named_fts_message").splitlines(), (
            "the three name lines are b-tree findings and have to be reported "
            "as unread rather than absorbed into the FTS class")

    assert (names_only["status"], names_only["classes"]) != (
        both["status"], both["classes"]), (
            "the capture with genuine FTS damage and the capture with only an "
            "index named after it still classify identically")


def test_an_index_name_cannot_take_a_line_away_from_the_class_it_deserved():
    """The second half of the same defect, and the direction that loses data.

    ``wrong # of entries in index fts5: corrupt`` is one finding about one
    ordinary index whose name is an FTS message. Under the unanchored table the
    FTS needle matched it and the ``break`` then hid CANONICAL_INDEX_COUNT, so
    the capture did not merely gain a class it had not earned: it LOST the one
    the line was actually about. A test asserting only that FTS is absent would
    pass on a parser that answered UNKNOWN here, which is why the right class
    is named.
    """
    res = classify_integrity("wrong # of entries in index fts5: corrupt")
    assert res["classes"] == ["CANONICAL_INDEX_COUNT"]


def test_a_name_inside_a_genuine_fts_message_does_not_win_over_it():
    """The precedence the table's ordering exists for, in the other direction.

    An FTS table can be called ``out of order``, and then a genuine FTS
    diagnostic about it carries a CANONICAL needle inside the text SQLite
    interpolated. The anchored needles are tried first precisely so the reading
    grounded in position beats the one that is free to match anywhere: this
    line is FTS damage, and the rowid disorder is a name.

    Unlike the others added with it, this one passes against the pre-fix table
    too, because the FTS needles preceded the CANONICAL needles there as well.
    It is kept as a guard on the ordering rather than as evidence for the fix:
    it fails if the CONTAINED rows are ever moved in front of the anchored ones,
    which is the edit that would quietly undo the precedence.
    """
    res = classify_integrity(
        "malformed inverted index for FTS5 table main.out of order")
    assert res["classes"] == ["FTS_CORRUPTION"]


@pytest.mark.parametrize("prefix", [
    "Parse error in 2nd command line argument: ",
    "Parse error near line 1: ",
    "Error near line 1: ",
    "Error near line 1 of /tmp/script.sql: ",
])
def test_a_known_shell_wrapper_does_not_cost_a_signature(prefix):
    """Anchoring the FTS needles must not break the shell as a capture path.

    This module documents the sqlite3 shell as one of the channels a capture
    arrives on, and the shell puts its own wrapper on anything it reports as an
    error: measured on shell 3.53.4, a kind and a locator before the message.
    An earlier note here concluded from that fact that the needles could not be
    held to the start of a line, which was the right premise and the wrong
    conclusion, since the wrapper is a closed family that comes off first.

    Both a wrapped and a bare line are checked, because a stripper that removed
    too much would satisfy the wrapped case alone. The bare half is checked
    once, by ``test_a_message_the_fts_module_wrote_is_read_as_fts_damage``,
    rather than again inside a parametrization it does not vary with: asserting
    it here would report one regression four times, from a test whose subject
    is wrappers.
    """
    assert classify_integrity(
        prefix + sample("fts5_malformed_inverted_index")
    )["classes"] == ["FTS_CORRUPTION"]


def test_the_wrapper_is_removed_for_matching_only_and_never_from_the_record():
    """``unclassified`` and ``raw`` are the record of the capture, not of the read.

    Stripping is an operation on a copy used to try the needles. A line nothing
    matches has to come back exactly as it arrived, wrapper included, because
    the wrapper says which channel the text came from and the next person to
    read an incident needs that as much as the message.
    """
    line = "Parse error near line 1: freelist count wrong: expected 7 got 9"
    res = classify_integrity(line)
    assert res["status"] == integrity.UNKNOWN
    assert res["unclassified"] == [line]
    assert res["raw"] == line


def test_an_unfamiliar_wrapper_costs_a_class_rather_than_inventing_one():
    """Which way the stripper fails, stated as a test rather than as a comment.

    The path in ``near line N of <path>`` is matched non-greedily, so it ends at
    the first colon FOLLOWED BY A SPACE rather than at the first colon: a path
    like ``/tmp/a:b.sql`` is consumed whole and costs nothing, and it takes a
    space after the colon to end the match early and leave part of the wrapper
    in front of the message. This test asserted the wrong trigger before it was
    run against the regex.

    The second case is the hazard the choice is made against, and it is a hazard
    only for the greedy form. ``something: malformed inverted index for FTS5
    table main.t`` is a message whose needle is not at its start, so it is not
    an FTS diagnostic by this module's rule. Stripping to the LAST colon-space
    would cut the message down to the needle and report FTS corruption from a
    line that never claimed it, which is the same fabrication from the other
    end. Both cases here report UNKNOWN: a class lost is the survivable error
    and a class invented is not.
    """
    early = classify_integrity(
        "Error near line 1 of /tmp/my file: v2.sql: fts5: corrupt something")
    assert early["status"] == integrity.UNKNOWN
    assert early["classes"] == []

    not_at_the_start = classify_integrity(
        "Error near line 1 of x.sql: something: malformed inverted index for "
        "FTS5 table main.t")
    assert not_at_the_start["status"] == integrity.UNKNOWN
    assert not_at_the_start["classes"] == []

    # And the path that merely contains a colon still costs nothing, which is
    # what makes the two assertions above a boundary rather than a blanket.
    assert classify_integrity(
        "Error near line 1 of /tmp/a:b.sql: fts5: corrupt something"
    )["classes"] == ["FTS_CORRUPTION"]


def test_a_signature_declaring_an_unknown_mode_raises_rather_than_going_quiet():
    """The guard that keeps a typo in the table from disabling a signature.

    A mode this code does not recognise has exactly one safe behaviour, and it
    is not ``False``. A needle that silently never matches reports UNKNOWN on
    real damage while every other test in this file stays green, which is the
    failure mode this whole tranche keeps finding: a guard that fails open.
    """
    with pytest.raises(ValueError) as excinfo:
        integrity._matches("fts5: corrupt", "somewhere", "a line", "a line")
    assert "somewhere" in str(excinfo.value)


@pytest.mark.parametrize("s", CORPUS, ids=CORPUS_IDS)
def test_the_corpus_labels_its_own_provenance(s):
    """The labelling is the acceptance criterion, so it is tested too.

    An unlabelled sample is worse than a missing one: it lets a later test
    assert that SQLite guarantees a shape that was made up here.
    """
    assert s.origin in (OBSERVED, SYNTHETIC)
    assert s.note.strip(), f"{s.name} does not say what it is for"


# ---------------------------------------------------------------------------
# Live SQLite: the two TASK-24 captures re-derived rather than recalled.
#
# Everything above drives frozen text, which is the right default. Versioning a
# corrupt database file produces a binary nobody can re-derive or review, and
# the corpus says so. But frozen text leaves one thing unchecked: it proves what
# this parser does with a recorded sentence, not that SQLite still writes that
# sentence. These four build the database, damage it and read it in process, so
# the input is whatever this SQLite printed just now.
#
# Only the two captures TASK-24 turns on are re-derived here. Making executable
# reproducers for the whole corpus is TASK-97 and is deliberately not started.
# ---------------------------------------------------------------------------

#: The name given to an ordinary b-tree index below. It is one of the module's
#: own FTS needles character for character, which is the entire point: SQLite
#: prints an index name UNQUOTED into its findings, so a name that IS a needle
#: reproduces that needle exactly rather than merely resembling it.
FTS_MESSAGE_AS_NAME = "fts5: corrupt"


def _fts5_available():
    con = sqlite3.connect(":memory:")
    try:
        con.execute("CREATE VIRTUAL TABLE probe USING fts5(body)")
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        con.close()


#: FTS5 is compiled into every build tried here, but it is an optional module
#: and a build without it would fail these for a reason that is not a defect in
#: this parser. Skipping is what tells the two apart.
needs_fts5 = pytest.mark.skipif(
    not _fts5_available(), reason="this SQLite build has no FTS5 module")


def _capture(con):
    """The text a caller reading the pragma's rows would assemble."""
    return "\n".join(row[0] for row in con.execute("PRAGMA integrity_check"))


def _index_out_of_step_with_its_expression(con, name, rows):
    """Damage an ORDINARY b-tree index by breaking a determinism promise.

    ``identity`` is registered ``deterministic=True``, which SQLite takes at its
    word: it stores the values the function returned and never recomputes them
    to check. Re-registering the same name with different behaviour leaves the
    stored keys disagreeing with what the table now computes, and the check
    reports every row as missing from the index.

    No FTS table is created and none exists in this database. ``name`` is only a
    name, and a name is all the findings will contain.
    """
    con.create_function("identity", 1, lambda x: x, deterministic=True)
    con.execute("CREATE TABLE ordinary(x)")
    con.executemany("INSERT INTO ordinary(x) VALUES (?)", [(n,) for n in rows])
    con.execute(f'CREATE INDEX "{name}" ON ordinary(identity(x))')
    con.commit()
    con.create_function("identity", 1, lambda x: x + 1, deterministic=True)


def _fts5_table_with_a_content_row_deleted(con):
    """Genuine FTS5 damage: a shadow-table row removed behind FTS5's back.

    The other half of the discrimination. The message this produces is written
    by the FTS module itself rather than interpolated from a name, and it is the
    one finding in these captures that FTS_CORRUPTION is entitled to.
    """
    con.execute("CREATE VIRTUAL TABLE messages_fts USING fts5(body)")
    con.executemany("INSERT INTO messages_fts(body) VALUES (?)",
                    [("alpha beta",), ("gamma delta",), ("epsilon zeta",)])
    con.commit()
    con.execute("DELETE FROM messages_fts_content WHERE id = 2")
    con.commit()


def _count_fault_on_a_named_index(path, name, with_fts):
    """Produce ``wrong # of entries in index <name>`` from a real database.

    A count fault rather than a value fault, and that difference decides which
    sentence SQLite prints. Rows inserted while a wrong index is present give
    the missing-row lines alone; rows inserted while the index is not in the
    schema AT ALL leave it short, and the check reports the count first. Hiding
    it takes ``writable_schema`` and a reopen, which is why this one needs a
    file: the schema is re-read on open, and an in-memory database does not
    survive being closed.

    The index's own rootpage is saved and restored. Reinserting the row with the
    table's rootpage instead would point the restored index at the wrong page
    and damage something other than what this is about.
    """
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE t(x)")
    con.execute(f'CREATE INDEX "{name}" ON t(x)')
    if with_fts:
        _fts5_table_with_a_content_row_deleted(con)
    con.commit()
    sql, rootpage = con.execute(
        "SELECT sql, rootpage FROM sqlite_schema WHERE type='index' AND name=?",
        (name,)).fetchone()
    con.close()

    con = sqlite3.connect(path)
    con.execute("PRAGMA writable_schema=ON")
    con.execute("DELETE FROM sqlite_schema WHERE type='index' AND name=?",
                (name,))
    con.commit()
    con.close()

    con = sqlite3.connect(path)
    con.executemany("INSERT INTO t(x) VALUES (?)", [(n,) for n in range(5)])
    con.commit()
    con.close()

    con = sqlite3.connect(path)
    con.execute("PRAGMA writable_schema=ON")
    con.execute(
        "INSERT INTO sqlite_schema(type,name,tbl_name,rootpage,sql)"
        " VALUES('index',?,'t',?,?)", (name, rootpage, sql))
    con.commit()
    con.close()

    con = sqlite3.connect(path)
    try:
        return _capture(con)
    finally:
        con.close()


def test_a_live_index_named_after_an_fts_message_reports_no_fts_damage():
    """The defect, run against a database rather than against a string.

    The assertion on the text is the load-bearing half and is deliberate. It
    ties the frozen corpus sample to a live capture, so the day SQLite changes
    this wording the corpus is reported as stale rather than quietly becoming a
    record of a sentence the library no longer emits.
    """
    con = sqlite3.connect(":memory:")
    try:
        _index_out_of_step_with_its_expression(
            con, FTS_MESSAGE_AS_NAME, (1, 2, 3))
        captured = _capture(con)
    finally:
        con.close()

    assert captured == sample("index_named_fts_message"), (
        "this SQLite no longer prints the message the corpus recorded")

    res = classify_integrity(captured)
    assert res["status"] == integrity.UNKNOWN
    assert res["classes"] == []
    assert len(res["unclassified"]) == 3


@needs_fts5
def test_a_live_database_tells_real_fts_damage_from_an_index_named_after_it():
    """One database, both kinds of line, and the distinction the class is for.

    Three findings whose text contains an FTS message because someone named an
    index that, and one written by FTS5 itself. Before the needles were held to
    the start of the message these two captures were indistinguishable: both
    came back DAMAGED with FTS_CORRUPTION and nothing unclassified, so the class
    said the same thing about a database holding no FTS as about this one.

    The count of unclassified lines is asserted, not the classes alone, because
    that count is what reports the three name lines as unread. A verdict naming
    the right class while silently swallowing them would satisfy a weaker test
    and still be hiding the same thing.
    """
    con = sqlite3.connect(":memory:")
    try:
        _index_out_of_step_with_its_expression(
            con, FTS_MESSAGE_AS_NAME, (1, 2, 3))
        _fts5_table_with_a_content_row_deleted(con)
        captured = _capture(con)
    finally:
        con.close()

    assert captured == sample("index_named_fts_message_beside_real_fts_damage")

    res = classify_integrity(captured)
    assert res["status"] == integrity.DAMAGED
    assert res["classes"] == ["FTS_CORRUPTION"]
    assert len(res["unclassified"]) == 3, (
        "the lines naming the index have to be reported as unread")


def test_a_live_count_fault_keeps_its_class_when_the_index_is_named_for_fts(
        tmp_path):
    """The repair, which is a different thing from the fix.

    ``wrong # of entries in index fts5: corrupt`` is one finding about one
    ordinary index. Under the unanchored table an FTS needle matched the name
    inside it, ``break`` ended the search, and CANONICAL_INDEX_COUNT was never
    reached, so the capture did not merely gain a class it had not earned: it
    LOST the one it had, and ``unclassified`` came back empty to report that
    everything had been read.

    Measured on the pre-fix table, this capture returned DAMAGED
    ['FTS_CORRUPTION'] with 0 unclassified.
    """
    captured = _count_fault_on_a_named_index(
        str(tmp_path / "count.db"), FTS_MESSAGE_AS_NAME, with_fts=False)

    assert captured.splitlines()[0] == (
        f"wrong # of entries in index {FTS_MESSAGE_AS_NAME}")

    res = classify_integrity(captured)
    assert res["classes"] == ["CANONICAL_INDEX_COUNT"], (
        "the count fault lost its own class to a needle inside the index name")
    assert res["unclassified"], (
        "the missing-row lines match no signature and have to say so")


@needs_fts5
def test_a_live_capture_carrying_both_families_reports_both(tmp_path):
    """A real mixed canonical and FTS capture, from one file and one check.

    The strongest single statement this criterion can make: in one output, a
    canonical fault whose index is named after an FTS message keeps its
    canonical class, a genuine FTS diagnostic earns the FTS class, and the five
    lines that are neither are reported as unread rather than absorbed into
    whichever class matched first.

    Measured on the pre-fix table this same capture returned DAMAGED
    ['FTS_CORRUPTION'] with 0 unclassified, the identical verdict it returned
    for the database holding no FTS at all.
    """
    captured = _count_fault_on_a_named_index(
        str(tmp_path / "both.db"), FTS_MESSAGE_AS_NAME, with_fts=True)

    res = classify_integrity(captured)
    assert res["status"] == integrity.DAMAGED
    assert res["classes"] == ["CANONICAL_INDEX_COUNT", "FTS_CORRUPTION"]
    assert len(res["unclassified"]) == 5


# ---------------------------------------------------------------------------
# The split under the anchor.
#
# Anchoring is a claim about where a needle sits in a LINE, and this module
# makes the lines itself. So the anchor is worth exactly as much as the split,
# and a boundary the parser invents is a boundary the user controls. Found by
# the final review of TASK-24, reproduced here on real SQLite before the split
# was changed.
# ---------------------------------------------------------------------------

#: An index name that carries a character Python calls a line break and SQLite
#: does not. U+2028 LINE SEPARATOR is an ordinary character inside a quoted
#: identifier, so this is one legal name and the CREATE INDEX is one statement
#: on one line.
NAME_WITH_A_FAKE_LINE_BREAK = "x\u2028fts5: corrupt"

#: The same attack through a character SQLite and Python agree about. This one
#: is NOT fixed by splitting on \n, and the test below says so.
NAME_WITH_A_REAL_LINE_BREAK = (
    "x\nmalformed inverted index for FTS5 table main.t")


def test_a_boundary_the_parser_invented_cannot_carry_an_anchored_needle():
    """The needle is at the start of a LINE that SQLite never ended.

    SQLite emits rows. This module splits them, and `str.splitlines` breaks on
    nine characters beyond `\\n`: \\v, \\f, \\r, \\x1c, \\x1d, \\x1e, \\x85,
    U+2028 and U+2029. SQLite emits none of them as a line break, and a quoted
    identifier may contain any of them, so splitlines took a character the user
    chose and made the rest of that name begin a line. The anchor then did
    exactly what it was built to do, on text SQLite never presented that way.

    The verdict on the pre-split-fix code was DAMAGED ['FTS_CORRUPTION'] with
    one line unclassified, for a database holding no FTS of any kind.
    """
    con = sqlite3.connect(":memory:")
    try:
        _index_out_of_step_with_its_expression(
            con, NAME_WITH_A_FAKE_LINE_BREAK, [1])
        rows = con.execute("PRAGMA integrity_check").fetchall()
        captured = _capture(con)
    finally:
        con.close()

    assert len(rows) == 1, (
        "SQLite emitted ONE row; anything else means this build treats U+2028 "
        "as a separator and the premise of the test has moved")
    assert captured == f"row 1 missing from index {NAME_WITH_A_FAKE_LINE_BREAK}"

    res = classify_integrity(captured)
    assert res["status"] == integrity.UNKNOWN
    assert res["classes"] == []
    assert res["unclassified"] == [captured], (
        "the row is one finding and has to be reported as one unread line, not "
        "cut in two at a character the index name happened to contain")


def test_a_real_newline_inside_a_name_is_the_residue_task_104_holds():
    """A tripwire on a KNOWN WRONG verdict, kept so the residue stays visible.

    This is the half that splitting on `\\n` does not fix and cannot. SQLite
    emits one row; the name inside it contains a genuine newline; and the text
    of that row is identical to the text of two findings. Nothing in the capture
    distinguishes them, so no rule reading text alone can, and the classifier
    reports FTS damage for a database with no FTS in it.

    The assertion below records what the code does TODAY, not what it should do.
    TASK-104 holds the fix, and when it lands this test fails and is what tells
    whoever lands it that the residue is closed.
    """
    con = sqlite3.connect(":memory:")
    try:
        _index_out_of_step_with_its_expression(
            con, NAME_WITH_A_REAL_LINE_BREAK, [1])
        rows = con.execute("PRAGMA integrity_check").fetchall()
        captured = _capture(con)
    finally:
        con.close()

    assert len(rows) == 1, "one index, one row, with a newline inside the name"
    assert "\n" in rows[0][0], (
        "the newline has to be in SQLite's own output; if the name came back "
        "escaped or quoted this residue would not exist")

    res = classify_integrity(captured)
    assert res["classes"] == ["FTS_CORRUPTION"], (
        "KNOWN RESIDUE, TASK-104: a name holding a real newline still takes a "
        "class it has not earned. Change this assertion when TASK-104 lands")
