---
id: TASK-24
title: SQL-01. Non dedurre FTS_ONLY dal solo nome dell'indice
status: Done
assignee:
  - '@opus-5-sql01'
created_date: '2026-09-16 12:20'
updated_date: '2026-09-17 02:02'
labels:
  - audit-2026-09-16
  - opus-5
  - sql
  - confirmed
milestone: m-3
dependencies:
  - TASK-25
references:
  - 'src/pyteman/sqlitekit/integrity.py:8-19'
documentation:
  - doc-1
  - doc-2
priority: high
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit 2026-09-16 sul commit a28b12662a46727ff806a42122db0ffe8333d760. Esecuzione futura prevista con Opus 5. Riprodurre il caso sullo stato corrente prima di correggere; non dipendere dalla conversazione originale.

**Priorità / stato:** P1, CONFIRMED su SQLite reale, aperto.

**File:** `src/pyteman/sqlitekit/integrity.py:8-19`.

**Evidenza:** una tabella ordinaria con indice espressione `idx_fts`, dopo sostituzione della funzione deterministica usata dall'indice, produce `row 1 missing from index idx_fts`; classify_integrity restituisce FTS_ONLY. Non è un indice FTS, il nome è soltanto una stringa scelta dall'utente.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 caso SQLite sopra non FTS_ONLY; fixture di veri shadow table/index FTS e danni misti classificate correttamente.
- [x] #2 Documentare quando il solo testo non basta e restituire un esito sconosciuto invece di inventare certezza.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Proposta iniziale da verificare sul codice corrente, non una correzione già applicata.

classificazione prudente basata su firme comprovate e, se disponibile, metadati di schema forniti esplicitamente. Non dedurre natura FTS da substring; mantenere separati indizi e classificazione certa. Testare danno misto FTS/canonico e nomi simili.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Indicazioni di coordinamento del documento di origine: SQL-02.

I prerequisiti operativi sono quelli nel campo Dependencies; i rinvii a consumer e file condivisi non impongono dipendenze reciproche. Aggiornare test e documentazione pertinente nello stesso task; riportare comandi e output reali prima di Done.

2026-09-17, rilievo documentale non bloccante emerso nella verifica indipendente di TASK-25 e registrato qui perche la correzione appartiene a questa tranche. La prosa dice che le righe non classificate sono conservate 'verbatim', ma classify_integrity applica str.strip a ogni riga prima di classificarla (`lines = [s for s in map(str.strip, text.splitlines()) if s]`), quindi 'unclassified' contiene righe normalizzate e solo 'raw' e integrale. Prova eseguita sullo stato approvato di TASK-25: classify_integrity('  mystery  \n') restituisce unclassified ['mystery'] mentre raw resta '  mystery  \n'. Occorrenze da correggere: docs/integrity.md riga 92, src/pyteman/sqlitekit/integrity.py righe 146 e 161, README.md riga 188 (unica frase sqlitekit gia nel perimetro). Vincolo esplicito del parent: non cambiare la semantica per sistemare la prosa. Si chiarisce che le righe sono normalizzate e che raw e integrale, e si aggiunge un test coerente sullo spazio bianco. Nessun campo nuovo nello schema di risposta.

## Simplify gate: outcome

Four cleanup reviewers ran in parallel (reuse, simplification, efficiency, altitude) against the post-implementation state. Findings were deduplicated and filtered: defects TASK-24 introduced were fixed, improvements to already-approved TASK-25 code with no defect behind them were not.

Applied, eight edits:

1. `test_the_needle_no_capture_backs_is_still_exercised_by_its_format_string` added to tests/test_integrity_classification.py. This closes a real coverage hole: the `fts5: checksum mismatch` needle was exercised by NO test. A reviewer proved it by deleting the needle and re-running, and the suite stayed green, because the other three needles keep FTS_CORRUPTION in every derived list. The needle was therefore deletable as dead code with no test objecting.
2. `test_every_needle_is_lowercase_because_matching_folds_the_line` added to the same file. Matching is `needle in line.lower()`, so an uppercase character in a needle makes it match nothing and fail silently. TASK-24 is what makes this worth pinning: the messages are mixed case on the wire, so pasting a newly observed message straight into the tuple is the natural next edit and is the one that breaks.
3. The `_SIGNATURES` ordering comment in integrity.py rewritten. My own change had made it false: it described the tuple as being in the order the entries were written, but the four FTS needles were inserted AHEAD of the CANONICAL pair that predates them.
4. The third paragraph of the `_SIGNATURES` FTS comment shortened. It re-derived an argument the module docstring makes sixty lines above; flagged independently by the reuse and the simplification reviewer as the cheapest available cut.
5. `SIGNATURE_NAMES` in test_docs_integrity.py deduplicated to `sorted({name for _, name in integrity._SIGNATURES})`. Fallout from the table becoming one-to-many: it yielded FTS_CORRUPTION four times, so one missing documentation paragraph reported itself as four separate defects.
6. The unreachable half of the truncation-message assertion removed.
7. The `DOCUMENTED_PROCEDURES` comment corrected. It claimed an independence that does not exist: it is `set(BODY_BY_NAME)` and shares every assumption `_entries` makes about the section formatting. What the two directions of the check genuinely do not share is the SOURCE of the names, and the comment now says that instead.
8. `CODER_PAOLO_FTS` in tests/test_integrity.py now reads `BY_NAME["fts5_malformed_inverted_index"].text` instead of repeating the string. Verified byte-identical before substituting. The duplicate was a defect TASK-24 introduced and it was the dangerous kind: the needle is a PREFIX of the message, so a stale copy would keep passing and the test could never report that it had drifted. `INCIDENT_ROOT` in the same file is deliberately left as a literal and now says why: it is not a corpus sample, it predates the corpus, and slicing it out of a longer sample would be a derivation the reader cannot check.

