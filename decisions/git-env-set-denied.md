# A command that sets a git location variable is denied

## The question

May an agent command set `GIT_DIR`, `GIT_WORK_TREE` or `GIT_INDEX_FILE`?

## The ruling

No. The guard denies a command that sets any of the three in a literal form, in Bash and in
PowerShell (rule `git-env-set`). Indirect forms are a named hole. Reading and unsetting stay allowed. A mention inside quoted text stays allowed.
Session start warns when `core.worktree` is set in the shared config of the repo in the cwd.

Incident: on q_max, 2026-10-14 02:41-02:47 CDT, an agent set `$env:GIT_DIR` and
`$env:GIT_WORK_TREE` in PowerShell. A test then ran a child `git init`, which inherited both.
Git wrote `core.worktree` into the shared config, and every checkout read the wrong tree. No
agent ran `git config`. The shared-tree gate asked on these sets before; an approved ask would
reopen that path, so deny wins (arbiter ruling, 03:05 CDT; the owner kept deny over ask and over a
named override, 2026-10-14 10:47 CDT).

## How it works

- `git_env_command_hit` in `hooks/guard_kill.py` reads each segment through the guard's own
  walker, including `sh -c`, `eval` and `pwsh -c`. Bash forms: `export`, an inline `VAR=`,
  `declare -x`, `env VAR=`. PowerShell forms: `$env:VAR =`, `SetEnvironmentVariable`,
  `Set-Item env:`.
- Rule 0c in `hooks/guard.py` runs it before the shared-tree gate.
- The remedy names `git -C` and a child env with the git variables removed.

## Holes, named

Debts: `git-env-set-indirect-forms` (indirect sets pass the guard), `git-env-glued-block` (a glued block opener hides the set), `git-env-set-false-alarms` (safe forms are denied), `git-env-set-untested-forms` (some escape, group and heredoc forms have no case). `git-env-warn-session-start` (the warning runs at session start only). `git-env-lower-case-fold` (lower-case names fold to the rule, so `git_dir=x cmd` is denied too).

## Build plan

Code in `hooks/guard_kill.py`, `hooks/guard.py` and `hooks/session_start.sh`. Cases in
`hooks/test_guard.py`, families `git-env` and `shared-tree`.

### windows

Built and run on this machine, Bash and PowerShell tools.

### macos

Same guard code. The macOS CI job runs the guard suite. Proof on the Mac clone is not measured.

Kind: build
Plan: decisions/git-env-set-denied.md#windows (windows)
Plan: decisions/git-env-set-denied.md#macos (macos)
