# A write inside a quoted command substitution is not read

- **What.** A write inside a command substitution in double quotes, `"$( ... > P)"`, is not seen, for the same glued-parenthesis reason. Main missed it too. Found in review of lane cap-ask-data.
- **Where.** `_shell_write_hit` in `hooks/guard_frozen.py`.
- **Decision.** `frozen-path-resolves-shell-vars`, the frozen-path reader.
- **Retire.** The reader reads each `$(...)` body as its own command, and a test shows the write is refused.
