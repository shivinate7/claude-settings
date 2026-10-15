# A crashed agent brief hook leaves no visible trace

- **What.** On an internal error the hook prints no context and writes one `agent_brief:` line to stderr. Claude never sees stderr from a hook that exits 0, so that line shows only with debug logging.
- **Where.** The error path of `hooks/agent_brief.py`.
- **Decision.** `agents-get-standing-rules` (every spawned agent gets the standing rules at start).
- **Retire.** A crash leaves a line that shows at the default log level, and a case in `hooks/test_agent_brief.py` pins it.
