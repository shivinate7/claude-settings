# section 33527
FAMILY = "session-home"
SH_AGENT = "shomeagent0f1e2d3c"  # an agent id in the shape AGENT_ID accepts


def sh_session():
    """A session id in the shape SESSION_ID_RE accepts, unique to one case."""
    return "shome-" + uuid.uuid4().hex


def sh_new_primary(name):
    """A primary checkout of its own, with one commit, under this run's folder."""
    primary = os.path.join(ROOT, "shome_" + name)
    make_repo(primary, {"src/app.py": "print(1)\n"})
    return primary


def sh_add_lane(primary, name):
    """A linked worktree at `.claude/worktrees/<name>`, the shape the harness makes. Returns
    (folder, branch)."""
    lane = os.path.join(primary, ".claude", "worktrees", name)
    branch = "shome-" + name
    made = run_vcs(primary, "worktree", "add", "-q", lane, "-b", branch)
    if made.returncode != 0:
        sys.exit("fixture setup failed: the worktree add at %r: %s" % (lane, made.stderr.strip()))
    return lane, branch


def sh_lose_lane(primary, lane, branch):
    """The harness removes a worktree's folder and its branch together."""
    run_vcs(primary, "worktree", "remove", "--force", lane)
    run_vcs(primary, "branch", "-D", branch)


def sh_record(primary, session):
    return os.path.join(primary, ".git", "session-homes", session)


def sh_holds(primary, session, folder):
    """True when the session's record names `folder`, compared through realpath. A missing or
    empty record holds nothing."""
    try:
        with open(sh_record(primary, session), encoding="utf-8") as handle:
            text = handle.read().strip()
    except OSError:
        return False
    return bool(text) and os.path.realpath(text) == os.path.realpath(folder)


def sh_refusal_problems(label, got, reason, primary, lost):
    """What a session-home refusal holds: the rule's name and the EnterWorktree tool. It never
    names a path: not the primary, not the lost folder, not the `.claude` folder."""
    if got != "deny":
        return ["%s: want deny, got %s (%s)" % (label, got, reason[:120])]
    problems = []
    if "session-home" not in reason or "EnterWorktree" not in reason:
        problems.append("%s: the refusal must name session-home and EnterWorktree: %s"
                        % (label, reason[:160]))
    for text in (primary, slash(primary), lost, slash(lost), ".claude"):
        if text in reason:
            problems.append("%s: the refusal names %r" % (label, text))
    return problems


def session_home_lost_refuses_case():
    """Rule session-home: a session whose worktree is gone is refused a write into the primary
    checkout, by Write, Edit, MultiEdit, NotebookEdit and a shell write. The refusal names
    EnterWorktree with a `name` and no `path`, and names no file path. The lane call that makes
    the record is checked first."""
    primary = sh_new_primary("lost")
    lane, branch = sh_add_lane(primary, "lane-lost")
    session = sh_session()
    problems = []
    got, reason = _decide_full("Bash", lane, session=session, command="echo hi")
    if got != "allow":
        problems.append("the lane call: want allow, got %s (%s)" % (got, reason[:120]))
    if not sh_holds(primary, session, lane):
        problems.append("the lane call wrote no session record naming the lane")
    sh_lose_lane(primary, lane, branch)
    src = os.path.join(primary, "src", "app.py")
    rows = (
        ("Write", {"file_path": src, "content": "x"}),
        ("Edit", {"file_path": src, "old_string": "1", "new_string": "2"}),
        ("MultiEdit", {"file_path": src, "edits": [{"old_string": "1", "new_string": "2"}]}),
        ("NotebookEdit", {"notebook_path": os.path.join(primary, "nb.ipynb"), "new_source": "x"}),
        ("Bash", {"command": "echo x > f.txt"}),
        ("Bash", {"command": "echo x > " + slash(os.path.join(primary, "f.txt"))}),
    )
    for index, (tool, tool_input) in enumerate(rows):
        got, reason = _decide_full(tool, primary, session=session, **tool_input)
        problems += sh_refusal_problems("row %d, %s" % (index, tool), got, reason, primary, lane)
        if ENTER_WORKTREE_SHAPE not in reason:
            problems.append("row %d, %s: the refusal does not say %s"
                            % (index, tool, ENTER_WORKTREE_SHAPE))
    if problems:
        return False, "; ".join(problems)
    return True, "every write tool and shell write is refused, naming session-home, EnterWorktree and its shape"


def session_home_present_folder_passes_case():
    """A session whose worktree folder is still there may write into the primary checkout. The
    record is checked first, so the pass is the record's doing, not a missing record's."""
    primary = sh_new_primary("present")
    lane, _ = sh_add_lane(primary, "lane-present")
    session = sh_session()
    problems = []
    _decide_full("Bash", lane, session=session, command="echo hi")
    if not sh_holds(primary, session, lane):
        problems.append("the lane call wrote no session record naming the lane")
    got, reason = _decide_full("Write", primary, session=session,
                               file_path=os.path.join(primary, "src", "app.py"), content="x")
    if got != "allow":
        problems.append("the primary Write with the folder present: want allow, got %s (%s)"
                        % (got, reason[:120]))
    got, reason = _decide_full("Bash", primary, session=session, command="echo x > f.txt")
    if got != "allow":
        problems.append("the primary shell write with the folder present: want allow, got %s (%s)"
                        % (got, reason[:120]))
    if problems:
        return False, "; ".join(problems)
    return True, "the primary checkout is writable while the recorded folder stands"


