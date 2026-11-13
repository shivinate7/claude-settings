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
- settings.json: one command hook on `Agent|AskUserQuestion|ArtifactData` and the two send tools runs call_judge.py with
  a timeout of 130 s: the dedicated past-ruling call (60 s) plus the form call (60 s) plus start-up. No `prompt` or
  `agent` hook is left on any of the three tools.
- Owner questions (the past-ruling rebuild): a send by a send tool whose message holds a Goal and a Problem line gets the
  dedicated past-ruling call (its prompt holds PAST_CALL_TEXT) before it goes. A judged page item write runs that call
  first, alone, and the form call after it. run_hook's `past` is the dedicated call's answer and `past_fail` makes it
  fail. Run.past holds the dedicated calls, Run.calls the chat and form calls, and Run.seq the order.
- Past rulings (spec past-rulings): a judged AskUserQuestion or waiting-page item write also carries the decision
  records and the `roadmap` step rulings that question_form.past_rulings finds, and an eighth item that refuses a
  question a standing ruling already decides. Each case builds its own real git repo (make_repo), and a fixture
  ruling is found in the prompt with the call's JSON cut out. A search that cannot read a source prints one stderr
  line, `past-ruling search unknown:`, and never says clear.
- A relative file_path on an items set or update with no `data`: the file is read against the payload's `cwd`, as
  question_form._write_data reads it, so that write is judged like inline data (the section "a relative file_path").
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
# The dedicated past-ruling call's prompt (lint/report_guard.py past_ruling_problem, also the Stop hook's): item 8 alone.
# Only that call holds this text, so a case tells it from the form and chat calls.
PAST_CALL_TEXT = "Judge only item 8 below"
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


# The waiting page's repo with a GitHub origin. PAGE_REPO above has no origin, so lint/layout.py repo_name reads it
# as unknown. The cross-repo rule (question-checked-with-repo) judges a decision's repo against this origin's repo,
# so its cases judge the write with cwd set here.
PAGE_ORIGIN_URL = "https://github.com/shivinate7/claude-settings.git"


def origin_page_repo():
    """The waiting-page repo whose origin is PAGE_ORIGIN_URL. make_repo caches it by name, so one repo per run."""
    repo = make_repo("page-origin", page=PAGE_URL)
    if not git(repo, "remote").stdout.strip():
        git(repo, "remote", "add", "origin", PAGE_ORIGIN_URL)
    return repo


# The record-branch checkout: a checkout on the record branch `roadmap` with no extras file, while origin/main holds
# the page's extras file. lint/layout.py reads the page from origin/main when the checkout has none, so the page checks
# run from here too. Built from plumbing and one branch switch. origin/main is a ref only (no local main stays), as a
# fetch leaves it. The one home of this fixture.
RECORD_CHECKOUT = os.path.join(ROOT, "record-branch-checkout")


def record_branch_checkout():
    """The checkout on `roadmap` whose origin/main holds the extras file of PAGE_URL, in the registry form main holds."""
    repo = RECORD_CHECKOUT
    if os.path.isdir(repo):
        return repo
    os.makedirs(repo)
    git(repo, "init", "-q")
    git(repo, "symbolic-ref", "HEAD", "refs/heads/roadmap")
    with open(os.path.join(repo, "README.md"), "w", encoding="utf-8") as f:
        f.write("# Record branch\n")
    git(repo, "add", "README.md")
    git(repo, "commit", "-q", "-m", "record")
    git(repo, "checkout", "-q", "-b", "main")
    os.makedirs(os.path.join(repo, ".claude"))
    with open(os.path.join(repo, ".claude", "layout-extras.json"), "w", encoding="utf-8") as f:
        json.dump({"kinds": {}, "artifacts": [{"id": "queue", "url": PAGE_URL, "role": "waiting-page", "account": "current"}]}, f)
    git(repo, "add", ".claude/layout-extras.json")
    git(repo, "commit", "-q", "-m", "extras")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(repo, "checkout", "-q", "roadmap")
    git(repo, "branch", "-q", "-D", "main")
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
    # The dedicated past-ruling call (report_guard.past_ruling_problem) carries "Judge only item 8 below" and answers
    # CJ_PAST_ANSWER; its failure is CJ_PAST_FAIL. Every other call is a chat or form call: CJ_ANSWER, CJ_MODEL_FAIL.
    if "Judge only item 8 below" in prompt:
        if os.environ.get("CJ_PAST_FAIL"):
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="stub past-ruling failure")
        answer = os.environ["CJ_PAST_ANSWER"]
    else:
        if os.environ.get("CJ_MODEL_FAIL"):
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="stub model failure")
        answer = os.environ["CJ_ANSWER"]
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
# CJ_BLOCK_IMPORT names a module the child cannot import: a None entry in sys.modules makes its import raise.
if os.environ.get("CJ_BLOCK_IMPORT"):
    sys.modules[os.environ["CJ_BLOCK_IMPORT"]] = None
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
        # calls: the chat and form calls, as before. past: the dedicated past-ruling calls (PAST_CALL_TEXT). seq: every
        # call in order, "past" or "form", so a case reads which call ran first.
        path = os.path.join(base, "calls.jsonl")
        self.calls, self.past, self.seq = [], [], []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    call = json.loads(line)
                    dedicated = PAST_CALL_TEXT in call["prompt"]
                    (self.past if dedicated else self.calls).append(call)
                    self.seq.append("past" if dedicated else "form")
        procs = os.path.join(base, "procs.log")
        self.procs = len(open(procs, encoding="utf-8").read().split()) if os.path.exists(procs) else 0
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


def run_hook(stdin_text, answer=ALLOW, model_fail=False, pass_=None, past=ALLOW, past_fail=False, block=None):
    """One hook run. `answer` is the chat and form calls' canned answer, `model_fail` makes those calls fail. `past` is
    the dedicated past-ruling call's answer and `past_fail` makes only that call fail. `block` names a module the child
    cannot import (a check that needs it cannot run)."""
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
    env["CJ_PAST_ANSWER"] = past
    if past_fail:
        env["CJ_PAST_FAIL"] = "1"
    if block:
        env["CJ_BLOCK_IMPORT"] = block
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


def shown_of(options):
    """The `shown` list a page write carries: each option's key, id and label, in order. A non-dict entry is skipped."""
    return [{"key": o.get("key"), "id": o.get("id"), "label": o.get("label")} for o in options if isinstance(o, dict)]


