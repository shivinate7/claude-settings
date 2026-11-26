#!/usr/bin/env python3
"""Cases for the kill guard when the session-tag read is unreadable (hooks/guard_kill.py, foreign_pid_kill).
Standard library only. Run from the repository root:

    python3 hooks/test_guard_kill.py

Each case runs hooks/guard.py as a child on a PreToolUse payload `kill <pid>`. The pid is a process this file
detaches, so init adopts it (PPID 1). In the child, `guard_kill.holds_session_tag` is replaced by a driver with the
case's answer: True (held), False (absent) or None (unreadable). The replacement is on the name the kill verdict
calls, so it does not depend on the platform. The child reads its config from an isolated folder
(lint/_test_temp.py isolated_config), so its guard.log never lands in the real ~/.claude.
Every detached process is killed at exit.
"""
import atexit
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "lint"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)
from case_runner_test import Skip, run_cases  # noqa: E402  the one case runner (hooks/case_runner_test.py)

RUN_FOLDER = _test_temp.run_folder()
GUARD = os.path.join(HERE, "guard.py")
TAG = "CLAUDE_CODE_SESSION_ID"
AGENT = "CLAUDE_AGENT_ID"
SESSION_ID = "guard-kill-unknown-session"
SLEEPER = [sys.executable, "-c", "import time; time.sleep(60)"]
DRIVER = ("import runpy, sys\nsys.path.insert(0, %r)\nimport guard_kill\n"
          "guard_kill.holds_session_tag = lambda pid, session_id: %r\n"
          "runpy.run_path(%r, run_name='__main__')\n")
CASES = []
CHILDREN = []


def case(fn):
    CASES.append(fn)
    return fn


def expect(ok, msg):
    return [] if ok else [msg]


def _cleanup():
    for pid in CHILDREN:
        try:
            os.kill(pid, 9)
        except OSError:
            pass


atexit.register(_cleanup)


def posix_only():
    if sys.platform == "win32":
        raise Skip("the kill guard's pid walk is POSIX")


def detached_job():
    """A python sleeper that init adopts (PPID 1). Skip when this host does not reparent a detached job to init."""
    script = '"$@" </dev/null >/dev/null 2>&1 & echo $!'
    answer = subprocess.run(["sh", "-c", script, "sh"] + SLEEPER, capture_output=True, text=True, timeout=20)
    pid = int(answer.stdout.strip())
    CHILDREN.append(pid)
    parent = subprocess.run(["ps", "-o", "ppid=", "-p", str(pid)], capture_output=True, text=True,
                            timeout=10).stdout.strip()
    if parent != "1":
        raise Skip("this host does not reparent a detached job to init")
    return pid


def guard_stdout(pid, answer):
    """The guard's stdout for `kill <pid>` when its session-tag read answers `answer`. Empty when it allows the call."""
    payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                          "tool_input": {"command": "kill %d" % pid}, "session_id": SESSION_ID})
    driver = DRIVER % (os.path.abspath(HERE), answer, os.path.abspath(GUARD))
    with _test_temp.isolated_config(RUN_FOLDER):
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("GUARD_", "MUTATE_ONLY")) and k not in (TAG, AGENT)}
        env["CLAUDE_GUARD_ROOT_PID"] = str(os.getpid())   # this test is the session root: the pid is not its descendant
        done = subprocess.run([sys.executable, "-c", driver], input=payload, capture_output=True, text=True,
                              env=env, timeout=120)
    return done.stdout


def decision(out):
    """(permissionDecision, reason) of the guard's last output line; (None, "") when it printed nothing."""
    lines = [line for line in out.splitlines() if line.strip()]
    if not lines:
        return None, ""
    try:
        hook = json.loads(lines[-1]).get("hookSpecificOutput", {})
    except ValueError:
        return "unparsed", lines[-1][:160]
    return hook.get("permissionDecision"), hook.get("permissionDecisionReason", "")


@case
def unreadable_tag_still_refuses_and_says_unknown():
    """K1. the session-tag read cannot run for a PPID-1 pid: the kill guard still denies, and its reason says
    unknown, not that this session did not start the process"""
    posix_only()
    pid = detached_job()
    kind, reason = decision(guard_stdout(pid, None))
    problems = expect(kind == "deny", f"kill guard gives {kind!r} for an unreadable tag, want deny: {reason[:160]!r}")
    if problems:
        return problems
    return expect(re.search(r"(?i)\bunknown\b", reason) is not None and "did not start" not in reason,
                  f"reason for an unreadable tag must say unknown, not that this session did not start it: {reason[:160]!r}")


@case
def absent_tag_is_refused_as_not_started_here():
    """K2. green control: a PPID-1 pid whose tag read answers absent is refused with the not-started reason"""
    posix_only()
    pid = detached_job()
    kind, reason = decision(guard_stdout(pid, False))
    problems = expect(kind == "deny", f"kill guard gives {kind!r} for an absent tag, want deny")
    return problems + expect("did not start" in reason, f"reason for an absent tag is not the not-started text: {reason[:160]!r}")


@case
def held_tag_lets_the_kill_through():
    """K3. green control: a PPID-1 pid whose tag read answers held is allowed: the guard gives no deny"""
    posix_only()
    pid = detached_job()
    kind, reason = decision(guard_stdout(pid, True))
    return expect(kind != "deny", f"kill guard denies a pid whose tag is held: {reason[:160]!r}")


if __name__ == "__main__":
    code = run_cases(CASES)
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)   # test-temp-standard: teardown removes the run folder
    sys.exit(code)