## Documentary finding: closed

The non-blocking finding recorded above is now corrected at all four occurrences. `unclassified` is normalised rather than verbatim, because the code strips every line; only `raw` is integral. Corrected at docs/integrity.md:92, integrity.py:146, integrity.py:161 and README.md:188. The semantics were NOT changed to fit the prose, per instruction: the prose was corrected to fit the measured behaviour, and the whitespace test is consistent with it.

## Deferred, filed as their own tasks in the same turn they were skipped

- TASK-96: derive the reproduction procedures from the corpus instead of parsing them back out of the document. Raised by the altitude review. The current checks are live and correct, so this is a structural improvement to approved TASK-25 code with no defect behind it.
- TASK-97: executable reproducers for the observed samples, following the examples/hermes-111912 and examples/hermes-109966 pattern, which would make the document's reproduced-here column derivable rather than asserted in prose.

## Skipped deliberately, with reasons

- Deleting the five-name non-CLEAN loop and the empty-string test as subsumed. Both do carry overlapping coverage, but deleting a test removes real coverage for a cosmetic gain and the overlap is not total.
- Deriving `STATUSES` in test_integrity_classification.py from the module. Approved TASK-25 code with no defect today; a drive-by.
- A `_CLASS_NOTES` mapping to hold the FTS sentence in `_diagnose`. Speculative generality for a single class.
- Asserting the SQLite version in the suite. Would version-lock the tests to the host library, and a divergence there is news about SQLite rather than a defect here. TASK-97 is the right home for that signal.
- Hardening the citation-harvest regex. Fragile for no measured gain; the current form was confirmed to harvest exactly the four real sample names.
- Rewrapping long lines in README.md, tests/integrity_corpus.py and docs/integrity.md. Reformatting, explicitly out of scope.

## Test perimeter after the simplify gate

tests/test_integrity.py, tests/test_integrity_classification.py and tests/test_docs_integrity.py: 226 passed. The count moved from 227 to 226 rather than to 229, and the cause is edit 5 above rather than a regression: `_SIGNATURES` holds 8 rows over 5 distinct names, so deduplicating the derived list dropped `test_every_signature_name_is_documented` from 8 parametrized cases to 5. 227 minus 3 plus the 2 new tests is 226, which is the number observed.

FINDING A (critical, from code review, reproduced independently twice): the needle `fts5: missing row` reported status=damaged / FTS_CORRUPTION on a database that is not damaged. Measured on SQLite 3.51.2. Build an ordinary table `notes` and an external-content FTS5 index over it (`content='notes'`, `content_rowid='id'`), then insert a row into the index alone without inserting it into `notes`. The index is out of step with its content and nothing is corrupt: `PRAGMA integrity_check`, `PRAGMA quick_check` and FTS5's own `INSERT INTO notes_fts(notes_fts) VALUES('integrity-check')` all return ok, while `SELECT * FROM notes_fts WHERE notes_fts MATCH 'alpha'` raises `fts5: missing row 1 from content table 'main'.'notes'`. A genuinely damaged database (a row deleted out of `messages_fts_content`) raises `fts5: missing row 2 from content table 'main'.'messages_fts_content'`. The two sentences differ only in a rowid and in whether the printed table is a shadow table, and deciding that requires the schema, which is exactly the name-reading this task exists to abolish. So the needle is removed and that text now reports UNKNOWN.

Removing it costs no coverage of real corruption: the damaged database is reported separately by integrity_check as `malformed inverted index for FTS5 table main.messages_fts`, which the first FTS needle reads. Pinned by test_declining_that_sentence_costs_no_coverage_of_the_damaged_database.

