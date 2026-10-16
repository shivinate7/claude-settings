# A redirect onto a quoted path with a space is not read

- **What.** `cat > "dir with space/.claude/settings.json"` writes the settings file, but the reader splits the quoted path on its space, and no fragment of it follows the `>`. So a cap write there is not asked. Main missed it too. Found in review of lane cap-ask-data.
- **Where.** `_shell_write_hit` and `writes_to` in `hooks/guard_frozen.py` (near line 370).
- **Decision.** `subagent-model-cap`.
- **Retire.** The reader keeps a quoted redirect target whole, and a test shows a cap write onto a settings path with a space asks.
