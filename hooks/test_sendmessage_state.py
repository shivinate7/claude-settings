#!/usr/bin/env python3
"""Cases for hooks/sendmessage_state.py, the SendMessage PreToolUse command hook.
Standard library only, and no test runner.

Run it from the repository root:

    python hooks/test_sendmessage_state.py

Each hook case runs the real script as a child, with the harness's stdin shape, and reads back
its exit code, stdout and stderr. Two fakes sit under it:
- `claude -p` (the model). A sitecustomize.py on the child's PYTHONPATH wraps subprocess.run, as
  hooks/test_reply_judge.py does, and answers `claude -p` with the JSON envelope that
  decision_watch.invoke_model parses. The real invoke_model runs on each canned answer.
- The reader stub (STUB_READER). Every hook run points the hook's pointer checkout at a temp clone
  whose receiver-state.mjs is that stub. Real node runs it. The stub reads the rows file the case
  wrote and prints the state with the repo's lib.mjs, so the rows-to-state mapping is real. Only the
  `claude agents --json` read is stubbed, and a stub failure prints unseen, as the real reader does.
  fake_claude.py's agents branch is now unused. The claude launcher stays on PATH for the model call.
Every claude call is recorded, so "no model call" is read from the record, not assumed.
CLAUDE_CONFIG_DIR is a fresh temp folder: no real pointer file or token is read.

Canary: every hook run must leave a `loaded` file (the sitecustomize ran) and, when the hook
reaches the reader, exactly one stub call naming the peer, with no agents call. Without them, a
"no model call" pass proves nothing.

Git: the sitecustomize also records every git start (kind git), so a rulings read is counted, not
assumed. The past-ruling cases put the fixture repo only in the payload's cwd. The child's own cwd
is a folder with no store, so a hook that reads the process cwd finds nothing and fails.

Timing: the answer cases set READER_TIMEOUT to None, so a slow runner cannot cut the stub short. A stub
that never answers ends at run_hook's cap as one FAIL line that names the case: a hang guard, not a speed
check. Only the hang and hold cases set a short timeout, and they need it to fire.

Mutation: SENDMESSAGE_STATE_UNDER_TEST names another copy of the hook to run instead. Its
find_reader looks for mods/ beside that copy, so a copy needs a mods/ folder beside its hooks/.
"""
import atexit
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.environ.get("SENDMESSAGE_STATE_UNDER_TEST") or os.path.join(HERE, "sendmessage_state.py")
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lint"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)
import test_ruled_store as fixture  # noqa: E402  the one home of the roadmap-ref fixtures (lint/test_ruled_store.py)
ROOT = _test_temp.run_folder()  # every temp file of this run, fixture repos included, lives under it
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import cost_probe  # noqa: E402  the shared cost counters (testing/cost_probe.py)
atexit.register(shutil.rmtree, ROOT, ignore_errors=True)  # a pass, a failed case or a crash leaves no folder
STUB_DIR = os.path.join(ROOT, "stub")
FAILED = []
SKIPPED = []
RUNS = [0]
PEER, OTHER = "peer", "other"
SID_A, SID_B = "ses00001", "ses00002"
ALLOW = '{"ok": true}'
FLAG = '{"ok": false, "reason": "parallelism-no-mid-task-talk: send only what changes the work."}'
READER_SECONDS = 3  # the hook's READER_TIMEOUT for the hang and hold cases, set by TIMED_HOOK
NO_BOUND = None  # the hook's READER_TIMEOUT for every answer case: the stub is never cut short
HOLD_MS = 30000  # the held child writes "done" only after this, far later than the hook's return
HARNESS_CAP = HOLD_MS // 1000 + 30  # a hang guard for the harness call, never a timing check

STUB_SITE = r'''
import json, os, subprocess
_real_run = subprocess.run
_real_popen = subprocess.Popen


class _RecordingPopen(_real_popen):
    """Writes one record per git start (subprocess.run and Popen both come here), then starts it as usual."""

    def __init__(self, args, *a, **kw):
        try:
            argv = [str(x) for x in args] if isinstance(args, (list, tuple)) else [str(args)]
            if argv and os.path.basename(argv[0]).lower() in ("git", "git.exe"):
                with open(os.environ["SM_RECORD"], "a", encoding="utf-8") as f:
                    f.write(json.dumps({"argv": argv, "kind": "git"}) + "\n")
        except Exception:
            pass  # a record that cannot be written never stops the git start
        _real_popen.__init__(self, args, *a, **kw)


subprocess.Popen = _RecordingPopen


def _fake_run(argv, **kwargs):
    if not (isinstance(argv, (list, tuple)) and argv
            and os.path.basename(str(argv[0])).lower() in ("claude", "claude.exe", "claude.cmd")):
        return _real_run(argv, **kwargs)
    prompt = kwargs.get("input") or b""
    prompt = prompt.decode("utf-8", "replace") if isinstance(prompt, bytes) else str(prompt)
    kind = "wording" if prompt.startswith("Judge this SendMessage call") else "busy"
    with open(os.environ["SM_RECORD"], "a", encoding="utf-8") as f:
        f.write(json.dumps({"argv": list(argv), "kind": kind}) + "\n")
    if os.environ.get("SM_MODEL_FAIL"):
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="stub model failure")
    answer = os.environ["SM_WORDING_ANSWER" if kind == "wording" else "SM_ANSWER"]
    return subprocess.CompletedProcess(argv, 0, stdout=json.dumps({"result": answer}), stderr="")


subprocess.run = _fake_run
with open(os.path.join(os.environ["SM_LOADED_DIR"], "loaded"), "w", encoding="utf-8") as f:
    f.write("1")
'''

FAKE_CLAUDE = r'''
import json, os, sys
with open(os.environ["SM_RECORD"], "a", encoding="utf-8") as f:
    f.write(json.dumps({"argv": sys.argv[1:]}) + "\n")
if os.environ.get("SM_AGENTS_FAIL"):
    sys.exit(1)
if "-p" in sys.argv:
    sys.stdout.write(json.dumps({"result": os.environ["SM_ANSWER"]}))
else:
    with open(os.environ["SM_AGENTS_FILE"], encoding="utf-8") as f:
        sys.stdout.write(f.read())
'''


# The reader stub: real node runs it in place of hooks/mods/session-board/hooks/receiver-state.mjs.
# idle or waiting prints that word. hang sleeps with no child. hold starts a child that keeps this
# process's stdout open, writes "started" first and "done" last; the hook must return before "done".
STUB_READER = r'''
import { spawn } from "node:child_process";
import { appendFileSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const dir = process.env.SM_READER_DIR;
const mode = process.env.SM_READER_MODE;
const holdMs = Number(process.env.SM_READER_HOLD_MS || "30000");
appendFileSync(join(dir, "reader.jsonl"), JSON.stringify({ argv: process.argv.slice(2) }) + "\n");
function report(word) {
    writeFileSync(join(dir, "word.txt"), word);  // written before the answer, so a crash leaves no word
    process.stdout.write(word + "\n");
}
if (mode === "idle" || mode === "waiting") {
    report(mode);
} else if (mode === "board") {
    // Only the claude board read is stubbed. The rows-to-state step is the repo's lib.mjs.
    if (process.env.SM_AGENTS_FAIL) {
        report("unseen");  // a failed board read prints unseen, as receiver-state.mjs does
    } else {
        const lib = await import(pathToFileURL(process.env.SM_LIB_PATH).href);
        report(lib.receiverState(lib.parseAgentsJson(readFileSync(process.env.SM_AGENTS_FILE, "utf8")), process.argv[2]));
    }
} else {
    if (mode === "hold") {
        // The child writes "started" first, holds the inherited stdout for the hold, and writes "done"
        // as its last act, so it must outlive a kill of node alone. On Windows, node puts each plain
        // child in a job that dies with node, so the done-writer is detached; a tree kill still reaches
        // it. "&&" holds done until the hold finishes: a kill of the hold must not reach it. Relative
        // names, with cwd set, keep the cmd quoting free of spaces.
        const secs = Math.ceil(holdMs / 1000);
        const stdio = ["ignore", "inherit", "inherit"];
        const child = process.platform === "win32"
            ? spawn("cmd.exe", ["/d", "/c", "echo 1 > started.flag & ping -n " + (secs + 1) + " 127.0.0.1 > nul && echo 1 > done.flag"],
                     { stdio, cwd: dir, windowsHide: true, detached: true })
            : spawn("sh", ["-c", "echo 1 > started.flag && sleep " + secs + " && echo 1 > done.flag"], { stdio, cwd: dir });
        child.on("error", () => {});
    }
    setTimeout(() => {}, holdMs + 5000);  // exits by itself if nothing kills it
}
'''

# Runs the hook with READER_TIMEOUT set: a number, or None for no wait bound. The product reads that
# module global at call time, so a fix that changes how the reader is run still meets this seam.
TIMED_HOOK = r'''
import importlib.util, sys
spec = importlib.util.spec_from_file_location("sendmessage_state_timed", %r)
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)
hook.READER_TIMEOUT = %r
sys.exit(hook.main())
'''


def check(name, ok, detail=""):
    if ok:
        print("ok   " + name)
    else:
        FAILED.append(name)
        print("FAIL " + name + (" :: " + detail if detail else ""))


