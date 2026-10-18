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

Kind: process
Home: hooks/guard_core.py
