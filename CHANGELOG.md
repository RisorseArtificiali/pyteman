# Changelog

## Unreleased

- The action mapping is now read once at bind time and fired from that snapshot (TASK-85). Mutating `rule.action` after install no longer changes what fires, and an action read that raises on any install-path read, the first or a later one, refuses the patch with nothing installed. The raising refusal is older than this change, the async-sleep door already read the action at install and the bind already rendered it; what moves is every read that used to sit at firing time, where a rebound action changed what ran after admission, and the driver-road flag, which used to re-derive from a live read at every extension.
- The generic suspendable-refusal message no longer repeats the rule description that the accompanying note already carries; the rule behind a refusal is named once, in `__notes__`.

## 0.2.0 - 2026-09-23

### Breaking changes

- Rule ids must now be strings at both doors, programmatic and YAML. `Patcher` refuses a non-str id at construction with `RuleError("id must be a string, got <type>")`, and `load_rules` refuses the non-str, empty and duplicate ids that 0.1.0 accepted unvalidated: an unquoted `id: 5` in YAML was one case that worked end to end before. The contract row in the Rule fields table of docs/rules.md and its enforcement shipped together in this release; no earlier release documented any id contract. Callers relying on the earlier leniency should convert their ids to `str`.
