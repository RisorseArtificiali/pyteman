import json
import sqlite3

import pytest

from pyteman.firing import open_log
from pyteman.rules import Rule, RuleError, load_rules
from pyteman.patcher import install
from pyteman.targets import resolve_target

import target_mod
from target_mod import SessionDB
from hostile_fixtures import PARITY_INPUTS, InterruptName, Nameless
from test_log_actions import ends, records


def outcomes_of(logpath, log):
    log.close()
    return [json.loads(l).get("outcome") for l in logpath.read_text().splitlines()]


def make_rule(point, action, event="entry"):
    return Rule(id="t", module="target_mod", symbol=point, event=event,
                action=action, fire={"mode": "always"})


def pragma_action(target=None, name="synchronous", value="OFF"):
    a = {"kind": "pragma", "name": name, "value": value}
    if target is not None:
        a["target"] = target
    return a


def sync_of(con):
    return con.execute("PRAGMA synchronous").fetchone()[0]


@pytest.fixture
def session(tmp_path):
    s = SessionDB(str(tmp_path / "state.db"))
    yield s
    s.close()


def test_self_walk_reaches_attribute_held_connection(session):
    # The hermes shape: the connection lives on self._conn, not in the args.
    assert sync_of(session._conn) != 0  # not already OFF
    p = install([make_rule("save", pragma_action(target="self._conn"))], log=None)
    try:
        p.force_patch_module("target_mod")
        target_mod.save(session, "hello")
        assert sync_of(session._conn) == 0
    finally:
        p.uninstall()


def test_method_receiver_is_self(session):
    p = install([make_rule("SessionDB.append", pragma_action(target="self._conn"))], log=None)
    try:
        p.force_patch_module("target_mod")
        session.append("user", "m")
        assert sync_of(session._conn) == 0
    finally:
        p.uninstall()


def test_param_by_name_positional(tmp_path):
    con = sqlite3.connect(str(tmp_path / "p.db"))
    try:
        p = install([make_rule("save_kw", pragma_action(target="param:db"))], log=None)
        try:
            p.force_patch_module("target_mod")
            target_mod.save_kw(None, con)  # positional: bound by signature
            assert sync_of(con) == 0
        finally:
            p.uninstall()
    finally:
        con.close()


def test_param_by_name_keyword(tmp_path):
    con = sqlite3.connect(str(tmp_path / "k.db"))
    try:
        p = install([make_rule("save_kw", pragma_action(target="param:db"))], log=None)
        try:
            p.force_patch_module("target_mod")
            target_mod.save_kw(msg=None, db=con)  # keyword
            assert sync_of(con) == 0
        finally:
            p.uninstall()
    finally:
        con.close()


def test_result_target_on_exit_event(tmp_path):
    p = install([make_rule("open_conn", pragma_action(target="result"), event="exit")], log=None)
    try:
        p.force_patch_module("target_mod")
        con = target_mod.open_conn(str(tmp_path / "r.db"))
        try:
            assert sync_of(con) == 0
        finally:
            con.close()
    finally:
        p.uninstall()


def test_unresolved_target_notes_the_firing_log(tmp_path, session):
    # Every attempt gets its own terminal record (LOG-02). The miss used to
    # be deduplicated per (rule, message), which made two identical misses
    # indistinguishable from one, and that is precisely what stopped the
    # attempt count from being reconstructible.
    logpath = tmp_path / "firing.jsonl"
    log = open_log(str(logpath))
    p = install([make_rule("save", pragma_action(target="self._missing"))], log=log)
    try:
        p.force_patch_module("target_mod")
        target_mod.save(session, "hello")  # must not raise
        target_mod.save(session, "again")  # second miss: its own record, not suppressed
    finally:
        p.uninstall()
    outs = outcomes_of(logpath, log)
    assert sum("no attribute '_missing'" in (o or "") for o in outs) == 2


def test_legacy_scan_still_works_without_target(tmp_path):
    con = sqlite3.connect(str(tmp_path / "l.db"))
    try:
        p = install([make_rule("save_kw", pragma_action())], log=None)
        try:
            p.force_patch_module("target_mod")
            target_mod.save_kw(None, con)  # connection IS a direct argument here
            assert sync_of(con) == 0
        finally:
            p.uninstall()
    finally:
        con.close()


