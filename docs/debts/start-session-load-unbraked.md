# A session start meets no load brake

**What.** `start_session` is no longer refused on a full machine. The load brake read the load only inside the PreToolUse guard, and that hook cannot list `start_session` (it makes the desktop app show its start card on every start). Mac lanes start by `start_session`, so a lane can start while memory is over 95% or the disk is under 5 GB free. Four lanes did that on 2026-10-26.

**Where.** `load_hit` and `START_TOOLS` in `hooks/guard.py` (the tool is listed, but no hook call reaches it). `hooks/start_session_audit.py` reads no load.

**Decision.** `start-session-not-pretooluse` (start_session is not gated at PreToolUse). `machine-load-brake` (the machine-load brake).

**Retire.** A lane start on a full machine is stopped some way that adds no PreToolUse hook on `start_session`: for example the coordinator's own Agent or Task call carries the check, or the audit stops a session started at full. The owner picks the route. Closed when a case in `hooks/test_guard.py` shows that start refused or stopped on a full reading, red on today's code.
