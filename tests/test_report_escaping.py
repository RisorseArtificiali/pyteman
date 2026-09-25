"""What the report promises about a hostile value, and what it does not.

RUN-05. The audit found cell ids and signatures interpolated straight into the
table, where a pipe added a column and a newline added a row. ``_text`` closes
that, and these tests pin the closure: a defect with no test is one refactor
away from returning.

The promise has two halves, and the second is the one that is easy to lose.
The structural half keeps every stored value in its own row and its own cell,
in the file and through a real renderer, whatever characters it holds. The
literal half keeps the value from being *interpreted*: a cell holds result
data, and result data is not markup, so ``*x*`` arrives as three characters and
``<script>`` arrives as text rather than as a script element. The structural
half alone was measured through pandoc and left ten of the thirty sample values
below rendering as active elements, which is why both halves are pinned here.

What is deliberately not promised is pinned too, in the last two tests, so the
contract cannot be quietly overstated: whitespace still collapses, and a stored
control picture still renders as the line ending it stands for.
"""

import json
import os
import shutil
import sqlite3
import string
import subprocess
import sys
from html.parser import HTMLParser

import pytest

from pyteman.runner.report import _text, matrix_markdown

# Every family the acceptance criteria name, plus the inline-markup families
# the literal half has to defeat. The two error labels are covered separately,
# by the rows _foreign_db adds below: not because a fixed string the report
# chooses could break the table, but because they travel the same escape as
# foreign data and that path grants no column an exemption.
HOSTILE = [
    ("pipe", "a|b"),
    ("pipe-run", "|||"),
    ("backslash", "a\\b"),
    ("backslash-pipe", "a\\|b"),
    ("literal-backslash-n", "a\\nb"),
    ("newline", "a\nb"),
    ("carriage-return", "a\rb"),
    ("crlf", "a\r\nb"),
    ("backtick", "a`b"),
    ("backtick-pair", "`code`"),
    ("emphasis-star", "*x*"),
    ("emphasis-underscore", "_x_"),
    ("strong", "**x**"),
    ("intraword-underscore", "a_b_c"),
    ("html-bold", "<b>bold</b>"),
    ("html-script", "<script>alert(1)</script>"),
    ("html-entity", "&amp;"),
    ("html-entity-lt", "&lt;x&gt;"),
    ("md-link", "[a](http://x)"),
    ("md-image", "![a](http://x)"),
    ("autolink", "<https://x>"),
    ("bare-url", "http://x.y"),
    ("heading", "# h"),
    ("unicode-emoji", "☕"),
    ("unicode-combining", "caffè"),
    ("unicode-rtl-override", "a‮b"),
    ("unicode-zero-width", "a​b"),
    ("unicode-line-separator", "a b"),
    ("row-separator", "|---|---|---|---|"),
    ("empty", ""),
]

# Values the escape deliberately does not render as themselves. Line endings
# become their Unicode control pictures, and bidi formatting controls become
# their standard abbreviation in brackets. Both transformations are there to
# keep a reader from being misled: one by a row that splits, the other by
# text that reorders.
AS_SUBSTITUTED = {"newline": "a␊b", "carriage-return": "a␍b",
                  "crlf": "a␍␊b",
                  "unicode-rtl-override": "a[RLO]b"}

COLUMNS = ("experiment", "cell_id", "status", "signature")


def _foreign_db(path, column):
    """One row per hostile case, the case in ``column`` and the rest benign.

    Written straight into sqlite rather than through ``run_matrix``, which
    refuses several of these before they reach a row. That is not a contrivance
    to reach the branch: ``_read`` renders results tables this runner did not
    write, and those are precisely the rows that can hold anything at all.
    """
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE results(experiment, fingerprint, cell_id, status, "
                "result_json, artifact_dir)")
    for i, (_, value) in enumerate(HOSTILE):
        row = {"experiment": "exp", "cell_id": f"c{i:03d}", "status": "done",
               "signature": "CLEAN"}
        row[column] = value
        con.execute("INSERT INTO results VALUES (?, 'ff', ?, ?, ?, '/tmp/a')",
                    (row["experiment"], row["cell_id"], row["status"],
                     json.dumps({"signature": row["signature"]})))
    # The two ways a result fails to be readable. Their labels are rendered by
    # the report rather than stored, so they exercise the escape from the one
    # direction a hostile database cannot reach directly.
    con.execute("INSERT INTO results VALUES ('exp', 'ff', 'zz-not-json', 'done', "
                "'not json', '/tmp/a')")
    con.execute("INSERT INTO results VALUES ('exp', 'ff', 'zz-not-mapping', 'done', "
                "'[1, 2]', '/tmp/a')")
    con.commit()
    con.close()
    return str(path)