def with_frozen_fields(data, ids=True):
    """A copy of a page write's data with the fields a session's write carries when it writes options: `shown`, the
    options as first shown, and with `ids` an id on each option that has none (opt-<n>, n its 1-based position, never
    a lone letter). An id the option already has, even "" or a repeat, is kept, so a case can write a bad id. Data with
    no options list is copied unchanged. question_form.frozen_letters_hit (rule option-letters-frozen) reads both."""
    found = dict(data)
    options = data.get("options")
    if not isinstance(options, list):
        return found
    filled = []
    for i, option in enumerate(options):
        if isinstance(option, dict):
            option = dict(option)
            if ids:
                option.setdefault("id", "opt-%d" % (i + 1))
        filled.append(option)
    found["options"] = filled
    found["shown"] = shown_of(filled)
    return found


def good_page_item(mark=PAGE_MARK, **over):
    """A waiting-page decision that passes the form. `mark` rides in option a's gain, so a case finds the item
    in the prompt. `over` replaces fields, for a case that changes one. Its options carry ids and `shown` (see
    with_frozen_fields), so a case that replaces `options` gets a matching `shown` too."""
    context = "\n".join((GOAL_LINE, PROBLEM_LINE, *BASED_LINES, DEPARTS_LINE))
    item = {"kind": "decision", "title": "Ship the change today?", "status": "open", "context": context,
            "options": [{"key": "a", "label": "Ship it", "gain": "The change lands today. " + mark,
                         "lose": "Nobody reads it first."},
                        {"key": "b", "label": "Hold it", "gain": "A reviewer reads it first.",
                         "lose": "The change lands a day later."}]}
    item.update(over)
    return with_frozen_fields(item)


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
               "data": with_frozen_fields({"kind": "decision", "context": second["context"], "options": second["options"]})}]
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
    check("page unvetted: a model failure on an item write refuses once, the remedy names Unvetted:",
          r.code == 0 and (r.deny() or {}).get("permissionDecision") == "deny" and "Unvetted:" in r.reason()
          and len(r.calls) == 1, detail(r))


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


# ------------------------------------------------------------------ a relative file_path (ArtifactData)
#
# An items write can name its data by a file_path, with no data. question_form._write_data reads that file against the
# payload's cwd, and item_hit does. judged_item_writes must read it the same way, or the write never reaches the model
# review, so item 8 (the past-ruling check) never sees it. Each file name below is unique and absent from the cwd the
# hook runs in (run_hook inherits this test run's cwd), so a read that finds the file can only come from the join to the
# payload's cwd. The item's text shares words with the APPS ruling, so the past-ruling search lists that record.
def apps_refusal():
    """The model's refusal, which cites the APPS record: a listed candidate, so the past-ruling refusal runs."""
    return json.dumps({"ok": False, "reason": "decisions/%s: already decided by the keep-the-apps ruling." % APPS_SLUG})


def relative_item_repo():
    """The repo whose one decision record is the APPS ruling. Its waiting page is PAGE_URL."""
    return make_repo("relative-file", decisions={APPS_SLUG: APPS_RULING})


def apps_item():
    """A waiting-page decision on the apps question: it passes item_hit, and its text lists the APPS record."""
    context = "\n".join((APPS_GOAL, APPS_PROBLEM, APPS_BASED[0], DEPARTS_LINE))
    options = [
        {"key": "a", "label": "Keep the apps", "gain": "Calls into the repo stay straightforward. " + PAGE_MARK,
         "lose": "An unused app keeps its access."},
        {"key": "b", "label": "Remove the apps", "gain": "Fewer apps can write to the repo.",
         "lose": "Each call into the repo needs a manual step."}]
    return good_page_item(title="Keep the GitHub apps' access?", context=context, options=options)


def write_item_file(path, item):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(item, f)


def relative_name_precondition(repo, name):
    """Scope before subject: the file is at the payload cwd, and no file of that name is at the hook's cwd."""
    check("relative item %s: the file is at the payload cwd" % name, os.path.isfile(os.path.join(repo, name)), repo)
    check("relative item %s: no file of that name at the hook's cwd, so only a join to the payload cwd finds it" % name,
          not os.path.exists(name), os.getcwd())


def case_page_relative_file_path_reaches_the_review():
    # A relative file_path must be read against the payload cwd. Read without it, the file is not found and the
    # write is dropped: the hook exits 0 with no model call, so the APPS ruling is never checked.
    import question_form  # the one form check (hooks/question_form.py)
    repo, name = relative_item_repo(), "relative-item-deny.json"
    write_item_file(os.path.join(repo, name), apps_item())
    relative_name_precondition(repo, name)
    got = question_form.item_hit("set", {"collection": PAGE_ITEMS, "doc_id": "p1", "file_path": name}, repo)
    check("relative item: the form check reads the file at the payload cwd and passes it", got == ("", ""), got)
    # Item 8 runs in the dedicated past-ruling call, which is the call that refuses the item here.
    r = run_hook(page_input("set", None, doc_id="p1", cwd=repo, file_path=name), answer=ALLOW, past=apps_refusal())
    prompt = r.past[0]["prompt"] if len(r.past) == 1 else ""
    check("relative item: the write reaches one dedicated model review", len(r.past) == 1, detail(r))
    check("relative item: the model sees the item read from the file", PAGE_MARK in prompt, prompt[:160])
    check("relative item: the APPS record and its ruling reach the dedicated call's prompt",
          APPS_SLUG in prompt and APPS_RULING in prompt, prompt[:160])
    rule = question_form.PAST_RULING_RULE
    check("relative item: the past-ruling refusal is denied under rule %s, with one deny line" % rule,
          r.code == 0 and (r.deny() or {}).get("permissionDecision") == "deny" and r.reason().startswith(rule + ": ")
          and r.log.count("\tdeny\t%s\t" % rule) == 1, detail(r))


def case_page_relative_file_path_passing_item_passes():
    # The negative: the same shape, and the model says ok. Only the one-call check tells a pass from a skip,
    # because a skipped write also exits 0 with no output.
    repo, name = relative_item_repo(), "relative-item-pass.json"
    write_item_file(os.path.join(repo, name), apps_item())
    relative_name_precondition(repo, name)
    r = run_hook(page_input("set", None, doc_id="p1", cwd=repo, file_path=name), answer=ALLOW)
    prompt = r.calls[0]["prompt"] if r.calls else ""
    check("relative item, ok: the write reaches one model review", len(r.calls) == 1 and PAGE_MARK in prompt, detail(r))
    check("relative item, ok: exit 0, no output, no deny",
          r.code == 0 and r.out == "" and "\tdeny\t" not in r.log, detail(r))


