# Reading `PRAGMA integrity_check` output

Design decision record for `pyteman.sqlitekit.integrity`. The verdict schema and
the corpus are TASK-25 / SQL-02, 2026-09-16; everything about how FTS is
recognised, from "What the old criterion did" onward, is TASK-24 / SQL-01,
2026-09-17. That split is by subject rather than by position in the file:
TASK-24 also rewrote what the `unclassified` bullet below says about
normalising finding lines, which is schema and not FTS.

## The problem

`classify_integrity` answered with a list of signature names and the raw text.
When it recognised nothing, that list was empty, and an empty list was the
answer to three different situations:

- nothing was captured at all,
- a header arrived with no findings under it,
- the database was damaged in a way no rule reads.

An empty list reads as "no signatures found", which a reader hears as "nothing
wrong". All three are the opposite of that.

A fourth defect sits alongside them and is not an empty list. An output holding
a recognised line and unrecognised ones answered with the recognised half
alone and discarded the rest, so the answer named a signature and was still
missing most of what SQLite said: the observed index-corruption output is one
recognised line followed by sixty that were dropped.

## What actually arrives

Measured on SQLite 3.51.2 (the `sqlite3` module in CPython 3.14.7) and the
3.53.4 shell, against databases created and damaged for the purpose:

| Situation | Where the text comes from |
|---|---|
| Undamaged database | one row, `ok` |
| Rowid disorder, orphan pages | a **single** row holding the `*** in database <name> ***` header and every finding of the b-tree check, separated by newlines inside that one row |
| Index entry count mismatch | one row per finding (61 for the sample below), with **no** header on this path |
| File is not a database | **raised** `DatabaseError`; shell writes stderr with empty stdout, exit status depends on the file (below) |
| Schema will not parse | **raised** `DatabaseError`; shell writes stderr, exits 1 |
| File truncated below its page count | **raised** `DatabaseError`; shell writes stderr, exits 1, measured at 1, 2 and 8 pages cut |

The header belongs to one check rather than to the output as a whole, which is
what the first two rows of that table are really showing. `integrity_check`
runs several checks, and the b-tree structural one joins all of its own
findings into a single string with the header prefixed to it, so it arrives as
one row however many findings it holds. The index checks then emit a row each,
with no header. A database carrying both kinds of damage shows both halves at
once, measured here: 62 rows, the header and the rowid finding together in the
first, the 61 index findings in their own rows after it. So the header is not a
property of the whole capture, and one thing does follow from this that the
module leans on: the header is never a row by itself, because the string it is
prefixed to is emitted only when that check found something.

Three consequences shape the module.

First, the failures that matter most never arrive as output. `file is not a
database` and `malformed database schema` are exception messages, so they reach
the classifier only because a caller caught the error and passed the message
on. The input is therefore "whatever was captured, from whichever channel",
not "the rows integrity_check returned".

Second, **the empty string is a real input**. A caller that redirects stdout
gets exactly nothing from a destroyed file. Meanwhile a zero-byte file is a
valid empty database and reports `ok`. The emptier input is the healthy one,
so reading an empty capture as an absence of damage inverts the verdict on the
worst case there is.

The exit status does not rescue that caller either, which is why the table
above defers it. Measured on shell 3.53.4 against three files that are all not
databases: random bytes and a plausible-looking header both print `file is not
a database` to stderr and exit 1, while a file of ASCII text is read as a SQL
script instead, printing a syntax error and exiting **0**. Stdout is empty in
all three. Python raises `DatabaseError` for all three. So a caller can come
away with an empty capture and a successful exit status from a file that is not
a database at all, which is the exact pairing `NO_OUTPUT` exists to refuse to
read as a pass.

Third, **the header names the database being checked**, so it is matched by
shape and not against the literal `*** in database main ***`. Checking a file
through `ATTACH` prints `*** in database aux1 ***`, observed on SQLite 3.51.2
and held in the corpus. Matching the literal instead would file that line as a
finding, which runs the count in the diagnosis one high and leaves
`INCONCLUSIVE` unreachable for any database not called `main`. That is the
measured behaviour of the rejected alternative, reached by substituting it and
re-running, rather than a fault any released version of this module shipped.

