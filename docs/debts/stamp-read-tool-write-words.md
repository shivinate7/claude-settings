# The checked-stamp rule reads some read-only tools as writes

**What.** `_is_read` in `hooks/precompact_handoff.py` reads an MCP tool by the words in its name. The write words `run` and `reply` (`WRITE_MCP_WORDS`) veto the read word, so `mcp__github__get_check_run` and `mcp__github__get_project_message_reply` count as writes. A tool outside `READ_TOOLS` with no read word, such as `ArtifactData`, the `Artifact` read action and NotebookRead, backs nothing either. Mistake: Claude checks a CI premise with `get_check_run` alone, then restamps its handoff. Harm: the rule refuses once. The escape is another read, `Checked never`, or an override, so it is no dead end. Reported 2026-11-10 (lane handoff-checked-stamp, round 3); read again on main.

**Where.** `hooks/precompact_handoff.py`, `_is_read`, `READ_MCP_WORDS`, `WRITE_MCP_WORDS`, and `READ_TOOLS`.

**Decision.** `precompact-handoff` (checkpoints keep the handoff current), item 15 (a handoff restamp needs evidence). The debt `stamp-read-false-alarms` holds the same harm for shell calls.

**Retire.** A case per tool above, each a read that must back its premise, red on the current code. Test file: `hooks/test_precompact_handoff.py`.
