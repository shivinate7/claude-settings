#!/usr/bin/env python3
"""Stall watch for background Bash commands. Standard library only.

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

See decisions/stall-watch.md.
"""
import json
import os
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
    # A trailing `\` joins the next line. sh and bash drop it at the end of a command, and zsh
    # reads it as an empty word. The blank line keeps `}` apart; the empty word below is
    # expanded by zsh only, so each shell runs the original as it would bare.
    tail = "\n${ZSH_VERSION:+''}" if len(original) - len(original.rstrip("\\")) & 1 else ""
    wrapped = (
        "{ " + original + tail + "\n\n} > " + q(log) + " 2>&1 & pid=$!; "
        + " ".join(q(a) for a in [sys.executable, os.path.abspath(__file__)])
        + " --watch-pid $pid --log " + q(log) + " --quiet " + q(quiet) + "; rc=$?; "
        + "[ $rc -eq 3 ] && exit 3; wait $pid; rc=$?; rm -f " + q(log) + "; exit $rc"
    )
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "updatedInput": dict(inp, command=wrapped)}}))
    return 0


def main(argv):
    if argv[:1] == ["--hook"]:
        return hook()
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
