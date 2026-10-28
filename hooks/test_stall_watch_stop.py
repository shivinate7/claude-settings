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
- A listed job shows its note: the text after `until:` in the description of the Bash call that
  started it, to the end of that line. The note sits on the job's own line, and the message asks
  whether it is met. A job whose call holds no `until:` text is still listed, with no note.
- When guard_stream cannot be imported, --stop still lists each stale job, with no note.
- Any error prints nothing and exits 0.

Seams: STALL_WATCH_NOW (epoch seconds, the clock), STALL_WATCH_OUTPUT_BASE (a folder that
replaces the folder of each transcript output path and keeps its file name), STALL_WATCH_QUIET
(the age in seconds). STALL_WATCH_MODULE picks the module under test, as in test_stall_watch.py.

No posix check: this mode must run on Windows. These cases use no sh, ps or lsof. Every case that
expects silence also runs a control that must list a stale job, so a mode that is absent or
silent everywhere cannot pass it.
"""

import atexit
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

from case_runner_test import Skip, run_cases

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE = os.environ.get("STALL_WATCH_MODULE") or os.path.join(HERE, "stall_watch.py")
PY = sys.executable
SCRATCH = tempfile.mkdtemp(prefix="test-stall-watch-stop-")
atexit.register(shutil.rmtree, SCRATCH, ignore_errors=True)
NOW = int(time.time())  # the clock every case passes as STALL_WATCH_NOW, so no case sleeps
ADVICE = "stop it or tell the owner"
RESUME_SUMMARY = "Background shell command didn't finish before the previous session ended"
WIN_DIR = (r"C:\Users\SHIVAM~1\AppData\Local\Temp\claude"
           r"\C--Users-ShivamSemwal-Clones-claude-settings\58b19313-e243-4dfd-b256-23ef68a15564\tasks")
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


def transcript(items):
    """Write a session transcript. A dict is one JSON record; bytes are written as they are."""
    path = os.path.join(new_dir(), "session.jsonl")
    with open(path, "wb") as f:
        for item in items:
            f.write(item if isinstance(item, bytes) else json.dumps(item).encode("utf-8") + b"\n")
    return path


def output_file(base, job_id, idle):
    """Write <base>/<job_id>.output, its mtime set idle seconds before NOW."""
    os.makedirs(base, exist_ok=True)
    path = os.path.join(base, job_id + ".output")
    with open(path, "wb") as f:
        f.write(b"output\n")
    os.utime(path, (NOW - idle, NOW - idle))
    return path


def run_stop(transcript_path, base=None, stop_hook_active=False, quiet=None, stdin=None, nt=False,
             module=None):
    """Run the Stop mode the way the Stop hook does. Return (rc, stdout, stderr). module, when
    given, is the script run in place of MODULE."""
    mod = module or MODULE
    if not os.path.isfile(mod):
        raise Fail(f"{mod} is missing")
    env = {k: v for k, v in os.environ.items() if not k.startswith("STALL_WATCH_")}
    if module is not None:
        env.pop("PYTHONPATH", None)  # a copy must not import its siblings from another checkout
    env["STALL_WATCH_NOW"] = str(NOW)
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


def listed_once(msg, job_id):
    """Each job prints its output path once, so its file name appears once."""
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
    """N3. guard_stream cannot be imported (a scratch copy of stall_watch.py and shared_names.py with no
    guard_stream beside them): --stop exits 0 and lists the quiet job once, with no note. A control runs the real
    module on the same transcript and shows the note, so the missing note is not a broken fixture"""
    base = new_dir()
    output_file(base, "bnoimp600", 600)
    recs = flagged("bnoimp600", desc="Serve q_max files on 3202. until: round 1 bids are served")
    path = transcript(recs)
    lone = new_dir()
    shutil.copy(MODULE, os.path.join(lone, "stall_watch.py"))
    shutil.copy(os.path.join(HERE, "shared_names.py"), lone)
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


if __name__ == "__main__":
    sys.exit(run_cases(CASES))