## The response

`classify_integrity(text)` returns a mapping with five keys:

- **`status`**: one of `CLEAN`, `DAMAGED`, `UNKNOWN`, `INCONCLUSIVE`,
  `NO_OUTPUT`, exported as module constants. The single field to branch on.
- **`classes`**: sorted signature names. Non-empty exactly when `status` is
  `DAMAGED`; that equivalence is an invariant and is tested.
- **`unclassified`**: every finding line no signature matched, in SQLite's
  order. Never summarised away, because a line this parser cannot read is still
  evidence, and it is what an investigation needs most. The lines are
  normalised, not reproduced: classification strips each line of surrounding
  whitespace, and it is the stripped line that is kept, so
  `classify_integrity("  mystery  \n")` reports `["mystery"]`. What is preserved
  is the finding, not the layout it arrived in.
- **`diagnosis`**: a sentence for a human, non-empty for every status.
- **`raw`**: the input exactly as passed, always, whatever the verdict.

`CLEAN` used to appear in `classes`. It moved to `status`, because a list of
damage signatures that also carries the absence of damage makes the empty list
mean two opposite things, and reads a healthy database as damaged under a plain
`if result["classes"]`.

Non-`str` input raises `TypeError` naming the type received and saying to pass
`''` instead. That keeps the likely accident, a capture helper that returned
`None`, apart from a capture that legitimately produced nothing. Before, the
`None` failed on `.splitlines()` inside the function with a message naming
neither the function nor the argument.

`INCONCLUSIVE` and `NO_OUTPUT` are separate because the remedy differs. Nothing
captured sends an operator to the channel the message actually went down,
meaning stderr and the exit status. A header with no findings under it sends
them back to the capture itself: no run measured here produced that shape,
because the header is prefixed to the b-tree check's findings and is emitted
with them, so the text is more likely to have been cut than the database to
have been silent.

`UNKNOWN` states that the text was not read, and deliberately stops there. It
is not a pass, because `ok` is the only output that means a pass. It is also
not a report of damage, and the difference is not pedantry: the error channel
this classifier reads from carries messages from healthy databases too.
`PRAGMA integrity_check` raises `OperationalError('database is locked')` when
another connection holds an EXCLUSIVE lock, and `OperationalError` is a
`DatabaseError`, so that message arrives by the same route as `file is not a
database`. So do `unable to open database file`, `disk I/O error` and `attempt
to write a readonly database`. A verdict that called any of those damage would
invert exactly the mistake this module was built to prevent, in the other
direction.

## Running the check: `check_integrity`

`check_integrity(path)` is the recommended entry point for a caller that does
not already have a capture. It opens the database, runs `PRAGMA
integrity_check`, catches the `DatabaseError` that a non-database or a corrupt
schema raises instead of returning rows, and passes whichever text arrived to
`classify_integrity`. The return value is the same five-key mapping documented
above.

The distinction it makes is the one the module docstring describes: a file that
is not a database makes the PRAGMA raise, so a caller redirecting only stdout
sees nothing and `classify_integrity("")` reports `NO_OUTPUT`. `check_integrity`
catches the exception and feeds the message through, so that same file produces
`NOTADB` instead. `NO_OUTPUT` then means what it should: the capture was not
performed, rather than the check was performed and produced nothing.

`classify_integrity` remains public and unchanged for callers that already own
a capture, whether from the sqlite3 shell, a subprocess, or a different
execution path. `check_integrity` delegates to it after assembling the text.

## The signature names

`CANONICAL_ROWID_DISORDER` and `CANONICAL_INDEX_COUNT` are **incident-specific
and not a general taxonomy**. They name the two signatures the original
corruption investigation was identified by, and "canonical" means that matching
both marked a database as *that incident* rather than as damage in general. A
database can be thoroughly destroyed and match neither. `NOTADB` and `SCHEMA`
name error-channel messages, per the table above.

