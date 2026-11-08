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
- A re-ask (ruled Nov 1 17:44 CST): a judged items set or update (question_form.judged_item_writes) whose data has
  non-empty `options` and a `lastAnswer` dict with choice `none` (or no choice) whose `note` is a string, non-empty
  after strip. A picked choice with a note is not a re-ask, and neither is a `lastAnswer` that carries `done`. The one model prompt
  holds call_judge.NONE_DIRECTION_RULE exactly once when a write in the call is a re-ask (a batch too), and not at
  all otherwise. The cases read the constant with load_file_module, never a copy of its text. A missing constant
  fails those checks, with no crash.
- The widening rule (decision uniform-over-variants, a shared tool never grows a second accepted form): call_judge.WIDENING_RULE
  is appended to the formatted PAGE_PROMPT exactly once when a judged waiting-page write (question_form.judged_item_writes) is a
  set or update whose data has non-empty `options`, and never otherwise, never on AskUserQuestion or Agent. question_form.WIDENS_KEY
  is the one home of the mark's key, "widens", and WIDENING_RULE contains it. The cases read both with load_file_module, never a
  copy, and a missing name fails its checks with a named cause, never a crash.
- settings.json: one command hook on `Agent|AskUserQuestion|ArtifactData` runs call_judge.py with a timeout
  above the longest model call (60 s). No `prompt` or `agent` hook is left on any of the three tools.
- Past rulings (spec past-rulings): a judged AskUserQuestion or waiting-page item write also carries the decision
  records and the `roadmap` step rulings that question_form.past_rulings finds, and an eighth item that refuses a
  question a standing ruling already decides. Each case builds its own real git repo (make_repo), and a fixture
  ruling is found in the prompt with the call's JSON cut out. A search that cannot read a source prints one stderr
  line, `past-ruling search unknown:`, and never says clear.
- Owner-question sends: a send_message or SendMessage whose message carries a Goal line and a Problem line gets the
  past-ruling check (lint/report_guard.py past_ruling_problem, the one home) before it is sent, whoever the target is.
  The Goal line may be plain, bold, bulleted, quoted, or a `## Goal:` heading. The Problem line may carry a stake, a
  stake outside the set, or none. A message over report_guard.ASK_TEXT_MAX keeps its Based on lines and its text from
  its first form line. Any other send makes no model call and starts no subprocess. A refusal is rule `past-ruling`
  with the relay remedy. A check that could not run refuses unless every question in the message carries its own
  `Unvetted:` line.
- Page item writes (ruled 14:38 CST): a judged item write gets the dedicated past-ruling call first (item 8 alone, Sonnet).
  A refusal denies with rule past-ruling and makes no form-judge call. Otherwise the form judge (Opus) runs, and its
  prompt carries no item 8.
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
# waiting page (PAGE_URL) in .claude/layout-extras.json, unless the `page` option names another url or None
# (no page key). These git calls run in the test process, not in the hook.
GIT_ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
REPOS = {}
REPO_PAGES = {}


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, "-c", "user.name=test", "-c", "user.email=test@example.invalid",
                           "-c", "commit.gpgsign=false", *args],
                          capture_output=True, text=True, env=GIT_ENV, check=True)


def make_repo(name, decisions=None, steps=None, debts=None, page=PAGE_URL):
    """`page` is the repo's waiting-page url. None writes no page key: a repo with no page, which layout reads as unknown.
    A name is cached, so a second call must name the same page: a different one would silently get the first repo."""
    if name in REPOS:
        if REPO_PAGES[name] != page:
            raise ValueError("make_repo %r was made with page %r, not %r" % (name, REPO_PAGES[name], page))
        return REPOS[name]
    repo = os.path.join(ROOT, "repo-" + name)
    os.makedirs(os.path.join(repo, ".claude"))
    extras = {"kinds": {}} if page is None else {"kinds": {}, "waiting-page": page}
    with open(os.path.join(repo, ".claude", "layout-extras.json"), "w", encoding="utf-8") as f:
        json.dump(extras, f)
    REPO_PAGES[name] = page
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
    if debts:
        folder = os.path.join(repo, "docs", "debts")
        os.makedirs(folder)
        for slug, what in debts.items():
            with open(os.path.join(folder, slug + ".md"), "w", encoding="utf-8") as f:
                f.write("# %s\n\nWhat: %s\n" % (slug, what))
        git(repo, "add", "docs")
        git(repo, "commit", "-q", "-m", "debt records")
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


def _cite_shown(prompt, mark):
    # A model that cites only what it was shown: the first candidate line (`<id>: <text>`) after the past-ruling
    # header that holds `mark`, as a refusal naming its id. "" when no shown line holds it. The header's own line is
    # skipped, and the list is the lines after it.
    head = "Past rulings (item 8)"
    if head not in prompt:
        return ""
    for line in prompt.split(head, 1)[1].splitlines()[1:]:
        if mark in line and ": " in line:
            rid = line.split(": ", 1)[0].strip()
            return json.dumps({"ok": False, "reason": rid + ": ruled by the owner, so it is settled."})
    return ""


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
    # CJ_FORM_FAIL makes only the form call fail: a call whose prompt lacks the dedicated call's text.
    if os.environ.get("CJ_FORM_FAIL") and "Judge only item 8 below" not in prompt:
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="stub form failure")
    # The dedicated past-ruling call asks item 8 alone, so only its prompt holds this text. It answers CJ_PAST_ANSWER
    # when a case sets one, else the case's answer. CJ_PAST_FAIL makes that call fail alone.
    answer = os.environ["CJ_ANSWER"]
    if "Judge only item 8 below" in prompt:
        if os.environ.get("CJ_PAST_FAIL"):
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="stub past-ruling failure")
        answer = os.environ.get("CJ_PAST_ANSWER") or answer
    # CJ_CITE_SHOWN names a marker: the answer cites the shown candidate that holds it, and allows when none does.
    if os.environ.get("CJ_CITE_SHOWN"):
        answer = _cite_shown(prompt, os.environ["CJ_CITE_SHOWN"]) or '{"ok": true}'
    return subprocess.CompletedProcess(argv, 0, stdout=json.dumps({"result": answer}), stderr="")


_real_popen = subprocess.Popen


class _CountingPopen(_real_popen):
    # Records each git process start, so a case counts the git processes a judged call spawns. Every process start
    # also goes to procs.log, so a case counts all the subprocesses a call spawns (the claude stub is not one).
    def __init__(self, args, *rest, **kwargs):
        argv = args if isinstance(args, (list, tuple)) else [args]
        name = os.path.basename(str(argv[0])).lower() if argv else ""
        with open(os.path.join(os.environ["CJ_LOADED_DIR"], "procs.log"), "a", encoding="utf-8") as f:
            f.write((name or "?") + "\n")
        if name in ("git", "git.exe"):
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
        procs = os.path.join(base, "procs.log")
        self.procs = len(open(procs, encoding="utf-8").read().split()) if os.path.exists(procs) else 0
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


def run_hook(stdin_text, answer=ALLOW, model_fail=False, pass_=None, past=None, past_fail=False, form_fail=False,
             cite_shown=None):
    """One hook run. `answer` is the canned model answer. `past` is the dedicated past-ruling call's answer, and
    `past_fail` makes only that call fail; unset, the dedicated call takes `answer`. `form_fail` makes only the form call
    fail. `cite_shown` is a marker: the model then cites the first shown candidate line that holds it, and allows
    otherwise (the stub's _cite_shown), so a case reads what the judge may cite from the list it was shown."""
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
    if past is not None:
        env["CJ_PAST_ANSWER"] = past
    if past_fail:
        env["CJ_PAST_FAIL"] = "1"
    if form_fail:
        env["CJ_FORM_FAIL"] = "1"
    if cite_shown:
        env["CJ_CITE_SHOWN"] = cite_shown
    proc = subprocess.run([sys.executable, HOOK], input=stdin_text, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, timeout=120)
    return Run(proc, base)


# The dedicated past-ruling call of a page item write asks item 8 alone, so its prompt carries this text (the stub
# above reads the same text). The form judge's prompt never does.
PAST_CALL_TEXT = "Judge only item 8 below"


def past_calls(r):
    return [c for c in r.calls if PAST_CALL_TEXT in c["prompt"]]


def form_calls(r):
    return [c for c in r.calls if PAST_CALL_TEXT not in c["prompt"]]


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
    r = run_hook(page_input("set", item), answer=PAGE_FLAG, past=ALLOW)
    d = r.deny() or {}
    check("page: a good item the judge rejects is denied with the judge's reason", r.code == 0
          and d.get("permissionDecision") == "deny" and "plain effect" in r.reason(), detail(r))
    check("page: the deny names rule question-judge and logs one deny line",
          r.reason().startswith("question-judge: ") and r.log.count("\tdeny\tquestion-judge\t") == 1, detail(r))
    check("page: one form-judge call, claude-opus-5-5, no effort", len(form_calls(r)) == 1
          and model_of(form_calls(r)[0]["argv"]) == QUESTION_MODEL and "--effort" not in form_calls(r)[0]["argv"], detail(r))
    prompt = form_calls(r)[0]["prompt"] if form_calls(r) else ""
    check("page: the model sees the item the write carries", PAGE_MARK in prompt, prompt[:160])
    check("page: the refusal ends with the override line",
          override is not None and hasattr(override, "offer")
          and r.reason().rstrip().endswith(override.offer("question-judge").strip()), r.reason()[-160:])
    ok = run_hook(page_input("set", item), answer=ALLOW)
    check("page: the same item the judge accepts is not denied, after one form-judge call",
          ok.code == 0 and ok.out == "" and "\tdeny\t" not in ok.log and len(form_calls(ok)) == 1, detail(ok))


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
    prompt = form_calls(r)[0]["prompt"] if form_calls(r) else ""
    check("page batch: two qualifying item writes make exactly one form-judge call, claude-opus-5-5",
          r.code == 0 and r.out == "" and len(form_calls(r)) == 1 and model_of(form_calls(r)[0]["argv"]) == QUESTION_MODEL,
          detail(r))
    check("page batch: the one prompt carries both writes", PAGE_MARK in prompt and PAGE_MARK_B in prompt,
          prompt[:160])
    r = run_hook(page_batch_input(writes), answer=PAGE_FLAG, past=ALLOW)
    check("page batch: a refusal of the batch is one deny line, from one call",
          len(form_calls(r)) == 1 and r.log.count("\tdeny\tquestion-judge\t") == 1 and (r.deny() or {}).get(
              "permissionDecision") == "deny", detail(r))


def case_page_override():
    flagged, agent_call = page_input("set", good_page_item()), page_input("set", good_page_item(), agent="a1")
    for label, inp, pass_, lifted in (
        ("timed override", flagged, (SID_A, TIMED), True),
        ("one-act override", flagged, (SID_A, ONCE), True),
        ("one-act override, an agent's call", agent_call, (SID_A, ONCE), False),
        ("no override", flagged, None, False),
    ):
        r = run_hook(inp, answer=PAGE_FLAG, past=ALLOW, pass_=pass_)
        if lifted:
            check("page: %s lifts the refusal (no output, one override log line)" % label,
                  r.code == 0 and r.out == "" and lifted_log(r, "question-judge"), detail(r))
        else:
            check("page: %s leaves the deny" % label,
                  r.code == 0 and (r.deny() or {}).get("permissionDecision") == "deny"
                  and "\toverride\t" not in r.log, detail(r))


def case_page_model_failure_refuses_as_unvetted():
    r = run_hook(page_input("set", good_page_item()), answer=PAGE_FLAG, model_fail=True)
    check("page unvetted: a model failure on an item write refuses once, the remedy names Unvetted:",
          r.code == 0 and (r.deny() or {}).get("permissionDecision") == "deny" and "Unvetted:" in r.reason()
          and len(r.calls) == 1, detail(r))


