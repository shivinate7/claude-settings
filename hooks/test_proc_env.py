#!/usr/bin/env python3
"""Cases for hooks/proc_env.py: the exec-time environment read. Standard library only.

Run it from the repository root:

    python3 hooks/test_proc_env.py

Each case starts its own child (`sleep 30`) with the environment the case names. The two tag names are
removed from the inherited environment first, so a tag the harness set cannot answer for the case. On
Linux a case first reads the child's own /proc environ (the scope): a wrong answer is then the reader's.
Every child is killed at exit.

The entry_value cases name the reader's new API, so on a branch without it they fail with AttributeError.
That is not a red (test-practices P3): the mutant run after the build records them going red.
holds_session_tag is the one existing reader; its case is a green control.
"""
import atexit
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from case_runner_test import Skip, run_cases  # noqa: E402  the one case runner (hooks/case_runner_test.py)
import proc_env  # noqa: E402  the one home of the exec-time read (hooks/proc_env.py)

SESSION_TAG = "CLAUDE_CODE_SESSION_ID"
AGENT_TAG = "CLAUDE_AGENT_ID"
AGENT_ID = "3f9c1e7a0b2d4e6f8"
SESSION_ID = "sess-abc123"
CASES = []
CHILDREN = []


def case(fn):
    CASES.append(fn)
    return fn


def expect(ok, msg):
    return [] if ok else [msg]


def supported():
    return sys.platform.startswith("linux") or sys.platform == "darwin"


READY = "import os, time; os.write(1, b'ready'); time.sleep(30)"


