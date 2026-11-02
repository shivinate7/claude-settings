#!/usr/bin/env python3
"""Cases for hooks/call_judge.py, the one PreToolUse command hook that judges an Agent spawn and an
AskUserQuestion call with a model, and refuses through guard_core.refuse(), so an owner override
lifts the refusal (decision owner-override, step c85). It replaces the settings.json `prompt` hook
on Agent and the `agent` hook on AskUserQuestion, which no override could reach.
Standard library only, and no test runner.

Run it from the repository root:

    python hooks/test_call_judge.py

Each hook case runs the real script as a child, with the harness's stdin shape, and reads back its
exit code, stdout, stderr and guard.log. The model is faked: a sitecustomize.py on the child's
PYTHONPATH wraps subprocess.run and answers `claude -p` with the JSON envelope that
decision_watch.invoke_model parses, so the real invoke_model runs on each canned answer. Every
claude call is recorded, so "no model call" is read from the record. CLAUDE_CONFIG_DIR is a fresh
temp folder.

Interface the hook must match:
- File: hooks/call_judge.py, run as a script, one PreToolUse payload on stdin. Exit 0 on every path.
- Agent: model claude-sonnet-5-5, no --effort, rule id `spawn-judge`. AskUserQuestion: model
  claude-opus-5-5, no --effort, rule id `question-judge`. The prompts are the settings.json prompts,
  with the call's tool_input JSON where $ARGUMENTS stood.
- A model answer {"ok": false, "reason": R} refuses through guard_core.refuse(): a PreToolUse deny
  that holds R and the override line, and one guard.log deny line. An override lifts it: no output.
- Veto (an act no override lifts): an Explore spawn whose model field is neither sonnet nor opus.
  Every other refusal is liftable.
- The Explore remedy: the spawn prompt's fix clause and the Agent fallback reason name the audit marker,
  EXPLORE_AUDIT_MARKER in hooks/guard.py, read at test time and never copied here.
- Any model error, or malformed input, fails open: no deny, exit 0, one stderr line.
- AskUserQuestion: a box that fails the code check (hooks/question_form.py chat_hit) is refused before
  any model call, with the rule chat_hit names. The model sees only a box that passes it, and judges only
  what code cannot (the cases are in hooks/test_question_form.py, which reuses run_hook below).
- ArtifactData on the waiting page (ruled Nov 1 11:51 CST): a write of an item (set, update, a str_replace, or a
  batch entry) on collection `items` that is not closed and carries `options` or `context` on a decision, or
  `context`, `steps` or `options` on a task (kind task, coordinator follow-up after the same ruling), or any write
  that carries `steps` (steps are task-only, so no kind is read as a task), or a str_replace on field `context` or
  `options`, judged on its new text, gets one model call, claude-opus-5-5, rule `question-judge`, after
  question_form.item_hit passes it. A task's prompt carries the whole-unit replace rule. A str_replace is judged on
  its new_str only, under a fragment preamble. A batch makes one call for all its qualifying writes. An item_hit hit, a read, another collection or url, a delete, a
  str_replace on another field, and an update with none of these fields make no call and no refusal from call_judge
  (guard.py refuses a hit). A read, and a write of another collection, never import question_form in the hook.
  The page's url is the `waiting-page` key of .claude/layout-extras.json in the git root of the payload's `cwd`.
- settings.json: one command hook on `Agent|AskUserQuestion|ArtifactData` runs call_judge.py with a timeout
  above the longest model call (60 s). No `prompt` or `agent` hook is left on any of the three tools.
- Past rulings (spec past-rulings): a judged AskUserQuestion or waiting-page item write also carries the decision
  records and the `roadmap` step rulings that question_form.past_rulings finds, and an eighth item that refuses a
  question a standing ruling already decides. Each case builds its own real git repo (make_repo), and a fixture
  ruling is found in the prompt with the call's JSON cut out. A search that cannot read a source prints one stderr
  line, `past-ruling search unknown:`, and never says clear.
"""
import atexit
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
HOOK = os.environ.get("CALL_JUDGE_UNDER_TEST") or os.path.join(HERE, "call_judge.py")
GUARD = os.environ.get("GUARD_UNDER_TEST") or os.path.join(HERE, "guard.py")
SETTINGS = os.environ.get("SETTINGS_UNDER_TEST") or os.path.join(REPO, "settings.json")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "lint"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)
ROOT = _test_temp.run_folder()
atexit.register(shutil.rmtree, ROOT, ignore_errors=True)
STUB_DIR = os.path.join(ROOT, "stub")
FAILED = []
RUNS = [0]
SID_A, SID_B = "ses00001", "ses00002"
ALLOW = '{"ok": true}'
FLAG = '{"ok": false, "reason": "roles-brief-contents: name the files and the check that proves it done."}'
FUTURE, PAST = "2099-01-01T00:00:00+00:00", "2000-01-01T00:00:00+00:00"
TIMED = {"kind": "timed", "until": FUTURE}
ONCE = {"kind": "once", "until": FUTURE, "id": "0" * 32}
MARK = "BRIEFMARK-7d2e"
AGENT_MODEL, QUESTION_MODEL = "claude-sonnet-5-5", "claude-opus-5-5"
# The waiting page of a fixture repo. lint/layout.py reads it from .claude/layout-extras.json, key
# "waiting-page", in the git root of the payload's cwd. The one home of this fixture: hooks/test_question_form.py
# reuses PAGE_URL and PAGE_REPO. Its items sit in collection `items`.
PAGE_URL = "https://claude.ai/artifact/waitpage"
PAGE_REPO = os.path.join(ROOT, "page-repo")
PAGE_ITEMS = "items"
os.makedirs(os.path.join(PAGE_REPO, ".git"))
os.makedirs(os.path.join(PAGE_REPO, ".claude"))
with open(os.path.join(PAGE_REPO, ".claude", "layout-extras.json"), "w", encoding="utf-8") as _f:
    json.dump({"kinds": {}, "waiting-page": PAGE_URL}, _f)

# ------------------------------------------------------------------ real git fixtures (past rulings)
#
# make_repo builds a real git repo under ROOT. `decisions` maps a slug to its ruling paragraph (docs/decisions/<slug>.md).
# `steps` maps a step id to its note (roadmap/data/steps/<id>.json on a local `roadmap` branch). Every repo carries the
# waiting page (PAGE_URL) in .claude/layout-extras.json. These git calls run in the test process, not in the hook.
GIT_ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
REPOS = {}


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, "-c", "user.name=test", "-c", "user.email=test@example.invalid",
                           "-c", "commit.gpgsign=false", *args],
                          capture_output=True, text=True, env=GIT_ENV, check=True)


def make_repo(name, decisions=None, steps=None):
    if name in REPOS:
        return REPOS[name]
    repo = os.path.join(ROOT, "repo-" + name)
    os.makedirs(os.path.join(repo, ".claude"))
    with open(os.path.join(repo, ".claude", "layout-extras.json"), "w", encoding="utf-8") as f:
        json.dump({"kinds": {}, "waiting-page": PAGE_URL}, f)
    git(repo, "init", "-q")
    git(repo, "commit", "-q", "--allow-empty", "-m", "init")
    if decisions:
        folder = os.path.join(repo, "docs", "decisions")
        os.makedirs(folder)
        for slug, ruling in decisions.items():
            with open(os.path.join(folder, slug + ".md"), "w", encoding="utf-8") as f:
                f.write("# %s\n\n## The ruling\n\n%s\n" % (slug, ruling))
        git(repo, "add", "docs")
        git(repo, "commit", "-q", "-m", "decision records")
    if steps:
        git(repo, "checkout", "-q", "-b", "roadmap")
        folder = os.path.join(repo, "roadmap", "data", "steps")
        os.makedirs(folder)
        for step_id, note in steps.items():
            with open(os.path.join(folder, step_id + ".json"), "w", encoding="utf-8") as f:
                json.dump({"title": "Step " + step_id, "phase": "test", "status": "done", "note": note, "why": ""}, f)
        git(repo, "add", "roadmap")
        git(repo, "commit", "-q", "-m", "step notes")
        git(repo, "checkout", "-q", "-")
    REPOS[name] = repo
    return repo