def skip(name, detail=""):
    """NOT-RUN: the case could not reach its precondition in time. Reported as SKIP, never PASS or FAIL."""
    SKIPPED.append(name)
    print("SKIP " + name + (" :: " + detail if detail else ""))
    if os.environ.get("GITHUB_ACTIONS"):  # a SKIP leaves the step green, so CI shows it as a warning
        print("::warning::SKIP " + name.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A"))


def write_launchers():
    os.makedirs(STUB_DIR, exist_ok=True)
    for name, text in (("sitecustomize.py", STUB_SITE), ("fake_claude.py", FAKE_CLAUDE)):
        with open(os.path.join(STUB_DIR, name), "w", encoding="utf-8") as f:
            f.write(text)
    fake = os.path.join(STUB_DIR, "fake_claude.py")
    posix = os.path.join(STUB_DIR, "claude")
    with open(posix, "w", encoding="utf-8", newline="\n") as f:
        f.write('#!/bin/sh\nexec "%s" "%s" "$@"\n' % (sys.executable, fake))
    os.chmod(posix, 0o755)
    with open(os.path.join(STUB_DIR, "claude.cmd"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write('@"%s" "%s" %%*\r\n' % (sys.executable, fake))


def argv_lines(path, kind=None):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    return [r["argv"] for r in rows if kind is None or r.get("kind") == kind]


def read_text(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


class Run:
    def __init__(self, proc, base, elapsed):
        self.base = base
        self.code = proc.returncode
        self.out = proc.stdout or ""
        self.err = proc.stderr or ""
        self.elapsed = elapsed
        self.loaded = os.path.exists(os.path.join(base, "loaded"))
        self.started = os.path.exists(os.path.join(base, "started.flag"))  # the hold child's first act
        self.done = os.path.exists(os.path.join(base, "done.flag"))  # the hold child's last act
        self.word = read_text(os.path.join(base, "word.txt"))  # the state the stub printed, if it got that far
        self.calls = argv_lines(os.path.join(base, "calls.jsonl"))
        self.reader_calls = argv_lines(os.path.join(base, "reader.jsonl"))
        self.model_calls = [a for a in argv_lines(os.path.join(base, "calls.jsonl"), "busy") if "-p" in a]  # the busy judge
        self.wording_calls = [a for a in argv_lines(os.path.join(base, "calls.jsonl"), "wording") if "-p" in a]
        self.log = read_text(os.path.join(base, "config", "guard.log")) or ""
        self.agents_calls = [a for a in self.calls if a[:2] == ["agents", "--json"]]
        self.git_starts = argv_lines(os.path.join(base, "calls.jsonl"), "git")
        self.rulings_reads = [a for a in self.git_starts if any("roadmap" in x for x in a)]  # any git start naming the roadmap

    def deny(self):
        """The hookSpecificOutput of a deny, or None when stdout is empty."""
        if not self.out.strip():
            return None
        return json.loads(self.out)["hookSpecificOutput"]

    def reached_board(self):
        """The hook asked the stub reader once, about PEER, and no claude board read ran."""
        return self.loaded and self.reader_calls == [[PEER]] and not self.agents_calls


def detail(r):
    return "code=%s out=%r err=%r busy=%d wording=%d agents=%d reader=%d word=%r loaded=%s wall=%.1fs" % (
        r.code, r.out[:160], r.err[-200:], len(r.model_calls), len(r.wording_calls), len(r.agents_calls),
        len(r.reader_calls), r.word, r.loaded, r.elapsed)


def point_reader_at_stub(cfg, base):
    """Point the hook's pointer checkout (guard_pointer.pointer_checkout) at a temp clone whose
    receiver-state.mjs is STUB_READER. find_reader then returns the stub, and node runs it."""
    clone = os.path.join(base, "clone")
    reader = os.path.join(clone, "mods", "session-board", "hooks", "receiver-state.mjs")
    os.makedirs(os.path.dirname(reader))
    with open(reader, "w", encoding="utf-8") as f:
        f.write(STUB_READER)
    with open(os.path.join(cfg, "CLAUDE.md"), "w", encoding="utf-8") as f:
        f.write("@%s/CLAUDE.md\n" % clone.replace("\\", "/"))


def run_hook(stdin_text, rows=None, answer=ALLOW, model_fail=False, agents_fail=False,
             reader_mode="board", reader_seconds=NO_BOUND, direct=False, cap=120, wording=ALLOW,
             override=None, base=None, cwd=None):
    RUNS[0] += 1
    base = os.path.join(ROOT, "run-%03d" % RUNS[0])
    cfg = os.path.join(base, "config")
    os.makedirs(cfg)
    if override is not None:  # (session id, override file body): the override the owner's prompt would write
        write_pass(cfg, *override)
    agents = os.path.join(base, "agents.json")
    with open(agents, "w", encoding="utf-8") as f:
        f.write(json.dumps(rows if rows is not None else []))
    env = {k: v for k, v in os.environ.items() if not k.startswith(("SM_", "GIT_"))}  # GIT_DIR would move the hook's git
    env.update({
        "CLAUDE_CONFIG_DIR": cfg,
        "PATH": STUB_DIR + os.pathsep + os.environ.get("PATH", ""),
        "PYTHONPATH": STUB_DIR,
        "SM_LOADED_DIR": base,
        "SM_RECORD": os.path.join(base, "calls.jsonl"),
        "SM_AGENTS_FILE": agents,
        "SM_ANSWER": answer,
        "SM_WORDING_ANSWER": wording,
    })
    if model_fail:
        env["SM_MODEL_FAIL"] = "1"
    if agents_fail:
        env["SM_AGENTS_FAIL"] = "1"
    script = HOOK
    point_reader_at_stub(cfg, base)  # every run: no case reaches the real reader
    env.update({"SM_READER_DIR": base, "SM_READER_MODE": reader_mode, "SM_READER_HOLD_MS": str(HOLD_MS),
                "SM_LIB_PATH": os.path.join(os.path.dirname(HERE), "mods", "session-board", "hooks", "lib.mjs")})
    if not direct:  # the hook's own READER_TIMEOUT is replaced here; direct runs the script as shipped
        script = os.path.join(base, "hook_timed.py")
        with open(script, "w", encoding="utf-8") as f:
            f.write(TIMED_HOOK % (HOOK, reader_seconds))
    started = time.monotonic()
    proc = subprocess.run([sys.executable, script], input=stdin_text, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, timeout=cap, cwd=cwd)
    return Run(proc, base, time.monotonic() - started)


def hook_input(to=PEER, message="Status: the step is done, no change for you.", session=SID_A, agent=None, cwd=None):
    payload = {"session_id": session, "tool_name": "SendMessage", "tool_input": {"to": to, "message": message}}
    if agent:
        payload["agent_id"] = agent
    if cwd:  # the payload's cwd: the repo the hook reads (Claude Code sends it on each tool call)
        payload["cwd"] = cwd
    return json.dumps(payload)


def write_pass(cfg, session, body):
    """Write <config>/state/override/<session>.json, the owner override (hooks/override.py)."""
    folder = os.path.join(cfg, "state", "override")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, session + ".json"), "w", encoding="utf-8") as f:
        f.write(body if isinstance(body, str) else json.dumps(body))


def row(sid, name, status, cwd="/x/app"):
    return {"sessionId": sid, "cwd": cwd, "name": name, "status": status}


# ---- the reader find (in-process; the pointer and the hooks folder are swapped in)

def load_hook():
    spec = importlib.util.spec_from_file_location("sendmessage_state_under_test", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def reader_at(root):
    path = os.path.join(root, "mods", "session-board", "hooks", "receiver-state.mjs")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("")
    return path


def find_with(mod, pointer, here):
    """find_reader() with guard_pointer.pointer_checkout and the hooks folder swapped in."""
    fake = types.ModuleType("guard_pointer")
    fake.pointer_checkout = pointer
    saved_module, saved_here = sys.modules.get("guard_pointer"), mod.HERE
    sys.modules["guard_pointer"] = fake
    mod.HERE = here
    try:
        return mod.find_reader()
    finally:
        mod.HERE = saved_here
        if saved_module is None:
            sys.modules.pop("guard_pointer", None)
        else:
            sys.modules["guard_pointer"] = saved_module


def same_path(a, b):
    return os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))


def case_find_reader():
    mod = load_hook()
    base = tempfile.mkdtemp(prefix="find_", dir=ROOT)
    pointer_root = os.path.join(base, "pointer")
    pointer_reader = reader_at(pointer_root)
    sibling_root = os.path.join(base, "sibling")
    sibling_reader = reader_at(sibling_root)
    here = os.path.join(sibling_root, "hooks")
    os.makedirs(here)
    empty_here = os.path.join(base, "empty", "hooks")
    os.makedirs(empty_here)

    def boom():
        raise OSError("no pointer file")

    got = find_with(mod, lambda: pointer_root, here)
    check("find_reader: the pointer checkout wins over the sibling clone",
          same_path(got, pointer_reader), repr(got))
    got = find_with(mod, lambda: "", here)
    check("find_reader: no pointer falls back to the sibling clone",
          same_path(got, sibling_reader), repr(got))
    got = find_with(mod, boom, here)
    check("find_reader: a pointer that raises falls back to the sibling clone",
          same_path(got, sibling_reader), repr(got))
    got = find_with(mod, lambda: os.path.join(base, "no-such-root"), here)
    check("find_reader: a pointer with no reader falls back to the sibling clone",
          same_path(got, sibling_reader), repr(got))
    got = find_with(mod, lambda: "", empty_here)
    check("find_reader: neither found returns empty", got == "", repr(got))


# ---- the hook, run as a child with the harness's stdin shape

def case_idle_and_waiting_allow_with_no_model_call():
    # The stub reader answers the word, so no claude board read runs. Its record shows it was asked
    # about PEER. Allow and unseen look the same here; the no-busy-call check is what a mutant that
    # sends idle to the busy judge turns red. The wording judge reads every send, once.
    for status in ("idle", "waiting"):
        r = run_hook(hook_input(), reader_mode=status)
        check("%s receiver: allow, no busy call, one wording call, no output" % status,
              r.code == 0 and r.out == "" and r.err == "" and not r.model_calls and not r.agents_calls
              and len(r.wording_calls) == 1 and r.loaded and r.reader_calls == [[PEER]], detail(r))


# Busy receiver and a model FLAG. Each row: (row id, model answer, reason prefix the deny carries).
# The blank-reason row reaches the default-reason branch, which the model-reason row does not.
BUSY_FLAG_ROWS = (
    ("busy + model FLAG: one deny carrying the model's reason", FLAG,
     "parallelism-no-mid-task-talk"),
    ("busy + FLAG with a blank reason: deny with the default reason",
     '{"ok": false, "reason": "   "}', "parallelism-no-mid-task-talk"),
)


def case_busy_flag_rows():
    for name, answer, want in BUSY_FLAG_ROWS:
        r = run_hook(hook_input(), rows=[row(SID_A, PEER, "busy")], answer=answer)
        d = r.deny()
        check(name, r.code == 0 and d is not None and d.get("permissionDecision") == "deny"
              and d.get("permissionDecisionReason", "").startswith(want)
              and len(r.model_calls) == 1 and r.reached_board(), detail(r))


def case_busy_allows_when_the_model_does_not_flag():
    r = run_hook(hook_input(), rows=[row(SID_A, PEER, "busy")], answer=ALLOW)
    check("busy + model ok: allow, one model call, no deny",
          r.code == 0 and r.out == "" and r.err == "" and len(r.model_calls) == 1 and r.reached_board(), detail(r))


def case_unseen_receivers_allow_with_no_model_call():
    cases = [
        ("no board row for the name", [row(SID_B, OTHER, "busy")]),
        ("a duplicate name", [row(SID_A, PEER, "busy"), row(SID_B, PEER, "idle")]),
        ("an unknown status", [row(SID_A, PEER, "running")]),
    ]
    # The rows-to-state step is the real lib.mjs, so each row shape must come out unseen there.
    # The word check catches a stub that crashed: the hook would then read unseen for the wrong reason.
    for label, rows in cases:
        r = run_hook(hook_input(), rows=rows)
        check("unseen (%s): allow, no busy call, one wording call" % label,
              r.code == 0 and r.out == "" and r.err == "" and not r.model_calls and r.reached_board()
              and len(r.wording_calls) == 1
              and r.word == "unseen", detail(r))
    # SM_AGENTS_FAIL: the stub stands in for a failed claude read, and prints unseen as the real reader does.
    r = run_hook(hook_input(), rows=[row(SID_A, PEER, "busy")], agents_fail=True)
    check("unseen (agents list fails): allow, no busy call",
          r.code == 0 and r.out == "" and r.err == "" and not r.model_calls and r.reached_board()
          and r.word == "unseen", detail(r))


def case_advisor_named_receiver_is_a_peer():
    # The terminal advisor is retired (questions-go-to-owner), so no name is carved out: a busy
    # session named advisor-ab reaches the model judge like any peer.
    for name in ("advisor-ab", "advisorx", "advisor-asks-xx", "advisor-a", "advisor-abcdefg"):
        r = run_hook(hook_input(to=name, message="Chat."), rows=[row(SID_A, name, "busy")], answer=FLAG)
        check("%s is a peer, judged as before" % name,
              r.deny() is not None and len(r.model_calls) == 1, detail(r))


def case_malformed_input_fails_open_with_no_deny():    # direct=True runs the script as shipped, so its __main__ line is under test. The first two raise
    # inside main() and print the failed-open line, with no judge call. The rest are not a plain message
    # to a named receiver: no board read and no busy call, but the wording judge still reads them.
    for label, text, opened, wording in (
        ("stdin is not JSON", "not json", True, 0),
        ("tool_input is not an object", '{"tool_input": "oops"}', True, 0),
        ("to is not a string", '{"tool_input": {"to": 5, "message": "x"}}', False, 1),
        ("to is blank", '{"tool_input": {"to": "  ", "message": "x"}}', False, 1),
        ("message is an object", '{"tool_input": {"to": "peer", "summary": "s", "message": {"type": "x"}}}', False, 1),
    ):
        r = run_hook(text, rows=[row(SID_A, PEER, "busy")], answer=FLAG, direct=True)
        check("malformed input (%s): exit 0, no deny, no busy call, %d wording call, no reader call, failed-open line %s"
              % (label, wording, "printed" if opened else "absent"),
              r.code == 0 and r.out == "" and not r.model_calls and len(r.wording_calls) == wording
              and r.reader_calls == [] and ("failed open" in r.err) == opened, detail(r))
    r = run_hook('{"session_id": "%s", "tool_input": {"to": "peer", "summary": "chat about X", "message": {"type": "x"}}}'
                 % SID_A, wording=FLAG, direct=True)
    d = r.deny()
    check("a structured message the wording judge flags: one deny, no board read",
          d is not None and d.get("permissionDecision") == "deny" and len(r.wording_calls) == 1
          and r.reader_calls == [], detail(r))


def case_reader_timeout_allows_with_one_plain_line():
    # A reader that hangs with no child, under the short timeout: a real kill, not a fake. The board
    # would say busy and the model would flag, so a timeout that reached the model shows as a deny.
    r = run_hook(hook_input(), rows=[row(SID_A, PEER, "busy")], answer=FLAG,
                 reader_mode="hang", reader_seconds=READER_SECONDS)
    lines = r.err.strip().splitlines()
    check("reader times out: exit 0, no deny, no busy call, one plain board-timeout line",
          r.code == 0 and r.out == "" and not r.model_calls and r.loaded and len(lines) == 1
          and "board read timed out" in lines[0] and "TimeoutExpired" not in r.err and "Command" not in r.err,
          detail(r))


def case_reader_that_holds_the_pipe_returns_before_the_child_ends():
    # The reader's child holds the stdout pipe for HOLD_MS, then writes "done" as its last act. Order,
    # not speed: the hook has returned while done does not exist yet, so it did not wait on the pipe.
    # No wall-clock bound. If node did not start the child before the timeout, the case is NOT-RUN.
    # Only Windows tells a pipe wait from none. On POSIX, subprocess.run's timeout path waits on the child only, so
    # a run() read of the pipe returns early there; a Popen + communicate() read is unmeasured there.
    try:
        r = run_hook(hook_input(), reader_mode="hold", reader_seconds=READER_SECONDS, cap=HARNESS_CAP)
    except subprocess.TimeoutExpired:  # the hold ends at HOLD_MS and the stub by itself 5 s later
        skip("reader holds the pipe: hook returned before the harness cap",
             "still running after %d s, past the hold and the stub's own end: a slow runner, "
             "so the order is not tested" % HARNESS_CAP)
        return
    if not r.started:
        skip("reader holds the pipe: the child wrote its started marker before the timeout",
             "started not seen within %s s, so the order is not tested :: %s" % (READER_SECONDS, detail(r)))
        return
    check("reader holds the pipe: hook returned before the held child wrote done",
          r.code == 0 and not r.done, detail(r))
    check("reader holds the pipe: exit 0, no deny, no busy call, board-timeout line",
          r.code == 0 and r.out == "" and not r.model_calls and "board read timed out" in r.err, detail(r))


def case_model_failures_fail_open_with_no_deny():
    r = run_hook(hook_input(), rows=[row(SID_A, PEER, "busy")], answer=FLAG, model_fail=True)
    check("busy + model exits non-zero: exit 0, no deny, failed-open line",
          r.code == 0 and r.out == "" and "failed open" in r.err and len(r.model_calls) == 1
          and r.reached_board(), detail(r))
    # One model call is required too: a reader timeout also prints "failed open", with no call.
    r = run_hook(hook_input(), rows=[row(SID_A, PEER, "busy")], answer='{"verdict": "FLAG"}')
    check("busy + off-shape model answer: exit 0, no deny, failed-open line, one model call",
          r.code == 0 and r.out == "" and "failed open" in r.err and len(r.model_calls) == 1
          and r.reached_board(), detail(r))


def case_model_row_names_the_call():
    # The model-per-role table has one row per model call of this hook; each row's model and effort
    # must equal what the call uses. Busy judge: decision_watch.MODEL at invoke_model's default effort.
    # Wording judge: the hook's WORDING_MODEL, and no --effort (the model's default).
    record = os.path.join(os.path.dirname(HERE), "docs", "decisions", "agent-model-cap.md")
    try:
        with open(record, encoding="utf-8") as f:
            lines = [line for line in f if line.startswith("|")]
    except OSError as exc:
        lines = []
        check("model table: record readable", False, str(exc))
    rows = [line for line in lines if "hooks/sendmessage_state.py" in line]
    wording_rows = [line for line in lines if line.startswith("| SendMessage wording judge")]
    check("model table: exactly one row for the SendMessage busy judge", len(rows) == 1, repr(rows)[:200])
    check("model table: exactly one row for the SendMessage wording judge", len(wording_rows) == 1,
          repr(wording_rows)[:200])
    spec = importlib.util.spec_from_file_location("decision_watch", os.path.join(HERE, "decision_watch.py"))
    dw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dw)
    with open(os.path.join(HERE, "decision_watch.py"), encoding="utf-8") as f:
        effort_arg = 'effort="xhigh"):' in f.read()
    if len(rows) == 1:
        cells = [c.strip() for c in rows[0].strip().strip("|").split("|")]
        check("model table: busy row model is the call's model (haiku)",
              "haiku" in cells[1] and dw.MODEL == "haiku", repr(cells[1:2]))
        check("model table: busy row effort is the call's effort (xhigh)",
              cells[2] == "xhigh" and effort_arg, repr(cells[2:3]))
    if len(wording_rows) == 1:
        cells = [c.strip() for c in wording_rows[0].strip().strip("|").split("|")]
        model = getattr(load_hook(), "WORDING_MODEL", None)  # None on a hook with no wording judge: a FAIL
        check("model table: wording row model is the call's model (%s)" % model,
              bool(model) and model in cells[1], repr(cells[1:2]))
        check("model table: wording row effort is the model default", cells[2].startswith("model default"),
              repr(cells[2:3]))


