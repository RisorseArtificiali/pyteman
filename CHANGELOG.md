# Changelog

## Unreleased

- The generic suspendable-refusal message no longer repeats the rule description that the accompanying note already carries; the rule behind a refusal is named once, in `__notes__`.

## 0.2.0 - 2026-09-23

### Breaking changes

- Rule ids must now be strings at both doors, programmatic and YAML. `Patcher` refuses a non-str id at construction with `RuleError("id must be a string, got <type>")`, and `load_rules` refuses the non-str, empty and duplicate ids that 0.1.0 accepted unvalidated: an unquoted `id: 5` in YAML was one case that worked end to end before. The contract row in the Rule fields table of docs/rules.md and its enforcement shipped together in this release; no earlier release documented any id contract. Callers relying on the earlier leniency should convert their ids to `str`.