`FTS_CORRUPTION` names the messages SQLite's own FTS code writes when it reports
corruption. It replaced a criterion that read a name, and the replacement is
TASK-24; what follows is why the old one had to go and what the new one does and
does not claim.

### What the old criterion did

`FTS_ONLY` fired when no other signature had matched and every finding line
contained `_fts`. That decided a class from a property of the whole capture,
where every other class is decided by reading one line, and `_fts` is a string a
user chooses. Measured on SQLite 3.51.2, it was wrong in four distinct ways at
once, and the corpus holds a sample for the first three:

- **It fired on a name.** An ordinary expression index called `idx_fts`, over a
  table with no FTS in it anywhere, prints `row 1 missing from index idx_fts`
  and was reported as confirmed FTS damage (`expression_index_named_fts`).
- **It fired on a message that reports nothing.** `unable to validate the
  inverted index for FTS5 table main.messages_fts` says the check could not be
  completed, which is the opposite of a finding, and was read as damage because
  the table name contains `_fts` (`unable_to_validate_fts_message`).
- **It stayed silent on real FTS5 corruption whenever another signature had
  matched first.** A database damaged in both ways at once classified as
  `CANONICAL_INDEX_COUNT`, and the one line SQLite's FTS code wrote was filed
  under `unclassified` (`mixed_fts_and_index_count`).
- **It stayed silent whenever any single line lacked `_fts`.** One unrelated
  finding alongside genuine FTS5 corruption was enough to suppress it entirely.
  This one has no sample of its own, and deliberately so: the shape is one
  arbitrary line placed beside a real FTS capture, so
  `test_one_unrelated_line_no_longer_suppresses_real_fts_corruption` builds it
  inline from a literal and `fts5_malformed_inverted_index`. A corpus sample
  would fix the arbitrary line as though SQLite had chosen it.

The last two are the ones worth dwelling on. A criterion that reports FTS damage
on a name is embarrassing; a criterion that goes quiet on FTS damage precisely
when the database has more than one fault is dangerous, and it fails in the
direction nobody checks.

### What replaced it

The needles are in `_SIGNATURES` with the rest, matched a line at a time. They
were enumerated from the format strings of the library in use, and two of the
three were then produced here from a database damaged for the purpose, so those
two are backed both by the string in the binary and by a capture:

| Needle | Emitted for | Reproduced here |
|---|---|---|
| `malformed inverted index for fts` | the wrapper `integrity_check` puts around an FTS corruption, for FTS3, FTS4 and FTS5 alike | FTS5 and FTS4 |
| `fts5: corrupt` | a damaged `%_data` block, page, segment or structure record | yes |
| `fts5: checksum mismatch` | FTS5's own `integrity-check` command finding the index out of step with the content | **no** |

The second row stands for four format strings rather than one, because the
library writes both `corrupt` and `corruption` across the same family of faults.

The first row's answer is partial on purpose. FTS5 and FTS4 are both in the
corpus as captures, and FTS3 is not: the needle covers it because the format
string differs only in the digit, which by this document's own rule proves the
message exists and not how it arrives.

The last row is the one to read carefully. FTS5 emits that message from
`INSERT INTO <table>(<table>) VALUES('integrity-check')` rather than from the
PRAGMA, and running it against every damaged database tried here raised
`database disk image is malformed` instead. The needle is kept, because the
format string is genuinely in the library and a caller that runs that command
can hand us the message. The corpus sample is marked synthetic, because nothing
here observed it. Enumerating a format string proves the message exists; only a
capture proves how it arrives, and conflating the two is how a corpus starts
asserting things SQLite never promised.

### Where the needle has to appear

Choosing the right needles is half the rule. The other half is where in the line
they are allowed to match, and the first version of this rewrite got it wrong in
a way that is worth recording, because the criterion it replaced had made the
same mistake.

SQLite interpolates user-chosen object names into its findings, and it prints
them **unquoted**. So a finding line has a region in it that holds arbitrary
text, and a needle looked for anywhere in the line is eventually found there. An
ordinary expression index named `fts5: corrupt`, in a database holding no FTS of
any kind, prints `row 1 missing from index fts5: corrupt` once its index is out
of step with its table, and that line does not contain the needle: it *is* the
needle, with a b-tree finding in front of it. Measured on SQLite 3.51.2, every
needle in the table above was reachable this way by naming an index after it
(`index_named_fts_message`).

