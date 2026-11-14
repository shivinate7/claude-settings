#!/usr/bin/env python3
"""Stall watch for background Bash commands. Standard library only.

Modes:
- --hook: Before a background Bash command, wraps it so a watcher reports a stall after
  300 seconds with no new output. The job keeps running. For a background call with an agent_id
  in the payload (17 lowercase hex), it puts the agent marker ahead of the wrapper.
- --stop: At Stop, lists each open background job whose output file did not change for
  the quiet age, and blocks a Stop while a CI wait has no check-in.

Hook: stall_watch.py --hook
  PreToolUse hook. For a Bash call with run_in_background true, it returns updatedInput only
  (no permissionDecision), with this command, run by the harness shell:

    : > LOG; : > BEAT; {
    (
    trap 'rm -f LOG BEAT' EXIT; export STALL_WATCH_BEAT=BEAT
    { <original>

    }
    ) >| LOG 2>&1 9<&- 8<&- & pid=$!; python3 stall_watch.py --watch-pid $pid --log LOG --quiet N --beat BEAT
      --log-fd 9 --beat-fd 8;
    rc=$?; [ $rc -eq 3 ] && exit 3; wait $pid; rc=$?; rm -f LOG BEAT; exit $rc
    } 9< LOG 8< BEAT

  The wrapper creates LOG and BEAT and opens both (fds 9 and 8) before the job starts; the watcher
  streams from those handles, so a job that ends at once, and removes its files, loses no output. The
  job's EXIT trap removes both files when the job ends, also after a stall (the job keeps running and
  writing until then) and for the original's `exit N`, whose code the wrapper keeps. The STALL report
  says the log is usually removed when the job ends. Limit: an original that execs or sets its own EXIT trap
  drops the trap; the wrapper's `rm -f` after `wait` still cleans up a job that never stalled.

  BEAT is stall-watch-<id>.beat next to LOG. A tool that is quiet by
  design (bin/verdict) appends its heartbeat there too, and the watcher relays it to its stdout (the
  harness output file), so a redirect in the command cannot hide it from the watcher or the Stop check.
  Each log the original names (named_logs: `> F`, `>> F`, `&> F`, `>& F`, `tee F`, `--log F`)
  is passed as `--also F`.
  Cost: one append per heartbeat by the tool, and one read of BEAT on each 0.2 s loop pass in the watcher.

  Agent marker: for a background Bash call whose payload has a valid agent_id, the wrapper above gets
  `export CLAUDE_AGENT_ID=<id>` and a newline in front, so each process the job execs holds the marker
  (name: proc_env.AGENT_TAG_NAME; read by proc_env.entry_value). That export line is the one addition.
  The job's `( )` subshell is a fork, so it holds no marker; its exec'd children do. A foreground call is
  never rewritten, with or without agent_id: Claude Code checks permission rules on a hook's rewritten
  input, so a rewrite would change what the rules see. A foreground agent call is unmarked. With no or
  a malformed agent_id the output is as before. Windows is unchanged and unmarked (reads as unmarked,
  which keeps a tree). Cost: no new process start, no file written; one string prepend per background
  agent Bash call, inside the hook process that already runs per Bash call.

  The original stays unquoted, as top-level shell code, so a settings deny rule still sees it.
  STALL_WATCH_QUIET overrides the default quiet time (for tests and proofs only).

Watcher: stall_watch.py --watch-pid PID --log LOG [--quiet SECS] [--beat BEAT] [--also F]...
         [--log-fd N] [--beat-fd N]
  Streams LOG to stdout (from fd N when given: the handle the wrapper opened, else by path). Any new byte, also a bare \\r, resets the timer. It streams each new byte
  of BEAT (a file that need not exist yet) to stdout too, and it resets the timer the same way. After SECS (default
  300) without new bytes, and with no change to any --also log, it prints a STALL report and exits 3,
  and the job keeps running. The
  STALL line lists the job's shell and every process under it, parent first. Stopping them in that
  order ends the job, with two limits: an orphan (`(sleep N &); sleep N`) is adopted by init and
  not listed, and a TERM trap that returns respawns a loop body (SIGKILL ends it). When the job
  ends first, it exits 0.

Stop: stall_watch.py --stop
  Stop hook. Reads the Stop JSON on stdin, scans the session transcript for background shells
  (also a foreground call that its timeout moved to the background, which --hook never sees),
  and prints one {"systemMessage": ...} line that lists each open job whose output file, and each
  log its command names, has not changed for the quiet age, and whose stall crossed after the previous
  Stop (the newest stop_hook_summary record, skipping the run after a blocked Stop). A job with no
  output file is listed once, at the first Stop after its call. With no summary, all are listed. A job closes on a <task-notification> with status completed, failed,
  killed or stopped (a user message, or a queued_command attachment record), or on the result of
  a TaskStop call, 'Successfully stopped task: <id>'. A job with no output file is listed as
  unknown. A background agent (toolUseResult isAsync, status async_launched, agentId) is a job too: its
  transcript is <session dir>/<session stem>/subagents/agent-<id>.jsonl (else the launch's outputFile),
  and it closes as a shell does. It is not listed while a tool_use in the read window has no tool_result, read from
  the last 64 KB of a quiet agent's transcript, widened to hold a whole last record. Cost: one stat per
  running agent, one tail read per quiet agent. Any error, or stop_hook_active true, prints nothing and exits 0. No posix check.
  CI-wait check: the same Stop run reads the transcript once more, one record at a time. The newest
  ready call (`gh pr ready <N>` in Bash or PowerShell, outside quotes, heredoc bodies and `#` comments, not
  --undo; or MCP update_pull_request with draft false) opens a wait. A `gh` global flag before `pr`
  (`gh -R o/r pr ready 5`) is skipped. A later user or queued message with a
  `CI green|cancelled on <sha>` line closes it; a `CI unknown` line leaves it open. A merge or close that
  names the waited PR number closes it (bin/merge N, merge N, gh pr merge N, gh pr close N in Bash or
  PowerShell, same scanner rules; MCP merge_pull_request with that pullNumber). The ready call's PR and a
  merge's are read alike (pr_ref): the first all-digit word or the N of a /pull/N URL, with each flag and its
  value (CI_VALUE_FLAGS: -R o/r, -C /repo, --body "x", --body-file f, --subject "Fix", --comment x,
  --session lane) skipped; with no number, the first non-dash word (a branch) is the PR named. A gh pr merge or close with no
  PR word, only flags and their values, closes any open wait; so does one whose PR word is a $var, an unknown
  number. A bin/merge with no PR word, or a $var one, gives no event. A gh pr merge with --auto or
  --disable-auto closes nothing, and an MCP merge with no pullNumber closes none. A wait
  whose ready call named no number (bare gh pr ready, or a $var) closes on a merge or close of any PR. A
  `CI red` line keeps it open and voids the check-ins before it. A later send_later, create_trigger,
  CronCreate or ScheduleWakeup call covers it, unless its tool_result has is_error true. An open wait with no check-in prints
  {"decision": "block", "reason": ...} naming the PR (the systemMessage of any stale job rides in the same
  line). Rule git-ci-wait-checks-in. Cost: one more read of the transcript at Stop, zero process starts, zero
  files written, zero timers, no network. Any error prints nothing.
  Seams: STALL_WATCH_NOW (epoch seconds), STALL_WATCH_OUTPUT_BASE (replaces the folder of each
  output path, keeps the file name), STALL_WATCH_QUIET (the age in seconds).
  A listed job shows the `until:` note from the description of the call that started it (Bash or
  PowerShell), read by guard_stream.until_note. The guard refuses a background server with no note.

See docs/decisions/stall-watch.md.
"""
import calendar
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import own_session  # the one home of the agent transcript folder
try:
    import _nowindow  # the one home of a no-window child start (hooks/_nowindow.py)
