# section 34371
FAMILY = "scratchpad-owner"
SPO_RULE = "scratchpad-owner"
SPO_WRITER = "spo-writer-01"   # an agent id in the shape AGENT_ID accepts
SPO_OTHER = "spo-other-02"
SPO_SLUG = "-home-user-claude-settings"   # the project folder the scratchpad sits under
PY_TEXT = "print(1)\n"
SH_TEXT = "echo hi\n"
SPO_NT = "skipped: these cases use POSIX shell forms and POSIX paths"


def spo_fixture(tag, real=False):
    """One case's folders under this run's folder: a temp folder the guard reads as TMPDIR, this
    session's scratchpad inside it (`<tmp>/<slug>/<session>/scratchpad`), and a working folder that
    sits in no checkout. The session id is new for each case. With `real`, the scratchpad sits under
    the scratchpad base (SCRATCH_BASE, named by CLAUDE_SCRATCHPAD_BASE in `env`) instead, and TMPDIR stays
    the case's own folder, so the guard must find the scratchpad by its base and not by TMPDIR."""
    folder = os.path.join(ROOT, "spo", tag)
    fx = {"tmp": os.path.join(folder, "tmp"), "sid": "spo-" + uuid.uuid4().hex,
          "work": os.path.join(folder, "work"), "folder": folder}
    if real:
        fx["env"] = SCRATCH_BASE_ENV
        fx["scratch"] = os.path.join(SCRATCH_BASE, "spo", tag, SPO_SLUG, fx["sid"], "scratchpad")
    else:
        fx["scratch"] = os.path.join(fx["tmp"], SPO_SLUG, fx["sid"], "scratchpad")
    # TMPDIR must name a folder that exists: tempfile.gettempdir() skips a missing one for /tmp, and the
    # guard would then read /tmp as its base and find the real scratchpad there.
    os.makedirs(fx["tmp"], exist_ok=True)
    os.makedirs(fx["scratch"], exist_ok=True)
    os.makedirs(fx["work"], exist_ok=True)
    return fx


def spo_call(fx, tool, agent, **tool_input):
    """One guard call, as the harness sends it in this case: its session, its temp folder and its
    working folder. `agent` is None for the top-level session."""
    return _decide_full(tool, fx["work"], agent_id=agent, session=fx["sid"], temp=fx["tmp"],
                        env=fx.get("env"), **tool_input)


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


# The one reader of the lift line (tests/lift_line.py). A lifted refusal prints that line, and decide() reads it as "unparsable".
sys.path.insert(0, os.path.join(REPO, "tests"))
import lift_line  # noqa: E402,F401  the one reader of the lift line


def spo_allowed(name, got, reason):
    """A call the rule passes: the decision is allow."""
    if got == "allow":
        return ""
    return "%s: want allow, got %s (%s)" % (name, got, reason[:100])


def spo_lifted(name, got, reason):
    """A call that the owner's override lifts: the guard prints the one lift line, and it names scratchpad-owner."""
    if lift_line.lift_of(got, reason, SPO_RULE):
        return ""
    return "%s: want the override to lift %s, got %s (%s)" % (name, SPO_RULE, got, reason[:100])


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



def pr2015_spo_case_1():
    """Agent A writes probe2.py with Write; agent B runs it with python3: refused."""
    fx = spo_fixture("c1")
    probe = os.path.join(fx["scratch"], "probe2.py")
    problems = [spo_scope(fx, "1", probe)] + spo_wrote(fx, "1", SPO_WRITER, probe, PY_TEXT)
    got, reason = spo_run(fx, SPO_OTHER, "python3 %s" % probe)
    problems.append(spo_refused("1", got, reason, (fx["scratch"], "probe2.py")))
    return spo_result(problems, "agent B's python3 run of agent A's script is refused")


def pr2015_spo_case_2():
    """Agent A writes probe2.py with Write; agent B runs it after a cd into the scratchpad: refused."""
    fx = spo_fixture("c2")
    probe = os.path.join(fx["scratch"], "probe2.py")
    problems = [spo_scope(fx, "2", probe)] + spo_wrote(fx, "2", SPO_WRITER, probe, PY_TEXT)
    got, reason = spo_run(fx, SPO_OTHER, "cd %s && python3 probe2.py" % fx["scratch"])
    problems.append(spo_refused("2", got, reason, (fx["scratch"], "probe2.py")))
    return spo_result(problems, "agent B's cd and python3 run of agent A's script is refused")


def pr2015_spo_case_3():
    """Agent A writes p.sh by a bash heredoc; agent B runs it through bash: refused."""
    fx = spo_fixture("c3")
    script = os.path.join(fx["scratch"], "p.sh")
    heredoc = "cat > %s <<'EOF'\n%sEOF" % (script, SH_TEXT)
    problems = [spo_scope(fx, "3", script)] + spo_wrote(
        fx, "3", SPO_WRITER, script, SH_TEXT, tool="Bash", command=heredoc)
    got, reason = spo_run(fx, SPO_OTHER, "bash %s" % script)
    problems.append(spo_refused("3", got, reason, (fx["scratch"], "p.sh")))
    return spo_result(problems, "agent B's bash run of agent A's heredoc script is refused")


def pr2015_spo_case_4():
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



def pr2015_spo_case_10():
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
             pr2015_spo_case_1)
spo_register("scratchpad-owner: 2 agent B runs agent A's script after cd into the scratchpad: refused",
             pr2015_spo_case_2)
spo_register("scratchpad-owner: 3 agent B runs agent A's script through bash, after A wrote it by a heredoc: refused",
             pr2015_spo_case_3)
spo_register("scratchpad-owner: 4 agent B runs agent A's script as the command word: refused", pr2015_spo_case_4)


spo_register("scratchpad-owner: 5 agent A runs its own script: allowed", spo_case_5)
spo_register("scratchpad-owner: 6 agent B runs a script with no record, made outside the guard: allowed",
             spo_case_6)
spo_register("scratchpad-owner: 7 a top-level call with no agent_id runs agent A's script: allowed",
             spo_case_7)
spo_register("scratchpad-owner: 8 agent B reads agent A's script with cat: allowed", spo_case_8)
spo_register("scratchpad-owner: 9 agent writes outside any scratchpad create no file under this session's "
             "scratchpad: allowed", spo_case_9)

spo_register("scratchpad-owner: 10 agent B runs the oldest of forty scripts agent A wrote: refused",
             pr2015_spo_case_10)
spo_register("scratchpad-owner: extra, a run inside single quotes is text: allowed", spo_extra_quoted)
spo_register("scratchpad-owner: extra, a run after a comment mark is text: allowed", spo_extra_comment)
spo_register("scratchpad-owner: extra, a run in a heredoc body is text: allowed", spo_extra_heredoc)
spo_register("scratchpad-owner: extra, a lone apostrophe in double quotes does not hide a read: allowed",
             spo_extra_apostrophe)
