"""docs/integrity.md is the only statement of what the verdict means.

The module docstring defers to it for the response schema, the signature names
and the corpus provenance, so a stale sentence there is not cosmetic: it is the
whole account. These tests pin the parts of the document that are derived from
code, pinning each documented name, needle and claim against the code value
it comes from, so drift breaks in CI rather than in an incident.

The document also promises that its reproduction procedures cover every
observed sample. That promise is checked here too, because an observed sample
with no procedure is a text nobody can re-derive, which is exactly the failure
mode not versioning the corrupt binaries was meant to avoid.
"""
from pathlib import Path
import re

import pytest

from pyteman.sqlitekit import integrity

from integrity_corpus import BY_NAME, CORPUS, OBSERVED

DOC = Path(__file__).resolve().parent.parent / "docs" / "integrity.md"
TEXT = DOC.read_text()

#: Every public uppercase string constant, which is every status and nothing
#: else. Derived rather than listed so a sixth status added without a paragraph
#: about it fails here.
STATUS_CONSTANTS = sorted(
    name for name, value in vars(integrity).items()
    if not name.startswith("_") and name.isupper() and isinstance(value, str)
)

#: The class names the signature table produces. Deduplicated, because the
#: table is one-to-many since TASK-24: three needles carry FTS_CORRUPTION, and
#: without the set the same assertion runs three times and a single missing
#: paragraph reports itself as three documentation defects.
SIGNATURE_NAMES = sorted({name for _, name, _ in integrity._SIGNATURES})

#: The needle TEXT, which is a separate binding from the class names above and
#: the one that was missing. No floor assertion of its own: it derives from the
#: same table, so the check on SIGNATURE_NAMES already catches an empty one.
SIGNATURE_NEEDLES = [needle for needle, _, _ in integrity._SIGNATURES]


def test_the_document_is_present_and_not_a_stub():
    # The floor comes first because every assertion below is satisfied by an
    # empty file if the path is wrong: `x in ""` is False, but so is the whole
    # parametrization when the list it derives from is empty. A wrong path
    # cannot reach here, since read_text raises during collection; what this
    # catches is a document truncated to a heading.
    assert len(TEXT) > 2000, "docs/integrity.md was truncated"
    assert STATUS_CONSTANTS, "no status constants were found to check"
    assert SIGNATURE_NAMES, "no signature names were found to check"


@pytest.mark.parametrize("name", STATUS_CONSTANTS)
def test_every_status_constant_is_documented(name):
    """A status a caller can branch on that the document never explains.

    The five are not interchangeable, and the document is where the difference
    between INCONCLUSIVE and NO_OUTPUT is written down; a sixth added silently
    would leave a caller reading four paragraphs for five outcomes.
    """
    assert name in TEXT, f"status {name} is exported but not documented"


@pytest.mark.parametrize("name", SIGNATURE_NAMES)
def test_every_signature_name_is_documented(name):
    """The CANONICAL_* names mean nothing without the paragraph explaining them.

    They are incident-specific rather than a general taxonomy, which is only
    true because the document says so. A name that reaches a report without
    that sentence behind it reads as a classification it is not.
    """
    assert name in TEXT, f"signature {name} is produced but not documented"


@pytest.mark.parametrize("needle", SIGNATURE_NEEDLES)
def test_every_needle_is_quoted_in_the_document(needle):
    """The class names were bound to the code already; the needle text was not.

    The document's whole argument for anchoring is made ABOUT these literal
    strings, so a needle edited in the table leaves a paragraph reasoning about
    a string the parser no longer looks for, with the suite green. That is the
    drift this module exists to break, at the site where it would be hardest to
    notice, because a wrong example still reads as a correct explanation.

    Whitespace is collapsed first because at least one needle is line-wrapped
    inside its own backticks, so the raw text does not contain it.
    """
    collapsed = " ".join(TEXT.split())
    assert f"`{needle}`" in collapsed, (
        f"the needle {needle!r} is matched but never quoted in the document")


def test_the_limit_of_the_fts_class_is_documented():
    """What FTS_CORRUPTION cannot do is the half a reader will assume away.

    The class is a reading of what SQLite's FTS code wrote, so its presence is
    solid and its ABSENCE proves nothing: an FTS table's shadow tables are
    ordinary b-trees and report as ordinary b-tree damage, naming no FTS at
    all. A reader who takes a clean-of-FTS_CORRUPTION verdict as FTS being
    healthy has made exactly the error TASK-24 removed, in the other direction,
    and this sentence is what stands between them and it.

    The binding is a phrase rather than a keyword, because any paragraph that
    happens to say "FTS" would satisfy the loose form, including one that makes
    the opposite claim. Whitespace is collapsed first so that rewrapping the
    paragraph cannot break or satisfy this by accident.
    """
    collapsed = " ".join(TEXT.split())
    assert "absence of `FTS_CORRUPTION` is not evidence that FTS is healthy" \
        in collapsed, (
            "the document no longer states what an FTS verdict's absence means")


OBSERVED_NAMES = {s.name for s in CORPUS if s.origin == OBSERVED}


