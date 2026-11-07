# A commit with conflict markers is refused

## The ruling

Rule `conflict-markers` in `hooks/guard.py` refuses a Bash `git commit` whose commit would hold git conflict markers. Its home is `conflict_markers_hit` in `hooks/guard_merge.py`, beside the records-page check, and it reads the commit's shape the same way.

- The mistake: a conflict-fix step fails, and the next command in the chain still stages and commits the file (incident, lane merge-waits-required-only, 2026-11-07 02:36 CST, local only, removed by a fix commit before push).
- The harm: markers on a pushed branch break every file they touch, and a reviewer or a later merge may carry them on.
- The guard runs before the command, so it judges what the commit will hold. An earlier `git add` in the chain, `commit -a`, or a commit with paths: the working tree against HEAD. Otherwise: the index against HEAD. After `git add <paths>`, the files those paths cover are read from the working tree and the rest from the index.
- It counts only `git diff --check`'s leftover-conflict-marker findings, never its whitespace findings. A hit needs all three markers in one file's added lines: `<<<<<<< `, a lone `=======`, `>>>>>>> `. So a doc that quotes one marker, or a heading underlined by seven `=`, commits. A full triplet inside a markdown fence is refused: a real conflict in a doc looks the same.
- A failed git read, a repo with no commits, or an unmerged index judged alone (git refuses that commit itself) is no hit (`guard-that-cries-wolf-is-spent`).
- Not read: `sh -c`, `eval`, and a file outside the tracked set that `git add -A` would add (`guard-guards-mistakes-only`). `merge`, `rebase` and `cherry-pick --continue` are not judged yet.
- Cost: one `git diff --check` per `git commit` segment. No log, file or process.

Protected by the `conflict-markers` cases in `hooks/test_guard.py`, red on main before the rule landed.

Kind: process
Home: hooks/guard.py
