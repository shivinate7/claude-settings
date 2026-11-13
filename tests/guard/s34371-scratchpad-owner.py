# section 34371
FAMILY = "scratchpad-owner"
SPO_RULE = "scratchpad-owner"
SPO_WRITER = "spo-writer-01"   # an agent id in the shape AGENT_ID accepts
SPO_OTHER = "spo-other-02"
SPO_SLUG = "-home-user-claude-settings"   # the project folder the scratchpad sits under
PY_TEXT = "print(1)\n"
SH_TEXT = "echo hi\n"
SPO_NT = "skipped: these cases use POSIX shell forms and POSIX paths"


def spo_fixture(tag):
    """One case's folders under this run's folder: a temp folder the guard reads as TMPDIR, this
    session's scratchpad inside it (`<tmp>/<slug>/<session>/scratchpad`), and a working folder that
    sits in no checkout. The session id is new for each case."""
    folder = os.path.join(ROOT, "spo", tag)
    fx = {"tmp": os.path.join(folder, "tmp"), "sid": "spo-" + uuid.uuid4().hex,
          "work": os.path.join(folder, "work")}
    fx["scratch"] = os.path.join(fx["tmp"], SPO_SLUG, fx["sid"], "scratchpad")
    os.makedirs(fx["scratch"], exist_ok=True)
    os.makedirs(fx["work"], exist_ok=True)
    return fx


def spo_call(fx, tool, agent, **tool_input):
    """One guard call, as the harness sends it in this case: its session, its temp folder and its
    working folder. `agent` is None for the top-level session."""
    return _decide_full(tool, fx["work"], agent_id=agent, session=fx["sid"], temp=fx["tmp"],
                        **tool_input)


def spo_run(fx, agent, command):
    """One Bash call from `agent`, by its command text."""
    return spo_call(fx, "Bash", agent, command=command)


def spo_scope(fx, name, path):
    """Scope before subject: `path` lies inside this case's session scratchpad, by its real path."""
    if os.path.realpath(path).startswith(os.path.realpath(fx["scratch"]) + os.sep):
        return ""
    return "%s: scope, the fixture is not under this session's scratchpad" % name


def spo_wrote(fx, name, agent, path, text, tool="Write", command=None):
    """Agent `agent` makes `path`: its guard call first, then the file lands on disk, as the tool
    would write it. A refused call is a problem, since the record needs an allowed write."""
    if tool == "Write":
        got, reason = spo_call(fx, "Write", agent, file_path=path, content=text)
    else:
        got, reason = spo_call(fx, "Bash", agent, command=command)
    if got != "allow":
        return ["%s: setup, agent %s's write is %s, want allow (%s)"
                % (name, agent, got, reason[:100])]
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return []


def spo_allowed(name, got, reason):
    """A call the rule passes: the decision is allow."""
    if got == "allow":
        return ""
    return "%s: want allow, got %s (%s)" % (name, got, reason[:100])


def spo_refused(name, got, reason, banned):
    """A run or write the rule refuses: decision deny, the rule's id in the reason, and no path in it. The
    `banned` fragments are the scratchpad folder and the script's name, which the refusal never names."""
    if got != "deny":
        return "%s: want deny naming %s, got %s (%s)" % (name, SPO_RULE, got, reason[:100])
    if SPO_RULE not in reason:
        return "%s: the refusal does not name %s (%s)" % (name, SPO_RULE, reason[:100])
    if names_the_target(reason, SPO_RULE) or any(item in reason for item in banned):
        return "%s: the refusal names the scratchpad or the script" % name
    return ""


def spo_result(problems, passed):
    """(True, `passed`) when no problem holds, else (False, the problems joined)."""
    found = [p for p in problems if p]
    return (False, "; ".join(found)) if found else (True, passed)


def spo_snapshot(folder):
    """Every entry under `folder`, dotfiles included, with its size and mtime: any write shows."""
    seen = {}
    for dirpath, dirnames, filenames in os.walk(folder):
        for name in dirnames + filenames:
            path = os.path.join(dirpath, name)
            info = os.lstat(path)
            seen[os.path.relpath(path, folder)] = (info.st_size, info.st_mtime_ns)
    info = os.lstat(folder)
    seen["."] = (info.st_size, info.st_mtime_ns)
    return seen


def spo_case_1():
    """Agent A writes probe2.py with Write; agent B runs it with python3: refused."""
    fx = spo_fixture("c1")
    probe = os.path.join(fx["scratch"], "probe2.py")
    problems = [spo_scope(fx, "1", probe)] + spo_wrote(fx, "1", SPO_WRITER, probe, PY_TEXT)
    got, reason = spo_run(fx, SPO_OTHER, "python3 %s" % probe)
    problems.append(spo_refused("1", got, reason, (fx["scratch"], "probe2.py")))
    return spo_result(problems, "agent B's python3 run of agent A's script is refused")


def spo_case_2():
    """Agent A writes probe2.py with Write; agent B runs it after a cd into the scratchpad: refused."""
    fx = spo_fixture("c2")
    probe = os.path.join(fx["scratch"], "probe2.py")
    problems = [spo_scope(fx, "2", probe)] + spo_wrote(fx, "2", SPO_WRITER, probe, PY_TEXT)
    got, reason = spo_run(fx, SPO_OTHER, "cd %s && python3 probe2.py" % fx["scratch"])
    problems.append(spo_refused("2", got, reason, (fx["scratch"], "probe2.py")))
    return spo_result(problems, "agent B's cd and python3 run of agent A's script is refused")