def session_home_fresh_session_passes_case():
    """Pinned: a session with no record, which never had a worktree, writes into the primary
    checkout, and a primary call writes no record."""
    primary = sh_new_primary("fresh")
    session = sh_session()
    src = os.path.join(primary, "src", "app.py")
    problems = []
    got, reason = _decide_full("Write", primary, session=session, file_path=src, content="x")
    if got != "allow":
        problems.append("the primary Write: want allow, got %s (%s)" % (got, reason[:120]))
    got, reason = _decide_full("Bash", primary, session=session, command="echo x > f.txt")
    if got != "allow":
        problems.append("the primary shell write: want allow, got %s (%s)" % (got, reason[:120]))
    if os.path.exists(sh_record(primary, session)):
        problems.append("a primary call wrote a session record")
    if problems:
        return False, "; ".join(problems)
    return True, "a session with no record writes into the primary checkout and writes no record"


def session_home_other_sessions_pass_case():
    """Records are per session. Another session's lost record refuses that session only. A session
    that never had a worktree, and a session whose record file is empty, both write into the
    primary checkout."""
    primary = sh_new_primary("other")
    lane, branch = sh_add_lane(primary, "lane-other")
    lost_for = sh_session()
    src = os.path.join(primary, "src", "app.py")
    problems = []
    _decide_full("Bash", lane, session=lost_for, command="echo hi")
    if not sh_holds(primary, lost_for, lane):
        problems.append("the lane call wrote no session record naming the lane")
    sh_lose_lane(primary, lane, branch)
    got, reason = _decide_full("Write", primary, session=lost_for, file_path=src, content="x")
    problems += sh_refusal_problems("the session that lost its worktree", got, reason, primary, lane)
    never = sh_session()
    got, reason = _decide_full("Write", primary, session=never, file_path=src, content="x")
    if got != "allow":
        problems.append("a session that never had a worktree: want allow, got %s (%s)"
                        % (got, reason[:120]))
    empty = sh_session()
    write(sh_record(primary, empty), "")  # a record that names no folder
    got, reason = _decide_full("Write", primary, session=empty, file_path=src, content="x")
    if got != "allow":
        problems.append("a session whose record is empty: want allow, got %s (%s)"
                        % (got, reason[:120]))
    if problems:
        return False, "; ".join(problems)
    return True, "the lost session is refused; a session with no record or an empty one passes"


def session_home_agent_call_writes_no_record_case():
    """An agent shares its session's id, so an agent call never writes or rewrites the session's
    record. A lost record never refuses an agent's call from the primary checkout."""
    primary = sh_new_primary("agent")
    agent_lane, _ = sh_add_lane(primary, "agent-" + SH_AGENT)
    lane, lane_branch = sh_add_lane(primary, "lane-agent")
    session = sh_session()
    problems = []
    got, reason = _decide_full("Bash", agent_lane, session=session, agent_id=SH_AGENT,
                               command="echo hi")
    if got != "allow":
        problems.append("an agent call from its own worktree: want allow, got %s (%s)"
                        % (got, reason[:120]))
    if os.path.exists(sh_record(primary, session)):
        problems.append("an agent call wrote the session record")
    _decide_full("Bash", lane, session=session, command="echo hi")
    if not sh_holds(primary, session, lane):
        problems.append("the top-level call from the lane wrote no session record naming it")
    _decide_full("Bash", agent_lane, session=session, agent_id=SH_AGENT, command="echo hi")
    if not sh_holds(primary, session, lane):
        problems.append("after an agent call the session record no longer names the lane")
    sh_lose_lane(primary, lane, lane_branch)
    got, reason = _decide_full("Write", primary, session=session, agent_id=SH_AGENT,
                               file_path=os.path.join(primary, "src", "app.py"), content="x")
    if "session-home" in reason:
        problems.append("an agent's Write from the primary checkout was refused as session-home: %s"
                        % reason[:120])
    if problems:
        return False, "; ".join(problems)
    return True, "an agent call neither writes nor rewrites the session record, nor is refused by it"


def session_home_new_worktree_rewrites_case():
    """After a lost worktree, a call from a new worktree rewrites the session's record to name it.
    The primary write then follows the record's folder: allowed while that folder stands, refused
    once it is gone."""
    primary = sh_new_primary("rewrite")
    old, old_branch = sh_add_lane(primary, "lane-old")
    session = sh_session()
    src = os.path.join(primary, "src", "app.py")
    problems = []
    _decide_full("Bash", old, session=session, command="echo hi")
    sh_lose_lane(primary, old, old_branch)
    got, reason = _decide_full("Write", primary, session=session, file_path=src, content="x")
    problems += sh_refusal_problems("the primary Write after the first loss", got, reason,
                                    primary, old)
    new, new_branch = sh_add_lane(primary, "lane-new")
    got, reason = _decide_full("Write", new, session=session,
                               file_path=os.path.join(new, "src", "new.py"), content="x")
    if got != "allow":
        problems.append("a write inside the new worktree: want allow, got %s (%s)"
                        % (got, reason[:120]))
    if not sh_holds(primary, session, new):
        problems.append("the call from the new worktree did not rewrite the record to name it")
    got, reason = _decide_full("Write", primary, session=session, file_path=src, content="x")
    if got != "allow":
        problems.append("the primary Write while the new worktree stands: want allow, got %s (%s)"
                        % (got, reason[:120]))
    sh_lose_lane(primary, new, new_branch)
    got, reason = _decide_full("Write", primary, session=session, file_path=src, content="x")
    problems += sh_refusal_problems("the primary Write after the second loss", got, reason,
                                    primary, new)
    if problems:
        return False, "; ".join(problems)
    return True, "the record follows the newest worktree, and the primary write follows the record"