FTS ERROR FORMAT STRINGS, enumerated from the library actually in use (`strings -a /lib64/libsqlite3.so.0`, SQLite 3.51.2) rather than from memory or from a reviewer's claim: `fts5: checksum mismatch for table "%s"`, `fts5: corruption found reading blob %lld from table "%s"`, `fts5: corruption in table "%s"`, `fts5: corruption on page %d, segment %d, table "%s"`, `fts5: corrupt structure record for table "%s"`, `fts5: missing row %lld from content table %s`, `fts5: syntax error near "%.1s"`, `invalid fts5 file format (found %d, expected %d or %d) - run 'rebuild'`, `malformed inverted index for FTS5 table %s.%s`, `malformed inverted index for FTS%d table %s.%s`, `unable to validate the inverted index for FTS%d table %s.%s: %s`.

Two consequences. First, the needle `fts5: corrupt` covers FOUR of those format strings at once, because the library writes both `corrupt` and `corruption` across the same family of faults; the comment in _SIGNATURES now says so. Second, `invalid fts5 file format` is real FTS5 text whose honest verdict is UNKNOWN rather than damage: it is what a database written by a NEWER FTS5 produces with nothing wrong with it. It is in the corpus as a synthetic sample with that measurement, and pinned by test_a_format_this_build_cannot_read_is_not_read_as_damage. The gap it exposed was documentation, not classification, so no needle was added for it.

DESIGN RULE now written into the module docstring: having been written by the FTS module is NECESSARY AND NOT SUFFICIENT for FTS_CORRUPTION. The bare `fts5: ` prefix marks which module spoke, not what it said, and arrives on syntax errors from undamaged databases.

OUT-OF-PERIMETER DEFECTS FILED SO NO REVIEW RECOMMENDATION LEAKS: TASK-98 (Low) holds the integrity_check header shape that can swallow a finding written on the same line. TASK-99 (Medium) holds the fact that the needles are unanchored substrings, so a user-chosen object name interpolated into a finding line can take that line's class, and the `break` then hides the class the line deserved, with an empty `unclassified` to show for it. The vector is exotic (it needs a deliberately quoted identifier such as `CREATE INDEX "fts5: corrupt idx"`) and it pre-exists this task in the approved CANONICAL needles.

ANCHORING IS NOT THE FIX, and this is recorded in TASK-99 because a reviewer recommended it. Anchoring the needles to the start of a line with `line.startswith` would break the capture path this module documents: measured on the sqlite3 shell 3.53.4, error lines arrive prefixed, as in `Parse error in 2nd command line argument: file is not a database (26)`, so `file is not a database` would stop matching altogether. Accepting that recommendation would have traded an exotic bug for a regression on the common path. The unanchored substring match is load-bearing rather than an oversight.

Count correction. Earlier notes on this task recorded 8 signature rows over 5 distinct names, FTS_CORRUPTION yielded four times, and 226 tests in the perimeter. All three were superseded by later work in the same tranche and are wrong as they stand. Measured from the code just now: _SIGNATURES holds 7 rows over 5 distinct class names, of which 3 carry FTS_CORRUPTION, and the corpus holds 29 samples, 20 observed and 9 synthetic. The perimeter is 242 tests and the full suite is 615 passed with 7 failures in tests/test_activation_atomic.py that belong to the concurrent agent and are described below.

Simplify gate applied, four reviewers on reuse, simplification, altitude and a stale-prose angle substituted for the stock efficiency angle because the work is prose-heavy. Seventeen fixes applied. The load-bearing one: the citation harvester in tests/test_docs_integrity.py used a regex requiring a single backticked name alone inside parentheses, so the one citation naming two samples, which is the pair carrying this task's central measurement, was harvested by nothing. Measured rather than taken on report: the old pattern finds 3 names in that section and the new one finds 5, and the 2 it missed are fts5_missing_row_from_healthy_index and fts5_missing_content_row_message. The harvester now reads the list form and is pinned by its own test. Two further guards were added: the section listing what is deliberately not matched is now read back and executed, so every message the document says is left at UNKNOWN has to actually classify that way, and btree_index_named_fts, which no test classified at all, is now pinned by parametrizing the ordinary-index-named-fts test over both samples. A test helper was tightened: the skeleton comparison blanked every digit run including the module number, so it equated an FTS5 message with the FTS4 spelling of the same line, which is the distinction another corpus sample exists to keep visible. Verified both directions by running it.

Deferred recommendations filed rather than dropped: TASK-101 carries the three structural proposals against already-approved TASK-25 shapes, which are expected-verdict fields on Sample, a class-notes mapping in _diagnose, and a sample-pairing field. TASK-102 carries five redundancy items, which are the entailed not-CLEAN loop, a third pin of one sample verdict, a derivable alias in the docs tests, a comprehension variable named l, and the three-way duplication of the FTS criterion account across module docstring, document and corpus notes. Nothing from the reviews was left unlanded.

