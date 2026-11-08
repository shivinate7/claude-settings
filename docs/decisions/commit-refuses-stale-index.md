# A commit never reverts a moved head

## The ruling

Rule `stale-index` in `hooks/guard.py` refuses a `git commit` whose tree is an old one while HEAD moved on. Its home is `stale_index_hit` in `hooks/guard_merge.py`, beside `conflict_markers_hit`. Layer: the planner, 2026-11-08 11:11 CST; lane rulings 11:27 CST, process-only.

- The mistake: HEAD moved forward and this checkout's index did not. Another worktree's `update-ref` of the shared branch does it, and so does a `reset --soft` or `update-ref` here that no `read-tree` follows. A plain `git commit` then takes the old index as its tree (incident, lane red-run-pre-push, 2026-11-08, commit 33220ecba).
- The harm: the commit silently reverts the newer commit's files. A merge of that branch undoes work that was already merged.
- The signal: the old head C. Two file reads give it, with no spawn. First, this worktree's HEAD log: its newest new value when that is not HEAD, or the old value of a newest step that is a reset or has no message. Second, only when this worktree has no HEAD log of its own, the shared branch log: its newest old value when its new value is HEAD. A move made in another worktree shows only there. With a HEAD log, the first read already covers every move this worktree missed, and the shared log would only repeat a step this worktree switched away from and back to.
- A chained move: `update-ref <this branch> X` or `reset --soft X` before the commit in the same call. The guard resolves X with `git rev-parse` and runs nothing. It judges the commit with C as the current HEAD and X as the head it will sit on, and refuses only when C is a strict ancestor of X. A backward `reset --soft` (a squash) passes. The ancestor test is `branch_is_ancestor` in `hooks/git_reads.py`.
- A hit: C is a strict ancestor of HEAD, and a path the commit carries has the same entry as at C (absent included) while HEAD's entry differs. The commit carries the index, or the working tree for `-a`, a pathspec and a commit after an earlier `git add`. The refusal names only those paths. The remedy: copy your edited files aside, run `git read-tree -m -u <C> HEAD`, then `git update-ref -m "stale-index: synced to HEAD" HEAD HEAD` (a HEAD log line whose old value equals its new one, which the guard reads as no move; agents may not run `git reset`), then copy your files back and re-stage.
- Passes: a backward `reset --soft` (C is no ancestor of HEAD), a revert, a file checked out from an older commit, an amend with no move, a repo with no commits, and a checkout whose index already holds HEAD's tree.
- Judged like `conflict-markers`: only when each earlier segment is a git add, a git read, `true`, `false` or `cd`, and only the first commit of a call. Any other earlier step could fix the index, so the commit is not read.
- Limits: a path edited after the move whose entry matches neither C nor HEAD is not caught. A HEAD log that cannot be read gives no hit. With no HEAD log of its own, two moves made in other worktrees give only the newest one's C, so the older move's files are missed. Two chained moves, and a move whose target holds a substitution, are not read. A commit in `sh -c` or `eval`, a link or a directory where a file was, a failed read, and paths past the first 1000 are not judged (`guard-guards-mistakes-only`).
  - A chained move to a target that diverged from HEAD is not judged.
  - `git fetch && git commit` in one call is not judged, because fetch is not chain-safe.
  - A read-tree without the sync still refuses a later deliberate `rm`. This is accepted (lane ruling, 12:50 CST Nov 8).
  - After a forward `reset --hard X`, a deliberate `rm` of a file X added is refused until you run the remedy, because the log message cannot tell reset modes apart.
- Cost: per commit segment, one `git rev-parse` and two small file reads. Only when C exists: one `git merge-base --is-ancestor`, one `git diff-index`, two `git ls-tree`, and one `git ls-files` or `git hash-object`. A chained move adds one `git rev-parse`. Files written: none. `stale_commit_cost_case` in `hooks/test_guard.py` pins the one added spawn for a commit with no move.

Protected by the `stale-index` cases in `hooks/test_guard.py`, red before the rule landed.

Kind: process
Home: hooks/guard.py