def test_no_connection_anywhere_notes_instead_of_silence(tmp_path):
    logpath = tmp_path / "firing2.jsonl"
    log = open_log(str(logpath))
    p = install([make_rule("plain", pragma_action())], log=log)
    try:
        p.force_patch_module("target_mod")
        target_mod.plain(1)  # no connection anywhere: outcome note, not silence
    finally:
        p.uninstall()
    outs = outcomes_of(logpath, log)
    assert any("no target spec and no sqlite3.Connection" in (o or "") for o in outs)


def test_pragma_execute_failure_noted(tmp_path, session):
    # SQLite silently IGNORES unknown pragma names, so the reliable failure
    # shape is a target that resolves but has no .execute (the SessionDB
    # itself): the AttributeError must surface as an outcome note, not
    # propagate.
    logpath = tmp_path / "firing3.jsonl"
    log = open_log(str(logpath))
    p = install([make_rule("save", pragma_action(target="self"))], log=log)
    try:
        p.force_patch_module("target_mod")
        target_mod.save(session, "hello")  # noted, swallowed
    finally:
        p.uninstall()
    outs = outcomes_of(logpath, log)
    assert any("pragma execute failed on SessionDB" in (o or "") for o in outs)


# --- load-time validation -------------------------------------------------

def _rules_file(tmp_path, body):
    f = tmp_path / "r.yaml"
    f.write_text(body)
    return str(f)


def test_load_rules_rejects_target_on_non_pragma(tmp_path):
    f = _rules_file(tmp_path, "- id: x\n  point: target_mod.plain\n  event: entry\n"
                             "  action: {kind: sleep, ms: 1, target: self}\n")
    with pytest.raises(RuleError, match="only consumed by pragma"):
        load_rules(f)


def test_load_rules_rejects_unknown_root(tmp_path):
    f = _rules_file(tmp_path, "- id: x\n  point: target_mod.plain\n  event: entry\n"
                             "  action: {kind: pragma, name: synchronous, value: 'OFF', target: locals}\n")
    with pytest.raises(RuleError, match="target root"):
        load_rules(f)


def test_load_rules_rejects_bare_param(tmp_path):
    f = _rules_file(tmp_path, "- id: x\n  point: target_mod.plain\n  event: entry\n"
                             "  action: {kind: pragma, name: synchronous, value: 'OFF', target: 'param:'}\n")
    with pytest.raises(RuleError, match="parameter name"):
        load_rules(f)


def test_load_rules_accepts_valid_targets(tmp_path):
    for t in ("self._conn", "param:db", "param:db.inner", "result"):
        f = _rules_file(tmp_path, f"- id: x\n  point: target_mod.plain\n  event: exit\n"
                                  f"  action: {{kind: pragma, name: synchronous, value: 'OFF', target: '{t}'}}\n")
        load_rules(f)  # must not raise


# --- resolve_target unit level --------------------------------------------

def test_resolve_target_unit_cases():
    class Holder:
        inner = object()
    h = Holder()
    ctx = {"args": (h,), "kwargs": {}}
    v, why = resolve_target(ctx, "self.inner")
    assert v is Holder.inner and why is None
    v, why = resolve_target(ctx, "self.nope")
    assert v is None and "no attribute" in why
    v, why = resolve_target(ctx, "result")
    assert v is None and "exit" in why
    v, why = resolve_target({"args": (), "kwargs": {}}, "self")
    assert v is None and "no positional" in why

# --- code-review regression tests (2026-09-14 findings) --------------------

def test_whitespace_param_spec_is_treated_consistently(tmp_path):
    # The patcher and the resolver must agree on the spec KIND; a leading
    # space used to skip signature capture while the resolver still read
    # param:, producing a false "not instrumented" skip.
    con = sqlite3.connect(str(tmp_path / "w.db"))
    try:
        p = install([make_rule("save_kw", pragma_action(target=" param:db"))], log=None)
        try:
            p.force_patch_module("target_mod")
            target_mod.save_kw(None, con)
            assert sync_of(con) == 0
        finally:
            p.uninstall()
    finally:
        con.close()