That is the old criterion's mistake at a longer length. Reading `_fts` out of a
name and reading an entire FTS message out of a name are the same error, and
abolishing the first without moving the match does not fix it.

So the FTS needles are matched at the **start of the message** rather than
anywhere in the line. What makes that available is that each of them is a whole
message: the entire text SQLite emitted, which therefore begins the line it
arrives on. An object name never does, because a line **SQLite emitted** begins
with what SQLite chose to say.

That qualification is exact, and the final review of TASK-24 is what made it
exact. A capture is one string and this module splits it, so a line boundary the
module invents is a boundary the user controls, and an anchor is worth only as
much as the split beneath it. `str.splitlines()` breaks on `\v`, `\f`, `\r`,
`\x1c`, `\x1d`, `\x1e`, `\x85`, `U+2028` and `U+2029`, none of which SQLite
emits as a line break and any of which may sit inside a quoted object name.
Measured on SQLite 3.51.2, an index named `x<U+2028>fts5: corrupt` over an
ordinary table in a database holding no FTS produced ONE row,
`row 1 missing from index x<U+2028>fts5: corrupt`, which `splitlines()` cut into
two findings and which then reported damaged `["FTS_CORRUPTION"]`. The split is
now `text.split("\n")`, which is the only boundary SQLite writes.

A name holding a real `\n` reaches the same result and is NOT fixed by that:
SQLite emits one row that is indistinguishable, as text, from two findings. That
residue is real, out of this change, and held by TASK-104.

The sqlite3 shell is the complication, and it is the reason an earlier note in
the module concluded that anchoring could not be the fix. The shell puts its own
wrapper on anything it reports as an error, so the message does not begin the
line there. That premise is true and the conclusion does not follow: the wrapper
is a small closed family, measured on shell 3.53.4, and it comes off before the
needles are tried.

| Wrapper | When |
|---|---|
| `Parse error <locator>: ` | the statement failed before it ran |
| `Error <locator>: ` | the statement failed while running |

The locators observed are `in Nth command line argument`, `near line N`, and
`near line N of <path>`, some of them followed by a result code such as ` (26)`.
Rows returned by `integrity_check` itself carry no wrapper at all.

Removing it is done on a copy, for matching only. `unclassified` and `raw` keep
the line exactly as it arrived, wrapper included, because those two keys are the
record of the capture rather than of how it was read, and the wrapper says which
channel the text came from. The path in `near line N of <path>` is read
non-greedily, so it ends at the first colon **followed by a space** rather than
at the first colon: a path like `/tmp/a:b.sql` is consumed whole and costs
nothing. Where a path does end the match early, the leftover prefix stops an
anchored needle from matching and the line reports `UNKNOWN`. That direction is
chosen. Reading to the last colon-space instead would cut into the message:
`something: malformed inverted index for FTS5 table main.t` would be reduced to
the needle and reported as FTS corruption, which is this parser's own invention
rather than SQLite's finding. A class lost is survivable and a class invented is
the thing this document exists to prevent.

The four remaining needles still match anywhere, and that is a statement about
their text rather than a lower standard for them. `out of order` is a fragment
at the end of `Tree 2 page 2 cell 0: Rowid 2 out of order`, so it has no start
of its own to be held to, and `wrong # of entries in index` is followed by a
name rather than preceded by one. An index named `out of order` therefore still
carries its needle into a line about something else. That residue is real,
deliberately out of this change, and held by TASK-99 together with the captures
that show it: what is fixed here is that an object's name is no longer
attributed to SQLite's FTS code.

The gain is not only that a false verdict stops. It is that the two cases become
distinguishable at all. One database can carry both an index named after an FTS
message and genuine FTS5 corruption, and before this rule that capture and a
capture holding only the names returned the identical verdict, `DAMAGED` with
`FTS_CORRUPTION` and nothing unclassified
(`index_named_fts_message`, `index_named_fts_message_beside_real_fts_damage`).
The class carried no information and no part of the output marked the misreading.
Now the genuine line produces the class and the three name lines are reported
unread, which is what `unclassified` is for.

