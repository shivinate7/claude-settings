# The allow passes any linked worktree

- **What.** The allow passes any linked worktree, not only the caller's own. A git call against a sibling linked worktree passes the allow.
- **Where.** The allow check in `hooks/guard_shared_tree.py`.
- **Decision.** `agent-worktree-discard-is-noted` (a discard or remove in a worktree).
- **Retire.** Decide the scope. Either refuse a sibling worktree, or name the scope as a limit. A test pins the chosen rule.
