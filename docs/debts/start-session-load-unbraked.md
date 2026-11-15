# A session start on a full machine is flagged, not stopped

**What.** Status: open. A started session on a full machine gets a flag from its own start check (`hooks/start_check.py` `flag_text`, decision `start-checks-after-call`, the start checks run in the started session). The flag asks a lane to do no work and to tell its parent. A model can ignore it, and nothing stops the start. Whether the desktop app delivers the flag to a `start_session` session is unknown. Mac lanes start by `start_session`, which no PreToolUse guard can judge (decision `start-session-not-pretooluse`, start_session is not judged at PreToolUse). Main stops no `start_session` at full, since PR 3501.

**Where.** `hooks/start_check.py` (`flag_text`). `load_hit` and `START_TOOLS` in `hooks/guard.py` list the tool, but no hook call reaches it. `hooks/start_session_audit.py` reads no load.

**Decision.** `start-session-not-pretooluse`. `start-checks-after-call`. `machine-load-brake` (the machine-load brake).

**Retire.** A route that stops a full-machine start and that a model cannot ignore. The owner picks the route. Closed when that stop is in place and a case in `hooks/test_start_check.py` shows it. Until then this debt stays open.