def case_page_absolute_file_path_is_judged():
    # The control: an absolute file_path is read as a file on main too. The dedicated past-ruling call refuses it.
    import question_form  # the one form check (hooks/question_form.py)
    repo = relative_item_repo()
    path = os.path.join(repo, "absolute-item-deny.json")
    write_item_file(path, apps_item())
    check("absolute item: the file is at its absolute path", os.path.isabs(path) and os.path.isfile(path), path)
    r = run_hook(page_input("set", None, doc_id="p1", cwd=repo, file_path=path), answer=ALLOW, past=apps_refusal())
    prompt = r.past[0]["prompt"] if len(r.past) == 1 else ""
    rule = question_form.PAST_RULING_RULE
    check("absolute item: the write reaches one dedicated model review", len(r.past) == 1 and PAGE_MARK in prompt,
          detail(r))
    check("absolute item: the past-ruling refusal is denied under rule %s" % rule,
          r.code == 0 and (r.deny() or {}).get("permissionDecision") == "deny" and r.reason().startswith(rule + ": "),
          detail(r))


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
    return with_frozen_fields({"options": good_page_item(mark)["options"], "lastAnswer": last_answer(note, choice, done)})


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
    prompt = r.calls[0]["prompt"] if r.calls else ""
    check("re-ask: an update with options and a lastAnswer note makes one model call, and no deny",
          len(r.calls) == 1 and r.code == 0 and r.out == "" and "\tdeny\t" not in r.log, detail(r))
    check("re-ask: the one prompt holds NONE_DIRECTION_RULE exactly once", bool(rule) and prompt.count(rule) == 1,
          rule_detail(rule, r))
    check("re-ask: the one prompt carries the owner's note", REASK_NOTE in prompt, prompt[:200])


def case_reask_cheaper_note_holds_rule_once():
    # Case 2: the note asks for other options. The model decides, so the rule still reaches it, and the fake's allow
    # gives no deny.
    rule = none_direction_rule()
    r = run_hook(page_input("update", reask_item(PAGE_MARK, SHOW_CHEAPER_NOTE)), answer=ALLOW)
    prompt = r.calls[0]["prompt"] if r.calls else ""
    check("re-ask, cheaper-options note: one model call, and the model's allow is no deny",
          len(r.calls) == 1 and r.code == 0 and r.out == "" and "\tdeny\t" not in r.log, detail(r))
    check("re-ask, cheaper-options note: the one prompt holds NONE_DIRECTION_RULE exactly once",
          bool(rule) and prompt.count(rule) == 1, rule_detail(rule, r))


def case_options_without_note_lacks_rule():
    # Case 3: options with no lastAnswer is not a re-ask. The call still makes its one model call, so an early exit
    # cannot pass this check.
    rule = none_direction_rule()
    r = run_hook(page_input("update", with_frozen_fields({"options": good_page_item()["options"]})), answer=ALLOW)
    prompt = r.calls[0]["prompt"] if r.calls else ""
    check("no re-ask, options only: one model call, and no deny", len(r.calls) == 1 and r.code == 0 and r.out == ""
          and "\tdeny\t" not in r.log, detail(r))
    check("no re-ask, options only: the prompt lacks NONE_DIRECTION_RULE", bool(rule) and prompt.count(rule) == 0,
          rule_detail(rule, r))


def case_blank_note_lacks_rule():
    # Case 4: a note that is blank after strip is not a direction, so the write is not a re-ask.
    rule = none_direction_rule()
    data = with_frozen_fields({"options": good_page_item()["options"], "lastAnswer": last_answer("  ")})
    r = run_hook(page_input("update", data), answer=ALLOW)
    prompt = r.calls[0]["prompt"] if r.calls else ""
    check("no re-ask, blank note: one model call, and no deny", len(r.calls) == 1 and r.code == 0 and r.out == ""
          and "\tdeny\t" not in r.log, detail(r))
    check("no re-ask, blank note: the prompt lacks NONE_DIRECTION_RULE", bool(rule) and prompt.count(rule) == 0,
          rule_detail(rule, r))


def case_context_only_note_lacks_rule():
    # Case 5: a context-only write has no options, so a note on it is not a re-ask.
    rule = none_direction_rule()
    data = {"context": good_page_item()["context"], "lastAnswer": last_answer(REASK_NOTE)}
    r = run_hook(page_input("update", data), answer=ALLOW)
    prompt = r.calls[0]["prompt"] if r.calls else ""
    check("no re-ask, context only with a note: one model call, and no deny",
          len(r.calls) == 1 and r.code == 0 and r.out == "" and "\tdeny\t" not in r.log, detail(r))
    check("no re-ask, context only with a note: the prompt lacks NONE_DIRECTION_RULE",
          bool(rule) and prompt.count(rule) == 0, rule_detail(rule, r))


def case_reask_batch_one_call_rule_once():
    # Case 6: two re-asks in one batch make one model call, and the one prompt holds the rule once, not once per write.
    rule = none_direction_rule()
    writes = [{"op": "set", "collection": PAGE_ITEMS, "doc_id": "p1",
               "data": good_page_item(PAGE_MARK, lastAnswer=last_answer(REASK_NOTE))},
              {"op": "update", "collection": PAGE_ITEMS, "doc_id": "p2", "data": reask_item(PAGE_MARK_B, SHOW_CHEAPER_NOTE)}]
    r = run_hook(page_batch_input(writes), answer=ALLOW)
    prompt = r.calls[0]["prompt"] if r.calls else ""
    check("re-ask batch: two re-asks make one model call, claude-opus-5-5, and no deny",
          len(r.calls) == 1 and model_of(r.calls[0]["argv"]) == QUESTION_MODEL and r.code == 0 and r.out == ""
          and "\tdeny\t" not in r.log, detail(r))
    check("re-ask batch: the one prompt carries both writes", PAGE_MARK in prompt and PAGE_MARK_B in prompt,
          prompt[:200])
    check("re-ask batch: the one prompt holds NONE_DIRECTION_RULE exactly once", bool(rule) and prompt.count(rule) == 1,
          rule_detail(rule, r))


def case_reask_refusal_denies():
    # Case 7: case 1's write, and the fake refuses it. The deny is question-judge, and the prompt holds the rule
    # once, so this case pins the rule's count in the prompt, apart from the deny.
    rule = none_direction_rule()
    r = run_hook(page_input("update", reask_item(PAGE_MARK)), answer=REASK_FLAG)
    d = r.deny() or {}
    prompt = r.calls[0]["prompt"] if r.calls else ""
    check("re-ask refusal: the judge's deny is rule question-judge, one deny line, one model call",
          r.code == 0 and d.get("permissionDecision") == "deny" and r.reason().startswith("question-judge: ")
          and "already gives the direction" in r.reason() and r.log.count("\tdeny\tquestion-judge\t") == 1
          and len(r.calls) == 1, detail(r))
    check("re-ask refusal: the one prompt holds NONE_DIRECTION_RULE exactly once", bool(rule) and prompt.count(rule) == 1,
          rule_detail(rule, r))


