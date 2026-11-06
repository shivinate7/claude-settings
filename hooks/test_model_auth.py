#!/usr/bin/env python3
"""Cases for the model-call auth check: a model call that cannot authenticate is never quiet.

Run it from the repository root:

    python3 hooks/test_model_auth.py

Standard library only. Each case returns a list of problems, empty for a pass (hooks/case_runner_test.py).
No case makes a real model call. Every invoke_model start runs against a fake, and a tripwire refuses any
`claude` start that a case did not fake.

Interfaces these cases expect. The builder implements to them. A missing name is a failed assert that
names it, never a crash.

- decision_watch.auth_check(model_call=invoke_model) -> str
    '' when silent, else one line for the owner. The token file `<config dir>/state/hook-token`:
    present and non-empty means no probe and silence. Absent or empty means exactly one probe,
    model_call(prompt, model=..., timeout=..., effort=None), with a timeout under MODEL_TIMEOUT.
    The probe fails: the line names `claude setup-token`, the hook-token path under guard.config_dir(),
    and the probe's error. The token file is not text: the line names the fix, and there is no probe.
- decision_watch.invoke_model(prompt, ..., session_id=None) -> (verdict | None, error | None)
    Gains one keyword. A non-empty session_id records the outcome: a failure adds one to the session's
    consecutive-failure count and keeps the scrubbed error; a success resets the count.
    Without a session_id nothing is recorded.
- decision_watch.record_model_outcome(session_id, error) -> None
    error None is a success. A falsy session_id writes nothing.
- decision_watch.streak_line(session_id) -> str
    '' below three failures in a row. From three on: "Model calls: N failed in a row this session
    (last: <error>). Hook judges are not running. Fix: <the auth_check fix>".
- hooks/stall_watch.py --stop (the existing Stop hook) puts streak_line in its one systemMessage line.
- settings.json: one SessionStart command runs decision_watch.py --auth-check. No Stop command names
  decision_watch.
- The streak file lives under the config dir's state folder. These cases do not name it. They scan every
  file there except the token file.
"""
import atexit
import contextlib
import importlib.util
import inspect
import json
import os
import shutil
import subprocess
import sys
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lint"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
from case_runner_test import run_cases  # noqa: E402
import test_stall_watch_stop as tss  # noqa: E402  the Stop harness and its stale-job case: called, not copied

# Loaded the way hooks/test_decision_watch.py loads it. Not imported from there: that module makes a
# scratch folder in the system temp dir when it is imported, outside this run's folder.
_spec = importlib.util.spec_from_file_location(
    "decision_watch_under_test",
    os.environ.get("DECISION_WATCH_UNDER_TEST") or os.path.join(HERE, "decision_watch.py"),
)
dw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dw)

SCRATCH = _test_temp.run_folder()
atexit.register(shutil.rmtree, SCRATCH, ignore_errors=True)

FAKE_TOKEN = "sk-ant-oat01-FAKE"
UNREADABLE_MARK = b"BYTES-MARKER"
SETUP = "claude setup-token"
HOOK_TOKEN_REL = os.path.join("state", "hook-token")
STDERR = "not logged in"
FAIL_ERR = "model exited 1: " + STDERR  # what invoke_model returns for that failed start
OK_VERDICT = {"verdict": "ALLOW"}
CASES = []
REAL_CALLS = []
_REAL_RUN = subprocess.run


def _refuse_real_claude(argv, *args, **kwargs):
    """Refuse a `claude` start that a case did not fake. Every other start runs as it would."""
    first = str(argv[0]) if isinstance(argv, (list, tuple)) and argv else str(argv)
    if os.path.basename(first).lower().startswith("claude"):
        REAL_CALLS.append(first)
        raise RuntimeError("a case tried to start claude for real")
    return _REAL_RUN(argv, *args, **kwargs)


# The tripwire covers every start, including the one invoke_model makes through _nowindow.run.
subprocess.run = _refuse_real_claude


def case(fn):
    CASES.append(fn)
    return fn


