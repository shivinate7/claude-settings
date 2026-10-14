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

Sampling cases (case 8 on) run several Stops of one config dir in a row. Each Stop is still a
new process, so the counter must persist in files, not in memory.
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
SETTINGS_PATH = os.environ.get("SETTINGS_UNDER_TEST") or os.path.join(REPO_ROOT, "settings.json")
ROOT = tempfile.mkdtemp(prefix="reply_judge_cases_")
STUB_DIR = os.path.join(ROOT, "stub")
FAILED = []
RED_CASES = []
RUNS = [0]

MARK = "Stage two is live, MARK-7f3a"  # one line, no quotes, no rule id, no background word
BLOCK_REASON = "output-never-paste-passing-output: paste the verdict, not the run's output."
RULE_IDS = ("output-start-with-point", "style-cut-narration", "output-never-paste-passing-output")
BACKGROUND_WORDS = ("background", "unfinished", "never")
REPLY_SESSION = "reply-judge-cases"

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
        "stdin": kwargs.get("input"),
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
if os.environ.get("RJ_FAIL_REPLACE"):
    # Fake write failure, in the hook process only: every os.replace raises, so no counter write lands.
    def _refused_replace(src, dst, *args, **kwargs):
        raise OSError("fake write failure: os.replace refused")
    os.replace = _refused_replace
if os.environ.get("RJ_FAIL_REMOVE"):
    # Fake read-only counter, in the hook process only: os.remove refuses a counter file, so a
    # failed write cannot drop the file either. Every other remove goes to the real os.remove.
    _real_remove = os.remove
    def _refused_remove(path, *args, **kwargs):
        if str(path).endswith(".count"):
            raise PermissionError("fake remove failure: counter file is read-only")
        return _real_remove(path, *args, **kwargs)
    os.remove = _refused_remove
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

    def __init__(self, proc, base, config):
        self.code = proc.returncode
        self.out = proc.stdout or ""
        self.err = proc.stderr or ""
        self.config = config
        self.loaded = os.path.exists(os.path.join(base, "loaded"))
        self.calls = []
        record = os.path.join(base, "calls.jsonl")
        if os.path.exists(record):
            with open(record, encoding="utf-8") as f:
                self.calls = [json.loads(line) for line in f if line.strip()]

    def prompt(self):
        # The prompt travels on the child's stdin, never in argv (Windows caps a command line).
        return (self.calls[0].get("stdin") or "") if self.calls else ""


def run_hook(text, scenario="ok", answer="", stop_active=False, config=None, session=REPLY_SESSION,
             fail_replace=False, fail_remove=False):
    """One Stop, one new process. With no `config`, the config dir is fresh and empty, so the
    Stop is the session's first. A shared `config` carries the counter from Stop to Stop.
    `text` may be ABSENT: the payload then has no last_assistant_message key at all.
    `fail_replace` makes every os.replace in the hook process raise (a fake write failure).
    `fail_remove` makes os.remove raise on a counter file (a fake read-only counter)."""
    RUNS[0] += 1
    base = os.path.join(ROOT, "run-%03d" % RUNS[0])
    os.makedirs(base, exist_ok=True)
    if config is None:
        config = os.path.join(base, "config")
    os.makedirs(config, exist_ok=True)  # empty on first use: no settings, hooks, credential or token
    env = dict(os.environ)
    for name in ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY"):
        env.pop(name, None)
    if fail_replace:
        env["RJ_FAIL_REPLACE"] = "1"
    else:
        env.pop("RJ_FAIL_REPLACE", None)
    if fail_remove:
        env["RJ_FAIL_REMOVE"] = "1"
    else:
        env.pop("RJ_FAIL_REMOVE", None)
    env.update(
        CLAUDE_CONFIG_DIR=config,
        PYTHONPATH=STUB_DIR,
        RJ_SCENARIO=scenario,
        RJ_ANSWER=answer,
        RJ_RECORD=os.path.join(base, "calls.jsonl"),
        RJ_LOADED=os.path.join(base, "loaded"),
    )
    payload = {
        "session_id": session,
        "hook_event_name": "Stop",
        "cwd": base,
        "stop_hook_active": stop_active,
        "last_assistant_message": text,
    }
    if text is ABSENT:
        del payload["last_assistant_message"]
    proc = subprocess.run(
        [sys.executable, MODULE_PATH],
        input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=60, env=env, cwd=base,
    )
    run = Run(proc, base, config)
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
# A model answer of {"ok": false, "reason": R} is a finding. It never blocks. Stdout is one JSON
# object, the Stop note that Claude Code delivers at the start of the next turn:
#   {"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": NOTE}}
# NOTE names the rule id and the fix. The shape is the one Claude Code's async hook validator
# accepts for a Stop hook (checked in the installed binary, 2026-10-13).

