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
  `<status>` is terminal: completed, failed or killed.
- A job is stale when its output file has not changed for the quiet age (STALL_WATCH_QUIET,
  default 300 s). A job whose output file is missing is listed as "unknown", never dropped.
- Any error prints nothing and exits 0.

Seams: STALL_WATCH_NOW (epoch seconds, the clock), STALL_WATCH_OUTPUT_BASE (a folder that
replaces the folder of each transcript output path and keeps its file name), STALL_WATCH_QUIET
(the age in seconds). STALL_WATCH_MODULE picks the module under test, as in test_stall_watch.py.

No posix gate: this mode must run on Windows. These cases use no sh, ps or lsof. Every case that
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

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE = os.environ.get("STALL_WATCH_MODULE") or os.path.join(HERE, "stall_watch.py")
PY = sys.executable
SCRATCH = tempfile.mkdtemp(prefix="test-stall-watch-stop-")
atexit.register(shutil.rmtree, SCRATCH, ignore_errors=True)
NOW = int(time.time())  # the clock every case passes as STALL_WATCH_NOW, so no case sleeps
ADVICE = "stop it or tell the owner"
WIN_DIR = (r"C:\Users\SHIVAM~1\AppData\Local\Temp\claude"
           r"\C--Users-ShivamSemwal-Clones-claude-settings\58b19313-e243-4dfd-b256-23ef68a15564\tasks")
CASES = []
NT_DRIVER = ("import json, os, runpy, shlex, shutil, subprocess, sys, tempfile, time, uuid\n"
             "os.name = 'nt'\n"
             "sys.argv = [sys.argv[1], '--stop']\n"
             "runpy.run_path(sys.argv[0], run_name='__main__')\n")


class Skip(Exception):
    pass


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


def call(call_id, command, background=False):
    """A Bash tool_use. A call moved by its timeout has no run_in_background key."""
    inp = {"command": command, "description": "test"}
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


def moved(job_id, path=None):
    """A Bash call that its timeout moved to the background, and its result."""
    cid = "toolu_" + job_id
    return [call(cid, "sleep 600"), started(cid, job_id, path or win_path(job_id), True)]


def flagged(job_id):
    """A Bash call started with run_in_background, and its result."""
    cid = "toolu_" + job_id
    return [call(cid, "sleep 600", background=True), started(cid, job_id, win_path(job_id), False)]


def notice(job_id, status="completed"):
    """A completion notice as the transcript holds it: a user message whose content is a string."""
    body = ("<task-notification>\n<task-id>%s</task-id>\n<tool-use-id>toolu_%s</tool-use-id>\n"
            "<output-file>%s</output-file>\n<status>%s</status>\n"
            "<summary>Background command \"sleep 600\" %s</summary>\n</task-notification>"
            % (job_id, job_id, win_path(job_id), status, status))
    return {"type": "user", "message": {"role": "user", "content": body}}


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


def run_stop(transcript_path, base=None, stop_hook_active=False, quiet=None, stdin=None, nt=False):
    """Run the Stop mode the way the Stop hook does. Return (rc, stdout, stderr)."""
    if not os.path.isfile(MODULE):
        raise Fail(f"{MODULE} is missing")
    env = {k: v for k, v in os.environ.items() if not k.startswith("STALL_WATCH_")}
    env["STALL_WATCH_NOW"] = str(NOW)
    if base is not None:
        env["STALL_WATCH_OUTPUT_BASE"] = base
    if quiet is not None:
        env["STALL_WATCH_QUIET"] = str(quiet)
    if stdin is None:
        payload = {"session_id": "test-stall-watch-stop", "hook_event_name": "Stop", "cwd": SCRATCH,
                   "transcript_path": transcript_path, "stop_hook_active": stop_hook_active}
        stdin = json.dumps(payload).encode("utf-8")
    argv = [PY, "-c", NT_DRIVER, MODULE] if nt else [PY, MODULE, "--stop"]
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


@case
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


@case
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


@case
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


@case
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


@case
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
def stop_mode_has_no_posix_gate():
    """S13. with os.name patched to nt the mode still lists the stale job"""
    base = new_dir()
    output_file(base, "bnt600", 600)
    rc, out, err = run_stop(transcript(moved("bnt600")), base, nt=True)
    problems = expect(rc == 0, f"exit {rc}, want 0 with os.name nt: {err.strip()[:200]}")
    msg = system_message(out, problems)
    problems += listed_once(msg, "bnt600")
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
