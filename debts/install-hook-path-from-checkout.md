# The post-merge hook takes its install path from the checkout that pulled

- **What.** The post-merge git hook runs the installer from the checkout that ran the pull. A linked worktree that holds `main` would run the installer from itself. The installer now refuses a linked worktree, so this case fails loudly, not silently. Today only the main clone holds `main`.
- **Where.** `install.ps1`, lines 102-106 and the hook copy at lines 143-146.
- **Decision.** None. The incident of 2026-10-14 16:40 CDT: an install from a linked worktree pointed the owner's config at that worktree.
- **Retire.** The hook takes its path from the parent folder of `git rev-parse --git-common-dir`. A test pulls `main` in a linked worktree and sees the install run from the main clone.
