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
    The fix is prompted once: a later start in the same config dir with no token file prints nothing.
    Why: the setup must work on every account and device, or the fix must be prompted once.
    A successful recorded judge call clears that mark (record_model_outcome), so a lost login after a repaired
    one prints the fix again. A reply at exit 0 that is not a verdict but asks for a login ("Please run /login")
    prints one line; it is not a working login.
- decision_watch.invoke_model(prompt, ..., session_id=None) -> (verdict | None, error | None)
    Gains one keyword. A non-empty session_id records the outcome: a failure adds one to the session's
    consecutive-failure count and keeps the scrubbed error; a success resets the count.
    Without a session_id nothing is recorded.
- decision_watch.record_model_outcome(session_id, error) -> None
    error None is a success: it resets the count and clears the prompted mark, so the fix shows again for a
    later lost login. A falsy session_id writes nothing.
- decision_watch.streak_line(session_id) -> str
    An AUTH error (its text names a lost login) gives the line from the first failure, with the auth_check fix,
    and no streak wait. Owner, 11:43 CST Nov 6: "It never fails quietly". Coordinator ruling, 08:28 CST Nov 12.
    Any other error (RUN) gives '' below three failures in a row. From three on: "Model calls: N failed in a row
    this session (last: <error>). Hook judges are not running." and no fix line, since the error names no login.
- hooks/stall_watch.py --stop (the existing Stop hook) puts streak_line in its one systemMessage line.
- The classifier: invoke_model's error (a str) carries `kind`. "AUTH": the model start exited non-zero and its
    text names an authentication failure ("401", "Invalid API key", "/login", "authentication"). "RUN": a start
    that failed, a timeout, or any other non-zero exit. "REPLY": a ReplyError, a call that ran and answered
    badly. An exit 0 with an envelope `is_error: true` is a failure, "AUTH" or "RUN" by the same text test,
    never "REPLY". An error with no kind reads as "RUN". auth_check gives the setup-token fix for "AUTH" only. "RUN" names the error and says the
    check failed. The R1 to R3 cases stub hooks/_nowindow.run, the one start a model call makes.
- settings.json: one SessionStart command runs decision_watch.py --auth-check. No Stop command names
  decision_watch.
- The streak file lives under the config dir's state folder. These cases do not name it. They scan every
  file there except the token file.
"""
import contextlib
import importlib.util
import inspect
import io
import json
import os
import subprocess
import sys
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lint"))
import _test_temp  # noqa: E402  test-temp-standard: sweeps and makes run folders (lint/_test_temp.py)
import _nowindow  # noqa: E402  the one home of a no-window start; R1 to R3 stub its run (hooks/_nowindow.py)
from case_runner_test import Skip, run_cases  # noqa: E402
import test_stall_watch_stop as tss  # noqa: E402  the Stop harness and its stale-job case: called, not copied

# Loaded the way hooks/test_decision_watch.py loads it. Not imported from there: that module makes a
# scratch folder in the system temp dir when it is imported, outside this run's folder.
DW_PATH = os.environ.get("DECISION_WATCH_UNDER_TEST") or os.path.join(HERE, "decision_watch.py")
_spec = importlib.util.spec_from_file_location("decision_watch_under_test", DW_PATH)
dw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dw)

SCRATCH = tss.SCRATCH  # one run folder per run: the Stop harness makes it and removes it at exit

FAKE_TOKEN = "sk-ant-oat01-FAKE"
KEY_NAME = "ANTHROPIC_API_KEY"
FAKE_KEY = "sk-ant-api03-FAKE"  # a fake value: a failure names the key's presence, never its value
UNREADABLE_MARK = b"BYTES-MARKER"
SETUP = "claude setup-token"
HOOK_TOKEN_REL = os.path.join("state", "hook-token")
STDERR = "not logged in"
RUN_STDERR = "connection reset by peer"  # a failed start that names no login: its kind is RUN (no AUTH_TEXT match)
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


class Kinded(str):
    """An error text that carries `kind`, as invoke_model's error does (the classifier named at the top of the file)."""

    def __new__(cls, text, kind):
        error = super().__new__(cls, text)
        error.kind = kind
        return error


class Probe:
    """Stands in for invoke_model as auth_check's model_call. Records each call and returns `result`."""

    def __init__(self, result):
        self.result = result
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.result