Anchoring also recovers a class that the unanchored form was taking away.
`wrong # of entries in index fts5: corrupt` is one finding about one ordinary
index, and the FTS needle used to match it first, so the capture did not merely
gain `FTS_CORRUPTION`: it lost `CANONICAL_INDEX_COUNT`, the class the line was
actually about.

Both captures are re-derived rather than only recalled. `tests/test_integrity_classification.py`
builds each database, damages it and reads `PRAGMA integrity_check` in process,
then asserts that what SQLite prints still equals the recorded sample before
classifying it. That is what keeps this section honest as SQLite moves: if the
wording changes, the corpus is reported stale rather than quietly becoming a
record of a sentence SQLite no longer writes. Run against the pre-fix table, all
four of those tests fail, each on the verdict this section claims it repaired.

### What is deliberately not matched

Four FTS messages are left to `UNKNOWN`, and each is in the corpus with the
measurement behind it, because a decision not to match something rots in
silence otherwise.

| Message | Why it is not a needle |
|---|---|
| `fts5: ` on its own | The prefix says which module spoke, not what it said. `fts5: syntax error near ""` carries it and reports no damage whatever, reproduced here from a MATCH whose expression does not parse against an undamaged database (`fts5_syntax_error_message`). |
| `unable to validate the inverted index for FTS%d table %s.%s` | It names FTS5 twice and reports that the check could not be completed, which is the opposite of a finding (`unable_to_validate_fts_message`). |
| `invalid fts5 file format (found %d, expected %d or %d) - run 'rebuild'` | FTS5's own code writes it and it ends in an instruction to rebuild, so it reads like a repair order. What it reports is that this build does not recognise the index format it found, which a database written by a newer FTS5 produces with nothing wrong with it (`invalid_fts5_file_format_message`). |
| `fts5: missing row %lld from content table %s` | The same sentence comes back from a damaged shadow table and from a healthy index merely out of step with its content. The measurement is below. |

That last one was a needle until it was measured, and the measurement is the
sharpest case in this document of text that cannot decide what it means. On
SQLite 3.51.2, an external-content FTS5 index over a table whose rows were
never inserted:

```
PRAGMA integrity_check                                      -> ok
PRAGMA quick_check                                          -> ok
INSERT INTO notes_fts(notes_fts) VALUES('integrity-check')  -> ok
SELECT * FROM notes_fts WHERE notes_fts MATCH 'alpha'
  -> fts5: missing row 1 from content table 'main'.'notes'
```

and the same sentence from a database that really is damaged, with a row
deleted out of the content shadow table:

```
PRAGMA integrity_check
  -> malformed inverted index for FTS5 table main.messages_fts
SELECT * FROM messages_fts WHERE messages_fts MATCH 'gamma'
  -> fts5: missing row 2 from content table 'main'.'messages_fts_content'
```

Three separate SQLite checks call the first database healthy. The two messages
differ in a rowid and in the name of the table they print, and that name is the
whole difference: `'main'.'notes'` is the user's own table, while
`'main'.'messages_fts_content'` is a shadow table. Separating them means
deciding which kind of table a name belongs to, which takes the schema this
function is not given, and deciding it from the spelling of the name is the
criterion this task removed. So the needle is gone
(`fts5_missing_row_from_healthy_index`, `fts5_missing_content_row_message`).

Declining it costs nothing on the damaged side. That database announces itself
one line higher, through `integrity_check`, where `malformed inverted index for
fts` reads it. What was given up is a second route to damage that a healthy
database can take as well.

Everything the new criterion declines to match now reports `UNKNOWN` and lands
in `unclassified`, which is the cautious answer rather than a confident wrong
one: the text did not establish FTS damage, and the parser says so instead of
inventing certainty from a name.

### When the text is not enough

The converse is not covered and cannot be. **The absence of `FTS_CORRUPTION` is
not evidence that FTS is healthy**, and the corpus carries the proof: an FTS5
table's shadow tables are ordinary b-trees, so damaging the content table of
`messages_fts` produced

