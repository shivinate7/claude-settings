# An agent called session tools by mistake

- **What.** On 2026-11-07 an agent called session tools by mistake. A test-author called `create_session`, and that session was archived. A test-author called `interrupt_session`, and it was refused. The harm: a stray session, or a stopped peer.
- **Where.** `hooks/guard.py`, `CREATE_SESSION_TOOL`, and `hooks/guard_merge.py`, `ARCHIVE_TOOL` and `BRIEF_TOOL`. The rules read these tools for lane and archive cases only. No rule is aimed at agents, and `interrupt_session` has no rule.
- **Decision.** `none`.
- **Retire.** A case in `hooks/test_guard.py` refuses each of `create_session`, `interrupt_session`, `send_message` and `archive_session` when an agent calls it, and allows the main session's call. The suite passes.
