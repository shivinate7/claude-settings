# A write inside a subshell is not read

- **What.** A write inside a subshell, `( ... > P)`, is not seen: the closing parenthesis stays glued to the path word, so the path never matches. Main missed it too. Found in review of lane cap-ask-data.
- **Where.** `_shell_write_hit` in `hooks/guard_frozen.py`.
- **Decision.** `frozen-path-resolves-shell-vars`, the frozen-path reader.
- **Retire.** The reader splits a subshell's text off its parentheses, and a test shows the write is refused.