def session_home_exit_worktree_clears_case():
    """ExitWorktree from a session's live lane deletes its record, so the primary checkout is writable
    again. The clear is the live lane's: an ExitWorktree from the primary leaves the record in place,
    see session_home_exit_from_primary_case. An agent's ExitWorktree shares the session's id, so it
    leaves the record in place too."""
    primary = sh_new_primary("exit")
    lane, branch = sh_add_lane(primary, "lane-exit")
    session = sh_session()
    src = os.path.join(primary, "src", "app.py")
    problems = []
    _decide_full("Bash", lane, session=session, command="echo hi")
    if not sh_holds(primary, session, lane):
        problems.append("the lane call wrote no session record naming the lane")
    got, reason = _decide_full("ExitWorktree", lane, session=session, agent_id=SH_AGENT)
    if got != "allow":
        problems.append("an agent's ExitWorktree: want allow, got %s (%s)" % (got, reason[:120]))
    if not sh_holds(primary, session, lane):
        problems.append("after an agent's ExitWorktree the session record no longer names the lane")
    got, reason = _decide_full("ExitWorktree", lane, session=session)
    if got != "allow":
        problems.append("the session's ExitWorktree: want allow, got %s (%s)" % (got, reason[:120]))
    if os.path.exists(sh_record(primary, session)):
        problems.append("the session's ExitWorktree left its record")
    sh_lose_lane(primary, lane, branch)
    got, reason = _decide_full("Write", primary, session=session, file_path=src, content="x")
    if got != "allow":
        problems.append("the primary Write after ExitWorktree: want allow, got %s (%s)"
                        % (got, reason[:120]))
    if problems:
        return False, "; ".join(problems)
    return True, "ExitWorktree from the session clears the record; an agent's leaves it"


def session_home_pass_through_case():
    """While a session's worktree is gone, its writes into the clone's .git and into a folder in
    no checkout still pass, and so does every read and every non-writing shell call. Only a write
    into the primary's own files is refused. The refusal is checked first."""
    primary = sh_new_primary("pass")
    lane, branch = sh_add_lane(primary, "lane-pass")
    session = sh_session()
    src = os.path.join(primary, "src", "app.py")
    exclude = os.path.join(primary, ".git", "info", "exclude")
    scratch = os.path.join(ROOT, "shome_scratch", "note.txt")
    _decide_full("Bash", lane, session=session, command="echo hi")
    sh_lose_lane(primary, lane, branch)
    problems = []
    got, reason = _decide_full("Write", primary, session=session, file_path=src, content="x")
    problems += sh_refusal_problems("the control: the primary Write", got, reason, primary, lane)
    rows = (
        ("Write into the clone's .git", "Write", {"file_path": exclude, "content": "x"}),
        ("Write to a folder in no checkout", "Write", {"file_path": scratch, "content": "x"}),
        ("shell append into the clone's .git", "Bash", {"command": "echo x >> " + slash(exclude)}),
        ("shell git fetch of main", "Bash", {"command": VCS + " fetch origin main"}),
        ("shell git status", "Bash", {"command": VCS + " status"}),
        ("shell cat of a primary file", "Bash", {"command": "cat " + slash(src)}),
        ("Read of a primary file", "Read", {"file_path": src}),
        ("Grep of the primary checkout", "Grep", {"pattern": "x", "path": primary}),
    )
    for label, tool, tool_input in rows:
        got, reason = _decide_full(tool, primary, session=session, **tool_input)
        if got != "allow":
            problems.append("%s: want allow, got %s (%s)" % (label, got, reason[:120]))
    # The refusal is for a call whose cwd is the primary checkout. A call from another live linked
    # worktree is judged by the other rules alone. This check runs last: its own call from a
    # `.claude/worktrees/<name>` folder rewrites the record to name that live folder.
    live, _ = sh_add_lane(primary, "lane-live")
    got, reason = _decide_full("Write", live, session=session,
                               file_path=os.path.join(live, "src", "new.py"), content="x")
    if got != "allow":
        problems.append("a write from another live worktree: want allow, got %s (%s)"
                        % (got, reason[:120]))
    if problems:
        return False, "; ".join(problems)
    return True, "the control is refused; .git, a scratch folder, fetch, status, reads and a live worktree pass"


def session_home_owner_override_lifts_case():
    """session-home is liftable: the owner may mean the write. It is refused before a timed
    override and allowed under it. It is not in never_lifted, so the override reaches it."""
    config = ov_config("session-home")
    primary = sh_new_primary("override")
    lane, branch = sh_add_lane(primary, "lane-override")
    session = sh_session()
    ov_call("Bash", {"command": "echo hi"}, lane, config, session, 0)  # records the lane
    sh_lose_lane(primary, lane, branch)
    src = os.path.join(primary, "src", "app.py")
    call = lambda s: ov_call("Write", {"file_path": src, "content": "x"}, primary, config,
                             session, s)
    problem = ov_want(*call(0), "deny", "session-home")
    if problem:
        return False, "before the override: " + problem
    note = ov_type(config, session, "override 15m", 30)
    ok, why = ov_story([("under a timed override", lambda: call(60), "allow", "session-home")], note)
    return ok, why or "refused before the override, lifted under it"


