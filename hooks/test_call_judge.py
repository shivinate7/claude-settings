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
- A challenge to a past ruling (decision `question-form`, rule outcomes-stale-decision-protocol): item 8 passes a
  question that names the record and brings a new fact, or that names the record, quotes the ruling's sentence that states
  no measure, and says the claim is unmeasured. The outcome protected, what protects it now and a proposed fix are optional. It refuses a re-ask that brings no new
  fact. A denial tells the session how to challenge, never to
  withdraw. A challenge is a question, never a grant (see the section "a challenge to a past ruling").
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
    r = run_hook(page_input("set", None, doc_id="p1", cwd=repo, file_path=name), answer=apps_refusal())
    prompt = r.calls[0]["prompt"] if r.calls else ""
    check("relative item: the write reaches one model review", len(r.calls) == 1, detail(r))
    check("relative item: the model sees the item read from the file", PAGE_MARK in prompt, prompt[:160])
    check("relative item: the APPS record and its ruling reach the prompt",
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
    # The control: an absolute file_path is read on main too, so this case is green before and after the fix.
    import question_form  # the one form check (hooks/question_form.py)
    repo = relative_item_repo()
    path = os.path.join(repo, "absolute-item-deny.json")
    write_item_file(path, apps_item())
    check("absolute item: the file is at its absolute path", os.path.isabs(path) and os.path.isfile(path), path)
    r = run_hook(page_input("set", None, doc_id="p1", cwd=repo, file_path=path), answer=apps_refusal())
    prompt = r.calls[0]["prompt"] if r.calls else ""
    rule = question_form.PAST_RULING_RULE
    check("absolute item: the write reaches one model review", len(r.calls) == 1 and PAGE_MARK in prompt, detail(r))
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
    # Two git starts: the roadmap read, then the ruled store's ls-tree (one start when the store is absent).
    r = run_hook(question_input(box=box, cwd=CI_REPO), answer=ALLOW)
    check("past ruling cost: a judged question runs two git processes, the roadmap read and the store's ls-tree",
          len(r.calls) == 1 and r.git == 2, detail(r))
    item = good_page_item(title="Raise the CI milestone job cap?", context=CI_PAGE_CONTEXT, options=CI_PAGE_OPTIONS)
    p = run_hook(page_input("set", item, doc_id="c133", cwd=CI_REPO), answer=ALLOW)
    check("past ruling cost: a judged page write runs two git processes", len(p.calls) == 1 and p.git == 2, detail(p))
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
    r = run_hook(page_input("set", task, doc_id="t8", cwd=DECISIONS_REPO), answer=refuse)
    prompt = r.calls[0]["prompt"] if r.calls else ""
    check("page task: the one model call carries item 8 and the ruling, and the item never exempts a task",
          len(r.calls) == 1 and item_text(prompt, 8) != "" and "never applies to a task" not in item_text(prompt, 8).lower()
          and APPS_RULING in without_call(prompt, task), detail(r))
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


# ------------------------------------------------------------------ a challenge to a past ruling (R39)
#
# Decision `question-form` and rule outcomes-stale-decision-protocol: a question that names the record and brings a new
# fact passes, and the other parts are optional. Item 8 refuses a re-ask that takes neither route. A denial tells the
# session how to challenge, never to withdraw. A challenge reaches the owner as a question, never as a grant. The model is
# mocked, so these cases read the text the code gives the model, the denial text the code appends, and the grant readers
# that no question path calls.
CHAL_GOAL = "Goal: decide whether the GitHub apps keep access to claude-settings, now the audit counts more of them"
CHAL_PROBLEM = ("Problem (risk): %s says 'keep the apps' access to claude-settings as is', which protected easy calls "
                "into the repo; the monthly audit now protects that, and it counts 14 apps where the ruling named 9, "
                "so the ruling needs your word" % APPS_SLUG)
CHAL_BASED = ("Based on (measured): the monthly audit counts 14 apps with access, 5 more than the 9 %s was written on"
              % APPS_SLUG,)
CHAL_OPTIONS = [
    {"label": "Remove the 5 apps the audit lists as unused (Recommended)",
     "description": "Gain: fewer apps can write to the repo, and the calls the ruling protected stay simple. "
                    "Lose: five apps lose access."},
    {"label": "Keep the apps as the ruling says",
     "description": "Gain: nothing changes on the repo. Lose: five apps keep access the audit does not justify."}]
CHAL_GRANT_OPTIONS = [
    {"label": "Yes, grant it now (Recommended)",
     "description": "Gain: a yes here overrides the ruling and grants the change now. Lose: the ruling's protection goes."},
    {"label": "Hold it",
     "description": "Gain: the ruling stands. Lose: the five extra apps keep access."}]
CHAL_CONTEXT = "\n".join((CHAL_GOAL, CHAL_PROBLEM, CHAL_BASED[0], DEPARTS_LINE))
CHAL_PAGE_TITLE = "Remove the five unused apps?"
WITHDRAW_PHRASES = ("withdraw", "drop the question", "take the question back", "do not send", "don't send")
# The grant readers of the owner's own prompts (hooks/override.py, hooks/local_time.py). No question path may call one.
GRANT_READERS = ("grant_override_ask", "grant_opus_ask", "grant_override", "opus_ask", "override_ask", "opus_scope")
JUDGE_SOURCES = ("hooks/call_judge.py", "hooks/question_form.py", "hooks/reply_judge.py", "lint/report_guard.py")


def sentences_of(text):
    """The lowercase sentences of `text`, split at a full stop or a line break."""
    return [s for s in re.split(r"[.\n]", text.lower()) if s.strip()]


# A route-two challenge brings no new fact, so a "no new fact" refusal would wrongly refuse it; a bare re-ask is one
# that takes neither route (decision question-form).
def refuses_a_bare_re_ask(text):
    """True when a sentence of `text` refuses a re-ask that takes neither route. A negation in that sentence, such as
    "do not refuse", is no refusal."""
    return any("refuse" in s and "re-ask" in s and "neither route" in s and NEGATED_ROUTE.search(s) is None
               for s in sentences_of(text))


def says_new_fact_alone_passes(text):
    """True when a sentence of `text` says a challenge passes on a new fact alone. That wording makes a new fact the only
    ground of a pass, so it refuses the unmeasured route, which passes with no new fact. The item must not hold it."""
    return any("new fact alone" in s and "pass" in s for s in sentences_of(text))


# The negation sits right before the noun: "is not a new fact", "is no new fact", "is not a challenge". A negative word
# elsewhere in the sentence does not count, so "is a new fact, not a measure" is no negation of the new fact.
NEGATED_NEW_FACT_NOUN = re.compile(r"\b(?:not|no|never)\s+(?:a\s+)?new fact\b")
# The negation sits right before `challenge`, after the record clause: "is not a challenge".
NEGATED_CHALLENGE = re.compile(r"\b(?:not|no|never)\s+(?:a\s+)?challenge\b")
# A negative word, then `record` within four words: "does not name the record", "names no record", "without the record".
NEGATED_RECORD = re.compile(r"\b(?:not|no|without)\b(?:\s+[\w'-]+){0,4}\s+record\b")
# A negative word, then `new fact` within three words: "is not a new fact", "does not count as a new fact". It is wide on
# purpose here: says_unmeasured_is_no_new_fact must flag more blended wording, and the check refuses every flag.
NEGATED_NEW_FACT = re.compile(r"\b(?:not|never|no)\b(?:\s+[\w'-]+){0,3}\s+new fact")
# A negative word, or `no pass`, anywhere in a sentence that names the unmeasured route.
NEGATED_ROUTE = re.compile(r"\b(?:not|never|without)\b|\bno\s+(?:a\s+)?pass")


def restates_is_no_new_fact(text):
    """True when a sentence of `text` says a restatement of the ruling's own claim is not a new fact: the negation governs
    `new fact`, so "is a new fact, not a measure" is no pass."""
    return any(("restat" in s or "own claim" in s) and NEGATED_NEW_FACT_NOUN.search(s) is not None
               for s in sentences_of(text))


def names_unmeasured_route(text, needs_pass=True):
    """True when a sentence of `text` names the unmeasured route with the record and the quoted sentence of the ruling that
    states no measure (rule outcomes-stale-decision-protocol: name the record and the sentence). One sentence holds
    `unmeasured`, `record`, a quote and `sentence`, and no negation (not, never, without, or no pass). With `needs_pass`
    that sentence also says the route passes, as the whole word, so "is refused too" and "fails" are no pass. The tail
    and the records pass needs_pass=False: their route sentence has no pass word, and the tail's pass is its own sentence
    (passes_on_either_route)."""
    return any("unmeasured" in s and "record" in s and "quot" in s and "sentence" in s and NEGATED_ROUTE.search(s) is None
               and (not needs_pass or re.search(r"\bpass", s) is not None)
               for s in sentences_of(text))


def sentences_with(text, phrase):
    """The sentences of `text` that hold `phrase` (lowercase), joined for a failure's detail, so it shows the wording."""
    return " | ".join(s.strip() for s in sentences_of(text) if phrase in s)[:300]


def passes_on_either_route(text):
    """The sentences of `text` that say a challenge on either route passes: the words `either route` and the whole word
    pass. The caller reads them, so a missing sentence and a negated one fail by name."""
    return [s for s in sentences_of(text) if "either route" in s and re.search(r"\bpass", s) is not None]


def says_unmeasured_is_no_new_fact(text):
    """True when a sentence of `text` refuses the word unmeasured as a new fact."""
    return any("unmeasured" in s and NEGATED_NEW_FACT.search(s) is not None for s in sentences_of(text))


def excludes_a_re_ask_without_the_record(text):
    """True when a sentence of `text` says a re-ask that does not name the record is not a challenge. The negation must
    stand on the record clause, and `challenge` must follow it with a negation right before it, so "does not name the
    record is a challenge" is no pass."""
    for s in sentences_of(text):
        record = NEGATED_RECORD.search(s)
        if re.search(r"\bre-?ask", s) is not None and record is not None and NEGATED_CHALLENGE.search(s, record.end()):
            return True
    return False


def new_shape_checks(text, subject):
    """Checks that `text` passes a challenge that names the record and brings a new fact, with the other parts optional,
    refuses a re-ask that takes neither route, and no longer says a new fact alone is not a pass. `subject` opens each
    check's name, so a failure names where the text came from. A failure's detail is one line."""
    flat = " ".join(text.split())[:300]
    sentences = sentences_of(text)
    check("%s: a challenge that names the record and brings a new fact passes" % subject,
          any("challenge" in s and "pass" in s and "record" in s and "new fact" in s for s in sentences), flat)
    check("%s: the outcome and the fix are optional, never required" % subject,
          any(re.search(r"\b(optional|never required|not required)\b", s) and ("outcome" in s or "fix" in s)
              for s in sentences), flat)
    check("%s: a re-ask that takes neither route is refused" % subject, refuses_a_bare_re_ask(text),
          sentences_with(text, "re-ask"))
    check("%s: no longer says a re-ask that brings no new fact is refused" % subject,
          "brings no new fact" not in text.lower(), sentences_with(text, "brings no new fact"))
    check("%s: the item no longer says a new fact alone is not a pass" % subject,
          "a new fact alone is not a pass" not in text.lower(), flat)


def item8_of(prompt):
    return item_text(prompt, 8)


def case_past_ruling_item_passes_a_challenge_with_a_new_fact():
    item = load_file_module(HOOK, "call_judge_under_test").PAST_RULING_ITEM
    new_shape_checks(item, "challenge pass: the item")


def case_past_ruling_challenge_question_gets_item_8():
    import question_form  # the one form check (hooks/question_form.py)
    box = good_box(goal=CHAL_GOAL, problem=CHAL_PROBLEM, based=CHAL_BASED, options=CHAL_OPTIONS)
    check("challenge question fixture: the box passes chat_hit, so the model judges it",
          question_form.chat_hit(box) == ("", ""), question_form.chat_hit(box))
    r = run_hook(question_input(box=box, cwd=DECISIONS_REPO), answer=ALLOW)
    check("challenge question: one model call, and the box reaches the owner with no refusal",
          len(r.calls) == 1 and r.code == 0 and r.out == "", detail(r))
    item8 = item8_of(r.calls[0]["prompt"] if r.calls else "")
    check("challenge question: the prompt holds item 8", item8 != "", detail(r))
    new_shape_checks(item8, "challenge question: item 8")


def case_past_ruling_challenge_page_item_gets_item_8():
    import question_form  # the one form check (hooks/question_form.py)
    item = good_page_item(title=CHAL_PAGE_TITLE, context=CHAL_CONTEXT)
    got = question_form.item_hit("set", {"collection": PAGE_ITEMS, "doc_id": "chal1", "data": item})
    check("challenge page fixture: the item passes item_hit, so the model judges it", got == ("", ""), got)
    r = run_hook(page_input("set", item, doc_id="chal1", cwd=DECISIONS_REPO), answer=ALLOW)
    check("challenge page item: one model call", len(r.calls) == 1, detail(r))
    item8 = item8_of(r.calls[0]["prompt"] if r.calls else "")
    check("challenge page item: the prompt holds item 8", item8 != "", detail(r))
    new_shape_checks(item8, "challenge page item: item 8")


NEW_FACT_PROBLEM = ("Problem (risk): the record decisions/%s says 'keep the apps' access to claude-settings as is'; the "
                    "monthly audit counts 14 apps with access, where the ruling was written on 9, so the ruling needs your word"
                    % APPS_SLUG)
NEW_FACT_BASED = ("Based on (measured): the monthly audit counts 14 apps with access, 5 more than the 9 the ruling was "
                  "written on",)


def case_new_fact_alone_question_gets_item_8():
    # A challenge that names the record and brings a new fact, with no outcome and no fix: one model call and no refusal
    # (a green control). The item 8 the model reads is the one the new-fact checks read.
    import question_form  # the one form check (hooks/question_form.py)
    box = good_box(goal=CHAL_GOAL, problem=NEW_FACT_PROBLEM, based=NEW_FACT_BASED, options=CHAL_OPTIONS)
    check("new fact alone fixture: the box passes chat_hit, so the model judges it",
          question_form.chat_hit(box) == ("", ""), question_form.chat_hit(box))
    r = run_hook(question_input(box=box, cwd=DECISIONS_REPO), answer=ALLOW)
    check("new fact alone question: one model call, and it reaches the owner with no refusal",
          len(r.calls) == 1 and r.code == 0 and r.out == "", detail(r))
    item8 = item8_of(r.calls[0]["prompt"] if r.calls else "")
    check("new fact alone question: the prompt holds item 8", item8 != "", detail(r))
    new_shape_checks(item8, "new fact alone question: item 8")
    check("new fact alone question: item 8 names the unmeasured route with the record and the quoted sentence",
          names_unmeasured_route(item8), " ".join(item8.split())[:300])


def case_new_fact_is_one_the_ruling_left_unweighed():
    # A new fact is a measure or an observed harm the ruling left unweighed. A challenge that names the record and says the
    # claim is unmeasured is its own route, and quotes the ruling's sentence that states no measure. A restatement of the
    # ruling's own claim is not a new fact. The check reads the item's sentences; a failure prints the sentences with the word.
    item = load_file_module(HOOK, "call_judge_under_test").PAST_RULING_ITEM
    flat = " ".join(item.split())
    unmeasured = " | ".join(s.strip() for s in sentences_of(item) if "unmeasured" in s)
    check("unweighed: the item says a measure is a new fact only when the ruling left it unweighed",
          re.search(r"\bmeasure\b(?:(?!\bclaim)[^.])*\bunweighed\b", flat.lower()) is not None, flat[:300])
    check("unweighed: the item names the unmeasured route with the record and the quoted sentence that states no measure",
          names_unmeasured_route(item), unmeasured[:300])
    check("unweighed: the item no longer says the word unmeasured is not a new fact",
          not says_unmeasured_is_no_new_fact(item), unmeasured[:300])
    check("unweighed: the item says a restatement of the ruling's own claim is not a new fact",
          restates_is_no_new_fact(item), flat[:300])


def case_past_ruling_item_refuses_a_bare_re_ask():
    # A re-ask that takes neither route is refused by a sentence of the item. The item no longer says "brings no new fact",
    # and no longer refuses by "such a challenge", which named a four-part bar.
    item = load_file_module(HOOK, "call_judge_under_test").PAST_RULING_ITEM
    flat = " ".join(item.split())[:300]
    check("bare re-ask: the item refuses a re-ask that takes neither route", refuses_a_bare_re_ask(item),
          sentences_with(item, "re-ask"))
    check("bare re-ask: the item no longer says a re-ask that brings no new fact is refused",
          "brings no new fact" not in item.lower(), sentences_with(item, "brings no new fact"))
    check("bare re-ask: the item no longer refuses a re-ask as not such a challenge",
          "such a challenge" not in item.lower(), flat)


def case_question_form_record_refuses_a_bare_re_ask_on_neither_route():
    # The question-form record states the item 8 wording: a re-ask that takes neither route is refused, and no sentence
    # says a re-ask that brings no new fact is refused. The record is read whole; a missing record fails by name.
    path = os.path.join(REPO, "docs", "decisions", "question-form.md")
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        text = ""
    check("question-form record: is found", text.strip() != "", path)
    if text.strip():
        flat = " ".join(text.split())
        check("question-form record: a re-ask that takes neither route is refused, the item 8 wording",
              refuses_a_bare_re_ask(text), sentences_with(text, "re-ask"))
        check("question-form record: no longer says a re-ask that brings no new fact is refused",
              "a re-ask that brings no new fact is refused" not in flat.lower(), sentences_with(text, "brings no new fact"))


def case_challenge_how_says_either_route_passes():
    # The how-to-challenge tail says a challenge on either route passes this check, in a sentence no negation reaches.
    # The sentence is the pass, so the route sentence above it carries no pass word of its own (needs_pass=False).
    tail = load_file_module(HOOK, "call_judge_under_test").CHALLENGE_HOW
    passing = passes_on_either_route(tail)
    check("challenge how: a sentence says a challenge on either route passes this check", passing != [], tail[:300])
    check("challenge how: the pass sentence is not negated",
          passing != [] and all(NEGATED_ROUTE.search(s) is None for s in passing), " | ".join(passing)[:300])


def case_past_ruling_item_names_the_unmeasured_route():
    # (a) Item 8 names the unmeasured route with the record and the quoted sentence of the ruling that states no measure
    # (rule outcomes-stale-decision-protocol: "name the record and the sentence").
    item = load_file_module(HOOK, "call_judge_under_test").PAST_RULING_ITEM
    check("unmeasured route: item 8 names it with the record and the quoted sentence that states no measure",
          names_unmeasured_route(item), " ".join(item.split())[:300])


def case_negation_governs_the_claim_it_negates():
    # Probes on literal sentences, never product text. Each inverted sentence must be refused and each true one accepted,
    # one check per sentence, so a red names the sentence. The last true unmeasured sentence says "states no measure", so the
    # unmeasured route's negation rule is shown not to refuse that phrase.
    probes = (
        ("re-ask", excludes_a_re_ask_without_the_record, "A re-ask that does not name the record is a challenge.", False),
        ("re-ask", excludes_a_re_ask_without_the_record, "A re-ask that names no record is a challenge.", False),
        ("re-ask", excludes_a_re_ask_without_the_record, "A re-ask that names the record is not a challenge.", False),
        ("re-ask", excludes_a_re_ask_without_the_record, "A re-ask that does not name the record is not a challenge.", True),
        ("re-ask", excludes_a_re_ask_without_the_record, "A re-ask that names no record is not a challenge.", True),
        ("restatement", restates_is_no_new_fact,
         "A restatement of the ruling's own claim is a new fact, not a measure.", False),
        ("restatement", restates_is_no_new_fact, "A restatement of the ruling's own claim is a new fact.", False),
        ("restatement", restates_is_no_new_fact, "A restatement of the ruling's own claim is not a new fact.", True),
        ("unmeasured", names_unmeasured_route,
         "A challenge that says the claim is unmeasured does not need the record or the quoted sentence.", False),
        ("unmeasured", names_unmeasured_route,
         "A challenge that says the claim is unmeasured passes without the record and the quoted sentence.", False),
        ("unmeasured", names_unmeasured_route,
         "A challenge that says the claim is unmeasured, with the record and the quoted sentence, is no pass.", False),
        ("unmeasured", names_unmeasured_route,
         "A challenge that names the record, says the claim is unmeasured, and quotes the ruling's sentence that states "
         "no measure, passes.", True),
        ("unmeasured", names_unmeasured_route,
         "A challenge that names the record, says the claim is unmeasured, and quotes the ruling's sentence that states "
         "no measure, is refused too.", False),
        ("unmeasured", names_unmeasured_route,
         "A challenge that names the record, says the claim is unmeasured, and quotes the ruling's sentence that states "
         "no measure, fails.", False),
        ("refusal", refuses_a_bare_re_ask, "Refuse a re-ask that takes neither route.", True),
        ("refusal", refuses_a_bare_re_ask, "Do not refuse a re-ask that takes neither route.", False),
        ("refusal", refuses_a_bare_re_ask, "Refuse a re-ask that brings no new fact.", False),
    )
    for kind, helper, sentence, want in probes:
        got = helper(sentence)
        check("probe %s: %r is %s" % (kind, sentence, "accepted" if want else "refused"), got == want,
              "the helper returned %s" % got)


def line_with(path, anchor):
    """The first line of the file at `path` that holds `anchor`, or "" when no line does or the file cannot be read."""
    try:
        with open(path, encoding="utf-8") as handle:
            return next((line for line in handle if anchor in line), "")
    except OSError:
        return ""


def stale_protocol_reason():
    """The mechanism reason of rule outcomes-stale-decision-protocol (line 19 of lint/rule_mechanisms.json), or "" when the
    entry or the file cannot be read."""
    try:
        with open(os.path.join(REPO, "lint", "rule_mechanisms.json"), encoding="utf-8") as handle:
            return json.load(handle)["rules"]["outcomes-stale-decision-protocol"]["mechanism"]["reason"]
    except (OSError, ValueError, KeyError, TypeError):
        return ""


def case_records_name_the_unmeasured_route_with_the_quote():
    # (d) The two decision records and the rule-mechanism entry that name the ways to challenge carry the unmeasured route,
    # with the record and the quoted sentence, as the code does. Each text is found first, so a missing text fails by its
    # name and is never read as an empty pass.
    decisions = os.path.join(REPO, "docs", "decisions")
    records = (
        ("docs/decisions/question-form.md",
         line_with(os.path.join(decisions, "question-form.md"), "`PAST_RULING_ITEM` in `hooks/call_judge.py`")),
        ("docs/decisions/guard-remedy-not-to-owner.md",
         line_with(os.path.join(decisions, "guard-remedy-not-to-owner.md"), "To challenge the ruling")),
        ("lint/rule_mechanisms.json, outcomes-stale-decision-protocol", stale_protocol_reason()),
    )
    for label, text in records:
        check("records: %s is found" % label, text.strip() != "", "no line or entry holds the anchor")
        if text.strip():
            check("records: %s names the unmeasured route with the record and the quoted sentence" % label,
                  names_unmeasured_route(text, needs_pass=False), " ".join(text.split())[:300])


def case_past_ruling_item_never_says_withdraw():
    item = load_file_module(HOOK, "call_judge_under_test").PAST_RULING_ITEM
    hits = [p for p in WITHDRAW_PHRASES if p in item.lower()]
    check("withdraw: the item never tells the session to withdraw the question", not hits, hits)


def case_past_ruling_tail_names_the_record_and_the_new_fact():
    # The how-to-challenge tail of a past-ruling denial: name the record, bring the new fact, the other parts optional, and
    # never withdraw. It also carries both exclusions: a restatement of the ruling's claim is no new fact, and a re-ask that
    # does not name the record is no challenge. Read from call_judge.CHALLENGE_HOW, never copied here.
    tail = load_file_module(HOOK, "call_judge_under_test").CHALLENGE_HOW
    lower = tail.lower()
    check("tail: names the record and brings the new fact", "record" in lower and "new fact" in lower, tail[:300])
    check("tail: the other parts are optional", re.search(r"\b(optional|never required|not required)\b", lower) is not None,
          tail[:300])
    hits = [p for p in WITHDRAW_PHRASES if p in lower]
    check("tail: never tells the session to withdraw the question", not hits, hits)
    check("tail: a restatement of the ruling's own claim is not a new fact", restates_is_no_new_fact(tail), tail[:300])
    check("tail: a re-ask that does not name the record is not a challenge", excludes_a_re_ask_without_the_record(tail),
          tail[:300])


def case_challenge_how_names_the_unmeasured_route():
    # (c) The how-to-challenge tail names the unmeasured route on its own: the record, the quoted sentence of the ruling that
    # states no measure, and the claim is unmeasured. The denial the session reads carries this tail (the next case).
    tail = load_file_module(HOOK, "call_judge_under_test").CHALLENGE_HOW
    check("challenge how: the tail names the unmeasured route with the record and the quoted sentence",
          names_unmeasured_route(tail, needs_pass=False), " ".join(tail.split())[:300])


def case_bare_re_ask_is_refused_beside_a_passing_challenge():
    # R39 item 4: the same question with no new fact is refused. Its denial tells the session how to challenge, and never
    # to withdraw. A challenge that brings a new fact, asked beside it, reaches the owner with no denial.
    bare_box = good_box(goal=APPS_GOAL, problem=APPS_PROBLEM, based=APPS_BASED, options=APPS_OPTIONS)
    refuse = json.dumps({"ok": False, "reason": "decisions/%s: already decided by the keep-the-apps ruling." % APPS_SLUG})
    r = run_hook(question_input(box=bare_box, cwd=DECISIONS_REPO), answer=refuse)
    reason = r.reason().lower()
    check("re-ask with no new fact: the mocked refusal reaches the denial under the past-ruling rule",
          (r.deny() or {}).get("permissionDecision") == "deny" and reason.startswith("past-ruling"), detail(r))
    check("re-ask with no new fact: the denial tells the session how to challenge", "challenge" in reason, reason[:300])
    check("re-ask with no new fact: the denial names the record and a new fact", "record" in reason and "new fact" in reason,
          reason[:300])
    check("re-ask with no new fact: the denial says the other parts are optional",
          re.search(r"\b(optional|never required|not required)\b", reason) is not None, reason[:300])
    hits = [p for p in WITHDRAW_PHRASES if p in reason]
    check("re-ask with no new fact: the denial never tells the session to withdraw the question", not hits, hits)
    check("re-ask with no new fact: the denial names the unmeasured route with the record and the quoted sentence",
          names_unmeasured_route(reason, needs_pass=False), reason[:300])
    challenge = run_hook(question_input(box=good_box(goal=CHAL_GOAL, problem=CHAL_PROBLEM, based=CHAL_BASED,
                                                     options=CHAL_OPTIONS), cwd=DECISIONS_REPO), answer=ALLOW)
    check("challenge beside it: judged once, reaches the owner with no denial",
          len(challenge.calls) == 1 and challenge.code == 0 and challenge.out == "", detail(challenge))


def case_past_ruling_item_says_a_challenge_never_grants():
    # The item's own sentence that a challenge only asks. Deleting that sentence turns this check red: the behavioural
    # case below stays green on such a mutant, because the hook's grant readers never run on a question either way.
    item = load_file_module(HOOK, "call_judge_under_test").PAST_RULING_ITEM
    says = any("challenge" in s and "grant" in s and re.search(r"\b(never|not)\b", s) is not None
               for s in sentences_of(item))
    check("grant sentence: the item says a challenge never grants anything", says, " ".join(item.split())[:300])


def case_challenge_question_writes_no_grant():
    import question_form  # the one form check (hooks/question_form.py)
    box = good_box(goal=CHAL_GOAL, problem=CHAL_PROBLEM, based=CHAL_BASED, options=CHAL_GRANT_OPTIONS)
    check("grant text fixture: the box passes chat_hit, so the model judges it",
          question_form.chat_hit(box) == ("", ""), question_form.chat_hit(box))
    r = run_hook(question_input(box=box, cwd=DECISIONS_REPO), answer=ALLOW)
    check("grant text: the challenge is judged once and reaches the owner with no refusal",
          len(r.calls) == 1 and r.code == 0 and r.out == "", detail(r))
    grants = os.path.join(r.base, "config", "state", "override")
    check("grant text: no override is written", not os.path.isdir(grants) or not os.listdir(grants), detail(r))
    check("grant text: guard.log holds no override line", "\toverride\t" not in r.log, r.log[-200:])


def case_challenge_text_never_lifts_a_refusal():
    import question_form  # the one form check (hooks/question_form.py)
    box = good_box(goal=CHAL_GOAL, problem=CHAL_PROBLEM, based=CHAL_BASED, options=CHAL_GRANT_OPTIONS)
    bare = json.dumps({"ok": False, "reason": "decisions/%s: already decided by the keep-the-apps ruling." % APPS_SLUG})
    r = run_hook(question_input(box=box, cwd=DECISIONS_REPO), answer=bare)
    check("grant text: a refusal stands when the challenge carries grant words",
          (r.deny() or {}).get("permissionDecision") == "deny", detail(r))
    check("grant text: no lift line for the refusal, and no override line at all",
          not lifted_log(r, question_form.PAST_RULING_RULE) and "\toverride\t" not in r.log, r.log[-200:])


def case_item_has_no_new_fact_alone_route():
    # (b) The unmeasured route is its own route. The item must not say a challenge passes on a new fact alone, because
    # "alone" makes a new fact the only ground of a pass, and the unmeasured route passes with none. Green controls beside
    # it: the new-fact route still passes with the record named (new_shape_checks), and the item no longer requires four parts.
    item = load_file_module(HOOK, "call_judge_under_test").PAST_RULING_ITEM
    flat = " ".join(item.split())[:300]
    check("no new-fact-alone route: the item does not say a challenge passes on a new fact alone",
          not says_new_fact_alone_passes(item), flat)
    new_shape_checks(item, "no new-fact-alone route: the item")
    check("no new-fact-alone route: the item no longer requires a challenge with four parts",
          not any("only" in s and "four" in s for s in sentences_of(item)), flat)


# A plain-words explain question: its item 5 refusal names a record the repo holds, and it keeps the question judge's
# rule id. Only a past-ruling refusal gets the challenge tail.
EXPLAIN_SLUG = "question-form"
EXPLAIN_RULING = "Owner, 2026-10-20: every question names its ids and explains each one in plain words."
EXPLAIN_REPO = make_repo("explain", decisions={EXPLAIN_SLUG: EXPLAIN_RULING})
EXPLAIN_REASON = "Item 5: explain decisions/%s in plain words." % EXPLAIN_SLUG


def case_plain_words_explain_keeps_its_rule_id():
    import question_form  # the one form check (hooks/question_form.py)
    question_rule = load_file_module(HOOK, "call_judge_under_test").QUESTION_RULE
    box = good_box(goal=APPS_GOAL, problem=APPS_PROBLEM, based=APPS_BASED, options=APPS_OPTIONS)
    check("explain fixture: the box passes chat_hit, so the model judges it",
          question_form.chat_hit(box) == ("", ""), question_form.chat_hit(box))
    r = run_hook(question_input(box=box, cwd=EXPLAIN_REPO), answer=json.dumps({"ok": False, "reason": EXPLAIN_REASON}))
    reason = r.reason()
    check("explain: the denial keeps the question-judge rule id, not the past-ruling one",
          (r.deny() or {}).get("permissionDecision") == "deny" and reason.startswith(question_rule + ":"), detail(r))
    check("explain: the guard.log deny line names the question-judge rule",
          ("\tdeny\t%s\t" % question_rule) in r.log, r.log[-200:])
    check("explain: the denial carries no past-ruling challenge tail", "challenge" not in reason.lower(), reason[:300])


# ------------------------------------------------------------------ a denial keeps its id, its date and the tail (R39)
#
# A refusal names the ruling's id and date, then may say not to re-ask it. The denial keeps both, and the how-to-challenge
# tail follows. The tail is read from call_judge.CHALLENGE_HOW, never copied here.
APPS_DATE = "2026-10-28"  # the date APPS_RULING carries


def case_past_ruling_denial_keeps_its_id_and_date():
    import question_form  # the one form check (hooks/question_form.py)
    tail = load_file_module(HOOK, "call_judge_under_test").CHALLENGE_HOW
    box = good_box(goal=APPS_GOAL, problem=APPS_PROBLEM, based=APPS_BASED, options=APPS_OPTIONS)
    refuse = json.dumps({"ok": False, "reason": "decisions/%s (%s): already decided; do not re-ask it."
                         % (APPS_SLUG, APPS_DATE)})
    r = run_hook(question_input(box=box, cwd=DECISIONS_REPO), answer=refuse)
    reason = r.reason()
    check("denial with a give-up sentence: the rule stays past-ruling",
          (r.deny() or {}).get("permissionDecision") == "deny" and reason.startswith(question_form.PAST_RULING_RULE),
          detail(r))
    check("denial with a give-up sentence: the denial keeps the ruling's id", "decisions/%s" % APPS_SLUG in reason,
          detail(r))
    check("denial with a give-up sentence: the denial keeps the ruling's date", APPS_DATE in reason, detail(r))
    check("denial with a give-up sentence: the how-to-challenge tail follows", tail != "" and tail in reason, detail(r))


def case_past_ruling_denial_plain_reason_keeps_its_id_and_date():
    # Green control: a refusal with no give-up words keeps its id and date on the current code. The loss in the case
    # above comes from the give-up sentence alone.
    box = good_box(goal=APPS_GOAL, problem=APPS_PROBLEM, based=APPS_BASED, options=APPS_OPTIONS)
    refuse = json.dumps({"ok": False, "reason": "decisions/%s (%s): already decided by the keep-the-apps ruling."
                         % (APPS_SLUG, APPS_DATE)})
    r = run_hook(question_input(box=box, cwd=DECISIONS_REPO), answer=refuse)
    reason = r.reason()
    check("denial without a give-up sentence: keeps the ruling's id and date",
          "decisions/%s" % APPS_SLUG in reason and APPS_DATE in reason, detail(r))


# ------------------------------------------------------------------ a replayed missed re-ask (R39)
#
# Replay of a missed re-ask: a question asked whether the shared-tree guard should read git inside Python strings, and a
# page item had already ruled to keep that gap (page item 366 option b, Nov 7). The ruling is held as a decision record.
# The re-ask carries no challenge and no Based on (ruling) line, and the mocked model refuses it.
REPLAY_SLUG = "shared-tree-guard-git-strings"
REPLAY_DATE = "2026-11-07"
REPLAY_RULING = ("Owner, %s, page item 366 option b: keep the gap. The shared-tree guard does not read git inside a "
                 "Python string. Marker gap-5e21." % REPLAY_DATE)
REPLAY_REPO = make_repo("shared-tree-gap", decisions={REPLAY_SLUG: REPLAY_RULING})
REPLAY_TITLE = "Widen the shared-tree guard to read git inside Python strings?"
REPLAY_CONTEXT = "\n".join((
    "Goal: decide whether the shared-tree guard reads git inside Python strings",
    "Problem (risk): a git call inside a Python string gets past the guard, so the guard's reach needs your word",
    "Based on (read): the guard reads git calls in shell lines only",
    DEPARTS_LINE))
REPLAY_CHALLENGE_CONTEXT = "\n".join((
    "Goal: decide whether the shared-tree guard reads git inside Python strings, given the ruling to keep the gap",
    "Problem (risk): the record decisions/%s says \"keep the gap\" for git inside a Python string, and the ruling needs "
    "your word" % REPLAY_SLUG,
    "Based on (measured): the gap was re-asked 4 times in 5 days, and the guard missed 3 of 30 sampled git calls held "
    "in Python strings",
    DEPARTS_LINE))
REPLAY_OPTIONS = [
    {"key": "a", "label": "Widen the guard", "gain": "Git inside a Python string is checked.",
     "lose": "The guard grows a parser."},
    {"key": "b", "label": "Keep the gap", "gain": "The guard stays small.",
     "lose": "Git inside a Python string is not checked."}]


def case_past_ruling_replay_item_532():
    import question_form  # the one form check (hooks/question_form.py)
    item = good_page_item(title=REPLAY_TITLE, context=REPLAY_CONTEXT, options=REPLAY_OPTIONS)
    got = question_form.item_hit("set", {"collection": PAGE_ITEMS, "doc_id": "c532", "data": item})
    check("replay 532 fixture: the item passes item_hit, so the model judges it", got == ("", ""), got)
    refuse = json.dumps({"ok": False, "reason": "decisions/%s (%s): already decided, keep the gap; do not re-ask it."
                         % (REPLAY_SLUG, REPLAY_DATE)})
    r = run_hook(page_input("set", item, doc_id="c532", cwd=REPLAY_REPO), answer=refuse)
    prompt = r.calls[0]["prompt"] if r.calls else ""
    check("replay 532: the ruling reaches the candidate list, in one model call",
          len(r.calls) == 1 and REPLAY_SLUG in without_call(prompt, item) and REPLAY_RULING in without_call(prompt, item),
          detail(r))
    check("replay 532: item 8 refuses a re-ask that takes neither route", refuses_a_bare_re_ask(item8_of(prompt)),
          sentences_with(item8_of(prompt), "re-ask"))
    reason = r.reason()
    check("replay 532: the write is denied under the past-ruling rule",
          (r.deny() or {}).get("permissionDecision") == "deny" and reason.startswith(question_form.PAST_RULING_RULE),
          detail(r))
    check("replay 532: the denial names the ruling's id", "decisions/%s" % REPLAY_SLUG in reason, detail(r))
    check("replay 532: the denial names the ruling's date", REPLAY_DATE in reason, detail(r))
    check("replay 532: the denial carries the how-to-challenge tail",
          load_file_module(HOOK, "call_judge_under_test").CHALLENGE_HOW in reason, detail(r))
    check("replay 532: the guard.log deny line names the past-ruling rule",
          "\tdeny\t%s\t" % question_form.PAST_RULING_RULE in r.log, r.log[-200:])


def case_past_ruling_replay_item_532_challenge_passes():
    # Green control, beside the replay: the same question with the record named and a new fact, and no outcome and no fix.
    # One model call and no refusal. The item 8 the model reads passes a challenge with the record and a new fact.
    import question_form  # the one form check (hooks/question_form.py)
    challenge = good_page_item(title=REPLAY_TITLE, context=REPLAY_CHALLENGE_CONTEXT, options=REPLAY_OPTIONS)
    got = question_form.item_hit("set", {"collection": PAGE_ITEMS, "doc_id": "c532c", "data": challenge})
    check("replay 532 challenge fixture: the item passes item_hit, so the model judges it", got == ("", ""), got)
    r = run_hook(page_input("set", challenge, doc_id="c532c", cwd=REPLAY_REPO), answer=ALLOW)
    prompt = r.calls[0]["prompt"] if r.calls else ""
    check("replay 532 challenge: one model call, and it reaches the owner with no refusal",
          len(r.calls) == 1 and r.code == 0 and r.out == "", detail(r))
    check("replay 532 challenge: the ruling reaches the candidate list",
          REPLAY_SLUG in without_call(prompt, challenge) and REPLAY_RULING in without_call(prompt, challenge), detail(r))
    item8 = item8_of(prompt)
    new_shape_checks(item8, "replay 532 challenge: item 8")
    check("replay 532 challenge: item 8 names the unmeasured route with the record and the quoted sentence",
          names_unmeasured_route(item8), " ".join(item8.split())[:300])


# ------------------------------------------------------------------ the Item N opener of a refusal (R39)
#
# A refusal that opens on `Item N:` names the form item it misses, and keeps its own rule id. A reason that opens on
# item 8 names a listed record, so it stays a past-ruling refusal with the tail.


def case_item_8_reason_stays_past_ruling():
    # Green control: a reason that opens on item 8 and names a listed record is still a past-ruling refusal, with the tail.
    import question_form  # the one form check (hooks/question_form.py)
    tail = load_file_module(HOOK, "call_judge_under_test").CHALLENGE_HOW
    box = good_box(goal=APPS_GOAL, problem=APPS_PROBLEM, based=APPS_BASED, options=APPS_OPTIONS)
    refuse = json.dumps({"ok": False, "reason": "Item 8: decisions/%s (%s): already decided." % (APPS_SLUG, APPS_DATE)})
    r = run_hook(question_input(box=box, cwd=DECISIONS_REPO), answer=refuse)
    reason = r.reason()
    check("item 8 reason: the denial stays under the past-ruling rule",
          (r.deny() or {}).get("permissionDecision") == "deny" and reason.startswith(question_form.PAST_RULING_RULE),
          detail(r))
    check("item 8 reason: the past-ruling tail follows", tail != "" and tail in reason, detail(r))


def case_item_n_reasons_keep_their_own_rule_id():
    # An Item 5 reason, and an `Items 3 and 5:` reason, name a shown record and are form items. Each keeps the
    # question-judge rule id and carries no past-ruling tail. The `Items 3 and 5:` reason is the one a form-item
    # reading that matches only `Item N` misses.
    question_rule = load_file_module(HOOK, "call_judge_under_test").QUESTION_RULE
    tail = load_file_module(HOOK, "call_judge_under_test").CHALLENGE_HOW
    box = good_box(goal=APPS_GOAL, problem=APPS_PROBLEM, based=APPS_BASED, options=APPS_OPTIONS)
    for label, text in (("Item 5", EXPLAIN_REASON),
                        ("Items 3 and 5", "Items 3 and 5: explain decisions/%s in plain words." % EXPLAIN_SLUG)):
        r = run_hook(question_input(box=box, cwd=EXPLAIN_REPO), answer=json.dumps({"ok": False, "reason": text}))
        reason = r.reason()
        check("%s reason: the denial keeps the question-judge rule id" % label,
              (r.deny() or {}).get("permissionDecision") == "deny" and reason.startswith(question_rule + ":"), detail(r))
        check("%s reason: the denial carries no past-ruling tail" % label, tail != "" and tail not in reason, detail(r))


def case_reply_spec_asks_an_item_n_opening():
    # The reply line of the judge items, which the question and the page prompts both carry, asks a refusal to open
    # with `Item N:`. The hook reads that opener to tell a form item from a past ruling.
    items = load_file_module(HOOK, "call_judge_under_test").JUDGE_ITEMS
    spec = items[items.find("Reply JSON only"):] if "Reply JSON only" in items else ""
    check("reply spec: the reason opens with 'Item N:'", "Item N:" in spec, " ".join(spec.split())[:300])


def called_names(path):
    """The names of each call in the Python file at `path`, read with the ast parser, so a name in a string or a
    comment is no call."""
    import ast
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), path)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)
    return names


