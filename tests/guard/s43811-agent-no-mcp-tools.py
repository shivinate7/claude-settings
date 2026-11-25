# section 43811
FAMILY = "agent-no-mcp-tools"
AGENT_NO_MCP = "agent-no-mcp-tools"  # the rule id the refusal names
# The refusal says why: an agent cannot answer a permission prompt, so a call that would ask waits on no one.
MCP_REFUSAL = "answer a permission prompt"
# MCP tools the settings.json allow list does not cover: a computer-use tool and a rea tool.
UNLISTED_MCP_CALLS = (
    ("mcp__computer-use__app_click", {}),
    ("mcp__rea__list_names", {}),
)
# An MCP tool the allow list covers: settings.json names the whole mcp__Claude_Browser server.
LISTED_MCP_CALL = ("mcp__Claude_Browser__navigate", {"url": "about:blank"})


def mcp_call(name, tool_input, agent_id=None, agent_type=None):
    """The PreToolUse payload of one MCP call as the hook receives it. remote_call prefixes only the claude-code-remote
    server, so a call to any other server names its tool in full here. An agent's payload carries agent_id and
    agent_type beside tool_name and tool_input. The session's own payload carries neither."""
    body = {"tool_name": name, "tool_input": tool_input, "cwd": NOGIT}
    if agent_id:
        body["agent_id"] = agent_id
    if agent_type:
        body["agent_type"] = agent_type
    return json.dumps(body)


# An agent's call to an unlisted MCP tool is refused, from either agent shape. The reason carries the phrase and no remote rule id.
for _name, _input in UNLISTED_MCP_CALLS:
    for _shape, _id, _type in AGENT_SHAPES:
        add("agent-no-mcp-tools: %s from %s is refused" % (_name, _shape), "deny",
            raw=mcp_call(_name, _input, _id, _type), rule=AGENT_NO_MCP, carries=MCP_REFUSAL, lacks=AGENT_NO_REMOTE)
    # The same call from the session itself, with no agent_id, passes: the rule judges an agent's calls only.
    add("agent-no-mcp-tools: %s from the session itself is allowed" % _name, "allow", raw=mcp_call(_name, _input))

# An agent's call to an MCP tool the allow list covers passes, from either agent shape.
for _shape, _id, _type in AGENT_SHAPES:
    add("agent-no-mcp-tools: %s from %s is allowed, the allow list covers it" % (LISTED_MCP_CALL[0], _shape), "allow",
        raw=mcp_call(LISTED_MCP_CALL[0], LISTED_MCP_CALL[1], _id, _type))

# A remote-server tool that the allow list names is still refused by agent-no-remote-tools, which judges it before this rule.
add("agent-no-mcp-tools: send_message from a general-purpose agent is still refused by agent-no-remote-tools", "deny",
    raw=remote_call("send_message", {"session_id": "session_AGENTSEND01", "message": "x"}, AGENT_ID_VALUE, "general-purpose"),
    rule=AGENT_NO_REMOTE, lacks=AGENT_NO_MCP)
