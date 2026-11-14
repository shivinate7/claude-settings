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
    body or a multi-line string, or passes probe2.py as an argument to a command that runs another file, and runs
    no scratchpad file: allowed. `command_of(probe, outside)` builds the call."""
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


# A run of agent A's file in a form a first-command reader does not read: a substitution, a subshell, a pipe, a
# stdin redirect, a shell `-c` string, or a runner or wrapper word ahead of the script. A row is (tag, the form, the
# file's name, its text, the call with the file's path as %s). Agent B's run is refused; agent A's same run is allowed.
TS_TEXT = "console.log(1)\n"
SPO_RUNNER_FORMS = (
    ("subst", "out=$(python3 F)", "probe2.py", PY_TEXT, "out=$(python3 %s)"),
    ("echo-subst", "echo $(python3 F)", "probe2.py", PY_TEXT, "echo $(python3 %s)"),
    # A substitution in double quotes, and a `[` test that holds one, run the file the same as the unquoted form.
    ("subst-quoted", 'out="$(python3 F)"', "probe2.py", PY_TEXT, 'out="$(python3 %s)"'),
    ("echo-subst-quoted", 'echo "$(python3 F)"', "probe2.py", PY_TEXT, 'echo "$(python3 %s)"'),
    # A backtick substitution, the form the scratchpad-owner-runners debt names: the run sits inside the backticks.
    ("backtick", "echo `python3 F`", "probe2.py", PY_TEXT, "echo `python3 %s`"),
    ("test-subst", '[ "$(python3 F)" = ok ]', "probe2.py", PY_TEXT, '[ "$(python3 %s)" = ok ]'),
    # An assignment ahead of a substitution that closes inside the same word (`A=$(date)`, a quoted, backtick or
    # `$((` form, or `env` ahead of it). The group ends in that word, so the command after it runs the file too.
    # The open form `x=$(python3 F)` is the control below, where the run sits inside the group.
    ("subst-assign", "A=$(date) python3 F", "probe2.py", PY_TEXT, "A=$(date) python3 %s"),
    ("subst-assign-quoted", 'A="$(date)" python3 F', "probe2.py", PY_TEXT, 'A="$(date)" python3 %s'),
    ("subst-assign-backtick", "A=`date` python3 F", "probe2.py", PY_TEXT, "A=`date` python3 %s"),
    ("subst-assign-arith", "A=$((1+2)) python3 F", "probe2.py", PY_TEXT, "A=$((1+2)) python3 %s"),
    ("subst-assign-env", "env A=$(pwd) python3 F", "probe2.py", PY_TEXT, "env A=$(pwd) python3 %s"),
    ("subshell", "(python3 F)", "probe2.py", PY_TEXT, "(python3 %s)"),
    ("uv", "uv run F", "probe2.py", PY_TEXT, "uv run %s"),
    ("npx-tsx", "npx tsx F", "probe2.ts", TS_TEXT, "npx tsx %s"),
    ("bun", "bun run F", "probe2.ts", TS_TEXT, "bun run %s"),
    ("deno", "deno run F", "probe2.ts", TS_TEXT, "deno run %s"),
    ("pytest", "pytest F", "probe2.py", PY_TEXT, "pytest %s"),
    ("pytest-m", "python3 -m pytest F", "probe2.py", PY_TEXT, "python3 -m pytest %s"),
    ("pytest-k", "pytest -k expr F", "probe2.py", PY_TEXT, "pytest -k expr %s"),
    ("pytest-mark", "pytest -m slow F", "probe2.py", PY_TEXT, "pytest -m slow %s"),
    ("pytest-c", "pytest -c cfg.ini F", "probe2.py", PY_TEXT, "pytest -c cfg.ini %s"),
    ("py", "py F", "probe2.py", PY_TEXT, "py %s"),
    ("py-3", "py -3 F", "probe2.py", PY_TEXT, "py -3 %s"),
    ("stdbuf", "stdbuf -oL python3 F", "probe2.py", PY_TEXT, "stdbuf -oL python3 %s"),
    # `setsid python3 F` is not here: detached launch denies it for every agent, the writer's own run too, so this
    # rule is never reached and the case could not go red for it.
    ("stdin", "python3 < F", "probe2.py", PY_TEXT, "python3 < %s"),
    ("pipe", "cat F | python3", "probe2.py", PY_TEXT, "cat %s | python3"),
    ("bash-c", 'bash -c "python3 F"', "probe2.py", PY_TEXT, 'bash -c "python3 %s"'),
    ("sh-c", 'sh -c "python3 F"', "probe2.py", PY_TEXT, 'sh -c "python3 %s"'),
    # A flag whose value follows a space (`-n 2`, `--cov-report html`, `--with x`), and `ionice`, a wrapper no
    # runner list names. Each is a run of the file.
    ("pytest-n", "pytest -n 2 F", "probe2.py", PY_TEXT, "pytest -n 2 %s"),
    ("pytest-cov", "pytest --cov-report html F", "probe2.py", PY_TEXT, "pytest --cov-report html %s"),
    ("uv-with", "uv run --with x F", "probe2.py", PY_TEXT, "uv run --with x %s"),
    ("ionice", "ionice -c3 python3 F", "probe2.py", PY_TEXT, "ionice -c3 python3 %s"),
    # The scanner must read through a quote, a `#` in a string and a line break, not stop at them.
    ("subst-apostrophe", 'echo "don\'t $(python3 F)"', "probe2.py", PY_TEXT, 'echo "don\'t $(python3 %s)"'),
    ("subst-second-line", "a run on the second line of out=$(...)", "probe2.py", PY_TEXT,
     "out=$(\npython3 %s\n)"),
    ("sh-c-hash", 'bash -c "echo \'#\' && python3 F"', "probe2.py", PY_TEXT, 'bash -c "echo \'#\' && python3 %s"'),
)


def spo_runner_case(tag, form, script_name, text, template):
    """Agent A writes the script with Write. Agent B runs it in `form`: refused. Agent A's same run is allowed."""
    return lambda: spo_run_case("run-" + tag, "runner %s" % form, script_name, lambda fx, p: template % p,
                                "agent B's %s run of agent A's script is refused" % form, text=text)


def spo_cp_in_case():
    """Agent A copies a script into the scratchpad with cp. Agent B runs the copy: refused. A's run of its copy is
    allowed."""
    fx = spo_fixture("cp-in")
    source = os.path.join(fx["work"], "x.py")   # outside the scratchpad, in this case's folder
    write(source, PY_TEXT)
    dest = os.path.join(fx["scratch"], "g.py")
    problems = [spo_scope(fx, "cp in", dest)]
    problems += spo_wrote(fx, "cp in", SPO_WRITER, dest, PY_TEXT, tool="Bash", command="cp %s %s" % (source, dest))
    got, reason = spo_run(fx, SPO_OTHER, "python3 %s" % dest)
    problems.append(spo_refused("cp in, B's run of A's copy", got, reason, (fx["scratch"], "g.py")))
    got, reason = spo_run(fx, SPO_WRITER, "python3 %s" % dest)
    problems.append(spo_allowed("cp in, control: A's run of its copy", got, reason))
    return spo_result(problems, "agent B's run of a script agent A copied into the scratchpad with cp is refused")


def spo_mv_carry_case():
    """Agent A writes probe2.py, then moves it to h.py with mv, and the move lands. Agent B runs h.py: refused,
    since the mv carries A's record to the new name. A's run of h.py is allowed."""
    fx = spo_fixture("mv-carry")
    probe = os.path.join(fx["scratch"], "probe2.py")
    moved = os.path.join(fx["scratch"], "h.py")
    problems = [spo_scope(fx, "mv carry", probe)] + spo_wrote(fx, "mv carry", SPO_WRITER, probe, PY_TEXT)
    got, reason = spo_call(fx, "Bash", SPO_WRITER, command="mv %s %s" % (probe, moved))
    problems.append(spo_allowed("mv carry, A's mv of its own file", got, reason))
    if got == "allow":
        os.rename(probe, moved)   # the approved mv lands its file at the new name
    got, reason = spo_run(fx, SPO_OTHER, "python3 %s" % moved)
    problems.append(spo_refused("mv carry, B's run of the moved file", got, reason, (fx["scratch"], "h.py")))
    got, reason = spo_run(fx, SPO_WRITER, "python3 %s" % moved)
    problems.append(spo_allowed("mv carry, control: A's run of the moved file", got, reason))
    return spo_result(problems, "an mv carries agent A's record to the new name: B's run is refused")


def spo_cp_own_case():
    """Agent A writes probe2.py. Agent B copies it to mine.py with cp. The copy keeps A as its writer, as an mv does,
    so B's run of mine.py is refused: B ran a script it never read. A's run of it is the control, which is allowed.
    The refusal's remedy says to read the file and write an own copy, and never names cp."""
    fx = spo_fixture("cp-own")
    probe = os.path.join(fx["scratch"], "probe2.py")
    mine = os.path.join(fx["scratch"], "mine.py")
    problems = [spo_scope(fx, "cp own", probe)] + spo_wrote(fx, "cp own", SPO_WRITER, probe, PY_TEXT)
    problems += spo_wrote(fx, "cp own", SPO_OTHER, mine, PY_TEXT, tool="Bash", command="cp %s %s" % (probe, mine))
    got, reason = spo_run(fx, SPO_OTHER, "python3 %s" % mine)
    problems.append(spo_refused("cp own, B's run of its copy of A's file", got, reason, (fx["scratch"], "mine.py")))
    if "read the file" not in reason or re.search(r"\bcp\b", reason):
        problems.append("cp own: the remedy must say read, then write an own copy, and never name cp (%s)" % reason[:160])
    got, reason = spo_run(fx, SPO_WRITER, "python3 %s" % mine)
    problems.append(spo_allowed("cp own, control: A's run of the copy of its file", got, reason))
    return spo_result(problems, "agent B's copy of agent A's file keeps A as writer, and B's run of it is refused")