def parse_stdout(run):
    try:
        got = json.loads(run.out)
    except ValueError:
        return None
    return got if isinstance(got, dict) else None


def case_model_finding_emits_note_not_block():
    run = run_hook(MARK, answer=json.dumps({"ok": False, "reason": BLOCK_REASON}))
    check("finding: exit 0", run.code == 0, run.code)
    got = parse_stdout(run)
    specific = got.get("hookSpecificOutput") if got else None
    check("finding: stdout is one JSON object holding hookSpecificOutput",
          isinstance(specific, dict), run.out)
    check("finding: hookEventName is Stop",
          isinstance(specific, dict) and specific.get("hookEventName") == "Stop", run.out)
    note = specific.get("additionalContext") if isinstance(specific, dict) else None
    check("finding: additionalContext names the rule id",
          isinstance(note, str) and "output-never-paste-passing-output" in note, run.out)
    check("finding: additionalContext holds the fix",
          isinstance(note, str) and "paste the verdict" in note, run.out)
    check("finding: never a block, no decision key at the top level or in hookSpecificOutput",
          got is not None and "decision" not in got and "decision" not in (specific or {}), run.out)


# A finding with no reason is still a note. The fallback must not turn it into a block.

def case_finding_without_reason_is_still_a_note():
    run = run_hook(MARK, answer=json.dumps({"ok": False}))
    got = parse_stdout(run)
    specific = got.get("hookSpecificOutput") if got else None
    note = specific.get("additionalContext") if isinstance(specific, dict) else None
    check("finding without reason: exit 0", run.code == 0, run.code)
    check("finding without reason: a non-empty note, not a block",
          isinstance(note, str) and note.strip() != "" and got is not None and "decision" not in got,
          run.out)


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
    check("timeout: claude was called, so the leak checks mean something", bool(run.calls), run.calls)
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


# --------------------------------------------------------------------------- case 7
# settings.json. The reply judge Stop entry is async, so a finding never holds the turn. The
# report gate Stop entry is not async: it still blocks. Each entry is found by its script path.

def stop_hooks_running(script):
    with open(SETTINGS_PATH, encoding="utf-8") as f:
        settings = json.load(f)
    found = []
    for entry in (settings.get("hooks") or {}).get("Stop") or []:
        for hook in entry.get("hooks") or []:
            if script in str(hook.get("command", "")):
                found.append(hook)
    return found


def case_settings_reply_judge_is_async_and_report_gate_is_not():
    try:
        judge = stop_hooks_running("hooks/reply_judge.py")
        gate = stop_hooks_running("lint/report_gate.py")
    except (OSError, ValueError) as exc:
        check("settings: settings.json reads as JSON", False, "%s: %s" % (type(exc).__name__, exc))
        return
    check("settings: exactly one reply_judge Stop hook", len(judge) == 1, judge)
    check("settings: reply_judge Stop hook has async true",
          len(judge) == 1 and judge[0].get("async") is True, judge)
    check("settings: exactly one report_gate Stop hook", len(gate) == 1, gate)
    check("settings: report_gate Stop hook is not async",
          len(gate) == 1 and gate[0].get("async") is not True, gate)


# --------------------------------------------------------------------------- cases 8-13
# Sampling. Owner ruling, 2026-10-13 14:40 CDT: the reply judge runs on one Stop in five. Stop n
# of a session is judged when (n - 1) % 5 == 0: Stops 1, 6, 11, so a short session is judged
# once. The count is a file in the state folder under CLAUDE_CONFIG_DIR, one per session, the
# home decision_watch.py uses. Every Stop writes it back, skipped Stops included. A skipped Stop
# returns at once: no model call, no output, exit 0.
#
# Guesses, pinned here and named in the report:
#   (a) the file holds the Stops so far; this Stop is n = stored + 1.
#   (b) a missing, unreadable or corrupt file reads as no count. That Stop is Stop 1 and is
#       judged, and its write repairs the file. One branch, not two: a fresh session and a
#       damaged file take the same path. Fail open in the sense that nothing is blocked; a
#       judged Stop costs one model call, never a refusal.
#   (c) the file's own name and folder under state/ are not pinned. Only that a file appears.
#   (d) not pinned: whether a stop_hook_active Stop advances the count. The guard returns
#       first, so it is assumed not to.

