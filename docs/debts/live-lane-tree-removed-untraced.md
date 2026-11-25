# A live lane's tree removed under it, with no record of the remover

- **What.** A live lane in the home repo (lane tv-spotify, session record 22196) ran in a worktree that was removed under it. The remover is not known. The sweep log shows the sweep kept that tree four times, each time as a live session.
- **Where.** `remove_worktree` in `janitor/sweep.py`. The sweep, the agent-end reap and the merge tool's `remove_held_tree` in `merge/merge.py` all delete a tree through it. It writes a removal marker that holds a time only. A `git worktree remove` that a session runs itself does not pass through it.
- **Decision.** `when-a-worktree-may-be-removed` (when a worktree may be removed).
- **Retire.** Each removal writes its remover's name and the tree's path, so a tree removed under a live session names its remover. The closing check is `janitor/test_sweep.py`, with a case that proves it.