def spo_cp_keeps_cases(tag, name, first_agent, passed):
    """`first_agent` writes src.py (None is the top-level session, whose write leaves no record). Agent B copies it
    to c.py with cp, and runs c.py. When B wrote src.py, or no agent did, the copy is B's: B's run is allowed and another agent's is refused."""
    fx = spo_fixture(tag)
    src = os.path.join(fx["scratch"], "src.py")
    dest = os.path.join(fx["scratch"], "c.py")
    problems = [spo_scope(fx, name, src)] + spo_wrote(fx, name, first_agent, src, PY_TEXT)
    problems += spo_wrote(fx, name, SPO_OTHER, dest, PY_TEXT, tool="Bash", command="cp %s %s" % (src, dest))
    got, reason = spo_run(fx, SPO_OTHER, "python3 %s" % dest)
    problems.append(spo_allowed(name + ", B's run of its copy", got, reason))
    got, reason = spo_run(fx, SPO_WRITER, "python3 %s" % dest)   # the copy is B's text: another agent's run is refused
    problems.append(spo_refused(name + ", A's run of the copy B made", got, reason, (fx["scratch"], "c.py")))
    return spo_result(problems, passed)


def spo_cp_own_file_case():
    return spo_cp_keeps_cases("cp-keeps-own", "cp-mv 7", SPO_OTHER, "agent B's copy of B's own file is B's, and B's run "
                                                                   "of it is allowed")


def spo_cp_top_level_case():
    """Agent A writes src.py. The top-level session (no agent_id) copies it to c.py with cp: the file is the
    session's own now, as any write of that call makes it, so agent B's run of c.py is allowed."""
    fx = spo_fixture("cp-top")
    src = os.path.join(fx["scratch"], "src.py")
    dest = os.path.join(fx["scratch"], "c.py")
    problems = [spo_scope(fx, "cp-mv 9", src)] + spo_wrote(fx, "cp-mv 9", SPO_WRITER, src, PY_TEXT)
    problems += spo_wrote(fx, "cp-mv 9", None, dest, PY_TEXT, tool="Bash", command="cp %s %s" % (src, dest))
    got, reason = spo_run(fx, SPO_OTHER, "python3 %s" % dest)
    problems.append(spo_allowed("cp-mv 9, B's run of the top-level session's copy", got, reason))
    return spo_result(problems, "the top-level session's cp of agent A's file clears the record, and B's run is allowed")


SPO_THIRD = "spo-third-03"


def spo_cp_copier_case():
    """Agent A writes src.py. Agent B copies it to c.py with cp. B runs c.py: refused, as the writer is A. B may
    still re-run the cp, write over c.py with the Write tool, and remove it with rm: the copier owns its copy. A and
    a third agent C, who are not the copier, may not write over c.py."""
    fx = spo_fixture("cp-copier")
    src = os.path.join(fx["scratch"], "src.py")
    dest = os.path.join(fx["scratch"], "c.py")
    copy = "cp %s %s" % (src, dest)
    problems = [spo_scope(fx, "cp-mv 10", src)] + spo_wrote(fx, "cp-mv 10", SPO_WRITER, src, PY_TEXT)
    problems += spo_wrote(fx, "cp-mv 10", SPO_OTHER, dest, PY_TEXT, tool="Bash", command=copy)
    got, reason = spo_run(fx, SPO_OTHER, "python3 %s" % dest)
    problems.append(spo_refused("cp-mv 10, B's run of its copy", got, reason, (fx["scratch"], "c.py")))
    got, reason = spo_call(fx, "Write", SPO_WRITER, file_path=dest, content="print(3)\n")   # the record still names A
    problems.append(spo_refused("cp-mv 10, control: A's Write over B's fresh copy", got, reason, (fx["scratch"], "c.py")))
    got, reason = spo_run(fx, SPO_OTHER, copy)
    problems.append(spo_allowed("cp-mv 10, B's retry of the cp", got, reason))
    got, reason = spo_call(fx, "Write", SPO_OTHER, file_path=dest, content="print(2)\n")
    problems.append(spo_allowed("cp-mv 10, B's Write over its copy", got, reason))
    for agent in (SPO_WRITER, SPO_THIRD):
        got, reason = spo_call(fx, "Write", agent, file_path=dest, content="print(3)\n")
        problems.append(spo_refused("cp-mv 10, control: %s's Write over B's file" % agent, got, reason,
                                    (fx["scratch"], "c.py")))
    problems += spo_wrote(fx, "cp-mv 10", SPO_OTHER, dest, PY_TEXT, tool="Bash", command=copy)
    got, reason = spo_run(fx, SPO_OTHER, "rm %s" % dest)
    problems.append(spo_allowed("cp-mv 10, B's rm of its copy", got, reason))
    return spo_result(problems, "agent B's copy of A's file runs refused, and B may still re-copy, rewrite and remove "
                                "it, which no other agent may")


def spo_cp_mv_case(tag, name, one_call, mover=SPO_OTHER):
    """Agent A writes src.py. Agent B copies it to c.py, and `mover` moves the copy to d.py, in two calls or in one
    (`mover` is None for the top-level session). The mv carries the copier: C's rm of d.py is refused, B's rm of it is
    allowed, and B's run of it is refused."""
    fx = spo_fixture(tag)
    src = os.path.join(fx["scratch"], "src.py")
    mid = os.path.join(fx["scratch"], "c.py")
    dest = os.path.join(fx["scratch"], "d.py")
    problems = [spo_scope(fx, name, src)] + spo_wrote(fx, name, SPO_WRITER, src, PY_TEXT)
    if one_call:
        problems += spo_wrote(fx, name, SPO_OTHER, dest, PY_TEXT, tool="Bash",
                              command="cp %s %s && mv %s %s" % (src, mid, mid, dest))
    else:
        problems += spo_wrote(fx, name, SPO_OTHER, mid, PY_TEXT, tool="Bash", command="cp %s %s" % (src, mid))
        got, reason = spo_run(fx, mover, "mv %s %s" % (mid, dest))
        who = "B's mv of its own copy" if mover == SPO_OTHER else "the top-level session's mv of B's copy"
        problems.append(spo_allowed(name + ", " + who, got, reason))
        if os.path.exists(mid):
            os.replace(mid, dest)   # the mv lands, as the harness would run it
        else:
            write(dest, PY_TEXT)
    got, reason = spo_run(fx, SPO_OTHER, "python3 %s" % dest)
    problems.append(spo_refused(name + ", B's run of the moved copy", got, reason, (fx["scratch"], "d.py")))
    got, reason = spo_run(fx, SPO_THIRD, "rm %s" % dest)
    problems.append(spo_refused(name + ", control: C's rm of the moved copy", got, reason, (fx["scratch"], "d.py")))
    got, reason = spo_run(fx, SPO_OTHER, "rm %s" % dest)
    problems.append(spo_allowed(name + ", B's rm of the moved copy", got, reason))
    return spo_result(problems, "an mv of a copy keeps its copier: B may remove it and C may not")


def spo_cp_mv_two_call():
    return spo_cp_mv_case("cp-mv-two", "cp-mv 12", False)


def spo_cp_mv_one_call():
    return spo_cp_mv_case("cp-mv-one", "cp-mv 13", True)


def spo_cp_mv_top_case():
    return spo_cp_mv_case("cp-mv-top", "cp-mv 14", False, mover=None)


def spo_mv_unrecorded_case():
    """The top-level session writes src.py, so no record names it. Agent B moves it to new.py with mv. An mv of an
    unrecorded source gets no record, so agent A's run of new.py and B's rm of it are allowed."""
    fx = spo_fixture("mv-unrecorded")
    src = os.path.join(fx["scratch"], "src.py")
    moved = os.path.join(fx["scratch"], "new.py")
    problems = [spo_scope(fx, "cp-mv 15", src)] + spo_wrote(fx, "cp-mv 15", None, src, PY_TEXT)
    got, reason = spo_run(fx, SPO_OTHER, "mv %s %s" % (src, moved))
    problems.append(spo_allowed("cp-mv 15, B's mv of the unrecorded file", got, reason))
    if got == "allow":
        os.replace(src, moved)   # the mv lands, as the harness would run it
    got, reason = spo_run(fx, SPO_WRITER, "python3 %s" % moved)
    problems.append(spo_allowed("cp-mv 15, A's run of the moved file", got, reason))
    got, reason = spo_run(fx, SPO_OTHER, "rm %s" % moved)
    problems.append(spo_allowed("cp-mv 15, B's rm of the moved file", got, reason))
    return spo_result(problems, "an mv of a file no record names gets no record: A's run and B's rm are allowed")