def _generate_procedure_section():
    """Build the expected reproduction section from the corpus.

    The corpus is the source of truth for procedures. The document section is
    a rendering of this data, and its content is verified by comparing the
    document against what this function produces.
    """
    header = [
        "### Reproduction procedure",
        "",
        "All of these create a database in a scratch directory. None of them "
        "touches an",
        "existing file.",
    ]
    bullets = [
        f"- **{s.name}**: {s.procedure}"
        for s in CORPUS
        if s.origin == OBSERVED and s.procedure
    ]
    return "\n".join(header + bullets) + "\n"


@pytest.mark.parametrize("name", sorted(OBSERVED_NAMES))
def test_every_observed_sample_carries_a_procedure(name):
    """An observed sample without a procedure is a text nobody can re-derive.

    No corrupt database file is versioned, so the procedure is the only route
    back to an observed sample. The field sits on the dataclass, so a sample
    added without one fails here rather than passing in silence.
    """
    assert BY_NAME[name].procedure, (
        f"observed sample {name} has no procedure")
    assert len(BY_NAME[name].procedure) > 20, (
        f"the procedure for {name} is too short to be a reproduction step")


def test_the_document_procedure_section_matches_the_corpus():
    """The document section is generated from the corpus, not parsed back.

    If the two disagree, update the corpus (the source of truth) and
    regenerate the document section to match.
    """
    expected = _generate_procedure_section()
    assert "### Reproduction procedure" in TEXT, (
        "the document has no reproduction procedure section")
    actual = "### Reproduction procedure" + TEXT.split(
        "### Reproduction procedure", 1)[1]
    assert actual == expected, (
        "the document's procedure section does not match the corpus; "
        "regenerate it from the corpus")


#: Schema objects a sample's own text quotes. A message naming one of these is
#: only reproducible verbatim if the procedure says what to call it, so these
#: are the particulars a procedure cannot leave to the reader.
#:
#: Four forms, because SQLite prints object names four ways in the corpus. An
#: index is recognised by its name alone, and so is an FTS table, whose shadow
#: tables carry the same stem with a suffix. The third covers everything a
#: database qualifier names, which is how the FTS messages print their table:
#: `main.m4` quotes an object whose own name matches no pattern at all, and it
#: is the qualifier rather than the spelling that marks it as one. Matching the
#: word after `index` instead would be shorter and wrong, since `malformed
#: inverted index for FTS5 table ...` would then report an object called `for`.
#:
#: The fourth is the one TASK-24 added, and it exists because the first three
#: are all spelling rules and a quoted identifier has no spelling. SQLite prints
#: an index name UNQUOTED at the end of `row N missing from index ...`, so the
#: name can be any text at all, `fts5: corrupt` included, and that sample is
#: precisely the one whose name has to be reproduced exactly or the capture
#: cannot be re-derived. Without this alternative that sample harvests nothing
#: and passes the procedure check by finding no object to demand, which is the
#: check failing open on the one sample it most needs to hold. It is placed last
#: so the existing spelling rules keep their reading of the ordinary `idx_*`
#: names, which this form would otherwise capture identically.
NAMED_OBJECTS = re.compile(
    r"\bidx_\w+|\w+_fts\w*|(?<=\.)\w+|(?<=\.')\w+"
    r"|(?<=missing from index )\S.*")


@pytest.mark.parametrize("name", sorted(OBSERVED_NAMES))
def test_a_procedure_names_the_schema_objects_its_sample_quotes(name):
    """The document says a procedure reproduces the damage, and that what
    comes back verbatim depends on particulars the entry has to name.

    This checks the half of that claim a test can reach. An index or table
    whose name SQLite prints into the message is not incidental: follow a
    procedure that leaves it unsaid and the message comes back under a name of
    your own, so the recorded sample cannot be confirmed against it. It is also
    what makes btree_index_named_fts the sample it is, since the whole point of
    that one is the `_fts` in a name.

    Samples whose text quotes no schema object parametrize to a vacuous pass,
    which is correct: there is nothing there for a procedure to fix.
    """
    for token in sorted(set(NAMED_OBJECTS.findall(BY_NAME[name].text))):
        assert token in BY_NAME[name].procedure, (
            f"the sample {name} quotes {token}, which its procedure never "
            "names, so following it reproduces the damage under a different "
            "name and not the recorded text")


def test_an_object_is_recognised_by_its_qualifier_not_by_the_word_before_it():
    """The two halves of the pattern that are easy to get backwards.

    An FTS message names its table through a database qualifier, and the table
    can be called anything: `main.m4` is a real capture in the corpus and its
    name matches no spelling rule at all. Reading the qualifier is what finds
    it, and a sample whose object goes unfound passes this file's procedure
    check without checking anything.

    The tempting shortcut is the word after `index`, and it is wrong on that
    very line: the message says `inverted index for FTS5 table`, so the
    shortcut reports an object called `for` and then demands that a procedure
    say a word which names nothing.
    """
    found = set(NAMED_OBJECTS.findall(
        "malformed inverted index for FTS5 table main.m4"))
    assert found == {"m4"}