def case_page_str_replace_judged():
    # Ruled Nov 1 11:51 CST: a str_replace on `context` or `options` that item_hit passes gets the same model
    # review as a chat question. The model sees only new_str, under a fragment preamble.
    fragment = "The change lands this week. " + PAGE_NEW
    for field in ("context", "options", "options.0.gain"):
        r = run_hook(page_input("str_replace", None, field=field, old_str=PAGE_OLD, new_str=fragment),
                     answer=PAGE_FLAG, past=ALLOW)
        d = r.deny() or {}
        check("page str_replace: a %s edit the judge rejects is denied, rule question-judge, one call" % field,
              r.code == 0 and d.get("permissionDecision") == "deny" and r.reason().startswith("question-judge: ")
              and r.log.count("\tdeny\tquestion-judge\t") == 1 and len(form_calls(r)) == 1, detail(r))
        check("page str_replace: a %s edit is one form-judge call, claude-opus-5-5, no effort" % field,
              len(form_calls(r)) == 1 and model_of(form_calls(r)[0]["argv"]) == QUESTION_MODEL
              and "--effort" not in form_calls(r)[0]["argv"], detail(r))
    flagged = run_hook(page_input("str_replace", None, field="context", old_str=PAGE_OLD, new_str=fragment),
                       answer=PAGE_FLAG, past=ALLOW)
    prompt = form_calls(flagged)[0]["prompt"] if form_calls(flagged) else ""
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
                 answer=PAGE_FLAG, past=ALLOW, pass_=(SID_A, TIMED))
    check("page str_replace: a timed override lifts the refusal", r.code == 0 and r.out == ""
          and lifted_log(r, "question-judge"), detail(r))
    ok = run_hook(page_input("str_replace", None, field="context", old_str=PAGE_OLD, new_str=fragment),
                  answer=ALLOW)
    check("page str_replace: a good fragment the judge accepts is allowed, after one form-judge call",
          ok.code == 0 and ok.out == "" and "\tdeny\t" not in ok.log and len(form_calls(ok)) == 1, detail(ok))
    writes = [{"op": "set", "collection": PAGE_ITEMS, "doc_id": "p1", "data": good_page_item(PAGE_MARK)},
              {"op": "str_replace", "collection": PAGE_ITEMS, "doc_id": "p2", "field": "context",
               "old_str": PAGE_OLD, "new_str": fragment}]
    r = run_hook(page_batch_input(writes), answer=ALLOW)
    prompt = form_calls(r)[0]["prompt"] if form_calls(r) else ""
    check("page str_replace: a context edit joins a batch's one form-judge call",
          r.code == 0 and r.out == "" and len(form_calls(r)) == 1 and model_of(form_calls(r)[0]["argv"]) == QUESTION_MODEL
          and PAGE_MARK in prompt and PAGE_NEW in prompt and PAGE_OLD not in prompt, detail(r))


def case_page_task_item_judged():
    # Coordinator follow-up after the Nov 1 11:51 CST ruling: a task item (kind task) that carries context, steps or
    # options gets one form-judge call after item_hit passes it, and its prompt carries the whole-unit replace rule.
    import question_form  # the one form check (hooks/question_form.py)
    bad, good = good_task_item(ITEM_99_STEP), good_task_item()
    for label, data in (("item 99's task", bad), ("the good task", good)):
        got = question_form.item_hit("set", {"collection": PAGE_ITEMS, "doc_id": "t99", "data": data})
        check("task fixture: %s passes question_form.item_hit, so a refusal below is the judge's" % label,
              got == ("", ""), got)
    r = run_hook(page_input("set", bad), answer=TASK_FLAG, past=ALLOW)
    d = r.deny() or {}
    check("task item: item 99's step is denied by the judge, rule question-judge, one form-judge call", r.code == 0
          and d.get("permissionDecision") == "deny" and r.reason().startswith("question-judge: ")
          and r.log.count("\tdeny\tquestion-judge\t") == 1 and len(form_calls(r)) == 1, detail(r))
    check("task item: the one call is claude-opus-5-5, no effort", len(form_calls(r)) == 1
          and model_of(form_calls(r)[0]["argv"]) == QUESTION_MODEL and "--effort" not in form_calls(r)[0]["argv"], detail(r))
    prompt = form_calls(r)[0]["prompt"] if form_calls(r) else ""
    check("task item: the prompt holds item 99's step text", ITEM_99_STEP in prompt, prompt[:200])
    # The item's own strings are cut out first, so only the prompt's words can satisfy the rule check.
    rest = prompt.replace(ITEM_99_STEP, "").replace(TASK_WHY, "").lower()
    sentences = re.split(r"[.\n]", rest)
    check("task item: the prompt holds the whole-unit rule (quote the whole line or value, show the line after the change in full)",
          any("whole" in s and any(w in s for w in ("line", "value", "unit")) for s in sentences)
          and any("full" in s and any(w in s for w in ("after", "change")) for s in sentences), rest[:300])
    upd = run_hook(page_input("update", {"kind": "task", "steps": [ITEM_99_STEP]}), answer=TASK_FLAG, past=ALLOW)
    check("task item: an update that carries item 99's step (kind task) is denied after one form-judge call",
          (upd.deny() or {}).get("permissionDecision") == "deny" and len(form_calls(upd)) == 1
          and upd.log.count("\tdeny\tquestion-judge\t") == 1, detail(upd))
    ok = run_hook(page_input("set", good), answer=ALLOW)
    check("task item: a good task item (its step quotes the whole line before and after) is allowed after one form-judge call",
          ok.code == 0 and ok.out == "" and "\tdeny\t" not in ok.log and len(form_calls(ok)) == 1, detail(ok))
    writes = [{"op": "set", "collection": PAGE_ITEMS, "doc_id": "t99", "data": bad},
              {"op": "set", "collection": PAGE_ITEMS, "doc_id": "p1", "data": good_page_item()}]
    batch = run_hook(page_batch_input(writes), answer=ALLOW)
    prompt = form_calls(batch)[0]["prompt"] if form_calls(batch) else ""
    check("task batch: a task item and a decision make exactly one form-judge call, claude-opus-5-5",
          batch.code == 0 and batch.out == "" and len(form_calls(batch)) == 1
          and model_of(form_calls(batch)[0]["argv"]) == QUESTION_MODEL, detail(batch))
    check("task batch: the one prompt carries the task's step and the decision",
          ITEM_99_STEP in prompt and PAGE_MARK in prompt, prompt[:200])


def case_page_task_exempt_from_decision_items():
    # A task item has no Goal, Problem or pick, so decision items 1, 2 and 7 do not apply to it. The prompt for a
    # lone task write must say so, or the judge holds the task to items it cannot meet. Matched loosely: only the
    # sentences that name a task are read, and together they must exempt the Goal, the Problem and the recommended
    # option, carry a negation or an only-rule, and state what a task is judged on.
    r = run_hook(page_input("set", good_task_item()), answer=ALLOW)
    check("task exempt: a lone good task write makes one form-judge call, claude-opus-5-5, no effort",
          r.code == 0 and len(form_calls(r)) == 1 and model_of(form_calls(r)[0]["argv"]) == QUESTION_MODEL
          and "--effort" not in form_calls(r)[0]["argv"], detail(r))
    prompt = form_calls(r)[0]["prompt"] if form_calls(r) else ""
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
    r = run_hook(page_input("update", upd), answer=TASK_FLAG, past=ALLOW)
    d = r.deny() or {}
    check("task steps: an update of item 99's step with no kind is denied by the judge, rule question-judge, one call",
          r.code == 0 and d.get("permissionDecision") == "deny" and r.reason().startswith("question-judge: ")
          and r.log.count("\tdeny\tquestion-judge\t") == 1 and len(form_calls(r)) == 1, detail(r))
    prompt = form_calls(r)[0]["prompt"] if form_calls(r) else ""
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


# ------------------------------------------------------------------ a re-ask of an answered item (ruled Nov 1 17:44 CST)
#
# An owner's "none of these" note that gives a direction closes the item and becomes a step, so a write that asks
# the owner again with options gets the model review's rule question-judge. The rule's text reaches the model only
# when a write in the call is a re-ask. The text is read from hooks/call_judge.py at test time, never copied here.
REASK_NOTE = "Ship the plain page and drop the chart."
SHOW_CHEAPER_NOTE = "None fit; show me cheaper options."
PLAIN_NOTE = "Ship the plain page."
REASK_FLAG = ('{"ok": false, "reason": "the note already gives the direction, so the item closes and is not asked '
              'again."}')
ANSWERED_AT = "2026-11-01T17:44:00-06:00"


def none_direction_rule():
    """The rule's text, read from call_judge.py. "" when the constant is missing, so each check fails with its own
    detail and the other cases still run."""
    value = getattr(load_file_module(HOOK, "call_judge_none_probe"), "NONE_DIRECTION_RULE", "")
    return value if isinstance(value, str) and value.strip() else ""


def last_answer(note, choice="none", done=None):
    """The lastAnswer the owner's answer leaves on an item (docs/design/last-answer-notes.md). A task's answer carries
    `done` and no choice, so a `done` value leaves the choice out."""
    if done is None:
        return {"choice": choice, "note": note, "at": ANSWERED_AT}
    return {"done": done, "note": note, "at": ANSWERED_AT}


def reask_item(mark, note=REASK_NOTE, choice="none", done=None):
    """Data for an update of an answered decision: its options and the owner's note, no context."""
    return {"options": good_page_item(mark)["options"], "lastAnswer": last_answer(note, choice, done)}


def rule_detail(rule, r):
    return "NONE_DIRECTION_RULE missing" if not rule else detail(r)


def case_reask_update_holds_rule_once():
    # Case 1: an update with options and a lastAnswer note is a re-ask, so the one prompt holds the rule once.
    import question_form  # the one form check (hooks/question_form.py)
    fixture = reask_item(PAGE_MARK)
    got = question_form.item_hit("update", {"collection": PAGE_ITEMS, "doc_id": "p1", "data": fixture})
    check("re-ask fixture: the update passes question_form.item_hit, so a refusal below is the judge's", got == ("", ""),
          got)
    rule = none_direction_rule()
    r = run_hook(page_input("update", fixture), answer=ALLOW)
    prompt = form_calls(r)[0]["prompt"] if form_calls(r) else ""
    check("re-ask: an update with options and a lastAnswer note makes one form-judge call, and no deny",
          len(form_calls(r)) == 1 and r.code == 0 and r.out == "" and "\tdeny\t" not in r.log, detail(r))
    check("re-ask: the one prompt holds NONE_DIRECTION_RULE exactly once", bool(rule) and prompt.count(rule) == 1,
          rule_detail(rule, r))
    check("re-ask: the one prompt carries the owner's note", REASK_NOTE in prompt, prompt[:200])


def case_reask_cheaper_note_holds_rule_once():
    # Case 2: the note asks for other options. The model decides, so the rule still reaches it, and the fake's allow
    # gives no deny.
    rule = none_direction_rule()
    r = run_hook(page_input("update", reask_item(PAGE_MARK, SHOW_CHEAPER_NOTE)), answer=ALLOW)
    prompt = form_calls(r)[0]["prompt"] if form_calls(r) else ""
    check("re-ask, cheaper-options note: one form-judge call, and the model's allow is no deny",
          len(form_calls(r)) == 1 and r.code == 0 and r.out == "" and "\tdeny\t" not in r.log, detail(r))
    check("re-ask, cheaper-options note: the one prompt holds NONE_DIRECTION_RULE exactly once",
          bool(rule) and prompt.count(rule) == 1, rule_detail(rule, r))


def case_options_without_note_lacks_rule():
    # Case 3: options with no lastAnswer is not a re-ask. The call still makes its one form-judge call, so an early exit
    # cannot pass this check.
    rule = none_direction_rule()
    r = run_hook(page_input("update", {"options": good_page_item()["options"]}), answer=ALLOW)
    prompt = form_calls(r)[0]["prompt"] if form_calls(r) else ""
    check("no re-ask, options only: one form-judge call, and no deny", len(form_calls(r)) == 1 and r.code == 0 and r.out == ""
          and "\tdeny\t" not in r.log, detail(r))
    check("no re-ask, options only: the prompt lacks NONE_DIRECTION_RULE", bool(rule) and prompt.count(rule) == 0,
          rule_detail(rule, r))


