# section 29526
FAMILY = "agent-remote-tools"
REMOTE_PREFIX = "mcp__claude-code-remote__"
AGENT_ID_VALUE = "a1b2c3d4e5f607182"  # 17 hex characters, the measured agent_id shape
# archive_session is judged by lane-closes-after-records, which refuses a target it cannot read as a non-lane. A
# triage target is the allowed one (archive_allow above), so the archive rows reach the agent rule on old code.
OUTWARD_CALLS = (
    ("create_session", {"prompt": "x"}, None),
    ("archive_session", {"session_id": ROLE_OTHER}, role_path("archive-triage")),
    ("send_message", {"session_id": "session_AGENTSEND01", "message": "x"}, None),
    ("set_session_tags", {"session_ids": ["session_AGENTTAG01"], "add": ["x"]}, None),
    ("create_trigger", {"name": "x", "prompt": "x", "initiation": "own_followup"}, None),
)
READ_CALLS = (
    ("get_session", {"session_id": "session_AGENTREAD01"}),
    ("list_sessions", {"limit": 5}),
)
AGENT_SHAPES = (
    ("a general-purpose agent", AGENT_ID_VALUE, "general-purpose"),
    ("an agent with no agent_type", AGENT_ID_VALUE, None),
)
# The session server's start_session. It is the one outward tool outside claude-code-remote: it has its own prefix, so
# it is named whole here (full_name), never built from REMOTE_PREFIX. An agent's call starts a session through it.
START_SESSION_CALL = "mcp__ccd_session__start_session"
START_SESSION_INPUT = {"initiation": "user_asked", "prompt": "x", "model": "sonnet"}


def full_name(tool):
    """The full tool name: a short claude-code-remote name gets REMOTE_PREFIX, and a full name is kept."""
    return tool if tool.startswith("mcp__") else REMOTE_PREFIX + tool


def short_name(tool):
    """The name a refusal must not carry: a claude-code-remote tool's short form, else the full name."""
    return tool[len(REMOTE_PREFIX):] if tool.startswith(REMOTE_PREFIX) else tool


def remote_call(tool, tool_input, agent_id=None, agent_type=None, transcript=None):
    """The PreToolUse payload of one outward tool call as the hook receives it. An agent's payload carries
    agent_id and agent_type beside tool_name and tool_input. The session's own payload carries neither."""
    body = {"tool_name": full_name(tool), "tool_input": tool_input, "cwd": NOGIT}
    if agent_id:
        body["agent_id"] = agent_id
    if agent_type:
        body["agent_type"] = agent_type
    if transcript:
        body["transcript_path"] = transcript
    return json.dumps(body)


def outward_case(name, expected, tool, tool_input, transcript, agent_id=None, agent_type=None, **kw):
    """One case on an outward tool's payload. A transcript-reading call runs in ROLE_ENV, as archive_allow does. The case
    names the full tool, so the load brake's probe reads a start call as a start call."""
    add(name, expected, raw=remote_call(tool, tool_input, agent_id, agent_type, transcript),
        tool=full_name(tool), env=ROLE_ENV if transcript else None, **kw)


for _tool, _input, _transcript in OUTWARD_CALLS:
    for _shape, _id, _type in AGENT_SHAPES:
        outward_case("agent-no-remote-tools: %s from %s is refused" % (_tool, _shape), "deny", _tool, _input,
                     _transcript, _id, _type, rule=AGENT_NO_REMOTE, lacks=_tool)
# A truthy agent_id that fails the AGENT_ID shape is still a carried agent_id: the rule keys on the field, so a
# harness id that drifts from the measured form stays refused rather than turning the rule off.
outward_case("agent-no-remote-tools: create_session with an agent_id that fails the AGENT_ID shape is refused", "deny",
             "create_session", {"prompt": "x"}, None, "agent:1", "general-purpose", rule=AGENT_NO_REMOTE,
             lacks="create_session")
for _tool, _input, _transcript in OUTWARD_CALLS:
    outward_case("agent-no-remote-tools: %s from the session itself keeps today's verdict" % _tool, "allow",
                 _tool, _input, _transcript)
    outward_case("agent-no-remote-tools: %s from an agent_type with no agent_id keeps today's verdict" % _tool,
                 "allow", _tool, _input, _transcript, None, "general-purpose")
for _tool, _input in READ_CALLS:
    for _shape, _id, _type in AGENT_SHAPES:
        add("agent-no-remote-tools: %s from %s is allowed" % (_tool, _shape), "allow", silent=True,
            raw=remote_call(_tool, _input, _id, _type))
# start_session: an agent's call is refused in both agent shapes, and the session's own call and an agent_type with no
# agent_id keep their verdict. A call that carries a lane tag is no lane start: the lane gate reads tags on create_session
# only (is_lane_create_session), so no lane rule judges this call, and it keeps its verdict too.
for _shape, _id, _type in AGENT_SHAPES:
    outward_case("agent-no-remote-tools: start_session from %s is refused" % _shape, "deny", START_SESSION_CALL,
                 START_SESSION_INPUT, None, _id, _type, rule=AGENT_NO_REMOTE, lacks=START_SESSION_CALL)
outward_case("agent-no-remote-tools: start_session from the session itself keeps today's verdict", "allow",
             START_SESSION_CALL, START_SESSION_INPUT, None)
outward_case("agent-no-remote-tools: start_session from an agent_type with no agent_id keeps today's verdict", "allow",
             START_SESSION_CALL, START_SESSION_INPUT, None, None, "general-purpose")
