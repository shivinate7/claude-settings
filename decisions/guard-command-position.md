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

- A substitution inside a token is not read: `$(`, backticks and `x=$(...)`. Debt: guard-substitution-in-token.
- Only the WSL rule reads the script of `env -S 'cmd'`. The impeccable-review-only, draft-pr, detached-launch and rm-var-unguarded rules do not see inside it. Debt: env-split-string-wsl-only.
- The wrapper and value-flag lists are closed. An unlisted wrapper, such as `stdbuf` or `chrt`, or an unlisted value flag hides the command word. Debt: guard-wrapper-lists-closed.
- The segment split ignores backslash escapes, so `echo '; pkill foo; echo 'x'` hides `pkill`. Debt: guard-split-ignores-backslash.
- The second reading can show a `cd` that bash never runs, as in `git restore f.txt` then `echo don't; cd <lane>`. The run-folder walk then judges the restore in the lane. Debt: guard-cd-walk-extra-reading.
- An odd count of `'` doubles guard time. A 6,001-word command takes 31.8 s, past the 20 s hook timeout, and a timed-out hook lets the call run. Debt: guard-long-command-near-timeout.
- Commit-message rules read heredoc headers one way only. A lone `'` line before a heredoc commit then hides a path-citing body. Main denies it. Debt: guard-heredoc-one-reading.
- A leading redirect, `)#`, and a heredoc header that ends in an open quote hide a kill, as on main. Debt: guard-redirect-paren-heredoc.

Kind: process
Home: hooks/guard_core.py
