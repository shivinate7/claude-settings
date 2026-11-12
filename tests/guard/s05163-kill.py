# section 5163
FAMILY = "kill"

sh("kill: pkill by pattern denies", "pkill -f node", "deny", "machine-wide-kill", cwd=NOGIT)
sh("kill: pkill by name reaches every match", "pkill node", "deny", "machine-wide-kill", cwd=NOGIT)
sh("kill: pkill with the long flag", 'pkill --full "node server.ts"', "deny", "machine-wide-kill",
   cwd=NOGIT)
sh("kill: killall by name", "killall node", "deny", "machine-wide-kill", cwd=NOGIT)
# Re-pointed (rule shared-trees-no-machine-wide-kill, refusal-vs-rule row machine-wide-kill): a list
# of pids kills nothing, so `lsof -t` alone passes. Its kill is refused where it feeds one, below.
sh("kill: lsof -t lists the pids on a port, kills nothing", "lsof -t -i :3000", "allow", cwd=NOGIT)
sh("kill: the same flag bundled lists the pids, kills nothing", "lsof -ti :3000", "allow", cwd=NOGIT)
sh("kill: lsof -ti piped into xargs kill is the pid list of a kill", "lsof -ti :3000 | xargs kill",
   "deny", "machine-wide-kill", cwd=NOGIT)
sh("kill: a pid list from lsof -ti substituted into kill is refused", "kill $(lsof -ti :3000)",
   "deny", "machine-wide-kill", cwd=NOGIT)
# THE CALL KILLS, NOT ONLY THE SEGMENT. A pid list from `lsof -t` reaches a kill across a filter, a
# loop, a file, or a loop header. `lsof -t` passes only when nothing in the call kills (rule
# shared-trees-no-machine-wide-kill).
sh("kill: lsof -t through head into xargs kill is refused", "lsof -ti:3000 | head -1 | xargs kill -9",
   "deny", "machine-wide-kill", cwd=NOGIT)
sh("kill: lsof -t read by a while loop that kills is refused",
   "lsof -ti:3000 | while read p; do kill $p; done", "deny", "machine-wide-kill", cwd=NOGIT)
sh("kill: lsof -t written to a file, then killed from it, is refused",
   "lsof -ti:3000 > f; kill $(cat f)", "deny", "machine-wide-kill", cwd=NOGIT)
sh("kill: lsof -t in a for header, killed in the loop body, is refused",
   "for p in $(lsof -ti:3000); do kill $p; done", "deny", "machine-wide-kill", cwd=NOGIT)
sh("kill: taskkill by image name", "taskkill /IM node.exe /F", "deny", "machine-wide-kill",
   cwd=NOGIT)
sh("kill: taskkill by image name, dash spelling", "taskkill -im node.exe", "deny",
   "machine-wide-kill", cwd=NOGIT)
sh("kill: Stop-Process by name", "Stop-Process -Name node", "deny", "machine-wide-kill",
   tool="PowerShell", cwd=NOGIT)
sh("kill: Stop-Process by name, abbreviated", "Stop-Process -n node", "deny", "machine-wide-kill",
   tool="PowerShell", cwd=NOGIT)

sh("kill: asking which port is busy kills nothing", "lsof -i :3000", "allow", cwd=NOGIT)
# OWNERSHIP of a pid. The suite is the session root (`CLAUDE_GUARD_ROOT_PID`, set in `decide`).
# OWNED is a live child of the suite. FOREIGN is the suite's own parent: alive, not a descendant.
NOPS = os.path.join(ROOT, "nops")   # an empty directory: `ps` cannot be found through it
os.makedirs(NOPS, exist_ok=True)
OWNED = subprocess.Popen(["sleep", "300"])
FOREIGN = os.getppid()
sh("kill: a pid this session started", "kill %d" % OWNED.pid, "allow", cwd=NOGIT)
sh("kill: a signal flag and a pid this session started", "kill -9 %d" % OWNED.pid, "allow",
   cwd=NOGIT)
sh("kill: a pid nothing is running under", "kill 4194303", "allow", cwd=NOGIT)
sh("kill: a pid held in a variable cannot be read, so it passes", "kill $!", "allow", cwd=NOGIT)
sh("kill: listing signals kills nothing", "kill -l 1", "allow", cwd=NOGIT)
# Re-pointed (rule shared-trees-no-machine-wide-kill, refusal-vs-rule row machine-wide-kill): `pkill -P`
# names the children of ONE parent pid, so a parent this session owns passes, as `kill` does.
sh("kill: pkill -P of the shell's own pid passes", "pkill -P $$", "allow", cwd=NOGIT)
# Ruling (lane orchestrator, process-only, under shared-trees-no-machine-wide-kill, "Kill only yours"):
# a parent that the guard cannot read is no pid this session holds, so only `$$` and `$!` pass.
sh("kill: pkill -P of the last background job's pid passes", "pkill -P $!", "allow", cwd=NOGIT)
sh("kill: pkill -P of a command substitution is refused", "pkill -P $(pgrep -f vite)", "deny",
   "machine-wide-kill", cwd=NOGIT)
sh("kill: pkill -P of PPID is refused", "pkill -P $PPID", "deny", "machine-wide-kill", cwd=NOGIT)
sh("kill: pkill -P of a variable is refused", "pkill -P $SOME_VAR", "deny", "machine-wide-kill",
   cwd=NOGIT)
if os.name != "nt":   # Windows has no `ps`: ownership reads unknown, so these allow
    sh("kill: pkill -P of a parent this session started passes", "pkill -P %d" % OWNED.pid,
       "allow", cwd=NOGIT)
    sh("kill: pkill -P of a parent this session did not start is refused", "pkill -P %d" % FOREIGN,
       "deny", "machine-wide-kill", cwd=NOGIT)
    # pid 1 is init. foreign_pid_kill judges 0, 1 and -1 with no root, so it stays refused whatever ps says.
    sh("kill: pkill -P of init is refused", "pkill -P 1", "deny", "machine-wide-kill", cwd=NOGIT)
else:
    skip_case("kill: pkill -P of a parent this session started passes", NO_PS)
    skip_case("kill: pkill -P of a parent this session did not start is refused", NO_PS)
    skip_case("kill: pkill -P of init is refused", NO_PS)
# SUBSTITUTION, kill. A pkill inside `$( )` or backticks runs, so each form denies as the plain pkill does.
for _name, _command in (
    ("a dollar paren in double quotes", 'echo "$(pkill -f foo)"'),
    ("a dollar paren in an echo", "echo $(pkill -f foo)"),
    ("a dollar paren with spaces inside", "echo $( pkill -f foo )"),
    ("an assignment from a dollar paren", "x=$(pkill -f foo)"),
    ("backticks in an echo", "echo `pkill -f foo`"),
):
    sh("substitution: kill, %s denies" % _name, _command, "deny", "machine-wide-kill", cwd=NOGIT)
# ALLOW controls: a hash opens a comment, so the text after it runs nothing, and an unclosed single
# quote makes bash refuse to parse the line, so it runs nothing.
sh("substitution: kill, a dollar paren after a hash comment allowed", "echo hi # $(pkill -f foo)",
   "allow", cwd=NOGIT)
sh("substitution: kill, a dollar paren after an unclosed quote allowed", "echo Don't $(pkill -f foo)",
   "allow", cwd=NOGIT)
if os.name != "nt":   # Windows has no `ps`: ownership reads unknown, so these allow
    sh("kill: a pid this session did not start", "kill %d" % FOREIGN, "deny", "machine-wide-kill",
       cwd=NOGIT, carries="did not start")
else:
    skip_case("kill: a pid this session did not start", NO_PS)
if os.name != "nt":   # Windows has no `ps`: ownership reads unknown, so these allow
    sh("kill: a foreign pid behind a signal flag", "kill -9 %d" % FOREIGN, "deny",
       "machine-wide-kill", cwd=NOGIT)
else:
    skip_case("kill: a foreign pid behind a signal flag", NO_PS)
if os.name != "nt":   # Windows has no `ps`: ownership reads unknown, so these allow
    sh("kill: a foreign pid behind a named signal", "kill -s TERM %d" % FOREIGN, "deny",
       "machine-wide-kill", cwd=NOGIT)
else:
    skip_case("kill: a foreign pid behind a named signal", NO_PS)
if os.name != "nt":   # Windows has no `ps`: ownership reads unknown, so these allow
    sh("kill: a foreign pid after the end-of-flags mark", "kill -- %d" % FOREIGN, "deny",
       "machine-wide-kill", cwd=NOGIT)
else:
    skip_case("kill: a foreign pid after the end-of-flags mark", NO_PS)
if os.name != "nt":   # Windows has no `ps`: ownership reads unknown, so these allow
    sh("kill: one foreign pid in a list of pids", "kill %d %d" % (OWNED.pid, FOREIGN), "deny",
       "machine-wide-kill", cwd=NOGIT)
else:
    skip_case("kill: one foreign pid in a list of pids", NO_PS)
sh("kill: init", "kill 1", "deny", "machine-wide-kill", cwd=NOGIT)
sh("kill: every process", "kill -9 -- -1", "deny", "machine-wide-kill", cwd=NOGIT)
sh("kill: the shell's own process group", "kill 0", "deny", "machine-wide-kill", cwd=NOGIT)
if os.name != "nt":   # Windows has no `ps`: ownership reads unknown, so these allow
    sh("kill: the session's own claude process", "kill %d" % os.getpid(), "deny",
       "machine-wide-kill", cwd=NOGIT)
else:
    skip_case("kill: the session's own claude process", NO_PS)
sh("kill: init with the root unknown", "kill 1", "deny", "machine-wide-kill", cwd=NOGIT,
   no_root=True)
sh("kill: every process with the root unknown", "kill -9 -- -1", "deny", "machine-wide-kill",
   cwd=NOGIT, no_root=True)
sh("kill: the process group with the root unknown", "kill 0", "deny", "machine-wide-kill",
   cwd=NOGIT, no_root=True)
sh("kill: any other pid with the root unknown is unknown, so it passes", "kill %d" % FOREIGN,
   "allow", cwd=NOGIT, no_root=True)
# AGENT WORKTREES OF THIS SESSION (owner ruling 2026-10-10). A pid whose PPID is 1 is no longer a
# child of this session, but its cwd can still sit in `.claude/worktrees/agent-<id>`. That pid is
# owned when `agent-<id>.jsonl` exists in THIS session's `subagents/` folder. The hook payload's
# `transcript_path` is `<dir>/<session>.jsonl`, and that folder is `<dir>/<session>/subagents/`.
# A worktree of another session, or one not named `agent-<id>`, stays foreign.
SUB_SESSION = "reapbatch-session-0001"   # SESSION_ID_RE: 8 to 200 of [A-Za-z0-9._-]
OTHER_SESSION = "reapbatch-other-0002"
SUBCFG = os.path.join(ROOT, "subcfg")    # a config dir that holds only transcripts
SUBWT = os.path.join(ROOT, "subwt")
OWN_ID, OTHER_ID, PLAIN_ID = "a0246dbf02b4a0327", "b1357ecf13c5b1438", "c2468fd024d6c2549"
ORPHAN_PIDS = []


def spawn_orphan(cwd):
    """A `sleep` whose shell exits first, so the kernel hands it to init (PPID 1), with CWD as its
    working directory. Returns its pid, or None when the parent is not 1 on this host."""
    os.makedirs(cwd, exist_ok=True)
    try:
        answer = subprocess.run(["sh", "-c", "sleep 300 </dev/null >/dev/null 2>&1 & echo $!"],
                                cwd=cwd, capture_output=True, text=True, timeout=20)
        pid = int(answer.stdout.strip())
        ORPHAN_PIDS.append(pid)
        parent = subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)], capture_output=True,
                                text=True, timeout=5).stdout.strip()
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return pid if parent == "1" else None