def spo_case_3():
    """Agent A writes p.sh by a bash heredoc; agent B runs it through bash: refused."""
    fx = spo_fixture("c3")
    script = os.path.join(fx["scratch"], "p.sh")
    heredoc = "cat > %s <<'EOF'\n%sEOF" % (script, SH_TEXT)
    problems = [spo_scope(fx, "3", script)] + spo_wrote(
        fx, "3", SPO_WRITER, script, SH_TEXT, tool="Bash", command=heredoc)
    got, reason = spo_run(fx, SPO_OTHER, "bash %s" % script)
    problems.append(spo_refused("3", got, reason, (fx["scratch"], "p.sh")))
    return spo_result(problems, "agent B's bash run of agent A's heredoc script is refused")


def spo_case_4():
    """Agent A writes p.sh with Write; agent B runs it as the command word: refused."""
    fx = spo_fixture("c4")
    script = os.path.join(fx["scratch"], "p.sh")
    problems = [spo_scope(fx, "4", script)] + spo_wrote(fx, "4", SPO_WRITER, script, SH_TEXT)
    got, reason = spo_run(fx, SPO_OTHER, script)
    problems.append(spo_refused("4", got, reason, (fx["scratch"], "p.sh")))
    return spo_result(problems, "agent B's run of agent A's script by its path is refused")


def spo_case_5():
    """Agent A writes probe2.py with Write, then runs it itself: allowed."""
    fx = spo_fixture("c5")
    probe = os.path.join(fx["scratch"], "probe2.py")
    problems = [spo_scope(fx, "5", probe)] + spo_wrote(fx, "5", SPO_WRITER, probe, PY_TEXT)
    got, reason = spo_run(fx, SPO_WRITER, "python3 %s" % probe)
    problems.append(spo_allowed("5", got, reason))
    return spo_result(problems, "agent A runs its own script and is allowed")


def spo_case_6():
    """probe2.py is made outside the guard, so no record names it; agent B runs it: allowed."""
    fx = spo_fixture("c6")
    probe = os.path.join(fx["scratch"], "probe2.py")
    with open(probe, "w", encoding="utf-8") as handle:
        handle.write(PY_TEXT)
    problems = [spo_scope(fx, "6", probe)]
    got, reason = spo_run(fx, SPO_OTHER, "python3 %s" % probe)
    problems.append(spo_allowed("6", got, reason))
    return spo_result(problems, "agent B runs a script with no record and is allowed")


def spo_case_7():
    """Agent A writes probe2.py with Write; a top-level call with no agent_id runs it: allowed."""
    fx = spo_fixture("c7")
    probe = os.path.join(fx["scratch"], "probe2.py")
    problems = [spo_scope(fx, "7", probe)] + spo_wrote(fx, "7", SPO_WRITER, probe, PY_TEXT)
    got, reason = spo_run(fx, None, "python3 %s" % probe)
    problems.append(spo_allowed("7", got, reason))
    return spo_result(problems, "the top-level session runs agent A's script and is allowed")


def spo_case_8():
    """Agent A writes probe2.py with Write; agent B reads it with cat: allowed."""
    fx = spo_fixture("c8")
    probe = os.path.join(fx["scratch"], "probe2.py")
    problems = [spo_scope(fx, "8", probe)] + spo_wrote(fx, "8", SPO_WRITER, probe, PY_TEXT)
    got, reason = spo_run(fx, SPO_OTHER, "cat %s" % probe)
    problems.append(spo_allowed("8", got, reason))
    return spo_result(problems, "agent B reads agent A's script with cat and is allowed")


def spo_case_9():
    """Agent A's Write and its Bash redirect, both outside any scratchpad, create no file under this
    session's scratchpad: the scratchpad's entries, sizes and times are unchanged."""
    fx = spo_fixture("c9")
    seed = os.path.join(fx["scratch"], "notes.txt")
    with open(seed, "w", encoding="utf-8") as handle:
        handle.write("seed\n")
    before = spo_snapshot(fx["scratch"])
    outside = os.path.join(fx["work"], "outside")   # a folder in no scratchpad
    os.makedirs(outside, exist_ok=True)
    got, reason = spo_call(fx, "Write", SPO_WRITER,
                           file_path=os.path.join(outside, "out.txt"), content="x\n")
    problems = [spo_allowed("9a", got, reason)]
    got, reason = spo_run(fx, SPO_WRITER, "echo x > %s" % os.path.join(outside, "y.txt"))
    problems.append(spo_allowed("9b", got, reason))
    if spo_snapshot(fx["scratch"]) != before:
        problems.append("9: a write outside the scratchpad changed the scratchpad")
    return spo_result(problems, "agent writes outside any scratchpad leave the scratchpad unchanged")


def spo_case_10():
    """Full size: agent A writes forty scripts with Write, then agent B runs the oldest one: refused.
    The record must hold the early files as well as the late ones."""
    fx = spo_fixture("c10")
    problems = []
    for index in range(40):
        path = os.path.join(fx["scratch"], "part%02d.py" % index)
        problems += spo_wrote(fx, "10", SPO_WRITER, path, PY_TEXT)
        if problems:
            break
    oldest = os.path.join(fx["scratch"], "part00.py")
    problems.append(spo_scope(fx, "10", oldest))
    got, reason = spo_run(fx, SPO_OTHER, "python3 %s" % oldest)
    problems.append(spo_refused("10", got, reason, (fx["scratch"], "part00.py")))
    return spo_result(problems, "agent B's run of the oldest of forty agent A scripts is refused")