@contextlib.contextmanager
def scratch_config(name, parent_key=None):
    """Point CLAUDE_CONFIG_DIR at this case's own folder under the run folder, and set or clear this
    process's ANTHROPIC_API_KEY, then restore both. A case that names no key starts with it cleared."""
    cfg = os.path.join(SCRATCH, "config-" + name)
    os.makedirs(cfg, exist_ok=True)
    keys = ("CLAUDE_CONFIG_DIR", KEY_NAME)
    prior = {k: os.environ.get(k) for k in keys}
    os.environ["CLAUDE_CONFIG_DIR"] = cfg
    if parent_key is None:
        os.environ.pop(KEY_NAME, None)
    else:
        os.environ[KEY_NAME] = parent_key
    try:
        yield cfg
    finally:
        for k in keys:
            if prior[k] is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = prior[k]


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
def C1_token_file_present_is_silent_and_never_probes_and_a_first_login_failure_names_the_fix():
    """C1. a token file holds a token: auth_check prints nothing and makes no probe. Then a judge call fails with a
    lost login: the Stop line names the fix on that first failure, with no streak wait. Owner, 11:43 CST Nov 6:
    "It never fails quietly". Coordinator ruling, 08:28 CST Nov 12: the first failure of kind AUTH prints the fix."""
    sid = "model-auth-c1"
    with scratch_config("c1") as cfg:
        token_file(cfg, FAKE_TOKEN + "\n")
        problems = scoped(cfg) + takes_session_id_problems()
        fn, miss = interface("auth_check")
        if miss:
            return problems + miss
        if problems:
            return problems
        probe = Probe((OK_VERDICT, None))
        text = fn(model_call=probe)
        _verdict, error = invoke_failing(session_id=sid)  # the token file stays: the login it names is lost
        kind = getattr(error, "kind", None)
        p, msg, _out = stop_message(sid)
        path = os.path.join(cfg, HOOK_TOKEN_REL)
    problems += p
    problems += expect(text == "", "token file present: auth_check printed %r, want nothing" % text)
    problems += expect(not probe.calls, "token file present: the probe ran %d time(s), want 0" % len(probe.calls))
    problems += expect(kind == "AUTH", "precondition: the lost-login text reads as kind %r, want 'AUTH'" % kind)
    problems += expect(SETUP in msg, "the first lost-login failure gave no Stop line naming %r: %r" % (SETUP, msg))
    problems += expect(path in msg, "the first lost-login failure's Stop line does not name the hook-token path %r: %r"
                       % (path, msg))
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
        probe = Probe((None, Kinded(FAIL_ERR, "AUTH")))  # an authentication failure: the fix applies
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
def C15_the_fix_line_names_the_api_key_the_judge_uses_when_no_setup_token_is_saved():
    """C15. no token file and a failed probe: the one fix line names ANTHROPIC_API_KEY. Why: a judge uses that key
    when no setup token is saved, so an account with only an API key is told the route it can use."""
    with scratch_config("c15") as cfg:
        problems = scoped(cfg)
        fn, miss = interface("auth_check")
        if miss:
            return problems + miss
        probe = Probe((None, Kinded(FAIL_ERR, "AUTH")))  # an authentication failure: the fix applies
        text = fn(model_call=probe)
    if text == "":
        return problems + ["no token file and the probe failed: auth_check printed nothing"]
    problems += expect(KEY_NAME in text, "the fix line does not name ANTHROPIC_API_KEY: %r" % text)
    return problems