try:
    import override
except ImportError:
    override = None

STUB_SITE = r'''
import json, os, subprocess
_real_run = subprocess.run


def _fake_run(argv, **kwargs):
    if not (isinstance(argv, (list, tuple)) and argv
            and os.path.basename(str(argv[0])).lower() in ("claude", "claude.exe", "claude.cmd")):
        return _real_run(argv, **kwargs)
    prompt = kwargs.get("input") or b""
    prompt = prompt.decode("utf-8", "replace") if isinstance(prompt, bytes) else str(prompt)
    with open(os.environ["CJ_RECORD"], "a", encoding="utf-8") as f:
        f.write(json.dumps({"argv": list(argv), "prompt": prompt}) + "\n")
    if os.environ.get("CJ_MODEL_FAIL"):
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="stub model failure")
    return subprocess.CompletedProcess(argv, 0, stdout=json.dumps({"result": os.environ["CJ_ANSWER"]}), stderr="")


_real_popen = subprocess.Popen


class _CountingPopen(_real_popen):
    # Records each git process start, so a case counts the git processes a judged call spawns.
    def __init__(self, args, *rest, **kwargs):
        argv = args if isinstance(args, (list, tuple)) else [args]
        if argv and os.path.basename(str(argv[0])).lower() in ("git", "git.exe"):
            with open(os.path.join(os.environ["CJ_LOADED_DIR"], "git.log"), "a", encoding="utf-8") as f:
                f.write("git\n")
        _real_popen.__init__(self, args, *rest, **kwargs)


subprocess.Popen = _CountingPopen
subprocess.run = _fake_run
with open(os.path.join(os.environ["CJ_LOADED_DIR"], "loaded"), "w", encoding="utf-8") as f:
    f.write("1")


import sys


class _WatchQuestionForm:
    # Records each import request for question_form in the child, so a case reads whether the hook loaded it.
    def find_spec(self, name, path=None, target=None):
        if name == "question_form":
            with open(os.path.join(os.environ["CJ_LOADED_DIR"], "imports.log"), "a", encoding="utf-8") as f:
                f.write(name + "\n")
        return None


sys.meta_path.insert(0, _WatchQuestionForm())
'''


def check(name, ok, detail=""):
    if ok:
        print("ok   " + name)
    else:
        FAILED.append(name)
        print("FAIL " + name + (" :: " + str(detail) if detail else ""))


class Run:
    def __init__(self, proc, base):
        self.base, self.code = base, proc.returncode
        self.out, self.err = proc.stdout or "", proc.stderr or ""
        self.loaded = os.path.exists(os.path.join(base, "loaded"))
        imports = os.path.join(base, "imports.log")
        self.imports = open(imports, encoding="utf-8").read().split() if os.path.exists(imports) else []
        path = os.path.join(base, "calls.jsonl")
        self.calls = []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.calls = [json.loads(line) for line in f if line.strip()]
        gitlog = os.path.join(base, "git.log")
        self.git = len(open(gitlog, encoding="utf-8").read().split()) if os.path.exists(gitlog) else 0
        log = os.path.join(base, "config", "guard.log")
        self.log = open(log, encoding="utf-8").read() if os.path.exists(log) else ""

    def deny(self):
        if not self.out.strip():
            return None
        return json.loads(self.out)["hookSpecificOutput"]

    def reason(self):
        return (self.deny() or {}).get("permissionDecisionReason", "")


def detail(r):
    return "code=%s out=%r err=%r calls=%d git=%d loaded=%s imports=%s log=%r" % (
        r.code, r.out[:200], r.err[-200:], len(r.calls), r.git, r.loaded, r.imports, r.log[-200:])


def write_pass(cfg, session, body):
    folder = os.path.join(cfg, "state", "override")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, session + ".json"), "w", encoding="utf-8") as f:
        f.write(body if isinstance(body, str) else json.dumps(body))


def run_hook(stdin_text, answer=ALLOW, model_fail=False, pass_=None):
    RUNS[0] += 1
    base = os.path.join(ROOT, "run-%03d" % RUNS[0])
    cfg = os.path.join(base, "config")
    os.makedirs(cfg)
    os.makedirs(STUB_DIR, exist_ok=True)
    with open(os.path.join(STUB_DIR, "sitecustomize.py"), "w", encoding="utf-8") as f:
        f.write(STUB_SITE)
    if pass_ is not None:  # (session id, override file body): what the owner's prompt would write
        write_pass(cfg, *pass_)
    env = {k: v for k, v in os.environ.items() if not k.startswith("CJ_")}
    env.update({"CLAUDE_CONFIG_DIR": cfg, "PYTHONPATH": STUB_DIR, "CJ_LOADED_DIR": base,
                "CJ_RECORD": os.path.join(base, "calls.jsonl"), "CJ_ANSWER": answer})
    if model_fail:
        env["CJ_MODEL_FAIL"] = "1"
    proc = subprocess.run([sys.executable, HOOK], input=stdin_text, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, timeout=120)
    return Run(proc, base)


def spawn_input(kind="Explore", model="haiku", session=SID_A, agent=None, brief=None):
    tool_input = {"subagent_type": kind, "description": "check", "prompt": brief or ("Audit the module. " + MARK)}
    if model:
        tool_input["model"] = model
    payload = {"session_id": session, "tool_name": "Agent", "tool_input": tool_input}
    if agent:
        payload["agent_id"] = agent
    return json.dumps(payload)


# The question form (hooks/question_form.py): a box with 2+ options carries these lines in `question`, and
# each option a `Gain:` and a `Lose:` in its description. hooks/test_question_form.py builds its variants
# from good_box(), so the box has one home.
GOAL_LINE = "Goal: ship the change today"
PROBLEM_LINE = "Problem (risk): the change touches the guard, so it needs your word"
BASED_LINES = ("Based on (read): the diff changes one rule",)
# The line a question to the owner carries (rule question-departs): what is on main, and what changes.
DEPARTS_LINE = "Departs from: lint/stamp.py:run_stamp — the stamp check moves to the lint job"


def good_options():
    return [{"label": "Ship it (Recommended)",
             "description": "Gain: the change lands today. Lose: nobody reads it first. " + MARK},
            {"label": "Hold it",
             "description": "Gain: a reviewer reads it first. Lose: the change lands a day later."}]


def good_box(goal=GOAL_LINE, problem=PROBLEM_LINE, based=BASED_LINES, options=None, departs=DEPARTS_LINE):
    """An AskUserQuestion input that meets the form and the Departs from line. A line passed as None or
    empty is left out, so a case drops one line and keeps the rest."""
    text = "\n".join(line for line in (goal, problem, *based, departs) if line)
    return {"questions": [{"question": text, "header": "Ship", "multiSelect": False,
                           "options": options or good_options()}]}


def question_input(session=SID_A, agent=None, box=None, cwd=PAGE_REPO):
    payload = {"session_id": session, "tool_name": "AskUserQuestion", "tool_input": box or good_box(),
               "cwd": cwd}
    if agent:
        payload["agent_id"] = agent
    return json.dumps(payload)


# ------------------------------------------------------------------ the waiting page (ArtifactData)
#
# Ruled Nov 1 11:51 CST: a waiting-page item write gets the same model review as a chat question.
# good_page_item() passes question_form.item_hit: the chat box's form lines in `context`, and two options keyed
# a and b, each with a plain gain and lose. A case that makes a model call answers PAGE_FLAG, so a call that
# refuses shows as a deny.
PAGE_FLAG = ('{"ok": false, "reason": "the gain is not a plain effect on the owner: say what he gets and what '
             'he gives up."}')
PAGE_MARK, PAGE_MARK_B = "PAGEMARK-3f9c", "PAGEMARK-8d21"
# A str_replace's old_str and new_str. The model sees only new_str, so a case checks that the marks split this way.
PAGE_OLD, PAGE_NEW = "PAGEOLD-5a0e", "PAGENEW-7c3d"


