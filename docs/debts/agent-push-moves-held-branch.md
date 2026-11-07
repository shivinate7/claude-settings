# An agent's push moves a branch another worktree holds

- **What.** On 2026-11-07, lane override-plain-ask: a builder fetched and pushed `lane/override-plain-ask` while the lane's own worktree had that branch checked out. The branch ref moved under that worktree, so its files and index stayed at the old commit and showed as a staged change. A commit there would have undone the builder's fix.
- **Where.** The guard on agent git writes (`hooks/guard_branch_worktree.py`) and agent briefs.
- **Decision.** `owner-override` holds no ruling here; none exists yet.
- **Retire.** A builder or test-author write to a branch that another worktree holds is refused, with a red case first. Or briefs name a branch of the agent's own, and a check proves it.
