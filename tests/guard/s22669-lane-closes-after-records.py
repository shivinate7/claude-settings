# section 22669
FAMILY = "lane-closes-after-records"
for _label, _check in (
        ("lane-closes-after-records: own_session_read reads a bare JSON record, unwrapped",
         own_read_case("archive-lane", [ARCH_LANE_TAGS])),
        ("lane-closes-after-records: own_session_read reads a record in the real wrapper, the nonce on both tags",
         own_read_case("archive-wrapped-lane", [ARCH_LANE_TAGS])),
        ("lane-closes-after-records: own_session_read reads a triage record in the real wrapper",
         own_read_case("archive-wrapped-triage", [ARCH_TRIAGE_TAGS])),
        ("lane-closes-after-records: own_session_read reads no record when the closing nonce differs",
         own_read_case("archive-wrapped-nonce-close", [None])),
        ("lane-closes-after-records: own_session_read reads no record when the wrapper has no closing tag",
         own_read_case("archive-wrapped-unclosed", [None])),
        ("lane-closes-after-records: own_session_read reads no record when text follows the JSON in the wrapper",
         own_read_case("archive-wrapped-trailing-text", [None])),
        ("lane-closes-after-records: own_session_read reads no forged triage record from the JSON title",
         own_read_case("archive-wrapped-forged-title", [None, ARCH_LANE_TAGS])),
        ("lane-closes-after-records: own_session_read reads no forged triage record written as raw text",
         own_read_case("archive-wrapped-forged-text", [None, ARCH_LANE_TAGS])),
        ("lane-closes-after-records: own_session_read skips a get_session result with no content, and reads on",
         own_read_case("body-missing-then-lane", [ARCH_LANE_TAGS])),
        ("lane-closes-after-records: own_session_read skips a get_session result with no content, reads no record",
         own_read_case("body-missing", [None])),
        ("lane-closes-after-records: own_session_read skips a get_session result whose content is a dict, and reads on",
         own_read_case("body-dict-then-lane", [ARCH_LANE_TAGS])),
        ("lane-closes-after-records: own_session_read skips a get_session result whose content is a dict, reads no record",
         own_read_case("body-dict", [None])),
        ("lane-closes-after-records: own_session_read skips a get_session result whose content is an int, and reads on",
         own_read_case("body-int-then-lane", [ARCH_LANE_TAGS])),
        ("lane-closes-after-records: own_session_read skips a get_session result whose content is an int, reads no record",
         own_read_case("body-int", [None]))):
    LOG_CHECKS_EXTRA.append((_label, _check))


# The agent's own transcript folder has one home (rule agent-transcript-path-one-home): own_session's agent_transcript_dir,
# The agent folder beside the transcript: <transcript minus .jsonl>/subagents/agent-<id>.jsonl. The copies in hooks/guard_kill.py and hooks/stall_watch.py must name that folder.
# The copies in lint/report_guard.py and lint/ruling_census.py are pinned in their own suites.
AGENT_HOME_ID = "ab12cd34ef56a7890"  # an agent id as the harness sends it: 17 hex characters


def load_hook(name, file_name):
    """A hooks module beside the guard under test (GUARD), loaded by path, so a mutant copy of the guard reads its own copy."""
    import importlib.util
    hooks = os.path.dirname(GUARD)
    if hooks not in sys.path:
        sys.path.insert(0, hooks)  # guard_kill imports its siblings by name
    spec = importlib.util.spec_from_file_location(name, os.path.join(hooks, file_name))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def agent_home_shape_check():
    """agent_transcript_dir names the agent folder beside the transcript, for a transcript path with .jsonl, without it, and dotted."""
    own = _load_own_session()
    if not hasattr(own, "agent_transcript_dir"):
        return False, "own_session has no agent_transcript_dir: the one home of the agent folder is not built"
    base = os.path.join(ROOT, "agenthome")
    for name in ("sess.jsonl", "sess", "sess.v2"):
        got = own.agent_transcript_dir(os.path.join(base, name))
        want = os.path.join(base, name[:-len(".jsonl")] if name.endswith(".jsonl") else name, "subagents")
        if got != want:
            return False, "agent_transcript_dir(%s) is %s, want %s" % (name, got, want)
    return True, "agent_transcript_dir names the agent folder beside the transcript for each shape"


