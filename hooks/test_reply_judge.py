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

Route-row cases give each run its own rows file and point GUARD_ROUTE_ROWS at it, so no run reads the
repo's rows file. The stub logs each read of that file in the hook process to RJ_OPENS.
"""
import json
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO_ROOT, "lint"))
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per test run (lint/_test_temp.py)
import cost_probe  # noqa: E402  the shared cost counters (testing/cost_probe.py)

MODULE_PATH = os.environ.get("REPLY_JUDGE_UNDER_TEST") or os.path.join(HERE, "reply_judge.py")
SETTINGS_PATH = os.environ.get("SETTINGS_UNDER_TEST") or os.path.join(REPO_ROOT, "settings.json")
ROOT = _test_temp.run_folder()
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
    if os.environ.get("RJ_SPAWNS"):
        # The claude answer is a process start too. The spy below sees every other start in Popen.
        with open(os.environ["RJ_SPAWNS"], "a", encoding="utf-8") as f:
            f.write(json.dumps({"argv": list(argv)}) + "\\n")
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
    if scenario == "doable_if_shown":
        # A judge can name a doable route only from a row the prompt carries: the answer comes back only
        # when the prompt holds the marker id RJ_DOABLE_ID, else the judge answers ok.
        marker = os.environ.get("RJ_DOABLE_ID") or ""
        if marker and marker in (stdin or ""):
            return subprocess.CompletedProcess(argv, 0, json.dumps({"result": os.environ.get("RJ_ANSWER", "")}), "")
        return subprocess.CompletedProcess(argv, 0, json.dumps({"result": json.dumps({"ok": True})}), "")
    if scenario == "timeout":
        raise subprocess.TimeoutExpired(argv, kwargs.get("timeout"))
    if scenario == "error":
        return subprocess.CompletedProcess(argv, 1, "", "first stderr line\\nsecond stderr line\\n")
    if scenario == "nonjson_envelope":
        return subprocess.CompletedProcess(argv, 0, "this is not json", "")
    if scenario == "nojson_answer":
        return subprocess.CompletedProcess(argv, 0, json.dumps({"result": "Looks fine to me."}), "")
    return subprocess.CompletedProcess(argv, 0, json.dumps({"result": os.environ.get("RJ_ANSWER", "")}), "")


if os.environ.get("RJ_OPENS"):
    # A spy on reads of the route rows file, in the hook process only. It logs each open of that file to
    # RJ_OPENS, a file of its own, so the calls record stays the record of model calls alone.
    import builtins
    _real_open = builtins.open
    _rows_env = os.environ.get("GUARD_ROUTE_ROWS") or ""

    def _spy_open(file, *args, **kwargs):
        if isinstance(file, (str, bytes, os.PathLike)):
            name = os.fsdecode(file)
            if os.path.basename(name) == "route_rows.json" or (
                    _rows_env and os.path.abspath(name) == os.path.abspath(_rows_env)):
                with _real_open(os.environ["RJ_OPENS"], "a", encoding="utf-8") as f:
                    f.write(json.dumps({"opened": name}) + "\\n")
        return _real_open(file, *args, **kwargs)

    builtins.open = _spy_open

with open(os.environ["RJ_LOADED"], "w", encoding="utf-8") as f:
    f.write("loaded")
if os.environ.get("RJ_SPAWNS"):
    # A spy on each process start in the hook process: every subprocess.Popen (subprocess.run calls it) and
    # every os.system. Each start writes one line to RJ_SPAWNS, so a case reads how many starts a Stop made.
    _real_popen = subprocess.Popen
    _real_system = os.system

    def _log_start(argv):
        with open(os.environ["RJ_SPAWNS"], "a", encoding="utf-8") as f:
            f.write(json.dumps({"argv": argv}) + "\\n")

    class _SpyPopen(_real_popen):
        def __init__(self, args, *rest, **kwargs):
            _log_start(list(args) if isinstance(args, (list, tuple)) else [str(args)])
            super().__init__(args, *rest, **kwargs)

    def _spy_system(command):
        _log_start(["os.system", str(command)])
        return _real_system(command)

    subprocess.Popen = _SpyPopen
    os.system = _spy_system
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
        self.opens = []  # each read of the route rows file in the hook process, from the stub's spy
        opened = os.path.join(base, "opens.jsonl")
        if os.path.exists(opened):
            with open(opened, encoding="utf-8") as f:
                self.opens = [json.loads(line) for line in f if line.strip()]

    def prompt(self):
        # The prompt travels on the child's stdin, never in argv (Windows caps a command line).
        return (self.calls[0].get("stdin") or "") if self.calls else ""


MISSING_ROWS = object()  # the rows file is absent: GUARD_ROUTE_ROWS names a path that does not exist


def run_hook(text, scenario="ok", answer="", stop_active=False, config=None, session=REPLY_SESSION,
             fail_replace=False, fail_remove=False, rows=MISSING_ROWS, doable="", surface="local"):
    """One Stop, one new process. With no `config`, the config dir is fresh and empty, so the
    Stop is the session's first. A shared `config` carries the counter from Stop to Stop.
    `text` may be ABSENT: the payload then has no last_assistant_message key at all.
    `fail_replace` makes every os.replace in the hook process raise (a fake write failure).
    `fail_remove` makes os.remove raise on a counter file (a fake read-only counter).
    `rows` is the route rows file: a list of rows written as {"rows": [...]}, or MISSING_ROWS for no
    file. The path always comes from GUARD_ROUTE_ROWS, so no run reads the repo's own rows file.
    `doable` is the id the "doable_if_shown" stub looks for in the prompt.
    `surface` is "local" (the default: CLAUDE_CODE_REMOTE is unset) or "cloud" (CLAUDE_CODE_REMOTE is "true")."""
    RUNS[0] += 1
    base = os.path.join(ROOT, "run-%03d" % RUNS[0])
    os.makedirs(base, exist_ok=True)
    if config is None:
        config = os.path.join(base, "config")
    os.makedirs(config, exist_ok=True)  # empty on first use: no settings, hooks, credential or token
    rows_file = os.path.join(base, "route_rows.json")
    if rows is not MISSING_ROWS:
        write_rows(rows_file, rows)
    env = dict(os.environ)
    for name in ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY", "CLAUDE_CODE_REMOTE"):
        env.pop(name, None)
    if surface == "cloud":
        env["CLAUDE_CODE_REMOTE"] = "true"  # guard_core.is_cloud reads exactly this
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
        RJ_DOABLE_ID=doable,
        RJ_RECORD=os.path.join(base, "calls.jsonl"),
        RJ_LOADED=os.path.join(base, "loaded"),
        RJ_OPENS=os.path.join(base, "opens.jsonl"),
        GUARD_ROUTE_ROWS=rows_file,
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
# stub here, so a canned {"ok": false} on a prose-step reply would pass the case too and prove
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


# --------------------------------------------------------------------------- case 5b, the gh login
# The gh login clause of output-never-hand-off-doable-step: a gh command left to the owner opens its
# block (after any cd) with `gh auth switch -u <login>`. The default login is shivinate7; the fallback
# only where the default has no access. This is a text pin on a model prompt, so it is weak: it shows
# the prompt names the switch, not that the judge flags a block that has none.

GH_STEP = (  # a gh command left to the owner, with no switch in its block
    "> **Done**\n> Input Needed: a branch-protection change on claude-settings main needs admin.\n\n"
    "Run this in Git Bash:\n\n"
    "```bash\ncd ~/claude-settings\n"
    "gh api -X PATCH repos/shivinate7/claude-settings/branches/main/protection/required_status_checks -f strict=true\n"
    "```\n"
)


def case_owner_gh_step_prompt_names_the_login_switch():
    sentences = run_owner_step_reply("gh login", GH_STEP)
    check("owner step, gh login: a sentence says a gh command left to the owner opens with gh auth switch and the default login",
          has_pin(sentences, ("gh auth switch",), ("shivinate7",)), sentences)


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
# report guard Stop entry is not async: it still blocks. Each entry is found by its script path.

def stop_hooks_running(script):
    with open(SETTINGS_PATH, encoding="utf-8") as f:
        settings = json.load(f)
    found = []
    for entry in (settings.get("hooks") or {}).get("Stop") or []:
        for hook in entry.get("hooks") or []:
            if script in str(hook.get("command", "")):
                found.append(hook)
    return found


def case_settings_reply_judge_is_async_and_report_guard_is_not():
    try:
        judge = stop_hooks_running("hooks/reply_judge.py")
        guard = stop_hooks_running("lint/report_guard.py")
    except (OSError, ValueError) as exc:
        check("settings: settings.json reads as JSON", False, "%s: %s" % (type(exc).__name__, exc))
        return
    check("settings: exactly one reply_judge Stop hook", len(judge) == 1, judge)
    check("settings: reply_judge Stop hook has async true",
          len(judge) == 1 and judge[0].get("async") is True, judge)
    check("settings: exactly one report_guard Stop hook", len(guard) == 1, guard)
    check("settings: report_guard Stop hook is not async",
          len(guard) == 1 and guard[0].get("async") is not True, guard)


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


def probe_ignored_stop(payload, config=None, starts=None, answer=FINDING_ANSWER):
    """Return (the hook's stdout, the GUARD_FAMILY modules its process imported, the model calls).
    The model is the stub, so a Stop that is wrongly judged reaches no real claude. A shared
    `config` carries the sampling counter from an earlier Stop. A list passed as `starts` is filled
    with one entry per process start in the hook process (the stub's spy); None leaves the spy off.
    `answer` is the stub's answer, so a judged Stop with an ok answer writes no guard.log line."""
    RUNS[0] += 1
    base = os.path.join(ROOT, "probe-%03d" % RUNS[0])
    config = config or os.path.join(base, "config")
    os.makedirs(base, exist_ok=True)
    os.makedirs(config, exist_ok=True)
    record = os.path.join(base, "calls.jsonl")
    spawns = os.path.join(base, "spawns.jsonl")
    env = dict(os.environ, CLAUDE_CONFIG_DIR=config, PYTHONPATH=STUB_DIR, RJ_SCENARIO="",
               RJ_ANSWER=answer, RJ_RECORD=record, RJ_LOADED=os.path.join(base, "loaded"))
    if starts is None:
        env.pop("RJ_SPAWNS", None)
    else:
        env["RJ_SPAWNS"] = spawns
    proc = subprocess.run(
        [sys.executable, "-c", IMPORT_PROBE, MODULE_PATH],
        input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=60, env=env, cwd=base,
    )
    out, mark, tail = proc.stdout.rpartition("PROBE ")
    if not mark:
        raise RuntimeError("the probe did not finish: %s" % proc.stderr[-300:])
    if starts is not None and os.path.exists(spawns):
        with open(spawns, encoding="utf-8") as f:
            starts.extend(json.loads(line) for line in f if line.strip())
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


# --------------------------------------------------------------------------- c139
# Uniform ruling (topic t18): a repo that differs from a shared format changes to match, and the
# shared tool never grows a second form. An option that widens what a shared tool accepts carries
# "Goes against your ruling: a repo changes to fit a shared tool, never the tool to fit a repo" and is never
# the recommended option. Rule
# `style-question-form` holds that text (the one question form, hooks/question_form.py).

WIDENS_RULE = "style-question-form"
WIDENS_ASK = (
    "Done: read banchi's record titles.\n"
    "Input Needed: pick A or B. A: let the stamp accept banchi's titles. B: rename banchi's titles. "
    "I recommend A.\n"
)
WIDENS_FINDING = {"ok": False, "reason": WIDENS_RULE + ": A widens a shared tool; label it and recommend B."}
COUNT_WORDS = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")


def judged_rules():
    import ast
    with open(MODULE_PATH, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "JUDGED_RULES" for t in node.targets):
            return ast.literal_eval(node.value)
    return ()


def case_prompt_count_matches_judged_rules():
    run = run_hook(WIDENS_ASK, answer=OK_ANSWER)
    head = run.prompt().split(WIDENS_ASK, 1)[0]
    rules = judged_rules()
    check("rule count: JUDGED_RULES holds %s" % WIDENS_RULE, WIDENS_RULE in rules, rules)
    m = re.search(r"against (\w+) rules", head)
    word = COUNT_WORDS[len(rules) - 1] if 0 < len(rules) <= len(COUNT_WORDS) else "?"
    check("rule count: the prompt's count word is %s" % word, bool(m) and m.group(1) == word, head[:120])
    check("rule count: the prompt names each judged rule with a colon",
          all(r + ":" in head for r in rules), [r for r in rules if r + ":" not in head])
    with open(MODULE_PATH, encoding="utf-8") as f:
        first = f.read().split("\n", 2)[1]
    check("rule count: the docstring's count word is %s" % word, ("against %s rules" % word) in first, first[:120])


def case_prompt_flags_a_recommended_option_that_widens():
    run = run_hook(WIDENS_ASK, answer=OK_ANSWER)
    sentences = rule_sentences(run, WIDENS_ASK)
    check("prompt: a sentence flags a recommended option that widens what a shared tool accepts",
          has_pin(sentences, ("flag",), ("recommend",), ("widen",), ("shared tool",)), sentences)
    check("prompt: a sentence flags such an option offered without its label",
          has_pin(sentences, ("flag",), ("widen",),
                  ("goes against your ruling: a repo changes to fit a shared tool, never the tool to fit a repo",)),
          sentences)
    check("prompt: a sentence spares an option where the repo changes to match",
          has_pin(sentences, ("never flag",), ("repo",), ("match",)), sentences)
    check("prompt: a sentence judges only offered options and spares a reply that describes the rule",
          has_pin(sentences, ("judge only",), ("options",), ("offers",)), sentences)
    check("prompt: a sentence never flags a reply that describes the rule itself",
          has_pin(sentences, ("never flag",), ("describes the rule",)), sentences)


# Roadmap c135, item 31's shape: options that can all be done together, asked as pick-one. The prompt
# flags it and says to ask it as a multi-select item (`multi: true`). Options that exclude each other,
# such as now or later, stay a pick-one question.
COMBINE_ASK = (
    "Done: read the waiting page.\n"
    "Input Needed: pick A, B or C. A: add rank buttons to the page. B: add picture cards to the page. "
    "C: add a keyboard shortcut to the page. I recommend A.\n"
)


def case_prompt_flags_a_pick_one_question_whose_options_could_combine():
    run = run_hook(COMBINE_ASK, answer=OK_ANSWER)
    sentences = rule_sentences(run, COMBINE_ASK)
    check("prompt: the prompt carries the reply", COMBINE_ASK in run.prompt(), run.prompt()[:300])
    check("prompt: a sentence flags a pick-one question whose options could combine and names multi-select",
          has_pin(sentences, ("flag",), ("pick-one", "pick one"), ("combine",), ("multi: true", "multi-select")),
          sentences)
    check("prompt: a sentence never flags options that exclude each other",
          has_pin(sentences, ("never flag",), ("exclude",)), sentences)
    check("prompt: the prompt judges against nine rules",
          has_pin(sentences, ("against nine rules",)), sentences[:2])


def case_widens_finding_logs_its_rule():
    run, config = second_stop(WIDENS_ASK, answer=json.dumps(WIDENS_FINDING), label="c139-log",
                              session="c139-log")
    parts = (guard_lines(config) or [""])[0].split("\t")
    out = parse_stdout(run)
    check("widens finding: guard.log rule is %s" % WIDENS_RULE, len(parts) == 6 and parts[3] == WIDENS_RULE, parts)
    check("widens finding: a note, never a block, exit 0",
          run.code == 0 and isinstance(out, dict) and "decision" not in out
          and out.get("hookSpecificOutput", {}).get("additionalContext") == WIDENS_FINDING["reason"],
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


# --------------------------------------------------------------------------- c164
# A session answers a waiting-page comment by rewriting the item, never by a comment-thread reply:
# a rebuilt page drops its threads (decision questions-go-to-owner, "Answer on the page, not in a
# comment thread").

THREAD_REPLY = (
    "Done: read the owner's comment on waiting-page item 27 and replied on the thread with the "
    "reason for option B.\n"
)


def case_prompt_flags_a_thread_reply_to_a_waiting_page_comment():
    run = run_hook(THREAD_REPLY, answer=OK_ANSWER)
    sentences = rule_sentences(run, THREAD_REPLY)
    check("prompt: a sentence flags a waiting-page comment answered in a comment thread",
          has_pin(sentences, ("flag",), ("waiting-page", "waiting page"), ("comment",), ("thread",)),
          sentences)
    check("prompt: a sentence says the session rewrites the item instead",
          has_pin(sentences, ("thread",), ("rewrit",), ("item",)), sentences)


def case_prompt_spares_a_reply_that_rewrote_the_item():
    run = run_hook(THREAD_REPLY, answer=OK_ANSWER)
    sentences = rule_sentences(run, THREAD_REPLY)
    check("prompt: never flag a reply that says it rewrote or updated the waiting-page item",
          has_pin(sentences, ("never flag",), ("rewrote", "updated"), ("item",)), sentences)
    check("prompt: the thread-reply example names the waiting-page thread",
          has_pin(sentences, ("flag",), ("replied on the waiting-page thread",)), sentences)
    check("prompt: never flag a reply in a PR review thread or on another artifact",
          has_pin(sentences, ("never flag",), ("pr review thread",), ("another artifact",)), sentences)


# ----------------------------------------------------------- route rows (claims-carry-backing, part (v) layer (b))
# A "Why yours" line that cites `(route <id>)` puts three kinds of rows in the judge prompt: the cited row, every
# other row with its act, and every row whose act is one of the cited row's `alternates` (a list of act values,
# as the rows file holds them). A rows file that is missing or holds no rows gives the prompt it gets today. The
# fixtures: one act with a refused route and a works route, two rows in the alternate act, and one unrelated act.
# judge_row builds a row in the rows file's shape. It is not test_refusal_note.route_row: that fixture ties each
# act to its row id and sets no alternates.

ROUTE_ACT = "amend the trailer of a commit already pushed to its branch"
ALT_ACT = "rewrite the history of a branch"
OTHER_ACT = "push a commit straight to main"


def judge_row(row_id, act, route, outcome, alternates=None, surface="local"):
    row = {"id": row_id, "act": act, "route": route, "surface": surface, "outcome": outcome,
           "measured": "2026-11-05", "cc_version": "2.1.0", "evidence": "fixture transcript",
           "by": "test-author", "pattern": "fixture-" + row_id}
    if alternates is not None:
        row["alternates"] = alternates
    return row


CITED_ROW = judge_row("trailer-amend-pushed", ROUTE_ACT, "git commit --amend on the pushed branch", "refused",
                      alternates=[ALT_ACT])
SAME_ACT_ROW = judge_row("cherry-pick-to-new-branch", ROUTE_ACT, "cherry-pick to a new branch", "works")
ALT_ROW = judge_row("rebase-fixup-new-branch", ALT_ACT, "git rebase -i fixup on a new branch", "works")
ALT_ROW_B = judge_row("filter-branch-new-branch", ALT_ACT, "git filter-branch on a new branch", "works")
OTHER_ROW = judge_row("push-main-direct", OTHER_ACT, "git push origin main", "refused")
ALL_ROWS = [CITED_ROW, SAME_ACT_ROW, ALT_ROW, ALT_ROW_B, OTHER_ROW]
CITED_ID = CITED_ROW["id"]
SAME_ACT_ID = SAME_ACT_ROW["id"]

# A reply must not hand a commit's trailer to the owner as "only you can": a cherry-pick to a new
# branch carries the trailer with no refusal, so the judge flags that step as doable
# (decision claims-carry-backing).
TRAILER_REPLY = (
    "> **Done**\n> BUILT: the hook change is pushed on branch prose-truth-reply-judge-t.\n"
    "> Input Needed: commit abc1234 needs a new trailer.\n\n"
    "Why yours: only you can change your commit; check: check_red_run reads only the commit's own message "
    "(route %s).\n" % CITED_ID
)
DOABLE_ANSWER = json.dumps({"ok": False, "reason": "output-never-hand-off-doable-step: doable: cherry-pick to a "
                            "new branch (route %s)." % SAME_ACT_ID})


def write_rows(path, rows):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"rows": rows}, handle)


def reference_module():
    """The hook's module, loaded in this process, for its INSTRUCTIONS: the prompt text it builds today."""
    spec = importlib.util.spec_from_file_location("reply_judge_reference", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Scope first: each case checks the judge's one model call, then the rows it carries.

def case_route_cite_carries_cited_same_act_and_alternate_rows():
    run = run_hook(TRAILER_REPLY, answer=OK_ANSWER, rows=ALL_ROWS)
    check("route rows, cite: claude called once", len(run.calls) == 1, run.calls)
    prompt = run.prompt()
    for label, row in (("cited row", CITED_ROW), ("same-act row", SAME_ACT_ROW), ("alternate-act row", ALT_ROW),
                       ("second alternate-act row", ALT_ROW_B)):
        check("route rows, cite: the prompt carries the %s" % label,
              row["route"] in prompt and row["id"] in prompt, prompt[:300])
    check("route rows, cite: a row of another act does not ride the prompt",
          OTHER_ROW["route"] not in prompt and OTHER_ROW["id"] not in prompt, prompt[:300])


# A full rows file: 300 rows of another act. Only the rows the cite names ride the prompt.

def case_route_cite_skips_other_acts_in_a_full_rows_file():
    filler = [judge_row("filler-%03d" % n, OTHER_ACT, "filler route %03d" % n, "refused") for n in range(300)]
    run = run_hook(TRAILER_REPLY, answer=OK_ANSWER, rows=[CITED_ROW, SAME_ACT_ROW, ALT_ROW, ALT_ROW_B] + filler)
    check("full rows file: claude called once", len(run.calls) == 1, run.calls)
    prompt = run.prompt()
    check("full rows file: the same-act row rides the prompt", SAME_ACT_ROW["route"] in prompt, prompt[:300])
    check("full rows file: the alternate-act rows ride the prompt",
          ALT_ROW["route"] in prompt and ALT_ROW_B["route"] in prompt, prompt[:300])
    carried = sum(1 for n in range(300) if ("filler route %03d" % n) in prompt)
    check("full rows file: no row of another act rides the prompt", carried == 0,
          "%d filler rows in the prompt" % carried)


# The incident. The model names a doable route only when the prompt carries that route's row (the stub).
# The note it prints must name the route.

def case_trailer_hand_off_names_the_doable_route():
    run = run_hook(TRAILER_REPLY, scenario="doable_if_shown", answer=DOABLE_ANSWER, rows=ALL_ROWS,
                   doable=SAME_ACT_ID)
    check("trailer hand-off: claude called once", len(run.calls) == 1, run.calls)
    check("trailer hand-off: exit 0", run.code == 0, run.code)
    got = parse_stdout(run)
    specific = got.get("hookSpecificOutput") if got else None
    note = specific.get("additionalContext") if isinstance(specific, dict) else None
    check("trailer hand-off: the judge prints a Stop note", isinstance(note, str) and note.strip() != "",
          run.out or run.err)
    check("trailer hand-off: the note names the doable route %s" % SAME_ACT_ID,
          isinstance(note, str) and SAME_ACT_ID in note, note)


# No rows file, or a file with no rows: today's prompt, and no route text in its head. The expected prompt is
# the hook's INSTRUCTIONS with the same reply, so a route sentence added to the head fails here.

def case_no_route_rows_keeps_today_prompt():
    expected = "%s\n\nReply:\n%s" % (reference_module().INSTRUCTIONS, TRAILER_REPLY)
    for label, rows in (("rows file missing", MISSING_ROWS), ("rows file holds no rows", [])):
        run = run_hook(TRAILER_REPLY, answer=OK_ANSWER, rows=rows)
        check("no route rows (%s): claude called once" % label, len(run.calls) == 1, run.calls)
        check("no route rows (%s): the prompt is today's prompt" % label, run.prompt() == expected,
              run.prompt()[:300])
        head = run.prompt().split(TRAILER_REPLY, 1)[0]
        check("no route rows (%s): the prompt head names no route" % label, "route" not in head.lower(), head[:300])


# Cost: the rows file is read only for a reply with a Why yours line, and once per hook run. The model is
# still called once per judged reply.

def case_route_rows_are_read_once_and_only_for_a_why_yours_line():
    plain = run_hook(MARK, answer=OK_ANSWER, rows=ALL_ROWS)
    check("rows read, no Why yours: claude called once", len(plain.calls) == 1, plain.calls)
    check("rows read, no Why yours: the rows file is never read", plain.opens == [], plain.opens)
    cited = run_hook(TRAILER_REPLY, answer=OK_ANSWER, rows=ALL_ROWS)
    check("rows read, Why yours: claude called once", len(cited.calls) == 1, cited.calls)
    check("rows read, Why yours: the rows file is read once", len(cited.opens) == 1, cited.opens)


# --------------------------------------------------------------------------- route rows 2: surface, cap order, head
# Each case checks the judge's one model call first, then the rows or the block text the prompt carries.

CLOUD_ROW = judge_row("cherry-pick-cloud-only", ROUTE_ACT, "cloud-only cherry-pick route", "works", surface="cloud")


def sentences_of(text):
    """The lowercase sentences of `text`, split at a period or a line break."""
    return [s.strip() for s in re.split(r"[.\n]", text.lower()) if s.strip()]


def route_block_sentences(run, reply):
    """The sentences the prompt adds beside today's prompt: neither the hook's INSTRUCTIONS nor the reply. Where the
    block sits is not pinned, so a block before the reply and one after it read the same."""
    own = set(sentences_of(reference_module().INSTRUCTIONS)) | set(sentences_of(reply))
    return [s for s in sentences_of(run.prompt()) if s not in own]


# A cloud "works" row is no route for a local session, so it never rides a local prompt.

def case_local_session_carries_no_cloud_row():
    run = run_hook(TRAILER_REPLY, answer=OK_ANSWER, rows=ALL_ROWS + [CLOUD_ROW], surface="local")
    check("surface, local: claude called once", len(run.calls) == 1, run.calls)
    prompt = run.prompt()
    check("surface, local: the local same-act row rides the prompt", SAME_ACT_ROW["route"] in prompt, prompt[:300])
    check("surface, local: a cloud works row does not ride the prompt", CLOUD_ROW["route"] not in prompt, prompt[:300])


# The same rows in a cloud session: the cloud row rides, and the local same-act row does not.

def case_cloud_session_carries_cloud_rows_not_local_ones():
    run = run_hook(TRAILER_REPLY, answer=OK_ANSWER, rows=ALL_ROWS + [CLOUD_ROW], surface="cloud")
    check("surface, cloud: claude called once", len(run.calls) == 1, run.calls)
    prompt = run.prompt()
    check("surface, cloud: the cloud works row rides the prompt", CLOUD_ROW["route"] in prompt, prompt[:300])
    check("surface, cloud: a local row does not ride the prompt", SAME_ACT_ROW["route"] not in prompt, prompt[:300])


# Forty same-act rows come before the alternate-act rows in the file. The outcome pinned is that an alternate-act
# row still reaches the prompt, not how the cap orders the rows.

def case_alternate_act_row_survives_forty_same_act_rows():
    same = [judge_row("same-%02d" % n, ROUTE_ACT, "cherry-pick route %02d" % n, "works") for n in range(40)]
    run = run_hook(TRAILER_REPLY, answer=OK_ANSWER, rows=[CITED_ROW] + same + [ALT_ROW, ALT_ROW_B])
    check("cap order: claude called once", len(run.calls) == 1, run.calls)
    prompt = run.prompt()
    check("cap order: the cited row rides the prompt", CITED_ROW["route"] in prompt, prompt[:300])
    check("cap order: at least one alternate-act row rides the prompt",
          ALT_ROW["route"] in prompt or ALT_ROW_B["route"] in prompt, prompt[:300])


# The block must not tell the judge to flag every time. One sentence says to flag only when a works row on this
# surface covers the act.

def case_route_block_flags_only_on_a_works_row_on_this_surface():
    run = run_hook(TRAILER_REPLY, answer=OK_ANSWER, rows=ALL_ROWS)
    check("route head: claude called once", len(run.calls) == 1, run.calls)
    block = route_block_sentences(run, TRAILER_REPLY)
    check("route head: a sentence says flag only when a works row on this surface covers the act",
          has_pin(block, ("flag",), ("only", "unless", "when", " if "), ("works",), ("surface",)), block)


# --------------------------------------------------------------------------- route rows: one id, two surfaces, the cap
# The cite names one id, and two rows carry it: a local refused row and a cloud works row. Each row lists its own
# alternate act. A local session carries only its own surface's rows, so the cloud row and the works row for the
# cloud row's alternate act stay out, while the local row and the works row for the local row's alternate act ride.

SPLIT_ID = "amend-pushed-two-surfaces"
SPLIT_ACT_B = "reset a pushed branch to an older commit"  # the local row's alternate act
SPLIT_ACT_C = "delete the remote branch and push it again"  # the cloud row's alternate act
SPLIT_LOCAL = judge_row(SPLIT_ID, ROUTE_ACT, "local amend route", "refused", alternates=[SPLIT_ACT_B])
SPLIT_CLOUD = judge_row(SPLIT_ID, ROUTE_ACT, "cloud amend route", "works", alternates=[SPLIT_ACT_C],
                        surface="cloud")
SPLIT_B_WORKS = judge_row("reset-pushed-local", SPLIT_ACT_B, "local reset route", "works")
SPLIT_C_WORKS = judge_row("repush-remote-local", SPLIT_ACT_C, "local repush route", "works")


def cite_reply(route_id):
    """TRAILER_REPLY with its `(route <id>)` cite named `route_id`, so one case can cite a row of its own."""
    return TRAILER_REPLY.replace("(route %s)" % CITED_ID, "(route %s)" % route_id)


def case_shared_route_id_carries_only_its_surface_rows():
    rows = [SPLIT_LOCAL, SPLIT_CLOUD, SPLIT_B_WORKS, SPLIT_C_WORKS]
    run = run_hook(cite_reply(SPLIT_ID), answer=OK_ANSWER, rows=rows, surface="local")
    check("split id, local: claude called once", len(run.calls) == 1, run.calls)
    prompt = run.prompt()
    check("split id, local: the local row of the cited id rides the prompt", SPLIT_LOCAL["route"] in prompt,
          prompt[:300])
    check("split id, local: the works row for the local row's alternate act rides the prompt",
          SPLIT_B_WORKS["route"] in prompt, prompt[:300])
    check("split id, local: the cloud row of the cited id does not ride the prompt",
          SPLIT_CLOUD["route"] not in prompt, prompt[:300])
    check("split id, local: the works row for the cloud row's alternate act does not ride the prompt",
          SPLIT_C_WORKS["route"] not in prompt, prompt[:300])


# One act holds thirty-one refused rows, and its one works row comes last in the file. The cite names the first
# refused row. The cap holds at thirty rows, so the works row must be one of the thirty that ride: a works row
# behind a long run of refused rows of its own act is still the act's evidence for the judge.

CAP_ACT = "rename a pushed branch on the remote"
CAP_REFUSED = [judge_row("cap-refused-%02d" % n, CAP_ACT, "cap refused route %02d" % n, "refused")
               for n in range(31)]
CAP_WORKS = judge_row("cap-works", CAP_ACT, "cap works route", "works")


def case_cap_keeps_a_works_row_behind_thirty_one_refused_rows():
    run = run_hook(cite_reply(CAP_REFUSED[0]["id"]), answer=OK_ANSWER, rows=CAP_REFUSED + [CAP_WORKS],
                   surface="local")
    check("cap, one act: claude called once", len(run.calls) == 1, run.calls)
    prompt = run.prompt()
    check("cap, one act: the works row rides the prompt under the thirty-row cap",
          CAP_WORKS["route"] in prompt, prompt[:300])
    carried = prompt.count('"outcome": ')
    check("cap, one act: no more than thirty route rows ride the prompt", carried <= 30,
          "%d route rows in the prompt" % carried)


# --------------------------------------------------------------------------- counts-from-rest
# verification-counts-from-rest: a reply that quotes a GitHub search total (total_count, a search result
# count) as a count or a state is flagged. A count read from REST is not, and neither is a search used only
# to find candidates. Code finds a search total and sends that Stop to the model off-sample (SEARCH_TOTAL in
# reply_judge.py): a reply that holds `total_count`, a `search/<endpoint>` path, or the word "search" within
# 120 characters of a count word (a digit, none, zero, no), in either order. The model decides. Each leg has
# its own fixture, so a regex that drops one leg fails that leg's case alone.

SEARCH_RULE = "verification-counts-from-rest"
SEARCH_COUNT_REPLY = "Done: checked the PR list. search total_count 0: no PRs closed since 09:30."
REST_COUNT_REPLY = "Done: checked the PR list. REST pulls list: 100 closed 10:00-11:00."
CANDIDATES_REPLY = "Done: gh api search/issues found 3 candidates; each confirmed with REST: 2 closed."
SEARCH_FINDING = {"ok": False, "reason": SEARCH_RULE + ": a search total is a candidate count, not a count; "
                  "confirm each with REST."}
TOTAL_LEG = "Done: the PR list reply carried total_count and nothing else was read."  # no digit, no word search
ENDPOINT_LEG = "Done: read the rows with gh api search/%s?q=rule and kept them."  # no digit, no word search
ENDPOINTS = ("issues", "code", "commits", "repositories", "users")
WORD_LEG = "Done: a search came back with 7 rows for the rule."  # the word search, a digit after it
DIGIT_BEFORE_LEG = "Done: 7 rows came back from the search for the rule."  # a digit before it
FAR_FROM_DIGIT = ("Done: the search of the docs took a long time, because it read every page of the handbook for "
                  "the rule text and then the rule text again, and the final count of pages was 40.")  # 155 characters
RESEARCH_REPLY = "Done: the research on the rule took 3 passes."  # holds the letters search, not the word
LONG_FILLER = "Next: open the follow-up lane. " * 250  # about 8,250 characters, so the reply passes REPLY_MAX


def stop_payload(text, session=SESSION_ALPHA):
    return {"session_id": session, "stop_hook_active": False, "last_assistant_message": text}


def every_file(config):
    """Paths, relative to the config dir, of every file under it, not only under state/."""
    found = []
    for dirpath, _dirs, names in os.walk(config):
        for name in names:
            found.append(os.path.relpath(os.path.join(dirpath, name), config))
    return sorted(found)


def gap_chars(text, first, second):
    """Characters from the end of the first word to the start of the second, both found in the text."""
    return text.index(second) - (text.index(first) + len(first))


def case_search_total_reply_is_judged_off_sample():
    run, _ = second_stop(SEARCH_COUNT_REPLY, label="counts-a", session="counts-a")
    check("search total: Stop 2 exit 0", run.code == 0, run.code)
    check("search total: Stop 2 calls the model once", len(run.calls) == 1, run.calls)


def case_search_total_finding_is_a_note_logged_as_its_rule():
    run, config = second_stop(SEARCH_COUNT_REPLY, answer=json.dumps(SEARCH_FINDING), label="counts-a2",
                              session="counts-a2")
    got = parse_stdout(run)
    specific = got.get("hookSpecificOutput") if got else None
    note = specific.get("additionalContext") if isinstance(specific, dict) else None
    check("search total finding: Stop 2 prints the reason as its note", note == SEARCH_FINDING["reason"], run.out)
    check("search total finding: exit 0", run.code == 0, run.code)
    check("search total finding: never a decision block", "decision" not in (got or {}), run.out)
    lines = guard_lines(config)
    parts = lines[0].split("\t") if len(lines) == 1 else []
    check("search total finding: guard.log holds one line, with rule %s" % SEARCH_RULE,
          len(parts) == 6 and parts[3] == SEARCH_RULE, lines)


def case_rest_count_reply_is_not_judged_off_sample():
    run, _ = second_stop(REST_COUNT_REPLY, label="counts-b", session="counts-b")
    check("REST count: Stop 2 exit 0 and silent", run.code == 0 and run.out == "", (run.code, run.out))
    check("REST count: Stop 2 never calls the model", not run.calls, run.calls)


def case_search_used_for_candidates_is_judged_off_sample():
    run, _ = second_stop(CANDIDATES_REPLY, label="counts-c", session="counts-c")
    check("candidates: Stop 2 exit 0", run.code == 0, run.code)
    check("candidates: Stop 2 calls the model once, since the search/issues leg matches", len(run.calls) == 1,
          run.calls)


def case_each_search_trigger_leg_is_judged_off_sample():
    legs = [("total_count", TOTAL_LEG)]
    legs += [("search/%s" % endpoint, ENDPOINT_LEG % endpoint) for endpoint in ENDPOINTS]
    legs += [("the word search with a digit after it", WORD_LEG),
             ("the word search with a digit before it", DIGIT_BEFORE_LEG)]
    for n, (name, text) in enumerate(legs):
        run, _ = second_stop(text, label="counts-leg-%02d" % n, session="counts-leg-%02d" % n)
        check("search trigger, %s: Stop 2 calls the model once" % name, len(run.calls) == 1, run.calls)


def case_search_word_far_from_a_digit_is_not_judged_off_sample():
    # Controls: the word search with no count word within 120 characters, and a word that only holds its letters.
    gap = gap_chars(FAR_FROM_DIGIT, "search", "40")
    check("far digit: the digit sits more than 120 characters past the search word", gap > 120, gap)
    for n, (name, text) in enumerate((("a digit %d characters past the search word" % gap, FAR_FROM_DIGIT),
                                      ("research, which holds the letters search", RESEARCH_REPLY))):
        run, _ = second_stop(text, label="counts-far-%02d" % n, session="counts-far-%02d" % n)
        check("no search trigger, %s: Stop 2 never calls the model" % name, not run.calls, run.calls)


def case_long_reply_search_total_past_the_clip_is_judged():
    reply = "Done: shipped the check.\n" + LONG_FILLER + SEARCH_COUNT_REPLY + "\n" + LONG_FILLER
    module = reference_module()
    # Scope first: the reply is clipped for the prompt, and the clip cuts the search total out of it.
    check("long reply: the reply is longer than the prompt clip", len(reply) > module.REPLY_MAX, len(reply))
    check("long reply: the prompt clip cuts the search total out of the prompt",
          SEARCH_COUNT_REPLY not in module.build_prompt(reply), "the clip kept the search total")
    run, _ = second_stop(reply, label="counts-long", session="counts-long")
    check("long reply: Stop 2 calls the model once, so the trigger read the whole reply", len(run.calls) == 1,
          run.calls)


def case_prompt_flags_a_search_total_read_as_a_count():
    run = run_hook(SEARCH_COUNT_REPLY, answer=OK_ANSWER)
    sentences = rule_sentences(run, SEARCH_COUNT_REPLY)
    check("prompt: names %s with a colon before the reply" % SEARCH_RULE,
          any(SEARCH_RULE + ":" in s for s in sentences), run.prompt()[:300])
    # Each pin holds the rule id, so it reads the flag sentence and no other. SEARCH_TOTAL_PHRASES takes the old
    # wording (total_count, result count) and the new one (search total, result total) alike.
    check("prompt: a sentence flags a search total read as a count",
          has_pin(sentences, (SEARCH_RULE,), ("flag",), ("search",), SEARCH_TOTAL_PHRASES, ("count",)), sentences)
    check("prompt: a sentence flags a search total read as a state (open, closed, merged, CI status)",
          has_pin(sentences, (SEARCH_RULE,), ("flag",), ("search",), SEARCH_TOTAL_PHRASES, ("state", "status"),
                  ("open", "closed", "merged")), sentences)


def case_prompt_never_flags_a_count_read_from_rest():
    run = run_hook(REST_COUNT_REPLY, answer=OK_ANSWER)
    sentences = rule_sentences(run, REST_COUNT_REPLY)
    check("prompt: a sentence says never flag a count read from REST",
          has_pin(sentences, ("never flag",), ("rest",), ("count",)), sentences)


def case_prompt_names_the_fix_confirm_with_rest():
    run = run_hook(SEARCH_COUNT_REPLY, answer=OK_ANSWER)
    sentences = rule_sentences(run, SEARCH_COUNT_REPLY)
    check("prompt: a sentence names the fix, confirm each with REST",
          has_pin(sentences, ("confirm",), ("rest",)), sentences)


def case_prompt_never_flags_a_search_used_only_for_candidates():
    run = run_hook(CANDIDATES_REPLY, answer=OK_ANSWER)
    sentences = rule_sentences(run, CANDIDATES_REPLY)
    check("prompt: a sentence says never flag a search used only to find candidates",
          has_pin(sentences, ("never flag",), ("search",), ("candidate",)), sentences)


def case_prompt_says_nine_rules_with_the_counts_rule():
    run = run_hook(SEARCH_COUNT_REPLY, answer=OK_ANSWER)
    sentences = rule_sentences(run, SEARCH_COUNT_REPLY)
    check("nine rules: the prompt says against nine rules", has_pin(sentences, ("against nine rules",)),
          sentences[:2])
    rules = judged_rules()
    check("nine rules: JUDGED_RULES holds nine rules", len(rules) == 9, rules)
    check("nine rules: JUDGED_RULES holds %s" % SEARCH_RULE, SEARCH_RULE in rules, rules)
    with open(MODULE_PATH, encoding="utf-8") as f:
        first = f.read().split("\n", 2)[1]
    check("nine rules: the docstring says against nine rules", "against nine rules" in first, first[:120])


# Cost. A Stop that the trigger does not match starts no process and writes no file beyond the count file. Stop 1
# is judged first, so the spy is seen to record a real start before a zero count means anything.

def case_rest_count_stop_starts_no_process_and_writes_no_file():
    config = sample_config("counts-cost-rest")
    judged = []
    probe_ignored_stop(stop_payload(MARK), config=config, starts=judged, answer=OK_ANSWER)  # Stop 1, judged
    check("cost, spy: the judged Stop 1 starts one process, the claude call",
          [os.path.basename(s["argv"][0]) for s in judged] == ["claude"], judged)
    before = every_file(config)
    check("cost, count file: Stop 1 leaves the count file and nothing else", before == counter_files(config)
          and len(before) == 1, before)
    starts = []
    out, imported, called = probe_ignored_stop(stop_payload(REST_COUNT_REPLY), config=config, starts=starts)  # Stop 2
    check("cost, REST Stop 2: prints nothing and calls no model", out.strip() == "" and not called, (out, called))
    check("cost, REST Stop 2: starts no process", starts == [], starts)
    check("cost, REST Stop 2: imports no guard-family module", imported == [], imported)
    check("cost, REST Stop 2: writes no file beyond the count file", every_file(config) == before,
          every_file(config))


def case_search_total_stop_starts_only_the_judge_call():
    config = sample_config("counts-cost-search")
    probe_ignored_stop(stop_payload(MARK), config=config, starts=[], answer=OK_ANSWER)  # Stop 1, judged
    starts = []
    out, _imported, called = probe_ignored_stop(stop_payload(SEARCH_COUNT_REPLY), config=config, starts=starts,
                                                answer=OK_ANSWER)
    check("cost, search Stop 2: the model is called", called, (out, called))
    check("cost, search Stop 2: the trigger starts no process of its own, the only start is the claude call",
          [os.path.basename(s["argv"][0]) for s in starts] == ["claude"], starts)


# --------------------------------------------------------------------------- counts-from-rest: trigger words
# The off-sample trigger also takes a search word in any form (search, searched, --search), a search/<word>
# endpoint, and a count word (a digit, zero, none) within 120 characters of a search word. Each form is its own
# check, so a regex that drops one form fails that check alone. A count word with no search word is no trigger.

SEARCHED_LEG = "Done: I searched the repo and found 4 open issues."
ZERO_LEG = "Done: the search returned zero open PRs."
NONE_FLAG_LEG = "Done: gh pr list --search 'is:open' returned none."
LABELS_ENDPOINT_LEG = "Done: gh api search/labels listed the rows."  # no digit, no count word: the endpoint alone
LABELS_ENDPOINT_NONE_LEG = "Done: gh api search/labels returned none."
GH_SEARCH_DIGIT_LEG = "Done: gh search prs shows 6 open"  # a control: the digit 6 already triggers it
REST_COUNT_WORDS_REPLY = "Done: checked the PR list with REST: none open and zero closed."  # count words, no search
FAR_FROM_COUNT_WORD = ("Done: the search of the docs took a long time, because it read every page of the handbook "
                       "for the rule text and then the rule text again, and the final count of pages was zero.")
REFUTE_REPLY = ("Done: checked the PR list. REST says 4 open PRs; the search total_count of 6 includes closed ones, "
                "so it was not used.")
SEARCH_TOTAL_PHRASES = ("total_count", "total count", "search total", "result total", "result count")  # old and new


def case_searched_word_with_a_digit_is_judged_off_sample():
    run, _ = second_stop(SEARCHED_LEG, label="counts-d-searched", session="counts-d-searched")
    check("search word 'searched', with the digit 4 after it: Stop 2 calls the model once", len(run.calls) == 1,
          run.calls)


def case_search_with_a_count_word_is_judged_off_sample():
    legs = (("the count word zero", ZERO_LEG), ("the count word none, after --search", NONE_FLAG_LEG))
    for n, (name, text) in enumerate(legs):
        run, _ = second_stop(text, label="counts-d-word-%02d" % n, session="counts-d-word-%02d" % n)
        check("search with %s: Stop 2 calls the model once" % name, len(run.calls) == 1, run.calls)


def case_any_search_endpoint_is_judged_off_sample():
    legs = (("search/labels with no count word", LABELS_ENDPOINT_LEG),
            ("search/labels returned none", LABELS_ENDPOINT_NONE_LEG))
    for n, (name, text) in enumerate(legs):
        run, _ = second_stop(text, label="counts-d-endpoint-%02d" % n, session="counts-d-endpoint-%02d" % n)
        check("search endpoint, %s: Stop 2 calls the model once" % name, len(run.calls) == 1, run.calls)


def case_gh_search_with_a_digit_is_judged_off_sample():
    # A control: the old code already judges this one, by the digit 6 after the word search.
    run, _ = second_stop(GH_SEARCH_DIGIT_LEG, label="counts-d-gh", session="counts-d-gh")
    check("gh search with the digit 6: Stop 2 calls the model once", len(run.calls) == 1, run.calls)


def case_count_words_without_a_search_word_are_not_judged_off_sample():
    # A control: a REST count in count words, and no search word anywhere in the reply.
    run, _ = second_stop(REST_COUNT_WORDS_REPLY, label="counts-d-rest", session="counts-d-rest")
    check("REST count words, no search word: Stop 2 exit 0 and silent", run.code == 0 and run.out == "",
          (run.code, run.out))
    check("REST count words, no search word: Stop 2 never calls the model", not run.calls, run.calls)


def case_search_word_far_from_a_count_word_is_not_judged_off_sample():
    # Scope first: the search word and the count word are more than 120 characters apart in the reply.
    gap = FAR_FROM_COUNT_WORD.index("zero") - (FAR_FROM_COUNT_WORD.index("search") + len("search"))
    check("far count word: the count word sits more than 120 characters past the search word", gap > 120, gap)
    run, _ = second_stop(FAR_FROM_COUNT_WORD, label="counts-d-far", session="counts-d-far")
    check("far count word, %d characters away: Stop 2 never calls the model" % gap, not run.calls, run.calls)


# The window is 120 characters, in either order. The near fixtures sit past 60 and within 120, so only the
# 120-character window judges them. The 120 and 121 pair pins the exact edge. The far fixtures sit past 120.
REALISTIC_REPLY = ("Searched the org with gh search prs --state open across all repos we track, and the total came to "
                   "5 open PRs.")
NEAR_AFTER_REPLY = ("Done: searched the open PRs across every tracked repo, and read each row with its labels "
                    "and owners, so the total is 4 open.")
NEAR_BEFORE_REPLY = ("Done: 4 open PRs were read across every tracked repo, with each row and its labels "
                     "and owners in full, then searched again.")
FAR_AFTER_REPLY = ("Done: searched the open PRs across every tracked repo, and read each row with its labels, owners, "
                   "reviewers, comments and checks in full, so the total is 4 open.")
FAR_BEFORE_REPLY = ("Done: 4 open PRs were read across every tracked repo, with each row and its labels, owners, "
                    "reviewers, comments and checks in full, and then searched again.")


def search_count_reply(gap, count_first):
    """A reply whose count word and search word sit `gap` characters apart, in the order named."""
    spacer = " " + "x" * (gap - 2) + " "  # gap characters, filler that is no count word and no search word
    if count_first:
        return "Done: 4" + spacer + "searched the tracked repos."
    return "Done: searched" + spacer + "4 open PRs."


def case_realistic_search_total_sentence_is_judged_off_sample():
    gap = gap_chars(REALISTIC_REPLY, "search", "5")  # the nearest search word, the one in "gh search prs"
    check("realistic sentence: the count word sits past 60 and within 120 characters of the search word",
          60 < gap <= 120, gap)
    run, _ = second_stop(REALISTIC_REPLY, label="counts-g-realistic", session="counts-g-realistic")
    check("realistic sentence: Stop 2 calls the model once", len(run.calls) == 1, run.calls)


def case_count_word_about_100_characters_from_a_search_word_is_judged_off_sample():
    legs = (("after the search word", NEAR_AFTER_REPLY, "searched", "4"),
            ("before the search word", NEAR_BEFORE_REPLY, "4", "searched"))
    for n, (name, text, first, second) in enumerate(legs):
        gap = gap_chars(text, first, second)
        check("near window, count word %s: the gap is past 60 and within 120 characters" % name,
              60 < gap <= 120, gap)
        run, _ = second_stop(text, label="counts-g-near-%02d" % n, session="counts-g-near-%02d" % n)
        check("near window, count word %s: Stop 2 calls the model once" % name, len(run.calls) == 1, run.calls)


def case_search_word_120_characters_from_a_count_word_is_judged_off_sample():
    for n, count_first in enumerate((True, False)):
        text = search_count_reply(120, count_first)
        first, second = ("4", "searched") if count_first else ("searched", "4")
        order = "count word first" if count_first else "search word first"
        gap = gap_chars(text, first, second)
        check("window edge 120, %s: the words sit exactly 120 characters apart" % order, gap == 120, gap)
        run, _ = second_stop(text, label="counts-h-edge-%02d" % n, session="counts-h-edge-%02d" % n)
        check("window edge 120, %s: Stop 2 calls the model once" % order, len(run.calls) == 1, run.calls)


def case_search_word_121_characters_from_a_count_word_is_not_judged_off_sample():
    for n, count_first in enumerate((True, False)):
        text = search_count_reply(121, count_first)
        first, second = ("4", "searched") if count_first else ("searched", "4")
        order = "count word first" if count_first else "search word first"
        gap = gap_chars(text, first, second)
        check("window edge 121, %s: the words sit exactly 121 characters apart" % order, gap == 121, gap)
        run, _ = second_stop(text, label="counts-h-past-%02d" % n, session="counts-h-past-%02d" % n)
        check("window edge 121, %s: Stop 2 never calls the model" % order, not run.calls, run.calls)


def case_count_word_past_120_characters_is_not_judged_off_sample():
    legs = (("after the search word", FAR_AFTER_REPLY, "searched", "4"),
            ("before the search word", FAR_BEFORE_REPLY, "4", "searched"))
    for n, (name, text, first, second) in enumerate(legs):
        gap = gap_chars(text, first, second)
        check("far count word, %s: the gap is more than 120 characters" % name, gap > 120, gap)
        run, _ = second_stop(text, label="counts-i-far-%02d" % n, session="counts-i-far-%02d" % n)
        check("far count word, %s: Stop 2 never calls the model" % name, not run.calls, run.calls)


def case_prompt_never_flags_a_reply_that_refutes_a_search_total():
    run = run_hook(REFUTE_REPLY, answer=OK_ANSWER)
    sentences = rule_sentences(run, REFUTE_REPLY)
    check("prompt: a sentence says never flag a reply that refutes a search total",
          has_pin(sentences, ("never flag",), ("refut", "not used"), ("search",), ("total",)), sentences)


UNCONFIRMED_SEARCH_REPLY = "Done: gh search prs found 6 open PRs."  # a search, and no REST read that confirms it


def case_prompt_flag_sentence_exempts_only_a_search_rest_confirms():
    run = run_hook(UNCONFIRMED_SEARCH_REPLY, answer=OK_ANSWER)
    flag = [s for s in rule_sentences(run, UNCONFIRMED_SEARCH_REPLY) if SEARCH_RULE + ":" in s]
    check("prompt: one sentence starts the counts rule and flags it", len(flag) == 1 and "flag" in flag[0], flag)
    # The exemption is one clause of the flag sentence, split at each semicolon. It must name REST and confirm in
    # its own clause, so a search with no REST read is not taken for candidates. The fix clause also holds REST and
    # confirm, but it has no "never", so it cannot satisfy the exemption.
    clauses = [c for s in flag for c in s.split(";")]
    check("prompt: the candidates exemption names REST and confirm in its own clause",
          has_pin(clauses, ("never", "not"), ("candidate",), ("rest",), ("confirm",)), clauses)


# SEARCH_WORD needs a word boundary, and "_" is a word character, so a search word joined to other words by "_"
# (mcp__github__search_issues, search_pull_requests) must still be seen. The control is a whole-word search with a
# digit before it, which already triggers.
UNDERSCORE_ISSUES_REPLY = "Done: mcp__github__search_issues found 4 open issues."
UNDERSCORE_PRS_REPLY = "Done: search_pull_requests returned 5 open PRs."
TOTAL_CONTROL_REPLY = "Done: GraphQL totalCount 6 open PRs from the search."


def case_search_joined_by_underscore_is_judged_off_sample():
    legs = (("mcp__github__search_issues, the digit 4 after it", UNDERSCORE_ISSUES_REPLY),
            ("search_pull_requests, the digit 5 after it", UNDERSCORE_PRS_REPLY),
            ("totalCount, a whole-word search after the digit 6 (control)", TOTAL_CONTROL_REPLY))
    for n, (name, text) in enumerate(legs):
        run, _ = second_stop(text, label="counts-e-%02d" % n, session="counts-e-%02d" % n)
        check("search trigger, %s: Stop 2 calls the model once" % name, len(run.calls) == 1, run.calls)


# Mutation-proof pins. Each one names the alternative it proves. A scratch mutant that drops that alternative turns
# its own case red and no other case in this block.
NO_COUNT_WORD_REPLY = "Done: the search found no open PRs."  # the count word no, and no digit anywhere
SEARCHES_REPLY = "Done: the rule searches returned 4 open PRs."  # the search word with es, the digit 4 after it
SEARCHING_REPLY = "Done: searching the rule returned 4 open PRs."  # the search word with ing, the digit 4 after it


def case_search_with_count_word_no_is_judged_off_sample():
    run, _ = second_stop(NO_COUNT_WORD_REPLY, label="counts-f-no", session="counts-f-no")
    check("search with the count word no: Stop 2 calls the model once", len(run.calls) == 1, run.calls)


def case_searches_with_a_digit_is_judged_off_sample():
    run, _ = second_stop(SEARCHES_REPLY, label="counts-f-es", session="counts-f-es")
    check("search word 'searches', with the digit 4 after it: Stop 2 calls the model once", len(run.calls) == 1,
          run.calls)


def case_searching_with_a_digit_is_judged_off_sample():
    run, _ = second_stop(SEARCHING_REPLY, label="counts-f-ing", session="counts-f-ing")
    check("search word 'searching', with the digit 4 after it: Stop 2 calls the model once", len(run.calls) == 1,
          run.calls)


# The counts rule as CLAUDE.md states it. The rule's words sit between the anchor before it and its own anchor.
# They must name the GitHub REST API as the count source, and say a search is not one. Naming REST alone is not
# enough: the case also needs the "not a search" clause. No other test reads rule-line text, so this one lives here.
COUNTS_ANCHOR = "<!-- rule:verification-counts-from-rest -->"
CLAUDE_MD = os.path.join(REPO_ROOT, "CLAUDE.md")


def counts_rule_text(text):
    """The counts rule's words in CLAUDE.md, or "" when its anchor is absent."""
    at = text.find(COUNTS_ANCHOR)
    if at < 0:
        return ""
    before = text[:at]
    prev = before.rfind("-->")  # the anchor of the rule before this one, if any
    return before[prev + 3:] if prev >= 0 else before


def case_claude_md_counts_rule_names_the_github_rest_api_and_not_a_search():
    with open(CLAUDE_MD, encoding="utf-8") as f:
        text = f.read()
    anchors = text.count(COUNTS_ANCHOR)
    check("claude.md: the counts rule has one anchor", anchors == 1, anchors)
    rule = counts_rule_text(text)
    check("claude.md: the counts rule names the GitHub REST API as its count source",
          "GitHub REST API" in rule, rule[-300:])
    check("claude.md: the counts rule says a search is not a count source", "not a search" in rule, rule[-300:])


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
    case_owner_gh_step_prompt_names_the_login_switch,
    case_limits_narration_prompt_flags_it,
    case_limits_blocked_work_prompt_passes_it,
    case_limits_dropped_item_prompt_passes_it,
    case_limits_done_result_line_is_not_narration,
    case_limits_verdict_outside_done_is_not_narration,
    case_child_cannot_retrigger_hook,
    case_settings_reply_judge_is_async_and_report_guard_is_not,
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
    case_prompt_flags_a_thread_reply_to_a_waiting_page_comment,
    case_prompt_spares_a_reply_that_rewrote_the_item,
    case_blocked_on_reply_is_judged_off_sample,
    case_prompt_flags_a_port_question_marked_blocking,
    case_prompt_spares_a_departure_not_marked_blocking,
    case_port_finding_is_a_note_with_its_rule,
    case_prompt_count_matches_judged_rules,
    case_prompt_flags_a_recommended_option_that_widens,
    case_widens_finding_logs_its_rule,
    case_prompt_flags_a_pick_one_question_whose_options_could_combine,
    case_route_cite_carries_cited_same_act_and_alternate_rows,
    case_route_cite_skips_other_acts_in_a_full_rows_file,
    case_trailer_hand_off_names_the_doable_route,
    case_no_route_rows_keeps_today_prompt,
    case_route_rows_are_read_once_and_only_for_a_why_yours_line,
    case_local_session_carries_no_cloud_row,
    case_cloud_session_carries_cloud_rows_not_local_ones,
    case_alternate_act_row_survives_forty_same_act_rows,
    case_route_block_flags_only_on_a_works_row_on_this_surface,
    case_shared_route_id_carries_only_its_surface_rows,
    case_cap_keeps_a_works_row_behind_thirty_one_refused_rows,
    case_search_total_reply_is_judged_off_sample,
    case_search_total_finding_is_a_note_logged_as_its_rule,
    case_rest_count_reply_is_not_judged_off_sample,
    case_search_used_for_candidates_is_judged_off_sample,
    case_each_search_trigger_leg_is_judged_off_sample,
    case_search_word_far_from_a_digit_is_not_judged_off_sample,
    case_long_reply_search_total_past_the_clip_is_judged,
    case_prompt_flags_a_search_total_read_as_a_count,
    case_prompt_never_flags_a_count_read_from_rest,
    case_prompt_names_the_fix_confirm_with_rest,
    case_prompt_never_flags_a_search_used_only_for_candidates,
    case_prompt_says_nine_rules_with_the_counts_rule,
    case_rest_count_stop_starts_no_process_and_writes_no_file,
    case_search_total_stop_starts_only_the_judge_call,
    case_searched_word_with_a_digit_is_judged_off_sample,
    case_search_with_a_count_word_is_judged_off_sample,
    case_any_search_endpoint_is_judged_off_sample,
    case_gh_search_with_a_digit_is_judged_off_sample,
    case_count_words_without_a_search_word_are_not_judged_off_sample,
    case_search_word_far_from_a_count_word_is_not_judged_off_sample,
    case_realistic_search_total_sentence_is_judged_off_sample,
    case_count_word_about_100_characters_from_a_search_word_is_judged_off_sample,
    case_search_word_120_characters_from_a_count_word_is_judged_off_sample,
    case_search_word_121_characters_from_a_count_word_is_not_judged_off_sample,
    case_count_word_past_120_characters_is_not_judged_off_sample,
    case_prompt_never_flags_a_reply_that_refutes_a_search_total,
    case_search_joined_by_underscore_is_judged_off_sample,
    case_search_with_count_word_no_is_judged_off_sample,
    case_searches_with_a_digit_is_judged_off_sample,
    case_searching_with_a_digit_is_judged_off_sample,
    case_prompt_flag_sentence_exempts_only_a_search_rest_confirms,
    case_claude_md_counts_rule_names_the_github_rest_api_and_not_a_search,
)


def run_case(case):
    before = len(FAILED)
    try:
        case()
    except Exception as exc:  # a case that cannot run is red, never silently green
        check("%s: case ran" % case.__name__, False, "%s: %s" % (type(exc).__name__, exc))
    if len(FAILED) > before:
        RED_CASES.append(case.__name__)


# The cost of one Stop (decision reply-judge). The first Stop of a session is judged: one model call, no child of
# its own. A Stop sampled out makes no call and writes only its counter. A finding is a note, and adds one guard line.
REPLY = "Done. The change is in place."
JUDGED_REASON = "output-start-with-point: start with the point."


def stop_hook(reply=REPLY, session="cost-reply", active=False):
    return json.dumps({"session_id": session, "stop_hook_active": active, "last_assistant_message": reply})


class CostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = os.path.join(ROOT, "cost")  # a subfolder of this run's ROOT: the run removes ROOT, not this
        os.makedirs(cls.base, exist_ok=True)
        spec = importlib.util.spec_from_file_location("reply_judge_cost", MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.model_timeout = module.MODEL_TIMEOUT

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.base, ignore_errors=True)

    def folder(self):
        return tempfile.mkdtemp(dir=self.base)

    def stop(self, folder, stdin, answers=None):
        return cost_probe.run_hook(MODULE_PATH, stdin, folder, answers)

    def test_a_stop_hook_active_stop_starts_nothing(self):
        run = self.stop(self.folder(), stop_hook(active=True), [[{"ok": True}, None]])
        self.assertEqual((run["code"], run["models"], run["children"], run["files"]), (0, [], [], []))

    def test_an_empty_reply_starts_nothing(self):
        run = self.stop(self.folder(), stop_hook(reply="   "), [[{"ok": True}, None]])
        self.assertEqual((run["code"], run["models"], run["children"], run["files"]), (0, [], [], []))

    def test_a_judged_stop_costs_one_model_call_and_no_child(self):
        run = self.stop(self.folder(), stop_hook(), [[{"ok": True}, None]])
        self.assertEqual(len(run["models"]), 1, "Stop 1 is judged: one model call, got %r" % run["models"])
        self.assertEqual(run["models"][0]["timeout"], self.model_timeout)
        self.assertEqual(run["children"], [], "the judge starts no child of its own")
        self.assertEqual(run["out"].strip(), "", "an allow prints nothing")
        self.assertEqual(len(run["files"]), 1, "a judged allow writes the counter only; got %r" % run["files"])
        self.assertTrue(run["files"][0].startswith("state/reply-judge/"), run["files"])

    def test_a_sampled_out_stop_costs_no_model_call_and_writes_only_the_counter(self):
        folder = self.folder()
        first = self.stop(folder, stop_hook(), [[{"ok": True}, None]])
        second = self.stop(folder, stop_hook(), [[{"ok": False, "reason": JUDGED_REASON}, None]])
        self.assertEqual(len(first["models"]), 1, "Stop 1 is judged")
        self.assertEqual(second["models"], [], "Stop 2 is sampled out: no model call")
        self.assertEqual(second["children"], [])
        self.assertEqual(len(second["files"]), 1, "a sampled-out Stop writes the counter only; got %r" % second["files"])
        self.assertTrue(second["files"][0].startswith("state/reply-judge/"), second["files"])

    def test_a_judged_stop_with_a_finding_adds_the_guard_log_line(self):
        run = self.stop(self.folder(), stop_hook(), [[{"ok": False, "reason": JUDGED_REASON}, None]])
        self.assertEqual(len(run["models"]), 1)
        self.assertIn("additionalContext", run["out"], "a finding is a note, not a block")
        self.assertIn("guard.log", run["files"], "a finding writes its guard log line; got %r" % run["files"])
        self.assertEqual(run["children"], [])


def main():
    _write_stub()
    try:
        for case in CASES:
            run_case(case)
        if not cost_probe.run_class(CostTests):
            RED_CASES.append("CostTests")
    finally:
        shutil.rmtree(ROOT, ignore_errors=True)
    if RED_CASES:
        print("test_reply_judge FAIL: %d of %d cases red" % (len(RED_CASES), len(CASES)))
        return 1
    print("test_reply_judge PASS: all %d cases green" % len(CASES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
