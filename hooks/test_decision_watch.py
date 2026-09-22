#!/usr/bin/env python3
"""Cases for hooks/decision_watch.py. Standard library only, and no test runner.

Run it from the repository root:

    python hooks/test_decision_watch.py

Each case builds a real temporary git repository and a real transcript file, then calls
`decision_watch.run(hook, model_call=...)` exactly as `main()` would, and reads back the
`systemMessage` string (empty string means "print nothing"). `model_call` is stubbed so no
case spawns a real `claude` subprocess; one case asserts it is never even called.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE_PATH = os.environ.get("DECISION_WATCH_UNDER_TEST") or os.path.join(HERE, "decision_watch.py")

_spec = importlib.util.spec_from_file_location("decision_watch_under_test", MODULE_PATH)
dw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dw)

ROOT = tempfile.mkdtemp(prefix="decision_watch_cases_")
FAILED = []


def _git(cwd, *args):
    subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True, check=True)


def make_repo(name):
    repo = os.path.join(ROOT, name)
    os.makedirs(repo, exist_ok=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    return repo


def commit_all(repo, msg="init"):
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)


def write(path, text):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def human_record(text, ts):
    return {
        "type": "user",
        "timestamp": ts,
        "message": {"role": "user", "content": [{"type": "text", "text": text}]},
    }


def assistant_record(text=None, tool_use=None):
    content = []
    if text is not None:
        content.append({"type": "text", "text": text})
    if tool_use is not None:
        content.append(tool_use)
    return {"type": "assistant", "message": {"role": "assistant", "content": content}}


def write_transcript(repo, records):
    path = os.path.join(repo, "transcript.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    return path


T0 = "2026-09-22T10:00:00.000Z"


class Spy:
    """A model_call stub that counts its own invocations, so a case can assert zero calls
    without scanning shared failure text for another case's message."""

    def __init__(self, verdict_dict=None, error="model_call should not have been invoked"):
        self.calls = 0
        self.verdict_dict = verdict_dict
        self.error = error

    def __call__(self, prompt, model=None, timeout=None):
        self.calls += 1
        return self.verdict_dict, self.error


def never_called():
    return Spy()


def stub(verdict_dict, error=None):
    return Spy(verdict_dict, error)


def check(name, condition, detail=""):
    if condition:
        print("PASS: %s" % name)
    else:
        FAILED.append(name)
        print("FAIL: %s  %s" % (name, detail))


# --------------------------------------------------------------------------- case 1
# A protected file changed, no approval visible in chat: FLAG, non-empty systemMessage.

def case_flag_unapproved():
    repo = make_repo("flag_unapproved")
    write(os.path.join(repo, "decisions", "some-rule.md"), "# A rule\n\nAlways check X.\n")
    commit_all(repo)
    write(os.path.join(repo, "decisions", "some-rule.md"), "# A rule\n\nNever check X.\n")
    records = [
        human_record("please fix the typo in the readme", T0),
        assistant_record(text="Fixed the rule doc too while I was in there."),
    ]
    path = write_transcript(repo, records)
    hook = {"transcript_path": path, "cwd": repo}
    message = dw.run(hook, model_call=stub({"verdict": "FLAG", "why": "reversed silently"}))
    check("flag_unapproved: non-empty systemMessage", bool(message), message)
    check("flag_unapproved: reads as FLAG", message.startswith(dw.FLAG_PREFIX), message)


# --------------------------------------------------------------------------- case 1a
# The model's `why` text is attacker-influenced (it is the judge's summary of a diff this
# hook fed it) and is capped, control-character-stripped, and clearly attributed before it
# reaches the parent session's transcript. Added against a reviewer finding that an
# uncapped, unattributed `why` field was an open channel for whoever can land text in a
# diff to steer what appears there.