def agent_path_check():
    """agent_transcript_path is the agent's file in the home folder."""
    own = _load_own_session()
    if not hasattr(own, "agent_transcript_dir"):
        return False, "own_session has no agent_transcript_dir: agent_transcript_path has no home to build on"
    transcript = os.path.join(ROOT, "agenthome", "sess.jsonl")
    got = own.agent_transcript_path(transcript, AGENT_HOME_ID)
    want = os.path.join(own.agent_transcript_dir(transcript), "agent-" + AGENT_HOME_ID + ".jsonl")
    if got != want:
        return False, "agent_transcript_path is %s, want %s" % (got, want)
    return True, "agent_transcript_path is the agent's file in the home folder"


def agent_kill_finds_check():
    """in_own_agent_worktree finds the agent file beside a .jsonl transcript, for a pid whose parent is init in its worktree."""
    kill = load_hook("guard_kill_home_check", "guard_kill.py")
    base = os.path.join(ROOT, "agenthome-kill")
    transcript = os.path.join(base, "live.jsonl")
    write(transcript, "{}\n")
    write(os.path.join(base, "live", "subagents", "agent-" + AGENT_HOME_ID + ".jsonl"), "{}\n")
    cwd = os.path.join(base, ".claude", "worktrees", "agent-" + AGENT_HOME_ID)
    kill._ps_ppid = lambda pid: 1  # a pid whose parent is init
    kill._pid_cwd = lambda pid: cwd  # a cwd inside this agent's worktree
    if not kill.in_own_agent_worktree(4242, transcript):
        return False, "in_own_agent_worktree does not find the agent file beside the transcript"
    return True, "in_own_agent_worktree finds the agent file beside the transcript"


def agent_stall_finds_check():
    """agent_transcripts lists the agent file beside the session first."""
    stall = load_hook("stall_watch_home_check", "stall_watch.py")
    base = os.path.join(ROOT, "agenthome-stall")
    got = stall.agent_transcripts(os.path.join(base, "sess.jsonl"), AGENT_HOME_ID, "")[:1]
    want = [os.path.join(base, "sess", "subagents", "agent-" + AGENT_HOME_ID + ".jsonl")]
    if got != want:
        return False, "agent_transcripts lists %r first, want %r" % (got, want)
    return True, "agent_transcripts lists the agent file beside the session first"


def agent_copies_agree_check():
    """The stall_watch and guard_kill copies name the agent folder beside the transcript, for each transcript shape."""
    own = _load_own_session()
    stall = load_hook("stall_watch_home_agree", "stall_watch.py")
    kill = load_hook("guard_kill_home_agree", "guard_kill.py")
    base = os.path.join(ROOT, "agenthome-agree")
    for name in ("sess.jsonl", "sess", "sess.v2"):
        transcript = os.path.join(base, name)
        stem = name[:-len(".jsonl")] if name.endswith(".jsonl") else name
        agent_file = os.path.join(base, stem, "subagents", "agent-" + AGENT_HOME_ID + ".jsonl")
        write(agent_file, "{}\n")
        got = stall.agent_transcripts(transcript, AGENT_HOME_ID, "")[0]
        if got != agent_file:
            return False, "agent_transcripts names %s for %s, want %s" % (got, name, agent_file)
    if not hasattr(own, "agent_transcript_dir"):
        return False, "own_session has no agent_transcript_dir: the copies have no home to agree with"
    jsonl = os.path.join(base, "sess.jsonl")  # guard_kill reads a transcript that ends in .jsonl, by its own gate
    kill._ps_ppid = lambda pid: 1
    kill._pid_cwd = lambda pid: os.path.join(base, ".claude", "worktrees", "agent-" + AGENT_HOME_ID)
    if not kill.in_own_agent_worktree(4242, jsonl):
        return False, "in_own_agent_worktree finds no agent file in the folder beside sess.jsonl"
    return True, "the stall_watch and guard_kill copies name the home's folder for each shape"


