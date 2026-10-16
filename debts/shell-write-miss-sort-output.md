# A sort onto a frozen path by -o is not read as a write

- **What.** `sort -o P` writes P, but `sort` is not in `MUTATING_COMMAND` and `-o` is not a redirect, so the write is not seen. Main missed it too. Found in review of lane cap-ask-data.
- **Where.** `MUTATING_COMMAND` and `writes_to` in `hooks/guard_frozen.py` (near line 160), read by `_shell_write_hit`.
- **Decision.** `frozen-path-resolves-shell-vars`, the frozen-path reader.
- **Retire.** `writes_to` reads the value of `sort -o` and `--output` as a target, and a test shows the write is refused.
