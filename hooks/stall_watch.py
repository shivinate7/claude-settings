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

    { <original>
    } > LOG 2>&1 & pid=$!; python3 stall_watch.py --watch-pid $pid --log LOG --quiet N;
    rc=$?; [ $rc -eq 3 ] && exit 3; wait $pid; rc=$?; rm -f LOG; exit $rc

  Each log the original names (named_logs: `> F`, `>> F`, `&> F`, `>& F`, `tee F`, `--log F`)
  is passed as `--also F`.

  The original stays unquoted, as top-level shell code, so a settings deny rule still sees it.
  STALL_WATCH_QUIET overrides the default quiet time (for tests and proofs only).

Watcher: stall_watch.py --watch-pid PID --log LOG [--quiet SECS]
  Streams LOG to stdout. Any new byte, also a bare \\r, resets the timer. After SECS (default
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
  log its command names, has not changed for the quiet age. A job closes on a <task-notification> with status completed, failed,
  killed or stopped (a user message, or a queued_command attachment record), or on the result of
  a TaskStop call, 'Successfully stopped task: <id>'. A job with no output file is listed as
  unknown. Any error, or stop_hook_active true, prints nothing and exits 0. No posix gate.
  Seams: STALL_WATCH_NOW (epoch seconds), STALL_WATCH_OUTPUT_BASE (replaces the folder of each
  output path, keeps the file name), STALL_WATCH_QUIET (the age in seconds).
  A listed job shows the `until:` note from the description of the call that started it (Bash or
  PowerShell), read by guard_stream.until_note. The guard refuses a background server with no note.

See docs/decisions/stall-watch.md.
"""
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


def report(pid, quiet, log, also=()):
    rows = job_tree(pid)
    pids = ",".join(r[0] for r in rows) or str(pid)
    lines = ["STALL: no output for %ss; pid=%s is still running" % (quiet, pids),
             "The job was not stopped, and the session cannot stop it: the job is not its child.",
             "Diagnose it from this report. To stop the job, ask the owner to stop pid=%s, in order."
             % pids,
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
        with open(log, "rb") as f:
            tail = f.read().decode("utf-8", "replace").replace("\r", "\n").splitlines()[-TAIL_LINES:]
    except OSError:
        tail = []
    lines += ["Last %d output lines:" % TAIL_LINES] + ["  " + l for l in tail or ["(no output)"]]
    lines.append("Log: " + log)
    lines += ["Named log, no growth either: " + os.path.abspath(p) for p in also]
    sys.stdout.write("\n".join(lines) + "\n")
    sys.stdout.flush()


def watch(pid, log, quiet, also=()):
    """Stream LOG; report a stall after quiet seconds with no new byte on it and no change to any
    named log (named_logs). The named logs cost one stat each a second, in this loop."""
    last = time.monotonic()
    marks = log_marks(also)
    next_check = 0.0
    recheck = False
    waited = 0
    while not os.path.exists(log):  # the shell creates it a moment before this runs
        waited += 1
        if waited % 10 == 0 and ended_state(job_state(pid)):  # a dead job with no log: stop
            return 0
        time.sleep(0.05)
    with open(log, "rb") as f:
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
            data = f.read()  # read after the state check, so the last output is not lost
            if data:
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()
                last = time.monotonic()
            if ended:
                return 0
            if time.monotonic() - last >= quiet:
                if not checked:  # the last sample may be a second old: sample again, then decide
                    recheck = True
                    continue
                report(pid, quiet, log, also)
                return STALL_EXIT
            time.sleep(0.2)


def eof_backslash_literal():
    """True when /bin/sh keeps a backslash at end of input (dash, bash 5). Bash 3.2 drops it."""
    try:
        return _nowindow.run(["/bin/sh", "-c", "printf %s \\"], capture_output=True, text=True,
                              timeout=TOOL_TIMEOUT).stdout == "\\"
    except Exception:
        return False


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
    log = os.path.join(os.path.realpath(tempfile.gettempdir()), "stall-watch-%s.log" % uuid.uuid4().hex)
    q = shlex.quote
    # An odd run of trailing backslashes ends in a line continuation. Bare, a shell that keeps the
    # backslash at end of input runs it as a literal; the rewrite's `}` line would swallow it. So
    # there, double the last one. The blank line before `}` stops the join in shells that drop it.
    if (len(original) - len(original.rstrip("\\"))) % 2 and eof_backslash_literal():
        original += "\\"
    wrapped = (
        "{ " + original + "\n\n} > " + q(log) + " 2>&1 & pid=$!; "
        + " ".join(q(a) for a in [sys.executable, os.path.abspath(__file__)])
        + " --watch-pid $pid --log " + q(log) + " --quiet " + q(quiet)
        + "".join(" --also " + q(p) for p in named_logs(original))
        + "; rc=$?; "
        + "[ $rc -eq 3 ] && exit 3; wait $pid; rc=$?; rm -f " + q(log) + "; exit $rc"
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


def scan_jobs(transcript):
    """Return {job id: (output path or None, until note or '', (named logs, cwd))} for every job with
    no terminal task notice and no TaskStop result. The note and the named logs come from the call
    that started the job, matched by tool_use_id."""
    jobs, done, stops, notes, job_call, logs = {}, set(), set(), {}, {}, {}
    with open(transcript, "rb") as f:
        for line in f:
            if not any(k in line for k in (b"backgroundTaskId", b"TaskStop", b"Successfully stopped", b"until:", b"tool_use") + NOTICE_KEY):
                continue
            try:
                rec = json.loads(line)
                kind = rec.get("type")
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
            if isinstance(tur, dict) and isinstance(tur.get("backgroundTaskId"), str):
                m = RESULT_PATH.search(text)
                jobs.setdefault(tur["backgroundTaskId"], m.group(1) if m else None)
                if isinstance(content, list):
                    job_call.setdefault(tur["backgroundTaskId"], next(
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
    return {k: (v, notes.get(job_call.get(k)) or "", logs.get(job_call.get(k)) or ((), None))
            for k, v in jobs.items() if k not in done}


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
        for job, (path, note, (named, cwd)) in scan_jobs(call["transcript_path"]).items():
            until = " | until: " + note if note else ""
            real = path
            if path and base:
                real = os.path.join(base, re.split(r"[\\/]", path)[-1])
            try:
                idle = now - os.stat(real).st_mtime
            except (OSError, TypeError, ValueError):  # TypeError: no path recorded; ValueError: NUL in path
                rows.append("%s: unknown, output file not found: %s%s" % (job, path or "(path not recorded)", until))
                continue
            for mark in log_marks([p for p in named if os.path.isabs(p) or cwd], cwd).values():
                if mark:  # a named log the job still writes keeps it off the list
                    idle = min(idle, now - mark[1])
            if idle >= quiet:
                rows.append("%s: no output for %ds: %s%s" % (job, idle, path, until))
        if rows:
            head = "Background shells still running and quiet: stop it or tell the owner."
            if "| until: " in "".join(rows):
                head += " Say whether each until condition is met."
            print(json.dumps({"systemMessage": "\n".join([head] + rows)}))
    except Exception:  # gate-hooks-fail-closed: a failed check prints nothing and does not block
        pass
    return 0


def main(argv):
    if argv[:1] == ["--hook"]:
        return hook()
    if argv[:1] == ["--stop"]:
        return stop()
    opts = {"--quiet": DEFAULT_QUIET, "--watch-pid": None, "--log": None}
    also = []
    for i in range(0, len(argv) - 1, 2):
        if argv[i] == "--also":
            also.append(argv[i + 1])
        elif argv[i] in opts:
            opts[argv[i]] = argv[i + 1]
    if not opts["--watch-pid"] or not opts["--log"]:
        print(__doc__)
        return 2
    return watch(int(opts["--watch-pid"]), opts["--log"], float(opts["--quiet"]), also)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