def _signature_db(path, values):
    """One row per value, the value in the signature column and the id benign.

    The shorter sibling of ``_foreign_db``, for the tests that put the value
    under test in the signature column only and then read the rendered column
    back by position. The ids are zero-padded so that ordering by cell_id is
    ordering by index for any number of values, which is what makes reading by
    position sound.
    """
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE results(cell_id, status, result_json, artifact_dir)")
    for i, value in enumerate(values):
        con.execute("INSERT INTO results VALUES (?, 'done', ?, '/tmp/a')",
                    (f"c{i:03d}", json.dumps({"signature": value})))
    con.commit()
    con.close()
    return str(path)


def body_rows(path):
    """The data rows, split on the only thing markdown counts as a line ending.

    ``splitlines`` also breaks on \\x0b, \\x0c, \\x85, \\u2028 and \\u2029,
    none of which end a line in markdown. Using it here would count rows the
    renderer does not, and report the escape as broken for characters it
    handles correctly.
    """
    return [line for line in path.read_text().split("\n")[2:] if line]


def unescaped_pipes(row):
    """Cell delimiters only: ``\\|`` is an escaped pipe and delimits nothing.

    Reading a row this way trusts the escape to backslash the backslash as
    well. It does, so ``\\|`` in the file is always an escaped pipe and never a
    stored backslash meeting a real delimiter, and the count means what it says.
    """
    return row.replace("\\|", "").count("|")


