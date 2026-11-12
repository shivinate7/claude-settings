# The hand-made worktree rule refuses agent worktrees

**What.** The hand-made-worktree rule refuses an agent's own worktree, even when the agent follows the remedy that the refusal gives.

**Where.** `hooks/guard.py`, rule `hand-made-worktree`.

**Decision.** cull-guard-wrong-refusals (the guard cull), which lists this gap.

**Retire.** Closed when a case in `hooks/test_guard.py` lets an agent worktree through the rule after the remedy is followed.