def session_home_spawn_cost_case():
    """The record and the refusal add no git read to the same call made with no session. Each
    check compares the two, so the other rules' reads cancel out: the record write adds none, a
    refused primary write adds no more than the same write would, and a non-writing shell call
    adds none. A stand-in git on PATH logs each spawn."""
    if os.name == "nt":
        return SKIP, "skipped: a stand-in git is not reached through CreateProcess"
    real = shutil.which(VCS)
    if not real:
        return False, "no git on PATH"
    primary = sh_new_primary("cost")
    lane, branch = sh_add_lane(primary, "lane-cost")
    folder = os.path.join(ROOT, "shome_cost_bin")
    log = os.path.join(ROOT, "shome_cost_spawns.log")
    stand_in = os.path.join(folder, VCS)
    write(stand_in, "#!/bin/sh\nprintf '%%s\\n' \"$*\" >> '%s'\nexec '%s' \"$@\"\n" % (log, real))
    os.chmod(stand_in, 0o755)
    path = folder + os.pathsep + os.environ.get("PATH", "")

    def counted(tool, cwd, session, **tool_input):
        """(decision, reason, git spawns) for one guard call."""
        if os.path.exists(log):
            os.remove(log)
        got, reason = decide({
            "raw": None, "tool": tool, "cwd": cwd, "session": session, "env_path": path,
            "config": None, "agent_id": None, "tool_input": tool_input,
        })
        spawns = open(log, encoding="utf-8").read().splitlines() if os.path.exists(log) else []
        return got, reason, len(spawns)

    session = sh_session()
    src = os.path.join(primary, "src", "app.py")
    problems = []
    lane_write = {"file_path": os.path.join(lane, "src", "new.txt"), "content": "x"}
    got, reason, with_record = counted("Write", lane, session, **lane_write)
    _, _, without = counted("Write", lane, None, **lane_write)
    if got != "allow":
        problems.append("the lane write: want allow, got %s (%s)" % (got, reason[:120]))
    if not sh_holds(primary, session, lane):
        problems.append("the lane write wrote no session record naming the lane")
    if with_record < 1:  # other-checkout reads the worktree list on any write: no spawn means no stand-in
        problems.append("the stand-in git saw no spawn, so the counts below prove nothing")
    if with_record != without:
        problems.append("the record write spent %d git spawn(s), the same call with no session %d"
                        % (with_record, without))
    sh_lose_lane(primary, lane, branch)
    lost_got, lost_reason, lost_n = counted("Write", primary, session, file_path=src, content="x")
    _, _, free_n = counted("Write", primary, None, file_path=src, content="x")
    problems += sh_refusal_problems("the lost primary Write", lost_got, lost_reason, primary, lane)
    if lost_n > free_n:
        problems.append("the refused primary write spent %d git spawn(s), more than the same write "
                        "with no session %d" % (lost_n, free_n))
    status = {"command": VCS + " status"}
    _, _, status_with = counted("Bash", primary, session, **status)
    _, _, status_without = counted("Bash", primary, None, **status)
    if status_with != status_without:
        problems.append("a non-writing shell call spent %d git spawn(s), the same call with no "
                        "session %d" % (status_with, status_without))
    if problems:
        return False, "; ".join(problems)
    return True, "the record write, the refused write and a non-writing shell call add no git spawn"


def session_home_non_isolated_agent_case():
    """An agent with no worktree of its own (no agent-home record, cwd in the primary checkout) is
    not refused as session-home while the session's record is lost. Rule session-home judges only a
    call with no agent_id: an agent shares its session's id, so the session's lost record must not
    refuse a non-isolated agent's write into the primary. The session's own write is refused, which
    shows the record is live."""
    primary = sh_new_primary("nonisolated")
    lane, branch = sh_add_lane(primary, "lane-nonisolated")
    session = sh_session()
    agent = "shomenonisolated01"  # an agent id in the shape AGENT_ID accepts, with no worktree
    src = os.path.join(primary, "src", "app.py")
    problems = []
    _decide_full("Bash", lane, session=session, command="echo hi")
    if not sh_holds(primary, session, lane):
        problems.append("the lane call wrote no session record naming the lane")
    sh_lose_lane(primary, lane, branch)
    got, reason = _decide_full("Write", primary, session=session, file_path=src, content="x")
    problems += sh_refusal_problems("the session's own primary Write (control)", got, reason,
                                    primary, lane)
    got, reason = _decide_full("Write", primary, session=session, agent_id=agent, file_path=src,
                               content="x")
    if got != "allow":
        problems.append("a non-isolated agent's Write into the primary: want allow, got %s (%s)"
                        % (got, reason[:120]))
    got, reason = _decide_full("Bash", primary, session=session, agent_id=agent,
                               command="echo x > f.txt")
    if got != "allow":
        problems.append("a non-isolated agent's shell write into the primary: want allow, got %s (%s)"
                        % (got, reason[:120]))
    if problems:
        return False, "; ".join(problems)
    return True, "a non-isolated agent writes into the primary while the session's record is lost"


LOG_CHECKS_EXTRA.append(("session-home: a non-isolated agent, with no record of its own, writes into the "
                         "primary checkout while the session's record is lost",
                         session_home_non_isolated_agent_case))