def spo_text_case(tag, name, command_of, passed):
    """Agent A writes probe2.py; agent B's call holds the run's text as quoted text, a comment, a heredoc
    body or a multi-line string, and runs nothing: allowed. `command_of(probe, outside)` builds the call."""
    fx = spo_fixture(tag)
    probe = os.path.join(fx["scratch"], "probe2.py")
    problems = [spo_scope(fx, name, probe)] + spo_wrote(fx, name, SPO_WRITER, probe, PY_TEXT)
    outside = os.path.join(fx["work"], "notes.txt")
    got, reason = spo_run(fx, SPO_OTHER, command_of(probe, outside))
    problems.append(spo_allowed(name, got, reason))
    return spo_result(problems, passed)


def spo_extra_quoted():
    return spo_text_case("x1", "extra-quoted", lambda probe, outside: "echo 'python3 %s'" % probe,
                         "a run inside single quotes is text and is allowed")


def spo_extra_comment():
    return spo_text_case("x2", "extra-comment", lambda probe, outside: "echo hi # python3 %s" % probe,
                         "a run after a comment mark is text and is allowed")


def spo_extra_heredoc():
    return spo_text_case("x3", "extra-heredoc",
                         lambda probe, outside: "cat > %s <<'EOF'\npython3 %s\nEOF" % (outside, probe),
                         "a run in a heredoc body is text and is allowed")


def spo_extra_apostrophe():
    return spo_text_case("x4", "extra-apostrophe",
                         lambda probe, outside: 'echo "don\'t" && cat %s' % probe,
                         "a lone apostrophe in double quotes does not hide the read and is allowed")


def spo_extra_multiline():
    return spo_text_case("x5", "extra-multiline",
                         lambda probe, outside: 'echo "first line\npython3 %s"' % probe,
                         "a run on the second line of a double-quoted string is text and is allowed")


def spo_register(label, check):
    """Register one scratchpad-owner check. Each check builds only its own folders, so a family run
    skips the fixture build. POSIX only: the cases use shell forms and POSIX paths."""
    def run():
        if os.name == "nt":
            return SKIP, SPO_NT
        return check()
    FIXTURELESS_CHECKS.add(run)
    LOG_CHECKS_EXTRA.append((label, run))


spo_register("scratchpad-owner: 1 agent B runs agent A's script with python3, after A wrote it with Write: refused",
             spo_case_1)
spo_register("scratchpad-owner: 2 agent B runs agent A's script after cd into the scratchpad: refused",
             spo_case_2)
spo_register("scratchpad-owner: 3 agent B runs agent A's script through bash, after A wrote it by a heredoc: refused",
             spo_case_3)
spo_register("scratchpad-owner: 4 agent B runs agent A's script as the command word: refused", spo_case_4)
spo_register("scratchpad-owner: 5 agent A runs its own script: allowed", spo_case_5)
spo_register("scratchpad-owner: 6 agent B runs a script with no record, made outside the guard: allowed",
             spo_case_6)
spo_register("scratchpad-owner: 7 a top-level call with no agent_id runs agent A's script: allowed",
             spo_case_7)
spo_register("scratchpad-owner: 8 agent B reads agent A's script with cat: allowed", spo_case_8)
spo_register("scratchpad-owner: 9 agent writes outside any scratchpad create no file under this session's "
             "scratchpad: allowed", spo_case_9)
spo_register("scratchpad-owner: 10 agent B runs the oldest of forty scripts agent A wrote: refused",
             spo_case_10)
spo_register("scratchpad-owner: extra, a run inside single quotes is text: allowed", spo_extra_quoted)
spo_register("scratchpad-owner: extra, a run after a comment mark is text: allowed", spo_extra_comment)
spo_register("scratchpad-owner: extra, a run in a heredoc body is text: allowed", spo_extra_heredoc)
spo_register("scratchpad-owner: extra, a lone apostrophe in double quotes does not hide a read: allowed",
             spo_extra_apostrophe)
spo_register("scratchpad-owner: extra, a run on the second line of a double-quoted string is text: allowed",
             spo_extra_multiline)


# Rule scratchpad-owner, the overwrite form: an agent with a valid agent_id that writes over a file under
# this session's scratchpad whose record names a different agent is refused. The writes are the ones the
# record covers: Write, and a shell write target (a redirect, a heredoc `cat > f`, or an append). The
# first write of a file, a rewrite by its own writer, a call with no agent_id and a read pass. Each case
# builds its own session, as the cases above do.


def ovw_case_1():
    """Agent A writes msg.txt with Write; agent B writes the same file with Write: refused."""
    fx = spo_fixture("o1")
    msg = os.path.join(fx["scratch"], "msg.txt")
    problems = [spo_scope(fx, "o1", msg)] + spo_wrote(fx, "o1", SPO_WRITER, msg, "from A\n")
    got, reason = spo_call(fx, "Write", SPO_OTHER, file_path=msg, content="from B\n")
    problems.append(spo_refused("o1", got, reason, (fx["scratch"], "msg.txt")))
    return spo_result(problems, "agent B's Write over agent A's file is refused")


def ovw_case_2():
    """Agent A writes msg.txt with Write; agent B redirects echo over it: refused."""
    fx = spo_fixture("o2")
    msg = os.path.join(fx["scratch"], "msg.txt")
    problems = [spo_scope(fx, "o2", msg)] + spo_wrote(fx, "o2", SPO_WRITER, msg, "from A\n")
    got, reason = spo_run(fx, SPO_OTHER, "echo x > %s" % msg)
    problems.append(spo_refused("o2", got, reason, (fx["scratch"], "msg.txt")))
    return spo_result(problems, "agent B's shell redirect over agent A's file is refused")