def spo_guard_crashes(log):
    """The messages of the `guard-crash` lines in a guard log. A guard crash fails open to allow, so the decision
    alone does not show it."""
    if not os.path.exists(log):
        return []
    with open(log, encoding="utf-8") as handle:
        lines = handle.read().split("\n")
    return [line.split("\t")[4] for line in lines if line.split("\t")[2:4] == ["crash", "guard-crash"]]


def spo_mv_chain_case():
    """Agent A writes src.py, and agent B copies it to c.py. B's one call moves c.py to d.py and back to c.py. The call
    is allowed, and the guard does not crash on it: the cycle between the two moves ends. What later runs of c.py read
    is not asserted."""
    fx = spo_fixture("cp-mv-chain")
    src = os.path.join(fx["scratch"], "src.py")
    mid = os.path.join(fx["scratch"], "c.py")
    dest = os.path.join(fx["scratch"], "d.py")
    cfg = os.path.join(os.path.dirname(fx["work"]), "cfg")   # this case's config folder, so its guard.log is its own
    os.makedirs(cfg, exist_ok=True)
    problems = [spo_scope(fx, "cp-mv 16", src)] + spo_wrote(fx, "cp-mv 16", SPO_WRITER, src, PY_TEXT)
    problems += spo_wrote(fx, "cp-mv 16", SPO_OTHER, mid, PY_TEXT, tool="Bash", command="cp %s %s" % (src, mid))
    chain = "mv %s %s && mv %s %s" % (mid, dest, dest, mid)
    got, reason = decide({"raw": None, "tool": "Bash", "cwd": fx["work"], "session": fx["sid"], "env_path": None,
                          "config": cfg, "agent_id": SPO_OTHER, "process_cwd": None, "temp": fx["tmp"],
                          "tool_input": {"command": chain}})
    problems.append(spo_allowed("cp-mv 16, B's mv chain in one call", got, reason))
    crashes = spo_guard_crashes(os.path.join(cfg, "guard.log"))
    if crashes:
        problems.append("cp-mv 16, the guard crashed on B's mv chain and failed open: %s" % crashes[0][:120])
    return spo_result(problems, "agent B's one call that moves its copy to d.py and back is allowed, with no guard crash")


def spo_cp_copier_folder_case():
    """Agent A writes src.py. Agent B copies it into the folder d, and removes the folder with rm -rf: allowed, since
    the file in it is B's copy. A third agent's rm -rf of d is refused. B's run of d/c.py is refused."""
    fx = spo_fixture("cp-copier-dir")
    src = os.path.join(fx["scratch"], "src.py")
    folder = os.path.join(fx["scratch"], "d")
    dest = os.path.join(folder, "c.py")
    os.makedirs(folder, exist_ok=True)
    problems = [spo_scope(fx, "cp-mv 11", src)] + spo_wrote(fx, "cp-mv 11", SPO_WRITER, src, PY_TEXT)
    problems += spo_wrote(fx, "cp-mv 11", SPO_OTHER, dest, PY_TEXT, tool="Bash", command="cp %s %s" % (src, dest))
    got, reason = spo_run(fx, SPO_OTHER, "python3 %s" % dest)
    problems.append(spo_refused("cp-mv 11, B's run of d/c.py", got, reason, (fx["scratch"], "c.py")))
    got, reason = spo_run(fx, SPO_THIRD, "rm -rf %s" % folder)
    problems.append(spo_refused("cp-mv 11, control: C's rm -rf of d", got, reason, (fx["scratch"], "c.py")))
    got, reason = spo_run(fx, SPO_OTHER, "rm -rf %s" % folder)
    problems.append(spo_allowed("cp-mv 11, B's rm -rf of d", got, reason))
    return spo_result(problems, "agent B may remove a folder that holds only its copy of A's file, and C may not")


def spo_cp_unrecorded_case():
    return spo_cp_keeps_cases("cp-keeps-none", "cp-mv 8", None, "agent B's copy of a file with no recorded writer is "
                                                                "B's, and B's run of it is allowed")


def spo_mv_approved_case():
    """Agent A writes probe2.py. Agent B's mv of it to m.py is refused. The owner types `override 15m` at 30 s, and
    B's mv at 60 s is lifted, so it lands. The mv carries A's record to m.py: A's run of m.py is allowed and B's run
    of it is refused."""
    fx = spo_fixture("mv-approved")
    config = ov_config("spo-mv-approved")
    probe = os.path.join(fx["scratch"], "probe2.py")
    moved = os.path.join(fx["scratch"], "m.py")
    banned = (fx["scratch"], "probe2.py", "m.py")
    problems = [spo_scope(fx, "mv approved", probe)] + spo_wrote(fx, "mv approved", SPO_WRITER, probe, PY_TEXT)

    def call(agent, tool, tool_input, seconds):
        return ov_call(tool, tool_input, fx["work"], config, fx["sid"], seconds, agent_id=agent, temp=fx["tmp"])

    mv = {"command": "mv %s %s" % (probe, moved)}
    got, reason = call(SPO_OTHER, "Bash", mv, 0)
    problems.append(spo_refused("mv approved, B's mv before the override", got, reason, banned))
    note = ov_type(config, fx["sid"], "override 15m", 30)
    got, reason = call(SPO_OTHER, "Bash", mv, 60)
    problems.append(spo_allowed("mv approved, B's mv under the override", got, reason))
    if got == "allow":
        os.rename(probe, moved)   # the approved mv lands its file at the new name
    later = OV_TIMED_SECONDS + 120   # the override typed at 30 s has ended by now
    got, reason = call(SPO_WRITER, "Bash", {"command": "python3 %s" % moved}, later)
    problems.append(spo_allowed("mv approved, A's run of m.py", got, reason))
    got, reason = call(SPO_OTHER, "Bash", {"command": "python3 %s" % moved}, later)
    problems.append(spo_refused("mv approved, B's run of m.py", got, reason, banned))
    if note and any(problems):
        problems.append("the override was not typed through override.grant: " + note)
    return spo_result(problems,
                      "an approved mv carries agent A's record to m.py: A's run is allowed, B's is refused")


def spo_mv_in_case():
    """Agent A moves a file from outside the scratchpad into the scratchpad as o.py. The move is A's write, so the
    record names A: B's run of o.py is refused, and A's run is allowed."""
    fx = spo_fixture("mv-in")
    source = os.path.join(fx["work"], "s_src.py")   # outside the scratchpad, in this case's folder
    write(source, PY_TEXT)
    dest = os.path.join(fx["scratch"], "o.py")
    problems = [spo_scope(fx, "mv in", dest)]
    got, reason = spo_call(fx, "Bash", SPO_WRITER, command="mv %s %s" % (source, dest))
    problems.append(spo_allowed("mv in, A's mv into the scratchpad", got, reason))
    if got == "allow":
        os.rename(source, dest)   # the mv lands its file at the new name
    got, reason = spo_run(fx, SPO_OTHER, "python3 %s" % dest)
    problems.append(spo_refused("mv in, B's run of o.py", got, reason, (fx["scratch"], "o.py")))
    got, reason = spo_run(fx, SPO_WRITER, "python3 %s" % dest)
    problems.append(spo_allowed("mv in, control: A's run of o.py", got, reason))
    return spo_result(problems, "agent B's run of a file agent A moved in from outside the scratchpad is refused")


def spo_cp_dir_case():
    """Agent A copies s.py into the scratchpad's dir/ folder with cp, so the copy lands at dir/s.py. Agent B's run
    of dir/s.py is refused, and A's run is allowed."""
    fx = spo_fixture("cp-dir")
    source = os.path.join(fx["work"], "s.py")   # outside the scratchpad, in this case's folder
    write(source, PY_TEXT)
    folder = os.path.join(fx["scratch"], "dir")
    os.makedirs(folder, exist_ok=True)
    dest = os.path.join(folder, "s.py")
    problems = [spo_scope(fx, "cp dir", dest)]
    problems += spo_wrote(fx, "cp dir", SPO_WRITER, dest, PY_TEXT, tool="Bash",
                          command="cp %s %s/" % (source, folder))
    got, reason = spo_run(fx, SPO_OTHER, "python3 %s" % dest)
    problems.append(spo_refused("cp dir, B's run of dir/s.py", got, reason, (fx["scratch"], "s.py")))
    got, reason = spo_run(fx, SPO_WRITER, "python3 %s" % dest)
    problems.append(spo_allowed("cp dir, control: A's run of dir/s.py", got, reason))
    return spo_result(problems,
                      "agent B's run of a script agent A copied into a folder of the scratchpad is refused")


def spo_b_file_runs(fx, name, dest, moved_name):
    """The two runs of a file agent B built and moved to `dest`: agent A's run is refused, since B wrote it, and
    B's own run is the control, which is allowed. Returns the problems."""
    got, reason = spo_run(fx, SPO_WRITER, "python3 %s" % dest)
    problems = [spo_refused(name + ", A's run of the file B built", got, reason, (fx["scratch"], moved_name))]
    got, reason = spo_run(fx, SPO_OTHER, "python3 %s" % dest)
    problems.append(spo_allowed(name + ", control: B's own run", got, reason))
    return problems