except ImportError:  # a hook never dies for a missing helper (it lands a moment after the hook in an install)
    _nowindow = subprocess
try:
    from proc_env import AGENT_TAG_NAME  # the one home of the agent marker's name
except ImportError:  # without it the hook cannot mark an agent call: it leaves the call unmarked
    AGENT_TAG_NAME = None
try:
    from guard_stream import until_note  # the one parser of the `until:` note
except ImportError:  # the Stop check is a recovery control: it runs without notes, never dies
    def until_note(description) -> str:
        return ""
try:
    from guard_core import strip_heredoc_bodies  # the one heredoc walk: a body is text, not a redirect
except ImportError:  # without it a heredoc body may name a log: at worst a stall is missed there
    def strip_heredoc_bodies(cmd, shells_only=False) -> str:
        return cmd
try:
    from shared_names import TASK_NOTIFICATION_TAG  # the one home of the notice tag
except ImportError:  # without the tag no notice can close a job, so Stop prints nothing
    TASK_NOTIFICATION_TAG = None
# The pre-filter's bytes key: the tag's bare name, so a line with the name in any form passes.
NOTICE_KEY = (TASK_NOTIFICATION_TAG.strip("<>").encode(),) if TASK_NOTIFICATION_TAG else ()

DEFAULT_QUIET = 300
STALL_EXIT = 3
TAIL_LINES = 20
TOOL_TIMEOUT = 5  # seconds for each ps or lsof call, so the report cannot hang


REDIRECT_OPS = (">", ">>", ">|", "&>", "&>>", ">&")
LOG_FLAGS = ("--log",)


def named_logs(command):
    """The files a command names as its own log: the target of `> F`, `>> F`, `&> F` or `>& F` (any
    descriptor), each file argument of `tee`, and the value of `--log F` or `--log=F`. shlex reads
    the command, so a path inside quotes or after `#` is text. A heredoc body is dropped first. A
    target with `$`, a backtick or a glob, a descriptor (`>&2`) and a /dev/ path are left out. A
    command shlex cannot read names none. The paths stay as written: a relative one resolves against
    the reader's own working directory."""
    try:
        lex = shlex.shlex(strip_heredoc_bodies(command, shells_only=True), posix=True,
                          punctuation_chars=True)
        lex.whitespace_split = True
        tokens = list(lex)
    except Exception:
        return []
    punct = set(lex.punctuation_chars)
    found, i = [], 0
    while i < len(tokens):
        tok, nxt = tokens[i], tokens[i + 1] if i + 1 < len(tokens) else None
        if set(tok) <= punct and tok.endswith(REDIRECT_OPS) and nxt is not None:
            if not (tok.endswith(">&") and (nxt.isdigit() or nxt == "-")):
                found.append(nxt)
            i += 2
            continue
        if os.path.basename(tok) == "tee" and (i == 0 or set(tokens[i - 1]) <= punct):
            j = i + 1
            while j < len(tokens) and not set(tokens[j]) <= punct:
                if not tokens[j].startswith("-"):
                    found.append(tokens[j])
                j += 1
            i = j
            continue
        if tok in LOG_FLAGS and nxt is not None:
            found.append(nxt)
        elif tok.startswith(tuple(f + "=" for f in LOG_FLAGS)):
            found.append(tok.split("=", 1)[1])
        i += 1
    keep = []
    for path in found:
        path = os.path.expanduser(path)
        if path and not re.search(r"[$`*?\[]", path) and not path.startswith("/dev/") and path not in keep:
            keep.append(path)
    return keep