def case_wording_call_carries_its_model_and_no_effort():
    model = getattr(load_hook(), "WORDING_MODEL", None)
    r = run_hook(hook_input(), reader_mode="idle")
    argv = r.wording_calls[0] if len(r.wording_calls) == 1 else []
    pairs = list(zip(argv, argv[1:]))
    check("wording call: --model %s, no --effort" % model,
          bool(model) and ("--model", model) in pairs and "--effort" not in argv, detail(r) + " argv=%r" % argv)


def case_wording_judge_denies_any_receiver():
    # The wording judge reads every send, so an idle, busy or unseen receiver is denied on its FLAG.
    for label, kwargs in (("idle", {"reader_mode": "idle"}),
                          ("unseen", {"rows": [row(SID_B, OTHER, "busy")]}),
                          ("busy, busy judge ok", {"rows": [row(SID_A, PEER, "busy")], "answer": ALLOW})):
        r = run_hook(hook_input(message="Chat."), wording=FLAG, **kwargs)
        d = r.deny()
        check("wording FLAG (%s): one deny carrying the rule once" % label,
              r.code == 0 and d is not None and d.get("permissionDecision") == "deny"
              and d.get("permissionDecisionReason", "").startswith("parallelism-no-mid-task-talk: ")
              and d.get("permissionDecisionReason", "").count("parallelism-no-mid-task-talk") == 1
              and len(r.wording_calls) == 1, detail(r))
    r = run_hook(hook_input(message="Chat."), reader_mode="idle", wording=FLAG)
    check("wording FLAG: the deny writes one guard.log line", "\tdeny\tparallelism-no-mid-task-talk\t" in r.log,
          detail(r) + " log=%r" % r.log)


