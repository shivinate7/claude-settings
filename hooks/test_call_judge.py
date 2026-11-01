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
- Any model error, or malformed input, fails open: no deny, exit 0, one stderr line.
- AskUserQuestion: a box that fails the code check (hooks/question_form.py chat_hit) is refused before
  any model call, with the rule chat_hit names. The model sees only a box that passes it, and judges only
  what code cannot (the cases are in hooks/test_question_form.py, which reuses run_hook below).
- settings.json: one command hook on `Agent|AskUserQuestion` runs call_judge.py with a timeout above
  the longest model call (60 s). No `prompt` or `agent` hook is left on either tool.
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


subprocess.run = _fake_run
with open(os.path.join(os.environ["CJ_LOADED_DIR"], "loaded"), "w", encoding="utf-8") as f:
    f.write("1")
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
        path = os.path.join(base, "calls.jsonl")
        self.calls = []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.calls = [json.loads(line) for line in f if line.strip()]
        log = os.path.join(base, "config", "guard.log")
        self.log = open(log, encoding="utf-8").read() if os.path.exists(log) else ""

    def deny(self):
        if not self.out.strip():
            return None
        return json.loads(self.out)["hookSpecificOutput"]

    def reason(self):
        return (self.deny() or {}).get("permissionDecisionReason", "")


def detail(r):
    return "code=%s out=%r err=%r calls=%d loaded=%s log=%r" % (
        r.code, r.out[:200], r.err[-200:], len(r.calls), r.loaded, r.log[-200:])


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


def question_input(session=SID_A, agent=None, box=None):
    payload = {"session_id": session, "tool_name": "AskUserQuestion", "tool_input": box or good_box()}
    if agent:
        payload["agent_id"] = agent
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
    asks = prompt.replace(json.dumps(good_box(), ensure_ascii=False), "")
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


def case_fail_open():
    for label, inp, kwargs in (
        ("a model failure on a spawn", spawn_input("builder", model="sonnet"), {"model_fail": True}),
        ("a model failure on a question", question_input(), {"model_fail": True}),
        ("an odd answer", spawn_input("builder", model="sonnet"), {"answer": '{"ok": "maybe"}'}),
        ("unreadable stdin", "not json", {}),
        ("an empty payload", "{}", {}),
    ):
        r = run_hook(inp, **kwargs)
        errs = [line for line in r.err.splitlines() if line.strip()]
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
            and re.search(r"\b(Agent|AskUserQuestion)\b", e.get("matcher") or "")]
    check("settings: no prompt or agent hook is left on Agent or AskUserQuestion", left == [], left)
    rows = [(e, h) for e in pre for h in e["hooks"] if "call_judge.py" in h.get("command", "")]
    check("settings: one command hook runs call_judge.py", len(rows) == 1 and rows[0][1].get("type") == "command", rows)
    if len(rows) != 1:
        return
    entry, hook = rows[0]
    matcher = set((entry.get("matcher") or "").split("|"))
    check("settings: its matcher is Agent and AskUserQuestion", matcher == {"Agent", "AskUserQuestion"}, entry.get("matcher"))
    check("settings: its timeout exceeds the longest model call (60 s)", hook.get("timeout", 0) > 60, hook)
    empty = os.path.join(ROOT, "empty-config")
    os.makedirs(empty, exist_ok=True)
    proc = subprocess.run(["sh", "-c", hook["command"]], input="{}", capture_output=True, text=True,
                          env=dict(os.environ, CLAUDE_CONFIG_DIR=empty), timeout=60)
    errs = [line for line in proc.stderr.splitlines() if line.strip()]
    check("settings: with the script missing the launcher exits 0 with one stderr line, never a block",
          proc.returncode == 0 and proc.stdout == "" and len(errs) == 1, (proc.returncode, proc.stderr[-160:]))


def main():
    for case in (case_agent_refusal, case_spawn_prompt_bars_a_lane_waiting_page_write, case_agent_override, case_explore_row_is_vetoed, case_question,
                 case_question_departs, case_fail_open, case_settings_row):
        try:
            case()
        except Exception as exc:
            check(case.__name__, False, "raised %s: %s" % (type(exc).__name__, exc))
    print("FAIL: %d failed" % len(FAILED) if FAILED else "all checks passed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