def good_page_item(mark=PAGE_MARK, **over):
    """A waiting-page decision that passes the form. `mark` rides in option a's gain, so a case finds the item
    in the prompt. `over` replaces fields, for a case that changes one."""
    context = "\n".join((GOAL_LINE, PROBLEM_LINE, *BASED_LINES, DEPARTS_LINE))
    item = {"kind": "decision", "title": "Ship the change today?", "status": "open", "context": context,
            "options": [{"key": "a", "label": "Ship it", "gain": "The change lands today. " + mark,
                         "lose": "Nobody reads it first."},
                        {"key": "b", "label": "Hold it", "gain": "A reviewer reads it first.",
                         "lose": "The change lands a day later."}]}
    item.update(over)
    return item


# A task item (kind task) is judged like a decision (coordinator follow-up after the Nov 1 11:51 CST ruling). Its
# `context` holds the Why yours line and its `steps` hold the text the owner reads. ITEM_99_STEP is item 99's step:
# it told the owner to replace a line and quoted only the value, so following it dropped the script call.
TASK_WHY = "Why yours: a session on your computer was asked first and none could reach the remote"
ITEM_99_STEP = "Find GUARD_SHELL_SKIP= ... change it to GUARD_SHELL_SKIP=tree. Change nothing else."
GOOD_TASK_STEP = ("Find the line `GUARD_SHELL_SKIP= scripts/guard-shell.py --hook` and replace the whole line with "
                  "`GUARD_SHELL_SKIP=tree scripts/guard-shell.py --hook`. Change nothing else.")
TASK_FLAG = '{"ok": false, "reason": "a step that replaces text quotes the whole line before and after the change."}'


def good_task_item(step=GOOD_TASK_STEP, **over):
    """A task item that passes question_form.item_hit: its Why yours line in `context`, and one step. `over`
    replaces fields, for a case that changes one."""
    item = {"kind": "task", "title": "Set the guard skip", "status": "open", "context": TASK_WHY, "steps": [step]}
    item.update(over)
    return item


def page_input(action="set", data=None, collection=PAGE_ITEMS, doc_id="p1", url=PAGE_URL, session=SID_A,
               agent=None, cwd=PAGE_REPO, **extra):
    """One ArtifactData call, as the harness sends it, with the payload's cwd set to the fixture repo.
    `doc_id` None leaves the key out (a list). `extra` holds the str_replace fields."""
    tool_input = {"action": action, "url": url, "collection": collection}
    if doc_id is not None:
        tool_input["doc_id"] = doc_id
    if data is not None:
        tool_input["data"] = data
    tool_input.update(extra)
    payload = {"session_id": session, "tool_name": "ArtifactData", "tool_input": tool_input, "cwd": cwd}
    if agent:
        payload["agent_id"] = agent
    return json.dumps(payload)


def page_batch_input(writes, session=SID_A):
    """A batch ArtifactData call: `writes` are {op, collection, doc_id, data} entries, and the call has no
    top-level collection or doc_id."""
    payload = {"session_id": session, "tool_name": "ArtifactData", "cwd": PAGE_REPO,
               "tool_input": {"action": "batch", "url": PAGE_URL, "writes": writes}}
    return json.dumps(payload)


def model_of(argv):
    return argv[argv.index("--model") + 1] if "--model" in argv else None


def lifted_log(r, rule):
    return r.log.count("\toverride\t%s\t" % rule) == 1 and "\tdeny\t" not in r.log


def case_agent_refusal():
    r = run_hook(spawn_input("builder", model="sonnet"), answer=FLAG)
    d = r.deny() or {}
    check("agent: a flagged spawn is denied with the judge's reason", r.code == 0
          and d.get("permissionDecision") == "deny" and "name the files" in r.reason(), detail(r))
    check("agent: the deny names rule spawn-judge and logs one deny line",
          "spawn-judge" in r.reason() and r.log.count("\tdeny\tspawn-judge\t") == 1, detail(r))
    check("agent: one model call, claude-sonnet-5-5, no effort", len(r.calls) == 1
          and model_of(r.calls[0]["argv"]) == AGENT_MODEL and "--effort" not in r.calls[0]["argv"], detail(r))
    prompt = r.calls[0]["prompt"] if r.calls else ""
    check("agent: the prompt is the spawn prompt with the call's JSON",
          prompt.startswith("Judge this agent spawn:") and MARK in prompt and '"subagent_type"' in prompt
          and "$ARGUMENTS" not in prompt and "audit Explore row" in prompt, prompt[:160])
    check("agent: the refusal ends with the override line",
          "override" in r.reason() and (override is not None and hasattr(override, "offer")
                                         and r.reason().rstrip().endswith(override.offer("spawn-judge").strip())),
          r.reason()[-160:])
    ok = run_hook(spawn_input("builder", model="sonnet"), answer=ALLOW)
    check("agent: an ok answer is empty stdout, exit 0, no deny logged",
          ok.code == 0 and ok.out == "" and "\tdeny\t" not in ok.log and len(ok.calls) == 1, detail(ok))


def case_spawn_prompt_bars_a_lane_waiting_page_write():
    # A lane has no wake after it ends, so it cannot read its answer (step c126). The orchestrator writes the item.
    r = run_hook(spawn_input("builder", model="sonnet",
                             brief="Build the screen. If you have a question, post an item on the waiting page. " + MARK),
                 answer=ALLOW)
    prompt = (r.calls[0]["prompt"] if r.calls else "").lower()
    sentences = re.split(r"[.\n]", prompt)
    check("agent: the spawn prompt flags a brief that tells a lane to write a waiting-page item",
          any(all(w in s for w in ("flag", "waiting", "lane")) for s in sentences), prompt[:200])
    check("agent: the spawn prompt passes a brief that forbids a lane to write the item",
          any(all(w in s for w in ("forbid", "waiting")) and ("never flag" in s or "fine" in s) for s in sentences), prompt[:200])
    check("agent: the spawn prompt says the lane puts its question in its report",
          any(all(w in s for w in ("report", "question")) for s in sentences), prompt[:200])


def case_agent_override():
    flagged = spawn_input("builder", model="sonnet")
    agent_call = spawn_input("builder", model="sonnet", agent="a1")
    for label, inp, pass_, lifted in (
        ("timed override", flagged, (SID_A, TIMED), True),
        ("one-act override", flagged, (SID_A, ONCE), True),
        ("timed override, an agent's call", agent_call, (SID_A, TIMED), True),
        ("one-act override, an agent's call", agent_call, (SID_A, ONCE), False),
        ("an ended override", flagged, (SID_A, dict(TIMED, until=PAST)), False),
        ("another session's override", flagged, (SID_B, TIMED), False),
        ("a corrupt override file", flagged, (SID_A, "{not json"), False),
        ("no override", flagged, None, False),
    ):
        r = run_hook(inp, answer=FLAG, pass_=pass_)
        if lifted:
            check("agent: %s lifts the refusal (no output, one override log line)" % label,
                  r.code == 0 and r.out == "" and lifted_log(r, "spawn-judge"), detail(r))
        else:
            d = r.deny() or {}
            check("agent: %s leaves the deny" % label,
                  r.code == 0 and d.get("permissionDecision") == "deny" and "\toverride\t" not in r.log, detail(r))


def case_explore_row_is_vetoed():
    # An Explore spawn on a model that is neither sonnet nor opus is the Explore row of agent-model-cap,
    # a model guard. No override lifts it.
    constant = getattr(override, "NO_OVERRIDE", None) if override is not None else None
    for label, model in (("haiku", "haiku"), ("no model field", None)):
        r = run_hook(spawn_input("Explore", model=model), answer=FLAG, pass_=(SID_A, TIMED))
        d = r.deny() or {}
        check("explore: a flagged spawn on %s stays denied under a timed override" % label,
              r.code == 0 and d.get("permissionDecision") == "deny" and "\toverride\t" not in r.log, detail(r))
        check("explore: its refusal carries the no-override line (%s)" % label,
              bool(constant) and constant.strip() in r.reason() and "override 15m" not in r.reason(),
              r.reason()[-160:])
    for label, inp in (("an Explore spawn on sonnet", spawn_input("Explore", model="sonnet")),
                       ("an Explore spawn on opus", spawn_input("Explore", model="opus")),
                       ("a builder spawn with no model field", spawn_input("builder", model=None))):
        r = run_hook(inp, answer=FLAG, pass_=(SID_A, TIMED))
        check("explore: %s is not vetoed, a timed override lifts it" % label,
              r.code == 0 and r.out == "" and lifted_log(r, "spawn-judge"), detail(r))