def case_picked_choice_with_note_lacks_rule():
    # A picked choice (a key) with a note is the owner choosing an option, not a "none of these" direction, so the
    # write is no re-ask. The call still makes its one model call, so an early exit cannot pass this check.
    import question_form  # the one form check (hooks/question_form.py)
    fixture = reask_item(PAGE_MARK, PLAIN_NOTE, choice="a")
    got = question_form.item_hit("update", {"collection": PAGE_ITEMS, "doc_id": "p1", "data": fixture})
    check("picked-choice fixture: the update passes question_form.item_hit, so a refusal below is the judge's",
          got == ("", ""), got)
    rule = none_direction_rule()
    r = run_hook(page_input("update", fixture), answer=ALLOW)
    prompt = r.calls[0]["prompt"] if r.calls else ""
    check("picked choice with a note: one model call, and no deny",
          len(r.calls) == 1 and r.code == 0 and r.out == "" and "\tdeny\t" not in r.log, detail(r))
    check("picked choice with a note: the prompt lacks NONE_DIRECTION_RULE", bool(rule) and prompt.count(rule) == 0,
          rule_detail(rule, r))


def case_none_choice_with_note_holds_rule_once():
    # The same write with choice none is a "none of these" re-ask, so the one prompt holds the rule once.
    rule = none_direction_rule()
    r = run_hook(page_input("update", reask_item(PAGE_MARK, PLAIN_NOTE, choice="none")), answer=ALLOW)
    prompt = r.calls[0]["prompt"] if r.calls else ""
    check("none choice with a note: one model call, and no deny",
          len(r.calls) == 1 and r.code == 0 and r.out == "" and "\tdeny\t" not in r.log, detail(r))
    check("none choice with a note: the one prompt holds NONE_DIRECTION_RULE exactly once",
          bool(rule) and prompt.count(rule) == 1, rule_detail(rule, r))


def case_done_answer_is_not_reask():
    # A task's answer carries `done` and no choice: "Marked done." or "Not marked done." (docs/design/last-answer-notes.md,
    # section 4). It gives no "none of these" direction, so the one prompt lacks the rule. The call still makes its one
    # model call, so an early exit cannot pass this check.
    import question_form  # the one form check (hooks/question_form.py)
    rule = none_direction_rule()
    for done in (False, True):
        fixture = reask_item(PAGE_MARK, done=done)
        got = question_form.item_hit("update", {"collection": PAGE_ITEMS, "doc_id": "p1", "data": fixture})
        check("done=%s fixture: the update passes question_form.item_hit, so a refusal below is the judge's" % done,
              got == ("", ""), got)
        r = run_hook(page_input("update", fixture), answer=ALLOW)
        prompt = r.calls[0]["prompt"] if r.calls else ""
        check("done=%s answer: one model call, and no deny" % done,
              len(r.calls) == 1 and r.code == 0 and r.out == "" and "\tdeny\t" not in r.log, detail(r))
        check("done=%s answer: the prompt lacks NONE_DIRECTION_RULE" % done,
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
    # Case 1: a set with options, none marked, makes one model call, and the one prompt holds the rule once.
    rule = widening_rule()
    r = run_hook(page_input("set", good_page_item()), answer=ALLOW)
    check("widening set: one model call, and no deny", len(r.calls) == 1 and r.code == 0 and r.out == ""
          and "\tdeny\t" not in r.log, detail(r))
    prompt = r.calls[0]["prompt"] if r.calls else ""
    ok, cause = rule_once(prompt, rule)
    check("widening set: the one prompt holds WIDENING_RULE exactly once, after the question-format prompt", ok, cause)


def case_widening_batch_holds_rule_once():
    # Case 2: two option writes in one batch make one model call, and the one prompt holds the rule exactly once.
    rule = widening_rule()
    writes = [{"op": "set", "collection": PAGE_ITEMS, "doc_id": "p1", "data": good_page_item(PAGE_MARK)},
              {"op": "update", "collection": PAGE_ITEMS, "doc_id": "p2",
               "data": with_frozen_fields({"options": good_page_item(PAGE_MARK_B)["options"]})}]
    r = run_hook(page_batch_input(writes), answer=ALLOW)
    check("widening batch: two option writes make one model call, and no deny", len(r.calls) == 1 and r.code == 0
          and r.out == "" and "\tdeny\t" not in r.log, detail(r))
    prompt = r.calls[0]["prompt"] if r.calls else ""
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
        ("an update with context and empty options", page_input("update", with_frozen_fields({"context": context, "options": []})),
         "PAGE_PROMPT"),
        ("an AskUserQuestion box with options", question_input(), "QUESTION_PROMPT"),
        ("an Agent spawn", spawn_input("builder", model="sonnet"), "SPAWN_PROMPT"),
    ):
        r = run_hook(inp, answer=ALLOW)
        check("widening absent: %s is judged once, and no deny" % label, len(r.calls) == 1 and r.code == 0
              and r.out == "" and "\tdeny\t" not in r.log, detail(r))
        prompt = r.calls[0]["prompt"] if r.calls else ""
        ok, cause = no_widening_rule(prompt, template)
        check("widening absent: %s gets no widening rule" % label, ok, cause)


