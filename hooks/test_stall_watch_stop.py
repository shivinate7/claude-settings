#!/usr/bin/env python3
"""Cases for the Stop-time check of hooks/stall_watch.py (`--stop`). Standard library only.

Run it from the repository root:

    python hooks/test_stall_watch_stop.py

Design under test: the Stop hook runs `stall_watch.py --stop`. The mode reads the Stop JSON on
stdin, scans the session transcript for background shells, and prints ONE JSON line
`{"systemMessage": "..."}` that lists each stale job, or prints nothing.

- A job is a Bash call that a background run began. Its id is the `backgroundTaskId` in the
  record's structured `toolUseResult`. Text that quotes a result does not make a job.
- A job is dropped once the transcript holds a `<task-notification>` for its id whose
  `<status>` is terminal: completed, failed, killed or stopped, in any letter case. A stopped notice
  comes on a session resume for a job that did not finish. A running notice closes nothing. The
  notice is a user message or a queued_command attachment record.
- A job is also dropped once a TaskStop result says `Successfully stopped task: <id>` for its id.
  The result is a JSON string, or a list of text blocks. A stop result, or any other text, that
  names another id closes nothing.
- A record whose tool_use_id is not a string does not stop the scan: a job after it is still
  listed.
- A job is stale when its output file has not changed for the quiet age (STALL_WATCH_QUIET,
  default 300 s). A job whose output file is missing, or whose path os.stat rejects (a NUL byte), is
  listed as "unknown", never dropped, and it never drops the other rows.
- A job is listed only when its stall crossed after the previous Stop: the newest stop_hook_summary record,
  skipping the run after a blocked Stop (non-empty hookErrors, or preventedContinuation true). No summary, or an
  unreadable timestamp, lists every quiet job. An unknown job (no output file) is listed when its call is later
  than that Stop.
- A listed job shows its note: the text after `until:` in the description of the Bash call that
  started it, to the end of that line. The note sits on the job's own line, and the message asks
  whether it is met. A job whose call holds no `until:` text is still listed, with no note.
- A background agent (an Agent call started with run_in_background) is a job too. Its id is the
  agentId in the launch's toolUseResult, and its transcript is `<stem>/subagents/agent-<id>.jsonl`
  beside the session file. It is listed when that transcript has not changed for the quiet age and
  its last assistant record holds a tool_use with no result (one long call is not a stall). A
  completed notice or a TaskStop result closes it, as for a shell. A missing transcript is listed
  as unknown, once.
- When guard_stream cannot be imported, --stop still lists each stale job, with no note.
- Any error prints nothing and exits 0.

Seams: STALL_WATCH_NOW (epoch seconds, the clock), STALL_WATCH_OUTPUT_BASE (a folder that
replaces the folder of each transcript output path and keeps its file name), STALL_WATCH_QUIET
(the age in seconds). STALL_WATCH_MODULE picks the module under test, as in test_stall_watch.py.

No posix check: this mode must run on Windows. These cases use no sh, ps or lsof. Every case that
expects silence also runs a control that must list a stale job, so a mode that is absent or
silent everywhere cannot pass it.

The CI-wait check of the same mode (decision ci-wait-reads-run-status, "The fallback"). It reads the same
transcript and prints one JSON line `{"decision": "block", "reason": "..."}`, or nothing:
- A wait opens at the newest ready call: `gh pr ready <N>` in Bash or PowerShell, or a GitHub MCP
  update_pull_request with draft false. Draft true or absent starts none. Quoted text, heredoc bodies and
  `#` comments are no call. Global flags before `pr` (`gh -R <repo> pr ready <N>`) do not hide the call, and the
  PR is read as a merge's is: `-R <repo> <N>`, or the number in a pull URL. A `$VAR` PR word is no number.
- A later user or queued message with a green or cancelled CI verdict line closes the wait. A red verdict
  keeps it open and voids the check-ins before it. A `CI unknown` line (still running included) closes nothing.
- A merge closes the wait only when it names the waited PR: `gh pr merge <N>` or `gh pr close <N>` in Bash or
  PowerShell, `bin/merge <N>` or `merge <N>` (the merge tool), or a GitHub MCP merge_pull_request with that
  pullNumber. A bare `gh pr merge` or `gh pr close` (no number, so gh aims at the current branch's PR) also
  closes it. A merge that names another PR closes nothing, and an MCP merge with no pullNumber closes nothing.
  A merge that names a branch (`gh pr merge feature-x`) names no PR, so it closes no numbered wait.
  A merge with only flags and their values (`gh pr merge --squash --body "x"`) is bare, so it closes the wait
  too. A merge with `--auto` closes nothing: nothing has merged yet. A `$VAR` PR word is bare, and a wait on
  `$VAR` closes on any merge or close, as a bare wait does.
- A check-in is a later call of send_later, create_trigger, CronCreate or ScheduleWakeup. A check-in whose
  tool_result is an error does not count; one with no result yet, or a good result, does. An open wait with no
  check-in after its anchor (the newest ready call or red verdict) blocks, and the reason names the PR.
  A bad or unreadable transcript prints nothing.
- The check reads the transcript only: no process, no network, no file write (the cost case).
"""

import atexit
import builtins
import contextlib
import importlib.util
import io
import itertools
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time

from case_runner_test import Skip, run_cases

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lint"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)
MODULE = os.environ.get("STALL_WATCH_MODULE") or os.path.join(HERE, "stall_watch.py")
PY = sys.executable
SCRATCH = _test_temp.run_folder()
atexit.register(shutil.rmtree, SCRATCH, ignore_errors=True)
NOW = int(time.time())  # the clock every case passes as STALL_WATCH_NOW, so no case sleeps
ADVICE = "stop it or tell the owner"
RESUME_SUMMARY = "Background shell command didn't finish before the previous session ended"
WIN_DIR = (r"C:\Users\EXAMPL~1\AppData\Local\Temp\claude"
           r"\C--Users-ExampleUser-Clones-claude-settings\00000000-0000-4000-8000-000000000000\tasks")
CASES = []
NT_DRIVER = ("import json, os, runpy, shlex, shutil, subprocess, sys, tempfile, time, uuid\n"
             "os.name = 'nt'\n"
             "sys.argv = [sys.argv[1], '--stop']\n"
             "runpy.run_path(sys.argv[0], run_name='__main__')\n")


class Fail(Exception):
    pass


def case(fn):
    CASES.append(fn)
    return fn


def expect(ok, msg):
    return [] if ok else [msg]


def new_dir():
    return tempfile.mkdtemp(dir=SCRATCH)


def win_path(job_id):
    return WIN_DIR + "\\" + job_id + ".output"


def call(call_id, command, background=False, desc="test"):
    """A Bash tool_use. A call moved by its timeout has no run_in_background key. desc is the call's
    description; None leaves the key out, as a call in an older transcript has none."""
    inp = {"command": command}
    if desc is not None:
        inp["description"] = desc
    if background:
        inp["run_in_background"] = True
    return {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": call_id, "name": "Bash", "input": inp}]}}


def started(call_id, job_id, path, timed_out):
    """The tool_result of a background call, with its structured toolUseResult.

    timedOutAfterMs is present only when the timeout moved the call to the background. The text
    follows the transcript: a moved call says so, a call started in the background names its ID."""
    tur = {"stdout": "", "stderr": "", "interrupted": False, "isImage": False,
           "noOutputExpected": False, "backgroundTaskId": job_id}
    if timed_out:
        tur["timedOutAfterMs"] = 120000
        text = ("Command did not complete within its 120s timeout and was moved to the background "
                "(ID: %s). Output is being written to: %s. You will be notified when it finishes."
                % (job_id, path))
    else:
        text = "Command running in background with ID: %s. Output is being written to: %s" % (job_id, path)
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": call_id, "content": text, "is_error": False}]},
        "toolUseResult": tur}


def moved(job_id, path=None, desc="test"):
    """A Bash call that its timeout moved to the background, and its result."""
    cid = "toolu_" + job_id
    return [call(cid, "sleep 600", desc=desc), started(cid, job_id, path or win_path(job_id), True)]


def flagged(job_id, desc="test"):
    """A Bash call started with run_in_background, and its result."""
    cid = "toolu_" + job_id
    return [call(cid, "sleep 600", background=True, desc=desc),
            started(cid, job_id, win_path(job_id), False)]


def task_notification(job_id, status, summary=None):
    """The text of a completion notice: a <task-notification> block. The summary defaults to the
    command name and the status."""
    if summary is None:
        summary = 'Background command "sleep 600" ' + status
    return ("<task-notification>\n<task-id>%s</task-id>\n<tool-use-id>toolu_%s</tool-use-id>\n"
            "<output-file>%s</output-file>\n<status>%s</status>\n"
            "<summary>%s</summary>\n</task-notification>"
            % (job_id, job_id, win_path(job_id), status, summary))


def notice(job_id, status="completed", summary=None):
    """A completion notice as the transcript holds it: a user message whose content is a string."""
    return {"type": "user", "message": {"role": "user",
                                        "content": task_notification(job_id, status, summary)}}


def attachment_notice(job_id, status="completed", summary=None):
    """The same notice as a queued_command attachment record. It has no message key."""
    return {"type": "attachment", "attachment": {
        "type": "queued_command", "prompt": task_notification(job_id, status, summary)}}


def stop_call(call_id, job_id):
    """A TaskStop tool_use, as the assistant records it."""
    return {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": call_id, "name": "TaskStop", "input": {"task_id": job_id}}]}}


def stop_result(call_id, job_id, command="sleep 600", blocks=False):
    """The result of a TaskStop call: a tool_result whose content is a JSON string, or a list of
    text blocks when blocks is true, and a toolUseResult with the same fields."""
    body = {"message": "Successfully stopped task: %s (%s)" % (job_id, command), "task_id": job_id,
            "task_type": "local_bash", "command": command}
    content = [{"type": "text", "text": body["message"]}] if blocks else json.dumps(body)
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": call_id, "content": content}]},
        "toolUseResult": body}


def tool_result(call_id, text, is_error=False, tool_use_result=None):
    """The user record that carries one call's result: a tool_result block with its is_error flag. The record's
    toolUseResult is tool_use_result, when given."""
    rec = {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": call_id, "content": text, "is_error": is_error}]}}
    if tool_use_result is not None:
        rec["toolUseResult"] = tool_use_result
    return rec


def bash_result(call_id, text):
    """The result of a Bash call that started no job: plain stdout, no task id."""
    return tool_result(call_id, text, tool_use_result={"stdout": text, "stderr": "", "interrupted": False})


def assistant_text(text):
    """A plain text block of an assistant message."""
    return {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "text", "text": text}]}}


def transcript(items, agents=(), folder=None):
    """Write a session transcript, and each agent's transcript beside it. A dict is one JSON record;
    bytes are written as they are. agents is a list of (agent id, records, idle) tuples: each agent
    transcript is written at agent_path() with its mtime idle seconds before NOW. folder, when given,
    holds the session file."""
    folder = folder or new_dir()
    path = os.path.join(folder, "session.jsonl")
    with open(path, "wb") as f:
        for item in items:
            f.write(item if isinstance(item, bytes) else json.dumps(item).encode("utf-8") + b"\n")
    for aid, records, idle in agents:
        out = agent_path(folder, aid)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "wb") as f:
            for rec in records:
                f.write(json.dumps(rec).encode("utf-8") + b"\n")
        os.utime(out, (NOW - idle, NOW - idle))
    return path


def prompt(text):
    """A user prompt that opens a turn: a user message whose content is plain text."""
    return {"type": "user", "message": {"role": "user", "content": text}}


def at(rec, ago):
    """The record with the timestamp the transcript gives it: `ago` seconds before NOW, as ISO text
    ending in Z."""
    return dict(rec, timestamp=time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(NOW - ago)))


def stamped(records, ago):
    """Each record of a list, stamped `ago` seconds before NOW."""
    return [at(rec, ago) for rec in records]


def stop_summary(ago, blocked=False):
    """The stop_hook_summary record the harness writes after each Stop run, with the fields of a real one.
    blocked gives it hookErrors: a Stop that a hook blocked, whose next run is not a Stop (scan_jobs)."""
    return at({"type": "system", "subtype": "stop_hook_summary", "hookCount": 2,
               "hookInfos": [{"command": "command hook 1", "durationMs": 77}, {"command": "command hook 2"}],
               "hookErrors": ["Stop hook: send the report now."] if blocked else [],
               "hookAdditionalContext": [], "preventedContinuation": False, "stopReason": "",
               "hasOutput": blocked, "level": "suggestion"}, ago)


def queue_op(operation, ago):
    """A queue-operation record: a queued prompt that is enqueued or dequeued. It opens no turn."""
    return at({"type": "queue-operation", "operation": operation, "sessionId": "test-stall-watch-stop",
               "content": "queued prompt"}, ago)


def meta_wake(text, ago):
    """A user record with isMeta true: a hand-back or a hook's feedback that wakes a turn with no prompt."""
    return at({"type": "user", "isMeta": True, "message": {"role": "user", "content": text}}, ago)


def stop_listing(recs, base, now=None):
    """Run one Stop over the records. Return (problems, systemMessage), the message '' when none printed."""
    rc, out, err = run_stop(transcript(recs), base, now=now)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    return problems, system_message(out, problems)


def output_file(base, job_id, idle):
    """Write <base>/<job_id>.output, its mtime set idle seconds before NOW."""
    os.makedirs(base, exist_ok=True)
    path = os.path.join(base, job_id + ".output")
    with open(path, "wb") as f:
        f.write(b"output\n")
    os.utime(path, (NOW - idle, NOW - idle))
    return path


def run_stop(transcript_path, base=None, stop_hook_active=False, quiet=None, stdin=None, nt=False,
             module=None, now=None):
    """Run the Stop mode the way the Stop hook does. Return (rc, stdout, stderr). module, when
    given, is the script run in place of MODULE. now, when given, is the clock of this Stop (epoch
    seconds), so a case can run an earlier Stop than the others."""
    mod = module or MODULE
    if not os.path.isfile(mod):
        raise Fail(f"{mod} is missing")
    env = {k: v for k, v in os.environ.items() if not k.startswith("STALL_WATCH_")}
    if module is not None:
        env.pop("PYTHONPATH", None)  # a copy must not import its siblings from another checkout
    env["STALL_WATCH_NOW"] = str(NOW if now is None else now)
    if base is not None:
        env["STALL_WATCH_OUTPUT_BASE"] = base
    if quiet is not None:
        env["STALL_WATCH_QUIET"] = str(quiet)
    if stdin is None:
        payload = {"session_id": "test-stall-watch-stop", "hook_event_name": "Stop", "cwd": SCRATCH,
                   "transcript_path": transcript_path, "stop_hook_active": stop_hook_active}
        stdin = json.dumps(payload).encode("utf-8")
    argv = [PY, "-c", NT_DRIVER, mod] if nt else [PY, mod, "--stop"]
    proc = subprocess.run(argv, input=stdin, capture_output=True, env=env, timeout=20)
    return proc.returncode, proc.stdout.decode("utf-8", "replace"), proc.stderr.decode("utf-8", "replace")


def system_message(out, problems):
    """Return the systemMessage of the one JSON line the mode prints, or '' when it printed nothing."""
    if out.strip() == "":
        return ""
    if len(out.strip().splitlines()) != 1:
        problems.append(f"stop output is not one line: {out[:200]!r}")
    try:
        msg = json.loads(out)["systemMessage"]
    except (ValueError, KeyError, TypeError):
        problems.append(f"stop output is not a systemMessage JSON object: {out[:200]!r}")
        return ""
    if not isinstance(msg, str):
        problems.append("systemMessage is not a string")
        return ""
    return msg


def listed_once(msg, job_id, by_line=False):
    """Each job prints its output path once, so its file name appears once. An agent row (by_line)
    names the agent id, so the lines that name the id are counted instead."""
    if by_line:
        n = sum(job_id in line for line in msg.splitlines())
    else:
        n = msg.count(job_id + ".output")
    return expect(n == 1, f"job {job_id} listed {n} times, want 1: {msg!r}")


@case
def stale_moved_job_is_listed():
    """S1. a call its timeout moved to the background, quiet 600 s: listed once, with age and advice"""
    base = new_dir()
    output_file(base, "bmv600a", 600)
    rc, out, err = run_stop(transcript(moved("bmv600a")), base)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += listed_once(msg, "bmv600a")
    problems += expect("600s" in msg, f"age 600s is not in the listing: {msg!r}")
    problems += expect(ADVICE in msg.lower(), f"no advice {ADVICE!r}: {msg!r}")
    return problems


