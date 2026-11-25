# A session record whose folder is gone stands in no tree

## The ruling

A session record whose folder is gone stands in no tree, for a removal that the dirty, locked and unmerged keeps also guard (owner, 20:53 CST Nov 24 2026). The case it covers is a live session whose worktree was deleted under it. Exception: a folder moved or renamed while its session lives reads the same way. The process check in `decide_worktree` still keeps such a tree while a process sits inside it. Whether a live session always leaves one there is unmeasured. A read that cannot tell still keeps it.

A folder counts as gone only when `os.stat` on the record's cwd raises FileNotFoundError or NotADirectoryError, and the drive or root above it still reads. Every other error keeps. So does an unreadable target.

Owner rulings, 2026-11-24:

- 20:53 CST, on "a session record whose folder is gone counts as not in this worktree": "i'm a fan of this but think an opus agent needs to plan it and u need to aggregate all the work sim manager gives to you on this worktree concept".
- 21:19 CST, on the orphan-process reap and the trash sweep: "the notion had been that if a sessino loses its worktree bc its told to commit everything beforehand nothing's rly lost, it just needs to know it needs to make a new worktree and reach main. and with that implemented it should basically be B or C right". Read as: those two acts keep as on main until a session that loses its worktree is told to commit first and make a new one.

## Scope as built

This is the consultant's pick, undoable: the opt-in scope. The owner has not ruled on the rest.

The answer is off by default: `worktree_live_session(target, absent_is_out=False)`. Only these callers opt in. Each one also keeps a dirty, locked or unmerged tree.

- `decide_worktree` in `janitor/sweep.py`. Its callers: the sweep's per-tree judge in `sweep_repo` (every sweep run, the session-end agent rule included), `decide_agent_end_worktree` (agent-end reap), and `remove_held_tree` in `merge/merge.py` (the merge tool's removal of the tree that holds the merged branch).
- `worktree_remove_subject` in `hooks/guard_core.py`, which decides `git worktree remove`. It keeps dirty and locked trees before its live read. It has no process check.

These callers stay on the default. A session record whose folder is gone still keeps the tree there:

- `decide_listener` in `janitor/sweep.py`, the orphaned TCP listener reap, which stops the listener (owner ruling 21:19).
- `trash_verdict` in `janitor/sweep.py`, read before `reap_trash` deletes a folder (owner ruling 21:19).
- `_restore_cut_short` in `janitor/sweep.py`, the cut-short restore. It runs its own checks and does not go through `decide_worktree`.
- `husk_verdict` in `janitor/sweep.py`, the husk read. A husk is a folder of only `huskNames`. Its delete has no dirty, locked or unmerged check in front of it.
- The two branch-cut holder reads in `sweep_repo`: the read taken before a removed tree's delete, and the read of a tree still on disk. A branch cut keeps its branch on an unknown answer.
- `_decide` and `build_keep` in `janitor/agent_end_reap.py`: the orphan process decisions for the ending agent's tree, and the build-folder keep. Neither has a dirty check. The trees themselves are removed by `decide_agent_end_worktree`, which is opted in.

## Known effect

From the code, not measured: a stale record whose cwd sits outside the tree's current path, such as a moved or renamed tree, lets an opted-in verdict remove the tree. The branch cut's default read answers None for that record, so the branch stays, with the reason `checked-out: session read again`.

## What still guards a tree with a stale record

- In `decide_worktree`: the dirty, locked, unpushed and unmerged checks, and the process check.
- In `worktree_remove_subject`: the dirty and locked checks.

Kind: process
Home: janitor/sweep.py
Home: janitor/agent_end_reap.py
Home: hooks/git_reads.py