def ovw_case_3():
    """Agent A writes msg.txt with Write; agent B cds into the scratchpad and heredocs over it: refused."""
    fx = spo_fixture("o3")
    msg = os.path.join(fx["scratch"], "msg.txt")
    problems = [spo_scope(fx, "o3", msg)] + spo_wrote(fx, "o3", SPO_WRITER, msg, "from A\n")
    heredoc = "cd %s && cat > msg.txt <<'EOF'\nfrom B\nEOF" % fx["scratch"]
    got, reason = spo_run(fx, SPO_OTHER, heredoc)
    problems.append(spo_refused("o3", got, reason, (fx["scratch"], "msg.txt")))
    return spo_result(problems, "agent B's heredoc after a cd over agent A's file is refused")


def ovw_case_4():
    """Agent A writes msg.txt, then rewrites it with Write: allowed."""
    fx = spo_fixture("o4")
    msg = os.path.join(fx["scratch"], "msg.txt")
    problems = [spo_scope(fx, "o4", msg)] + spo_wrote(fx, "o4", SPO_WRITER, msg, "from A\n")
    got, reason = spo_call(fx, "Write", SPO_WRITER, file_path=msg, content="from A again\n")
    problems.append(spo_allowed("o4", got, reason))
    return spo_result(problems, "agent A's rewrite of its own file is allowed")


def ovw_case_5():
    """Agent B writes msg.txt, a file no agent wrote before: allowed."""
    fx = spo_fixture("o5")
    msg = os.path.join(fx["scratch"], "msg.txt")
    problems = [spo_scope(fx, "o5", msg)]
    got, reason = spo_call(fx, "Write", SPO_OTHER, file_path=msg, content="from B\n")
    problems.append(spo_allowed("o5", got, reason))
    return spo_result(problems, "agent B's first write of a file nobody wrote is allowed")


def ovw_case_6():
    """Agent A writes msg.txt; a top-level call with no agent_id overwrites it: allowed."""
    fx = spo_fixture("o6")
    msg = os.path.join(fx["scratch"], "msg.txt")
    problems = [spo_scope(fx, "o6", msg)] + spo_wrote(fx, "o6", SPO_WRITER, msg, "from A\n")
    got, reason = spo_call(fx, "Write", None, file_path=msg, content="from the top session\n")
    problems.append(spo_allowed("o6", got, reason))
    return spo_result(problems, "a top-level call with no agent_id overwrites agent A's file and is allowed")


def ovw_case_7():
    """Agent A writes msg.txt; agent B appends to it with >>: refused."""
    fx = spo_fixture("o7")
    msg = os.path.join(fx["scratch"], "msg.txt")
    problems = [spo_scope(fx, "o7", msg)] + spo_wrote(fx, "o7", SPO_WRITER, msg, "from A\n")
    got, reason = spo_run(fx, SPO_OTHER, "echo x >> %s" % msg)
    problems.append(spo_refused("o7", got, reason, (fx["scratch"], "msg.txt")))
    return spo_result(problems, "agent B's append to agent A's file is refused")


spo_register("scratchpad-owner: overwrite 1 agent B's Write over agent A's file: refused", ovw_case_1)
spo_register("scratchpad-owner: overwrite 2 agent B's shell redirect over agent A's file: refused", ovw_case_2)
spo_register("scratchpad-owner: overwrite 3 agent B's heredoc after a cd over agent A's file: refused",
             ovw_case_3)
spo_register("scratchpad-owner: overwrite 4 agent A rewrites its own file: allowed", ovw_case_4)
spo_register("scratchpad-owner: overwrite 5 agent B's first write of a file nobody wrote: allowed",
             ovw_case_5)
spo_register("scratchpad-owner: overwrite 6 a top-level call overwrites agent A's file: allowed",
             ovw_case_6)
spo_register("scratchpad-owner: overwrite 7 agent B's append to agent A's file: refused", ovw_case_7)


# Rule scratchpad-owner, more cases. Each case's label says refused, allowed or passes,
# and each control beside it stays green: the writer runs the same call, so a red case names this rule's gap.

# A different length from PY_TEXT, so a record keyed on size tells the two texts apart.
SPO_OVERWRITE_TEXT = "print(1234)\n"
# The owner entry points and the sidecar helpers they reach. The scratchpad-root helpers are not named: the
# shared-tree rules call them too, and a call from those rules is not an owner call.
SPO_HELPERS = ("scratchpad_agent", "scratchpad_writes", "scratchpad_owner_write", "scratchpad_owner_hit",
               "scratchpad_writer_record", "scratchpad_record_writer", "scratchpad_writer_of")
# The guard run as the harness runs it, with the disk calls of the scratchpad-owner helpers counted. A call
# counts while a helper is on the stack, so the count holds whichever module imported the helper.
SPO_COUNTING_GUARD = '''import atexit, builtins, json, os, runpy, sys, tempfile
HELPERS = frozenset(os.environ["SPO_HELPERS"].split(","))
FILES = ("guard.py", "guard_shared_tree.py")
COUNTS = {"os.path.realpath": 0, "open": 0, "tempfile.gettempdir": 0}


def in_helper():
    frame = sys._getframe(2)
    while frame is not None:
        if frame.f_code.co_name in HELPERS and os.path.basename(frame.f_code.co_filename) in FILES:
            return True
        frame = frame.f_back
    return False


def counted(name, real):
    def call(*args, **kwargs):
        if in_helper():
            COUNTS[name] += 1
        return real(*args, **kwargs)
    return call


def save():
    with builtins.open(os.environ["SPO_COUNTS"], "w", encoding="utf-8") as handle:
        json.dump(COUNTS, handle)


os.path.realpath = counted("os.path.realpath", os.path.realpath)
builtins.open = counted("open", builtins.open)
tempfile.gettempdir = counted("tempfile.gettempdir", tempfile.gettempdir)
sys.path.insert(0, os.path.dirname(os.environ["SPO_GUARD"]))
atexit.register(save)
runpy.run_path(os.environ["SPO_GUARD"], run_name="__main__")
'''