Unrelated failures observed in the full suite and not touched: 7 tests in tests/test_activation_atomic.py fail on a ledger entry arity mismatch, ValueError unpacking 3 values where 5 are expected and the reverse. src/pyteman/patcher.py was written at 02:31 and tests/test_activation_atomic.py at 01:47, so the test file predates the production change. Both belong to the concurrent rules agent. No file in this task's perimeter is implicated and none was modified in response.

Retraction of an earlier skip recorded on this task. The note above under 'Skipped deliberately' says hardening the citation-harvest regex was fragile for no measured gain and that the current form was confirmed to harvest exactly the four real sample names. The second half of that was wrong and the first half followed from it. The form `\(`([a-z0-9_]+)`\)` requires the closing parenthesis immediately after the backtick, so it reads a citation naming one sample and silently skips one naming two. At the time that skip was written the document contained exactly such a citation, holding the pair of samples this task's central measurement rests on, so the gain was real and was measurable then. It has now been measured and the regex reads both forms. Recorded here rather than by rewriting the earlier note so that the reasoning error stays visible: the skip was justified by an unverified claim about what the pattern harvested, and one run of the pattern would have refuted it.

## Code review gate: findings reconciled, each verified by measurement first

The high-effort code review returned AC 1 met, AC 2 met, code correctness clean. It stated plainly that it had no shell tool and verified by reading and hand-derivation only, so both of its findings were re-derived here by running code before anything was edited.

FINDING 1, CONFIRMED and fixed. The module docstring generalised one observation into a universal: 'Damage to an FTS table's own shadow tables is printed as ordinary b-tree damage naming no FTS at all, observed here on a corrupted messages_fts_content'. The corpus contradicts it on the very table cited. Re-measured on SQLite 3.51.2 this turn: create messages_fts, insert three rows, DELETE FROM messages_fts_content WHERE id = 2, and PRAGMA integrity_check prints 'malformed inverted index for FTS5 table main.messages_fts', which the first needle reads. So that same shadow table prints FTS under one damage and no FTS under another (fts5_shadow_table_btree_damage), and fts5_corruption is a second shadow table (%_data) printing FTS. The claim is now the narrow one the paragraph needs: SOME shadow-table damage prints as ordinary b-tree damage, and which form arrives depends on the damage rather than on the table. Corrected at both sites that carried the universal, src/pyteman/sqlitekit/integrity.py and the docstring of test_fts_damage_can_arrive_with_no_fts_anywhere_in_the_text.

FINDING 2, REFUTED AS FRAMED, and the defect underneath it fixed. The review reported docs/integrity.md as recording two conflicting search tokens for one capture, MATCH 'gamma' in the measurement block and MATCH 'sqlite' in the procedure, concluding the documented route back to the sample does not work. Measured: BOTH tokens raise the recorded sample text verbatim, so neither record is wrong and reconciling them would have deleted a true measurement. What is真 wrong is different and was invisible to the review. Two particulars decide whether the sample arrives and neither is in the sample: the query must select a column, since SELECT rowid fetches no content row and raises nothing for any token, and the token must reach the DELETED row. Measured: 'sqlite' (in all three rows) and 'gamma' (in the deleted row) both raise it; 'alpha' and 'epsilon' match only surviving rows and return normally with no error. The procedure said only 'insert rows'. It now states the three row texts, the exact DELETE, the fact that the shadow table's columns are id and c0 whatever the FTS table declares, and both particulars. This is a deliberate divergence from the reviewer's recommended fix and is reported as such.

Typo correction to the note above: the sentence reading 'What is真 wrong is different' carries a stray character and should read 'What is wrong is different'. The text is otherwise as intended.

## Three below-bar review items, landed rather than filed

The review listed three items below its reporting bar. All three were verified here and fixed in the same turn, none deferred.

1. docs/integrity.md said a None input 'failed on .strip()'. Measured: classify_integrity evaluates text.splitlines() first, so None raises on .splitlines(). Both spellings produce an AttributeError naming only NoneType, which is why the error never contradicted the prose. Corrected to .splitlines(), which is what integrity.py:258 and the test at test_integrity_classification.py already said.
2. The provenance header credited TASK-25 with everything before 'What the old criterion did'. docs/integrity.md is untracked, so git cannot adjudicate it; the contemporaneous record on this task can, and it states that TASK-24 corrected docs/integrity.md line 92, inside the unclassified bullet, when it closed the verbatim-versus-normalised finding. The header now says the split is by subject rather than by position and names that bullet as TASK-24's.
3. The class-ordering test said 'the corpus pair' in the singular. Measured by classifying every sample: two multi-class verdicts exist, mixed_fts_and_index_count (CANONICAL_INDEX_COUNT, FTS_CORRUPTION) and mixed_known_and_unknown (CANONICAL_INDEX_COUNT, CANONICAL_ROWID_DISORDER). The 27-of-60 seed measurement was taken on one pair and is not restated as though it covered both; the docstring now says one such pair was measured, that the corpus holds two since TASK-24, and that a second coin flip is not a check on the first.

