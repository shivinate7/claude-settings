#!/usr/bin/env python3
"""Cases for hooks/decision_watch.py. Standard library only, and no test runner.

Run it from the repository root:

    python hooks/test_decision_watch.py

Each case builds a real temporary git repository and a real transcript file, then calls
`decision_watch.run(hook, model_call=...)` exactly as `main()` would, and reads back the
`systemMessage` string (empty string means "print nothing"). `model_call` is stubbed so no
case spawns a real `claude` subprocess; one case asserts it is never even called.
"""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lint"))
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
MODULE_PATH = os.environ.get("DECISION_WATCH_UNDER_TEST") or os.path.join(HERE, "decision_watch.py")

_spec = importlib.util.spec_from_file_location("decision_watch_under_test", MODULE_PATH)
dw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dw)

ROOT = tempfile.mkdtemp(prefix="decision_watch_cases_")
FAILED = []
SKIPPED = []  # cases that cannot run on this platform: printed as SKIP, counted, never a PASS


def _git(cwd, *args):
    subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True, check=True)


def make_repo(name):
    repo = os.path.join(ROOT, name)
    os.makedirs(repo, exist_ok=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    return repo


def commit_all(repo, msg="init", when="2020-01-01T00:00:00Z"):
    """Commit everything. The default date is long before every fixture's human message, so a
    setup commit is never read as work landed this turn; pass `when=None` for a commit made now."""
    _git(repo, "add", "-A")
    env = dict(os.environ, GIT_COMMITTER_DATE=when, GIT_AUTHOR_DATE=when) if when else None
    subprocess.run(["git", "-C", repo, "commit", "-q", "-m", msg], capture_output=True, text=True,
                   check=True, env=env)


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


def skip(name, reason):
    """A case that cannot run on this platform. It prints SKIP and is counted in the summary."""
    SKIPPED.append(name)
    print("SKIP: %s: %s" % (name, reason))


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


# --------------------------------------------------------------------------- case 1z
# A protected file DELETED this turn must still flag. `changed_this_turn` must not call
# os.path.getmtime on a deleted path: the FileNotFoundError would drop the file from the
# changed set, and an empty "protected" set reads as a clean pass, not even UNKNOWN, on
# the case the judge prompt names as a FLAG criterion ("removed").

def case_flag_deleted_protected_file():
    repo = make_repo("flag_deleted_protected")
    rule_path = os.path.join(repo, "decisions", "some-other-rule.md")
    write(rule_path, "# A rule\n\nAlways check X.\n")
    commit_all(repo)
    os.remove(rule_path)
    records = [
        human_record("please fix the typo in the readme", T0),
        assistant_record(text="Removed the stale rule doc too while I was in there."),
    ]
    path = write_transcript(repo, records)
    hook = {"transcript_path": path, "cwd": repo}
    message = dw.run(hook, model_call=stub({"verdict": "FLAG", "why": "removed silently"}))
    check("flag_deleted_protected_file: non-empty systemMessage", bool(message), message)
    check("flag_deleted_protected_file: reads as FLAG", message.startswith(dw.FLAG_PREFIX), message)


# --------------------------------------------------------------------------- case 1a
# The model's `why` text is attacker-influenced (it is the judge's summary of a diff this
# hook fed it). It is capped, control-character-stripped, and attributed before it reaches
# the parent session's transcript: an uncapped, unattributed `why` lets whoever can land
# text in a diff steer what appears there.

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
# rule that has not executed yet. This shape alone is a false positive, so it must not trigger
# a model call by itself. Silent, and the model is never even called.

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


# --------------------------------------------------------------------------- peer reply mid-turn
# A cross-session reply is type user, origin.kind peer, isMeta true. It lands mid-turn, so it is
# never the owner's last message. Both readers here must walk past it to the owner's own line.

def peer_record(body, ts):
    return {
        "type": "user",
        "isMeta": True,
        "timestamp": ts,
        "origin": {"kind": "peer", "from": "uds:fixture-pipe", "msg_id": "m-" + body[:8],
                   "name": "peer-cf", "fromSession": "local_fixture", "fromMode": "bypass",
                   "body": body},
        "message": {"role": "user", "content": "Another Claude session sent a message:\n"
                    '<cross-session-message from="uds:fixture-pipe" from-session="local_fixture" '
                    'from-name="peer-cf" from-mode="bypass">%s</cross-session-message>' % body},
    }


def case_last_human_reader_skips_a_peer_record():
    t1 = "2026-09-22T10:00:05.000Z"
    t2 = "2026-09-22T10:00:09.000Z"
    records = [
        human_record("rename the guard", T0),
        assistant_record(text="Asking a peer."),
        peer_record("Answer: yes, rename it.", t1),
        assistant_record(text="Renamed."),
    ]
    idx, stamp = dw.last_human_index_and_stamp(records)
    check("peer reply: last_human_index_and_stamp finds the owner's line, not the peer's",
          (idx, stamp) == (0, T0), repr((idx, stamp)))
    check("peer reply: last_human_stamp (shared reader) returns the owner's stamp",
          dw.last_human_stamp(records) == T0, repr(dw.last_human_stamp(records)))
    # Pin (green before the fix): a later owner line still wins over an earlier peer reply.
    later = records + [human_record("thanks, now the next one", t2)]
    check("peer reply: a later owner line is still the last human",
          dw.last_human_index_and_stamp(later) == (4, t2), repr(dw.last_human_index_and_stamp(later)))


# --------------------------------------------------------------------------- case 6
# A folder with no git repo: one plain line, once per session, then silence. A new session
# hears it again. Never UNKNOWN jargon, never a flag. CLAUDE_CONFIG_DIR is isolated so the
# per-session store never touches a real one.

def case_not_a_repo():
    plain = os.path.join(ROOT, "not_a_repo")
    os.makedirs(plain, exist_ok=True)
    records = [human_record("hi", T0)]
    path = write_transcript(plain, records)
    hook = {"transcript_path": path, "cwd": plain, "session_id": "no-repo-session-1"}
    line = getattr(dw, "NO_REPO_MESSAGE", "<NO_REPO_MESSAGE missing>")

    scratch_cfg = os.path.join(ROOT, "cfg_not_a_repo")
    os.makedirs(scratch_cfg, exist_ok=True)
    prior = os.environ.get("CLAUDE_CONFIG_DIR")
    os.environ["CLAUDE_CONFIG_DIR"] = scratch_cfg
    try:
        first = dw.run(hook, model_call=never_called())
        check("not_a_repo: first run says the plain line", first == line, first)
        check("not_a_repo: no UNKNOWN jargon", "UNKNOWN" not in first, first)

        second = dw.run(hook, model_call=never_called())
        check("not_a_repo: second run, same session, silent", second == "", second)

        other = dict(hook, session_id="no-repo-session-2")
        third = dw.run(other, model_call=never_called())
        check("not_a_repo: a new session hears the line again", third == line, third)

        no_id = {"transcript_path": path, "cwd": plain}
        check("not_a_repo: no session_id still says the line",
              dw.run(no_id, model_call=never_called()) == line)

        # A .git that git cannot read is a broken repo, not a folder with none: still UNKNOWN.
        broken = os.path.join(ROOT, "broken_repo")
        os.makedirs(broken, exist_ok=True)
        write(os.path.join(broken, ".git"), "gitdir: %s\n" % os.path.join(ROOT, "no_such_gitdir"))
        broken_hook = {"transcript_path": write_transcript(broken, records), "cwd": broken,
                       "session_id": "no-repo-session-1"}
        failed = dw.run(broken_hook, model_call=never_called())
        check("not_a_repo: a git failure inside a repo stays UNKNOWN",
              failed.startswith(dw.UNKNOWN_PREFIX), failed)
    finally:
        if prior is None:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["CLAUDE_CONFIG_DIR"] = prior


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


# --------------------------------------------------------------------------- case 8b
# THE CHEAP CHECK COMES FIRST. `run` must end on `git status` alone, before it parses the
# transcript, when no protected path is dirty AND newer than the last human message. A
# counter on `read_transcript` shows the exit; the last pair shows it does not hide a turn
# that did change a protected file.

class _Counted:
    def __init__(self, real):
        self.real, self.calls = real, 0

    def __call__(self, *a, **k):
        self.calls += 1
        return self.real(*a, **k)


def _in_future(seconds):
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def case_early_exit_before_transcript_read():
    real = dw.read_transcript
    counter = _Counted(real)
    dw.read_transcript = counter
    try:
        repo = make_repo("early_idle")
        write(os.path.join(repo, "src", "app.py"), "print(1)\n")
        write(os.path.join(repo, "decisions", "r.md"), "# R\n\nAlways X.\n")
        commit_all(repo)
        path = write_transcript(repo, [human_record("hi", T0), assistant_record(text="hello")])
        spy = never_called()
        message = dw.run({"transcript_path": path, "cwd": repo}, model_call=spy)
        check("early_exit: idle turn silent", message == "", message)
        check("early_exit: idle turn never parses the transcript", counter.calls == 0, counter.calls)
        check("early_exit: idle turn never calls the model", spy.calls == 0)

        write(os.path.join(repo, "decisions", "r.md"), "# R\n\nNever X.\n")
        path = write_transcript(repo, [human_record("hi", _in_future(3600)), assistant_record(text="hello")])
        message = dw.run({"transcript_path": path, "cwd": repo}, model_call=spy)
        check("early_exit: protected dirt older than the human message ends early",
              message == "" and counter.calls == 0 and spy.calls == 0, (message, counter.calls, spy.calls))

        path = write_transcript(repo, [human_record("hi", T0), assistant_record(text="hello")])
        allow = stub({"verdict": "ALLOW"})
        dw.run({"transcript_path": path, "cwd": repo}, model_call=allow)
        check("early_exit: protected dirt newer than the human message is judged",
              counter.calls == 1 and allow.calls == 1, (counter.calls, allow.calls))
    finally:
        dw.read_transcript = real


# --------------------------------------------------------------------------- case 8c
# AN ALLOW IS CACHED, LIKE A FLAG. One model call per change to a protected file, not one per
# Stop. Run against a fake `claude` binary on PATH (never a real model call) that counts its
# own invocations. The key holds the file's bytes, so an edited file is judged again, even
# when the edit falls past the 4000 characters of diff the model is shown.

def _fake_claude(name, verdict='{"verdict": "ALLOW"}'):
    """Put a fake `claude` first on PATH. Return (count_file, restore)."""
    bindir = os.path.join(ROOT, name + "_bin")
    os.makedirs(bindir, exist_ok=True)
    count = os.path.join(bindir, "count")
    py = os.path.join(bindir, "fake_claude.py")
    write(py, "import json, sys\nopen(%r, 'a').write('x')\nprint(json.dumps({'result': %r}))\n" % (count, verdict))
    launcher = os.path.join(bindir, "claude")
    write(launcher, '#!/bin/sh\nexec "%s" "%s" "$@"\n' % (sys.executable, py))
    os.chmod(launcher, 0o755)
    prior = os.environ.get("PATH", "")
    os.environ["PATH"] = bindir + os.pathsep + prior

    def restore():
        os.environ["PATH"] = prior
    return count, restore


def _calls(count_file):
    try:
        with open(count_file, encoding="utf-8") as f:
            return len(f.read())
    except OSError:
        return 0


def case_allow_verdict_cached_until_the_file_changes():
    if sys.platform == "win32":
        skip("allow_cache", "the fake claude is a POSIX launcher")
        return
    repo = make_repo("allow_cache")
    rule = os.path.join(repo, "decisions", "r.md")
    write(rule, "# R\n\nAlways X.\n")
    commit_all(repo)
    write(rule, "# R\n\nAlways X, and Y.\n")
    path = write_transcript(repo, [human_record("add Y", T0), assistant_record(text="Added Y.")])
    hook = {"transcript_path": path, "cwd": repo, "session_id": "allow-cache-session"}
    cfg = os.path.join(ROOT, "cfg_allow_cache")
    os.makedirs(cfg, exist_ok=True)
    prior_cfg = os.environ.get("CLAUDE_CONFIG_DIR")
    os.environ["CLAUDE_CONFIG_DIR"] = cfg
    count, restore = _fake_claude("allow_cache")
    try:
        for _ in range(3):
            message = dw.run(hook)
        check("allow_cache: three Stops, one unchanged file: one model call", _calls(count) == 1, _calls(count))
        check("allow_cache: stays silent", message == "", message)
        write(rule, "# R\n\nAlways X, and Y, and Z.\n")
        dw.run(hook)
        dw.run(hook)
        check("allow_cache: an edited file is judged again, once", _calls(count) == 2, _calls(count))

        # A new file is shown to the model as its first 4000 characters, so only the key's
        # own hash of the bytes sees an edit past that cut. (A tracked file's diff header
        # carries the blob id, which moves with every byte.)
        big = os.path.join(repo, "decisions", "big.md")
        write(big, "# Big\n\n" + "line\n" * 1500 + "tail A\n")
        dw.run(hook)
        before = _calls(count)
        write(big, "# Big\n\n" + "line\n" * 1500 + "tail B\n")
        dw.run(hook)
        check("allow_cache: an edit past the 4000 diff characters is judged again",
              _calls(count) == before + 1, (before, _calls(count)))
    finally:
        restore()
        if prior_cfg is None:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["CLAUDE_CONFIG_DIR"] = prior_cfg


def case_unknown_is_never_cached():
    repo = make_repo("unknown_not_cached")
    rule = os.path.join(repo, "decisions", "r.md")
    write(rule, "# R\n\nAlways X.\n")
    commit_all(repo)
    write(rule, "# R\n\nAlways Y.\n")
    path = write_transcript(repo, [human_record("edit", T0), assistant_record(text="Done.")])
    hook = {"transcript_path": path, "cwd": repo, "session_id": "unknown-session"}
    cfg = os.path.join(ROOT, "cfg_unknown")
    os.makedirs(cfg, exist_ok=True)
    prior_cfg = os.environ.get("CLAUDE_CONFIG_DIR")
    os.environ["CLAUDE_CONFIG_DIR"] = cfg
    try:
        first = dw.run(hook, model_call=stub(None, "model exited 1: boom"))
        allow = stub({"verdict": "ALLOW"})
        dw.run(hook, model_call=allow)
        check("unknown_not_cached: first Stop reads UNKNOWN", first.startswith(dw.UNKNOWN_PREFIX), first)
        check("unknown_not_cached: the next Stop still asks the model", allow.calls == 1, allow.calls)
    finally:
        if prior_cfg is None:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["CLAUDE_CONFIG_DIR"] = prior_cfg


# --------------------------------------------------------------------------- case 8d
# A PROTECTED FILE COMMITTED THIS TURN is clean in `git status`, so only the commit log shows
# it. Edited and committed after the human message: judged (once, then cached). The same
# commit made before the message: not judged.

def case_protected_file_committed_this_turn_is_judged():
    if sys.platform == "win32":
        skip("committed_this_turn", "the fake claude is a POSIX launcher")
        return
    repo = make_repo("committed_turn")
    rule = os.path.join(repo, "decisions", "r.md")
    write(rule, "# R\n\nAlways X.\n")
    commit_all(repo)
    write(rule, "# R\n\nNever X.\n")
    commit_all(repo, "flip", when=None)
    path = write_transcript(repo, [human_record("go", T0), assistant_record(text="Done.")])
    hook = {"transcript_path": path, "cwd": repo, "session_id": "committed-turn"}
    cfg = os.path.join(ROOT, "cfg_committed_turn")
    os.makedirs(cfg, exist_ok=True)
    prior_cfg = os.environ.get("CLAUDE_CONFIG_DIR")
    os.environ["CLAUDE_CONFIG_DIR"] = cfg
    root = make_repo("committed_root")
    write(os.path.join(root, "decisions", "r.md"), "# R\n\nAlways X.\n")
    commit_all(root, "root", when=None)
    seen = []
    dw.run({"transcript_path": write_transcript(root, [human_record("go", T0), assistant_record(text="x")]),
            "cwd": root}, model_call=lambda prompt, **k: (seen.append(prompt), ({"verdict": "ALLOW"}, None))[1])
    check("committed_turn: a root commit made this turn is judged as a new file",
          len(seen) == 1 and "(new file)" in seen[0], seen[:1])
    count, restore = _fake_claude("committed_turn")
    try:
        message = dw.run(hook)
        dw.run(hook)
        check("committed_turn: a clean-status protected commit is judged once", _calls(count) == 1, _calls(count))
        check("committed_turn: ALLOW stays silent", message == "", message)
        flag = stub({"verdict": "FLAG", "why": "flipped"})
        fresh = dict(hook, session_id="committed-turn-2")
        check("committed_turn: the judge sees the committed diff",
              dw.run(fresh, model_call=flag).startswith(dw.FLAG_PREFIX) and flag.calls == 1)
        before = _calls(count)
        path = write_transcript(repo, [human_record("go", _in_future(3600)), assistant_record(text="Done.")])
        spy = never_called()
        dw.run(dict(hook, transcript_path=path, session_id="committed-turn-3"), model_call=spy)
        check("committed_turn: a commit before the human message is not judged",
              spy.calls == 0 and _calls(count) == before, (spy.calls, _calls(count)))
    finally:
        restore()
        if prior_cfg is None:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["CLAUDE_CONFIG_DIR"] = prior_cfg


# --------------------------------------------------------------------------- case 8e
# The verdict cache never crosses repos, and the byte hash reads a bounded amount.

def case_cache_key_holds_the_repo_and_a_bounded_read():
    spies = []
    cfg = os.path.join(ROOT, "cfg_two_repos")
    os.makedirs(cfg, exist_ok=True)
    prior_cfg = os.environ.get("CLAUDE_CONFIG_DIR")
    os.environ["CLAUDE_CONFIG_DIR"] = cfg
    try:
        for name in ("two_repos_a", "two_repos_b"):
            repo = make_repo(name)
            write(os.path.join(repo, "decisions", "r.md"), "# R\n\nAlways X.\n")
            commit_all(repo)
            write(os.path.join(repo, "decisions", "r.md"), "# R\n\nNever X.\n")
            path = write_transcript(repo, [human_record("go", T0), assistant_record(text="Done.")])
            spy = stub({"verdict": "ALLOW"})
            dw.run({"transcript_path": path, "cwd": repo, "session_id": "one-session"}, model_call=spy)
            spies.append(spy.calls)
    finally:
        if prior_cfg is None:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["CLAUDE_CONFIG_DIR"] = prior_cfg
    check("cache_key: one session in two repos, same bytes: judged in each", spies == [1, 1], spies)

    repo = make_repo("digest_cap")
    big = os.path.join(repo, "decisions", "big.md")
    write(big, "x" * (dw.DIGEST_READ_MAX + 10))
    first = dw.content_digest(repo, ["decisions/big.md"])
    write(big, "x" * (dw.DIGEST_READ_MAX + 20))
    check("digest_cap: a file past the cap still changes the digest (size)",
          dw.content_digest(repo, ["decisions/big.md"]) != first)


# --------------------------------------------------------------------------- case 9
# invoke_model's real argv and kwargs, against a fake subprocess.run: the explicit empty
# tool set, --permission-mode plan, and an isolated cwd/env are on the command line, not
# only stated in a docstring. A statement of "no tools" with an argv that grants every tool,
# in this project's directory, inheriting its permissions.allow, must fail.

class _FakeCompletedProcess:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# --------------------------------------------------------------------------- case 9a
# _judge_isolation copies the real login credential into the isolated config dir. An empty
# isolated config dir fails a real run with "Not logged in", on any machine, not only a
# sandboxed one.

def case_judge_isolation_copies_credentials():
    fake_home_config = os.path.join(ROOT, "fake_home_config")
    os.makedirs(fake_home_config, exist_ok=True)
    creds_path = os.path.join(fake_home_config, dw.CREDENTIALS_FILENAME)
    write(creds_path, '{"fake": "credential-content"}')

    # _judge_isolation calls guard.config_dir(). guard resolves that name through git_reads, so the
    # patch goes on the guard module itself and is removed after.
    guard_module = dw.guard
    had_own = "config_dir" in vars(guard_module)
    real_config_dir = guard_module.config_dir
    guard_module.config_dir = lambda: fake_home_config
    try:
        judge_cwd, judge_env = dw._judge_isolation()
    finally:
        if had_own:
            guard_module.config_dir = real_config_dir
        else:
            del guard_module.config_dir

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


def _capture_invoke(fake_run):
    real = dw.subprocess.run
    dw.subprocess.run = fake_run
    try:
        return dw.invoke_model("P")
    finally:
        dw.subprocess.run = real


# A timeout is an error (UNKNOWN upstream), never an ALLOW verdict.
def case_invoke_model_timeout_is_error():
    def fake_run(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs.get("timeout"))

    verdict, error = _capture_invoke(fake_run)
    check("timeout: no verdict", verdict is None, verdict)
    check("timeout: error names the failure", bool(error), error)


# The one home for the child's isolation flags. Decision reply-judge-samples-never-refuses (the
# reply judge) and the reply judge row of agent-model-cap: haiku, xhigh effort, module timeout.
def case_invoke_model_argv():
    # Its env checks assume no token file: pin CLAUDE_CONFIG_DIR so a real one on this
    # machine cannot change the child's env.
    with scratch_config("argv"):
        _invoke_model_argv_body()


def _invoke_model_argv_body():
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
    kwargs = captured.get("kwargs") or {}
    # The prompt travels on stdin, never in argv: Windows refuses a command line past 32,767
    # chars (WinError 206), so a prompt in argv cannot reach `claude` at its real size.
    pairs = list(zip(argv, argv[1:]))
    check("invoke_model_argv: --model haiku in argv", ("--model", "haiku") in pairs, argv)
    check("invoke_model_argv: --effort xhigh in argv", ("--effort", "xhigh") in pairs, argv)
    check("invoke_model_argv: prompt is not in argv",
          not any("JUDGE THIS PROMPT" in arg for arg in argv), argv)
    check("invoke_model_argv: prompt arrives on stdin",
          kwargs.get("input") == b"JUDGE THIS PROMPT", kwargs.get("input"))
    # Catches: the child runs with a timeout other than the module's MODEL_TIMEOUT.
    check("invoke_model_argv: subprocess gets the module timeout",
          kwargs.get("timeout") == dw.MODEL_TIMEOUT, kwargs.get("timeout"))
    # --effort xhigh is checked above; its position is free, so it is dropped before the compare.
    if "--effort" in argv:
        i = argv.index("--effort")
        argv = argv[:i] + argv[i + 2:]
    expected = [
        "claude", "-p",
        "--model", "haiku",
        "--output-format", "json",
        "--tools", "",
        "--safe-mode",
        "--permission-mode", "plan",
    ]
    print("invoke_model argv: %r" % argv)
    check("invoke_model_argv: matches the expected restricted command line", argv == expected, argv)

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


# Prompts reach the child on stdin. The child is a real process. A bare `claude` cannot be
# started from a script on Windows, so the shim in each case runs this interpreter on a fake.
# The fake reads stdin as raw bytes with no newline folding. It returns the bytes hex-encoded,
# so a case compares what the child received with what was sent.
FAKE_CLAUDE_SRC = '''\
import json, sys
raw = sys.stdin.buffer.read()
text = raw.decode("utf-8")
verdict = {"verdict": "ALLOW", "stdin_len": len(text), "stdin_tail": text[-40:],
           "stdin_hex": raw.hex()}
print(json.dumps({"result": json.dumps(verdict)}))
'''
LONG_PROMPT_LEN = 60000
LONG_PROMPT_END = "<<end-of-prompt>>"


def _invoke_through_fake_claude(prompt, name):
    """invoke_model with `claude` replaced by the fake, in a scratch config. Returns the
    verdict, the error, and the argv the child was started with."""
    fake = os.path.join(ROOT, "fake-claude", "fake_claude.py")
    write(fake, FAKE_CLAUDE_SRC)
    captured = {}
    real_run = dw.subprocess.run

    def shim(argv, **kwargs):
        captured["argv"] = list(argv)
        child = [sys.executable, fake] + list(argv[1:]) if argv and argv[0] == "claude" else argv
        return real_run(child, **kwargs)

    dw.subprocess.run = shim
    try:
        with scratch_config(name):
            verdict, error = dw.invoke_model(prompt)
    finally:
        dw.subprocess.run = real_run
    return verdict, error, captured.get("argv") or []


# The filler has no newline. A Windows text-mode write turns each "\n" into "\r\n", which would
# add 1 char per line and make this case measure line endings. The byte-exact case below owns
# line endings, so this case measures length, the command line, and the tail.
def case_invoke_model_long_prompt_reaches_child_whole():
    filler = "evidence row " * LONG_PROMPT_LEN
    prompt = filler[:LONG_PROMPT_LEN - len(LONG_PROMPT_END)] + LONG_PROMPT_END
    verdict, error, argv = _invoke_through_fake_claude(prompt, "longprompt")

    cmd_len = sum(len(arg) + 1 for arg in argv)
    check("long prompt: invoke_model returns no error", error is None, error)
    check("long prompt: the command line stays under the 32,767-char Windows cap",
          cmd_len < 32767, cmd_len)
    check("long prompt: the child reads all 60,000 chars on stdin",
          (verdict or {}).get("stdin_len") == LONG_PROMPT_LEN, (verdict or {}).get("stdin_len"))
    check("long prompt: the child reads the prompt's last 40 chars",
          (verdict or {}).get("stdin_tail") == prompt[-40:], (verdict or {}).get("stdin_tail"))


# A prompt with LF, CRLF and non-ASCII characters reaches the child byte for byte, as UTF-8.
# The text-mode write (`input=prompt`, `text=True`) on Windows turns each "\n" into "\r\n", so
# "a\nb\r\nc" arrives as b"a\r\nb\r\r\nc". The non-ASCII check is separate: it passes on its own,
# so a red byte check points at line endings, not at encoding.
BYTE_PROMPT = "a\nb\r\nc — é"


def case_invoke_model_prompt_bytes_reach_child_exact():
    verdict, error, _ = _invoke_through_fake_claude(BYTE_PROMPT, "promptbytes")
    received = bytes.fromhex((verdict or {}).get("stdin_hex", ""))

    check("prompt bytes: invoke_model returns no error", error is None, error)
    check("prompt bytes: the em dash and e-acute arrive as UTF-8",
          "—".encode("utf-8") in received and "é".encode("utf-8") in received, received)
    check("prompt bytes: the child receives the prompt byte-for-byte as UTF-8",
          received == BYTE_PROMPT.encode("utf-8"), received)


# --------------------------------------------------------------------------- case 10
# main() itself, invoked as the harness invokes it: a real subprocess, JSON on stdin,
# stdout and exit code read back. Every other case stubs model_call, so this one exercises
# main()'s own contract (stdin parsing, stop_hook_active, the systemMessage envelope, exit 0).

def _run_main(hook_payload, timeout=30):
    # An empty config directory, so the config report never reads this machine's own guard.log.
    config = os.path.join(ROOT, "empty-config")
    os.makedirs(config, exist_ok=True)
    env = dict(os.environ, CLAUDE_CONFIG_DIR=config)
    return subprocess.run(
        [sys.executable, MODULE_PATH],
        input=json.dumps(hook_payload), capture_output=True, text=True, timeout=timeout, env=env,
    )


def _says_unknown(result):
    """True when main() printed an UNKNOWN systemMessage. The known-bad half of a silent pair."""
    try:
        return json.loads(result.stdout.strip()).get("systemMessage", "").startswith(dw.UNKNOWN_PREFIX)
    except Exception:
        return False


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
    # KNOWN-BAD PAIR: a stub that always exits 0 silent passes the two lines above. The same
    # payload with the transcript gone must print UNKNOWN, so a stub fails here.
    os.remove(path)
    paired = _run_main({"transcript_path": path, "cwd": repo})
    check("main_ordinary_turn: known-bad pair prints UNKNOWN", _says_unknown(paired), paired.stdout)


def case_main_prints_the_config_report():
    # The config report was its own Stop hook. It is a section of this one now, so main() must
    # print its message, and only that message here: nothing protected changed, so the judgment
    # has nothing to say.
    repo = make_repo("main_config_report")
    write(os.path.join(repo, "src", "app.py"), "print('hello')\n")
    commit_all(repo)
    target = os.path.join(repo, ".claude", "settings.local.json")
    edit = {"type": "tool_use", "name": "Edit", "input": {"file_path": target}}
    records = [
        human_record("tune the project settings", T0),
        assistant_record(tool_use=edit),
        assistant_record(text="done"),
    ]
    path = write_transcript(repo, records)
    result = _run_main({"transcript_path": path, "cwd": repo})
    check("main_config_report: exit 0", result.returncode == 0, result.returncode)
    try:
        message = json.loads(result.stdout.strip()).get("systemMessage", "")
    except Exception:
        message = ""
    check("main_config_report: names the config file", "Config files changed this turn" in message
          and "settings.local.json" in message, result.stdout)
    check("main_config_report: no judgment text beside it", dw.FLAG_PREFIX not in message
          and dw.UNKNOWN_PREFIX not in message, result.stdout)


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
    # KNOWN-BAD PAIR: the same payload without the flag must not be silent.
    paired = _run_main({"transcript_path": "/does/not/matter", "cwd": "."})
    check("main_stop_hook_active: known-bad pair prints UNKNOWN", _says_unknown(paired), paired.stdout)


# --------------------------------------------------------------------------- case 12
# The one-year token file (decisions/reply-judge-samples-never-refuses.md).
# invoke_model reads `${CLAUDE_CONFIG_DIR:-~/.claude}/state/hook-token` and passes its
# stripped content to the child as CLAUDE_CODE_OAUTH_TOKEN. Every case uses the fake
# FAKE_TOKEN and a scratch CLAUDE_CONFIG_DIR, so no case reads a real token or this
# machine's own config. No case prints a token value.

FAKE_TOKEN = "tok-test-123"
PARENT_TOKEN = "tok-parent-456"
TOKEN_KEY = "CLAUDE_CODE_OAUTH_TOKEN"
ALLOW = {"verdict": "ALLOW"}


@contextlib.contextmanager
def scratch_config(name, parent_token=None):
    """Point CLAUDE_CONFIG_DIR at a scratch dir, and set or clear this process's own
    CLAUDE_CODE_OAUTH_TOKEN, for one case. Both are restored afterwards."""
    cfg = os.path.join(ROOT, "config-" + name)
    os.makedirs(cfg, exist_ok=True)
    keys = ("CLAUDE_CONFIG_DIR", TOKEN_KEY)
    prior = {k: os.environ.get(k) for k in keys}
    os.environ["CLAUDE_CONFIG_DIR"] = cfg
    if parent_token is None:
        os.environ.pop(TOKEN_KEY, None)
    else:
        os.environ[TOKEN_KEY] = parent_token
    try:
        yield cfg
    finally:
        for k in keys:
            if prior[k] is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = prior[k]


def _token_file(cfg, text):
    write(os.path.join(cfg, "state", "hook-token"), text)


def _run_invoke(captured, returncode=0, stderr="", raises=None):
    """invoke_model with a fake subprocess.run that records the child's argv and env."""
    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["env"] = kwargs.get("env") or {}
        if raises is not None:
            raise raises
        # The real subprocess.run refuses an env value that holds a NUL character.
        for k, v in captured["env"].items():
            if "\x00" in k or "\x00" in v:
                raise ValueError("embedded null character")
        return _FakeCompletedProcess(returncode, json.dumps({"result": json.dumps(ALLOW)}), stderr)
    return _capture_invoke(fake_run)


def _presence(env):
    return "present" if TOKEN_KEY in env else "absent"


# T1. A token file present: the child's env carries its stripped content as the token.
def case_token_t1_file_reaches_child_env():
    captured = {}
    with scratch_config("t1") as cfg:
        _token_file(cfg, FAKE_TOKEN + "\n")
        verdict, error = _run_invoke(captured)
    env = captured.get("env") or {}
    check("token_t1: call returns ALLOW with a token file", verdict == ALLOW and error is None, error)
    check("token_t1: child env holds CLAUDE_CODE_OAUTH_TOKEN", TOKEN_KEY in env, sorted(env))
    check("token_t1: child token is the file's stripped content",
          env.get(TOKEN_KEY) == FAKE_TOKEN, "token is " + _presence(env))


# T3. The parent's own CLAUDE_CODE_OAUTH_TOKEN is never passed through: the file is the
# only source. The allowlist stays closed.
def case_token_t3_parent_env_not_passed_through():
    captured = {}
    with scratch_config("t3-file", parent_token=PARENT_TOKEN) as cfg:
        _token_file(cfg, FAKE_TOKEN + "\n")
        _run_invoke(captured)
    env = captured.get("env") or {}
    check("token_t3: with a file, child token is the file's, not the parent's",
          env.get(TOKEN_KEY) == FAKE_TOKEN, "token is " + _presence(env))

    captured = {}
    with scratch_config("t3-nofile", parent_token=PARENT_TOKEN):
        _run_invoke(captured)
    env = captured.get("env") or {}
    check("token_t3: with no file, parent token is not passed through", TOKEN_KEY not in env,
          "token is " + _presence(env))


# T4. No usable token file means no token key in the child env, and the call still returns
# ALLOW on the old path. Each row is one input: no file, and each file that holds no token.
def case_token_t4_no_usable_token_file_is_no_token():
    cases = (
        # Catches: no token file at all adds a token key to the child env.
        ("no file", lambda cfg: None),
        # Catches: an empty token file adds a token key.
        ("empty", lambda cfg: _token_file(cfg, "")),
        # Catches: a whitespace-only token file with LF adds a token key.
        ("whitespace LF", lambda cfg: _token_file_bytes(cfg, b"  \n")),
        # Catches: a whitespace-only token file with CRLF (PowerShell line ending) adds a token key.
        ("whitespace CRLF", lambda cfg: _token_file_bytes(cfg, b"  \r\n")),
        # Catches: a UTF-16 file that holds only a BOM adds a token key.
        ("UTF-16 BOM only", lambda cfg: _token_file_bytes(cfg, b"\xff\xfe")),
        # Catches: a token path that is a directory adds a token key, or crashes the call.
        ("unreadable, a directory", lambda cfg: os.makedirs(os.path.join(cfg, "state", "hook-token"),
                                                             exist_ok=True)),
    )
    for label, setup in cases:
        captured = {}
        with scratch_config("t4-" + label.replace(" ", "-").replace(",", "")) as cfg:
            setup(cfg)
            verdict, error = _run_invoke(captured)
        env = captured.get("env") or {}
        check("token_t4(%s): no token key in child env" % label, TOKEN_KEY not in env,
              "token is " + _presence(env))
        check("token_t4(%s): call still returns ALLOW" % label, verdict == ALLOW and error is None, error)


# T5. A model failure never puts the token in the error string. The fake child echoes
# the token it was given on stderr, as a failing CLI can. Both failure paths are checked.
def case_token_t5_failure_error_omits_token():
    captured = {}
    with scratch_config("t5") as cfg:
        _token_file(cfg, FAKE_TOKEN + "\n")
        verdict, error = _run_invoke(captured, returncode=1, stderr="auth failed for " + FAKE_TOKEN)
    check("token_t5: nonzero exit is an error, not a verdict", verdict is None and bool(error),
          "verdict=%s" % (verdict,))
    check("token_t5: error string omits the token", FAKE_TOKEN not in (error or ""),
          "token found in error string")

    with scratch_config("t5-spawn") as cfg:
        _token_file(cfg, FAKE_TOKEN + "\n")
        verdict, error = _run_invoke({}, raises=OSError("could not start with " + FAKE_TOKEN))
    check("token_t5(spawn): failure to start is an error, not a verdict", verdict is None and bool(error),
          "verdict=%s" % (verdict,))
    check("token_t5(spawn): error string omits the token", FAKE_TOKEN not in (error or ""),
          "token found in error string")


# Token file encodings, as Windows PowerShell 5.1 writes them. The reader must return the bare
# token whatever the BOM, line ending or NUL characters. The file's bytes are written as given.
def _token_file_bytes(cfg, data):
    path = os.path.join(cfg, "state", "hook-token")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def case_token_encodings_read_as_the_bare_token():
    cases = (
        # Catches: a UTF-8 BOM (Set-Content -Encoding utf8) stays in the token.
        ("utf8 BOM", b"\xef\xbb\xbf" + FAKE_TOKEN.encode("ascii") + b"\n"),
        # Catches: a UTF-16 LE BOM file (Out-File) is not read as the bare token.
        ("utf16 LE BOM", b"\xff\xfe" + (FAKE_TOKEN + "\r\n").encode("utf-16-le")),
        # Catches: a CRLF line ending stays in the token.
        ("utf8 CRLF", FAKE_TOKEN.encode("ascii") + b"\r\n"),
        # Catches: a UTF-16 LE file with no BOM keeps its NUL characters, and the call fails on them.
        ("utf16 LE no BOM", (FAKE_TOKEN + "\r\n").encode("utf-16-le")),
        # Catches: a trailing NUL reaches the child env, and the call fails with embedded null character.
        ("utf8 trailing NUL", FAKE_TOKEN.encode("ascii") + b"\n\x00"),
    )
    for label, data in cases:
        captured = {}
        with scratch_config("enc-" + label.replace(" ", "-")) as cfg:
            _token_file_bytes(cfg, data)
            verdict, error = _run_invoke(captured)
        env = captured.get("env") or {}
        check("token_encodings(%s): call returns ALLOW, no embedded-null error" % label,
              verdict == ALLOW and error is None, error)
        check("token_encodings(%s): child token is the bare token" % label,
              env.get(TOKEN_KEY) == FAKE_TOKEN, "token is " + _presence(env))


# T10. A token file that exists but cannot be decoded: FF FE BOM plus an odd byte count.
# invoke_model must return an error that says the token file could not be read, the error
# must hold no file bytes, and no subprocess may start (no silent fall back to the expired
# credentials copy). The reader must fail closed on a decode error.
def case_token_t10_undecodable_file_is_an_error():
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return _FakeCompletedProcess(0, json.dumps({"result": json.dumps(ALLOW)}), "")

    undecodable = b"\xff\xfe" + FAKE_TOKEN.encode("utf-16-le") + b"\x41"
    with scratch_config("t10") as cfg:
        _token_file_bytes(cfg, undecodable)
        verdict, error = _capture_invoke(fake_run)
    text = error or ""
    check("token_t10: no verdict for an undecodable token file", verdict is None, verdict)
    check("token_t10: error says the token file could not be read",
          "token file" in text.lower() and "could not be read" in text.lower(), text)
    check("token_t10: error holds no file bytes",
          not any(s in text for s in (FAKE_TOKEN, "\\xff", "\\xfe", "\\x41")), text)
    check("token_t10: no subprocess started", calls == [], "%d call(s)" % len(calls))


# --------------------------------------------------------------------------- case E1
# The child writes UTF-8 (the judge's JSON carries an em dash in the why). The fake child
# returns BYTES, and decodes them the way subprocess.run does for the call's own arguments:
# the named encoding when one is passed, else the Windows code page (cp1252) when text=True.
E1_WHY = "The wait option answers timing — the three-try limit is not in it."


def _decode_as_subprocess_run_would(raw, kwargs):
    if kwargs.get("encoding"):
        return raw.decode(kwargs["encoding"])
    if kwargs.get("text") or kwargs.get("universal_newlines"):
        return raw.decode("cp1252")
    return raw


def case_e1_model_output_is_read_as_utf8():
    envelope = {"result": json.dumps({"verdict": "FLAG", "why": E1_WHY}, ensure_ascii=False)}
    raw = json.dumps(envelope, ensure_ascii=False).encode("utf-8")

    def fake_run(argv, **kwargs):
        stdout = _decode_as_subprocess_run_would(raw, kwargs)
        return _FakeCompletedProcess(0, stdout, "")

    verdict, error = _capture_invoke(fake_run)
    check("e1: no error", error is None, error)
    why = (verdict or {}).get("why", "")
    check("e1: why holds the em dash", why == E1_WHY, repr(why))
    check("e1: why holds no mojibake", "â€" not in why, repr(why))


# --------------------------------------------------------------------------- the verdict parse
# parse_verdict(text, shape) is the one home of the verdict parse. invoke_model calls it, and
# so does the --model-text entry. The shape is the caller's accepted answer, as before.

ALLOW_JSON = '{"verdict": "ALLOW"}'


def _invoke_with(fake_run, *args, **kwargs):
    real = dw.subprocess.run
    dw.subprocess.run = fake_run
    try:
        return dw.invoke_model("P", *args, **kwargs)
    finally:
        dw.subprocess.run = real


def _envelope(result_text):
    def fake_run(argv, **kwargs):
        return _FakeCompletedProcess(0, json.dumps({"result": result_text}), "")
    return fake_run


def _timeout_run(argv, **kwargs):
    raise subprocess.TimeoutExpired(argv, kwargs.get("timeout"))


def case_invoke_model_return_shape_pinned():
    # reply_judge calls invoke_model: its (verdict | None, error | None) return must not move.
    with scratch_config("invoke_signature"):
        ok = _invoke_with(_envelope(ALLOW_JSON))
        bad = _invoke_with(_timeout_run)
    check("invoke_model return: success is (verdict, None)", ok == ({"verdict": "ALLOW"}, None), ok)
    check("invoke_model return: failure is (None, error text)", bad[0] is None and bool(bad[1]), bad)


def case_parse_verdict_default_shape():
    # Default shape: ALLOW or FLAG, one JSON object.
    pv = dw.parse_verdict
    v, e = pv(ALLOW_JSON)
    check("parse_verdict: ALLOW", v == {"verdict": "ALLOW"} and e is None, (v, e))
    v, e = pv('Here you go: {"verdict": "FLAG", "why": "r"} thanks')
    check("parse_verdict: FLAG with why, prose around it", v == {"verdict": "FLAG", "why": "r"} and e is None, (v, e))
    for text, label in [("no json here", "no JSON"), ('{"verdict": "PERHAPS"}', "value outside ALLOW/FLAG"),
                        ("{not json}", "unparseable JSON")]:
        v, e = pv(text)
        check("parse_verdict: %s gives no verdict and an error" % label, v is None and bool(e), (v, e))


def case_parse_verdict_honours_a_custom_shape():
    # reply_judge's shape: one key, ok true or false. A value outside it is an error, never a pass.
    shape = {"ok": (True, False)}
    v, e = dw.parse_verdict('{"ok": true}', shape)
    check("parse_verdict shape: ok true (positional shape)", v == {"ok": True} and e is None, (v, e))
    v, e = dw.parse_verdict('{"ok": false}', shape=shape)
    check("parse_verdict shape: ok false (keyword shape)", v == {"ok": False} and e is None, (v, e))
    v, e = dw.parse_verdict('{"ok": "maybe"}', shape)
    check("parse_verdict shape: a value outside the shape is an error", v is None and bool(e), (v, e))
    v, e = dw.parse_verdict(ALLOW_JSON, shape)
    check("parse_verdict shape: the default key is refused under a custom shape", v is None and bool(e), (v, e))


def case_parse_verdict_is_the_one_home():
    # invoke_model reads its reply through parse_verdict: the same reply text gives the same answer.
    shape = {"ok": (True, False)}
    with scratch_config("one_home"):
        for text in ['{"ok": true}', '{"verdict": "FLAG", "why": "r"}', "junk"]:
            got = _invoke_with(_envelope(text), shape=shape)
            want = dw.parse_verdict(text, shape)
            check("parse_verdict is the one home: invoke_model matches it for %r" % text[:24],
                  got == want, (got, want))


def case_invoke_model_custom_shape_end_to_end():
    # invoke_model with reply_judge's shape, through a fake subprocess.
    shape = {"ok": (True, False)}
    with scratch_config("custom_shape"):
        got = _invoke_with(_envelope('{"ok": true}'), shape=shape)
        refused = _invoke_with(_envelope(ALLOW_JSON), shape=shape)
    check("invoke_model custom shape: ok true returns the verdict", got == ({"ok": True}, None), got)
    check("invoke_model custom shape: the default key is an error", refused[0] is None and bool(refused[1]), refused)


# --------------------------------------------------------------------------- the two-phase run
# The mod runs this file twice on the same Stop JSON: --emit-prompt, then --model-text or
# --model-error. These cases call main() in this process. A `claude` spawn is counted and
# answered with ALLOW, never run; git and every other spawn are real. Each case has its own
# scratch config, so the "already judged" cache never carries from one case to the next.

BAD_ARGV = [
    ["--emit-prompt", "x"], ["--model-text"], ["--model-error"], ["--model-text", "a", "b"],
    ["--emit-prompt", "--model-text", "x"], ["--model-error", "a", "b"], ["--foo"],
]


def run_case(case):
    """A missing seam is one FAIL line for its case, not a crash that hides the other cases."""
    try:
        case()
    except Exception as exc:
        check("%s: raised" % case.__name__, False, "%s: %s" % (type(exc).__name__, exc))


def _judged_hook(name):
    """A protected CLAUDE.md edit with no approval in chat, so run() reaches the model call."""
    repo = make_repo(name)
    write(os.path.join(repo, "CLAUDE.md"), "# Rules\n\nAlways X.\n")
    commit_all(repo)
    write(os.path.join(repo, "CLAUDE.md"), "# Rules\n\nAlways Y.\n")
    records = [human_record("edit claude.md", T0), assistant_record(text="Done.")]
    return {"transcript_path": write_transcript(repo, records), "cwd": repo, "session_id": "sess-" + name}


def _main_in_process(hook, argv):
    """Run main() here with argv and the hook on stdin. Return (stdout, claude_spawn_count)."""
    out = io.StringIO()
    spawns = []
    real_run = dw.subprocess.run

    def fake_run(argv_, *args, **kwargs):
        if argv_ and argv_[0] == "claude":
            spawns.append(argv_)
            return _FakeCompletedProcess(0, json.dumps({"result": ALLOW_JSON}), "")
        return real_run(argv_, *args, **kwargs)

    saved_argv, saved_stdin = sys.argv, sys.stdin
    sys.argv = ["decision_watch.py"] + list(argv)
    sys.stdin = io.StringIO(json.dumps(hook))
    dw.subprocess.run = fake_run
    try:
        with contextlib.redirect_stdout(out):
            try:
                dw.main()
            except SystemExit:
                pass
    finally:
        dw.subprocess.run = real_run
        sys.argv, sys.stdin = saved_argv, saved_stdin
    return out.getvalue().strip(), len(spawns)


def _json_or_none(text):
    try:
        return json.loads(text)
    except Exception:
        return None


def _system_message(text):
    got = _json_or_none(text)
    return got.get("systemMessage", "") if isinstance(got, dict) else ""


def _run_script(hook, argv, cfg):
    """Run decision_watch.py the way the mod spawns it: python -I, the Stop JSON on stdin, and a
    PATH that holds git and no claude. A default-path model call fails fast there and never runs."""
    git = shutil.which("git")
    env = dict(os.environ, CLAUDE_CONFIG_DIR=cfg, PATH=os.path.dirname(git) if git else "")
    return subprocess.run(
        [sys.executable, "-I", MODULE_PATH] + list(argv),
        input=json.dumps(hook), capture_output=True, text=True, timeout=60, env=env,
    )


def case_argv_bad_combinations_fall_back_to_invoke_model():
    # Any argv that is not one well-formed flag falls back to the default model call, invoke_model.
    pick = dw._model_call_from_argv
    check("argv: no flags is invoke_model", pick([]) is dw.invoke_model)
    for argv in BAD_ARGV:
        check("argv %r falls back to invoke_model" % (argv,), pick(argv) is dw.invoke_model)


def case_bad_flag_runs_the_default_model_call():
    # A malformed flag run is the default path: one claude call, in-process.
    for i, argv in enumerate((["--model-text"], ["--foo"])):
        name = "argv_fallback_%d" % i
        with scratch_config(name):
            _, spawns = _main_in_process(_judged_hook(name), argv)
        check("argv %r: the default path calls claude once" % (argv,), spawns == 1, spawns)


def case_emit_prompt_prints_needs_model_and_calls_no_model():
    # --emit-prompt on a due model call prints {needs_model, prompt, model, key} and
    # spawns no model. It writes no cache, so a second run still asks.
    name = "emit_needs"
    with scratch_config(name):
        hook = _judged_hook(name)
        out1, spawns1 = _main_in_process(hook, ["--emit-prompt"])
        out2, _ = _main_in_process(hook, ["--emit-prompt"])
        captured = []

        def spy(prompt):
            captured.append(prompt)
            return None, "spy: not a verdict"

        dw.run(hook, model_call=spy)
    got = _json_or_none(out1)
    check("emit-prompt: no model subprocess", spawns1 == 0, spawns1)
    check("emit-prompt: prints exactly needs_model, prompt, model, key",
          isinstance(got, dict) and set(got) == {"needs_model", "prompt", "model", "key"}, out1[:200])
    check("emit-prompt: needs_model is true", isinstance(got, dict) and got.get("needs_model") is True, out1[:200])
    check("emit-prompt: model is MODEL", isinstance(got, dict) and got.get("model") == dw.MODEL, out1[:200])
    check("emit-prompt: prompt names the protected file",
          isinstance(got, dict) and "CLAUDE.md" in str(got.get("prompt")), out1[:200])
    check("emit-prompt: the prompt is the one run() would send",
          isinstance(got, dict) and bool(captured) and got.get("prompt") == captured[0], out1[:200])
    again = _json_or_none(out2)
    check("emit-prompt: a second run still asks for the model (phase 1 writes no cache)",
          isinstance(again, dict) and again.get("needs_model") is True, out2[:200])


def case_emit_prompt_is_silent_when_nothing_is_due():
    # A clean turn prints nothing, and never a needs_model.
    name = "emit_clean"
    with scratch_config(name):
        repo = make_repo(name)
        write(os.path.join(repo, "src", "app.py"), "print('hello')\n")
        commit_all(repo)
        write(os.path.join(repo, "src", "app.py"), "print('hello world')\n")
        path = write_transcript(repo, [human_record("say hello world instead", T0),
                                       assistant_record(text="Updated src/app.py.")])
        out, spawns = _main_in_process({"transcript_path": path, "cwd": repo, "session_id": "sess-" + name},
                                       ["--emit-prompt"])
    check("emit-prompt quiet: nothing printed", out == "", out[:200])
    check("emit-prompt quiet: no model subprocess", spawns == 0, spawns)


def case_emit_prompt_missing_transcript_never_asks_for_a_model():
    # A missing transcript is UNKNOWN, and the cheap path never asks for a model.
    name = "emit_missing"
    with scratch_config(name):
        hook = {"transcript_path": os.path.join(ROOT, "no-such-transcript.jsonl"), "cwd": ROOT,
                "session_id": "sess-" + name}
        out, spawns = _main_in_process(hook, ["--emit-prompt"])
    check("emit-prompt missing transcript: no needs_model", "needs_model" not in out, out[:200])
    check("emit-prompt missing transcript: reads as UNKNOWN",
          _system_message(out).startswith(dw.UNKNOWN_PREFIX), out[:200])
    check("emit-prompt missing transcript: no model subprocess", spawns == 0, spawns)


def case_model_text_flag_prints_flag_and_calls_no_model():
    # --model-text with a FLAG prints the FLAG message and spawns no model.
    name = "text_flag"
    with scratch_config(name):
        out, spawns = _main_in_process(_judged_hook(name),
                                       ["--model-text", '{"verdict": "FLAG", "why": "reversed silently"}'])
    msg = _system_message(out)
    check("model-text FLAG: no model subprocess", spawns == 0, spawns)
    check("model-text FLAG: prints the FLAG message", msg.startswith(dw.FLAG_PREFIX) and "reversed silently" in msg,
          out[:200])


def case_model_text_allow_is_silent_and_cached():
    # --model-text with an ALLOW prints nothing, spawns no model, and caches the
    # verdict: the next --emit-prompt on this session is silent too.
    name = "text_allow"
    with scratch_config(name):
        hook = _judged_hook(name)
        out, spawns = _main_in_process(hook, ["--model-text", ALLOW_JSON])
        again, spawns2 = _main_in_process(hook, ["--emit-prompt"])
    check("model-text ALLOW: prints nothing", out == "", out[:200])
    check("model-text ALLOW: no model subprocess", spawns == 0, spawns)
    check("model-text ALLOW: the verdict is cached, so the next Stop asks nothing",
          again == "" and spawns2 == 0, (again[:200], spawns2))


def case_model_text_without_a_verdict_is_unknown_never_a_pass():
    # A reply with no verdict reads as UNKNOWN, never as silence.
    for name, reply in [("text_unknown_prose", "The change looks fine to me."),
                        ("text_unknown_shape", '{"ok": true}')]:
        with scratch_config(name):
            out, spawns = _main_in_process(_judged_hook(name), ["--model-text", reply])
        check("model-text %s: reads as UNKNOWN" % name, _system_message(out).startswith(dw.UNKNOWN_PREFIX), out[:200])
        check("model-text %s: no model subprocess" % name, spawns == 0, spawns)


def case_model_error_is_unknown_cut_to_200_and_not_cached():
    # --model-error reads as UNKNOWN, keeps the first 200 characters of the error,
    # and is not cached: a later reply still judges.
    name = "model_error"
    with scratch_config(name):
        hook = _judged_hook(name)
        out, spawns = _main_in_process(hook, ["--model-error", "Z" * 300])
        later, _ = _main_in_process(hook, ["--model-text", '{"verdict": "FLAG", "why": "later"}'])
    msg = _system_message(out)
    check("model-error: reads as UNKNOWN", msg.startswith(dw.UNKNOWN_PREFIX), out[:200])
    check("model-error: no model subprocess", spawns == 0, spawns)
    check("model-error: message holds the first 200 characters", ("Z" * 200) in msg and ("Z" * 201) not in msg,
          len(msg))
    check("model-error: not cached, so a later reply still judges",
          _system_message(later).startswith(dw.FLAG_PREFIX), later[:200])


def case_emit_prompt_runs_with_dash_I_as_the_mod_spawns_it():
    # The mod spawns `python -I decision_watch.py --emit-prompt`. The file must
    # import under -I and print needs_model.
    name = "emit_dash_i"
    with scratch_config(name) as cfg:
        result = _run_script(_judged_hook(name), ["--emit-prompt"], cfg)
    got = _json_or_none(result.stdout.strip())
    check("-I emit-prompt: exit 0", result.returncode == 0, result.returncode)
    check("-I emit-prompt: prints needs_model",
          isinstance(got, dict) and got.get("needs_model") is True,
          (result.stdout[:200], result.stderr[-200:]))


def case_phase_one_prints_a_key_for_the_evidence_it_judged():
    # SAFETY HOLE 1 (decision decision-watch-mod-limits): phase 1 prints a non-empty
    # "key" with the needs_model JSON, so phase 2 can be given back the evidence it judged.
    name = "key_printed"
    with scratch_config(name):
        out, spawns = _main_in_process(_judged_hook(name), ["--emit-prompt"])
    got = _json_or_none(out)
    key = got.get("key") if isinstance(got, dict) else None
    check("key: phase 1 prints needs_model with a non-empty key",
          isinstance(key, str) and key != "", out[:200])
    check("key: phase 1 calls no model", spawns == 0, spawns)


def case_phase_two_with_a_moved_key_reads_unknown_never_allow():
    # The evidence moves between the two phases: the protected file is edited after
    # phase 1 printed its key. Phase 2 gets that key back, so it reads UNKNOWN and never a silent
    # ALLOW on evidence that is no longer the evidence judged.
    name = "key_moved"
    with scratch_config(name):
        hook = _judged_hook(name)
        first, _ = _main_in_process(hook, ["--emit-prompt"])
        key = (_json_or_none(first) or {}).get("key") or "missing"
        write(os.path.join(hook["cwd"], "CLAUDE.md"), "# Rules\n\nAlways Z.\n")
        out, spawns = _main_in_process(hook, ["--model-text", ALLOW_JSON, "--key", key])
    check("key moved: never a silent ALLOW", out != "", out[:200])
    check("key moved: reads as UNKNOWN", _system_message(out).startswith(dw.UNKNOWN_PREFIX), out[:200])
    check("key moved: no model subprocess", spawns == 0, spawns)


def case_phase_two_with_the_same_key_stays_silent_on_allow():
    # Guard. An unchanged turn keeps its ALLOW silent: a rule that makes every keyed reply loud
    # would teach the reader to skip the watch.
    name = "key_same"
    with scratch_config(name):
        hook = _judged_hook(name)
        first, _ = _main_in_process(hook, ["--emit-prompt"])
        key = (_json_or_none(first) or {}).get("key") or "missing"
        out, spawns = _main_in_process(hook, ["--model-text", ALLOW_JSON, "--key", key])
    check("key same: ALLOW stays silent", out == "", out[:200])
    check("key same: no model subprocess", spawns == 0, spawns)


def case_default_path_still_calls_claude_without_a_flag():
    # With no flag the watch calls the model itself. With no claude on PATH
    # that call fails, and the answer is UNKNOWN, never needs_model.
    name = "default_subproc"
    with scratch_config(name) as cfg:
        result = _run_script(_judged_hook(name), [], cfg)
    got = _json_or_none(result.stdout.strip()) or {}
    check("default path: no needs_model without a flag", "needs_model" not in got, result.stdout[:200])
    check("default path: a missing model reads as UNKNOWN",
          _system_message(result.stdout).startswith(dw.UNKNOWN_PREFIX),
          (result.stdout[:200], result.stderr[-200:]))


# --------------------------------------------------------------------------- a verdict lost
# A reply handed in with --model-text or --model-error that the run never uses (the verdict is
# already recorded for this turn) must not read as silence. Silence after a reply is an ALLOW.

def case_model_text_after_a_cached_verdict_says_verdict_lost():
    # --model-text ALLOW records the verdict. A second reply on the same turn returns before the
    # model step. Printing nothing would read as a pass. It must read UNKNOWN.
    name = "text_lost"
    with scratch_config(name):
        hook = _judged_hook(name)
        first, _ = _main_in_process(hook, ["--model-text", ALLOW_JSON])
        out, spawns = _main_in_process(hook, ["--model-text", '{"verdict": "FLAG", "why": "late"}'])
    msg = _system_message(out)
    check("verdict lost: the first ALLOW prints nothing", first == "", first[:200])
    check("verdict lost: the second reply reads as UNKNOWN, verdict lost",
          msg.startswith(dw.UNKNOWN_PREFIX) and "verdict lost" in msg, out[:200])
    check("verdict lost: no model subprocess", spawns == 0, spawns)


def case_model_error_after_a_cached_verdict_is_not_silent():
    # The same early exit with --model-error must read UNKNOWN, not print nothing.
    name = "error_lost"
    with scratch_config(name):
        hook = _judged_hook(name)
        _main_in_process(hook, ["--model-text", ALLOW_JSON])
        out, spawns = _main_in_process(hook, ["--model-error", "boom"])
    check("model-error after a cached verdict: not silent, reads as UNKNOWN",
          _system_message(out).startswith(dw.UNKNOWN_PREFIX), out[:200])
    check("model-error after a cached verdict: no model subprocess", spawns == 0, spawns)


def case_split_output_carries_the_config_notice_apart_from_the_verdict():
    # Under a split flag (the mod's --emit-prompt), the script prints `verdict` (the judgment's
    # text alone) and `notices` (one string per kind of notice), besides the joined systemMessage.
    # A settings edit with no protected change is one notice and no verdict: `verdict` stays empty
    # and does not carry the notice text.
    name = "split_config_notice"
    repo = make_repo(name)
    write(os.path.join(repo, "src", "app.py"), "print('hello')\n")
    commit_all(repo)
    target = os.path.join(repo, ".claude", "settings.local.json")
    edit = {"type": "tool_use", "name": "Edit", "input": {"file_path": target}}
    records = [
        human_record("tune the project settings", T0),
        assistant_record(tool_use=edit),
        assistant_record(text="done"),
    ]
    hook = {"transcript_path": write_transcript(repo, records), "cwd": repo, "session_id": "sess-" + name}
    with scratch_config(name) as cfg:
        result = _run_script(hook, ["--emit-prompt"], cfg)
    got = _json_or_none(result.stdout.strip())
    got = got if isinstance(got, dict) else {}
    notices = got.get("notices")
    first = notices[0] if isinstance(notices, list) and notices and isinstance(notices[0], str) else ""
    check("split notices: exit 0", result.returncode == 0, result.returncode)
    check("split notices: one notice for the config edit",
          isinstance(notices, list) and len(notices) == 1, result.stdout[:300])
    check("split notices: the notice names the config file",
          "Config files changed this turn" in first and "settings.local.json" in first, first[:200])
    check("split notices: systemMessage still carries the joined text",
          "Config files changed" in str(got.get("systemMessage", "")), result.stdout[:300])
    check("split verdict: a separate field, empty when there is no judgment",
          got.get("verdict") == "", result.stdout[:300])
    check("split verdict: the notice text is not in the verdict",
          "Config files changed" not in str(got.get("verdict", "")), result.stdout[:300])


# --------------------------------------------------------------------------- dw-unread-dir (c)
# Under the mod env, python gets CLAUDE_CONFIG_DIR = the mod's state folder and no DW_REAL_CONFIG_DIR. The unread
# reader then falls back to the state folder, where guard.log is not, so the real folder's unread subject is lost.
# The fallback must print a line that names DW_REAL_CONFIG_DIR, on stdout or stderr, not stay silent.
# Guessed contract point: only the name DW_REAL_CONFIG_DIR is pinned, not the wording.
def case_unread_fallback_is_named_when_dw_real_config_dir_is_unset():
    name = "unread_fallback"
    repo = make_repo(name)
    write(os.path.join(repo, "src", "app.py"), "print('hello')\n")
    commit_all(repo)
    now = datetime.now(timezone.utc)
    records = [
        human_record("check the record folders", (now - timedelta(seconds=60)).strftime("%Y-%m-%dT%H:%M:%S.000Z")),
        assistant_record(text="done"),
    ]
    hook = {"transcript_path": write_transcript(repo, records), "cwd": repo, "session_id": "sess-" + name}
    # The real config folder holds one unread-subject line from this turn. The mod's state folder holds none.
    real = os.path.join(ROOT, name + "-real")
    os.makedirs(real, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    write(os.path.join(real, "guard.log"), "\t".join([stamp, "Bash", "noted", "subject-unread", "UNREAD-SUBJECT-BETA-4", "sess-" + name]) + "\n")
    state = os.path.join(ROOT, name + "-state", "decision-watch-shadow")
    os.makedirs(state, exist_ok=True)
    env = dict(os.environ, CLAUDE_CONFIG_DIR=state)
    for key in list(env):
        if key.upper() == "DW_REAL_CONFIG_DIR":
            del env[key]
    def emit(run_env):
        return subprocess.run(
            [sys.executable, "-I", MODULE_PATH, "--emit-prompt"],
            input=json.dumps(hook), capture_output=True, text=True, timeout=60, env=run_env,
        )

    result = emit(env)
    seen = result.stdout + result.stderr
    check("unread fallback: exit 0", result.returncode == 0, result.stderr[:300])
    check("unread fallback: a line names DW_REAL_CONFIG_DIR, so the fallback is not silent",
          "DW_REAL_CONFIG_DIR" in seen, seen[:300])
    # Control: with the real folder named, the same fixture shows the subject. So a red above is
    # the fallback, not a fixture that never produces the notice.
    control = emit(dict(env, DW_REAL_CONFIG_DIR=real))
    got = _json_or_none(control.stdout.strip())
    notices = got.get("notices") if isinstance(got, dict) else None
    shown = isinstance(notices, list) and any("UNREAD-SUBJECT-BETA-4" in n for n in notices if isinstance(n, str))
    check("unread fallback control: with DW_REAL_CONFIG_DIR set, the unread subject shows",
          shown, (control.stdout + control.stderr)[:300])


def main():
    case_flag_unapproved()
    case_flag_deleted_protected_file()
    case_why_field_is_sanitized()
    case_allow_approved()
    case_outbound_alone_no_disk_change()
    case_missing_transcript()
    case_ordinary_turn()
    case_last_human_reader_skips_a_peer_record()
    case_not_a_repo()
    case_model_failure()
    case_incident_cap_same_session()
    case_early_exit_before_transcript_read()
    case_allow_verdict_cached_until_the_file_changes()
    case_unknown_is_never_cached()
    case_protected_file_committed_this_turn_is_judged()
    case_cache_key_holds_the_repo_and_a_bounded_read()
    case_judge_isolation_copies_credentials()
    case_invoke_model_argv()
    case_invoke_model_timeout_is_error()
    case_e1_model_output_is_read_as_utf8()
    case_token_t1_file_reaches_child_env()
    case_token_t3_parent_env_not_passed_through()
    case_token_t4_no_usable_token_file_is_no_token()
    case_token_t5_failure_error_omits_token()
    case_token_encodings_read_as_the_bare_token()
    case_token_t10_undecodable_file_is_an_error()
    case_main_ordinary_turn()
    case_main_prints_the_config_report()
    case_main_missing_transcript()
    case_main_stop_hook_active_stays_quiet()

    for case in (
        case_invoke_model_long_prompt_reaches_child_whole,
        case_invoke_model_prompt_bytes_reach_child_exact,
        case_invoke_model_return_shape_pinned,
        case_parse_verdict_default_shape,
        case_parse_verdict_honours_a_custom_shape,
        case_parse_verdict_is_the_one_home,
        case_invoke_model_custom_shape_end_to_end,
        case_argv_bad_combinations_fall_back_to_invoke_model,
        case_bad_flag_runs_the_default_model_call,
        case_emit_prompt_prints_needs_model_and_calls_no_model,
        case_emit_prompt_is_silent_when_nothing_is_due,
        case_emit_prompt_missing_transcript_never_asks_for_a_model,
        case_model_text_flag_prints_flag_and_calls_no_model,
        case_model_text_allow_is_silent_and_cached,
        case_model_text_without_a_verdict_is_unknown_never_a_pass,
        case_model_error_is_unknown_cut_to_200_and_not_cached,
        case_emit_prompt_runs_with_dash_I_as_the_mod_spawns_it,
        case_default_path_still_calls_claude_without_a_flag,
        case_model_text_after_a_cached_verdict_says_verdict_lost,
        case_model_error_after_a_cached_verdict_is_not_silent,
        case_phase_one_prints_a_key_for_the_evidence_it_judged,
        case_phase_two_with_a_moved_key_reads_unknown_never_allow,
        case_phase_two_with_the_same_key_stays_silent_on_allow,
        case_split_output_carries_the_config_notice_apart_from_the_verdict,
        case_unread_fallback_is_named_when_dw_real_config_dir_is_unset,
    ):
        run_case(case)

    if FAILED:
        print("test_decision_watch FAIL: %d failing check(s)" % len(FAILED))
        return 1
    print("test_decision_watch PASS: all checks right, %d skipped" % len(SKIPPED))
    return 0


if __name__ == "__main__":
    sys.exit(main())
