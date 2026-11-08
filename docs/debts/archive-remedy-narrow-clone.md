# An archive push leaves no holder in a narrow-fetch clone

- **What.** In a narrow-fetch clone (`--depth` or single-branch, as cloud sessions make), the fetch refspec is `+refs/heads/main:refs/remotes/origin/main`. Pushing `b:refs/heads/archive/b` creates no tracking ref, so the guard sees no holder and still refuses the delete. A depth-1 probe confirmed it: after `git fetch origin refs/heads/archive/b:refs/remotes/origin/archive/b`, the delete is allowed. The printed remedy is a dead end, which costs Claude a retry or a stuck lane.
- **Where.** `hooks/guard_branch_worktree.py`, `design_push_delete_verdict` (its `branch_on_remote` call). `hooks/git_reads.py`, `branch_on_remote`.
- Fix: name that explicit fetch in the refusal reason, or read origin with `ls-remote` when the tracking refs are narrow. The 2026-11-03 18:55 CST ruling against an `ls-remote` per delete covers the tip read only, not this holder read.
- **Decision.** `design-branch-delete-guard`, a branch delete keeps the design file it holds. Its 2026-11-03 18:55 CST ruling covers the tip read only, not this holder read.
- **Retire.** No check shows it closed yet.
