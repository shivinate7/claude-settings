# No text tells an agent to remove the cap override file before it expires

- **What.** The watch reverts a raised subagent cap only when `_subagentCapUntil` passes. The rule that said to remove the file when the raise is no longer needed is gone from `CLAUDE.md`. Nothing now reminds an agent to remove the file early.
- **Where.** Deleted rule `roles-remove-override-file`. The revert logic sits in `hooks/config_watch.py`.
- **Decision.** `claude-md-shrink` (CLAUDE.md drops the prose of a rule that a guard or gate enforces).
- **Retire.** The ask for a cap write tells the agent to remove the file when done, and a test in `hooks/` pins the text. Or the owner rules that expiry alone is enough.
