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
    skip_case("kill: a lease holder recorded to another agent with its start text is refused for the calling agent", NO_PS)
    skip_case("kill: a lease holder recorded to another agent with its start ticks is refused (control)", NO_PS)
else:
    import atexit

    AGENT_CALLER = "5c0a1e7d93b2f4860"  # 17 hex characters, as the payload's agent_id carries it
    AGENT_OTHER = "b71f3d0c2a9e56847"
    PROCS = os.path.join(ROOT, "agent-procs")
    os.makedirs(PROCS, exist_ok=True)

    def _child_with_marker(agent):
        env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_AGENT_ID", "CLAUDE_CODE_SESSION_ID")}
        env["CLAUDE_AGENT_ID"] = agent
        child = subprocess.Popen(["sleep", "300"], env=env)
        atexit.register(lambda: child.kill())
        return child

    def _start_ticks(pid):
        with open("/proc/%d/stat" % pid, encoding="utf-8") as handle:
            return int(handle.read().rsplit(")", 1)[1].split()[19])

    def _write_procs(agent, entries):
        with open(os.path.join(PROCS, agent + ".json"), "w", encoding="utf-8") as handle:
            json.dump({"agent": agent, "procs": entries}, handle)

    def _record(agent, child):
        _write_procs(agent, [{"pid": child.pid, "start": _start_ticks(child.pid), "owner": agent, "kind": "background"}])

    def _plain_child():
        """A sleeping child with no agent marker. The kill check reads its record, not its environment."""
        env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_AGENT_ID", "CLAUDE_CODE_SESSION_ID")}
        child = subprocess.Popen(["sleep", "300"], env=env)
        atexit.register(lambda: child.kill())
        return child

    def _lstart(pid):
        """The `ps -o lstart=` text of PID, which bin/sim-lease writes as a lease row's start (TZ=UTC)."""
        return subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True,
                              env=dict(os.environ, TZ="UTC")).stdout.strip()

    OTHERS_CHILD = _child_with_marker(AGENT_OTHER)
    OWN_CHILD = _child_with_marker(AGENT_CALLER)
    _record(AGENT_OTHER, OTHERS_CHILD)
    _record(AGENT_CALLER, OWN_CHILD)
    GUARD_ENV = {"CLAUDE_AGENT_PROCS_DIR": PROCS}
    sh("kill: a pid recorded to another agent is refused for the calling agent", "kill %d" % OTHERS_CHILD.pid,
       "deny", "machine-wide-kill", cwd=NOGIT, agent_id=AGENT_CALLER, env=GUARD_ENV)
    sh("kill: a pid recorded to the calling agent is allowed", "kill %d" % OWN_CHILD.pid, "allow", cwd=NOGIT,
       agent_id=AGENT_CALLER, env=GUARD_ENV)
    # A simulator lease holder: no agent marker, and its row carries the lease's start text, as bin/sim-lease writes it.
    # The control is the same shape with the start ticks, which the record reads, so the two differ only in the start.
    AGENT_LEASE = "c3e9a07b1d5f28460"  # 17 hex characters: the agent whose take granted the lease
    LEASE_HOLDER = _plain_child()
    LEASE_TICKED = _plain_child()
    _write_procs(AGENT_LEASE, [
        {"pid": LEASE_HOLDER.pid, "start": _lstart(LEASE_HOLDER.pid), "owner": AGENT_LEASE, "kind": "sim-lease"},
        {"pid": LEASE_TICKED.pid, "start": _start_ticks(LEASE_TICKED.pid), "owner": AGENT_LEASE, "kind": "sim-lease"},
    ])
    sh("kill: a lease holder recorded to another agent with its start text is refused for the calling agent",
       "kill %d" % LEASE_HOLDER.pid, "deny", "machine-wide-kill", cwd=NOGIT, agent_id=AGENT_CALLER, env=GUARD_ENV)
    sh("kill: a lease holder recorded to another agent with its start ticks is refused (control)",
       "kill %d" % LEASE_TICKED.pid, "deny", "machine-wide-kill", cwd=NOGIT, agent_id=AGENT_CALLER, env=GUARD_ENV)