def spo_one_call_case(tag, name, moved_name, command_of, passed):
    """Agent B's one Bash call writes x.tmp and moves it to `moved_name`. `command_of(fx, tmp, dest)` builds the call.
    The call's write and move are both B's, so it is allowed, and A's run of the moved file is refused."""
    fx = spo_fixture(tag)
    tmp = os.path.join(fx["scratch"], "x.tmp")
    dest = os.path.join(fx["scratch"], moved_name)
    write(os.path.join(fx["work"], "src.py"), PY_TEXT)   # the copy's source, outside the scratchpad
    problems = [spo_scope(fx, name, dest)]
    problems += spo_wrote(fx, name, SPO_OTHER, dest, PY_TEXT, tool="Bash", command=command_of(fx, tmp, dest))
    problems += spo_b_file_runs(fx, name, dest, moved_name)
    return spo_result(problems, passed)


def spo_one_call_heredoc():
    return spo_one_call_case("one-call-heredoc", "one-call 1", "x.py",
                             lambda fx, tmp, dest: "cat > %s <<'EOF' && mv %s %s\n%sEOF" % (tmp, tmp, dest, PY_TEXT),
                             "agent B's heredoc to x.tmp and mv to x.py in one call: A's run of x.py is refused")


def spo_one_call_cp():
    return spo_one_call_case("one-call-cp", "one-call 2", "x.py",
                             lambda fx, tmp, dest: "cp %s %s && mv %s %s"
                             % (os.path.join(fx["work"], "src.py"), tmp, tmp, dest),
                             "agent B's cp to x.tmp and mv to x.py in one call: A's run of x.py is refused")


def spo_two_call_case():
    """Agent B writes x.tmp by a heredoc in one call, and moves it to x.py in the next. The move carries B's record,
    so A's run of x.py is refused. This is the control: the two-call form already records B."""
    fx = spo_fixture("two-call")
    tmp = os.path.join(fx["scratch"], "x.tmp")
    dest = os.path.join(fx["scratch"], "x.py")
    problems = [spo_scope(fx, "two-call", dest)]
    problems += spo_wrote(fx, "two-call", SPO_OTHER, tmp, PY_TEXT, tool="Bash",
                          command="cat > %s <<'EOF'\n%sEOF" % (tmp, PY_TEXT))
    got, reason = spo_call(fx, "Bash", SPO_OTHER, command="mv %s %s" % (tmp, dest))
    problems.append(spo_allowed("two-call, B's mv in the next call", got, reason))
    if got == "allow":
        os.rename(tmp, dest)   # the mv lands its file at the new name
    problems += spo_b_file_runs(fx, "two-call", dest, "x.py")
    return spo_result(problems, "agent B's two-call write then mv leaves the record with B: A's run is refused")


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


# Rule scratchpad-owner, a folder removed or moved. A record names a writer per file, so a folder has no record of
# its own: a rm or mv that names a folder must read the files under it. The incident's exact command text is unknown
# (it is not in the logs). These cases name the likely forms: the flags, a trailing slash, quotes, a variable, a glob,
# the scratchpad root, a nested folder and a mv. Each label starts `folder rm` or `folder move`.
SPO_FOLDER_SUB = ((SPO_WRITER, "sub/a.txt", "from A\n"), (SPO_WRITER, "sub/deep/b.txt", "from A deep\n"))
SPO_FOLDER_MIXED = ((SPO_WRITER, "mixed/a.txt", "from A\n"), (SPO_OTHER, "mixed/own.txt", "from B\n"))
SPO_FOLDER_OWN = ((SPO_OTHER, "bonly/x.txt", "from B\n"), (SPO_OTHER, "bonly/deep/y.txt", "from B\n"))
# Agent B's own folders beside agent A's `sub`: a brace list over two of them, and a parent segment back to its own.
SPO_FOLDER_BRACE_OWN = SPO_FOLDER_SUB + ((SPO_OTHER, "own1/x.txt", "from B\n"),
                                         (SPO_OTHER, "own2/y.txt", "from B\n"))
SPO_FOLDER_PARENT_OWN = SPO_FOLDER_SUB + ((SPO_OTHER, "own/x.txt", "from B\n"),
                                          (SPO_OTHER, "own/deep/y.txt", "from B\n"))
# Agent B's own file and folders, which it moves into agent A's `sub`: the move takes nothing from A.
SPO_FOLDER_MOVE_OWN = SPO_FOLDER_SUB + ((SPO_OTHER, "own.txt", "from B\n"),
                                        (SPO_OTHER, "own1/x.txt", "from B\n"),
                                        (SPO_OTHER, "own2/y.txt", "from B\n"))
# Agent A's second folder `d2`, which a numeric range over d1..d3 names.
SPO_FOLDER_RANGE = SPO_FOLDER_SUB + ((SPO_WRITER, "d2/f.txt", "from A\n"),)


def spo_folder_writes(fx, name, writes):
    """Each (agent, relative path, text) of `writes`, in order, under this case's scratchpad. An agent writes with
    Write, so its record names it. An agent of None writes outside the guard, as an editor would: no record is made."""
    problems = []
    for agent, rel, text in writes:
        path = os.path.join(fx["scratch"], rel)
        problems.append(spo_scope(fx, name, path))
        if agent is None:
            write(path, text)
        else:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            problems += spo_wrote(fx, name, agent, path, text)
    return problems


def spo_folder_case(tag, name, writes, agent, command_of, passed, want="deny"):
    """The files of `writes` are made, then `agent`'s call `command_of(scratchpad)` runs. With `want` "deny" the call
    is refused, and the refusal names scratchpad-owner, neither the folder nor the files. With "allow" it passes."""
    fx = spo_fixture(tag)
    problems = spo_folder_writes(fx, name, writes)
    got, reason = spo_run(fx, agent, command_of(fx["scratch"]))
    if want == "allow":
        problems.append(spo_allowed(name, got, reason))
    else:
        banned = (fx["scratch"],) + tuple(os.path.basename(rel) for _, rel, _ in writes)
        problems.append(spo_refused(name, got, reason, banned))
    return spo_result(problems, passed)


SPO_FOLDER_FORMS = (
    # (case tag, label, agent B's command for the folder at scratchpad path s)
    ("folder-rm-1", "folder rm 1, agent B's rm -rf of agent A's folder",
     lambda s: "rm -rf %s" % os.path.join(s, "sub")),
    ("folder-rm-2", "folder rm 2, agent B's rm -r of agent A's folder",
     lambda s: "rm -r %s" % os.path.join(s, "sub")),
    ("folder-rm-3", "folder rm 3, agent B's rm -fr of agent A's folder",
     lambda s: "rm -fr %s" % os.path.join(s, "sub")),
    ("folder-rm-4", "folder rm 4, agent B's rm -rf -- of agent A's folder",
     lambda s: "rm -rf -- %s" % os.path.join(s, "sub")),
    ("folder-rm-5", "folder rm 5, agent B's rm -rf of agent A's folder with a trailing slash",
     lambda s: "rm -rf %s/" % os.path.join(s, "sub")),
    ("folder-rm-6", "folder rm 6, agent B's rm -rf of agent A's folder in double quotes",
     lambda s: 'rm -rf "%s"' % os.path.join(s, "sub")),
    ("folder-rm-7", "folder rm 7, agent B's rm -rf of agent A's folder by a shell variable",
     lambda s: 'D=%s; rm -rf "$D"' % os.path.join(s, "sub")),
    ("folder-rm-8", "folder rm 8, agent B's rm -rf of the files in agent A's folder by a glob",
     lambda s: "rm -rf %s/*" % os.path.join(s, "sub")),
    ("folder-rm-9", "folder rm 9, agent B's rm -rf of every folder in the scratchpad by a glob",
     lambda s: "rm -rf %s/*" % s),
    ("folder-rm-10", "folder rm 10, agent B's rm -rf of the scratchpad root",
     lambda s: "rm -rf %s" % s),
    ("folder-rm-11", "folder rm 11, agent B's rm -rf of a nested folder holding only agent A's file",
     lambda s: "rm -rf %s" % os.path.join(s, "sub", "deep")),
    ("folder-move-1", "folder move 1, agent B's mv of agent A's folder",
     lambda s: "mv %s %s" % (os.path.join(s, "sub"), os.path.join(s, "moved"))),
    # A brace list nested in another one: bash expands the inner list too, so `sub` is one of the words.
    ("folder-rm-19", "folder rm 19, agent B's rm -rf of agent A's folder in a nested brace list",
     lambda s: "rm -rf %s/{x,{sub,y}}" % s),
    # A brace list inside a name: `su{b,c}` is `sub` and `suc`, so the text before the list is kept.
    ("folder-rm-20", "folder rm 20, agent B's rm -rf of agent A's folder by a brace list inside its name",
     lambda s: "rm -rf %s/su{b,c}" % s),
    # An empty brace element: `sub{,.bak}` is `sub` and `sub.bak`.
    ("folder-rm-21", "folder rm 21, agent B's rm -rf of agent A's folder by a brace list with an empty element",
     lambda s: "rm -rf %s/sub{,.bak}" % s),
    # A letter range: `{s..u}ub` is `sub`, `tub` and `uub`.
    ("folder-rm-22", "folder rm 22, agent B's rm -rf of agent A's folder by a letter range",
     lambda s: "rm -rf %s/{s..u}ub" % s),
    # A brace list is expanded by bash before rm runs, so each name in it is a folder to remove.
    ("folder-rm-13", "folder rm 13, agent B's rm -rf of agent A's folder in a brace list, the folder first",
     lambda s: "rm -rf %s/{sub,nothing}" % s),
    ("folder-rm-14", "folder rm 14, agent B's rm -rf of agent A's folder in a brace list, the folder last",
     lambda s: "rm -rf %s/{nothing,sub}" % s),
    ("folder-rm-15", "folder rm 15, agent B's rm -rf of agent A's folder in a brace list with a glob",
     lambda s: "rm -rf %s/{sub,x}/*" % s),
    # A parent segment names the folder it returns to, so the walk must read the folder it resolves to.
    ("folder-rm-16", "folder rm 16, agent B's rm -rf of agent A's folder through a parent segment, S/../S/sub",
     lambda s: "rm -rf %s" % os.path.join(s, "..", os.path.basename(s), "sub")),
    ("folder-rm-17", "folder rm 17, agent B's rm -rf of agent A's folder through a parent segment, S/sub/../sub",
     lambda s: "rm -rf %s" % os.path.join(s, "sub", "..", "sub")),
    ("folder-rm-18", "folder rm 18, agent B's rm -rf of agent A's folder through a parent segment, S/sub/deep/..",
     lambda s: "rm -rf %s" % os.path.join(s, "sub", "deep", "..")),
)