FUTURE, PAST = "2099-01-01T00:00:00+00:00", "2000-01-01T00:00:00+00:00"
TIMED = {"kind": "timed", "until": FUTURE}
ONCE = {"kind": "once", "until": FUTURE, "id": "0" * 32}


def claims(r):
    folder = os.path.join(r.base, "config", "state", "override")
    return [n for n in os.listdir(folder) if n.endswith(".claim")] if os.path.isdir(folder) else []


def case_override_lifts_a_deny():
    # decision owner-override: an active override lifts either judge.
    both = {"rows": [row(SID_A, PEER, "busy")], "answer": FLAG, "wording": FLAG}
    for label, override, inp, kwargs, lifted in (
        ("timed override, both judges FLAG", (SID_A, TIMED), hook_input(), both, True),
        ("timed override, an agent's call", (SID_A, TIMED), hook_input(agent="a1"), both, True),
        ("one-act override, wording FLAG", (SID_A, ONCE), hook_input(), {"reader_mode": "idle", "wording": FLAG}, True),
        ("one-act override, busy FLAG", (SID_A, ONCE), hook_input(), {"rows": [row(SID_A, PEER, "busy")], "answer": FLAG}, True),
        ("one-act override, an agent's call", (SID_A, ONCE), hook_input(agent="a1"), both, False),
        ("an ended override", (SID_A, dict(TIMED, until=PAST)), hook_input(), both, False),
        ("another session's override", (SID_B, TIMED), hook_input(), both, False),
        ("a corrupt override file", (SID_A, "{not json"), hook_input(), both, False),
        ("no override", None, hook_input(), both, False),
    ):
        r = run_hook(inp, override=override, **kwargs)
        if lifted:
            check("%s: lifted, no output, one override log line" % label,
                  r.code == 0 and r.out == "" and r.log.count("\toverride\tparallelism-no-mid-task-talk\t") == 1
                  and "\tdeny\t" not in r.log, detail(r) + " log=%r" % r.log)
        else:
            d = r.deny()
            check("%s: the deny stands" % label,
                  r.code == 0 and d is not None and d.get("permissionDecision") == "deny"
                  and "\toverride\t" not in r.log, detail(r) + " log=%r" % r.log)
    r = run_hook(hook_input(), override=(SID_A, ONCE), reader_mode="idle", wording=FLAG)
    check("one-act override: the lift spends it (one claim marker)", len(claims(r)) == 1, detail(r))
    r = run_hook(hook_input(), override=(SID_A, ONCE), reader_mode="idle", wording=ALLOW)
    check("one-act override: an allowed send leaves it unspent", r.out == "" and claims(r) == [], detail(r))


def case_deny_ends_with_the_override_line():
    # step c80 of decision owner-override: a refusal an override can lift names the typed word.
    r = run_hook(hook_input(), reader_mode="idle", wording=FLAG)
    d = r.deny() or {}
    check("a deny names `override 15m` for the main session", d.get("permissionDecision") == "deny"
          and "override 15m" in d.get("permissionDecisionReason", ""), detail(r))
    r = run_hook(hook_input(agent="a1"), reader_mode="idle", wording=FLAG)
    reason = (r.deny() or {}).get("permissionDecisionReason", "")
    check("a deny for an agent's call names `override 15m`", "override 15m" in reason, detail(r))


# ---- the past-ruling check: a settling message that cites a decision a ruling superseded
#
# The check reads the rulings store (the roadmap ref's roadmap/rulings tree) with git, in the payload's cwd.
# Each past-ruling case runs the child with its own cwd in a folder with no store (the "plain" kind), and
# puts the fixture repo only in the payload, so a hook that reads the process cwd finds no store and fails.


class FixtureError(Exception):
    """A fixture repo did not build. Its case records one FAIL line, and the other cases still run."""


SETTLING = (  # one phrase per message: a check that matches only some of the phrases fails the others
    ("settled", "This is settled."),
    ("no owner item", "There is no owner item for it."),
    ("already ruled", "It is already ruled."),
    ("owner already decided", "The owner already decided it."),
)
SLUG = "action-pins-follow-sessions"  # the decision R44 supersedes: the incident's decision
KEPT = "kept-decision"  # cited by no ruling's ref line
FREE = "free-text-decision"  # named only in r46's free ruling text
PREFIX = "action-pins"  # a true prefix of SLUG, cited by no ruling
R44_PATH = "roadmap/rulings/r44.json"
R44_REF = ('docs/decisions/%s.md: "Pins stay current on demand: the session that runs the tool sees the drift '
           'and moves the pin. No bot and no schedule."' % SLUG)
R44_TEXT = ("- **R44. Child repos follow claude-settings, with cited exceptions only.** Free text: decision %s "
            "says pins move only when a session sees drift." % SLUG)
R46_TEXT = "- **R46. Fixture ruling with a free-text mention only.** Free text: decision %s stands as written." % FREE
R47_REF = "test-strategy-reset: Reset of the test strategy: the old plan applies no longer, and the new plan replaces it."
R47_TEXT = "- **R47. Fixture ruling that replaces the test strategy.** Free text: a new strategy note, nothing more."
R48_REF = ('docs/decisions/punct-case-decision.md: "CURRENT demand: the Session sees the DRIFT, and it moves on; '
           'no SCHEDULE!"')  # the same key words as R44's sentence, in other case and punctuation
R48_TEXT = "- **R48. Fixture ruling whose quoted sentence has other case and punctuation.** Free text: none."
R49_TEXT = "- **R49. Fixture ruling that retires a whole decision by its docs path.** Free text: none."
R50_TEXT = "- **R50. Fixture ruling that retires a whole decision by its bare slug.** Free text: none."
LAST_SLUGS = ("list-oxford-last", "semi-last-decision", "paren-last-decision", "slash-last-decision")  # r51 retires each
R51_TEXT = "- **R51. Fixture ruling that retires the last slug of each cite list.** Free text: none."
R52_REF = "lint/report_guard.py:36: 'The refusal remedy never names an owner, per decision guard-remedy-not-to-owner.'"
R52_TEXT = "- **R52. Fixture ruling whose code-style ref mentions a decision in the middle of its text.** Free text: none."
KEY_SENTENCE = "The session sees the drift."  # two key words shared with R44's sentence: the deny threshold
CITE_FORMS = ("docs/decisions/%s.md", "`docs/decisions/%s`", "decision %s", "decisions `%s`", "decision `%s`")
GIT_IDENT = {"GIT_AUTHOR_NAME": "fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
             "GIT_COMMITTER_NAME": "fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid"}
STORES = {}  # one fixture repo per kind, built on first use and shared by the cases of this run


def settled_text(sentence, cite):
    return "%s Pin the four actions to a main commit, per %s. %s" % (sentence, cite, KEY_SENTENCE)


def ruling_json(rid, ruling, refs=()):
    """refs: a ref string (kind main-sentence, the docs-path shape) or a {"kind", "ref"} dict."""
    supersedes = [r if isinstance(r, dict) else {"kind": "main-sentence", "ref": r} for r in refs]
    return json.dumps({"id": rid, "at": "2026-11-11T14:05:00-06:00", "ruling": ruling, "status": "open",
                       "supersedes": supersedes, "title": "Fixture ruling %s." % rid}, indent=1) + "\n"