def spo_outside(name, path):
    """Scope before subject for a cost case: `path` names no scratchpad, by its real path or its text."""
    if "scratchpad" in os.path.realpath(path) or "scratchpad" in path:
        return "%s: setup, the path names a scratchpad: %s" % (name, path)
    return ""


def spo_counted(fx, tag, tool, agent, **tool_input):
    """One guard call as `spo_call` makes it, through the counting wrapper. Returns (decision, reason, counts),
    where counts maps each counted call to its number, or is None when the run wrote no count."""
    folder = os.path.dirname(fx["work"])
    wrapper = os.path.join(folder, "counting_guard.py")
    write(wrapper, SPO_COUNTING_GUARD)
    counts = os.path.join(folder, "counts-%s.json" % tag)
    got, reason = decide({"raw": None, "tool": tool, "cwd": fx["work"], "session": fx["sid"],
                          "env_path": None, "config": None, "agent_id": agent, "process_cwd": None,
                          "temp": fx["tmp"], "tool_input": dict(tool_input), "guard": wrapper,
                          "env": {"SPO_GUARD": GUARD, "SPO_COUNTS": counts,
                                  "SPO_HELPERS": ",".join(SPO_HELPERS)}})
    if not os.path.exists(counts):
        return got, reason, None
    with open(counts, encoding="utf-8") as handle:
        return got, reason, json.load(handle)


def spo_run_case(tag, name, script_name, command_of, passed, text=PY_TEXT):
    """Agent A writes `script_name` with Write. Agent B's call `command_of(fx, path)` acts on the file and is
    refused. Agent A's same call is the control, and is allowed."""
    fx = spo_fixture(tag)
    path = os.path.join(fx["scratch"], script_name)
    problems = [spo_scope(fx, name, path)] + spo_wrote(fx, name, SPO_WRITER, path, text)
    got, reason = spo_run(fx, SPO_OTHER, command_of(fx, path))
    problems.append(spo_refused(name, got, reason, (fx["scratch"], script_name)))
    got, reason = spo_run(fx, SPO_WRITER, command_of(fx, path))
    problems.append(spo_allowed(name + ", control: agent A's own call", got, reason))
    return spo_result(problems, passed)


def spo_flag_1():
    return spo_run_case("flag1", "flag 1", "probe2.py", lambda fx, p: "python3 -W ignore %s" % p,
                        "agent B's python3 -W ignore run of agent A's script is refused")


def spo_flag_2():
    return spo_run_case("flag2", "flag 2", "probe2.py", lambda fx, p: "python3 -X dev %s" % p,
                        "agent B's python3 -X dev run of agent A's script is refused")


def spo_flag_3():
    return spo_run_case("flag3", "flag 3", "x.js", lambda fx, p: "node --require /x %s" % p,
                        "agent B's node --require run of agent A's script is refused", text="console.log(1)\n")


def spo_variable_1():
    return spo_run_case("var1", "variable 1", "probe2.py",
                        lambda fx, p: 'S=%s; python3 "$S/probe2.py"' % os.path.dirname(p),
                        "agent B's run of agent A's script by a shell variable path is refused")


def spo_removal_1():
    return spo_run_case("rm1", "removal 1", "msg.txt", lambda fx, p: "rm %s" % p,
                        "agent B's rm of agent A's file is refused", text="from A\n")


def spo_move_1():
    return spo_run_case("mv1", "move 1", "msg.txt",
                        lambda fx, p: "mv %s %s" % (p, os.path.join(fx["work"], "moved.txt")),
                        "agent B's mv of agent A's file is refused", text="from A\n")


def spo_approved_case():
    """Agent A writes probe2.py. Agent B's overwrite is refused. The owner types `override 15m` at 30 s, and B's
    overwrite at 60 s is lifted. Once the override has ended, B's run and B's rewrite pass with no override in
    effect, so the approved overwrite must have moved the record to B. The approval is the override file, the
    way the suite simulates an owner override for other rules."""
    fx = spo_fixture("approved")
    config = ov_config("spo-approved")
    probe = os.path.join(fx["scratch"], "probe2.py")
    problems = [spo_scope(fx, "approved", probe)] + spo_wrote(fx, "approved", SPO_WRITER, probe, PY_TEXT)

    def call(tool, tool_input, seconds):
        return ov_call(tool, tool_input, fx["work"], config, fx["sid"], seconds, agent_id=SPO_OTHER,
                       temp=fx["tmp"])

    overwrite = {"file_path": probe, "content": SPO_OVERWRITE_TEXT}
    got, reason = call("Write", overwrite, 0)
    problems.append(spo_refused("approved, B's overwrite before the override", got, reason,
                                (fx["scratch"], "probe2.py")))
    note = ov_type(config, fx["sid"], "override 15m", 30)
    got, reason = call("Write", overwrite, 60)
    problems.append(spo_allowed("approved, B's overwrite under the override", got, reason))
    if got == "allow":
        write(probe, SPO_OVERWRITE_TEXT)   # the approved act lands its bytes, as the tool would
    later = OV_TIMED_SECONDS + 120   # the override typed at 30 s ends 15 min on
    got, reason = call("Bash", {"command": "python3 %s" % probe}, later)
    problems.append(spo_allowed("approved, B's run after the override ended", got, reason))
    got, reason = call("Write", overwrite, later + 60)
    problems.append(spo_allowed("approved, B's rewrite after the override ended", got, reason))
    if got == "allow":
        write(probe, SPO_OVERWRITE_TEXT)
    if note and any(problems):
        problems.append("the override was not typed through override.grant: " + note)
    return spo_result(problems, "an approved overwrite moves the record: B's later run and rewrite are allowed")


