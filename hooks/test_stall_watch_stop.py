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

No posix check: this mode must run on Windows. These cases use no sh, ps or lsof, except S21a: it
starts a shell job and skips off posix, so Windows runs the rest. Every case that expects silence
also runs a control that must list a stale job, so a mode that is absent or silent everywhere
cannot pass it.
"""

import atexit
import builtins
import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import signal
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


def bash_result(call_id, text):
    """The result of a Bash call that started no job: plain stdout, no task id."""
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": call_id, "content": text, "is_error": False}]},
        "toolUseResult": {"stdout": text, "stderr": "", "interrupted": False}}


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


def stop_in_process(transcript_path):
    """Run the Stop check in this process at NOW, with the default quiet age and no output base. Return
    (rc, stdout, the paths os.stat was called with, the paths open was called with). The wrappers count
    every path the check stats or opens, so a case counts the calls that name one agent."""
    spec = importlib.util.spec_from_file_location("stall_watch_in_process", MODULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    stats, opens = [], []
    real_stat, real_os_open, real_open, real_io_open = os.stat, os.open, builtins.open, io.open

    def counted_stat(path, *args, **kwargs):
        stats.append(str(path))
        return real_stat(path, *args, **kwargs)

    def counted_open(file, *args, **kwargs):
        opens.append(str(file))
        return real_open(file, *args, **kwargs)

    def counted_os_open(path, *args, **kwargs):
        opens.append(str(path))
        return real_os_open(path, *args, **kwargs)

    keys = ("STALL_WATCH_NOW", "STALL_WATCH_OUTPUT_BASE", "STALL_WATCH_QUIET")
    saved = {k: os.environ.get(k) for k in keys}
    payload = {"session_id": "test-stall-watch-stop", "hook_event_name": "Stop", "cwd": SCRATCH,
               "transcript_path": transcript_path, "stop_hook_active": False}
    old_stdin = sys.stdin
    try:
        os.environ["STALL_WATCH_NOW"] = str(NOW)
        os.environ.pop("STALL_WATCH_OUTPUT_BASE", None)
        os.environ.pop("STALL_WATCH_QUIET", None)
        sys.stdin = io.StringIO(json.dumps(payload))
        os.stat, os.open, builtins.open, io.open = counted_stat, counted_os_open, counted_open, counted_open
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            rc = mod.stop()
        return rc, buf.getvalue(), stats, opens
    finally:
        os.stat, os.open, builtins.open, io.open = real_stat, real_os_open, real_open, real_io_open
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


def start_job(command, path):
    """Start `command` in the background, as the harness does: its stdout is the job's output file. The job
    has its own process group, so a case can end every process under it. The command may use `{sync}`, the
    fd it writes one byte to once it is busy. Return (process, read end of the sync pipe)."""
    r, w = os.pipe()
    with open(path, "ab") as out:
        proc = subprocess.Popen(["sh", "-c", command.format(sync=w)], stdin=subprocess.DEVNULL, stdout=out,
                                stderr=subprocess.STDOUT, start_new_session=True, pass_fds=(w,))
    os.close(w)
    return proc, r


def end_job(proc, r):
    """Kill the job's process group, and close the read end of its sync pipe."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        pass
    proc.wait()
    os.close(r)


@case
def busy_job_with_no_output_is_not_listed():
    """S21a. a background `| tail -1` job whose child spins a CPU, with no output and its output file quiet 600 s:
    not listed, since its CPU time is life. A job that only sleeps, quiet 600 s, is listed (control)"""
    if os.name != "posix" or not shutil.which("sh"):
        raise Skip("needs sh and process groups, which this host lacks")
    base = new_dir()
    busy_path = output_file(base, "bmcpu600", 600)
    sleep_path = output_file(base, "bmsleep600", 600)
    busy_cmd = "while :; do :; done | tail -1"
    sleep_cmd = "sleep 60 | tail -1"
    busy, busy_r = start_job("echo x >&{sync}; " + busy_cmd, busy_path)
    sleeper, sleep_r = start_job(sleep_cmd, sleep_path)
    try:
        if os.read(busy_r, 1) != b"x":  # the child is spinning now, so the Stop check runs while it is busy
            return ["the busy job did not start its spin"]
        recs = log_job("bmcpu600", busy_cmd) + log_job("bmsleep600", sleep_cmd)
        rc, out, err = run_stop(transcript(recs), base)
        problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
        msg = system_message(out, problems)
        problems += expect("bmcpu600" not in msg, f"a job whose child spins a CPU is listed as quiet: {msg!r}")
        problems += listed_once(msg, "bmsleep600")
        return problems
    finally:
        end_job(busy, busy_r)
        end_job(sleeper, sleep_r)


@case
def unresolved_log_is_named_as_not_watched():
    """S21b. `cd "$REPO" && make > build.log`, with build.log grown 10 s ago: its directory is unknown, so the Stop
    check does not watch the log, as the watcher does (27e in test_stall_watch.py). The job is still listed, and
    its row says the log is not watched. A plain quiet job is listed (control)"""
    base, d = new_dir(), new_dir()
    output_file(base, "bmenv600", 600)
    output_file(base, "bmplain600", 600)
    log_at(os.path.join(d, "build.log"), 10)
    recs = log_job("bmenv600", 'cd "$REPO" && make > build.log', cwd=d) + moved("bmplain600")
    rc, out, err = run_stop(transcript(recs), base)
    problems = expect(rc == 0, f"exit {rc}, want 0: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += listed_once(msg, "bmplain600")
    problems += listed_once(msg, "bmenv600")
    problems += expect(any("not watched" in line and "build.log" in line for line in msg.splitlines()),
                       f"the job's log build.log is not named as not watched: {msg!r}")
    return problems


if __name__ == "__main__":
    sys.exit(run_cases(CASES))