@case
def C16_the_fix_line_never_says_the_api_key_is_not_offered():
    """C16. no token file and a failed probe: the fix line does not say the API key is not offered. Why: that
    text is false for a judge with no setup token, so it would send the owner away from a working route."""
    with scratch_config("c16") as cfg:
        problems = scoped(cfg)
        fn, miss = interface("auth_check")
        if miss:
            return problems + miss
        probe = Probe((None, Kinded(FAIL_ERR, "AUTH")))  # an authentication failure: the fix applies
        text = fn(model_call=probe)
    if text == "":
        return problems + ["no token file and the probe failed: auth_check printed nothing"]
    problems += expect("not offered" not in text, "the fix line still says the API key is not offered: %r" % text)
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
def C13_a_second_session_start_with_no_token_does_not_repeat_the_fix():
    """C13. the owner's rule, prompt once: no token file and a failed probe warn with the fix; the next session
    start in the same config folder prints nothing; a token file that appears keeps it silent"""
    with scratch_config("c13-warn-once") as cfg:
        problems = scoped(cfg)
        fn, miss = interface("auth_check")
        if miss:
            return problems + miss
        first = fn(model_call=Probe((None, Kinded(FAIL_ERR, "AUTH"))))
        second = fn(model_call=Probe((None, Kinded(FAIL_ERR, "AUTH"))))
        token_file(cfg, FAKE_TOKEN + "\n")
        third = fn(model_call=Probe((OK_VERDICT, None)))
    problems += expect(SETUP in first, "first start, no token file: the warning does not name %r: %r" % (SETUP, first))
    problems += expect(second == "", "second start, no token file: the fix is prompted again: %r" % second)
    problems += expect(third == "", "token file present: auth_check printed %r, want nothing" % third)
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
    """C5. three failures in a row: the Stop line says 3 with the last error and fix; 12 says 12; success clears it"""
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
def C6_fewer_than_three_run_failures_show_no_line_and_the_third_shows_it():
    """C6. run failures (a reset connection: no login named, kind RUN) give no Stop line after none, or after two.
    The third brings the line. Coordinator ruling, 08:28 CST Nov 12: run failures keep the streak of 3, and a
    lost login does not wait (C1). Owner, 11:43 CST Nov 6: "It never fails quietly"."""
    sid = "model-auth-c6"
    with scratch_config("c6") as cfg:
        problems = scoped(cfg) + takes_session_id_problems()
        if problems:
            return problems
        _verdict, error = invoke_failing(stderr=RUN_STDERR)  # no session id: records nothing
        kind = getattr(error, "kind", None)
        problems += expect(kind == "RUN", "precondition: the run failure's text reads as kind %r, want 'RUN'" % kind)
        p, msg, _out = stop_message(sid)
        problems += p
        problems += expect("Model calls:" not in msg, "no failures yet: the Stop line is %r" % msg)
        for _ in range(2):
            invoke_failing(stderr=RUN_STDERR, session_id=sid)
        p, msg, _out = stop_message(sid)
        problems += p
        problems += expect("Model calls:" not in msg, "two run failures: the Stop line is %r" % msg)
        invoke_failing(stderr=RUN_STDERR, session_id=sid)
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


@case
def C14_a_judge_error_that_holds_the_api_key_keeps_its_text_and_loses_the_key():
    """C14. no token file, the key in this process, and a judge error that echoes the key: the Stop line keeps
    the error text around the key, and the key is in no stdout and no written file. Why: the judge holds the key
    when no token is saved, so the error path must scrub the key as it scrubs the token."""
    sid = "model-auth-c14"
    with scratch_config("c14", parent_key=FAKE_KEY) as cfg:
        problems = scoped(cfg) + takes_session_id_problems()
        problems += expect(os.environ.get(KEY_NAME) == FAKE_KEY, "scope: this process does not carry the fake key")
        problems += expect(not os.path.exists(os.path.join(cfg, HOOK_TOKEN_REL)), "scope: a token file is present")
        if problems:
            return problems
        for _ in range(3):
            invoke_failing(stderr="auth failed for " + FAKE_KEY, session_id=sid)
        p, msg, out = stop_message(sid)
    problems += p
    problems += expect("Model calls: 3 failed in a row" in msg, "no Stop line after three failures")
    problems += expect("auth failed for" in msg, "the Stop line lost the error text around the key")
    problems += expect(FAKE_KEY not in msg, "the API key value is in the Stop line")
    problems += expect(FAKE_KEY not in out, "the API key value is in the Stop output")
    for rel in files_under(cfg):
        with open(os.path.join(cfg, rel), "rb") as f:
            if FAKE_KEY.encode("utf-8") in f.read():
                problems.append("the API key value is in the written file %s" % rel)
    return problems