def store_files():
    """The rulings a real store holds: r44 supersedes SLUG in the docs-path shape, r47 supersedes a slug in the
    slug-first shape, r46 names FREE in its free text, r48 quotes a sentence in other case and punctuation,
    r49 and r50 retire a whole decision (no quoted sentence), and the filler brings the store to full size."""
    files = {"r44.json": ruling_json("r44", R44_TEXT, (R44_REF,)), "r46.json": ruling_json("r46", R46_TEXT),
             "r47.json": ruling_json("r47", R47_TEXT, ({"kind": "decision", "ref": R47_REF},)),
             "r48.json": ruling_json("r48", R48_TEXT, (R48_REF,)),
             "r49.json": ruling_json("r49", R49_TEXT, ("docs/decisions/bare-path-retired.md",)),
             "r50.json": ruling_json("r50", R50_TEXT, ({"kind": "decision", "ref": "bare-slug-retired"},)),
             "r51.json": ruling_json("r51", R51_TEXT, tuple({"kind": "decision", "ref": s} for s in LAST_SLUGS)),
             "r52.json": ruling_json("r52", R52_TEXT, ({"kind": "main-sentence", "ref": R52_REF},))}
    for n in range(1, 151):
        files.setdefault("r%d.json" % n, ruling_json("r%d" % n, "Filler ruling %d, supersedes nothing." % n))
    return files


def git_out(repo, *args, check=True):
    """One git call in a fixture repo. Identity and config come from the fixture, not the reader's environment."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_IDENT)
    proc = subprocess.run(["git", "-C", repo, "-c", "commit.gpgsign=false", *args],
                          capture_output=True, text=True, env=env, timeout=60)
    if check and proc.returncode:
        raise FixtureError("git %s in %s: %s" % (args[0], os.path.basename(repo), " ".join(proc.stderr.split())))
    return proc


def ref_resolves(repo, ref):
    return git_out(repo, "rev-parse", "--verify", "--quiet", ref, check=False).returncode == 0


def make_repo(name, rulings=None, ref="roadmap", origin_extra=None):
    """A repo under the run folder, with a main commit. `rulings` (file name -> JSON text) makes a store commit
    under roadmap/rulings/. `ref` names the store commit: "roadmap" (the local branch), "origin" (the
    remote-tracking ref refs/remotes/origin/roadmap) or None (no store ref). With no rulings, the store commit
    is the main commit, so the ref holds no rulings. `origin_extra` (file name -> JSON text) is committed on top
    of the store as origin/roadmap, so the local ref can lack a ruling that origin has."""
    repo = os.path.join(ROOT, name)
    os.makedirs(repo)
    git_out(repo, "init", "-q")
    with open(os.path.join(repo, "README.md"), "w", encoding="utf-8") as f:
        f.write("fixture\n")
    git_out(repo, "add", "README.md")
    main = git_out(repo, "commit-tree", git_out(repo, "write-tree").stdout.strip(), "-m", "main").stdout.strip()
    git_out(repo, "update-ref", "refs/heads/main", main)
    store = main
    if rulings is not None:
        folder = os.path.join(repo, "roadmap", "rulings")
        os.makedirs(folder)
        for fname, text in rulings.items():
            with open(os.path.join(folder, fname), "w", encoding="utf-8") as f:
                f.write(text)
        git_out(repo, "add", "roadmap")
        tree = git_out(repo, "write-tree").stdout.strip()
        store = git_out(repo, "commit-tree", tree, "-p", main, "-m", "store").stdout.strip()
    if ref == "roadmap":
        git_out(repo, "update-ref", "refs/heads/roadmap", store)
    elif ref == "origin":
        git_out(repo, "update-ref", "refs/remotes/origin/roadmap", store)
    if origin_extra:
        folder = os.path.join(repo, "roadmap", "rulings")
        os.makedirs(folder, exist_ok=True)
        for fname, text in origin_extra.items():
            with open(os.path.join(folder, fname), "w", encoding="utf-8") as f:
                f.write(text)
        git_out(repo, "add", "roadmap")
        tree = git_out(repo, "write-tree").stdout.strip()
        origin = git_out(repo, "commit-tree", tree, "-p", store, "-m", "origin").stdout.strip()
        git_out(repo, "update-ref", "refs/remotes/origin/roadmap", origin)
    return repo


def drop_blob(repo, ref, path):
    """Delete the loose object of one file's blob: the ref still resolves, and git cannot read that file."""
    sha = git_out(repo, "rev-parse", "%s:%s" % (ref, path)).stdout.strip()
    obj = os.path.join(repo, ".git", "objects", sha[:2], sha[2:])
    os.chmod(obj, stat.S_IWRITE)  # git makes objects read-only, and Windows will not delete one otherwise
    os.remove(obj)


def store(kind):
    """The fixture repo of one kind. Built once per run; no case writes to one."""
    if kind not in STORES:
        if kind == "full":
            STORES[kind] = make_repo("full", store_files())
        elif kind == "origin":
            STORES[kind] = make_repo("origin-only", store_files(), ref="origin")
        elif kind == "empty":
            STORES[kind] = make_repo("empty", None, ref="roadmap")
        elif kind == "absent":
            STORES[kind] = make_repo("absent", None, ref=None)
        elif kind == "absent-stale-head":  # no roadmap ref anywhere; its FETCH_HEAD is set by its one case
            STORES[kind] = make_repo("absent-stale-head", None, ref=None)
        elif kind == "stale-local":  # the local roadmap ref lacks r44, and origin/roadmap has it
            full = store_files()
            STORES[kind] = make_repo("stale-local", {k: v for k, v in full.items() if k != "r44.json"},
                                     ref="roadmap", origin_extra={"r44.json": full["r44.json"]})
        elif kind == "broken":
            STORES[kind] = make_repo("broken", store_files())
            drop_blob(STORES[kind], "roadmap", R44_PATH)
        else:  # "plain": a folder that is no repository
            STORES[kind] = os.path.join(ROOT, "plain")
            os.makedirs(STORES[kind], exist_ok=True)
    return STORES[kind]


STORE_KINDS = ("full", "origin", "empty", "stale-local", "broken")  # the kinds whose repo holds a roadmap ref


def prime(kind):
    """A fresh roadmap FETCH_HEAD in the repo of store `kind`, written by each run. One written at build time ages past
    roadmap_ref.MAX_AGE on a slow runner, and the run then reads the ref as stale. A kind with no roadmap ref gets none,
    so the freshness check finds no roadmap fetch on record for it."""
    if kind in STORE_KINDS:
        fixture.write_fetch_head(store(kind), "roadmap")


def past_run(text, kind, **kwargs):
    """Run the hook on `text`, the payload's cwd in store `kind`, the child's own cwd in the plain folder."""
    prime(kind)
    return run_hook(hook_input(message=text, cwd=store(kind)), reader_mode="idle", cwd=store("plain"), **kwargs)


def denied(r):
    """The deny's reason, or None when the hook did not deny. Output that is not a deny reads as no deny."""
    try:
        d = r.deny()
    except (ValueError, KeyError, TypeError):
        return None
    if not d or d.get("permissionDecision") != "deny":
        return None
    return d.get("permissionDecisionReason", "")


def store_text(repo, ref, path):
    return git_out(repo, "show", "%s:%s" % (ref, path), check=False).stdout


def check_allow_with_no_git(r, label):
    check("%s: allow (exit 0, no output, no stderr)" % label, r.code == 0 and r.out == "" and r.err == "", detail(r))
    check("%s: the send reaches the wording judge once" % label, len(r.wording_calls) == 1, detail(r))
    check("%s: no git start at all (no store read, no pre-check)" % label, not r.git_starts,
          detail(r) + " git=%r" % r.git_starts)


def case_git_popen_is_recorded():
    base = os.path.join(ROOT, "git-canary")
    os.makedirs(base)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("SM_", "GIT_"))}
    env.update({"PYTHONPATH": STUB_DIR, "SM_LOADED_DIR": base, "SM_RECORD": os.path.join(base, "calls.jsonl")})
    code = ("import subprocess\n"
            "subprocess.run(['git', '--version'], capture_output=True)\n"
            "subprocess.Popen(['git', '--version'], stdout=subprocess.DEVNULL).wait()\n")
    subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=60)
    starts = argv_lines(os.path.join(base, "calls.jsonl"), "git")
    check("git recorder (canary): the stub loaded, and subprocess.run and Popen each recorded one git start",
          os.path.exists(os.path.join(base, "loaded")) and len(starts) == 2, "starts=%r" % starts)


def case_settled_superseded_is_denied():
    text = store_text(store("full"), "roadmap", R44_PATH)
    check("fixture: the full store's r44 ref line names docs/decisions/%s.md" % SLUG,
          '"ref": "docs/decisions/%s.md' % SLUG in text, " ".join(text.split())[:160])
    runs = {}
    for phrase, sentence in SETTLING:
        runs[phrase] = past_run(settled_text(sentence, "`decision %s`" % SLUG), "full")
        reason = denied(runs[phrase])
        check("settling phrase %r + superseded decision: deny, rule past-ruling, naming %s and r44" % (phrase, SLUG),
              reason is not None and reason.startswith("past-ruling: ") and SLUG in reason and "r44" in reason,
              detail(runs[phrase]))
    r = runs["settled"]
    check("settled + superseded decision: the check runs before the judges (no model call)",
          not r.wording_calls and not r.model_calls, detail(r))
    check("settled + superseded decision: one past-ruling deny line in guard.log",
          r.log.count("\tdeny\tpast-ruling\t") == 1, detail(r) + " log=%r" % r.log)
    check("settled + superseded decision: the store is read by one git start", len(r.rulings_reads) == 1, detail(r))


def case_two_cited_ids_read_the_store_once():
    r = past_run(settled_text(SETTLING[0][1], "`docs/decisions/%s.md` and `decision %s`" % (KEPT, SLUG)), "full")
    reason = denied(r)
    check("settled + two cited ids, one superseded: deny naming %s and r44" % SLUG,
          reason is not None and SLUG in reason and "r44" in reason, detail(r))
    check("settled + two cited ids: one store read, not one per id", len(r.rulings_reads) == 1, detail(r))


