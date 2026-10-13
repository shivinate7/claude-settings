#!/usr/bin/env python3
"""Cases for hooks/reply_judge.py, the Stop command hook that judges the final reply.
Standard library only, and no test runner.

Run it from the repository root:

    python hooks/test_reply_judge.py

Each case runs the real script the way the harness does: `[sys.executable, hooks/reply_judge.py]`
with the Stop JSON on stdin, and its exit code, stdout and stderr read back. The model is
stubbed one level down, at `subprocess.run` inside that child process. A generated
`sitecustomize.py`, put first on PYTHONPATH, wraps `subprocess.run` and answers only calls
whose program is `claude`. Every other call goes to the real `subprocess.run`. So the real
`invoke_model` parses each canned answer, and a hook that never calls the model is seen as
a hook that never spawned `claude`.

The stub writes a canary file when it loads. Every run checks the canary, so a stub that did
not load cannot make a "never called" check pass for no reason.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
MODULE_PATH = os.environ.get("REPLY_JUDGE_UNDER_TEST") or os.path.join(HERE, "reply_judge.py")
ROOT = tempfile.mkdtemp(prefix="reply_judge_cases_")
STUB_DIR = os.path.join(ROOT, "stub")
FAILED = []
RED_CASES = []
RUNS = [0]

MARK = "Stage two is live, MARK-7f3a"  # one line, no quotes, no rule id, no background word
BLOCK_REASON = "output-never-paste-passing-output: paste the verdict, not the run's output."
RULE_IDS = ("output-start-with-point", "style-cut-narration", "output-never-paste-passing-output")
BACKGROUND_WORDS = ("background", "unfinished", "never")

STUB_SOURCE = '''
import json
import os
import subprocess

_real_run = subprocess.run


def _is_claude(argv):
    if not isinstance(argv, (list, tuple)) or not argv:
        return False
    return os.path.basename(str(argv[0])).lower() in ("claude", "claude.exe", "claude.cmd")


def _fake_run(argv, **kwargs):
    if not _is_claude(argv):
        return _real_run(argv, **kwargs)
    env = kwargs.get("env") or {}
    cfg = env.get("CLAUDE_CONFIG_DIR")
    cwd = kwargs.get("cwd")
    rec = {
        "argv": list(argv),
        "cwd": cwd,
        "cwd_entries": sorted(os.listdir(cwd)) if cwd and os.path.isdir(cwd) else None,
        "config_dir": cfg,
        "config_entries": sorted(os.listdir(cfg)) if cfg and os.path.isdir(cfg) else None,
    }
    with open(os.environ["RJ_RECORD"], "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\\n")
    scenario = os.environ.get("RJ_SCENARIO", "")
    if scenario == "timeout":
        raise subprocess.TimeoutExpired(argv, kwargs.get("timeout"))
    if scenario == "error":
        return subprocess.CompletedProcess(argv, 1, "", "first stderr line\\nsecond stderr line\\n")
    if scenario == "nonjson_envelope":
        return subprocess.CompletedProcess(argv, 0, "this is not json", "")
    if scenario == "nojson_answer":
        return subprocess.CompletedProcess(argv, 0, json.dumps({"result": "Looks fine to me."}), "")
    return subprocess.CompletedProcess(argv, 0, json.dumps({"result": os.environ.get("RJ_ANSWER", "")}), "")


with open(os.environ["RJ_LOADED"], "w", encoding="utf-8") as f:
    f.write("loaded")
subprocess.run = _fake_run
'''


def check(name, condition, detail=""):
    if condition:
        print("PASS: %s" % name)
    else:
        FAILED.append(name)
        print("FAIL: %s  %s" % (name, str(detail)[:600]))


def _write_stub():
    os.makedirs(STUB_DIR, exist_ok=True)
    with open(os.path.join(STUB_DIR, "sitecustomize.py"), "w", encoding="utf-8") as f:
        f.write(STUB_SOURCE)


class Run:
    """One run of the hook process, read back the way the harness reads it."""

    def __init__(self, proc, base):
        self.code = proc.returncode
        self.out = proc.stdout or ""
        self.err = proc.stderr or ""
        self.config = os.path.join(base, "config")
        self.loaded = os.path.exists(os.path.join(base, "loaded"))
        self.calls = []
        record = os.path.join(base, "calls.jsonl")
        if os.path.exists(record):
            with open(record, encoding="utf-8") as f:
                self.calls = [json.loads(line) for line in f if line.strip()]

    def prompt(self):
        argv = self.calls[0]["argv"] if self.calls else []
        return argv[argv.index("-p") + 1] if "-p" in argv else ""


def run_hook(text, scenario="ok", answer="", stop_active=False):
    RUNS[0] += 1
    base = os.path.join(ROOT, "run-%03d" % RUNS[0])
    config = os.path.join(base, "config")
    os.makedirs(config)  # empty: no settings, no hooks, no credential, no token
    env = dict(os.environ)
    for name in ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY"):
        env.pop(name, None)
    env.update(
        CLAUDE_CONFIG_DIR=config,
        PYTHONPATH=STUB_DIR,
        RJ_SCENARIO=scenario,
        RJ_ANSWER=answer,
        RJ_RECORD=os.path.join(base, "calls.jsonl"),
        RJ_LOADED=os.path.join(base, "loaded"),
    )
    payload = {
        "session_id": "reply-judge-cases",
        "hook_event_name": "Stop",
        "cwd": base,
        "stop_hook_active": stop_active,
        "last_assistant_message": text,
    }
    proc = subprocess.run(
        [sys.executable, MODULE_PATH],
        input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=60, env=env, cwd=base,
    )
    run = Run(proc, base)
    check("canary: stub loaded in the hook process (scenario %s)" % scenario, run.loaded, run.err)
    return run


# --------------------------------------------------------------------------- case 1
# stop_hook_active true: this Stop firing is already a rewrite. Exit 0, print nothing, and never
# spawn claude, even when the stubbed answer would block.

def case_stop_hook_active_never_calls_model():
    run = run_hook(MARK, answer=json.dumps({"ok": False, "reason": BLOCK_REASON}), stop_active=True)
    check("stop_hook_active: exit 0", run.code == 0, run.code)
    check("stop_hook_active: nothing on stdout", run.out.strip() == "", run.out)
    check("stop_hook_active: claude never spawned", run.calls == [], run.calls)


# --------------------------------------------------------------------------- case 2
# A model answer of {"ok": true}: exit 0, nothing printed. Empty stderr separates an accepted
# answer from a fail-open path, which prints one stderr line.

def case_model_ok_is_silent():
    run = run_hook(MARK, answer=json.dumps({"ok": True}))
    check("ok: exit 0", run.code == 0, run.code)
    check("ok: nothing on stdout", run.out.strip() == "", run.out)
    check("ok: nothing on stderr, so the answer was accepted and not failed open",
          run.err.strip() == "", run.err)
    check("ok: exactly one claude call", len(run.calls) == 1, len(run.calls))


# Owner ruling: run model haiku at effort xhigh.

def case_model_is_haiku_at_xhigh():
    run = run_hook(MARK, answer=json.dumps({"ok": True}))
    argv = run.calls[0]["argv"] if run.calls else []
    pairs = list(zip(argv, argv[1:]))
    check("model: --model haiku in argv", ("--model", "haiku") in pairs, argv)
    check("model: --effort xhigh in argv", ("--effort", "xhigh") in pairs, argv)


# --------------------------------------------------------------------------- case 3
# A model answer of {"ok": false, "reason": R}: stdout is exactly the block decision with R.

def case_model_block_emits_block_json():
    run = run_hook(MARK, answer=json.dumps({"ok": False, "reason": BLOCK_REASON}))
    check("block: exit 0", run.code == 0, run.code)
    try:
        got = json.loads(run.out)
    except ValueError:
        got = None
    check("block: stdout is exactly the block decision with the model's reason",
          got == {"decision": "block", "reason": BLOCK_REASON}, run.out)


# --------------------------------------------------------------------------- case 4
# Model error, timeout, or non-JSON: fail open. Exit 0, nothing on stdout, one stderr line.
# The non-zero exit fake writes two stderr lines, so a hook that echoes raw stderr fails here.

FAIL_OPEN = (
    ("non-zero exit", "error"),
    ("timeout", "timeout"),
    ("non-JSON envelope", "nonjson_envelope"),
    ("answer with no JSON", "nojson_answer"),
)


def case_model_failure_fails_open():
    for label, scenario in FAIL_OPEN:
        run = run_hook(MARK, scenario=scenario)
        check("fail open, %s: exit 0" % label, run.code == 0, run.code)
        check("fail open, %s: nothing on stdout" % label, run.out.strip() == "", run.out)
        lines = [line for line in run.err.splitlines() if line.strip()]
        check("fail open, %s: exactly one stderr line" % label, len(lines) == 1, run.err)
        check("fail open, %s: claude was called once" % label, len(run.calls) == 1, len(run.calls))


# --------------------------------------------------------------------------- case 4b
# A timeout raises TimeoutExpired, and its message repeats the argv, which holds the prompt and
# the reply. stderr must carry neither, and must say the call timed out, not failed to start.
# The reply check uses a sentinel, which survives repr() escaping. The prompt check tests both
# the raw and the repr-escaped form of the prompt.

TIMEOUT_SENTINEL = "SENTINEL-timeout-5d0e"


def case_timeout_leaks_no_reply_text():
    run = run_hook("Reply body %s, end." % TIMEOUT_SENTINEL, scenario="timeout")
    prompt = run.prompt()
    check("timeout: claude was called, so the leak checks mean something", bool(prompt), run.calls)
    check("timeout: stderr holds no reply text", TIMEOUT_SENTINEL not in run.err, run.err)
    check("timeout: stderr holds no prompt, raw or repr-escaped",
          prompt != "" and prompt not in run.err and repr(prompt)[1:-1] not in run.err, run.err)
    check("timeout: stderr says timed out", "timed out" in run.err, run.err)
    check("timeout: stderr does not say failed to start", "failed to start" not in run.err, run.err)


# --------------------------------------------------------------------------- case 5
# The prompt holds the reply text and the three rules, and says running background work never
# makes a reply unfinished (the second false block, 2026-10-13).

def case_prompt_carries_reply_and_rules():
    run = run_hook(MARK, answer=json.dumps({"ok": True}))
    prompt = run.prompt()
    check("prompt: carries last_assistant_message", MARK in prompt, prompt[:300])
    for rule in RULE_IDS:
        check("prompt: names rule %s" % rule, rule in prompt, prompt[:300])
    sentences = re.split(r"[.\n]", prompt)
    check("prompt: says running background work never makes a reply unfinished",
          any(all(word in s.lower() for word in BACKGROUND_WORDS) for s in sentences), prompt[:300])


# --------------------------------------------------------------------------- case 6
# Recursion. The child claude call reuses decision_watch's isolation: --safe-mode, --tools "",
# an empty config dir with no settings or hooks, and a scratch cwd outside this repo.

def case_child_cannot_retrigger_hook():
    run = run_hook(MARK, answer=json.dumps({"ok": True}))
    call = run.calls[0] if run.calls else {}
    argv = call.get("argv", [])
    pairs = list(zip(argv, argv[1:]))
    check("recursion: child runs with --safe-mode (no hooks, MCP, plugins or skills)",
          "--safe-mode" in argv, argv)
    check("recursion: child runs with --tools set to empty (no tools)",
          ("--tools", "") in pairs, argv)
    config_entries = call.get("config_entries") or []
    check("recursion: child config dir has no settings or hooks to load",
          not {"settings.json", "settings.local.json", "hooks"} & set(config_entries), config_entries)
    check("recursion: child config dir is not the parent's config dir",
          call.get("config_dir") not in (None, run.config), call.get("config_dir"))
    cwd = call.get("cwd") or ""
    inside_repo = os.path.normcase(os.path.realpath(cwd)).startswith(
        os.path.normcase(os.path.realpath(REPO_ROOT)))
    check("recursion: child cwd is outside this repo", bool(cwd) and not inside_repo, cwd)
    cwd_entries = call.get("cwd_entries") or []
    check("recursion: child cwd holds no .claude or settings.json",
          not {".claude", "settings.json"} & set(cwd_entries), cwd_entries)


CASES = (
    case_stop_hook_active_never_calls_model,
    case_model_ok_is_silent,
    case_model_is_haiku_at_xhigh,
    case_model_block_emits_block_json,
    case_model_failure_fails_open,
    case_timeout_leaks_no_reply_text,
    case_prompt_carries_reply_and_rules,
    case_child_cannot_retrigger_hook,
)


def run_case(case):
    before = len(FAILED)
    try:
        case()
    except Exception as exc:  # a case that cannot run is red, never silently green
        check("%s: case ran" % case.__name__, False, "%s: %s" % (type(exc).__name__, exc))
    if len(FAILED) > before:
        RED_CASES.append(case.__name__)


def main():
    _write_stub()
    try:
        for case in CASES:
            run_case(case)
    finally:
        shutil.rmtree(ROOT, ignore_errors=True)
    if RED_CASES:
        print("test_reply_judge FAIL: %d of %d cases red" % (len(RED_CASES), len(CASES)))
        return 1
    print("test_reply_judge PASS: all %d cases green" % len(CASES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