spo_register("scratchpad-owner: extra, a run on the second line of a double-quoted string is text: allowed",
             spo_extra_multiline)



# Rule scratchpad-owner, the overwrite form: an agent with a valid agent_id that writes over a file under
# this session's scratchpad whose record names a different agent is refused (deny). The writes are the
# ones the record covers: Write, and a shell write
# target (a redirect, a heredoc `cat > f`, or an append). The first write of a file, a rewrite by its own
# writer, a call with no agent_id and a read pass. Each case builds its own session, as the cases above do.


def pr2015_ovw_case_1():
    """Agent A writes msg.txt with Write; agent B writes the same file with Write: refused."""
    fx = spo_fixture("o1")
    msg = os.path.join(fx["scratch"], "msg.txt")
    problems = [spo_scope(fx, "o1", msg)] + spo_wrote(fx, "o1", SPO_WRITER, msg, "from A\n")
    got, reason = spo_call(fx, "Write", SPO_OTHER, file_path=msg, content="from B\n")
    problems.append(spo_refused("o1", got, reason, (fx["scratch"], "msg.txt")))
    return spo_result(problems, "agent B's Write over agent A's file is refused")


def pr2015_ovw_case_2():
    """Agent A writes msg.txt with Write; agent B redirects echo over it: refused."""
    fx = spo_fixture("o2")
    msg = os.path.join(fx["scratch"], "msg.txt")
    problems = [spo_scope(fx, "o2", msg)] + spo_wrote(fx, "o2", SPO_WRITER, msg, "from A\n")
    got, reason = spo_run(fx, SPO_OTHER, "echo x > %s" % msg)
    problems.append(spo_refused("o2", got, reason, (fx["scratch"], "msg.txt")))
    return spo_result(problems, "agent B's shell redirect over agent A's file is refused")


def pr2015_ovw_case_3():
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



def pr2015_ovw_case_7():
    """Agent A writes msg.txt; agent B appends to it with >>: refused."""
    fx = spo_fixture("o7")
    msg = os.path.join(fx["scratch"], "msg.txt")
    problems = [spo_scope(fx, "o7", msg)] + spo_wrote(fx, "o7", SPO_WRITER, msg, "from A\n")
    got, reason = spo_run(fx, SPO_OTHER, "echo x >> %s" % msg)
    problems.append(spo_refused("o7", got, reason, (fx["scratch"], "msg.txt")))
    return spo_result(problems, "agent B's append to agent A's file is refused")


spo_register("scratchpad-owner: overwrite 1 agent B's Write over agent A's file: refused", pr2015_ovw_case_1)
spo_register("scratchpad-owner: overwrite 2 agent B's shell redirect over agent A's file: refused", pr2015_ovw_case_2)
spo_register("scratchpad-owner: overwrite 3 agent B's heredoc after a cd over agent A's file: refused",
             pr2015_ovw_case_3)


spo_register("scratchpad-owner: overwrite 4 agent A rewrites its own file: allowed", ovw_case_4)
spo_register("scratchpad-owner: overwrite 5 agent B's first write of a file nobody wrote: allowed",
             ovw_case_5)
spo_register("scratchpad-owner: overwrite 6 a top-level call overwrites agent A's file: allowed",
             ovw_case_6)

spo_register("scratchpad-owner: overwrite 7 agent B's append to agent A's file: refused", pr2015_ovw_case_7)


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



def pr2015_spo_run_case(tag, name, script_name, command_of, passed, text=PY_TEXT):
    """Agent A writes `script_name` with Write. Agent B's call `command_of(fx, path)` acts on the file and is
    refused: a run of the file, or a removal or move of it. Agent A's same call is the control, and is allowed."""
    fx = spo_fixture(tag)
    path = os.path.join(fx["scratch"], script_name)
    problems = [spo_scope(fx, name, path)] + spo_wrote(fx, name, SPO_WRITER, path, text)
    got, reason = spo_run(fx, SPO_OTHER, command_of(fx, path))
    problems.append(spo_refused(name, got, reason, (fx["scratch"], script_name)))
    got, reason = spo_run(fx, SPO_WRITER, command_of(fx, path))
    problems.append(spo_allowed(name + ", control: agent A's own call", got, reason))
    return spo_result(problems, passed)


def pr2015_spo_flag_1():
    return pr2015_spo_run_case("flag1", "flag 1", "probe2.py", lambda fx, p: "python3 -W ignore %s" % p,
                        "agent B's python3 -W ignore run of agent A's script is refused")


def pr2015_spo_flag_2():
    return pr2015_spo_run_case("flag2", "flag 2", "probe2.py", lambda fx, p: "python3 -X dev %s" % p,
                        "agent B's python3 -X dev run of agent A's script is refused")


def pr2015_spo_flag_3():
    return pr2015_spo_run_case("flag3", "flag 3", "x.js", lambda fx, p: "node --require /x %s" % p,
                        "agent B's node --require run of agent A's script is refused", text="console.log(1)\n")


def pr2015_spo_variable_1():
    return pr2015_spo_run_case("var1", "variable 1", "probe2.py",
                        lambda fx, p: 'S=%s; python3 "$S/probe2.py"' % os.path.dirname(p),
                        "agent B's run of agent A's script by a shell variable path is refused")


def pr2015_spo_removal_1():
    return pr2015_spo_run_case("rm1", "removal 1", "msg.txt", lambda fx, p: "rm %s" % p,
                        "agent B's rm of agent A's file is refused", text="from A\n")