def load_file_module(path, name):
    """Load a file as a module, so a case reads its constant at test time, never a copy."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def guard_audit_marker():
    return load_file_module(GUARD, "guard_marker_probe").EXPLORE_AUDIT_MARKER


def fix_clause(prompt):
    """The spawn prompt's fix clause: from `the fix is` to the end of its sentence, or "" when absent."""
    start = prompt.find("the fix is")
    if start < 0:
        return ""
    end = prompt.find(". ", start)
    return prompt[start:end + 1] if end > start else prompt[start:]


def case_explore_remedy_names_marker():
    # Rule agent-role-model (decision agent-model-cap): an audit Explore on sonnet passes only when its brief's
    # first non-blank line carries the marker. The judge's fix clause names that line and the marker, or a
    # session fixes one refusal and hits the next.
    marker = guard_audit_marker()
    r = run_hook(spawn_input("Explore", model="haiku"), answer=ALLOW)
    prompt = r.calls[0]["prompt"] if r.calls else ""
    clause = fix_clause(prompt)
    check("explore remedy: the spawn prompt's fix clause names the first non-blank line",
          "first non-blank line" in clause, clause or detail(r))
    check("explore remedy: the spawn prompt's fix clause names the audit marker read from guard.py",
          bool(marker) and marker in clause, clause or detail(r))


def case_agent_fallback_names_marker():
    # The fallback reason is the deny when the model gives no reason, so it names the same marker.
    marker = guard_audit_marker()
    fallback = load_file_module(HOOK, "call_judge_under_test").JUDGES["Agent"][4]
    check("agent fallback: the Agent fallback reason names the audit marker read from guard.py",
          bool(marker) and marker in fallback, fallback)


def case_question():
    r = run_hook(question_input(), answer=FLAG)
    d = r.deny() or {}
    check("question: a flagged call is denied with the judge's reason", r.code == 0
          and d.get("permissionDecision") == "deny" and "name the files" in r.reason(), detail(r))
    check("question: the deny names rule question-judge and logs one deny line",
          "question-judge" in r.reason() and r.log.count("\tdeny\tquestion-judge\t") == 1, detail(r))
    check("question: one model call, claude-opus-5-5, no effort", len(r.calls) == 1
          and model_of(r.calls[0]["argv"]) == QUESTION_MODEL and "--effort" not in r.calls[0]["argv"], detail(r))
    prompt = r.calls[0]["prompt"] if r.calls else ""
    check("question: the prompt is the question prompt with the call's JSON",
          prompt.startswith("Review this AskUserQuestion call:") and MARK in prompt
          and "$ARGUMENTS" not in prompt, prompt[:160])
    # Code reads the form lines (chat_hit), so the model prompt no longer asks for them. The call's own JSON
    # holds those lines, so it is cut out before the words are read.
    # Items 1 to 7 only: item 8 (past rulings) names the Based on (ruling) line on purpose.
    asks = prompt.replace(json.dumps(good_box(), ensure_ascii=False), "").split("\n8. ")[0]
    check("question: the prompt leaves the Goal, Problem and Based on lines to the code check",
          MARK not in asks and not any(t in asks for t in ("Goal:", "Problem:", "Based on", "premise-format")), asks[:400])
    kept = ("gain", "lose", "unexplained", "outside the box", "recommend")
    check("question: the prompt keeps what code cannot decide (gain and lose, ids, outside the box, a recommendation)",
          all(word in asks.lower() for word in kept), [w for w in kept if w not in asks.lower()])
    check("question: the refusal ends with the override line",
          override is not None and hasattr(override, "offer")
          and r.reason().rstrip().endswith(override.offer("question-judge").strip()), r.reason()[-160:])
    for label, inp, pass_, lifted in (
        ("timed override", question_input(), (SID_A, TIMED), True),
        ("one-act override", question_input(), (SID_A, ONCE), True),
        ("one-act override, an agent's call", question_input(agent="a1"), (SID_A, ONCE), False),
        ("no override", question_input(), None, False),
    ):
        r = run_hook(inp, answer=FLAG, pass_=pass_)
        if lifted:
            check("question: %s lifts the refusal" % label,
                  r.code == 0 and r.out == "" and lifted_log(r, "question-judge"), detail(r))
        else:
            check("question: %s leaves the deny" % label,
                  r.code == 0 and (r.deny() or {}).get("permissionDecision") == "deny", detail(r))
    r = run_hook(question_input(), answer=ALLOW)
    check("question: an ok answer is empty stdout", r.code == 0 and r.out == "" and len(r.calls) == 1, detail(r))


def case_question_departs():
    # Rule question-departs (hooks/question_form.py, chat_hit): a box with no Departs from line, or one that
    # restates main, is refused in code before any model call, and the refusal names the line.
    restates = "Departs from: agent-model-cap — Opus above the row stays the existing ask"
    for label, departs in (("no Departs from line", None), ("a line that restates main", restates)):
        r = run_hook(question_input(box=good_box(departs=departs)), answer=ALLOW)
        d = r.deny() or {}
        check("question departs: %s is refused by code, though the model would answer ok" % label,
              r.code == 0 and d.get("permissionDecision") == "deny" and "Departs from" in r.reason(), detail(r))
        check("question departs: the code refusal makes no model call (%s)" % label, r.calls == [], detail(r))
        check("question departs: one question-departs deny line (%s)" % label,
              r.log.count("\tdeny\tquestion-departs\t") == 1, detail(r))
    r = run_hook(question_input(box=good_box(departs=None)), answer=ALLOW)
    check("question departs: the code refusal ends with the override line",
          override is not None and hasattr(override, "offer")
          and r.reason().rstrip().endswith(override.offer("question-departs").strip()), r.reason()[-160:])
    r = run_hook(question_input(box=good_box(departs=None)), answer=ALLOW, pass_=(SID_A, TIMED))
    check("question departs: a timed override lifts the code refusal",
          r.code == 0 and r.out == "" and lifted_log(r, "question-departs"), detail(r))
    r = run_hook(question_input(), answer=ALLOW)
    check("question departs: a box with the line reaches the model once and is not refused",
          r.code == 0 and r.out == "" and len(r.calls) == 1 and "\tdeny\t" not in r.log, detail(r))
    one = good_box(departs=None)
    one["questions"][0].update(question="Ship it?", options=[{"label": "Yes", "description": "go"}])
    r = run_hook(question_input(box=one), answer=ALLOW)
    check("question departs: a one-option question with no line is not refused",
          r.code == 0 and r.out == "" and "\tdeny\t" not in r.log, detail(r))
    options = good_options()
    options[1] = {"label": "Hold it", "description": "Lose: the change lands a day later."}
    r = run_hook(question_input(box=good_box(options=options, departs=None)), answer=ALLOW)
    check("question departs: a box with no line and an option with no gain is refused as question-form first",
          r.code == 0 and "\tdeny\tquestion-form\t" in r.log and "\tdeny\tquestion-departs\t" not in r.log, detail(r))


def case_page_fixture_passes_the_form():
    # Precondition: the good item is a pass for the form check, so a refusal below is the judge's, not the form's.
    import question_form  # the one form check (hooks/question_form.py)
    got = question_form.item_hit("set", {"collection": PAGE_ITEMS, "doc_id": "p1", "data": good_page_item()})
    check("page fixture: the good item passes question_form.item_hit", got == ("", ""), got)


