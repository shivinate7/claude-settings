# section 71834
FAMILY = "kill"

# AGENT-OWNED KILL (step agent-owned-processes, ruling own-agent-owned-processes). The kill-only-yours guard reads
# the record of the processes each agent started: a pid recorded to another agent is refused for the calling agent,
# and a pid recorded to the calling agent is allowed. The record is `<dir>/<agent_id>.json` under
# CLAUDE_AGENT_PROCS_DIR, and its start is the process's start ticks (field 22 of /proc/<pid>/stat).
# Both children are live children of this suite, so the ownership walk reads each as this session's: only the
# record tells the two agents apart.
if not os.path.isdir("/proc"):
    skip_case("kill: a pid recorded to another agent is refused for the calling agent", NO_PS)
    skip_case("kill: a pid recorded to the calling agent is allowed", NO_PS)
else:
    import atexit

    AGENT_CALLER = "5c0a1e7d93b2f4860"  # 17 hex characters, as the payload's agent_id carries it
    AGENT_OTHER = "b71f3d0c2a9e56847"
    PROCS = os.path.join(ROOT, "agent-procs")
    os.makedirs(PROCS, exist_ok=True)

    def _child_with_marker(agent):
        # No marker when AGENT is None: a child only the record can tie to an agent.
        env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_AGENT_ID", "CLAUDE_CODE_SESSION_ID")}
        if agent:
            env["CLAUDE_AGENT_ID"] = agent
        child = subprocess.Popen(["sleep", "300"], env=env)
        atexit.register(lambda: child.kill())
        return child

    def _start_ticks(pid):
        with open("/proc/%d/stat" % pid, encoding="utf-8") as handle:
            return int(handle.read().rsplit(")", 1)[1].split()[19])

    def _record(agent, *children):
        entries = [{"pid": child.pid, "start": _start_ticks(child.pid), "owner": agent, "kind": "background"}
                   for child in children]
        with open(os.path.join(PROCS, agent + ".json"), "w", encoding="utf-8") as handle:
            json.dump({"agent": agent, "procs": entries}, handle)

    OTHERS_CHILD = _child_with_marker(AGENT_OTHER)
    OWN_CHILD = _child_with_marker(AGENT_CALLER)
    # Each of these two is refused by one check alone: MARKED_UNRECORDED has the other agent's marker and no record,
    # UNMARKED_RECORDED has a record to the other agent and no marker. OTHERS_CHILD has both, so it cannot tell them apart.
    MARKED_UNRECORDED = _child_with_marker(AGENT_OTHER)
    UNMARKED_RECORDED = _child_with_marker(None)
    _record(AGENT_OTHER, OTHERS_CHILD, UNMARKED_RECORDED)
    _record(AGENT_CALLER, OWN_CHILD)
    GUARD_ENV = {"CLAUDE_AGENT_PROCS_DIR": PROCS}
    sh("kill: a pid recorded to another agent is refused for the calling agent", "kill %d" % OTHERS_CHILD.pid,
       "deny", "machine-wide-kill", cwd=NOGIT, agent_id=AGENT_CALLER, env=GUARD_ENV)
    sh("kill: a pid recorded to the calling agent is allowed", "kill %d" % OWN_CHILD.pid, "allow", cwd=NOGIT,
       agent_id=AGENT_CALLER, env=GUARD_ENV)
    sh("kill: a pid marked for another agent, with no record, is refused for the calling agent",
       "kill %d" % MARKED_UNRECORDED.pid, "deny", "machine-wide-kill", cwd=NOGIT, agent_id=AGENT_CALLER, env=GUARD_ENV)
    sh("kill: a pid recorded to another agent, with no marker, is refused for the calling agent",
       "kill %d" % UNMARKED_RECORDED.pid, "deny", "machine-wide-kill", cwd=NOGIT, agent_id=AGENT_CALLER, env=GUARD_ENV)
