# A commit never reverts a moved head

## The ruling

Rule `stale-index` in `hooks/guard.py` refuses a `git commit` whose tree is an old one while HEAD moved on. Its home is `stale_index_hit` in `hooks/guard_merge.py`, beside `conflict_markers_hit`. Layer: the planner, 2026-11-08 11:11 CST; lane rulings 11:27 CST, process-only.

- The mistake: HEAD moved forward and this checkout's index did not. Another worktree's `update-ref` of the shared branch does it, and so does a `reset --soft` or `update-ref` here that no `read-tree` follows. A plain `git commit` then takes the old index as its tree (incident, lane red-run-pre-push, 2026-11-08, commit 33220ecba).
- The harm: the commit silently reverts the newer commit's files. A merge of that branch undoes work that was already merged.
- The signal: the old head C. Two file reads give it, with no spawn. First, this worktree's HEAD log: its newest new value when that is not HEAD, or the old value of a newest step that is a reset or has no message. Second, the shared branch log: its newest old value when its new value is HEAD and this worktree's HEAD log did not write that step. A move made in another worktree shows only in the second.
- A hit: C is a strict ancestor of HEAD, and a path the commit carries has the same entry as at C (absent included) while HEAD's entry differs. The commit carries the index, or the working tree for `-a`, a pathspec and a commit after an earlier `git add`. The refusal names only those paths. The remedy is `git read-tree -m -u <C> HEAD`, then re-stage your own edits.
- Passes: a backward `reset --soft` (C is no ancestor of HEAD), a revert, a file checked out from an older commit, an amend with no move, a repo with no commits, and a checkout whose index already holds HEAD's tree.
- Judged like `conflict-markers`: only when each earlier segment is a git add, a git read, `true`, `false` or `cd`, and only the first commit of a call. Any other earlier step could fix the index, so the commit is not read.
- Limits: a path edited after the move whose entry matches neither C nor HEAD is not caught. A HEAD log that cannot be read gives no hit. A commit in `sh -c` or `eval`, a link or a directory where a file was, a failed read, and paths past the first 1000 are not judged (`guard-guards-mistakes-only`).
- Cost: per commit segment, one `git rev-parse` and two small file reads. Only when C exists: one `git merge-base --is-ancestor`, one `git diff-index`, two `git ls-tree`, and one `git ls-files` or `git hash-object`. Files written: none. `stale_commit_cost_case` in `hooks/test_guard.py` pins the one added spawn for a commit with no move.

Protected by the `stale-index` cases in `hooks/test_guard.py`, red before the rule landed.

Kind: process
Home: hooks/guard.py