def case_blank_note_lacks_rule():
    # Case 4: a note that is blank after strip is not a direction, so the write is not a re-ask.
    rule = none_direction_rule()
    data = {"options": good_page_item()["options"], "lastAnswer": last_answer("  ")}
    r = run_hook(page_input("update", data), answer=ALLOW)
    prompt = form_calls(r)[0]["prompt"] if form_calls(r) else ""
    check("no re-ask, blank note: one form-judge call, and no deny", len(form_calls(r)) == 1 and r.code == 0 and r.out == ""
          and "\tdeny\t" not in r.log, detail(r))
    check("no re-ask, blank note: the prompt lacks NONE_DIRECTION_RULE", bool(rule) and prompt.count(rule) == 0,
          rule_detail(rule, r))


def case_context_only_note_lacks_rule():
    # Case 5: a context-only write has no options, so a note on it is not a re-ask.
    rule = none_direction_rule()
    data = {"context": good_page_item()["context"], "lastAnswer": last_answer(REASK_NOTE)}
    r = run_hook(page_input("update", data), answer=ALLOW)
    prompt = form_calls(r)[0]["prompt"] if form_calls(r) else ""
    check("no re-ask, context only with a note: one form-judge call, and no deny",
          len(form_calls(r)) == 1 and r.code == 0 and r.out == "" and "\tdeny\t" not in r.log, detail(r))
    check("no re-ask, context only with a note: the prompt lacks NONE_DIRECTION_RULE",
          bool(rule) and prompt.count(rule) == 0, rule_detail(rule, r))


def case_reask_batch_one_call_rule_once():
    # Case 6: two re-asks in one batch make one form-judge call, and the one prompt holds the rule once, not once per write.
    rule = none_direction_rule()
    writes = [{"op": "set", "collection": PAGE_ITEMS, "doc_id": "p1",
               "data": good_page_item(PAGE_MARK, lastAnswer=last_answer(REASK_NOTE))},
              {"op": "update", "collection": PAGE_ITEMS, "doc_id": "p2", "data": reask_item(PAGE_MARK_B, SHOW_CHEAPER_NOTE)}]
    r = run_hook(page_batch_input(writes), answer=ALLOW)
    prompt = form_calls(r)[0]["prompt"] if form_calls(r) else ""
    check("re-ask batch: two re-asks make one form-judge call, claude-opus-5-5, and no deny",
          len(form_calls(r)) == 1 and model_of(form_calls(r)[0]["argv"]) == QUESTION_MODEL and r.code == 0 and r.out == ""
          and "\tdeny\t" not in r.log, detail(r))
    check("re-ask batch: the one prompt carries both writes", PAGE_MARK in prompt and PAGE_MARK_B in prompt,
          prompt[:200])
    check("re-ask batch: the one prompt holds NONE_DIRECTION_RULE exactly once", bool(rule) and prompt.count(rule) == 1,
          rule_detail(rule, r))


def case_reask_refusal_denies():
    # Case 7: case 1's write, and the fake refuses it. The deny is question-judge, and the prompt holds the rule
    # once, so this case is red on main for the rule and not for the deny.
    rule = none_direction_rule()
    r = run_hook(page_input("update", reask_item(PAGE_MARK)), answer=REASK_FLAG, past=ALLOW)
    d = r.deny() or {}
    prompt = form_calls(r)[0]["prompt"] if form_calls(r) else ""
    check("re-ask refusal: the judge's deny is rule question-judge, one deny line, one form-judge call",
          r.code == 0 and d.get("permissionDecision") == "deny" and r.reason().startswith("question-judge: ")
          and "already gives the direction" in r.reason() and r.log.count("\tdeny\tquestion-judge\t") == 1
          and len(form_calls(r)) == 1, detail(r))
    check("re-ask refusal: the one prompt holds NONE_DIRECTION_RULE exactly once", bool(rule) and prompt.count(rule) == 1,
          rule_detail(rule, r))


def case_picked_choice_with_note_lacks_rule():
    # A picked choice (a key) with a note is the owner choosing an option, not a "none of these" direction, so the
    # write is no re-ask. The call still makes its one form-judge call, so an early exit cannot pass this check.
    import question_form  # the one form check (hooks/question_form.py)
    fixture = reask_item(PAGE_MARK, PLAIN_NOTE, choice="a")
    got = question_form.item_hit("update", {"collection": PAGE_ITEMS, "doc_id": "p1", "data": fixture})
    check("picked-choice fixture: the update passes question_form.item_hit, so a refusal below is the judge's",
          got == ("", ""), got)
    rule = none_direction_rule()
    r = run_hook(page_input("update", fixture), answer=ALLOW)
    prompt = form_calls(r)[0]["prompt"] if form_calls(r) else ""
    check("picked choice with a note: one form-judge call, and no deny",
          len(form_calls(r)) == 1 and r.code == 0 and r.out == "" and "\tdeny\t" not in r.log, detail(r))
    check("picked choice with a note: the prompt lacks NONE_DIRECTION_RULE", bool(rule) and prompt.count(rule) == 0,
          rule_detail(rule, r))


def case_none_choice_with_note_holds_rule_once():
    # The same write with choice none is a "none of these" re-ask, so the one prompt holds the rule once.
    rule = none_direction_rule()
    r = run_hook(page_input("update", reask_item(PAGE_MARK, PLAIN_NOTE, choice="none")), answer=ALLOW)
    prompt = form_calls(r)[0]["prompt"] if form_calls(r) else ""
    check("none choice with a note: one form-judge call, and no deny",
          len(form_calls(r)) == 1 and r.code == 0 and r.out == "" and "\tdeny\t" not in r.log, detail(r))
    check("none choice with a note: the one prompt holds NONE_DIRECTION_RULE exactly once",
          bool(rule) and prompt.count(rule) == 1, rule_detail(rule, r))


def case_done_answer_is_not_reask():
    # A task's answer carries `done` and no choice: "Marked done." or "Not marked done." (docs/design/last-answer-notes.md,
    # section 4). It gives no "none of these" direction, so the one form prompt lacks the rule. The form judge still runs,
    # so an early exit cannot pass this check. The dedicated past-ruling call is not a form call, so form_calls skips it.
    import question_form  # the one form check (hooks/question_form.py)
    rule = none_direction_rule()
    for done in (False, True):
        fixture = reask_item(PAGE_MARK, done=done)
        got = question_form.item_hit("update", {"collection": PAGE_ITEMS, "doc_id": "p1", "data": fixture})
        check("done=%s fixture: the update passes question_form.item_hit, so a refusal below is the judge's" % done,
              got == ("", ""), got)
        r = run_hook(page_input("update", fixture), answer=ALLOW)
        prompt = form_calls(r)[0]["prompt"] if form_calls(r) else ""
        check("done=%s answer: one form-judge call, and no deny" % done,
              len(form_calls(r)) == 1 and r.code == 0 and r.out == "" and "\tdeny\t" not in r.log, detail(r))
        check("done=%s answer: the form prompt lacks NONE_DIRECTION_RULE" % done,
              bool(rule) and prompt.count(rule) == 0, rule_detail(rule, r))


# ------------------------------------------------------------------ the widening rule (decision uniform-over-variants)
#
# An option that widens what a shared tool accepts is marked `widens: true`, and an unmarked widening option is
# refused. The judge is told in call_judge.WIDENING_RULE, appended once to the
# formatted PAGE_PROMPT for a judged write that sets or updates options. The mark's key is question_form.WIDENS_KEY.
# A build without that name gets the sentinel, so a marked option carries no mark and the scope check fails on its cause.
WIDENS_SENTINEL = "__no-WIDENS_KEY-in-question_form__"
QF_PATH = os.path.join(HERE, "question_form.py")
WIDENING_FLAG = '{"ok": false, "reason": "option `b` widens a shared tool; mark it widens: true"}'


def widening_rule():
    """WIDENING_RULE's text, read from call_judge.py. "" when the constant is missing or blank."""
    value = getattr(load_file_module(HOOK, "call_judge_widen_probe"), "WIDENING_RULE", "")
    return value if isinstance(value, str) and value.strip() else ""


def widens_key():
    """question_form.WIDENS_KEY, the one home of the mark's key. "" when the constant is missing or blank."""
    value = getattr(load_file_module(QF_PATH, "question_form_widen_probe"), "WIDENS_KEY", "")
    return value if isinstance(value, str) and value.strip() else ""


def hook_template(name):
    """A prompt template of call_judge.py (PAGE_PROMPT, QUESTION_PROMPT or SPAWN_PROMPT), read at test time."""
    value = getattr(load_file_module(HOOK, "call_judge_widen_probe"), name, "")
    return value if isinstance(value, str) else ""


def widening_region(prompt, template_name):
    """The text a judged prompt adds after its formatted template and before the past-ruling tail, where the widening
    rule goes. None when the prompt does not hold the template formatted with the call's JSON."""
    head, mark, suffix = hook_template(template_name).partition("%s")
    if not mark or not prompt.startswith(head) or suffix not in prompt:
        return None
    after = prompt[prompt.index(suffix) + len(suffix):]
    import question_form  # the one home of the past-ruling tail (candidates_block)
    return after.split(question_form.candidates_block([], []).split("(none found)", 1)[0], 1)[0]


def rule_once(prompt, rule):
    """(ok, cause) for one judged item prompt: WIDENING_RULE is in it exactly once, after the question-format prompt.
    The cause names one thing: no text in that slot, a missing constant, or a count other than one."""
    region = widening_region(prompt, "PAGE_PROMPT")
    if region is None:
        return False, "the judge's prompt is not the question-format prompt"
    if not region.strip():
        return False, "no text after the question-format prompt: the judge is not told the widening mark"
    if not rule:
        return False, "WIDENING_RULE is not defined in call_judge.py"
    count = prompt.count(rule)
    return count == 1, "WIDENING_RULE is in the judge's prompt %d times, not once" % count


def no_widening_rule(prompt, template_name):
    """(ok, cause) for a prompt that must carry no widening rule: nothing in its widening slot."""
    region = widening_region(prompt, template_name)
    if region is None:
        return False, "the prompt is not %s formatted with the call" % template_name
    return region.strip() == "", "%s carries text in the widening slot with no widening option: %r" % (
        template_name, region.strip()[:60])


def case_widening_set_holds_rule_once():
    # Case 1: a set with options, none marked, makes one form-judge call, and the one prompt holds the rule once.
    rule = widening_rule()
    r = run_hook(page_input("set", good_page_item()), answer=ALLOW)
    check("widening set: one form-judge call, and no deny", len(form_calls(r)) == 1 and r.code == 0 and r.out == ""
          and "\tdeny\t" not in r.log, detail(r))
    prompt = form_calls(r)[0]["prompt"] if form_calls(r) else ""
    ok, cause = rule_once(prompt, rule)
    check("widening set: the one prompt holds WIDENING_RULE exactly once, after the question-format prompt", ok, cause)


def case_widening_batch_holds_rule_once():
    # Case 2: two option writes in one batch make one form-judge call, and the one prompt holds the rule exactly once.
    rule = widening_rule()
    writes = [{"op": "set", "collection": PAGE_ITEMS, "doc_id": "p1", "data": good_page_item(PAGE_MARK)},
              {"op": "update", "collection": PAGE_ITEMS, "doc_id": "p2",
               "data": {"options": good_page_item(PAGE_MARK_B)["options"]}}]
    r = run_hook(page_batch_input(writes), answer=ALLOW)
    check("widening batch: two option writes make one form-judge call, and no deny", len(form_calls(r)) == 1 and r.code == 0
          and r.out == "" and "\tdeny\t" not in r.log, detail(r))
    prompt = form_calls(r)[0]["prompt"] if form_calls(r) else ""
    check("widening batch: the one prompt carries both writes", PAGE_MARK in prompt and PAGE_MARK_B in prompt,
          prompt[:160])
    ok, cause = rule_once(prompt, rule)
    check("widening batch: the one prompt holds WIDENING_RULE exactly once, after the question-format prompt", ok, cause)