def spawn_live_parent(cwd):
    """A `sleep` (P) whose parent `sh` (Q) is still ALIVE, and Q was reparented to init (PPID 1),
    so Q's ancestry never reaches the suite root. P sits in CWD. Returns P's pid, or None when the
    shape does not hold on this host. Owner ruling 2026-10-10: this left-behind shape is foreign."""
    os.makedirs(cwd, exist_ok=True)
    try:
        # The inner shell keeps no foreground sleep: `wait` holds it alive, and P is the only
        # sleep, redirected and tracked. Its stderr goes to /dev/null so the suite's stderr is free.
        outer = subprocess.Popen(
            ["sh", "-c", "sh -c 'sleep 300 </dev/null >/dev/null 2>&1 & echo $!; echo $$; wait' "
                         "</dev/null 2>/dev/null &"],
            cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        outer.wait(timeout=20)   # the outer shell exits; its background child is reparented
        child, parent = int(outer.stdout.readline()), int(outer.stdout.readline())
        ORPHAN_PIDS.extend([child, parent])
        ps_parent = subprocess.run(["ps", "-o", "ppid=", "-p", str(parent)], capture_output=True,
                                   text=True, timeout=5).stdout.strip()
        ps_child = subprocess.run(["ps", "-o", "ppid=", "-p", str(child)], capture_output=True,
                                  text=True, timeout=5).stdout.strip()
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return child if (ps_parent == "1" and ps_child == str(parent)) else None


ORPHAN_CASES = os.name != "nt"   # Windows has no `ps`: ownership reads unknown, so none are run
PROJECT_DIR = os.path.join(SUBCFG, "projects", "-reapbatch-slug")
SUB_TRANSCRIPT = os.path.join(PROJECT_DIR, SUB_SESSION + ".jsonl")   # the payload's transcript_path
if ORPHAN_CASES:
    write(SUB_TRANSCRIPT, "{}\n")
    for session, agent_id in ((SUB_SESSION, OWN_ID), (OTHER_SESSION, OTHER_ID),
                              (SUB_SESSION, PLAIN_ID)):
        write(os.path.join(PROJECT_DIR, session, "subagents", "agent-" + agent_id + ".jsonl"),
              "{}\n")
    OWN_PID = spawn_orphan(os.path.join(SUBWT, ".claude", "worktrees", "agent-" + OWN_ID))
    OTHER_PID = spawn_orphan(os.path.join(SUBWT, ".claude", "worktrees", "agent-" + OTHER_ID))
    PLAIN_PID = spawn_orphan(os.path.join(SUBWT, ".claude", "worktrees", PLAIN_ID))
    LIVE_PID = spawn_live_parent(os.path.join(SUBWT, ".claude", "worktrees", "agent-" + OWN_ID))
    if None in (OWN_PID, OTHER_PID, PLAIN_PID, LIVE_PID):
        print("note: no PPID-1 orphan on this host, so the agent-worktree kill cases are not run")
        ORPHAN_CASES = False
if ORPHAN_CASES:
    sh("kill: a PPID-1 pid whose cwd is in this session's agent worktree", "kill %d" % OWN_PID,
       "allow", cwd=NOGIT, session=SUB_SESSION, config=SUBCFG, transcript=SUB_TRANSCRIPT)
    sh("kill: a PPID-1 pid in another session's agent worktree", "kill %d" % OTHER_PID, "deny",
       "machine-wide-kill", cwd=NOGIT, session=SUB_SESSION, config=SUBCFG,
       transcript=SUB_TRANSCRIPT, carries="did not start")
    sh("kill: a PPID-1 pid in a worktree not named agent-<id>", "kill %d" % PLAIN_PID, "deny",
       "machine-wide-kill", cwd=NOGIT, session=SUB_SESSION, config=SUBCFG,
       transcript=SUB_TRANSCRIPT)
    sh("kill: a pid in this session's agent worktree whose parent is alive, not init",
       "kill %d" % LIVE_PID, "deny", "machine-wide-kill", cwd=NOGIT, session=SUB_SESSION,
       config=SUBCFG, transcript=SUB_TRANSCRIPT, carries="did not start")
else:
    skip_case("kill: a PPID-1 pid whose cwd is in this session's agent worktree", NO_ORPHAN)
    skip_case("kill: a PPID-1 pid in another session's agent worktree", NO_ORPHAN)
    skip_case("kill: a PPID-1 pid in a worktree not named agent-<id>", NO_ORPHAN)
    skip_case("kill: a pid in this session's agent worktree whose parent is alive, not init", NO_ORPHAN)

# THE SESSION TAG (decision a-kill-by-pid-needs-an-owned-pid). A PPID-1 pid is owned when its
# ENVIRONMENT holds `CLAUDE_CODE_SESSION_ID=<this session's id>` exactly, the id the payload's
# `session_id` carries. argv, a suffix or prefix of the entry, another variable's value and an empty
# entry do not own it. Each holder is a python process that calls setsid, so it leads its own process
# group, which the group case names. Pids 0, 1 and -1 stay denied by the `kill: init`, `kill: every
# process` and `kill: the shell's own process group` cases above, and by their root-unknown twins.
TAG = "CLAUDE_CODE_SESSION_ID"
TAG_CWD = os.path.join(ROOT, "tagged")   # a scratch folder, not an agent worktree
TAG_HOLDER = "import os, time; os.setsid(); time.sleep(300)"


def tag_orphan(env_entries=(), argv_extra=(), holder=None):
    """A holder whose shell exits first, so init adopts it (PPID 1). `env_entries` are NAME=value
    strings for its environment, with the inherited tag removed first. `argv_extra` is appended to
    its argv. `holder` replaces the holder's argv (a shell stub, which leads no group of its own,
    so only PPID 1 is waited for). Returns its pid, or None when it is not an orphan leading its
    own process group (an orphan, for a `holder`)."""
    env = {key: value for key, value in os.environ.items() if key != TAG}
    env.update(entry.split("=", 1) for entry in env_entries)
    os.makedirs(TAG_CWD, exist_ok=True)
    script = '"$@" </dev/null >/dev/null 2>&1 & echo $!'
    try:
        answer = subprocess.run(["sh", "-c", script, "sh"] + (holder or [sys.executable, "-c", TAG_HOLDER])
                                + list(argv_extra), cwd=TAG_CWD, env=env, capture_output=True,
                                text=True, timeout=20)
        pid = int(answer.stdout.strip())
        ORPHAN_PIDS.append(pid)
        for _ in range(100):   # setsid runs a moment after the shell exits
            ppid, pgid = subprocess.run(["ps", "-o", "ppid=,pgid=", "-p", str(pid)],
                                        capture_output=True, text=True, timeout=5).stdout.split()
            if ppid != "1":
                return None
            if holder or pgid == str(pid):
                return pid
            time.sleep(0.05)  # poll gap of a condition wait: ends when the pgid reads back, not on elapsed time
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return None


def stranded_job(job_env_words, wrappers=0):
    """The `holder` of a stranded stub: a shell that runs one `sleep` as its child and waits. The
    child's environment is set by `job_env_words`: `env NAME=value` gives it a tag, `env -u NAME`
    takes the stub's away. `wrappers` adds that many shell wrappers between the stub and the job.
    The stub's own environment is `env_entries` of tag_orphan."""
    return ["sh", "-c", '"$@" & wait', "sh"] * (1 + wrappers) + list(job_env_words) + ["sleep", "300"]


def child_of(parent):
    """The pid of the one child of `parent`, once it has forked one, or None."""
    for _ in range(100):
        try:
            rows = subprocess.run(["ps", "-axo", "pid=,ppid="], capture_output=True, text=True,
                                  timeout=10).stdout.splitlines()
        except (OSError, subprocess.SubprocessError):
            return None
        for row in rows:
            fields = row.split()
            if len(fields) == 2 and fields[1] == str(parent) and fields[0].isdigit():
                ORPHAN_PIDS.append(int(fields[0]))
                return int(fields[0])
        time.sleep(0.05)  # poll gap of a condition wait: ends when a child shows in ps, not on elapsed time
    return None


def stub_job(stub, depth=1):
    """The pid `depth` levels under `stub`, once that pid has exec'd `sleep`, or None. Until its
    exec, a forked pid holds its parent's environment, so the tag is read only after it."""
    pid = stub
    for _ in range(depth):
        pid = child_of(pid)
        if pid is None:
            return None
    for _ in range(100):
        try:
            comm = subprocess.run(["ps", "-o", "comm=", "-p", str(pid)], capture_output=True,
                                  text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None
        if comm == "sleep":
            return pid
        time.sleep(0.05)  # poll gap of a condition wait: ends when comm reads sleep, not on elapsed time
    return None


def tag_case(name, expected, env_entries=(), argv_extra=(), session=SUB_SESSION, carries=(),
             holder=None, job=False, depth=1, **who):
    """One kill of a PPID-1 holder, or with `job` of the pid `depth` levels under a stranded stub
    (`holder` from stranded_job). Returns the killed pid, or None when it was skipped. `who` is
    agent_id and agent_type, the payload fields that mark an agent call."""
    pid = tag_orphan(env_entries, argv_extra, holder) if ORPHAN_CASES else None
    if pid is not None and job:
        pid = stub_job(pid, depth)
    if pid is None:
        skip_case(name, NO_ORPHAN)
    else:
        sh(name, "kill %d" % pid, expected, "machine-wide-kill" if expected == "deny" else None,
           cwd=NOGIT, session=session, config=SUBCFG, transcript=SUB_TRANSCRIPT, carries=carries,
           **who)
    return pid


TAG_LEADER = tag_case("kill: a PPID-1 pid whose environment holds this session's id", "allow",
                      env_entries=[TAG + "=" + SUB_SESSION])
# Every agent shares the main session's id, so the tag owns a pid for the main session only
# (decision a-kill-by-pid-needs-an-owned-pid). A truthy agent_id or agent_type
# marks an agent call, which keeps the agent-worktree rule alone. AGENT_CALLS is the one list of
# those call shapes; the stranded-job cases below loop over it too.
AGENT_CALLS = (("agent_id and agent_type", dict(agent_id="tag-sub1", agent_type="general-purpose")),
               ("agent_id only", dict(agent_id="tag-sub1")),
               ("agent_type only", dict(agent_type="general-purpose")))
for _who, _kw in AGENT_CALLS:
    tag_case("kill: a PPID-1 pid with this session's id, called by an agent (%s)" % _who, "deny",
             env_entries=[TAG + "=" + SUB_SESSION], carries="did not start", **_kw)
tag_case("kill: a PPID-1 pid whose environment holds another session's id", "deny",
         env_entries=[TAG + "=" + OTHER_SESSION], carries="did not start")
tag_case("kill: a PPID-1 pid with no session id in its environment", "deny",
         carries="did not start")
tag_case("kill: a PPID-1 pid with this session's id only in its argv", "deny",
         argv_extra=[TAG + "=" + SUB_SESSION], carries="did not start")
tag_case("kill: a PPID-1 pid whose session id entry has a suffix", "deny",
         env_entries=[TAG + "=" + SUB_SESSION + "x"], carries="did not start")
tag_case("kill: a PPID-1 pid whose session id entry has a prefix", "deny",
         env_entries=["X_" + TAG + "=" + SUB_SESSION], carries="did not start")
tag_case("kill: a PPID-1 pid with this session's id as another variable's value", "deny",
         env_entries=["SESSION_HINT=" + SUB_SESSION], carries="did not start")
tag_case("kill: a PPID-1 pid with an empty session id entry and no id in the payload", "deny",
         env_entries=[TAG + "="], session=None, carries="did not start")
if TAG_LEADER is None:
    skip_case("kill: the group led by a PPID-1 pid whose environment holds this session's id",
              NO_ORPHAN)
else:
    sh("kill: the group led by a PPID-1 pid whose environment holds this session's id",
       "kill -- -%d" % TAG_LEADER, "allow", cwd=NOGIT, session=SUB_SESSION, config=SUBCFG,
       transcript=SUB_TRANSCRIPT)
# A STRANDED JOB. After a stall the stub shell is under init, and the job is its child. In a real
# stall the stub holds no tag and the job holds the session tag. The guard owns a pid that holds this
# session's id when its parent or grandparent is init (decision a-kill-by-pid-needs-an-owned-pid),
# so a tagged job under a stub is owned whether the stub is tagged or not. The cases below check that
# in the main session, and that these stay refused: an agent call, which passes no session id and so
# owns no pid by tag; a job with no id or another session's id; an untagged job under a tagged stub;
# a tagged job two levels under the stub, where init is the great-grandparent. The wait form,
# bin/wait-pid, owns these shapes by its own test (lint/test_wait_pid.py).
tag_case("kill: a job under an untagged PPID-1 stub, holding this session's id, from the main session",
         "allow", holder=stranded_job(["env", TAG + "=" + SUB_SESSION]), job=True)
tag_case("kill: a job under a tagged PPID-1 stub, holding this session's id, from the main session",
         "allow", env_entries=[TAG + "=" + SUB_SESSION],
         holder=stranded_job(["env", TAG + "=" + SUB_SESSION]), job=True)
for _who, _kw in AGENT_CALLS:
    tag_case("kill: a job under an untagged PPID-1 stub, holding this session's id, called by an agent (%s)"
             % _who, "deny", holder=stranded_job(["env", TAG + "=" + SUB_SESSION]), job=True,
             carries="did not start", **_kw)
tag_case("kill: a job under an untagged PPID-1 stub, holding another session's id, stays refused",
         "deny", holder=stranded_job(["env", TAG + "=" + OTHER_SESSION]), job=True,
         carries="did not start")
tag_case("kill: a tagged job two levels under an untagged PPID-1 stub, from the main session, stays refused",
         "deny", holder=stranded_job(["env", TAG + "=" + SUB_SESSION], wrappers=1), job=True, depth=2,
         carries="did not start")
tag_case("kill: a job under a PPID-1 stub that holds this session's id, the job untagged, stays refused",
         "deny", env_entries=[TAG + "=" + SUB_SESSION], holder=stranded_job(["env", "-u", TAG]),
         job=True, carries="did not start")
tag_case("kill: a job under a PPID-1 stub, neither holding a session id, stays refused", "deny",
         holder=stranded_job(["env", "-u", TAG]), job=True, carries="did not start")

sh("kill: a pid list made by pgrep", "kill $(pgrep -f node)", "deny", "machine-wide-kill",
   cwd=NOGIT)
sh("kill: a pid list made by pidof", "kill -9 $(pidof node)", "deny", "machine-wide-kill",
   cwd=NOGIT)
sh("kill: a pid list made by pgrep, backtick form", "kill `pgrep node`", "deny",
   "machine-wide-kill", cwd=NOGIT)
sh("kill: a pid list made by pgrep, spaced and by path", "kill $( /usr/bin/pgrep node )",
   "deny", "machine-wide-kill", cwd=NOGIT)
sh("kill: a pid list made by pgrep behind command", "kill $(command pgrep node)", "deny",
   "machine-wide-kill", cwd=NOGIT)
sh("kill: pgrep piped into xargs kill", "pgrep -f node | xargs kill", "deny",
   "machine-wide-kill", cwd=NOGIT)
sh("kill: xargs kill after a pipe from a plain list is not by name", "echo 1 | xargs kill -l",
   "allow", cwd=NOGIT)
sh("kill: pgrep alone only reads", "pgrep -f node", "allow", cwd=NOGIT)

# Four ways to stop a process by port, or every
# process, and the guard must refuse each. `kill $(lsof -t ...)` is the `$(pgrep ...)` act: the pid list is made by
# a pattern, but the guard names only pgrep and pidof. `fuser -k` and `kill-port` kill by port, the
# same act as `lsof -t | xargs kill`. `kill -9 -1` reads `-1` as a flag, so pid -1 (every process)
# never reaches the pid check; `kill -9 -- -1` above already denies. Claude writes each of these when
# a dev server holds a port, so each is a mistake it could make. `kill -KILL -1` and `kill -s KILL -1`
# are the same safety hole as `kill -9 -1`; they were found while verifying the finding, not named in it.
for _name, _command in (
    ("a pid list made by lsof -t", "kill $(lsof -t -i :3000)"),
    ("a pid list made by lsof -ti behind a signal", "kill -9 $(lsof -ti :3000)"),
    ("a pid list made by lsof -t, backtick form", "kill `lsof -t -i :3000`"),
    ("fuser -k by port", "fuser -k 3000/tcp"),
    ("fuser -k bundled with -n", "fuser -kn tcp 3000"),
    ("npx kill-port", "npx kill-port 3000"),
    ("npx kill-port behind a flag", "npx --yes kill-port 3000"),
    ("kill-port on the path", "kill-port 3000"),
    ("every process behind a signal number", "kill -9 -1"),
    ("every process behind a signal name", "kill -KILL -1"),
    ("every process behind -s", "kill -s KILL -1"),
):
    sh("kill: " + _name, _command, "deny", "machine-wide-kill", cwd=NOGIT)
sh("kill: every process behind a signal number, with the root unknown", "kill -9 -1", "deny",
   "machine-wide-kill", cwd=NOGIT, no_root=True)
# The matchers read the COMMAND WORD, so a tool named in text, and a read of a port, stay allowed:
# `fuser` without -k lists the holders, and kill-port in a quoted message is text.
sh("kill: fuser without -k only lists the holders", "fuser -v 3000/tcp", "allow", cwd=NOGIT)
sh("kill: grep for kill-port in a file is no kill", 'grep -n "kill-port" package.json', "allow",
   cwd=NOGIT)
# A pid list read from a file the session wrote
# is no pattern kill, so the new `$(lsof -t ...)` match must not widen to every substitution.
sh("kill: a pid list read from a file is no pattern kill", "kill $(cat f)", "allow", cwd=NOGIT)
sh("kill: a commit message that names fuser -k and kill-port is no kill",
   VCS + ' commit -m "docs: refuse fuser -k and kill-port"', "allow", cwd=NOGIT)
sh("kill: one process id with taskkill", "taskkill /PID 4711 /F", "allow", cwd=NOGIT)
sh("kill: one process id with Stop-Process", "Stop-Process -Id 123", "allow", tool="PowerShell",
   cwd=NOGIT)
sh("kill: taskkill by image name, no other flag", "taskkill /IM node.exe", "deny",
   "machine-wide-kill", cwd=NOGIT)
sh("kill: xargs unwraps to the real command it runs", "xargs pkill", "deny",
   "machine-wide-kill", cwd=NOGIT)

# THE PLAYWRIGHT BROWSER CACHE. Owner ruling: a command that sets PLAYWRIGHT_BROWSERS_PATH is
# refused, mechanically. INCIDENT 2026-10-10: a feed-build session pointed the variable at a scratch
# directory to work around a missing chromium_headless_shell. The real cause was a stale `__dirlock`
# in ~/Library/Caches/ms-playwright. The install sat 73 minutes, and the workaround hid the cause.
# One table of set forms. One row per branch the walk in guard_kill.py reads: each regex alternative
# and each list entry it matches (PLAYWRIGHT_PS_SET, PLAYWRIGHT_PROFILE, ASSIGNING_BUILTINS,
# INLINE_SCRIPT_SHELLS, the cmdlet names), each wrapper form, each write route, the printf filter,
# the continuation. Row: (name, command, tool).
PLAYWRIGHT_SET_DENY = (
    # The shell words that set the variable.
    ("playwright: an inline assignment ahead of an install",
     "PLAYWRIGHT_BROWSERS_PATH=/tmp/x npx playwright install chromium", "Bash"),
    ("playwright: an export ahead of a test run",
     "export PLAYWRIGHT_BROWSERS_PATH=/tmp/x; npm test", "Bash"),
    ("playwright: env names the variable for a test run",
     "env PLAYWRIGHT_BROWSERS_PATH=/tmp/x npx playwright test", "Bash"),
    ("playwright: bash -c sets it", 'bash -c "export PLAYWRIGHT_BROWSERS_PATH=/x"', "Bash"),
    ("playwright: eval sets it", 'eval "export PLAYWRIGHT_BROWSERS_PATH=/x"', "Bash"),
    ("playwright: a subshell assigns it ahead of a test run",
     "(PLAYWRIGHT_BROWSERS_PATH=/x npx playwright test)", "Bash"),
    ("playwright: cmd /c set sets it", "cmd /c set PLAYWRIGHT_BROWSERS_PATH=C:\\x", "Bash"),
    ("playwright: cmd /c with a quoted set sets it",
     'cmd /c "set PLAYWRIGHT_BROWSERS_PATH=C:\\x"', "Bash"),
    ("playwright: sh -c assigns it ahead of a test run",
     "sh -c 'PLAYWRIGHT_BROWSERS_PATH=/x npx playwright test'", "Bash"),
    ("playwright: builtin export sets it", "builtin export PLAYWRIGHT_BROWSERS_PATH=/x", "Bash"),
    ("playwright: exec env names it", "exec env PLAYWRIGHT_BROWSERS_PATH=/x npx", "Bash"),
    ("playwright: a case-folded name still sets it", "playwright_browsers_path=/x npx", "Bash"),
    ("playwright: npx cross-env sets it ahead of an install",
     "npx cross-env PLAYWRIGHT_BROWSERS_PATH=/x npx playwright install", "Bash"),
    ("playwright: cross-env sets it ahead of an install, bare",
     "cross-env PLAYWRIGHT_BROWSERS_PATH=/x npx playwright install", "Bash"),
    # PowerShell statements: one row per form the PowerShell reader matches.
    ("playwright: the PowerShell form sets it", '$env:PLAYWRIGHT_BROWSERS_PATH = "C:\\x"', "PowerShell"),
    ("playwright: PowerShell += appends to it",
     '$env:PLAYWRIGHT_BROWSERS_PATH += ";C:\\x"', "PowerShell"),
    ("playwright: PowerShell braced env drive sets it",
     '${env:PLAYWRIGHT_BROWSERS_PATH} = "C:\\x"', "PowerShell"),
    ("playwright: Set-Item on the env drive sets it", "Set-Item env:PLAYWRIGHT_BROWSERS_PATH C:\\x",
     "PowerShell"),
    ("playwright: Set-Item on the Env:\\ drive sets it", "Set-Item Env:\\PLAYWRIGHT_BROWSERS_PATH C:\\x",
     "PowerShell"),
    ("playwright: the New-Item alias ni sets the env drive variable, denies",
     r"ni env:PLAYWRIGHT_BROWSERS_PATH -Value D:\x", "PowerShell"),
    ("playwright: SetEnvironmentVariable sets it",
     '[Environment]::SetEnvironmentVariable("PLAYWRIGHT_BROWSERS_PATH","C:\\x")', "PowerShell"),
    ("playwright: the real PowerShell setter inside pwsh -c stays denied",
     """pwsh -c '$env:PLAYWRIGHT_BROWSERS_PATH = "x"'""", "Bash"),
    ("playwright: a PowerShell path ending in a backslash, then a setter on the next line, denies",
     "Set-Location C:\\tmp\\\nSet-Item env:PLAYWRIGHT_BROWSERS_PATH D:\\cache", "PowerShell"),
    # Profile writes: one row per write route, and one row per profile file name.
    ("playwright: a shell rc file gets the export",
     "echo 'export PLAYWRIGHT_BROWSERS_PATH=/x' >> ~/.zshrc", "Bash"),
    ("playwright: a heredoc writes the export into a shell rc file",
     "cat >> ~/.zshrc <<'EOF'\nexport PLAYWRIGHT_BROWSERS_PATH=/x\nEOF", "Bash"),
    ("playwright: tee appends the export to a shell rc file",
     "echo 'export PLAYWRIGHT_BROWSERS_PATH=/x' | tee -a ~/.zshrc", "Bash"),
    ("playwright: printf with a %s format writes the export to zshrc, denies",
     "printf 'export PLAYWRIGHT_BROWSERS_PATH=%s\\n' \"$HOME/pw\" >> ~/.zshrc", "Bash"),
    ("playwright: printf writes the export line into zshrc, denies",
     'printf "%s\\n" "export PLAYWRIGHT_BROWSERS_PATH=/x" >> ~/.zshrc', "Bash"),
    ("playwright: echo writes the export line into zshrc past noclobber with >|, denies",
     "echo 'export PLAYWRIGHT_BROWSERS_PATH=/x' >| ~/.zshrc", "Bash"),
    ("playwright: an echo appends the export to ~/.zshenv",
     "echo 'export PLAYWRIGHT_BROWSERS_PATH=/x' >> ~/.zshenv", "Bash"),
    ("playwright: an echo appends the export to ~/.zlogin",
     "echo 'export PLAYWRIGHT_BROWSERS_PATH=/x' >> ~/.zlogin", "Bash"),
    ("playwright: an echo appends the export to ~/.bash_login",
     "echo 'export PLAYWRIGHT_BROWSERS_PATH=/x' >> ~/.bash_login", "Bash"),
    ("playwright: an envrc file gets the assignment",
     "echo PLAYWRIGHT_BROWSERS_PATH=/x > .envrc", "Bash"),
    # A backslash-newline is a continuation, so the assignment still reaches the install.
    ("playwright: an assignment continued by a backslash-newline still sets it for an install",
     "PLAYWRIGHT_BROWSERS_PATH=/x \\\nnpx playwright install", "Bash"),
)
for _name, _command, _tool in PLAYWRIGHT_SET_DENY:
    sh(_name, _command, "deny", "playwright-browsers-path", tool=_tool, cwd=NOGIT)
# Re-pointed (class a): decision playwright-install-once allows a main-session install only as the
# Node 22 cli.js form. The subject is unchanged: the headless shell installs by its own name.
sh("playwright: the headless shell installs by its own name",
   "npx -y node@22 node_modules/playwright/cli.js install chromium-headless-shell", "allow",
   cwd=NOGIT)
sh("playwright: echo only reads the variable", "echo $PLAYWRIGHT_BROWSERS_PATH", "allow",
   cwd=NOGIT)
sh("playwright: grep only reads the name", "grep -r PLAYWRIGHT_BROWSERS_PATH .", "allow",
   cwd=NOGIT)
sh("playwright: unset clears the variable", "unset PLAYWRIGHT_BROWSERS_PATH", "allow", cwd=NOGIT)
# THE UNGUARDED VARIABLE DELETE. Decision rm-on-a-variable-needs-a-guard (owner ruling, 2026-10-11,
# item 1). A recursive rm whose target has an unguarded variable, then "/", then a glob, another
# variable, a slash, a quote, or the end, is refused: Claude Code's prompt shape. A literal after
# the slash is not refused. The remedy is ${NAME:?} only when every such name is safe (the
# allow-list), else a literal path that prints no expanded path.
sh("rm-var: a loop deletes under an unguarded variable",
   "S=/tmp/x; for d in a b; do rm -rf $S/$d; done", "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("rm -rf ${S:?}/${d:?}",))
# New (allow-list passes): each name is a literal or mktemp binding, so the remedy is ${NAME:?}.
sh("rm-var: the mailaudit incident loop gets ${NAME:?} advice",
   "S=/tmp/mailaudit; for d in rv5 rv5full; do rm -rf $S/$d; done", "deny", "rm-var-unguarded",
   cwd=NOGIT, carries=("rm -rf ${S:?}/${d:?}",), lacks=("literal path",))
sh("rm-var: a variable set to a literal path before a glob gets ${D:?} advice",
   'D=/tmp/w; rm -rf "$D"/*', "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=('rm -rf "${D:?}"/*',), lacks=("literal path",))
sh("rm-var: a variable set from mktemp before a glob gets ${D:?} advice",
   'D=$(mktemp -d); rm -rf "$D"/*', "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=('rm -rf "${D:?}"/*',), lacks=("literal path",))
# Trigger shape (ruling item 1): refused when an unguarded variable is followed by "/" and then a
# glob, another variable, a slash, a quote, or the end. Each name is unassigned, so the remedy is
# the literal path.
sh("rm-var: a variable then a glob is refused",
   "rm -rf $S/*", "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${S:?}",))
sh("rm-var: a quoted variable then a variable is refused",
   'rm -rf "$S"/$d', "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${S:?}",))
sh("rm-var: a variable then a trailing slash is refused",
   "rm -rf $S/", "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${S:?}",))
# Windows only: a Git Bash drive spelling (/c/Users/<name>) names the real home, so the variable
# is the home folder or the drive root and the remedy is the literal path, never ${S:?}.
if os.name == "nt":
    _home = os.path.expanduser("~")
    _gb = "/" + _home[0].lower() + _home[2:].replace("\\", "/")
    sh("rm-var: a variable set to the home folder in Git Bash spelling names a literal path",
       "S=%s; rm -rf $S/" % _gb, "deny", "rm-var-unguarded", cwd=NOGIT,
       carries=("literal path",), lacks=("${S:?}",))
    sh("rm-var: a variable set to the drive root in Git Bash spelling names a literal path",
       "S=/%s; rm -rf $S/" % _home[0].lower(), "deny", "rm-var-unguarded", cwd=NOGIT,
       carries=("literal path",), lacks=("${S:?}",))
# Not refused (ruling item 1): a literal follows the slash, so Claude Code does not prompt.
sh("rm-var: a quoted $ROOT with a literal dist is not refused",
   'rm -rf "$ROOT/dist"', "allow", cwd=NOGIT)
sh("rm-var: a quoted $HOME with a literal cache path is not refused",
   'rm -rf "$HOME/.cache/x"', "allow", cwd=NOGIT)
sh("rm-var: $TMPDIR with a literal path is not refused",
   "rm -rf $TMPDIR/foo", "allow", cwd=NOGIT)
# D is unassigned, so the remedy is the literal path.
sh("rm-var: a quoted variable before a glob",
   'rm -rf "$D"/*', "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${D:?}",))
# D is unassigned, so the remedy is the literal path.
sh("rm-var: a variable before a trailing slash",
   "rm -rf $D/", "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${D:?}",))