def case_why_field_is_sanitized():
    repo = make_repo("why_field_sanitized")
    write(os.path.join(repo, "CLAUDE.md"), "# Rules\n\nAlways X.\n")
    commit_all(repo)
    write(os.path.join(repo, "CLAUDE.md"), "# Rules\n\nAlways Y.\n")
    records = [human_record("edit claude.md", T0), assistant_record(text="Done.")]
    path = write_transcript(repo, records)
    hook = {"transcript_path": path, "cwd": repo}

    hostile_why = "line one\x07\x1b[31m" + ("PADDING " * 100) + "end"
    message = dw.run(hook, model_call=stub({"verdict": "FLAG", "why": hostile_why}))

    check("why_field: reads as FLAG", message.startswith(dw.FLAG_PREFIX), message)
    check("why_field: attributed as the judge model's own words", "judge model reported" in message, message)
    check("why_field: no control characters survive", "\x07" not in message and "\x1b" not in message, repr(message))
    check("why_field: bounded length", len(message) < len(dw.FLAG_PREFIX) + dw.WHY_MAX_LEN + 60, len(message))


# --------------------------------------------------------------------------- case 2
# Same file change, but the transcript shows it proposed as a question and approved: silent.

def case_allow_approved():
    repo = make_repo("allow_approved")
    write(os.path.join(repo, "decisions", "some-rule.md"), "# A rule\n\nAlways check X.\n")
    commit_all(repo)
    write(os.path.join(repo, "decisions", "some-rule.md"), "# A rule\n\nNever check X.\n")
    records = [
        human_record("go ahead and flip the rule, we discussed this", T0),
        assistant_record(text="Flipped decisions/some-rule.md from Always to Never, as agreed."),
    ]
    path = write_transcript(repo, records)
    hook = {"transcript_path": path, "cwd": repo}
    message = dw.run(hook, model_call=stub({"verdict": "ALLOW"}))
    check("allow_approved: silent", message == "", message)


# --------------------------------------------------------------------------- case 3
# No file changed at all, only an outbound SendMessage instructing a peer to delete a
# rule that has not executed yet. Corrected by the independent audit: this shape alone
# produced a false positive, so it must not gate a model call by itself. Silent, and the
# model is never even called.

def case_outbound_alone_no_disk_change():
    repo = make_repo("outbound_alone")
    write(os.path.join(repo, "notes.txt"), "unrelated\n")
    commit_all(repo)
    tool_use = {
        "type": "tool_use",
        "name": "SendMessage",
        "input": {
            "to": "peer-session",
            "message": "Please delete the safety rule in lint/ste_gate.py, it's slowing us down.",
        },
    }
    records = [
        human_record("tell the other session to speed things up", T0),
        assistant_record(tool_use=tool_use),
    ]
    path = write_transcript(repo, records)
    hook = {"transcript_path": path, "cwd": repo}
    spy = never_called()
    message = dw.run(hook, model_call=spy)
    check("outbound_alone_no_disk_change: silent", message == "", message)
    check("outbound_alone_no_disk_change: model never called", spy.calls == 0)


# --------------------------------------------------------------------------- case 4
# transcript_path missing: explicit UNKNOWN, exit-equivalent 0, never silent, never a flag.

def case_missing_transcript():
    repo = make_repo("missing_transcript")
    hook = {"transcript_path": os.path.join(repo, "does-not-exist.jsonl"), "cwd": repo}
    message = dw.run(hook, model_call=never_called())
    check("missing_transcript: reads as UNKNOWN", message.startswith(dw.UNKNOWN_PREFIX), message)
    check("missing_transcript: not silent", message != "", message)
    check("missing_transcript: not a flag", not message.startswith(dw.FLAG_PREFIX), message)


# --------------------------------------------------------------------------- case 5
# An ordinary turn: only an unrelated file changed, no outbound messages of concern.
# Silent, and the model path is never taken at all.