def case_widening_absent_without_options():
    # Case 3: a write with no options, a write with an empty options list, a box and a spawn get no widening rule. Each
    # absence first asserts that its call was made, so an early exit cannot pass it. The box has options and still gets none.
    context = good_page_item()["context"]
    for label, inp, template in (
        ("a context-only update", page_input("update", {"context": context}), "PAGE_PROMPT"),
        ("an update with context and empty options", page_input("update", {"context": context, "options": []}),
         "PAGE_PROMPT"),
        ("an AskUserQuestion box with options", question_input(), "QUESTION_PROMPT"),
        ("an Agent spawn", spawn_input("builder", model="sonnet"), "SPAWN_PROMPT"),
    ):
        r = run_hook(inp, answer=ALLOW)
        check("widening absent: %s is judged once, and no deny" % label, len(form_calls(r)) == 1 and r.code == 0
              and r.out == "" and "\tdeny\t" not in r.log, detail(r))
        prompt = form_calls(r)[0]["prompt"] if form_calls(r) else ""
        ok, cause = no_widening_rule(prompt, template)
        check("widening absent: %s gets no widening rule" % label, ok, cause)


def case_widening_refusal_names_the_option():
    # Case 4: an unmarked option that widens a shared tool is refused, and the refusal names its key. The model is faked,
    # so the deny is the hook passing the reason through. The rule check reads what the judge is told before it answers.
    import question_form  # the one form check (hooks/question_form.py)
    rule = widening_rule()
    item = good_page_item(PAGE_MARK)
    item["options"][1]["label"] = "Accept a second accepted form"
    got = question_form.item_hit("set", {"collection": PAGE_ITEMS, "doc_id": "p1", "data": item})
    check("widening refusal fixture: the item passes question_form.item_hit, so a refusal below is the judge's",
          got == ("", ""), got)
    r = run_hook(page_input("set", item), answer=WIDENING_FLAG, past=ALLOW)
    d = r.deny() or {}
    check("widening refusal: the unmarked option is denied, rule question-judge, and the reason names its key",
          r.code == 0 and d.get("permissionDecision") == "deny" and r.reason().startswith("question-judge: ")
          and "option `b`" in r.reason() and r.log.count("\tdeny\tquestion-judge\t") == 1 and len(form_calls(r)) == 1,
          detail(r))
    prompt = form_calls(r)[0]["prompt"] if form_calls(r) else ""
    ok, cause = rule_once(prompt, rule)
    check("widening refusal: the judge's prompt holds WIDENING_RULE exactly once, after the question-format prompt",
          ok, cause)


def case_widening_fair_option_passes_code_path():
    # Case 5: a fair option whose label only names a repo, and a marked option that is not the pick. The fake model allows, and
    # the guard path (question_form.page_item_hit, the filter guard.py reads) does not refuse the write either. The scope
    # check proves the mark is read: the same marked option, picked, is refused as uniform-pick.
    # The model's false-flag rate on real items is unmeasured, since the model is faked.
    import question_form  # the one form check (hooks/question_form.py)
    rule, key = widening_rule(), widens_key()
    mark_key = key or WIDENS_SENTINEL
    fair = {"key": "a", "label": "Keep the change in claude-settings",
            "gain": "The change lands in the repo today. " + PAGE_MARK, "lose": "The shared tool keeps its one form."}
    marked = {"key": "b", "label": "Accept a second accepted form", "gain": "Other repos read the shared tool alike.",
              "lose": "The shared tool takes a second form.", mark_key: True}
    item = good_page_item(PAGE_MARK, pick="a", options=[fair, marked])
    got = question_form.item_hit("set", {"collection": PAGE_ITEMS, "doc_id": "p1", "data": item})
    check("fair option fixture: the item passes question_form.item_hit with the pick on the fair option",
          got == ("", ""), got)
    tool_input = {"action": "set", "url": PAGE_URL, "collection": PAGE_ITEMS, "doc_id": "p1", "data": item}
    hit, _writes = question_form.page_item_hit(tool_input, PAGE_REPO)
    check("fair option code path: question_form.page_item_hit does not refuse it", hit == ("", ""), hit)
    r = run_hook(page_input("set", item), answer=ALLOW)
    check("fair option code path: one judge call and no deny from call_judge", len(form_calls(r)) == 1 and r.code == 0
          and r.out == "" and "\tdeny\t" not in r.log, detail(r))
    picked = dict(item, pick="b")
    got = question_form.item_hit("set", {"collection": PAGE_ITEMS, "doc_id": "p1", "data": picked})
    check("widening scope: the marked option, picked, is refused as uniform-pick, so the mark is read",
          got[0] == "uniform-pick", "the marked option carries no mark: question_form.WIDENS_KEY is not defined"
          if not key else got)
    prompt = form_calls(r)[0]["prompt"] if form_calls(r) else ""
    ok, cause = rule_once(prompt, rule)
    check("fair option code path: the judge's prompt holds WIDENING_RULE exactly once, after the question-format prompt",
          ok, cause)


def case_widening_rule_names_the_mark():
    # Case 6: WIDENING_RULE contains question_form.WIDENS_KEY. Each name is its own check, so a missing name fails with
    # its own cause, and a blank key cannot pass the containment check.
    rule, key = widening_rule(), widens_key()
    check("widening key: call_judge.WIDENING_RULE is defined as non-blank text", bool(rule),
          "WIDENING_RULE is not defined in call_judge.py")
    check("widening key: question_form.WIDENS_KEY is defined as non-blank text", bool(key),
          "WIDENS_KEY is not defined in question_form.py")
    cause = ("WIDENING_RULE is not defined" if not rule else "WIDENS_KEY is not defined" if not key
             else "WIDENING_RULE does not contain WIDENS_KEY")
    check("widening key: WIDENING_RULE contains WIDENS_KEY", bool(rule) and bool(key) and key in rule, cause)