outward_case("agent-no-remote-tools: start_session carrying a lane tag from the session is not a lane start", "allow",
             START_SESSION_CALL, dict(START_SESSION_INPUT, tags=["cs-build:lane"]), None)
# The twenty-one outward tools, pinned by full name: the twenty claude-code-remote names, and start_session, which has its
# own prefix. Each name gets its own deny case from a general-purpose agent, so a REMOTE_OUTWARD_TOOLS that drops one name
# goes red on that name. The equality check holds the constant to this set.
PINNED_OUTWARD_TOOLS = (
    "mcp__claude-code-remote__create_session",
    "mcp__claude-code-remote__send_message",
    "mcp__claude-code-remote__archive_session",
    "mcp__claude-code-remote__unarchive_session",
    "mcp__claude-code-remote__interrupt_session",
    "mcp__claude-code-remote__set_session_tags",
    "mcp__claude-code-remote__set_session_title",
    "mcp__claude-code-remote__create_trigger",
    "mcp__claude-code-remote__update_trigger",
    "mcp__claude-code-remote__delete_trigger",
    "mcp__claude-code-remote__fire_trigger",
    "mcp__claude-code-remote__send_later",
    "mcp__claude-code-remote__watch_url",
    "mcp__claude-code-remote__unwatch_url",
    "mcp__claude-code-remote__subscribe_pr_activity",
    "mcp__claude-code-remote__unsubscribe_pr_activity",
    "mcp__claude-code-remote__add_repo",
    "mcp__claude-code-remote__register_repo_root",
    "mcp__claude-code-remote__confirm_repository_trust",
    "mcp__claude-code-remote__request_computer_folder",
    START_SESSION_CALL,
)
# Three pinned names have a main rule that answers first (judge() in guard.py: rules 8a before 8b). Each name's case on
# the bare call expects that owner rule. A second case, on a shape the owner lets through, expects agent-no-remote-tools,
# so the new rule is proven for each name. OUTWARD_CALLS also runs archive_session on that shape; the pinned case is the
# one the pin set counts, so both stay.
OWNED_PINNED = {
    "mcp__claude-code-remote__archive_session": (ARCHIVE_RULE, {}),
    "mcp__claude-code-remote__confirm_repository_trust": (TRUST_RULE, {}),
    "mcp__claude-code-remote__request_computer_folder": (TRUST_RULE, {}),
}
# The shape each owner lets through, with the transcript it reads: a non-lane target, and an untagged own record.
OWNER_PASSES = {
    "mcp__claude-code-remote__archive_session": ({"session_id": ROLE_OTHER}, role_path("archive-triage")),
    "mcp__claude-code-remote__confirm_repository_trust": (TRUST_TOOLS["mcp__claude-code-remote__confirm_repository_trust"],
                                                          role_path("untagged")),
    "mcp__claude-code-remote__request_computer_folder": (TRUST_TOOLS["mcp__claude-code-remote__request_computer_folder"],
                                                         role_path("untagged")),
}
for _full in PINNED_OUTWARD_TOOLS:
    _short = short_name(_full)
    if _full in OWNED_PINNED:
        _owner, _bare_input = OWNED_PINNED[_full]
        outward_case("agent-no-remote-tools: pinned %s from a general-purpose agent is refused by %s first" % (_short, _owner),
                     "deny", _short, _bare_input, None, AGENT_ID_VALUE, "general-purpose", rule=_owner,
                     lacks=(_short, AGENT_NO_REMOTE))
        _pass_input, _pass_transcript = OWNER_PASSES[_full]
        outward_case("agent-no-remote-tools: pinned %s from a general-purpose agent on a shape %s allows is refused" % (_short, _owner),
                     "deny", _short, _pass_input, _pass_transcript, AGENT_ID_VALUE, "general-purpose", rule=AGENT_NO_REMOTE,
                     lacks=_short)
        continue
    _input = START_SESSION_INPUT if _full == START_SESSION_CALL else {}
    outward_case("agent-no-remote-tools: pinned %s from a general-purpose agent is refused" % _short, "deny",
                 _short, _input, None, AGENT_ID_VALUE, "general-purpose", rule=AGENT_NO_REMOTE, lacks=_short)


def pinned_outward_check():
    """REMOTE_OUTWARD_TOOLS in hooks/shared_names.py is the pinned set: it holds each pinned name, once, and no other.
    It reads the copy beside this file, so a copy under test is the one checked."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("shared_names_pinned", os.path.join(HERE, "shared_names.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "REMOTE_OUTWARD_TOOLS"):
        return False, "shared_names.py defines no REMOTE_OUTWARD_TOOLS"
    constant = tuple(module.REMOTE_OUTWARD_TOOLS)
    for name in PINNED_OUTWARD_TOOLS:
        if name not in constant:
            return False, "REMOTE_OUTWARD_TOOLS lacks %s" % name
    for name in constant:
        if name not in PINNED_OUTWARD_TOOLS:
            return False, "REMOTE_OUTWARD_TOOLS holds %s, which is not pinned" % name
    if len(set(constant)) != len(constant):
        return False, "REMOTE_OUTWARD_TOOLS repeats a name"
    return True, "REMOTE_OUTWARD_TOOLS holds exactly the 21 pinned names"


FIXTURELESS_CHECKS.add(pinned_outward_check)
LOG_CHECKS_EXTRA.append(("agent-remote-tools: REMOTE_OUTWARD_TOOLS holds exactly the pinned outward names",
                         pinned_outward_check))