def expect(ok, msg):
    return [] if ok else [msg]


@contextlib.contextmanager
def model_run(fake):
    """Route every subprocess start inside the block to `fake`, then restore the tripwire."""
    prior = subprocess.run
    subprocess.run = fake
    try:
        yield fake
    finally:
        subprocess.run = prior


class FakeRun:
    """The fake model start. A failed start has exit 1 and `stderr`; a success prints a verdict envelope."""

    def __init__(self, returncode=0, stdout=None, stderr=""):
        self.returncode = returncode
        if stdout is None:
            stdout = json.dumps({"result": json.dumps(OK_VERDICT)})
        self.stdout = stdout
        self.stderr = stderr

    def __call__(self, *args, **kwargs):
        argv = args[0] if args else kwargs.get("args")
        return subprocess.CompletedProcess(argv, self.returncode, self.stdout, self.stderr)


def invoke_failing(stderr=STDERR, **kwargs):
    """One invoke_model call whose model start fails with `stderr`. Returns (verdict, error)."""
    with model_run(FakeRun(returncode=1, stderr=stderr)):
        return dw.invoke_model("judge this", **kwargs)


def invoke_ok(**kwargs):
    """One invoke_model call whose model start succeeds. Returns (verdict, error)."""
    with model_run(FakeRun()):
        return dw.invoke_model("judge this", **kwargs)


class Probe:
    """Stands in for invoke_model as auth_check's model_call. Records each call and returns `result`."""

    def __init__(self, result):
        self.result = result
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.result


@contextlib.contextmanager
def scratch_config(name):
    """Point CLAUDE_CONFIG_DIR at this case's own folder under the run folder, then restore it."""
    cfg = os.path.join(SCRATCH, "config-" + name)
    os.makedirs(cfg, exist_ok=True)
    prior = os.environ.get("CLAUDE_CONFIG_DIR")
    os.environ["CLAUDE_CONFIG_DIR"] = cfg
    try:
        yield cfg
    finally:
        if prior is None:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["CLAUDE_CONFIG_DIR"] = prior


def token_file(cfg, data):
    path = os.path.join(cfg, HOOK_TOKEN_REL)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data.encode("utf-8") if isinstance(data, str) else data)
    return path


def files_under(cfg, skip=()):
    """Every file under `cfg`, as a path relative to it, minus `skip`."""
    found = []
    for root, _dirs, names in os.walk(cfg):
        for name in names:
            rel = os.path.relpath(os.path.join(root, name), cfg)
            if rel not in skip:
                found.append(rel)
    return found


def scoped(cfg):
    """Scope first (P7): the config dir the code reads is this case's folder, before any assert about it."""
    got = dw.guard.config_dir()
    return expect(os.path.realpath(got) == os.path.realpath(cfg),
                  "scope: the config dir is %r, not this case's %r" % (got, cfg))


def interface(name):
    """Return (the decision_watch name or None, problems). A missing name is a failed assert, not a crash."""
    fn = getattr(dw, name, None)
    return fn, ([] if fn is not None else ["decision_watch.%s is not defined" % name])


def takes_session_id_problems():
    try:
        ok = "session_id" in inspect.signature(dw.invoke_model).parameters
    except (TypeError, ValueError):
        ok = False
    return expect(ok, "invoke_model takes no session_id, so a model failure cannot reach the Stop line")


def stop_message(session_id):
    """Run the Stop hook for one session. Return (problems, systemMessage, raw stdout)."""
    transcript = tss.transcript([tss.prompt("hello")])
    payload = {"session_id": session_id, "hook_event_name": "Stop", "cwd": SCRATCH,
               "transcript_path": transcript, "stop_hook_active": False}
    rc, out, err = tss.run_stop(transcript, stdin=json.dumps(payload).encode("utf-8"))
    problems = expect(rc == 0, "Stop exit %d, want 0: %s" % (rc, err.strip()[:200]))
    return problems, tss.system_message(out, problems), out


# --------------------------------------------------------------------------- Part A: the session-start check

