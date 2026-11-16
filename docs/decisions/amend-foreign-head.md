# An amend rewrites only a commit this checkout made

## The ruling

Rule `amend-foreign-head` in `hooks/guard.py` refuses a Bash `git commit --amend` when HEAD's reflog in the target folder shows no own entry whose new sha is HEAD. Its home is `amend_foreign_head_hit` in `hooks/guard.py`, beside `entry_kind`, which reads the reflog subjects.

- The mistake: a refused command left HEAD unchanged, and the next `git commit --amend` rewrote another agent's commit (incident: consultant, 2026-11-16 09:14 CST).
- The harm: that agent's commit and its Red-run proof are silently rewritten, so the proof no longer matches the commit it was made for.
- A hit: the `--amend` flag of a `git commit` call, in any flag form, chained, or through `-C`, while no HEAD reflog entry that `entry_kind` reads as OWN or NOTED carries HEAD's sha. A clone, reset, switch, pull and plain cherry-pick entry is no own entry.
- The remedy names the new commit: leave that commit as it is and make a new commit with `git commit`.
- Unknown is no hit: a folder, HEAD or reflog that cannot be read, a repo with no commit, and a throwaway repo under the temp folder pass.
- Not pinned: the session form, a call with no agent id in another agent's worktree, the literal incident. No other rule reaches it on the old guard, and the owner has not ruled on it.
- Not exempt: an amend during a rebase stop, where HEAD is a plain `rebase (pick)` entry, is refused like any other foreign HEAD.
- Cost: one `git rev-parse` and one `git reflog show` per amend, none for any other command. No log, file or long-lived process.

Protected by the `amend-foreign-head` cases in `hooks/test_guard.py`, red on the guard before the rule landed.

Kind: process
Home: hooks/guard.py
