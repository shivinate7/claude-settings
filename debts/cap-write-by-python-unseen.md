# A cap write made by a Python script is not asked

- **What.** A Python command that writes `CLAUDE_CODE_SUBAGENT_MODEL` into a settings file is allowed with no ask. The shell-write reader matches text, so it cannot see a write made by code. Found while pinning lane cap-ask-data.
- **Where.** `_shell_write_hit` in `hooks/guard_frozen.py` (near line 231), used by the model-cap rule.
- **Decision.** `subagent-model-cap`.
- **Retire.** The guard parses an inline Python body for a file write to a settings path, and a test shows a Python cap write asks.