class _Table(HTMLParser):
    """Rows of cells, with any REAL element marked so it cannot be read as text.

    A regex over ``<tr>`` misread pandoc's ``<tr class="odd">`` and misaligned
    every row, so the reading of a renderer's output has to be exact.

    The obvious parser cannot answer the question the literal half asks. With
    ``convert_charrefs`` the literal text ``&lt;b&gt;`` arrives at
    ``handle_data`` as ``<b>``, byte-identical to how a naive parser would
    record an actual ``<b>`` element, so text and markup become
    indistinguishable in exactly the test that exists to distinguish them.
    Real tags are therefore recorded with guillemets, which no case above
    stores: a cell holding ``«b»`` saw an element, one holding ``<b>`` saw text.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows, self._row, self._cell = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
        elif self._cell is not None:
            self._cell.append(f"«{tag}»")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._row is not None and self._cell is not None:
            self._row.append("".join(self._cell))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            # The open cell closes with its row. Left dangling it would carry
            # text out of a malformed row and into the next one, and this
            # parser is the measuring instrument, so it does not get to guess.
            self.rows.append(self._row)
            self._row = self._cell = None
        elif self._cell is not None:
            self._cell.append(f"«/{tag}»")

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_comment(self, data):
        """Content that reaches none of the handlers above, marked not dropped.

        A comment, a declaration, a processing instruction and a marked section
        each terminate somewhere other than ``handle_data``. This parser is the
        measuring instrument, so a cell whose content ended up in one must not
        read back empty: an empty cell where a value should be is also how a
        value that rendered as itself reads, and the instrument would report a
        pass for a value it had lost. Not reachable while ``<`` is escaped,
        which the deterministic test pins; the instrument declines to depend on
        that. Measured before these four were covered, a cell holding
        ``<![CDATA[secret]]>`` read back as ``''``, and pandoc passes a marked
        section through a GFM cell into the ``<td>`` unaltered.
        """
        if self._cell is not None:
            self._cell.append("«markup»")

    # Spelled out rather than aliased onto handle_comment: the base class gives
    # these parameters different names, and a type checker reads an alias as a
    # signature mismatch.
    def handle_decl(self, decl):
        self.handle_comment(decl)

    def handle_pi(self, data):
        self.handle_comment(data)

    def unknown_decl(self, data):
        self.handle_comment(data)

# pandoc is the reference GFM implementation available here, but it is a
# developer tool and not a dependency of this package: the suite has to pass
# without it. Skipped rather than faked, because a hand-rolled stand-in would
# only re-assert this module's own reading of the spec. The tests above the
# marker are deterministic and carry the contract on their own.
pandoc = pytest.mark.skipif(shutil.which("pandoc") is None,
                            reason="pandoc renders the table; not a test dependency")


def _pandoc_html(out):
    """The report as pandoc renders it, which is the reference GFM reading."""
    # Rendering one small table, so the budget only has to bound a hang. An
    # external binary is the one child here this suite does not control the
    # source of.
    return subprocess.run(["pandoc", "-f", "gfm", "-t", "html", str(out)],
                          capture_output=True, text=True, check=True,
                          timeout=60).stdout


def _rendered_rows(html):
    """Every row a renderer produced, header included, as lists of cells."""
    parser = _Table()
    parser.feed(html)
    return parser.rows


def _data_rows(rows):
    """The rows a reader reads: everything after the header.

    The header is a ``<tr>`` of ``<th>`` and parses like any other row, so it
    goes by position. It used to be selected by width as well, which measured
    as dead: across both renderers and all four columns, every row arrives four
    wide, because GFM normalises a body row to the header's width rather than
    letting it be short or long. A filter that cannot fire can still drop a row
    that did arrive wrong, and silently losing a row is the one thing a
    measuring instrument must not do, so the width is asserted where it is
    meant rather than applied here.
    """
    return rows[1:]


def _rendered_signatures(out):
    """The signature cell of every data row, as a reader would see it."""
    return [row[3] for row in _data_rows(_rendered_rows(_pandoc_html(out)))]


@pytest.mark.parametrize("column", COLUMNS)
def test_a_hostile_value_keeps_its_own_row_and_its_own_column(tmp_path, column):
    """AC #1, at the level of the file: structure survives every family.

    Asserted by counting rather than by matching each value back, because the
    query orders by experiment and cell_id: a hostile value placed in either of
    those reorders the table, so position cannot carry the alignment. The three
    counts below say the same thing without needing it. One row per result, one
    delimiter count per row, and no two rows alike.
    """
    db = _foreign_db(tmp_path / f"{column}.db", column)
    out = tmp_path / "m.md"
    matrix_markdown(db, str(out))

    rows = body_rows(out)
    expected = len(HOSTILE) + 2  # the two unreadable-result rows
    assert len(rows) == expected, "a value added or removed a row"
    split = [row for row in rows if unescaped_pipes(row) != 5]
    assert split == [], f"a value added or removed a column: {split!r}"
    assert len(set(rows)) == expected, "two distinct results rendered identically"


def test_the_two_error_labels_reach_the_signature_column_and_are_told_apart(tmp_path):
    """The 'errors' half of AC #1: a row whose result cannot be read still renders.

    These labels are written by the report rather than stored, so they are the
    one thing in the table a hostile database cannot set directly. They are
    covered here because an unreadable result is still a result and still owes
    the reader a row.

    This test deliberately does not claim to pin the escape. The labels hold no
    pipe, so it passes with the escape removed entirely, which a mutation check
    confirmed. What it pins is that the two faults stay distinguishable and land
    in the signature column rather than being folded into one label.
    """
    db = _foreign_db(tmp_path / "labels.db", "status")
    out = tmp_path / "m.md"
    matrix_markdown(db, str(out))

    cells = [row.split("|") for row in body_rows(out)]
    labels = [row[4].strip() for row in cells if row[2].strip().startswith("zz")]
    assert sorted(labels) == sorted([_text("(result is not a mapping)"),
                                     _text("(unreadable result)")])


def test_the_escape_does_not_touch_what_is_stored(tmp_path):
    """Rendering is not migration: the database still holds what the run wrote.

    ``_text`` exists to decide how a value is *shown*. A reader who goes back to
    the results db to check a signature by hand has to find the bytes the run
    recorded, not the escaped form the report chose, or the report has quietly
    rewritten the evidence it was asked to display.
    """
    db = _foreign_db(tmp_path / "raw.db", "signature")
    matrix_markdown(db, str(tmp_path / "m.md"))

    con = sqlite3.connect(db)
    stored = [json.loads(r[0])["signature"] for r in con.execute(
        "SELECT result_json FROM results WHERE cell_id LIKE 'c%' ORDER BY cell_id")]
    con.close()
    assert stored == [value for _, value in HOSTILE]


def test_the_escape_is_punctuation_backslashed_and_line_endings_pictured():
    """The two halves of the rule, without a renderer, so the suite always says it.

    Every renderer test below is skipped where pandoc is absent. This one is
    not, so a mutation that empties the escape still fails somewhere: the
    backslash half is what makes punctuation literal and keeps the pipe from
    splitting the row, and the control-picture half is what a backslash cannot
    do, because a cell is one line and a line ending has nowhere to go.

    The backslash is pinned on its own line and not left to stand as one more
    punctuation character, because it is the one that makes the mapping
    injective. Dropped from the table, a stored ``a\\|b`` and a stored ``a|b``
    both render ``a|b`` and two distinct values collapse into one. That
    mutation was run: it is caught only by the pandoc tests below, so without
    this line it ships green anywhere pandoc is absent, which is precisely the
    case this test exists to cover.

    The whole set is asserted before the readable cases, rather than left to
    them. Sampled characters pin only themselves, and the mutation that matters
    is not emptying the escape but trimming it: measured with neither renderer
    installed, an escape narrowed to leave out ``&``, ``;``, ``:``, ``/``,
    ``.`` or the backtick passed every test in this file. Neither renderer,
    not merely pandoc: the second-renderer test carries no pandoc marker and
    catches the backtick on its own where python-markdown happens to be
    importable, which is an ambient package rather than a declared dependency.
    The cases below stay because they say what the rule means; the line above
    them is what makes it a rule.
    """
    assert _text(string.punctuation) == "".join("\\" + c for c in string.punctuation)
    assert _text("a|b") == "a\\|b"
    assert _text("a\\b") == "a\\\\b"
    assert _text("*x*") == "\\*x\\*"
    assert _text("<b>") == "\\<b\\>"
    assert _text("a\nb") == "a␊b"
    assert _text("a\r\nb") == "a␍␊b"
    # Not punctuation and not a line ending: left exactly alone, so a report
    # does not sprout backslashes through ordinary text. The digits are here
    # deliberately. The equality above is a subset check and cannot see an
    # escape that grows, and a widened table is the same class of lie as a
    # narrowed one: measured by adding string.digits to the table, a stored
    # "<script>alert(1)</script>" reaches the reader as "alert(\1)", because
    # CommonMark gives a backslash before a digit no escape meaning at all.
    # That mutation is caught by pandoc alone, so without the digits here it
    # ships green wherever pandoc is not installed.
    assert _text("caffè 42 ☕") == "caffè 42 ☕"


def test_bidi_controls_become_their_abbreviation():
    """Bidi formatting controls are replaced with a visible label.

    Without the replacement, U+202E reorders every glyph that follows
    it and a signature can display as text it does not contain. The
    label neutralises the reordering and marks the position.
    """
    assert _text("a‮b") == "a\\[RLO\\]b"
    assert _text("‪") == "\\[LRE\\]"
    assert _text("‫") == "\\[RLE\\]"
    assert _text("‬") == "\\[PDF\\]"
    assert _text("‭") == "\\[LRO\\]"
    assert _text("⁦") == "\\[LRI\\]"
    assert _text("⁧") == "\\[RLI\\]"
    assert _text("⁨") == "\\[FSI\\]"
    assert _text("⁩") == "\\[PDI\\]"


def test_the_report_writes_where_the_locale_is_not_utf_8(tmp_path):
    """The escape manufactures non-ASCII, so the write cannot take the locale.

    The control pictures are the only characters this report produces that are
    not ASCII, and it produces them from a stored line ending, which is ASCII.
    That put a crash within reach of ordinary data: a results db holding
    nothing more unusual than a newline rendered to a report that would not
    write at all, failing in ``open`` rather than anywhere near the escape.
    Measured before the encoding was pinned::

        UnicodeEncodeError: 'latin-1' codec can't encode character '\\u240a'

    Run in a child process because the locale encoding is read once, when the
    interpreter starts, so it has to be wrong for a whole run to be wrong at
    all. Skipped where no non-UTF-8 locale is installed, since there the parent
    and the child would agree and the test would pass without asking anything.
    """
    db = _signature_db(tmp_path / "nl.db", ["a\nb"])
    out = tmp_path / "m.md"
    env = {**os.environ, "LC_ALL": "en_US.ISO-8859-1", "PYTHONUTF8": "0"}
    # Interpreter startup and one print, so the budget is short on purpose:
    # anything slower than this is a hang and not a slow machine.
    encoding = subprocess.run(
        [sys.executable, "-c",
         "import locale; print(locale.getpreferredencoding(False))"],
        env=env, capture_output=True, text=True, timeout=30).stdout.strip()
    if encoding.lower().replace("-", "") in ("utf8", ""):
        pytest.skip(f"no non-UTF-8 locale here to write under: got {encoding!r}")

    # Wider than the probe above because this one imports the package and
    # writes a report, and narrower than a build because that is all it does.
    done = subprocess.run(
        [sys.executable, "-c",
         "from pyteman.runner.report import matrix_markdown\n"
         f"matrix_markdown({db!r}, {str(out)!r})"],
        env=env, capture_output=True, text=True, timeout=60)

    assert done.returncode == 0, f"the report would not write: {done.stderr}"
    assert "␊" in out.read_text(encoding="utf-8"), (
        "the newline did not reach the file as its control picture")


@pandoc
@pytest.mark.parametrize("column", COLUMNS)
def test_a_real_renderer_also_keeps_every_result_in_its_own_cell(tmp_path, column):
    """AC #2. The file being well formed is not the same as it rendering right.

    GFM splits a table row on its pipes before any inline parsing runs, so the
    two levels can disagree: a value can be safe in the file and still move in
    the renderer. This asks pandoc rather than reasoning about the spec.

    What it asks is the content of the columns *not* under test, because a
    width check alone cannot fail here. GFM normalises every body row to the
    header's width, padding a short one and discarding the cells past the
    fourth; verified directly, a five-cell body row under a four-column header
    renders four ``<td>`` and loses the rest. So a split row arrives the right
    width with the wrong values in it, which is what the benign columns below
    detect. Measured with the pipe escape removed, this fails for three of the
    four parametrisations; the fourth is the signature, the last column, whose
    displaced cells fall past the truncation boundary and are seen only by
    ``test_every_stored_value_renders_as_the_text_it_is``.
    """
    db = _foreign_db(tmp_path / f"{column}.db", column)
    out = tmp_path / "m.md"
    matrix_markdown(db, str(out))

    rows = _rendered_rows(_pandoc_html(out))
    data = _data_rows(rows)
    assert len(data) == len(HOSTILE) + 2, "the renderer saw a different table"
    assert {len(row) for row in rows} == {4}, "a row rendered a wrong width"
    benign = {"experiment": "exp", "status": "done", "signature": "CLEAN"}
    for row in data:
        for name, value in benign.items():
            # The signature of the two unreadable-result rows is a label the
            # report writes, not the CLEAN the others carry.
            if name == column or (name == "signature" and row[1].startswith("zz")):
                continue
            got = row[COLUMNS.index(name)]
            assert got == value, (
                f"a hostile {column} displaced another column: {name} holds {got!r}")


@pandoc
def test_every_stored_value_renders_as_the_text_it_is(tmp_path):
    """AC #2, the literal half: what a reader sees is what the database holds.

    Alignment by position is sound here and only here: the hostile value sits
    in the signature column while the cell ids stay benign and ordered, so the
    query's ORDER BY cannot be steered by the data under test.

    Two assertions, because either alone would pass a broken escape. Matching
    the text catches a value that arrives altered; the guillemet check catches
    a value that arrives as an *element*, which the text match cannot see at
    all, since a rendered ``<b>`` and the literal characters ``<b>`` read back
    from HTML identically.
    """
    db = _foreign_db(tmp_path / "literal.db", "signature")
    out = tmp_path / "m.md"
    matrix_markdown(db, str(out))

    rendered = _rendered_signatures(out)[:len(HOSTILE)]
    wrong = [(name, value, got) for (name, value), got in zip(HOSTILE, rendered)
             if got != AS_SUBSTITUTED.get(name, value)]
    assert wrong == [], f"a stored value did not render as itself: {wrong!r}"
    active = [(name, got) for (name, _), got in zip(HOSTILE, rendered) if "«" in got]
    assert active == [], f"a stored value rendered as active markup: {active!r}"


@pandoc
def test_a_stored_backslash_n_renders_apart_from_a_stored_newline(tmp_path):
    """The distinction the control pictures are there to buy.

    Escaping every punctuation character makes rendering close to the identity,
    and that is what puts this pair at risk: rendering a real newline as a
    backslash and an ``n`` would print it identically to the two characters
    someone stored, at exactly the point a reader is trying to tell them apart.
    """
    db = _signature_db(tmp_path / "nl.db", ["a\\nb", "a\nb"])
    out = tmp_path / "m.md"
    matrix_markdown(db, str(out))

    assert len(set(body_rows(out))) == 2, "the two collapsed in the file"
    rendered = _rendered_signatures(out)
    assert rendered[0] == "a\\nb", "the stored backslash-n did not survive"
    assert rendered[1] == "a␊b", "the real newline did not become its picture"


@pandoc
def test_a_bidi_override_renders_as_its_label_not_as_reordered_text(
        tmp_path):
    """The distinction the bidi labels are there to buy.

    Without the escape, U+202E reverses the reading order of every
    glyph that follows it. A signature ``sig`` followed by RLO and
    ``DEKAF`` displays as ``sigFAKED``, which is text the database
    does not contain. The label makes the control visible and
    neutralises the reordering.
    """
    bidi = [
        ("‪", "[LRE]"), ("‫", "[RLE]"),
        ("‬", "[PDF]"),
        ("‭", "[LRO]"), ("‮", "[RLO]"),
        ("⁦", "[LRI]"), ("⁧", "[RLI]"),
        ("⁨", "[FSI]"), ("⁩", "[PDI]"),
    ]
    values = [f"a{ctrl}b" for ctrl, _ in bidi]
    db = _signature_db(tmp_path / "bidi.db", values)
    out = tmp_path / "m.md"
    matrix_markdown(db, str(out))

    rendered = _rendered_signatures(out)
    wrong = [
        (f"U+{ord(ctrl):04X}", label, got)
        for (ctrl, label), got in zip(bidi, rendered)
        if got != f"a{label}b"
    ]
    assert wrong == [], (
        f"a bidi control did not render as its label: {wrong!r}")


def test_a_second_renderer_agrees_that_no_value_becomes_markup(tmp_path):
    """The safety half, checked against a renderer from a different family.

    pandoc implements CommonMark, and the escape is built on a CommonMark rule,
    so pandoc alone cannot say whether the contract holds or whether the test
    and the code merely share one reading of one spec. python-markdown is not
    CommonMark and honours a narrower set of backslash escapes, which makes it
    the useful second opinion.

    What it is asked is deliberately narrower than what pandoc is asked above.
    Exact text is a CommonMark promise: measured here, eight of thirty values
    arrive carrying a visible backslash where this renderer does not recognise
    the escape. What holds on both, and is the half that matters for safety, is
    that nothing becomes an active element and no two distinct stored values
    collapse into one rendering.
    """
    markdown = pytest.importorskip(
        "markdown", reason="second renderer; not a test dependency")
    db = _foreign_db(tmp_path / "second.db", "signature")
    out = tmp_path / "m.md"
    matrix_markdown(db, str(out))

    rows = _rendered_rows(markdown.markdown(out.read_text(), extensions=["tables"]))
    rendered = [row[3] for row in _data_rows(rows)][:len(HOSTILE)]
    assert len(rendered) == len(HOSTILE), "the renderer saw a different table"
    active = [(name, got) for (name, _), got in zip(HOSTILE, rendered) if "«" in got]
    assert active == [], f"a stored value rendered as active markup: {active!r}"
    assert len(set(rendered)) == len(HOSTILE), "two distinct values collapsed into one"


@pandoc
def test_what_the_escape_still_does_not_promise(tmp_path):
    """The limits, executable, so they cannot be quietly overstated or lost.

    Two values differing only in whitespace still arrive alike: markdown strips
    and collapses spaces inside a cell before any escape can speak, and no
    backslash reaches that. TASK-68 holds the question of whether it is worth
    closing.

    A stored control picture still renders as the line ending it stands for.
    That collision is kept knowingly and permanently: escaping the picture only
    moves it onto a stored backslash followed by a real newline, and closing it
    properly needs a doubling scheme that would cost every report its
    readability. Both are pinned rather than described, so a change of
    behaviour has to be a change of contract too.
    """
    db = _signature_db(tmp_path / "limits.db", ["lead", "  lead", "a\nb", "a␊b"])
    out = tmp_path / "m.md"
    matrix_markdown(db, str(out))

    # Distinct in the file: the structural promise holds even where the
    # rendered promise does not, which is the difference worth keeping visible.
    assert len(set(body_rows(out))) == 4

    rendered = _rendered_signatures(out)
    assert rendered[0] == rendered[1] == "lead", "leading space is no longer stripped"
    assert rendered[2] == rendered[3] == "a␊b", "the picture collision is gone"