def case_widening_refusal_names_the_option():
    # Case 4: an unmarked option that widens a shared tool is refused, and the refusal names its key. The model is faked,
    # so the deny is the hook passing the reason through. The rule check reads what the judge is told before it answers.
    import question_form  # the one form check (hooks/question_form.py)
    rule = widening_rule()
    item = good_page_item(PAGE_MARK)
    item["options"][1]["label"] = "Accept a second accepted form"
    item = with_frozen_fields(item)  # the relabelled option is the item's first write, so its shown is the new label
    got = question_form.item_hit("set", {"collection": PAGE_ITEMS, "doc_id": "p1", "data": item})
    check("widening refusal fixture: the item passes question_form.item_hit, so a refusal below is the judge's",
          got == ("", ""), got)
    r = run_hook(page_input("set", item), answer=WIDENING_FLAG)
    d = r.deny() or {}
    check("widening refusal: the unmarked option is denied, rule question-judge, and the reason names its key",
          r.code == 0 and d.get("permissionDecision") == "deny" and r.reason().startswith("question-judge: ")
          and "option `b`" in r.reason() and r.log.count("\tdeny\tquestion-judge\t") == 1 and len(r.calls) == 1,
          detail(r))
    prompt = r.calls[0]["prompt"] if r.calls else ""
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
    check("fair option code path: one judge call and no deny from call_judge", len(r.calls) == 1 and r.code == 0
          and r.out == "" and "\tdeny\t" not in r.log, detail(r))
    picked = dict(item, pick="b")
    got = question_form.item_hit("set", {"collection": PAGE_ITEMS, "doc_id": "p1", "data": picked})
    check("widening scope: the marked option, picked, is refused as uniform-pick, so the mark is read",
          got[0] == "uniform-pick", "the marked option carries no mark: question_form.WIDENS_KEY is not defined"
          if not key else got)
    prompt = r.calls[0]["prompt"] if r.calls else ""
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
    check("settings: its matcher is Agent, AskUserQuestion, ArtifactData and the two send tools",
          matcher == {"Agent", "AskUserQuestion", "ArtifactData", *SEND_TOOL_NAMES}, entry.get("matcher"))
    # A judged page write runs the dedicated past-ruling call (60 s) and then the form call (60 s), so the hook needs
    # both plus start-up. A hook timeout lets the write through unvetted.
    check("settings: its timeout is 130 s, past-ruling call 60 s plus form call 60 s plus start-up",
          hook.get("timeout", 0) == 130, hook)
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
    # Item 8 of a judged page write runs in the dedicated past-ruling call, so the step ruling reaches that call.
    prompt = r.past[0]["prompt"] if len(r.past) == 1 else ""
    check("past ruling 133: the dedicated call holds the step c95 ruling sentence",
          len(r.past) == 1 and CI_STEP_SENTENCE in without_call(prompt, item), detail(r))


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
    # Two git starts: the roadmap read, then the ruled store's ls-tree (one start when the store is absent).
    r = run_hook(question_input(box=box, cwd=CI_REPO), answer=ALLOW)
    check("past ruling cost: a judged question runs two git processes, the roadmap read and the store's ls-tree",
          len(r.calls) == 1 and r.git == 2, detail(r))
    item = good_page_item(title="Raise the CI milestone job cap?", context=CI_PAGE_CONTEXT, options=CI_PAGE_OPTIONS)
    p = run_hook(page_input("set", item, doc_id="c133", cwd=CI_REPO), answer=ALLOW)
    # A judged page write adds one Sonnet call, the dedicated past-ruling call, before its one form call. Its git reads
    # are the same two starts as before.
    check("past ruling cost: a judged page write runs its dedicated call, then the form call, with two git processes",
          len(p.past) == 1 and len(p.calls) == 1 and p.git == 2, detail(p))
    q = run_hook(question_input(box=good_box(), cwd=BARE_REPO), answer=ALLOW)
    check("past ruling cost: a judged question with no roadmap ref runs at most two git processes",
          len(q.calls) == 1 and q.git <= 2, detail(q))
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
    check("unvetted page: the same item with an Unvetted: line in context passes after one model attempt",
          r.code == 0 and r.out == "" and len(r.calls) == 1 and "\tdeny\t" not in r.log, detail(r))


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
    # Item 8 of a judged page write runs in the dedicated past-ruling call, which refuses the ruled task.
    r = run_hook(page_input("set", task, doc_id="t8", cwd=DECISIONS_REPO), answer=ALLOW, past=refuse)
    prompt = r.past[0]["prompt"] if len(r.past) == 1 else ""
    check("page task: the dedicated call carries item 8 and the ruling, and the item never exempts a task",
          len(r.past) == 1 and item_text(prompt, 8) != "" and "never applies to a task" not in item_text(prompt, 8).lower()
          and APPS_RULING in without_call(prompt, task), detail(r))
    check("page task: a ruled task is refused by the dedicated call", (r.deny() or {}).get("permissionDecision") == "deny"
          and r.reason().startswith("past-ruling: ") and "Unvetted:" not in r.reason(), detail(r))


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


# ------------------------------------------------------------------ owner-question sends and the dedicated call
#
# Rulings of the past-ruling rebuild. (1) An owner question, a message by a send tool with a Goal line and a Problem
# line that has a stake, outside code fences, gets the dedicated past-ruling call (lint/report_guard.py
# past_ruling_problem, item 8 alone) before it is sent. A judged page item write runs that call first, alone, and the
# form judge (items 1 to 7) only after it allows. (2) Every Unvetted outcome of a PreToolUse refusal prints
# UNVETTED_REMEDY with its `Unvetted:` marker, and a relay refusal (a ruling found) stays facts-only. (3) Item 8 holds
# the record-kind sentence R and the step rules S1 to S4. The send tool names are the harness's own, pinned here; a
# case checks that the one home (hooks/shared_names.py) holds them.
SEND_TOOL_NAMES = ("mcp__claude-code-remote__send_message", "SendMessage")
PAGE_FILLER = "Background sentence for the owner. " * 200  # about 8,000 characters, past ASK_TEXT_MAX
SEND_LOG_FILLER = "Lane 4 log: ruff clean, no finding.\n" * 200  # about 7,200 characters, past ASK_TEXT_MAX
SHARED_NAMES = os.path.join(HERE, "shared_names.py")
REPORT_GUARD = os.path.join(REPO, "lint", "report_guard.py")
TRANSCRIPT = os.path.join(REPO, "lint", "_transcript.py")
WT_SLUG, OUT_SLUG = "when-a-worktree-may-be-removed", "an-agent-outside-its-home-tree-must-stop"
WT_MARK, OUT_MARK = "worktree-5e8a", "outside-2b7f"
WT_RULING = ("Owner, 2026-10-30: a worktree goes only when it is clean and idle, and a running agent's lock is never "
             "freed. Marker " + WT_MARK + ".")
OUT_RULING = ("Owner, 2026-10-30: each session writes only inside its own checkout, and an agent whose worktree is gone "
              "stops and reports. Marker " + OUT_MARK + ".")
SEND_REPO = make_repo("send-incidents", decisions={WT_SLUG: WT_RULING, OUT_SLUG: OUT_RULING})
GOAL_357 = "Goal: a merge frees disk without losing a running agent's work."
PROBLEM_357 = "Problem (risk): freeing a running agent's worktree loses its uncommitted files."
BASED_READ = ("Based on (read): guard rule worktree-home already stops an agent whose worktree is gone, so it cannot "
              "write into main.")
BASED_RULING = ("Based on (ruling): decisions/%s says a worktree goes only when clean and idle. This case has a running "
                "agent, so the owner is asked again: the ruling does not name it." % WT_SLUG)
# The owner question a send carries (the coordinator's page item text, verbatim).
INCIDENT = "\n".join([
    "Page item for the owner (from coordinator). Title: How should a merge free disk without losing a running agent's work?",
    GOAL_357,
    PROBLEM_357,
    BASED_READ,
    "Departs from: main, where the merge frees any lock it finds. Each option adds a test before the free.",
    "Options: a. Never free a running agent's lock; the worktree goes when the agent ends. b. Save, then free: copy "
    "uncommitted changes to an archive ref, then remove the worktree. c. Both: a for running agents, b for finished ones "
    "(recommended).",
])
WT_OPTIONS = [
    {"label": "Never free a running lock (Recommended)",
     "description": "Gain: a running agent keeps its uncommitted files. Lose: the worktree stays until the agent ends."},
    {"label": "Save, then free",
     "description": "Gain: the worktree goes now. Lose: the archive ref must be cleaned up later."}]