```
*** in database main ***
Tree 4 page 4 cell 0: Rowid 2 out of order
```

which is real FTS damage whose text names no FTS at all
(`fts5_shadow_table_btree_damage`). It classifies as
`CANONICAL_ROWID_DISORDER`, which is exactly what the text supports and is not
the whole truth about the database.

Nothing in the capture distinguishes that from the same damage to an ordinary
table, and this module reads captures. Establishing which tables are FTS tables
requires the schema, which the caller may not have and this function is not
given; deciding it from the message would put us back to reading names. So the
answer is a narrower claim rather than a metadata requirement: `FTS_CORRUPTION`
means SQLite's FTS code reported corruption, and its absence means only that
nothing in this text did.

That is one of two ways the text runs out, and the second is the harder one. The
first is a message that names no FTS when FTS is what broke. The second is a
message that names FTS and still does not say whether anything is wrong:
`fts5: missing row %lld from content table %s` arrives in the same words from a
healthy index out of step with its content and from a damaged shadow table, as
the measurement above sets out. The first is a gap in what the text mentions and
the second is a gap in what the text can decide, and neither closes by reading
harder. Both end in the same place, which is what the status is for: the parser
answers `UNKNOWN` and leaves the line in `unclassified` rather than choosing
whichever reading sounds more useful.

The same holds for the verdict as a whole. `UNKNOWN` on a capture full of `_fts`
lines is not a statement that FTS is fine; it is a statement that the text was
not read.

## The corpus

`tests/integrity_corpus.py` holds labelled samples. Each carries an origin:

- **`observed`**: captured from a real SQLite run, by creating a throwaway
  database and damaging it.
- **`synthetic`**: written to exercise a branch. It pins what this parser does
  with that shape and says nothing about what SQLite emits.

The distinction is load-bearing and is itself tested. Without it a later test
drifts into asserting that SQLite guarantees a shape nobody ever saw. Four
samples exist mainly to hold that line. `header_then_ok` is marked synthetic
because every clean database tried printed a bare `ok`, and the header appeared
only above real findings. The other three are marked synthetic although their
format strings were read out of the library itself, which is the harder case:
`unable_to_validate_fts_message`, `fts5_checksum_mismatch` and
`invalid_fts5_file_format_message` all quote a string SQLite really can write,
and none of them was captured. Taking the first of those, the string is
genuine and the capture is not, because it is emitted when the check fails for
a reason that is not corruption and no damage contrived here produced one.
Enumerating a format string proves the message exists, not that this is how it
arrives.

Only text is versioned. No corrupt database file is kept: a binary ages into
something nobody can re-derive, whereas the procedures below reproduce every
observed sample from scratch. What a procedure fixes is the damage. Whether the
text comes back verbatim as well depends on particulars the message embeds, an
index name or a row range among them, and an entry whose sample embeds any
names them. Several samples are past that line, and always for the same reason:
the message carries an internal address rather than a choice the procedure can
state. `fts5_corruption` quotes the id of the block that was zeroed,
`fts5_missing_content_row_message` the rowid it could not find,
`fts5_missing_row_from_healthy_index` the rowid put into the index, and
`fts5_shadow_table_btree_damage` a page and cell number inside the shadow
table. Each procedure reproduces the damage and the message; the numbers come
back as whatever that run allocated.

### Reproduction procedure

All of these create a database in a scratch directory. None of them touches an
existing file.

- **clean**: create a table, insert rows, run the check.
- **empty_file_is_clean**: create a zero-byte file, open it, run the check.
- **rowid_disorder**: create a table small enough that its root page is a leaf,
  then swap the first two 2-byte entries of that page's cell pointer array (at
  offset 8 into the page header, or 108 on page 1).