def log_marks(paths, base=None):
    """{path: (size, mtime) or None} for each named log; a relative path joins base when given."""
    marks = {}
    for path in paths:
        real = os.path.join(base, path) if base else path
        try:
            st = os.stat(real)
            marks[path] = (st.st_size, st.st_mtime)
        except (OSError, ValueError):
            marks[path] = None
    return marks


def _run(args):
    try:
        return _nowindow.run(args, capture_output=True, text=True, errors="replace",
                              timeout=TOOL_TIMEOUT).stdout
    except Exception as exc:
        return "(%s did not answer: %s)\n" % (args[0], type(exc).__name__)


def job_state(pid):
    """Return the ps state of pid, or '' when it is gone. A Z state is an ended job whose
    parent shell has not yet waited for it."""
    return _run(["ps", "-o", "stat=", "-p", str(pid)]).strip()


def ended_state(state):
    return state == "" or state.startswith("Z")


def job_tree(pid):
    """Return rows [pid, state, elapsed, command] for the job's shell and every process under it,
    parent first. The job's pid is the one `&` gave the shell. Stopping the rows in order ends the
    job: a parent dies before it can start another child."""
    rows, kids = {}, {}
    for line in _run(["ps", "-axo", "pid=,ppid=,stat=,etime=,command="]).splitlines():
        p = line.split(None, 4)
        if len(p) >= 4:
            rows[p[0]] = p
            kids.setdefault(p[1], []).append(p[0])
    found, stack = [], [str(pid)]
    while stack:
        cur = stack.pop()
        if cur in rows:
            p = rows[cur]
            found.append([p[0], p[2], p[3], p[4] if len(p) > 4 else ""])
            stack.extend(kids.get(cur, [])[::-1])
    return found


def report(pid, quiet, log, also=(), beat=None, logf=None, beatf=None):
    """Print the STALL report. logf and beatf are the handles the watcher holds (the job removes the
    files by path when it ends, so the tail reads the handle, never the path)."""
    rows = job_tree(pid)
    pids = ",".join(r[0] for r in rows) or str(pid)
    lines = ["STALL: no output for %ss; pid=%s is still running" % (quiet, pids),
             "The job was not stopped, and the session cannot stop it: the job is not its child.",
             "Diagnose it from this report. To stop the job, ask the owner to stop pid=%s, in order."
             % pids,
             "To wait on the job without a loop, run `~/.claude/bin/wait-pid %s` (it never stops the job)."
             % pid,
             "A long wait runs with run_in_background: Bash's default foreground timeout is 120 s.",
             "Processes (pid state elapsed command):"]
    lines += ["  " + " ".join(r) for r in rows] or ["  (none found)"]
    if shutil.which("lsof"):
        locks = [l for l in _run(["lsof", "-nP", "-p", pids]).splitlines() if "lock" in l.lower()]
        lines += ["Open files with 'lock' in the path:"] + ["  " + l for l in locks or ["(none)"]]
        net = _run(["lsof", "-nP", "-i", "-a", "-p", pids]).splitlines()
        lines += ["Network connections:"] + ["  " + l for l in net or ["(none)"]]
    else:
        lines.append("lsof is not installed: open files and connections not listed.")
    try:
        if logf is not None:
            logf.seek(0)
            raw = logf.read()
        else:
            with open(log, "rb") as f:
                raw = f.read()
        tail = raw.decode("utf-8", "replace").replace("\r", "\n").splitlines()[-TAIL_LINES:]
    except (OSError, ValueError):
        tail = []
    lines += ["Last %d output lines:" % TAIL_LINES] + ["  " + l for l in tail or ["(no output)"]]
    lines.append("Log: %s (usually removed when the job ends)" % log)
    lines += ["Named log, no growth either: " + os.path.abspath(p) for p in also]
    try:  # the wrapper creates the beat file empty: a heartbeat is a non-empty one
        beat_used = os.fstat(beatf.fileno()).st_size > 0 if beatf is not None else bool(beat and os.path.exists(beat))
    except (OSError, ValueError):
        beat_used = False
    if beat_used:
        lines.append("Beat file (verdict heartbeat), no growth: " + os.path.abspath(beat))
    sys.stdout.write("\n".join(lines) + "\n")
    sys.stdout.flush()


def held(fd):
    """A read handle on an fd the wrapper opened before the job started, or None when fd is not
    given or not open (the watcher then opens the path, as a direct run does)."""
    try:
        return os.fdopen(int(fd), "rb") if fd is not None else None
    except (OSError, ValueError):
        return None


