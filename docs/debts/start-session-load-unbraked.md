# A session start is braked only after it starts

**What.** The load brake does not refuse a `start_session` call. A started session's own start check stops a start on a full machine (`hooks/start_check.py`, decision `start-checks-after-call`, the start checks run in the started session). That stop works only if the desktop app honours it. Whether it does is unknown. Until the owner's test shows it, a lane can start on a full machine. Mac lanes start by `start_session`, which the PreToolUse guard cannot judge (decision `start-session-not-pretooluse`, start_session is not judged at PreToolUse).

**Where.** `hooks/start_check.py` (`stop_reason`). `load_hit` and `START_TOOLS` in `hooks/guard.py` list the tool, but no hook call reaches it. `hooks/start_session_audit.py` reads no load.

**Decision.** `start-session-not-pretooluse`. `start-checks-after-call`. `machine-load-brake` (the machine-load brake).

**Retire.** The owner's test shows the desktop app honours `continue: false` from a started session's SessionStart hook. Closed when that test is recorded, and `hooks/test_start_check.py` is green on the head.
