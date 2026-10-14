# The guard does not read a substitution inside a token

- **What.** A command inside a token is not read as a command: `$(...)` glued after other text, backticks, and `x=$(...)`. A refused command there passes the guard.
- **Where.** `command_indexes` in `hooks/guard_core.py`. It reads only a token that starts with `(` or `$(`.
- **Decision.** `guard-command-position` (the guard reads the command word through one resolver).
- **Retire.** Read each `$(`, backtick and assignment substitution inside a token as a command start. A guard test with `x=$(wsl --shutdown)` and `` echo `wsl --shutdown` `` denies.
