#!/usr/bin/env python3
"""Stall watch for background Bash commands. Standard library only.

Wrapper: stall_watch.py [--quiet SECS] [--log PATH] -- <command> [args...]
  Runs the command in its own process group, with its output going to the log file. The wrapper
  passes that output to its own stdout. After --quiet seconds (default 300) with no new output,
  it prints a STALL report and exits 3. The command keeps running, and its output keeps going to
  the log. If the command ends first, the wrapper exits with its code.

Hook: stall_watch.py --hook
  PreToolUse hook. For a Bash call with run_in_background true, it returns updatedInput whose
  command runs the wrapper around the original. Otherwise it prints nothing.
  STALL_WATCH_QUIET overrides the default quiet time (for tests and proofs only).

See decisions/stall-watch.md.
"""
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time

DEFAULT_QUIET = 300
STALL_EXIT = 3
TAIL_LINES = 20


def _run(args, timeout=10):
    try:
        return subprocess.run(args, capture_output=True, text=True, errors="replace",
                              timeout=timeout).stdout
    except Exception as exc:
        return "(%s failed: %s)\n" % (args[0], exc)


def group_rows(pgid):
    """Return [pid, state, elapsed, command] for each process in the group."""
    rows = []
    for line in _run(["ps", "-axo", "pid=,pgid=,stat=,etime=,command="]).splitlines():
        p = line.split(None, 4)
        if len(p) >= 4 and p[1] == str(pgid):
            rows.append([p[0], p[2], p[3], p[4] if len(p) > 4 else ""])
    return rows


def report(proc, pgid, quiet, log):
    rows = group_rows(pgid)
    pids = ",".join(r[0] for r in rows) or str(proc.pid)
    lines = ["STALL: no output for %ss; pid=%d pgid=%d still running" % (quiet, proc.pid, pgid),
             "The command was not stopped. Diagnose it, then stop it yourself if needed.",
             "Processes in the group (pid state elapsed command):"]
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
            tail = f.read().decode("utf-8", "replace").splitlines()[-TAIL_LINES:]
    except OSError:
        tail = []
    lines += ["Last %d output lines:" % TAIL_LINES] + ["  " + l for l in tail or ["(no output)"]]
    lines.append("Log: " + log)
    sys.stdout.write("\n".join(lines) + "\n")
    sys.stdout.flush()


def wrap(quiet, log, cmd):
    if not log:
        fd, log = tempfile.mkstemp(prefix="stall-watch-", suffix=".log")
        os.close(fd)
    with open(log, "ab") as out:
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=out,
                                    stderr=subprocess.STDOUT, start_new_session=True)
        except OSError as exc:
            print("stall_watch: cannot start %s: %s" % (cmd[0], exc))
            return 127
    pgid = proc.pid  # start_new_session makes the child its group leader

    def stop(sig, _frame):  # the task was stopped: stop the command too
        try:
            os.killpg(pgid, signal.SIGTERM)
        except OSError:
            pass
        sys.exit(128 + sig)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    last = time.monotonic()
    with open(log, "rb") as f:
        while True:
            rc = proc.poll()  # read the exit state first, so the read below sees all output
            data = f.read()
            if data:
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()
                last = time.monotonic()
            if rc is not None:
                return rc if rc >= 0 else 128 - rc
            if time.monotonic() - last >= quiet:
                report(proc, pgid, quiet, log)
                return STALL_EXIT
            time.sleep(0.2)


def hook():
    try:
        call = json.load(sys.stdin)
        inp = call["tool_input"]
        if call.get("tool_name") != "Bash" or inp.get("run_in_background") is not True:
            return 0
        original = inp["command"]
    except Exception:
        return 0
    args = [sys.executable, os.path.abspath(__file__)]
    quiet = os.environ.get("STALL_WATCH_QUIET")
    if quiet:
        args += ["--quiet", quiet]
    wrapped = " ".join(shlex.quote(a) for a in args + ["--", "bash", "-c", original])
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "allow",
        "updatedInput": dict(inp, command=wrapped)}}))
    return 0


def main(argv):
    if argv[:1] == ["--hook"]:
        return hook()
    quiet, log = DEFAULT_QUIET, None
    i = 0
    while i + 1 < len(argv) and argv[i] in ("--quiet", "--log"):
        if argv[i] == "--quiet":
            quiet = float(argv[i + 1])
        else:
            log = argv[i + 1]
        i += 2
    if argv[i:i + 1] != ["--"] or len(argv) == i + 1:
        print(__doc__)
        return 2
    return wrap(quiet, log, argv[i + 1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