def spo_made_folder_case():
    """Agent B makes an empty folder with mkdir, which the guard allows. B's rm -rf of that folder is allowed: it holds
    no file, so no file under it has a record."""
    fx = spo_fixture("folder-made")
    made = os.path.join(fx["scratch"], "made")
    problems = [spo_scope(fx, "folder rm control 4", made)]
    got, reason = spo_run(fx, SPO_OTHER, "mkdir -p %s" % made)
    problems.append(spo_allowed("folder rm control 4, agent B's mkdir of the folder", got, reason))
    os.makedirs(made, exist_ok=True)   # the mkdir lands its folder, as the shell would
    got, reason = spo_run(fx, SPO_OTHER, "rm -rf %s" % made)
    problems.append(spo_allowed("folder rm control 4, agent B's rm -rf of the empty folder", got, reason))
    return spo_result(problems, "agent B's rm -rf of an empty folder it made is allowed")


def spo_outside_folder_case():
    """Agent B's rm -rf of a folder that is outside every scratchpad, a working folder with no checkout. No scratchpad
    rule applies to it, so it is allowed."""
    fx = spo_fixture("folder-outside")
    folder = os.path.join(fx["work"], "other")
    problems = [spo_outside("folder rm control 5", folder)]
    write(os.path.join(folder, "x.txt"), "plain\n")
    write(os.path.join(folder, "deep", "y.txt"), "plain\n")
    got, reason = spo_run(fx, SPO_OTHER, "rm -rf %s" % folder)
    problems.append(spo_allowed("folder rm control 5, agent B's rm -rf of a folder outside a scratchpad", got, reason))
    return spo_result(problems, "agent B's rm -rf of a folder outside any scratchpad is allowed")


# Rule scratchpad-owner, the walk's two limits. The folder check reads at most SCRATCHPAD_WALK_CAP entries, and it does
# not follow a symlink below the folder it is given. The guard runs as its own process for each case, so the cap is not
# patched: each case builds a real folder over the cap. A bare folder's entries come in no fixed order, so the cap cases
# name their entries by a glob. The guard sorts a glob's matches, so `big` is read whole before `zz_a.txt`, and the
# boundary is exact.
SPO_CAP_DIR = "big"        # the folder of unrecorded files, the first match of the glob
SPO_CAP_FILE = "zz_a.txt"  # agent A's file, the second match
SPO_WALK_CAP_DEFAULT = 5000   # the cap the rule states, used only where the guard names no cap


def spo_walk_cap():
    """The folder walk's cap, read from the guard's module, its one home. A product that names no cap reads as the
    stated default, so the case fails on what the guard does, not on a missing name."""
    import guard_shared_tree
    return getattr(guard_shared_tree, "SCRATCHPAD_WALK_CAP", SPO_WALK_CAP_DEFAULT)


def spo_cap_case(tag, name, past, passed):
    """Folder `capfold` holds `big`, which holds unrecorded files, and agent A's file `zz_a.txt`. B's rm -rf of
    `capfold/*` reads `big` (one entry), its children, then the file. With `past` False the children number the cap
    less two, so the file is the last entry the walk reads, and the call is refused. With `past` True they number the
    cap less one, so the cap stops the walk before the file, and the call passes."""
    import glob
    cap = spo_walk_cap()
    fx = spo_fixture(tag)
    folder = os.path.join(fx["scratch"], "capfold")
    big = os.path.join(folder, SPO_CAP_DIR)
    fillers = cap - 1 if past else cap - 2
    problems = [spo_scope(fx, name, big)]
    for index in range(fillers):
        write(os.path.join(big, "n%05d.txt" % index), "plain\n")
    problems += spo_folder_writes(fx, name, ((SPO_WRITER, "capfold/%s" % SPO_CAP_FILE, "from A\n"),))
    listed = sorted(os.path.basename(path) for path in glob.glob(os.path.join(folder, "*")))
    if listed != sorted([SPO_CAP_DIR, SPO_CAP_FILE]):
        problems.append("%s: setup, the glob capfold/* lists %s, want %s" % (name, listed, [SPO_CAP_DIR, SPO_CAP_FILE]))
    held = len(os.listdir(big))
    if held != fillers:
        problems.append("%s: setup, %s holds %d entries, want %d" % (name, SPO_CAP_DIR, held, fillers))
    got, reason = spo_run(fx, SPO_OTHER, "rm -rf %s/*" % folder)
    if past:
        problems.append(spo_allowed(name, got, reason))
    else:
        problems.append(spo_refused(name, got, reason, (fx["scratch"], SPO_CAP_FILE)))
    return spo_result(problems, passed)


def spo_symlink_inside_case():
    """Agent A's file sits in `keep`, and folder `symfold` holds only a symlink `ln` to `keep`. B's rm -rf of `symfold`
    removes the link and leaves `keep` alone, so the call passes: the walk does not follow the link."""
    fx = spo_fixture("folder-walk-link-1")
    name = "folder rm walk link 1"
    keep = os.path.join(fx["scratch"], "keep")
    folder = os.path.join(fx["scratch"], "symfold")
    link = os.path.join(folder, "ln")
    problems = [spo_scope(fx, name, keep), spo_scope(fx, name, folder)]
    problems += spo_folder_writes(fx, name, ((SPO_WRITER, "keep/a.txt", "from A\n"),))
    os.makedirs(folder, exist_ok=True)
    os.symlink(keep, link)
    if os.path.realpath(link) != os.path.realpath(keep):
        problems.append("%s: setup, %s does not lead to %s" % (name, link, keep))
    got, reason = spo_run(fx, SPO_OTHER, "rm -rf %s" % folder)
    problems.append(spo_allowed("%s, agent B's rm -rf of a folder whose link leads to agent A's file" % name, got, reason))
    return spo_result(problems, "agent B's rm -rf of a folder holding a link to agent A's file is allowed, as the link "
                                "is not followed")


def spo_symlink_out_case():
    """Folder `d1` holds a symlink `ln` to `target`, a folder outside every scratchpad that holds as many unrecorded files
    as the cap. Folder `zz` holds agent A's file. B's rm -rf of the scratchpad's entries, `S/*`, is refused: the walk
    skips `ln` and reads `zz/a.txt`. A walk that followed `ln` would spend the cap on `target` and stop before `zz`."""
    import glob
    cap = spo_walk_cap()
    fx = spo_fixture("folder-walk-link-2")
    name = "folder rm walk link 2"
    target = os.path.join(fx["work"], "target")
    d1 = os.path.join(fx["scratch"], "d1")
    link = os.path.join(d1, "ln")
    problems = [spo_outside(name, target)]
    for index in range(cap):
        write(os.path.join(target, "n%05d.txt" % index), "plain\n")
    os.makedirs(d1, exist_ok=True)
    os.symlink(target, link)
    problems += spo_folder_writes(fx, name, ((SPO_WRITER, "zz/a.txt", "from A\n"),))
    listed = sorted(os.path.basename(path) for path in glob.glob(os.path.join(fx["scratch"], "*")))
    if listed != ["d1", "zz"]:
        problems.append("%s: setup, the glob scratchpad/* lists %s, want ['d1', 'zz']" % (name, listed))
    if os.path.realpath(link) != os.path.realpath(target):
        problems.append("%s: setup, %s does not lead to %s" % (name, link, target))
    if len(os.listdir(target)) < cap:
        problems.append("%s: setup, %s holds fewer entries than the walk cap %d" % (name, target, cap))
    got, reason = spo_run(fx, SPO_OTHER, "rm -rf %s/*" % fx["scratch"])
    problems.append(spo_refused(name, got, reason, (fx["scratch"], "a.txt")))
    return spo_result(problems, "agent B's rm -rf of the scratchpad's entries is refused: the link out is not followed, "
                                "and agent A's file is read")