WT_PAGE_ITEM = good_page_item(
    context="\n".join((GOAL_357, PROBLEM_357, BASED_READ, DEPARTS_LINE)),
    options=[{"key": "a", "label": "Never free a running lock", "gain": "A running agent keeps its uncommitted files.",
              "lose": "The worktree stays until the agent ends."},
             {"key": "b", "label": "Save, then free", "gain": "The worktree goes now.",
              "lose": "The archive ref needs cleaning later."}])
# Item 8's sentences, verbatim (the one text, call_judge.PAST_RULING_ITEM, that the chat box and the dedicated call send).
ITEM8_SENTENCES = (
    ("R", "A listed decision or debt record is a ruling by its kind, so cite it with no owner marker."),
    ("S1", "A step line is a ruling when it says the owner ruled, answered, picked or granted."),
    ("S2", "A line where a session made the call, such as a recommended option, a proposed pick, or a lane's call, "
           "is not a ruling."),
    ("S3", "An incident or gripe line that only tells what went wrong is not a ruling."),
    ("S4", "A ruling that mentions a risk, a defect or an incident is still a ruling."),
)


def ruled_by(slug):
    """A canned refusal that cites the one record the model was shown, with its date, as item 8 asks."""
    return json.dumps({"ok": False, "reason": "decisions/%s: ruled 2026-10-30, so the owner is not asked again." % slug})


def send_input(tool, message, cwd=SEND_REPO, session=SID_A):
    """One send, as the harness sends it. The mcp tool names its target by session_id, SendMessage by to."""
    if tool == SEND_TOOL_NAMES[0]:
        tool_input = {"session_id": "session_lane07", "message": message}
    else:
        tool_input = {"to": "session_lane07", "message": message, "summary": "owner question"}
    return json.dumps({"session_id": session, "tool_name": tool, "tool_input": tool_input, "cwd": cwd})


def batch_input(writes, cwd):
    """A batch ArtifactData call with the payload's cwd set to `cwd` (page_batch_input fixes it to PAGE_REPO)."""
    payload = {"session_id": SID_A, "tool_name": "ArtifactData", "cwd": cwd,
               "tool_input": {"action": "batch", "url": PAGE_URL, "writes": writes}}
    return json.dumps(payload)


def unvetted_marker(text):
    """The backtick span an Unvetted remedy asks for: `Unvetted: <why it could not be checked>`."""
    found = re.search(r"`Unvetted: [^`]*`", text or "")
    return found.group(0) if found else ""


def facts_only_line(reason, constant):
    """True when a refusal prints the facts-only owner line of lint/report_guard.py `constant`, read at test time: its
    fixed text on both sides of the judge's reason, in order, and no `Remedy:` text and no `Unvetted:` marker anywhere
    (decision guard-remedy-not-to-owner). False for a missing constant, so the check fails on the missing piece."""
    text = guard_constant(REPORT_GUARD, constant)
    wording = getattr(load_file_module(REPORT_GUARD, "probe_session_wording"), "session_wording", None)
    if text.count("%s") != 1 or wording is None:
        return False
    head, tail = text.split("%s", 1)
    at = reason.find(head)
    return (at >= 0 and tail in reason[at + len(head):] and not wording(head + tail)
            and "Remedy:" not in reason and "Unvetted:" not in reason)


def guard_constant(path, name):
    """One constant of a hook or lint file, read at test time and never copied. "" when the file or the name is absent,
    so a check names the missing piece instead of crashing."""
    try:
        return getattr(load_file_module(path, "probe_" + name), name, "") or ""
    except Exception:
        return ""


def page_item_passes_the_form(label):
    # Scope first: the item must pass the form, so the judge runs and a refusal below is the judge's.
    import question_form  # the one form check (hooks/question_form.py)
    got = question_form.item_hit("set", {"collection": PAGE_ITEMS, "doc_id": "p1", "data": WT_PAGE_ITEM})
    check("page dedicated %s: the item passes question_form.item_hit, so the judge runs" % label, got == ("", ""), got)


def case_send_owner_question_gets_the_dedicated_call_before_it_goes():
    # Control: the same ruled question in the chat box is refused as past-ruling.
    import question_form  # the one form check (hooks/question_form.py)
    box = good_box(goal=GOAL_357, problem=PROBLEM_357, based=(BASED_READ,), options=WT_OPTIONS)
    check("send fixture: the box passes chat_hit", question_form.chat_hit(box) == ("", ""), question_form.chat_hit(box))
    control = run_hook(question_input(box=box, cwd=SEND_REPO), answer=ruled_by(WT_SLUG))
    check("send control: the same question in the chat box is refused as past-ruling",
          (control.deny() or {}).get("permissionDecision") == "deny" and control.reason().startswith("past-ruling: "),
          detail(control))
    for tool in SEND_TOOL_NAMES:
        name = "send via %s" % tool
        r = run_hook(send_input(tool, INCIDENT), past=ruled_by(WT_SLUG))
        check(name + ": the dedicated past-ruling call runs before the send, and no other call", r.seq == ["past"],
              detail(r))
        check(name + ": the dedicated call runs on Sonnet", len(r.past) == 1
              and model_of(r.past[0]["argv"]) == AGENT_MODEL, detail(r))
        check(name + ": the dedicated call holds the ruling record", len(r.past) == 1
              and WT_MARK in r.past[0]["prompt"], detail(r))
        check(name + ": the send is denied", (r.deny() or {}).get("permissionDecision") == "deny", detail(r))
        check(name + ": the refusal is rule past-ruling", r.reason().startswith("past-ruling: "), r.reason()[:160])
        check(name + ": the refusal prints the relay owner line, facts only",
              facts_only_line(r.reason(), "RELAY_RULE_REASON"), r.reason()[:200])


def case_send_based_on_ruling_line_reaches_the_dedicated_call():
    # A re-ask the ruling allows is sent. The dedicated call reads the Based on (ruling) line, and the allow passes it.
    text = INCIDENT.replace(BASED_READ, BASED_READ + "\n" + BASED_RULING, 1)
    check("send based-on fixture: the Based on ruling line follows the Based on read line", BASED_RULING in text, "fixture")
    for tool in SEND_TOOL_NAMES:
        name = "send based-on via %s" % tool
        r = run_hook(send_input(tool, text), past=ALLOW)
        check(name + ": one dedicated call, and no form call", r.seq == ["past"], detail(r))
        check(name + ": the prompt carries the Based on ruling line", len(r.past) == 1
              and BASED_RULING in r.past[0]["prompt"], detail(r))
        check(name + ": the allowed send is not refused", r.code == 0 and r.deny() is None, detail(r))