def test_second_log_instance_still_gets_its_note(tmp_path, session):
    # There is no outcome suppression at all any more (LOG-02): each attempt
    # writes its own terminal record. This keeps guarding the direction a
    # suppression cache would break first, a second FiringLog in one process
    # inheriting a previous log's memory of what it already reported.
    first, second = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    rule = make_rule("save", pragma_action(target="self._missing"))
    for path in (first, second):
        log = open_log(str(path))
        p = install([rule], log=log)
        try:
            p.force_patch_module("target_mod")
            target_mod.save(session, "x")
        finally:
            p.uninstall()
        outs = outcomes_of(path, log)
        assert any("_missing" in (o or "") for o in outs)


def test_entry_result_target_rejected_at_load(tmp_path):
    f = _rules_file(tmp_path, "- id: x\n  point: target_mod.plain\n  event: entry\n"
                             "  action: {kind: pragma, name: synchronous, value: 'OFF', target: result}\n")
    with pytest.raises(RuleError, match="exit events"):
        load_rules(f)


def test_empty_path_step_rejected_at_load(tmp_path):
    f = _rules_file(tmp_path, "- id: x\n  point: target_mod.plain\n  event: entry\n"
                             "  action: {kind: pragma, name: synchronous, value: 'OFF', target: 'self..a'}\n")
    with pytest.raises(RuleError, match="empty step"):
        load_rules(f)


def test_pragma_without_name_rejected_at_load(tmp_path):
    f = _rules_file(tmp_path, "- id: x\n  point: target_mod.plain\n  event: entry\n"
                             "  action: {kind: pragma, value: 'OFF'}\n")
    with pytest.raises(RuleError, match="pragma action needs 'name'"):
        load_rules(f)


# --- exception policy (CFG-06) -------------------------------------------


def terminal_records(logpath, log):
    log.close()
    return ends(records(logpath))


@pytest.fixture
def hostile_session(tmp_path):
    from target_mod import HostileSession
    s = HostileSession(str(tmp_path / "hostile.db"))
    yield s
    s.close()


@pytest.mark.parametrize("value", [v for _, v in PARITY_INPUTS],
                         ids=[k for k, _ in PARITY_INPUTS])
def test_type_name_agrees_with_the_guarded_pair(value):
    """The third guarded name helper answers what the pair answers.

    Driven from the same shared inputs as the patcher and sitecustomize
    copies, so a new hostile shape reaches all three at once.
    """
    from pyteman.patcher import _typename
    from pyteman.targets import type_name

    assert type_name(value) == _typename(value)
    assert type(type_name(value)) is str


def test_type_name_absorbs_a_raising_lookup_whatever_it_raises():
    # Exact pins beside the parity loop: the loop compares the helpers to
    # each other, so a pair that narrowed together would still agree.
    from pyteman.targets import type_name

    assert type_name(Nameless()) == "<unknown type>"
    assert type_name(InterruptName()) == "<unknown type>"


def test_resolve_target_absent_attr_with_hostile_metaclass():
    ctx = {"args": (Nameless(),), "kwargs": {}}
    v, why = resolve_target(ctx, "self.nope")
    assert v is None
    assert "<unknown type>" in why


def test_resolve_target_getter_exception_propagates(hostile_session):
    """resolve_target lets non-AttributeError through; the consumer decides."""
    with pytest.raises(RuntimeError, match="pool closed"):
        resolve_target({"args": (hostile_session,), "kwargs": {}},
                       "self.broken_conn")


@pytest.mark.parametrize(
    "spec,status,fragment",
    [("self.broken_conn", "pragma_failed", "pool closed"),
     ("self._missing", "pragma_skipped", "no attribute"),
     # The carve-out's forced branch, pinned: a getter that RAISES
     # AttributeError is indistinguishable from absence at this depth.
     ("self.attrerror_conn", "pragma_skipped", "no attribute")])