@case
def C1_token_file_present_is_silent_and_never_probes():
    """C1. a token file holds a token: auth_check prints nothing and makes no probe"""
    with scratch_config("c1") as cfg:
        token_file(cfg, FAKE_TOKEN + "\n")
        problems = scoped(cfg)
        fn, miss = interface("auth_check")
        if miss:
            return problems + miss
        probe = Probe((OK_VERDICT, None))
        text = fn(model_call=probe)
    problems += expect(text == "", "token file present: auth_check printed %r, want nothing" % text)
    problems += expect(not probe.calls, "token file present: the probe ran %d time(s), want 0" % len(probe.calls))
    return problems


@case
def C2_no_token_or_empty_token_file_probes_once_and_stays_silent_when_it_succeeds():
    """C2. no token file, or an empty one (the cloud case): one probe that succeeds, and nothing printed"""
    problems = []
    for name, data in (("absent", None), ("empty", b"")):
        with scratch_config("c2-" + name) as cfg:
            if data is not None:
                token_file(cfg, data)
            problems += scoped(cfg)
            fn, miss = interface("auth_check")
            if miss:
                return problems + miss
            probe = Probe((OK_VERDICT, None))
            text = fn(model_call=probe)
        problems += expect(text == "", "%s token file, probe succeeded: auth_check printed %r" % (name, text))
        problems += expect(len(probe.calls) == 1,
                           "%s token file: the probe ran %d time(s), want 1" % (name, len(probe.calls)))
        if len(probe.calls) == 1:
            _args, kwargs = probe.calls[0]
            problems += expect(kwargs.get("effort", "unset") is None,
                               "%s token file: probe effort is %r, want None" % (name, kwargs.get("effort", "unset")))
            timeout = kwargs.get("timeout")
            problems += expect(isinstance(timeout, (int, float)) and timeout < dw.MODEL_TIMEOUT,
                               "%s token file: probe timeout is %r, want a short one" % (name, timeout))
    return problems


@case
def C3_no_token_and_probe_fails_warns_once_with_the_fix():
    """C3. no token file, probe fails: one line names claude setup-token, the hook-token path and the error"""
    with scratch_config("c3") as cfg:
        problems = scoped(cfg)
        fn, miss = interface("auth_check")
        if miss:
            return problems + miss
        probe = Probe((None, FAIL_ERR))
        text = fn(model_call=probe)
        path = os.path.join(cfg, HOOK_TOKEN_REL)
    if text == "":
        return problems + ["no token file and the probe failed: auth_check printed nothing"]
    problems += expect(len(probe.calls) == 1, "no token file: the probe ran %d time(s), want 1" % len(probe.calls))
    problems += expect("\n" not in text, "the warning spans more than one line: %r" % text)
    problems += expect(SETUP in text, "the warning does not name %r: %r" % (SETUP, text))
    problems += expect(path in text, "the warning does not name the hook-token path %r: %r" % (path, text))
    problems += expect(STDERR in text, "the warning does not carry the probe error: %r" % text)
    return problems


@case
def C4_token_file_that_is_not_text_warns_with_the_fix_and_never_probes():
    """C4. a token file that is not text: one warning with the fix, no probe, and none of the file's bytes printed"""
    with scratch_config("c4") as cfg:
        token_file(cfg, b"\x80\x81\xfe" + UNREADABLE_MARK)
        problems = scoped(cfg)
        fn, miss = interface("auth_check")
        if miss:
            return problems + miss
        probe = Probe((OK_VERDICT, None))
        text = fn(model_call=probe)
        path = os.path.join(cfg, HOOK_TOKEN_REL)
    if text == "":
        return problems + ["token file is not text: auth_check printed nothing"]
    problems += expect(not probe.calls, "token file is not text: the probe ran %d time(s), want 0" % len(probe.calls))
    problems += expect(SETUP in text, "the warning does not name %r: %r" % (SETUP, text))
    problems += expect(path in text, "the warning does not name the hook-token path %r: %r" % (path, text))
    problems += expect(UNREADABLE_MARK.decode() not in text, "the warning prints the token file's bytes: %r" % text)
    return problems