SESSION_ALPHA = "sample-session-alpha"
SESSION_BETA = "sample-session-beta"
OK_ANSWER = json.dumps({"ok": True})
FINDING_ANSWER = json.dumps({"ok": False, "reason": BLOCK_REASON})
DAMAGE = ("missing", "corrupt", "unreadable")
ABSENT = object()  # a payload with no last_assistant_message key
EMPTY_REPLIES = ("", "  \n", None, ABSENT)  # no reply text: empty, whitespace, null, missing


def sample_config(label):
    path = os.path.join(ROOT, "sample-%s" % label, "config")
    os.makedirs(path, exist_ok=True)
    return path


def counter_files(config):
    """Paths, relative to the config dir, of every file under state/. Empty when there are none."""
    found = []
    for dirpath, _dirs, names in os.walk(os.path.join(config, "state")):
        for name in names:
            found.append(os.path.relpath(os.path.join(dirpath, name), config))
    return sorted(found)


def damage_counter(config, how):
    for rel in counter_files(config):
        path = os.path.join(config, rel)
        if how == "missing":
            os.remove(path)
        elif how == "corrupt":
            with open(path, "wb") as f:
                f.write(b"\xc3\x28 not a count \xff")  # not UTF-8, not JSON, not a number
        else:  # unreadable: a folder where the file was, so open() fails
            os.remove(path)
            os.makedirs(path)


# --------------------------------------------------------------------------- case 8
# The model is called on Stops 1, 6 and 11 of one session, once each, and on no other Stop.

def case_sampling_judges_stops_1_6_11():
    config = sample_config("eleven")
    codes = []
    called = {}
    for n in range(1, 12):
        run = run_hook(MARK, answer=OK_ANSWER, config=config, session=SESSION_ALPHA)
        codes.append(run.code)
        if run.calls:
            called[n] = len(run.calls)
    check("sampling: exit 0 on each of 11 Stops", all(c == 0 for c in codes), codes)
    check("sampling: claude called once on Stops 1, 6 and 11, never on the others",
          called == {1: 1, 6: 1, 11: 1}, called)


# --------------------------------------------------------------------------- case 9
# A skipped Stop: no model call, nothing on stdout or stderr, exit 0. The stubbed answer on
# Stop 2 is a finding, so a hook that called the model would print a note and fail this case.

def case_skipped_stop_is_silent():
    config = sample_config("skip")
    run_hook(MARK, answer=OK_ANSWER, config=config, session=SESSION_ALPHA)  # Stop 1, judged
    skipped = run_hook(MARK, answer=FINDING_ANSWER, config=config, session=SESSION_ALPHA)  # Stop 2
    check("skip: Stop 2 exit 0", skipped.code == 0, skipped.code)
    check("skip: Stop 2 never calls the model", skipped.calls == [], skipped.calls)
    check("skip: Stop 2 prints nothing on stdout", skipped.out.strip() == "", skipped.out)
    check("skip: Stop 2 prints nothing on stderr", skipped.err.strip() == "", skipped.err)


# --------------------------------------------------------------------------- case 10
# Two sessions, interleaved Stop by Stop, in one config dir. A counter shared by both would
# skip Beta's first Stop, and would judge the wrong Stops for each session.

def case_sessions_keep_separate_counters():
    config = sample_config("two-sessions")
    called = {SESSION_ALPHA: [], SESSION_BETA: []}
    for n in range(1, 7):
        for session in (SESSION_ALPHA, SESSION_BETA):
            run = run_hook(MARK, answer=OK_ANSWER, config=config, session=session)
            if run.calls:
                called[session].append(n)
    check("sessions: each session judged on its own Stops 1 and 6",
          called == {SESSION_ALPHA: [1, 6], SESSION_BETA: [1, 6]}, called)