@case
def stale_flagged_job_is_listed():
    """S2. a call started with run_in_background, quiet 600 s: listed, from the same signal"""
    base = new_dir()
    output_file(base, "bfl600b", 600)
    rc, out, err = run_stop(transcript(flagged("bfl600b")), base)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += listed_once(msg, "bfl600b")
    return problems


def terminal_notice_drops_job_and_its_neighbour_stays():
    """S3. completed, failed and killed notices drop their jobs (completed is sent twice, as in the
    transcript). A stale job with no notice is still listed, so the mode itself works"""
    base = new_dir()
    for job in ("bdone600", "bfail600", "bkill600", "bopen600"):
        output_file(base, job, 600)
    recs = (moved("bdone600") + moved("bfail600") + moved("bkill600") + moved("bopen600")
            + [notice("bdone600"), notice("bdone600"), notice("bfail600", "failed"),
               notice("bkill600", "killed")])
    rc, out, err = run_stop(transcript(recs), base)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    for job in ("bdone600", "bfail600", "bkill600"):
        problems += expect(job not in msg, f"job {job} has a terminal notice but is listed: {msg!r}")
    problems += listed_once(msg, "bopen600")
    return problems


@case
def fresh_output_is_not_listed():
    """S4. a job whose output changed 10 s ago is not listed; a stale job beside it is"""
    base = new_dir()
    output_file(base, "bfresh10", 10)
    output_file(base, "bstale600", 600)
    rc, out, err = run_stop(transcript(moved("bfresh10") + moved("bstale600")), base)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += expect("bfresh10" not in msg, f"a job quiet 10 s is listed: {msg!r}")
    problems += listed_once(msg, "bstale600")
    return problems


@case
def no_job_prints_nothing_and_quoted_result_is_not_a_job():
    """S5. no background job: prints nothing, exit 0. Text that quotes a background result, with a
    stale output file behind it, is not a job. Control: the same transcript plus a real stale job
    lists that job and not the quoted one"""
    base = new_dir()
    output_file(base, "bquote600", 600)
    quoted = ("Command running in background with ID: bquote600. Output is being written to: %s\n"
              '"backgroundTaskId":"bquote600"' % win_path("bquote600"))
    quote_recs = [
        call("toolu_ls", "ls"),
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "toolu_ls", "content": "a\nb", "is_error": False}]},
         "toolUseResult": {"stdout": "a\nb", "stderr": "", "interrupted": False}},
        call("toolu_cat", "cat notes.txt"),
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "toolu_cat", "content": quoted, "is_error": False}]}},
    ]
    rc, out, err = run_stop(transcript(quote_recs), base)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    problems += expect(out.strip() == "", f"printed {out.strip()[:160]!r} with no job")
    output_file(base, "breal600", 600)
    rc, out, err = run_stop(transcript(quote_recs + moved("breal600")), base)
    msg = system_message(out, problems)
    problems += listed_once(msg, "breal600")
    problems += expect("bquote600" not in msg, f"quoted text was listed as a job: {msg!r}")
    return problems


def missing_or_unreadable_transcript_prints_nothing():
    """S6a. transcript path missing, or a folder: exit 0, nothing printed. Control: a readable
    transcript lists its stale job"""
    base = new_dir()
    output_file(base, "bgone600", 600)
    missing = os.path.join(new_dir(), "gone.jsonl")
    folder = new_dir()
    problems = []
    for bad in (missing, folder):
        rc, out, err = run_stop(bad, base)
        problems += expect(rc == 0, f"{bad}: exit {rc}, want 0: {err.strip()[:200]}")
        problems += expect(out.strip() == "", f"{bad}: printed {out.strip()[:120]!r}")
    rc, out, err = run_stop(transcript(moved("bgone600")), base)
    msg = system_message(out, problems)
    problems += listed_once(msg, "bgone600")
    return problems


def bad_stop_payload_prints_nothing():
    """S6b. stdin that is not JSON, or empty: exit 0, nothing printed. Control: a good payload
    lists the stale job"""
    base = new_dir()
    output_file(base, "bpay600", 600)
    tr = transcript(moved("bpay600"))
    problems = []
    for bad in (b"{not json", b""):
        rc, out, err = run_stop(tr, base, stdin=bad)
        problems += expect(rc == 0, f"stdin {bad!r}: exit {rc}, want 0: {err.strip()[:200]}")
        problems += expect(out.strip() == "", f"stdin {bad!r}: printed {out.strip()[:120]!r}")
    rc, out, err = run_stop(tr, base)
    msg = system_message(out, problems)
    problems += listed_once(msg, "bpay600")
    return problems


@case
def missing_output_file_is_unknown_not_clear():
    """S6c. a job with no output file and no notice: its line says unknown, exit 0. Control: a
    stale job beside it is listed with its age"""
    base = new_dir()
    output_file(base, "bhasout600", 600)
    recs = moved("bnoout600") + moved("bhasout600")
    rc, out, err = run_stop(transcript(recs), base)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    lines = msg.splitlines()
    problems += expect(any("bnoout600" in l and "unknown" in l.lower() for l in lines),
                       f"no line for bnoout600 says unknown: {msg!r}")
    problems += expect("clear" not in msg.lower(), f"the listing says clear: {msg!r}")
    problems += listed_once(msg, "bhasout600")
    return problems


@case
def stop_hook_active_prints_nothing():
    """S7. stop_hook_active true (this firing already rewrote the turn): nothing printed, exit 0.
    Control: the same transcript with stop_hook_active false lists the stale job"""
    base = new_dir()
    output_file(base, "bactive600", 600)
    tr = transcript(moved("bactive600"))
    rc, out, err = run_stop(tr, base, stop_hook_active=True)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    problems += expect(out.strip() == "", f"printed {out.strip()[:120]!r} with stop_hook_active true")
    rc, out, err = run_stop(tr, base, stop_hook_active=False)
    msg = system_message(out, problems)
    problems += listed_once(msg, "bactive600")
    return problems


@case
def each_stale_job_is_listed_once():
    """S8. three stale jobs, one of them with a duplicated started record: each listed exactly once"""
    base = new_dir()
    ids = ["bmany601", "bmany602", "bmany603"]
    recs = []
    for job in ids:
        output_file(base, job, 600)
        recs += moved(job)
    recs += moved("bmany601")[1:]  # the same started record again
    rc, out, err = run_stop(transcript(recs), base)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    for job in ids:
        problems += listed_once(msg, job)
    problems += expect(msg.count(".output") == 3, f"{msg.count('.output')} output paths, want 3: {msg!r}")
    return problems


@case
def default_age_is_300_seconds():
    """S9a. no STALL_WATCH_QUIET: a job quiet 200 s is not listed, one quiet 400 s is"""
    base = new_dir()
    output_file(base, "bdef200", 200)
    output_file(base, "bdef400", 400)
    rc, out, err = run_stop(transcript(moved("bdef200") + moved("bdef400")), base)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += expect("bdef200" not in msg, f"a job quiet 200 s is listed under the 300 s default: {msg!r}")
    problems += listed_once(msg, "bdef400")
    return problems


@case
def quiet_env_sets_the_age():
    """S9b. STALL_WATCH_QUIET=60 (the same name the PreToolUse watch reads): quiet 120 s is listed,
    quiet 30 s is not"""
    base = new_dir()
    output_file(base, "bq120", 120)
    output_file(base, "bq30", 30)
    rc, out, err = run_stop(transcript(moved("bq120") + moved("bq30")), base, quiet=60)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += expect("bq30" not in msg, f"a job quiet 30 s is listed under a 60 s age: {msg!r}")
    problems += listed_once(msg, "bq120")
    return problems


@case
def settings_has_one_stop_row_for_stop_mode():
    """S10. settings.json: exactly one Stop row runs stall_watch.py --stop, with timeout 10"""
    path = os.path.join(HERE, "..", "settings.json")
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError) as e:
        return [f"cannot read {path}: {e}"]
    rows = []
    for entry in cfg.get("hooks", {}).get("Stop", []):
        for h in entry.get("hooks", []):
            if re.search(r"stall_watch\.py.*--stop\b", h.get("command", "")):
                rows.append(h)
    problems = expect(len(rows) == 1, f"{len(rows)} Stop rows run stall_watch.py --stop, want 1")
    problems += expect(all(h.get("timeout") == 10 for h in rows),
                       f"timeout is {[h.get('timeout') for h in rows]}, want 10")
    return problems


@case
def windows_style_paths_resolve_by_file_name():
    """S11a. transcript paths with a drive letter and backslashes: the file is found by its name
    under the base folder, so it is not unknown"""
    base = new_dir()
    output_file(base, "bwinpath600", 600)
    rc, out, err = run_stop(transcript(moved("bwinpath600")), base)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += listed_once(msg, "bwinpath600")
    problems += expect("unknown" not in msg.lower(), f"an existing file is reported unknown: {msg!r}")
    problems += expect("600s" in msg, f"age 600s is not in the listing: {msg!r}")
    return problems


@case
def windows_path_is_printed_as_written():
    """S11b. no base folder, a drive-letter path with no file behind it: the job is listed as
    unknown, and the path shows its backslashes once, as written"""
    rc, out, err = run_stop(transcript(moved("bwinmiss60")), None)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += expect(WIN_DIR in msg, f"the path is not printed as written, with single backslashes: {msg!r}")
    problems += expect(any("bwinmiss60" in l and "unknown" in l.lower() for l in msg.splitlines()),
                       f"no line for bwinmiss60 says unknown: {msg!r}")
    return problems


@case
def real_windows_path_is_stat_ed():
    """S11c. Windows only: a real temp file at its real drive-letter path, quiet 600 s: listed"""
    if os.name != "nt":
        raise Skip("needs a Windows host")
    real = output_file(new_dir(), "bwinreal600", 600)
    rc, out, err = run_stop(transcript(moved("bwinreal600", path=real)), None)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += listed_once(msg, "bwinreal600")
    problems += expect("unknown" not in msg.lower(), f"a real file is reported unknown: {msg!r}")
    return problems


def huge_or_non_utf8_line_does_not_stop_the_scan():
    """S12a. a 3 MB line and a line with invalid UTF-8 bytes come before a stale job: exit 0,
    and the job is listed"""
    base = new_dir()
    output_file(base, "bhuge600", 600)
    big = b'{"type":"user","message":{"role":"user","content":"' + b"x" * (3 << 20) + b"\xff\xfe\"}}\n"
    bad = b'{"type":"user","message":{"role":"user","content":"\xff\xc3("}}\n'
    rc, out, err = run_stop(transcript([big, bad] + moved("bhuge600")), base)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += listed_once(msg, "bhuge600")
    return problems


def garbage_or_truncated_line_keeps_earlier_jobs():
    """S12b. a line that is not JSON in the middle, and a truncated last line (a live transcript):
    the stale job before them is still listed"""
    base = new_dir()
    output_file(base, "btrunc600", 600)
    tr = transcript([b"not json at all\n"] + moved("btrunc600")
                    + [b'{"type":"assistant","message":{"role":"assi'])
    rc, out, err = run_stop(tr, base)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += listed_once(msg, "btrunc600")
    return problems