def spo_top_write(fx, probe, name):
    return spo_wrote(fx, name, None, probe, SPO_OVERWRITE_TEXT)


def spo_top_redirect(fx, probe, name):
    return spo_wrote(fx, name, None, probe, SPO_OVERWRITE_TEXT, tool="Bash",
                     command="echo 'print(1234)' > %s" % probe)


def spo_top_level_case(tag, name, overwrite):
    """Agent A writes probe2.py, and agent B's run is refused (the control). A call with no agent_id then overwrites
    the file, and that call is allowed. Agent B's run after it passes: a top-level overwrite leaves no record."""
    fx = spo_fixture(tag)
    probe = os.path.join(fx["scratch"], "probe2.py")
    problems = [spo_scope(fx, name, probe)] + spo_wrote(fx, name, SPO_WRITER, probe, PY_TEXT)
    got, reason = spo_run(fx, SPO_OTHER, "python3 %s" % probe)
    problems.append(spo_refused(name + ", control before the overwrite", got, reason,
                                (fx["scratch"], "probe2.py")))
    problems += overwrite(fx, probe, name)
    got, reason = spo_run(fx, SPO_OTHER, "python3 %s" % probe)
    problems.append(spo_allowed(name + ", B's run after it", got, reason))
    return spo_result(problems, "a top-level overwrite leaves no record: B's run after it is allowed")


def spo_lifted_removal_case(tag, name, command_of, land, passed):
    """Agent A writes probe2.py. Agent B's removal of it is refused: `command_of` names the rm or mv. The owner types
    `override 15m` at 30 s, and B's removal at 60 s is lifted, so it lands: `land` acts on the file as the tool would.
    A removal records no writer, so the record stays with agent A. The file then comes back outside the guard, as an
    editor's save would. Once the override has ended, B's run is refused and A's run is allowed."""
    fx = spo_fixture(tag)
    config = ov_config("spo-" + tag)
    probe = os.path.join(fx["scratch"], "probe2.py")
    problems = [spo_scope(fx, name, probe)] + spo_wrote(fx, name, SPO_WRITER, probe, PY_TEXT)

    def call(agent, command, seconds):
        return ov_call("Bash", {"command": command}, fx["work"], config, fx["sid"], seconds, agent_id=agent,
                       temp=fx["tmp"])

    removal = command_of(fx, probe)
    got, reason = call(SPO_OTHER, removal, 0)
    problems.append(spo_refused(name + ", B's removal before the override", got, reason,
                                (fx["scratch"], "probe2.py")))
    note = ov_type(config, fx["sid"], "override 15m", 30)
    got, reason = call(SPO_OTHER, removal, 60)
    problems.append(spo_allowed(name + ", B's removal under the override", got, reason))
    if got == "allow":
        land(fx, probe)   # the approved removal lands, as the tool would
    write(probe, PY_TEXT)   # the file comes back outside the guard, as an editor's save would
    later = OV_TIMED_SECONDS + 120   # the override typed at 30 s has ended by then
    got, reason = call(SPO_OTHER, "python3 %s" % probe, later)
    problems.append(spo_refused(name + ", B's run after the override ended", got, reason,
                                (fx["scratch"], "probe2.py")))
    got, reason = call(SPO_WRITER, "python3 %s" % probe, later)
    problems.append(spo_allowed(name + ", control: agent A's own run", got, reason))
    if note and any(problems):
        problems.append("the override was not typed through override.grant: " + note)
    return spo_result(problems, passed)


def spo_moved_path(fx):
    return os.path.join(fx["work"], "moved.txt")


def spo_approved_rm_case():
    return spo_lifted_removal_case("lrm", "approved 2 rm", lambda fx, p: "rm %s" % p,
                                   lambda fx, p: os.remove(p),
                                   "an approved rm keeps the record with agent A: B's later run is refused")


def spo_approved_mv_case():
    return spo_lifted_removal_case("lmv", "approved 3 mv", lambda fx, p: "mv %s %s" % (p, spo_moved_path(fx)),
                                   lambda fx, p: os.rename(p, spo_moved_path(fx)),
                                   "an approved mv keeps the record with agent A: B's later run is refused")


def spo_removed_case():
    """Agent A writes probe2.py. The file is removed outside the guard before any agent B step, so A's record is
    the only trace left. Agent B's Write of a new probe2.py at the same path is allowed. The record still names
    A, so a rule that does not check the record against the file asks here: the case fails on that gap."""
    fx = spo_fixture("removed")
    probe = os.path.join(fx["scratch"], "probe2.py")
    problems = [spo_scope(fx, "removed", probe)] + spo_wrote(fx, "removed", SPO_WRITER, probe, PY_TEXT)
    os.remove(probe)
    if os.path.exists(probe):
        problems.append("removed, setup: probe2.py still exists after the removal")
    got, reason = spo_call(fx, "Write", SPO_OTHER, file_path=probe, content=PY_TEXT)
    problems.append(spo_allowed("removed, B's new probe2.py", got, reason))
    return spo_result(problems, "a new file at a removed file's path is allowed")


