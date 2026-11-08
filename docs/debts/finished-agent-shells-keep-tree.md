# A finished agent's shells keep its tree

**What.** A finished agent's own shells, such as a dev server, have the live host as parent. No process can yet be shown to be the agent's own, so the agent-end reap stops nothing. A finished tree with any process inside is kept until the host exits. The owner ruled to stop the agent's shells (2026-10-15 19:43 CDT). That half is not built. A per-agent process marker would let the reaper tell the agent's shells from the session's own.

**Where.** `janitor/agent_end_reap.py`, `reap_worktrees`; `janitor/sweep.py`, `decide_worktree` (the process-inside keep).

**Decision.** when-a-worktree-may-be-removed (when a worktree may be removed).

**Fix.** `step:agent-process-marker`

**Retire.** At a later agent end, the reaper stops the marked shells of a finished agent's tree that is idle 30 min or more, then removes the tree. A `janitor/test_sweep.py` case shows a tree with a marked host-child shell removed, and a tree with an unmarked process kept.