@case
def stop_mode_has_no_posix_check():
    """S13. with os.name patched to nt the mode still lists the stale job"""
    base = new_dir()
    output_file(base, "bnt600", 600)
    rc, out, err = run_stop(transcript(moved("bnt600")), base, nt=True)
    problems = expect(rc == 0, f"exit {rc}, want 0 with os.name nt: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += listed_once(msg, "bnt600")
    return problems


def attachment_completed_notice_closes_job():
    """S14a. a completed notice that arrives as a queued_command attachment closes its job, and a
    stale job with no notice beside it is still listed"""
    base = new_dir()
    output_file(base, "batt600", 600)
    output_file(base, "batt601", 600)
    recs = moved("batt600") + moved("batt601") + [attachment_notice("batt600")]
    rc, out, err = run_stop(transcript(recs), base)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += expect("batt600" not in msg,
                       f"job batt600 has an attachment completed notice but is listed: {msg!r}")
    problems += listed_once(msg, "batt601")
    return problems


def attachment_failed_and_killed_notices_close_jobs():
    """S14b. failed and killed notices in attachment form close their jobs, and an open job beside
    them is still listed"""
    base = new_dir()
    for job in ("bafail600", "bakill600", "baopen600"):
        output_file(base, job, 600)
    recs = (moved("bafail600") + moved("bakill600") + moved("baopen600")
            + [attachment_notice("bafail600", "failed"), attachment_notice("bakill600", "killed")])
    rc, out, err = run_stop(transcript(recs), base)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    for job in ("bafail600", "bakill600"):
        problems += expect(job not in msg, f"job {job} has a terminal attachment notice but is listed: {msg!r}")
    problems += listed_once(msg, "baopen600")
    return problems


def attachment_notice_for_longer_id_does_not_close_shorter_job():
    """S14c. a notice for bapfx600 does not close the job bapfx60, whose id is a prefix of it. The
    notice does close bapfx600 itself"""
    base = new_dir()
    output_file(base, "bapfx60", 600)
    output_file(base, "bapfx600", 600)
    recs = moved("bapfx60") + moved("bapfx600") + [attachment_notice("bapfx600")]
    rc, out, err = run_stop(transcript(recs), base)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += expect("bapfx600" not in msg, f"job bapfx600 has its notice but is listed: {msg!r}")
    problems += listed_once(msg, "bapfx60")
    return problems


def attachment_record_without_prompt_does_not_stop_the_scan():
    """S14d. attachment records with no attachment key, a string attachment, no prompt, or a prompt
    that is null or a list come before a good notice: exit 0, the notice still closes its job, and
    the stale job before them is still listed"""
    base = new_dir()
    output_file(base, "banoprm600", 600)
    output_file(base, "banoprmk600", 600)
    bad = [
        {"type": "attachment"},
        {"type": "attachment", "attachment": "not an object"},
        {"type": "attachment", "attachment": {"type": "queued_command"}},
        {"type": "attachment", "attachment": {"type": "queued_command", "prompt": None}},
        {"type": "attachment", "attachment": {"type": "queued_command", "prompt": ["a", "list"]}},
    ]
    recs = moved("banoprm600") + bad + moved("banoprmk600") + [attachment_notice("banoprmk600")]
    rc, out, err = run_stop(transcript(recs), base)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += expect("banoprmk600" not in msg, f"the notice after the bad records did not close its job: {msg!r}")
    problems += listed_once(msg, "banoprm600")
    return problems


def stop_result_closes_stopped_job():
    """S15a. a job followed by a TaskStop result 'Successfully stopped task: ID' is closed. The
    command text of that result names another job, which stays listed"""
    base = new_dir()
    output_file(base, "bstop600", 600)
    output_file(base, "bstopk600", 600)
    recs = (moved("bstop600") + moved("bstopk600")
            + [stop_call("toolu_stop1", "bstop600"),
               stop_result("toolu_stop1", "bstop600", command='echo "Successfully stopped task: bstopk600"')])
    rc, out, err = run_stop(transcript(recs), base)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += expect("bstop600" not in msg, f"job bstop600 has a stop result but is listed: {msg!r}")
    problems += listed_once(msg, "bstopk600")
    return problems


def stop_result_for_longer_id_does_not_close_shorter_job():
    """S15b. a stop result for bpfx600 does not close the job bpfx60, whose id is a prefix of it. The
    stop closes bpfx600 itself"""
    base = new_dir()
    output_file(base, "bpfx60", 600)
    output_file(base, "bpfx600", 600)
    recs = (moved("bpfx60") + moved("bpfx600")
            + [stop_call("toolu_stop2", "bpfx600"), stop_result("toolu_stop2", "bpfx600")])
    rc, out, err = run_stop(transcript(recs), base)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += expect("bpfx600" not in msg, f"job bpfx600 has a stop result but is listed: {msg!r}")
    problems += listed_once(msg, "bpfx60")
    return problems


def assistant_text_naming_another_id_does_not_close_job():
    """S15c. an assistant message that quotes 'Successfully stopped task' for another id, and names
    the stale job, does not close that job. The real stop result still closes its own job"""
    base = new_dir()
    output_file(base, "bastxt600", 600)
    output_file(base, "bastxk600", 600)
    recs = (moved("bastxt600") + moved("bastxk600")
            + [assistant_text("Successfully stopped task: batxother (sleep 9). bastxt600 is still running."),
               stop_call("toolu_stop3", "bastxk600"), stop_result("toolu_stop3", "bastxk600")])
    rc, out, err = run_stop(transcript(recs), base)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += expect("bastxk600" not in msg, f"job bastxk600 has a stop result but is listed: {msg!r}")
    problems += listed_once(msg, "bastxt600")
    return problems


def other_tool_result_naming_another_id_does_not_close_job():
    """S15d. a Bash result that quotes 'Successfully stopped task' for another id, and names the
    stale job, does not close that job. The real stop result still closes its own job"""
    base = new_dir()
    output_file(base, "batool600", 600)
    output_file(base, "batoolk600", 600)
    recs = (moved("batool600") + moved("batoolk600")
            + [call("toolu_grep", "cat notes.txt"),
               bash_result("toolu_grep", "Successfully stopped task: batoolx (sleep 9)\nbatool600 still running"),
               stop_call("toolu_stop4", "batoolk600"), stop_result("toolu_stop4", "batoolk600")])
    rc, out, err = run_stop(transcript(recs), base)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += expect("batoolk600" not in msg, f"job batoolk600 has a stop result but is listed: {msg!r}")
    problems += listed_once(msg, "batool600")
    return problems


def stopped_notice_in_record_form_closes_job():
    """S16a. a stopped notice, as a session resume sends it, in user-record form closes its job. An
    open stale job beside it is still listed"""
    base = new_dir()
    output_file(base, "bstpu600", 600)
    output_file(base, "bstpuopen600", 600)
    recs = moved("bstpu600") + moved("bstpuopen600") + [notice("bstpu600", "stopped", RESUME_SUMMARY)]
    rc, out, err = run_stop(transcript(recs), base)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += expect("bstpu600" not in msg, f"job bstpu600 has a stopped notice but is listed: {msg!r}")
    problems += listed_once(msg, "bstpuopen600")
    return problems


def stopped_notice_in_attachment_form_closes_job():
    """S16b. the same stopped notice as a queued_command attachment closes its job. An open stale
    job beside it is still listed"""
    base = new_dir()
    output_file(base, "bstpa600", 600)
    output_file(base, "bstpaopen600", 600)
    recs = moved("bstpa600") + moved("bstpaopen600") + [attachment_notice("bstpa600", "stopped", RESUME_SUMMARY)]
    rc, out, err = run_stop(transcript(recs), base)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += expect("bstpa600" not in msg,
                       f"job bstpa600 has a stopped attachment notice but is listed: {msg!r}")
    problems += listed_once(msg, "bstpaopen600")
    return problems


@case
def running_notice_does_not_close_job_and_stopped_notice_does():
    """S16c. a running notice in user-record form leaves its job listed once. A stopped notice in
    attachment form closes its own job, so that job is not listed."""
    base = new_dir()
    output_file(base, "brunrun600", 600)
    output_file(base, "bstpb600", 600)
    recs = (moved("brunrun600") + moved("bstpb600")
            + [notice("brunrun600", "running"), attachment_notice("bstpb600", "stopped", RESUME_SUMMARY)])
    rc, out, err = run_stop(transcript(recs), base)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += listed_once(msg, "brunrun600")
    problems += expect("bstpb600" not in msg, f"job bstpb600 has a stopped attachment notice but is listed: {msg!r}")
    return problems


def stopped_notice_for_longer_id_does_not_close_shorter_job():
    """S16d. a stopped notice for bstpq600 does not close bstpq60, whose id is a prefix of it. The
    notice closes bstpq600 itself"""
    base = new_dir()
    output_file(base, "bstpq60", 600)
    output_file(base, "bstpq600", 600)
    recs = moved("bstpq60") + moved("bstpq600") + [notice("bstpq600", "stopped", RESUME_SUMMARY)]
    rc, out, err = run_stop(transcript(recs), base)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += expect("bstpq600" not in msg, f"job bstpq600 has a stopped notice but is listed: {msg!r}")
    problems += listed_once(msg, "bstpq60")
    return problems


def stop_result_as_text_blocks_closes_job():
    """S17a. a TaskStop result whose content is a list of text blocks closes its job, as the string
    form does. An open stale job beside it is still listed"""
    base = new_dir()
    output_file(base, "bblk600", 600)
    output_file(base, "bblkopen600", 600)
    recs = (moved("bblk600") + moved("bblkopen600")
            + [stop_call("toolu_blk1", "bblk600"), stop_result("toolu_blk1", "bblk600", blocks=True)])
    rc, out, err = run_stop(transcript(recs), base)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += expect("bblk600" not in msg, f"job bblk600 has a block-list stop result but is listed: {msg!r}")
    problems += listed_once(msg, "bblkopen600")
    return problems


def stop_result_as_text_blocks_for_longer_id_does_not_close_shorter_job():
    """S17b. a block-list stop result for bblx600 does not close bblx60, whose id is a prefix of it.
    The stop closes bblx600 itself"""
    base = new_dir()
    output_file(base, "bblx60", 600)
    output_file(base, "bblx600", 600)
    recs = (moved("bblx60") + moved("bblx600")
            + [stop_call("toolu_blk2", "bblx600"), stop_result("toolu_blk2", "bblx600", blocks=True)])
    rc, out, err = run_stop(transcript(recs), base)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += expect("bblx600" not in msg, f"job bblx600 has a block-list stop result but is listed: {msg!r}")
    problems += listed_once(msg, "bblx60")
    return problems


def malformed_tool_use_id_does_not_drop_the_alarm():
    """S18. user records whose tool_use_id is a list, or a dict, come before one open stale job:
    exit 0, and the alarm still lists that job"""
    base = new_dir()
    output_file(base, "bmal600", 600)
    bad = [
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": ["q"], "content": "Successfully stopped task: other"}]}},
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": {"id": "q"}, "content": "Successfully stopped task: other"}]}},
    ]
    rc, out, err = run_stop(transcript(bad + moved("bmal600")), base)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += listed_once(msg, "bmal600")
    return problems


def mixed_case_status_closes_job():
    """S19. a notice with status 'Completed', and an attachment notice with status 'KILLED', close
    their jobs. An open stale job beside them is still listed"""
    base = new_dir()
    for job in ("bmixc600", "bmixk600", "bmixopen600"):
        output_file(base, job, 600)
    recs = (moved("bmixc600") + moved("bmixk600") + moved("bmixopen600")
            + [notice("bmixc600", "Completed"), attachment_notice("bmixk600", "KILLED")])
    rc, out, err = run_stop(transcript(recs), base)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    for job in ("bmixc600", "bmixk600"):
        problems += expect(job not in msg, f"job {job} has a mixed-case terminal notice but is listed: {msg!r}")
    problems += listed_once(msg, "bmixopen600")
    return problems


def nul_path_drops_one_row_not_the_run():
    """S12c. a job whose output path holds a NUL byte (os.stat raises ValueError) is listed as
    unknown, and a stale job beside it is still listed"""
    base = new_dir()
    output_file(base, "bnulgood600", 600)
    recs = moved("bnul600", path=WIN_DIR + "\\bnul\x00600.output") + moved("bnulgood600")
    rc, out, err = run_stop(transcript(recs), base)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += expect("unknown" in line_of(msg, "bnul600"), f"the NUL-path job has no unknown row: {msg!r}")
    problems += listed_once(msg, "bnulgood600")
    return problems


def line_of(msg, job_id):
    """The line of the message that names the job, or '' when none does."""
    return next((line for line in msg.splitlines() if job_id in line), "")


@case
def until_note_is_printed_beside_its_quiet_job():
    """N1. a quiet job whose call's description holds `until: <condition>` shows that condition on
    the job's own line, and the message asks whether it is met"""
    base = new_dir()
    output_file(base, "bnote600", 600)
    recs = flagged("bnote600", desc="Serve q_max files on 3202. until: round 1 bids are served")
    rc, out, err = run_stop(transcript(recs), base)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += listed_once(msg, "bnote600")
    problems += expect("round 1 bids are served" in line_of(msg, "bnote600"),
                       f"the note is not on the job's own line: {msg!r}")
    problems += expect(re.search(r"\bmet\b", msg.lower()) is not None,
                       f"the message does not ask whether the condition is met: {msg!r}")
    return problems


@case
def each_quiet_job_shows_its_own_note():
    """N2. three quiet jobs: a flagged call and a call its timeout moved, each with its own note, and
    a call with no description. Each note sits on its own job's line only, and the job with no note
    is still listed"""
    base = new_dir()
    for job in ("bnoteA", "bnoteB", "bnoteC"):
        output_file(base, job, 600)
    recs = (flagged("bnoteA", desc="until: round 1 bids are served")
            + moved("bnoteB", desc="until: round 2 bids are served")
            + flagged("bnoteC", desc=None))
    rc, out, err = run_stop(transcript(recs), base)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    for job in ("bnoteA", "bnoteB", "bnoteC"):
        problems += listed_once(msg, job)
    a, b, c = line_of(msg, "bnoteA"), line_of(msg, "bnoteB"), line_of(msg, "bnoteC")
    problems += expect("round 1 bids are served" in a and "round 2" not in a,
                       f"job A's line does not hold only its own note: {a!r}")
    problems += expect("round 2 bids are served" in b and "round 1" not in b,
                       f"job B's line does not hold only its own note: {b!r}")
    problems += expect("round" not in c, f"job C has no note, but its line names one: {c!r}")
    return problems


@case
def stop_lists_quiet_job_without_notes_when_guard_stream_is_missing():
    """N3. guard_stream cannot be imported (a scratch copy of stall_watch.py, shared_names.py and own_session.py,
    with no guard_stream beside them): --stop exits 0 and lists the quiet job once, with no note. A control runs
    the real module on the same transcript and shows the note, so the missing note is not a broken fixture"""
    base = new_dir()
    output_file(base, "bnoimp600", 600)
    recs = flagged("bnoimp600", desc="Serve q_max files on 3202. until: round 1 bids are served")
    path = transcript(recs)
    lone = new_dir()
    shutil.copy(MODULE, os.path.join(lone, "stall_watch.py"))
    shutil.copy(os.path.join(HERE, "shared_names.py"), lone)
    # stall_watch imports own_session with no guard, so the copy needs it; guard_stream is the one left out
    shutil.copy(os.path.join(HERE, "own_session.py"), lone)
    rc, out, err = run_stop(path, base, module=os.path.join(lone, "stall_watch.py"))
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += listed_once(msg, "bnoimp600")
    problems += expect("600s" in msg, f"age 600s is not in the listing: {msg!r}")
    problems += expect("round 1 bids" not in msg and "| until:" not in msg,
                       f"a note is printed with guard_stream missing: {msg!r}")
    rc, out, err = run_stop(path, base)
    control = system_message(out, [])
    problems += expect(rc == 0 and "round 1 bids are served" in control,
                       f"control: the real module does not print the note: rc {rc}, {out[:200]!r}")
    return problems


def hooks_copy(shared):
    """A scratch copy of hooks/*.py. shared None leaves out shared_names.py; "stale" writes one with no
    TASK_NOTIFICATION_TAG; "real" keeps the real one. Returns the copy's stall_watch.py."""
    lone = new_dir()
    for name in os.listdir(HERE):
        if name.endswith(".py") and not (name == "shared_names.py" and shared != "real"):
            shutil.copy(os.path.join(HERE, name), os.path.join(lone, name))
    if shared == "stale":
        with open(os.path.join(lone, "shared_names.py"), "w", encoding="utf-8") as f:
            f.write("PROJECT_FROZEN_FILES = ()\n")
    return os.path.join(lone, os.path.basename(MODULE))


def finished_job_is_silent_without_the_notice_tag(shared, label):
    """A job its completed notice closed, idle 2 h: with shared_names `shared` the check prints nothing
    and exits 0, since a false 'still running' alarm is worse than a missed stall. A control runs the
    copy with the real shared_names on the same transcript (silent) and a still-running job (listed)."""
    base = new_dir()
    output_file(base, "bfin7200", 7200)
    output_file(base, "brun7200", 7200)
    done = transcript(flagged("bfin7200") + [notice("bfin7200")])
    rc, out, err = run_stop(done, base, module=hooks_copy(shared))
    problems = expect(rc == 0, f"{label}: exit {rc}, want 0: {err.strip()[:200]}")
    problems += expect(out.strip() == "", f"{label}: a finished job prints an alarm: {out[:300]!r}")
    real = hooks_copy("real")
    rc, out, err = run_stop(done, base, module=real)
    problems += expect(rc == 0 and out.strip() == "", f"control: real shared_names, finished job: rc {rc}, {out[:200]!r}")
    rc, out, err = run_stop(transcript(flagged("brun7200")), base, module=real)
    problems += expect(rc == 0 and "brun7200" in out, f"control: a running job is not listed: rc {rc}, {out[:200]!r}")
    return problems


@case
def finished_job_is_silent_with_shared_names_missing():
    """N4a. shared_names.py absent: a finished job idle 2 h prints nothing, exit 0"""
    return finished_job_is_silent_without_the_notice_tag(None, "shared_names missing")


@case
def finished_job_is_silent_with_shared_names_stale():
    """N4b. shared_names.py without TASK_NOTIFICATION_TAG: a finished job idle 2 h prints nothing, exit 0"""
    return finished_job_is_silent_without_the_notice_tag("stale", "shared_names stale")


# Row tables. Each row is one case body from above, and keeps its S-label.
PREFIX_ROWS = (
    attachment_notice_for_longer_id_does_not_close_shorter_job,
    stop_result_for_longer_id_does_not_close_shorter_job,
    stopped_notice_for_longer_id_does_not_close_shorter_job,
    stop_result_as_text_blocks_for_longer_id_does_not_close_shorter_job,
)
NOTICE_ROWS = (
    terminal_notice_drops_job_and_its_neighbour_stays,
    attachment_completed_notice_closes_job,
    attachment_failed_and_killed_notices_close_jobs,
    stopped_notice_in_record_form_closes_job,
    stopped_notice_in_attachment_form_closes_job,
    mixed_case_status_closes_job,
)
JUNK_ROWS = (
    missing_or_unreadable_transcript_prints_nothing,
    bad_stop_payload_prints_nothing,
    huge_or_non_utf8_line_does_not_stop_the_scan,
    garbage_or_truncated_line_keeps_earlier_jobs,
    attachment_record_without_prompt_does_not_stop_the_scan,
    malformed_tool_use_id_does_not_drop_the_alarm,
    nul_path_drops_one_row_not_the_run,
)
TASKSTOP_ROWS = (
    stop_result_closes_stopped_job,
    assistant_text_naming_another_id_does_not_close_job,
    other_tool_result_naming_another_id_does_not_close_job,
    stop_result_as_text_blocks_closes_job,
)


def table_rows(rows):
    """Run each row body. A failing row prints its S-label before its problem. A crash names
    its row too, and does not stop the table."""
    problems = []
    for body in rows:
        label = body.__doc__.split(".")[0].strip()
        try:
            found = body()
        except Exception as e:
            found = [str(e)]
        problems += ["%s: %s" % (label, p) for p in found]
    return problems


@case
def table_longer_id_never_closes_a_shorter_job():
    """Table, id prefix: a longer id closes no shorter job, in each notice and stop form."""
    return table_rows(PREFIX_ROWS)


@case
def table_notice_form_by_status_closes_terminal_jobs():
    """Table, notice form by status: completed, failed, killed and stopped notices close their
    jobs, in record and attachment form."""
    return table_rows(NOTICE_ROWS)


@case
def table_junk_input_keeps_the_alarm():
    """Table, junk input: bad stdin, transcript and records never stop the scan or the alarm."""
    return table_rows(JUNK_ROWS)


@case
def table_taskstop_forms():
    """Table, TaskStop forms: a stop result closes its job, as text or as a block list, and a
    quoted or other-tool id closes nothing."""
    return table_rows(TASKSTOP_ROWS)


def log_job(job_id, command, cwd=None):
    """A background call whose command sends its output to a log, and its result. cwd, when given,
    is the call record's working directory, as the transcript holds it."""
    cid = "toolu_" + job_id
    rec = call(cid, command, background=True)
    if cwd is not None:
        rec["cwd"] = cwd
    return [rec, started(cid, job_id, win_path(job_id), False)]


def log_at(path, idle):
    with open(path, "wb") as f:
        f.write(b"merge: waiting on checks\n")
    os.utime(path, (NOW - idle, NOW - idle))
    return path


@case
def open_job_whose_named_log_grows_is_not_listed():
    """S20a. a merge.py-like job: its output file quiet 600 s, the log its command names by
    redirection changed 10 s ago: not listed. A relative log resolves against the call's cwd"""
    base, d = new_dir(), new_dir()
    output_file(base, "bmlog600", 600)
    output_file(base, "bmrel600", 600)
    output_file(base, "bmopen600", 600)
    log = log_at(os.path.join(d, "merge.log"), 10)
    log_at(os.path.join(d, "rel.log"), 10)
    recs = (log_job("bmlog600", "python3 merge.py 586 --confirm > '%s' 2>&1" % log)
            + log_job("bmrel600", "python3 merge.py 586 >> rel.log 2>&1", cwd=d) + moved("bmopen600"))
    rc, out, err = run_stop(transcript(recs), base)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += expect("bmlog600" not in msg, f"a job whose named log grows is listed: {msg!r}")
    problems += expect("bmrel600" not in msg, f"a job whose relative named log grows is listed: {msg!r}")
    problems += listed_once(msg, "bmopen600")
    return problems


@case
def open_job_whose_named_log_is_quiet_is_listed():
    """S20b. the same job whose named log is also quiet 600 s is listed; so is a job that names a log
    only inside quotes or a comment, though that file changed 10 s ago"""
    base, d = new_dir(), new_dir()
    output_file(base, "bmquiet600", 600)
    output_file(base, "bmquote600", 600)
    quiet = log_at(os.path.join(d, "quiet.log"), 600)
    fresh = log_at(os.path.join(d, "fresh.log"), 10)
    recs = (log_job("bmquiet600", "python3 merge.py 586 > '%s' 2>&1" % quiet)
            + log_job("bmquote600", "echo '> %s' \"--log %s\"; sleep 600 # >> %s" % (fresh, fresh, fresh)))
    rc, out, err = run_stop(transcript(recs), base)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += listed_once(msg, "bmquiet600")
    problems += listed_once(msg, "bmquote600")
    return problems


@case
def named_log_with_odd_cwd_keeps_the_report():
    """S20c. a call record whose cwd is not a string, with a relative and a `--log=F` named log: the
    report still lists the stale jobs, and a fresh absolute `--log=F` log still keeps its job off"""
    base, d = new_dir(), new_dir()
    output_file(base, "bmodd600", 600)
    output_file(base, "bmflag600", 600)
    fresh = log_at(os.path.join(d, "flag.log"), 10)
    recs = (log_job("bmodd600", "python3 merge.py 586 &> rel.log", cwd=["x"])
            + log_job("bmflag600", "python3 merge.py 586 --log='%s'" % fresh, cwd=5))
    rc, out, err = run_stop(transcript(recs), base)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += listed_once(msg, "bmodd600")
    problems += expect("bmflag600" not in msg, f"a job whose --log= log grows is listed: {msg!r}")
    return problems


@case
def job_listed_at_one_stop_is_silent_at_the_next():
    """B1. a job started in a prior turn, quiet since 1400 s ago, so its stall crossed 1100 s ago, after the
    previous Stop (its stop_hook_summary, 1200 s ago). The first Stop, at the end of the next turn, lists it. The
    second Stop, with no new output, is silent about it: its stall crossed before the first Stop's summary, 900 s
    ago. A job started in the turn after is listed at the second Stop, the control that shows the second Stop still lists"""
    base = new_dir()
    output_file(base, "bcross", 1400)
    turn0 = [at(prompt("first"), 1500)] + stamped(moved("bcross"), 1490) + [at(assistant_text("first answer"), 1200), stop_summary(1200)]
    turn1 = [at(prompt("start"), 1000), at(assistant_text("started"), 900)]
    rc1, out1, err1 = run_stop(transcript(turn0 + turn1), base, now=NOW - 900)
    problems = expect(rc1 == 0, f"first Stop exit {rc1}, want 0: {err1.strip()[:200]}")
    msg1 = system_message(out1, problems)
    problems += listed_once(msg1, "bcross")
    output_file(base, "bctl1", 600)  # the control: quiet since 600 s ago, so its stall crossed 300 s ago
    turn2 = [stop_summary(900), at(prompt("next"), 800)] + stamped(moved("bctl1"), 800) + [at(assistant_text("ok"), 700)]
    rc2, out2, err2 = run_stop(transcript(turn0 + turn1 + turn2), base)
    problems += expect(rc2 == 0, f"second Stop exit {rc2}, want 0: {err2.strip()[:200]}")
    msg2 = system_message(out2, problems)
    problems += expect("bcross" not in msg2, f"job bcross is listed again at the second Stop: {msg2!r}")
    problems += listed_once(msg2, "bctl1")
    return problems


@case
def job_that_stalls_again_is_listed_again():
    """B2. a job listed at the first Stop, whose output file or whose named log moves after it and goes quiet
    again: the second Stop lists it again. The named-log job keeps its output file quiet, so a rule that reads
    only the output file misses that re-stall"""
    base, d = new_dir(), new_dir()
    output_file(base, "bagain", 1300)
    output_file(base, "bnlog", 1300)
    log = log_at(os.path.join(d, "merge.log"), 1300)
    turn1 = ([at(prompt("start"), 1400)] + stamped(moved("bagain"), 1390)
             + stamped(log_job("bnlog", "python3 merge.py 586 > '%s' 2>&1" % log), 1390)
             + [at(assistant_text("started"), 900)])
    rc1, out1, err1 = run_stop(transcript(turn1), base, now=NOW - 900)
    problems = expect(rc1 == 0, f"first Stop exit {rc1}, want 0: {err1.strip()[:200]}")
    msg1 = system_message(out1, problems)
    problems += listed_once(msg1, "bagain")
    problems += listed_once(msg1, "bnlog")
    output_file(base, "bagain", 600)  # its output file moves after the first Stop, then goes quiet
    log_at(log, 600)  # the named log of bnlog moves after the first Stop, then goes quiet
    turn2 = [at(prompt("next"), 800), at(assistant_text("ok"), 700)]
    rc2, out2, err2 = run_stop(transcript(turn1 + turn2), base)
    problems += expect(rc2 == 0, f"second Stop exit {rc2}, want 0: {err2.strip()[:200]}")
    msg2 = system_message(out2, problems)
    problems += listed_once(msg2, "bagain")
    problems += listed_once(msg2, "bnlog")
    return problems


@case
def unknown_job_is_reported_at_the_first_stop_after_it_starts():
    """B3. a job with no output file, started in turn 1, after the turn 0 Stop 1300 s ago: the first Stop after it
    lists it as unknown, and the next Stop does not. A job started in turn 2 is listed at the next Stop. Its start
    is 1000 s before NOW, after the turn 0 summary, so the first Stop lists it. The first Stop's summary is 600 s
    before NOW, so the second Stop does not list it again"""
    base = new_dir()  # empty: every job here is unknown
    turn0 = [at(prompt("first"), 1500), at(assistant_text("first answer"), 1300), stop_summary(1300)]
    turn1 = [at(prompt("start"), 1200)] + stamped(moved("bunk1"), 1000) + [at(assistant_text("started"), 600)]
    rc1, out1, err1 = run_stop(transcript(turn0 + turn1), base, now=NOW - 600)
    problems = expect(rc1 == 0, f"first Stop exit {rc1}, want 0: {err1.strip()[:200]}")
    msg1 = system_message(out1, problems)
    problems += listed_once(msg1, "bunk1")
    problems += expect("unknown" in line_of(msg1, "bunk1"), f"bunk1 is not listed as unknown: {msg1!r}")
    turn2 = [stop_summary(600), at(prompt("next"), 550)] + stamped(moved("bunk2"), 500) + [at(assistant_text("ok"), 400)]
    rc2, out2, err2 = run_stop(transcript(turn0 + turn1 + turn2), base)
    problems += expect(rc2 == 0, f"second Stop exit {rc2}, want 0: {err2.strip()[:200]}")
    msg2 = system_message(out2, problems)
    problems += expect("bunk1" not in msg2, f"unknown job bunk1 is listed again at the second Stop: {msg2!r}")
    problems += listed_once(msg2, "bunk2")
    return problems


@case
def first_stop_lists_a_quiet_job_as_before():
    """B4. a transcript with no prior turn, the first Stop: a quiet job is listed with its age, as before"""
    base = new_dir()
    output_file(base, "bfirst", 600)
    recs = [at(prompt("start"), 1000)] + stamped(moved("bfirst"), 990) + [at(assistant_text("started"), 900)]
    rc, out, err = run_stop(transcript(recs), base)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += listed_once(msg, "bfirst")
    problems += expect("600s" in msg, f"age 600s is not in the listing: {msg!r}")
    return problems


@case
def C1_stall_in_the_idle_gap_before_a_prompt_is_listed():
    """C1. a queue-operation enqueue and dequeue sit between the previous Stop and the next prompt. A job whose
    stall crossed in that gap, after the previous Stop, is listed at the next Stop"""
    base = new_dir()
    output_file(base, "bgap", 1800)  # crossed 1500 s ago, after the Stop 2000 s ago
    recs = ([at(prompt("first"), 2300)] + stamped(moved("bgap"), 2290)
            + [at(assistant_text("ok"), 2100), stop_summary(2000), queue_op("enqueue", 1010),
               queue_op("dequeue", 1000), at(prompt("next"), 999), at(assistant_text("ok"), 900)])
    problems, msg = stop_listing(recs, base)
    return problems + listed_once(msg, "bgap")


@case
def C2_two_stop_runs_in_one_turn_list_a_job_once():
    """C2. two Stop runs in one turn, each with its summary. A job whose stall crossed before the first run is
    listed there and is silent at the second run. A job whose stall crossed after the first run is listed at the second"""
    base = new_dir()
    output_file(base, "bdup", 1200)  # crossed 900 s ago
    output_file(base, "bnew", 600)  # crossed 300 s ago, after the first run 800 s ago
    turn = ([at(prompt("first"), 1500)] + stamped(moved("bdup"), 1490)
            + [at(assistant_text("ok"), 1100), stop_summary(1100), at(prompt("start"), 1000)]
            + stamped(moved("bnew"), 900) + [at(assistant_text("working"), 850)])
    problems, msg1 = stop_listing(turn, base, now=NOW - 800)
    problems += listed_once(msg1, "bdup")
    problems += expect("bnew" not in msg1, f"job bnew is listed before its stall crossed: {msg1!r}")
    turn += [stop_summary(800), at(assistant_text("again"), 700)]  # the first run's summary, then the second run
    p2, msg2 = stop_listing(turn, base)
    problems += p2 + expect("bdup" not in msg2, f"job bdup is listed again at the second Stop of the turn: {msg2!r}")
    return problems + listed_once(msg2, "bnew")


@case
def C3_isMeta_hand_back_does_not_relist_a_listed_job():
    """C3. a job listed at the Stop 800 s ago (its summary), then an isMeta hand-back wakes a turn with no prompt
    record. The Stop at the end of that turn is silent about the job. A job that crossed after that summary is
    listed there, so the hand-back does not hide it"""
    base = new_dir()
    output_file(base, "bhand", 1200)  # crossed 900 s ago, before the summary
    output_file(base, "bfresh", 800)  # crossed 500 s ago, after the summary
    recs = ([at(prompt("zero"), 2100), at(assistant_text("ok"), 2000), stop_summary(2000),
             at(prompt("first"), 1500)] + stamped(moved("bhand"), 1490) + stamped(moved("bfresh"), 1000)
            + [at(assistant_text("ok"), 850), stop_summary(800), meta_wake("agent report", 700),
               at(assistant_text("ok"), 650)])
    problems, msg = stop_listing(recs, base)
    problems += expect("bhand" not in msg, f"job bhand is listed again after the isMeta hand-back: {msg!r}")
    return problems + listed_once(msg, "bfresh")


@case
def C4_queued_notice_after_a_text_record_does_not_hide_a_stall():
    """C4. a stall that crossed 900 s ago, after the Stop 1200 s ago. Then a text-only assistant record, a queued
    notice for another job, and no Stop since: the Stop now lists the stall"""
    base = new_dir()
    output_file(base, "bearly", 1200)  # crossed 900 s ago
    recs = ([at(prompt("first"), 1500)] + stamped(moved("bearly"), 1490)
            + [at(assistant_text("ok"), 1250), stop_summary(1200), at(prompt("next"), 1000),
               at(assistant_text("working"), 700), at(attachment_notice("bother"), 600),
               at(assistant_text("ok"), 550)])
    problems, msg = stop_listing(recs, base)
    return problems + listed_once(msg, "bearly")


@case
def H1_stall_between_a_blocked_stop_and_its_active_run_is_listed_at_the_next_stop():
    """H1. a Stop at 800 s ago that a hook blocked, the reply, the run at 600 s ago with stop_hook_active true
    (it prints nothing), then a new prompt. A stall that crossed 700 s ago, between the blocked run and the active
    run, is listed at this Stop. A stall that crossed before the blocked run is silent here"""
    base = new_dir()
    output_file(base, "bduring", 1000)  # crossed 700 s ago
    output_file(base, "bbefore", 1300)  # crossed 1000 s ago
    recs = ([at(prompt("first"), 1500)] + stamped(moved("bduring"), 1490) + stamped(moved("bbefore"), 1480)
            + [at(assistant_text("ok"), 850), stop_summary(800, blocked=True),
               meta_wake("Stop hook feedback: send the report now.", 790), at(assistant_text("report"), 650),
               stop_summary(600), at(prompt("next"), 500), at(assistant_text("ok"), 450)])
    problems, msg = stop_listing(recs, base)
    problems += listed_once(msg, "bduring")
    return problems + expect("bbefore" not in msg, f"job bbefore is listed again: {msg!r}")


@case
def C6_stall_between_two_blocked_stops_is_listed_after_a_clean_run():
    """C6. a Stop at 1000 s ago that a hook blocked, its reply, the run at 800 s ago that a hook blocked too, the
    run at 600 s ago that is clean, then a new prompt. A stall that crossed 900 s ago, between the first and the
    second blocked run, is listed at this Stop. A stall that crossed 1100 s ago, before the first blocked run, is
    silent here. A stall that crossed 400 s ago, after the clean run, is listed"""
    base = new_dir()
    output_file(base, "bmid6", 1200)  # crossed 900 s ago
    output_file(base, "bpre6", 1400)  # crossed 1100 s ago
    output_file(base, "bpost6", 700)  # crossed 400 s ago
    recs = ([at(prompt("first"), 1500)] + stamped(moved("bmid6"), 1490) + stamped(moved("bpre6"), 1480)
            + stamped(moved("bpost6"), 1470)
            + [at(assistant_text("ok"), 1050), stop_summary(1000, blocked=True),
               meta_wake("Stop hook feedback: send the report now.", 990), at(assistant_text("report"), 950),
               stop_summary(800, blocked=True), meta_wake("Stop hook feedback: send the report now.", 790),
               at(assistant_text("report"), 750), stop_summary(600),
               at(prompt("next"), 500), at(assistant_text("ok"), 450)])
    problems, msg = stop_listing(recs, base)
    problems += listed_once(msg, "bmid6")
    problems += expect("bpre6" not in msg, f"job bpre6 is listed though its stall crossed before the first blocked Stop: {msg!r}")
    return problems + listed_once(msg, "bpost6")


@case
def C5_newest_summary_with_a_bad_timestamp_fails_open():
    """C5. the newest Stop summary has a timestamp that is not ISO text, and an older summary is readable. The job
    whose stall crossed before the older summary is listed: a bad timestamp lists every quiet job"""
    base = new_dir()
    output_file(base, "bbad", 1800)  # crossed 1500 s ago, before the older summary
    bad = stop_summary(800)
    bad["timestamp"] = "yesterday"
    recs = ([at(prompt("first"), 1600)] + stamped(moved("bbad"), 1590)
            + [at(assistant_text("ok"), 1450), stop_summary(1400), at(assistant_text("ok"), 900), bad,
               at(prompt("next"), 500), at(assistant_text("ok"), 450)])
    problems, msg = stop_listing(recs, base)
    return problems + listed_once(msg, "bbad")


# Background agents. An Agent call started with run_in_background returns an async launch whose
# toolUseResult names the agent id and the outputFile. The agent's own transcript sits beside the
# session file, at <stem>/subagents/agent-<id>.jsonl. Each case builds that layout with transcript(agents=).


def agent_id(n):
    """A 17-character agent id. Every id has the same length, so no id is a part of another."""
    return "a%016x" % (0x51a7e0000 + n)


def agent_path(folder, aid):
    """Where a background agent's transcript sits beside the session file in folder: the folder named
    after the file's stem, then subagents/agent-<id>.jsonl."""
    return os.path.join(folder, "session", "subagents", "agent-%s.jsonl" % aid)


def agent_launch(aid, output, desc="review the diff"):
    """A background agent's launch: its Agent tool_use, then the async result. The result's toolUseResult
    names the agent id and the outputFile."""
    cid = "toolu_" + aid
    use = {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": cid, "name": "Agent",
         "input": {"description": desc, "prompt": "review", "run_in_background": True}}]}}
    result = {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": cid,
         "content": "Async agent launched successfully. agentId: %s." % aid}]},
        "toolUseResult": {"isAsync": True, "status": "async_launched", "agentId": aid,
                          "description": desc, "outputFile": output}}
    return [use, result]