def test_a_resolution_that_cannot_act_settles_as_one_terminal_record(
        tmp_path, hostile_session, spec, status, fragment):
    logpath = tmp_path / "hostile.jsonl"
    log = open_log(str(logpath))
    rule = make_rule("save", pragma_action(target=spec))
    p = install([rule], log=log)
    try:
        p.force_patch_module("target_mod")
        target_mod.save(hostile_session, "x")
    finally:
        p.uninstall()
    terms = terminal_records(logpath, log)
    assert len(terms) == 1
    assert terms[0]["status"] == status
    assert fragment in terms[0].get("outcome", "")


def test_getter_exception_does_not_propagate(tmp_path, hostile_session):
    rule = make_rule("save", pragma_action(target="self.broken_conn"))
    p = install([rule], log=None)
    try:
        p.force_patch_module("target_mod")
        target_mod.save(hostile_session, "x")
    finally:
        p.uninstall()


def test_an_unnameable_exception_keeps_its_diagnostic(tmp_path, hostile_session):
    # The deferred render names the exception's type; when the type
    # refuses to be named, the guard keeps both the marker and the
    # original message instead of collapsing to diagnostic-unavailable.
    logpath = tmp_path / "unnamed.jsonl"
    log = open_log(str(logpath))
    rule = make_rule("save", pragma_action(target="self.unnamed_conn"))
    p = install([rule], log=log)
    try:
        p.force_patch_module("target_mod")
        target_mod.save(hostile_session, "x")
    finally:
        p.uninstall()
    terms = terminal_records(logpath, log)
    assert len(terms) == 1
    assert terms[0]["status"] == "pragma_failed"
    assert "target resolution failed: <unknown type>" in terms[0].get(
        "outcome", "")
    assert "pool closed" in terms[0].get("outcome", "")


def test_an_unprintable_exception_keeps_the_marker(tmp_path, hostile_session):
    # The message half of the same promise: an exception whose __str__
    # raises degrades to <unprintable> without taking the marker with it.
    logpath = tmp_path / "hostile.jsonl"
    log = open_log(str(logpath))
    rule = make_rule("save", pragma_action(target="self.hostile_conn"))
    p = install([rule], log=log)
    try:
        p.force_patch_module("target_mod")
        target_mod.save(hostile_session, "x")
    finally:
        p.uninstall()
    terms = terminal_records(logpath, log)
    assert len(terms) == 1
    assert terms[0]["status"] == "pragma_failed"
    assert terms[0].get("outcome", "") == "target resolution failed: Hostile: <unprintable>"


def test_a_str_subclass_message_is_normalised_not_interpolated(tmp_path,
                                                              hostile_session):
    # The exact-str half of the guard: a __str__ returning a subclass
    # would run its own __format__ inside the record's f-string, so the
    # guard takes the value and drops the subclass.
    logpath = tmp_path / "boom.jsonl"
    log = open_log(str(logpath))
    rule = make_rule("save", pragma_action(target="self.boomstr_conn"))
    p = install([rule], log=log)
    try:
        p.force_patch_module("target_mod")
        target_mod.save(hostile_session, "x")
    finally:
        p.uninstall()
    terms = terminal_records(logpath, log)
    assert len(terms) == 1
    assert terms[0].get("outcome", "") == "target resolution failed: BoomStrError: boom-msg"


def test_base_exception_from_getter_propagates(tmp_path, hostile_session):
    rule = make_rule("save", pragma_action(target="self.fatal_conn"))
    p = install([rule], log=None)
    try:
        p.force_patch_module("target_mod")
        with pytest.raises(KeyboardInterrupt):
            target_mod.save(hostile_session, "x")
    finally:
        p.uninstall()


def test_resolved_to_none_message(tmp_path, session):
    # result-None and attribute-None are misses with an honest cause, not
    # the bare "pragma skipped: None".
    logpath = tmp_path / "n.jsonl"
    log = open_log(str(logpath))
    p = install([make_rule("save", pragma_action(target="self.absent"))], log=log)
    try:
        p.force_patch_module("target_mod")
        target_mod.save(session, "x")
    finally:
        p.uninstall()
    outs = outcomes_of(logpath, log)
    assert any("resolved to None" in (o or "") for o in outs)
