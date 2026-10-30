# ExitWorktree reaching the guard is unmeasured

- **What.** The guard clears a session-home record on an ExitWorktree call. Whether the harness sends ExitWorktree to PreToolUse under that name is read from the docs, not measured live. If it never fires, each deliberate exit with remove leaves a lost record, and primary writes are refused after it.
- **Where.** `settings.json` guard matcher, `hooks/guard.py` `session_home_keep`, rule `session-home`.
- **Decision.** an-agent-outside-its-home-tree-must-stop (an agent outside its home tree must stop).
- **Retire.** One live run after merge: EnterWorktree, ExitWorktree with remove, then a Write in the primary passes. Record the result in the decision's Premises bullet.