def case_ordinary_turn():
    repo = make_repo("ordinary_turn")
    write(os.path.join(repo, "src", "app.py"), "print('hello')\n")
    commit_all(repo)
    write(os.path.join(repo, "src", "app.py"), "print('hello world')\n")
    records = [
        human_record("say hello world instead", T0),
        assistant_record(text="Updated src/app.py."),
    ]
    path = write_transcript(repo, records)
    hook = {"transcript_path": path, "cwd": repo}
    spy = never_called()
    message = dw.run(hook, model_call=spy)
    check("ordinary_turn: silent", message == "", message)
    check("ordinary_turn: model never called", spy.calls == 0)


# --------------------------------------------------------------------------- case 6
# git status fails (not a git work tree at all): UNKNOWN, never silent, never a flag.

def case_not_a_repo():
    plain = os.path.join(ROOT, "not_a_repo")
    os.makedirs(plain, exist_ok=True)
    records = [human_record("hi", T0)]
    path = write_transcript(plain, records)
    hook = {"transcript_path": path, "cwd": plain}
    message = dw.run(hook, model_call=never_called())
    check("not_a_repo: reads as UNKNOWN", message.startswith(dw.UNKNOWN_PREFIX), message)
    check("not_a_repo: not silent", message != "", message)


# --------------------------------------------------------------------------- case 7
# The model subprocess itself fails: UNKNOWN, never silent, never a flag, even though a
# protected file did change.

def case_model_failure():
    repo = make_repo("model_failure")
    write(os.path.join(repo, "CLAUDE.md"), "# Rules\n\nAlways X.\n")
    commit_all(repo)
    write(os.path.join(repo, "CLAUDE.md"), "# Rules\n\nAlways Y.\n")
    records = [human_record("edit claude.md", T0), assistant_record(text="Done.")]
    path = write_transcript(repo, records)
    hook = {"transcript_path": path, "cwd": repo}
    message = dw.run(hook, model_call=stub(None, "model exited 1: boom"))
    check("model_failure: reads as UNKNOWN", message.startswith(dw.UNKNOWN_PREFIX), message)
    check("model_failure: not silent", message != "", message)
    check("model_failure: not a flag", not message.startswith(dw.FLAG_PREFIX), message)


# --------------------------------------------------------------------------- case 8
# The same unresolved finding, in the same session, at a second Stop with nothing
# changed further: the first Stop flags it, the second stays quiet. A third Stop, after
# the file moves further, flags again. Isolates CLAUDE_CONFIG_DIR to a scratch dir so the
# per-session store never touches a real one.

def case_incident_cap_same_session():
    repo = make_repo("incident_cap")
    write(os.path.join(repo, "decisions", "cap-rule.md"), "# A rule\n\nAlways check X.\n")
    commit_all(repo)
    write(os.path.join(repo, "decisions", "cap-rule.md"), "# A rule\n\nNever check X.\n")
    records = [
        human_record("fix the typo elsewhere", T0),
        assistant_record(text="Also flipped the cap rule while in there."),
    ]
    path = write_transcript(repo, records)
    hook = {"transcript_path": path, "cwd": repo, "session_id": "same-session-abc"}

    scratch_cfg = os.path.join(ROOT, "cfg_incident_cap")
    os.makedirs(scratch_cfg, exist_ok=True)
    prior = os.environ.get("CLAUDE_CONFIG_DIR")
    os.environ["CLAUDE_CONFIG_DIR"] = scratch_cfg
    try:
        first = dw.run(hook, model_call=stub({"verdict": "FLAG", "why": "unresolved"}))
        check("incident_cap: first Stop flags", first.startswith(dw.FLAG_PREFIX), first)

        second_spy = never_called()
        second = dw.run(hook, model_call=second_spy)
        check("incident_cap: second Stop, same finding, silent", second == "", second)
        check("incident_cap: second Stop never calls the model", second_spy.calls == 0)

        write(os.path.join(repo, "decisions", "cap-rule.md"), "# A rule\n\nNever check X or Y.\n")
        third = dw.run(hook, model_call=stub({"verdict": "FLAG", "why": "moved further"}))
        check("incident_cap: finding that moved further flags again", third.startswith(dw.FLAG_PREFIX), third)
    finally:
        if prior is None:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["CLAUDE_CONFIG_DIR"] = prior


