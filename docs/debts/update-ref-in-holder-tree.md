# An update-ref in the holder's own tree leaves its index stale

- **What.** The two-worktrees guard passes `update-ref` and `symbolic-ref` that run in the holder's own tree, by the holder's own shell or by `git -C <holder>`, which may name another session's tree. `git -C <holder> update-ref refs/heads/x HEAD` or `-d` moves the ref alone, so the holder's index and files stay at the old commit. The remedy text offers `git -C <holder> merge --ff-only <commit>`, which covers only a fast-forward. A move that is not a fast-forward, and a delete, have no remedy in the text.
- **Where.** `two_worktrees_hit` in `hooks/guard_branch_worktree.py`, the own-tree exclusion.
- **Decision.** `held-branch-ref-moves` (a ref move never touches a branch another worktree holds).
- **Retire.** The guard tells the holder's own tree from another session's tree. It refuses or asks for an `update-ref` or `symbolic-ref` that moves a held ref from a tree it does not own, with a red case for `-C <holder>`. The remedy text names a path for a non-fast-forward move and a delete.