def case_fail_open():
    for label, inp, kwargs in (
        ("a model failure on a spawn", spawn_input("builder", model="sonnet"), {"model_fail": True}),
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
    # Re-pointed for the owner-question sends: the one command hook also runs on the two send tools, and no other.
    check("settings: its matcher is Agent, AskUserQuestion, ArtifactData and the two send tools",
          matcher == {"Agent", "AskUserQuestion", "ArtifactData", SEND_MCP, SEND_BUILTIN}, entry.get("matcher"))
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
    # Re-pointed (dedicated past-ruling call, page item writes): the ruling reaches the call that checks item 8.
    prompt = past_calls(r)[0]["prompt"] if past_calls(r) else ""
    check("past ruling 133: the dedicated call holds the step c95 ruling sentence",
          len(past_calls(r)) == 1 and CI_STEP_SENTENCE in without_call(prompt, item), detail(r))


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
    check("past ruling cost: a judged page write runs one git process, in its dedicated call",
          len(past_calls(p)) == 1 and len(form_calls(p)) == 1 and p.git == 1, detail(p))
    q = run_hook(question_input(box=good_box(), cwd=BARE_REPO), answer=ALLOW)
    check("past ruling cost: a judged question with no roadmap ref runs at most one git process",
          len(q.calls) == 1 and q.git <= 1, detail(q))
    f = run_hook(question_input(box=good_box(problem=None), cwd=CI_REPO), answer=ALLOW)
    check("past ruling cost: a box refused by the form makes no model call and no git process",
          f.calls == [] and f.git == 0 and (f.deny() or {}).get("permissionDecision") == "deny", detail(f))


# ------------------------------------------------------------------ unvetted marker and docs/debts
#
# When the model review cannot run (a model error, or a decisions folder or roadmap ref that cannot be read), a question
# is refused once, and its remedy adds an `Unvetted: <reason>` line. A question that already carries the line gets one
# model attempt. If that attempt fails, the question passes, because the line tells the owner no check ran.
# The closed page items notice alone never triggers it. docs/debts/*.md records reach the candidates, one line each.
UNVETTED_LINE = "Unvetted: the model review could not run, so the owner reads this question unchecked."
DEBT_SLUG = "settled-question-unchecked"
DEBT_WHAT = "a settled question reached the owner with no past-ruling check. Marker debt-9d3e."
FULL_REPO = make_repo("full", decisions={APPS_SLUG: APPS_RULING}, steps={CI_STEP_ID: CI_STEP_SENTENCE})
DEBTS_REPO = make_repo("debts", decisions={APPS_SLUG: APPS_RULING}, steps={CI_STEP_ID: CI_STEP_SENTENCE},
                       debts={DEBT_SLUG: DEBT_WHAT})


def case_unvetted_marker():
    box = good_box(goal=APPS_GOAL, problem=APPS_PROBLEM, based=APPS_BASED, options=APPS_OPTIONS)
    r = run_hook(question_input(box=box, cwd=DECISIONS_REPO), answer=ALLOW, model_fail=True)
    check("unvetted box: a model error refuses the question once, the remedy names Unvetted:",
          r.code == 0 and (r.deny() or {}).get("permissionDecision") == "deny" and "Unvetted:" in r.reason()
          and len(r.calls) == 1, detail(r))
    marked = good_box(goal=APPS_GOAL, problem=APPS_PROBLEM, based=APPS_BASED, options=APPS_OPTIONS)
    marked["questions"][0]["question"] += "\n" + UNVETTED_LINE
    r = run_hook(question_input(box=marked, cwd=DECISIONS_REPO), answer=ALLOW, model_fail=True)
    check("unvetted box: the same question with an Unvetted: line passes after one model attempt, the check always runs",
          r.code == 0 and r.out == "" and len(r.calls) == 1 and "\tdeny\t" not in r.log, detail(r))


def case_unvetted_page_marker():
    item = good_page_item()
    r = run_hook(page_input("set", item, cwd=DECISIONS_REPO), answer=ALLOW, model_fail=True)
    check("unvetted page: a model error refuses the item write once, the remedy names Unvetted:",
          r.code == 0 and (r.deny() or {}).get("permissionDecision") == "deny" and "Unvetted:" in r.reason()
          and len(r.calls) == 1, detail(r))
    marked = good_page_item(context=item["context"] + "\n" + UNVETTED_LINE)
    r = run_hook(page_input("set", marked, cwd=DECISIONS_REPO), answer=ALLOW, model_fail=True)
    # Re-pointed: the attempt that counts is the dedicated call. The form judge is not held to one call here.
    check("unvetted page: the same item with an Unvetted: line in context passes after one dedicated attempt",
          r.code == 0 and r.out == "" and len(past_calls(r)) == 1 and "\tdeny\t" not in r.log, detail(r))


def case_unvetted_not_for_closed_items():
    # Every source reads (decisions and roadmap). Only the closed page items notice is unknown, so it never refuses.
    r = run_hook(question_input(box=good_box(), cwd=FULL_REPO), answer=ALLOW)
    check("unvetted: the closed page items notice alone does not refuse, the call is allowed",
          r.code == 0 and r.out == "" and len(r.calls) == 1 and "\tdeny\t" not in r.log and "Unvetted" not in r.err,
          detail(r))


def case_past_ruling_debt_candidates():
    box = good_box(goal=APPS_GOAL, problem=APPS_PROBLEM, based=APPS_BASED, options=APPS_OPTIONS)
    r = run_hook(question_input(box=box, cwd=DEBTS_REPO), answer=ALLOW)
    prompt = r.calls[0]["prompt"] if r.calls else ""
    rest = without_call(prompt, box)
    check("past ruling debts: a docs/debts record's slug and What line reach the candidates",
          len(r.calls) == 1 and DEBT_SLUG in rest and DEBT_WHAT in rest, detail(r))


def case_unshown_id_takes_the_unvetted_path():
    # Index shape (spec, Nov 1 18:58 CST): a refusal whose reason cites a record id the index did not show is a model
    # error, so it takes the Unvetted path and never stands as a plain refusal.
    box = good_box(goal=APPS_GOAL, problem=APPS_PROBLEM, based=APPS_BASED, options=APPS_OPTIONS)
    bogus = json.dumps({"ok": False, "reason": "decisions/no-such-record: this was already decided."})
    r = run_hook(question_input(box=box, cwd=DECISIONS_REPO), answer=bogus)
    check("unshown id: a refusal citing an id not shown takes the Unvetted path, not a plain refusal",
          r.code == 0 and (r.deny() or {}).get("permissionDecision") == "deny" and "Unvetted:" in r.reason(),
          detail(r))


def case_marker_does_not_skip_the_check():
    # The Unvetted line never skips the check. A marker written ahead of time, with a working model, still runs the
    # check, which refuses a ruled question.
    box = good_box(goal=APPS_GOAL, problem=APPS_PROBLEM, based=APPS_BASED, options=APPS_OPTIONS)
    box["questions"][0]["question"] += "\n" + UNVETTED_LINE
    refuse = json.dumps({"ok": False, "reason": "decisions/%s: already decided by the keep-the-apps ruling." % APPS_SLUG})
    r = run_hook(question_input(box=box, cwd=DECISIONS_REPO), answer=refuse)
    check("unvetted marker: a marker written ahead of time does not skip the check, which refuses the ruled question",
          len(r.calls) == 1 and (r.deny() or {}).get("permissionDecision") == "deny" and "Unvetted:" not in r.reason(),
          detail(r))


def case_unknown_names_the_claude_settings_records():
    # The claude-settings checkout comes from guard_pointer.pointer_checkout(). This repo has its own docs/decisions and
    # no pointer, so the claude-settings records are unread, and the unknown notice names them.
    r = run_hook(question_input(box=good_box(), cwd=DECISIONS_REPO), answer=ALLOW)
    notes = [line for line in r.err.splitlines() if PAST_UNKNOWN in line]
    check("past ruling unknown: with its own decisions and no pointer, the notice names the claude-settings records",
          len(notes) == 1 and "claude-settings" in notes[0], detail(r))


def case_cite_of_a_shown_record_is_not_bogus():
    # A reason citing a shown record with a .md suffix, with or without the docs/ prefix, is a real cite. It is a plain
    # refusal, never the Unvetted path.
    box = good_box(goal=APPS_GOAL, problem=APPS_PROBLEM, based=APPS_BASED, options=APPS_OPTIONS)
    for cite in ("decisions/%s.md" % APPS_SLUG, "docs/decisions/%s.md" % APPS_SLUG):
        answer = json.dumps({"ok": False, "reason": "%s: already decided by the keep-the-apps ruling." % cite})
        r = run_hook(question_input(box=box, cwd=DECISIONS_REPO), answer=answer)
        check("cite: a refusal citing %s (a shown record) is a plain refusal, not Unvetted" % cite,
              r.code == 0 and (r.deny() or {}).get("permissionDecision") == "deny" and "Unvetted:" not in r.reason(),
              detail(r))


def case_page_task_gets_item_8_and_is_refused():
    # A page task gets item 8 too. A task that asks a ruled question carries the ruling and item 8, and the judge refuses
    # it. The item text never exempts a task.
    import question_form  # the one form check (hooks/question_form.py)
    task = good_task_item(step="Decide whether the GitHub apps keep their access to claude-settings, then say so in chat.")
    got = question_form.item_hit("set", {"collection": PAGE_ITEMS, "doc_id": "t8", "data": task})
    check("page task fixture: the task passes item_hit, so the model judges it", got == ("", ""), got)
    refuse = json.dumps({"ok": False, "reason": "decisions/%s: already decided by the keep-the-apps ruling." % APPS_SLUG})
    r = run_hook(page_input("set", task, doc_id="t8", cwd=DECISIONS_REPO), answer=refuse)
    # Re-pointed: the refusal comes from the dedicated call, which carries item 8 and the ruling. No form call follows it.
    prompt = past_calls(r)[0]["prompt"] if past_calls(r) else ""
    check("page task: the one model call is the dedicated call, and it carries item 8 and the ruling",
          len(r.calls) == 1 and len(past_calls(r)) == 1 and len(form_calls(r)) == 0 and item_text(prompt, 8) != ""
          and APPS_RULING in without_call(prompt, task), detail(r))
    check("page task: the item never exempts a task from item 8",
          "never applies to a task" not in item_text(prompt, 8).lower(), item_text(prompt, 8)[:200])
    check("page task: a ruled task is refused by the judge", (r.deny() or {}).get("permissionDecision") == "deny"
          and "Unvetted:" not in r.reason(), detail(r))


def case_mid_reason_unlisted_id_is_a_plain_refusal():
    # An item 1 to 7 refusal that names an unlisted id mid-reason is a plain refusal. A reason that opens with an
    # unlisted id is still a bogus cite, and takes the Unvetted path.
    box = good_box(goal=APPS_GOAL, problem=APPS_PROBLEM, based=APPS_BASED, options=APPS_OPTIONS)
    mid = json.dumps({"ok": False, "reason": "Item 5: explain decisions/zzz in plain words."})
    r = run_hook(question_input(box=box, cwd=DECISIONS_REPO), answer=mid)
    check("unlisted id mid-reason: an item 5 refusal that names decisions/zzz stays a plain refusal, not Unvetted",
          (r.deny() or {}).get("permissionDecision") == "deny" and "Unvetted:" not in r.reason(), detail(r))
    opens = json.dumps({"ok": False, "reason": "decisions/zzz: already decided."})
    r = run_hook(question_input(box=box, cwd=DECISIONS_REPO), answer=opens)
    check("unlisted id opening the reason: still a bogus cite, takes the Unvetted path",
          "Unvetted:" in r.reason(), detail(r))


# ------------------------------------------------------------------ owner questions sent to a session (send tools)
#
# A send_message or SendMessage whose message carries a Goal line and a Problem line is an owner question. It
# gets the past-ruling check, the one home lint/report_guard.py past_ruling_problem, before it is sent, whoever the target
# is: the page writer is not special. Any other send makes no model call and starts no subprocess.
from shared_names import SEND_TOOLS  # noqa: E402  the one home of the send tool names (hooks/shared_names.py)
SEND_MCP, SEND_BUILTIN = SEND_TOOLS
SEND_TARGET = "session_lane07"  # a lane, not the page writer: a send with the form is judged all the same
REPORT_GUARD = os.path.join(REPO, "lint", "report_guard.py")
# The two page items the past-ruling cases use, verbatim. Inline on purpose: a test run reads no file outside the repo.
INCIDENT_357 = "\n".join([
    "Page item for the owner (from coordinator). Title: How should a merge free disk without losing a running agent's work?",
    "Goal: a merge frees disk without losing a running agent's work.",
    "Problem (risk): freeing a running agent's worktree loses its uncommitted files.",
    "Based on (read): guard rule worktree-home already stops an agent whose worktree is gone, so it cannot write into main.",
    "Departs from: main, where the merge frees any lock it finds. Each option adds a test before the free.",
    "Options: a. Never free a running agent's lock; the worktree goes when the agent ends. b. Save, then free: copy "
    "uncommitted changes to an archive ref, then remove the worktree. c. Both: a for running agents, b for finished ones "
    "(recommended).",
])
INCIDENT_370 = "\n".join([
    "Page item for the owner (from coordinator). Title: Should the guard catch a write into the main checkout from a "
    "session that stands outside every checkout?",
    "Goal: a write into the main checkout from a session that stands outside any checkout gets caught.",
    'Problem (rule): the guard lets it pass, because a working folder in no checkout has no "other" checkout.',
    "Based on (read): the notes sort found this gap.",
    'Departs from: main, where a working folder in no checkout passes every write. Option b counts the main checkout as '
    '"other" for such a session.',
    'Options: a. Keep main (recommended until an incident names it). b. The main checkout counts as "other" for a session '
    "outside every checkout.",
])
# One fixture ruling per incident. Each holds a marker the question never holds, so the prompt check finds it there.
WORKTREE_SLUG, OUTSIDE_SLUG = "when-a-worktree-may-be-removed", "an-agent-outside-its-home-tree-must-stop"
WORKTREE_MARK, OUTSIDE_MARK = "worktree-5e8a", "outside-2b7f"
WORKTREE_RULING = ("Owner, 2026-10-30: a worktree goes only when it is clean and idle, and a running agent's lock is "
                   "never freed. Marker " + WORKTREE_MARK + ".")
OUTSIDE_RULING = ("Owner, 2026-10-30: each session writes only inside its own checkout, and an agent whose worktree is "
                  "gone stops and reports. Marker " + OUTSIDE_MARK + ".")
INCIDENT_REPO = make_repo("incidents", decisions={WORKTREE_SLUG: WORKTREE_RULING, OUTSIDE_SLUG: OUTSIDE_RULING})
WORKTREE_OPTIONS = [
    {"label": "Never free a running lock (Recommended)",
     "description": "Gain: a running agent keeps its uncommitted files. Lose: the worktree stays until the agent ends."},
    {"label": "Save, then free",
     "description": "Gain: the worktree goes now. Lose: the archive ref must be cleaned up later."}]
BASED_READ_357 = ("Based on (read): guard rule worktree-home already stops an agent whose worktree is gone, so it cannot "
                  "write into main.")
BASED_RULING_357 = ("Based on (ruling): decisions/%s says a worktree goes only when clean and idle. This case has a running "
                    "agent, so the owner is asked again: the ruling does not name it." % WORKTREE_SLUG)
# Sends that are no owner question. The last is a full-size message, near the 64 KiB send bound.
NO_FORM = (
    ("a status line", "Status: lane 4 is green on lint/test_stamp.py. Nothing needs your word."),
    ("a lane brief with a Goal line and no Problem line",
     "Lane brief: stamp-split. Topic: lint.\nGoal: split the stamp job in two.\nFiles: lint/stamp.py.\n"
     "Check: python3 lint/test_stamp.py."),
    ("a Goal line and a Based on line, no Problem line",
     "Goal: know which rule owns the stamp.\nBased on (read): the stamp rule is in lint/stamp.py."),
    ("an empty message", ""),
    ("a full-size status, under the 64 KiB send bound", "Lane 4 log: ruff clean, no finding. " * 1700),
)


def ruled(slug):
    # A canned refusal that cites the one record the model was shown, with its date, as item 8 asks.
    return json.dumps({"ok": False, "reason": "decisions/%s: ruled 2026-10-30, so the owner is not asked again." % slug})


def send_input(tool, message, cwd=INCIDENT_REPO, target=SEND_TARGET, session=SID_A):
    """One send, as the harness sends it. The mcp tool names its target by session_id, SendMessage by to."""
    if tool == SEND_MCP:
        tool_input = {"session_id": target, "message": message}
    else:
        tool_input = {"to": target, "message": message, "summary": "owner question"}
    return json.dumps({"session_id": session, "tool_name": tool, "tool_input": tool_input, "cwd": cwd})


def guard_constant(path, name):
    """One constant of a hook or lint file, read at test time and never copied. "" when the file or the name is absent,
    so a check names the missing piece instead of crashing."""
    try:
        return getattr(load_file_module(path, "probe_" + name), name, "") or ""
    except Exception:
        return ""


def relay_remedy():
    """The remedy of the Stop hook's past-ruling refusal (lint/report_guard.py RELAY_RULE_REASON): its text from `Remedy:`."""
    text = guard_constant(REPORT_GUARD, "RELAY_RULE_REASON")
    return text[text.find("Remedy:"):] if "Remedy:" in text else ""


def unvetted_marker(text):
    """The backtick span an Unvetted remedy asks for: `Unvetted: <why it could not be checked>`."""
    found = re.search(r"`Unvetted: [^`]*`", text or "")
    return found.group(0) if found else ""


def case_send_owner_question_is_judged_before_it_is_sent():
    # Both incidents, through both send tools. Scope first: the model is called and its prompt holds the ruling record.
    # Then the verdict: a deny, rule past-ruling, with the relay remedy.
    import question_form  # the one form check (hooks/question_form.py)
    remedy = relay_remedy()
    for label, text, slug, mark in (("357", INCIDENT_357, WORKTREE_SLUG, WORKTREE_MARK),
                                    ("370", INCIDENT_370, OUTSIDE_SLUG, OUTSIDE_MARK)):
        check("send incident %s carries the form: a Goal line and a Problem line" % label,
              bool(question_form.GOAL_LINE.search(text)) and bool(question_form.PROBLEM_LINE.search(text)), label)
        for tool in SEND_TOOLS:
            name = "send incident %s via %s" % (label, tool)
            r = run_hook(send_input(tool, text), answer=ruled(slug))
            check(name + ": the one model call is made before the send", len(r.calls) == 1, detail(r))
            prompt = r.calls[0]["prompt"] if r.calls else ""
            check(name + ": the prompt carries the ruling record", mark in prompt, detail(r))
            check(name + ": the send is denied", (r.deny() or {}).get("permissionDecision") == "deny", detail(r))
            check(name + ": the refusal rule is past-ruling", r.reason().startswith("past-ruling: "), r.reason()[:160])
            check(name + ": the refusal carries the relay remedy", bool(remedy) and remedy in r.reason(),
                  "remedy %r, reason %r" % (remedy[:40], r.reason()[-160:]))


def case_question_box_with_the_same_ruling_is_refused_as_past_ruling():
    # Control, green today: the same canned refusal on the same repo, through AskUserQuestion, is refused as past-ruling.
    # So a red send case is the missing send route, and not a fixture or a repo that cannot refuse.
    box = good_box(goal="Goal: a merge frees disk without losing a running agent's work.",
                   problem="Problem (risk): freeing a running agent's worktree loses its uncommitted files.",
                   based=("Based on (read): guard rule worktree-home already stops an agent whose worktree is gone.",),
                   options=WORKTREE_OPTIONS)
    r = run_hook(question_input(box=box, cwd=INCIDENT_REPO), answer=ruled(WORKTREE_SLUG))
    check("control: a question box on the same ruling is refused as past-ruling",
          (r.deny() or {}).get("permissionDecision") == "deny" and r.reason().startswith("past-ruling: "), detail(r))


def case_send_with_a_based_on_ruling_line_is_sent():
    # The incident with a Based on (ruling) line after its Based on (read) line, sent through both tools. A re-ask the
    # ruling allows is not refused. The model's answer here is canned as ok, so the verdict is the answer, not the judge.
    text = INCIDENT_357.replace(BASED_READ_357, BASED_READ_357 + "\n" + BASED_RULING_357, 1)
    check("send based-on: the Based on ruling line follows the Based on read line", BASED_RULING_357 in text,
          "the incident text lost its Based on read line")
    for tool in SEND_TOOLS:
        name = "send with a Based on ruling line via %s" % tool
        r = run_hook(send_input(tool, text), answer=ALLOW)
        check(name + ": the send is not refused", r.code == 0 and r.deny() is None, detail(r))
        check(name + ": the one model call is made", len(r.calls) == 1, detail(r))
        # Plumbing only: the judge reads the Based on line, so the prompt must carry it. The verdict is the canned answer.
        prompt = r.calls[0]["prompt"] if r.calls else ""
        check(name + ": the prompt carries the Based on ruling line", BASED_RULING_357 in prompt, detail(r))


def case_send_without_the_form_makes_no_call_and_no_subprocess():
    # A send that is no owner question passes with zero model calls and zero subprocesses. The canned answer would refuse
    # it, so a call that was made shows as a deny. The cwd is the repo with the ruling, so an empty repo explains nothing.
    import question_form
    for label, message in NO_FORM:
        check("send without the form (%s): no Goal and Problem pair" % label,
              not (question_form.GOAL_LINE.search(message) and question_form.PROBLEM_LABEL.search(message)), label)
        check("send without the form (%s): within the 64 KiB send bound" % label,
              len(message.encode("utf-8")) < 65536, len(message.encode("utf-8")))
        for tool in SEND_TOOLS:
            name = "send without the form (%s) via %s" % (label, tool)
            r = run_hook(send_input(tool, message), answer=ruled(WORKTREE_SLUG))
            check(name + ": no model call", len(r.calls) == 0, detail(r))
            check(name + ": no subprocess", r.procs == 0, detail(r))
            check(name + ": not refused", r.code == 0 and r.deny() is None, detail(r))


def case_send_model_error_refuses_as_unvetted_unless_marked():
    # A check that could not run (the model failed) refuses the send as Unvetted. A marked question passes. The marker does
    # not skip the check that can run: the model is still called, and it fails.
    call_marker = unvetted_marker(guard_constant(HOOK, "UNVETTED_REMEDY"))
    guard_marker = unvetted_marker(guard_constant(REPORT_GUARD, "UNVETTED_REASON"))
    check("send unvetted: both Unvetted remedies name one marker form",
          bool(call_marker) and call_marker == guard_marker, (call_marker, guard_marker))
    marked = INCIDENT_357 + "\nUnvetted: the review could not run, so the owner reads this question unchecked."
    for tool in SEND_TOOLS:
        name = "send model error via %s" % tool
        r = run_hook(send_input(tool, INCIDENT_357), model_fail=True)
        check(name + ": the model is called and fails", len(r.calls) == 1, detail(r))
        check(name + ": refused as Unvetted", (r.deny() or {}).get("permissionDecision") == "deny", detail(r))
        check(name + ": the refusal names the Unvetted marker", bool(call_marker) and call_marker in r.reason(), detail(r))
        check(name + ": the refusal names the cause, a check that could not run", "could not run" in r.reason(), detail(r))
        r = run_hook(send_input(tool, marked), model_fail=True)
        check(name + " with an Unvetted line: the model is called and fails", len(r.calls) == 1, detail(r))
        check(name + " with an Unvetted line: not refused", r.code == 0 and r.deny() is None, detail(r))


def case_send_two_questions_one_unvetted_line_is_refused_when_a_check_cannot_run():
    # Two owner questions in one send, and one `Unvetted:` line, in either place. The check cannot run (the model fails),
    # so the send is refused: each question needs its own marker, as a page batch already does. Both places are cased, so
    # a check that reads only the first question's block, or only the last, fails one of them.
    first, second = INCIDENT_357, INCIDENT_370
    orders = (("after the first question", first + "\n" + UNVETTED_LINE + "\n\n" + second),
              ("after the second question", first + "\n\n" + second + "\n" + UNVETTED_LINE))
    marker = unvetted_marker(guard_constant(HOOK, "UNVETTED_REMEDY"))
    for label, message in orders:
        for tool in SEND_TOOLS:
            name = "send two questions, marker %s, via %s" % (label, tool)
            r = run_hook(send_input(tool, message), model_fail=True)
            check(name + ": the check is attempted", len(r.calls) >= 1, detail(r))
            check(name + ": refused with the Unvetted remedy",
                  (r.deny() or {}).get("permissionDecision") == "deny" and bool(marker) and marker in r.reason(),
                  detail(r))
    # Control, green on the old code: each question carries its own marker, so the send is not refused.
    both = first + "\n" + UNVETTED_LINE + "\n\n" + second + "\n" + UNVETTED_LINE
    for tool in SEND_TOOLS:
        name = "send two questions, each with its own marker, via %s" % tool
        r = run_hook(send_input(tool, both), model_fail=True)
        check(name + ": the check is attempted", len(r.calls) >= 1, detail(r))
        check(name + ": not refused", r.code == 0 and r.deny() is None, detail(r))


# ------------------------------------------------------------------ the dedicated past-ruling call (page item writes)
#
# Coordinator ruling (14:38 CST): a judged page item write gets the dedicated past-ruling call first (lint/report_guard.py
# past_ruling_problem: Sonnet, item 8 alone). A refusal denies with rule past-ruling and the relay remedy, and makes no
# form-judge call. Otherwise the form judge runs as before, and its prompt no longer carries item 8. The measured cause:
# in the combined Opus prompt, item 8 caught page item 371 in 1 of 3 runs (ruling report-guard-refusal-right); the
# dedicated call caught it in 2 of 2.
WORKTREE_PAGE_ITEM = good_page_item(
    context="\n".join((
        "Goal: a merge frees disk without losing a running agent's work.",
        "Problem (risk): freeing a running agent's worktree loses its uncommitted files.",
        BASED_READ_357,
        DEPARTS_LINE,
    )),
    options=[
        {"key": "a", "label": "Never free a running lock", "gain": "A running agent keeps its uncommitted files.",
         "lose": "The worktree stays until the agent ends."},
        {"key": "b", "label": "Save, then free", "gain": "The worktree goes now.",
         "lose": "The archive ref needs cleaning later."},
    ])


def page_item_passes_the_form(label):
    # Scope first: the item must pass the form, so the judge runs and a refusal below is the judge's.
    import question_form  # the one form check (hooks/question_form.py)
    got = question_form.item_hit("set", {"collection": PAGE_ITEMS, "doc_id": "p1", "data": WORKTREE_PAGE_ITEM})
    check("page past %s: the item passes question_form.item_hit, so the judge runs" % label, got == ("", ""), got)


def case_page_past_ruling_refuses_before_the_form_judge():
    # Case A. A judged item write that a listed ruling settles is refused by the dedicated call: rule past-ruling, the
    # relay remedy, and exactly one model call, which is that call. The form judge's canned answer is ok, so a form call
    # would have allowed the write; a second call would mean the dedicated call did not stop it.
    page_item_passes_the_form("A")
    r = run_hook(page_input("set", WORKTREE_PAGE_ITEM, cwd=INCIDENT_REPO), answer=ALLOW, past=ruled(WORKTREE_SLUG))
    check("page past A: exactly one model call", len(r.calls) == 1, detail(r))
    check("page past A: the one call is the dedicated past-ruling call", len(past_calls(r)) == 1, detail(r))
    check("page past A: the write is denied", (r.deny() or {}).get("permissionDecision") == "deny", detail(r))
    check("page past A: the refusal rule is past-ruling", r.reason().startswith("past-ruling: "), r.reason()[:160])
    remedy = relay_remedy()
    check("page past A: the refusal carries the relay remedy", bool(remedy) and remedy in r.reason(),
          "remedy %r, reason %r" % (remedy[:40], r.reason()[-160:]))


def case_page_past_ruling_ok_then_the_form_judge_without_item_8():
    # Case B. The dedicated call answers ok, so the form judge runs next, on Opus, and its prompt holds no item 8. Then
    # the write is allowed. The item 8 text comes from hooks/call_judge.py at test time, never copied here.
    page_item_passes_the_form("B")
    item8 = guard_constant(HOOK, "PAST_RULING_ITEM")
    check("page past B: call_judge holds the item 8 text to look for", bool(item8), "PAST_RULING_ITEM is missing")
    r = run_hook(page_input("set", WORKTREE_PAGE_ITEM, cwd=INCIDENT_REPO), answer=ALLOW, past=ALLOW)
    check("page past B: exactly two model calls, the dedicated call and the form judge", len(r.calls) == 2, detail(r))
    check("page past B: the dedicated call runs first", len(r.calls) == 2 and PAST_CALL_TEXT in r.calls[0]["prompt"],
          detail(r))
    dedicated = past_calls(r)
    check("page past B: the dedicated call runs on Sonnet", len(dedicated) == 1
          and model_of(dedicated[0]["argv"]) == AGENT_MODEL, detail(r))
    form = form_calls(r)
    check("page past B: the form judge runs once, on Opus", len(form) == 1
          and model_of(form[0]["argv"]) == QUESTION_MODEL, detail(r))
    form_prompt = form[0]["prompt"] if form else ""
    check("page past B: the form-judge prompt holds no item 8 text", bool(item8) and item8 not in form_prompt,
          item8[:60])
    check("page past B: the write is allowed, with no deny", r.code == 0 and r.out == "" and r.deny() is None, detail(r))


def case_page_past_ruling_error_is_unvetted_unless_marked():
    # Case C. A model error in the dedicated call refuses the write as Unvetted, and no form call follows. A context with
    # an Unvetted: line passes after the attempt, and the form judge then runs (its canned answer is ok).
    page_item_passes_the_form("C")
    r = run_hook(page_input("set", WORKTREE_PAGE_ITEM, cwd=INCIDENT_REPO), answer=ALLOW, past_fail=True)
    check("page past C: the dedicated call is made and fails", len(past_calls(r)) == 1, detail(r))
    check("page past C: the write is refused as Unvetted", (r.deny() or {}).get("permissionDecision") == "deny",
          detail(r))
    check("page past C: no form call follows the refusal", len(form_calls(r)) == 0, detail(r))
    marker = unvetted_marker(guard_constant(HOOK, "UNVETTED_REMEDY"))
    check("page past C: the refusal names the Unvetted marker", bool(marker) and marker in r.reason(), detail(r))
    marked = dict(WORKTREE_PAGE_ITEM, context=WORKTREE_PAGE_ITEM["context"] + "\n" + UNVETTED_LINE)
    r = run_hook(page_input("set", marked, cwd=INCIDENT_REPO), answer=ALLOW, past_fail=True)
    check("page past C: with an Unvetted: line in context, the dedicated call fails and the write is not refused",
          len(past_calls(r)) == 1 and r.code == 0 and r.deny() is None, detail(r))


def case_non_item_and_non_judged_writes_make_no_model_call():
    # Case D, a control, green today. A read, another collection, a delete, a closed item and a title-only edit make no
    # model call, the dedicated call included. The answer would refuse any call, so a call shows as a deny. The cwd holds
    # the rulings, so no call is not an empty repo.
    item = good_page_item()
    cases = (
        ("an items get", page_input("get", None, doc_id="p1", cwd=INCIDENT_REPO)),
        ("an items list", page_input("list", None, doc_id=None, cwd=INCIDENT_REPO)),
        ("a receipts write", page_input("set", item, collection="receipts", doc_id="r1", cwd=INCIDENT_REPO)),
        ("an items delete", page_input("delete", None, doc_id="p1", cwd=INCIDENT_REPO)),
        ("a closed item", page_input("set", good_page_item(status="closed"), cwd=INCIDENT_REPO)),
        ("a title-only update", page_input("update", {"title": "Renamed"}, cwd=INCIDENT_REPO)),
    )
    for label, inp in cases:
        r = run_hook(inp, answer=ruled(WORKTREE_SLUG), past=ruled(WORKTREE_SLUG))
        check("non-judged write (%s): no model call, dedicated call included" % label, len(r.calls) == 0, detail(r))
        check("non-judged write (%s): not refused" % label, r.code == 0 and r.deny() is None, detail(r))


# ------------------------------------------------------------------ past-ruling cases: batches, form errors, send forms
#
# The cases below cover a page batch cut from the front, a batch whose one question no check reached, a form error that
# must refuse, the send check's forms (markdown, bullet, a heading Goal, a Problem with no stake), a send cut from the
# front, a send whose form sits only in a code fence, and the send tool names, which come from hooks/shared_names.py.
PAGE_FILLER = "Background sentence for the owner. " * 200  # about 8,000 characters, past ASK_TEXT_MAX
SEND_LOG_FILLER = "Lane 4 log: ruff clean, no finding.\n" * 200  # about 7,200 characters, past ASK_TEXT_MAX


def case_page_batch_passes_every_write_to_the_dedicated_call():
    # A batch past ASK_TEXT_MAX joined characters. Its first write is short and its second is long, so a front
    # cut drops the first write, whose mark PAGE_MARK sits in option a's gain. Both writes must reach the dedicated call.
    cap = guard_constant(REPORT_GUARD, "ASK_TEXT_MAX")
    long_context = "\n".join((GOAL_LINE, PROBLEM_LINE, *BASED_LINES, DEPARTS_LINE, PAGE_FILLER))
    writes = [{"op": "set", "collection": PAGE_ITEMS, "doc_id": "p1", "data": good_page_item(PAGE_MARK)},
              {"op": "set", "collection": PAGE_ITEMS, "doc_id": "p2",
               "data": good_page_item(PAGE_MARK_B, context=long_context)}]
    check("page batch past the cap: the batch is longer than ASK_TEXT_MAX",
          isinstance(cap, int) and len(long_context) > cap, cap)
    r = run_hook(page_batch_input(writes), answer=ALLOW)
    prompts = [c["prompt"] for c in past_calls(r)]
    check("page batch past the cap: the dedicated call is made", len(prompts) >= 1, detail(r))
    check("page batch past the cap: the first write's text reaches the dedicated call",
          any(PAGE_MARK in p for p in prompts), detail(r))
    check("page batch past the cap: the second write's text reaches the dedicated call",
          any(PAGE_MARK_B in p for p in prompts), detail(r))


def case_page_batch_with_one_unvetted_line_is_refused_when_a_check_cannot_run():
    # Two questions in one batch. Only the second carries `Unvetted:`, and the dedicated call fails. The first
    # question was never checked, so the batch is refused with the Unvetted remedy: each question needs its own marker.
    marked = "\n".join((GOAL_LINE, PROBLEM_LINE, *BASED_LINES, DEPARTS_LINE, UNVETTED_LINE))
    writes = [{"op": "set", "collection": PAGE_ITEMS, "doc_id": "p1", "data": good_page_item(PAGE_MARK)},
              {"op": "set", "collection": PAGE_ITEMS, "doc_id": "p2", "data": good_page_item(PAGE_MARK_B, context=marked)}]
    r = run_hook(page_batch_input(writes), answer=ALLOW, past_fail=True)
    marker = unvetted_marker(guard_constant(HOOK, "UNVETTED_REMEDY"))
    check("page batch, one Unvetted line, check down: the dedicated call is made and fails",
          len(past_calls(r)) >= 1, detail(r))
    check("page batch, one Unvetted line, check down: the batch is denied",
          (r.deny() or {}).get("permissionDecision") == "deny", detail(r))
    check("page batch, one Unvetted line, check down: the refusal names the Unvetted marker",
          bool(marker) and marker in r.reason(), detail(r))


def case_page_form_error_refuses_as_unvetted():
    # The dedicated call passes and only the form call errors. The form judge is the check that could not run,
    # so the write is refused with the Unvetted remedy, as on main. A form error is not a pass.
    page_item_passes_the_form("3")
    r = run_hook(page_input("set", WORKTREE_PAGE_ITEM, cwd=INCIDENT_REPO), answer=ALLOW, past=ALLOW, form_fail=True)
    check("page form error: the dedicated call passes and the form call is made and fails",
          len(past_calls(r)) == 1 and len(form_calls(r)) == 1, detail(r))
    check("page form error: the write is denied", (r.deny() or {}).get("permissionDecision") == "deny", detail(r))
    marker = unvetted_marker(guard_constant(HOOK, "UNVETTED_REMEDY"))
    check("page form error: the refusal names the Unvetted marker", bool(marker) and marker in r.reason(), detail(r))


def replace_line(text, prefix, line):
    """`text` with each line that starts with `prefix` replaced by `line`."""
    return "\n".join(line if part.startswith(prefix) else part for part in text.split("\n"))


def case_send_check_judges_each_form_variant():
    # The send check reads a Goal line and a Problem line in the forms owners' pages use: bold, a bullet, a blockquote,
    # a `## Goal:` heading, and a Problem line with no stake or with one outside the set. Each variant makes one
    # dedicated call, and the incident ruling refuses it.
    goal = "a merge frees disk without losing a running agent's work."
    problem = "freeing a running agent's worktree loses its uncommitted files."
    variants = (
        ("a bold Goal", replace_line(INCIDENT_357, "Goal:", "**Goal:** " + goal)),
        ("a bulleted Goal", replace_line(INCIDENT_357, "Goal:", "- Goal: " + goal)),
        ("a blockquoted Goal", replace_line(INCIDENT_357, "Goal:", "> Goal: " + goal)),
        ("a heading Goal", replace_line(INCIDENT_357, "Goal:", "## Goal: " + goal)),
        ("a bold Problem (risk)", replace_line(INCIDENT_357, "Problem (risk):", "**Problem (risk):** " + problem)),
        ("a Problem with no stake", replace_line(INCIDENT_357, "Problem (risk):", "Problem: " + problem)),
        ("a Problem with a stake outside the set",
         replace_line(INCIDENT_357, "Problem (risk):", "Problem (cost): " + problem)),
    )
    for label, message in variants:
        for tool in SEND_TOOLS:
            name = "send check, %s via %s" % (label, tool)
            r = run_hook(send_input(tool, message), answer=ruled(WORKTREE_SLUG))
            check(name + ": one model call before the send", len(r.calls) == 1, detail(r))
            check(name + ": the send is denied as past-ruling",
                  (r.deny() or {}).get("permissionDecision") == "deny" and r.reason().startswith("past-ruling: "),
                  r.reason()[:160])


def case_send_over_the_cap_keeps_the_goal_and_problem():
    # A send past ASK_TEXT_MAX whose form lines sit at the top, where a front cut would drop them. Both lines must
    # reach the prompt that the dedicated call reads.
    cap = guard_constant(REPORT_GUARD, "ASK_TEXT_MAX")
    lines = INCIDENT_357.split("\n")
    goal_line, problem_line = lines[1], lines[2]
    message = INCIDENT_357 + "\n" + SEND_LOG_FILLER
    check("send over the cap: the message is longer than ASK_TEXT_MAX",
          isinstance(cap, int) and len(message) > cap, cap)
    for tool in SEND_TOOLS:
        r = run_hook(send_input(tool, message), answer=ALLOW)
        prompt = r.calls[0]["prompt"] if r.calls else ""
        check("send over the cap via %s: the one model call is made" % tool, len(r.calls) == 1, detail(r))
        check("send over the cap via %s: the Goal line reaches the prompt" % tool, goal_line in prompt, detail(r))
        check("send over the cap via %s: the Problem line reaches the prompt" % tool, problem_line in prompt, detail(r))


def case_send_over_the_cap_keeps_a_based_on_line_above_the_goal():
    # A send past ASK_TEXT_MAX whose Based on (ruling) line sits above its Goal line. A cut from the first form line drops
    # that line, so the judge would not see the ruling the question names. The line must reach the prompt.
    cap = guard_constant(REPORT_GUARD, "ASK_TEXT_MAX")
    title, goal_line, *rest = INCIDENT_357.split("\n")
    message = "\n".join([title, BASED_RULING_357, goal_line, *rest]) + "\n" + SEND_LOG_FILLER
    check("send based-on over the cap: the message is longer than ASK_TEXT_MAX",
          isinstance(cap, int) and len(message) > cap, cap)
    check("send based-on over the cap: the Based on ruling line sits above the Goal line",
          message.index(BASED_RULING_357) < message.index(goal_line), "fixture order")
    for tool in SEND_TOOLS:
        r = run_hook(send_input(tool, message), answer=ALLOW)
        prompt = r.calls[0]["prompt"] if r.calls else ""
        check("send based-on over the cap via %s: the one model call is made" % tool, len(r.calls) == 1, detail(r))
        check("send based-on over the cap via %s: the Based on ruling line reaches the prompt" % tool,
              BASED_RULING_357 in prompt, detail(r))


def case_send_with_the_form_only_in_a_fence_makes_no_call():
    # The Goal and Problem lines sit inside a code fence, quoted as text. The send is no owner question, so it
    # makes no model call and is not refused.
    import question_form  # the one form check (hooks/question_form.py)
    message = ("A quote from an earlier message, for reference only:\n```\n" + INCIDENT_357 + "\n```\n"
               "No question for the owner in this message.")
    check("fenced send: the fence holds both form lines",
          bool(question_form.GOAL_LINE.search(message)) and bool(question_form.PROBLEM_LINE.search(message)),
          "the fence has no form lines to test")
    for tool in SEND_TOOLS:
        r = run_hook(send_input(tool, message), answer=ruled(WORKTREE_SLUG))
        check("fenced send via %s: no model call" % tool, len(r.calls) == 0, detail(r))
        check("fenced send via %s: not refused" % tool, r.code == 0 and r.deny() is None, detail(r))


def module_send_copies(path):
    """The line numbers of module-level assignments in `path` that hold a send tool name as a literal: a copy of the
    names, where the file must import them. The file is read as syntax, so a comment or a function body is no copy."""
    import ast
    from shared_names import SEND_TOOLS as names  # the one home of the send tool names
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), path)
    copies = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            literals = [c.value for c in ast.walk(node.value) if isinstance(c, ast.Constant) and isinstance(c.value, str)]
            if any(value in names for value in literals):
                copies.append(node.lineno)
    return copies