# The target is a glob, which is the trigger shape.
sh("rm-var: a braced variable with no guard",
   'rm -r "${D}"/*', "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${D:?}",))
# $S is unassigned in the script, so the remedy is the literal path.
sh("rm-var: sh -c runs the unguarded delete",
   "sh -c 'rm -rf $S/*'", "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${S:?}",))
# S and d are unassigned, so the remedy is the literal path.
sh("rm-var: the short flag order counts too",
   "rm -fr $S/$d", "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${S:?}", "${d:?}"))
# $HOME is tainted: a ${NAME:?} guard does not clear it (the docs say so), so the refusal names a
# literal path and never offers ${HOME:?}. The reason may name either form. The target is a variable
# after the slash, which is the trigger shape.
sh("rm-var: $HOME under a recursive delete names a literal path, not ${HOME:?}",
   "rm -rf $HOME/$d", "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("HOME:?", os.path.expanduser("~")))
# $S is unassigned in the script, so the remedy is the literal path. The escaped dollar must not
# reach the reason: eval's double quotes turn \$ into $, so the remedy must be the plain guarded
# target with no backslash before $.
sh("rm-var: eval with an escaped dollar prints no backslash",
   'eval "rm -rf \\$S/*"', "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("\\$", "${S:?}"))
# Scanner cases (rule building-scanner-respects-strings): a comment opener, a double slash, a lone
# quote, and a newline inside a quoted string must not hide the live rm that follows.
# S is assigned a literal and the target is $S/*, so the allow-list gives ${S:?} advice.
sh("rm-var: a hash inside a string does not hide the delete",
   'S=/tmp/x; echo "#"; rm -rf $S/*', "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("rm -rf ${S:?}/*",))
sh("rm-var: a double slash inside a string does not hide the delete",
   'S=/tmp/x; echo "a // b"; rm -rf $S/*', "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("rm -rf ${S:?}/*",))
sh("rm-var: a lone quote in echo text does not hide the delete",
   'S=/tmp/x; echo "it\'s"; rm -rf $S/*', "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("rm -rf ${S:?}/*",))
sh("rm-var: a newline inside a quoted string does not hide the delete",
   'S=/tmp/x; echo "a\nb"; rm -rf $S/*', "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("rm -rf ${S:?}/*",))
sh("rm-var: a trailing comment does not hide a live delete",
   "S=/tmp/x; rm -rf $S/* # note", "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("rm -rf ${S:?}/*",))
# New scanner case: a slash-star inside a string is not a comment, so the delete after it is found.
sh("rm-var: a slash-star inside a string does not hide the delete",
   'S=/tmp/x; echo "/*"; rm -rf $S/*', "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("rm -rf ${S:?}/*",))
# Allow cases: a guarded target, a bare variable, a literal path, a non-recursive rm, text that
# only mentions rm, and a literal single-quoted $ (no expansion).
sh("rm-var: a guarded loop target passes",
   'rm -rf "${S:?}/${d:?}"', "allow", cwd=NOGIT)
sh("rm-var: a guarded variable before a glob passes",
   'rm -rf "${D:?}"/*', "allow", cwd=NOGIT)
sh("rm-var: a bare variable is not refused",
   'rm -rf "$d"', "allow", cwd=NOGIT)
sh("rm-var: a literal relative path passes",
   "rm -rf build/out", "allow", cwd=NOGIT)
sh("rm-var: a non-recursive delete passes",
   "rm $S/file", "allow", cwd=NOGIT)
sh("rm-var: echo only prints the delete",
   "echo rm -rf $S/x", "allow", cwd=NOGIT)
sh("rm-var: a quoted string that mentions the delete passes",
   'echo "rm -rf $S/x"', "allow", cwd=NOGIT)
sh("rm-var: a newline inside a string that mentions the delete passes",
   'echo "a\nrm -rf $S/x"', "allow", cwd=NOGIT)
sh("rm-var: a single-quoted dollar is a literal path",
   "rm -rf '$S/x'", "allow", cwd=NOGIT)
# New (ruling item 1, literal-path reason): a name with no safe binding gets the literal-path
# reason. The reason prints no ${NAME:?} advice and no expanded path. Each lacks list names the
# advice form and any path the shell would expand.
sh("rm-var: an inherited OLDPWD before a glob names a literal path",
   'rm -rf "$OLDPWD"/*', "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${OLDPWD:?}",))
sh("rm-var: a $USER path before a glob names a literal path",
   "rm -rf /Users/$USER/*", "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${USER:?}", "/Users/"))
sh("rm-var: an unassigned quoted variable before a glob names a literal path",
   'rm -rf "$S"/*', "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${S:?}",))
sh("rm-var: a variable set to .. names a literal path",
   'D=..; rm -rf "$D"/*', "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${D:?}",))
sh("rm-var: a variable set to . names a literal path",
   'D=.; rm -rf "$D"/*', "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${D:?}",))
sh("rm-var: a variable set to / names a literal path",
   'D=/; rm -rf "$D"/*', "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${D:?}",))
sh("rm-var: a loop over . and .. names a literal path",
   'for d in . ..; do rm -rf "$d"/*; done', "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${d:?}",))
sh("rm-var: a read loop names a literal path",
   'find . -type d | while read d; do rm -rf "$d"/*; done', "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${d:?}",))
sh("rm-var: a cd before the delete names a literal path",
   'S=build; cd .. && rm -rf "$S"/', "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${S:?}",))
sh("rm-var: a tilde value in bash -c names a literal path",
   'D=~; bash -c "rm -rf $D/*"', "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${D:?}", os.path.expanduser("~")))
# Flagged reading (see Input Needed): the decision's shape list does not name "..", so this case
# pins that a parent step after the slash is still refused.
sh("rm-var: a parent step after a set literal names a literal path",
   'S=build; rm -rf "$S"/../*', "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${S:?}",))
sh("rm-var: a git toplevel value names a literal path",
   'ROOT=$(git rev-parse --show-toplevel); rm -rf "$ROOT"/*', "deny", "rm-var-unguarded",
   cwd=NOGIT, carries=("literal path",), lacks=("${ROOT:?}",))
sh("rm-var: a literal value that resolves to the cwd names a literal path",
   'D=%s; rm -rf "$D"/*' % NOGIT, "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${D:?}", NOGIT))
# Taint (decision rm-on-a-variable-needs-a-guard): $HOME, $PWD and a variable set
# from $(pwd) or $HOME are refused with the literal-path reason when in the trigger shape, even
# when guarded. The reason never names ${NAME:?} advice for that name.
sh("rm-var: a guarded $HOME target is refused for a literal path",
   "rm -rf ${HOME:?}/*", "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${HOME:?}", os.path.expanduser("~")))
sh("rm-var: a quoted guarded $HOME before a glob is refused for a literal path",
   'rm -rf "${HOME:?}"/*', "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${HOME:?}", os.path.expanduser("~")))
sh("rm-var: $PWD is refused and its remedy names no ${PWD:?} advice",
   'rm -rf "$PWD"/*', "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${PWD:?}",))
sh("rm-var: a quoted guarded $PWD is refused and its remedy names no ${PWD:?} advice",
   'rm -rf "${PWD:?}"/*', "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${PWD:?}",))
# ---- rm-var taint spellings, one table against the assigned-value reader. A delete whose variable is
# set from pwd, HOME or ~ (in any substitution, loop or quoting) is tainted, so its refusal names the
# literal path and never ${NAME:?}. guard_rm_var.rm_var_hits reads the bindings (_rm_values) and the
# taint names, and the one sh() case per distinct branch stays above. Incident 2026-10-10 to 10-11:
# 7 of 24 Bash prompts were rm on a $var path. Rows: (text, name). Each is a spelling that reaches a
# branch the sh() rows already hold, so it is a row here, not a subprocess case.
TAINT_READER_ROWS = (
    ("D=$(pwd); rm -rf $D/*", "D"),
    ('D=$(/bin/pwd); rm -rf "$D"/*', "D"),
    ('D=$(command pwd); rm -rf "$D"/*', "D"),
    ('D=`pwd -P`; rm -rf "$D"/*', "D"),
    ('OUT=$(pwd -L); rm -rf "$OUT"/*', "OUT"),
    ('D="$(pwd -P)"; rm -rf "$D"/*', "D"),
    ("D=$HOME; rm -rf ${D:?}/*", "D"),
    ('for D in $HOME; do rm -rf "${D:?}"/*; done', "D"),
    ("D=$(echo $HOME); rm -rf $D/*", "D"),
    ('D=$(cd ..; pwd); rm -rf "$D"/*', "D"),
    ('D=$(cd .. || exit; pwd -P); rm -rf "$D"/*', "D"),
    ('D=`cd .. && pwd`; rm -rf "$D"/*', "D"),
    ('D=$(echo x | (cd .. && pwd)); rm -rf "$D"/*', "D"),
    ("""D="$(: ')' ; pwd)"; rm -rf "${D:?}"/*""", "D"),
)


def rm_var_taint_reader_case():
    """Each TAINT_READER_ROWS text gets the literal-path reason, and the reason never names ${NAME:?}.
    The module loads from the folder of GUARD, so a GUARD_UNDER_TEST copy of guard_rm_var is the one
    read. A reader that loses a taint source fails here, and the sh() rows above fail too."""
    import importlib.util
    path = os.path.join(os.path.dirname(GUARD), "guard_rm_var.py")
    spec = importlib.util.spec_from_file_location("guard_rm_var_under_test", path)
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    bad = []
    for text, name in TAINT_READER_ROWS:
        reason = reader.rm_var_reason(reader.rm_var_hits(text, NOGIT))
        if "literal path" not in reason or ("${%s:?}" % name) in reason:
            bad.append(text)
    if bad:
        return False, "the reader does not name the literal path for: " + " | ".join(bad)
    return True, ("%d taint spellings name the literal path, none names ${NAME:?}"
                  % len(TAINT_READER_ROWS))


sh("rm-var: a guarded variable set from $(pwd) is refused and its remedy names no ${D:?} advice",
   'D=$(pwd); rm -rf "${D:?}"/*', "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${D:?}",))
# Taint (decision rm-on-a-variable-needs-a-guard): a pwd command in $(...) or backticks taints,
# with any flags or path.
sh("rm-var: a variable set from $(pwd -P) is refused for a literal path, not ${D:?}",
   'D=$(pwd -P); rm -rf "$D"/*', "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${D:?}",))
sh("rm-var: a loop over $(pwd -P) is refused for a literal path, not ${D:?}",
   'for D in $(pwd -P); do rm -rf "${D:?}"/*; done', "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${D:?}",))
sh("rm-var: a guarded variable from a non-pwd word that starts with pwd stays allowed",
   'D=build-pwd; rm -rf "${D:?}"/*', "allow", cwd=NOGIT)
sh("rm-var: a guarded variable set to a literal path passes",
   'D=/tmp/w; rm -rf "${D:?}"/*', "allow", cwd=NOGIT)
# Derived forms (decision rm-on-a-variable-needs-a-guard): a variable whose assigned or loop value
# holds ~, HOME, PWD or pwd is tainted, so its refusal names a literal path, never ${D:?} advice.
sh("rm-var: a variable set to ~ names a literal path, not ${D:?}",
   'D=~; rm -rf "${D:?}"/*', "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${D:?}", os.path.expanduser("~")))
sh("rm-var: a default that falls back to $HOME names a literal path, not ${D:?}",
   "D=${X:-$HOME}; rm -rf ${D:?}/*", "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${D:?}", os.path.expanduser("~")))
# $HOME/x is not the trigger shape, so it is not refused. The literal-path case for a $HOME
# target is "$HOME/$d" above.
sh("rm-var: $HOME joined to a literal path is not refused",
   "rm -rf $HOME/x", "allow", cwd=NOGIT)
# Whether the refusal also prints ${S:?} advice is not pinned.
sh("rm-var: a $HOME target and a safe variable name both get the literal-path remedy",
   "S=/tmp/w; rm -rf $HOME/* $S/*", "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",))
# Taint comes only from a real expansion (decision rm-on-a-variable-needs-a-guard). A literal
# value that spells pwd or HOME is not one.
sh("rm-var: a literal HOME inside a path is not tainted",
   'D=/tmp/HOME/x; rm -rf "${D:?}"/*', "allow", cwd=NOGIT)
sh("rm-var: a tilde in a flag value is not a home expansion, so $dir gets its own advice",
   'make --dir=~ && dir=/tmp/b; rm -rf "$dir"/*', "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=('rm -rf "${dir:?}"/*',), lacks=("literal path",))
sh("rm-var: $HOME under a glob names a literal path, not the computed home",
   "rm -rf $HOME/*", "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=(os.path.expanduser("~"),))
# Substitution spans (decision rm-on-a-variable-needs-a-guard). The assigned-value reader cuts the
# value at ; & | even inside $(...) or backticks, so a pwd after the cut is missed. Each case must
# deny with the literal-path reason.
sh("rm-var: a pwd after && inside $(…) taints the variable, not ${D:?}",
   'D=$(cd .. && pwd); rm -rf "$D"/*', "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${D:?}",))
sh("rm-var: a guarded variable set after && in a list stays allowed",
   'D=/tmp/w; true && rm -rf "${D:?}"/*', "allow", cwd=NOGIT)
# Taint (decision rm-on-a-variable-needs-a-guard): a command word pwd, or an expansion of HOME or
# PWD, anywhere in the command taints every variable it assigns. The guard reads no $(…) span, so
# quotes and ; inside the span cannot hide the source. Each case must deny with the literal-path
# reason and never name ${D:?}.
sh("rm-var: a pwd after a quoted ) in $(…) taints D, not ${D:?}",
   'D=$(: ")" ; pwd); rm -rf "${D:?}"/*', "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${D:?}",))
sh("rm-var: $HOME expanded inside $(…) taints D, not ${D:?}",
   'D=$(x=1; echo $HOME); rm -rf "${D:?}"/*', "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${D:?}",))
# pwd as an argument is text, not a command word, so the value stays a literal and passes.
sh("rm-var: a cat of pwd.txt inside $(…) is text, not a command word, and stays allowed",
   'D=$(cat pwd.txt); rm -rf "${D:?}"/*', "allow", cwd=NOGIT)
# MORE CONDITIONS (decision rm-on-a-variable-needs-a-guard). Each case below has an unsafe binding,
# a value the guard cannot read, or a value whose path is the home folder or the cwd, so the
# refusal names the literal path and never ${NAME:?}. Each case must be refused. A pass, or a
# crash that exits 0, is a FAIL.
HOME = os.path.expanduser("~")
sh("rm-var: a dollar then a quoted dollar before the slash names a literal path",
   'D=x; rm -rf $D/$"E"', "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${D:?}",))
sh("rm-var: a mktemp value with a parent walk after it names a literal path, not ${N:?}",
   "N=$(mktemp -d)/../../..; rm -rf $N/", "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${N:?}",))
sh("rm-var: a value with a space and the home path names a literal path, not ${D:?}",
   'D="x %s"; rm -rf $D/' % HOME, "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${D:?}", HOME))
sh("rm-var: a tilde joined to a variable before the slash names a literal path, not ${D:?}",
   "D=/; rm -rf ~$D/", "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${D:?}",))
sh("rm-var: a brace list before a variable names a literal path, not ${D:?}",
   "D=Users; rm -rf {/,x}$D/", "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${D:?}",))
sh("rm-var: a glob before a variable names a literal path, not ${D:?}",
   "D=shivinate; rm -rf /*/$D/", "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${D:?}",))
sh("rm-var: a prefix assignment before the rm names a literal path, not ${OLDPWD:?}",
   "OLDPWD=/tmp rm -rf $OLDPWD/", "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${OLDPWD:?}",))
sh("rm-var: a binding after the rm names a literal path, not ${OLDPWD:?}",
   "rm -rf $OLDPWD/; OLDPWD=/tmp", "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${OLDPWD:?}",))
# macOS only: the home folder's file system is case-folded, so an upper or lower spelling of it
# is the home folder and must name a literal path. The case is not registered elsewhere.
if sys.platform == "darwin":
    sh("rm-var: the home path upper-cased in a variable names a literal path on macOS",
       "D=%s; rm -rf $D/" % HOME.upper(), "deny", "rm-var-unguarded", cwd=NOGIT,
       carries=("literal path",), lacks=("${D:?}", HOME))
    sh("rm-var: the home path lower-cased in a variable names a literal path on macOS",
       "D=%s; rm -rf $D/" % HOME.lower(), "deny", "rm-var-unguarded", cwd=NOGIT,
       carries=("literal path",), lacks=("${D:?}", HOME))
# The cwd spelled through a symlink is the cwd, so it names a literal path. Registered only where
# the fixture can build the link (no symlink privilege means no case, and the report says so).
CWDLINK = os.path.join(ROOT, "nogit-link")
try:
    os.symlink(NOGIT, CWDLINK)
except OSError:
    CWDLINK = None
if CWDLINK:
    sh("rm-var: the cwd spelled through a symlink names a literal path, not ${D:?}",
       "D=%s; rm -rf $D/" % CWDLINK, "deny", "rm-var-unguarded", cwd=NOGIT,
       carries=("literal path",), lacks=("${D:?}", CWDLINK))
# Ruling item 1 (decision rm-on-a-variable-needs-a-guard): a binding written AFTER a wrapper
# still comes before no rm in the wrapper's own text, so the name must get the literal-path reason,
# never ${NAME:?}.
sh("rm-var: a binding after sh -c names a literal path, not ${OLDPWD:?}",
   "sh -c 'rm -rf $OLDPWD/*'; OLDPWD=/tmp/x", "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${OLDPWD:?}",))