- **index_count_with_residue**, **btree_index_named_fts**: create a table and an
  index, insert rows, record the index's `rootpage`, delete its row from
  `sqlite_master` under `PRAGMA writable_schema=ON`, reopen and insert more rows
  so the index is never updated, then reinstate the `sqlite_master` row with the
  original `rootpage`. Both samples name their index and their rows, so both
  are fixed by the procedure: 200 rows first and 60 after, under an index named
  `idx_messages_session_id` for the first sample and `idx_fts` for the second,
  which is what makes the second one's every line contain `_fts`. The first
  sample is the whole capture and comes back from that procedure line for
  line; the second is an excerpt, and what it holds is the first five of the
  sixty residue lines rather than all of them.
- **orphan_pages**: the same, stopping after the `sqlite_master` deletion, so
  the index's pages are reachable from nothing. How many pages are orphaned
  depends on how wide the indexed values are, and the sample's five pages are
  not what a narrow column gives: 200 rows of `"s%06d" % i` repeated ten times
  reproduce exactly the recorded `Page 3, 4, 5, 9, 11`, while short values such
  as `s0`..`s199` fit in a single page and report only one.
- **attached_database_header**: the same orphaning, then open a separate
  connection and `ATTACH` the damaged file as `aux1` before running the check.
  This sample is a separate instance rather than the one above re-read: its
  indexed values are short, so one page is orphaned and one finding is printed.
- **fts5_corruption**: create an FTS5 table named `messages_fts`, insert rows,
  overwrite a block in its `%_data` shadow table with
  `zeroblob(length(block))`. The numeric blob id
  in the message identifies the block that was zeroed, so it depends on which
  row of `%_data` was chosen and on how many rows were inserted; the table name
  in the message is the FTS5 table's own. The recorded sample is one such
  capture rather than a value the procedure fixes.
- **fts5_malformed_inverted_index**, **fts5_missing_content_row_message**: one
  damaged database read two ways. Create an FTS5 table named `messages_fts`
  over a single column, insert the three rows `alpha beta sqlite`, `gamma delta
  sqlite` and `epsilon zeta sqlite`, then delete the second of them from the
  `messages_fts_content` shadow table with `DELETE FROM messages_fts_content
  WHERE id = 2`, which FTS5 does not see. The shadow table's columns are `id`
  and `c0` whatever the FTS table declares, so its own column name is not the
  one to delete by. Running the check prints the first sample; running `SELECT
  * FROM messages_fts WHERE messages_fts MATCH 'sqlite'` instead raises the
  second, whose text quotes the rowid that went missing. Two particulars decide
  whether that second sample arrives at all, and neither is visible in it. The
  query has to select a column, since `SELECT rowid` fetches no content row and
  raises nothing for any token; and the token has to reach the DELETED row,
  since `sqlite` is in all three rows and `gamma` is in the deleted one and
  both raise it, while `alpha` matches only a surviving row and returns it
  with no error. Updating a content row rather than deleting it reaches the
  same first message, so the wrapper is what the check prints for either.
- **fts5_missing_row_from_healthy_index**: no damage at all, and the twin of
  the sample above. Create an ordinary table `notes`, then an external-content
  FTS5 index over it declared with `content='notes'` and `content_rowid='id'`,
  and insert a row into the index alone with `INSERT INTO notes_fts(rowid,
  body)` without ever inserting it into `notes`. The index is now out of step
  with its content and nothing whatever is corrupt: `PRAGMA integrity_check`,
  `PRAGMA quick_check` and `INSERT INTO notes_fts(notes_fts)
  VALUES('integrity-check')` all return ok, while `SELECT * FROM notes_fts
  WHERE notes_fts MATCH 'alpha'` raises the sample. The rowid in the message is
  the one inserted into the index, and the table named at the end is the
  content table. That name is the only difference between this capture and the
  damaged one that a reader could decide anything from; the rowid differs too
  and says nothing, which is why the test blanks both.
- **fts4_malformed_inverted_index**: the same shape one module older. Create an
  FTS4 table named `m4`, insert rows, then empty its `m4_segdir` shadow table.
  The message differs from the FTS5 one only in the digit, which is what the
  needle is written to span.