# --------------------------------------------------------------------------- case 11
# The count is a file under the config dir. A copy of that state, read by a new process in a new
# config dir, gives the same count. A config dir with no state counts as a first Stop.

def case_counter_is_a_file_that_survives_between_processes():
    config = sample_config("survives")
    run_hook(MARK, answer=OK_ANSWER, config=config, session=SESSION_ALPHA)  # Stop 1, judged
    files = counter_files(config)
    check("counter: Stop 1 wrote a file under <config>/state/",
          bool(files) and all(p.split(os.sep)[0] == "state" for p in files), files)
    copied = os.path.join(ROOT, "sample-survives-copy", "config")
    shutil.copytree(config, copied)
    second = run_hook(MARK, answer=OK_ANSWER, config=copied, session=SESSION_ALPHA)  # Stop 2
    check("counter: Stop 2 reads the count back from the copied file and is skipped",
          second.calls == [], second.calls)
    fresh = run_hook(MARK, answer=OK_ANSWER, session=SESSION_ALPHA)  # empty config, no state
    check("counter: an empty config dir has no count, so its Stop is judged",
          len(fresh.calls) == 1, fresh.calls)


# --------------------------------------------------------------------------- case 12
# A missing, corrupt or unreadable counter fails open: exit 0, no traceback, no block, and this
# Stop is judged (guess (b)). For missing and corrupt, the write repairs the file, so Stop 3 is
# skipped. For unreadable, the write fails too, so every Stop is judged; Stop 3 is not pinned.

def case_damaged_counter_fails_open():
    for how in DAMAGE:
        config = sample_config("damaged-%s" % how)
        run_hook(MARK, answer=OK_ANSWER, config=config, session=SESSION_ALPHA)  # Stop 1, judged
        check("damaged %s: Stop 1 wrote a counter to damage" % how, bool(counter_files(config)),
              counter_files(config))
        damage_counter(config, how)
        second = run_hook(MARK, answer=OK_ANSWER, config=config, session=SESSION_ALPHA)  # Stop 2
        check("damaged %s: Stop 2 exit 0, no traceback" % how,
              second.code == 0 and "Traceback" not in second.err, second.err)
        check("damaged %s: Stop 2 judged once, the damaged counter read as none" % how,
              len(second.calls) == 1, second.calls)
        check("damaged %s: Stop 2 prints nothing on stdout" % how, second.out.strip() == "", second.out)
        if how != "unreadable":
            third = run_hook(MARK, answer=OK_ANSWER, config=config, session=SESSION_ALPHA)  # Stop 3
            check("damaged %s: the write repaired the counter, so Stop 3 is skipped" % how,
                  third.calls == [], third.calls)


# --------------------------------------------------------------------------- case 13
# A counter write that fails never blocks or crashes the Stop. The state folder is made a plain
# file, so every write under it fails and so does every read. The finding still comes out as a
# note, and the Stop is judged once. Green on main by construction: main writes no counter, so
# this case guards the write the builder adds.

def case_counter_write_failure_never_blocks():
    config = sample_config("write-fails")
    with open(os.path.join(config, "state"), "w", encoding="utf-8") as f:
        f.write("a file where the state folder must be\n")
    run = run_hook(MARK, answer=FINDING_ANSWER, config=config, session=SESSION_ALPHA)
    got = parse_stdout(run)
    specific = got.get("hookSpecificOutput") if got else None
    check("write fails: exit 0", run.code == 0, run.code)
    check("write fails: no traceback on stderr", "Traceback" not in run.err, run.err)
    check("write fails: the finding is still a note, never a block",
          isinstance(specific, dict) and "decision" not in got and "decision" not in specific, run.out)
    check("write fails: the Stop is judged once", len(run.calls) == 1, run.calls)


# --------------------------------------------------------------------------- cases 14-16
# Hole 1 (review round 1): a failed counter write froze the stored count at k. Every later Stop
# read k, returned n = k + 1 and was skipped forever. Pin: the Stop after a failed write is judged.
# Stop 1 writes a good count. From Stop 2 on, the stub's os.replace refuses every write. Stop 2
# reads 1, so n = 2 and is skipped, and its write fails. Stops 3 to 9 must each be judged, since
# every one of them follows a failed write. No Stop is skipped forever.