def case_origin_only_store_is_read():
    check("fixture: the origin-only store has no local roadmap ref",
          not ref_resolves(store("origin"), "refs/heads/roadmap"))
    r = past_run(settled_text(SETTLING[0][1], "`decision %s`" % SLUG), "origin")
    reason = denied(r)
    check("store on origin/roadmap only: deny naming %s and r44" % SLUG,
          reason is not None and SLUG in reason and "r44" in reason, detail(r))


def case_override_lifts_a_past_ruling_refusal():
    r = past_run(settled_text(SETTLING[0][1], "`decision %s`" % SLUG), "full", override=(SID_A, TIMED))
    check("past-ruling override: the send lands (exit 0, no output)", r.code == 0 and r.out == "", detail(r))
    check("past-ruling override: one override line for past-ruling, no deny line",
          r.log.count("\toverride\tpast-ruling\t") == 1 and "\tdeny\tpast-ruling\t" not in r.log,
          detail(r) + " log=%r" % r.log)


def case_settled_citing_an_unsuperseded_decision_is_allowed():
    r = past_run(settled_text(SETTLING[1][1], "`docs/decisions/%s.md`" % KEPT), "full")
    check("settled + a decision nothing supersedes: allow (exit 0, no output, no stderr)",
          r.code == 0 and r.out == "" and r.err == "", detail(r))
    check("settled + a decision nothing supersedes: the send reaches the wording judge once",
          len(r.wording_calls) == 1, detail(r))
    check("settled + a decision nothing supersedes: the store is read by one git start",
          len(r.rulings_reads) == 1, detail(r))


def case_unsettled_citing_a_superseded_decision_is_allowed_with_no_git():
    r = past_run("Still checking whether `docs/decisions/%s.md` applies to the four actions." % SLUG, "full")
    check_allow_with_no_git(r, "not settling, cites the superseded decision")


def case_settled_citing_nothing_is_allowed_with_no_git():
    r = past_run("This is settled: no change for you, the step is done.", "full")
    check_allow_with_no_git(r, "settled, cites nothing")


def case_cite_forms_are_caught():
    for form in CITE_FORMS:
        cite = form % SLUG
        r = past_run(settled_text(SETTLING[2][1], cite), "full")
        reason = denied(r)
        check("cite form %s: deny naming %s and r44" % (cite, SLUG),
              reason is not None and SLUG in reason and "r44" in reason, detail(r))
    r = past_run("%s Don't reopen it.\n- decision %s. %s" % (SETTLING[0][1], SLUG, KEY_SENTENCE), "full")
    reason = denied(r)
    check("cite after a lone apostrophe and a newline: deny naming %s and r44" % SLUG,
          reason is not None and SLUG in reason and "r44" in reason, detail(r))


def case_absent_store_allows_silently():
    absent = store("absent")
    check("fixture: the absent repo has no roadmap ref, local or origin",
          not ref_resolves(absent, "roadmap") and not ref_resolves(absent, "origin/roadmap"))
    empty = store("empty")
    check("fixture: the empty store's roadmap ref holds no rulings",
          ref_resolves(empty, "roadmap")
          and git_out(empty, "ls-tree", "-r", "--name-only", "roadmap", "--", "roadmap/rulings",
                      check=False).stdout.strip() == "")
    for kind, label in (("absent", "no roadmap ref"), ("empty", "a roadmap ref with no rulings"),
                        ("plain", "no repo at all")):
        r = past_run(settled_text(SETTLING[0][1], "`decision %s`" % SLUG), kind)
        check("absent store (%s): allow silently (exit 0, no output, no stderr), the send reaches the judge" % label,
              r.code == 0 and r.out == "" and r.err == "" and len(r.wording_calls) == 1, detail(r))


def case_absent_store_with_a_stale_fetch_head_allows_silently():
    """An absent store (no roadmap ref, no origin) whose FETCH_HEAD is an old fetch of main alone. No roadmap fetch is
    on record and nothing is primed, so the store is absent: the read allows and says nothing on stderr."""
    repo = store("absent-stale-head")
    check("fixture: the absent-stale-head repo has no roadmap ref, local or origin",
          not ref_resolves(repo, "roadmap") and not ref_resolves(repo, "origin/roadmap"))
    head = fixture.fetch_head(repo)
    fixture.write_fetch_head(repo, "main")
    stamp = os.stat(head).st_mtime
    os.utime(head, (stamp - 120, stamp - 120))  # 120 s old: past roadmap_ref.MAX_AGE
    check("fixture: its FETCH_HEAD is an old fetch of main only",
          "branch 'main' of" in read_text(head) and "branch 'roadmap' of" not in read_text(head))
    r = past_run(settled_text(SETTLING[0][1], "`decision %s`" % SLUG), "absent-stale-head")
    check("absent store, stale FETCH_HEAD: the send reaches the wording judge once", len(r.wording_calls) == 1,
          detail(r))
    check("absent store, stale FETCH_HEAD: allow silently (exit 0, no output, no stderr)",
          r.code == 0 and r.out == "" and r.err == "", detail(r))


def case_a_store_aged_by_a_slow_runner_reads_fresh():
    """A slow runner can leave a store's FETCH_HEAD more than roadmap_ref.MAX_AGE old by the time a case reads it.
    The run primes its own store first, so a FETCH_HEAD aged 61 s still reads fresh: the read denies, starts no fetch
    and says nothing on stderr."""
    repo = store("full")
    head = fixture.fetch_head(repo)
    last = os.stat(head).st_mtime
    os.utime(head, (last - 61, last - 61))  # 61 s before its last write: stale by roadmap_ref.MAX_AGE
    try:
        r = past_run(settled_text(SETTLING[0][1], "`decision %s`" % SLUG), "full")
    finally:
        fixture.write_fetch_head(repo, "roadmap")  # the shared store is left fresh for the cases after this one
    reason = denied(r) or ""
    check("aged store: the read reaches the store (deny naming %s and r44)" % SLUG,
          reason.startswith("past-ruling: ") and SLUG in reason and "r44" in reason, detail(r))
    check("aged store: no fetch starts, the run primed the ref", not [a for a in r.git_starts if "fetch" in a],
          detail(r) + " git=%r" % r.git_starts)
    check("aged store: nothing on stderr", r.err == "", detail(r))


def case_broken_store_fails_open_with_one_stderr_line():
    broken = store("broken")
    check("fixture: the broken store's roadmap ref resolves, and r44's blob is gone",
          ref_resolves(broken, "roadmap")
          and git_out(broken, "cat-file", "-e", "roadmap:%s" % R44_PATH, check=False).returncode != 0)
    r = past_run(settled_text(SETTLING[3][1], "`decision %s`" % SLUG), "broken")
    check("broken store: allow (exit 0, no output, no deny)", r.code == 0 and r.out == "", detail(r))
    check("broken store: exactly one stderr line", len(r.err.strip().splitlines()) == 1, detail(r))
    check("broken store: the send reaches the wording judge once", len(r.wording_calls) == 1, detail(r))


def case_free_text_decision_is_not_superseded():
    check("fixture: %s is in r46's free text and in no ref line" % FREE,
          FREE in R46_TEXT and FREE not in R44_REF
          and FREE in store_text(store("full"), "roadmap", "roadmap/rulings/r46.json"))
    r = past_run(settled_text(SETTLING[1][1], "`docs/decisions/%s.md`" % FREE), "full")
    check("free-text-only decision: allow (exit 0, no output, no stderr)", r.code == 0 and r.out == "" and r.err == "",
          detail(r))
    check("free-text-only decision: the send reaches the wording judge once", len(r.wording_calls) == 1, detail(r))
    check("free-text-only decision: the store is read by one git start", len(r.rulings_reads) == 1, detail(r))


def case_prefix_slug_does_not_match():
    check("fixture: %s is a true prefix of %s" % (PREFIX, SLUG), SLUG.startswith(PREFIX + "-"))
    r = past_run(settled_text(SETTLING[0][1], "`decision %s` and `docs/decisions/%s.md`" % (PREFIX, PREFIX)), "full")
    check("prefix slug %s: allow (exit 0, no output, no stderr)" % PREFIX,
          r.code == 0 and r.out == "" and r.err == "", detail(r))
    check("prefix slug %s: the send reaches the wording judge once" % PREFIX, len(r.wording_calls) == 1, detail(r))
    check("prefix slug %s: the store is read by one git start" % PREFIX, len(r.rulings_reads) == 1, detail(r))


# ---- past-ruling check: a later slug in a list, the slug-first ref shape, more settling
# phrases, negations, a payload with no cwd, a stale local ref, and the refusal's remedy text.


def case_second_slug_in_a_list_is_caught():
    check("fixture: test-practices is in no ref line, so only the later slug is superseded",
          "test-practices" not in R44_REF + R47_REF)
    for text in ("Settled, per decisions test-practices and %s. %s" % (SLUG, KEY_SENTENCE),
                 "Settled. Decision: %s. %s" % (SLUG, KEY_SENTENCE),
                 "Settled. decisions/%s.md. %s" % (SLUG, KEY_SENTENCE)):
        r = past_run(text, "full")
        reason = denied(r) or ""
        check("second slug in a list (%r): deny naming %s and r44, not test-practices" % (text, SLUG),
              reason.startswith("past-ruling: ") and SLUG in reason and "r44" in reason
              and "test-practices" not in reason, detail(r))