sh("rm-var: a binding after bash -c names a literal path, not ${OLDPWD:?}",
   "bash -c 'rm -rf $OLDPWD/*'; OLDPWD=/tmp/x", "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${OLDPWD:?}",))
sh("rm-var: a binding after eval names a literal path, not ${OLDPWD:?}",
   "eval 'rm -rf $OLDPWD/*'; OLDPWD=/tmp/x", "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${OLDPWD:?}",))
# Ruling item 1, home's parents: the parent of home holds home, so a glob under it can empty home.
# The parent is read from HOME, never fixed, so the case holds on any account.
PARENT_OF_HOME = os.path.dirname(HOME)
sh("rm-var: a variable set to the parent of home names a literal path, not ${D:?}",
   "D=%s; rm -rf $D/*" % PARENT_OF_HOME, "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${D:?}",))

# REDIRECT SHAPES. Claude Code's built-in rm check lost its safeguard when the command also redirected
# to ~ or a wildcard (changelog 2.1.287, Oct 2026). Each redirect case has a plain-command control, in
# this block or in the rm-var and delete sections. A redirect must not change the verdict the plain
# command gets.
sh("rm-var redirect: plain $S/x is not refused",
   "rm -rf $S/x", "allow", cwd=NOGIT)
sh("rm-var redirect: $S/x with a redirect to ~ is not refused",
   "rm -rf $S/x > ~/rm.log", "allow", cwd=NOGIT)
