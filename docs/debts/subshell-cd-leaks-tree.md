# A subshell cd leaks into the two-worktrees guard's tree

- **What.** The guard sets the judged tree on `(cd X` and never restores it at `)`. So `(cd <holder> && git status) ; git update-ref refs/heads/x HEAD` judges the second call in the holder's tree, and it passes while the holder holds `x`. The base form `checkout -B` shares the leak.
- **Where.** `hooks/guard.py` rule 1b2, the `_segment_cd_target` step (about lines 3644 to 3651).
- **Decision.** `held-branch-ref-moves` (a ref move never touches a branch another worktree holds); the leak is older than it and also affects `two-worktrees-one-branch`.
- **Retire.** The tree resets at the closing `)` of a subshell, with a red case for the chain above. The fix belongs in its own lane.