def imports_send_tools(path):
    """True when `path` binds SEND_TOOLS at module level by an import from shared_names."""
    import ast
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), path)
    return any(isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[-1] == "shared_names"
               and any(alias.name == "SEND_TOOLS" for alias in node.names) for node in tree.body)


def case_send_tool_names_come_from_shared_names():
    # The send tool names have one home, hooks/shared_names.py. Each of the two test files imports SEND_TOOLS
    # from it and binds no literal copy of the names at module level.
    files = (("hooks/test_call_judge.py", os.path.join(HERE, "test_call_judge.py")),
             ("lint/test_settings_matcher.py", os.path.join(REPO, "lint", "test_settings_matcher.py")))
    for label, path in files:
        copies = module_send_copies(path)
        check("%s: no module-level literal copy of a send tool name" % label, copies == [],
              "copies at lines %s" % copies)
        check("%s: imports SEND_TOOLS from shared_names" % label, imports_send_tools(path), label)


# ------------------------------------------------------------------ owner-only rulings (spec past-rulings)
#
# A candidate is a ruling only when the owner gave it: a record whose ruling line names him, or a sentence that names him
# as its source, `Owner, <date>` or `Ruling (owner, <date>)`. A roadmap note that holds an incident, or a recommendation
# the owner has not answered, is no ruling, so the judge may not cite it. Each stub answer below cites a candidate only
# when the list it was shown holds the case's marker (CJ_CITE_SHOWN). So a candidate that is not offered, and one that is
# offered but not cited as a refusal, both allow the question.
NOTE_INCIDENT_MARK = "hand-merged the release fix"
NOTE_INCIDENT = ("Incident, 2026-11-05: a lane hand-merged the release fix onto #1488 before the owner's review, so the "
                 "milestone check never ran.")
