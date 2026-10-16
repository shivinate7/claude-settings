# The session-end sweep's deadline does not bound a call already running

- **What.** The SessionEnd run starts no phase and no tree read at or past its deadline, `JUDGE_BUDGET_SECONDS` (12 s) after it starts. A call that starts just before the deadline still runs to its own timeout: `guard._git` 10 s, `ls-remote` 10 s per remote, `rev-list --stdin` 30 s, a repo's `reap:worktrees` script 15 s. The budget is also fixed, while `session_end_sweep.py` kills the sweep at min(25 s, the time its hook has left), which can be under 12 s. So a finish inside the kill limit is not proven. A kill during `git worktree remove` can leave a half-removed tree. How often either happens is unmeasured. Named in review round 2 of lane sweep-fast, item (d).
- **Where.** `sweep_repo` and `main` in `janitor/sweep.py` (near lines 2614-2810 and 3060); `guard._git` in `hooks/guard_core.py`; the sweep call in `janitor/session_end_sweep.py`.
- **Decision.** `agent-end-reap-stops-what-a-finished-agent-left`.
- **Retire.** The sweep takes its kill limit from `session_end_sweep.py` and caps each subprocess timeout at the time left. A case with a slow git call shows the pass ends inside the limit.
