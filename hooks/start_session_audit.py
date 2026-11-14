#!/usr/bin/env python3
"""PostToolUse audit of a desktop session start (docs/decisions/start-session-not-pretooluse.md).

After a start_session call, flags a start below the model floor (guard.floor_hit, the one reading) or one made with
the calling session's handoff unread (reread_check.unread_handoff, the guard's own read). A flagged start prints
PostToolUse additionalContext that tells the calling session to stop the new session with interrupt_session or
archive_session. A start that passes prints nothing. It never refuses and never exits 2.

The start check cannot run at PreToolUse: a PreToolUse matcher that covers start_session makes the desktop app show
the "Allow Claude to start the session?" card on every start, even in Bypass (anthropics/claude-code#103832). So the
check runs after the call and the model's only remedy is to stop the new session. A bad payload, a failed import or
any read error prints nothing: the audit fails open.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def reasons(payload):
    """The flags a start earns, as short phrases: the model below the floor, and an unread handoff. Empty for a
    start that passes."""
    import guard
    from reread_check import unread_handoff
    tool_input = payload.get("tool_input")
    found = []
    if isinstance(tool_input, dict):
        floor_model = guard.floor_hit(guard.SESSION_TOOL, tool_input)
        if floor_model:
            found.append("it names the model %s, below the Sonnet floor" % floor_model)
    unread = unread_handoff(payload)
    if unread:
        found.append("the calling session had not read its handoff (%s) after compaction" % unread)
    return found


def stop_line():
    """The remedy: the two tools that end a session, named as the repo's remote server names them."""
    from shared_names import REMOTE_SERVER
    return "call %s__interrupt_session or %s__archive_session on it now" % (REMOTE_SERVER, REMOTE_SERVER)


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict) or payload.get("tool_name") != "mcp__ccd_session__start_session":
            return 0
        found = reasons(payload)
        if found:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": ("The session you just started is a bad start: %s. Stop it: %s. Then start "
                                      "it again with a good start. (decision start-session-not-pretooluse, "
                                      "start_session is checked after the call)" % ("; ".join(found), stop_line())),
            }}))
    except Exception as err:   # fail open: a hook that cannot read says nothing
        sys.stderr.write("start_session_audit: %s\n" % err)
    return 0


if __name__ == "__main__":
    sys.exit(main())