@case
def C17_an_undecodable_token_file_with_the_api_key_set_never_hands_the_call_to_the_key():
    """C17. an undecodable token file, with ANTHROPIC_API_KEY set in this process: the judge call fails closed
    (no verdict, no judge start), and the key value is in no judge env, no error text, no Stop output, and no
    outcome record. Why: the key is a fallback for a judge with no setup token only, so an undecodable token file
    must never hand the call to the key. Scope: a file that exists and cannot be decoded. A token path that exists
    but cannot be opened is not covered here."""
    sid = "model-auth-c17"
    with scratch_config("c17", parent_key=FAKE_KEY) as cfg:
        problems = scoped(cfg) + takes_session_id_problems()
        problems += expect(os.environ.get(KEY_NAME) == FAKE_KEY, "scope: this process does not carry the fake key")
        token_file(cfg, b"\x80\x81\xfe" + UNREADABLE_MARK)
        problems += expect(os.path.isfile(os.path.join(cfg, HOOK_TOKEN_REL)), "scope: no token file was written")
        if problems:
            return problems
        judge_envs = []

        def judge_start(argv, *args, **kwargs):
            judge_envs.append(dict(kwargs.get("env") or {}))
            return subprocess.CompletedProcess(argv, 0, json.dumps({"result": json.dumps(OK_VERDICT)}), "")

        with model_run(judge_start):
            verdict, error = dw.invoke_model("judge this", session_id=sid)
        text = error or ""
        problems += expect(verdict is None,
                           "undecodable token file with the key set: the judge returned a verdict, want none")
        problems += expect("token file" in text.lower() and "could not be read" in text.lower(),
                           "undecodable token file with the key set: the error does not say the token file "
                           "could not be read: %r" % text)
        problems += expect(UNREADABLE_MARK.decode() not in text, "the error text holds the token file's bytes")
        problems += expect(FAKE_KEY not in text, "the API key value is in the error text")
        problems += expect(not judge_envs,
                           "undecodable token file with the key set: %d judge start(s), want 0" % len(judge_envs))
        for env in judge_envs:
            problems += expect(KEY_NAME not in env and FAKE_KEY not in env.values(),
                               "the API key reached the judge env")
        p, msg, out = stop_message(sid)
        problems += p
        problems += expect("Model calls: 1 failed in a row" in msg, "no Stop line to check for the key: %r" % msg)
        problems += expect(FAKE_KEY not in out, "the API key value is in the Stop output")
        record = files_under(cfg, skip=(HOOK_TOKEN_REL,))
        problems += expect(bool(record), "control: the failed call wrote no outcome record")
        for rel in record:
            with open(os.path.join(cfg, rel), "rb") as f:
                if FAKE_KEY.encode("utf-8") in f.read():
                    problems.append("the API key value is in the written file %s" % rel)
    return problems


FAKE_CLAUDE = (
    "#!/bin/sh\n"
    ": > \"${0%/*}/probe-ran\"\n"  # beside this fake: the child's PATH has no dirname, and no marker variable
    "echo 'not logged in' >&2\n"
    "exit 1\n"
)


def entry_run(name, with_token):
    """Run `decision_watch.py --auth-check` the way the SessionStart hook does. A fake `claude` is the only
    one on PATH, and it writes a marker when started. Return (returncode, stdout, marker written)."""
    cfg = os.path.join(SCRATCH, "config-" + name)
    fake_dir = os.path.join(SCRATCH, "fake-bin-" + name)
    os.makedirs(cfg, exist_ok=True)
    os.makedirs(fake_dir, exist_ok=True)
    fake = os.path.join(fake_dir, "claude")
    with open(fake, "w", encoding="utf-8") as f:
        f.write(FAKE_CLAUDE)
    os.chmod(fake, 0o755)
    marker = os.path.join(fake_dir, "probe-ran")
    if with_token:
        token_file(cfg, FAKE_TOKEN + "\n")
    env = dict(os.environ, CLAUDE_CONFIG_DIR=cfg, PATH=fake_dir)
    env.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
    payload = {"session_id": "model-auth-entry-" + name, "hook_event_name": "SessionStart",
               "cwd": SCRATCH, "source": "startup"}
    proc = subprocess.run([sys.executable, DW_PATH, "--auth-check"], input=json.dumps(payload).encode("utf-8"),
                          capture_output=True, env=env, timeout=30)
    return proc.returncode, proc.stdout.decode("utf-8", "replace"), os.path.exists(marker)


@case
def C10_session_start_entry_prints_one_system_message_line_only_when_the_fix_is_needed():
    """C10. the SessionStart entry: a token file means no output and no claude start. No token file means one
    systemMessage line that names the fix, after one claude start"""
    if os.name == "nt":
        raise Skip("the fake claude is a POSIX shell script")
    rc, out, started = entry_run("c10-token", with_token=True)
    problems = expect(rc == 0, "token file present: the entry exited %d, want 0" % rc)
    problems += expect(out.strip() == "", "token file present: the entry printed %r, want nothing" % out)
    problems += expect(not started, "token file present: claude was started, want no probe")
    rc, out, started = entry_run("c10-absent", with_token=False)
    problems += expect(rc == 0, "no token file: the entry exited %d, want 0" % rc)
    problems += expect(started, "no token file: claude was not started, so no probe ran")
    probe_problems = []
    msg = tss.system_message(out, probe_problems)
    problems += probe_problems
    problems += expect(SETUP in msg, "no token file: the entry's systemMessage does not name %r: %r" % (SETUP, msg))
    problems += expect(STDERR in msg, "no token file: the entry's systemMessage lacks the probe error: %r" % msg)
    return problems


