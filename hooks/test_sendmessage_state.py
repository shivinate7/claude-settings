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
import subprocess
import sys
import tempfile
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.environ.get("SENDMESSAGE_STATE_UNDER_TEST") or os.path.join(HERE, "sendmessage_state.py")
ROOT = tempfile.mkdtemp(prefix="sendmessage_state_cases_")
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
        // it. "&&" gates done on the hold finishing: a kill of the hold must not reach it. Relative
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
             override=None, base=None):
    RUNS[0] += 1
    base = os.path.join(ROOT, "run-%03d" % RUNS[0])
    cfg = os.path.join(base, "config")
    os.makedirs(cfg)
    if override is not None:  # (session id, override file body): the override the owner's prompt would write
        write_pass(cfg, *override)
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
                          encoding="utf-8", errors="replace", env=env, timeout=cap)
    return Run(proc, base, time.monotonic() - started)


def hook_input(to=PEER, message="Status: the step is done, no change for you.", session=SID_A, agent=None):
    payload = {"session_id": session, "tool_name": "SendMessage", "tool_input": {"to": to, "message": message}}
    if agent:
        payload["agent_id"] = agent
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
    record = os.path.join(os.path.dirname(HERE), "docs", "decisions", "subagent-model-cap.md")
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
        ("timed override, a subagent's call", (SID_A, TIMED), hook_input(agent="a1"), both, True),
        ("one-act override, wording FLAG", (SID_A, ONCE), hook_input(), {"reader_mode": "idle", "wording": FLAG}, True),
        ("one-act override, busy FLAG", (SID_A, ONCE), hook_input(), {"rows": [row(SID_A, PEER, "busy")], "answer": FLAG}, True),
        ("one-act override, a subagent's call", (SID_A, ONCE), hook_input(agent="a1"), both, False),
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


def case_hook_runs():
    for case in (case_model_row_names_the_call,
                 case_wording_call_carries_its_model_and_no_effort,
                 case_wording_judge_denies_any_receiver,
                 case_override_lifts_a_deny,
                 case_idle_and_waiting_allow_with_no_model_call,
                 case_busy_flag_rows,
                 case_busy_allows_when_the_model_does_not_flag,
                 case_unseen_receivers_allow_with_no_model_call,
                 case_advisor_named_receiver_is_a_peer,
                 case_malformed_input_fails_open_with_no_deny,
                 case_model_failures_fail_open_with_no_deny,
                 case_reader_timeout_allows_with_one_plain_line,
                 case_reader_that_holds_the_pipe_returns_before_the_child_ends):
        try:
            case()
        except subprocess.TimeoutExpired as exc:  # run_hook's cap: one FAIL line naming the case, no traceback
            check(case.__name__, False, "the hook run hit its %s s cap (a hang guard)" % exc.timeout)


if __name__ == "__main__":
    write_launchers()
    case_find_reader()
    case_hook_runs()
    if FAILED:
        print("%d check(s) failed" % len(FAILED))
    elif SKIPPED:
        print("SKIP: %d check(s) not run, none failed" % len(SKIPPED))  # never "all checks passed"
    else:
        print("all checks passed")
    sys.exit(1 if FAILED else 0)