def spo_cost_case():
    """Agent A writes probe2.py. Its own run is the control: the helpers read its record, so the counter is live.
    Agent B's Write and B's run, outside any scratchpad and naming none, make no realpath, open or gettempdir call
    inside a helper, and both are allowed."""
    fx = spo_fixture("cost")
    probe = os.path.join(fx["scratch"], "probe2.py")
    problems = [spo_scope(fx, "cost", probe)] + spo_wrote(fx, "cost", SPO_WRITER, probe, PY_TEXT)
    got, reason, counts = spo_counted(fx, "control", "Bash", SPO_WRITER, command="python3 %s" % probe)
    problems.append(spo_allowed("cost, control: agent A's own run", got, reason))
    if not counts or not any(counts.values()):
        problems.append("cost, control: the scratchpad's own run counted no helper call, so the counter is not live")
    notes = os.path.join(fx["work"], "notes.txt")
    tool = os.path.join(fx["work"], "tool.py")
    write(tool, PY_TEXT)
    problems += [spo_outside("cost, notes.txt", notes), spo_outside("cost, tool.py", tool)]
    outside = (("write", "Write", {"file_path": notes, "content": "x\n"}),
               ("run", "Bash", {"command": "python3 %s" % tool}))
    for label, tool_name, tool_input in outside:
        got, reason, counts = spo_counted(fx, label, tool_name, SPO_OTHER, **tool_input)
        problems.append(spo_allowed("cost, %s" % label, got, reason))
        if counts is None:
            problems.append("cost, %s: no count was written" % label)
        elif any(counts.values()):
            problems.append("cost, %s: a helper made disk calls on a call outside any scratchpad: %s"
                            % (label, counts))
    return spo_result(problems, "a call outside any scratchpad makes no helper realpath, open or gettempdir call")


spo_register("scratchpad-owner: flag 1 agent B runs agent A's script past python3 -W ignore: refused", spo_flag_1)
spo_register("scratchpad-owner: flag 2 agent B runs agent A's script past python3 -X dev: refused", spo_flag_2)
spo_register("scratchpad-owner: flag 3 agent B runs agent A's script past node --require: refused", spo_flag_3)
spo_register("scratchpad-owner: variable 1 agent B runs agent A's script by a shell variable path: refused",
             spo_variable_1)
spo_register("scratchpad-owner: approved 1 agent B's overwrite the owner approves moves the record: "
             "B's later run and rewrite pass", spo_approved_case)
spo_register("scratchpad-owner: approved 2 agent B's rm the owner approves keeps the record with agent A: "
             "B's later run is refused", spo_approved_rm_case)
spo_register("scratchpad-owner: approved 3 agent B's mv the owner approves keeps the record with agent A: "
             "B's later run is refused", spo_approved_mv_case)
spo_register("scratchpad-owner: top-level 1 a call with no agent_id overwrites agent A's file with Write: "
             "B's later run passes", lambda: spo_top_level_case("top1", "top-level 1", spo_top_write))
spo_register("scratchpad-owner: top-level 2 a call with no agent_id overwrites agent A's file with a shell "
             "redirect: B's later run passes", lambda: spo_top_level_case("top2", "top-level 2", spo_top_redirect))
spo_register("scratchpad-owner: removed 1 agent A's file removed outside the guard: B's new file at its path "
             "is allowed", spo_removed_case)
spo_register("scratchpad-owner: removal 1 agent B's rm of agent A's file: refused", spo_removal_1)
spo_register("scratchpad-owner: move 1 agent B's mv of agent A's file: refused", spo_move_1)
spo_register("scratchpad-owner: cost 1 a call outside any scratchpad makes no helper realpath, open or "
             "gettempdir call", spo_cost_case)


def spo_stdin_case():
    """Agent A writes data.json. Agent B runs python3 with `-`, so the program is the heredoc on stdin, and passes
    data.json as an argument: allowed. data.json is read as data, never run."""
    fx = spo_fixture("stdin")
    data = os.path.join(fx["scratch"], "data.json")
    problems = [spo_scope(fx, "stdin", data)] + spo_wrote(fx, "stdin", SPO_WRITER, data, '{"a": 1}\n')
    got, reason = spo_run(fx, SPO_OTHER, "python3 - %s <<'PY'\nprint(1)\nPY" % data)
    problems.append(spo_allowed("stdin, agent B's python3 - with agent A's data.json as an argument", got, reason))
    return spo_result(problems, "a file passed to python3 - as an argument is data, and the run is allowed")


def spo_dashdash_1():
    return spo_run_case("dash1", "dashdash 1", "x.py", lambda fx, p: "python3 -- %s" % p,
                        "agent B's python3 -- run of agent A's script is refused")


spo_register("scratchpad-owner: stdin 1 agent B's python3 - with a heredoc and agent A's data.json as an "
             "argument: allowed", spo_stdin_case)
spo_register("scratchpad-owner: dashdash 1 agent B's python3 -- run of agent A's script: refused", spo_dashdash_1)


# Rule scratchpad-owner, the refusal's remedy and the record. A refused call has decision deny, and its remedy
# names a fresh file name of the agent's own. It never tells the agent to ask or to overwrite. The `Remedy:` clause
# is judged on its own: the decision gloss and the override offer line, which follow it, never count. A refused
# call leaves the record with the first writer, and only a call the owner lifts moves it.
SPO_FRESH_NAME = re.compile(r"\b(fresh|new)\b[^.;()]{0,24}?\bnames?\b", re.IGNORECASE)
SPO_FORBIDDEN_ROUTE = re.compile(r"\b(ask\w*|overwrit\w*)\b", re.IGNORECASE)


def spo_remedy(reason):
    """The text from `Remedy:` up to the decision gloss, or '' when the reason holds no `Remedy:` clause."""
    start = reason.find("Remedy:")
    if start < 0:
        return ""
    end = reason.find(" (decision", start)
    return reason[start:] if end < 0 else reason[start:end]


