# The guard reads the command word through one resolver

## The ruling

One resolver in `hooks/guard_core.py` finds the command word for every rule.

- It skips assignments and leading loop keywords, `(` and `$(`.
- It unwraps `sudo`, `env`, `command`, `nohup`, `nice`, `time`, `doas`, `xargs`, `timeout`, `verdict`, `exec`, `builtin`, `!` and PowerShell `&`.
- It reads each wrapper's flags getopt-style against the one table `WRAPPER_VALUE_FLAGS`. A short-flag cluster such as `sudo -Eu root` or `xargs -rn 1` skips its value.
- `nested_script` reads the script that `sh -c`, `cmd /c`, `pwsh -c`, `iex` and `env -S` run. `env -S` counts only when `env` is a wrapper of the segment.
- `heredoc_heads` is the one quote-aware reader of heredoc headers.
- `split_segments` reads quotes as bash does. Only when that reading ends inside an open quote does a second pass read each contraction-shaped `'` (`don't`) as text. The guard judges the segments of both readings. Both passes are linear. So `echo a's b'; pkill foo` and `echo don't (x; pkill foo` show their second command.

Why: each wrapper moved the command word off the slot the rules read, so a refused command passed. The guard tests (families wsl, kill, env, impeccable, shared-tree) protect it.

## Holes, named

Debts: `guard-substitution-in-token` (a substitution inside a token is not read). `env-split-string-wsl-only` (only the WSL rule reads `env -S`). `guard-wrapper-lists-closed` (an unlisted wrapper or value flag hides the command word). `guard-split-ignores-backslash` (no guard test denies the `\'` and `\"` forms). `cmd-c-script-skips-kill` (a `cmd /c` script is not read for a kill). `pwsh-cmd-script-gaps` (five pwsh or cmd script shapes pass). `in-throwaway-reads-paths-only` (`in_throwaway` reads paths only). `guard-cd-walk-extra-reading` (the second reading shows a cd that bash never runs). `guard-timeout-fails-open` (a long command can run unjudged). `guard-lone-quote-overdeny` (a lone quote can deny a clean commit). `guard-redirect-paren-heredoc` (three command shapes hide a kill). `guard-split-heredocs-here-string` (a here-string is read as a heredoc). `guard-interp-heredoc-lone-quote` (a lone quote in an interpreter heredoc hides a later command). `ps-script-block-not-read` (a PowerShell script block is not cut out as text). `cmd-c-quote-count-bash-reader` (the bash reader counts a cmd /c quote differently from cmd). `printf-quote-walk-bandaid` (the printf cut is a bandaid; the quote walk is the cause). `discards-output-slow-path` (the silent-write check re-walks each segment per redirect; unmeasured).

Kind: process
Home: hooks/guard_core.py