def case_page_reject_and_accept():
    item = good_page_item()
    r = run_hook(page_input("set", item), answer=PAGE_FLAG)
    d = r.deny() or {}
    check("page: a good item the judge rejects is denied with the judge's reason", r.code == 0
          and d.get("permissionDecision") == "deny" and "plain effect" in r.reason(), detail(r))
    check("page: the deny names rule question-judge and logs one deny line",
          r.reason().startswith("question-judge: ") and r.log.count("\tdeny\tquestion-judge\t") == 1, detail(r))
    check("page: one model call, claude-opus-5-5, no effort", len(r.calls) == 1
          and model_of(r.calls[0]["argv"]) == QUESTION_MODEL and "--effort" not in r.calls[0]["argv"], detail(r))
    prompt = r.calls[0]["prompt"] if r.calls else ""
    check("page: the model sees the item the write carries", PAGE_MARK in prompt, prompt[:160])
    check("page: the refusal ends with the override line",
          override is not None and hasattr(override, "offer")
          and r.reason().rstrip().endswith(override.offer("question-judge").strip()), r.reason()[-160:])
    ok = run_hook(page_input("set", item), answer=ALLOW)
    check("page: the same item the judge accepts is not denied, after one model call",
          ok.code == 0 and ok.out == "" and "\tdeny\t" not in ok.log and len(ok.calls) == 1, detail(ok))


def case_page_no_model_call():
    # Cost proof: a model call only for an items write that is not closed, passes item_hit, and carries options or
    # context on a decision, or context, steps or options on a task, or a str_replace on context or options. Each
    # input below would be denied if the judge were called on it, so a call shows as a deny.
    item, bad_form = good_page_item(), good_page_item(context=GOAL_LINE + "\n" + PROBLEM_LINE + "\n" + DEPARTS_LINE)
    cases = (
        ("a receipts collection write", page_input("set", item, collection="receipts", doc_id="r1")),
        ("an answers delete", page_input("delete", None, collection="answers", doc_id="a1")),
        ("an items get", page_input("get", None, doc_id="p1")),
        ("an items list", page_input("list", None, doc_id=None)),
        ("an items delete", page_input("delete", None, doc_id="p1")),
        ("a write to another artifact", page_input("set", item, url="https://claude.ai/artifact/otherpage")),
        ("an items write that fails the form", page_input("set", bad_form)),
        ("a closed item", page_input("set", good_page_item(status="closed"))),
        ("an items update that closes an item with no form line",
         page_input("update", {"status": "closed", "context": "Answered: ship it."})),
        ("a str_replace on the title", page_input("str_replace", None, field="title",
                                                  old_str="Ship the change today?",
                                                  new_str="Ship the change this week?")),
        ("a context str_replace that removes the Goal line (fails item_hit)",
         page_input("str_replace", None, field="context", old_str=GOAL_LINE, new_str="")),
        ("an items update with neither options nor context", page_input("update", {"title": "Renamed"})),
        ("a closed task item with item 99's step", page_input("set", good_task_item(ITEM_99_STEP, status="closed"))),
        ("a task update with a title only", page_input("update", {"kind": "task", "title": "Renamed"})),
        ("a batch of a delete and a title-only update", page_batch_input([
            {"op": "delete", "collection": PAGE_ITEMS, "doc_id": "p1"},
            {"op": "update", "collection": PAGE_ITEMS, "doc_id": "p2", "data": {"title": "Renamed"}}])),
        ("a batch with a good item and one that fails the form", page_batch_input([
            {"op": "set", "collection": PAGE_ITEMS, "doc_id": "p1", "data": item},
            {"op": "set", "collection": PAGE_ITEMS, "doc_id": "p2", "data": bad_form}])),
    )
    for label, inp in cases:
        r = run_hook(inp, answer=PAGE_FLAG)
        check("page no model call: %s (no call, no refusal from call_judge)" % label,
              r.code == 0 and r.out == "" and r.calls == [] and "\tdeny\t" not in r.log, detail(r))


def case_page_batch_one_call():
    second = good_page_item(PAGE_MARK_B)
    writes = [{"op": "set", "collection": PAGE_ITEMS, "doc_id": "p1", "data": good_page_item()},
              {"op": "update", "collection": PAGE_ITEMS, "doc_id": "p2",
               "data": {"kind": "decision", "context": second["context"], "options": second["options"]}}]
    r = run_hook(page_batch_input(writes), answer=ALLOW)
    prompt = r.calls[0]["prompt"] if r.calls else ""
    check("page batch: two qualifying item writes make exactly one model call, claude-opus-5-5",
          r.code == 0 and r.out == "" and len(r.calls) == 1 and model_of(r.calls[0]["argv"]) == QUESTION_MODEL,
          detail(r))
    check("page batch: the one prompt carries both writes", PAGE_MARK in prompt and PAGE_MARK_B in prompt,
          prompt[:160])
    r = run_hook(page_batch_input(writes), answer=PAGE_FLAG)
    check("page batch: a refusal of the batch is one deny line, from one call",
          len(r.calls) == 1 and r.log.count("\tdeny\tquestion-judge\t") == 1 and (r.deny() or {}).get(
              "permissionDecision") == "deny", detail(r))


def case_page_override():
    flagged, agent_call = page_input("set", good_page_item()), page_input("set", good_page_item(), agent="a1")
    for label, inp, pass_, lifted in (
        ("timed override", flagged, (SID_A, TIMED), True),
        ("one-act override", flagged, (SID_A, ONCE), True),
        ("one-act override, an agent's call", agent_call, (SID_A, ONCE), False),
        ("no override", flagged, None, False),
    ):
        r = run_hook(inp, answer=PAGE_FLAG, pass_=pass_)
        if lifted:
            check("page: %s lifts the refusal (no output, one override log line)" % label,
                  r.code == 0 and r.out == "" and lifted_log(r, "question-judge"), detail(r))
        else:
            check("page: %s leaves the deny" % label,
                  r.code == 0 and (r.deny() or {}).get("permissionDecision") == "deny"
                  and "\toverride\t" not in r.log, detail(r))


def case_page_model_failure_fails_open():
    r = run_hook(page_input("set", good_page_item()), answer=PAGE_FLAG, model_fail=True)
    errs = failed_open_lines(r)
    check("page fail open: a model failure on an item write allows, after one model call",
          r.code == 0 and r.out == "" and len(r.calls) == 1 and "\tdeny\t" not in r.log, detail(r))
    check("page fail open: one stderr line from the hook", len(errs) == 1 and r.code == 0
          and "can't open file" not in errs[0], detail(r))


def case_page_str_replace_judged():
    # Ruled Nov 1 11:51 CST: a str_replace on `context` or `options` that item_hit passes gets the same model
    # review as a chat question. The model sees only new_str, under a fragment preamble.
    fragment = "The change lands this week. " + PAGE_NEW
    for field in ("context", "options", "options.0.gain"):
        r = run_hook(page_input("str_replace", None, field=field, old_str=PAGE_OLD, new_str=fragment),
                     answer=PAGE_FLAG)
        d = r.deny() or {}
        check("page str_replace: a %s edit the judge rejects is denied, rule question-judge, one call" % field,
              r.code == 0 and d.get("permissionDecision") == "deny" and r.reason().startswith("question-judge: ")
              and r.log.count("\tdeny\tquestion-judge\t") == 1 and len(r.calls) == 1, detail(r))
        check("page str_replace: a %s edit is one model call, claude-opus-5-5, no effort" % field,
              len(r.calls) == 1 and model_of(r.calls[0]["argv"]) == QUESTION_MODEL
              and "--effort" not in r.calls[0]["argv"], detail(r))
    flagged = run_hook(page_input("str_replace", None, field="context", old_str=PAGE_OLD, new_str=fragment),
                       answer=PAGE_FLAG)
    prompt = flagged.calls[0]["prompt"] if flagged.calls else ""
    check("page str_replace: the model sees new_str and not old_str", PAGE_NEW in prompt and PAGE_OLD not in prompt,
          prompt[:200])
    sentences = re.split(r"[.\n]", prompt.lower())
    check("page str_replace: the prompt calls the text a fragment and never flags a missing line or option",
          any("fragment" in s for s in sentences) and any("missing" in s and "option" in s for s in sentences),
          prompt[:300])
    check("page str_replace: the refusal ends with the override line",
          override is not None and hasattr(override, "offer")
          and flagged.reason().rstrip().endswith(override.offer("question-judge").strip()), flagged.reason()[-160:])
    r = run_hook(page_input("str_replace", None, field="context", old_str=PAGE_OLD, new_str=fragment),
                 answer=PAGE_FLAG, pass_=(SID_A, TIMED))
    check("page str_replace: a timed override lifts the refusal", r.code == 0 and r.out == ""
          and lifted_log(r, "question-judge"), detail(r))
    ok = run_hook(page_input("str_replace", None, field="context", old_str=PAGE_OLD, new_str=fragment),
                  answer=ALLOW)
    check("page str_replace: a good fragment the judge accepts is allowed, after one model call",
          ok.code == 0 and ok.out == "" and "\tdeny\t" not in ok.log and len(ok.calls) == 1, detail(ok))
    writes = [{"op": "set", "collection": PAGE_ITEMS, "doc_id": "p1", "data": good_page_item(PAGE_MARK)},
              {"op": "str_replace", "collection": PAGE_ITEMS, "doc_id": "p2", "field": "context",
               "old_str": PAGE_OLD, "new_str": fragment}]
    r = run_hook(page_batch_input(writes), answer=ALLOW)
    prompt = r.calls[0]["prompt"] if r.calls else ""
    check("page str_replace: a context edit joins a batch's one model call",
          r.code == 0 and r.out == "" and len(r.calls) == 1 and model_of(r.calls[0]["argv"]) == QUESTION_MODEL
          and PAGE_MARK in prompt and PAGE_NEW in prompt and PAGE_OLD not in prompt, detail(r))


