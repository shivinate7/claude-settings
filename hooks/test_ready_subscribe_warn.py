#!/usr/bin/env python3
"""Cases for hooks/ready_subscribe_warn.py, a warn-only PreToolUse hook. Standard library only.

Run it from the repository root:

    python3 hooks/test_ready_subscribe_warn.py

The hook sees the GitHub MCP update call. A call with `draft` false marks a PR ready. When the session's
transcript holds no `mcp__claude-code-remote__subscribe_pr_activity` call for that owner, repo and
pullNumber, the hook prints one warning and exits 0. A later `unsubscribe_pr_activity` for that PR cancels
an earlier subscribe. The hook never refuses: its warning carries no permissionDecision.

Contract, as the cases pin it:
- Warning: stdout is one JSON object, {"hookSpecificOutput": {"hookEventName": "PreToolUse",
  "additionalContext": <text naming subscribe_pr_activity>}}, and exit 0.
- Silent: stdout empty and exit 0 for a call whose draft is absent or true, any other tool, empty or junk
  stdin, no transcript_path, or a transcript_path that cannot be read. A call that is not a ready mark
  reads no transcript.
- The transcript is read with lint/_transcript.py (read_transcript, tool_uses). A call in an isSidechain
  record counts. A call in an api-request-blob record does not.
- Cost: one read of the transcript per ready mark. No subprocess, no file opened for writing, no timer.

A warning case is a red on a commit without the hook: it fails on the missing warning. A silent case is the
green control beside it: it passes wherever the hook stays silent. The hook file runs as a subprocess, the
way Claude Code runs it. The silent-no-read and cost cases run the same file in this process, with its
file opens, subprocess calls, timers and sleeps recorded.
"""
import builtins
import io
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lint"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
from _transcript import read_transcript, tool_uses  # noqa: E402  the one transcript reader (lint/_transcript.py)
from case_runner_test import run_cases  # noqa: E402  the one case runner (hooks/case_runner_test.py)

HOOK = os.path.join(HERE, "ready_subscribe_warn.py")
READY_TOOL = "mcp__github__update_pull_request"
SUBSCRIBE = "mcp__claude-code-remote__subscribe_pr_activity"
UNSUBSCRIBE = "mcp__claude-code-remote__unsubscribe_pr_activity"
OWNER, REPO, PR = "octo-org", "app", 12
ABSENT = object()  # mcp_input leaves draft out of the call when this is passed
TIMEOUT = 60  # a safety bound on one hook process; no case asserts on a time
FILLER = 300  # records of about 1 KB each: more than the reader's 256 KB chunk
SUBPROCESS_CALLS = ("run", "Popen", "call", "check_call", "check_output")
WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
# "subscribe_pr_activity" inside "unsubscribe_pr_activity" is not a subscribe name.
SUBSCRIBE_NAME = re.compile(r"(?<!un)subscribe_pr_activity")
RUN = _test_temp.run_folder()
_IDS = itertools.count(1)
real_open, real_os_open = builtins.open, os.open


class Counts:
    """What one in-process run did beyond its output."""

    def __init__(self):
        self.reads = 0       # opens of the transcript path
        self.writes = []     # paths opened for writing
        self.subprocess = []  # subprocess calls that were refused
        self.timers = []     # threading.Timer constructions that were refused
        self.sleeps = []     # time.sleep calls


class Run:
    """One hook run. ran is False when the hook file is absent: nothing ran, so nothing was read or written."""

    def __init__(self, ran, rc, out, err, counts=None):
        self.ran, self.rc, self.out, self.err = ran, rc, out, err
        self.counts = counts or Counts()


def new_case_folder():
    return tempfile.mkdtemp(prefix="case-", dir=RUN)


def call(name, tool_input, sidechain=False, blob=False):
    """One transcript record that holds one tool call, shaped as the transcript writes it."""
    rec = {"type": "api-request-blob" if blob else "assistant",
           "message": {"role": "assistant", "content": [
               {"type": "tool_use", "id": "toolu_%d" % next(_IDS), "name": name, "input": tool_input}]}}
    if sidechain:
        rec["isSidechain"] = True
    return rec