def case_judges_call_no_grant_reader():
    for rel in JUDGE_SOURCES:
        hit = sorted(called_names(os.path.join(REPO, *rel.split("/"))) & set(GRANT_READERS))
        check("no grant: %s calls no grant reader" % rel, not hit, hit)


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
                 case_past_ruling_item_passes_a_challenge_with_a_new_fact, case_past_ruling_challenge_question_gets_item_8,
                 case_past_ruling_challenge_page_item_gets_item_8, case_past_ruling_item_refuses_a_bare_re_ask,
                 case_past_ruling_item_never_says_withdraw, case_bare_re_ask_is_refused_beside_a_passing_challenge,
                 case_past_ruling_item_says_a_challenge_never_grants, case_challenge_question_writes_no_grant,
                 case_challenge_text_never_lifts_a_refusal, case_item_has_no_new_fact_alone_route,
                 case_new_fact_is_one_the_ruling_left_unweighed, case_past_ruling_item_names_the_unmeasured_route,
                 case_negation_governs_the_claim_it_negates, case_challenge_how_names_the_unmeasured_route,
                 case_records_name_the_unmeasured_route_with_the_quote,
                 case_question_form_record_refuses_a_bare_re_ask_on_neither_route, case_challenge_how_says_either_route_passes,
                 case_plain_words_explain_keeps_its_rule_id, case_judges_call_no_grant_reader,
                 case_past_ruling_denial_keeps_its_id_and_date, case_past_ruling_denial_plain_reason_keeps_its_id_and_date,
                 case_past_ruling_replay_item_532, case_past_ruling_replay_item_532_challenge_passes,
                 case_item_8_reason_stays_past_ruling, case_item_n_reasons_keep_their_own_rule_id,
                 case_reply_spec_asks_an_item_n_opening,
                 case_past_ruling_tail_names_the_record_and_the_new_fact, case_new_fact_alone_question_gets_item_8):
        try:
            case()
        except Exception as exc:
            check(case.__name__, False, "raised %s: %s" % (type(exc).__name__, exc))
    print("FAIL: %d failed" % len(FAILED) if FAILED else "all checks passed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