sh("rm-var redirect: plain quoted $S is not refused",
   'rm -rf "$S"', "allow", cwd=NOGIT)
sh("rm-var redirect: quoted $S with a stderr redirect to ~ is not refused",
   'rm -rf "$S" 2> ~/err.txt', "allow", cwd=NOGIT)
sh("rm-var redirect: $S/* with an append to ~ is refused",
   "rm -rf $S/* >> ~/.cache/log", "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${S:?}",))
sh("rm-var redirect: $S/* with a stderr redirect to /dev/null is refused",
   "rm -rf $S/* 2>/dev/null", "deny", "rm-var-unguarded", cwd=NOGIT,
   carries=("literal path",), lacks=("${S:?}",))
sh("rm-var redirect: plain ~/.cache/* is not refused",
   "rm -rf ~/.cache/*", "allow", cwd=NOGIT)
sh("rm-var redirect: ~/.cache/* with a redirect to /dev/null is not refused",
   "rm -rf ~/.cache/* > /dev/null", "allow", cwd=NOGIT)
sh("rm-var redirect: $S/x piped through tee to ~ is not refused",
   "rm -rf $S/x 2>&1 | tee ~/log", "allow", cwd=NOGIT)
sh("rm-var redirect: $S/x with a quoted $HOME redirect is not refused",
   'rm -rf $S/x > "$HOME/log"', "allow", cwd=NOGIT)
sh("rm-var redirect: a redirect before the command does not change the verdict",
   "> ~/log rm -rf $S/x", "allow", cwd=NOGIT)
sh("rm-var redirect: a redirect with no space before ~ does not change the verdict",
   "rm -rf $S/x >~/log", "allow", cwd=NOGIT)
sh("rm-var redirect: plain $S/x with a stderr redirect to /dev/null is not refused",
   "rm -rf $S/x 2>/dev/null", "allow", cwd=NOGIT)
sh("rm-var redirect: plain ~/x is not refused",
   "rm -rf ~/x", "allow", cwd=NOGIT)
sh("rm-var redirect: ~/x with a redirect to ~ is not refused",
   "rm -rf ~/x > ~/log", "allow", cwd=NOGIT)
sh("rm-var redirect: plain root is refused",
   "rm -rf /", "deny", "destructive-delete", cwd=NOGIT)
sh("rm-var redirect: root with a redirect to ~ is refused",
   "rm -rf / > ~/log", "deny", "destructive-delete", cwd=NOGIT)
sh("rm-var redirect: plain home is refused",
   "rm -rf ~", "deny", "destructive-delete", cwd=NOGIT)
sh("rm-var redirect: home with a stderr redirect to /dev/null is refused",
   "rm -rf ~ 2>/dev/null", "deny", "destructive-delete", cwd=NOGIT)