def test_an_index_name_that_is_not_an_identifier_is_still_harvested():
    """The form that has no spelling, and the reason the fourth one exists.

    An index name is printed unquoted at the end of this message, so it can be
    any text whatever. `fts5: corrupt` is a real index name from a real capture
    and matches none of the spelling rules, which means that before this
    alternative the sample quoting it harvested the empty set and satisfied the
    procedure check by demanding nothing. A check that finds no object to insist
    on reports the same silent pass as one whose document is complete, so the
    form is pinned here rather than trusted.

    The second assertion is the regression the ordering protects: an ordinary
    name matches this alternative too, and reading it through this form instead
    of the index rule must not change what comes back.
    """
    assert set(NAMED_OBJECTS.findall(
        "row 1 missing from index fts5: corrupt")) == {"fts5: corrupt"}
    assert set(NAMED_OBJECTS.findall(
        "row 201 missing from index idx_messages_session_id")) == {
            "idx_messages_session_id"}



#: A sample cited in the prose, written as a parenthesised backticked name, or
#: as a parenthesised comma-separated list of them where one claim rests on two
#: samples at once. Nothing else in this document puts a backticked lowercase
#: identifier inside parentheses, which is what lets the citations be harvested
#: without a hand-maintained list beside them.
#:
#: The list form is read because TASK-24 wrote one and the single-name pattern
#: skipped it in silence. `\(`([a-z0-9_]+)`\)` wants the closing parenthesis
#: immediately after the backtick, so the one citation carrying this module's
#: central measurement, the pair of missing-row samples, was the one citation
#: nothing checked. A harvester that quietly reads less than the prose contains
#: cannot report that it has stopped working, so the list form is pinned by its
#: own test below, the way the bold-inside-a-bullet case already is.
_CITATION = re.compile(r"\((`[a-z0-9_]+`(?:,\s*`[a-z0-9_]+`)*)\)")
_BACKTICKED = re.compile(r"`([a-z0-9_]+)`")


def _citations(text):
    return {name for run in _CITATION.findall(text)
            for name in _BACKTICKED.findall(run)}


CITED_SAMPLES = _citations(TEXT)


def test_a_citation_naming_two_samples_is_read_as_two():
    # The regression this file exists to prevent, in miniature: the harvest is
    # what makes every other citation check meaningful, and it fails open.
    # Under the old pattern this assertion returned the empty set while the
    # suite stayed green.
    assert _citations("So the needle is gone (`alpha_one`, `beta_two`).") == {
        "alpha_one", "beta_two"}
    assert _citations("reported as damage (`gamma_three`).") == {"gamma_three"}


def test_the_prose_cites_samples_that_are_in_the_corpus():
    """The document argues from named samples, so the names have to resolve.

    The section on the old criterion claims four failure modes and points the
    first three at the sample that shows each. That is the document's whole
    evidentiary structure: without the pointer a reader has an assertion, and
    with a stale pointer they have an assertion plus a wrong place to check it.
    The fourth mode is cited to a test rather than a sample, and the document
    says why, which is the shape this test cannot check and a reader can.

    This replaces a test that pinned a citation of one frozen test by name.
    That test was renamed by TASK-24, as its own docstring said it would be,
    and the mechanism is kept rather than dropped: whatever the document names,
    it has to exist.
    """
    assert CITED_SAMPLES, "the prose stopped citing samples by name"
    unknown = CITED_SAMPLES - set(BY_NAME)
    assert not unknown, (
        f"the document cites {sorted(unknown)}, which the corpus does not hold")


#: Scoped like the procedures, and for the same reason, but the end of the
#: section matters here as much as the start: the section that follows is the
#: one about what the text cannot decide, and it cites
#: `fts5_shadow_table_btree_damage`, which is real damage and classifies
#: DAMAGED. Run past the boundary and this test asserts UNKNOWN of a sample the
#: document never claimed was unmatched. Any heading depth closes the section,
#: because the next one here is a sibling rather than a parent.
NOT_MATCHED_SECTION = re.split(
    r"\n#{2,4} ", TEXT.split("### What is deliberately not matched", 1)[-1])[0]


def test_every_sample_the_document_declines_to_match_really_is_unmatched():
    """TASK-24 AC 2, the half the document rather than the code carries.

    That section is a table of messages this parser deliberately leaves at
    UNKNOWN. Written as prose it is a claim about the code that the code knows
    nothing about: add a needle for `unable to validate` tomorrow and the table
    is false, while every existing test stays green, because the samples it
    names all still exist and the cited names all still resolve.

    So the section is read back and executed. Each sample it cites has to
    classify UNKNOWN with no class attached, which is what the section says of
    all of them, and a fifth row added without a measurement behind it fails
    here rather than in a reader's hands.
    """
    cited = _citations(NOT_MATCHED_SECTION)
    assert len(cited) >= 4, (
        f"the section cites {sorted(cited)}, too few to be the table")
    for name in sorted(cited):
        res = integrity.classify_integrity(BY_NAME[name].text)
        assert res["status"] == integrity.UNKNOWN, (
            f"the document says {name} is deliberately not matched, but it "
            f"classifies as {res['status']} with {res['classes']}")
        assert res["classes"] == []
