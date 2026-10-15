# A git diff onto a frozen path by --output is not read as a write

- **What.** `git diff --output=P` writes P, but the flag value is not read as a target, so the write is not seen. Main missed it too. Found in review of lane cap-ask-data.
- **Where.** `writes_to` in `hooks/guard_frozen.py` (near line 167), read by `_shell_write_hit`.
- **Decision.** `frozen-path-resolves-shell-vars`, the frozen-path reader.
- **Retire.** `writes_to` reads the value of `--output` on a git call as a target, and a test shows the write is refused.