@case
def C11_an_off_shape_reply_is_silent_at_session_start_and_adds_no_stop_line():
    """C11. the model ran and answered off-shape: that login works, so auth_check is silent and three such
    replies give no Stop line. Three plain failures after them give the line (the positive control)"""
    sid = "model-auth-c11"
    with scratch_config("c11") as cfg:
        problems = scoped(cfg)
        fn, miss = interface("auth_check")
        if miss:
            return problems + miss
        problems += takes_session_id_problems()
        if problems:
            return problems

        def off_shape_probe(*args, **kwargs):
            with model_run(FakeRun(stdout=json.dumps({"result": "no verdict"}))):
                return dw.invoke_model(*args, **kwargs)

        text = fn(model_call=off_shape_probe)
        problems += expect(text == "", "an off-shape reply: auth_check printed %r, want nothing" % text)
        for _ in range(3):
            with model_run(FakeRun(stdout=json.dumps({"result": "no verdict"}))):
                _verdict, error = dw.invoke_model("judge this", session_id=sid)
        problems += expect(bool(error), "three off-shape replies: invoke_model gave no error text to check")
        p, msg, _out = stop_message(sid)
        problems += p
        problems += expect("Model calls:" not in msg, "three off-shape replies: the Stop line is %r, want none" % msg)
        for _ in range(3):
            invoke_failing(session_id=sid)
        p, msg, _out = stop_message(sid)
        problems += p
        problems += expect("Model calls: 3 failed in a row" in msg,
                           "control: three plain failures after the off-shape replies: the Stop line is %r" % msg)
    return problems


@case
def C12_three_failed_reply_judge_calls_give_the_stop_line():
    """C12. the reply judge's model call fails three times in one session: the Stop line says 3 failed in a row"""
    import reply_judge  # noqa: E402  hooks/reply_judge.py, a Stop hook that passes its session id to invoke_model
    sid = "model-auth-c12"
    payload = json.dumps({"session_id": sid, "last_assistant_message": "| a | b |\n|---|---|\n| 1 | 2 |",
                          "stop_hook_active": False})
    with scratch_config("c12") as cfg:
        problems = scoped(cfg)
        prior_in, prior_err = sys.stdin, sys.stderr
        try:
            for _ in range(3):
                sys.stdin, sys.stderr = io.StringIO(payload), io.StringIO()
                with model_run(FakeRun(returncode=1, stderr=STDERR)):
                    reply_judge.main()
        finally:
            sys.stdin, sys.stderr = prior_in, prior_err
        p, msg, _out = stop_message(sid)
        problems += p
        problems += expect("Model calls: 3 failed in a row" in msg,
                           "three failed reply judge calls: the Stop line is %r" % msg)
    return problems


# --------------------------------------------------------------------------- the error text, the error kind, is_error envelopes

class NowindowRun:
    """Stands in for hooks/_nowindow.run, the one start a model call makes. Returns `result`, or raises `raises`."""

    def __init__(self, result=None, raises=None):
        self.result, self.raises = result, raises

    def __call__(self, argv, *args, **kwargs):
        if self.raises is not None:
            raise self.raises
        return self.result


@contextlib.contextmanager
def nowindow_run(fake):
    """Route every model start inside the block to `fake`, then restore the real start."""
    prior = _nowindow.run
    _nowindow.run = fake
    try:
        yield fake
    finally:
        _nowindow.run = prior


def started(stdout="", stderr="", returncode=0):
    """A finished model start, as hooks/_nowindow.run returns it."""
    return subprocess.CompletedProcess(["claude", "-p"], returncode, stdout, stderr)


def envelope(result, is_error=False):
    """The JSON envelope `claude -p --output-format json` prints on stdout."""
    return json.dumps({"is_error": is_error, "result": result})


AUTH_TEXT = "Invalid API key · Please run /login"  # the text the CLI prints for a lost login