for _label, _check in (
        ("agent-transcript-path-one-home: agent_transcript_dir names the agent folder beside the transcript, with or without .jsonl",
         agent_home_shape_check),
        ("agent-transcript-path-one-home: agent_transcript_path is the agent's file in the home folder",
         agent_path_check),
        ("agent-transcript-path-one-home: guard_kill finds the agent file beside a .jsonl transcript",
         agent_kill_finds_check),
        ("agent-transcript-path-one-home: stall_watch lists the agent file beside the session first",
         agent_stall_finds_check),
        ("agent-transcript-path-one-home: the stall_watch and guard_kill copies name the home's folder for each shape",
         agent_copies_agree_check)):
    LOG_CHECKS_EXTRA.append((_label, _check))


def _still_open(fd):
    """True while this process holds `fd` open."""
    try:
        os.fstat(fd)
    except OSError:
        return False
    return True


def own_ccr_unreadable_case():
    """A check: own_session_ccr returns None, and does not raise, for each input it cannot read, and it leaves
    the descriptor an int path names open. The lane fixture must hold the own record first, or the non-string
    id proves nothing."""
    missing = os.path.join(ROLE_DIR, "no-such-transcript.jsonl")
    folder = role_path("unreadable")
    lane = role_path("archive-lane")
    deep = role_path("body-deep")
    if os.path.exists(missing) or not os.path.isdir(folder) or not os.path.isfile(lane) or not os.path.isfile(deep):
        return False, "fixture: the missing path, the folder, the lane or the deep transcript is not as the case needs"
    try:
        module = _load_own_session()
        if module.own_session_ccr(lane, ROLE_OTHER) is None:
            return False, "fixture: the lane transcript holds no own record for a string id"
    except Exception as error:
        return False, "own_session_ccr raises %s on the readable lane transcript: %s" % (type(error).__name__, error)
    with tempfile.NamedTemporaryFile(dir=ROOT) as temp:
        live = os.dup(temp.fileno())  # a live descriptor of this run, named by the int path
    try:
        # The int path goes first: it is the input that can close a descriptor, so its check reads the
        # descriptor before any other input opens a file.
        inputs = (
            ("an int path", live, ROLE_OTHER),
            ("the empty path", "", ROLE_OTHER),
            ("a path that does not exist", missing, ROLE_OTHER),
            ("a path that is a folder", folder, ROLE_OTHER),
            ("a None path", None, ROLE_OTHER),
            ("a target id that is not a string", lane, 3),
            ("a record nested too deep to parse", deep, ROLE_OTHER),
        )
        for label, transcript, own_id in inputs:
            try:
                got = module.own_session_ccr(transcript, own_id)
            except Exception as error:
                return False, "own_session_ccr raises %s for %s: %s" % (type(error).__name__, label, error)
            if got is not None:
                return False, "own_session_ccr returns a record for %s, want None" % label
            if not _still_open(live):
                return False, "own_session_ccr closes the descriptor named by %s, want it left open" % label
        return True, ("own_session_ccr returns None, without a raise, for all %d unreadable inputs, "
                      "and leaves the int path's descriptor open" % len(inputs))
    finally:
        if _still_open(live):
            os.close(live)


LOG_CHECKS_EXTRA.append(("lane-closes-after-records: own_session_ccr returns None, without a raise, for each input it cannot read",
                         own_ccr_unreadable_case))
