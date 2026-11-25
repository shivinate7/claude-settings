# Send-tool lists omit the desktop send tool

**What.** `lint/_transcript.py` SEND_TOOLS names the desktop session send tool, `mcp__ccd_session_mgmt__send_message`. Four other lists name the send tools on their own and do not: `hooks/answered_claims.py` TEXT_FIELDS, `hooks/decision_watch.py` PEER_MESSAGE_TOOLS, and two PreToolUse matchers in `settings.json`. No PreToolUse matcher matches the desktop tool, so a before-a-tool send rule does not run on a desktop send. A rule that reads a sent message (an answered claim, a watched decision) does not see one either. A desktop session sends with that tool in normal work, so Claude will hit this. Found on PR 3892, which adds the desktop tool to SEND_TOOLS.

**Where.** `hooks/answered_claims.py`, `TEXT_FIELDS` at line 42. `hooks/decision_watch.py`, `PEER_MESSAGE_TOOLS` at line 123. `settings.json`, the PreToolUse matchers at lines 269 and 319.

**Decision.** `session-messages` (messages to and from sessions, with the peer guard).

**Retire.** Each list reads SEND_TOOLS, or a check proves the lists agree with it. The two settings matchers name the desktop send tool.
