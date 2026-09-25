# Changelog

## 0.2.0

### Breaking changes

- **Patcher now refuses a non-str `id` at construction.** A rule whose `id` is
  not a `str` instance raises `RuleError("id must be a string, got <type>")`.
  Previously, a hashable non-str value such as `id=5` was accepted and worked
  end to end: `json.dumps` serialised it for the firing record, and the outcome
  dedup key needed only hashability. The documented contract at
  `docs/rules.md:467` already required a non-empty string, so no published
  interface changes; callers relying on the undocumented leniency should convert
  their ids to `str`.
