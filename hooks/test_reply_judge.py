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
RULE_IDS = ("output-start-with-point", "style-cut-narration", "output-never-paste-passing-output",
            "style-limits-kept-silently")
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
    stdin = kwargs.get("input")
    if isinstance(stdin, bytes):  # the judge sends the prompt as UTF-8 bytes, not text
        stdin = stdin.decode("utf-8")
    rec = {
        "argv": list(argv),
        "stdin": stdin,
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


# The hook runs model haiku at effort xhigh. This case alone pins the model this hook passes
# (reply_judge.py, the invoke_model call). test_decision_watch case_invoke_model_argv pins the
# argv builder; neither covers the other's call site.

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
# accepts for a Stop hook (checked in the installed binary).

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
# makes a reply unfinished.

def case_prompt_carries_reply_and_rules():
    run = run_hook(MARK, answer=json.dumps({"ok": True}))
    prompt = run.prompt()
    check("prompt: carries last_assistant_message", MARK in prompt, prompt[:300])
    for rule in RULE_IDS:
        check("prompt: names rule %s" % rule, rule in prompt, prompt[:300])
    sentences = re.split(r"[.\n]", prompt)
    check("prompt: says running background work never makes a reply unfinished",
          any(all(word in s.lower() for word in BACKGROUND_WORDS) for s in sentences), prompt[:300])


# --------------------------------------------------------------------------- case 5b
# The owner-step rule, output-never-hand-off-doable-step: a step left to the owner comes as its
# own fenced code block, outside the report blockquote. The judge is a model and the model is a
# stub here, so a canned {"ok": false} on a prose-step reply would also be green on main and prove
# nothing. What can go red is the prompt, the one input the real model gets. Each case sends one
# reply and reads the rule text before it (never the reply, so a word in the reply cannot satisfy
# a pin). A pin is one sentence that holds a word from every group. The wording stays the
# builder's, inside these words.
#
# Dropped, and said so: a case for a block that mixes shells (PowerShell and bash lines). It needs
# a code check, and this hook has none. See the report to the orchestrator.

OWNER_STEP_RULE = "output-never-hand-off-doable-step"
STEP_IN_PROSE = (  # (a) the owner is told to run a command, with no fenced block anywhere
    "The hook change is pushed on branch owner-step-command.\n\n"
    "To see it work, open a terminal in the repo and run python hooks/reply_judge.py with a Stop "
    "payload on stdin. Then tell me what it prints."
)
STEP_IN_OWN_BLOCK = (  # (b) the same step as its own fenced block, outside the report blockquote
    "> **Done**\n> BUILT: the hook change, commit abc1234.\n> Input Needed: run the check below.\n\n"
    "Run this in PowerShell:\n\n"
    "```powershell\ncd C:\\Users\\me\\repo\npython hooks\\test_reply_judge.py\n```\n"
)
NO_OWNER_STEP = "Both checks pass. The branch is pushed and nothing is left for you to do."  # (c)
QUOTES_RAN_COMMAND = (  # false alarm: a command the reply already ran, quoted as history
    "I ran `python -I hooks/test_reply_judge.py` and it passed in 32 s. The branch is pushed. "
    "No step is left for you."
)
COMMAND_IN_REPORT_LINE = (  # false alarm: a command named inside a report line
    "> **Done**\n> BUILT: `python hooks/reply_judge.py` now reads the new rule. Commit abc1234.\n"
    "> Next: a builder adds the check.\n"
)


def rule_sentences(run, reply):
    """The prompt's rule text as lowercase sentences. It is the part before the reply."""
    head = run.prompt().split(reply, 1)[0].lower()
    return [s for s in re.split(r"[.\n]", head) if s.strip()]


def has_pin(sentences, *groups):
    """True when one sentence holds at least one word from each group."""
    return any(all(any(word in s for word in group) for group in groups) for s in sentences)


def run_owner_step_reply(label, reply):
    run = run_hook(reply, answer=OK_ANSWER)
    sentences = rule_sentences(run, reply)
    check("owner step, %s: the prompt carries the reply" % label, reply in run.prompt(), run.prompt()[:300])
    check("owner step, %s: the prompt names %s before the reply" % (label, OWNER_STEP_RULE),
          any(OWNER_STEP_RULE in s for s in sentences), run.prompt()[:300])
    return sentences


# (a) A reply that tells the owner to run a command in prose, with no fenced block, is a breach
# the judge must be asked about: one sentence says a step left to the owner needs a code block.

def case_owner_step_in_prose_prompt_asks_for_fenced_block():
    sentences = run_owner_step_reply("prose step", STEP_IN_PROSE)
    check("owner step, prose step: a sentence says a step left to the owner needs a fenced code block",
          has_pin(sentences, ("owner", "user"), ("step", "command"), ("fenced", "code block", "fence")),
          sentences)


# (b) The same step as its own fenced block, outside the report blockquote, passes. The judge
# must be told where the block sits: one sentence says the block is outside the report.

def case_owner_step_block_outside_report_prompt_says_where():
    sentences = run_owner_step_reply("own block", STEP_IN_OWN_BLOCK)
    check("owner step, own block: a sentence says the block sits outside the report blockquote",
          has_pin(sentences, ("block", "fence"),
                  ("outside", "not inside", "never inside", "after the report", "below the report"),
                  ("report", "blockquote")),
          sentences)


# (c) A reply with no owner step passes, and so do the two false alarms: a command the reply
# already ran, and a command named in a report line. The judge must be told neither is a step
# left to the owner. The stub answers ok for all three, so a silent hook shows only that the
# new rule text adds no stdout of its own.

def case_owner_step_carve_outs_in_prompt():
    for label, reply in (("no step", NO_OWNER_STEP), ("quotes a command it ran", QUOTES_RAN_COMMAND),
                         ("command in a report line", COMMAND_IN_REPORT_LINE)):
        sentences = run_owner_step_reply(label, reply)
        check("owner step, %s: a sentence says a command already run is not a step left to the owner" % label,
              has_pin(sentences, ("already",), ("ran", "run"), ("not", "never", "no ")), sentences)
        check("owner step, %s: a sentence says a command named in a report line is not a step left to the owner" % label,
              has_pin(sentences, ("report",), ("line",), ("name", "mention"), ("not", "never", "no ")), sentences)


# --------------------------------------------------------------------------- case 5c
# The silent-limits rule, style-limits-kept-silently. As in case 5b the model is a stub, so the
# prompt is what can go red: each case reads the rule text before the reply.

LIMITS_RULE = "style-limits-kept-silently"
NARRATES_LIMIT = "Staying under the 15-line cap. Rule X holds.\n\nThe hook change is pushed."  # (a)
LIMIT_BLOCKED = (  # (b) a limit blocked the work, so naming it is right
    "The 15-line cap blocks this fix: the change needs 40 lines, so I split it into two lanes."
)
NAMES_DROPPED_ITEM = (  # (c) a dropped item is said
    "I dropped the table check from this batch. It needs a parser the repo lacks."
)
DONE_RESULT_LINE = "> **Done**\n> BUILT: the judge clause, commit abc1234, tests pass.\n"  # (d)

VERDICT_OUTSIDE_DONE = "CI is green on the head."  # (e) a reported verdict outside Done


def run_limits_reply(label, reply):
    run = run_hook(reply, answer=OK_ANSWER)
    sentences = rule_sentences(run, reply)
    check("limits, %s: the prompt carries the reply" % label, reply in run.prompt(), run.prompt()[:300])
    check("limits, %s: the prompt names %s before the reply" % (label, LIMITS_RULE),
          any(LIMITS_RULE in s for s in sentences), run.prompt()[:300])
    return sentences


def case_limits_narration_prompt_flags_it():
    sentences = run_limits_reply("narrates a limit", NARRATES_LIMIT)
    check("limits, narrates a limit: a sentence says narrating a kept limit or a passed check is flagged",
          has_pin(sentences, ("flag",), ("narrat",), ("limit",), ("check",)), sentences)


def case_limits_blocked_work_prompt_passes_it():
    sentences = run_limits_reply("limit blocked the work", LIMIT_BLOCKED)
    check("limits, limit blocked the work: a sentence says a limit that blocked the work or changed the plan passes",
          has_pin(sentences, ("limit",), ("blocked",), ("plan",), ("never flag", "passes", "not flag")), sentences)


def case_limits_dropped_item_prompt_passes_it():
    sentences = run_limits_reply("names a dropped item", NAMES_DROPPED_ITEM)
    check("limits, names a dropped item: a sentence says a named skipped step or dropped item passes",
          has_pin(sentences, ("skipped",), ("dropped",), ("never flag", "passes", "not flag")), sentences)


def case_limits_done_result_line_is_not_narration():
    sentences = run_limits_reply("Done result line", DONE_RESULT_LINE)
    check("limits, Done result line: a sentence says a result line such as tests pass in Done is not narration",
          has_pin(sentences, ("result",), ("done",), ("tests pass",), ("not narration", "never flag")), sentences)


def case_limits_verdict_outside_done_is_not_narration():
    sentences = run_limits_reply("verdict outside Done", VERDICT_OUTSIDE_DONE)
    check("limits, verdict outside Done: a sentence says a reported result or verdict is not narration",
          has_pin(sentences, ("result",), ("verdict",), ("anywhere",), ("not narration", "never flag")), sentences)


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
# Sampling: the reply judge runs on one Stop in five. Stop n
# of a session is judged when (n - 1) % 5 == 0: Stops 1, 6, 11, so a short session is judged
# once. The count is a file in the state folder under CLAUDE_CONFIG_DIR, one per session, the
# home decision_watch.py uses. Every Stop writes it back, skipped Stops included. A skipped Stop
# returns at once: no model call, no output, exit 0.
#
# Assumptions pinned here:
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
# Stop is judged (assumption (b)). For missing and corrupt, the write repairs the file, so Stop 3 is
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
# note, and the Stop is judged once.

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
# A failed counter write must not freeze the stored count at k: every later Stop would read k,
# return n = k + 1 and be skipped forever. The Stop after a failed write is judged.
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


# An empty Stop (no reply text) writes no counter change and counts for nothing, so it never
# uses a sample slot. Stops 1, 6 and 11 are counted among Stops that carry a reply.

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
# After a good read, a failed write removes the counter file. If that remove also fails (a
# read-only file on Windows), the old count stays on disk and every later Stop would read it and
# be skipped. When the write and the remove both fail, the Stop is judged, as a damaged
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


# --------------------------------------------------------------------------- imports on an ignored Stop
# A Stop the hook ignores must not import the shell parser (guard), the model caller
# (decision_watch) or the linter (ste_lint). The probe runs the hook file as __main__ in a fresh
# process, then reports which of them that process imported. The hook's output comes first.

GUARD_FAMILY = ("guard", "decision_watch", "ste_lint")
IMPORT_PROBE = (
    "import json, runpy, sys\n"
    "try:\n"
    "    runpy.run_path(sys.argv[1], run_name='__main__')\n"
    "except SystemExit:\n"
    "    pass\n"
    "print('PROBE ' + json.dumps([m for m in %r if m in sys.modules]))\n" % (GUARD_FAMILY,)
)


def probe_ignored_stop(payload, config=None):
    """Return (the hook's stdout, the GUARD_FAMILY modules its process imported, the model calls).
    The model is the stub, so a Stop that is wrongly judged reaches no real claude. A shared
    `config` carries the sampling counter from an earlier Stop."""
    RUNS[0] += 1
    base = os.path.join(ROOT, "probe-%03d" % RUNS[0])
    config = config or os.path.join(base, "config")
    os.makedirs(base, exist_ok=True)
    os.makedirs(config, exist_ok=True)
    record = os.path.join(base, "calls.jsonl")
    env = dict(os.environ, CLAUDE_CONFIG_DIR=config, PYTHONPATH=STUB_DIR, RJ_SCENARIO="",
               RJ_ANSWER=FINDING_ANSWER, RJ_RECORD=record, RJ_LOADED=os.path.join(base, "loaded"))
    proc = subprocess.run(
        [sys.executable, "-c", IMPORT_PROBE, MODULE_PATH],
        input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=60, env=env, cwd=base,
    )
    out, mark, tail = proc.stdout.rpartition("PROBE ")
    if not mark:
        raise RuntimeError("the probe did not finish: %s" % proc.stderr[-300:])
    return out, json.loads(tail), os.path.exists(record)


def case_ignored_stop_imports_no_guard_family_module():
    rows = [("stop_hook_active", {"session_id": REPLY_SESSION, "stop_hook_active": True,
                                  "last_assistant_message": MARK})]
    for text in EMPTY_REPLIES:
        payload = {"session_id": REPLY_SESSION, "stop_hook_active": False}
        if text is not ABSENT:
            payload["last_assistant_message"] = text
        rows.append(("reply %r" % ("(missing)" if text is ABSENT else text), payload))
    for label, payload in rows:
        out, imported, called = probe_ignored_stop(payload)
        check("ignored Stop (%s): nothing printed, no model call" % label, out.strip() == "" and not called, out)
        check("ignored Stop (%s): no guard-family module imported" % label, imported == [],
              "imported before it had work to do: %s" % imported)


def case_sampling_skipped_stop_imports_no_guard_family_module():
    config = sample_config("skip-imports")
    seed = run_hook(MARK, answer=OK_ANSWER, config=config, session=SESSION_ALPHA)  # Stop 1, judged
    check("skip imports: Stop 1 is judged, so Stop 2 is sampled out", len(seed.calls) == 1, seed.calls)
    payload = {"session_id": SESSION_ALPHA, "stop_hook_active": False, "last_assistant_message": MARK}
    out, imported, called = probe_ignored_stop(payload, config=config)  # Stop 2, skipped
    check("skip imports: Stop 2 prints nothing and calls no model", out.strip() == "" and not called, out)
    check("skip imports: Stop 2 imports no guard-family module", imported == [],
          "imported before it had work to do: %s" % imported)


# Row tables. A row is one case body from above. A row that raises is red and names
# itself, so it cannot hide behind its table.
def run_rows(rows):
    for body in rows:
        try:
            body()
        except Exception as exc:
            check("%s: case ran" % body.__name__, False, "%s: %s" % (type(exc).__name__, exc))


def table_sampling():
    run_rows((case_sampling_judges_stops_1_6_11, case_good_write_path_judges_stops_1_6_11,
              case_skipped_stop_is_silent, case_counter_is_a_file_that_survives_between_processes))


def table_failed_write():
    run_rows((case_failed_write_does_not_freeze_the_count,
              case_write_fails_remove_ok_judges_the_next_stop))


def table_write_and_remove():
    run_rows((case_write_and_remove_both_fail_judges_the_stop,
              case_frozen_counter_judges_every_later_stop))


# --------------------------------------------------------------------------- c45
# Input Needed reports are judged on every Stop, not only the 1-in-5 sample (the label is found by
# a string match in code). A finding also writes one guard.log line. Still never blocks.

FINDING = {"ok": False, "reason": "output-never-hand-off-doable-step: name the reason and the check."}
IN_BOLD = "**Input Needed**\n- Delete the two test App IDs on developer.apple.com."
IN_PLAIN = "Done: shipped the change.\nInput Needed: delete the two test App IDs on developer.apple.com"
NO_IN = "Done: shipped the change.\nNext: open the follow-up lane."


def second_stop(text, answer=OK_ANSWER, label="c45", session="c45-session", fail_log=False):
    """Stop 1 is a sample Stop with a plain reply; the returned run is Stop 2, which is not."""
    config = sample_config(label)
    run_hook(MARK, answer=OK_ANSWER, config=config, session=session)
    if fail_log:  # a directory where guard.log would go: every append fails
        os.makedirs(os.path.join(config, "guard.log"), exist_ok=True)
    return run_hook(text, answer=answer, config=config, session=session), config


def case_input_needed_label_is_judged_off_sample():
    for label, text in (("bold", IN_BOLD), ("plain", IN_PLAIN)):
        run, _ = second_stop(text, label="c45-in-" + label)
        check("input needed (%s): Stop 2 calls the model once" % label, len(run.calls) == 1, run.calls)
        check("input needed (%s): exit 0" % label, run.code == 0, run.code)


def case_no_input_needed_off_sample_is_not_judged():
    run, _ = second_stop(NO_IN, answer=json.dumps(FINDING), label="c45-none")
    check("no Input Needed label: Stop 2 never calls the model", not run.calls, run.calls)
    check("no Input Needed label: Stop 2 is silent", run.out == "" and run.code == 0, (run.code, run.out))


def case_label_forms_judged_and_non_labels_not():
    judged = {
        "quoted lower-case": "Done: x.\n> **Input needed:**\n> - Delete the test App IDs.",
        "colon inside bold": "Done: x.\n**Input Needed:** delete the test App IDs.",
    }
    for name, text in judged.items():
        run, _ = second_stop(text, label="c45-form-" + name.split()[0])
        check("label form (%s): judged off-sample" % name, len(run.calls) == 1, run.calls)
    not_judged = {
        "prose mention": "Done: x.\nThe Input Needed section is below the fold in the old layout.",
        "none inline": "Done: x.\n**Input Needed:** none",
        "none on next line": "Done: x.\n> **Input Needed**\n> None.\n> **Next**\n> Go on.",
        "empty": "Done: x.\n**Input Needed**\n\n**Next**\nGo on.",
    }
    for name, text in not_judged.items():
        run, _ = second_stop(text, label="c45-non-" + name.split()[0] + name[-2:])
        check("not a label hand-off (%s): not judged off-sample" % name, not run.calls, run.calls)


def case_prompt_asks_for_reason_and_check():
    run = run_hook(IN_BOLD, answer=OK_ANSWER)
    sentences = re.split(r"[.\n]", run.prompt().split("\n\nReply:\n")[0])
    check("prompt: one sentence ties Input Needed to a reason and a check",
          any(all(w in s for w in ("Input Needed", "reason", "check")) for s in sentences), run.prompt()[:400])


def guard_lines(config):
    path = os.path.join(config, "guard.log")
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [l for l in f.read().split("\n") if l]


def case_finding_writes_one_guard_log_line():
    # Line shape: <iso time> TAB Stop TAB noted TAB <rule id> TAB stop=<n> <reason> TAB <session>.
    # Decision "noted" is one the reader counts; the rule is the first known rule id the reason
    # names, else "reply-judge".
    run, config = second_stop(IN_BOLD, answer=json.dumps(FINDING), label="c45-log")
    lines = guard_lines(config)
    check("guard.log: one line for the finding", len(lines) == 1, lines)
    line = lines[0] if lines else ""
    parts = line.split("\t")
    check("guard.log: six tab fields", len(parts) == 6, parts)
    if len(parts) == 6:
        check("guard.log: tool Stop, decision noted", parts[1:3] == ["Stop", "noted"], parts)
        check("guard.log: rule is the id the reason names", parts[3] == "output-never-hand-off-doable-step", parts)
        check("guard.log: matched carries the Stop number", "stop=2" in parts[4].split(), parts)
        check("guard.log: session is the last field", parts[5] == "c45-session", parts)
    sys.path.insert(0, os.path.join(REPO_ROOT, "lint"))
    import guard_log_report
    row = guard_log_report.parse_line(line) if line else None
    check("guard.log: lint/guard_log_report.parse_line reads it",
          row is not None and row.decision == "noted" and row.session == "c45-session"
          and row.rule == "output-never-hand-off-doable-step", row)
    check("guard.log: finding still goes out as additionalContext, exit 0",
          run.code == 0 and parse_stdout(run) is not None, (run.code, run.out))


def case_finding_without_known_rule_logs_the_judge_id():
    run, config = second_stop(IN_BOLD, answer=json.dumps({"ok": False, "reason": "fix it"}), label="c45-log2")
    parts = (guard_lines(config) or [""])[0].split("\t")
    check("guard.log: no rule named, rule is reply-judge", len(parts) == 6 and parts[3] == "reply-judge", parts)


def case_ok_verdict_writes_no_guard_log_line():
    _, config = second_stop(IN_BOLD, answer=OK_ANSWER, label="c45-ok")
    check("guard.log: ok true writes nothing", guard_lines(config) == [], guard_lines(config))


def case_guard_log_failure_fails_open():
    good, _ = second_stop(IN_BOLD, answer=json.dumps(FINDING), label="c45-fo-a", session="c45-fo")
    bad, _ = second_stop(IN_BOLD, answer=json.dumps(FINDING), label="c45-fo-b", session="c45-fo", fail_log=True)
    check("guard.log failure: exit code unchanged", bad.code == good.code == 0, (good.code, bad.code))
    check("guard.log failure: stdout unchanged and a note", bad.out == good.out and parse_stdout(bad) is not None,
          (good.out, bad.out))


def case_input_needed_finding_never_blocks():
    run, _ = second_stop(IN_PLAIN, answer=json.dumps(FINDING), label="c45-nb")
    out = parse_stdout(run)
    check("never blocks: exit 0, no decision block, note is additionalContext",
          run.code == 0 and isinstance(out, dict) and "decision" not in out
          and out.get("hookSpecificOutput", {}).get("additionalContext") == FINDING["reason"], (run.code, run.out))


# --------------------------------------------------------------------------- c93
# style-table-gold-column: a comparison table carries a column for what good looks like. Code
# finds a Markdown table (a separator row such as |---|---|) and judges that Stop off-sample; the
# model decides whether the table compares and whether a gold-standard column is there.

TABLE_RULE = "style-table-gold-column"
TABLE_REPLY = (
    "Two hooks compared.\n\n| Hook | Runs per day |\n|---|---:|\n| guard | 400 |\n| judge | 80 |\n"
)
PIPES_NO_TABLE = "Done: x.\nThe guard reads `a | b` and the judge reads `c | d`."


def case_table_reply_is_judged_off_sample():
    run, _ = second_stop(TABLE_REPLY, label="c93-table", session="c93-session")
    check("table: Stop 2 calls the model once", len(run.calls) == 1, run.calls)
    check("table: exit 0", run.code == 0, run.code)


def case_pipes_without_table_not_judged_off_sample():
    run, _ = second_stop(PIPES_NO_TABLE, label="c93-pipes", session="c93-pipes-session")
    check("pipes with no separator row: Stop 2 never calls the model", not run.calls, run.calls)


def case_prompt_asks_for_gold_column():
    run = run_hook(TABLE_REPLY, answer=OK_ANSWER)
    sentences = rule_sentences(run, TABLE_REPLY)
    check("prompt: names %s before the reply" % TABLE_RULE, any(TABLE_RULE in s for s in sentences),
          run.prompt()[:300])
    check("prompt: a sentence ties a comparison table to a gold-standard or target column",
          has_pin(sentences, ("table",), ("compar",), ("gold", "target"), ("column",)), sentences)


# --------------------------------------------------------------------------- c102
# questions-go-to-owner: a question whose pick can be undone is taken, not asked. Code already
# judges every Input Needed Stop; the model reads whether an item's pick can be undone and, if it
# can, notes it. A pick that cannot be undone, or that changes the owner's goal, is never noted.

ASK_RULE = "questions-go-to-owner"
UNDOABLE_ASK = (
    "Done: built the waiting page.\n"
    "Input Needed: link the waiting page now with a folder move, or later? Later changes nothing.\n"
)
UNDOABLE_FINDING = {"ok": False, "reason": ASK_RULE + ": the pick can be undone; take it and name it under Done."}


def case_undoable_pick_question_is_judged_off_sample():
    run, _ = second_stop(UNDOABLE_ASK, label="c102-judged", session="c102-judged")
    check("undoable pick: Stop 2 calls the model once", len(run.calls) == 1, run.calls)


def case_prompt_notes_an_undoable_pick():
    run = run_hook(UNDOABLE_ASK, answer=OK_ANSWER)
    sentences = rule_sentences(run, UNDOABLE_ASK)
    check("prompt: names %s before the reply" % ASK_RULE, any(ASK_RULE in s for s in sentences),
          run.prompt()[:300])
    check("prompt: a sentence flags an Input Needed pick that can be undone",
          has_pin(sentences, ("input needed",), ("undo",), ("flag",)), sentences)
    check("prompt: a sentence says the session takes the pick and names it under Done",
          has_pin(sentences, ("take",), ("done",)), sentences)


def case_prompt_spares_irreversible_and_goal_picks():
    run = run_hook(UNDOABLE_ASK, answer=OK_ANSWER)
    sentences = rule_sentences(run, UNDOABLE_ASK)
    check("prompt: never flag a pick that cannot be undone",
          has_pin(sentences, ("never flag",), ("cannot be undone",)), sentences)
    check("prompt: never flag a pick that changes the owner's goal",
          has_pin(sentences, ("never flag",), ("goal",)), sentences)
    check("prompt: never flag work in another repo",
          has_pin(sentences, ("never flag",), ("another repo", "other repo")), sentences)
    check("prompt: never flag a pick another rule keeps for the owner's grant",
          has_pin(sentences, ("never flag",), ("rule",), ("grant",)), sentences)


def case_undoable_pick_finding_logs_its_rule():
    run, config = second_stop(UNDOABLE_ASK, answer=json.dumps(UNDOABLE_FINDING), label="c102-log",
                              session="c102-log")
    parts = (guard_lines(config) or [""])[0].split("\t")
    check("guard.log: rule is %s" % ASK_RULE, len(parts) == 6 and parts[3] == ASK_RULE, parts)
    out = parse_stdout(run)
    check("undoable pick: a note, never a block, exit 0",
          run.code == 0 and isinstance(out, dict) and "decision" not in out
          and out.get("hookSpecificOutput", {}).get("additionalContext") == UNDOABLE_FINDING["reason"],
          (run.code, run.out))


# --------------------------------------------------------------------------- c148
# A port or redesign keeps the existing app's behaviour. A reply that marks work "blocked on", or an
# Input Needed item as blocking, a question about such a port is flagged, since the existing app
# answers it. A question that says how the work departs, with a "Departs from:" line, and is not
# marked blocking, is never flagged. Code sends every "blocked on" Stop to the model, off-sample.

PORT_BLOCKED = ("Plan: blocked on what happens to Suspense cards when Card in Hand closes "
                "(Duo port of the web app).")
PORT_FINDING = {"ok": False, "reason": ASK_RULE + ": the web app answers it; read it and cite file and symbol."}


def case_blocked_on_reply_is_judged_off_sample():
    run, _ = second_stop(PORT_BLOCKED, label="c148-judged", session="c148-judged")
    check("blocked on: Stop 2 calls the model once", len(run.calls) == 1, run.calls)
    run, _ = second_stop("Plan: BLOCKED ON the answer.", label="c148-case", session="c148-case")
    check("blocked on: the words are read in any case", len(run.calls) == 1, run.calls)
    run, _ = second_stop("Plan: the work is blocking nothing; unblocked and moving.", label="c148-none",
                         session="c148-none")
    check("blocked on: a reply without the words is not judged off-sample", len(run.calls) == 0, run.calls)
    run, _ = second_stop("Plan: the test went green, unblocked on retry.", label="c148-unblocked",
                         session="c148-unblocked")
    check("blocked on: unblocked on retry is not judged off-sample", len(run.calls) == 0, run.calls)


def case_prompt_flags_a_port_question_marked_blocking():
    run = run_hook(PORT_BLOCKED, answer=OK_ANSWER)
    sentences = rule_sentences(run, PORT_BLOCKED)
    check("prompt: a sentence flags work blocked on a question about a port or redesign of an existing app",
          has_pin(sentences, ("flag",), ("blocked on",), ("port",), ("redesign",), ("existing app",)),
          sentences)
    check("prompt: a sentence flags an Input Needed item marked blocking on such a question",
          has_pin(sentences, ("flag",), ("input needed",), ("blocking",), ("port",)), sentences)
    check("prompt: a sentence says the existing app's behaviour answers it",
          has_pin(sentences, ("existing app",), ("behaviour",), ("answer",)), sentences)
    check("prompt: a sentence flags a port question with no Departs from line",
          has_pin(sentences, ("flag",), ("port",), ("departs from:",)), sentences)


def case_prompt_spares_a_departure_not_marked_blocking():
    run = run_hook(PORT_BLOCKED, answer=OK_ANSWER)
    sentences = rule_sentences(run, PORT_BLOCKED)
    check("prompt: never flag a question that says how the work departs and is not marked blocking",
          has_pin(sentences, ("never flag",), ("departs",), ("not marked blocking", "not blocking")),
          sentences)
    check("prompt: the never-flag-a-merge exemption stays",
          has_pin(sentences, ("never flag",), ("merge",)), sentences)


def case_port_finding_is_a_note_with_its_rule():
    run, config = second_stop(PORT_BLOCKED, answer=json.dumps(PORT_FINDING), label="c148-log",
                              session="c148-log")
    parts = (guard_lines(config) or [""])[0].split("\t")
    out = parse_stdout(run)
    check("port finding: guard.log rule is %s" % ASK_RULE, len(parts) == 6 and parts[3] == ASK_RULE, parts)
    check("port finding: a note, never a block, exit 0",
          run.code == 0 and isinstance(out, dict) and "decision" not in out
          and out.get("hookSpecificOutput", {}).get("additionalContext") == PORT_FINDING["reason"],
          (run.code, run.out))


# --------------------------------------------------------------------------- d9
# A pick between visual options needs a picture of each option in the reply. A reply that asks the
# owner to pick and only links to the mockups (a folder, a repo or a file) is flagged.

LINK_ONLY_ASK = (
    "Done: drew three layouts for the price history.\n"
    "Input Needed: pick where a card's price history shows, A, B or C. The three mockups are in "
    "https://github.com/shivinate7/banchi/tree/main/docs/mockups/price-history\n"
)


def case_prompt_flags_a_visual_pick_that_only_links():
    run = run_hook(LINK_ONLY_ASK, answer=OK_ANSWER)
    sentences = rule_sentences(run, LINK_ONLY_ASK)
    check("prompt: a sentence flags a pick between visual options that only links to them",
          has_pin(sentences, ("flag",), ("visual", "look"), ("link",), ("folder", "repo", "file")), sentences)
    check("prompt: a sentence names the exception, a pointer to the waiting-page item that carries the designs",
          has_pin(sentences, ("waiting",), ("item",), ("design",), ("never flag", "fine", "not a breach")), sentences)
    check("prompt: a sentence says each option needs its own picture",
          has_pin(sentences, ("picture", "image", "design"), ("each option", "every option")), sentences)


CASES = (
    case_stop_hook_active_never_calls_model,
    case_ignored_stop_imports_no_guard_family_module,
    case_sampling_skipped_stop_imports_no_guard_family_module,
    case_model_ok_is_silent,
    case_model_is_haiku_at_xhigh,
    case_model_finding_emits_note_not_block,
    case_finding_without_reason_is_still_a_note,
    case_model_failure_fails_open,
    case_timeout_leaks_no_reply_text,
    case_prompt_carries_reply_and_rules,
    case_owner_step_in_prose_prompt_asks_for_fenced_block,
    case_owner_step_block_outside_report_prompt_says_where,
    case_owner_step_carve_outs_in_prompt,
    case_limits_narration_prompt_flags_it,
    case_limits_blocked_work_prompt_passes_it,
    case_limits_dropped_item_prompt_passes_it,
    case_limits_done_result_line_is_not_narration,
    case_limits_verdict_outside_done_is_not_narration,
    case_child_cannot_retrigger_hook,
    case_settings_reply_judge_is_async_and_report_gate_is_not,
    table_sampling,
    case_sessions_keep_separate_counters,
    case_damaged_counter_fails_open,
    case_counter_write_failure_never_blocks,
    table_failed_write,
    case_empty_stop_writes_nothing_and_counts_nothing,
    case_empty_stops_between_replies_do_not_shift_samples,
    table_write_and_remove,
    case_input_needed_label_is_judged_off_sample,
    case_no_input_needed_off_sample_is_not_judged,
    case_label_forms_judged_and_non_labels_not,
    case_prompt_asks_for_reason_and_check,
    case_finding_writes_one_guard_log_line,
    case_finding_without_known_rule_logs_the_judge_id,
    case_ok_verdict_writes_no_guard_log_line,
    case_guard_log_failure_fails_open,
    case_input_needed_finding_never_blocks,
    case_table_reply_is_judged_off_sample,
    case_pipes_without_table_not_judged_off_sample,
    case_prompt_asks_for_gold_column,
    case_undoable_pick_question_is_judged_off_sample,
    case_prompt_notes_an_undoable_pick,
    case_prompt_spares_irreversible_and_goal_picks,
    case_undoable_pick_finding_logs_its_rule,
    case_prompt_flags_a_visual_pick_that_only_links,
    case_blocked_on_reply_is_judged_off_sample,
    case_prompt_flags_a_port_question_marked_blocking,
    case_prompt_spares_a_departure_not_marked_blocking,
    case_port_finding_is_a_note_with_its_rule,
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
