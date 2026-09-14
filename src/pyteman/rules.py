from dataclasses import dataclass, field
from typing import Optional
import yaml

from pyteman.targets import parse_target_spec, validate_target_spec

class RuleError(Exception):
    pass

_EVENTS = ("entry", "exit")
_ACTION_KINDS = ("sleep", "raise", "return_value", "return_none", "kill", "pragma", "barrier")
_FIRE_MODES = ("always", "once_per", "countdown")

@dataclass
class Rule:
    id: str
    module: str
    symbol: str
    event: str
    action: dict
    fire: dict = field(default_factory=lambda: {"mode": "always"})
    when: Optional[str] = None

def parse_point(point: str) -> tuple[str, str]:
    """Split a point string at the LAST dot: "os.path.join" -> ("os.path", "join").

    Rule points deliberately resolve differently: load_rules splits at the
    FIRST dot so "pkg.Class.method" yields module "pkg" and symbol
    "Class.method", the attribute chain walked from the imported module.
    """
    if "." not in point:
        raise RuleError(f"point must be 'module.symbol' (got {point!r})")
    mod, _, sym = point.rpartition(".")
    return mod, sym

def load_rules(path: str) -> list:
    with open(path) as fh:
        raw = yaml.safe_load(fh)
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raise RuleError("ruleset must be a YAML list")
    rules = []
    for i, item in enumerate(raw):
        where = f"rule #{i}"
        if not isinstance(item, dict):
            raise RuleError(f"{where}: mapping required")
        for key in ("id", "point", "event", "action"):
            if key not in item:
                raise RuleError(f"{where}: missing {key}")
        if item["event"] not in _EVENTS:
            raise RuleError(f"{where}: event must be one of {_EVENTS}")
        action = item["action"]
        if not isinstance(action, dict) or action.get("kind") not in _ACTION_KINDS:
            raise RuleError(f"{where}: action.kind must be one of {_ACTION_KINDS}")
        # target: is consumed by pragma only (today). Validate loudly here so a
        # typo'd spec dies at load, never as a silent runtime no-op.
        if action.get("kind") == "pragma":
            for field in ("name", "value"):
                if field not in action:
                    raise RuleError(f"{where}: pragma action needs '{field}'")
        if "target" in action:
            if action.get("kind") != "pragma":
                raise RuleError(f"{where}: 'target' is only consumed by pragma actions")
            try:
                validate_target_spec(action["target"], where)
            except ValueError as e:
                raise RuleError(str(e)) from None
            parsed, _ = parse_target_spec(action["target"])
            if parsed is not None and parsed[0] == "result" and item["event"] == "entry":
                raise RuleError(
                    f"{where}: target 'result' can only resolve on exit events")
        fire = item.get("fire", {"mode": "always"})
        if not isinstance(fire, dict):
            raise RuleError(f"{where}: fire must be a mapping")
        if fire.get("mode") not in _FIRE_MODES:
            raise RuleError(f"{where}: fire.mode must be one of {_FIRE_MODES}")
        # Rule targets are "module.Class.method": the module is the first dot
        # component and the symbol is the attribute path walked from it, so the
        # split here is at the FIRST dot (parse_point keeps the last-dot split
        # for module-path interpretation).
        point = item["point"]
        if not isinstance(point, str):
            raise RuleError(f"{where}: point must be a string")
        if "." not in point:
            raise RuleError(f"point must be 'module.symbol' (got {point!r})")
        mod, _, sym = point.partition(".")
        rules.append(Rule(id=item["id"], module=mod, symbol=sym, event=item["event"],
                          action=action, fire=fire, when=item.get("when")))
    return rules