sh("rm-var redirect: PowerShell plain $S\\x is not refused",
   "Remove-Item -Recurse $S\\x", "allow", tool="PowerShell", cwd=NOGIT)
sh("rm-var redirect: PowerShell $S\\x with a redirect to $HOME is not refused",
   "Remove-Item -Recurse $S\\x > $HOME\\log", "allow", tool="PowerShell", cwd=NOGIT)
sh("rm-var redirect: PowerShell plain $S\\* is not refused",
   "Remove-Item -Recurse -Force $S\\*", "allow", tool="PowerShell", cwd=NOGIT)
sh("rm-var redirect: PowerShell $S\\* with a redirect to $HOME is not refused",
   "Remove-Item -Recurse -Force $S\\* > $HOME\\log", "allow", tool="PowerShell", cwd=NOGIT)
sh("rm-var redirect: PowerShell drive root with a redirect to $HOME is refused",
   "Remove-Item -Recurse -Force C:\\ > $HOME\\log", "deny", "destructive-delete",
   tool="PowerShell", cwd=NOGIT)

# A DELETE AFTER A CD. Decision rm-after-cd-names-absolute-path (likely risk):
# `cd X; rm -r.. <relative target>` is refused, because Claude Code's own critical-path prompt cannot
# follow the cd, and a failed cd runs the rm in the working folder. The remedy names the target
# under the cd folder. An absolute or variable target, and an rm with no -r, pass.
sh("rm-var: the 2026-10-27 scratch delete, a cd then a relative glob, is refused",
   "S=/private/tmp/claude-501/w/scratchpad; cd $S; rm -rf dl/*", "deny", "rm-after-cd",
   cwd=NOGIT, carries=('rm -rf "${S:?}"/dl/*',))
sh("rm-var: cd and && then a relative target is refused",
   'cd "$S" && rm -rf dl', "deny", "rm-after-cd", cwd=NOGIT, carries=('rm -rf "${S:?}"/dl',))
sh("rm-var: a cd to a literal path then a relative target names the joined path",
   "cd /tmp/w && rm -r out/a", "deny", "rm-after-cd", cwd=NOGIT, carries=("rm -r /tmp/w/out/a",))
sh("rm-var: a cd, another command, then a relative target is refused",
   "cd /tmp/w; ls; rm -rf out", "deny", "rm-after-cd", cwd=NOGIT)
sh("rm-var: a cd and rm in a subshell is refused",
   "(cd /tmp/w && rm -rf out)", "deny", "rm-after-cd", cwd=NOGIT, carries=("rm -rf /tmp/w/out",))
sh("rm-var: a cd and rm after set -e is refused",
   "set -e; cd /tmp/w; rm -rf out", "deny", "rm-after-cd", cwd=NOGIT)
sh("rm-var: a cd and rm in a brace group is refused",
   "{ cd /tmp/w; rm -Rf out; }", "deny", "rm-after-cd", cwd=NOGIT)
sh("rm-var: a long recursive flag after a cd is refused",
   "cd /tmp/w && rm --recursive --force out", "deny", "rm-after-cd", cwd=NOGIT)
sh("rm-var: a cd to a command substitution prints the DIR placeholder, guarded",
   "cd $(mktemp -d) && rm -rf out", "deny", "rm-after-cd", cwd=NOGIT,
   carries=('rm -rf "${DIR:?}"/out',))
sh("rm-var: a redirect word after the rm is no target",
   "cd /tmp/w && rm -rf out 2>&1", "deny", "rm-after-cd", cwd=NOGIT, lacks=("2>&1",))
sh("rm-var: a cd then an absolute target passes",
   "cd /tmp/w && rm -rf /tmp/w/out", "allow", cwd=NOGIT)
sh("rm-var: a cd then a quoted variable target passes",
   'cd "$S"; rm -rf "$S"/dl', "allow", cwd=NOGIT)
sh("rm-var: the remedy form passes",
   'S=/tmp/w; rm -rf "$S"/dl/a', "allow", cwd=NOGIT)
sh("rm-var: a cd then an rm with no -r passes",
   "cd /tmp/w && rm out/a.txt", "allow", cwd=NOGIT)
sh("rm-var: a cd then rm -f with no -r passes",
   "cd /tmp/w; rm -f out/a.txt", "allow", cwd=NOGIT)
sh("rm-var: a relative recursive delete with no cd passes",
   "rm -rf out", "allow", cwd=NOGIT)
sh("rm-var: an rm inside a quoted string after a cd passes",
   'cd /tmp/w && echo "rm -rf out"', "allow", cwd=NOGIT)
sh("rm-var: a semicolon and rm inside a quote after a cd pass",
   "cd /tmp/w && echo \"don't; rm -rf out\"", "allow", cwd=NOGIT)
sh("rm-var: an rm after a comment opener on the cd line passes",
   "cd /tmp/w # it's; rm -rf out", "allow", cwd=NOGIT)
sh("rm-var: a hash inside a word is no comment, the delete after a cd is refused",
   "cd /tmp/w; rm -rf fix#3", "deny", "rm-after-cd", cwd=NOGIT)
sh("rm-var: an apostrophe in a comment after the rm does not hide it",
   "cd /tmp/w; rm -rf out # the driver's shape", "deny", "rm-after-cd", cwd=NOGIT)

sh("playwright: the bare PowerShell read is allowed", "$env:PLAYWRIGHT_BROWSERS_PATH", "allow",
   tool="PowerShell", cwd=NOGIT)
# False alarms: each one only reads or writes a note, so each is allowed.
sh("playwright: grep for the assignment only reads",
   'grep -rn "PLAYWRIGHT_BROWSERS_PATH=" hooks/ 2>/dev/null', "allow", cwd=NOGIT)
sh("playwright: a note that mentions the assignment is allowed",
   'echo "set PLAYWRIGHT_BROWSERS_PATH=/x to override" >> notes.md', "allow", cwd=NOGIT)
sh("playwright: a quoted arrow in a command that names the variable is allowed",
   'echo "PLAYWRIGHT_BROWSERS_PATH -> cache dir"', "allow", cwd=NOGIT)
sh("playwright: grep for the PowerShell setter only reads",
   'grep "Set-Item env:PLAYWRIGHT_BROWSERS_PATH" -r .', "allow", cwd=NOGIT)
sh("playwright: a doc heredoc whose body mentions an assignment is allowed",
   "cat > README.md <<'EOF'\nset PLAYWRIGHT_BROWSERS_PATH=/x to override\nEOF", "allow", cwd=NOGIT)
# False alarms: each one only writes a log or reads a docs folder.
sh("playwright: printf into a log names the variable and is allowed",
   "printf 'PLAYWRIGHT_BROWSERS_PATH=%s\\n' \"$P\" >> run.log", "allow", cwd=NOGIT)
sh("playwright: echo into a log names the variable and is allowed",
   'echo "PLAYWRIGHT_BROWSERS_PATH=$X" >> build.log', "allow", cwd=NOGIT)
sh("playwright: grep for the PowerShell setter in docs is allowed",
   "grep '\\$env:PLAYWRIGHT_BROWSERS_PATH *=' docs/", "allow", cwd=NOGIT)
# The control keeps a quoted continuation inert for an unrelated rule: the kill word inside echo's
# quotes is text, not a call.
sh("control: a quoted backslash-newline echo of a kill word is allowed",
   'echo "pkill \\\nnode"', "allow", cwd=NOGIT)
# (c) False alarms: each form names the PowerShell setter text but only reads it, quotes it into
# a body, or writes it to a note.
sh("playwright: sed prints the lines that name the setter, a read only",
   "sed -n '/$env:PLAYWRIGHT_BROWSERS_PATH = /p' f", "allow", cwd=NOGIT)
sh("playwright: a gh comment body quotes the setter text, allowed",
   """gh pr comment 1 --body '$env:PLAYWRIGHT_BROWSERS_PATH = "x"'""", "allow", cwd=NOGIT)
sh("playwright: an echo writes the setter text into a note, allowed",
   """echo '$env:PLAYWRIGHT_BROWSERS_PATH = "x"' >> notes.md""", "allow", cwd=NOGIT)
sh("playwright: Select-String reads the name, allowed",
   "Select-String '$env:PLAYWRIGHT_BROWSERS_PATH' f.ps1", "allow", tool="PowerShell", cwd=NOGIT)
sh("playwright: Select-String searches for the setter text with an equals sign, allowed",
   "Select-String -Pattern '$env:PLAYWRIGHT_BROWSERS_PATH = ' f.ps1", "allow",
   tool="PowerShell", cwd=NOGIT)
# An escaped backslash before a newline is not a continuation, so the kill
# rule still sees the pkill on the next line. A variable given to node as an argument is no setting.
sh("kill: an escaped backslash before a newline is not a continuation, pkill still denies",
   "echo \\\\\npkill -f node", "deny", "machine-wide-kill", cwd=NOGIT)
sh("playwright: cross-env passes the variable to node as an argument, allowed",
   "cross-env FOO=1 node x.js PLAYWRIGHT_BROWSERS_PATH=/x", "allow", cwd=NOGIT)
# A backslash before a newline is a PowerShell path end, not a continuation,
# so each line is its own command.
sh("control: a PowerShell path ending in a backslash, then a force push on the next line, denies",
   "Set-Location C:\\tmp\\\ngit push -f origin feat", "deny", "force-push", tool="PowerShell",
   cwd=PUSHFEAT)
# The setter text sits only inside a quoted argument of gh, a command that
# sets nothing. pwsh -c is a PowerShell shell, so the whole segment reaches PLAYWRIGHT_PS_SET.
sh("playwright: the setter text is only a gh comment body inside pwsh -c, allowed",
   r'''pwsh -c "gh pr comment 314 --body 'Do not set \$env:PLAYWRIGHT_BROWSERS_PATH = x'"''',
   "allow", cwd=NOGIT)

# THE PLAYWRIGHT BROWSER INSTALL. An agent never runs a Playwright browser install.
# A main-session install runs only as the Node 22 cli.js form. INCIDENT 2026-10-11 (feed-build):
# three test-author agents ran `npx playwright install chromium` at once under the Mac default
# Node 26.11. The install hangs while it unpacks (measured, see decision playwright-browsers-path).
# One hung 20 minutes, and they fought over the shared ~/Library/Caches/ms-playwright/__dirlock.
# The main-session forms below are denied. Each one runs an install under the default Node.
# One table of the main-session deny forms. One row per branch _playwright_install_hit reads: each
# runner in _PW_RUNNERS, each CLI path in _PW_CLIS, the npx-only value-flag list, the name followed by
# another name, the wrapper shells, the scoped and pinned names, the bin path, the chain, and the
# quoted text the scanner must see past. Row: (name, command, tool).
PLAYWRIGHT_INSTALL_DENY = (
    ("playwright-install: npx names the browser install", "npx playwright install chromium", "Bash"),
    ("playwright-install: npx -y installs without a prompt", "npx -y playwright install", "Bash"),
    ("playwright-install: npx -p names the package, the install still denies",
     "npx -p playwright playwright install", "Bash"),
    # npx takes only its own value flags (--prefix, -w, --workspace), so -F's value is the name here.
    ("playwright-install: npx -F names the package and the install runs",
     "npx -F playwright install", "Bash"),
    ("playwright-install: npx pins a version for the install", "npx playwright@1.58 install", "Bash"),
    ("playwright-install: the local bin runs the install", "node_modules/.bin/playwright install",
     "Bash"),
    ("playwright-install: the default node runs the cli.js install",
     "node node_modules/playwright/cli.js install", "Bash"),
    ("playwright-install: node runs the playwright-core cli.js install",
     "node node_modules/playwright-core/cli.js install", "Bash"),
    ("playwright-install: bash -c wraps the install", "bash -c 'npx playwright install chromium'",
     "Bash"),
    ("playwright-install: cd then && runs the install", "cd x && npx playwright install chromium",
     "Bash"),
    ("playwright-install: the Node 22 bin form is not the cli.js form",
     "npx -y node@22 node_modules/.bin/playwright install", "Bash"),
    # Scanner cases: a lone quote, a comment opener inside quotes, and a multi-line quoted string
    # must not hide an install that follows them.
    ("playwright-install: a double-quoted apostrophe in an echo does not hide the install",
     'echo "don\'t"; npx playwright install', "Bash"),
    ("playwright-install: a hash inside quotes is no comment, the install still denies",
     'echo "#" && npx playwright install chromium', "Bash"),
    ("playwright-install: a multi-line quoted string does not hide the install",
     'echo "one\ntwo" && npx playwright install chromium', "Bash"),
    ("playwright-install: npx -c runs the install in a shell string", "npx -c 'npx playwright install'",
     "Bash"),
    ("playwright-install: cmd /c runs the install", "cmd /c npx playwright install", "Bash"),
    ("playwright-install: powershell -Command runs the install",
     'powershell -Command "npx playwright install"', "Bash"),
    ("playwright-install: pwsh -c runs the install", "pwsh -c 'npx playwright install'", "Bash"),
    ("playwright-install: pwsh -Command runs the install", "pwsh -Command npx playwright install",
     "Bash"),
    # The scoped package's bin is playwright, so its install is the same act.
    ("playwright-install: the scoped test package installs the browsers",
     "npx @playwright/test install", "Bash"),
    ("playwright-install: npm exec --yes runs the install", "npm exec --yes playwright install",
     "Bash"),
    ("playwright-install: npm -w exec runs the install", "npm -w app exec playwright install",
     "Bash"),
    ("playwright-install: npm --workspace exec -- runs the install",
     "npm --workspace app exec -- playwright install", "Bash"),
    ("playwright-install: pnpm exec runs the install", "pnpm exec playwright install", "Bash"),
    ("playwright-install: yarn runs the install", "yarn playwright install", "Bash"),
    ("playwright-install: bunx runs the install", "bunx playwright install", "Bash"),
)
for _name, _command, _tool in PLAYWRIGHT_INSTALL_DENY:
    sh(_name, _command, "deny", "playwright-install", tool=_tool, cwd=NOGIT)
