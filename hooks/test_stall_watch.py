#!/usr/bin/env python3
"""Cases for hooks/stall_watch.py. Standard library only, and no test runner.

Run it from the repository root:

    python3 hooks/test_stall_watch.py

Each case runs the real module as a subprocess, the way Claude Code runs it. No case imports it.
Scratch files live in one temp directory, removed at exit. Every process group a report names is
killed at exit, and never the test's own group.

Interface the module must match (the test is the contract; the module follows it):
- Wrapper: `python3 hooks/stall_watch.py [--quiet SECS] [--log PATH] -- <command> [args...]`.
  Default --quiet is 300. `--log PATH` names the log file. The command runs in its own process
  group, with its output going to the log file. The wrapper passes that output to its own stdout.
- Stall: after --quiet seconds with no output, the wrapper prints one report and exits 3. The
  report starts with `STALL:` on its first line. It names `pid=<n>` and `pgid=<n>`, one line per
  process in the group with state and elapsed time, the open files whose paths contain "lock"
  (lsof, when present), the network connections (lsof -i, when present), the last 20 output
  lines, and the log path. The command keeps running, detached, and its output continues to the log.
- Exit first: if the command exits before a stall, the wrapper exits with the command's code and
  prints no report.
- Hook: `python3 hooks/stall_watch.py --hook` reads one PreToolUse payload on stdin. For a Bash
  call with tool_input.run_in_background true, it prints one JSON object whose
  hookSpecificOutput.updatedInput.command runs the wrapper around the original command. The other
  tool_input fields are kept. For any other input it prints nothing.

The wrapper's stdout is a file in these tests, not a pipe, so a detached child that holds the
descriptor never blocks a case.
"""

import atexit
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE = os.path.join(HERE, "stall_watch.py")
PY = sys.executable
SCRATCH = tempfile.mkdtemp(prefix="test-stall-watch-")
OWN_PGID = os.getpgid(0)
GROUPS = set()
PIDS = set()
CASES = []

# The original command for case 6. It has double quotes, single quotes and `$` in it.
ORIG_QUOTING = r'''printf '%s\n' "it's" 'x$HOME' "$((1+2))"'''
QUOTING_WANT = "it's\nx$HOME\n3\n"


class Skip(Exception):
    pass


def case(fn):
    CASES.append(fn)
    return fn


def expect(ok, msg):
    return [] if ok else [msg]


def new_dir():
    return tempfile.mkdtemp(dir=SCRATCH)


def remember(text):
    for m in re.finditer(r"\bpgid=(\d+)", text):
        GROUPS.add(int(m.group(1)))
    for m in re.finditer(r"\bpid=(\d+)", text):
        PIDS.add(int(m.group(1)))


def reap():
    """Kill the process groups and pids that reports named, then forget them."""
    for pg in list(GROUPS):
        if pg > 0 and pg != OWN_PGID:
            try:
                os.killpg(pg, signal.SIGKILL)
            except OSError:
                pass
    for pid in list(PIDS):
        try:
            if os.getpgid(pid) in GROUPS:
                os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    GROUPS.clear()
    PIDS.clear()


def _cleanup():
    reap()
    shutil.rmtree(SCRATCH, ignore_errors=True)


atexit.register(_cleanup)


def pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def run_wrapper(args, timeout):
    """Run the wrapper with stdout in a file. Return (exit code or None, text, seconds)."""
    if not os.path.isfile(MODULE):
        raise RuntimeError("hooks/stall_watch.py is missing")
    out_path = os.path.join(new_dir(), "wrapper.out")
    start = time.monotonic()
    with open(out_path, "wb") as out:
        proc = subprocess.Popen(
            [PY, MODULE, *args],
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=subprocess.STDOUT,
        )
        try:
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            rc = None
    secs = time.monotonic() - start
    with open(out_path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    remember(text)
    return rc, text, secs


def run_hook(payload):
    if not os.path.isfile(MODULE):
        raise RuntimeError("hooks/stall_watch.py is missing")
    proc = subprocess.run(
        [PY, MODULE, "--hook"],
        input=json.dumps(payload).encode("utf-8"),
        capture_output=True,
        timeout=20,
    )
    return proc.returncode, proc.stdout.decode("utf-8", "replace"), proc.stderr.decode("utf-8", "replace")


@case
def stall_reports_and_exits_3():
    """1. sleep 30, no output: STALL within about 4 s, exit 3, sleep still alive"""
    log = os.path.join(new_dir(), "run.log")
    rc, out, secs = run_wrapper(["--quiet", "2", "--log", log, "--", "sleep", "30"], timeout=20)
    problems = expect(rc == 3, f"exit code {rc}, want 3")
    problems += expect(out.startswith("STALL:"), "report does not start with STALL:")
    problems += expect(secs <= 5.0, f"wrapper ran {secs:.1f}s, want about 4s")
    problems += expect(os.path.basename(log) in out, "report does not name the log path")
    pid_m = re.search(r"\bpid=(\d+)", out)
    pgid_m = re.search(r"\bpgid=(\d+)", out)
    if not pid_m or not pgid_m:
        problems.append("report lacks pid= or pgid=")
    else:
        pid = int(pid_m.group(1))
        problems += expect(pid_alive(pid), "sleep process is not alive after the wrapper exited")
        comm = subprocess.run(["ps", "-o", "comm=", "-p", str(pid)], capture_output=True, text=True).stdout
        problems += expect("sleep" in comm, f"pid {pid} is {comm.strip()!r}, want sleep")
    reap()
    return problems


@case
def chatty_command_no_stall():
    """2. prints every second for 5 s, then exits 0: no STALL, exit 0"""
    log = os.path.join(new_dir(), "run.log")
    cmd = [PY, "-c", "import time\nfor i in range(5):\n    print(i, flush=True)\n    time.sleep(1)"]
    rc, out, secs = run_wrapper(["--quiet", "2", "--log", log, "--", *cmd], timeout=30)
    problems = expect(rc == 0, f"exit code {rc}, want 0")
    problems += expect("STALL:" not in out, "a STALL report was printed for a chatty command")
    problems += expect(secs >= 3.5, f"command ended after {secs:.1f}s, want about 5s")
    reap()
    return problems


@case
def fast_exit_passes_code():
    """3. command exits 7 fast: wrapper exits 7, no STALL"""
    log = os.path.join(new_dir(), "run.log")
    rc, out, secs = run_wrapper(["--quiet", "2", "--log", log, "--", "/bin/sh", "-c", "exit 7"], timeout=20)
    problems = expect(rc == 7, f"exit code {rc}, want 7")
    problems += expect("STALL:" not in out, "a STALL report was printed for a fast exit")
    reap()
    return problems


@case
def output_reaches_log_after_wrapper_exits():
    """4. after a stall exit, the command's later output still reaches the log"""
    log = os.path.join(new_dir(), "run.log")
    cmd = ["/bin/sh", "-c", "echo first; sleep 4; echo second"]
    rc, out, _secs = run_wrapper(["--quiet", "2", "--log", log, "--", *cmd], timeout=15)
    problems = expect(rc == 3, f"exit code {rc}, want 3 (the 4 s gap is a stall)")
    deadline = time.monotonic() + 15
    text = ""
    while time.monotonic() < deadline:
        if os.path.exists(log):
            with open(log, encoding="utf-8", errors="replace") as f:
                text = f.read()
            if "second" in text:
                break
        time.sleep(0.2)
    problems += expect("first" in text, "log lacks the output printed before the stall")
    problems += expect("second" in text, "log lacks output printed after the wrapper exited")
    reap()
    return problems


@case
def stall_report_lists_lock_path():
    """5. a child holding a file under a *lock* path: the report lists that path"""
    if shutil.which("lsof") is None:
        raise Skip("lsof is not installed")
    d = new_dir()
    lock = os.path.join(d, "playwright-install.lock")
    log = os.path.join(d, "run.log")
    cmd = [
        PY,
        "-c",
        "import sys, time\nf = open(sys.argv[1], 'w')\nprint('held', flush=True)\ntime.sleep(30)",
        lock,
    ]
    rc, out, _secs = run_wrapper(["--quiet", "2", "--log", log, "--", *cmd], timeout=20)
    problems = expect(rc == 3 and out.startswith("STALL:"), f"exit {rc}, want a STALL report and exit 3")
    problems += expect(os.path.realpath(lock) in out, "report does not list the lock path held open")
    reap()
    return problems


@case
def hook_wraps_background_bash():
    """6a. hook: run_in_background true returns updatedInput; the command runs the wrapper"""
    payload = {
        "session_id": "test-stall-watch",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": ORIG_QUOTING, "description": "quoting", "run_in_background": True},
    }
    rc, out, err = run_hook(payload)
    problems = expect(rc == 0, f"hook exit {rc}, want 0: {err.strip()[:200]}")
    try:
        obj = json.loads(out)
    except ValueError:
        return problems + ["hook stdout is not one JSON object"]
    hso = obj.get("hookSpecificOutput", {})
    problems += expect(hso.get("hookEventName") == "PreToolUse", "hookEventName is not PreToolUse")
    problems += expect(hso.get("permissionDecision", "allow") == "allow", "permissionDecision is not allow")
    ui = hso.get("updatedInput")
    if not isinstance(ui, dict):
        return problems + ["no hookSpecificOutput.updatedInput"]
    cmd = ui.get("command", "")
    problems += expect("stall_watch" in cmd, "updated command does not run stall_watch")
    problems += expect(ui.get("description") == "quoting", "other tool_input fields were dropped")
    run = subprocess.run(
        ["/bin/sh", "-c", cmd], stdin=subprocess.DEVNULL, capture_output=True, timeout=30
    )
    got = run.stdout.decode("utf-8", "replace")
    problems += expect(run.returncode == 0, f"wrapped command exit {run.returncode}, want 0")
    problems += expect(got == QUOTING_WANT, f"wrapped output {got!r}, want {QUOTING_WANT!r}")
    return problems


@case
def hook_leaves_foreground_bash_alone():
    """6b. hook: run_in_background false does nothing"""
    payload = {
        "session_id": "test-stall-watch",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": ORIG_QUOTING, "run_in_background": False},
    }
    rc, out, err = run_hook(payload)
    problems = expect(rc == 0, f"hook exit {rc}, want 0: {err.strip()[:200]}")
    if out.strip():
        try:
            obj = json.loads(out)
        except ValueError:
            return problems + ["hook printed output that is not JSON"]
        problems += expect("updatedInput" not in obj.get("hookSpecificOutput", {}),
                           "hook rewrote a foreground call")
    return problems


def main():
    failed = skipped = 0
    for fn in CASES:
        name = (fn.__doc__ or fn.__name__).strip()
        try:
            problems = fn()
        except Skip as s:
            skipped += 1
            print(f"SKIP {name}: {s}")
            continue
        except Exception as e:  # a missing module or a crash is a failed case, not a stop
            problems = [str(e)]
        if problems:
            failed += 1
            print(f"FAIL {name}")
            for p in problems:
                print(f"  - {p}")
        else:
            print(f"PASS {name}")
    print(f"{len(CASES)} cases, {failed} failed, {skipped} skipped")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
