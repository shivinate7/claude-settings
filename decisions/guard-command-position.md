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
- A contraction (`don't`) opens no quote only when the rest of the text holds an even count of `'`. Else the `'` is a quote, as the shell and main read it. So `echo a's b'; pkill foo` still shows its second command.

## Why

The wsl-allow-list record (WSL runs only a fixed list of test commands) named these wrappers as holes. Each one moved the command word off the slot the rules read, so a refused command passed.

## What protects it

The guard tests, families wsl, kill, env, impeccable and shared-tree.

## Holes, named

- A substitution inside a token is not read: `$(`, backticks and `x=$(...)`. Debt: guard-substitution-in-token.
- Only the WSL rule reads the script of `env -S 'cmd'`. The impeccable-review-only, draft-pr, detached-launch and rm-var-unguarded rules do not see inside it. Debt: env-split-string-wsl-only.
- The wrapper and value-flag lists are closed. An unlisted wrapper, such as `stdbuf` or `chrt`, or an unlisted value flag hides the command word. Debt: guard-wrapper-lists-closed.
- The segment split ignores backslash escapes, so `echo '; pkill foo; echo 'x'` hides `pkill`. Debt: guard-split-ignores-backslash.

Kind: process
Home: hooks/guard_core.py