def session_home_exit_from_primary_case():
    """Rule session-home: only an ExitWorktree whose cwd sits in the recorded, live worktree clears the
    record. From the primary checkout, with the recorded worktree lost, the record stays and the
    primary write stays refused."""
    primary = sh_new_primary("exitprim")
    lane, branch = sh_add_lane(primary, "lane-exitprim")
    session = sh_session()
    src = os.path.join(primary, "src", "app.py")
    problems = []
    _decide_full("Bash", lane, session=session, command="echo hi")
    if not sh_holds(primary, session, lane):
        problems.append("the lane call wrote no session record naming the lane")
    sh_lose_lane(primary, lane, branch)
    got, reason = _decide_full("ExitWorktree", primary, session=session)
    if got != "allow":
        problems.append("an ExitWorktree from the primary: want allow, got %s (%s)"
                        % (got, reason[:120]))
    if not sh_holds(primary, session, lane):
        problems.append("an ExitWorktree from the primary changed the lost session's record")
    got, reason = _decide_full("Write", primary, session=session, file_path=src, content="x")
    problems += sh_refusal_problems("the primary Write after that ExitWorktree", got, reason,
                                    primary, lane)
    if problems:
        return False, "; ".join(problems)
    return True, "an ExitWorktree from the primary leaves the lost record; the primary write stays refused"


def session_home_lost_home_path_case():
    """Rule session-home: a write to the lost home path, `.claude/worktrees/<name>/...`, would re-create
    the gone worktree by mistake, and is refused while the record is lost. A write into a different,
    live worktree is other-checkout's business: this case checks only that session-home does not name it."""
    primary = sh_new_primary("lostpath")
    lane, branch = sh_add_lane(primary, "lane-lostpath")
    session = sh_session()
    problems = []
    _decide_full("Bash", lane, session=session, command="echo hi")
    if not sh_holds(primary, session, lane):
        problems.append("the lane call wrote no session record naming the lane")
    sh_lose_lane(primary, lane, branch)
    live, _ = sh_add_lane(primary, "lane-livepath")
    got, reason = _decide_full("Write", primary, session=session,
                               file_path=os.path.join(lane, "x.ts"), content="x")
    problems += sh_refusal_problems("a Write to the lost home path", got, reason, primary, lane)
    got, reason = _decide_full("Write", primary, session=session,
                               file_path=os.path.join(live, "x.ts"), content="x")
    if "session-home" in reason:
        problems.append("a Write into the live worktree was named session-home: %s" % reason[:120])
    if problems:
        return False, "; ".join(problems)
    return True, "a write to the lost home path is refused; a live worktree write is not session-home's"


def session_home_git_verbs_case():
    """Rule session-home: while the record is lost, a git verb that changes the primary's files or
    branch is refused from the primary. A read, a fetch, a branch and a worktree add under
    `.claude/worktrees` pass. A commit run with -C into a live worktree is refused by other-checkout,
    not session-home, because that worktree is another checkout of the clone."""
    primary = sh_new_primary("verbs")
    lane, branch = sh_add_lane(primary, "lane-verbs")
    session = sh_session()
    problems = []
    _decide_full("Bash", lane, session=session, command="echo hi")
    if not sh_holds(primary, session, lane):
        problems.append("the lane call wrote no session record naming the lane")
    sh_lose_lane(primary, lane, branch)
    live, _ = sh_add_lane(primary, "lane-verbslive")
    for verb in ("checkout -b x", "switch main", "pull --ff-only", "merge origin/main", "commit -m x",
                 "reset --hard", "stash", "rebase origin/main", "restore f"):
        command = VCS + " " + verb
        got, reason = _decide_full("Bash", primary, session=session, command=command)
        problems += sh_refusal_problems(command, got, reason, primary, lane)
    for verb in ("fetch origin main", "status", "log", "diff", "worktree add .claude/worktrees/y origin/main",
                 "branch y"):
        command = VCS + " " + verb
        got, reason = _decide_full("Bash", primary, session=session, command=command)
        if got != "allow":
            problems.append("%s: want allow, got %s (%s)" % (command, got, reason[:120]))
    command = VCS + " -C " + slash(live) + " commit -m x"
    got, reason = _decide_full("Bash", primary, session=session, command=command)
    if got != "deny" or "other-checkout" not in reason:
        problems.append("%s: want deny by other-checkout, got %s (%s)" % (command, got, reason[:120]))
    if problems:
        return False, "; ".join(problems)
    return True, ("the primary's file and branch verbs are refused; reads, fetch, branch and worktree add pass; "
                  "a -C commit into a live worktree is refused by other-checkout")


LOG_CHECKS_EXTRA.append(("session-home: an ExitWorktree from the primary checkout leaves a lost session's "
                         "record in place, and the primary write stays refused", session_home_exit_from_primary_case))
LOG_CHECKS_EXTRA.append(("session-home: a write to the lost home path is refused; a write into a live "
                         "worktree is not named session-home", session_home_lost_home_path_case))
LOG_CHECKS_EXTRA.append(("session-home: while lost, git verbs that change the primary's files or branch are "
                         "refused; reads, fetch, branch and worktree add pass, and a live -C commit is other-checkout's",
                         session_home_git_verbs_case))


# sh_lost_lane sets up the state the stash cases below judge: a primary whose session has lost its
# worktree. The session's lane call writes its session record naming the lane, then the lane and its
# branch are removed, so the record names a folder that is gone. The session-home reader judges a stash
# call in that primary by its action word. `create` reads the tree and index and writes an unreachable
# commit with no entry, so it is allowed. `pop` and `drop` take or destroy an entry, so they stay refused.
def sh_lost_lane(name):
    """A primary whose session has lost its worktree. The session's lane call wrote its record, then
    the harness removed the lane and its branch. Returns (primary, session, lane, recorded): `recorded`
    is False when the lane call wrote no record naming the lane."""
    primary = sh_new_primary(name)
    lane, branch = sh_add_lane(primary, "lane-" + name)
    session = sh_session()
    _decide_full("Bash", lane, session=session, command="echo hi")
    recorded = sh_holds(primary, session, lane)
    sh_lose_lane(primary, lane, branch)
    return primary, session, lane, recorded


