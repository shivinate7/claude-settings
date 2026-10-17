# An agent meets the cap expiry field only after a bad write

- **What.** The override file needs `_subagentCapUntil` outside `env`, an ISO-8601 time at most 24 hours ahead. The rule that taught it is gone from `CLAUDE.md`. An agent now meets the field only in the revoke message, after the watch reverts a bad write.
- **Where.** `EXPIRE_MESSAGE` in `hooks/config_watch.py`. `cap_ask_reason` in `hooks/guard.py`, the text of the ask for a cap write, does not name the field.
- **Decision.** `claude-md-shrink` (CLAUDE.md drops the prose of a rule that a guard or gate enforces).
- **Retire.** `cap_ask_reason` names `_subagentCapUntil`, and a test in `hooks/` pins the text.
