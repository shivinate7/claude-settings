# The finish proof reads one transcript folder

- **What.** The finish proof reads only the ending session's transcript folder. So a worktree on a dead host, left by an earlier session, has no removal route.
- **Where.** `janitor/agent_end_reap.py`, `agent_finished`, on origin/agent-process-marker-carry. In PR #2712 with PR #2783, not yet on main.
- **Decision.** `when-a-worktree-may-be-removed` (when a finished agent's worktree may be removed).
- **Retire.** A test in `janitor/test_prove_agent_end_reap.py`, red on the current code first, gives a worktree locked by a dead host from an earlier session and expects the reaper to remove it.