def spo_remedy_problem(name, got, reason, check):
    """The first problem with the remedy of one refusal, else ''. A call that is allowed has no refusal to judge."""
    if got == "allow":
        return "%s: setup, B's call is allowed, so there is no refusal whose remedy to judge" % name
    text = spo_remedy(reason)
    if not text:
        return "%s: the refusal holds no Remedy: clause (%s)" % (name, reason[:100])
    return check(name, text)


def spo_fresh_name_check(name, text):
    if SPO_FRESH_NAME.search(text):
        return ""
    return "%s: the remedy names no fresh or new file name (%s)" % (name, text[:100])


def spo_no_route_check(name, text):
    match = SPO_FORBIDDEN_ROUTE.search(text)
    if not match:
        return ""
    return "%s: the remedy routes the agent to %r (%s)" % (name, match.group(0), text[:100])


def spo_refusal(tag, form):
    """Agent A writes one file; agent B's call in `form` acts on it. `overwrite` is B's Write over the file,
    `run` is B's run of it. Agent A's own call in the same form is the control, and is allowed. Returns
    (problems, decision, reason)."""
    fx = spo_fixture(tag)
    # The control runs before B's call. A refused call leaves the record with A, so both calls read A's record.
    if form == "overwrite":
        path = os.path.join(fx["scratch"], "msg.txt")
        problems = [spo_scope(fx, tag, path)] + spo_wrote(fx, tag, SPO_WRITER, path, "from A\n")
        control_got, control_reason = spo_call(fx, "Write", SPO_WRITER, file_path=path, content="from A again\n")
        got, reason = spo_call(fx, "Write", SPO_OTHER, file_path=path, content="from B\n")
    else:
        path = os.path.join(fx["scratch"], "probe2.py")
        problems = [spo_scope(fx, tag, path)] + spo_wrote(fx, tag, SPO_WRITER, path, PY_TEXT)
        control_got, control_reason = spo_run(fx, SPO_WRITER, "python3 %s" % path)
        got, reason = spo_run(fx, SPO_OTHER, "python3 %s" % path)
    problems.append(spo_allowed("%s, control: agent A's own %s" % (tag, form), control_got, control_reason))
    return [p for p in problems if p], got, reason


def spo_remedy_case(tag, form, check, passed):
    """Agent B's refused call in `form`: its remedy passes `check`."""
    problems, got, reason = spo_refusal(tag, form)
    return spo_result(problems + [spo_remedy_problem(tag, got, reason, check)], passed)


def spo_remedy_fresh_overwrite():
    return spo_remedy_case("remedy-fresh-overwrite", "overwrite", spo_fresh_name_check,
                           "the overwrite refusal names a fresh or new file name")


def spo_remedy_fresh_run():
    return spo_remedy_case("remedy-fresh-run", "run", spo_fresh_name_check,
                           "the run refusal names a fresh or new file name")


def spo_remedy_route_overwrite():
    return spo_remedy_case("remedy-route-overwrite", "overwrite", spo_no_route_check,
                           "the overwrite refusal names no ask and no overwrite")


def spo_remedy_route_run():
    return spo_remedy_case("remedy-route-run", "run", spo_no_route_check,
                           "the run refusal names no ask and no overwrite")


def spo_record_case():
    """Agent A writes probe2.py. Agent B's overwrite of it is refused, and B's retry of the same overwrite and B's
    run of A's file are refused too: a refused call leaves the record with A. Only a call the owner lifts moves the
    record. The first failing step returns, so each message names one cause."""
    fx = spo_fixture("record")
    probe = os.path.join(fx["scratch"], "probe2.py")
    first = [spo_scope(fx, "record", probe)] + spo_wrote(fx, "record", SPO_WRITER, probe, PY_TEXT)
    if any(first):
        return spo_result(first, "")
    got, reason = spo_run(fx, SPO_WRITER, "python3 %s" % probe)
    if got != "allow":
        return spo_result(["record, control: agent A's own run is %s, want allow (%s)" % (got, reason[:100])], "")
    overwrite = {"file_path": probe, "content": SPO_OVERWRITE_TEXT}
    got, reason = spo_call(fx, "Write", SPO_OTHER, **overwrite)
    if got == "allow":
        return spo_result(["record, B's overwrite is allowed, so no refusal is tested"], "")
    got, reason = spo_call(fx, "Write", SPO_OTHER, **overwrite)
    if got == "allow":
        return spo_result(["record, B's retry of its refused overwrite is allowed: the refused call moved the "
                           "record to B"], "")
    got, reason = spo_run(fx, SPO_OTHER, "python3 %s" % probe)
    if got == "allow":
        return spo_result(["record, B's run of A's file is allowed: the record names B, not A"], "")
    return spo_result([], "a refused overwrite leaves the record with agent A: B's retry and B's run are refused")


spo_register("scratchpad-owner: remedy 1 the overwrite refusal names a fresh or new file name",
             spo_remedy_fresh_overwrite)
spo_register("scratchpad-owner: remedy 2 the run refusal names a fresh or new file name", spo_remedy_fresh_run)
spo_register("scratchpad-owner: remedy 3 the overwrite refusal names no ask and no overwrite",
             spo_remedy_route_overwrite)
spo_register("scratchpad-owner: remedy 4 the run refusal names no ask and no overwrite", spo_remedy_route_run)
spo_register("scratchpad-owner: record 1 a refused overwrite leaves the record with agent A: B's retry and B's "
             "run are refused", spo_record_case)


# =========================================================================== mask_script lexemes
