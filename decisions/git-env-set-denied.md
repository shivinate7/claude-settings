# A command that sets a git location variable is denied

## The ruling

No agent command may set `GIT_DIR`, `GIT_WORK_TREE` or `GIT_INDEX_FILE`. The guard denies a literal set of any of the three, in Bash and in PowerShell (rule `git-env-set`). The owner kept deny over ask and over a named override (2026-10-14 10:47 CDT). The command stays denied under any owner override pass (`owner-override-pass`, the owner's typed pass; owner, 2026-10-18 15:34 CDT).

- Reading and unsetting stay allowed. A mention inside quoted text stays allowed. Indirect forms are a named hole.
- `git_env_command_hit` in `hooks/guard_kill.py` reads each segment through the guard's own walker, including `sh -c`, `eval` and `pwsh -c`.
- The remedy names `git -C` and a child env with the git variables removed.
- Session start warns when `core.worktree` is set in the shared config of the repo in the cwd.

Why: a child `git init` inherited the variables and wrote `core.worktree` into the shared config, so every checkout read the wrong tree. An approved ask would reopen that path, so deny wins.

Kind: process
Home: hooks/guard_kill.py