sh("playwright-install: an apostrophe in a commit message names the install and is allowed",
   'git commit -m "don\'t run npx playwright install"', "allow", cwd=NOGIT)
# The allowed main-session form: Node 22 through the cli.js file, with or without the GC skip.
sh("playwright-install: the Node 22 cli.js install is allowed in the main session",
   "npx -y node@22 node_modules/playwright/cli.js install chromium", "allow", cwd=NOGIT)
sh("playwright-install: the GC skip may lead the Node 22 cli.js install",
   "PLAYWRIGHT_SKIP_BROWSER_GC=1 npx -y node@22 node_modules/playwright/cli.js install chromium",
   "allow", cwd=NOGIT)
# Not installs: a test run, a report, OS packages, and text that only names the install.
sh("playwright-install: a test run is allowed", "npx playwright test", "allow", cwd=NOGIT)
sh("playwright-install: show-report is allowed", "npx playwright show-report", "allow", cwd=NOGIT)
sh("playwright-install: install-deps installs OS packages, allowed",
   "npx playwright install-deps", "allow", cwd=NOGIT)
sh("playwright-install: grep for the install text in a README is allowed",
   'grep "playwright install" README.md', "allow", cwd=NOGIT)
sh("playwright-install: echo of the install text is allowed", "echo npx playwright install",
   "allow", cwd=NOGIT)
# Rule 1: an agent call that runs an install is denied whatever the form, including the Node 22
# cli.js form, and whatever the role the agent carries. The switch reads agent_id or agent_type
# (guard.py passes bool of either), so one row per outcome pins it: a plain install and the Node 22
# cli.js form denied, and a test run allowed.
sh("playwright-install: an agent install is denied",
   "npx playwright install chromium", "deny", "playwright-install", cwd=NOGIT,
   agent_id="pw-sub1", agent_type="builder")
sh("playwright-install: an agent Node 22 cli.js install is denied, rule 1 wins",
   "npx -y node@22 node_modules/playwright/cli.js install chromium", "deny",
   "playwright-install", cwd=NOGIT, agent_id="pw-sub1", agent_type="test-author")
sh("playwright-install: an agent test run is allowed", "npx playwright test", "allow",
   cwd=NOGIT, agent_id="pw-sub1")
# False alarm: the Node 22 cli.js form with a ./ path is the allowed form.
sh("playwright-install: the Node 22 cli.js form with a ./ path is allowed in the main session",
   "npx -y node@22 ./node_modules/playwright/cli.js install chromium", "allow", cwd=NOGIT)
# Allowed main-session forms: the cli.js file named by an absolute or a parent-relative path.
sh("playwright-install: the Node 22 cli.js form with an absolute path is allowed",
   "npx -y node@22 /abs/path/node_modules/playwright/cli.js install chromium", "allow",
   cwd=NOGIT)
sh("playwright-install: the Node 22 cli.js form with a parent-relative path is allowed",
   "npx -y node@22 ../node_modules/playwright/cli.js install chromium", "allow", cwd=NOGIT)
# Control: a workspace exec that runs a test is not an install.
sh("playwright-install: a workspace exec test run is allowed",
   "npm -w app exec playwright test", "allow", cwd=NOGIT)
# The -w and --workspace list entries: alone, each one makes the name a workspace, not a command.
sh("playwright-install: npm -w takes a workspace name, its install is allowed",
   "npm -w playwright install", "allow", cwd=NOGIT)
sh("playwright-install: npm --workspace takes a workspace name, its install is allowed",
   "npm --workspace playwright install", "allow", cwd=NOGIT)
# Allows: a package manager's own install, a flag's value, and a test
# filter that names the word are not browser installs. The Node 22 cli.js forms are allowed.
sh("playwright-install: pnpm -C takes a directory, its install is allowed",
   "pnpm -C playwright install", "allow", cwd=NOGIT)
sh("playwright-install: npm --prefix takes a directory, its install is allowed",
   "npm --prefix ./playwright install", "allow", cwd=NOGIT)
sh("playwright-install: yarn --cwd takes a directory, its install is allowed",
   "yarn --cwd playwright install", "allow", cwd=NOGIT)
sh("playwright-install: pnpm -F filters a package, its install is allowed",
   "pnpm -F playwright install", "allow", cwd=NOGIT)
sh("playwright-install: a test run with -g install is allowed",
   "npx playwright test -g install", "allow", cwd=NOGIT)
sh("playwright-install: a test run with --grep install is allowed",
   "npx playwright test --grep install", "allow", cwd=NOGIT)
sh("playwright-install: the Node 22 cli.js form without -y is allowed",
   "npx node@22 node_modules/playwright/cli.js install chromium", "allow", cwd=NOGIT)
sh("playwright-install: the Node 22 cli.js form with --yes is allowed",
   "npx --yes node@22 node_modules/playwright/cli.js install chromium", "allow", cwd=NOGIT)
sh("playwright-install: the Node 22 playwright-core cli.js form is allowed in the main session",
   "npx -y node@22 node_modules/playwright-core/cli.js install chromium", "allow", cwd=NOGIT)
# THE PREDICATE IS THE ACT, NOT THE TOOL OR THE SPELLING. MEASURED: the owner ran
# `grep -n -i "...|make reap|pkill..." CLAUDE.md` to search CLAUDE.md for the word, and it was
# denied as a machine-wide kill, although the command calls grep. Each case below names the word
# without ever calling the program that shares it.
sh("kill: a grep for the word is not a call to it, the owner's report",
   'grep -n -i "graceful shutdown|make reap|pkill" CLAUDE.md', "allow", cwd=NOGIT)
sh("kill: the word inside a single-quoted argument",
   "grep -n -i 'graceful shutdown|make reap|pkill' CLAUDE.md", "allow", cwd=NOGIT)
sh("kill: an echoed word and flag, quoted, prints text and calls nothing",
   'echo "pkill -f node"', "allow", cwd=NOGIT)
sh("kill: the word on the far side of a pipe filter", "cat notes.md | grep pkill", "allow",
   cwd=NOGIT)
sh("kill: a quoted phrase ahead of a real chained kill still denies",
   'echo "safe text" && pkill node', "deny", "machine-wide-kill", cwd=NOGIT)

# BLAST RADIUS of the loop-keyword fix in `resolve_command` (Rule 9's own defect): a kill inside
# a loop's `do` block, or inside an `if`'s `then` block, used to resolve to the keyword as its
# command word and pass. MEASURED wrongly allowed before this fix.
sh("kill: a pkill inside a loop's do-block, MEASURED wrongly allowed",
   "while true; do pkill -f server; done", "deny", "machine-wide-kill", cwd=NOGIT)
sh("kill: a pkill inside an if's then-block, MEASURED wrongly allowed",
   "if true; then pkill -f server; fi", "deny", "machine-wide-kill", cwd=NOGIT)


# =========================================================================== 2b. detached launches
#
# On macOS an agent ran `(python3 -m http.server 8000
# >/tmp/http_server_wtweb.log 2>&1 &)`. The subshell exited at once, pid 1 adopted the server,
# the harness never tracked it, and no pid was kept, so rule 2's own remedy had no pid to name.

sh("detached: the incident's exact command orphans to pid 1",
   "(python3 -m http.server 8000 >/tmp/http_server_wtweb.log 2>&1 &)", "deny",
   "detached-launch", cwd=NOGIT)
sh("detached: the same shape, spaced",
   "( python3 -m http.server 8000 & )", "deny", "detached-launch", cwd=NOGIT)
sh("detached: nohup survives a session close, with a background job",
   "nohup python3 -m http.server 8000 &", "deny", "detached-launch", cwd=NOGIT)
# Re-pointed (rule detached-launch, refusal-vs-rule row detached-launch): nohup with no trailing `&`
# runs in the foreground, so it detaches nothing. The rule refuses only the detached forms.
sh("detached: nohup alone, no background job, runs in the foreground",
   "nohup npm run build", "allow", cwd=NOGIT)
sh("detached: nohup of make test, run in the foreground, is allowed", "nohup make test", "allow",
   cwd=NOGIT)
sh("detached: setsid -w waits for its child, so it runs in the foreground",
   "setsid -w make test", "allow", cwd=NOGIT)
sh("detached: nohup with a trailing background job is still refused", "nohup make test &", "deny",
   "detached-launch", cwd=NOGIT)
sh("detached: nohup with a redirect and a trailing background job is still refused",
   "nohup make test >log 2>&1 &", "deny", "detached-launch", cwd=NOGIT)
sh("detached: setsid with no -w starts its own session", "setsid make test", "deny",
   "detached-launch", cwd=NOGIT)
sh("detached: setsid -f forks, so the child outlives the call", "setsid -f make test", "deny",
   "detached-launch", cwd=NOGIT)
# A wrapper inside another wrapper detaches the same way: nohup passes its own command on, so the
# setsid it wraps is read too.
sh("detached: setsid with no -w, wrapped in nohup, is refused", "nohup setsid make test", "deny",
   "detached-launch", cwd=NOGIT)
sh("detached: setsid -f, wrapped in nohup, is refused", "nohup setsid -f make test", "deny",
   "detached-launch", cwd=NOGIT)
sh("detached: setsid -w with a trailing background job is still refused", "setsid -w make test &",
   "deny", "detached-launch", cwd=NOGIT)
sh("detached: setsid starts its own session",
   "setsid python3 server.py &", "deny", "detached-launch", cwd=NOGIT)
sh("detached: disown right after a background job",
   "python3 server.py & disown", "deny", "detached-launch", cwd=NOGIT)
sh("detached: disown right after a job whose pid is captured",
   "python3 server.py & disown $!", "deny", "detached-launch", cwd=NOGIT)
sh("detached: a bare trailing background job with no pid captured, MEASURED zero harmless "
   "matches in 16571 local Bash commands",
   "python3 server.py &", "deny", "detached-launch", cwd=NOGIT)

# MEASURED 2026-09-26 on Windows (the start-shapes entry, PR #144): each shape below was allowed,
# and each server outlived its call. `cmd &` then another line also outlived its agent.
sh("detached: a background job followed by another line, MEASURED to outlive the agent",
   "python -m http.server 8781 &\necho started", "deny", "detached-launch", cwd=NOGIT)
sh("detached: a background job mid-line, followed by another command",
   "python3 server.py & echo started", "deny", "detached-launch", cwd=NOGIT)
sh("detached: disown on its own line after a background job",
   "python3 server.py &\ndisown", "deny", "detached-launch", cwd=NOGIT)
sh("detached: disown on its own line, even with a pid printed first",
   "python3 server.py & echo $!\ndisown", "deny", "detached-launch", cwd=NOGIT)
sh("detached: a background job inside sh -c",
   "sh -c 'python3 -m http.server 8782 &'", "deny", "detached-launch", cwd=NOGIT)
sh("detached: a background job inside bash -lc, then another line",
   "bash -lc 'python3 server.py &\necho started'", "deny", "detached-launch", cwd=NOGIT)
# Re-pointed (rule detached-launch, refusal-vs-rule row detached-launch): nohup inside sh -c, with no
# background job, runs in the foreground and exits with the process.
sh("detached: nohup inside sh -c runs in the foreground", "sh -c 'nohup python3 server.py'",
   "allow", cwd=NOGIT)
sh("detached: sh -c with no background job runs and exits",
   "sh -c 'echo hi; ls'", "allow", cwd=NOGIT)
sh("detached: sh -c that prints the pid of its job",
   "sh -c 'python3 server.py & echo $!'", "allow", cwd=NOGIT)