def session_home_stash_create_case():
    """Rule session-home: `git stash create` in the primary checkout of a session whose worktree is gone
    is allowed, with a real entry on the stack. It reads the stack and takes no entry."""
    primary, session, lane, recorded = sh_lost_lane("stashcreate")
    if not recorded:
        return False, "the lane call wrote no session record naming the lane"
    write(os.path.join(primary, "src", "app.py"), "print(2)\n")
    if run_vcs(primary, *IDENT, "stash", "push", "-m", "cases").returncode != 0:
        return False, "fixture setup failed: the stash push in the primary"
    command = VCS + " stash create"
    got, reason = _decide_full("Bash", primary, session=session, command=command)
    if got != "allow":
        return False, "%s: want allow, got %s (%s)" % (command, got, reason[:120])
    return True, "git stash create in the primary of a lost session is allowed"


def session_home_stash_take_case():
    """Rule session-home: while the record is lost, `git stash pop` and `git stash drop` in the primary
    checkout are refused, naming session-home and EnterWorktree. A take and a drop are the stack's own
    acts, so the create allowance does not reach them."""
    primary, session, lane, recorded = sh_lost_lane("stashtake")
    if not recorded:
        return False, "the lane call wrote no session record naming the lane"
    problems = []
    for verb in ("pop", "drop"):
        command = VCS + " stash " + verb
        got, reason = _decide_full("Bash", primary, session=session, command=command)
        problems += sh_refusal_problems(command, got, reason, primary, lane)
    if problems:
        return False, "; ".join(problems)
    return True, "git stash pop and drop in the primary of a lost session stay refused, naming session-home"


def session_home_stash_agent_case():
    """Rule session-home: an agent's `git stash create` from the primary of a lost session is allowed.
    The rule judges a top-level call only, so the agent's call is not refused by it."""
    primary, session, lane, recorded = sh_lost_lane("stashagent")
    if not recorded:
        return False, "the lane call wrote no session record naming the lane"
    command = VCS + " stash create"
    got, reason = _decide_full("Bash", primary, agent_id=SH_AGENT, session=session, command=command)
    if got != "allow":
        return False, "%s from an agent: want allow, got %s (%s)" % (command, got, reason[:120])
    return True, "an agent's git stash create from the primary of a lost session is allowed"


def session_home_stash_quiet_pop_case():
    """Rule session-home: `git stash -q pop` in the primary of a lost session stays refused. The reader
    skips the -q option and reads `pop` as the action, so the option does not hide the take."""
    primary, session, lane, recorded = sh_lost_lane("stashquiet")
    if not recorded:
        return False, "the lane call wrote no session record naming the lane"
    command = VCS + " stash -q pop"
    got, reason = _decide_full("Bash", primary, session=session, command=command)
    problems = sh_refusal_problems(command, got, reason, primary, lane)
    if problems:
        return False, "; ".join(problems)
    return True, "git stash -q pop in the primary of a lost session stays refused, naming session-home"


def session_home_stash_help_case():
    """Rule session-home: a sole `git stash -h` in the primary of a lost session is allowed. The help
    flag prints usage and reads nothing, so the call is a read."""
    primary, session, lane, recorded = sh_lost_lane("stashhelp")
    if not recorded:
        return False, "the lane call wrote no session record naming the lane"
    command = VCS + " stash -h"
    got, reason = _decide_full("Bash", primary, session=session, command=command)
    if got != "allow":
        return False, "%s: want allow, got %s (%s)" % (command, got, reason[:120])
    return True, "git stash -h in the primary of a lost session is allowed"


LOG_CHECKS_EXTRA.append(("session-home: git stash create from the primary of a lost session is allowed",
                         session_home_stash_create_case))
LOG_CHECKS_EXTRA.append(("session-home: git stash pop and drop in the primary of a lost session stay refused, "
                         "naming session-home and EnterWorktree", session_home_stash_take_case))
LOG_CHECKS_EXTRA.append(("session-home: an agent's git stash create from the primary of a lost session is "
                         "allowed; the rule judges top-level calls only", session_home_stash_agent_case))
LOG_CHECKS_EXTRA.append(("session-home: while lost, git stash -q pop in the primary is refused, naming "
                         "session-home and EnterWorktree", session_home_stash_quiet_pop_case))
LOG_CHECKS_EXTRA.append(("session-home: while lost, git stash -h in the primary is allowed as a read",
                         session_home_stash_help_case))


def session_home_clean_refuses_case():
    """Rule session-home: while the record is lost, `git clean -fd` in the primary checkout is
    refused, as `git reset --hard` is. The primary tree is clean, so the refusal is
    session-home's alone, not the shared-tree rule's."""
    primary = sh_new_primary("cleanrefuse")
    lane, branch = sh_add_lane(primary, "lane-cleanrefuse")
    session = sh_session()
    problems = []
    _decide_full("Bash", lane, session=session, command="echo hi")
    if not sh_holds(primary, session, lane):
        problems.append("the lane call wrote no session record naming the lane")
    sh_lose_lane(primary, lane, branch)
    command = VCS + " clean -fd"
    got, reason = _decide_full("Bash", primary, session=session, command=command)
    problems += sh_refusal_problems(command, got, reason, primary, lane)
    if problems:
        return False, "; ".join(problems)
    return True, "git clean -fd in the primary is refused, naming session-home and EnterWorktree"