def case_slug_first_ref_shape_supersedes():
    text = store_text(store("full"), "roadmap", "roadmap/rulings/r47.json")
    check("fixture: r47's ref line is slug first: \"ref\": \"test-strategy-reset: ...\"",
          '"ref": "test-strategy-reset: ' in text, " ".join(text.split())[:160])
    r = past_run("Settled, per decision test-strategy-reset: the old plan applies no longer.", "full")
    reason = denied(r) or ""
    check("slug-first ref shape (r47): deny naming test-strategy-reset and r47",
          reason.startswith("past-ruling: ") and "test-strategy-reset" in reason and "r47" in reason, detail(r))
    r = past_run("Settled, per decision %s. %s" % (SLUG, KEY_SENTENCE), "full")
    reason = denied(r) or ""
    check("the docs-path ref shape (r44) still denies, naming %s and r44" % SLUG,
          reason.startswith("past-ruling: ") and SLUG in reason and "r44" in reason, detail(r))


def case_already_decided_phrase_denies():
    r = past_run("Already decided: see decision %s. %s" % (SLUG, KEY_SENTENCE), "full")
    reason = denied(r) or ""
    check("'already decided' settles: deny naming %s and r44" % SLUG,
          reason.startswith("past-ruling: ") and SLUG in reason and "r44" in reason, detail(r))


def case_negated_settling_word_is_allowed():
    for text in ("Not settled yet: decision %s may still apply. %s" % (SLUG, KEY_SENTENCE),
                 "This isn't settled: decision %s may still apply. %s" % (SLUG, KEY_SENTENCE),
                 "It is unsettled: decision %s may still apply. %s" % (SLUG, KEY_SENTENCE)):
        r = past_run(text, "full")
        check("negated settling word (%r): allow (exit 0, no output, no stderr), no git start, judge reached" % text,
              r.code == 0 and r.out == "" and r.err == "" and not r.git_starts and len(r.wording_calls) == 1,
              detail(r) + " git=%r" % r.git_starts)


def case_no_cwd_allows_with_one_stderr_line():
    r = run_hook(hook_input(message=settled_text(SETTLING[0][1], "`decision %s`" % SLUG)),
                 reader_mode="idle", cwd=store("plain"))
    lines = r.err.strip().splitlines()
    check("no cwd in the payload: one stderr line saying the rulings store was not read",
          len(lines) == 1 and "rulings store" in lines[0] and "not read" in lines[0], detail(r))
    check("no cwd in the payload: allow (exit 0, no output), no git start",
          r.code == 0 and r.out == "" and not r.git_starts, detail(r))


def case_stale_local_ref_checks_origin():
    repo = store("stale-local")
    check("fixture: the local roadmap ref lacks r44, and origin/roadmap has it",
          store_text(repo, "roadmap", R44_PATH) == ""
          and '"ref": "docs/decisions/%s.md' % SLUG in store_text(repo, "origin/roadmap", R44_PATH))
    r = past_run(settled_text(SETTLING[0][1], "`decision %s`" % SLUG), "stale-local")
    reason = denied(r) or ""
    check("local roadmap stale, origin/roadmap has the ruling: deny naming %s and r44" % SLUG,
          reason.startswith("past-ruling: ") and SLUG in reason and "r44" in reason, detail(r))


def case_refusal_remedy_is_generic():
    r = past_run(settled_text(SETTLING[0][1], "`decision %s`" % SLUG), "full")
    reason = denied(r) or ""
    check("refusal names the decision and the ruling (r44)", SLUG in reason and "r44" in reason,
          detail(r) + " reason=%r" % reason)
    check("refusal has no 'reply without citing %s' sentence" % SLUG,
          ("reply without citing %s" % SLUG) not in reason.lower(), detail(r) + " reason=%r" % reason)
    check("refusal remedy is generic: re-check the later ruling, and an owner override lifts it",
          "re-check" in reason.lower() and "override" in reason.lower(), detail(r) + " reason=%r" % reason)


# ---- A quoted sentence refuses a reply only when the two share at least two key words. Key words:
# lowercase words of 5+ letters in the sentence, minus question_form.STOPWORDS and minus the words of the
# decision's own slug. A ref with no quoted sentence (a bare slug, or a docs path with nothing after) refuses
# any settling cite of that decision.


def case_real_sentence_refuses_a_reply_with_two_key_words():
    check("fixture: r44's ref quotes the real sentence",
          '"Pins stay current on demand: the session that runs the tool sees the drift and moves the pin. '
          'No bot and no schedule."' in R44_REF)
    r = past_run("Settled per decision %s: no bot, the session sees the drift and moves the pin" % SLUG, "full")
    reason = denied(r) or ""
    check("real r44 sentence, reply shares session, drift and moves: deny naming %s and r44" % SLUG,
          reason.startswith("past-ruling: ") and SLUG in reason and "r44" in reason, detail(r))


def case_reply_under_two_key_words_is_allowed():
    r = past_run("Settled per decision %s: the zizmor twin runs in place" % SLUG, "full")
    check("real r44 sentence, reply shares no key word: allow (exit 0, no output, no stderr), judge reached",
          r.code == 0 and r.out == "" and r.err == "" and len(r.wording_calls) == 1, detail(r))


def case_threshold_is_two_shared_key_words():
    r = past_run("Settled per decision %s: the session stays put." % SLUG, "full")
    check("exactly one shared key word (session): allow (exit 0, no output)",
          r.code == 0 and r.out == "" and denied(r) is None, detail(r))
    r = past_run("Settled per decision %s: the session sees the drift." % SLUG, "full")
    reason = denied(r) or ""
    check("exactly two shared key words (session, drift): deny naming %s and r44" % SLUG,
          reason.startswith("past-ruling: ") and SLUG in reason and "r44" in reason, detail(r))


def case_whole_decision_ref_refuses_any_settling_cite():
    full = store("full")
    check("fixture: r49 and r50 are whole-decision refs, with no quoted sentence",
          '"ref": "docs/decisions/bare-path-retired.md"' in store_text(full, "roadmap", "roadmap/rulings/r49.json")
          and '"ref": "bare-slug-retired"' in store_text(full, "roadmap", "roadmap/rulings/r50.json"))
    for slug, rid in (("bare-path-retired", "r49"), ("bare-slug-retired", "r50")):
        r = past_run("Settled, per decision %s." % slug, "full")
        reason = denied(r) or ""
        check("whole-decision ref (%s): deny with no key word shared, naming %s and %s" % (slug, slug, rid),
              reason.startswith("past-ruling: ") and slug in reason and rid in reason, detail(r))


def case_slug_words_do_not_count():
    check("fixture: r47's quoted sentence has strategy and reset, which are slug words",
          "strategy" in R47_REF and "reset" in R47_REF)
    r = past_run("Settled per decision %s: pins and sessions follow the action." % SLUG, "full")
    check("reply repeating only the slug's own words (pins, sessions, follow, action): allow, no deny",
          denied(r) is None and r.code == 0 and r.out == "", detail(r))
    r = past_run("Settled, per decision test-strategy-reset: the strategy reset and the test strategy.", "full")
    check("reply repeating slug words the quoted sentence also has (strategy, reset): allow, no deny",
          denied(r) is None and r.code == 0 and r.out == "", detail(r))


def case_sentence_matches_case_and_punctuation_blind():
    check("fixture: r48's quoted sentence is in other case and punctuation (Session, DRIFT)",
          "Session" in R48_REF and "DRIFT" in R48_REF)
    r = past_run("Settled per decision punct-case-decision: the session sees the drift.", "full")
    reason = denied(r) or ""
    check("stored sentence in other case and punctuation: two key words still deny, naming punct-case-decision and r48",
          reason.startswith("past-ruling: ") and "punct-case-decision" in reason and "r48" in reason, detail(r))


# ---- Cite parsing: every slug in a cite list counts, whatever separates them, and a code-style
# ref that names a decision mid-text (no usable sentence after the cite) refuses no reply per decision.


def case_every_slug_in_a_cite_list_is_kept():
    text = store_text(store("full"), "roadmap", "roadmap/rulings/r51.json")
    check("fixture: r51 retires each last slug whole, and names no first slug",
          all('"ref": "%s"' % s in text for s in LAST_SLUGS)
          and not any(s in text for s in ("test-practices", "question-form", "semi-first-decision",
                                          "paren-first-decision", "slash-first-decision")))
    for cited, last in (
        ("Settled per decisions test-practices, question-form, and list-oxford-last.", "list-oxford-last"),
        ("Settled: decisions semi-first-decision; semi-last-decision", "semi-last-decision"),
        ("Settled (decisions paren-first-decision, paren-last-decision)", "paren-last-decision"),
        ("Settled, per decisions slash-first-decision / slash-last-decision.", "slash-last-decision"),
    ):
        r = past_run(cited, "full")
        reason = denied(r) or ""
        check("cite list (%r): deny naming %s and r51" % (cited, last),
              reason.startswith("past-ruling: ") and last in reason and "r51" in reason, detail(r))


def case_mid_text_code_ref_does_not_refuse_per_decision():
    text = store_text(store("full"), "roadmap", "roadmap/rulings/r52.json")
    check("fixture: r52's only ref for guard-remedy-not-to-owner is a code-style line naming it mid-text",
          "lint/report_guard.py:36" in text and "per decision guard-remedy-not-to-owner." in text
          and '"ref": "guard-remedy-not-to-owner"' not in text)
    r = past_run("Settled, per decision guard-remedy-not-to-owner: names its guard.", "full")
    check("mid-text code ref, no usable sentence after the cite: allow (exit 0, no output, no stderr), judge reached",
          r.code == 0 and r.out == "" and r.err == "" and len(r.wording_calls) == 1, detail(r))
    r = past_run("Settled, per decision bare-slug-retired.", "full")
    reason = denied(r) or ""
    check("bare {kind: decision, ref: <slug>} still denies: deny naming bare-slug-retired and r50",
          reason.startswith("past-ruling: ") and "bare-slug-retired" in reason and "r50" in reason, detail(r))


