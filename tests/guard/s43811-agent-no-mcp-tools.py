# section 43811
FAMILY = "agent-no-mcp-tools"
AGENT_NO_MCP = "agent-no-mcp-tools"  # the rule id the refusal names
# The refusal says why: an agent cannot answer a permission prompt, so a call that would ask waits on no one.
MCP_REFUSAL = "answer a permission prompt"
# The refusal leads with its rule id, the label before the reason's first ": ". A case asserts the rule by that label (rule=,
# and the label in carries), never by the absence of a sibling's slug, because the refusal may cite the record that holds it.
MCP_LABEL = AGENT_NO_MCP + ": "
MCP_REFUSAL_CARRIES = (MCP_LABEL, MCP_REFUSAL)
# The decision that holds this rule (decision agent-no-remote-tools). Its slug equals the sibling rule's name, so it is
# named here by its own constant and never by AGENT_NO_REMOTE. OLD_CITE is the record the refusal cited before, which it must drop.
HOME_CITE = "decision agent-no-remote-tools"
OLD_CITE = "lanes-start-as-agents"
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


# An agent's call to an unlisted MCP tool is refused, from either agent shape. The reason leads with this rule's label and carries the phrase.
for _name, _input in UNLISTED_MCP_CALLS:
    for _shape, _id, _type in AGENT_SHAPES:
        add("agent-no-mcp-tools: %s from %s is refused" % (_name, _shape), "deny",
            raw=mcp_call(_name, _input, _id, _type), rule=AGENT_NO_MCP, carries=MCP_REFUSAL_CARRIES)
    # The same call from the session itself, with no agent_id, passes: the rule judges an agent's calls only.
    add("agent-no-mcp-tools: %s from the session itself is allowed" % _name, "allow", raw=mcp_call(_name, _input))
# The refusal cites the record that holds this rule, and not the record the sibling agent rule's refusal is copied from.
add("agent-no-mcp-tools: an agent's MCP refusal cites decision agent-no-remote-tools, not lanes-start-as-agents", "deny",
    raw=mcp_call(UNLISTED_MCP_CALLS[0][0], UNLISTED_MCP_CALLS[0][1], AGENT_ID_VALUE, "general-purpose"),
    rule=AGENT_NO_MCP, carries=HOME_CITE, lacks=OLD_CITE)

# An agent's call to an MCP tool the allow list covers passes, from either agent shape.
for _shape, _id, _type in AGENT_SHAPES:
    add("agent-no-mcp-tools: %s from %s is allowed, the allow list covers it" % (LISTED_MCP_CALL[0], _shape), "allow",
        raw=mcp_call(LISTED_MCP_CALL[0], LISTED_MCP_CALL[1], _id, _type))

# A remote-server tool that the allow list names is still refused by agent-no-remote-tools, which judges it before this rule.
add("agent-no-mcp-tools: send_message from a general-purpose agent is still refused by agent-no-remote-tools", "deny",
    raw=remote_call("send_message", {"session_id": "session_AGENTSEND01", "message": "x"}, AGENT_ID_VALUE, "general-purpose"),
    rule=AGENT_NO_REMOTE, lacks=AGENT_NO_MCP)

# A lookalike server is another server: an allow entry covers the server named in full and its `__` tools, so the lookalike
# below, which starts with that name, is refused for an agent and gets no verdict from the session's own call.
LOOKALIKE_MCP_CALL = ("mcp__Claude_Browser_evil__navigate", {"url": "about:blank"})
add("agent-no-mcp-tools: %s from a designer agent is refused, a lookalike server is not covered" % LOOKALIKE_MCP_CALL[0],
    "deny", raw=mcp_call(LOOKALIKE_MCP_CALL[0], LOOKALIKE_MCP_CALL[1], AGENT_ID_VALUE, "designer"),
    rule=AGENT_NO_MCP, carries=MCP_REFUSAL_CARRIES)
add("agent-no-mcp-tools: %s from the session itself gets no verdict from this rule" % LOOKALIKE_MCP_CALL[0],
    "allow", raw=mcp_call(LOOKALIKE_MCP_CALL[0], LOOKALIKE_MCP_CALL[1]), silent=True)

# settings.json that yields no allow list covers nothing (hooks/guard.py mcp_allow_entries). Each guard copy below is a whole
# guard family in its own folder, with its settings.json beside its hooks folder. The config folder's settings.json is "{}"
# (s00442-misc), so the second read finds no list either. The control copy reads the same call as allowed, so the refusal
# comes from the file and not from the copy.
COPY_ALLOW_TEXT = '{"permissions": {"allow": ["mcp__Claude_Browser"]}}\n'
MCP_COPY_ROOT = os.path.join(ROOT, "agent-mcp-copies")
MCP_COPY_TEXT = {
    "nokey": '{"env": {}}\n',
    "badjson": "{ not json\n",
    "allowed": COPY_ALLOW_TEXT,
}


