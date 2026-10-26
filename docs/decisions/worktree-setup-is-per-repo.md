# Worktree setup is per repo

## The ruling

Each repo sets up the untracked state (node_modules, venv, caches) of a worktree itself. claude-settings
ships no worktree-setup hook. Reason: a worktree made mid-session gets no setup, because a SessionStart
hook runs only when a session starts in it. Dev-server ports are in reuse-needs-checkout-proof.

Facts a repo needs:

- Claude Code's own worktrees (Agent `isolation: worktree`) do not fire git `post-checkout`. A plain
  `git worktree add` does, with the old HEAD all zeros.
- A `WorktreeCreate` hook replaces Claude Code's worktree creation, must print the path, and fails
  creation if it fails. No documented event fires after default creation. Native options: the
  `worktree.symlinkDirectories` setting and a `.worktreeinclude` file.

Kind: process
Home: docs/decisions/worktree-setup-is-per-repo.md