def watch(pid, log, quiet, also=(), beat=None, log_fd=None, beat_fd=None):
    """Stream LOG and BEAT; report a stall after quiet seconds with no new byte on either and no
    change to any named log (named_logs). The named logs cost one stat each a second, in this loop.
    BEAT is where a quiet-by-design tool (bin/verdict) appends its heartbeat; it may not exist at
    start, so it is opened at the first check that finds it. The wrapper creates both files and opens
    both before the job starts, and the job removes them when it ends; log_fd and beat_fd are those
    handles, so a job that ends at once loses no output."""
    last = time.monotonic()
    marks = log_marks(also)
    next_check = 0.0
    recheck = False
    waited = 0
    lf, bf = held(log_fd), held(beat_fd)
    while lf is None and not os.path.exists(log):  # the shell creates it a moment before this runs
        waited += 1
        if waited % 10 == 0 and ended_state(job_state(pid)):  # a dead job with no log: stop
            return 0
        time.sleep(0.05)
    with (lf if lf is not None else open(log, "rb")) as f:
        while True:
            now = time.monotonic()
            ended = checked = False
            if now >= next_check or recheck:  # one ps a second, not one per read
                checked, recheck = True, False
                ended = ended_state(job_state(pid))
                next_check = now + 1.0
                if also:
                    seen = log_marks(also)
                    if seen != marks:  # the job still writes to a log it named
                        marks, last = seen, time.monotonic()
                if beat and bf is None:
                    try:
                        bf = open(beat, "rb")
                    except OSError:
                        pass
            data = f.read()  # read after the state check, so the last output is not lost
            if bf is not None:
                data += bf.read()
            if data:
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()
                last = time.monotonic()
            if ended:
                if bf is not None:
                    bf.close()
                return 0
            if time.monotonic() - last >= quiet:
                if not checked:  # the last sample may be a second old: sample again, then decide
                    recheck = True
                    continue
                report(pid, quiet, log, also, beat, f, bf)
                if bf is not None:
                    bf.close()
                return STALL_EXIT
            time.sleep(0.2)


def eof_backslash_literal():
    """True when /bin/sh keeps a backslash at end of input (dash, bash 5). Bash 3.2 drops it."""
    try:
        return _nowindow.run(["/bin/sh", "-c", "printf %s \\"], capture_output=True, text=True,
                              timeout=TOOL_TIMEOUT).stdout == "\\"
    except Exception:
        return False


AGENT_ID = re.compile(r"[0-9a-f]{17}")  # an agent_id as the payload carries it


def agent_export(call):
    """The agent marker line, `export CLAUDE_AGENT_ID=<id>` and a newline, for a call whose payload has a valid
    agent_id, else ""."""
    agent_id = call.get("agent_id")
    if AGENT_TAG_NAME and isinstance(agent_id, str) and AGENT_ID.fullmatch(agent_id):
        return "export %s=%s\n" % (AGENT_TAG_NAME, agent_id)
    return ""


def hook():
    # ponytail: posix only. The rewrite needs `&`, `$!` and `wait`, and Windows has no harness
    # shell that matches. Returning nothing leaves a Windows call unchanged, unmarked: a process
    # that reads unmarked keeps its tree (fail-safe).
    if os.name != "posix":
        return 0
    try:
        call = json.load(sys.stdin)
        inp = call["tool_input"]
        if call.get("tool_name") != "Bash":
            return 0
        original = inp["command"]
        if inp.get("run_in_background") is not True:
            return 0  # a foreground call is never rewritten: permission rules would see the rewrite
        prefix = agent_export(call)
    except Exception:
        return 0
    quiet = os.environ.get("STALL_WATCH_QUIET") or str(DEFAULT_QUIET)
    base = os.path.join(os.path.realpath(tempfile.gettempdir()), "stall-watch-%s" % uuid.uuid4().hex)
    log, beat = base + ".log", base + ".beat"  # the job makes the beat file, if a tool writes to it
    q = shlex.quote
    # An odd run of trailing backslashes ends in a line continuation. Bare, a shell that keeps the
    # backslash at end of input runs it as a literal; the rewrite's `}` line would swallow it. So
    # there, double the last one. The blank line before `}` stops the join in shells that drop it.
    if (len(original) - len(original.rstrip("\\"))) % 2 and eof_backslash_literal():
        original += "\\"
    # The wrapper creates LOG and BEAT and opens both (fds 9 and 8) before the job starts. The watcher
    # inherits the handles, so the job may remove the files by path the moment it ends and no output
    # is lost. The job closes both fds, so the original may use them. An EXIT trap in the job removes
    # the files when it ends, also after the watcher gave up on a stall, and for the original's `exit N`.
    # Limit: an original that execs, or sets its own EXIT trap, drops that trap; the wrapper's own
    # `rm -f` after `wait` still cleans up a job that never stalled.
    # The job group is `( )`: bash 3.2 (macOS /bin/sh) runs an EXIT trap only in a `( )` subshell.
    cleanup = "rm -f " + q(log) + " " + q(beat)
    wrapped = (
        ": > " + q(log) + "; : > " + q(beat) + "; {\n(\ntrap " + q(cleanup) + " EXIT; export STALL_WATCH_BEAT=" + q(beat)
        + "\n{ " + original + "\n\n}\n) >| " + q(log) + " 2>&1 9<&- 8<&- & pid=$!; "
        + " ".join(q(a) for a in [sys.executable, os.path.abspath(__file__)])
        + " --watch-pid $pid --log " + q(log) + " --quiet " + q(quiet) + " --beat " + q(beat)
        + " --log-fd 9 --beat-fd 8"
        + "".join(" --also " + q(p) for p in named_logs(original))
        + "; rc=$?; "
        + "[ $rc -eq 3 ] && exit 3; wait $pid; rc=$?; " + cleanup + "; exit $rc\n} 9< "
        + q(log) + " 8< " + q(beat)
    )
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "updatedInput": dict(inp, command=prefix + wrapped)}}))
    return 0


