# A finished agent's tree stays while its host lives

- **What.** A finished agent's worktree can hold the lock `claude agent agent-<id> (pid N)`, with no start time. N is the session's live claude.exe. The tree stays until the host exits. MEASURED 2026-10-15 23:31: 17 of 166 agent trees, later 22, all held by one pid.
- **Where.** `janitor/sweep.py`, `stale_agent_lock_verdict`: a live pid keeps the lock.
- **Decision.** `the-janitor-is-one-machine-wide-sweep` (the stale agent lock section, which says the tree stays until the host ends); `agent-end-reap-stops-what-a-finished-agent-left` (Part 4, the worktree is removed at agent end).
- **Retire.** An owner decision on a finished-agent proof, which the current ruling does not give. Then a case in `janitor/test_sweep.py` holds a finished agent's tree with a live host pid and expects it freed. It goes red on the current code, then green after the fix.