## Gate status for this increment

Everything changed since the code review is documentation-only and is exempt on that basis. Proved rather than asserted: each of the four strings written into .py files this turn was confirmed to lie inside a docstring by parsing the AST and searching only ast.get_docstring output, each occurring exactly once. The remaining three edits are in docs/integrity.md. The executable state that the simplify and code-review gates ran against is therefore unchanged, and no needle, constant or branch was touched.

## Test perimeter, precisely delimited

Perimeter is exactly three files, tests/test_integrity.py + tests/test_integrity_classification.py + tests/test_docs_integrity.py: 242 passed. Predicted 242 before running, on the grounds that no test was added or removed and only prose changed, and observed 242.

Full suite: 629 passed, 0 failed. This is NOT the 615 passed / 7 failed reported earlier and the change is not mine. The 7 failures were in tests/test_activation_atomic.py, owned by the concurrent rules agent; that file was rewritten at 09-17 02:40, after their src/pyteman/patcher.py at 02:31, and it now passes 43 tests on its own. Collected count rose from 622 to 629, so they also added 7 tests. My integrity.py was written at 02:49 and touches nothing they own.

## SHA256 file ownership, TASK-24 perimeter, current state

6ceb63b9ec37bfd83fe3e67a4c8443e2c381cdc765ac3e6d05afba212278efd5  src/pyteman/sqlitekit/integrity.py
b058e41f8ccf8f3ca4b0ed43e2d6192310cc08f1e49d226fdfbe9c9bd33d8ef1  tests/test_integrity.py
4d37c5ce0f218c3bce5f1b29f55c3e780ef5b5a7b9a3c820503521e7b4998678  tests/integrity_corpus.py
e35862214330a584c520136eda308f47e0fa8c4fe6739c559fa6f05d7cedf083  tests/test_integrity_classification.py
4e2ad6be678c583c835cbb0c8acbbe1fb5818f91782e5e7355a8b932751639bc  tests/test_docs_integrity.py
2b3d44e12c4809668e13a49f3419a696014e2778b12dca1b90ef81830ab40a04  docs/integrity.md

Frozen APPROVED files re-hashed and byte-identical to the recorded values: report.py bd0b0770..., test_report_escaping.py 6e8c4169..., test_report.py 6c30d101..., test_matrix.py 16f191d8....

Status stays In Progress and both acceptance criteria stay unchecked pending the parent's APPROVED, per the agreed gate order. No commit, no push.

## CHANGES REQUESTED by the parent, 2026-09-17. Reproduced here before accepting.

The verification rejected the tranche on the ground that the new FTS match still carries the central defect of this task, FTS inferred from the name of an ordinary index. It is right, and the reproduction is worse than the one it sent.

Measured on SQLite 3.51.2, real damage and real integrity_check output, five statements:

    con.create_function('identity', 1, lambda x: x, deterministic=True)
    CREATE TABLE ordinary(x); INSERT INTO ordinary(x) VALUES (1);
    CREATE INDEX "fts5: corrupt" ON ordinary(identity(x));
    # re-register identity as lambda x: x + 1, so the index is out of step
    PRAGMA integrity_check  ->  row 1 missing from index fts5: corrupt
    classify_integrity(...)  ->  damaged ['FTS_CORRUPTION']

All THREE FTS needles are reachable this way, not the two the parent named. Index named 'fts5: corrupt', 'malformed inverted index for fts5' and 'fts5: checksum mismatch' each produce their own needle inside a line about an ordinary b-tree index, and each returns FTS_CORRUPTION. An index named 'idx_fts' correctly returns unknown, which is the half of this task that does work.

The class of defect survived the rewrite. The old criterion read `_fts` out of a name; the needles I put in its place read an entire FTS message out of a name. The database in this reproduction contains no FTS of any kind.

## The discriminating capture, one real database, four real finding lines

Built here: an ordinary table whose expression index is named 'fts5: corrupt', plus a genuine FTS5 table in the same file with a content row deleted behind FTS5's back. PRAGMA integrity_check returns:

    row 1 missing from index fts5: corrupt
    row 2 missing from index fts5: corrupt
    row 3 missing from index fts5: corrupt
    malformed inverted index for FTS5 table main.messages_fts

The first three are not about FTS and the fourth is. Measured on the current code: the whole capture returns damaged ['FTS_CORRUPTION'] with unclassified empty, and the first three lines ALONE return damaged ['FTS_CORRUPTION'] with unclassified empty. The two verdicts are identical, so on this capture the class carries no information whatever, and nothing in the verdict reports that three lines were read wrongly rather than not read.

## Why my earlier 'anchoring is not the fix' note was wrong