@case
def R1_a_failed_start_with_empty_stderr_names_the_result_on_stdout():
    """R1. exit 1, empty stderr, a JSON envelope on stdout: the error names the envelope's result, with the token
    scrubbed and at most 200 characters of it"""
    with scratch_config("r1") as cfg:
        token_file(cfg, FAKE_TOKEN + "\n")
        problems = scoped(cfg)
        leaky = envelope("Invalid API key " + FAKE_TOKEN + " " + "z" * 400)
        with nowindow_run(NowindowRun(started(stdout=leaky, returncode=1))):
            verdict, error = dw.invoke_model("judge this")
    problems += expect(verdict is None and error is not None,
                       "a failed start gave (%r, %r), want (None, an error)" % (verdict, error))
    problems += expect("Invalid API key" in str(error),
                       "the error does not name the envelope's result: %r" % (error,))
    problems += expect(FAKE_TOKEN not in str(error), "the error carries the fake token: %r" % (error,))
    problems += expect("z" * 201 not in str(error), "the error carries more than 200 characters of the result")
    return problems


@case
def R2_a_timeout_warns_that_the_check_failed_with_no_setup_fix():
    """R2. a model call that times out: the warning says the check failed and names the timeout, and gives no
    claude setup-token fix, which is for a login that failed. The error's kind is RUN"""
    with scratch_config("r2-timeout") as cfg:
        problems = scoped(cfg)
        fn, miss = interface("auth_check")
        if miss:
            return problems + miss
        timed_out = subprocess.TimeoutExpired(["claude", "-p"], dw.MODEL_TIMEOUT)
        with nowindow_run(NowindowRun(raises=timed_out)):
            text = fn()
        with nowindow_run(NowindowRun(raises=timed_out)):
            _verdict, error = dw.invoke_model("judge this")
    problems += expect(text != "", "a timeout: auth_check printed nothing, want a warning")
    problems += expect("timed out" in text, "the warning does not name the timeout: %r" % text)
    problems += expect("failed" in text, "the warning does not say the check failed: %r" % text)
    problems += expect(SETUP not in text, "a timeout gives the claude setup-token fix: %r" % text)
    problems += expect(getattr(error, "kind", None) == "RUN",
                       "a timeout's error has kind %r, want 'RUN'" % getattr(error, "kind", None))
    return problems


@case
def R2_b_a_start_that_fails_warns_with_the_start_error_and_no_setup_fix():
    """R2. the claude binary cannot start: the warning names the start error and gives no claude setup-token fix.
    The error's kind is RUN"""
    with scratch_config("r2-start") as cfg:
        problems = scoped(cfg)
        fn, miss = interface("auth_check")
        if miss:
            return problems + miss
        missing = OSError("claude binary not found")
        with nowindow_run(NowindowRun(raises=missing)):
            text = fn()
        with nowindow_run(NowindowRun(raises=missing)):
            _verdict, error = dw.invoke_model("judge this")
    problems += expect(text != "", "a failed start: auth_check printed nothing, want a warning")
    problems += expect("binary not found" in text, "the warning does not name the start error: %r" % text)
    problems += expect(SETUP not in text, "a failed start gives the claude setup-token fix: %r" % text)
    problems += expect(getattr(error, "kind", None) == "RUN",
                       "a failed start's error has kind %r, want 'RUN'" % getattr(error, "kind", None))
    return problems


@case
def R2_c_an_authentication_failure_gives_the_setup_token_fix():
    """R2. control: a start that exits non-zero with 'Invalid API key' and '/login' gives the claude setup-token
    fix. The error's kind is AUTH"""
    with scratch_config("r2-auth") as cfg:
        problems = scoped(cfg)
        fn, miss = interface("auth_check")
        if miss:
            return problems + miss
        refused = started(stderr=AUTH_TEXT, returncode=1)
        with nowindow_run(NowindowRun(refused)):
            text = fn()
        with nowindow_run(NowindowRun(refused)):
            _verdict, error = dw.invoke_model("judge this")
    problems += expect(SETUP in text, "an authentication failure does not give the claude setup-token fix: %r" % text)
    problems += expect(getattr(error, "kind", None) == "AUTH",
                       "an authentication failure's error has kind %r, want 'AUTH'" % getattr(error, "kind", None))
    return problems


@case
def R3_exit_zero_with_is_error_counts_as_a_failure_in_the_streak():
    """R3. exit 0 and an envelope with is_error true: a failed call, not a reply that ran, so three in a row give
    the Stop line"""
    sid = "model-auth-r3"
    with scratch_config("r3") as cfg:
        problems = scoped(cfg) + takes_session_id_problems()
        if problems:
            return problems
        errors = []
        for _ in range(3):
            with nowindow_run(NowindowRun(started(stdout=envelope(AUTH_TEXT, is_error=True)))):
                _verdict, error = dw.invoke_model("judge this", session_id=sid)
            errors.append(error)
        p, msg, _out = stop_message(sid)
    problems += p
    problems += expect(not any(isinstance(e, dw.ReplyError) for e in errors),
                       "an is_error envelope came back as a ReplyError, a reply that ran: %r" % errors[-1:])
    problems += expect("Model calls: 3 failed in a row" in msg,
                       "three is_error envelopes: the Stop line is %r, want the three-failure line" % msg)
    return problems