def case_page_task_item_judged():
    # Coordinator follow-up after the Nov 1 11:51 CST ruling: a task item (kind task) that carries context, steps or
    # options gets one model call after item_hit passes it, and its prompt carries the whole-unit replace rule.
    import question_form  # the one form check (hooks/question_form.py)
    bad, good = good_task_item(ITEM_99_STEP), good_task_item()
    for label, data in (("item 99's task", bad), ("the good task", good)):
        got = question_form.item_hit("set", {"collection": PAGE_ITEMS, "doc_id": "t99", "data": data})
        check("task fixture: %s passes question_form.item_hit, so a refusal below is the judge's" % label,
              got == ("", ""), got)
    r = run_hook(page_input("set", bad), answer=TASK_FLAG)
    d = r.deny() or {}
    check("task item: item 99's step is denied by the judge, rule question-judge, one model call", r.code == 0
          and d.get("permissionDecision") == "deny" and r.reason().startswith("question-judge: ")
          and r.log.count("\tdeny\tquestion-judge\t") == 1 and len(r.calls) == 1, detail(r))
    check("task item: the one call is claude-opus-5-5, no effort", len(r.calls) == 1
          and model_of(r.calls[0]["argv"]) == QUESTION_MODEL and "--effort" not in r.calls[0]["argv"], detail(r))
    prompt = r.calls[0]["prompt"] if r.calls else ""
    check("task item: the prompt holds item 99's step text", ITEM_99_STEP in prompt, prompt[:200])
    # The item's own strings are cut out first, so only the prompt's words can satisfy the rule check.
    rest = prompt.replace(ITEM_99_STEP, "").replace(TASK_WHY, "").lower()
    sentences = re.split(r"[.\n]", rest)
    check("task item: the prompt holds the whole-unit rule (quote the whole line or value, show the line after the change in full)",
          any("whole" in s and any(w in s for w in ("line", "value", "unit")) for s in sentences)
          and any("full" in s and any(w in s for w in ("after", "change")) for s in sentences), rest[:300])
    upd = run_hook(page_input("update", {"kind": "task", "steps": [ITEM_99_STEP]}), answer=TASK_FLAG)
    check("task item: an update that carries item 99's step (kind task) is denied after one model call",
          (upd.deny() or {}).get("permissionDecision") == "deny" and len(upd.calls) == 1
          and upd.log.count("\tdeny\tquestion-judge\t") == 1, detail(upd))
    ok = run_hook(page_input("set", good), answer=ALLOW)
    check("task item: a good task item (its step quotes the whole line before and after) is allowed after one model call",
          ok.code == 0 and ok.out == "" and "\tdeny\t" not in ok.log and len(ok.calls) == 1, detail(ok))
    writes = [{"op": "set", "collection": PAGE_ITEMS, "doc_id": "t99", "data": bad},
              {"op": "set", "collection": PAGE_ITEMS, "doc_id": "p1", "data": good_page_item()}]
    batch = run_hook(page_batch_input(writes), answer=ALLOW)
    prompt = batch.calls[0]["prompt"] if batch.calls else ""
    check("task batch: a task item and a decision make exactly one model call, claude-opus-5-5",
          batch.code == 0 and batch.out == "" and len(batch.calls) == 1
          and model_of(batch.calls[0]["argv"]) == QUESTION_MODEL, detail(batch))
    check("task batch: the one prompt carries the task's step and the decision",
          ITEM_99_STEP in prompt and PAGE_MARK in prompt, prompt[:200])


def case_page_task_exempt_from_decision_items():
    # A task item has no Goal, Problem or pick, so decision items 1, 2 and 7 do not apply to it. The prompt for a
    # lone task write must say so, or the judge holds the task to items it cannot meet. Matched loosely: only the
    # sentences that name a task are read, and together they must exempt the Goal, the Problem and the recommended
    # option, carry a negation or an only-rule, and state what a task is judged on.
    r = run_hook(page_input("set", good_task_item()), answer=ALLOW)
    check("task exempt: a lone good task write makes one model call, claude-opus-5-5, no effort",
          r.code == 0 and len(r.calls) == 1 and model_of(r.calls[0]["argv"]) == QUESTION_MODEL
          and "--effort" not in r.calls[0]["argv"], detail(r))
    prompt = r.calls[0]["prompt"] if r.calls else ""
    # The item's own strings are cut out first, so only the prompt's words can satisfy the checks.
    rest = prompt.replace(GOOD_TASK_STEP, "").replace(TASK_WHY, "").lower()
    task = [s for s in re.split(r"[.;\n]", rest) if "task" in s]
    exempt = " ".join(s for s in task if re.search(r"\b(goal|problem|pick|recommend\w*)\b", s))
    check("task exempt: a sentence that names a task exempts the Goal", re.search(r"\bgoal\b", exempt) is not None,
          rest[:400])
    check("task exempt: a sentence that names a task exempts the Problem",
          re.search(r"\bproblem\b", exempt) is not None, rest[:400])
    check("task exempt: a sentence that names a task exempts the recommended option (pick)",
          re.search(r"\b(pick|recommend\w*)\b", exempt) is not None, rest[:400])
    check("task exempt: the exempting sentence carries a negation or an only-rule",
          re.search(r"\b(not|no|never|only|without|exempt)\b|n't", exempt) is not None, exempt[:300])
    judged = " ".join(task)
    check("task exempt: the sentences that name a task state the judged set (plain words, unexplained ids, "
          "pointers outside the item, the whole-unit rule)",
          all(w in judged for w in ("plain", "unexplain", "outside", "whole")), judged[:400])


def case_page_steps_judged():
    # Coordinator follow-up after the Nov 1 11:51 CST ruling: steps are task-only, so a write that carries `steps` is
    # judged as a task, even with no kind. No str_replace case: the tool's `field` is one top-level key, never `steps`
    # or `steps.N` (ArtifactData schema), so that write cannot occur.
    import question_form  # the one form check (hooks/question_form.py)
    upd = {"steps": [ITEM_99_STEP]}
    got = question_form.item_hit("update", {"collection": PAGE_ITEMS, "doc_id": "t99", "data": upd})
    check("task steps fixture: an update of item 99's step with no kind passes question_form.item_hit", got == ("", ""),
          got)
    r = run_hook(page_input("update", upd), answer=TASK_FLAG)
    d = r.deny() or {}
    check("task steps: an update of item 99's step with no kind is denied by the judge, rule question-judge, one call",
          r.code == 0 and d.get("permissionDecision") == "deny" and r.reason().startswith("question-judge: ")
          and r.log.count("\tdeny\tquestion-judge\t") == 1 and len(r.calls) == 1, detail(r))
    prompt = r.calls[0]["prompt"] if r.calls else ""
    check("task steps: the one prompt holds item 99's step text", ITEM_99_STEP in prompt, prompt[:200])