def pr_input(pull=PR, owner=OWNER, repo=REPO):
    return {"owner": owner, "repo": repo, "pullNumber": pull}


def subscribe(pull=PR, owner=OWNER, repo=REPO, **kw):
    return call(SUBSCRIBE, pr_input(pull, owner, repo), **kw)


def unsubscribe(pull=PR, owner=OWNER, repo=REPO):
    return call(UNSUBSCRIBE, pr_input(pull, owner, repo))


def filler(n):
    """Plain user records, for bulk: a transcript this size passes the reader's chunk."""
    return [{"type": "user", "message": {"role": "user", "content": "x" * 1000}} for _ in range(n)]


def write_transcript(records):
    """A transcript file in a new case folder. A str item is written as a raw line, not as JSON."""
    path = os.path.join(new_case_folder(), "transcript.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write((rec if isinstance(rec, str) else json.dumps(rec)) + "\n")
    return path


def mcp_input(pull=PR, draft=False):
    args = pr_input(pull)
    if draft is not ABSENT:
        args["draft"] = draft
    return args


def hook_json(tool_input, transcript, tool=READY_TOOL):
    """The PreToolUse payload Claude Code sends. transcript None leaves transcript_path out."""
    data = {"session_id": "session-1", "hook_event_name": "PreToolUse", "tool_name": tool,
            "tool_input": tool_input, "tool_use_id": "toolu_ready", "cwd": RUN}
    if transcript is not None:
        data["transcript_path"] = transcript
    return json.dumps(data)


def run_hook(data):
    """Run the hook file as a subprocess, with the payload on stdin, as Claude Code runs it.
    With no hook file, nothing runs: ran is False and the output is empty."""
    if not os.path.isfile(HOOK):
        return Run(False, None, "", "")
    proc = subprocess.run([sys.executable, HOOK], input=data.encode("utf-8"), cwd=RUN,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=TIMEOUT)
    return Run(True, proc.returncode, proc.stdout.decode("utf-8", "replace"),
               proc.stderr.decode("utf-8", "replace"))


def run_in_process(data, transcript):
    """Run the hook file's own __main__ in this process. Its stdin and stdout are strings. Its file opens are
    counted, and a subprocess call or a timer is refused, so no process starts. A sleep is counted and returns."""
    if not os.path.isfile(HOOK):
        return Run(False, None, "", "")
    with open(HOOK, encoding="utf-8") as f:
        code = compile(f.read(), HOOK, "exec")
    counts = Counts()
    target = os.path.abspath(transcript) if transcript else None

    def spy_open(file, mode="r", *args, **kwargs):
        if isinstance(file, (str, bytes, os.PathLike)):
            path = os.path.abspath(os.fsdecode(file))
            if path == target:
                counts.reads += 1
            if isinstance(mode, str) and any(c in mode for c in "wax+"):
                counts.writes.append(path)
        return real_open(file, mode, *args, **kwargs)

    def spy_os_open(path, flags, *args, **kwargs):
        if flags & WRITE_FLAGS and "__pycache__" not in str(path):
            counts.writes.append(os.path.abspath(os.fsdecode(path)))
        return real_os_open(path, flags, *args, **kwargs)

    def refuse(name):
        def stop(*args, **kwargs):
            counts.subprocess.append(name)
            raise RuntimeError("the test refuses %s" % name)
        return stop

    class SpyTimer:
        def __init__(self, *args, **kwargs):
            counts.timers.append(args[:1])
            raise RuntimeError("the test refuses threading.Timer")

    def spy_sleep(seconds):
        counts.sleeps.append(seconds)

    saved_sub = {name: getattr(subprocess, name) for name in SUBPROCESS_CALLS}
    saved = (builtins.open, io.open, os.open, os.system, threading.Timer, time.sleep,
             sys.stdin, sys.stdout, sys.stderr)
    builtins.open, io.open, os.open = spy_open, spy_open, spy_os_open
    os.system = refuse("os.system")
    threading.Timer = SpyTimer
    time.sleep = spy_sleep
    for name in SUBPROCESS_CALLS:
        setattr(subprocess, name, refuse("subprocess." + name))
    sys.stdin = io.StringIO(data)
    out, err = io.StringIO(), io.StringIO()
    sys.stdout, sys.stderr = out, err
    rc = 0
    try:
        exec(code, {"__name__": "__main__", "__file__": HOOK})
    except SystemExit as stop:
        rc = stop.code if isinstance(stop.code, int) else (0 if stop.code is None else 1)
    except BaseException:
        rc = 1
        err.write(traceback.format_exc())
    finally:
        (builtins.open, io.open, os.open, os.system, threading.Timer, time.sleep,
         sys.stdin, sys.stdout, sys.stderr) = saved
        for name, fn in saved_sub.items():
            setattr(subprocess, name, fn)
    return Run(True, rc, out.getvalue(), err.getvalue(), counts)


def calls_named(path, name):
    """The inputs of each call named `name` that the shared reader yields, in order. A case reads these first:
    the fixture's scope is checked before the hook's answer on it is."""
    found = []
    for rec in read_transcript(path):
        for use in tool_uses(rec):
            if use.get("name") == name:
                found.append(use.get("input"))
    return found


def premise(path, name, want):
    """A problem when the shared reader does not yield `want` for `name` in this fixture, else None."""
    got = calls_named(path, name)
    if got != want:
        return "fixture premise: the shared reader yields %r for %s, not %r" % (got, name, want)
    return None


def exit_problem(run):
    if run.ran and run.rc != 0:
        return "exit %s, not 0" % run.rc
    return None


def expect_warning(run):
    """A problem when the run does not print the subscribe warning, else None."""
    if run.out.strip() == "":
        return "no warning on stdout for a ready mark with no subscribe_pr_activity call before it"
    try:
        obj = json.loads(run.out)
    except ValueError:
        return "stdout is not one JSON object: %s" % run.out.strip()[:120]
    hso = obj.get("hookSpecificOutput") if isinstance(obj, dict) else None
    if not isinstance(hso, dict):
        return "stdout JSON has no hookSpecificOutput object"
    if hso.get("hookEventName") != "PreToolUse":
        return "hookEventName is %r, not PreToolUse" % hso.get("hookEventName")
    if "permissionDecision" in hso:
        return "the warning sets permissionDecision: the hook warns and never refuses"
    context = hso.get("additionalContext")
    if not isinstance(context, str) or not SUBSCRIBE_NAME.search(context):
        return "additionalContext does not name subscribe_pr_activity"
    return exit_problem(run)


def expect_silence(run):
    """A problem when the run prints anything, raises, or exits non-zero, else None."""
    if run.out.strip() != "":
        return "stdout is not empty where the hook should stay silent: %s" % run.out.strip()[:120]
    if "Traceback" in run.err:
        return "the hook raised instead of failing open"
    return exit_problem(run)


def expect_no_read(run):
    if run.counts.reads:
        return "the transcript was read %d time(s) for a call that is not a ready mark" % run.counts.reads
    return None


def result(*problems):
    return [p for p in problems if p]


def case_ready_mark_with_empty_transcript_warns():
    """A ready mark in an empty transcript prints the subscribe warning."""
    path = write_transcript([])
    return result(expect_warning(run_hook(hook_json(mcp_input(), path))))


def case_ready_mark_after_other_calls_warns():
    """A ready mark after unrelated calls, with no subscribe, prints the subscribe warning."""
    path = write_transcript([call("Bash", {"command": "ls"}),
                             call("mcp__github__merge_pull_request", pr_input())])
    bad = premise(path, SUBSCRIBE, [])
    if bad:
        return [bad]
    return result(expect_warning(run_hook(hook_json(mcp_input(), path))))


def case_full_size_transcript_without_a_subscribe_warns():
    """A full-size transcript with no subscribe call prints the subscribe warning."""
    path = write_transcript(filler(FILLER) + [call("Bash", {"command": "ls"})])
    bad = premise(path, SUBSCRIBE, [])
    if bad:
        return [bad]
    return result(expect_warning(run_hook(hook_json(mcp_input(), path))))


def case_subscribe_at_the_start_of_a_full_size_transcript_is_silent():
    """A subscribe at the start of a full-size transcript counts, however far back it sits."""
    path = write_transcript([subscribe()] + filler(FILLER))
    bad = premise(path, SUBSCRIBE, [pr_input()])
    if bad:
        return [bad]
    return result(expect_silence(run_hook(hook_json(mcp_input(), path))))


def case_subscribe_for_the_same_pr_is_silent():
    """A subscribe for this owner, repo and PR earlier in the transcript keeps the ready mark silent."""
    path = write_transcript([subscribe()])
    bad = premise(path, SUBSCRIBE, [pr_input()])
    if bad:
        return [bad]
    return result(expect_silence(run_hook(hook_json(mcp_input(), path))))


def case_subscribe_for_another_pr_warns():
    """A subscribe for another PR in the same repo does not count: the ready mark warns."""
    path = write_transcript([subscribe(pull=PR + 1)])
    bad = premise(path, SUBSCRIBE, [pr_input(pull=PR + 1)])
    if bad:
        return [bad]
    return result(expect_warning(run_hook(hook_json(mcp_input(), path))))


def case_subscribe_for_the_same_number_in_another_repo_warns():
    """A subscribe for the same number in another repo does not count: the ready mark warns."""
    path = write_transcript([subscribe(repo="other-app")])
    bad = premise(path, SUBSCRIBE, [pr_input(repo="other-app")])
    if bad:
        return [bad]
    return result(expect_warning(run_hook(hook_json(mcp_input(), path))))


def case_unsubscribe_after_the_subscribe_cancels_it():
    """A later unsubscribe for this PR cancels an earlier subscribe: the ready mark warns."""
    path = write_transcript([subscribe(), unsubscribe()])
    bad = premise(path, SUBSCRIBE, [pr_input()]) or premise(path, UNSUBSCRIBE, [pr_input()])
    if bad:
        return [bad]
    return result(expect_warning(run_hook(hook_json(mcp_input(), path))))


def case_draft_absent_is_silent_and_reads_nothing():
    """An update that sets no draft field is not a ready mark: silent, and no transcript read."""
    path = write_transcript([])
    run = run_in_process(hook_json(mcp_input(draft=ABSENT), path), path)
    return result(expect_silence(run), expect_no_read(run))


def case_draft_true_is_silent_and_reads_nothing():
    """An update with draft true is not a ready mark: silent, and no transcript read."""
    path = write_transcript([])
    run = run_in_process(hook_json(mcp_input(draft=True), path), path)
    return result(expect_silence(run), expect_no_read(run))


def case_other_tool_with_draft_false_is_silent_and_reads_nothing():
    """Another MCP tool, even with draft false in its input, is not the ready route: silent, no transcript read."""
    path = write_transcript([])
    run = run_in_process(hook_json(mcp_input(), path, tool="mcp__github__merge_pull_request"), path)
    return result(expect_silence(run), expect_no_read(run))


def case_bash_gh_pr_ready_is_silent_and_reads_nothing():
    """A Bash call that runs gh pr ready is not this hook's ready route: silent, no transcript read."""
    path = write_transcript([])
    run = run_in_process(hook_json({"command": "gh pr ready 12"}, path, tool="Bash"), path)
    return result(expect_silence(run), expect_no_read(run))


def case_subscribed_session_that_marks_ready_twice_stays_silent():
    """A session that subscribed, then marks the PR ready twice, stays silent both times."""
    path = write_transcript([subscribe()])
    bad = premise(path, SUBSCRIBE, [pr_input()])
    if bad:
        return [bad]
    problems = []
    for n in (1, 2):
        problems += ["ready mark %d: %s" % (n, p) for p in result(expect_silence(
            run_hook(hook_json(mcp_input(), path))))]
    return problems


def case_sidechain_subscribe_counts():
    """A subscribe in an isSidechain record is a call the shared reader yields, so it counts."""
    path = write_transcript([subscribe(sidechain=True)])
    bad = premise(path, SUBSCRIBE, [pr_input()])
    if bad:
        return [bad]
    return result(expect_silence(run_hook(hook_json(mcp_input(), path))))


def case_resumed_blob_copy_of_a_subscribe_does_not_count():
    """A subscribe that sits only in an api-request-blob record is not a call the shared reader yields: warns."""
    path = write_transcript([subscribe(blob=True)])
    bad = premise(path, SUBSCRIBE, [])
    if bad:
        return [bad]
    return result(expect_warning(run_hook(hook_json(mcp_input(), path))))


def case_missing_transcript_path_is_silent():
    """A ready mark with no transcript_path fails open: silent, exit 0."""
    return result(expect_silence(run_hook(hook_json(mcp_input(), None))))


def case_missing_transcript_file_is_silent():
    """A ready mark whose transcript file does not exist fails open: silent, exit 0."""
    path = os.path.join(new_case_folder(), "gone.jsonl")
    return result(expect_silence(run_hook(hook_json(mcp_input(), path))))


def case_transcript_path_that_is_a_directory_is_silent():
    """A ready mark whose transcript_path is a directory cannot be read, so it fails open: silent, exit 0."""
    path = new_case_folder()
    return result(expect_silence(run_hook(hook_json(mcp_input(), path))))


def case_junk_stdin_is_silent_and_never_raises():
    """Empty stdin, bad JSON, an object with no fields, or a JSON list fails open: silent, exit 0, no raise."""
    problems = []
    for label, text in (("empty stdin", ""), ("bad JSON", "{not json"), ("no fields", "{}"), ("a JSON list", "[]")):
        problems += ["%s: %s" % (label, p) for p in result(expect_silence(run_hook(text)))]
    return problems


def case_junk_lines_in_the_transcript_do_not_stop_the_search():
    """Unparseable transcript lines are skipped, so a subscribe after them still counts."""
    path = write_transcript(["{not json", subscribe(), "[unterminated"])
    bad = premise(path, SUBSCRIBE, [pr_input()])
    if bad:
        return [bad]
    return result(expect_silence(run_hook(hook_json(mcp_input(), path))))


def case_ready_mark_reads_once_and_starts_nothing_else():
    """A ready mark reads the transcript once, opens no file for writing, starts no subprocess and sets no timer,
    with or without a subscribe."""
    problems = []
    for label, records in (("with a subscribe", [subscribe()]), ("without a subscribe", [])):
        path = write_transcript(records)
        c = run_in_process(hook_json(mcp_input(), path), path).counts
        if c.reads != 1:
            problems.append("%s: the transcript was read %d time(s) for one ready mark, not 1" % (label, c.reads))
        if c.writes:
            problems.append("%s: a file was opened for writing: %s" % (label, c.writes[0]))
        if c.subprocess:
            problems.append("%s: a subprocess was started: %s" % (label, c.subprocess[0]))
        if c.timers:
            problems.append("%s: a timer was set" % label)
        if c.sleeps:
            problems.append("%s: the hook slept %d time(s)" % (label, len(c.sleeps)))
    return problems


CASES = [
    case_ready_mark_with_empty_transcript_warns,
    case_ready_mark_after_other_calls_warns,
    case_full_size_transcript_without_a_subscribe_warns,
    case_subscribe_at_the_start_of_a_full_size_transcript_is_silent,
    case_subscribe_for_the_same_pr_is_silent,
    case_subscribe_for_another_pr_warns,
    case_subscribe_for_the_same_number_in_another_repo_warns,
    case_unsubscribe_after_the_subscribe_cancels_it,
    case_draft_absent_is_silent_and_reads_nothing,
    case_draft_true_is_silent_and_reads_nothing,
    case_other_tool_with_draft_false_is_silent_and_reads_nothing,
    case_bash_gh_pr_ready_is_silent_and_reads_nothing,
    case_subscribed_session_that_marks_ready_twice_stays_silent,
    case_sidechain_subscribe_counts,
    case_resumed_blob_copy_of_a_subscribe_does_not_count,
    case_missing_transcript_path_is_silent,
    case_missing_transcript_file_is_silent,
    case_transcript_path_that_is_a_directory_is_silent,
    case_junk_stdin_is_silent_and_never_raises,
    case_junk_lines_in_the_transcript_do_not_stop_the_search,
    case_ready_mark_reads_once_and_starts_nothing_else,
]


if __name__ == "__main__":
    try:
        sys.exit(run_cases(CASES))
    finally:
        shutil.rmtree(RUN, ignore_errors=True)
