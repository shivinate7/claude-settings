# A cap write made by a Python script is not asked

- **What.** A Python command that writes `CLAUDE_CODE_SUBAGENT_MODEL` into a settings file is allowed with no ask. The shell-write reader matches text, so it cannot see a write made by code. The same holds for a `python script.py` that runs the text a printer pipes to it: that text is data to the reader. Found while pinning lane cap-ask-data.
- **Where.** `_shell_write_hit` in `hooks/guard_frozen.py` (near line 370), used by the model-cap rule.
- **Decision.** `subagent-model-cap`.
- **Retire.** The guard parses an inline Python body for a file write to a settings path, and a test shows a Python cap write asks.