def case_page_reads_and_other_collections_skip_question_form():
    # Cost proof: a read and a write of another collection exit before the hook imports question_form, the heavy
    # import. The last check is a control: a judged items write imports it, so an empty record means an early exit.
    item = good_page_item()
    for label, inp in (
        ("an items get", page_input("get", None, doc_id="p1", cwd=CI_REPO)),
        ("an items list", page_input("list", None, doc_id=None, cwd=CI_REPO)),
        ("a receipts write", page_input("set", item, collection="receipts", doc_id="r1", cwd=CI_REPO)),
    ):
        r = run_hook(inp, answer=PAGE_FLAG)
        check("page import: %s does not import question_form in the hook" % label,
              r.code == 0 and r.out == "" and r.calls == [] and "question_form" not in r.imports, detail(r))
        check("page import: %s runs no git process" % label, r.git == 0, detail(r))
    r = run_hook(page_input("set", item), answer=ALLOW)
    check("page import: a judged items write imports question_form (the record sees the import)",
          "question_form" in r.imports, detail(r))


def case_fail_open():
    for label, inp, kwargs in (
        ("a model failure on a spawn", spawn_input("builder", model="sonnet"), {"model_fail": True}),
        ("a model failure on a question", question_input(), {"model_fail": True}),
        ("an odd answer", spawn_input("builder", model="sonnet"), {"answer": '{"ok": "maybe"}'}),
        ("unreadable stdin", "not json", {}),
        ("an empty payload", "{}", {}),
    ):
        r = run_hook(inp, **kwargs)
        errs = failed_open_lines(r)
        check("fail open: %s allows" % label, r.code == 0 and r.out == "" and "\tdeny\t" not in r.log, detail(r))
        if label != "an empty payload":
            check("fail open: %s prints one stderr line, from the hook" % label,
                  len(errs) == 1 and "can't open file" not in errs[0] and r.code == 0, detail(r))
    r = run_hook(json.dumps({"session_id": SID_A, "tool_name": "Bash", "tool_input": {"command": "ls"}}), answer=FLAG)
    check("another tool: no model call, no output", r.code == 0 and r.out == "" and r.calls == [], detail(r))


def case_settings_row():
    with open(SETTINGS, encoding="utf-8") as f:
        pre = json.load(f)["hooks"]["PreToolUse"]
    left = [(e.get("matcher"), h.get("type")) for e in pre for h in e["hooks"]
            if h.get("type") in ("prompt", "agent")
            and re.search(r"\b(Agent|AskUserQuestion|ArtifactData)\b", e.get("matcher") or "")]
    check("settings: no prompt or agent hook is left on Agent, AskUserQuestion or ArtifactData", left == [], left)
    rows = [(e, h) for e in pre for h in e["hooks"] if "call_judge.py" in h.get("command", "")]
    check("settings: one command hook runs call_judge.py", len(rows) == 1 and rows[0][1].get("type") == "command", rows)
    if len(rows) != 1:
        return
    entry, hook = rows[0]
    matcher = set((entry.get("matcher") or "").split("|"))
    check("settings: its matcher is Agent, AskUserQuestion and ArtifactData",
          matcher == {"Agent", "AskUserQuestion", "ArtifactData"}, entry.get("matcher"))
    check("settings: its timeout exceeds the longest model call (60 s)", hook.get("timeout", 0) > 60, hook)
    empty = os.path.join(ROOT, "empty-config")
    os.makedirs(empty, exist_ok=True)
    proc = subprocess.run(["sh", "-c", hook["command"]], input="{}", capture_output=True, text=True,
                          env=dict(os.environ, CLAUDE_CONFIG_DIR=empty), timeout=60)
    errs = [line for line in proc.stderr.splitlines() if line.strip()]
    check("settings: with the script missing the launcher exits 0 with one stderr line, never a block",
          proc.returncode == 0 and proc.stdout == "" and len(errs) == 1, (proc.returncode, proc.stderr[-160:]))


# ------------------------------------------------------------------ past rulings (spec past-rulings)
#
# A judged question carries the decision records and the step rulings of the `roadmap` ref as candidates, and an eighth
# item that refuses a question a standing ruling already decides. Each fixture ruling holds a marker the question never
# holds, so a check that finds the marker in the prompt, with the call's JSON cut out, proves the ruling reached the model.
PAST_UNKNOWN = "past-ruling search unknown:"
APPS_SLUG, CAPS_SLUG = "github-apps-keep-access", "ci-job-caps"
APPS_RULING = ("Owner, 2026-10-28, page item 9: keep the apps' access to claude-settings as is, because it makes "
               "calling into a repo straightforward; revisit if it gets bloated. Marker apps-7b1e.")
CAPS_RULING = ("Owner, 2026-10-27: the job caps are generous on purpose, a stopgap until time-pinned tests go "
               "(decision test-strategy-reset). Marker caps-4c09.")
CI_STEP_ID = "c95"
CI_STEP_SENTENCE = ("Ruling (owner, Oct 27): a CI milestone run is red only when a test is broken, never because a "
                    "job ran out of time. Marker c95-1f2a.")
DECISIONS_REPO = make_repo("decisions", decisions={APPS_SLUG: APPS_RULING, CAPS_SLUG: CAPS_RULING})
CI_REPO = make_repo("ci", steps={CI_STEP_ID: CI_STEP_SENTENCE})
BARE_REPO = make_repo("bare")

APPS_GOAL = "Goal: decide whether the GitHub apps keep access to claude-settings"
APPS_PROBLEM = "Problem (risk): the apps can reach the repo, so keeping or removing them needs your word"
APPS_BASED = ("Based on (read): the GitHub audit lists Cloudflare, Render and Renovate beside Claude",)
APPS_CITED = ("Based on (ruling): %s says revisit only if the apps get bloated; Renovate opened 2 PRs here" % APPS_SLUG,)
APPS_OPTIONS = [
    {"label": "Keep the apps (Recommended)",
     "description": "Gain: calls into the repo stay straightforward. Lose: an unused app keeps its access."},
    {"label": "Remove the apps",
     "description": "Gain: fewer apps can write to the repo. Lose: each call into the repo needs a manual step."}]
CAPS_GOAL = "Goal: know whether the CI job cap rule means about 2x or under 80%"
CAPS_PROBLEM = "Problem (rule): the cap decides when a full CI run goes red, so the rule needs your word"
CAPS_BASED = ("Based on (measured): the slowest checks job ran at about 2x its cap in the last 30 runs",)
CAPS_OPTIONS = [
    {"label": "Set the cap to about 2x (Recommended)",
     "description": "Gain: jobs keep their headroom. Lose: a slow job can still end at its cap."},
    {"label": "Set the cap under 80%",
     "description": "Gain: a slow job gets a tighter bar. Lose: a normal run ends at its cap more often."}]
CI_GOAL = "Goal: finish CI milestone runs without a false red"
CI_PROBLEM = "Problem (risk): a milestone run ended at its job cap again, so the cap needs your word"
CI_BASED = ("Based on (measured): the milestone job ran out of time at its cap on the last run",)
CI_CHAT_OPTIONS = [
    {"label": "Raise the cap (Recommended)",
     "description": "Gain: the milestone run stops ending at its cap. Lose: each run takes longer."},
    {"label": "Keep the cap",
     "description": "Gain: nothing changes on main. Lose: the milestone run may end at its cap again."}]
CI_PAGE_CONTEXT = "\n".join((CI_GOAL, CI_PROBLEM, CI_BASED[0], DEPARTS_LINE))
CI_PAGE_OPTIONS = [
    {"key": "a", "label": "Raise the cap", "gain": "The milestone run stops ending at its cap.",
     "lose": "Each run takes longer and uses more minutes."},
    {"key": "b", "label": "Keep the cap", "gain": "Nothing changes on main.",
     "lose": "The milestone run may end at its cap again."}]