def mcp_copy_guard(name):
    """The guard copy of one MCP_COPY_TEXT folder: its hooks/guard.py, which reads the settings.json beside that folder."""
    return os.path.join(MCP_COPY_ROOT, name, "hooks", "guard.py")


def build_mcp_copies():
    """Every MCP_COPY_TEXT folder, built the first time a case names one of its guard copies."""
    for name, text in sorted(MCP_COPY_TEXT.items()):
        folder = os.path.join(MCP_COPY_ROOT, name)
        os.makedirs(os.path.join(folder, "hooks"), exist_ok=True)
        copy_guard_family(os.path.join(folder, "hooks"))
        write(os.path.join(folder, "settings.json"), text)


lazy_fixture([mcp_copy_guard(_name) for _name in MCP_COPY_TEXT], build_mcp_copies)
add("agent-no-mcp-tools: %s from a designer agent is refused when settings.json has no permissions key" % LISTED_MCP_CALL[0],
    "deny", raw=mcp_call(LISTED_MCP_CALL[0], LISTED_MCP_CALL[1], AGENT_ID_VALUE, "designer"),
    rule=AGENT_NO_MCP, carries=MCP_REFUSAL_CARRIES, guard=mcp_copy_guard("nokey"))
add("agent-no-mcp-tools: %s from a designer agent is refused when settings.json does not parse" % LISTED_MCP_CALL[0],
    "deny", raw=mcp_call(LISTED_MCP_CALL[0], LISTED_MCP_CALL[1], AGENT_ID_VALUE, "designer"),
    rule=AGENT_NO_MCP, carries=MCP_REFUSAL_CARRIES, guard=mcp_copy_guard("badjson"))
add("agent-no-mcp-tools: %s from a designer agent is allowed by the control copy whose settings.json lists the server"
    % LISTED_MCP_CALL[0], "allow", raw=mcp_call(LISTED_MCP_CALL[0], LISTED_MCP_CALL[1], AGENT_ID_VALUE, "designer"),
    guard=mcp_copy_guard("allowed"), silent=True)
add("agent-no-mcp-tools: %s from the session itself is not judged when settings.json has no permissions key"
    % LISTED_MCP_CALL[0], "allow", raw=mcp_call(LISTED_MCP_CALL[0], LISTED_MCP_CALL[1]),
    guard=mcp_copy_guard("nokey"), silent=True)

# The cost a watcher states for this rule (decision agent-no-remote-tools, Cost): one settings.json read per agent MCP call,
# a second only when the first copy cannot be read, one guard.log line on a refusal, and no write on an allowed call. The
# probe runs the guard in its own process under an audit hook, which records each open the run makes. Its config folder is a
# fresh one under ROOT, never the real ~/.claude.
COST_ROOT = os.path.join(ROOT, "agent-mcp-cost")
WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
PROBE_ENV_DROPS = ("CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_REMOTE_SESSION_ID", "CLAUDE_CODE_REMOTE", "CLAUDE_PROJECT_DIR",
                   "CS_SESSION_ROLE", "CLAUDE_SCRATCHPAD_BASE")
# The probe body, run with -c. It records (mode, flags, path) of every open event until the guard returns, then writes
# the list to PROBE_OUT. Its own write happens after the hook is switched off, so it is not counted.
AUDIT_PROBE = (
    "import json, os, runpy, sys\n"
    "events, done = [], []\n"
    "def hook(event, args):\n"
    "    if event == 'open' and not done and args and isinstance(args[0], str):\n"
    "        events.append([args[1] if len(args) > 1 else None, args[2] if len(args) > 2 else None, args[0]])\n"
    "sys.addaudithook(hook)\n"
    "try:\n"
    "    sys.argv = [os.environ['PROBE_GUARD']]\n"
    "    runpy.run_path(os.environ['PROBE_GUARD'], run_name='__main__')\n"
    "finally:\n"
    "    done.append(1)\n"
    "    with open(os.environ['PROBE_OUT'], 'w') as out:\n"
    "        json.dump(events, out)\n"
)


def is_write_open(event):
    """True when one recorded open writes: a text mode with w, a, x or +, or, for an os-level open with no mode, write flags."""
    mode, flags, _path = event
    if isinstance(mode, str):
        return any(letter in mode for letter in "wax+")
    return isinstance(flags, int) and bool(flags & WRITE_FLAGS)


