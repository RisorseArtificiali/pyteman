import json
import sqlite3

import pytest

from pyteman.firing import open_log
from pyteman.rules import Rule, RuleError, load_rules
from pyteman.patcher import install
from pyteman.targets import resolve_target

import target_mod
from target_mod import SessionDB


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

# --- TASK-12 / CFG-06: exception policy during target resolution -----------

def test_resolve_target_hostile_name_does_not_propagate():
    """A metaclass whose __name__ is a property that raises should not
    prevent resolve_target from returning the structured miss."""
    class HostileMeta(type):
        @property
        def __name__(cls):
            raise RuntimeError("hostile type name")

    class Victim(metaclass=HostileMeta):
        pass

    obj = Victim()
    ctx = {"args": (obj,), "kwargs": {}}
    v, why = resolve_target(ctx, "self.no_such_attr")
    assert v is None
    assert "no attribute" in why
    assert "unknown type" in why


def test_resolve_target_getter_exception_propagates():
    """resolve_target does NOT catch getter exceptions; the caller decides."""
    class Holder:
        @property
        def conn(self):
            raise RuntimeError("pool closed")

    ctx = {"args": (Holder(),), "kwargs": {}}
    with pytest.raises(RuntimeError, match="pool closed"):
        resolve_target(ctx, "self.conn")


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