sh("detached: a quoted ampersand is text, not a job",
   "echo 'a & b'", "allow", cwd=NOGIT)
sh("detached: PowerShell's call operator is a leading ampersand, not a job",
   '& "C:\\Program Files\\Git\\bin\\git.exe" status', "allow", tool="PowerShell", cwd=NOGIT)
sh("detached: PowerShell's call operator after an assignment",
   "$out = & git status", "allow", tool="PowerShell", cwd=NOGIT)
sh("detached: stderr to stdout is a redirect, not a job",
   "python3 build.py 2>&1\necho done", "allow", cwd=NOGIT)
sh("detached: an ampersand in a python heredoc body is Python, MEASURED 6 such local commands",
   "python3 - <<'PY'\nprint(6 & 3)\nPY\necho done", "allow", cwd=NOGIT)

sh("detached: run_in_background style is a plain foreground command, nothing to catch",
   "python3 server.py", "allow", cwd=NOGIT)
sh("detached: the printed pid is kept, the session can stop it later",
   "python3 server.py & echo $!", "allow", cwd=NOGIT)
sh("detached: a quoted echo of the shape prints text and starts nothing",
   'echo "nohup foo &"', "allow", cwd=NOGIT)
sh("detached: a grep for the word disown is not a call to it",
   'grep -n "disown" file.txt', "allow", cwd=NOGIT)
sh("detached: a quoted subshell-and-background shape inside echo's argument",
   'echo "(x &)"', "allow", cwd=NOGIT)
sh("detached: nohup wrapping a real kill still hits rule 2, not this rule",
   "nohup pkill foo", "deny", "machine-wide-kill", cwd=NOGIT)
sh("detached: the shape inside a heredoc body is data, not a command",
   "cat <<'EOF' > notes.txt\nnohup python3 server.py &\nEOF", "allow", cwd=NOGIT)

# THE WINDOWS FORMS, the owner's scope change: the same protection PowerShell needs, since
# guard.py judges Bash and PowerShell alike (SHELL_TOOLS). MEASURED 2026-09-24 against local
# transcripts: 4 real `Start-Process` calls, all through the PowerShell tool, all already
# carrying `-PassThru`. 0 `Start-Job` calls. 0 `cmd /c start` calls, from either shell.
sh("detached: Start-Job hands the work to a job object with no pid here at all",
   "Start-Job -ScriptBlock { python server.py }", "deny", "detached-launch",
   tool="PowerShell", cwd=NOGIT)
sh("detached: Start-Process with neither -Wait nor -PassThru",
   'Start-Process npx -ArgumentList "server.js"', "deny", "detached-launch",
   tool="PowerShell", cwd=NOGIT)
sh("detached: Start-Process -WindowStyle Hidden still denies without -Wait or -PassThru",
   "Start-Process notepad.exe -WindowStyle Hidden", "deny", "detached-launch",
   tool="PowerShell", cwd=NOGIT)
# The array form of a launch with a debug port is a detached launch, so detached-launch owns the deny.
sh("detached: a Start-Process array argument list with a remote-debugging port is denied",
   "Start-Process app.exe -ArgumentList '--disable-gpu','--remote-debugging-port=9222'", "deny",
   "detached-launch", tool="PowerShell", cwd=NOGIT)
sh("detached: a PowerShell assignment ahead of Start-Process is still read, MEASURED wrongly "
   "missed before _skip_assignments_and_keywords learned $name =",
   '$bad = Start-Process npx -ArgumentList "server.js"', "deny", "detached-launch",
   tool="PowerShell", cwd=NOGIT)
sh("detached: cmd /c start opens an untracked window, from PowerShell",
   "cmd /c start python server.py", "deny", "detached-launch", tool="PowerShell", cwd=NOGIT)
sh("detached: cmd.exe /c start opens an untracked window, from Bash",
   "cmd.exe /c start notepad.exe", "deny", "detached-launch", cwd=NOGIT)

sh("detached: Start-Process -Wait blocks until the child exits",
   "Start-Process notepad.exe -Wait", "allow", tool="PowerShell", cwd=NOGIT)
sh("detached: Start-Process -PassThru hands back the pid to stop later",
   "Start-Process notepad.exe -PassThru", "allow", tool="PowerShell", cwd=NOGIT)
sh("detached: the real measured launch, -PassThru kept in $p for cleanup",
   '$p = Start-Process npx -ArgumentList @("-y","supergateway@3.4.3") -PassThru '
   "-WindowStyle Hidden", "allow", tool="PowerShell", cwd=NOGIT)
sh("detached: cmd with no start subcommand runs and exits, nothing to catch",
   "cmd /c echo hello", "allow", tool="PowerShell", cwd=NOGIT)
sh("detached: a quoted mention of the shape prints text and starts nothing",
   'echo "cmd /c start something"', "allow", tool="PowerShell", cwd=NOGIT)
sh("detached: a grep for Start-Job is not a call to it",
   'grep -n "Start-Job" file.txt', "allow", tool="PowerShell", cwd=NOGIT)

# Bash reads `\&` as a literal `&` (the second `&` backgrounds) and `\;` as text; PowerShell has no such escape.
sh("kill: a bash cd with a backslash before && hides taskkill /IM, denies",
   r"cd C:\x\&& taskkill /F /IM node.exe", "deny", rule="machine-wide-kill", cwd=NOGIT)
sh("kill: a bash cmd /c with a backslash before && hides taskkill /IM, denies",
   r"cmd /c cd C:\x\&& taskkill /F /IM node.exe", "deny", rule="machine-wide-kill", cwd=NOGIT)
sh("kill: a PowerShell cmd /c with a backslash before && still denies taskkill /IM",
   r"cmd /c cd C:\x\&& taskkill /F /IM node.exe", "deny", rule="machine-wide-kill",
   tool="PowerShell", cwd=NOGIT)
sh("kill: a bash backslash before ; makes taskkill an argument of cd, allowed",
   r"cd C:\x\; taskkill /F /IM node.exe", "allow", cwd=NOGIT)


# A MACHINE-WIDE KILL IN A ONE-COMMAND PYTHON BODY STILL DENIES (owner ruling 2026-10-14 22:25): the
# body is one command, and the kill is a deny, which wins over any ask command in the same command.
sh("heredoc: a machine-wide kill in a python body still denies, in one command",
   "python3 - <<'PY'\npkill -f node\nPY", "deny", "machine-wide-kill", cwd=PROJ)


# H1: a python body under a backslash, single-quoted or double-quoted delimiter, closed at EOF,
# then a kill. The python body stays in view.
for _label, _open in (("backslash", "E\\OF"), ("single-quoted", "E'OF'"), ("double-quoted", '"E"OF')):
    sh("heredoc: r1-hd a python heredoc, %s delimiter closed at EOF, then a kill, denies" % _label,
       "python3 - <<" + _open + "\nx\nEOF\npkill -f node", "deny", "machine-wide-kill", cwd=PROJ)
# H2: a cat heredoc piped to a shell, closer EOF-X. The kill is in the body, which the shell runs.
for _shell in ("sh", "bash"):
    sh("heredoc: r1-hd a cat heredoc piped to %s, closer EOF-X, a kill in the body, denies" % _shell,
       "cat <<EOF-X | " + _shell + "\nx\nEOF\npkill -f node\nEOF-X", "deny", "machine-wide-kill", cwd=PROJ)
# A plain cat heredoc piped to sh, with a kill in its body.
sh("heredoc: r1-hd a plain cat heredoc piped to sh, a kill in the body, denies (red on main too)",
   "cat <<EOF | sh\npkill -f node\nEOF", "deny", "machine-wide-kill", cwd=PROJ)

# A heredoc opened inside `$( )`, `<( )` or backticks, or on a line feeding eval, source, `.` or xargs, is a shell body.
R2_FORMS = (
    ("source with <( ), an escaped delimiter", "source <(cat <<\\EOF\nBODY\nEOF\n)"),
    ("a heredoc piped to xargs", "cat <<'EOF-1' | xargs -I{} sh -c '{}'\nBODY\nEOF-1"),
    ("eval with backticks", "eval `cat <<'EOF-1'\nBODY\nEOF-1\n`"),
)
# Measured on main: the `eval "$( )"` form is denied for its env and cap payloads, but main ALLOWS its kill, so
# this form runs for env and cap only. The `. <(cat <<E-F)` form is left out: main allows all three of its
# payloads. Both gaps are ones main already has (reported, not regressions).
R2_EVAL_FORM = ("eval with $( )", "eval \"$(cat <<'EOF-1'\nBODY\nEOF-1\n)\"")
for _label, _form in R2_FORMS:
    sh("heredoc: r2-hd a kill in the body of a heredoc in %s, denies" % _label,
       _form.replace("BODY", "pkill -f node"), "deny", "machine-wide-kill", cwd=PROJ)
# SCANNERS (building-scanner-respects-strings). A hash inside double quotes is text, so the header
# after it is still a header. A lone apostrophe in a body line is text, so the kill after it is in a body.
sh("heredoc: r2-hd a hash inside double quotes, then a source heredoc with a kill in the body, denies",
   'echo "a # b" && source <(cat <<\\EOF\npkill -f node\nEOF\n)', "deny", "machine-wide-kill", cwd=PROJ)
sh("heredoc: r2-hd a lone apostrophe in the body of a source heredoc, then a kill, denies",
   "source <(cat <<\\EOF\necho don't\npkill -f node\nEOF\n)", "deny", "machine-wide-kill", cwd=PROJ)

# A shell runs each body, and its header is one a reader can misread: a delimiter it cannot read (`'EOF-1'`,
# `\EOF`), or a shorter word that a stray line closes on (`EOF-1` as `EOF`, `"E"OF` as `E`).
R3_KILL = "pkill -f node"
for _label, _form in (
        ("a write then sh, delimiter 'EOF-1'",
         "cat <<'EOF-1' > x.sh && sh x.sh\necho hi\nEOF\n" + R3_KILL + "\nEOF-1"),
        ("a write, then sh on the next line, delimiter 'EOF-1'",
         "cat <<'EOF-1' > x.sh\necho hi\nEOF\n" + R3_KILL + "\nEOF-1\nsh x.sh"),
        ("a tee, then bash, delimiter 'EOF-1'",
         "cat <<'EOF-1' | tee x.sh; bash x.sh\necho hi\nEOF\n" + R3_KILL + "\nEOF-1"),
        ("python3 on a backslash delimiter",
         "cat <<\\EOF | python3 -\n" + R3_KILL + "\nEOF"),
        ("a write then sh, unquoted EOF-1",
         "cat <<EOF-1 > x.sh\necho hi\nEOF\n" + R3_KILL + "\nEOF-1\nsh x.sh"),
        ("a write then sh, delimiter \"E\"OF",
         'cat <<"E"OF > x.sh\necho hi\nE\n' + R3_KILL + "\nEOF\nsh x.sh"),
        ("a lone apostrophe in the body, then a write and sh",
         "cat <<'EOF-1' > x.sh\necho don't\nEOF\n" + R3_KILL + "\nEOF-1\nsh x.sh"),
):
    sh("heredoc r3-bd: a kill in the body of %s, denies" % _label, _form, "deny", "machine-wide-kill", cwd=PROJ)

# eval, source and `.` run a heredoc that a `<( )`, `$( )` or backtick reads, and bash executes its body.
# Not pinned: `source $( )`, because its output is a file name, so no body runs.
for _label, _form in (
        ("source <( )", "source <(cat <<EOF\n" + R3_KILL + "\nEOF\n)"),
        ("dot <( )", ". <(cat <<EOF\n" + R3_KILL + "\nEOF\n)"),
        ("eval backticks", "eval `cat <<EOF\n" + R3_KILL + "\nEOF\n`"),
        ("unquoted eval $( )", "eval $(cat <<EOF\n" + R3_KILL + "\nEOF\n)"),
):
    sh("heredoc r3-fed: a kill in the body of a heredoc that %s runs, denies" % _label, _form,
       "deny", "machine-wide-kill", cwd=PROJ)

# Two heredocs in one command: the first delimiter must be read whole, or the payload lands in a body that `sh x.sh` runs.
HOLE_WSL = "wsl" + " --shutdown"
for _label, _open, _close, _mw in (
        ("E-F", "E-F", "E-F", "E"),
        ("E'OF'", "E'OF'", "EOF", "E"),
        ("EOF{", "EOF{", "EOF{", "EOF"),
):
    sh("heredoc safety hole: delimiter %s, a kill in the second body that sh runs, denies" % _label,
       "cat <<" + _open + "\na\n" + _close + "\ncat <<EOF2 > x.sh\necho hi\n" + _mw + "\n" + R3_KILL + "\nEOF2\nsh x.sh",
       "deny", "machine-wide-kill", cwd=PROJ)
