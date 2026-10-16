# An eval of a heredoc is not read as a write

- **What.** An eval of a heredoc body that writes a settings or frozen path is not seen. The body is stripped before the shell-write reader runs. Main missed it too. Found in review of lane cap-ask-data.
- **Where.** `strip_heredoc_bodies` in `hooks/guard_core.py`, read by `_shell_write_hit` in `hooks/guard_frozen.py`.
- **Decision.** `frozen-path-resolves-shell-vars`, the frozen-path reader.
- **Retire.** The shell-write reader keeps the body of a heredoc that an eval runs, and a test shows the write is refused.