def pr2015_spo_move_1():
    return pr2015_spo_run_case("mv1", "move 1", "msg.txt",
                        lambda fx, p: "mv %s %s" % (p, os.path.join(fx["work"], "moved.txt")),
                        "agent B's mv of agent A's file is refused", text="from A\n")


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
    return lambda: pr2015_spo_run_case("run-" + tag, "runner %s" % form, script_name, lambda fx, p: template % p,
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
    """Agent A writes probe2.py. Agent B copies it to mine.py with cp: a read of A's file and a new file of B's.
    B's run of mine.py is allowed, since the copier owns the copy."""
    fx = spo_fixture("cp-own")
    probe = os.path.join(fx["scratch"], "probe2.py")
    mine = os.path.join(fx["scratch"], "mine.py")
    problems = [spo_scope(fx, "cp own", probe)] + spo_wrote(fx, "cp own", SPO_WRITER, probe, PY_TEXT)
    problems += spo_wrote(fx, "cp own", SPO_OTHER, mine, PY_TEXT, tool="Bash", command="cp %s %s" % (probe, mine))
    got, reason = spo_run(fx, SPO_OTHER, "python3 %s" % mine)
    problems.append(spo_allowed("cp own, B's run of its own copy", got, reason))
    return spo_result(problems, "agent B's copy of agent A's file is B's own, and B's run of it is allowed")


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
    lifted = spo_lifted("mv approved, B's mv under the override", got, reason)
    problems.append(lifted)
    if not lifted:
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


# The overwrite reason's words (SCRATCHPAD_OVERWRITE_REASON). The folder reason says "removing or moving it" instead.
SPO_WRITE_OVER = "writing over it destroys work"


def spo_folder_case(tag, name, writes, agent, command_of, passed, want="deny", folder=False, overwrite=False):
    """The files of `writes` are made, then `agent`'s call `command_of(scratchpad)` runs. With `want` "deny" the call
    is refused, and the refusal names scratchpad-owner, neither the folder nor the files. With "allow" it passes.
    With `folder` a refusal must be the folder's reason, which names a folder; the file's reason names a file, so it
    fails here. With
    `overwrite` a refusal must be the overwrite reason, which says that writing over the file destroys work."""
    fx = spo_fixture(tag)
    problems = spo_folder_writes(fx, name, writes)
    got, reason = spo_run(fx, agent, command_of(fx["scratch"]))
    banned = (fx["scratch"],) + tuple(os.path.basename(rel) for _, rel, _ in writes)
    if want == "allow":
        problems.append(spo_allowed(name, got, reason))
    else:
        problems.append(spo_refused(name, got, reason, banned))
        if folder and got == "deny" and "folder" not in reason:
            problems.append("%s: the refusal is not the folder's reason (%s)" % (name, reason[:100]))
        if overwrite and got == "deny" and SPO_WRITE_OVER not in reason:
            problems.append("%s: the refusal is not the overwrite reason (%s)" % (name, reason[:100]))
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
    lifted = spo_lifted("approved, B's overwrite under the override", got, reason)
    problems.append(lifted)
    if not lifted:
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
    lifted = spo_lifted(name + ", B's removal under the override", got, reason)
    problems.append(lifted)
    if not lifted:
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



spo_register("scratchpad-owner: flag 1 agent B runs agent A's script past python3 -W ignore: refused",
             pr2015_spo_flag_1)
spo_register("scratchpad-owner: flag 2 agent B runs agent A's script past python3 -X dev: refused", pr2015_spo_flag_2)
spo_register("scratchpad-owner: flag 3 agent B runs agent A's script past node --require: refused", pr2015_spo_flag_3)
spo_register("scratchpad-owner: variable 1 agent B runs agent A's script by a shell variable path: refused",
             pr2015_spo_variable_1)


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

spo_register("scratchpad-owner: removal 1 agent B's rm of agent A's file: refused", pr2015_spo_removal_1)
spo_register("scratchpad-owner: move 1 agent B's mv of agent A's file: refused", pr2015_spo_move_1)
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
# Rule scratchpad-owner, one call that runs another agent's file and also removes or moves a folder holding another
# agent's file. The folder is judged before the run, so the call is refused, and the refusal names neither the folder
# nor the files. Agent A's script sits at the top of its scratchpad, beside its folder `sub`, or inside that folder.
# The control rows are the two halves alone: a run with no folder call is refused, and a folder removal with no run is
# refused.
SPO_RUN_FOLDER = SPO_FOLDER_SUB + ((SPO_WRITER, "probe.py", PY_TEXT),)
SPO_RUN_FOLDER_IN = SPO_FOLDER_SUB + ((SPO_WRITER, "sub/probe.py", PY_TEXT),)
SPO_RUN_FOLDER_FORMS = (
    # (case tag, label, agent B's command for the scratchpad path s)
    ("run-folder-1", "run and folder 1, agent B's python3 of agent A's script, then rm -rf of agent A's folder",
     lambda s: "python3 %s && rm -rf %s" % (os.path.join(s, "probe.py"), os.path.join(s, "sub"))),
    ("run-folder-2", "run and folder 2, agent B's python3 of agent A's script, then mv of agent A's folder",
     lambda s: "python3 %s && mv %s %s" % (os.path.join(s, "probe.py"), os.path.join(s, "sub"),
                                           os.path.join(s, "moved"))),
)
for _tag, _label, _command_of in SPO_RUN_FOLDER_FORMS:
    spo_register("scratchpad-owner: %s: refused" % _label,
                 lambda t=_tag, n=_label, c=_command_of: spo_folder_case(t, n, SPO_RUN_FOLDER, SPO_OTHER, c,
                                                                         "%s is refused" % n))
spo_register("scratchpad-owner: run and folder 3, agent B's python3 of agent A's script inside a folder, then rm -rf "
             "of that folder: refused",
             lambda: spo_folder_case("run-folder-3", "run and folder 3", SPO_RUN_FOLDER_IN, SPO_OTHER,
                                     lambda s: "python3 %s && rm -rf %s" % (os.path.join(s, "sub", "probe.py"),
                                                                           os.path.join(s, "sub")),
                                     "agent B's run of A's script inside a folder, then rm -rf of it, is refused"))
spo_register("scratchpad-owner: run and folder control 1, agent B's python3 of agent A's script alone: refused",
             lambda: spo_folder_case("run-folder-ctl-1", "run and folder control 1", SPO_RUN_FOLDER, SPO_OTHER,
                                     lambda s: "python3 %s" % os.path.join(s, "probe.py"),
                                     "agent B's run of agent A's script with no folder call is refused"))
spo_register("scratchpad-owner: run and folder control 2, agent B's rm -rf of agent A's folder alone: refused",
             lambda: spo_folder_case("run-folder-ctl-2", "run and folder control 2", SPO_RUN_FOLDER, SPO_OTHER,
                                     lambda s: "rm -rf %s" % os.path.join(s, "sub"),
                                     "agent B's rm -rf of agent A's folder with no run is refused"))
# Rule scratchpad-owner, one call that runs another agent's file and also overwrites, removes or moves another agent's
# file. The run alone is refused too, and an overwrite in the same call is refused with the overwrite reason: a
# refused write names its own reason, which says that writing over the file destroys another agent's work. Agent A's
# script `probe.py` and its file `other.txt` sit at the top of its scratchpad. The control names the same fixture and
# redirects the run onto agent B's own fresh file, which no agent wrote: that run is refused, as the run rows are.
SPO_RUN_OVERWRITE = ((SPO_WRITER, "probe.py", PY_TEXT), (SPO_WRITER, "other.txt", "from A\n"))
SPO_RUN_OVERWRITE_FORMS = (
    # (case tag, label, agent B's command for the scratchpad path s)
    ("run-overwrite-1", "run and overwrite 1, agent B's python3 of agent A's script, a redirect onto agent A's other "
                        "file",
     lambda s: "python3 %s > %s" % (os.path.join(s, "probe.py"), os.path.join(s, "other.txt"))),
    ("run-overwrite-2", "run and overwrite 2, agent B's python3 of agent A's script, then rm of agent A's other file",
     lambda s: "python3 %s && rm %s" % (os.path.join(s, "probe.py"), os.path.join(s, "other.txt"))),
    ("run-overwrite-3", "run and overwrite 3, agent B's python3 of agent A's script, then mv of B's x.txt onto agent "
                        "A's other file",
     lambda s: "python3 %s && mv x.txt %s" % (os.path.join(s, "probe.py"), os.path.join(s, "other.txt"))),
)
for _tag, _label, _command_of in SPO_RUN_OVERWRITE_FORMS:
    spo_register("scratchpad-owner: %s: refused with the overwrite reason" % _label,
                 lambda t=_tag, n=_label, c=_command_of: spo_folder_case(t, n, SPO_RUN_OVERWRITE, SPO_OTHER, c,
                                                                         "%s is refused with the overwrite reason" % n,
                                                                         overwrite=True))
spo_register("scratchpad-owner: run and overwrite control 1, agent B's python3 of agent A's script, a redirect onto "
             "B's own fresh file: refused",
             lambda: spo_folder_case("run-overwrite-ctl-1", "run and overwrite control 1", SPO_RUN_OVERWRITE, SPO_OTHER,
                                     lambda s: "python3 %s > %s" % (os.path.join(s, "probe.py"),
                                                                    os.path.join(s, "b-fresh.txt")),
                                     "agent B's run of agent A's script, redirected onto B's own fresh file, "
                                     "is refused"))
# Rule scratchpad-owner, one call that overwrites, removes or moves another agent's file and also removes or moves a
# folder that holds another agent's file. The file alone is refused too, and the folder makes the call a refusal
# whichever word comes first. Agent A's file `top.txt` sits beside its folder `sub`. The control rows are the folder
# first, then the file, and the file alone: all refused.
SPO_FILE_FOLDER = SPO_FOLDER_SUB + ((SPO_WRITER, "top.txt", "from A\n"),)
SPO_FILE_FOLDER_FORMS = (
    # (case tag, label, agent B's command for the scratchpad path s)
    ("file-folder-1", "file and folder 1, agent B's rm of agent A's file, then agent A's folder",
     lambda s: "rm %s %s" % (os.path.join(s, "top.txt"), os.path.join(s, "sub"))),
    ("file-folder-2", "file and folder 2, agent B's echo over agent A's file, then rm -rf of agent A's folder",
     lambda s: "echo x > %s && rm -rf %s" % (os.path.join(s, "top.txt"), os.path.join(s, "sub"))),
    ("file-folder-3", "file and folder 3, agent B's mv of agent A's file, then rm -rf of agent A's folder",
     lambda s: "mv %s %s && rm -rf %s" % (os.path.join(s, "top.txt"), os.path.join(s, "mine.txt"),
                                          os.path.join(s, "sub"))),
)
for _tag, _label, _command_of in SPO_FILE_FOLDER_FORMS:
    spo_register("scratchpad-owner: %s: refused" % _label,
                 lambda t=_tag, n=_label, c=_command_of: spo_folder_case(t, n, SPO_FILE_FOLDER, SPO_OTHER, c,
                                                                         "%s is refused" % n, folder=True))
spo_register("scratchpad-owner: file and folder control 1, agent B's rm -rf of agent A's folder, then its file: "
             "refused",
             lambda: spo_folder_case("file-folder-ctl-1", "file and folder control 1", SPO_FILE_FOLDER, SPO_OTHER,
                                     lambda s: "rm -rf %s %s" % (os.path.join(s, "sub"), os.path.join(s, "top.txt")),
                                     "agent B's rm -rf of agent A's folder, then its file, is refused", folder=True))
spo_register("scratchpad-owner: file and folder control 2, agent B's rm of agent A's file alone: refused",
             lambda: spo_folder_case("file-folder-ctl-2", "file and folder control 2", SPO_FILE_FOLDER, SPO_OTHER,
                                     lambda s: "rm %s" % os.path.join(s, "top.txt"),
                                     "agent B's rm of agent A's file with no folder call is refused"))
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



def pr2015_spo_dashdash_1():
    return pr2015_spo_run_case("dash1", "dashdash 1", "x.py", lambda fx, p: "python3 -- %s" % p,
                        "agent B's python3 -- run of agent A's script is refused")


spo_register("scratchpad-owner: stdin 1 agent B's python3 - with a heredoc and agent A's data.json as an "
             "argument: allowed", spo_stdin_case)

spo_register("scratchpad-owner: dashdash 1 agent B's python3 -- run of agent A's script: refused",
             pr2015_spo_dashdash_1)


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
# A file as an argument is data for the command, not the run: the run forms of the same runner (`uv run F`,
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
             lambda: pr2015_spo_run_case("arg-ctl-uv-python", "argument control 2, uv run python F", "probe2.py",
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
             lambda: pr2015_spo_run_case("arg-ctl-uv-q", "argument control 3, uv run -q F", "f.py",
                                         lambda fx, p: "uv run -q %s" % p,
                                         "agent B's uv run -q F, the file as the script word, is refused"))
spo_register("scratchpad-owner: argument control 4, agent B's npx tsx --watch F, the file as the script word: refused",
             lambda: pr2015_spo_run_case("arg-ctl-npx-watch", "argument control 4, npx tsx --watch F", "probe2.ts",
                                         lambda fx, p: "npx tsx --watch %s" % p,
                                         "agent B's npx tsx --watch F, the file as the script word, is refused",
                                         text=TS_TEXT))
spo_register("scratchpad-owner: argument control 5, agent B's deno run -A F, the file as the script word: refused",
             lambda: pr2015_spo_run_case("arg-ctl-deno-a", "argument control 5, deno run -A F", "probe2.ts",
                                         lambda fx, p: "deno run -A %s" % p,
                                         "agent B's deno run -A F, the file as the script word, is refused",
                                         text=TS_TEXT))
# A verb runner's wrapper (`timeout 60`) hands on its command, so the program the wrapper runs is the script word.
spo_register("scratchpad-owner: argument pin, agent B's uv run timeout 60 python3 F, the file as the wrapped "
             "program: refused", lambda: pr2015_spo_run_case("arg-pin-timeout",
                                                           "argument pin, uv run timeout 60 python3 F", "f.py",
                                                           lambda fx, p: "uv run timeout 60 python3 %s" % p,
                                                           "agent B's uv run timeout 60 python3 F is refused"))
spo_register("scratchpad-owner: runner x=$(python3 F), an open substitution in an assignment: agent B's run is "
             "refused", spo_runner_case("subst-open-ctl", "x=$(python3 F)", "probe2.py", PY_TEXT, "x=$(python3 %s)"))
spo_register("scratchpad-owner: cp-mv 1 agent B's run of a script agent A copied into the scratchpad with cp: "
             "refused", spo_cp_in_case)
spo_register("scratchpad-owner: cp-mv 2 agent B's run of a file agent A moved to a new name with mv: refused",
             spo_mv_carry_case)
spo_register("scratchpad-owner: cp-mv 3 agent B copies agent A's file with cp, and runs its own copy: allowed",
             spo_cp_own_case)
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
    refused = spo_refused("record, B's run of A's file", got, reason, (fx["scratch"], "probe2.py"))
    if refused:
        return spo_result([refused], "")
    return spo_result([], "a refused overwrite leaves the record with agent A: B's retry and B's run are refused")


spo_register("scratchpad-owner: remedy 1 the overwrite refusal names a fresh or new file name",
             spo_remedy_fresh_overwrite)
spo_register("scratchpad-owner: remedy 2 the run refusal names a fresh or new file name", spo_remedy_fresh_run)
spo_register("scratchpad-owner: remedy 3 the overwrite refusal names no ask and no overwrite",
             spo_remedy_route_overwrite)
spo_register("scratchpad-owner: remedy 4 the run refusal names no ask and no overwrite", spo_remedy_route_run)
spo_register("scratchpad-owner: record 1 a refused overwrite leaves the record with agent A: B's retry and B's "
             "run are refused", spo_record_case)


# Rule scratchpad-owner, the words of an overwrite refusal. The refusal tells the
# agent (a) that another agent of this session wrote the file, and that writing over it destroys work that agent may
# still need; (b) to write its own file under a fresh name in the scratchpad; (c) names no fragment of the reason
# rule's forbidden list (FORBIDDEN_IN_A_REASON, read through names_the_target); (d) tells the agent what to do when
# the refusal looks wrong for its task. Each case judges the verdict first and
# then one check, so a failure names one cause. The controls are overwrite 4 (an agent's own rewrite) and overwrite 6
# (a call with no agent_id), and spo_refusal runs the agent's own rewrite before each refused call.
SPO_WRITTEN_BY_OTHER = "written by another agent of this session"
SPO_DESTROYS_WORK = "destroys work that agent may still need"
SPO_IN_SCRATCHPAD = re.compile(r"\bscratchpad\b", re.IGNORECASE)


def spo_message_written_check(name, reason):
    """(a): the refusal says another agent of this session wrote the file, and writing over it destroys its work."""
    if SPO_WRITTEN_BY_OTHER in reason and SPO_DESTROYS_WORK in reason:
        return ""
    return "%s: the refusal does not say another agent of this session wrote the file and that writing over it " \
           "destroys its work (%s)" % (name, reason[:100])


def spo_message_remedy_check(name, reason):
    """(b): the remedy tells the agent to write its own file under a fresh name, in the scratchpad."""
    text = spo_remedy(reason)
    if not text:
        return "%s: the refusal holds no Remedy: clause (%s)" % (name, reason[:100])
    fresh = spo_fresh_name_check(name, text)
    if fresh:
        return fresh
    if SPO_IN_SCRATCHPAD.search(text):
        return ""
    return "%s: the remedy does not say the fresh file goes in the scratchpad (%s)" % (name, text[:100])


def spo_message_forbidden_check(name, reason):
    """(c): the refusal names no fragment of the reason rule's forbidden list."""
    fragment = names_the_target(reason, SPO_RULE)
    if not fragment:
        return ""
    return "%s: the refusal names %r, a fragment the reason rule forbids (%s)" % (name, fragment, reason[:100])


SPO_LOOKS_WRONG = "If this refusal looks wrong for your task, comply anyway and say so in your report."


def spo_message_looks_wrong_check(name, reason):
    """(d): the refusal tells the agent what to do when the refusal itself looks wrong for its task."""
    if SPO_LOOKS_WRONG in reason:
        return ""
    return "%s: the refusal lacks the sentence on what to do when the refusal looks wrong (%s)" % (name, reason[:100])


def spo_message_ends_check(name, reason):
    """(e): the reason ends with that sentence, or with it followed only by the decision cite in parentheses. The guard
    prints its override offer after the cite, so the reason is read up to the cite."""
    cut = reason.find(" (decision")
    if cut < 0:
        return "%s: the refusal holds no decision cite to end the reason on (%s)" % (name, reason[:100])
    if reason[:cut].rstrip().endswith(SPO_LOOKS_WRONG):
        return ""
    return "%s: the reason does not end with the sentence on a refusal that looks wrong, before the cite (%s)" \
           % (name, reason[:100])


def spo_message_case(tag, check, passed):
    """Agent B's overwrite of agent A's file. The verdict is judged first (spo_refused: deny, the rule's id, and no
    file name); then `check` reads the reason. One problem per case, so each failure names one cause."""
    problems, got, reason = spo_refusal(tag, "overwrite")
    problems.append(spo_refused(tag, got, reason, ("msg.txt",)) or check(tag, reason))
    return spo_result(problems, passed)


spo_register("scratchpad-owner: message 1 the overwrite refusal is a deny that says another agent of this session "
             "wrote the file and that writing over it destroys work that agent may still need",
             lambda: spo_message_case("message-1", spo_message_written_check,
                                      "the overwrite refusal says another agent of this session wrote the file, and "
                                      "that writing over it destroys its work"))
spo_register("scratchpad-owner: message 2 the overwrite refusal tells the agent to write its own file under a fresh "
             "name in the scratchpad",
             lambda: spo_message_case("message-2", spo_message_remedy_check,
                                      "the overwrite refusal tells the agent to write its own file under a fresh name "
                                      "in the scratchpad"))
spo_register("scratchpad-owner: message 3 the overwrite refusal names no fragment of the reason rule's forbidden list",
             lambda: spo_message_case("message-3", spo_message_forbidden_check,
                                      "the overwrite refusal names no fragment of the reason rule's forbidden list"))
spo_register("scratchpad-owner: message 4 the overwrite refusal tells the agent what to do when the refusal looks "
             "wrong for its task: comply anyway and say so in its report",
             lambda: spo_message_case("message-4", spo_message_looks_wrong_check,
                                      "the overwrite refusal carries the sentence on what to do when the refusal "
                                      "looks wrong"))
spo_register("scratchpad-owner: message 5 the overwrite reason ends with the sentence on what to do when the refusal "
             "looks wrong, before the decision cite",
             lambda: spo_message_case("message-5", spo_message_ends_check,
                                      "the overwrite reason ends with the sentence on what to do when the refusal "
                                      "looks wrong, before the decision cite"))


# Rule scratchpad-owner, the words of a run refusal. The refusal tells the agent (a) that another agent of this session
# wrote the file, and that running it runs code this agent did not write; (b) the correct act: read the file, then write
# its own copy under a fresh name and run that copy; (c) names no fragment of the reason rule's forbidden list; (d) the
# sentence on what to do when the refusal looks wrong; (e) the reason ends with that sentence, before the decision cite.
# spo_refusal makes the agent's own run first, so the record names A on both calls. The verdict is judged first.
SPO_RUN_WHY = "running it runs code this agent did not write"
SPO_READ_FIRST = re.compile(r"\bread\b", re.IGNORECASE)
SPO_RUN_CORRECT = re.compile(r"\brun\b", re.IGNORECASE)


def spo_message_run_why_check(name, reason):
    """(a): the refusal says another agent of this session wrote the file, and that running it runs code this agent
    did not write."""
    if SPO_WRITTEN_BY_OTHER in reason and SPO_RUN_WHY in reason:
        return ""
    return "%s: the refusal does not say another agent of this session wrote the file, and that running it runs " \
           "code this agent did not write (%s)" % (name, reason[:100])


def spo_message_run_remedy_check(name, reason):
    """(b): the remedy says to read the file, then write the agent's own copy under a fresh name and run that copy."""
    text = spo_remedy(reason)
    if not text:
        return "%s: the refusal holds no Remedy: clause (%s)" % (name, reason[:100])
    fresh = spo_fresh_name_check(name, text)
    if fresh:
        return fresh
    if SPO_READ_FIRST.search(text) and SPO_RUN_CORRECT.search(text):
        return ""
    return "%s: the remedy does not say to read the file and run the agent's own copy (%s)" % (name, text[:100])


def spo_run_message_case(tag, check, passed):
    """Agent B's run of agent A's file. The verdict is judged first (spo_refused: deny, the rule's id, and no file
    name); then `check` reads the reason. One problem per case, so each failure names one cause."""
    problems, got, reason = spo_refusal(tag, "run")
    problems.append(spo_refused(tag, got, reason, ("probe2.py",)) or check(tag, reason))
    return spo_result(problems, passed)


spo_register("scratchpad-owner: message run 1 the run refusal is a deny that says another agent of this session wrote "
             "the file, and that running it runs code this agent did not write",
             lambda: spo_run_message_case("message-run-1", spo_message_run_why_check,
                                          "the run refusal says another agent of this session wrote the file, and "
                                          "that running it runs code this agent did not write"))
spo_register("scratchpad-owner: message run 2 the run refusal tells the agent to read the file, then write and run its "
             "own copy under a fresh name",
             lambda: spo_run_message_case("message-run-2", spo_message_run_remedy_check,
                                          "the run refusal tells the agent to read the file, then write and run its "
                                          "own copy under a fresh name"))
spo_register("scratchpad-owner: message run 3 the run refusal names no fragment of the reason rule's forbidden list",
             lambda: spo_run_message_case("message-run-3", spo_message_forbidden_check,
                                          "the run refusal names no fragment of the reason rule's forbidden list"))
spo_register("scratchpad-owner: message run 4 the run refusal tells the agent what to do when the refusal looks wrong "
             "for its task: comply anyway and say so in its report",
             lambda: spo_run_message_case("message-run-4", spo_message_looks_wrong_check,
                                          "the run refusal carries the sentence on what to do when the refusal looks "
                                          "wrong"))
spo_register("scratchpad-owner: message run 5 the run reason ends with the sentence on what to do when the refusal "
             "looks wrong, before the decision cite",
             lambda: spo_run_message_case("message-run-5", spo_message_ends_check,
                                          "the run reason ends with the sentence on what to do when the refusal looks "
                                          "wrong, before the decision cite"))


def spo_run_lift_case():
    """Agent A writes probe2.py. Agent B's run of it is refused. The owner types `override 15m` at 30 s, and B's run at
    60 s is lifted, so it runs. A run writes nothing, so the record stays with agent A: once the override has ended,
    B's run is refused again, and A's own run is allowed."""
    fx = spo_fixture("run-lift")
    config = ov_config("spo-run-lift")
    probe = os.path.join(fx["scratch"], "probe2.py")
    problems = [spo_scope(fx, "run lift", probe)] + spo_wrote(fx, "run lift", SPO_WRITER, probe, PY_TEXT)
    banned = (fx["scratch"], "probe2.py")

    def call(agent, seconds):
        return ov_call("Bash", {"command": "python3 %s" % probe}, fx["work"], config, fx["sid"], seconds,
                       agent_id=agent, temp=fx["tmp"])

    got, reason = call(SPO_OTHER, 0)
    problems.append(spo_refused("run lift, B's run before the override", got, reason, banned))
    note = ov_type(config, fx["sid"], "override 15m", 30)
    got, reason = call(SPO_OTHER, 60)
    problems.append(spo_lifted("run lift, B's run under the override", got, reason))
    later = OV_TIMED_SECONDS + 120   # the override typed at 30 s has ended by then
    got, reason = call(SPO_OTHER, later)
    problems.append(spo_refused("run lift, B's run after the override ended", got, reason, banned))
    got, reason = call(SPO_WRITER, later)
    problems.append(spo_allowed("run lift, control: agent A's own run", got, reason))
    if note and any(problems):
        problems.append("the override was not typed through override.grant: " + note)
    return spo_result(problems, "an override lifts a run refusal once and moves no record: B's later run is refused")


spo_register("scratchpad-owner: run lift 1 an owner override lifts a run refusal once and moves no record: B's later "
             "run is refused", spo_run_lift_case)


def spo_own_script_case():
    """Agent B writes its own script under the scratchpad with Write, then runs it. Its record names B, so the run is
    its own, and it is allowed."""
    fx = spo_fixture("own-script")
    own = os.path.join(fx["scratch"], "own.py")
    problems = [spo_scope(fx, "own script", own)] + spo_wrote(fx, "own script", SPO_OTHER, own, PY_TEXT)
    got, reason = spo_run(fx, SPO_OTHER, "python3 %s" % own)
    problems.append(spo_allowed("own script, B's run of its own file", got, reason))
    return spo_result(problems, "agent B writes its own script under the scratchpad and runs it: allowed")


spo_register("scratchpad-owner: own 1 agent B writes its own script with Write and runs it: allowed",
             spo_own_script_case)
spo_register("scratchpad-owner: read 1 agent B greps agent A's script: allowed",
             lambda: spo_text_case("read-grep", "read 1, grep F", lambda probe, outside: "grep -n print %s" % probe,
                                   "agent B's grep of agent A's script is allowed"))
spo_register("scratchpad-owner: read 2 agent B heads agent A's script: allowed",
             lambda: spo_text_case("read-head", "read 2, head F", lambda probe, outside: "head -n 1 %s" % probe,
                                   "agent B's head of agent A's script is allowed"))


# The real layout (hooks/guard_shared_tree.py scratchpad_temp_bases): the scratchpad base is named by
# CLAUDE_SCRATCHPAD_BASE (SCRATCH_BASE, in this run's folder), not gettempdir(). These cases build the
# scratchpad there (spo_fixture real=True), so each one is red on a guard that reads only gettempdir(). POSIX only.


def spo_real_overwrite_case():
    """Agent A writes msg.txt with Write under the scratchpad base; agent B writes the same file with Write:
    refused. Agent A's rewrite of its own file is the control, and is allowed."""
    fx = spo_fixture("real1", real=True)
    msg = os.path.join(fx["scratch"], "msg.txt")
    problems = [spo_scope(fx, "real 1", msg)] + spo_wrote(fx, "real 1", SPO_WRITER, msg, "from A\n")
    got, reason = spo_call(fx, "Write", SPO_OTHER, file_path=msg, content="from B\n")
    problems.append(spo_refused("real 1", got, reason, (fx["scratch"], "msg.txt")))
    got, reason = spo_call(fx, "Write", SPO_WRITER, file_path=msg, content="from A again\n")
    problems.append(spo_allowed("real 1, control: agent A's own rewrite", got, reason))
    return spo_result(problems, "agent B's Write over agent A's file under the scratchpad base is refused")


def spo_real_symlink_case():
    """Agent A writes msg.txt with Write, named through a symlink to the scratchpad base; agent B writes the
    same file, named the same way: refused. The guard reads the path by its real path, so the symlinked
    /tmp still counts."""
    fx = spo_fixture("real2", real=True)
    link = os.path.join(fx["folder"], "tmp-link")
    os.symlink(SCRATCH_BASE, link)
    msg = os.path.join(link, os.path.relpath(fx["scratch"], SCRATCH_BASE), "msg.txt")
    problems = [spo_scope(fx, "real 2", msg)] + spo_wrote(fx, "real 2", SPO_WRITER, msg, "from A\n")
    got, reason = spo_call(fx, "Write", SPO_OTHER, file_path=msg, content="from B\n")
    problems.append(spo_refused("real 2", got, reason, (fx["scratch"], "msg.txt")))
    return spo_result(problems, "agent B's Write over agent A's file, reached through a symlinked /tmp, is refused")


def spo_real_outside_case():
    """Agent A writes probe2.py into a folder shaped like a scratchpad, outside every base; agent B runs it
    with python3: not refused under scratchpad-owner. A green control: the path is no scratchpad on the old
    guard or on the head, so the rule must not reach it."""
    fx = spo_fixture("real3")
    path = os.path.join(fx["folder"], "outside", SPO_SLUG, fx["sid"], "scratchpad", "probe2.py")
    problems = []
    for base in (fx["tmp"], SCRATCH_BASE):
        if (os.path.realpath(path) + os.sep).startswith(os.path.realpath(base) + os.sep):
            problems.append("real 3, setup: the path lies under the base %s" % base)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    problems += spo_wrote(fx, "real 3", SPO_WRITER, path, PY_TEXT)
    got, reason = spo_run(fx, SPO_OTHER, "python3 %s" % path)
    if got != "allow" and SPO_RULE in reason:
        problems.append("real 3: agent B's run of a script outside every base is refused by %s (%s)"
                        % (SPO_RULE, reason[:100]))
    return spo_result(problems, "a script under a scratchpad-shaped folder outside every base is not a scratchpad")


# The shape a base sets (hooks/guard_shared_tree.py _scratchpad_shapes): under the harness base a project folder
# comes first, so `<base>/scratchpad/x` is no scratchpad and `<base>/<project>/<sid>/scratchpad/x` is one. The
# probe runs in a child process with CLAUDE_SCRATCHPAD_BASE unset, so the harness base is the one read. It only
# judges text: nothing is made under the harness base.
SPO_SHAPE_PROBE = (
    "import json, sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "import guard_shared_tree\n"
    "print(json.dumps([bool(guard_shared_tree.in_any_session_scratchpad(p)) for p in json.loads(sys.argv[2])]))\n"
)


def spo_shape_probe(cases, tmp):
    """Run the shape probe over (name, path, want) rows with TMPDIR at `tmp` and no scratchpad base variable.
    Returns the rows that read the other way. A probe that does not run is one problem."""
    env = dict(os.environ)
    env.pop("CLAUDE_SCRATCHPAD_BASE", None)
    env.update(TMPDIR=tmp, TEMP=tmp, TMP=tmp)
    run = subprocess.run([sys.executable, "-c", SPO_SHAPE_PROBE, os.path.join(REPO, "hooks"),
                          json.dumps([path for _, path, _ in cases])],
                         env=env, capture_output=True, text=True, timeout=120)
    if run.returncode != 0:
        return ["shape, setup: the probe did not run: %s" % run.stderr.strip()[-160:]]
    values = json.loads(run.stdout)
    return ["shape: %s reads as a scratchpad: %s, want %s" % (name, got, want)
            for (name, _, want), got in zip(cases, values) if got != want]


def spo_shape_case():
    """Under the harness base a project folder comes first. `<base>/scratchpad/x` is no scratchpad, `<base>/<project>/
    <session>/scratchpad/x` is one, and `<base>/<project>/scratchpad/x` is none: its `scratchpad` is not a session id.
    TMPDIR is the case's own folder, so the base is the harness base and not the temp folder."""
    fx = spo_fixture("shape")
    harness = os.path.join(os.path.realpath("/tmp"), "claude-%d" % os.getuid())
    cases = [("<harness base>/scratchpad/x", os.path.join(harness, "scratchpad", "x"), False),
             ("<harness base>/<project>/<session>/scratchpad/x",
              os.path.join(harness, SPO_SLUG, fx["sid"], "scratchpad", "x"), True),
             ("<harness base>/<project>/scratchpad/x", os.path.join(harness, SPO_SLUG, "scratchpad", "x"), False)]
    return spo_result(spo_shape_probe(cases, fx["tmp"]),
                      "the harness base's own folder and a folder under a project with no session are no scratchpad")


def spo_shape_linux_case():
    """The Linux layout: TMPDIR is realpath(/tmp), so the harness base's own folder `claude-<uid>` lies inside
    Python's temp folder. The `skip` branch of _scratchpad_shapes keeps `<base>/scratchpad/x` from reading as the
    scratchpad of a session named `claude-<uid>`. A mutant that drops that branch (`if True:`) makes this row red."""
    tmp = os.path.realpath("/tmp")
    harness = os.path.join(tmp, "claude-%d" % os.getuid())
    sid = "spo-" + uuid.uuid4().hex
    cases = [("<harness base>/scratchpad/x", os.path.join(harness, "scratchpad", "x"), False),
             ("<harness base>/<project>/<session>/scratchpad/x",
              os.path.join(harness, SPO_SLUG, sid, "scratchpad", "x"), True)]
    return spo_result(spo_shape_probe(cases, tmp),
                      "with TMPDIR at /tmp, the harness base's own folder is no scratchpad, and a project folder under it is")


spo_register("scratchpad-owner: shape 2 with TMPDIR at realpath(/tmp), the Linux layout: <harness base>/scratchpad/x is "
             "no scratchpad", spo_shape_linux_case)
spo_register("scratchpad-owner: real 1 agent B's Write over agent A's file under the scratchpad base: refused",
             spo_real_overwrite_case)
spo_register("scratchpad-owner: real 2 agent B's Write over agent A's file through a symlinked /tmp: refused",
             spo_real_symlink_case)
spo_register("scratchpad-owner: real 3 a script under a scratchpad-shaped folder outside every base: not refused",
             spo_real_outside_case)
spo_register("scratchpad-owner: shape 1 <harness base>/scratchpad/x is no scratchpad, and a project folder under it is",
             spo_shape_case)


# Rule scratchpad-owner, a syntax check of another agent's script. `bash -n F`, `sh -n F`, `zsh -n F` and
# `node --check F` read the file and run nothing, so agent B's check of agent A's file is allowed. A run of the same
# file, a check chained to a run, and a `-c` string that runs the file are refused. `python3 -m py_compile F` is a
# control: the module form names no file to the rule, so it is allowed with or without this change.
spo_register("scratchpad-owner: syntax 1, agent B's bash -n of agent A's script is allowed",
             lambda: spo_data_case("syn-bash-n", "syntax 1, bash -n F", "a_sh.sh", SH_TEXT,
                                   lambda path: "bash -n %s" % path,
                                   "agent B's bash -n of agent A's script is a syntax check, and is allowed"))
spo_register("scratchpad-owner: syntax 2, agent B's node --check of agent A's script is allowed",
             lambda: spo_data_case("syn-node-check", "syntax 2, node --check F", "a_js.js", TS_TEXT,
                                   lambda path: "node --check %s" % path,
                                   "agent B's node --check of agent A's script is a syntax check, and is allowed"))
spo_register("scratchpad-owner: syntax control 1, agent B's sh -n of agent A's script is allowed",
             lambda: spo_data_case("syn-sh-n", "syntax control 1, sh -n F", "a_sh.sh", SH_TEXT,
                                   lambda path: "sh -n %s" % path,
                                   "agent B's sh -n of agent A's script is a syntax check, and is allowed"))
spo_register("scratchpad-owner: syntax control 2, agent B's zsh -n of agent A's script is allowed",
             lambda: spo_data_case("syn-zsh-n", "syntax control 2, zsh -n F", "a_sh.sh", SH_TEXT,
                                   lambda path: "zsh -n %s" % path,
                                   "agent B's zsh -n of agent A's script is a syntax check, and is allowed"))
spo_register("scratchpad-owner: syntax control 3, agent B's python3 -m py_compile of agent A's script is allowed",
             lambda: spo_data_case("syn-py-compile", "syntax control 3, python3 -m py_compile F", "a_py.py", PY_TEXT,
                                   lambda path: "python3 -m py_compile %s" % path,
                                   "agent B's python3 -m py_compile of agent A's script is a syntax check, and is allowed"))
spo_register("scratchpad-owner: syntax 3, agent B's bash run of agent A's script is refused",
             lambda: pr2015_spo_run_case("syn-bash-run", "syntax 3, bash F", "a_sh.sh",
                                         lambda fx, p: "bash %s" % p,
                                         "agent B's bash F run of agent A's script is refused", text=SH_TEXT))
spo_register("scratchpad-owner: syntax 4, agent B's node run of agent A's script is refused",
             lambda: pr2015_spo_run_case("syn-node-run", "syntax 4, node F", "a_js.js",
                                         lambda fx, p: "node %s" % p,
                                         "agent B's node F run of agent A's script is refused", text=TS_TEXT))
spo_register("scratchpad-owner: syntax 5, agent B's bash -n F && bash F, a check then a run, is refused",
             lambda: pr2015_spo_run_case("syn-chain", "syntax 5, bash -n F && bash F", "a_sh.sh",
                                         lambda fx, p: "bash -n %s && bash %s" % (p, p),
                                         "agent B's bash -n F && bash F is refused", text=SH_TEXT))
spo_register("scratchpad-owner: syntax 6, agent B's bash -n -c string that runs agent A's script is refused",
             lambda: pr2015_spo_run_case("syn-c-run", "syntax 6, bash -n -c 'bash F'", "a_sh.sh",
                                         lambda fx, p: 'bash -n -c "bash %s"' % p,
                                         "agent B's bash -n -c string that runs agent A's script is refused",
                                         text=SH_TEXT))
# A shell's `-n` or `--noexec` among its own flags is a check, a cluster included. The other flags are no check:
# a `-n` after the script is the script's argument, `-x` and `-e` run it, and a preload (`node -r`) runs it.
spo_register("scratchpad-owner: syntax 7, agent B's bash F -n, a -n after the script, is refused",
             lambda: pr2015_spo_run_case("syn-n-after", "syntax 7, bash F -n", "a_sh.sh",
                                         lambda fx, p: "bash %s -n" % p,
                                         "agent B's bash F -n run of agent A's script is refused: the -n is the script's argument",
                                         text=SH_TEXT))
spo_register("scratchpad-owner: syntax 8, agent B's bash -nc string that runs agent A's script is refused",
             lambda: pr2015_spo_run_case("syn-nc-run", "syntax 8, bash -nc 'bash F'", "a_sh.sh",
                                         lambda fx, p: 'bash -nc "bash %s"' % p,
                                         "agent B's bash -nc string that runs agent A's script is refused",
                                         text=SH_TEXT))
spo_register("scratchpad-owner: syntax 9, agent B's bash -x F, a trace that runs the script, is refused",
             lambda: pr2015_spo_run_case("syn-x-run", "syntax 9, bash -x F", "a_sh.sh",
                                         lambda fx, p: "bash -x %s" % p,
                                         "agent B's bash -x F run of agent A's script is refused", text=SH_TEXT))
spo_register("scratchpad-owner: syntax 10, agent B's bash -e F, an errexit run of the script, is refused",
             lambda: pr2015_spo_run_case("syn-e-run", "syntax 10, bash -e F", "a_sh.sh",
                                         lambda fx, p: "bash -e %s" % p,
                                         "agent B's bash -e F run of agent A's script is refused", text=SH_TEXT))
spo_register("scratchpad-owner: syntax 13, agent B's node -r ./x.js F, a preload then a run of F, is refused",
             lambda: pr2015_spo_run_case("syn-r-run", "syntax 13, node -r ./x.js F", "a_js.js",
                                         lambda fx, p: "node -r ./x.js %s" % p,
                                         "agent B's node -r ./x.js F run of agent A's script is refused", text=TS_TEXT))
spo_register("scratchpad-owner: syntax 14, agent B's bash -nv of agent A's script is allowed",
             lambda: spo_data_case("syn-nv", "syntax 14, bash -nv F", "a_sh.sh", SH_TEXT,
                                   lambda path: "bash -nv %s" % path,
                                   "agent B's bash -nv of agent A's script is a syntax check, and is allowed"))
spo_register("scratchpad-owner: syntax 15, agent B's bash --noexec of agent A's script is allowed",
             lambda: spo_data_case("syn-noexec", "syntax 15, bash --noexec F", "a_sh.sh", SH_TEXT,
                                   lambda path: "bash --noexec %s" % path,
                                   "agent B's bash --noexec of agent A's script is a syntax check, and is allowed"))


# =========================================================================== mask_script lexemes
