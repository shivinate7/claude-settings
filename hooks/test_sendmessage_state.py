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
- `claude agents --json`. The reader is a node child of the hook, so it meets a `claude` launcher
  on PATH: claude.cmd on Windows, a sh script elsewhere. The launcher runs fake_claude.py, which
  prints the canned rows and records the call.
Every claude call is recorded, so "no model call" is read from the record, not assumed.
CLAUDE_CONFIG_DIR is a fresh temp folder: no real pointer file or token is read.

Canary: every hook run must leave a `loaded` file (the sitecustomize ran) and, when the hook
reaches the board, exactly one agents call. Without them, a "no model call" pass proves nothing.

Mutation: SENDMESSAGE_STATE_UNDER_TEST names another copy of the hook to run instead. Its
find_reader looks for mods/ beside that copy, so a copy needs a mods/ folder beside its hooks/.
"""
import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import types

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.environ.get("SENDMESSAGE_STATE_UNDER_TEST") or os.path.join(HERE, "sendmessage_state.py")
ROOT = tempfile.mkdtemp(prefix="sendmessage_state_cases_")
STUB_DIR = os.path.join(ROOT, "stub")
FAILED = []
RUNS = [0]
PEER, OTHER = "peer", "other"
SID_A, SID_B = "ses00001", "ses00002"
ALLOW = '{"ok": true}'
FLAG = '{"ok": false, "reason": "parallelism-no-mid-task-talk: send only what changes the work."}'

STUB_SITE = r'''
import json, os, subprocess
_real_run = subprocess.run


def _fake_run(argv, **kwargs):
    if not (isinstance(argv, (list, tuple)) and argv
            and os.path.basename(str(argv[0])).lower() in ("claude", "claude.exe", "claude.cmd")):
        return _real_run(argv, **kwargs)
    with open(os.environ["SM_RECORD"], "a", encoding="utf-8") as f:
        f.write(json.dumps({"argv": list(argv)}) + "\n")
    if os.environ.get("SM_MODEL_FAIL"):
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="stub model failure")
    return subprocess.CompletedProcess(argv, 0, stdout=json.dumps({"result": os.environ["SM_ANSWER"]}), stderr="")


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


def check(name, ok, detail=""):
    if ok:
        print("ok   " + name)
    else:
        FAILED.append(name)
        print("FAIL " + name + (" :: " + detail if detail else ""))


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


class Run:
    def __init__(self, proc, base):
        self.code = proc.returncode
        self.out = proc.stdout or ""
        self.err = proc.stderr or ""
        self.loaded = os.path.exists(os.path.join(base, "loaded"))
        self.calls = []
        record = os.path.join(base, "calls.jsonl")
        if os.path.exists(record):
            with open(record, encoding="utf-8") as f:
                self.calls = [json.loads(line)["argv"] for line in f if line.strip()]
        self.model_calls = [a for a in self.calls if "-p" in a]
        self.agents_calls = [a for a in self.calls if a[:2] == ["agents", "--json"]]

    def deny(self):
        """The hookSpecificOutput of a deny, or None when stdout is empty."""
        if not self.out.strip():
            return None
        return json.loads(self.out)["hookSpecificOutput"]

    def reached_board(self):
        return self.loaded and len(self.agents_calls) == 1


def detail(r):
    return "code=%s out=%r err=%r model=%d agents=%d loaded=%s" % (
        r.code, r.out[:160], r.err[-200:], len(r.model_calls), len(r.agents_calls), r.loaded)


def run_hook(stdin_text, rows=None, answer=ALLOW, model_fail=False, agents_fail=False):
    RUNS[0] += 1
    base = os.path.join(ROOT, "run-%03d" % RUNS[0])
    cfg = os.path.join(base, "config")
    os.makedirs(cfg)
    agents = os.path.join(base, "agents.json")
    with open(agents, "w", encoding="utf-8") as f:
        f.write(json.dumps(rows if rows is not None else []))
    env = {k: v for k, v in os.environ.items() if not k.startswith("SM_")}
    env.update({
        "CLAUDE_CONFIG_DIR": cfg,
        "PATH": STUB_DIR + os.pathsep + os.environ.get("PATH", ""),
        "PYTHONPATH": STUB_DIR,
        "SM_LOADED_DIR": base,
        "SM_RECORD": os.path.join(base, "calls.jsonl"),
        "SM_AGENTS_FILE": agents,
        "SM_ANSWER": answer,
    })
    if model_fail:
        env["SM_MODEL_FAIL"] = "1"
    if agents_fail:
        env["SM_AGENTS_FAIL"] = "1"
    proc = subprocess.run([sys.executable, HOOK], input=stdin_text, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, timeout=120)
    return Run(proc, base)


def hook_input(to=PEER, message="Status: the step is done, no change for you."):
    return json.dumps({"tool_name": "SendMessage", "tool_input": {"to": to, "message": message}})


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
    for status in ("idle", "waiting"):
        r = run_hook(hook_input(), rows=[row(SID_A, PEER, status)])
        check("%s receiver: allow, no model call, no output" % status,
              r.code == 0 and r.out == "" and not r.model_calls and r.reached_board(), detail(r))


def case_busy_blocks_when_the_model_flags():
    r = run_hook(hook_input(), rows=[row(SID_A, PEER, "busy")], answer=FLAG)
    d = r.deny()
    check("busy + model FLAG: one deny carrying the model's reason",
          r.code == 0 and d is not None and d.get("permissionDecision") == "deny"
          and "parallelism-no-mid-task-talk" in d.get("permissionDecisionReason", "")
          and len(r.model_calls) == 1 and r.reached_board(), detail(r))


def case_busy_allows_when_the_model_does_not_flag():
    r = run_hook(hook_input(), rows=[row(SID_A, PEER, "busy")], answer=ALLOW)
    check("busy + model ok: allow, one model call, no deny",
          r.code == 0 and r.out == "" and len(r.model_calls) == 1 and r.reached_board(), detail(r))


def case_busy_flag_with_blank_reason_gets_the_default_reason():
    r = run_hook(hook_input(), rows=[row(SID_A, PEER, "busy")],
                 answer='{"ok": false, "reason": "   "}')
    d = r.deny()
    check("busy + FLAG with a blank reason: deny with the default reason",
          r.code == 0 and d is not None and d.get("permissionDecisionReason", "").startswith(
              "parallelism-no-mid-task-talk"), detail(r))


def case_unseen_receivers_allow_with_no_model_call():
    cases = [
        ("no board row for the name", [row(SID_B, OTHER, "busy")]),
        ("a duplicate name", [row(SID_A, PEER, "busy"), row(SID_B, PEER, "idle")]),
        ("an unknown status", [row(SID_A, PEER, "running")]),
    ]
    for label, rows in cases:
        r = run_hook(hook_input(), rows=rows)
        check("unseen (%s): allow, no model call" % label,
              r.code == 0 and r.out == "" and not r.model_calls and r.reached_board(), detail(r))
    r = run_hook(hook_input(), rows=[row(SID_A, PEER, "busy")], agents_fail=True)
    check("unseen (agents list fails): allow, no model call",
          r.code == 0 and r.out == "" and not r.model_calls and r.loaded, detail(r))


def case_malformed_input_fails_open_with_no_deny():
    for label, text in (
        ("stdin is not JSON", "not json"),
        ("tool_input is not an object", '{"tool_input": "oops"}'),
        ("to is not a string", '{"tool_input": {"to": 5, "message": "x"}}'),
        ("to is blank", '{"tool_input": {"to": "  ", "message": "x"}}'),
    ):
        r = run_hook(text, rows=[row(SID_A, PEER, "busy")], answer=FLAG)
        check("malformed input (%s): exit 0, no deny, no model call" % label,
              r.code == 0 and r.out == "" and not r.model_calls, detail(r))


def case_model_failures_fail_open_with_no_deny():
    r = run_hook(hook_input(), rows=[row(SID_A, PEER, "busy")], answer=FLAG, model_fail=True)
    check("busy + model exits non-zero: exit 0, no deny, failed-open line",
          r.code == 0 and r.out == "" and "failed open" in r.err and len(r.model_calls) == 1, detail(r))
    r = run_hook(hook_input(), rows=[row(SID_A, PEER, "busy")], answer='{"verdict": "FLAG"}')
    check("busy + off-shape model answer: exit 0, no deny, failed-open line",
          r.code == 0 and r.out == "" and "failed open" in r.err, detail(r))


def case_model_row_names_the_call():
    # The model-per-role table has one row for this hook's model call; the row's model and effort
    # must equal what the call uses (decision_watch.MODEL and its --effort argument).
    record = os.path.join(os.path.dirname(HERE), "decisions", "subagent-model-cap.md")
    try:
        with open(record, encoding="utf-8") as f:
            rows = [line for line in f if line.startswith("|") and "hooks/sendmessage_state.py" in line]
    except OSError as exc:
        rows = []
        check("model table: record readable", False, str(exc))
    check("model table: exactly one row for the SendMessage state judge", len(rows) == 1, repr(rows)[:200])
    if len(rows) == 1:
        cells = [c.strip() for c in rows[0].strip().strip("|").split("|")]
        spec = importlib.util.spec_from_file_location("decision_watch", os.path.join(HERE, "decision_watch.py"))
        dw = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dw)
        with open(os.path.join(HERE, "decision_watch.py"), encoding="utf-8") as f:
            effort_arg = '"--effort", "xhigh"' in f.read()
        check("model table: row model is the call's model (haiku)",
              "haiku" in cells[1] and dw.MODEL == "haiku", repr(cells[1:2]))
        check("model table: row effort is the call's effort (xhigh)",
              cells[2] == "xhigh" and effort_arg, repr(cells[2:3]))


def case_hook_runs():
    case_model_row_names_the_call()
    case_idle_and_waiting_allow_with_no_model_call()
    case_busy_blocks_when_the_model_flags()
    case_busy_allows_when_the_model_does_not_flag()
    case_busy_flag_with_blank_reason_gets_the_default_reason()
    case_unseen_receivers_allow_with_no_model_call()
    case_malformed_input_fails_open_with_no_deny()
    case_model_failures_fail_open_with_no_deny()


if __name__ == "__main__":
    write_launchers()
    case_find_reader()
    case_hook_runs()
    print("%d check(s) failed" % len(FAILED) if FAILED else "all checks passed")
    sys.exit(1 if FAILED else 0)
