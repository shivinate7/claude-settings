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


def main():
    case_flag_unapproved()
    case_allow_approved()
    case_outbound_alone_no_disk_change()
    case_missing_transcript()
    case_ordinary_turn()
    case_not_a_repo()
    case_model_failure()
    case_incident_cap_same_session()

    if FAILED:
        print("test_decision_watch FAIL: %d failing check(s)" % len(FAILED))
        return 1
    print("test_decision_watch PASS: all checks right")
    return 0


if __name__ == "__main__":
    sys.exit(main())
