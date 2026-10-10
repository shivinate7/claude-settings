# Worktree setup is per repo

## The question

A worktree made mid-session gets no setup of its untracked state (node_modules, venv, caches).
A SessionStart hook runs only when a session starts in that worktree. Should claude-settings own
one shared fix for every repo that imports it?

## The ruling

Owner, 2026-10-10: no. Each repo solves it itself. claude-settings ships no worktree-setup hook.

## Facts a repo needs

- Measured 2026-10-10: Claude Code's own worktrees (Agent `isolation: worktree`) do not fire
  git `post-checkout`. A plain `git worktree add` does, with the old HEAD all zeros.
- From the docs: a `WorktreeCreate` hook replaces Claude Code's worktree creation, must print
  the path, and fails creation if it fails. No documented event fires after default creation.
  Native options: the `worktree.symlinkDirectories` setting and a `.worktreeinclude` file.
- Incident: banchi (PR shivinate7/banchi#793). Checks needing node_modules reported "unknown"
  in a worktree made mid-session.