It argued from a true premise and stopped one step short. The sqlite3 shell does prefix its error lines, so anchoring to the raw start of a line would break the documented shell capture path. What the note never considered is that the prefixes are a small closed family with a locator and a colon, and that stripping the wrapper BEFORE anchoring keeps both properties. Re-measured on shell 3.53.4, both families:

    Parse error in 2nd command line argument: file is not a database (26)
    Parse error near line 1: file is not a database (26)
    Parse error near line 1 of script.sql: near "hello": syntax error
    Error in 2nd command line argument: fts5: missing row 2 from content table 'main'.'messages_fts_content'
    Error near line 1: fts5: missing row 2 from content table 'main'.'messages_fts_content'

Prepare-time faults say 'Parse error', run-time faults say 'Error', and both carry a locator then ': '. In every genuine FTS capture measured here the diagnostic BEGINS the message: integrity_check returns 'malformed inverted index for FTS5 table main.messages_fts' as a row of its own at column zero.

## Shape of the fix, and why it does not extend to the canonical needles

The two families are different kinds of text, which is what makes the split principled rather than arbitrary. An FTS diagnostic is a COMPLETE message and begins its line, so it can be required to begin the line. 'out of order' is a FRAGMENT inside a larger finding, 'Tree 2 page 2 cell 0: Rowid 2 out of order', so the same rule cannot be applied to it at all. So the FTS needles move to a start-of-message match after known shell prefixes are stripped, and the canonical needles stay as they are. TASK-99 holds that residue and its description has been corrected in this turn: the two refuted claims are recorded there as refuted, with the reproduction that refutes them, rather than deleted.

Stripping is computed for matching only. The line kept in 'unclassified' stays exactly what arrived, whitespace-stripped as before, so no approved output contract moves.

Status stays In Progress. No Done, no new generic scope.

## Correction implemented, 2026-09-17

The positional fix described above is now in the code. `_SIGNATURES` became 3-tuples of (needle, class, mode). `_matches(line, needle, mode)` dispatches on the mode and RAISES ValueError on an unrecognised one, because a silent never-match is the fail-open class this tranche exists to remove. The three FTS needles carry `_ANCHORED` and match with startswith against the line after `_strip_shell_wrapper` removes a known sqlite3-shell prefix; the four canonical needles keep `_CONTAINED`, for the shape reason recorded above.

Both mode constants are PRIVATE on purpose. tests/test_docs_integrity.py harvests every public uppercase string constant of the module as a documented status, so a public spelling would invent two phantom statuses and break that test.

`_SHELL_WRAPPER` covers the two observed families, `Parse error <locator>: ` and `Error <locator>: `, with the locator forms `in Nth command line argument`, `near line N` and `near line N of <path>`. The path alternative is NON-GREEDY on purpose and a test pins it: greedy was measured to reduce `something: malformed inverted index for FTS5 table main.t` to the bare needle and manufacture an FTS_CORRUPTION verdict, while non-greedy leaves the prefix in place and yields UNKNOWN. That is the fail-closed direction, and an unrecognised prefix costing UNKNOWN is the intended price. A bare `Error: ` with no locator is deliberately not stripped.

The stripped text is used for MATCHING ONLY. `unclassified` and `raw` keep what arrived, so no approved output contract moved.

## The captures are re-derived, not only recalled

Four tests at the end of tests/test_integrity_classification.py build a real database, damage it, read `PRAGMA integrity_check` in process, and assert that what SQLite prints still EQUALS the recorded corpus sample BEFORE classifying it. That is what answers the parent's constraint that no authenticity be promised for arbitrary text: the format of the known captures is checked mechanically, and if SQLite rewords a message the corpus is reported stale rather than quietly becoming a record of a sentence SQLite no longer writes.

- `test_a_live_index_named_after_an_fts_message_reports_no_fts_damage`: expression index named `fts5: corrupt` over an ordinary table, no FTS in the database, damaged by re-registering the deterministic function the index was built on. Capture equals `index_named_fts_message`; verdict UNKNOWN, classes `[]`, three lines in `unclassified`. This is AC1.
- `test_a_live_database_tells_real_fts_damage_from_an_index_named_after_it`: the same index beside a genuine FTS5 table with a content row deleted behind FTS5's back. Capture equals `index_named_fts_message_beside_real_fts_damage`; verdict DAMAGED, classes `["FTS_CORRUPTION"]` from the genuine line only, the three name lines in `unclassified`. This is AC2.
- `test_a_live_count_fault_keeps_its_class_when_the_index_is_named_for_fts`: the same name reached by the count-fault route, which needs a file on disk because the schema is re-read on open. First line is `wrong # of entries in index fts5: corrupt` and the class is `CANONICAL_INDEX_COUNT`, which is the SUPPRESSION half: before the fix the correct class was never reached.
- `test_a_live_capture_carrying_both_families_reports_both`: one database carrying both faults, reporting both classes with five lines unclassified.