def background_agent(folder, aid, records, idle, output=None):
    """A background agent of the session in folder. Return (launch, spec): the launch records for the
    session's items, and the spec for transcript(agents=). The launch names output when given, else the
    agent's own transcript."""
    return agent_launch(aid, output or agent_path(folder, aid)), (aid, records, idle)


def agent_step(tag, text="done\n"):
    """Agent transcript records that end on a tool_result: the agent's last step has finished."""
    return [call("toolu_" + tag, "ls"), bash_result("toolu_" + tag, text)]


def agent_long_call():
    """Agent transcript records that end on a tool_use with no result: one long call in progress."""
    return [assistant_text("checking the build"), call("toolu_long", "sleep 900")]


def stop_in_process(transcript_path, spies=None):
    """Run the Stop check in this process at NOW, with the default quiet age and no output base. Return
    (rc, stdout, the paths os.stat was called with, the paths open was called with). The wrappers count
    every path the check stats or opens, so a case counts the calls that name one agent.

    spies, when given, is a list that collects each process start, network call and write the check makes.
    Each such call raises, so none runs. A case reads the list after the run."""
    spec = importlib.util.spec_from_file_location("stall_watch_in_process", MODULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    stats, opens = [], []
    real_stat, real_os_open, real_open, real_io_open = os.stat, os.open, builtins.open, io.open
    write_flags = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC

    def counted_stat(path, *args, **kwargs):
        stats.append(str(path))
        return real_stat(path, *args, **kwargs)

    def counted_open(file, mode="r", *args, **kwargs):
        opens.append(str(file))
        if spies is not None and any(c in mode for c in "wax+"):
            spies.append(("write", str(file), mode))
            raise PermissionError("write refused in this check")
        return real_open(file, mode, *args, **kwargs)

    def counted_os_open(path, flags, *args, **kwargs):
        opens.append(str(path))
        if spies is not None and flags & write_flags:
            spies.append(("write", str(path), flags))
            raise PermissionError("write refused in this check")
        return real_os_open(path, flags, *args, **kwargs)

    keys = ("STALL_WATCH_NOW", "STALL_WATCH_OUTPUT_BASE", "STALL_WATCH_QUIET")
    saved = {k: os.environ.get(k) for k in keys}
    payload = {"session_id": "test-stall-watch-stop", "hook_event_name": "Stop", "cwd": SCRATCH,
               "transcript_path": transcript_path, "stop_hook_active": False}
    old_stdin = sys.stdin
    spied = []  # (owner, name, original) of each call the spies stand in for, restored in finally
    try:
        os.environ["STALL_WATCH_NOW"] = str(NOW)
        os.environ.pop("STALL_WATCH_OUTPUT_BASE", None)
        os.environ.pop("STALL_WATCH_QUIET", None)
        sys.stdin = io.StringIO(json.dumps(payload))
        os.stat, os.open, builtins.open, io.open = counted_stat, counted_os_open, counted_open, counted_open
        if spies is not None:
            spy_calls(spies, spied)
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            rc = mod.stop()
        return rc, buf.getvalue(), stats, opens
    finally:
        os.stat, os.open, builtins.open, io.open = real_stat, real_os_open, real_open, real_io_open
        unspy_calls(spied)
        sys.stdin = old_stdin
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@case
def A1_quiet_agent_is_listed_once_with_its_remedy():
    """A1. a background agent whose transcript has not changed for 600 s, after 300 earlier steps, its last
    record a tool_result: listed once, by its id, with the remedy: resume it by name, or send a fresh
    reviewer the prior report"""
    folder = new_dir()
    many = []
    for i in range(300):
        many += agent_step("s%d" % i)
    launch, spec = background_agent(folder, agent_id(1), many + agent_step("last"), 600)
    path = transcript(stamped(launch, 900), agents=[spec], folder=folder)
    rc, out, err = run_stop(path)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += listed_once(msg, agent_id(1), by_line=True)
    if problems:  # the remedy is read from a listing: with no listing, there is no remedy to check
        return problems
    low = msg.lower()
    for word in ("resume", "by name", "fresh reviewer", "prior report"):
        problems += expect(word in low, f"the remedy has no {word!r}: {msg!r}")
    return problems


@case
def A1b_quiet_agent_whose_result_quotes_a_tool_use_is_listed():
    """A1b. a quiet agent whose last record is a tool_result whose text quotes a tool_use record: listed once.
    A check that reads the text for a tool_use takes it for one long call and does not list the agent"""
    folder = new_dir()
    quoted = '{"type":"tool_use","id":"toolu_zz","name":"Bash","input":{"command":"sleep 900"}}'
    launch, spec = background_agent(folder, agent_id(2), agent_step("q1", quoted), 600)
    path = transcript(stamped(launch, 900), agents=[spec], folder=folder)
    rc, out, err = run_stop(path)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += listed_once(msg, agent_id(2), by_line=True)
    return problems


@case
def A1c_quiet_agent_with_a_huge_last_record_is_listed():
    """A1c. a quiet agent whose last record is a 300 KB tool_result: listed once. A tail read that gives up
    on a long last line never reaches the record, so the agent is not listed"""
    folder = new_dir()
    launch, spec = background_agent(folder, agent_id(3), agent_step("big", "x" * 300000), 600)
    path = transcript(stamped(launch, 900), agents=[spec], folder=folder)
    rc, out, err = run_stop(path)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += listed_once(msg, agent_id(3), by_line=True)
    return problems


@case
def A2_fresh_agent_is_not_listed():
    """A2. an agent whose transcript changed 10 s ago is not listed. Control: a quiet agent beside it is listed,
    so the check ran"""
    folder = new_dir()
    lf, fresh = background_agent(folder, agent_id(4), agent_step("f1"), 10)
    lc, ctl = background_agent(folder, agent_id(5), agent_step("c1"), 600)
    path = transcript(stamped(lf + lc, 900), agents=[fresh, ctl], folder=folder)
    rc, out, err = run_stop(path)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += listed_once(msg, agent_id(5), by_line=True)
    problems += expect(agent_id(4) not in msg, f"fresh agent {agent_id(4)} is listed: {msg!r}")
    return problems


@case
def A3a_completed_notice_drops_the_agent():
    """A3a. a completed notice, as a queued_command attachment, drops its agent. Control: a quiet agent
    with no notice is listed"""
    folder = new_dir()
    ld, done = background_agent(folder, agent_id(6), agent_step("d1"), 600)
    lc, ctl = background_agent(folder, agent_id(7), agent_step("c1"), 600)
    recs = (stamped(ld + lc, 900)
            + [attachment_notice(agent_id(6), "completed", summary='Agent "review the diff" completed')])
    path = transcript(recs, agents=[done, ctl], folder=folder)
    rc, out, err = run_stop(path)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += listed_once(msg, agent_id(7), by_line=True)
    problems += expect(agent_id(6) not in msg, f"agent {agent_id(6)} has a completed notice but is listed: {msg!r}")
    return problems


@case
def A3b_task_stop_result_drops_the_agent():
    """A3b. a TaskStop result that says 'Successfully stopped task: <id>' drops its agent. Control: a quiet
    agent with no stop is listed"""
    folder = new_dir()
    ls_, stopped = background_agent(folder, agent_id(8), agent_step("s1"), 600)
    lc, ctl = background_agent(folder, agent_id(9), agent_step("c1"), 600)
    recs = (stamped(ls_ + lc, 900)
            + [stop_call("toolu_ts1", agent_id(8)),
               stop_result("toolu_ts1", agent_id(8), command="review the diff")])
    path = transcript(recs, agents=[stopped, ctl], folder=folder)
    rc, out, err = run_stop(path)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += listed_once(msg, agent_id(9), by_line=True)
    problems += expect(agent_id(8) not in msg, f"agent {agent_id(8)} was stopped but is listed: {msg!r}")
    return problems


@case
def A4_quiet_agent_in_one_long_call_is_not_listed():
    """A4. a quiet agent whose last record is a tool_use with no result, one long call in progress: not listed.
    Control: a quiet agent whose last record is a tool_result is listed"""
    folder = new_dir()
    lw, wait = background_agent(folder, agent_id(10), agent_long_call(), 600)
    lc, ctl = background_agent(folder, agent_id(11), agent_step("c1"), 600)
    path = transcript(stamped(lw + lc, 900), agents=[wait, ctl], folder=folder)
    rc, out, err = run_stop(path)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += listed_once(msg, agent_id(11), by_line=True)
    problems += expect(agent_id(10) not in msg, f"agent {agent_id(10)} in one long call is listed: {msg!r}")
    return problems


@case
def A5_dead_windows_output_file_still_finds_the_agent_beside_the_session():
    """A5. a quiet agent whose launch names a Windows outputFile that does not exist here: the agent is found
    beside the session file and listed, not as unknown"""
    folder = new_dir()
    launch, spec = background_agent(folder, agent_id(12), agent_step("w1"), 600, output=win_path(agent_id(12)))
    path = transcript(stamped(launch, 900), agents=[spec], folder=folder)
    rc, out, err = run_stop(path)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += listed_once(msg, agent_id(12), by_line=True)
    problems += expect("unknown" not in line_of(msg, agent_id(12)),
                       f"agent {agent_id(12)} is listed as unknown: {msg!r}")
    return problems


@case
def A6_agent_with_no_transcript_is_unknown_at_the_first_stop_only():
    """A6. a background agent whose transcript is missing both at its outputFile and beside the session:
    listed as unknown at the first Stop after its launch, and not at the next. Control: an agent launched
    after that Stop is listed as unknown at the next one"""
    turn0 = [at(prompt("first"), 1500), at(assistant_text("first answer"), 1300), stop_summary(1300)]
    lu = agent_launch(agent_id(13), win_path(agent_id(13)))
    turn1 = [at(prompt("start"), 1200)] + stamped(lu, 1000) + [at(assistant_text("started"), 600)]
    rc1, out1, err1 = run_stop(transcript(turn0 + turn1), now=NOW - 600)
    problems = expect(rc1 == 0, f"first Stop exit {rc1}, want 0: {err1.strip()[:200]}")
    msg1 = system_message(out1, problems)
    problems += listed_once(msg1, agent_id(13), by_line=True)
    problems += expect("unknown" in line_of(msg1, agent_id(13)),
                       f"agent {agent_id(13)} is not listed as unknown: {msg1!r}")
    lc = agent_launch(agent_id(14), win_path(agent_id(14)))
    turn2 = [stop_summary(600), at(prompt("next"), 550)] + stamped(lc, 500) + [at(assistant_text("ok"), 400)]
    rc2, out2, err2 = run_stop(transcript(turn0 + turn1 + turn2))
    problems += expect(rc2 == 0, f"second Stop exit {rc2}, want 0: {err2.strip()[:200]}")
    msg2 = system_message(out2, problems)
    problems += listed_once(msg2, agent_id(14), by_line=True)
    problems += expect("unknown" in line_of(msg2, agent_id(14)),
                       f"agent {agent_id(14)} is not listed as unknown at the second Stop: {msg2!r}")
    problems += expect(agent_id(13) not in msg2,
                       f"unknown agent {agent_id(13)} is listed again at the second Stop: {msg2!r}")
    return problems


@case
def A7_quiet_agent_is_listed_once_per_crossing():
    """A7. a quiet agent whose stall crossed after the previous Stop is listed at the next Stop, and not again
    at the one after, as for a shell job. Control: an agent that goes quiet after that Stop is listed at the
    second one"""
    folder = new_dir()
    lx, x = background_agent(folder, agent_id(15), agent_step("x1"), 1400)  # quiet since 1400 s before NOW
    turn0 = ([at(prompt("first"), 1500)] + stamped(lx, 1490)
             + [at(assistant_text("first answer"), 1200), stop_summary(1200)])
    turn1 = [at(prompt("start"), 1000), at(assistant_text("started"), 900)]
    rc1, out1, err1 = run_stop(transcript(turn0 + turn1, agents=[x], folder=folder), now=NOW - 900)
    problems = expect(rc1 == 0, f"first Stop exit {rc1}, want 0: {err1.strip()[:200]}")
    msg1 = system_message(out1, problems)
    problems += listed_once(msg1, agent_id(15), by_line=True)
    lc, ctl = background_agent(folder, agent_id(16), agent_step("c1"), 600)  # quiet since 600 s before NOW
    turn2 = [stop_summary(900), at(prompt("next"), 800)] + stamped(lc, 800) + [at(assistant_text("ok"), 700)]
    rc2, out2, err2 = run_stop(transcript(turn0 + turn1 + turn2, agents=[ctl], folder=folder))
    problems += expect(rc2 == 0, f"second Stop exit {rc2}, want 0: {err2.strip()[:200]}")
    msg2 = system_message(out2, problems)
    problems += listed_once(msg2, agent_id(16), by_line=True)
    problems += expect(agent_id(15) not in msg2, f"agent {agent_id(15)} is listed again at the second Stop: {msg2!r}")
    return problems


@case
def A8_cost_one_stat_per_running_agent_and_a_read_only_when_quiet():
    """A8. the cost of the agent check, run in this process: each running agent is stat'ed once per Stop, a
    fresh agent is not opened, and a quiet agent is read. Scope first: the session file was opened and the
    quiet agent was read, so the counts below come from the agent check"""
    folder = new_dir()
    lf, fresh = background_agent(folder, agent_id(17), agent_step("f1"), 10)
    lq, quiet = background_agent(folder, agent_id(18), agent_step("q1"), 600)
    path = transcript(stamped(lf + lq, 900), agents=[fresh, quiet], folder=folder)
    rc, out, stats, opens = stop_in_process(path)
    problems = expect(rc == 0, f"exit {rc}, want 0")
    problems += expect(any(os.path.basename(p) == "session.jsonl" for p in opens),
                       f"stop() did not open the session transcript, so nothing was scanned: opens {opens}")
    problems += expect(any(agent_id(18) in p for p in opens),
                       f"the quiet agent {agent_id(18)} was not read (scope): opens {opens}")
    fresh_stats = sum(agent_id(17) in p for p in stats)
    problems += expect(fresh_stats == 1, f"fresh agent {agent_id(17)} stat count {fresh_stats}, want 1: {stats}")
    problems += expect(sum(agent_id(17) in p for p in opens) == 0,
                       f"fresh agent {agent_id(17)} was opened: {opens}")
    quiet_stats = sum(agent_id(18) in p for p in stats)
    problems += expect(quiet_stats == 1, f"quiet agent {agent_id(18)} stat count {quiet_stats}, want 1: {stats}")
    return problems


@case
def A9_shell_job_and_agent_share_one_message():
    """A9. a quiet shell job and a quiet agent in one transcript: both are listed in one systemMessage. The
    shell row is green on main, so it is the control for the agent row"""
    base, folder = new_dir(), new_dir()
    output_file(base, "bmix600", 600)
    launch, spec = background_agent(folder, agent_id(19), agent_step("m1"), 600)
    path = transcript(moved("bmix600") + stamped(launch, 900), agents=[spec], folder=folder)
    rc, out, err = run_stop(path, base)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += listed_once(msg, "bmix600")
    problems += listed_once(msg, agent_id(19), by_line=True)
    return problems


@case
def A10_full_size_each_quiet_agent_is_listed_once():
    """A10. thirty quiet agents at once: each is listed once, by its own id"""
    folder = new_dir()
    launches, specs, ids = [], [], []
    for n in range(30):
        aid = agent_id(100 + n)
        ids.append(aid)
        launch, spec = background_agent(folder, aid, agent_step("t%d" % n), 600)
        launches += launch
        specs.append(spec)
    path = transcript(stamped(launches, 900), agents=specs, folder=folder)
    rc, out, err = run_stop(path)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    for aid in ids:
        problems += listed_once(msg, aid, by_line=True)
    return problems


# ---- The CI-wait check of this mode (decision ci-wait-reads-run-status, "The fallback") ----
# A wait opens at the newest ready call and closes at a green or cancelled verdict, or a merge or close of its own
# PR. A wait that a bare ready call opens (no PR number) closes at a merge or close of any PR. A red verdict keeps
# it open. A check-in after the anchor (the newest ready call or red verdict) passes it, unless its result is an
# error. An unknown verdict closes nothing. The check reads the records in file order, so no fixture carries a time.

CI_PR = "4217"  # no sha, path or fixture id holds this number as a whole token, so \b4217\b names the PR alone
CI_OTHER_PR = "1111"
CI_SHA = "9f8e7d6"
CI_OWNER, CI_REPO = "example-org", "example-repo"
MCP_READY = "mcp__github__update_pull_request"
MCP_MERGE = "mcp__github__merge_pull_request"
SEND_LATER = "mcp__claude-code-remote__send_later"
CREATE_TRIGGER = "mcp__claude-code-remote__create_trigger"
CHECKIN_TOOLS = (SEND_LATER, CREATE_TRIGGER, "CronCreate", "ScheduleWakeup")
GREEN = "CI green on %s: no failing jobs" % CI_SHA
RED = "CI red on %s: lint, unit" % CI_SHA
CANCELLED = "CI cancelled on %s: build" % CI_SHA
UNKNOWN = "CI unknown on %s: still running" % CI_SHA
CALL_IDS = itertools.count(1)
# Each call that starts a process, opens a network socket or writes a file. The cost case stands each in for a
# recorder, so a check that makes one is named.
SPIED_CALLS = (
    (subprocess, "Popen", "process"), (subprocess, "run", "process"), (subprocess, "call", "process"),
    (subprocess, "check_call", "process"), (subprocess, "check_output", "process"),
    (os, "system", "process"), (os, "popen", "process"),
    (socket, "socket", "network"), (socket, "create_connection", "network"),
    (os, "remove", "write"), (os, "unlink", "write"), (os, "rename", "write"), (os, "replace", "write"),
    (os, "mkdir", "write"), (os, "makedirs", "write"), (os, "rmdir", "write"), (os, "utime", "write"),
    (os, "chmod", "write"),
)


def spy_calls(spies, spied):
    """Stand in for each SPIED_CALLS entry: it records itself in spies and raises. Each original goes in spied."""
    def refuse(kind):
        def fn(*args, **kwargs):
            spies.append((kind, repr(args)[:120]))
            raise PermissionError("%s refused in this check" % kind)
        return fn
    for owner, name, kind in SPIED_CALLS:
        spied.append((owner, name, getattr(owner, name)))
        setattr(owner, name, refuse(kind))


def unspy_calls(spied):
    """Put back each original that spy_calls stood in for."""
    for owner, name, real in spied:
        setattr(owner, name, real)


def cid():
    """A tool_use id no other call in the fixture has."""
    return "toolu_ci%03d" % next(CALL_IDS)


def ready(number=CI_PR, command=None):
    """A Bash call of `gh pr ready <number>`, or of command when given."""
    return call(cid(), command or "gh pr ready %s" % number, desc="Mark the PR ready")


def tool_call(name, inp):
    """An assistant call of any tool, with its input."""
    return {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": cid(), "name": name, "input": inp}]}}


def mcp_pr(name, number=CI_PR, **fields):
    """A GitHub MCP call that names one PR. The fields add draft, or leave it out for an absent draft."""
    return tool_call(name, dict({"owner": CI_OWNER, "repo": CI_REPO, "pullNumber": int(number)}, **fields))


def checkin(name):
    """A later call of one of the tools that set a check-in."""
    return tool_call(name, {"message": "CI check on PR %s" % CI_PR})


def checkin_answered(name, is_error):
    """A check-in call and its result, in file order. An error result carries its text as toolUseResult, as a
    failed call does in a transcript."""
    call_rec = checkin(name)
    call_id = call_rec["message"]["content"][0]["id"]
    text = "send_later failed: no session" if is_error else "scheduled"
    return [call_rec, tool_result(call_id, text, is_error=is_error, tool_use_result=text)]


def merge_bin(number=CI_PR, cmd="bin/merge", confirm=True):
    """A Bash call of the merge tool: cmd (bin/merge, or the bare merge command) with the PR number, and
    --confirm when confirm is true."""
    words = [cmd, str(number)] + (["--confirm"] if confirm else [])
    return call(cid(), " ".join(words), desc="Merge the PR")


def shell(command):
    """A Bash call of command, with no result."""
    return call(cid(), command)


def queued(text):
    """A verdict as a queued_command attachment record, the other form a notice takes."""
    return {"type": "attachment", "attachment": {"type": "queued_command", "prompt": text}}


def text_blocks(text):
    """A user message whose content is a list of text blocks."""
    return {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": text}]}}


def ci_run(source, stop_hook_active=False, base=None):
    """Run the Stop check on a transcript, given as a list of records or as a path. Return (problems, stdout)."""
    path = source if isinstance(source, str) else transcript(source)
    rc, out, err = run_stop(path, base, stop_hook_active=stop_hook_active)
    return expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}"), out


def block_reason(out, problems):
    """The reason of the one JSON line a block prints. None, with a problem added, when the output is not
    one block line."""
    lines = out.strip().splitlines()
    if len(lines) != 1:
        problems.append(f"stop output is not one line: {out[:200]!r}")
        return None
    try:
        body = json.loads(lines[0])
    except ValueError:
        problems.append(f"stop output is not JSON: {out[:200]!r}")
        return None
    if not isinstance(body, dict) or body.get("decision") != "block" or not isinstance(body.get("reason"), str):
        problems.append(f"stop output is not a block with a reason: {out[:200]!r}")
        return None
    return body["reason"]


def expect_block(source, pr=CI_PR, not_named=(), base=None, stop_hook_active=False):
    """The check prints one block that tells the session to set a send_later check-in and names pr. pr None: the
    wait names no PR number, so the reason is not checked for one. No number in not_named appears in the reason."""
    problems, out = ci_run(source, stop_hook_active, base)
    if out.strip() == "":
        return problems + ["no CI block printed, want one%s" % ("" if pr is None else f" naming PR {pr}")]
    reason = block_reason(out, problems)
    if reason is None:
        return problems
    problems += expect("send_later" in reason, f"block reason does not say to set a send_later check-in: {reason!r}")
    if pr is not None:
        problems += expect(re.search(r"\b%s\b" % pr, reason) is not None,
                           f"block reason does not name PR {pr}: {reason!r}")
    for other in not_named:
        problems += expect(re.search(r"\b%s\b" % other, reason) is None,
                           f"block reason names PR {other}, which has a closed wait: {reason!r}")
    return problems


def expect_silent(source, stop_hook_active=False, base=None):
    """The check prints nothing."""
    problems, out = ci_run(source, stop_hook_active, base)
    return problems + expect(out.strip() == "", f"the CI check printed where it should be silent: {out[:200]!r}")


def silent_with_control(source, control, stop_hook_active=False, pr=CI_PR):
    """source prints nothing about the CI wait. control, the same session with the closer left out or a ready
    call added, must block, and name pr. The control shows the check is live, so a mode that is absent or silent
    everywhere fails here too."""
    return expect_silent(source, stop_hook_active) + ["control: " + p for p in expect_block(control, pr=pr)]


@case
def CI01_no_ready_call_prints_nothing():
    """CI01. no ready call: plain Bash calls open no wait. Control: the same session with a ready call blocks"""
    c = cid()
    items = [prompt("check the tree"), call(c, "git status", desc="status"), bash_result(c, "clean")]
    return silent_with_control(items, items + [ready()])


@case
def CI02_ready_without_checkin_blocks_and_names_the_pr():
    """CI02. a ready call with no check-in after it blocks, and the reason names the PR"""
    return expect_block([prompt("merge when green"), ready()])


@case
def CI03_ready_then_send_later_passes():
    """CI03. ready, then a send_later check-in: passes. Control: ready with no check-in blocks"""
    return silent_with_control([ready(), checkin(SEND_LATER)], [ready()])


@case
def CI04_ready_then_create_trigger_passes():
    """CI04. ready, then a create_trigger check-in: passes. Control: ready with no check-in blocks"""
    return silent_with_control([ready(), checkin(CREATE_TRIGGER)], [ready()])


@case
def CI05_ready_then_croncreate_passes():
    """CI05. ready, then a CronCreate check-in: passes. Control: ready with no check-in blocks"""
    return silent_with_control([ready(), checkin(CHECKIN_TOOLS[2])], [ready()])


@case
def CI06_ready_then_schedulewakeup_passes():
    """CI06. ready, then a ScheduleWakeup check-in: passes. Control: ready with no check-in blocks"""
    return silent_with_control([ready(), checkin(CHECKIN_TOOLS[3])], [ready()])


@case
def CI07_ready_then_green_verdict_passes():
    """CI07. ready, then a user message with a green verdict line: passes. Control: ready with no verdict blocks"""
    return silent_with_control([ready(), prompt(GREEN)], [ready()])


@case
def CI08_ready_then_red_verdict_without_checkin_blocks():
    """CI08. ready, then a red verdict and no check-in: the red verdict re-opens the wait, so it blocks"""
    return expect_block([ready(), prompt(RED)])


@case
def CI09_red_verdict_then_checkin_passes():
    """CI09. ready, a red verdict, then a send_later check-in: passes. Control: the red verdict alone blocks"""
    return silent_with_control([ready(), prompt(RED), checkin(SEND_LATER)], [ready(), prompt(RED)])


@case
def CI10_second_red_after_a_checkin_blocks():
    """CI10. a second red verdict after the check-in re-opens the wait again, so it blocks. Control: the first
    red and its check-in pass"""
    items = [ready(), prompt(RED), checkin(SEND_LATER), prompt(RED)]
    return expect_block(items) + ["control: " + p for p in expect_silent(items[:3])]


@case
def CI11_checkin_before_the_ready_call_does_not_count():
    """CI11. a check-in made before the newest ready call does not cover it, so it blocks. Control: the same
    two calls in the other order pass"""
    return expect_block([checkin(SEND_LATER), ready()]) + [
        "control: " + p for p in expect_silent([ready(), checkin(SEND_LATER)])]


@case
def CI12_checkin_for_an_older_ready_does_not_cover_a_newer_one():
    """CI12. a check-in after an older ready call does not cover the newest one: it blocks, and the reason names
    the newest PR only. Control: a check-in after the newest ready call passes"""
    items = [ready(CI_OTHER_PR), checkin(SEND_LATER), ready(CI_PR)]
    return expect_block(items, not_named=[CI_OTHER_PR]) + [
        "control: " + p for p in expect_silent(items + [checkin(SEND_LATER)])]


@case
def CI13_green_verdict_closes_an_older_ready_only():
    """CI13. a green verdict closes the older wait, and the newest ready call is still open: it blocks, and the
    reason names the newest PR only. Control: the newest wait closed by its own green verdict passes"""
    items = [ready(CI_OTHER_PR), prompt(GREEN), ready(CI_PR)]
    return expect_block(items, not_named=[CI_OTHER_PR]) + [
        "control: " + p for p in expect_silent(items + [prompt(GREEN)])]


@case
def CI14_cancelled_verdict_closes_the_wait():
    """CI14. ready, then a cancelled verdict: passes. Control: ready with no verdict blocks"""
    return silent_with_control([ready(), prompt(CANCELLED)], [ready()])


@case
def CI15_unknown_verdict_leaves_the_wait_open():
    """CI15. ready, then a CI unknown verdict (still running): nothing wakes the session, so the wait stays open
    and blocks, and the reason names the PR. Control: ready, then a green verdict, passes"""
    return ["unknown verdict: " + p for p in expect_block([ready(), prompt(UNKNOWN)])] + [
        "control: " + p for p in expect_silent([ready(), prompt(GREEN)])]


@case
def CI16_verdict_before_the_ready_call_does_not_close_it():
    """CI16. a verdict made before the ready call closes nothing, so it blocks. Control: the verdict after the
    ready call passes"""
    return expect_block([prompt(GREEN), ready()]) + [
        "control: " + p for p in expect_silent([ready(), prompt(GREEN)])]


@case
def CI17_verdict_in_a_queued_command_closes_the_wait():
    """CI17. ready, then a verdict that arrives as a queued_command attachment: passes. Control: ready with no
    verdict blocks"""
    return silent_with_control([ready(), queued(GREEN)], [ready()])


@case
def CI18_verdict_in_a_text_block_list_closes_the_wait():
    """CI18. ready, then a user message whose content is a list of text blocks holding a verdict: passes.
    Control: ready with no verdict blocks"""
    return silent_with_control([ready(), text_blocks(GREEN)], [ready()])


@case
def CI19_verdict_on_its_own_line_in_a_longer_message_closes_the_wait():
    """CI19. ready, then a user message that holds a verdict on its own line: passes. Control: ready with no
    verdict blocks"""
    return silent_with_control([ready(), prompt("CI wake for the PR:\n%s\nsee the run" % GREEN)], [ready()])


@case
def CI20_assistant_text_quoting_a_verdict_closes_nothing():
    """CI20. the assistant quotes a green verdict line in its own text, so it blocks: only a user or queued
    message closes the wait. Control: the same line as a user message passes"""
    return expect_block([ready(), assistant_text(GREEN)]) + [
        "control: " + p for p in expect_silent([ready(), prompt(GREEN)])]


@case
def CI21_tool_result_printing_a_verdict_closes_nothing():
    """CI21. a Bash result that prints a verdict line closes nothing, so it blocks. Control: the same line as a
    user message passes"""
    c = cid()
    items = [ready(), call(c, "cat wake.log", desc="read the log"), bash_result(c, GREEN)]
    return expect_block(items) + ["control: " + p for p in expect_silent([ready(), prompt(GREEN)])]


def closer_pair(own, other, label):
    """A merge or close that names the waited PR closes the wait, so the check is silent. The same call naming
    another PR closes nothing, so it blocks, and the reason names only the waited PR. label names the form in
    each problem."""
    return (["%s of the waited PR: %s" % (label, p) for p in expect_silent([ready(), own])]
            + ["%s of another PR: %s" % (label, p)
               for p in expect_block([ready(), other], not_named=[CI_OTHER_PR])])


@case
def CI22_mcp_merge_closes_the_wait_only_for_its_own_pr():
    """CI22. a GitHub MCP merge_pull_request closes the wait only when it names the waited PR. Another PR's merge
    blocks, and the reason names only the waited PR. Control: the merge of the waited PR passes"""
    return closer_pair(mcp_pr(MCP_MERGE), mcp_pr(MCP_MERGE, CI_OTHER_PR), "GitHub MCP merge")


@case
def CI23_bin_merge_closes_the_wait_only_for_its_own_pr():
    """CI23. bin/merge closes the wait only when it names the waited PR. Another PR's merge blocks, and the reason
    names only the waited PR. Control: bin/merge of the waited PR passes"""
    return closer_pair(merge_bin(), merge_bin(CI_OTHER_PR), "bin/merge")


@case
def CI24_fresh_ready_after_red_then_green_passes():
    """CI24. ready, a red verdict, a fresh ready call, then a green verdict: passes. Control: the fresh ready
    call with no verdict blocks"""
    return silent_with_control([ready(), prompt(RED), ready(), prompt(GREEN)], [ready(), prompt(RED), ready()])


@case
def CI25_mcp_ready_draft_false_blocks():
    """CI25. a GitHub MCP update_pull_request with draft false is a ready call, so it blocks and names the PR"""
    return expect_block([mcp_pr(MCP_READY, draft=False)])


@case
def CI26_mcp_ready_draft_true_starts_no_wait():
    """CI26. an MCP update_pull_request with draft true starts no wait. Control: draft false blocks"""
    return silent_with_control([mcp_pr(MCP_READY, draft=True)], [mcp_pr(MCP_READY, draft=False)])


@case
def CI27_mcp_ready_draft_absent_starts_no_wait():
    """CI27. an MCP update_pull_request with no draft key starts no wait. Control: draft false blocks"""
    return silent_with_control([mcp_pr(MCP_READY)], [mcp_pr(MCP_READY, draft=False)])


@case
def CI28_mcp_ready_then_checkin_passes():
    """CI28. an MCP ready call, then a send_later check-in: passes. Control: the MCP ready call alone blocks"""
    return silent_with_control([mcp_pr(MCP_READY, draft=False), checkin(SEND_LATER)],
                               [mcp_pr(MCP_READY, draft=False)])


@case
def CI29_powershell_ready_blocks():
    """CI29. a PowerShell call of gh pr ready is a ready call, so it blocks and names the PR"""
    return expect_block([tool_call("PowerShell", {"command": "gh pr ready %s" % CI_PR,
                                                  "description": "Mark the PR ready"})])


@case
def CI30_ready_with_undo_starts_no_wait():
    """CI30. gh pr ready --undo turns a PR back to draft, so it starts no wait. Control: the plain ready call blocks"""
    return silent_with_control([ready(command="gh pr ready %s --undo" % CI_PR)], [ready()])


@case
def CI31_ready_in_double_quotes_is_not_a_ready_call():
    """CI31. gh pr ready inside double quotes is text, so it starts no wait. Control: the plain ready call blocks"""
    return silent_with_control([ready(command='echo "gh pr ready %s"' % CI_PR)], [ready()])


@case
def CI32_ready_in_single_quotes_is_not_a_ready_call():
    """CI32. gh pr ready inside single quotes is text, so it starts no wait. Control: the plain ready call blocks"""
    return silent_with_control([ready(command="echo 'gh pr ready %s'" % CI_PR)], [ready()])


@case
def CI33_ready_in_a_heredoc_body_is_not_a_ready_call():
    """CI33. gh pr ready in a heredoc body is text, so it starts no wait. Control: the plain ready call blocks"""
    return silent_with_control([ready(command="cat > notes.md <<'EOF'\ngh pr ready %s\nEOF" % CI_PR)], [ready()])


@case
def CI34_ready_after_a_hash_comment_is_not_a_ready_call():
    """CI34. gh pr ready after a # comment is a comment, so it starts no wait. Control: the plain ready call blocks"""
    return silent_with_control([ready(command="ls -la  # gh pr ready %s" % CI_PR)], [ready()])


@case
def CI35_ready_in_multi_line_quoted_text_is_not_a_ready_call():
    """CI35. gh pr ready on a middle line of a quoted string is text, so it starts no wait. Control: the plain
    ready call blocks"""
    return silent_with_control([ready(command='echo "first line\ngh pr ready %s\nlast line"' % CI_PR)], [ready()])


@case
def CI36_ready_in_assistant_prose_is_not_a_ready_call():
    """CI36. the assistant names gh pr ready in its text, not as a call, so it starts no wait. Control: the same
    session with a ready call blocks"""
    return silent_with_control([assistant_text("Next I will run gh pr ready %s." % CI_PR)], [ready()])


@case
def CI37_hash_inside_quotes_does_not_hide_a_ready_call():
    """CI37. a # inside quotes does not hide a real ready call after it: blocks"""
    return expect_block([ready(command='echo "# not a comment" && gh pr ready %s' % CI_PR)])


@case
def CI38_lone_apostrophe_does_not_hide_a_ready_call():
    """CI38. a lone apostrophe in an earlier word does not hide a real ready call after it: blocks"""
    return expect_block([ready(command="echo don't; gh pr ready %s" % CI_PR)])


@case
def CI39_ready_after_git_push_in_one_command_blocks():
    """CI39. a ready call chained after git push in one command is a real ready call: blocks"""
    return expect_block([ready(command="git push origin HEAD && gh pr ready %s" % CI_PR)])


@case
def CI40_stop_hook_active_prints_nothing_for_an_open_wait():
    """CI40. stop_hook_active true: the open wait prints nothing. Control: the same session with the flag false
    blocks"""
    items = [ready()]
    return silent_with_control(items, items, stop_hook_active=True)


@case
def CI41_missing_transcript_prints_nothing():
    """CI41. a transcript path with no file prints nothing. Control: a readable transcript with an open wait
    blocks"""
    return silent_with_control(os.path.join(new_dir(), "session.jsonl"), [ready()])


@case
def CI42_garbage_transcript_prints_nothing():
    """CI42. a transcript of garbage bytes and a truncated record prints nothing. Control: a readable transcript
    with an open wait blocks"""
    garbage = [b"\x00\xff not a record\n", b"{{{\n", b'{"type": "assistant", "message": ']
    return silent_with_control(garbage, [ready()])


@case
def CI43_empty_transcript_prints_nothing():
    """CI43. an empty transcript file prints nothing. Control: a readable transcript with an open wait blocks"""
    return silent_with_control([], [ready()])


@case
def CI44_transcript_path_that_is_a_folder_prints_nothing():
    """CI44. a transcript path that names a folder is unreadable, so it prints nothing. Control: a readable
    transcript with an open wait blocks"""
    return silent_with_control(new_dir(), [ready()])


@case
def CI45_full_size_session_blocks_and_names_only_the_newest():
    """CI45. full size: 2000 text records, then 30 PRs each closed by a green verdict, then one open ready call.
    It blocks and names only the open PR. Control: the same session without the open ready call is silent"""
    items = [prompt("start")] + [assistant_text("step %d" % n) for n in range(2000)]
    for i in range(30):
        items += [ready(str(1000 + i)), prompt(GREEN)]
    items.append(ready())
    closed = [str(1000 + i) for i in range(30)]
    return expect_block(items, not_named=closed) + ["control: " + p for p in expect_silent(items[:-1])]


@case
def CI46_open_wait_and_quiet_job_print_one_block_line():
    """CI46. an open wait and a quiet background job: one line is printed, the block, and it names the PR.
    Control: the quiet job alone is listed, so both results apply"""
    base = new_dir()
    output_file(base, "bci600", 600)
    problems = expect_block(moved("bci600") + [ready()], base=base)
    rc, out, err = run_stop(transcript(moved("bci600")), base)
    ctl = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    ctl += listed_once(system_message(out, ctl), "bci600")
    return problems + ["control: " + p for p in ctl]


@case
def CI47_closed_wait_and_quiet_job_print_the_system_message_only():
    """CI47. a closed wait and a quiet background job: the systemMessage lists the job, and no block is printed.
    This is the green control for CI46"""
    base = new_dir()
    output_file(base, "bci601", 600)
    rc, out, err = run_stop(transcript(moved("bci601") + [ready(), prompt(GREEN)]), base)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += listed_once(msg, "bci601")
    problems += expect("decision" not in out, f"a closed wait printed a block: {out[:200]!r}")
    return problems


@case
def CI48_check_reads_only_the_transcript():
    """CI48. cost: the CI check starts no process, opens no network and writes no file, and it reads no file but
    the transcript. Scope first: the transcript was opened, and the check blocked, so the calls counted below
    come from the check"""
    folder = new_dir()
    path = transcript([prompt("merge when green"), ready()], folder=folder)
    spies = []
    rc, out, stats, opens = stop_in_process(path, spies)
    problems = expect(any(os.path.basename(p) == "session.jsonl" for p in opens),
                      f"scope: stop() did not open the session transcript: opens {opens}")
    problems += expect(rc == 0, f"exit {rc}, want 0")
    if out.strip() == "":
        problems.append("no CI block printed, so the cost is not measured on the check")
    else:
        block_reason(out, problems)
    problems += expect(spies == [], f"the CI check made calls it must not make: {spies}")
    stray = [p for p in opens if p.startswith(folder) and os.path.basename(p) != "session.jsonl"]
    problems += expect(stray == [], f"the CI check read files other than the transcript: {stray}")
    return problems


@case
def CI49_gh_pr_merge_closes_the_wait_only_for_its_own_pr():
    """CI49. gh pr merge in Bash closes the wait only when it names the waited PR. Another PR's merge blocks, and
    the reason names only the waited PR. Control: the merge of the waited PR passes"""
    return closer_pair(shell("gh pr merge %s --squash --delete-branch" % CI_PR),
                       shell("gh pr merge %s --squash" % CI_OTHER_PR), "gh pr merge")


@case
def CI50_gh_pr_close_closes_the_wait_only_for_its_own_pr():
    """CI50. gh pr close in Bash closes the wait only when it names the waited PR. Another PR's close blocks, and
    the reason names only the waited PR. Control: the close of the waited PR passes"""
    return closer_pair(shell("gh pr close %s" % CI_PR), shell("gh pr close %s" % CI_OTHER_PR), "gh pr close")


@case
def CI51_powershell_gh_pr_merge_closes_the_wait_only_for_its_own_pr():
    """CI51. a PowerShell gh pr merge closes the wait only when it names the waited PR. Another PR's merge blocks,
    and the reason names only the waited PR. Control: the merge of the waited PR passes"""
    def ps(number):
        return tool_call("PowerShell", {"command": "gh pr merge %s --squash" % number, "description": "Merge the PR"})
    return closer_pair(ps(CI_PR), ps(CI_OTHER_PR), "PowerShell gh pr merge")


@case
def CI52_gh_pr_merge_in_quotes_closes_nothing():
    """CI52. gh pr merge inside double or single quotes is text, so it blocks. Control: the real merge of the
    waited PR passes"""
    problems = []
    for template, label in (('echo "gh pr merge %s"', "double quotes"), ("echo 'gh pr merge %s'", "single quotes")):
        problems += ["%s: %s" % (label, p) for p in expect_block([ready(), shell(template % CI_PR)])]
    problems += ["real merge (control): " + p
                 for p in expect_silent([ready(), shell("gh pr merge %s" % CI_PR)])]
    return problems


@case
def CI53_gh_pr_merge_in_a_heredoc_body_closes_nothing():
    """CI53. gh pr merge in a heredoc body is text, so it blocks. Control: the real merge of the waited PR passes"""
    text = "cat > notes.md <<'EOF'\ngh pr merge %s\nEOF" % CI_PR
    return expect_block([ready(), shell(text)]) + [
        "real merge (control): " + p for p in expect_silent([ready(), shell("gh pr merge %s" % CI_PR)])]


@case
def CI54_gh_pr_merge_after_a_hash_comment_closes_nothing():
    """CI54. gh pr merge after a # comment is a comment, so it blocks. Control: the real merge of the waited PR
    passes"""
    return expect_block([ready(), shell("ls -la  # gh pr merge %s" % CI_PR)]) + [
        "real merge (control): " + p for p in expect_silent([ready(), shell("gh pr merge %s" % CI_PR)])]


@case
def CI55_hash_inside_quotes_does_not_hide_a_real_merge():
    """CI55. a # inside quotes does not hide a real merge of the waited PR after it: passes. Control: the
    waited PR's wait with no merge blocks"""
    return silent_with_control([ready(), shell('echo "# not a comment" && gh pr merge %s' % CI_PR)], [ready()])


@case
def CI56_lone_apostrophe_does_not_hide_a_real_merge():
    """CI56. a lone apostrophe in an earlier word does not hide a real merge of the waited PR after it: passes.
    Control: the waited PR's wait with no merge blocks"""
    return silent_with_control([ready(), shell("echo don't; gh pr merge %s" % CI_PR)], [ready()])


@case
def CI57_merge_on_a_middle_line_of_quoted_text_closes_nothing():
    """CI57. gh pr merge on a middle line of a quoted string is text, so it blocks. Control: the real merge of the
    waited PR passes"""
    text = 'echo "first line\ngh pr merge %s\nlast line"' % CI_PR
    return expect_block([ready(), shell(text)]) + [
        "real merge (control): " + p for p in expect_silent([ready(), shell("gh pr merge %s" % CI_PR)])]


@case
def CI58_gh_pr_merge_chained_after_git_push_closes_the_wait():
    """CI58. a real gh pr merge of the waited PR chained after git push in one command: passes. Control: the
    waited PR's wait with no merge blocks"""
    return silent_with_control([ready(), shell("git push origin HEAD && gh pr merge %s" % CI_PR)], [ready()])


@case
def CI59_bare_gh_pr_merge_or_close_closes_the_wait():
    """CI59. gh pr merge or gh pr close with no PR number aims at the current branch's PR, so it closes the wait:
    passes. A GitHub MCP merge with no pullNumber names no PR, so it blocks. Control: gh pr merge of another PR
    blocks, and the reason names only the waited PR"""
    return (["bare gh pr merge: " + p for p in expect_silent([ready(), shell("gh pr merge --squash")])]
            + ["bare gh pr close: " + p
               for p in expect_silent([ready(), shell("gh pr close --delete-branch")])]
            + ["MCP merge with no pullNumber: " + p
               for p in expect_block([ready(), tool_call(MCP_MERGE, {"owner": CI_OWNER, "repo": CI_REPO})])]
            + ["control, other PR: " + p
               for p in expect_block([ready(), shell("gh pr merge %s --squash" % CI_OTHER_PR)],
                                     not_named=[CI_OTHER_PR])])


@case
def CI60_queued_unknown_verdict_leaves_the_wait_open():
    """CI60. a CI unknown verdict that arrives as a queued_command attachment closes nothing, so it blocks. Control:
    the same queued form with a green verdict passes"""
    return ["queued unknown verdict: " + p for p in expect_block([ready(), queued(UNKNOWN)])] + [
        "control: " + p for p in expect_silent([ready(), queued(GREEN)])]


@case
def CI61_checkin_with_an_error_result_does_not_count():
    """CI61. a check-in whose result is an error does not count, so the wait blocks. Control: a good check-in
    after the error one counts, and a good check-in alone passes"""
    err = checkin_answered(SEND_LATER, is_error=True)
    ok = checkin_answered(SEND_LATER, is_error=False)
    return ["error check-in alone: " + p for p in expect_block([ready()] + err)] + [
        "error check-in, then a good one: " + p for p in expect_silent([ready()] + err + ok)] + [
        "good check-in alone (control): " + p for p in expect_silent([ready()] + ok)]


@case
def CI62_merge_tool_forms_close_only_their_own_pr():
    """CI62. the merge tool called bare (merge N --confirm), and bin/merge without --confirm, close the wait only
    when they name the waited PR. Another PR's merge blocks, and the reason names only the waited PR"""
    return closer_pair(merge_bin(CI_PR, cmd="merge"), merge_bin(CI_OTHER_PR, cmd="merge"), "bare merge") + (
        closer_pair(merge_bin(CI_PR, confirm=False), merge_bin(CI_OTHER_PR, confirm=False),
                    "bin/merge without --confirm"))


@case
def CI63_full_size_named_merges_close_their_own_prs():
    """CI63. full size: 2000 text records, then 30 PRs each closed by gh pr merge of its own number, then one open
    ready call. It blocks and names only the open PR. Control: the same session without the open ready call is
    silent"""
    items = [prompt("start")] + [assistant_text("step %d" % n) for n in range(2000)]
    for i in range(30):
        items += [ready(str(1000 + i)), shell("gh pr merge %d --squash" % (1000 + i))]
    items.append(ready())
    closed = [str(1000 + i) for i in range(30)]
    return expect_block(items, not_named=closed) + ["control: " + p for p in expect_silent(items[:-1])]


def bare_wait_closed_by(closer, label):
    """A bare gh pr ready, which names no PR, opens a wait. A merge or close of any PR closes it, so the check is
    silent. Control: the bare wait alone blocks, and its reason names no PR number"""
    bare = [ready(command="gh pr ready")]
    return ["%s: %s" % (label, p) for p in silent_with_control(bare + [closer], bare, pr=None)]


def numbered_wait_closed_by(command, label):
    """A gh pr ready of PR 5 opens a wait. command closes it, so the check is silent. Control: the wait alone
    blocks on PR 5"""
    wait = [ready("5")]
    return ["%s: %s" % (label, p) for p in silent_with_control(wait + [shell(command)], wait, pr="5")]


@case
def CI64_bare_ready_closed_by_bin_merge_of_any_pr():
    """CI64. a bare gh pr ready opens a wait with no PR number, and bin/merge of PR 5 closes it: passes. Control:
    the bare wait alone blocks"""
    return bare_wait_closed_by(merge_bin("5"), "bin/merge of PR 5")


@case
def CI65_bare_ready_closed_by_gh_pr_merge_of_any_pr():
    """CI65. a bare gh pr ready opens a wait with no PR number, and gh pr merge of PR 5 closes it: passes. Control:
    the bare wait alone blocks"""
    return bare_wait_closed_by(shell("gh pr merge 5"), "gh pr merge of PR 5")


@case
def CI66_bare_ready_closed_by_gh_pr_close_of_any_pr():
    """CI66. a bare gh pr ready opens a wait with no PR number, and gh pr close of PR 5 closes it: passes. Control:
    the bare wait alone blocks"""
    return bare_wait_closed_by(shell("gh pr close 5"), "gh pr close of PR 5")


@case
def CI67_bare_ready_closed_by_mcp_merge_of_any_pr():
    """CI67. a bare gh pr ready opens a wait with no PR number, and a GitHub MCP merge_pull_request of PR 5 closes
    it: passes. Control: the bare wait alone blocks"""
    return bare_wait_closed_by(mcp_pr(MCP_MERGE, "5"), "GitHub MCP merge of PR 5")


@case
def CI68_merge_tool_with_repo_flag_closes_its_own_pr():
    """CI68. the merge tool called by path, with -C <repo> before the PR number, closes the wait on PR 5: passes.
    Control: the wait alone blocks"""
    return numbered_wait_closed_by("~/.claude/bin/merge -C /repo 5 --confirm", "merge tool with -C")


@case
def CI69_merge_tool_with_session_flag_closes_its_own_pr():
    """CI69. the merge tool with --session <name> before the PR number closes the wait on PR 5: passes. Control:
    the wait alone blocks"""
    return numbered_wait_closed_by("merge --session lane 5 --confirm", "merge tool with --session")


@case
def CI70_gh_pr_merge_with_body_flag_closes_its_own_pr():
    """CI70. gh pr merge with a --body value before the PR number closes the wait on PR 5: passes. Control: the
    wait alone blocks"""
    return numbered_wait_closed_by('gh pr merge --body "x" 5', "gh pr merge with --body")


@case
def CI71_gh_pr_merge_with_repo_flag_closes_its_own_pr():
    """CI71. gh pr merge with -R <owner/repo> before the PR number closes the wait on PR 5: passes. Control: the
    wait alone blocks"""
    return numbered_wait_closed_by("gh pr merge -R o/r 5", "gh pr merge with -R")


@case
def CI72_gh_pr_merge_by_url_closes_its_own_pr():
    """CI72. gh pr merge given a pull request URL closes the wait on the PR number in it, PR 5: passes. Control: the
    wait alone blocks"""
    return numbered_wait_closed_by("gh pr merge https://github.com/o/r/pull/5", "gh pr merge by URL")


@case
def CI73_gh_pr_merge_with_body_flag_of_another_pr_blocks():
    """CI73. gh pr merge with a --body value, then PR 6, does not close the wait on PR 5, so it blocks and the reason
    names only PR 5. Control: gh pr merge of PR 5 passes"""
    wait = [ready("5")]
    return (expect_block(wait + [shell('gh pr merge --body "x" 6')], pr="5", not_named=["6"])
            + ["control: " + p for p in expect_silent(wait + [shell("gh pr merge 5 --squash")])])


@case
def CI74_two_space_gh_pr_close_closes_its_own_pr():
    """CI74. gh  pr  close with two spaces between the words, then PR 5, closes the wait on PR 5: passes. Control:
    the wait alone blocks"""
    return numbered_wait_closed_by("gh  pr  close 5", "gh  pr  close with two spaces")


@case
def CI75_full_size_bare_wait_closed_by_a_merge_of_any_pr():
    """CI75. full size: 2000 text records, then a bare gh pr ready, then gh pr merge of PR 5. The merge closes the
    wait: passes. Control: the same session without the merge blocks, and its reason names no PR number"""
    items = [prompt("start")] + [assistant_text("step %d" % n) for n in range(2000)]
    items.append(ready(command="gh pr ready"))
    return silent_with_control(items + [shell("gh pr merge 5 --squash")], items, pr=None)


@case
def CI76_branch_name_merge_closes_no_numbered_wait():
    """CI76. gh pr merge <branch>, and bin/merge <branch> --confirm, name a branch and no PR, so each closes no
    numbered wait: it blocks on PR 5, and the reason names only PR 5. Control: gh pr merge 5 of the same wait passes"""
    wait = [ready("5")]
    return (["gh pr merge feature-x: " + p
             for p in expect_block(wait + [shell("gh pr merge feature-x")], pr="5", not_named=["feature-x"])]
            + ["bin/merge feature-x: " + p
               for p in expect_block(wait + [merge_bin("feature-x")], pr="5", not_named=["feature-x"])]
            + ["control, gh pr merge 5: " + p for p in expect_silent(wait + [shell("gh pr merge 5")])])


@case
def CI77_bare_ready_closed_by_a_branch_merge_of_any_pr():
    """CI77. a bare gh pr ready opens a wait with no PR number, and gh pr merge <branch> closes it, as a merge of any
    PR does: passes. Control: the bare wait alone blocks, and its reason names no PR number"""
    return bare_wait_closed_by(shell("gh pr merge feature-x"), "gh pr merge of a branch")


@case
def CI78_gh_global_flag_before_pr_opens_a_wait():
    """CI78. gh -R <repo> pr ready N and gh --repo <repo> pr ready N open a wait on PR N: blocks, and the reason
    names PR N. Control: the plain gh pr ready N blocks"""
    repo = "%s/%s" % (CI_OWNER, CI_REPO)
    return (["gh -R, ready: " + p
             for p in expect_block([ready(command="gh -R %s pr ready %s" % (repo, CI_PR))])]
            + ["gh --repo, ready: " + p
               for p in expect_block([ready(command="gh --repo %s pr ready %s" % (repo, CI_PR))])]
            + ["control, plain ready: " + p for p in expect_block([ready()])])


@case
def CI79_gh_global_flag_before_pr_closes_the_wait_on_a_merge():
    """CI79. gh pr ready N, then gh -R <repo> pr merge N, or gh --repo <repo> pr merge N, closes the wait on N:
    passes. Control: the wait alone blocks"""
    repo = "%s/%s" % (CI_OWNER, CI_REPO)
    wait = [ready()]
    return (["gh -R, merge: " + p
             for p in silent_with_control(wait + [shell("gh -R %s pr merge %s" % (repo, CI_PR))], wait)]
            + ["gh --repo, merge: " + p
               for p in silent_with_control(wait + [shell("gh --repo %s pr merge %s" % (repo, CI_PR))], wait)])


@case
def CI80_ready_with_repo_flag_before_the_number_waits_on_the_number():
    """CI80. gh pr ready -R <repo> N waits on PR N, not on the repo: blocks, and the reason names PR N. Control:
    the plain gh pr ready N blocks"""
    repo = "%s/%s" % (CI_OWNER, CI_REPO)
    return (expect_block([ready(command="gh pr ready -R %s %s" % (repo, CI_PR))])
            + ["control, plain ready: " + p for p in expect_block([ready()])])


@case
def CI81_ready_and_merge_with_repo_flag_close_the_wait_on_the_number():
    """CI81. gh pr ready -R <repo> N, then gh pr merge -R <repo> N, closes the wait on N: passes. Control: the -R
    wait alone blocks, and a merge of another PR with -R does not close it"""
    repo = "%s/%s" % (CI_OWNER, CI_REPO)
    wait = [ready(command="gh pr ready -R %s %s" % (repo, CI_PR))]
    return (["merge with -R of the waited PR: " + p
             for p in expect_silent(wait + [shell("gh pr merge -R %s %s" % (repo, CI_PR))])]
            + ["control, the -R wait alone: " + p for p in expect_block(wait, pr=None)]
            + ["control, merge with -R of PR %s: " % CI_OTHER_PR + p
               for p in expect_block(wait + [shell("gh pr merge -R %s %s" % (repo, CI_OTHER_PR))], pr=None,
                                     not_named=[CI_OTHER_PR])])


@case
def CI82_ready_by_pull_url_waits_on_the_number_in_it():
    """CI82. gh pr ready <pull URL> waits on the PR number in the URL, so gh pr merge N closes it, and so does a
    merge by the same URL: passes. Control: the URL wait alone blocks on PR N"""
    url = "https://github.com/%s/%s/pull/%s" % (CI_OWNER, CI_REPO, CI_PR)
    wait = [ready(command="gh pr ready %s" % url)]
    return (["merge by number: " + p for p in silent_with_control(wait + [shell("gh pr merge %s" % CI_PR)], wait)]
            + ["merge by the same URL: " + p
               for p in silent_with_control(wait + [shell("gh pr merge %s" % url)], wait)])


@case
def CI83_merge_with_only_flags_and_flag_values_is_bare_and_closes_the_wait():
    """CI83. gh pr merge with only flags and their values, and no PR number, is bare, so it closes the wait on N:
    --squash --body "x", --squash --body-file notes.md and --squash --subject "Fix" each pass. Control: a merge
    with --body "x" and another PR's number closes nothing, and the wait on N blocks"""
    wait = [ready()]
    problems = []
    for flags in ('--squash --body "x"', "--squash --body-file notes.md", '--squash --subject "Fix"'):
        problems += ["gh pr merge %s: %s" % (flags, p)
                     for p in silent_with_control(wait + [shell("gh pr merge " + flags)], wait)]
    problems += ["control, --body then PR %s: %s" % (CI_OTHER_PR, p)
                 for p in expect_block(wait + [shell('gh pr merge --squash --body "x" %s' % CI_OTHER_PR)],
                                       not_named=[CI_OTHER_PR])]
    return problems


@case
def CI84_merge_with_auto_closes_nothing():
    """CI84. gh pr merge N --auto, gh pr merge N --auto --squash and a bare gh pr merge --auto close nothing, since
    nothing has merged yet: each leaves the wait on N open, so it blocks and names PR N. Control: gh pr merge N
    --squash closes the wait"""
    wait = [ready()]
    return (["gh pr merge N --auto: " + p
             for p in expect_block(wait + [shell("gh pr merge %s --auto" % CI_PR)])]
            + ["gh pr merge N --auto --squash: " + p
               for p in expect_block(wait + [shell("gh pr merge %s --auto --squash" % CI_PR)])]
            + ["bare gh pr merge --auto: " + p for p in expect_block(wait + [shell("gh pr merge --auto")])]
            + ["control, gh pr merge N --squash: " + p
               for p in expect_silent(wait + [shell("gh pr merge %s --squash" % CI_PR)])])


@case
def CI85_ready_on_a_shell_variable_is_closed_by_a_merge_or_close_of_any_pr():
    """CI85. gh pr ready $PR opens a wait on an unknown number, which a merge or close of any PR closes, as a bare
    wait is: gh pr merge N and gh pr close N each pass. Control: the wait alone blocks"""
    wait = [ready(command="gh pr ready $PR")]
    return (["gh pr merge N: " + p
             for p in silent_with_control(wait + [shell("gh pr merge %s" % CI_PR)], wait, pr=None)]
            + ["gh pr close N: " + p
               for p in silent_with_control(wait + [shell("gh pr close %s" % CI_PR)], wait, pr=None)])


@case
def CI86_merge_on_a_shell_variable_is_bare_and_closes_a_numbered_wait():
    """CI86. gh pr merge $PR, whose PR word is a shell variable, is bare, so it closes the wait on PR N, as a merge
    of any PR does: passes. Control: the wait on PR N alone blocks"""
    wait = [ready()]
    return silent_with_control(wait + [shell("gh pr merge $PR")], wait)


@case
def CI87_full_size_flags_only_merge_closes_the_wait():
    """CI87. full size: 2000 text records, then a ready call of PR N, then gh pr merge --squash --body "x", which is
    bare and closes the wait: passes. Control: the same session without the merge blocks on PR N"""
    items = [prompt("start")] + [assistant_text("step %d" % n) for n in range(2000)]
    items.append(ready())
    return silent_with_control(items + [shell('gh pr merge --squash --body "x"')], items)


@case
def CI88_close_with_an_unquoted_comment_value_closes_the_wait():
    """CI88. gh pr close -c done and gh pr close --comment superseded, with the comment unquoted, are bare: the value
    is the comment, not the PR, so each closes the wait on N: passes. Control: the wait alone blocks"""
    wait = [ready()]
    return ["gh pr close %s: %s" % (flags, p)
            for flags in ("-c done", "--comment superseded")
            for p in silent_with_control(wait + [shell("gh pr close " + flags)], wait)]


@case
def CI89_merge_with_disable_auto_closes_nothing():
    """CI89. gh pr merge N --disable-auto, and a bare gh pr merge --disable-auto, merge nothing, so each leaves the
    wait on N open: it blocks and names PR N. Control: gh pr merge N --squash closes the wait"""
    wait = [ready()]
    return (["gh pr merge N --disable-auto: " + p
             for p in expect_block(wait + [shell("gh pr merge %s --disable-auto" % CI_PR)])]
            + ["bare gh pr merge --disable-auto: " + p
               for p in expect_block(wait + [shell("gh pr merge --disable-auto")])]
            + ["control, gh pr merge N --squash: " + p
               for p in expect_silent(wait + [shell("gh pr merge %s --squash" % CI_PR)])])


@case
def CI90_unquoted_subject_and_body_values_are_skipped_and_the_merge_closes_the_wait():
    """CI90. gh pr merge --subject Fix and gh pr merge --body x, with the values unquoted, are bare: each value is a
    flag's value, not the PR, so each closes the wait on N: passes. Control: the wait alone blocks"""
    wait = [ready()]
    return ["gh pr merge %s: %s" % (flags, p)
            for flags in ("--subject Fix", "--body x")
            for p in silent_with_control(wait + [shell("gh pr merge " + flags)], wait)]


@case
def CI91_short_value_flags_and_author_email_skip_their_value_and_the_merge_closes_the_wait():
    """CI91. gh pr merge -b x, -t Fix, -A dev@example.com and --author-email dev@example.com, with no PR word, are
    bare: each value is a flag's value, so each closes the wait on N: passes. Control: the wait alone blocks"""
    wait = [ready()]
    return ["gh pr merge %s: %s" % (flags, p)
            for flags in ("-b x", "-t Fix", "-A dev@example.com", "--author-email dev@example.com")
            for p in silent_with_control(wait + [shell("gh pr merge " + flags)], wait)]


@case
def CI92_session_value_is_not_read_as_the_pr():
    """CI92. merge --session 12 N (the merge tool) and gh pr merge --session 12 N read N as the PR, not 12: on the
    wait on N each closes it, passes. On the wait on another PR neither closes it: it blocks and names that PR, not N"""
    wait, other = [ready()], [ready(number=CI_OTHER_PR)]
    problems = []
    for call_text in ("merge --session 12 %s" % CI_PR, "gh pr merge --session 12 %s" % CI_PR):
        problems += ["%s, wait on N: %s" % (call_text, p)
                     for p in silent_with_control(wait + [shell(call_text)], wait)]
        problems += ["%s, wait on PR %s: %s" % (call_text, CI_OTHER_PR, p)
                     for p in expect_block(other + [shell(call_text)], pr=CI_OTHER_PR, not_named=[CI_PR])]
    return problems


@case
def CI93_match_head_commit_value_is_not_read_as_the_pr():
    """CI93. gh pr merge --match-head-commit 1234567 N reads N as the PR, not the SHA prefix: on the wait on N it
    closes it, passes. On the wait on another PR it leaves it open: blocks and names that PR, not N"""
    wait, other = [ready()], [ready(number=CI_OTHER_PR)]
    call_text = "gh pr merge --match-head-commit 1234567 %s" % CI_PR
    return (["wait on N: " + p for p in silent_with_control(wait + [shell(call_text)], wait)]
            + ["wait on PR %s: %s" % (CI_OTHER_PR, p)
               for p in expect_block(other + [shell(call_text)], pr=CI_OTHER_PR, not_named=[CI_PR])])


if __name__ == "__main__":
    sys.exit(run_cases(CASES))
