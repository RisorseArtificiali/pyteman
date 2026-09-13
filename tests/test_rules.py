import pytest
from pyteman.rules import Rule, RuleError, load_rules, parse_point

def write(tmp_path, text):
    p = tmp_path / "rules.yaml"; p.write_text(text); return str(p)

def test_parse_point_splits_at_last_dot():
    assert parse_point("os.path.join") == ("os.path", "join")
    assert parse_point("mod.fn") == ("mod", "fn")

def test_load_valid_rules(tmp_path):
    p = write(tmp_path, """
- id: hold-commit
  point: hermes_state.SessionDB._execute_write
  event: entry
  when: "fires > 3"
  action: {kind: sleep, ms: 250}
  fire: {mode: once_per, key: "kwargs.get('sid')"}
- id: kill5
  point: hermes_state.SessionDB.commit
  event: exit
  action: {kind: kill, exit_code: 70}
  fire: {mode: countdown, n: 5}
""")
    rules = load_rules(p)
    assert rules[0].module == "hermes_state"
    assert rules[0].symbol == "SessionDB._execute_write"
    assert rules[0].event == "entry"
    assert rules[0].action == {"kind": "sleep", "ms": 250}
    assert rules[1].fire == {"mode": "countdown", "n": 5}

def test_load_rejects_bad_event(tmp_path):
    p = write(tmp_path, "- id: x\n  point: mod.fn\n  event: middle\n  action: {kind: sleep, ms: 1}\n")
    with pytest.raises(RuleError, match="event"):
        load_rules(p)

def test_load_rejects_missing_action(tmp_path):
    p = write(tmp_path, "- id: x\n  point: mod.fn\n  event: entry\n")
    with pytest.raises(RuleError, match="action"):
        load_rules(p)

def test_load_rejects_point_without_dot(tmp_path):
    p = write(tmp_path, "- id: x\n  point: nodot\n  event: entry\n  action: {kind: sleep, ms: 1}\n")
    with pytest.raises(RuleError, match="point"):
        load_rules(p)

def test_load_rejects_non_mapping_fire(tmp_path):
    p = write(tmp_path, "- id: x\n  point: mod.fn\n  event: entry\n  action: {kind: sleep, ms: 1}\n  fire: hello\n")
    with pytest.raises(RuleError, match="fire"):
        load_rules(p)

def test_load_rejects_null_fire(tmp_path):
    p = write(tmp_path, "- id: x\n  point: mod.fn\n  event: entry\n  action: {kind: sleep, ms: 1}\n  fire:\n")
    with pytest.raises(RuleError, match="fire"):
        load_rules(p)

def test_load_rejects_non_string_point(tmp_path):
    p = write(tmp_path, "- id: x\n  point: 123\n  event: entry\n  action: {kind: sleep, ms: 1}\n")
    with pytest.raises(RuleError, match="point"):
        load_rules(p)

def test_default_fire_is_always(tmp_path):
    p = write(tmp_path, "- id: x\n  point: mod.fn\n  event: entry\n  action: {kind: sleep, ms: 1}\n")
    r = load_rules(p)[0]
    assert r.fire == {"mode": "always"}
    assert r.when is None