Red half proved rather than assumed. With `_SIGNATURES` monkeypatched back to all-`_CONTAINED` (a conftest in /tmp, so no tracked file was ever left in a wrong state), all four fail, each on its predicted verdict rather than on an incidental error.

The two FTS5 tests are skipped when the build has no FTS5. The skip is computed by actually creating an FTS5 table rather than by reading a compile option.

## The needle TEXT is now bound to the document

`test_every_needle_is_quoted_in_the_document` was added because only the CLASS NAMES were bound to docs/integrity.md; the needle strings themselves were checked by nothing, so a needle could be edited and the document would keep describing the old one, green. Whitespace is collapsed first because at least one needle is line-wrapped inside its own backticks.

## Hashes recorded earlier on this task are SUPERSEDED

The SHA256 block above, which lists `6ceb63b9...` for integrity.py, predates this correction and is stale for five of the six files. The current block is recorded below once the targeted review on the final state has landed and its findings are resolved. Status stays In Progress, both acceptance criteria stay unchecked, no commit, no push.

## Consegna definitiva TASK-24 / SQL-01 (2026-09-17). Supersedes the earlier hash block (6ceb63b9...), which is stale.

### 1. Final review disposition

The high-effort review of the final state returned one critical finding and one unproven claim. Both were re-derived here by running code before anything was edited, because the reviewer had no Bash tool and said so.

**Finding 1, CONFIRMED and FIXED.** `classify_integrity` split its input with `str.splitlines()`, which breaks on `\v`, `\f`, `\r`, `\x1c`, `\x1d`, `\x1e`, `\x85`, U+2028 and U+2029. SQLite emits none of those as a line break, and an object name may contain any of them, printed unquoted. So the parser manufactured a line boundary out of a character the user chose, put the rest of that name at position 0, and the anchored FTS needle then matched it. This defeats the exact mechanism TASK-24 delivers and violates AC1. Measured in process on SQLite 3.51.2, an index named `x<U+2028>fts5: corrupt` over an ordinary table in a database holding NO FTS:

    PRAGMA integrity_check returned ONE row
    pre-fix : damaged ['FTS_CORRUPTION'] unclassified=['row 1 missing from index x']
    post-fix: unknown [] unclassified=['row 1 missing from index x fts5: corrupt']

Fix: `text.split("\n")`, the only boundary SQLite writes. That closes all nine characters.

**The `Runtime error` shell prefix, REFUTED.** The reviewer hypothesised a third wrapper family and labelled it training-data memory rather than measurement. Probed on shell 3.53.4 across the one-argument form, piped stdin, `.read` of a script, and the stepping path (error raised after a row had already printed, via a deleted `m_content` row): every one emitted `Error <locator>: `. The stepping path gave `Error near line 1: fts5: missing row 2 from content table 'main'.'m_content'`. The only bare `Error: ` strings in the binary are dot-command errors, already documented as deliberately not stripped. The closed family in `_SHELL_WRAPPER` holds and was not widened.

**Six attacks on `_SHELL_WRAPPER`, all failed**, recorded as evidence rather than as a change.

**Four live tests traced**, no incidental-pass route found; the saved-rootpage logic in `_count_fault_on_a_named_index` confirmed correct.

**Three new tests also pass pre-fix.** Reported as fact; two of the three carry no label saying so. Not changed, because relabelling pre-existing tests is outside the disposition scope agreed for this turn.

### 2. What changed AFTER the review, exactly

Six edits, no other executable change:

1. integrity.py: `lines = [s for s in map(str.strip, text.splitlines()) if s]` became `text.split("\n")`, with a comment carrying the measurement. This is the only behavioural change.
2. integrity.py: the docstring of `classify_integrity` corrected, `.splitlines()` to `.split()`.
3. integrity.py module docstring and the `_SIGNATURES` comment: two absolute claims corrected. Both said an object name is never the first thing on a line. True only of a line SQLITE EMITTED, and this module makes the lines itself, so the anchor is worth exactly as much as the split beneath it. Both now say that and point at the split.
4. docs/integrity.md: the same absolute corrected, plus the measurement and the residue, plus a paragraph recording that the two captures are re-derived rather than only recalled.
5. tests/test_integrity_classification.py: two tests appended, described below.
6. tests/integrity_corpus.py: the `fts5_corruption` note lost a catalogue of four sample names that nothing resolved (last in-scope simplify finding).

Note on notation: the note above renders the U+2028 sample name with the character itself inside the post-fix line. Everywhere else in code and document it is written `<U+2028>` on purpose, and the source now holds ` ` as an escape, because a comment whose meaning depends on an invisible character is one an editor silently destroys.

### 3. The two new tests, red-green verified