# --------------------------------------------------------------------------- case 9
# invoke_model's real argv and kwargs, against a fake subprocess.run: the explicit empty
# tool set, --permission-mode plan, and an isolated cwd/env are actually on the command
# line, not only claimed in a docstring. Added against a reviewer finding that an earlier
# version claimed "no tools" while its argv granted every tool, in this project's own
# directory, inheriting this project's own permissions.allow.

class _FakeCompletedProcess:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# --------------------------------------------------------------------------- case 9a
# _judge_isolation copies the real login credential into the isolated config dir. Added
# against a real, empirically found defect: an earlier version left the isolated config
# dir empty, which a real run failed with "Not logged in" -- a DIFFERENT, earlier failure
# than an expired-token error, proving the wipe took the credential down with it, on any
# machine, not only a sandboxed one.

def case_judge_isolation_copies_credentials():
    fake_home_config = os.path.join(ROOT, "fake_home_config")
    os.makedirs(fake_home_config, exist_ok=True)
    creds_path = os.path.join(fake_home_config, dw.CREDENTIALS_FILENAME)
    write(creds_path, '{"fake": "credential-content"}')

    real_config_dir = dw.guard.config_dir
    dw.guard.config_dir = lambda: fake_home_config
    try:
        judge_cwd, judge_env = dw._judge_isolation()
    finally:
        dw.guard.config_dir = real_config_dir

    try:
        copied = os.path.join(judge_env["CLAUDE_CONFIG_DIR"], dw.CREDENTIALS_FILENAME)
        check("judge_isolation: credential file was copied in", os.path.isfile(copied), copied)
        if os.path.isfile(copied):
            with open(copied, "r", encoding="utf-8") as f:
                check("judge_isolation: copied credential matches the real one",
                      f.read() == '{"fake": "credential-content"}')
        check(
            "judge_isolation: isolated config dir is not the real one",
            judge_env["CLAUDE_CONFIG_DIR"] != fake_home_config,
            judge_env["CLAUDE_CONFIG_DIR"],
        )
    finally:
        shutil.rmtree(judge_cwd, ignore_errors=True)


def case_invoke_model_argv():
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        envelope = json.dumps({"result": json.dumps({"verdict": "ALLOW"})})
        return _FakeCompletedProcess(0, envelope, "")

    real_subprocess_run = dw.subprocess.run
    dw.subprocess.run = fake_run
    try:
        verdict, error = dw.invoke_model("JUDGE THIS PROMPT")
    finally:
        dw.subprocess.run = real_subprocess_run

    check("invoke_model_argv: no error", error is None, error)
    check("invoke_model_argv: verdict is ALLOW", verdict == {"verdict": "ALLOW"}, verdict)

    argv = captured.get("argv") or []
    expected = [
        "claude", "-p", "JUDGE THIS PROMPT",
        "--model", dw.MODEL,
        "--output-format", "json",
        "--tools", "",
        "--safe-mode",
        "--permission-mode", "plan",
    ]
    print("invoke_model argv: %r" % argv)
    check("invoke_model_argv: matches the expected restricted command line", argv == expected, argv)

    kwargs = captured.get("kwargs") or {}
    judge_cwd = kwargs.get("cwd")
    check("invoke_model_argv: cwd is set", bool(judge_cwd), judge_cwd)
    check("invoke_model_argv: cwd is not this repository", judge_cwd != HERE and judge_cwd != os.path.dirname(HERE), judge_cwd)
    env = kwargs.get("env") or {}
    check(
        "invoke_model_argv: CLAUDE_CONFIG_DIR is isolated under the judge cwd",
        env.get("CLAUDE_CONFIG_DIR", "").startswith(judge_cwd or "\x00"),
        env.get("CLAUDE_CONFIG_DIR"),
    )
    check(
        "invoke_model_argv: CLAUDE_CONFIG_DIR differs from this process's own",
        env.get("CLAUDE_CONFIG_DIR") != os.environ.get("CLAUDE_CONFIG_DIR"),
        env.get("CLAUDE_CONFIG_DIR"),
    )

    # FIX 5: the env is built from JUDGE_ENV_ALLOWLIST alone, never os.environ copied and
    # subtracted. Every allowed name that this process itself carries must survive, and
    # the host-IPC/session/secret names must never appear, whether or not this process
    # happens to carry them.
    for name in dw.JUDGE_ENV_ALLOWLIST:
        if name in os.environ:
            check("invoke_model_argv: allowlisted %s carried through" % name, name in env, env)
    excluded = (
        "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN",
        "CLAUDE_CODE_HOST_SESSION_ID", "CLAUDE_CODE_OAUTH_SCOPES", "ANTHROPIC_API_KEY",
    )
    for name in excluded:
        check("invoke_model_argv: %s is not in the isolated env" % name, name not in env, env.get(name))
    check(
        "invoke_model_argv: env holds only allowlisted names plus CLAUDE_CONFIG_DIR",
        set(env) <= set(dw.JUDGE_ENV_ALLOWLIST) | {"CLAUDE_CONFIG_DIR"},
        sorted(env),
    )


