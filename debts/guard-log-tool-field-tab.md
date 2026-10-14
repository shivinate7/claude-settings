# A tab in the tool field can add a seventh field

- **What.** The reader reads `session` as field 6, and `matched` as field 5 plus the later fields. The `decision_watch` fallback reads `matched` as field 5 only. The line gets a seventh field only through the `tool` field, which is not folded. Not every caller of `tool` was checked for a tab. `log_cut` folds tabs out of `matched`, and the session cell strips control characters.
- **Where.** The `tool` field written by `record` in `hooks/guard_core.py`, and the `decision_watch` fallback reader.
- **Decision.** `guard-log-read-weekly` (guard.log is read weekly, by one reader).
- **Retire.** The `tool` field folds tabs, as `matched` does. Every caller is checked. A case with a tab in each caller reads back the right fields.