`test_a_boundary_the_parser_invented_cannot_carry_an_anchored_needle` builds the live database, asserts SQLite returned ONE row, asserts the capture text, then asserts UNKNOWN with the whole row in `unclassified`. GENUINE regression test: verified against the pre-fix module, reconstructed in memory by substituting `splitlines()` back and exec'ing it as its own module object, so nothing on disk was mutated and no apply/revert happened on the shared checkout. Pre-fix it returns damaged ['FTS_CORRUPTION'], so all three assertions fail.

`test_a_real_newline_inside_a_name_is_the_residue_task_104_holds` is a TRIPWIRE ON A KNOWN WRONG VERDICT and its docstring says so in those terms. It asserts `classes == ["FTS_CORRUPTION"]`, which is what the code does today and not what it should do. Pre-fix and post-fix are identical here, which is the residue claim itself. When TASK-104 lands this test fails, and that failure is the signal.

### 4. Residue, filed the same turn it was named

TASK-104 (SQL-01b, m-3, medium, depends on TASK-24) now exists and carries the confirmed capture, the reproduction, the header-swallow variant, and the two candidate fixes worth measuring. It was named in a shipped code comment and twice in docs/integrity.md, so it was an outstanding promise; it is no longer. TASK-103 already holds the four out-of-diff simplify findings.

### 5. Test perimeter, delimited by collection rather than by recollection

Perimeter is exactly three files and nothing else:

    tests/test_integrity.py                     5 collected
    tests/test_integrity_classification.py    186 collected
    tests/test_docs_integrity.py               93 collected
                                              --- 
                                              284, and 284 passed in 0.19s

That is 282 before this turn plus the 2 tests above. Full suite: 693 passed, 0 failed, 693 collected. The full figure moved from 673 and the delta is NOT all mine: 2 of it is, and the rest belongs to the concurrent rules agent, whose files I do not own and did not touch. The 284 is the number to judge this task by.

### 6. SHA256, frozen on the final reviewed state

These supersede every earlier hash block on this task. Five of the six moved; `tests/test_integrity.py` did not and its hash is unchanged from the previous record, which is itself a check.

    0fece2abc4dc103fc747a7edfe7520c428840dd7e142be99d40b48725c1447e1  src/pyteman/sqlitekit/integrity.py
    b058e41f8ccf8f3ca4b0ed43e2d6192310cc08f1e49d226fdfbe9c9bd33d8ef1  tests/test_integrity.py
    3fe211eff0c31b0f3b52790f4608904f38bb8f74b7a327783662fea047c16a1c  tests/integrity_corpus.py
    d40c5b9225b174feb7741598ef4394157b61890a40bbb76ca4299057c718ece9  tests/test_integrity_classification.py
    440e812c5bf6d02197ca226837c23cbc73f7fdceb02c120d1ebdd1e85985e574  tests/test_docs_integrity.py
    cd87bdfbedb031e809ea5a2a7694940f0b4f0c98244c7cc5693940ebec526a83  docs/integrity.md

Sizes: integrity.py 445 lines, test_integrity_classification.py 1345, docs/integrity.md 590.

Frozen APPROVED files re-hashed this turn and byte-identical to their recorded values:

    bd0b0770fbd348775668ffcdc8283d0366989267d86770d6df2166f2b3d13e6e  src/pyteman/runner/report.py
    6e8c41690ce77594ab6a166beb42cc6d9c17dd29ba961209a558adaf0586110c  tests/test_report_escaping.py
    6c30d1016edf074266f2b6236eee9d3fbfd2052c1460d2c0292bcb0215cb4e35  tests/test_report.py
    16f191d8ed7523c7807ae13de236ea8290fd48073176da8c5933abcf1d3c1599  tests/test_matrix.py

Reviewers must read four of the six whole rather than diffing: docs/integrity.md, tests/integrity_corpus.py, tests/test_docs_integrity.py and tests/test_integrity_classification.py are UNTRACKED, so `git diff` shows only integrity.py and test_integrity.py.

### 7. Gate status, stated rather than implied

Simplify ran on the pre-review state and its last in-scope finding is item 6 above; the four out-of-diff ones are TASK-103. Code review ran at high effort on the final state and both of its claims are dispositioned in section 1. Tests were run this turn and the output read.

What has NOT had a fresh full review round is the six-edit delta in section 2, because the peer's instruction for this turn was targeted dispositions and a frozen delivery rather than another round. That delta is one changed line of executable code, which is the reviewer's OWN prescription applied, plus two tests whose red half was proved mechanically, plus prose. It is named here so the peer's verification can cover it deliberately instead of inheriting it silently.

No simplify pass was run over pre-existing tests, per instruction. No refactor was performed.

### 8. State on delivery

Status In Progress. Both acceptance criteria UNCHECKED. No commit, no push, no branch operation; HEAD is still a28b126 and the working tree carries this tranche plus the concurrent agent's, untouched by me. Awaiting APPROVED.
<!-- SECTION:NOTES:END -->
