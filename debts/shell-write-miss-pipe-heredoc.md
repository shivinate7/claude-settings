# A heredoc piped into a shell is not read as a write

- **What.** A heredoc piped into a shell (`cat <<EOF | sh`) that writes a settings or frozen path is not seen. Its body is stripped before the shell-write reader runs, because the header names `cat`, not an interpreter. Main missed it too. Found in review of lane cap-ask-data.
- **Where.** `strip_heredoc_bodies` in `hooks/guard_core.py`, read by `_shell_write_hit` in `hooks/guard_frozen.py`.
- **Decision.** `frozen-path-resolves-shell-vars`, the frozen-path reader.
- **Retire.** The strip keeps a heredoc body when a later segment of the command is a shell, and a test shows the write is refused.