def case_failed_write_does_not_freeze_the_count():
    config = sample_config("write-refused")
    run_hook(MARK, answer=OK_ANSWER, config=config, session=SESSION_ALPHA)  # Stop 1, good write
    check("write refused: Stop 1 wrote a counter", bool(counter_files(config)), counter_files(config))
    codes = []
    called = {}
    for n in range(2, 10):
        run = run_hook(MARK, answer=OK_ANSWER, config=config, session=SESSION_ALPHA, fail_replace=True)
        codes.append(run.code)
        called[n] = len(run.calls)
    check("write refused: exit 0 on Stops 2 to 9", all(c == 0 for c in codes), codes)
    check("write refused: Stop 2 is skipped, its read was good", called[2] == 0, called)
    check("write refused: Stops 3 to 9 are each judged, none skipped forever",
          all(called[n] == 1 for n in range(3, 10)), called)


# Hole 2 (review round 1): a Stop with no reply text was counted before the empty-reply return,
# so an empty Stop 1 used the session's first sample slot. Pin: an empty Stop writes no counter
# change and counts for nothing. Stops 1, 6 and 11 are counted among Stops that carry a reply.

def counter_snapshot(config):
    snap = {}
    for rel in counter_files(config):
        with open(os.path.join(config, rel), "rb") as f:
            snap[rel] = f.read()
    return snap


def empty_stop_is_silent(run):
    return run.code == 0 and run.calls == [] and run.out.strip() == ""


def case_empty_stop_writes_nothing_and_counts_nothing():
    config = sample_config("empty-first")
    empty = run_hook(EMPTY_REPLIES[0], answer=FINDING_ANSWER, config=config, session=SESSION_ALPHA)
    check("empty first Stop: exit 0, no call, nothing printed", empty_stop_is_silent(empty), empty.out)
    check("empty first Stop: no counter written", counter_files(config) == [], counter_files(config))
    reply = run_hook(MARK, answer=OK_ANSWER, config=config, session=SESSION_ALPHA)
    check("empty first Stop: the first reply is the first counted Stop, so it is judged",
          len(reply.calls) == 1, reply.calls)
    before = counter_snapshot(config)
    empty_again = run_hook(EMPTY_REPLIES[2], answer=FINDING_ANSWER, config=config, session=SESSION_ALPHA)
    check("empty after a counted reply: exit 0, no call, nothing printed",
          empty_stop_is_silent(empty_again), empty_again.out)
    check("empty after a counted reply: counter bytes unchanged",
          counter_snapshot(config) == before, counter_snapshot(config))


def case_empty_stops_between_replies_do_not_shift_samples():
    config = sample_config("empty-between")
    judged = []
    bad_empty = []
    for i in range(1, 12):  # 11 replies, each after one empty Stop of a different kind
        kind = EMPTY_REPLIES[i % len(EMPTY_REPLIES)]
        before = counter_snapshot(config)
        empty = run_hook(kind, answer=FINDING_ANSWER, config=config, session=SESSION_ALPHA)
        if not empty_stop_is_silent(empty) or counter_snapshot(config) != before:
            bad_empty.append(i)
        reply = run_hook(MARK, answer=OK_ANSWER, config=config, session=SESSION_ALPHA)
        if reply.calls:
            judged.append(i)
    check("empty between replies: each empty Stop is silent and changes no counter",
          bad_empty == [], bad_empty)
    check("empty between replies: the model is called on reply 1, 6 and 11 only",
          judged == [1, 6, 11], judged)


# --------------------------------------------------------------------------- cases 17-20
# Freeze defect: after a good read, a failed write removes the counter file. If that remove also
# fails (a read-only file on Windows), the old count stays on disk, so every later Stop reads it
# and is skipped. Pin: when the write and the remove both fail, the Stop is judged, as a damaged
# counter is (n = 1). Stops 1 to 3 with good writes leave the stored count at 3, so Stop 4 reads 3.

FREEZE_SETUP_JUDGED = [1]  # Stop 1 is judged; Stops 2 and 3 are skipped by sampling


def freeze_counter_at_three(config):
    """Stops 1 to 3 with good writes. Afterwards the stored count is 3."""
    judged = []
    for n in range(1, 4):
        run = run_hook(MARK, answer=OK_ANSWER, config=config, session=SESSION_ALPHA)
        if run.calls:
            judged.append(n)
    check("freeze setup: Stops 1 to 3 judged on Stop 1 only", judged == FREEZE_SETUP_JUDGED, judged)