def spo_root_link_case(tag, name, command, want, passed):
    """Agent A's file sits in `tgt`, and `rl` is a symlink to `tgt` at the top of the scratchpad. `command` is B's rm
    of `rl`. Without a trailing slash rm unlinks the link and leaves the target alone, so the call is allowed. With a
    trailing slash the shell reads through the link and empties the target, so the call is refused."""
    fx = spo_fixture(tag)
    target = os.path.join(fx["scratch"], "tgt")
    link = os.path.join(fx["scratch"], "rl")
    problems = [spo_scope(fx, name, link)]
    problems += spo_folder_writes(fx, name, ((SPO_WRITER, "tgt/a.txt", "from A\n"),))
    os.symlink(target, link)
    if os.path.realpath(link) != os.path.realpath(target):
        problems.append("%s: setup, %s does not lead to %s" % (name, link, target))
    got, reason = spo_run(fx, SPO_OTHER, command % link)
    if want == "allow":
        problems.append(spo_allowed(name, got, reason))
    else:
        problems.append(spo_refused(name, got, reason, (fx["scratch"], "a.txt")))
    return spo_result(problems, passed)


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
# The folder forms: agent A's files sit under sub/ and sub/deep/, and agent B's call names the folder or its files.
for _tag, _label, _command_of in SPO_FOLDER_FORMS:
    spo_register("scratchpad-owner: %s: refused" % _label,
                 lambda t=_tag, n=_label, c=_command_of: spo_folder_case(t, n, SPO_FOLDER_SUB, SPO_OTHER, c,
                                                                         "%s is refused" % n))
spo_register("scratchpad-owner: folder rm 12, agent B's rm -rf of a folder holding agent B's file and agent A's file: "
             "refused",
             lambda: spo_folder_case("folder-rm-12", "folder rm 12", SPO_FOLDER_MIXED, SPO_OTHER,
                                     lambda s: "rm -rf %s" % os.path.join(s, "mixed"),
                                     "agent B's rm -rf of a folder holding both agents' files is refused"))
spo_register("scratchpad-owner: folder rm pin 1, agent B's rm of agent A's file inside a folder: refused",
             lambda: spo_folder_case("folder-pin-1", "folder rm pin 1", SPO_FOLDER_SUB, SPO_OTHER,
                                     lambda s: "rm %s" % os.path.join(s, "sub", "a.txt"),
                                     "agent B's rm of agent A's file inside a folder is refused"))
spo_register("scratchpad-owner: folder rm control 1, agent A's rm -rf of its own folder S/sub: allowed",
             lambda: spo_folder_case("folder-ctl-1", "folder rm control 1", SPO_FOLDER_SUB, SPO_WRITER,
                                     lambda s: "rm -rf %s" % os.path.join(s, "sub"),
                                     "agent A's rm -rf of its own folder is allowed", want="allow"))
spo_register("scratchpad-owner: folder rm control 2, agent B's rm -rf of a folder holding only B's files: allowed",
             lambda: spo_folder_case("folder-ctl-2", "folder rm control 2", SPO_FOLDER_OWN, SPO_OTHER,
                                     lambda s: "rm -rf %s" % os.path.join(s, "bonly"),
                                     "agent B's rm -rf of a folder holding only its own files is allowed",
                                     want="allow"))
spo_register("scratchpad-owner: folder rm control 3, agent B's rm -rf of a folder nobody recorded: allowed",
             lambda: spo_folder_case("folder-ctl-3", "folder rm control 3",
                                     ((None, "loose/x.txt", "plain\n"), (None, "loose/deep/y.txt", "plain\n")),
                                     SPO_OTHER, lambda s: "rm -rf %s" % os.path.join(s, "loose"),
                                     "agent B's rm -rf of a folder nobody recorded is allowed", want="allow"))
spo_register("scratchpad-owner: folder rm control 4, agent B's rm -rf of an empty folder it made: allowed",
             spo_made_folder_case)
spo_register("scratchpad-owner: folder rm control 5, agent B's rm -rf of a folder outside any scratchpad: allowed",
             spo_outside_folder_case)
spo_register("scratchpad-owner: folder rm control 6, agent B's rm -rf of S/{sub}, one brace element bash leaves "
             "literal: allowed",
             lambda: spo_folder_case("folder-ctl-6", "folder rm control 6", SPO_FOLDER_SUB, SPO_OTHER,
                                     lambda s: "rm -rf %s/{sub}" % s,
                                     "agent B's rm -rf of a one-element brace names no folder and is allowed",
                                     want="allow"))
spo_register("scratchpad-owner: folder rm control 7, agent B's rm -rf of S/{own1,own2}, two folders of its own: "
             "allowed",
             lambda: spo_folder_case("folder-ctl-7", "folder rm control 7", SPO_FOLDER_BRACE_OWN, SPO_OTHER,
                                     lambda s: "rm -rf %s/{own1,own2}" % s,
                                     "agent B's rm -rf of a brace list of its own folders is allowed", want="allow"))
spo_register("scratchpad-owner: folder rm control 8, agent B's rm -rf of S/own/../own, its own folder: allowed",
             lambda: spo_folder_case("folder-ctl-8", "folder rm control 8", SPO_FOLDER_PARENT_OWN, SPO_OTHER,
                                     lambda s: "rm -rf %s" % os.path.join(s, "own", "..", "own"),
                                     "agent B's rm -rf of its own folder through a parent segment is allowed",
                                     want="allow"))
spo_register("scratchpad-owner: folder rm 23, agent B's rm -rf of agent A's folder in a numeric range: refused",
             lambda: spo_folder_case("folder-rm-23", "folder rm 23, agent B's rm -rf of agent A's folder in a numeric "
                                     "range", SPO_FOLDER_RANGE, SPO_OTHER,
                                     lambda s: "rm -rf %s/d{1..3}" % s,
                                     "agent B's rm -rf of a numeric range naming agent A's folder is refused"))
spo_register("scratchpad-owner: folder rm control 9, agent B's rm -rf of a numeric range naming no folder: allowed",
             lambda: spo_folder_case("folder-ctl-9", "folder rm control 9, agent B's rm -rf of a numeric range naming "
                                     "no folder", SPO_FOLDER_RANGE, SPO_OTHER,
                                     lambda s: "rm -rf %s/d{5..6}" % s,
                                     "agent B's rm -rf of a numeric range with no folder in it is allowed",
                                     want="allow"))
# Agent B's own file or folders moved into agent A's folder: the move takes nothing from A, so it passes. A move that
# takes A's file out of its folder is refused, and a copy of A's folder takes nothing away.
spo_register("scratchpad-owner: folder move control 1, agent B's mv of its own file into agent A's folder: allowed",
             lambda: spo_folder_case("folder-move-ctl-1", "folder move control 1, agent B's mv of its own file into "
                                     "agent A's folder", SPO_FOLDER_MOVE_OWN, SPO_OTHER,
                                     lambda s: "mv %s %s/" % (os.path.join(s, "own.txt"), os.path.join(s, "sub")),
                                     "agent B's mv of its own file into agent A's folder is allowed", want="allow"))
spo_register("scratchpad-owner: folder move control 2, agent B's mv of its own folder into agent A's folder: allowed",
             lambda: spo_folder_case("folder-move-ctl-2", "folder move control 2, agent B's mv of its own folder into "
                                     "agent A's folder", SPO_FOLDER_MOVE_OWN, SPO_OTHER,
                                     lambda s: "mv %s %s" % (os.path.join(s, "own1"), os.path.join(s, "sub")),
                                     "agent B's mv of its own folder into agent A's folder is allowed", want="allow"))
spo_register("scratchpad-owner: folder move control 3, agent B's mv of a brace list of its own folders into agent A's "
             "folder: allowed",
             lambda: spo_folder_case("folder-move-ctl-3", "folder move control 3, agent B's mv of a brace list of its "
                                     "own folders into agent A's folder", SPO_FOLDER_MOVE_OWN, SPO_OTHER,
                                     lambda s: "mv %s/{own1,own2} %s/" % (s, os.path.join(s, "sub")),
                                     "agent B's mv of a brace list of its own folders into agent A's folder is allowed",
                                     want="allow"))
spo_register("scratchpad-owner: folder move control 4, agent B's mv -t of its own file into agent A's folder: allowed",
             lambda: spo_folder_case("folder-move-ctl-4", "folder move control 4, agent B's mv -t of its own file into "
                                     "agent A's folder", SPO_FOLDER_MOVE_OWN, SPO_OTHER,
                                     lambda s: "mv -t %s %s" % (os.path.join(s, "sub"), os.path.join(s, "own.txt")),
                                     "agent B's mv -t of its own file into agent A's folder is allowed", want="allow"))
spo_register("scratchpad-owner: folder move control 5, agent B's mv of its own file to a new name in agent A's folder: "
             "allowed",
             lambda: spo_folder_case("folder-move-ctl-5", "folder move control 5, agent B's mv of its own file to a new "
                                     "name in agent A's folder", SPO_FOLDER_MOVE_OWN, SPO_OTHER,
                                     lambda s: "mv %s %s" % (os.path.join(s, "own.txt"),
                                                             os.path.join(s, "sub", "new.txt")),
                                     "agent B's mv of its own file to a new name in agent A's folder is allowed",
                                     want="allow"))
spo_register("scratchpad-owner: folder move control 6, agent B's cp -r of agent A's folder to a new name: allowed",
             lambda: spo_folder_case("folder-move-ctl-6", "folder move control 6, agent B's cp -r of agent A's folder to "
                                     "a new name", SPO_FOLDER_MOVE_OWN, SPO_OTHER,
                                     lambda s: "cp -r %s %s" % (os.path.join(s, "sub"), os.path.join(s, "copy")),
                                     "agent B's cp -r of agent A's folder to a new name is allowed", want="allow"))
