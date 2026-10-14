# Safe git-env set forms are denied

- **What.** False alarms on the safe side. `%{} $env:GIT_DIR='x'`, `try{$env:GIT_DIR=$null}catch{}`, and a quoted glued block in the same segment as a here-string are denied. So are backslash- or part-quoted heredoc delimiters read as unquoted, `Write-Host {$env:GIT_DIR=1}`, and a `@'...'@` body with `don't` before a set.
- **Where.** `git_env_command_hit` in `hooks/guard_kill.py`.
- **Decision.** `git-env-set-denied` (a command that sets a git location variable is denied).
- **Retire.** Each listed form passes, and a case per form in the git-env family of `hooks/test_guard.py` pins it.
