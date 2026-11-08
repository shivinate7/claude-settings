# A merged design branch is refused against an old origin/main

- **What.** A PR is merged on GitHub, and its design branch is deleted before this clone fetches origin. The guard reads the last-fetched origin/main. That copy lacks the design file, so the guard refuses the remote delete. The file is on main, so the refusal is a false alarm. Remedy: `git fetch origin`, or push an archive ref. The archive push clears it, except in a narrow-fetch clone: there the push leaves no tracking ref, so the refusal stays (debt `archive-remedy-narrow-clone`).
- **Where.** `hooks/guard_branch_worktree.py`, `design_push_delete_verdict`. Its default-branch read, `resolve_default_base` in `hooks/git_reads.py`, reads the remote-tracking `origin/HEAD`, else `origin/main`.
- **Decision.** `design-branch-delete-guard`, a branch delete keeps the design file it holds. Its 2026-11-03 18:55 CST ruling covers the tip read only, not this default-branch read.
- **Retire.** The guard stops refusing a merged branch on a stale origin/main. No check shows it closed yet. Until then the remedy above holds.
