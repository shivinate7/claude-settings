# The session-end sweep has no deadline on a repo with many worktrees

- **What.** The sweep checks each worktree in turn, with eight or more git calls per tree. The agent rule adds one more call, up to 10 s, for each tree that reaches it. On a repo with about 800 worktrees the sweep cannot finish in its 25 s budget. A kill during `git worktree remove` can leave a half-removed tree. Removals persist, so later sessions continue the work. The cost is unmeasured. Found in review round 2 of lane worktree-reap.
- **Where.** `sweep_repo` in `janitor/sweep.py` (near lines 2515-2640) and the serial map near line 1859.
- **Decision.** `agent-end-reap-stops-what-a-finished-agent-left`.
- **Retire.** The sweep stops at a deadline before its budget ends and never starts a remove it cannot finish. A test with many trees shows it.