def session_home_clean_reads_case():
    """Rule session-home: while the record is lost, `git clean -n` (a dry run that writes nothing)
    and `git status` in the primary checkout pass. The rule refuses a clean
    that deletes, so a list entry for clean must not refuse the dry run."""
    primary = sh_new_primary("cleanreads")
    lane, branch = sh_add_lane(primary, "lane-cleanreads")
    session = sh_session()
    problems = []
    _decide_full("Bash", lane, session=session, command="echo hi")
    if not sh_holds(primary, session, lane):
        problems.append("the lane call wrote no session record naming the lane")
    sh_lose_lane(primary, lane, branch)
    for command in (VCS + " clean -n", VCS + " status"):
        got, reason = _decide_full("Bash", primary, session=session, command=command)
        if got != "allow":
            problems.append("%s: want allow, got %s (%s)" % (command, got, reason[:120]))
    if problems:
        return False, "; ".join(problems)
    return True, "git clean -n and git status in the primary pass while the record is lost"


LOG_CHECKS_EXTRA.append(("looser-git-acts: session-home: while lost, git clean -fd in the primary is refused, "
                         "naming session-home and EnterWorktree", session_home_clean_refuses_case))
LOG_CHECKS_EXTRA.append(("looser-git-acts: session-home: while lost, git clean -n and git status in the primary "
                         "pass", session_home_clean_reads_case))


def session_home_agent_tree_inspect_case():
    """Rule session-home: a top-level call (no agent_id) whose cwd sits in an agent's worktree,
    `.claude/worktrees/agent-<id>`, is an orchestrator inspecting that tree. It writes no session
    record. Once that tree is removed, the primary checkout stays writable, and so does a git commit
    made there."""
    primary = sh_new_primary("inspect")
    tree, branch = sh_add_lane(primary, "agent-" + SH_AGENT)
    session = sh_session()
    src = os.path.join(primary, "src", "app.py")
    problems = []
    got, reason = _decide_full("Bash", tree, session=session, command="echo hi")
    if got != "allow":
        problems.append("the inspecting call: want allow, got %s (%s)" % (got, reason[:120]))
    if os.path.exists(sh_record(primary, session)):
        problems.append("a top-level call inside an agent's worktree wrote a session record")
    sh_lose_lane(primary, tree, branch)
    got, reason = _decide_full("Write", primary, session=session, file_path=src, content="x")
    if got != "allow":
        problems.append("the primary Write after the agent tree is removed: want allow, got %s (%s)"
                        % (got, reason[:120]))
    got, reason = _decide_full("Bash", primary, session=session, command=VCS + " commit -m x")
    if got != "allow":
        problems.append("the primary git commit after the agent tree is removed: want allow, got %s (%s)"
                        % (got, reason[:120]))
    if problems:
        return False, "; ".join(problems)
    return True, "an inspecting call writes no record; the primary write and commit pass after removal"


def session_home_exit_live_from_primary_case():
    """Rule session-home: an ExitWorktree from the primary checkout clears a record that names a live
    worktree. A record that names a lost worktree is kept, and the primary write stays refused."""
    primary = sh_new_primary("exitlive")
    live, live_branch = sh_add_lane(primary, "lane-exitlive")
    session = sh_session()
    src = os.path.join(primary, "src", "app.py")
    problems = []
    _decide_full("Bash", live, session=session, command="echo hi")
    if not sh_holds(primary, session, live):
        problems.append("the live lane call wrote no session record naming the lane")
    got, reason = _decide_full("ExitWorktree", primary, session=session)
    if got != "allow":
        problems.append("an ExitWorktree from the primary: want allow, got %s (%s)" % (got, reason[:120]))
    if os.path.exists(sh_record(primary, session)):
        problems.append("an ExitWorktree from the primary left the record naming a live worktree")
    sh_lose_lane(primary, live, live_branch)
    got, reason = _decide_full("Write", primary, session=session, file_path=src, content="x")
    if got != "allow":
        problems.append("the primary Write after the live lane is removed: want allow, got %s (%s)"
                        % (got, reason[:120]))
    lost, lost_branch = sh_add_lane(primary, "lane-exitlost")
    other = sh_session()
    _decide_full("Bash", lost, session=other, command="echo hi")
    if not sh_holds(primary, other, lost):
        problems.append("the lane call that is lost next wrote no session record naming the lane")
    sh_lose_lane(primary, lost, lost_branch)
    got, reason = _decide_full("ExitWorktree", primary, session=other)
    if got != "allow":
        problems.append("an ExitWorktree from the primary, lost record: want allow, got %s (%s)"
                        % (got, reason[:120]))
    if not sh_holds(primary, other, lost):
        problems.append("an ExitWorktree from the primary cleared a lost session's record")
    got, reason = _decide_full("Write", primary, session=other, file_path=src, content="x")
    problems += sh_refusal_problems("the primary Write for the lost session", got, reason,
                                    primary, lost)
    if problems:
        return False, "; ".join(problems)
    return True, "an ExitWorktree from the primary clears a live record and keeps a lost one"


def session_home_variable_folder_commit_case():
    """Rule session-home: while the record is lost, a git commit whose folder is a shell variable
    passes, both as `cd "$WT" && git commit` and as `git -C "$WT" commit`. The folder is unknown, and
    an unknown folder is no hit."""
    primary = sh_new_primary("varcommit")
    lane, branch = sh_add_lane(primary, "lane-varcommit")
    session = sh_session()
    problems = []
    _decide_full("Bash", lane, session=session, command="echo hi")
    if not sh_holds(primary, session, lane):
        problems.append("the lane call wrote no session record naming the lane")
    sh_lose_lane(primary, lane, branch)
    for command in ('cd "$WT" && ' + VCS + " commit -m x", VCS + ' -C "$WT" commit -m x'):
        got, reason = _decide_full("Bash", primary, session=session, command=command)
        if got != "allow":
            problems.append("%s: want allow, got %s (%s)" % (command, got, reason[:120]))
    if problems:
        return False, "; ".join(problems)
    return True, "a commit whose folder is a variable passes, by cd and by -C"


