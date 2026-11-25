# A session record whose folder is gone stands in no tree

## The ruling

A session record whose folder is gone stands in no tree, for a removal that the dirty, locked and unmerged keeps also guard (owner, 20:53 CST Nov 24 2026). The case it covers is a live session whose worktree was deleted under it. A folder moved or renamed inside a parent that stays reads gone too. Whether a live session always keeps a process in its tree is unmeasured.

Owner rulings, 2026-11-24:

- 20:53 CST, on "a session record whose folder is gone counts as not in this worktree": "i'm a fan of this but think an opus agent needs to plan it and u need to aggregate all the work sim manager gives to you on this worktree concept".
- 21:19 CST, on the orphan-process reap and the trash sweep: "the notion had been that if a sessino loses its worktree bc its told to commit everything beforehand nothing's rly lost, it just needs to know it needs to make a new worktree and reach main. and with that implemented it should basically be B or C right". Read as: those two acts keep as on main until a session that loses its worktree is told to commit first and make a new one.

Consultant's picks from round 1 review, not owner rulings:

- Missing parent. A folder reads gone only when its leaf is absent and its parent exists and is a folder (the folder test, `_folder_is_gone` in `hooks/git_reads.py`). A missing parent reads unknown: a moved or renamed parent, or an unmounted disk. Every other error reads unknown too, and so does an unreadable target.
- Process check. A live process with its cwd in the tree refuses the guard's `git worktree remove` whatever the record read says, an unreadable record included (the process read `_process_stands_in` in `hooks/guard_core.py`, which reads the sweep's `processes_in`). The sweep keeps such a tree too, except a finished agent's marked processes, which the marker rule stops first (see "A finished agent's tree" in `when-a-worktree-may-be-removed`).

## Scope as built

This is the consultant's pick, undoable: the opt-in scope. The owner has not ruled on the rest.

The answer is off by default: `worktree_live_session(target, absent_is_out=False)`. Only these callers opt in. Each one keeps a dirty or locked tree before its live read. The sweep's verdict also keeps an unpushed or unmerged tree.

- `decide_worktree` in `janitor/sweep.py`. Its callers: the sweep's per-tree judge in `sweep_repo` (every sweep run, the session-end agent rule included), `decide_agent_end_worktree` (agent-end reap), and `remove_held_tree` in `merge/merge.py` (the merge tool's removal of the tree that holds the merged branch).
- `worktree_remove_subject` in `hooks/guard_core.py`, which decides `git worktree remove`. It keeps dirty and locked trees before its live read. A process in the tree refuses whatever the record read says.

These callers stay on the default. A session record whose folder is gone still keeps the tree there:

- `decide_listener` in `janitor/sweep.py`, the orphaned TCP listener reap, which stops the listener (owner ruling 21:19).
- `trash_verdict` in `janitor/sweep.py`, read before `reap_trash` deletes a folder (owner ruling 21:19).
- `_restore_cut_short` in `janitor/sweep.py`, the cut-short restore. It runs its own checks and does not go through `decide_worktree`.
- `husk_verdict` in `janitor/sweep.py`, the husk read. A husk is a folder of only `huskNames`. Its delete has no dirty, locked or unmerged check in front of it.
- The two branch-cut holder reads in `sweep_repo`: the read taken before a removed tree's delete, and the read of a tree still on disk. A branch cut keeps its branch on an unknown answer.
- `_decide` and `build_keep` in `janitor/agent_end_reap.py`: the orphan process decisions for the ending agent's tree, and the build-folder keep. Neither has a dirty check. The trees themselves are removed by `decide_agent_end_worktree`, which is opted in.

## Unknown reads, as built

- Sweep: an unknown record read keeps the tree (`unreadable-subject`, the sweep's keep reason). This comes before any process read.
- Guard: an unknown read with no process confirmed in the tree is a noted allow (`subject-unread`) on a forced `git worktree remove` only. An unforced one passes with no note, because git itself refuses a dirty or locked tree (owner ruling `agent-worktree-discard-is-noted`: a note protects nothing on an unforced remove).

## Known effect

From the code, not measured: a record whose leaf was moved or renamed while its parent stays reads gone. An opted-in verdict then removes the tree when no process is inside it. The branch cut's default read answers None for that record, so the branch stays, with the reason `checked-out: session read again`.

## What still guards a tree with a stale record

- In `decide_worktree`: the dirty, locked, unpushed and unmerged checks, and the process check. A finished agent's marked processes may be stopped first (see "A finished agent's tree" in `when-a-worktree-may-be-removed`).
- In `worktree_remove_subject`: the dirty and locked checks, and the process check.

Kind: process
Home: janitor/sweep.py
Home: janitor/agent_end_reap.py
Home: hooks/git_reads.py
Home: hooks/guard_core.py