def probe_run(label, guard, payload):
    """Run one payload through `guard` under the audit probe, with a fresh config folder. Returns (stdout, opens, log_lines),
    where opens is every recorded open and log_lines is what the run left in that folder's guard.log. None when the probe
    did not finish, so a check reads that as a failure rather than as no opens."""
    folder = os.path.join(COST_ROOT, label)
    shutil.rmtree(folder, ignore_errors=True)
    cfg = os.path.join(folder, "cfg")
    write(os.path.join(cfg, "settings.json"), "{}\n")
    out_path = os.path.join(folder, "opens.json")
    env = dict(os.environ)
    for name in PROBE_ENV_DROPS:
        env.pop(name, None)
    env.update({"CLAUDE_CONFIG_DIR": cfg, "CLAUDE_GUARD_ROOT_PID": str(os.getpid()), "PYTHONDONTWRITEBYTECODE": "1",
                "PROBE_GUARD": guard, "PROBE_OUT": out_path})
    try:
        done = subprocess.run([sys.executable, "-c", AUDIT_PROBE], input=payload, capture_output=True, text=True,
                              env=env, cwd=folder, timeout=120)
        with open(out_path, encoding="utf-8") as handle:
            opens = json.load(handle)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    log_path = os.path.join(cfg, "guard.log")
    log_lines = []
    if os.path.isfile(log_path):
        with open(log_path, encoding="utf-8") as handle:
            log_lines = [line for line in handle.read().splitlines() if line]
    return done.stdout, opens, log_lines


def settings_reads(opens):
    """The opens of a settings.json file that only read it."""
    return [event for event in opens if event[2].endswith("settings.json") and not is_write_open(event)]


def agent_mcp_cost_case():
    """One agent MCP call costs one settings.json read, and a second only when the first copy cannot be read. An allowed
    call writes nothing; a refusal appends one guard.log line. Returns (ok, reason)."""
    materialize(mcp_copy_guard("badjson"))  # a log check runs outside any case, so it builds the copy it names
    faults = []
    allowed = probe_run("allowed", GUARD, mcp_call(LISTED_MCP_CALL[0], LISTED_MCP_CALL[1], AGENT_ID_VALUE, "general-purpose"))
    refused = probe_run("refused", GUARD, mcp_call(UNLISTED_MCP_CALLS[0][0], UNLISTED_MCP_CALLS[0][1], AGENT_ID_VALUE, "designer"))
    unreadable = probe_run("unreadable", mcp_copy_guard("badjson"),
                           mcp_call(LISTED_MCP_CALL[0], LISTED_MCP_CALL[1], AGENT_ID_VALUE, "designer"))
    for name, probe in (("allowed", allowed), ("refused", refused), ("unreadable", unreadable)):
        if probe is None:
            faults.append("%s: the probe did not finish" % name)
    if faults:
        return False, "; ".join(faults)
    allowed_out, allowed_opens, _ = allowed
    refused_out, refused_opens, refused_log = refused
    unreadable_out, unreadable_opens, _ = unreadable
    if allowed_out.strip():
        faults.append("an allowed call printed %r, not nothing" % allowed_out.strip()[:80])
    if [event for event in allowed_opens if is_write_open(event)]:
        faults.append("an allowed call wrote a file")
    if len(settings_reads(allowed_opens)) != 1:
        faults.append("an allowed call read settings.json %d times, not once" % len(settings_reads(allowed_opens)))
    if '"permissionDecision": "deny"' not in refused_out:
        faults.append("the unlisted call was not refused")
    if len(settings_reads(refused_opens)) != 1:
        faults.append("a refused call read settings.json %d times, not once" % len(settings_reads(refused_opens)))
    if len(refused_log) != 1:
        faults.append("a refused call left %d guard.log line(s), not one" % len(refused_log))
    if len([event for event in refused_opens if is_write_open(event)]) != 1:
        faults.append("a refused call opened more than guard.log for writing")
    if '"permissionDecision": "deny"' not in unreadable_out:
        faults.append("the call through the unreadable copy was not refused")
    if len(settings_reads(unreadable_opens)) != 2:
        faults.append("a call whose first settings.json cannot be read read it %d times, not twice"
                      % len(settings_reads(unreadable_opens)))
    if faults:
        return False, "; ".join(faults)
    return True, ("one settings.json read per agent MCP call, two when the first copy cannot be read, no write on an allowed "
                  "call, one guard.log line on a refusal")


# LOG_CHECKS_EXTRA joined LOG_CHECKS in section 40805, so this check joins LOG_CHECKS directly, with its family set here.
COST_CHECK_LABEL = ("agent-no-mcp-tools: one agent MCP call reads settings.json once, reads it again only when the first "
                    "copy cannot be read, writes nothing when allowed, and appends one guard.log line when refused")
LOG_FAMILY[COST_CHECK_LABEL] = FAMILY
LOG_CHECKS = LOG_CHECKS + ((COST_CHECK_LABEL, agent_mcp_cost_case),)
FIXTURELESS_CHECKS.add(agent_mcp_cost_case)  # it builds only the bad-JSON copy it names, not every fixture of the run