TASK_ID = re.compile(r"<task-id>(.*?)</task-id>", re.S)
TASK_STATUS = re.compile(r"<status>(.*?)</status>", re.S)
RESULT_PATH = re.compile(r"Output is being written to: (.*?\.output)", re.S)
STOPPED = re.compile(r"\s*Successfully stopped task: (\S+)")
TERMINAL = ("completed", "failed", "killed", "stopped")


def text_of(content):
    """The text of a message content: a string, or the text and tool_result strings of a list."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = [b.get("text") or b.get("content") for b in content if isinstance(b, dict)]
    return "\n".join(p for p in parts if isinstance(p, str))


ISO_Z = re.compile(r"(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)(?:\.(\d+))?Z$")


def parse_time(text):
    """Epoch seconds of an ISO timestamp ending in Z, or None. Not fromisoformat: before Python 3.11
    it rejects the Z."""
    m = ISO_Z.match(text) if isinstance(text, str) else None
    if not m:
        return None
    try:
        whole = calendar.timegm(tuple(int(g) for g in m.groups()[:6]) + (0, 0, 0))
    except (ValueError, OverflowError):
        return None
    return whole + (float("0." + m.group(7)) if m.group(7) else 0.0)


def scan_jobs(transcript):
    """Return ({job id: (output path or None, until note or '', (named logs, cwd), start time or None,
    is an agent)}, previous Stop time or None) for every job with no terminal task notice and no TaskStop
    result. A job is a shell (toolUseResult backgroundTaskId) or a background agent (toolUseResult
    isAsync true, status async_launched, agentId; its path is the launch's outputFile). The
    note and the named logs come from the call that started the job, matched by tool_use_id. The
    previous Stop is the timestamp of the newest stop_hook_summary record the harness wrote after a
    Stop run that this check ran in (see below); None when there is none or its timestamp is unreadable.
    A Stop that a hook blocked is followed by a run with stop_hook_active true, where stop() prints
    nothing: the summary of that run lists nothing, so it is not a Stop."""
    jobs, done, stops, notes, job_call, logs, began, agents = {}, set(), set(), {}, {}, {}, {}, set()
    prev_stop, blocked = None, False
    with open(transcript, "rb") as f:
        for line in f:
            if not any(k in line for k in (b"backgroundTaskId", b"TaskStop", b"Successfully stopped", b"until:", b"tool_use", b"stop_hook_summary", b"async_launched") + NOTICE_KEY):
                continue
            try:
                rec = json.loads(line)
                kind = rec.get("type")
                when = parse_time(rec.get("timestamp"))
                if kind == "system":
                    if rec.get("subtype") == "stop_hook_summary":
                        if not blocked:  # the run after a blocked Stop had stop_hook_active: it listed nothing
                            prev_stop = when
                        blocked = bool(rec.get("hookErrors")) or rec.get("preventedContinuation") is True
                    continue
                if kind == "attachment":  # a completion notice that arrives as a queued command
                    att = rec.get("attachment")
                    notice = att.get("prompt") if isinstance(att, dict) else None
                    if isinstance(notice, str):
                        done.update(closed_by_notice(notice))
                    continue
                content = rec["message"]["content"]
                text = text_of(content)
            except Exception:  # a bad or half-written line is skipped
                continue
            tur = rec.get("toolUseResult")
            jid = None
            if isinstance(tur, dict) and isinstance(tur.get("backgroundTaskId"), str):
                jid = tur["backgroundTaskId"]
                m = RESULT_PATH.search(text)
                jobs.setdefault(jid, m.group(1) if m else None)
            elif (isinstance(tur, dict) and tur.get("isAsync") is True and tur.get("status") == "async_launched"
                  and isinstance(tur.get("agentId"), str)):
                jid = tur["agentId"]
                out = tur.get("outputFile")
                jobs.setdefault(jid, out if isinstance(out, str) else None)
                agents.add(jid)
            if jid is not None:
                began.setdefault(jid, when)
                if isinstance(content, list):
                    job_call.setdefault(jid, next(
                        (b.get("tool_use_id") for b in content if isinstance(b, dict)
                         and b.get("type") == "tool_result"), None))
            elif kind == "assistant" and isinstance(content, list):
                for b in content:  # a Bash or PowerShell call: its description may hold the note
                    if isinstance(b, dict) and b.get("type") == "tool_use" and isinstance(b.get("input"), dict):
                        notes[b.get("id")] = until_note(b["input"].get("description"))
                        cmd = b["input"].get("command")
                        if isinstance(cmd, str):
                            cwd = rec.get("cwd")
                            logs[b.get("id")] = (named_logs(cmd), cwd if isinstance(cwd, str) else None)
                stops.update(b["id"] for b in content if isinstance(b, dict)
                             and b.get("type") == "tool_use" and b.get("name") == "TaskStop"
                             and isinstance(b.get("id"), str))
            elif kind == "user":
                done.update(closed_by_notice(text))
                if isinstance(content, list):  # only the result of a TaskStop call of this session
                    for b in content:
                        if isinstance(b, dict) and b.get("type") == "tool_result" and isinstance(b.get("tool_use_id"), str) and b["tool_use_id"] in stops:
                            done.update(stopped_ids(b.get("content")))
    return ({k: (v, notes.get(job_call.get(k)) or "", logs.get(job_call.get(k)) or ((), None), began.get(k),
                k in agents)
             for k, v in jobs.items() if k not in done}, prev_stop)


def closed_by_notice(text):
    """The ids of the <task-notification> blocks in text with a terminal status."""
    ids = []
    if not TASK_NOTIFICATION_TAG:
        return ids
    for note in text.split(TASK_NOTIFICATION_TAG)[1:]:
        tid, st = TASK_ID.search(note), TASK_STATUS.search(note)
        if tid and st and st.group(1).strip().lower() in TERMINAL:
            ids.append(tid.group(1).strip())
    return ids


def stopped_ids(content):
    """The id a TaskStop result closes: its message starts 'Successfully stopped task: <id>'. The
    result is a JSON string with a message field; the whole id is matched, never a prefix."""
    content = text_of(content)
    try:
        body = json.loads(content)
        msg = body["message"] if isinstance(body, dict) else content
    except Exception:
        msg = content
    m = STOPPED.match(msg) if isinstance(msg, str) else None
    return [m.group(1)] if m else []

CI_VERDICT = re.compile(r"^CI (green|red|cancelled|unknown) on \S", re.M)
CI_KEYS = (b"ready", b"pull_request", b"merge", b"send_later", b"create_trigger", b"CronCreate",
           b"ScheduleWakeup", b"CI ", b"close", b'"is_error":true', b'"is_error": true')
CI_CHECKIN_TOOLS = ("send_later", "create_trigger", "CronCreate", "ScheduleWakeup")
CI_SEGMENT = re.compile(r"[;&|\n]+")
PR_NUMBER = re.compile(r"[0-9]+\Z")
PR_URL = re.compile(r"/pull/([0-9]+)")
CI_VALUE_FLAGS = frozenset(("-R", "--repo", "--hostname", "-C", "--session", "-b", "--body", "-F", "--body-file",
                            "-t", "--subject", "-A", "--author-email", "--match-head-commit", "-c", "--comment"))
CI_REMEDY = ("Set a one-time send_later check-in for this wait (rule git-ci-wait-checks-in), then stop. "
             "Set the next one after each red CI verdict, wider apart.")


def unquoted(command):
    """The command with quoted text, `#` comments and heredoc bodies dropped, so only shell words remain.
    A quote with no closer is a plain character (an apostrophe in a word), so it hides nothing after it."""
    text = strip_heredoc_bodies(command)
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c in "'\"":
            j = i + 1
            while j < n and text[j] != c:
                j += 2 if (c == '"' and text[j] == "\\") else 1
            if j < n:
                out.append(c + c)
                i = j + 1
                continue
        elif c == "\\":
            out.append(text[i:i + 2])
            i += 2
            continue
        elif c == "#" and (not out or out[-1][-1] in " \t\n;&|("):
            while i < n and text[i] != "\n":
                i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def shell_calls(command):
    """The word lists of each simple command in a shell command line, quoted text and comments gone."""
    return [seg.split() for seg in CI_SEGMENT.split(unquoted(command)) if seg.strip()]


def pr_ref(words):
    """The PR a ready, merge or close call names: its first all-digit word, or the number in a /pull/<N> URL.
    A flag and the value it takes (CI_VALUE_FLAGS: -R o/r, -C /repo, --body "x", --session lane) are skipped.
    With no number, its first non-dash word (a branch name), which matches no numbered wait. '' when the
    call names no PR: only flags, or a PR word that is a shell variable or empty quotes, whose number is
    unknown. A call with no PR word is bare."""
    words = list(flag_free(words))
    for w in words:
        if PR_NUMBER.match(w):
            return w
        m = PR_URL.search(w)
        if m:
            return m.group(1)
    return next((w for w in words if not w.startswith(("$", "'", '"'))), "")


def flag_free(words):
    """The words with each flag and the value it takes dropped. A flag in --name=value form is one word."""
    skip = False
    for w in words:
        if skip:
            skip = False
        elif w.startswith("-"):
            skip = w in CI_VALUE_FLAGS
        else:
            yield w


def gh_pr_call(words):
    """('ready'|'merge'|'close', the words after it) for a `gh pr <sub>` call, global flags such as
    `-R o/r` before `pr` skipped; None for any other call."""
    if not words or words[0] != "gh":
        return None
    rest = list(words[1:])
    i = 0
    while i < len(rest) and rest[i].startswith("-"):
        i += 2 if rest[i] in CI_VALUE_FLAGS else 1
    if rest[i:i + 1] == ["pr"] and rest[i + 1:i + 2] and rest[i + 1] in ("ready", "merge", "close"):
        return rest[i + 1], rest[i + 2:]
    return None


def ci_events(rec):
    """The CI-wait events one transcript record holds, in order: ('ready', pr), ('checkin', call id),
    ('failed', call id), ('merge', pr), ('mergeany',), ('verdict', word). A user or queued message holds a
    verdict line; only an assistant call holds the rest. A tool result is no message, so a verdict it prints
    is not one, but its error flag voids the check-in it answers. ('merge', pr) is a merge or close that names
    pr (pr_ref); ('mergeany',) is a gh pr merge or close that names no PR at all, only flags, which aims at
    the current branch's PR."""
    kind = rec.get("type")
    if kind == "attachment":
        att = rec.get("attachment")
        text = att.get("prompt") if isinstance(att, dict) and att.get("type") == "queued_command" else None
        return [("verdict", m.group(1)) for m in CI_VERDICT.finditer(text)] if isinstance(text, str) else []
    content = rec["message"]["content"]
    if kind == "user":
        failed = [("failed", b.get("tool_use_id")) for b in (content if isinstance(content, list) else ())
                  if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("is_error") is True]
        if failed or "toolUseResult" in rec:
            return failed
        if isinstance(content, list):
            content = "\n".join(b["text"] for b in content if isinstance(b, dict) and b.get("type") == "text"
                                and isinstance(b.get("text"), str))
        return [("verdict", m.group(1)) for m in CI_VERDICT.finditer(content)] if isinstance(content, str) else []
    events = []
    for b in content if kind == "assistant" and isinstance(content, list) else ():
        if not (isinstance(b, dict) and b.get("type") == "tool_use" and isinstance(b.get("input"), dict)):
            continue
        name, inp = str(b.get("name")), b["input"]
        tool = name.rsplit("__", 1)[-1]
        if tool in CI_CHECKIN_TOOLS:
            events.append(("checkin", b.get("id")))
        elif tool == "merge_pull_request":
            if inp.get("pullNumber"):
                events.append(("merge", str(inp["pullNumber"])))
        elif tool == "update_pull_request" and inp.get("draft") is False:
            events.append(("ready", str(inp.get("pullNumber") or "")))
        elif isinstance(inp.get("command"), str) and name in ("Bash", "PowerShell"):
            for words in shell_calls(inp["command"]):
                gh = gh_pr_call(words)
                if gh and gh[0] == "ready":
                    if "--undo" not in gh[1]:
                        events.append(("ready", pr_ref(gh[1])))
                elif gh:
                    # --auto only queues the merge and --disable-auto drops it: neither has merged anything
                    if not {"--auto", "--disable-auto"} & set(gh[1]):
                        pr = pr_ref(gh[1])
                        events.append(("merge", pr) if pr else ("mergeany",))
                elif words[0] == "merge" or words[0].replace("\\", "/").endswith("bin/merge"):
                    pr = pr_ref(words[1:])
                    if pr:
                        events.append(("merge", pr))
    return events


def open_ci_wait(transcript):
    """The PR of a CI wait that is open with no check-in, as a string ('' when the call named none), or
    None. The newest ready call opens a wait. A green or cancelled verdict closes it; an unknown verdict
    leaves it open. A merge or close closes a numbered wait only when it names that PR, or is a gh pr merge
    or close that names no PR at all; it closes a wait whose ready call named no PR when it names any PR or
    none. A
    red verdict keeps it open and voids the check-ins before it. A check-in after the anchor
    covers it, unless its result was an error. One streamed read, records in file order."""
    wait = None  # [pr, ids of the check-ins since the anchor]
    with open(transcript, "rb") as f:
        for line in f:
            if not any(k in line for k in CI_KEYS):
                continue
            try:
                events = ci_events(json.loads(line))
            except Exception:  # a bad or half-written line is skipped
                continue
            for ev in events:
                if ev[0] == "ready":
                    wait = [ev[1], set()]
                elif wait is None:
                    continue
                elif ev[0] == "checkin":
                    wait[1].add(ev[1])
                elif ev[0] == "failed":
                    wait[1].discard(ev[1])
                elif ev[0] == "mergeany" or (ev[0] == "merge" and wait[0] in ("", ev[1])):
                    wait = None
                elif ev[0] == "verdict":
                    if ev[1] == "red":
                        wait[1].clear()
                    elif ev[1] != "unknown":
                        wait = None
    return wait[0] if wait and not wait[1] else None


TRANSCRIPT_AGENT_ID = re.compile(r"[\w-]+\Z")  # an id safe to put in a transcript file name
TAIL_BYTES = 64 * 1024  # the first read of an agent transcript's end; it doubles to hold the last record
TAIL_MAX = 32 * 1024 * 1024
AGENT_REMEDY = "Stop it, then resume it by name, or send a fresh reviewer the prior report."


def agent_transcripts(session, agent, output):
    """The paths of a background agent's transcript, in the order to try: beside the session file
    (<dir>/<stem>/subagents/agent-<id>.jsonl), then the launch's outputFile. An id with a separator
    has no path beside the session."""
    paths = []
    if TRANSCRIPT_AGENT_ID.match(agent):
        paths.append(own_session.agent_transcript_path(session, agent))
    if output and output not in paths:
        paths.append(output)
    return paths


def open_call(path, size):
    """True when any tool_use in the read window has no tool_result yet: the agent is in
    one long call, not stalled. Reads only the end of the file: TAIL_BYTES, doubled until the window
    holds a whole last record (the first line of a window that starts mid-file is cut and dropped).
    An empty file, or one with every tool_use answered, is not an open call."""
    window = TAIL_BYTES
    with open(path, "rb") as f:
        while True:
            start = max(0, size - window)
            f.seek(start)
            lines = f.read(size - start).split(b"\n")
            if start > 0:
                lines = lines[1:]
            lines = [l for l in lines if l.strip()]
            if lines or start == 0 or window >= TAIL_MAX:
                break
            window *= 2
    pending = set()
    for line in lines:
        try:
            rec = json.loads(line)
            content = rec["message"]["content"]
            if not isinstance(content, list):
                continue
            for b in content:
                if not isinstance(b, dict):
                    continue
                if rec.get("type") == "assistant" and b.get("type") == "tool_use":
                    pending.add(b.get("id"))
                elif rec.get("type") == "user" and b.get("type") == "tool_result":
                    pending.discard(b.get("tool_use_id"))
        except Exception:  # a bad or half-written line is skipped
            continue
    return bool(pending)


def stale_rows(call):
    """One row for each stale job in the call's transcript."""
    now = float(os.environ.get("STALL_WATCH_NOW") or time.time())
    quiet = float(os.environ.get("STALL_WATCH_QUIET") or DEFAULT_QUIET)
    base = os.environ.get("STALL_WATCH_OUTPUT_BASE")
    rows = []
    open_jobs, prev_stop = scan_jobs(call["transcript_path"])
    for job, (path, note, (named, cwd), began, agent) in open_jobs.items():
        until = " | until: " + note if note else ""
        real = path
        if path and base:
            real = os.path.join(base, re.split(r"[\\/]", path)[-1])
        st = None
        for real in (agent_transcripts(call["transcript_path"], job, real) if agent else [real]):
            try:
                st = os.stat(real)
                break
            except (OSError, TypeError, ValueError):  # TypeError: no path recorded; ValueError: NUL in path
                continue
        if st is None:
            if prev_stop is not None and began is not None and began <= prev_stop:
                continue  # started before the previous Stop, which listed it
            what = "transcript" if agent else "output file"
            rows.append("%s: unknown, %s not found: %s%s%s" % (
                job, what, path or "(path not recorded)", until, " " + AGENT_REMEDY if agent else ""))
            continue
        idle = now - st.st_mtime
        if agent:  # a transcript has no named logs; one long tool call is not a stall
            if idle >= quiet and not (prev_stop is not None and now - idle + quiet <= prev_stop):
                try:
                    busy = open_call(real, st.st_size)
                except OSError:
                    busy = False
                if not busy:
                    rows.append("%s: background agent, no activity for %ds: %s%s %s" % (
                        job, idle, real, until, AGENT_REMEDY))
            continue
        for mark in log_marks([p for p in named if os.path.isabs(p) or cwd], cwd).values():
            if mark:  # a named log the job still writes keeps it off the list
                idle = min(idle, now - mark[1])
        if idle >= quiet:
            if prev_stop is not None and now - idle + quiet <= prev_stop:
                continue  # its stall crossed before the previous Stop, which listed it
            rows.append("%s: no output for %ds: %s%s" % (job, idle, path, until))
    return rows


def stop():
    try:
        call = json.load(sys.stdin)
        if call.get("stop_hook_active") is True:
            return 0
    except Exception:  # guard-hooks-fail-closed: a failed check prints nothing and does not block
        return 0
    rows, out = [], {}
    if TASK_NOTIFICATION_TAG:  # without the tag every finished job would look open: list none
        try:
            rows = stale_rows(call)
        except Exception:
            pass
    try:
        pr = open_ci_wait(call["transcript_path"])
        if pr is not None:
            out["decision"] = "block"
            out["reason"] = "PR %s is marked ready and no check-in is set (decision ci-wait-reads-run-status). %s" % (pr or "(this branch)", CI_REMEDY)
    except Exception:
        pass
    if rows:
        head = "Background jobs still running and quiet: stop it or tell the owner."
        if "| until: " in "".join(rows):
            head += " Say whether each until condition is met."
        out["systemMessage"] = "\n".join([head] + rows)
    if out:
        print(json.dumps(out))
    return 0


def main(argv):
    if argv[:1] == ["--hook"]:
        return hook()
    if argv[:1] == ["--stop"]:
        return stop()
    opts = {"--quiet": DEFAULT_QUIET, "--watch-pid": None, "--log": None, "--beat": None,
            "--log-fd": None, "--beat-fd": None}
    also = []
    for i in range(0, len(argv) - 1, 2):
        if argv[i] == "--also":
            also.append(argv[i + 1])
        elif argv[i] in opts:
            opts[argv[i]] = argv[i + 1]
    if not opts["--watch-pid"] or not opts["--log"]:
        print(__doc__)
        return 2
    return watch(int(opts["--watch-pid"]), opts["--log"], float(opts["--quiet"]), also, opts["--beat"],
                 opts["--log-fd"], opts["--beat-fd"])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