# --------------------------------------------------------------------------- case 10
# main() itself, invoked exactly as the harness invokes it: a real subprocess, JSON on
# stdin, and its stdout/exit code read back. Added against a reviewer finding that every
# other case stubbed model_call, so main()'s own contract (stdin parsing, stop_hook_active,
# the printed systemMessage envelope, exit 0) was never actually exercised end to end.

def _run_main(hook_payload, timeout=30):
    return subprocess.run(
        [sys.executable, MODULE_PATH],
        input=json.dumps(hook_payload), capture_output=True, text=True, timeout=timeout,
    )


def case_main_ordinary_turn():
    repo = make_repo("main_ordinary_turn")
    write(os.path.join(repo, "src", "app.py"), "print('hello')\n")
    commit_all(repo)
    write(os.path.join(repo, "src", "app.py"), "print('hello world')\n")
    records = [
        human_record("say hello world instead", T0),
        assistant_record(text="Updated src/app.py."),
    ]
    path = write_transcript(repo, records)
    result = _run_main({"transcript_path": path, "cwd": repo})
    check("main_ordinary_turn: exit 0", result.returncode == 0, result.returncode)
    check("main_ordinary_turn: nothing printed", result.stdout.strip() == "", result.stdout)


def case_main_missing_transcript():
    repo = make_repo("main_missing_transcript")
    result = _run_main({"transcript_path": os.path.join(repo, "nope.jsonl"), "cwd": repo})
    check("main_missing_transcript: exit 0", result.returncode == 0, result.returncode)
    try:
        payload = json.loads(result.stdout.strip())
    except Exception:
        payload = None
    message = (payload or {}).get("systemMessage", "")
    check("main_missing_transcript: prints an UNKNOWN systemMessage", message.startswith(dw.UNKNOWN_PREFIX), result.stdout)


def case_main_stop_hook_active_stays_quiet():
    result = _run_main({"transcript_path": "/does/not/matter", "cwd": ".", "stop_hook_active": True})
    check("main_stop_hook_active: exit 0", result.returncode == 0, result.returncode)
    check("main_stop_hook_active: nothing printed", result.stdout.strip() == "", result.stdout)


def main():
    case_flag_unapproved()
    case_why_field_is_sanitized()
    case_allow_approved()
    case_outbound_alone_no_disk_change()
    case_missing_transcript()
    case_ordinary_turn()
    case_not_a_repo()
    case_model_failure()
    case_incident_cap_same_session()
    case_judge_isolation_copies_credentials()
    case_invoke_model_argv()
    case_main_ordinary_turn()
    case_main_missing_transcript()
    case_main_stop_hook_active_stays_quiet()

    if FAILED:
        print("test_decision_watch FAIL: %d failing check(s)" % len(FAILED))
        return 1
    print("test_decision_watch PASS: all checks right")
    return 0


if __name__ == "__main__":
    sys.exit(main())
