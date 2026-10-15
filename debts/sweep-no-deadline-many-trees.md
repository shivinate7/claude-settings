# The session-end sweep has no deadline on a repo with many worktrees

- **What.** The sweep checks each worktree in turn, with eight or more git calls per tree. The agent rule adds one more call, up to 10 s, for each tree that reaches it. On a repo with about 800 worktrees the sweep cannot finish in its 25 s budget. A kill during `git worktree remove` can leave a half-removed tree. Removals persist, so later sessions continue the work. Measured 2026-10-15: about 7.5 s per tree, and 610 agent worktrees piled up. Found in review round 2 of lane worktree-reap. Still open until lane sweep-fast lands.
- **Where.** `sweep_repo` in `janitor/sweep.py` (near lines 2515-2640) and the serial map near line 1859.
- **Decision.** `agent-end-reap-stops-what-a-finished-agent-left`.
- **Retire.** Lane sweep-fast (owner ruling, 2026-10-15) closes it. The lane does one pass of git reads, a time limit, oldest first. The check: the sweep stops at a deadline before its budget ends. It never starts a remove it cannot finish. A test with many trees shows it. The debt file is deleted in the PR that lands lane sweep-fast.
