# Agent process records are never pruned

- **What.** An agent that never stops keeps its Office start list, and a record entry with no comparable start (macOS, Windows) names its owner for good. A later solo Office pid can then read as shared and survive, and a reused pid can be refused to another agent. Every named pid reads every record file. The agent-owned-processes review (round 2, findings 3 and 5) named this; the safe side holds, the cost is a leaked hidden process or a refused kill.
- **Where.** `hooks/agent_procs.py`, `office_also_seen` and `lists_pid`, and `all_records`. Also the DISPLAY test in `janitor/agent_end_reap.py`, `has_display`: a Linux desktop that exports DISPLAY ends nothing at the stop (design choice, unmeasured).
- **Decision.** `none`.
- **Retire.** A case in `hooks/test_agent_procs.py` shows a record older than its agent's worktree, or of an agent whose stop has run, is dropped on read, and a solo Office pid is then ended. The suite passes.