def case_send_dedicated_call_error_is_unvetted_unless_marked():
    marker = unvetted_marker(guard_constant(HOOK, "UNVETTED_REMEDY"))
    check("send unvetted: call_judge holds UNVETTED_REMEDY with its `Unvetted:` marker", bool(marker),
          "UNVETTED_REMEDY has no backtick Unvetted marker")
    marked = INCIDENT + "\n" + UNVETTED_LINE
    for tool in SEND_TOOL_NAMES:
        name = "send, dedicated call fails, via %s" % tool
        r = run_hook(send_input(tool, INCIDENT), past_fail=True)
        check(name + ": refused as past-ruling", (r.deny() or {}).get("permissionDecision") == "deny"
              and r.reason().startswith("past-ruling: "), r.reason()[:160])
        check(name + ": the refusal names the Unvetted marker", bool(marker) and marker in r.reason(), r.reason()[:200])
        check(name + ": guard.log records the past-ruling deny", "\tdeny\tpast-ruling\t" in r.log, r.log[-200:])
        r = run_hook(send_input(tool, marked), past_fail=True)
        check(name + " with an Unvetted line: not refused", r.code == 0 and r.deny() is None, detail(r))


def case_send_check_that_cannot_run_is_refused_as_unvetted():
    # report_guard cannot be imported, so the past-ruling check cannot run. A send that a ruling settles must not go.
    marker = unvetted_marker(guard_constant(HOOK, "UNVETTED_REMEDY"))
    for tool in SEND_TOOL_NAMES:
        name = "send, check cannot run (report_guard blocked), via %s" % tool
        r = run_hook(send_input(tool, INCIDENT), block="report_guard")
        check(name + ": refused, not allowed", (r.deny() or {}).get("permissionDecision") == "deny", detail(r))
        check(name + ": the refusal is rule past-ruling", r.reason().startswith("past-ruling: "), r.reason()[:160])
        check(name + ": the refusal names the Unvetted marker", bool(marker) and marker in r.reason(), r.reason()[:200])
        check(name + ": no fail-open line on stderr", "call judge failed open" not in r.err, r.err[-200:])


def case_send_over_the_cap_keeps_the_goal_and_problem():
    # A send past ASK_TEXT_MAX: its form lines sit at the top, where a front cut would drop them. Both reach the prompt.
    cap = guard_constant(REPORT_GUARD, "ASK_TEXT_MAX")
    message = INCIDENT + "\n" + SEND_LOG_FILLER
    check("send over the cap: the message is longer than ASK_TEXT_MAX", isinstance(cap, int) and len(message) > cap, cap)
    for tool in SEND_TOOL_NAMES:
        name = "send over the cap via %s" % tool
        r = run_hook(send_input(tool, message), past=ALLOW)
        prompt = r.past[0]["prompt"] if len(r.past) == 1 else ""
        check(name + ": one dedicated call", r.seq == ["past"], detail(r))
        check(name + ": the Goal line reaches the prompt", GOAL_357 in prompt, detail(r))
        check(name + ": the Problem line reaches the prompt", PROBLEM_357 in prompt, detail(r))


def case_send_stray_fence_does_not_hide_the_form():
    # A fence line that never closes opens no fence: the form lines after it are prose, so the send is judged.
    message = "```\nAn earlier quote, left open by mistake:\n" + INCIDENT
    for tool in SEND_TOOL_NAMES:
        name = "send after a stray fence line via %s" % tool
        r = run_hook(send_input(tool, message), past=ruled_by(WT_SLUG))
        check(name + ": the dedicated call runs, and the send is denied as past-ruling",
              r.seq == ["past"] and (r.deny() or {}).get("permissionDecision") == "deny"
              and r.reason().startswith("past-ruling: "), detail(r))


def case_send_reads_the_forms_owners_pages_use():
    # The form lines on an owner's page are often bold, bulleted, quoted or headed. Each variant is still judged.
    def replace_line(prefix, new):
        return "\n".join(new if part.startswith(prefix) else part for part in INCIDENT.split("\n"))
    variants = (
        ("a bold Goal", replace_line("Goal:", "**Goal:** " + GOAL_357[len("Goal: "):])),
        ("a bulleted Goal", replace_line("Goal:", "- " + GOAL_357)),
        ("a blockquoted Goal", replace_line("Goal:", "> " + GOAL_357)),
        ("a heading Goal", replace_line("Goal:", "## " + GOAL_357)),
        ("a bold Problem (risk)", replace_line("Problem (risk):", "**" + PROBLEM_357 + "**")),
    )
    for label, message in variants:
        name = "send form, %s" % label
        r = run_hook(send_input(SEND_TOOL_NAMES[0], message), past=ruled_by(WT_SLUG))
        check(name + ": the dedicated call runs, and the send is denied as past-ruling",
              r.seq == ["past"] and (r.deny() or {}).get("permissionDecision") == "deny", detail(r))


def case_send_tool_names_have_one_home():
    shared = guard_constant(SHARED_NAMES, "SEND_TOOLS")
    check("send names: hooks/shared_names.py holds SEND_TOOLS, the two send tool names",
          tuple(shared) == SEND_TOOL_NAMES, shared)
    for path, label in ((HOOK, "hooks/call_judge.py"), (TRANSCRIPT, "lint/_transcript.py")):
        with open(path, encoding="utf-8") as f:
            text = f.read()
        check("send names: %s holds no literal copy of SEND_TOOLS" % label,
              re.search(r"^SEND_TOOLS\s*=", text, re.M) is None, label)


def case_item8_holds_the_record_kind_and_step_ruling_sentences():
    box = good_box(goal=GOAL_357, problem=PROBLEM_357, based=(BASED_READ,), options=WT_OPTIONS)
    r = run_hook(question_input(box=box, cwd=SEND_REPO), answer=ALLOW)
    item8 = item_text(r.calls[0]["prompt"], 8) if len(r.calls) == 1 else ""
    for name, sentence in ITEM8_SENTENCES:
        check("item 8 %s: the chat box's item 8 holds the sentence verbatim" % name, sentence in item8, item8[:160])