NOTE_RECOMMEND_MARK = "recommends raising the milestone job cap"
NOTE_RECOMMEND = ("Page item 150 (open) recommends raising the milestone job cap; the owner has not answered, so the cap "
                  "stays as it is until he does.")
NOTE_OWNER_MARK = "raise the milestone job cap, because"
NOTE_OWNER = ("Owner, page item 150, pick a, 2026-11-06 12:40 CST: raise the milestone job cap, because the run ended "
              "at its cap twice.")
INCIDENT_NOTE_REPO = make_repo("incident-note", steps={"hand-merge-release-fix": NOTE_INCIDENT})
RECOMMEND_NOTE_REPO = make_repo("recommend-note", steps={"milestone-cap-open": NOTE_RECOMMEND})
OWNER_NOTE_REPO = make_repo("owner-note", steps={"milestone-cap-answered": NOTE_OWNER})
OWNER_ONLY_GOAL = "Goal: decide whether the milestone job cap rises, and whether the hand-merged release fix stays on main"
OWNER_ONLY_PROBLEM = "Problem (rule): the milestone job cap decides when a full CI run goes red, so the rule needs your word"
OWNER_ONLY_BASED = ("Based on (read): the milestone job ran out of time at its cap on the last run",)
PAGE_RECOMMENDED_OPTIONS = [
    {"key": "a", "label": "Raise the cap (Recommended)", "gain": "The milestone run stops ending at its cap.",
     "lose": "Each run takes longer and uses more minutes."},
    {"key": "b", "label": "Keep the cap", "gain": "Nothing changes on main.",
     "lose": "The milestone run may end at its cap again."}]


