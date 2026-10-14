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
    } > LOG 2>&1 & pid=$!; python3 stall_watch.py --watch-pid $pid --log LOG --quiet N; rc=$?;
    [ $rc -eq 3 ] && exit 3; wait $pid; rc=$?; rm -f LOG; exit $rc

  The original stays unquoted, as top-level shell code, so a settings deny rule still sees it.
  STALL_WATCH_QUIET overrides the default quiet time (for tests and proofs only).

Watcher: stall_watch.py --watch-pid PID --log LOG [--quiet SECS]
  Streams LOG to stdout. Any new byte, also a bare \\r, resets the timer. After SECS (default
  300) without new bytes, it prints a STALL report and exits 3, and the job keeps running. When
  the job ends first, it exits 0.

Stop: stall_watch.py --stop
  Stop hook. Reads the Stop JSON on stdin, scans the session transcript for background shells
  (also a foreground call that its timeout moved to the background, which --hook never sees),
  and prints one {"systemMessage": ...} line that lists each open job whose output file has not
  changed for the quiet age. A job closes on a <task-notification> with status completed, failed,
  killed or stopped (a user message, or a queued_command attachment record), or on the result of
  a TaskStop call, 'Successfully stopped task: <id>'. A job with no output file is listed as
  unknown. Any error, or stop_hook_active true, prints nothing and exits 0. No posix gate.
  Seams: STALL_WATCH_NOW (epoch seconds), STALL_WATCH_OUTPUT_BASE (replaces the folder of each
  output path, keeps the file name), STALL_WATCH_QUIET (the age in seconds).

See decisions/stall-watch.md.
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

DEFAULT_QUIET = 300
STALL_EXIT = 3
TAIL_LINES = 20
TOOL_TIMEOUT = 5  # seconds for each ps or lsof call, so the report cannot hang


def _run(args):
    try:
        return subprocess.run(args, capture_output=True, text=True, errors="replace",
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
    """Return [pid, state, elapsed, command] for the job and its descendants."""
    rows = {}
    for line in _run(["ps", "-axo", "pid=,ppid=,stat=,etime=,command="]).splitlines():
        p = line.split(None, 4)
        if len(p) >= 4:
            rows[p[0]] = p
    kids = {}
    for p in rows.values():
        kids.setdefault(p[1], []).append(p[0])
    found, stack = [], [str(pid)]
    while stack:
        cur = stack.pop()
        if cur in rows:
            p = rows[cur]
            found.append([p[0], p[2], p[3], p[4] if len(p) > 4 else ""])
        stack.extend(kids.get(cur, []))
    return found


def report(pid, quiet, log):
    rows = job_tree(pid)
    pids = ",".join(r[0] for r in rows) or str(pid)
    lines = ["STALL: no output for %ss; pid=%d is still running" % (quiet, pid),
             "The job was not stopped, and the session cannot stop it: the job is not its child.",
             "Diagnose it from this report. To stop pid=%d, ask the owner to stop it." % pid,
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
    sys.stdout.write("\n".join(lines) + "\n")
    sys.stdout.flush()


def watch(pid, log, quiet):
    last = time.monotonic()
    next_check = 0.0
    waited = 0
    while not os.path.exists(log):  # the shell creates it a moment before this runs
        waited += 1
        if waited % 10 == 0 and ended_state(job_state(pid)):  # a dead job with no log: stop
            return 0
        time.sleep(0.05)
    with open(log, "rb") as f:
        while True:
            now = time.monotonic()
            ended = False
            if now >= next_check:  # one ps a second, not one per read
                ended = ended_state(job_state(pid))
                next_check = now + 1.0
            data = f.read()  # read after the state check, so the last output is not lost
            if data:
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()
                last = time.monotonic()
            if ended:
                return 0
            if time.monotonic() - last >= quiet:
                report(pid, quiet, log)
                return STALL_EXIT
            time.sleep(0.2)


def eof_backslash_literal():
    """True when /bin/sh keeps a backslash at end of input (dash, bash 5). Bash 3.2 drops it."""
    try:
        return subprocess.run(["/bin/sh", "-c", "printf %s \\"], capture_output=True, text=True,
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
        + " --watch-pid $pid --log " + q(log) + " --quiet " + q(quiet) + "; rc=$?; "
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
    """Return {job id: output path or None} for every job with no terminal task notice and no
    TaskStop result."""
    jobs, done, stops = {}, set(), set()
    with open(transcript, "rb") as f:
        for line in f:
            if not any(k in line for k in (b"backgroundTaskId", b"task-notification", b"TaskStop", b"Successfully stopped")):
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
            elif kind == "assistant" and isinstance(content, list):
                stops.update(b["id"] for b in content if isinstance(b, dict)
                             and b.get("type") == "tool_use" and b.get("name") == "TaskStop"
                             and isinstance(b.get("id"), str))
            elif kind == "user":
                done.update(closed_by_notice(text))
                if isinstance(content, list):  # only the result of a TaskStop call of this session
                    for b in content:
                        if isinstance(b, dict) and b.get("type") == "tool_result" and isinstance(b.get("tool_use_id"), str) and b["tool_use_id"] in stops:
                            done.update(stopped_ids(b.get("content")))
    return {k: v for k, v in jobs.items() if k not in done}


def closed_by_notice(text):
    """The ids of the <task-notification> blocks in text with a terminal status."""
    ids = []
    for note in text.split("<task-notification>")[1:]:
        tid, st = TASK_ID.search(note), TASK_STATUS.search(note)
        if tid and st and st.group(1).strip() in TERMINAL:
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
    try:
        call = json.load(sys.stdin)
        if call.get("stop_hook_active") is True:
            return 0
        now = float(os.environ.get("STALL_WATCH_NOW") or time.time())
        quiet = float(os.environ.get("STALL_WATCH_QUIET") or DEFAULT_QUIET)
        base = os.environ.get("STALL_WATCH_OUTPUT_BASE")
        rows = []
        for job, path in scan_jobs(call["transcript_path"]).items():
            real = path
            if path and base:
                real = os.path.join(base, re.split(r"[\\/]", path)[-1])
            try:
                idle = now - os.stat(real).st_mtime
            except (OSError, TypeError):  # TypeError: no path recorded
                rows.append("%s: unknown, output file not found: %s" % (job, path or "(path not recorded)"))
                continue
            if idle >= quiet:
                rows.append("%s: no output for %ds: %s" % (job, idle, path))
        if rows:
            head = "Background shells still running and quiet: stop it or tell the owner."
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
    for i in range(0, len(argv) - 1, 2):
        if argv[i] in opts:
            opts[argv[i]] = argv[i + 1]
    if not opts["--watch-pid"] or not opts["--log"]:
        print(__doc__)
        return 2
    return watch(int(opts["--watch-pid"]), opts["--log"], float(opts["--quiet"]))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