def item_text(prompt, number):
    # The text of judge item `number`, from its line to the reply line; "" when the prompt holds no such item.
    start = prompt.find("\n%d. " % number)
    if start < 0:
        return ""
    end = prompt.find("Reply JSON only", start)
    return prompt[start:end if end > start else len(prompt)]


def without_call(prompt, call):
    # The prompt with the call's own JSON cut out, so a check reads only the text the hook added.
    return prompt.replace(json.dumps(call, ensure_ascii=False), "")


def failed_open_lines(r):
    # The stderr lines of a failed-open run: the past-ruling notice is not one of them.
    return [line for line in r.err.splitlines() if line.strip() and PAST_UNKNOWN not in line]


def case_past_ruling_replay_item_145():
    import question_form  # the one form check (hooks/question_form.py)
    box = good_box(goal=APPS_GOAL, problem=APPS_PROBLEM, based=APPS_BASED, options=APPS_OPTIONS)
    check("past ruling 145 fixture: the box passes chat_hit, so the model judges it",
          question_form.chat_hit(box) == ("", ""), question_form.chat_hit(box))
    r = run_hook(question_input(box=box, cwd=DECISIONS_REPO), answer=ALLOW)
    prompt = r.calls[0]["prompt"] if r.calls else ""
    check("past ruling 145: the prompt holds the keep-the-apps ruling's slug and its line",
          len(r.calls) == 1 and APPS_SLUG in without_call(prompt, box) and APPS_RULING in without_call(prompt, box),
          detail(r))


def case_past_ruling_replay_item_133():
    import question_form  # the one form check (hooks/question_form.py)
    item = good_page_item(title="Raise the CI milestone job cap?", context=CI_PAGE_CONTEXT, options=CI_PAGE_OPTIONS)
    got = question_form.item_hit("set", {"collection": PAGE_ITEMS, "doc_id": "c133", "data": item})
    check("past ruling 133 fixture: the item passes item_hit, so the model judges it", got == ("", ""), got)
    r = run_hook(page_input("set", item, doc_id="c133", cwd=CI_REPO), answer=ALLOW)
    prompt = r.calls[0]["prompt"] if r.calls else ""
    check("past ruling 133: the prompt holds the step c95 ruling sentence",
          len(r.calls) == 1 and CI_STEP_SENTENCE in without_call(prompt, item), detail(r))


def case_past_ruling_cited_passes():
    import question_form  # the one form check (hooks/question_form.py)
    box = good_box(goal=APPS_GOAL, problem=APPS_PROBLEM, based=APPS_CITED, options=APPS_OPTIONS)
    check("past ruling cited fixture: the box passes chat_hit", question_form.chat_hit(box) == ("", ""),
          question_form.chat_hit(box))
    r = run_hook(question_input(box=box, cwd=DECISIONS_REPO), answer=ALLOW)
    check("past ruling cited: a Based on (ruling) question is still sent, one model call", len(r.calls) == 1, detail(r))
    check("past ruling cited: the ok answer allows it, with no deny",
          r.code == 0 and r.out == "" and "\tdeny\t" not in r.log, detail(r))
    prompt = r.calls[0]["prompt"] if r.calls else ""
    check("past ruling cited: the eighth item names the Based on (ruling) citation rule",
          "based on (ruling)" in item_text(prompt, 8).lower(), item_text(prompt, 8)[:200])


def case_past_ruling_explained_premise():
    import question_form  # the one form check (hooks/question_form.py)
    box = good_box(goal=CAPS_GOAL, problem=CAPS_PROBLEM, based=CAPS_BASED, options=CAPS_OPTIONS)
    check("past ruling premise fixture: the box passes chat_hit", question_form.chat_hit(box) == ("", ""),
          question_form.chat_hit(box))
    r = run_hook(question_input(box=box, cwd=DECISIONS_REPO), answer=ALLOW)
    prompt = r.calls[0]["prompt"] if r.calls else ""
    check("past ruling premise: the ci-job-caps record's slug and line reach the prompt",
          len(r.calls) == 1 and CAPS_SLUG in without_call(prompt, box) and CAPS_RULING in without_call(prompt, box),
          detail(r))
    item8 = item_text(prompt, 8).lower()
    check("past ruling premise: the eighth item covers a premise a standing decision already explains",
          "premise" in item8 and "explain" in item8 and "standing decision" in item8, item8[:300])


def case_past_ruling_unknown_is_named():
    box = good_box()
    r = run_hook(question_input(box=box, cwd=BARE_REPO), answer=ALLOW)
    check("past ruling unknown: the call is allowed, after one model call",
          r.code == 0 and r.out == "" and "\tdeny\t" not in r.log and len(r.calls) == 1, detail(r))
    notes = [line for line in r.err.splitlines() if PAST_UNKNOWN in line]
    line = notes[0].lower() if len(notes) == 1 else ""
    check("past ruling unknown: one stderr line names the unread sources, closed page items among them",
          len(notes) == 1 and "decision" in line and "roadmap" in line and "closed page items" in line, detail(r))
    check("past ruling unknown: the line never says clear",
          len(notes) == 1 and re.search(r"\bclear\b", line) is None, detail(r))
    prompt = r.calls[0]["prompt"] if r.calls else ""
    check("past ruling unknown: the model is told which sources were not searched",
          "closed page items" in without_call(prompt, box), prompt[:200])


def case_past_ruling_cost():
    import question_form  # the one form check (hooks/question_form.py)
    box = good_box(goal=CI_GOAL, problem=CI_PROBLEM, based=CI_BASED, options=CI_CHAT_OPTIONS)
    check("past ruling cost fixture: the box passes chat_hit", question_form.chat_hit(box) == ("", ""),
          question_form.chat_hit(box))
    r = run_hook(question_input(box=box, cwd=CI_REPO), answer=ALLOW)
    check("past ruling cost: a judged question runs one git process, the roadmap read",
          len(r.calls) == 1 and r.git == 1, detail(r))
    item = good_page_item(title="Raise the CI milestone job cap?", context=CI_PAGE_CONTEXT, options=CI_PAGE_OPTIONS)
    p = run_hook(page_input("set", item, doc_id="c133", cwd=CI_REPO), answer=ALLOW)
    check("past ruling cost: a judged page write runs one git process", len(p.calls) == 1 and p.git == 1, detail(p))
    q = run_hook(question_input(box=good_box(), cwd=BARE_REPO), answer=ALLOW)
    check("past ruling cost: a judged question with no roadmap ref runs at most one git process",
          len(q.calls) == 1 and q.git <= 1, detail(q))
    f = run_hook(question_input(box=good_box(problem=None), cwd=CI_REPO), answer=ALLOW)
    check("past ruling cost: a box refused by the form makes no model call and no git process",
          f.calls == [] and f.git == 0 and (f.deny() or {}).get("permissionDecision") == "deny", detail(f))


def main():
    for case in (case_agent_refusal, case_spawn_prompt_bars_a_lane_waiting_page_write, case_agent_override, case_explore_row_is_vetoed,
                 case_explore_remedy_names_marker, case_agent_fallback_names_marker, case_question,
                 case_question_departs, case_page_fixture_passes_the_form, case_page_reject_and_accept,
                 case_page_no_model_call, case_page_batch_one_call, case_page_override,
                 case_page_model_failure_fails_open, case_page_str_replace_judged,
                 case_page_task_item_judged, case_page_task_exempt_from_decision_items, case_page_steps_judged,
                 case_page_reads_and_other_collections_skip_question_form,
                 case_fail_open, case_settings_row, case_past_ruling_replay_item_145,
                 case_past_ruling_replay_item_133, case_past_ruling_cited_passes,
                 case_past_ruling_explained_premise, case_past_ruling_unknown_is_named,
                 case_past_ruling_cost):
        try:
            case()
        except Exception as exc:
            check(case.__name__, False, "raised %s: %s" % (type(exc).__name__, exc))
    print("FAIL: %d failed" % len(FAILED) if FAILED else "all checks passed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
