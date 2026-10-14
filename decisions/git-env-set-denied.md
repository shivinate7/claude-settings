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
reopen that path, so deny wins (arbiter ruling, 03:05 CDT).

## How it works

- `git_env_command_hit` in `hooks/guard_kill.py` reads each segment through the guard's own
  walker, including `sh -c`, `eval` and `pwsh -c`. Bash forms: `export`, an inline `VAR=`,
  `declare -x`, `env VAR=`. PowerShell forms: `$env:VAR =`, `SetEnvironmentVariable`,
  `Set-Item env:`.
- Rule 0c in `hooks/guard.py` runs it before the shared-tree gate.
- The remedy names `git -C` and a child env with the git variables removed.

## Holes, named

- The warning runs at session start only, so damage done mid-session shows at the next start.
- Lower-case names fold to the rule, so `git_dir=x cmd` is denied too.
- Indirect sets pass: a shell function around the set, `set -a` with `read` or `for`, a name
  built at run time, `iex`, `-EncodedCommand`, or `os.environ` in `python -c`. Debt:
  git-env-set-indirect-forms.
- A PowerShell block opener glued to its word, such as `%{`, `){`, `try{` or `$sb={`, hides a
  set inside it. Debt: git-env-glued-block.
- The env-file rule reads an apostrophe in an unquoted heredoc body as a quote, so a later
  substitution that reads an env file passes. Debt: git-env-glued-block.
- No case pins the PowerShell backtick escape, the shared group-opener pattern, or quote text in
  a heredoc body.
- False alarms on the safe side: backslash- or part-quoted heredoc delimiters read as unquoted,
  `Write-Host {$env:GIT_DIR=1}`, and a `@'...'@` body with `don't` before a set.

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
