# A reset must not move a branch under the tree that holds it

## The ruling

Coordinator ruling, 2026-11-08 04:50 CST: `git checkout -B <b> [start]` and `git switch -C <b> [start]` are refused when another worktree of the clone holds `<b>`. The running worktree's own branch passes. The guard rule is `checkout-b-current-branch` in `hooks/guard.py`, and its code is `held_branch_hit` in `hooks/guard_branch_worktree.py`.

- **Passes.** A `-B` or `-C` of a name no other worktree holds, including the running worktree's own branch. A plain `git checkout <b>`. `git switch -c <new>`. A checkout with no branch (detached). A `-C <path>` that names a checkout of another clone, judged by that clone's own worktrees.
- **The read.** One `git rev-parse --show-toplevel` and one `git worktree list --porcelain`, both in the checkout the command runs in (`-C`, else the last `cd`, else the cwd). Only for a call that holds `-B`, `-Bname`, `-C`, `-Cname` or `--force-create`. Any other git call starts no process for this rule. An unread run root or list allows, the family's stance for an unread subject. So does a list that does not name the run root.
- **The pointer checkout is left out.** Its reset of `main` onto `origin/main` is the session-start recovery path, and it must not depend on this rule (decision `recovery-independent-of-state`: a recovery control must not depend on the state it recovers). The `pointer-head` rule judges every act there, unchanged.
- **The refusal** says in words: choose a new branch name, or reset inside the worktree that holds the branch. It names neither the held branch nor the forcing flag git has for this case (`git-remedy-never-names-target`: a refusal's remedy never names the forbidden target).
- **An owner override lifts it** (`owner-override`).

Why: git 2.43 resets a held branch without refusing. The ref moves, and the holder's files and index keep the old commit, so its next status shows the reverse of the reset as staged work. A reset in the running worktree moves its own files and index cleanly: measured on git 2.43.0 in review round 2 of PR #1889 (the fix that narrowed this rule).

The mistake: an agent resets a branch that a sibling worktree holds. The harm: a stale index in the holder, and work that is easy to lose by committing or discarding the false diff. Named limits, each a form Claude rarely writes: a glued short cluster (`-fB name`), a `bash -c` string the guard leaves unparsed, and a branch named by a full ref (`refs/heads/b`).

Incidents:

- **Sibling worktree, Nov 7 22:47 CST.** The roadmap push-refusal lane (`roadmap-push-refusal-says-fetch`, PR #1777). Three agent worktrees ran `git checkout -B <lane branch> origin/<lane branch>` while an earlier agent's worktree held that branch. A commit in one moved the shared ref, and the holder showed staged reverts. The lane reproduced it on git 2.43.0 at 04:51 CST Nov 8.
- **Sibling worktree, Nov 8 02:49 CST.** Lane `idle-lane-steps-unknown`. A test-author worktree ran `git checkout -B idle-lane-holds-followup <sha>` while a builder worktree held that branch. `git worktree list` showed both on it. The builder's index kept a stale staged test file, which blocked its commit.

Risk kind: incident. Source: the roadmap step note for `checkout-b-current-branch`, and the two incidents above.

Kind: process
Home: hooks/guard_branch_worktree.py