@case
def N1_an_error_with_no_kind_is_read_as_a_run_failure_with_no_setup_fix():
    """N1. a caller's error with no kind (a plain str): auth_check says the check is unknown, names the error, and
    gives no claude setup-token fix. The default is RUN, as record_model_outcome reads it"""
    with scratch_config("n1") as cfg:
        problems = scoped(cfg)
        fn, miss = interface("auth_check")
        if miss:
            return problems + miss
        probe = Probe((None, FAIL_ERR))  # a plain str: no kind attribute
        text = fn(model_call=probe)
    problems += expect(len(probe.calls) == 1, "a kindless error: the probe ran %d time(s), want 1" % len(probe.calls))
    problems += expect("unknown" in text, "a kindless error: auth_check does not say the check is unknown: %r" % text)
    problems += expect(STDERR in text, "a kindless error: the warning does not name the error: %r" % text)
    problems += expect(SETUP not in text, "a kindless error gives the claude setup-token fix: %r" % text)
    return problems


@case
def N2_a_failed_authentication_named_on_stdout_is_an_auth_failure():
    """N2. exit 1, empty stderr, and an envelope on stdout that says the authentication failed: the error is AUTH,
    and auth_check gives the claude setup-token fix"""
    with scratch_config("n2") as cfg:
        problems = scoped(cfg)
        fn, miss = interface("auth_check")
        if miss:
            return problems + miss
        refused = started(stdout=envelope("Failed to authenticate. API Error: 403 forbidden"), returncode=1)
        with nowindow_run(NowindowRun(refused)):
            text = fn()
        with nowindow_run(NowindowRun(refused)):
            _verdict, error = dw.invoke_model("judge this")
    problems += expect(getattr(error, "kind", None) == "AUTH",
                       "a failed authentication named on stdout has kind %r, want 'AUTH'"
                       % getattr(error, "kind", None))
    problems += expect(SETUP in text, "a failed authentication named on stdout gives no claude setup-token fix: %r"
                       % text)
    return problems


@case
def N3_an_is_error_envelope_with_the_token_leaves_no_token_in_the_error_or_the_streak():
    """N3. exit 0 and an envelope with is_error true whose result carries the fake token: the token appears in no
    returned error and in no file the streak writes"""
    sid = "model-auth-n3"
    with scratch_config("n3") as cfg:
        token_file(cfg, FAKE_TOKEN + "\n")
        problems = scoped(cfg) + takes_session_id_problems()
        if problems:
            return problems
        leaky = envelope("API Error: 403 for " + FAKE_TOKEN, is_error=True)
        errors = []
        for _ in range(3):
            with nowindow_run(NowindowRun(started(stdout=leaky))):
                _verdict, error = dw.invoke_model("judge this", session_id=sid)
            errors.append(error)
        written = files_under(cfg, skip=(HOOK_TOKEN_REL,))
        for rel in written:
            with open(os.path.join(cfg, rel), "rb") as f:
                if FAKE_TOKEN.encode("utf-8") in f.read():
                    problems.append("the fake token is in the file %s" % rel)
    problems += expect(not any(FAKE_TOKEN in str(e) for e in errors),
                       "the fake token is in a returned error: %r" % (errors[-1:],))
    problems += expect(bool(written), "control: the failed calls wrote no streak file to check")
    return problems


# --------------------------------------------------------------------------- green controls

@case
def CTRL1_a_failed_model_start_is_an_error_from_invoke_model():
    """CTRL1. control: a failed model start makes invoke_model return (None, error), with the start's error in it.
    It guards the start-failure path, so a red case beside it fails for its own cause."""
    with model_run(FakeRun(returncode=1, stderr=STDERR)):
        verdict, error = dw.invoke_model("judge this")
    return expect(verdict is None and bool(error) and STDERR in error,
                  "a failed start gave (%r, %r), want (None, an error naming %r)" % (verdict, error, STDERR))