@case
def C9_entry_flag_is_in_settings_once_and_no_stop_command_is_added():
    """C9. settings.json: one SessionStart command runs decision_watch.py --auth-check; no Stop command names it"""
    with open(os.path.join(os.path.dirname(HERE), "settings.json"), encoding="utf-8") as f:
        hooks = json.load(f)["hooks"]

    def commands(event):
        return [h.get("command", "") for grp in hooks.get(event, []) for h in grp.get("hooks", [])]

    starts = [c for c in commands("SessionStart") if "decision_watch.py" in c]
    problems = expect(len(starts) == 1,
                      "want one SessionStart command naming decision_watch.py, found %d" % len(starts))
    if len(starts) == 1:
        cmd = starts[0]
        problems += expect("--auth-check" in cmd, "the SessionStart command has no --auth-check: %r" % cmd)
        problems += expect("CLAUDE_CONFIG_DIR" in cmd and "exit 0" in cmd,
                           "the SessionStart command lacks the launcher shape of the other hooks: %r" % cmd)
    problems += expect(not [c for c in commands("Stop") if "decision_watch" in c],
                       "a Stop command names decision_watch: the streak must ride the existing Stop hook")
    problems += expect(any("stall_watch.py" in c and "--stop" in c for c in commands("Stop")),
                       "the existing stall_watch --stop Stop command is gone")
    return problems


# --------------------------------------------------------------------------- Part B: the failure streak

@case
def C5_three_failures_show_count_fix_and_last_error_and_a_success_clears_the_line():
    """C5. three failures in a row: the Stop line says 3, with the last error and the fix; 12 says 12; success clears it"""
    sid = "model-auth-c5"
    with scratch_config("c5") as cfg:
        problems = scoped(cfg) + takes_session_id_problems()
        if problems:
            return problems
        path = os.path.join(cfg, HOOK_TOKEN_REL)
        for _ in range(3):
            invoke_failing(session_id=sid)
        p, msg, _out = stop_message(sid)
        problems += p
        problems += expect("Model calls: 3 failed in a row" in msg, "after 3 failures the Stop line is %r" % msg)
        problems += expect(STDERR in msg, "the Stop line does not carry the last error: %r" % msg)
        problems += expect("Hook judges are not running" in msg, "the Stop line does not say judges stopped: %r" % msg)
        problems += expect(SETUP in msg and path in msg, "the Stop line does not give the fix: %r" % msg)
        for _ in range(9):
            invoke_failing(session_id=sid)
        p, msg, _out = stop_message(sid)
        problems += p
        problems += expect("Model calls: 12 failed in a row" in msg, "after 12 failures the Stop line is %r" % msg)
        invoke_ok(session_id=sid)
        p, msg, _out = stop_message(sid)
        problems += p
        problems += expect("Model calls:" not in msg, "after a success the Stop line is still %r" % msg)
    return problems


@case
def C6_fewer_than_three_failures_show_no_line_and_the_third_shows_it():
    """C6. no failures, then two: no Stop line. The third failure brings the line"""
    sid = "model-auth-c6"
    with scratch_config("c6") as cfg:
        problems = scoped(cfg) + takes_session_id_problems()
        if problems:
            return problems
        p, msg, _out = stop_message(sid)
        problems += p
        problems += expect("Model calls:" not in msg, "no failures yet: the Stop line is %r" % msg)
        for _ in range(2):
            invoke_failing(session_id=sid)
        p, msg, _out = stop_message(sid)
        problems += p
        problems += expect("Model calls:" not in msg, "two failures: the Stop line is %r" % msg)
        invoke_failing(session_id=sid)
        p, msg, _out = stop_message(sid)
        problems += p
        problems += expect("Model calls: 3 failed in a row" in msg, "three failures: the Stop line is %r" % msg)
    return problems


