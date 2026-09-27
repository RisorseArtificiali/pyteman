# tests/test_shared_compile.py
"""One compile definition for rule expressions, both doors (TASK-56).

The loader compiles `when` and `fire.key` to validate at load; the
patcher recompiles to cover programmatic rules. One core
(_compile_expression) now serves both, each caller dressing the failure
in its own context. The test pins that the same malformed expression
produces the same core SyntaxError message through both doors, so the
two cannot drift on what a valid expression is.
"""
import pytest

from pyteman.patcher import Patcher
from pyteman.rules import Rule, RuleError, load_rules


def _assert_same_message_both_doors(tmp_path, yaml_when, raw_source, core):
    """Both doors refuse `raw_source` and share the same core text."""
    f = tmp_path / "r.yaml"
    f.write_text("- id: x\n  point: m.f\n  event: entry\n"
                 f"  when: {yaml_when}\n  action: {{kind: sleep, ms: 0}}\n")
    with pytest.raises(RuleError) as yaml_exc:
        load_rules(str(f))
    rule = Rule(id="x", module="m", symbol="f", event="entry",
                when=raw_source, action={"kind": "sleep", "ms": 0},
                fire={"mode": "always"})
    with pytest.raises(RuleError) as prog_exc:
        Patcher([rule], None)
    # The loader prefixes with the file location; the core text agrees.
    assert core in str(yaml_exc.value), yaml_exc.value
    assert core in str(prog_exc.value), prog_exc.value


def test_unclosed_bracket_same_core_text(tmp_path):
    _assert_same_message_both_doors(
        tmp_path, "(x +", "(x +", "'(' was never closed")


def test_keyword_as_expression_same_core_text(tmp_path):
    _assert_same_message_both_doors(
        tmp_path, "return 1", "return 1", "invalid syntax")
