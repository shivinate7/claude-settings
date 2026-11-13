# section 15866
FAMILY = "sendmessage-session-id"
FAMILIES["sendmessage-session-id"] = "SendMessage whose to starts session_: refused, since a session_ id is not an agent name and delivery to one is unmeasured; mcp__claude-code-remote__send_message takes the session_id. Any other to, and that tool, pass this rule"
#
# Rule sendmessage-session-id. SendMessage addresses an agent by name. A `session_` id is no agent name, and auto mode
# refused a SendMessage that named one. So a SendMessage whose `to` starts `session_` is refused: its hand-off could go
# missing, and whether SendMessage delivers to such an id is unmeasured. The refusal names the right tool,
# mcp__claude-code-remote__send_message, and its session_id argument. Only SendMessage with such a `to` is refused.
# An agent name, @parent, an empty, missing or non-string `to`, and the right tool itself all pass.
# The allows are as load-bearing as the refusals: a false alarm here stops a hand-off to a reviewer or the parent.
SENDMESSAGE_RULE = "sendmessage-session-id"
SENDMESSAGE_TOOL = "SendMessage"
SENDMESSAGE_STEER = (SEND_MESSAGE, "session_id")  # the remedy names the right tool and the argument that takes the id
SENDMESSAGE_BODY = "Review the diff and report back."


def sendmessage_refuse(name, to):
    """A SendMessage the guard refuses. The reason names its rule, and the right tool with its session_id argument."""
    add("sendmessage-session-id: " + name, "deny", rule=SENDMESSAGE_RULE, tool=SENDMESSAGE_TOOL, cwd=NOGIT,
        carries=SENDMESSAGE_STEER, to=to, message=SENDMESSAGE_BODY)


def sendmessage_allow(name, **tool_input):
    """A SendMessage the guard lets through silently. This rule refuses none of them."""
    add("sendmessage-session-id: " + name, "allow", tool=SENDMESSAGE_TOOL, cwd=NOGIT, silent=True, **tool_input)


# Refused: a session_ id in `to`, short and full length.
sendmessage_refuse("to a session_ id is refused", "session_abc123")
sendmessage_refuse("to a full-length cloud session id is refused", "session_01AbCdEfGhIjKlMnOpQrStUv")
# Allowed: an agent name and the parent, which SendMessage reaches as before.
sendmessage_allow("to an agent name, reviewer-1, is allowed", to="reviewer-1", message=SENDMESSAGE_BODY)
sendmessage_allow("to @parent is allowed", to="@parent", message=SENDMESSAGE_BODY)
# Allowed: a `to` with no session_ at its start. The empty string is the empty state, and a name with session_
# mid-name is a near miss that pins the match to the start of the value.
sendmessage_allow("to an empty string is allowed", to="", message=SENDMESSAGE_BODY)
sendmessage_allow("to a name with session_ mid-name is allowed", to="my-session_1", message=SENDMESSAGE_BODY)
# Allowed: a near miss to the prefix. Each pins the match to the exact `session_` at the start: a looser prefix such as
# startswith("session") refuses session-abc, a case-insensitive match refuses Session_abc, and a match that drops a
# leading @ refuses @session_abc.
sendmessage_allow("to session-abc, a dash not an underscore, is allowed", to="session-abc", message=SENDMESSAGE_BODY)
sendmessage_allow("to Session_abc, a capital S, is allowed", to="Session_abc", message=SENDMESSAGE_BODY)
sendmessage_allow("to @session_abc, an @ before the id, is allowed", to="@session_abc", message=SENDMESSAGE_BODY)
# Allowed: a missing `to`, and a `to` that is not a string.
sendmessage_allow("a call with no to is allowed", message=SENDMESSAGE_BODY)
sendmessage_allow("to a number is allowed", to=3, message=SENDMESSAGE_BODY)
sendmessage_allow("to null is allowed", to=None, message=SENDMESSAGE_BODY)
sendmessage_allow("to a list that holds a session_ id is allowed", to=["session_abc123"], message=SENDMESSAGE_BODY)
# The right tool is not refused by this rule, even with a session_ id. A cloud session's id goes in session_id.
add("sendmessage-session-id: the right tool, send_message, to a session_ id is allowed", "allow", tool=SEND_MESSAGE,
    cwd=NOGIT, silent=True, session_id=ROLE_OTHER, message=SENDMESSAGE_BODY)