- **fts5_syntax_error_message**: no damage at all. Create an FTS5 table, insert
  a row, and run a MATCH whose expression does not parse, such as `MATCH '('`.
  Several candidates were tried and most reach this same text: `(`, `^`, `{`,
  `a AND`, `a OR` and `NEAR(` all print it. Two do not, and they are worth
  recording because they show how narrow the path is: `"` is rejected earlier
  as an unterminated string, and `""` is accepted and matches nothing.
- **fts5_shadow_table_btree_damage**: create an FTS5 table named
  `messages_fts`, insert rows, read the `rootpage` of `messages_fts_content`
  from `sqlite_master`, then apply the rowid_disorder edit to that page,
  swapping the first two entries of its cell pointer array. The page and cell
  numbers in the message are wherever SQLite put that shadow table, page 4 in
  the recorded capture. The sample is here for what it does not say: the output
  names no FTS anywhere.
- **expression_index_named_fts**: create a table with no FTS in it, add an
  expression index named `idx_fts` over `lower(body)`, insert four rows, then
  hide the index from `sqlite_master` as above and **update** those four rows
  rather than inserting more before putting it back. Updating is what makes
  this sample what it is: the index keeps the right number of entries, so the
  count check prints nothing, and the capture is four unrecognised lines with
  no recognised line anywhere in it. Inserting instead prints `wrong # of
  entries in index idx_fts` first, which a signature matches.
- **mixed_fts_and_index_count**: both procedures on one database. Create
  `messages` with an index `idx_messages_session_id` and an FTS5 table
  `messages_fts`, insert twenty rows and eight documents, hide the index and
  insert five more rows before restoring it, then delete a row from
  `messages_fts_content`. The check prints seven rows: the count mismatch, five
  missing-row lines for rows 21 to 25, and the FTS wrapper last.
- **index_named_fts_message**: create a table `ordinary` with one column and
  insert three rows. Register a deterministic SQL function called `identity`
  that returns its argument, and create an expression index over it whose name
  is the FTS message being impersonated, quoting the name so the colon and the
  space are part of it: `CREATE INDEX "fts5: corrupt" ON ordinary(identity(x))`.
  Close the connection, reopen it, and register `identity` again under the same
  name and the same deterministic flag but returning its argument plus one, then
  run the check. Declaring a function deterministic is a promise that it answers
  the same thing for the same input, and SQLite relies on it: the stored index
  entries no longer agree with what the expression now computes, so every row is
  reported missing from the index. There is no FTS of any kind in this database.
  The name is what matters and it is printed unquoted, so the capture reproduces
  the needle `fts5: corrupt` exactly rather than merely containing it. Captured
  on SQLite 3.51.2. Substituting either of the other two FTS needles for the
  index name reproduces those the same way, which is what the parametrized test
  over the anchored needles asserts.
- **index_named_fts_message_beside_real_fts_damage**: both procedures on one
  database, and the order of the two halves does not matter. Build the ordinary
  table and its index named `fts5: corrupt` exactly as above, and in the same
  file create an FTS5 table `messages_fts` and insert three documents into it.
  Close, reopen, delete the row with id 2 out of `messages_fts_content`, then
  reopen once more with the altered `identity` and run the check. The output is
  four rows: three missing-row lines naming the index, and the FTS wrapper
  `malformed inverted index for FTS5 table main.messages_fts` last, which is the
  only one of the four that SQLite's own FTS code wrote. Captured on SQLite
  3.51.2.
- **not_a_database_via_stdout**, **not_a_database_message**: write text into a
  file and open it as a database. The shell prints to stderr with an empty
  stdout, so a stdout capture is empty; the exit status depends on the file, as
  recorded above. Python raises, and the message is the second sample.
- **malformed_schema_message**: under `PRAGMA writable_schema=ON`, set a table's
  `sql` in `sqlite_master` to something that will not parse, then reopen. The
  message quotes the table's name and the token SQLite stopped at, so both
  halves of the recorded `(t) - near "(": syntax error` come from the choices
  made here: the table was named `t`, and the replacement text put `(` where a
  keyword belongs. A different name or a different broken statement reproduces
  the class of message and not the sample verbatim.
- **disk_image_malformed_message**: truncate a populated database by a whole
  number of pages.