@case
def CTRL2_the_stop_hook_still_lists_a_quiet_background_job():
    """CTRL2. control: the Stop hook still lists a quiet background job. It calls the shared Stop-hook case
    stale_moved_job_is_listed, so both suites check one behaviour."""
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


# ---------------------------------------------- the first-failure rule, the prompted mark, the login text

# The refresh failure text, copied verbatim from a real failed refresh, so the cases match what a user sees.
REFRESH_TEXT = ("Failed to refresh OAuth token: another Claude Code process is refreshing it or exited "
                "mid-refresh")


@case
def F2_a_login_repaired_then_lost_again_prints_the_fix_again():
    """F2: the prompted mark must not hide a new failure. No token file. The first lost login prints
    the fix. A judge call that succeeds (the login repaired) clears the mark. The next lost login, at the next session
    start, prints the fix again. A failure is never quiet. Paired control: C13, where the mark still stops a repeat
    in the same state."""
    sid = "model-auth-f2"
    with scratch_config("f2") as cfg:
        problems = scoped(cfg) + takes_session_id_problems()
        fn, miss = interface("auth_check")
        if miss:
            return problems + miss
        if problems:
            return problems
        first = fn(model_call=Probe((None, Kinded(FAIL_ERR, "AUTH"))))
        invoke_ok(session_id=sid)  # the login is repaired: a judge call succeeds
        again = fn(model_call=Probe((None, Kinded(FAIL_ERR, "AUTH"))))  # the credentials expire again
    problems += expect(SETUP in first, "precondition: the first lost login gave no fix naming %r: %r" % (SETUP, first))
    problems += expect(SETUP in again, "a lost login after a repaired login gave no fix naming %r: %r" % (SETUP, again))
    return problems


@case
def F3_an_exit_zero_reply_that_asks_for_login_prints_a_line():
    """F3: an exit-0 reply that is not a verdict and asks for a login ('Please run /login') is a
    ReplyError, which auth_check reads as a working login, so it is silent. Want: auth_check prints one line.
    A failure is never quiet. unmeasured: the real CLI text is not known; this text is a guess.
    C11 pins off-shape replies that carry no login text, so this case is separate from it."""
    with scratch_config("f3") as cfg:
        problems = scoped(cfg)
        fn, miss = interface("auth_check")
        if miss:
            return problems + miss
        asks = started(stdout=envelope("Please run /login"), returncode=0)
        with nowindow_run(NowindowRun(asks)):
            text = fn()
    return problems + expect(text != "",
                             "an exit-0 reply that asks for /login: auth_check printed nothing, want one line")


@case
def F4_a_a_failed_start_with_the_refresh_text_on_stderr_prints_a_line_naming_it():
    """F4: the refresh failure text (REFRESH_TEXT), at exit 1 on stderr, is not quiet: auth_check
    prints one line and the line names the text. A failure is never quiet. The text is a run error (kind RUN,
    no login named), and auth_check must print it, not drop it."""
    with scratch_config("f4-a") as cfg:
        problems = scoped(cfg)
        fn, miss = interface("auth_check")
        if miss:
            return problems + miss
        with nowindow_run(NowindowRun(started(stderr=REFRESH_TEXT, returncode=1))):
            text = fn()
    problems += expect(text != "", "the refresh text on stderr at exit 1: auth_check printed nothing, want one line")
    problems += expect(REFRESH_TEXT in text,
                       "the refresh text on stderr at exit 1: the line does not name it: %r" % text)
    return problems


@case
def F4_c_three_refresh_text_failures_give_the_stop_line():
    """F4, streak half: three failed starts with the refresh text count as three failures in a row, so the Stop line
    comes. Owner, 11:43 CST Nov 6: "It never fails quietly". Keep-green on the build head."""
    sid = "model-auth-f4-c"
    with scratch_config("f4-c") as cfg:
        problems = scoped(cfg) + takes_session_id_problems()
        if problems:
            return problems
        for _ in range(3):
            with nowindow_run(NowindowRun(started(stderr=REFRESH_TEXT, returncode=1))):
                dw.invoke_model("judge this", session_id=sid)
        p, msg, _out = stop_message(sid)
    problems += p
    problems += expect("Model calls: 3 failed in a row" in msg,
                       "three refresh-text failures: the Stop line is %r, want the three-failure line" % msg)
    return problems


if __name__ == "__main__":
    rc = run_cases(CASES)
    if REAL_CALLS:
        print("FAIL a case tried a real claude start: %s" % ", ".join(REAL_CALLS))
        rc = 1
    sys.exit(rc)
