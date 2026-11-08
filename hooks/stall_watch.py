#!/usr/bin/env python3
"""Stall watch for background Bash commands. Standard library only.

Modes:
- --hook: Before a background Bash command, wraps it so a watcher reports a stall after
  300 seconds with no new output. The job keeps running.
- --stop: At Stop, lists each open background job whose output file did not change for
  the quiet age.

Hook: stall_watch.py --hook
  PreToolUse hook. For a Bash call with run_in_background true, it returns updatedInput only
  (no permissionDecision), with this command, run by the harness shell:

    : > LOG; : > BEAT; {
    (
    trap 'rm -f BEAT; [ -e LOG.stalled ] || rm -f LOG' EXIT; export STALL_WATCH_BEAT=BEAT
    { <original>

    }
    ) >| LOG 2>&1 9<&- 8<&- & pid=$!; python3 stall_watch.py --watch-pid $pid --log LOG --quiet N --beat BEAT
      --log-fd 9 --beat-fd 8;
    rc=$?; [ $rc -eq 3 ] && exit 3; wait $pid; rc=$?; rm -f BEAT; [ -e LOG.stalled ] || rm -f LOG; exit $rc
    } 9< LOG 8< BEAT

  The wrapper creates LOG and BEAT and opens both (fds 9 and 8) before the job starts; the watcher
  streams from those handles, so a job that ends at once, and removes its files, loses no output. The
  job's EXIT trap removes BEAT when the job ends, and LOG too unless the job stalled, also after a stall
  (the job keeps running and writing until then) and for the original's `exit N`, whose code the wrapper
  keeps. On a stall the watcher writes LOG.stalled, a marker beside the log, before it exits 3, and the
  trap keeps a log that has one. The STALL report says the log is kept 7 days, so the final output
  of a job that keeps writing after its report stays readable (decision stall-watch). Each --hook call removes, from the log folder, every stall-watch log with a marker not
  written for 7 days, and that marker, and no other file: no timer runs. Limit: an original that execs or sets its own
  EXIT trap drops the trap; the wrapper's cleanup after `wait` (the trap's command) still cleans up a job that never stalled,
  and a stalled job of that kind leaves its log and marker for the 7-day prune.

  BEAT is stall-watch-<id>.beat next to LOG. A tool that is quiet by
  design appends there too (hooks/stall_beat.py: bin/verdict's heartbeat, and bin/ci-job's start line per step), and the watcher relays it to its stdout (the
  harness output file), so a redirect in the command cannot hide it from the watcher or the Stop check.
  Each log the original names (named_logs: `> F`, `>> F`, `&> F`, `>& F`, `tee F`, `--log F`)
  is passed as `--also F`.
  Cost: one append per verdict heartbeat or ci-job step start, and one read of BEAT on each 0.2 s loop pass in the watcher.

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
try:
    import _nowindow  # the one home of a no-window child start (hooks/_nowindow.py)
except ImportError:  # a hook never dies for a missing helper (it lands a moment after the hook in an install)
    _nowindow = subprocess
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
STALLED_SUFFIX = ".stalled"  # marker beside a stalled job's log: the log is kept
KEEP_DAYS = 7
KEPT_LOG = re.compile(r"stall-watch-[0-9a-f]{32}\.log\Z")
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
             "To wait on the job without a loop, run `wait-pid %s` (bin/wait-pid; it never stops the job)."
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
    lines.append("Log: %s (kept 7 days after its last write)" % log)
    lines += ["Named log, no growth either: " + os.path.abspath(p) for p in also]
    try:  # the wrapper creates the beat file empty: a heartbeat is a non-empty one
        beat_used = os.fstat(beatf.fileno()).st_size > 0 if beatf is not None else bool(beat and os.path.exists(beat))
    except (OSError, ValueError):
        beat_used = False
    if beat_used:
        lines.append("Beat file (verdict heartbeat, ci-job start lines), no growth: " + os.path.abspath(beat))
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
    BEAT is where a quiet-by-design tool appends (bin/verdict its heartbeat, bin/ci-job each step's start line); it may not exist at
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
                try:  # the job's EXIT trap keeps a log that has this marker (see hook)
                    open(log + STALLED_SUFFIX, "wb").close()
                except OSError:
                    pass
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


def prune_kept_logs(folder, now=None):
    """Remove each stall-watch log in folder not written for KEEP_DAYS and having its marker, then the
    marker. A log with no marker may belong to a live job and is never touched. One folder listing, in
    the hook process already running. No other file is touched. Errors are ignored."""
    cutoff = (time.time() if now is None else now) - KEEP_DAYS * 86400
    try:
        with os.scandir(folder) as entries:
            for entry in entries:
                try:
                    if (KEPT_LOG.match(entry.name) and entry.is_file(follow_symlinks=False)
                            and entry.stat(follow_symlinks=False).st_mtime < cutoff
                            and os.path.lexists(entry.path + STALLED_SUFFIX)):
                        os.remove(entry.path)
                        os.remove(entry.path + STALLED_SUFFIX)  # marker last: a failed log removal retries next call
                except OSError:
                    pass
    except OSError:
        pass


def hook():
    # ponytail: posix only. The rewrite needs `&`, `$!` and `wait`, and Windows has no harness
    # shell that matches. Returning nothing leaves a Windows background call unchanged.
    if os.name != "posix":
        return 0
    try:
        call = json.load(sys.stdin)
        inp = call["tool_input"]
        if call.get("tool_name") != "Bash" or inp.get("run_in_background") is not True:
            return 0
        original = inp["command"]
    except Exception:
        return 0
    quiet = os.environ.get("STALL_WATCH_QUIET") or str(DEFAULT_QUIET)
    folder = os.path.realpath(tempfile.gettempdir())
    prune_kept_logs(folder)
    base = os.path.join(folder, "stall-watch-%s" % uuid.uuid4().hex)
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
    # BEAT, and LOG unless the watcher left its stall marker, when the job ends, also after the watcher
    # gave up on a stall, and for the original's `exit N`.
    # Limit: an original that execs, or sets its own EXIT trap, drops that trap; the wrapper's own
    # cleanup after `wait` still cleans up a job that never stalled.
    # The job group is `( )`: bash 3.2 (macOS /bin/sh) runs an EXIT trap only in a `( )` subshell.
    # The cleanup after `wait` is the trap's own command: a marker written before report() ends keeps the
    # log whatever the watcher's exit code, so a kill or pipe error in report() cannot remove it.
    trap = "rm -f " + q(beat) + "; [ -e " + q(log + STALLED_SUFFIX) + " ] || rm -f " + q(log)
    cleanup = trap
    wrapped = (
        ": > " + q(log) + "; : > " + q(beat) + "; {\n(\ntrap " + q(trap) + " EXIT; export STALL_WATCH_BEAT=" + q(beat)
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
        "hookEventName": "PreToolUse", "updatedInput": dict(inp, command=wrapped)}}))
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


AGENT_ID = re.compile(r"[\w-]+\Z")
TAIL_BYTES = 64 * 1024  # the first read of an agent transcript's end; it doubles to hold the last record
TAIL_MAX = 32 * 1024 * 1024
AGENT_REMEDY = "Stop it, then resume it by name, or send a fresh reviewer the prior report."


def agent_transcripts(session, agent, output):
    """The paths of a background agent's transcript, in the order to try: beside the session file
    (<dir>/<stem>/subagents/agent-<id>.jsonl), then the launch's outputFile. An id with a separator
    has no path beside the session."""
    paths = []
    if AGENT_ID.match(agent):
        stem = os.path.splitext(os.path.basename(session))[0]
        paths.append(os.path.join(os.path.dirname(session), stem, "subagents", "agent-%s.jsonl" % agent))
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


def stop():
    if not TASK_NOTIFICATION_TAG:  # every finished job would look open: say nothing
        return 0
    try:
        call = json.load(sys.stdin)
        if call.get("stop_hook_active") is True:
            return 0
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
        if rows:
            head = "Background jobs still running and quiet: stop it or tell the owner."
            if "| until: " in "".join(rows):
                head += " Say whether each until condition is met."
            print(json.dumps({"systemMessage": "\n".join([head] + rows)}))
    except Exception:  # guard-hooks-fail-closed: a failed check prints nothing and does not block
        pass
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