@case
def C7_calls_with_no_session_id_record_nothing_and_the_same_calls_with_one_do():
    """C7. model calls and record_model_outcome with no session id write no file. The same calls with one do"""
    sid = "model-auth-c7"
    with scratch_config("c7") as cfg:
        problems = scoped(cfg)
        record, miss = interface("record_model_outcome")
        if miss:
            return problems + miss
        streak, miss = interface("streak_line")
        if miss:
            return problems + miss
        problems += takes_session_id_problems()
        if problems:
            return problems
        for _ in range(3):
            invoke_failing()
        invoke_failing(session_id=None)
        invoke_failing(session_id="")
        record(None, FAIL_ERR)
        record("", FAIL_ERR)
        problems += expect(streak(None) == "" and streak("") == "",
                           "streak_line for no session id is not empty")
        written = files_under(cfg)
        problems += expect(not written, "no session id, yet these files were written: %s" % written)
        for _ in range(3):
            invoke_failing(session_id=sid)
        problems += expect(bool(files_under(cfg)), "control: three calls with a session id wrote no file")
    return problems


@case
def C8_fake_token_reaches_no_stdout_and_no_written_file_but_the_token_file():
    """C8. a fake token echoed in a model error: the Stop line shows, and the token is in no stdout or written file"""
    sid = "model-auth-c8"
    with scratch_config("c8") as cfg:
        token_file(cfg, FAKE_TOKEN + "\n")
        problems = scoped(cfg) + takes_session_id_problems()
        if problems:
            return problems
        for _ in range(3):
            invoke_failing(stderr="auth failed for " + FAKE_TOKEN, session_id=sid)
        p, msg, out = stop_message(sid)
        problems += p
        problems += expect("Model calls: 3 failed in a row" in msg, "no Stop line to check for the token: %r" % msg)
        problems += expect(FAKE_TOKEN not in out, "the fake token is in the Stop output")
        for rel in files_under(cfg, skip=(HOOK_TOKEN_REL,)):
            with open(os.path.join(cfg, rel), "rb") as f:
                if FAKE_TOKEN.encode("utf-8") in f.read():
                    problems.append("the fake token is in the written file %s" % rel)
    return problems


# --------------------------------------------------------------------------- green controls

@case
def CTRL1_a_failed_model_start_is_an_error_from_invoke_model():
    """CTRL1. control: a failed model start makes invoke_model return (None, error). Green on main"""
    with model_run(FakeRun(returncode=1, stderr=STDERR)):
        verdict, error = dw.invoke_model("judge this")
    return expect(verdict is None and bool(error) and STDERR in error,
                  "a failed start gave (%r, %r), want (None, an error naming %r)" % (verdict, error, STDERR))


@case
def CTRL2_the_stop_hook_still_lists_a_quiet_background_job():
    """CTRL2. control: the Stop hook still lists a quiet background job (the shared case, green on main)"""
    return tss.stale_moved_job_is_listed()


@case
def CTRL3_run_folder_sweep_removes_a_day_old_sibling_and_keeps_a_new_one():
    """CTRL3. control: the run-folder sweep removes a sibling run folder over a day old, and keeps a new one"""
    root = os.path.join(SCRATCH, "sweep-root")
    old = os.path.join(root, "1-" + uuid.uuid4().hex)
    new = os.path.join(root, "2-" + uuid.uuid4().hex)
    os.makedirs(old)
    os.makedirs(new)
    two_days_ago = time.time() - 2 * 24 * 60 * 60  # set up only, never read in an assert
    os.utime(old, (two_days_ago, two_days_ago))
    own = _test_temp.run_folder(temp_root=root)
    problems = expect(not os.path.exists(old), "a sibling run folder over a day old was kept")
    problems += expect(os.path.isdir(new), "a new sibling run folder was removed")
    problems += expect(os.path.isdir(own), "the run's own folder is missing")
    return problems


if __name__ == "__main__":
    rc = run_cases(CASES)
    if REAL_CALLS:
        print("FAIL a case tried a real claude start: %s" % ", ".join(REAL_CALLS))
        rc = 1
    sys.exit(rc)
