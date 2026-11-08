# A reset must not move a branch under the tree that holds it

## The ruling

Coordinator brief, 2026-11-08 03:16 CST: `git checkout -B <b> [start]` and `git switch -C <b> [start]` are refused when any worktree of the clone holds `<b>`. The holder is the running checkout, or a linked or primary checkout beside it. The guard rule is `checkout-b-current-branch` in `hooks/guard.py`, and its code is `held_branch_hit` in `hooks/guard_branch_worktree.py`.

- **Passes.** A `-B` or `-C` of a name no worktree of the clone holds. A plain `git checkout <b>`. `git switch -c <new>`. A checkout with no branch (detached). A `-C <path>` that names a checkout of another clone, judged by that clone's own worktrees.
- **The read.** One `git worktree list --porcelain`, in the checkout the command runs in (`-C`, else the last `cd`, else the cwd), and only for a call that holds `-B`, `-Bname`, `-C`, `-Cname` or `--force-create`. Any other git call starts no process for this rule. An unread list allows, the family's stance for an unread subject.
- **The pointer checkout is left out.** Its reset of `main` onto `origin/main` is the session-start recovery path, and it must not depend on this rule (`recovery-independent-of-state`). The `pointer-head` rule judges every act there, unchanged.
- **The refusal** says in words: choose a new branch name, or reset inside the worktree that holds the branch. It names neither the held branch nor the forcing flag git has for this case (`git-remedy-never-names-target`).
- **An owner override lifts it** (`owner-override`).

Why: git 2.43 resets a held branch without refusing. The ref moves, and the holder's files and index keep the old commit, so its next status shows the reverse of the reset as staged work.

The mistake: an agent resets a branch it, or a sibling worktree, already holds. The harm: a stale index in the holder, and work that is easy to lose by committing or discarding the false diff. Named limits, each a form Claude rarely writes: a glued short cluster (`-fB name`), a `bash -c` string the guard leaves unparsed, and a branch named by a full ref (`refs/heads/b`).

Risk kind: incident, the step `checkout-b-current-branch` note, and a lane's own reset of its held branch at 02:49 CST, 2026-11-08.

Kind: process
Home: hooks/guard_branch_worktree.py
