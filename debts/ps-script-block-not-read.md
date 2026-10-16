# A PowerShell script block is not cut out as text

- **What.** `_substitutions` has no branch for `{ }`. So a PowerShell script block is not cut out as its own text, as `$( )` and backticks are. Each rule reads the block's words only as part of the outer segment. A silenced write inside a block may pass. The passing form is not pinned by a test, and its effect is unmeasured. The lane tests pin script blocks only for the env and detached-launch rules. This is not `ps-quote-forms-unread` (smart quotes and block comments), and not `guard-bash-c-silent-write` (a `bash -c` script).
- **Where.** `_substitutions` in `hooks/guard_env.py` (no `{ }` branch in lines 183-264); the silent-write rule, `discards_output` in `hooks/guard.py`.
- **Decision.** `guard-command-position` (the guard reads the command word through one resolver).
- **Retire.** `_substitutions` cuts each PowerShell `{ }` block as its own text. A guard test denies a silenced git write inside a block, on a folder that is not a throwaway. The test goes red on the current code first.
