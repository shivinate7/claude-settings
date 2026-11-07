# Conflict markers never leave the machine

## The ruling

Rule `conflict-markers` in `hooks/guard.py` refuses a commit or a push that would carry git conflict markers. Its home is `conflict_markers_hit` in `hooks/guard_merge.py`, beside the records-page check. Layer: the coordinator, 2026-11-07 03:10 CST, option b, after review round 1 found the commit-only design both missed and cried wolf.

- The mistake: a conflict-fix step fails, and the next command in the chain still stages and commits the file (incident, lane merge-waits-required-only, 2026-11-07 02:36 CST, local only, removed by a fix commit before push).
- The harm: markers on a pushed branch break every file they touch, and a review or a later merge may carry them on.
- A hit: all three markers in one file's added lines, from `git diff --check`'s leftover-conflict-marker findings only, never its whitespace findings. The markers: `<<<<<<< `, a lone `=======`, `>>>>>>> `. A doc that quotes one marker, or a heading underlined by seven `=`, passes. A full triplet inside a markdown fence is refused: a real conflict in a doc looks the same.
- At commit. The guard runs before the command, so it cannot see what an earlier step in the same call does to the tree. It judges a commit only when each earlier segment is a git add, a git read, `true` or `false`. Then it reads the index, and the working-tree files those adds, `commit -a` or `commit <path>` cover. Any other earlier segment gives no hit at commit; the push check catches it.
- At push, for every session. It judges the commits the push would send, so `rebase --continue`, `merge --continue` and new files are covered. Committed content is real when the guard runs, so this check has no chain blind spot.
- A commit then a push in one call, where the commit cannot be judged: refused, with the remedy to push in a call of its own.
- A failed git read, or a repo with no commits, is no hit (`guard-that-cries-wolf-is-spent`). `sh -c` and `eval` are not read (`guard-guards-mistakes-only`).
- Why not a git pre-commit hook: a global `core.hooksPath` replaces each repo's `.git/hooks`, and a repo that sets its own `core.hooksPath` (such as `scripts/githooks`) overrides the global one, by git-config's order (repository config over global). So it would either break a repo's hooks or skip the repo silently.
- Cost: one `git diff --check` per judged commit, and one `git diff --check` over the sent range per push. No log, file or process.

Protected by the `conflict-markers` cases in `hooks/test_guard.py`, red before the rule landed.

Kind: process
Home: hooks/guard.py
