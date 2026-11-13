# A git commit, merge or push that skips git hooks is refused

## The ruling

The guard refuses a `git commit`, `git merge` or `git push` that skips git hooks (rule `hook-bypass`). The refused forms:

- `git -c core.hooksPath=<anything>` on the call, any case of the key.
- `--no-verify` on the call, and `-n` on `commit` only. On `push`, `-n` is a dry run, and on `merge` it is `--no-stat`; both pass.
- A `git config core.hooksPath <value>` write (`--local`, `--worktree`, `--global`, `--add`) in the same command as the commit, merge or push.
- The environment forms `GIT_CONFIG_PARAMETERS` and `GIT_CONFIG_KEY_<n>` naming `core.hooksPath`, on the same call.
- Any of these inside `sh -c`, `bash -c` or `eval`.

Coordinator, 2026-11-09 00:39 CST (a process ruling, not an owner ruling): a config write that disables hooks before a commit is the same mistake, and the step's goal covers it.

- A quoted mention, a commit message, a heredoc body and a read of the key (`git config core.hooksPath`) pass.
- The guard reads parsed tokens, never raw text.
- `hooks/mutate_shared.py` sets `core.hooksPath` inside Python for its own throwaway worktree. The guard never sees that call, so the guard holds no exemption for it. A test pins that the setting stays in that file.
- Known limits, not counted: `--config-env=core.hooksPath=VAR`, and an environment set in one command segment and used in another.
- Known limit, the likeliest way to hit the mistake: a `git config core.hooksPath <value>` write in one call and the commit in a later call. The guard judges one call at a time and the write stays in `.git/config`, so the later commit passes. A lone write is allowed on purpose: setting a repo's own hooks path is a normal setup step, and refusing every lone write would block it. A write that names a null path (`/dev/null`) is the form to refuse next, if an incident shows this gap.
- The same-call config write is refused for any value, including a repo's own hooks folder. That is a false alarm for a setup snippet that sets its path and commits in one call. Split the snippet into two calls.

Why: lane `bg-tail-loses-verdict`, 23:56 CST, 2026-11-08. A test-author on Haiku made its first commit with `git -c core.hooksPath=/dev/null`, which skipped every git hook. It amended with hooks on before the push, so the pushed head went through the hooks and no harm landed. Nothing refused the form. The harm a hook skip stops: a commit that carries what a hook exists to catch reaches a shared branch unchecked. This record replaces the debt note `no-verify-unguarded`, which waited for an incident.

Kind: process
Home: hooks/guard_merge.py