spo_register("scratchpad-owner: folder move 2, agent B's mv of agent A's file out of its folder: refused",
             lambda: spo_folder_case("folder-move-2", "folder move 2, agent B's mv of agent A's file out of its folder",
                                     SPO_FOLDER_MOVE_OWN, SPO_OTHER,
                                     lambda s: "mv %s %s" % (os.path.join(s, "sub", "a.txt"),
                                                             os.path.join(s, "mine.txt")),
                                     "agent B's mv of agent A's file out of its folder is refused"))
# Agent B's one call moves its own file into agent A's folder `sub`, and another word of the same call names that folder
# too. A folder is walked, not dropped, when another word names it: each of these calls is refused, since it removes or
# moves A's folder or A's file. Each form is a plain mistake, a move and a clean-up typed as one line.
SPO_MOVE_INTO_FORMS = (
    ("folder-move-3", "folder move 3, agent B's mv of its own file into agent A's folder, then rm -rf of that folder",
     lambda s: "mv %s %s/ && rm -rf %s" % (os.path.join(s, "own.txt"), os.path.join(s, "sub"),
                                            os.path.join(s, "sub"))),
    ("folder-move-4", "folder move 4, agent B's mv of its own file into agent A's folder, then a mv of that folder",
     lambda s: "mv %s %s/; mv %s %s" % (os.path.join(s, "own.txt"), os.path.join(s, "sub"),
                                        os.path.join(s, "sub"), os.path.join(s, "moved"))),
    ("folder-move-5", "folder move 5, agent B's mv -t of its own file into agent A's folder, then rm -rf of that folder",
     lambda s: "mv -t %s %s && rm -rf %s/" % (os.path.join(s, "sub"), os.path.join(s, "own.txt"),
                                              os.path.join(s, "sub"))),
    ("folder-move-6", "folder move 6, agent B's rm -rf of agent A's folder, then a mv of its own file into it",
     lambda s: "rm -rf %s && mv %s %s/" % (os.path.join(s, "sub"), os.path.join(s, "own.txt"),
                                           os.path.join(s, "sub"))),
    ("folder-move-7", "folder move 7, agent B's mv of its own file into a brace list naming agent A's folder",
     lambda s: "mv %s %s/{sub,own1}/" % (os.path.join(s, "own.txt"), s)),
    ("folder-move-8", "folder move 8, agent B's sudo mv of agent A's folder, then a mv of its own file into it",
     lambda s: "sudo mv %s %s; mv %s %s/" % (os.path.join(s, "sub"), os.path.join(s, "x"),
                                             os.path.join(s, "own.txt"), os.path.join(s, "sub"))),
)
for _tag, _label, _command_of in SPO_MOVE_INTO_FORMS:
    spo_register("scratchpad-owner: %s: refused" % _label,
                 lambda t=_tag, n=_label, c=_command_of: spo_folder_case(t, n, SPO_FOLDER_MOVE_OWN, SPO_OTHER, c,
                                                                         "%s is refused" % n))
# The walk's limits: the cap at its boundary (over a real folder, as the guard runs in its own process), and the symlinks.
spo_register("scratchpad-owner: folder rm walk cap 1, agent B's rm -rf of a folder's entries, agent A's file the last "
             "entry inside the walk cap: refused",
             lambda: spo_cap_case("folder-walk-cap-1", "folder rm walk cap 1", False,
                                  "agent A's file inside the walk cap is read, and agent B's rm -rf is refused"))
spo_register("scratchpad-owner: folder rm walk cap 2, agent B's rm -rf of a folder's entries, agent A's file the first "
             "entry past the walk cap: allowed",
             lambda: spo_cap_case("folder-walk-cap-2", "folder rm walk cap 2", True,
                                  "agent A's file past the walk cap is not read, and agent B's rm -rf is allowed"))
spo_register("scratchpad-owner: folder rm walk link 1, agent B's rm -rf of a folder whose symlink leads to agent A's "
             "file inside the scratchpad: allowed", spo_symlink_inside_case)
spo_register("scratchpad-owner: folder rm walk link 2, agent B's rm -rf of the scratchpad's entries, a symlink out to a "
             "folder past the cap: refused", spo_symlink_out_case)
spo_register("scratchpad-owner: folder rm walk link 3, agent B's rm -rf of a symlink to a folder holding agent A's "
             "file, no trailing slash: allowed",
             lambda: spo_root_link_case("folder-walk-link-3", "folder rm walk link 3", "rm -rf %s", "allow",
                                        "agent B's rm -rf of the link unlinks it, and the target's file is not read"))
spo_register("scratchpad-owner: folder rm walk link 4, agent B's rm -rf of a symlink with a trailing slash to a folder "
             "holding agent A's file: refused",
             lambda: spo_root_link_case("folder-walk-link-4", "folder rm walk link 4", "rm -rf %s/", "deny",
                                        "agent B's rm -rf of the link with a trailing slash is refused"))
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


# Rule scratchpad-owner, the run forms and the copy and move destinations. Agent A writes its file; agent B's call
# runs it or moves it. B's call is refused, and A's same call is the control, which is allowed.
for _tag, _form, _script, _text, _template in SPO_RUNNER_FORMS:
    spo_register("scratchpad-owner: runner %s: agent B's run of agent A's script is refused" % _form,
                 spo_runner_case(_tag, _form, _script, _text, _template))
spo_register("scratchpad-owner: runner control, agent B's python3 -m pytest with no file is allowed",
             lambda: spo_text_case("ctl-pytest", "runner control, python3 -m pytest",
                                   lambda probe, outside: "python3 -m pytest",
                                   "agent B's python3 -m pytest with no file is allowed"))
spo_register("scratchpad-owner: runner control, agent B's cat of agent A's script is allowed",
             lambda: spo_text_case("ctl-cat", "runner control, cat F",
                                   lambda probe, outside: "cat %s" % probe,
                                   "agent B's cat of agent A's script is allowed"))
spo_register("scratchpad-owner: runner control, agent B's out=$(cat F) of agent A's script is allowed",
             lambda: spo_text_case("ctl-subst-cat", "runner control, out=$(cat F)",
                                   lambda probe, outside: "out=$(cat %s)" % probe,
                                   "agent B's out=$(cat F) of agent A's script is allowed"))
# A file as an argument is data for the command, not the run: the refused forms of the same runner (`uv run F`,
# `npx tsx F`, `bun run F`) are the rows uv, npx-tsx and bun above, and `uv run python F` is the control below.
# Agent B's own script is relative, so it lies outside the scratchpad, and agent A's file is the only one named.
spo_register("scratchpad-owner: argument 1, agent B's uv run python mine.py with agent A's script as an argument: "
             "allowed", lambda: spo_text_case("arg-uv-python", "argument 1, uv run python mine.py F",
                                              lambda probe, outside: "uv run python mine.py %s" % probe,
                                              "agent B's uv run python mine.py F, with F as an argument, is allowed"))
spo_register("scratchpad-owner: argument 2, agent B's npx tsx s.ts with agent A's script as an argument: allowed",
             lambda: spo_text_case("arg-npx-tsx", "argument 2, npx tsx s.ts F",
                                   lambda probe, outside: "npx tsx s.ts %s" % probe,
                                   "agent B's npx tsx s.ts F, with F as an argument, is allowed"))
spo_register("scratchpad-owner: argument 3, agent B's uv run ruff check with agent A's script as an argument: allowed",
             lambda: spo_text_case("arg-ruff", "argument 3, uv run ruff check F",
                                   lambda probe, outside: "uv run ruff check %s" % probe,
                                   "agent B's uv run ruff check F is allowed"))
spo_register("scratchpad-owner: argument 4, agent B's uv run mypy with agent A's script as an argument: allowed",
             lambda: spo_text_case("arg-mypy", "argument 4, uv run mypy F",
                                   lambda probe, outside: "uv run mypy %s" % probe,
                                   "agent B's uv run mypy F is allowed"))
spo_register("scratchpad-owner: argument control 1, agent B's python3 mine.py with agent A's script as an argument: "
             "allowed", lambda: spo_text_case("arg-ctl-python", "argument control 1, python3 mine.py F",
                                              lambda probe, outside: "python3 mine.py %s" % probe,
                                              "agent B's python3 mine.py F, with F as an argument, is allowed"))
spo_register("scratchpad-owner: argument control 2, agent B's uv run python F with agent A's script is refused",
             lambda: spo_run_case("arg-ctl-uv-python", "argument control 2, uv run python F", "probe2.py",
                                  lambda fx, p: "uv run python %s" % p,
                                  "agent B's uv run python F, the file as the program, is refused"))


def spo_data_case(tag, name, data_name, text, command_of, passed):
    """Agent A writes `data_name` as a data file. Agent B's call `command_of(path)` passes it after the script, or as
    a flag's value, and runs no scratchpad file: allowed."""
    fx = spo_fixture(tag)
    path = os.path.join(fx["scratch"], data_name)
    problems = [spo_scope(fx, name, path)] + spo_wrote(fx, name, SPO_WRITER, path, text)
    got, reason = spo_run(fx, SPO_OTHER, command_of(path))
    problems.append(spo_allowed(name, got, reason))
    return spo_result(problems, passed)