def spawn(extra=None, extra_argv=()):
    """A child that sleeps, with the two tag names removed from the inherited environment, then `extra` added.
    The child writes `ready` once it runs. A read of its /proc record straight after Popen can still see the
    parent's record (the exec is not done), so a case waits for `ready` first: a wait on a pipe, not a sleep."""
    env = {k: v for k, v in os.environ.items() if k not in (SESSION_TAG, AGENT_TAG)}
    env.update(extra or {})
    child = subprocess.Popen([sys.executable, "-c", READY, *extra_argv], env=env, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    CHILDREN.append(child)
    if child.stdout.read(5) != b"ready":
        raise RuntimeError("child did not report ready")
    return child


def raw_entries(pid, source="environ"):
    with open("/proc/%d/%s" % (pid, source), "rb") as f:
        return f.read().split(b"\0")


def scope_problems(child, entry, source="environ"):
    """Scope first (P7): the child's own /proc record holds the entry. Off Linux there is no such read."""
    if not sys.platform.startswith("linux"):
        return []
    return expect(entry.encode() in raw_entries(child.pid, source),
                  "scope: the child's own %s does not hold %s" % (source, entry))


def _cleanup():
    for child in CHILDREN:
        try:
            child.kill()
            child.wait()
        except OSError:
            pass


atexit.register(_cleanup)


@case
def whole_entry_value_is_read():
    """E1. entry_value gives the value of the whole CLAUDE_AGENT_ID entry of a live child"""
    if not supported():
        raise Skip("entry_value reads Linux and macOS only")
    child = spawn({AGENT_TAG: AGENT_ID})
    problems = scope_problems(child, AGENT_TAG + "=" + AGENT_ID)
    if problems:
        return problems
    got = proc_env.entry_value(child.pid, AGENT_TAG)
    return expect(got == AGENT_ID, f"entry_value gives {got!r}, want {AGENT_ID!r}")


@case
def value_keeps_later_equals_signs():
    """E2. the value is everything after the first `=`: CLAUDE_AGENT_ID=a=b=c gives a=b=c"""
    if not supported():
        raise Skip("entry_value reads Linux and macOS only")
    child = spawn({AGENT_TAG: "a=b=c"})
    problems = scope_problems(child, AGENT_TAG + "=a=b=c")
    if problems:
        return problems
    got = proc_env.entry_value(child.pid, AGENT_TAG)
    return expect(got == "a=b=c", f"entry_value gives {got!r}, want 'a=b=c'")


@case
def empty_value_is_empty_string_not_none():
    """E3. CLAUDE_AGENT_ID= (an empty value) gives the empty string; None means no entry"""
    if not supported():
        raise Skip("entry_value reads Linux and macOS only")
    child = spawn({AGENT_TAG: ""})
    problems = scope_problems(child, AGENT_TAG + "=")
    if problems:
        return problems
    got = proc_env.entry_value(child.pid, AGENT_TAG)
    return expect(got == "", f"entry_value gives {got!r}, want ''")


@case
def absent_name_is_none():
    """E4. a child that holds only the session tag: entry_value for the agent name gives None"""
    if not supported():
        raise Skip("entry_value reads Linux and macOS only")
    child = spawn({SESSION_TAG: SESSION_ID})
    problems = scope_problems(child, SESSION_TAG + "=" + SESSION_ID)
    if problems:
        return problems
    got = proc_env.entry_value(child.pid, AGENT_TAG)
    return expect(got is None, f"entry_value gives {got!r} for a missing name, want None")


@case
def near_miss_names_are_none():
    """E5. whole-entry match: CLAUDE_AGENT_ID_X, XCLAUDE_AGENT_ID and CLAUDE_AGENT_IDX do not match the name"""
    if not supported():
        raise Skip("entry_value reads Linux and macOS only")
    near = {AGENT_TAG + "_X": AGENT_ID, "X" + AGENT_TAG: AGENT_ID, AGENT_TAG + "X": AGENT_ID}
    child = spawn(near)
    problems = scope_problems(child, AGENT_TAG + "_X=" + AGENT_ID)
    if problems:
        return problems
    got = proc_env.entry_value(child.pid, AGENT_TAG)
    return expect(got is None, f"entry_value gives {got!r} from a near-miss name, want None")


@case
def argv_is_not_environment():
    """E6. CLAUDE_AGENT_ID=<id> in argv, not in the environment: entry_value gives None"""
    if not supported():
        raise Skip("entry_value reads Linux and macOS only")
    child = spawn(extra_argv=(AGENT_TAG + "=" + AGENT_ID,))
    problems = []
    if sys.platform.startswith("linux"):
        problems += scope_problems(child, AGENT_TAG + "=" + AGENT_ID, source="cmdline")
        problems += expect(not any(e.startswith(AGENT_TAG.encode()) for e in raw_entries(child.pid)),
                           "scope: the child's environ holds the tag, so the argv case proves nothing")
    if problems:
        return problems
    got = proc_env.entry_value(child.pid, AGENT_TAG)
    return expect(got is None, f"entry_value gives {got!r} from argv, want None")


@case
def bad_pids_are_none():
    """E7. a pid that is 0, 1 or below, a bool, a string, a float or None: entry_value gives None for each"""
    if not supported():
        raise Skip("entry_value reads Linux and macOS only")
    problems = []
    for pid in (0, 1, -1, True, "123", 1.5, None):
        got = proc_env.entry_value(pid, AGENT_TAG)
        problems += expect(got is None, f"entry_value({pid!r}) gives {got!r}, want None")
    return problems


@case
def dead_pid_is_none():
    """E8. a child that has exited and been reaped: entry_value gives None"""
    if not supported():
        raise Skip("entry_value reads Linux and macOS only")
    child = spawn({AGENT_TAG: AGENT_ID})
    child.kill()
    child.wait()
    problems = expect(child.returncode is not None, "scope: the child was not reaped")
    if problems:
        return problems
    got = proc_env.entry_value(child.pid, AGENT_TAG)
    return expect(got is None, f"entry_value gives {got!r} for a dead pid, want None")


@case
def other_platform_is_none():
    """E9. on a platform the read does not cover (win32 here, patched), entry_value gives None for a live child"""
    child = spawn({AGENT_TAG: AGENT_ID})
    saved = sys.platform
    sys.platform = "win32"
    try:
        got = proc_env.entry_value(child.pid, AGENT_TAG)
    finally:
        sys.platform = saved
    return expect(got is None, f"entry_value gives {got!r} on win32, want None")


@case
def name_is_the_pinned_constant():
    """E10. the agent marker name is CLAUDE_AGENT_ID, pinned as AGENT_TAG_NAME"""
    got = proc_env.AGENT_TAG_NAME
    return expect(got == AGENT_TAG, f"AGENT_TAG_NAME is {got!r}, want {AGENT_TAG!r}")


@case
def entry_value_takes_the_name_as_a_parameter():
    """E11. entry_value reads whichever name it is given: the session tag gives the session id"""
    if not supported():
        raise Skip("entry_value reads Linux and macOS only")
    child = spawn({SESSION_TAG: SESSION_ID})
    problems = scope_problems(child, SESSION_TAG + "=" + SESSION_ID)
    if problems:
        return problems
    got = proc_env.entry_value(child.pid, SESSION_TAG)
    return expect(got == SESSION_ID, f"entry_value gives {got!r} for the session tag, want {SESSION_ID!r}")


@case
def holds_session_tag_keeps_its_behaviour():
    """E12. green control: holds_session_tag matches the whole session entry only, as before"""
    child = spawn({SESSION_TAG: SESSION_ID})
    if not supported():
        if proc_env.holds_session_tag(child.pid, SESSION_ID):
            return ["holds_session_tag is True on an unsupported platform"]
        return []
    problems = scope_problems(child, SESSION_TAG + "=" + SESSION_ID)
    if problems:
        return problems
    problems += expect(proc_env.holds_session_tag(child.pid, SESSION_ID) is True,
                       "holds_session_tag is not True for the whole entry")
    for wrong in ("sess-abc12", "sess-abc1234", "x=" + SESSION_ID, "", None):
        problems += expect(proc_env.holds_session_tag(child.pid, wrong) is False,
                           f"holds_session_tag is True for {wrong!r}")
    return problems


if __name__ == "__main__":
    sys.exit(run_cases(CASES))
