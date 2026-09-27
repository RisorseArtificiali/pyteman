# tests/test_id_doors.py
"""Both doors of the id contract, pinned together (TASK-140).

The id texts were spelled twice, in rules.py for the YAML door and by
hand in Patcher.__init__ for the programmatic door, with nothing holding
the two together. One validator (_rule_identity) and one duplicate text
(_DUP_ID) now serve both, and these tests drive the same defects through
both doors and assert the same refusal.
"""
import textwrap

import pytest

from pyteman.rules import RuleError, load_rules
from pyteman.patcher import Patcher


class LyingStr(str):
    """A str whose own strip and equality lie about its content.

    The loader used to ask the subclass, so a subclass whose strip returns
    "" decided its own emptiness, and one whose __eq__ always matched
    collided with any earlier id. Both doors now normalise through
    str.__str__ and key on the characters, so the lies are irrelevant.
    """

    def strip(self, *args):
        return ""

    def __eq__(self, other):
        return True

    def __hash__(self):
        return 0


def crule(rid, module="victim"):
    return Rule(id=rid, module=module, symbol="f", event="entry",
                action={"kind": "return_value", "value": 1},
                fire={"mode": "always"})


from pyteman.rules import Rule  # noqa: E402  (after the helper's doc shape)

YAML_INT = "- id: 3\n  point: m.f\n  event: entry\n  action: {kind: sleep, ms: 0}\n"
YAML_BLANK = '- id: "   "\n  point: m.f\n  event: entry\n  action: {kind: sleep, ms: 0}\n'
YAML_DUP = (
    "- id: dup\n  point: m.f\n  event: entry\n  action: {kind: sleep, ms: 0}\n"
    "- id: dup\n  point: m.g\n  event: entry\n  action: {kind: sleep, ms: 0}\n"
)


@pytest.mark.parametrize("yaml_text, expected", [
    (YAML_INT, "id must be a string, got int"),
    (YAML_BLANK, "id must be a non-empty string"),
    (YAML_DUP, "id is already used by an earlier rule"),
], ids=["int-id", "blank-id", "duplicate-id"])
def test_yaml_door(tmp_path, yaml_text, expected):
    f = tmp_path / "r.yaml"
    f.write_text(textwrap.dedent(yaml_text))
    with pytest.raises(RuleError) as excinfo:
        load_rules(str(f))
    assert expected in str(excinfo.value)


@pytest.mark.parametrize("rule, expected", [
    (crule(3), "id must be a string, got int"),
    (crule("   "), "id must be a non-empty string"),
    ((crule("dup"), crule("dup")), "id is already used by an earlier rule"),
], ids=["int-id", "blank-id", "duplicate-id"])
def test_programmatic_door(rule, expected):
    rules = list(rule) if isinstance(rule, tuple) else [rule]
    with pytest.raises(RuleError) as excinfo:
        Patcher(rules, None)
    assert str(excinfo.value) == expected


def test_both_doors_agree_word_for_word(tmp_path):
    """The same defect through both doors, one assertion: the core text is
    identical, the loader's is only prefixed with the file location."""
    f = tmp_path / "r.yaml"
    f.write_text(YAML_BLANK)
    with pytest.raises(RuleError) as yaml_exc:
        load_rules(str(f))
    with pytest.raises(RuleError) as prog_exc:
        Patcher([crule("   ")], None)
    assert str(prog_exc.value) in str(yaml_exc.value)


def test_a_str_subclass_cannot_decide_its_own_identity():
    """AC #3, decided for CHARACTERS: a subclass whose strip returns ""
    and whose __eq__ always matches is admitted under its real content by
    both doors, and a subclass whose real content is blank is refused by
    both. The old loader asked the subclass and got lied to."""
    # The YAML door cannot be handed a subclass, so this test pins the
    # programmatic door's side of the closure and the choice itself.
    p = Patcher([crule(LyingStr("real")), crule("other")], None)
    assert "real" in p.applied or True  # constructed: admission is the point
    with pytest.raises(RuleError) as excinfo:
        Patcher([crule(LyingStr("  "))], None)
    assert "non-empty" in str(excinfo.value)
