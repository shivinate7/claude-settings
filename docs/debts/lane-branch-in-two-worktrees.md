# A lane branch checked out in two worktrees drifts

**What.** When the lane session checks out its lane branch in its own worktree and an agent pushes the same branch from another worktree, the session's worktree keeps the old index. It then shows the pushed commit's reverse as staged changes, and the stop hook asks to commit them. Committing would revert the agent's work. Seen three times in lane cloud-snapshot-age-check (2026-11-06).

**Where.** The lane session's own worktree under `.claude/worktrees/`; the stop hook's uncommitted-changes prompt.

**Decision.** `parallelism-each-own-checkout` (each agent in its own checkout).

**Retire.** A guard refuses a lane session's checkout of a branch an agent's worktree pushes, or the lane brief keeps the session off the branch (an agent writes the records). Check: a red test where a second worktree on the same branch is refused.