def case_page_item_write_runs_the_dedicated_call_first_and_alone():
    page_item_passes_the_form("A")
    item8 = guard_constant(HOOK, "PAST_RULING_ITEM")
    check("page dedicated: call_judge holds the item 8 text to look for", bool(item8), "PAST_RULING_ITEM is missing")
    r = run_hook(page_input("set", WT_PAGE_ITEM, cwd=SEND_REPO), answer=ALLOW, past=ALLOW)
    check("page dedicated: the calls are the dedicated past-ruling call, then the form call", r.seq == ["past", "form"],
          detail(r))
    check("page dedicated: the dedicated call runs on Sonnet", len(r.past) == 1
          and model_of(r.past[0]["argv"]) == AGENT_MODEL, detail(r))
    check("page dedicated: the form call runs on Opus", len(r.calls) == 1
          and model_of(r.calls[0]["argv"]) == QUESTION_MODEL, detail(r))
    form_prompt = r.calls[0]["prompt"] if r.calls else ""
    check("page dedicated: the form-judge prompt holds no item 8 text", bool(item8) and item8 not in form_prompt,
          item8[:60])
    check("page dedicated: the write is allowed", r.code == 0 and r.out == "" and r.deny() is None, detail(r))


def case_page_item_refused_by_the_dedicated_call_is_denied_before_the_form_judge():
    # Control: the form judge's own refusal denies the same item, rule question-judge.
    page_item_passes_the_form("B")
    control = run_hook(page_input("set", WT_PAGE_ITEM, cwd=SEND_REPO), answer=PAGE_FLAG, past=ALLOW)
    check("page dedicated control: a form refusal denies the item, rule question-judge",
          (control.deny() or {}).get("permissionDecision") == "deny" and control.reason().startswith("question-judge: "),
          detail(control))
    r = run_hook(page_input("set", WT_PAGE_ITEM, cwd=SEND_REPO), answer=ALLOW, past=ruled_by(WT_SLUG))
    check("page dedicated: the dedicated call alone refuses the write, and no form call follows", r.seq == ["past"],
          detail(r))
    check("page dedicated: the refusal is rule past-ruling", r.reason().startswith("past-ruling: "), r.reason()[:160])
    check("page dedicated: the refusal prints the relay owner line, facts only",
          facts_only_line(r.reason(), "RELAY_RULE_REASON"), r.reason()[:200])


def case_page_item_dedicated_call_error_is_unvetted_unless_marked():
    page_item_passes_the_form("C")
    marker = unvetted_marker(guard_constant(HOOK, "UNVETTED_REMEDY"))
    r = run_hook(page_input("set", WT_PAGE_ITEM, cwd=SEND_REPO), answer=ALLOW, past_fail=True)
    check("page dedicated C: the write is refused as past-ruling, and no form call follows",
          (r.deny() or {}).get("permissionDecision") == "deny" and r.reason().startswith("past-ruling: ")
          and r.seq == ["past"], detail(r))
    check("page dedicated C: the refusal names the Unvetted marker", bool(marker) and marker in r.reason(), r.reason()[:200])
    marked = dict(WT_PAGE_ITEM, context=WT_PAGE_ITEM["context"] + "\n" + UNVETTED_LINE)
    r = run_hook(page_input("set", marked, cwd=SEND_REPO), answer=ALLOW, past_fail=True)
    check("page dedicated C: with an Unvetted line in context, the form call follows and the write is not refused",
          r.seq == ["past", "form"] and r.deny() is None, detail(r))


def case_page_check_that_cannot_run_is_refused_as_unvetted():
    page_item_passes_the_form("D")
    marker = unvetted_marker(guard_constant(HOOK, "UNVETTED_REMEDY"))
    r = run_hook(page_input("set", WT_PAGE_ITEM, cwd=SEND_REPO), answer=ALLOW, block="report_guard")
    check("page dedicated D: the write is refused, not allowed", (r.deny() or {}).get("permissionDecision") == "deny",
          detail(r))
    check("page dedicated D: the refusal is rule past-ruling and names the Unvetted marker",
          r.reason().startswith("past-ruling: ") and bool(marker) and marker in r.reason(), r.reason()[:200])
    check("page dedicated D: no form call follows", r.calls == [], detail(r))


def case_page_batch_reaches_the_dedicated_call_whole():
    # The batch's second write is past ASK_TEXT_MAX, so a front cut would drop the first write's text. Both reach the call.
    long_context = "\n".join((GOAL_357, PROBLEM_357, BASED_READ, DEPARTS_LINE, PAGE_FILLER))
    writes = [{"op": "set", "collection": PAGE_ITEMS, "doc_id": "p1", "data": good_page_item(PAGE_MARK)},
              {"op": "set", "collection": PAGE_ITEMS, "doc_id": "p2",
               "data": good_page_item(PAGE_MARK_B, context=long_context)}]
    r = run_hook(batch_input(writes, SEND_REPO), answer=ALLOW, past=ALLOW)
    prompt = r.past[0]["prompt"] if len(r.past) == 1 else ""
    check("page batch: one dedicated call for the batch, then one form call", r.seq == ["past", "form"], detail(r))
    check("page batch: the first write's text reaches the dedicated call", PAGE_MARK in prompt, detail(r))
    check("page batch: the second write's text reaches the dedicated call", PAGE_MARK_B in prompt, detail(r))


def main():
    for case in (case_agent_refusal, case_spawn_prompt_bars_a_lane_waiting_page_write, case_agent_override, case_explore_row_is_vetoed,
                 case_explore_remedy_names_marker, case_agent_fallback_names_marker, case_question,
                 case_question_departs, case_page_fixture_passes_the_form, case_page_reject_and_accept,
                 case_page_no_model_call, case_page_batch_one_call, case_page_override,
                 case_page_model_failure_fails_open, case_page_str_replace_judged,
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
                 case_page_relative_file_path_reaches_the_review, case_page_relative_file_path_passing_item_passes,
                 case_page_absolute_file_path_is_judged,
                 case_send_owner_question_gets_the_dedicated_call_before_it_goes,
                 case_send_based_on_ruling_line_reaches_the_dedicated_call,
                 case_send_dedicated_call_error_is_unvetted_unless_marked,
                 case_send_check_that_cannot_run_is_refused_as_unvetted,
                 case_send_over_the_cap_keeps_the_goal_and_problem,
                 case_send_stray_fence_does_not_hide_the_form,
                 case_send_reads_the_forms_owners_pages_use, case_send_tool_names_have_one_home,
                 case_item8_holds_the_record_kind_and_step_ruling_sentences,
                 case_page_item_write_runs_the_dedicated_call_first_and_alone,
                 case_page_item_refused_by_the_dedicated_call_is_denied_before_the_form_judge,
                 case_page_item_dedicated_call_error_is_unvetted_unless_marked,
                 case_page_check_that_cannot_run_is_refused_as_unvetted,
                 case_page_batch_reaches_the_dedicated_call_whole):
        try:
            case()
        except Exception as exc:
            check(case.__name__, False, "raised %s: %s" % (type(exc).__name__, exc))
    print("FAIL: %d failed" % len(FAILED) if FAILED else "all checks passed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
