#!/usr/bin/env python3
"""PostToolUse audit of a desktop session start (docs/decisions/start-session-not-pretooluse.md).

After a start_session call, flags a start that earns any of five reasons: a model below the floor (guard.floor_hit, the
one reading); the calling session's handoff unread (reread_check.unread_handoff, the guard's own read); a lane start (the
lane tag, shared_names.is_lane_tagged) that names no model; a lane start that names Opus when the calling session holds
no Opus override (override._take_opus, read only, so it spends nothing); and a top-level `env` that carries a session
role key, since only bin/claude-role sets a role and a start never claims one. A lane's own Grant line is not an owner
grant for Opus. An Opus override file that cannot be read adds no flag. A flagged start prints
PostToolUse additionalContext that tells the calling session to stop the new session with interrupt_session or
archive_session. A start that passes prints nothing. It never refuses and never exits 2.

The start check cannot run at PreToolUse: a PreToolUse matcher that covers start_session makes the desktop app show
the "Allow Claude to start the session?" card on every start, even in Bypass (anthropics/claude-code#103832). So the
check runs after the call and the model's only remedy is to stop the new session. A bad payload, a failed import or
any read error prints nothing: the audit fails open.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))


# A session id such as session_abc. The field name session_id and the word session_start are not ids.
SESSION_ID = re.compile(r"\bsession_(?!(?:id|start)\b)[A-Za-z0-9][A-Za-z0-9_-]*")


def response_text(response, depth=0):
    """The text of a tool_response, read from a string, a content list, a dict's `content`, `result` or `text`, or
    a list of any of these. Anything else, or a nest deeper than four, gives ""."""
    if depth > 4:
        return ""
    if isinstance(response, str):
        return response
    if isinstance(response, list):
        return "\n".join(response_text(item, depth + 1) for item in response)
    if isinstance(response, dict):
        return "\n".join(response_text(response.get(key), depth + 1) for key in ("text", "content", "result"))
    return ""


def started(response):
    """False when the tool_response shows no session started: an error flag or a refusal, or a response that is not
    text, a list or a dict (a number cannot be read, so the audit says nothing)."""
    if not isinstance(response, (str, list, dict)):
        return False
    return not (isinstance(response, dict) and any(response.get(key) for key in ("is_error", "isError", "deny")))


def new_session(response):
    """The new session's id from the response text, or a phrase that says it is unread."""
    found = SESSION_ID.search(response_text(response))
    return found.group(0) if found else "id is unread"


ROLE_ENV_KEY = "CS_SESSION_ROLE"   # the key bin/claude-role sets


def lane_opus_without_grant(payload):
    """True when the calling session holds no Opus override that covers a lane start now. A lane start runs as a
    general-purpose role, as the guard reads a create_session. An override file that cannot be read is no flag."""
    import override
    return override._take_opus(payload.get("session_id"), "general-purpose", override.now()) is None


def reasons(payload):
    """The flags a start earns, as short phrases: the model below the floor, a lane start with no model or with Opus
    and no owner grant, a role claimed in env, and an unread handoff. Empty for a start that passes."""
    import guard
    from reread_check import unread_handoff
    from shared_names import is_lane_tagged
    tool_input = payload.get("tool_input")
    found = []
    if isinstance(tool_input, dict):
        floor_model = guard.floor_hit(guard.SESSION_TOOL, tool_input)
        if floor_model:
            found.append("it names the model %s, below the Sonnet floor" % floor_model)
        if is_lane_tagged(tool_input):
            model = tool_input.get("model")
            if not (isinstance(model, str) and model.strip()):
                found.append("it is a lane start that names no model")
            elif "opus" in model.lower() and lane_opus_without_grant(payload):
                found.append("it is a lane start that names %s with no owner grant for Opus" % model)
        env = tool_input.get("env")
        if isinstance(env, dict) and ROLE_ENV_KEY in env:
            found.append("its env sets %s, which only bin/claude-role may set" % ROLE_ENV_KEY)
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
        if not started(payload.get("tool_response")):
            return 0
        found = reasons(payload)
        if found:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": ("The session you just started (%s) is a bad start: %s. Stop it: %s. Then start "
                                      "it again with a good start. (decision start-session-not-pretooluse, "
                                      "start_session is checked after the call)"
                                      % (new_session(payload.get("tool_response")), "; ".join(found), stop_line())),
            }}))
    except Exception as err:   # fail open: a hook that cannot read says nothing
        sys.stderr.write("start_session_audit: %s\n" % err)
    return 0


if __name__ == "__main__":
    sys.exit(main())