# A file after a verb runner's script is an argument of that script (`uv run -q mine.py F`, `npx tsx --watch s.ts F`,
# `deno run -A mine.ts F`), and a file a flag takes as its value is not run (`uv run --env-file F python mine.py`).
# Agent B's own script is relative, so it lies outside the scratchpad, and agent A's file is the only one named.
spo_register("scratchpad-owner: argument 5, agent B's uv run -q mine.py with agent A's data.csv as an argument: "
             "allowed", lambda: spo_data_case("arg-5", "argument 5, uv run -q mine.py D", "data.csv", "a,b\n",
                                             lambda p: "uv run -q mine.py %s" % p,
                                             "agent B's uv run -q mine.py D, with D as an argument, is allowed"))
spo_register("scratchpad-owner: argument 6, agent B's uv run --no-sync mine.py with agent A's data.csv as an "
             "argument: allowed", lambda: spo_data_case("arg-6", "argument 6, uv run --no-sync mine.py D",
                                                      "data.csv", "a,b\n",
                                                      lambda p: "uv run --no-sync mine.py %s" % p,
                                                      "agent B's uv run --no-sync mine.py D is allowed"))
spo_register("scratchpad-owner: argument 7, agent B's npx tsx --watch s.ts with agent A's data.csv as an argument: "
             "allowed", lambda: spo_data_case("arg-7", "argument 7, npx tsx --watch s.ts D", "data.csv", "a,b\n",
                                             lambda p: "npx tsx --watch s.ts %s" % p,
                                             "agent B's npx tsx --watch s.ts D is allowed"))
spo_register("scratchpad-owner: argument 8, agent B's deno run -A mine.ts with agent A's data.csv as an argument: "
             "allowed", lambda: spo_data_case("arg-8", "argument 8, deno run -A mine.ts D", "data.csv", "a,b\n",
                                             lambda p: "deno run -A mine.ts %s" % p,
                                             "agent B's deno run -A mine.ts D is allowed"))
spo_register("scratchpad-owner: argument 9, agent B's uv run --env-file with agent A's e.txt as its value, then "
             "python mine.py: allowed", lambda: spo_data_case("arg-9", "argument 9, uv run --env-file D", "e.txt",
                                                            "A=1\n",
                                                            lambda p: "uv run --env-file %s python mine.py" % p,
                                                            "agent B's uv run --env-file D python mine.py is allowed"))
spo_register("scratchpad-owner: argument 10, agent B's uv run --with-requirements with agent A's r.txt as its value, "
             "then python x.py: allowed", lambda: spo_data_case("arg-10", "argument 10, uv run --with-requirements D",
                                                              "r.txt", "requests\n",
                                                              lambda p: "uv run --with-requirements %s python x.py"
                                                              % p,
                                                              "agent B's uv run --with-requirements D python x.py is "
                                                              "allowed"))
spo_register("scratchpad-owner: argument control 3, agent B's uv run -q F, the file as the script word: refused",
             lambda: spo_run_case("arg-ctl-uv-q", "argument control 3, uv run -q F", "f.py",
                                  lambda fx, p: "uv run -q %s" % p,
                                  "agent B's uv run -q F, the file as the script word, is refused"))
spo_register("scratchpad-owner: argument control 4, agent B's npx tsx --watch F, the file as the script word: refused",
             lambda: spo_run_case("arg-ctl-npx-watch", "argument control 4, npx tsx --watch F", "probe2.ts",
                                  lambda fx, p: "npx tsx --watch %s" % p,
                                  "agent B's npx tsx --watch F, the file as the script word, is refused",
                                  text=TS_TEXT))
spo_register("scratchpad-owner: argument control 5, agent B's deno run -A F, the file as the script word: refused",
             lambda: spo_run_case("arg-ctl-deno-a", "argument control 5, deno run -A F", "probe2.ts",
                                  lambda fx, p: "deno run -A %s" % p,
                                  "agent B's deno run -A F, the file as the script word, is refused", text=TS_TEXT))
# A verb runner's wrapper (`timeout 60`) hands on its command, so the program the wrapper runs is the script word.
spo_register("scratchpad-owner: argument pin, agent B's uv run timeout 60 python3 F, the file as the wrapped "
             "program: refused", lambda: spo_run_case("arg-pin-timeout", "argument pin, uv run timeout 60 python3 F",
                                                      "f.py", lambda fx, p: "uv run timeout 60 python3 %s" % p,
                                                      "agent B's uv run timeout 60 python3 F is refused"))
spo_register("scratchpad-owner: runner x=$(python3 F), an open substitution in an assignment: agent B's run is "
             "refused", spo_runner_case("subst-open-ctl", "x=$(python3 F)", "probe2.py", PY_TEXT, "x=$(python3 %s)"))
spo_register("scratchpad-owner: cp-mv 1 agent B's run of a script agent A copied into the scratchpad with cp: "
             "refused", spo_cp_in_case)
spo_register("scratchpad-owner: cp-mv 2 agent B's run of a file agent A moved to a new name with mv: refused",
             spo_mv_carry_case)
spo_register("scratchpad-owner: cp-mv 3 agent B copies agent A's file with cp, and runs the copy: refused",
             spo_cp_own_case)
spo_register("scratchpad-owner: cp-mv 7 agent B copies its own file with cp, and runs the copy: allowed",
             spo_cp_own_file_case)
spo_register("scratchpad-owner: cp-mv 9 the top-level session's cp of agent A's file, then agent B's run of the copy: "
             "allowed", spo_cp_top_level_case)
spo_register("scratchpad-owner: cp-mv 10 agent B's copy of agent A's file: B's run is refused, B's re-copy, "
             "rewrite and rm are allowed, and A's and C's rewrite are refused", spo_cp_copier_case)
spo_register("scratchpad-owner: cp-mv 12 agent B's mv of its copy of agent A's file, in two calls: C's rm is "
             "refused and B's is allowed", spo_cp_mv_two_call)
spo_register("scratchpad-owner: cp-mv 13 agent B's cp and mv of agent A's file in one call: C's rm is refused and "
             "B's is allowed", spo_cp_mv_one_call)
spo_register("scratchpad-owner: cp-mv 14 the top-level session's mv of agent B's copy of agent A's file: C's rm is "
             "refused, and B's rm is allowed", spo_cp_mv_top_case)
spo_register("scratchpad-owner: cp-mv 15 the top-level session wrote a file, and agent B's mv of it: agent A's run "
             "and B's rm are allowed", spo_mv_unrecorded_case)
spo_register("scratchpad-owner: cp-mv 16 agent B's one call moves its copy to d.py and back: the call is allowed "
             "and returns", spo_mv_chain_case)
spo_register("scratchpad-owner: cp-mv 11 agent B's rm -rf of a folder holding its copy of agent A's file: "
             "allowed, and C's is refused", spo_cp_copier_folder_case)
spo_register("scratchpad-owner: cp-mv 8 agent B copies a file with no recorded writer with cp, and runs the copy: "
             "allowed", spo_cp_unrecorded_case)
spo_register("scratchpad-owner: cp-mv 4 agent B's mv of agent A's file to m.py, approved by the owner: A's run of "
             "m.py is allowed and B's is refused", spo_mv_approved_case)
spo_register("scratchpad-owner: cp-mv 5 agent B's run of a file agent A moved in from outside the scratchpad: "
             "refused", spo_mv_in_case)
spo_register("scratchpad-owner: cp-mv 6 agent B's run of dir/s.py, a copy agent A made into a scratchpad folder: "
             "refused", spo_cp_dir_case)
spo_register("scratchpad-owner: one-call 1 agent B's heredoc to x.tmp and mv to x.py in one call: agent A's run of "
             "x.py is refused", spo_one_call_heredoc)
spo_register("scratchpad-owner: one-call 2 agent B's cp to x.tmp and mv to x.py in one call: agent A's run of "
             "x.py is refused", spo_one_call_cp)
spo_register("scratchpad-owner: two-call control, agent B's heredoc to x.tmp, then its mv to x.py in the next call: "
             "agent A's run of x.py is refused", spo_two_call_case)


def spo_rm_cp_case(tag, name, with_rm, passed):
    """Agent B's one call copies src.py over t.py, after `rm -f t.py` when `with_rm`. No t.py is there before the call.
    The rm names t.py, and the cp that writes it discards that name, so the copy is B's: agent A's run of t.py is
    refused, and B's own run is the control, which is allowed."""
    fx = spo_fixture(tag)
    src = os.path.join(fx["work"], "src.py")   # outside the scratchpad, in this case's folder
    write(src, PY_TEXT)
    dest = os.path.join(fx["scratch"], "t.py")
    copy = "cp %s %s" % (src, dest)
    command = "rm -f %s && %s" % (dest, copy) if with_rm else copy
    problems = [spo_scope(fx, name, dest)]
    problems += spo_wrote(fx, name, SPO_OTHER, dest, PY_TEXT, tool="Bash", command=command)
    problems += spo_b_file_runs(fx, name, dest, "t.py")
    return spo_result(problems, passed)


spo_register("scratchpad-owner: one-call 3, agent B's rm -f t.py and cp src t.py in one call: agent A's run of t.py is "
             "refused", lambda: spo_rm_cp_case("one-call-rm", "one-call 3", True,
                                              "agent B's rm and cp of t.py in one call: A's run of t.py is refused"))
spo_register("scratchpad-owner: one-call control 1, agent B's cp src t.py with no rm: agent A's run of t.py is refused",
             lambda: spo_rm_cp_case("one-call-cp", "one-call control 1", False,
                                   "agent B's cp of t.py with no rm: A's run of t.py is refused"))


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
