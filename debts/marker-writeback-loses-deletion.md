# A cut-short remove's write-back can drop a person's deletion

- **What.** A failed remove leaves `claude-removal-started` in the tree's admin dir, on an intact tree. Later, at agent end, `_restore_cut_short` writes the unstaged tracked deletions back from the index. The restored tree is removed when HEAD is on a remote-tracking ref. The person's uncommitted deletion is lost. Narrow: it needs a prior failed remove.
- **Where.** `janitor/sweep.py`, added by lane `wt-reap`: `REMOVAL_MARKER`, `_restore_cut_short`, and its call in `decide_agent_end_worktree`.
- **Decision.** `agent-end-reap-stops-what-a-finished-agent-left` (the sweep that reaps what a finished agent left, Holes, named).
- **Retire.** Either the write-back skips a tree that holds any unstaged deletion, or the owner accepts the loss in a ruling. Check: a case in `janitor/test_sweep.py` with the marker and one unstaged tracked deletion expects keep. It goes red on the current code, then green after the fix.
