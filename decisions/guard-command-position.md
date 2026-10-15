# The guard reads the command word through one resolver

## The question

Where does a segment's real command sit, when a wrapper, a subshell, a heredoc header or a contraction stands in front of it?

## The ruling

One resolver finds the command word for every rule. It lives in `hooks/guard_core.py`.

- It skips assignments and leading loop keywords, `(` and `$(`.
- It unwraps `sudo`, `env`, `command`, `nohup`, `nice`, `time`, `doas`, `xargs`, `timeout`, `verdict`, `exec`, `builtin`, `!` and PowerShell `&`.
- It reads each wrapper's flags getopt-style against the one table `WRAPPER_VALUE_FLAGS`. A short-flag cluster such as `sudo -Eu root` or `xargs -rn 1` skips its value.
- `nested_script` reads the script that `sh -c`, `cmd /c`, `pwsh -c`, `iex` and `env -S` run. `env -S` counts only when `env` is a wrapper of the segment.
- `heredoc_heads` is the one quote-aware reader of heredoc headers.
- `split_segments` reads quotes as bash does, so each unquoted `'` opens a quote. Only when that reading ends inside an open quote does a second pass read each contraction-shaped `'` (`don't`) as text. The guard judges the segments of both readings. Both passes are linear. So `echo a's b'; pkill foo` and `echo don't (x; pkill foo` show their second command.

## Why

The wsl-allow-list record (WSL runs only a fixed list of test commands) named these wrappers as holes. Each one moved the command word off the slot the rules read, so a refused command passed.

## What protects it

The guard tests, families wsl, kill, env, impeccable and shared-tree.

## Holes, named

Debts: `guard-substitution-in-token` (a substitution inside a token is not read), `env-split-string-wsl-only` (only the WSL rule reads `env -S`), `guard-wrapper-lists-closed` (an unlisted wrapper or value flag hides the command word), `guard-split-ignores-backslash` (no guard test denies the `\'` and `\"` forms), `cmd-c-script-skips-kill` (a `cmd /c` script is not read for a kill; hole L1), `pwsh-cmd-script-gaps` (five script shapes pass; hole L3), `guard-cd-walk-extra-reading` (the second reading shows a cd that bash never runs), `guard-timeout-fails-open` (a long command can run unjudged), `guard-lone-quote-overdeny` (a lone quote can deny a clean commit), `guard-redirect-paren-heredoc` (three command shapes hide a kill). `guard-split-heredocs-here-string` (a here-string is read as a heredoc). `guard-interp-heredoc-lone-quote` (a lone quote in an interpreter heredoc hides a later command).

- L1. The kill rule does not read a `cmd /c` script as a command. `cmd /c taskkill /F /IM node.exe` and `cmd /c cd C:\x\& taskkill /F /IM node.exe` are allowed, on main too. Debt: cmd-c-script-skips-kill.
- L2. `in_throwaway` reads paths only. So `git --git-dir=/tmp/x/.git merge -q t` with a real cwd, `env -C <real> git commit` from a temp cwd, and a linked worktree under temp pass as throwaway. Debt: in-throwaway-reads-paths-only.
- L3. Five shapes of a pwsh or cmd script pass: a pwsh `taskkill`, a cmd lone `&` before wsl, `-EncodedCommand`, a substitution in a script, and the kill and stream forms of `iex`. All are allowed on main too. Debt: pwsh-cmd-script-gaps.

Kind: process
Home: hooks/guard_core.py
