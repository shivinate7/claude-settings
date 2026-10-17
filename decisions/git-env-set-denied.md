# A command that sets a git location variable is denied

## The ruling

No agent command may set `GIT_DIR`, `GIT_WORK_TREE` or `GIT_INDEX_FILE`. The guard denies a literal set of any of the three, in Bash and in PowerShell (rule `git-env-set`). The owner kept deny over ask and over a named override (2026-10-14 10:47 CDT).

- Reading and unsetting stay allowed. A mention inside quoted text stays allowed. Indirect forms are a named hole.
- `git_env_command_hit` in `hooks/guard_kill.py` reads each segment through the guard's own walker, including `sh -c`, `eval` and `pwsh -c`. Bash forms: `export`, an inline `VAR=`, `declare -x`, `env VAR=`. PowerShell forms: `$env:VAR =`, `SetEnvironmentVariable`, `Set-Item env:`.
- Rule 0c in `hooks/guard.py` runs it before the shared-tree gate.
- The remedy names `git -C` and a child env with the git variables removed.
- Session start warns when `core.worktree` is set in the shared config of the repo in the cwd.

Why: a child `git init` inherited the variables and wrote `core.worktree` into the shared config, so every checkout read the wrong tree. An approved ask would reopen that path, so deny wins.

## Holes, named

Debts: `git-env-set-indirect-forms` (indirect sets pass the guard), `git-env-glued-block` (a glued block opener hides the set), `git-env-set-false-alarms` (safe forms are denied), `git-env-set-untested-forms` (some escape, group and heredoc forms have no case), `git-env-warn-session-start` (the warning runs at session start only), `git-env-lower-case-fold` (lower-case names fold to the rule, so `git_dir=x cmd` is denied too).

## Build plan

Code in `hooks/guard_kill.py`, `hooks/guard.py` and `hooks/session_start.sh`. Cases in `hooks/test_guard.py`, families `git-env` and `shared-tree`.

### windows

Built and run here, Bash and PowerShell tools.

### macos

Same guard code. The macOS CI job runs the guard suite.

Kind: build
Plan: decisions/git-env-set-denied.md#windows (windows)
Plan: decisions/git-env-set-denied.md#macos (macos)