def case_hook_runs():
    for case in (case_model_row_names_the_call,
                 case_wording_call_carries_its_model_and_no_effort,
                 case_wording_judge_denies_any_receiver,
                 case_override_lifts_a_deny,
                 case_deny_ends_with_the_override_line,
                 case_idle_and_waiting_allow_with_no_model_call,
                 case_busy_flag_rows,
                 case_busy_allows_when_the_model_does_not_flag,
                 case_unseen_receivers_allow_with_no_model_call,
                 case_advisor_named_receiver_is_a_peer,
                 case_malformed_input_fails_open_with_no_deny,
                 case_model_failures_fail_open_with_no_deny,
                 case_reader_timeout_allows_with_one_plain_line,
                 case_reader_that_holds_the_pipe_returns_before_the_child_ends,
                 case_git_popen_is_recorded,
                 case_settled_superseded_is_denied,
                 case_two_cited_ids_read_the_store_once,
                 case_origin_only_store_is_read,
                 case_override_lifts_a_past_ruling_refusal,
                 case_settled_citing_an_unsuperseded_decision_is_allowed,
                 case_unsettled_citing_a_superseded_decision_is_allowed_with_no_git,
                 case_settled_citing_nothing_is_allowed_with_no_git,
                 case_cite_forms_are_caught,
                 case_absent_store_allows_silently,
                 case_absent_store_with_a_stale_fetch_head_allows_silently,
                 case_a_store_aged_by_a_slow_runner_reads_fresh,
                 case_broken_store_fails_open_with_one_stderr_line,
                 case_free_text_decision_is_not_superseded,
                 case_prefix_slug_does_not_match,
                 case_second_slug_in_a_list_is_caught,
                 case_slug_first_ref_shape_supersedes,
                 case_already_decided_phrase_denies,
                 case_negated_settling_word_is_allowed,
                 case_no_cwd_allows_with_one_stderr_line,
                 case_stale_local_ref_checks_origin,
                 case_refusal_remedy_is_generic,
                 case_real_sentence_refuses_a_reply_with_two_key_words,
                 case_reply_under_two_key_words_is_allowed,
                 case_threshold_is_two_shared_key_words,
                 case_whole_decision_ref_refuses_any_settling_cite,
                 case_slug_words_do_not_count,
                 case_sentence_matches_case_and_punctuation_blind,
                 case_every_slug_in_a_cite_list_is_kept,
                 case_mid_text_code_ref_does_not_refuse_per_decision):
        try:
            case()
        except subprocess.TimeoutExpired as exc:  # run_hook's cap: one FAIL line naming the case, no traceback
            check(case.__name__, False, "the hook run hit its %s s cap (a hang guard)" % exc.timeout)
        except FixtureError as exc:  # a fixture repo did not build: one FAIL line, and the other cases still run
            check("fixture: %s" % case.__name__, False, " ".join(str(exc).split()))


# What one SendMessage costs (decision sendmessage-state). The hook runs as a child under cost_probe.run_hook, which
# stands in the model call and counts each child start. A malformed call starts nothing. The reader child is killed
# with its process group at READER_TIMEOUT, and nothing in that group outlives the hook.

POSIX_ONLY = unittest.skipIf(os.name == "nt", "the fake reader is a POSIX shell script and a process group")


class CostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = os.path.join(ROOT, "cost")  # a subfolder of this run's ROOT: the run removes ROOT, not this
        os.makedirs(cls.base, exist_ok=True)
        spec = importlib.util.spec_from_file_location("sendmessage_state_cost", HOOK)
        cls.sm = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.sm)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.base, ignore_errors=True)

    def folder(self):
        return tempfile.mkdtemp(dir=self.base)

    @staticmethod
    def fake_node(folder, state):
        """A `node` on PATH that prints `state`: the reader's answer, with no board read."""
        bin_dir = os.path.join(folder, "bin")
        os.makedirs(bin_dir)
        path = os.path.join(bin_dir, "node")
        with open(path, "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\necho %s\n" % state)
        os.chmod(path, 0o755)
        return bin_dir

    def hook(self, stdin, state=None, folder=None):
        folder = folder or self.folder()
        env = {}
        if state is not None:
            env["PATH"] = self.fake_node(folder, state) + os.pathsep + os.environ.get("PATH", "")
        return cost_probe.run_hook(HOOK, stdin, folder, [[{"ok": True}, None]], env=env)

    @staticmethod
    def send(to, message):
        return json.dumps({"session_id": "cost-send", "tool_name": "SendMessage",
                           "tool_input": {"to": to, "message": message}})

    def test_a_malformed_call_starts_nothing(self):
        run = self.hook("not json")
        self.assertEqual((run["code"], run["models"], run["children"], run["files"], run["out"]), (0, [], [], [], ""))

    @POSIX_ONLY
    def test_a_plain_message_to_a_busy_receiver_costs_two_model_calls_and_one_reader_child(self):
        run = self.hook(self.send("peer", "Done"), state="busy")
        self.assertEqual(len(run["models"]), 2, "the wording call and the busy call; got %r" % run["models"])
        self.assertEqual(sorted(m["timeout"] for m in run["models"]),
                         sorted([self.sm.WORDING_TIMEOUT, self.sm.MODEL_TIMEOUT]))
        self.assertEqual(cost_probe.names(run["children"]), ["node"],
                         "one reader child and no other; got %r" % run["children"])
        self.assertEqual(run["files"], [], "the reader writes no file under the config dir")

    @POSIX_ONLY
    def test_a_plain_message_to_an_idle_receiver_costs_one_model_call_and_one_reader_child(self):
        run = self.hook(self.send("peer", "Done"), state="idle")
        self.assertEqual(len(run["models"]), 1, "only the wording call; got %r" % run["models"])
        self.assertEqual(cost_probe.names(run["children"]), ["node"])

    def test_a_structured_message_costs_one_wording_call_and_no_reader(self):
        run = self.hook(json.dumps({"session_id": "cost-send", "tool_name": "SendMessage",
                                    "tool_input": {"to": ["peer"], "message": {"text": "Done"}}}))
        self.assertEqual(len(run["models"]), 1, "the wording call only; got %r" % run["models"])
        self.assertEqual(run["children"], [], "a structured message reads no board")

    @POSIX_ONLY
    def test_a_reader_that_hangs_is_killed_with_its_group_at_the_timeout(self):
        folder = self.folder()
        marker = os.path.join(folder, "spawned")
        reader = os.path.join(folder, "reader.py")
        with open(reader, "w", encoding="utf-8") as f:
            f.write("import subprocess, sys, time\n"
                    "subprocess.Popen([sys.executable, '-c', 'import time\\nwhile True: time.sleep(1)'])\n"
                    "open(%r, 'w').close()\n"
                    "time.sleep(600)\n" % marker)
        with mock.patch.object(self.sm, "READER_TIMEOUT", 2), \
                mock.patch.object(self.sm, "find_reader", lambda: reader), \
                mock.patch.object(self.sm, "shutil", types.SimpleNamespace(which=lambda name: sys.executable)):
            with cost_probe.children() as log:
                state = self.sm.receiver_state("peer")
        if log.procs:  # a failing case must not leave the reader running
            self.addCleanup(cost_probe.stop_group, log.procs[0])
        self.assertEqual(state, "unseen", "a reader that times out reads as unseen")
        self.assertEqual(len(log.argvs), 1, "the hook starts one reader child; got %r" % log.argvs)
        self.assertTrue(os.path.exists(marker), "the reader started its own child before the timeout, so the case is not vacuous")
        leader = log.procs[0].pid
        deadline = time.monotonic() + 5  # a bounded wait for the kill to land; a kill that never lands fails
        left = cost_probe.group_members(leader)
        while left and time.monotonic() < deadline:
            time.sleep(0.05)
            left = cost_probe.group_members(leader)
        self.assertEqual(left, [], "nothing in the reader's group outlives the hook; still alive: %r" % left)

    @POSIX_ONLY
    def test_group_members_lists_the_live_group_when_proc_is_missing(self):
        # macOS has no /proc. With /proc missing from the helper's view, group_members must list the live members
        # of the group it is given, must not raise, and its own read must start no child that children() counts.
        child = subprocess.Popen([sys.executable, "-c", "import time\nwhile True: time.sleep(1)"], start_new_session=True)
        self.addCleanup(cost_probe.stop_group, child)
        real_listdir = os.listdir

        def listdir_without_proc(path="."):
            if path == "/proc":
                raise FileNotFoundError("No such file or directory: '/proc'")
            return real_listdir(path)

        argv = [sys.executable, "-c", "pass"]
        with mock.patch.object(cost_probe.os, "listdir", listdir_without_proc):
            self.assertRaises(FileNotFoundError, os.listdir, "/proc")  # the scope: /proc is missing in this case
            with cost_probe.children() as log:
                try:
                    members = cost_probe.group_members(child.pid)
                except OSError as err:
                    self.fail("group_members raised %s with /proc missing" % type(err).__name__)
                subprocess.run(argv, check=True)  # a known start, so the counter is live
        self.assertEqual(log.argvs, [argv], "group_members starts no child that children() counts; got %r" % log.argvs)
        self.assertEqual(members, [child.pid], "the one live member of the group it was given; got %r" % members)


if __name__ == "__main__":
    write_launchers()
    case_find_reader()
    case_hook_runs()
    if not cost_probe.run_class(CostTests):
        FAILED.append("CostTests")
    if FAILED:
        print("%d check(s) failed" % len(FAILED))
    elif SKIPPED:
        print("SKIP: %d check(s) not run, none failed" % len(SKIPPED))  # never "all checks passed"
    else:
        print("all checks passed")
    sys.exit(1 if FAILED else 0)