def owner_only_box():
    return good_box(goal=OWNER_ONLY_GOAL, problem=OWNER_ONLY_PROBLEM, based=OWNER_ONLY_BASED, options=CI_CHAT_OPTIONS)


def case_past_ruling_incident_note_is_not_cited():
    # The step note holds only an incident. It names no owner as its source, so it is no ruling, and a judge that cites it
    # must not refuse the question. Red on main: the note is offered as a ruling, and the cited note refuses the box.
    import question_form  # the one form check (hooks/question_form.py)
    box = owner_only_box()
    check("owner-only incident: the box passes chat_hit, so the model judges it",
          question_form.chat_hit(box) == ("", ""), question_form.chat_hit(box))
    r = run_hook(question_input(box=box, cwd=INCIDENT_NOTE_REPO), answer=ALLOW, cite_shown=NOTE_INCIDENT_MARK)
    check("owner-only incident: a judge's citation of an incident note in a roadmap step is not a refusal",
          len(r.calls) == 1 and (r.deny() or {}).get("permissionDecision") != "deny", detail(r))


def case_past_ruling_recommended_pick_is_not_cited():
    # The page item is unanswered and its option is marked (Recommended). The roadmap note that recommends the same pick
    # says the owner has not answered, so it is no ruling. A judge that cites it as the owner's answer must not refuse.
    # Red on main, for the same reason as the incident case.
    import question_form  # the one form check (hooks/question_form.py)
    item = good_page_item(title="Raise the milestone job cap?", context=CI_PAGE_CONTEXT, options=PAGE_RECOMMENDED_OPTIONS)
    got = question_form.item_hit("set", {"collection": PAGE_ITEMS, "doc_id": "c150", "data": item})
    check("owner-only recommended: the page item passes item_hit, so the dedicated call runs", got == ("", ""), got)
    r = run_hook(page_input("set", item, cwd=RECOMMEND_NOTE_REPO), answer=ALLOW, cite_shown=NOTE_RECOMMEND_MARK)
    check("owner-only recommended: a judge's citation of a note that recommends an unanswered pick is not a refusal",
          (r.deny() or {}).get("permissionDecision") != "deny" and r.code == 0, detail(r))


def case_past_ruling_owner_answered_page_item_stays_refused():
    # Control, green today: the owner's answer to page item 150 is recorded in a roadmap note with his name as its source.
    # A question that the answer settles is still refused as past-ruling.
    r = run_hook(question_input(box=owner_only_box(), cwd=OWNER_NOTE_REPO), answer=ALLOW, cite_shown=NOTE_OWNER_MARK)
    check("owner-only control: a question that a recorded owner answer to a page item settles is refused as past-ruling",
          (r.deny() or {}).get("permissionDecision") == "deny" and r.reason().startswith("past-ruling: "), detail(r))


def case_past_ruling_owner_decision_stays_refused():
    # Control, green today: a decision whose ruling line names the owner ("Owner, 2026-10-27: ...") is still refused.
    box = good_box(goal=CAPS_GOAL, problem=CAPS_PROBLEM, based=CAPS_BASED, options=CAPS_OPTIONS)
    r = run_hook(question_input(box=box, cwd=DECISIONS_REPO), answer=ALLOW, cite_shown="generous on purpose")
    check("owner-only control: a decision whose ruling line names the owner still refuses a question it settles",
          (r.deny() or {}).get("permissionDecision") == "deny" and r.reason().startswith("past-ruling: "), detail(r))


def main():
    for case in (case_agent_refusal,case_spawn_prompt_bars_a_lane_waiting_page_write, case_agent_override, case_explore_row_is_vetoed,
                 case_explore_remedy_names_marker, case_agent_fallback_names_marker, case_question,
                 case_question_departs, case_page_fixture_passes_the_form, case_page_reject_and_accept,
                 case_page_no_model_call, case_page_batch_one_call, case_page_override,
                 case_page_model_failure_refuses_as_unvetted, case_page_str_replace_judged,
                 case_page_task_item_judged, case_page_task_exempt_from_decision_items, case_page_steps_judged,
                 case_page_reads_and_other_collections_skip_question_form,
                 case_reask_update_holds_rule_once, case_reask_cheaper_note_holds_rule_once,
                 case_options_without_note_lacks_rule, case_blank_note_lacks_rule,
                 case_context_only_note_lacks_rule, case_reask_batch_one_call_rule_once, case_reask_refusal_denies,
                 case_picked_choice_with_note_lacks_rule, case_none_choice_with_note_holds_rule_once,
                 case_done_answer_is_not_reask,
                 case_widening_set_holds_rule_once, case_widening_batch_holds_rule_once,
                 case_widening_absent_without_options, case_widening_refusal_names_the_option,
                 case_widening_fair_option_passes_code_path, case_widening_rule_names_the_mark,
                 case_fail_open, case_settings_row, case_past_ruling_replay_item_145,
                 case_past_ruling_replay_item_133, case_past_ruling_cited_passes,
                 case_past_ruling_explained_premise, case_past_ruling_unknown_is_named,
                 case_past_ruling_cost, case_unvetted_marker, case_unvetted_page_marker,
                 case_unvetted_not_for_closed_items, case_past_ruling_debt_candidates,
                 case_unshown_id_takes_the_unvetted_path, case_marker_does_not_skip_the_check,
                 case_unknown_names_the_claude_settings_records, case_cite_of_a_shown_record_is_not_bogus,
                 case_page_task_gets_item_8_and_is_refused, case_mid_reason_unlisted_id_is_a_plain_refusal,
                 case_send_owner_question_is_judged_before_it_is_sent,
                 case_question_box_with_the_same_ruling_is_refused_as_past_ruling,
                 case_send_with_a_based_on_ruling_line_is_sent,
                 case_send_without_the_form_makes_no_call_and_no_subprocess,
                 case_send_model_error_refuses_as_unvetted_unless_marked,
                 case_send_two_questions_one_unvetted_line_is_refused_when_a_check_cannot_run,
                 case_page_past_ruling_refuses_before_the_form_judge,
                 case_page_past_ruling_ok_then_the_form_judge_without_item_8,
                 case_page_past_ruling_error_is_unvetted_unless_marked,
                 case_non_item_and_non_judged_writes_make_no_model_call,
                 case_page_batch_passes_every_write_to_the_dedicated_call,
                 case_page_batch_with_one_unvetted_line_is_refused_when_a_check_cannot_run,
                 case_page_form_error_refuses_as_unvetted, case_send_check_judges_each_form_variant,
                 case_send_over_the_cap_keeps_the_goal_and_problem,
                 case_send_over_the_cap_keeps_a_based_on_line_above_the_goal,
                 case_send_with_the_form_only_in_a_fence_makes_no_call,
                 case_send_tool_names_come_from_shared_names,
                 case_past_ruling_incident_note_is_not_cited, case_past_ruling_recommended_pick_is_not_cited,
                 case_past_ruling_owner_answered_page_item_stays_refused,
                 case_past_ruling_owner_decision_stays_refused):
        try:
            case()
        except Exception as exc:
            check(case.__name__, False, "raised %s: %s" % (type(exc).__name__, exc))
    print("FAIL: %d failed" % len(FAILED) if FAILED else "all checks passed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