def session_home_variable_primary_case():
    """Rule session-home, a variable folder: while the record is lost, a git commit or a shell write into
    the primary checkout is refused when its folder comes from a variable (cd "$R") as from its path. The
    refusal names session-home and EnterWorktree, and names no path."""
    primary = sh_new_primary("varprimary")
    lane, branch = sh_add_lane(primary, "lane-varprimary")
    session = sh_session()
    problems = []
    _decide_full("Bash", lane, session=session, command="echo hi")
    if not sh_holds(primary, session, lane):
        problems.append("the lane call wrote no session record naming the lane")
    sh_lose_lane(primary, lane, branch)
    rows = (
        ("the literal folder, cd then a commit", "cd " + slash(primary) + " && " + VCS + " commit -m x"),
        ("a variable folder, cd \"$R\" then a commit",
         'R=' + slash(primary) + '; cd "$R" && ' + VCS + " commit -m x"),
        ("the literal folder, cd then a shell write", "cd " + slash(primary) + " && echo x > f.txt"),
        ("a variable folder, cd \"$R\" then a shell write",
         'R=' + slash(primary) + '; cd "$R" && echo x > f.txt'),
    )
    for label, command in rows:
        got, reason = _decide_full("Bash", primary, session=session, command=command)
        problems += sh_refusal_problems(label, got, reason, primary, lane)
    if problems:
        return False, "; ".join(problems)
    return True, "a commit or a shell write into the primary checkout by a variable folder is refused, as by a literal one"


LOG_CHECKS_EXTRA.append(("session-home: a commit or a shell write into the primary checkout by a variable "
                         "folder is refused, as by a literal folder", session_home_variable_primary_case))
LOG_CHECKS_EXTRA.append(("session-home: a top-level call inside an agent's worktree writes no session "
                         "record, and the primary write and commit pass once that tree is removed",
                         session_home_agent_tree_inspect_case))
LOG_CHECKS_EXTRA.append(("session-home: an ExitWorktree from the primary clears a record that names a "
                         "live worktree, and keeps a lost one", session_home_exit_live_from_primary_case))
LOG_CHECKS_EXTRA.append(("session-home: while lost, a commit whose folder is a shell variable passes, "
                         "by cd and by -C", session_home_variable_folder_commit_case))
LOG_CHECKS_EXTRA.append(("session-home: a session whose worktree is gone is refused a write into the "
                         "primary checkout, by each write tool and a shell write, naming EnterWorktree "
                         "and no path", session_home_lost_refuses_case))
LOG_CHECKS_EXTRA.append(("session-home: a session whose worktree folder stands writes into the primary "
                         "checkout", session_home_present_folder_passes_case))
LOG_CHECKS_EXTRA.append(("session-home: a fresh session with no record writes into the primary checkout "
                         "and writes no record", session_home_fresh_session_passes_case))
LOG_CHECKS_EXTRA.append(("session-home: records are per session; another session's lost record, or an "
                         "empty one, does not refuse this session", session_home_other_sessions_pass_case))
LOG_CHECKS_EXTRA.append(("session-home: an agent call writes and rewrites no session record, and is "
                         "never refused as session-home", session_home_agent_call_writes_no_record_case))
LOG_CHECKS_EXTRA.append(("session-home: a call from a new worktree rewrites the record, and the primary "
                         "write follows the record's folder", session_home_new_worktree_rewrites_case))
LOG_CHECKS_EXTRA.append(("session-home: the session's ExitWorktree clears its record, an agent's leaves it",
                         session_home_exit_worktree_clears_case))
LOG_CHECKS_EXTRA.append(("session-home: while lost, the clone's .git, a folder in no checkout, fetch, "
                         "status, reads and a live worktree pass; the primary write is refused",
                         session_home_pass_through_case))
LOG_CHECKS_EXTRA.append(("session-home: an owner override lifts the refusal, which stays out of "
                         "never_lifted", session_home_owner_override_lifts_case))
LOG_CHECKS_EXTRA.append(("session-home: the record and the refusal add no git spawn to the same call "
                         "with no session", session_home_spawn_cost_case))

# A lost session's write into the primary checkout is refused for a Monitor call as for its Bash twin. The
# record _build_gitmain seeded names MON_LOST, which is gone, so the one call is the whole case.
monitor("Monitor: a lost session's write into the primary checkout is refused as session-home",
        "echo x > f.txt", "deny", "session-home", cwd=GITMAIN, session=MON_SESSION)
sh("Bash twin of the Monitor case: a lost session's write into the primary checkout is refused as session-home",
   "echo x > f.txt", "deny", "session-home", cwd=GITMAIN, session=MON_SESSION)


# =========================================================================== scratchpad-owner
# Rule scratchpad-owner (decision an-agent-outside-its-home-tree-must-stop, the own-scratchpad
# exemption). Every agent of one session shares that session's scratchpad (note
# scratchpad-shared-per-session), so an agent can run a script that another agent of the session left
# there. At write time the guard records the agent_id that wrote each file under THIS session's
# scratchpad. At run time it asks when an agent runs such a file that a different agent recorded. The
# writer, a top-level call, a file with no record and a read all pass. Each case makes its guard calls
# in its own temp folder and its own session, so one case's record never reaches another case.