def case_write_and_remove_both_fail_judges_the_stop():
    config = sample_config("both-fail")
    freeze_counter_at_three(config)
    frozen = run_hook(MARK, answer=OK_ANSWER, config=config, session=SESSION_ALPHA,
                      fail_replace=True, fail_remove=True)  # Stop 4: reads 3, write and remove fail
    check("both fail: Stop 4 exit 0, no traceback on stderr",
          frozen.code == 0 and "Traceback" not in frozen.err, frozen.err)
    check("both fail: Stop 4 prints nothing on stdout or stderr",
          frozen.out.strip() == "" and frozen.err.strip() == "", (frozen.out, frozen.err))
    check("both fail: Stop 4 is judged, as a damaged counter is (n = 1)",
          len(frozen.calls) == 1, frozen.calls)


def case_frozen_counter_judges_every_later_stop():
    config = sample_config("frozen-six")
    freeze_counter_at_three(config)
    judged = []
    bad = []
    for n in range(4, 10):  # Stops 4 to 9 of one session: every write fails, every remove fails
        run = run_hook(MARK, answer=OK_ANSWER, config=config, session=SESSION_ALPHA,
                       fail_replace=True, fail_remove=True)
        if run.code != 0 or run.err.strip() != "":
            bad.append(n)
        if run.calls:
            judged.append(n)
    check("frozen six: exit 0 and no stderr on Stops 4 to 9", bad == [], bad)
    check("frozen six: each of Stops 4 to 9 is judged, none skipped",
          judged == list(range(4, 10)), judged)


def case_write_fails_remove_ok_judges_the_next_stop():
    config = sample_config("write-only-fails")
    freeze_counter_at_three(config)
    failed = run_hook(MARK, answer=OK_ANSWER, config=config, session=SESSION_ALPHA,
                      fail_replace=True)  # Stop 4: write fails, remove succeeds, counter dropped
    check("write fails, remove ok: Stop 4 exit 0, no stderr",
          failed.code == 0 and failed.err.strip() == "", failed.err)
    nxt = run_hook(MARK, answer=OK_ANSWER, config=config, session=SESSION_ALPHA)  # Stop 5
    check("write fails, remove ok: Stop 5 is judged once",
          len(nxt.calls) == 1, nxt.calls)
    check("write fails, remove ok: Stop 5 exit 0, no stderr",
          nxt.code == 0 and nxt.err.strip() == "", nxt.err)


def case_good_write_path_judges_stops_1_6_11():
    config = sample_config("good-path")
    judged = []
    bad = []
    for n in range(1, 12):  # no fault injected: the good write path must keep its sampling
        run = run_hook(MARK, answer=OK_ANSWER, config=config, session=SESSION_ALPHA)
        if run.code != 0 or run.err.strip() != "":
            bad.append(n)
        if run.calls:
            judged.append(n)
    check("good path: exit 0 and no stderr on Stops 1 to 11", bad == [], bad)
    check("good path: judged on Stops 1, 6 and 11 only", judged == [1, 6, 11], judged)


CASES = (
    case_stop_hook_active_never_calls_model,
    case_model_ok_is_silent,
    case_model_is_haiku_at_xhigh,
    case_model_finding_emits_note_not_block,
    case_finding_without_reason_is_still_a_note,
    case_model_failure_fails_open,
    case_timeout_leaks_no_reply_text,
    case_prompt_carries_reply_and_rules,
    case_child_cannot_retrigger_hook,
    case_settings_reply_judge_is_async_and_report_gate_is_not,
    case_sampling_judges_stops_1_6_11,
    case_skipped_stop_is_silent,
    case_sessions_keep_separate_counters,
    case_counter_is_a_file_that_survives_between_processes,
    case_damaged_counter_fails_open,
    case_counter_write_failure_never_blocks,
    case_failed_write_does_not_freeze_the_count,
    case_empty_stop_writes_nothing_and_counts_nothing,
    case_empty_stops_between_replies_do_not_shift_samples,
    case_write_and_remove_both_fail_judges_the_stop,
    case_frozen_counter_judges_every_later_stop,
    case_write_fails_remove_ok_judges_the_next_stop,
    case_good_write_path_judges_stops_1_6_11,
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
