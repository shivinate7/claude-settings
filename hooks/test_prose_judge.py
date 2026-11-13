#!/usr/bin/env python3
"""Cases for hooks/prose_judge.py, the one PreToolUse command hook that judges an Edit or Write of
prose against speak-rewrite-superseded-in-place and rulings-declare-kind. It replaces the two
`type: prompt` hooks on Edit and Write. Standard library only, and no test runner.

Run it from the repository root:

    python hooks/test_prose_judge.py

Each case feeds one PreToolUse payload to `main()` on stdin (UTF-8 bytes, as Claude Code writes
them), then reads stdout and the exit code. `invoke_model` is replaced by a stub, so no case starts
a real `claude` process.

Interface the hook must match:
- File: hooks/prose_judge.py. Module-level `main()`; exit 0 on every path (a return or SystemExit(0)).
- Payload: `{"hook_event_name": "PreToolUse", "tool_name": "Edit"|"Write", "tool_input": {...}}`.
  Edit input: file_path, old_string, new_string. Write input: file_path, content.
- The model caller is `invoke_model`, a module-level function of hooks/prose_judge.py that calls
  hooks/decision_watch.py's `invoke_model` on first use. main() looks the name up at call time in
  the module, so the stub can replace it. Call: `invoke_model(prompt, timeout=MODEL_TIMEOUT,
  shape={"ok": (True, False)})`, returning (verdict_dict, error) as reply_judge.py uses it. The
  prompt is the first positional argument. The module exposes the int `MODEL_TIMEOUT`.
- Lazy load: the hook loads no other module of this repo (decision_watch, guard, and what they pull
  in) until a path passes the `decisions` check. A skipped path, or input it cannot read, ends the
  hook with none of them in sys.modules. The seam holds: `invoke_model` is a name in the module that
  a caller can replace, and the replacement is what main() calls.
- Which files: a path with a `decisions` folder segment (either slash, any case) is judged, as main's
  `Edit(**/decisions/**)` rows did. Any other path ends the hook at once: no model call, empty
  stdout, exit 0. That covers README.md, docs/x.md, debts/x.md and a file named decisions.md.
- The prompt holds the rule text of today's prompt hook for that tool, verbatim (EDIT_RULE and
  WRITE_RULE below), and the change: file_path, and for Edit old_string and new_string, for Write content.
- Block: model answer `{"ok": false, "reason": R}` -> stdout is one JSON object
  `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
  "permissionDecisionReason": <holds R>}}`, exit 0. The prompt hook it replaces blocks the same way:
  ok false stops the tool and hands the reason to Claude (continueOnBlock).
- Allow: model answer `{"ok": true}` -> empty stdout, exit 0.
- Model error or timeout: FAIL OPEN. Never a deny; stdout is empty or one `systemMessage` JSON; exit 0.
  Today's prompt hook fails open the same way (a hook that errors is a non-blocking error), and a
  judge outage must not stop every edit of a Markdown file.
- Malformed stdin, or no file_path: allow, no model call, exit 0.
- settings.json: the row's `timeout` exceeds MODEL_TIMEOUT.
"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
SETTINGS = os.environ.get("SETTINGS_UNDER_TEST") or os.path.join(REPO_ROOT, "settings.json")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO_ROOT, "lint"))
sys.path.insert(0, os.path.join(HERE, "test_support"))
import _test_ruling_kind_fixture as fx  # noqa: E402  the fixture record text (lint/_test_ruling_kind_fixture.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)
import cost_probe  # noqa: E402  the shared cost counters (hooks/test_support/cost_probe.py)

try:
    import prose_judge as pj
    LOAD_ERROR = None
except Exception as exc:  # the module does not exist yet: every case fails, none crashes
    pj, LOAD_ERROR = None, "%s: %s" % (type(exc).__name__, exc)

FAILED = []

# The Edit rule text the hook sends, verbatim, after "Judge this edit to a file: $ARGUMENTS\n".
# Decision rulings-declare-kind: a second ruling needs its own record. The lint, not the judge, counts
# Kind lines.
EDIT_RULE = (
    "Rule: speak-rewrite-superseded-in-place (superseded text is rewritten in place; no story, no old quote, "
    "and no superseded ruling kept beside the new one). A record may state a current fact with its history in "
    "one clause; that is not a breach. Rule: rulings-declare-kind (refuse only an edit whose new text deletes a "
    "`Plan:` or `Home:` line, or adds a second ruling section to a record; the fix is to move that ruling to its "
    "own record. A record has one `Kind:` line, and the lint counts it, so never refuse an edit for a `Kind:` "
    "line; you see only the changed text). Block only on a clear breach; when "
    "unsure answer {\"ok\": true}. Reply JSON only: {\"ok\": true} or {\"ok\": false, \"reason\": \"<rule id and "
    "the fix, one line>\"}."
)
WRITE_RULE = (
    "Rule: speak-rewrite-superseded-in-place (superseded text is rewritten in place; no story, no old quote, "
    "and no superseded ruling kept beside the new one). A record may state a current fact with its history in "
    "one clause; that is not a breach. Rule: rulings-declare-kind (refuse a decision record that has no "
    "`Kind: build` with `Plan: <path>#<slug> (<platform>)` lines, or `Kind: process` with a `Home:` line). "
    "Block only on a clear breach; when unsure answer {\"ok\": true}. Reply JSON only: {\"ok\": true} or "
    "{\"ok\": false, \"reason\": \"<rule id and the fix, one line>\"}."
)
OLD, NEW, BODY = "OLDTEXT-3c1f", "NEWTEXT-9b7d", "BODYTEXT-52ea"
REASON = "speak-rewrite-superseded-in-place: rewrite the ruling in place."


def check(name, ok, detail=""):
    if not ok:
        FAILED.append(name)
        print("FAIL: %s  %s" % (name, detail))


class Stub:
    def __init__(self, result):
        self.result, self.prompts, self.kwargs = result, [], []

    def __call__(self, prompt, *args, **kwargs):
        self.prompts.append(prompt)
        self.kwargs.append(kwargs)
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


def run(payload, result=({"ok": True}, None)):
    """Run main() on PAYLOAD with a stubbed model. Return (exit_code, stdout, stub)."""
    stub, out, code = Stub(result), io.StringIO(), None
    prior_stdin, prior_model = sys.stdin, pj.invoke_model
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    sys.stdin = io.TextIOWrapper(io.BytesIO(raw.encode("utf-8")), encoding="utf-8")
    pj.invoke_model = stub
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            try:
                pj.main()
            except SystemExit as exc:
                code = exc.code
    finally:
        sys.stdin, pj.invoke_model = prior_stdin, prior_model
    return (0 if code is None else code), out.getvalue(), stub


def edit(path):
    return {"hook_event_name": "PreToolUse", "tool_name": "Edit",
            "tool_input": {"file_path": path, "old_string": OLD, "new_string": NEW}}


def write(path):
    return {"hook_event_name": "PreToolUse", "tool_name": "Write",
            "tool_input": {"file_path": path, "content": BODY}}


def json_or_none(text):
    try:
        obj = json.loads(text)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def need_module():
    if pj is None:
        check("module hooks/prose_judge.py importable", False, LOAD_ERROR)
        return False
    return True


# (a) a path that is not prose ends the hook at once.
SKIP_PATHS = ["src/app.ts", "src/App.tsx", "settings.json", "hooks/guard.py", "C:\\r\\lint\\x.json",
              "notes.md.json", "docs.md/run.py", "README.md.bak", "README.md", "docs/x.md", "debts/x.md",
              "debts/x.json", "src/decisions.md"]


def case_a_other_paths_make_no_model_call():
    for path in SKIP_PATHS:
        for payload in (edit(path), write(path)):
            name = "a: %s %s" % (payload["tool_name"], path)
            if not need_module():
                return
            code, out, stub = run(payload, ({"ok": False, "reason": REASON}, None))
            check(name + ": no model call", stub.prompts == [], len(stub.prompts))
            check(name + ": exit 0", code == 0, code)
            check(name + ": no stdout", out == "", repr(out))


def case_a_prose_named_in_a_ts_body_is_not_judged():
    if not need_module():
        return
    p = edit("src/a.ts")
    p["tool_input"]["new_string"] = "see decisions/x.md and README.md"
    code, out, stub = run(p, ({"ok": False, "reason": REASON}, None))
    check("a: .ts body that names a .md file: no call, no output", stub.prompts == [] and out == "" and code == 0)


# (b) a file under a decisions folder is judged once, with the verbatim rule text and the change.
MD_PATHS = ["decisions/x.md", "C:\\repo\\decisions\\x.md", "a/DECISIONS/x.md", "decisions/sub/x.md"]


def case_b_md_edit_calls_model_once_with_rule_and_change():
    for path in MD_PATHS:
        if not need_module():
            return
        code, out, stub = run(edit(path))
        name = "b: Edit " + path
        check(name + ": one model call", len(stub.prompts) == 1, len(stub.prompts))
        prompt = stub.prompts[0] if stub.prompts else ""
        check(name + ": verbatim Edit rule text", EDIT_RULE in prompt)
        check(name + ": old_string, new_string and path in the prompt",
              OLD in prompt and NEW in prompt and path in prompt)
        check(name + ": allow is empty stdout, exit 0", code == 0 and out == "", (code, out))


def case_b_md_write_calls_model_once_with_rule_and_change():
    for path in MD_PATHS:
        if not need_module():
            return
        code, out, stub = run(write(path))
        name = "b: Write " + path
        check(name + ": one model call", len(stub.prompts) == 1, len(stub.prompts))
        prompt = stub.prompts[0] if stub.prompts else ""
        check(name + ": verbatim Write rule text", WRITE_RULE in prompt)
        check(name + ": content and path in the prompt", BODY in prompt and path in prompt)
        check(name + ": allow is empty stdout, exit 0", code == 0 and out == "", (code, out))


def case_b_model_call_shape_and_timeout():
    if not need_module():
        return
    _, _, stub = run(edit("decisions/a.md"))
    kw = stub.kwargs[0] if stub.kwargs else {}
    check("b: shape is the ok/not-ok verdict", kw.get("shape") == {"ok": (True, False)}, kw)
    check("b: timeout is MODEL_TIMEOUT", isinstance(getattr(pj, "MODEL_TIMEOUT", None), int)
          and kw.get("timeout") == pj.MODEL_TIMEOUT, kw)
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            rows = [h for e in json.load(f)["hooks"]["PreToolUse"] for h in e["hooks"]
                    if "prose_judge.py" in h.get("command", "")]
    except Exception:
        rows = []
    check("b: settings row timeout exceeds MODEL_TIMEOUT",
          len(rows) == 1 and rows[0].get("timeout", 0) > pj.MODEL_TIMEOUT, rows)


# (c) a decisions folder deeper in the path is judged too.
def case_c_decisions_folder_is_judged():
    for path in ("docs/decisions/x.md", "Decisions/x.md"):
        for payload in (edit(path), write(path)):
            if not need_module():
                return
            _, _, stub = run(payload)
            check("c: %s %s: called once" % (payload["tool_name"], path), len(stub.prompts) == 1, len(stub.prompts))


# (d) a model block answer blocks; a model failure fails open.
def case_d_model_block_denies_with_the_reason():
    for payload in (edit("decisions/a.md"), write("decisions/x.md")):
        if not need_module():
            return
        code, out, _ = run(payload, ({"ok": False, "reason": REASON}, None))
        obj = json_or_none(out)
        hso = (obj or {}).get("hookSpecificOutput") or {}
        name = "d: %s block" % payload["tool_name"]
        check(name + ": exit 0", code == 0, code)
        check(name + ": one PreToolUse deny object", hso.get("hookEventName") == "PreToolUse"
              and hso.get("permissionDecision") == "deny", repr(out))
        check(name + ": reason carries the model reason", REASON in hso.get("permissionDecisionReason", ""), repr(out))


def case_d_model_error_fails_open():
    for result in ((None, "model subprocess timed out"), (None, "model exited 1: x"), RuntimeError("boom")):
        for payload in (edit("decisions/a.md"), write("decisions/a.md")):
            if not need_module():
                return
            name = "d: %s fail-open on %r" % (payload["tool_name"], result)
            try:
                code, out, stub = run(payload, result)
            except Exception as exc:
                check(name, False, "main() raised %r" % exc)
                continue
            obj = json_or_none(out)
            denies = bool(obj and "hookSpecificOutput" in obj)
            check(name + ": exit 0", code == 0, code)
            check(name + ": no deny", not denies, repr(out))
            check(name + ": stdout empty or one systemMessage",
                  out == "" or bool(obj and set(obj) == {"systemMessage"}), repr(out))


def case_d_bad_input_allows():
    for raw in ("not json", "{}", json.dumps({"tool_name": "Edit", "tool_input": {}})):
        if not need_module():
            return
        code, out, stub = run(raw, ({"ok": False, "reason": REASON}, None))
        check("d: bad input %r: no call, no deny, exit 0" % raw[:20],
              stub.prompts == [] and "deny" not in out and code == 0, (code, out))

# (e) nothing heavy loads until the hook has work. Each case runs the hook in a fresh interpreter:
# sys.modules here is shared by every case, so only a new process shows what this hook alone loads,
# and the stand-in for decision_watch must not leak into the other cases.
CHILD = r"""
import io, json, os, sys, types
hooks, root, mode = sys.argv[1:4]
sys.path.insert(0, hooks)
calls = []
def model(name, verdict):
    def call(prompt, **kwargs):
        calls.append(name)
        return verdict, None
    return call
if mode == "broken":
    sys.modules["decision_watch"] = None  # `from decision_watch import ...` now raises ImportError
elif mode != "bare":
    # a stand-in for the real home, so no case can start a real `claude` process
    home = types.ModuleType("decision_watch")
    home.invoke_model = model("home", {"ok": True})
    sys.modules["decision_watch"] = home
import prose_judge
if mode == "replaced":
    prose_judge.invoke_model = model("replaced", {"ok": False, "reason": "R-replaced"})
sys.stdin = io.TextIOWrapper(io.BytesIO(os.environ["CHILD_PAYLOAD"].encode("utf-8")), encoding="utf-8")
code = prose_judge.main()
root = os.path.normcase(os.path.abspath(root))
loaded = sorted(n for n, m in sys.modules.items() if n != "prose_judge" and getattr(m, "__file__", None)
                and os.path.normcase(os.path.abspath(m.__file__)).startswith(root))
sys.stdout.write("\n" + json.dumps({"code": code, "calls": calls, "loaded": loaded}))
sys.exit(code)  # as the hook's own `sys.exit(main())` does, so the parent reads main's exit code
"""


def fresh_run(payload, mode):
    """Run the hook in a new interpreter. Return (exit_code, hook_stdout, result_dict_or_None)."""
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    env = dict(os.environ, CHILD_PAYLOAD=raw)
    proc = subprocess.run([sys.executable, "-c", CHILD, HERE, REPO_ROOT, mode], env=env,
                          capture_output=True, text=True, encoding="utf-8", timeout=60)
    out, _, tail = proc.stdout.rpartition("\n")
    try:
        return proc.returncode, out, json.loads(tail)
    except ValueError:
        return proc.returncode, proc.stdout + proc.stderr, None


def case_e_a_skipped_input_loads_no_repo_module():
    if not need_module():
        return
    for name, payload in (("Edit src/app.ts", edit("src/app.ts")), ("Write README.md", write("README.md")),
                          ("unreadable stdin", "not json")):
        code, out, result = fresh_run(payload, "bare")
        check("e: %s: hook ran" % name, result is not None and code == 0, (code, out[-200:]))
        check("e: %s: no repo module loaded" % name, result is not None and result["loaded"] == [],
              result and result["loaded"])
        check("e: %s: no output" % name, out == "", repr(out))


def case_e_a_replaced_invoke_model_is_the_one_called():
    if not need_module():
        return
    code, out, result = fresh_run(edit("decisions/x.md"), "replaced")
    hso = (json_or_none(out) or {}).get("hookSpecificOutput") or {}
    check("e: replaced invoke_model: ran", result is not None and code == 0, (code, out[-200:]))
    check("e: replaced invoke_model: only the replacement is called", result is not None
          and result["calls"] == ["replaced"], result and result["calls"])
    check("e: replaced invoke_model: its verdict denies", hso.get("permissionDecision") == "deny"
          and "R-replaced" in hso.get("permissionDecisionReason", ""), repr(out))


def case_e_the_unreplaced_call_reaches_decision_watch():
    if not need_module():
        return
    code, out, result = fresh_run(write("decisions/x.md"), "home")
    check("e: unreplaced: ran", result is not None and code == 0, (code, out[-200:]))
    check("e: unreplaced: decision_watch.invoke_model is called once", result is not None
          and result["calls"] == ["home"], result and result["calls"])
    check("e: unreplaced: its allow is empty stdout", out == "", repr(out))

def case_e_a_failed_decision_watch_import_does_not_block():
    if not need_module():
        return
    code, out, result = fresh_run(edit("decisions/x.md"), "broken")
    check("e: failed import: the hook ends, it does not crash at load", result is not None, (code, out[-200:]))
    check("e: failed import: not a block (exit 2 or a deny)", code != 2 and "deny" not in out, (code, out[-200:]))


# (f) a refusal goes through guard_core.refuse(), so an owner override lifts it (decision owner-override).
# Each case runs the hook in a fresh interpreter with a config folder of its own, and reads guard.log.
OV_CHILD = r"""
import io, json, os, sys
sys.path.insert(0, sys.argv[1])
import prose_judge
prose_judge.invoke_model = lambda prompt, **kw: ({"ok": False, "reason": os.environ["OV_REASON"]}, None)
sys.stdin = io.TextIOWrapper(io.BytesIO(os.environ["OV_PAYLOAD"].encode("utf-8")), encoding="utf-8")
sys.exit(prose_judge.main())
"""
OV_FUTURE, OV_PAST = "2099-01-01T00:00:00+00:00", "2000-01-01T00:00:00+00:00"


def ov_run(payload, override=None, session="ses00001"):
    """Run the hook once with a model that always blocks. override is (session id, file body) or None.
    Return (exit_code, stdout, guard.log text)."""
    import shutil
    import tempfile
    cfg = tempfile.mkdtemp(prefix="prose_judge_cfg_")
    try:
        if override is not None:
            folder = os.path.join(cfg, "state", "override")
            os.makedirs(folder)
            body = override[1]
            with open(os.path.join(folder, override[0] + ".json"), "w", encoding="utf-8") as f:
                f.write(body if isinstance(body, str) else json.dumps(body))
        env = dict(os.environ, CLAUDE_CONFIG_DIR=cfg, OV_REASON=REASON,
                   OV_PAYLOAD=json.dumps(dict(payload, session_id=session)))
        env.pop("CLAUDE_CODE_SESSION_ID", None)
        proc = subprocess.run([sys.executable, "-c", OV_CHILD, HERE], env=env, capture_output=True,
                              text=True, encoding="utf-8", timeout=60)
        log = os.path.join(cfg, "guard.log")
        text = open(log, encoding="utf-8").read() if os.path.exists(log) else ""
        return proc.returncode, proc.stdout, text, proc.stderr
    finally:
        shutil.rmtree(cfg, ignore_errors=True)


def case_f_an_override_lifts_the_refusal():
    if not need_module():
        return
    timed = {"kind": "timed", "until": OV_FUTURE}
    once = {"kind": "once", "until": OV_FUTURE, "id": "0" * 32}
    for tool_payload in (edit("decisions/a.md"), write("decisions/x.md")):
        name = "f: " + tool_payload["tool_name"]
        for label, override, lifted in (
            ("a timed override", ("ses00001", timed), True),
            ("a one-act override", ("ses00001", once), True),
            ("an ended override", ("ses00001", dict(timed, until=OV_PAST)), False),
            ("another session's override", ("ses00002", timed), False),
            ("a corrupt override file", ("ses00001", "{not json"), False),
            ("no override", None, False),
        ):
            code, out, log, err = ov_run(tool_payload, override)
            if lifted:
                check("%s, %s: lifted, no output, one override log line" % (name, label),
                      code == 0 and out == "" and log.count("\toverride\tprose-judge\t") == 1
                      and "\tdeny\t" not in log, (code, out[:120], log, err[-120:]))
            else:
                hso = (json_or_none(out) or {}).get("hookSpecificOutput") or {}
                check("%s, %s: the deny stands, with the judge's reason and one deny log line" % (name, label),
                      code == 0 and hso.get("permissionDecision") == "deny"
                      and REASON in hso.get("permissionDecisionReason", "")
                      and log.count("\tdeny\tprose-judge\t") == 1, (code, out[:120], log, err[-120:]))
    code, out, log, err = ov_run(edit("decisions/a.md"))
    reason = ((json_or_none(out) or {}).get("hookSpecificOutput") or {}).get("permissionDecisionReason", "")
    import override as home
    offer = getattr(home, "offer", None)
    check("f: the refusal ends with the override line", offer is not None
          and reason.rstrip().endswith(offer("prose-judge").strip()), reason[-160:])
    code, out, log, err = ov_run(edit("src/app.ts"), ("ses00001", {"kind": "once", "until": OV_FUTURE, "id": "1" * 32}))
    check("f: a path that is not judged spends no override", out == "" and "override" not in log, (out, log))


# (g) rulings-declare-kind: the judge refuses an edit that adds a second ruling section to a record, and
# its remedy is that ruling's own record, never a Kind line. It does not refuse a fold that keeps the one
# Kind line. The model is stubbed, so the rule text the judge is sent is the part a case can read.
# Decision rulings-declare-kind: a second ruling needs its own record.
ADD_OLD = "## How to write a test that earns its keep"
ADD_NEW = ("## Where CI runs a suite\n\n- Each CI job runs only when a file that its suites read changes.\n\n"
           + ADD_OLD)
FOLD_OLD = "Kind: process\nHome: " + fx.HOME_PATH  # the second Kind line of the record and its Home line
FOLD_NEW = "Home: " + fx.HOME_PATH  # the same Home line, the second Kind line folded away
ADD_REFUSAL = "adds a second ruling section to a record"
OWN_RECORD = "to its own record"
KIND_ASKS = ("adds a ruling section with no `Kind:` line", "add a `Kind:` line")
DELETE_DEMAND = "deletes a `Kind:`"


def case_g_one_kind_line_record_is_not_refused_for_a_kind_count():
    if not need_module():
        return
    path = "decisions/test-strategy-reset.md"
    add = edit(path)
    add["tool_input"].update(old_string=ADD_OLD, new_string=ADD_NEW)
    _, _, stub = run(add)
    prompt = stub.prompts[0] if stub.prompts else ""
    check("g: add-section Edit: one model call with the change", len(stub.prompts) == 1 and ADD_NEW in prompt,
          len(stub.prompts))
    check("g: add-section Edit: the rule text refuses a second ruling section added to a record",
          ADD_REFUSAL in prompt,
          "the judge does not refuse a second ruling section; rulings-declare-kind says it needs its own record")
    check("g: add-section Edit: the rule text's remedy is the ruling's own record",
          OWN_RECORD in prompt, "the judge names no own-record remedy for a second ruling section")
    check("g: add-section Edit: the rule text asks for no Kind line",
          not any(k in prompt for k in KIND_ASKS), "the judge asks for a Kind line for the added section")
    fold = edit(path)
    fold["tool_input"].update(old_string=FOLD_OLD, new_string=FOLD_NEW)
    _, _, stub = run(fold)
    prompt = stub.prompts[0] if stub.prompts else ""
    check("g: fold Edit: one model call with the change", len(stub.prompts) == 1 and FOLD_NEW in prompt,
          len(stub.prompts))
    check("g: fold Edit: no rule text refuses a deleted Kind line",
          DELETE_DEMAND not in prompt,
          "the judge refuses folding away the second Kind line; the lint counts Kind lines, not the judge")
    rec = write(path)
    rec["tool_input"]["content"] = fx.ONE_KIND_RECORD
    code, out, stub = run(rec)
    prompt = stub.prompts[0] if stub.prompts else ""
    check("g: Write of the one-Kind record: the record reaches the Write judge (control)",
          fx.ONE_KIND_RECORD in prompt and len(stub.prompts) == 1, len(stub.prompts))
    check("g: Write of the one-Kind record: an ok verdict allows it (control)", code == 0 and out == "", (code, out))


# The cost of one fire (the model-call judges row). A decisions path costs one model call and nothing else on an
# allow. Any other path or tool starts nothing. A refusal adds the guard log line and whatever guard_core starts,
# which the case reads from the run.

class CostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = _test_temp.run_folder()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.folder, ignore_errors=True)

    def fire(self, payload, answers=None):
        folder = tempfile.mkdtemp(dir=self.folder)
        return cost_probe.run_hook(os.path.join(HERE, "prose_judge.py"), json.dumps(payload), folder, answers)

    def test_a_path_outside_decisions_starts_nothing(self):
        run = self.fire(edit("README.md"))
        self.assertEqual((run["code"], run["models"], run["children"], run["files"], run["out"]), (0, [], [], [], ""))

    def test_a_tool_other_than_edit_or_write_starts_nothing(self):
        run = self.fire({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                         "tool_input": {"command": "ls docs/decisions"}})
        self.assertEqual((run["code"], run["models"], run["children"], run["files"], run["out"]), (0, [], [], [], ""))

    def test_an_allowed_decision_edit_costs_one_model_call_and_nothing_else(self):
        run = self.fire(edit("docs/decisions/x.md"), [[{"ok": True}, None]])
        self.assertEqual(len(run["models"]), 1, "one decisions edit makes one model call, got %r" % run["models"])
        self.assertEqual(run["models"][0]["timeout"], pj.MODEL_TIMEOUT)
        self.assertEqual((run["children"], run["files"], run["out"]), ([], [], ""),
                         "an allow starts no child and writes no file")

    def test_an_allowed_decision_write_costs_one_model_call_and_nothing_else(self):
        run = self.fire(write("docs/decisions/x.md"), [[{"ok": True}, None]])
        self.assertEqual(len(run["models"]), 1, "one decisions write makes one model call, got %r" % run["models"])
        self.assertEqual((run["children"], run["files"]), ([], []))

    def test_a_refusal_adds_the_guard_log_line_and_no_other_file(self):
        reason = "speak-rewrite-superseded-in-place: rewrite the ruling in place."
        run = self.fire(edit("docs/decisions/x.md"), [[{"ok": False, "reason": reason}, None]])
        self.assertEqual(len(run["models"]), 1)
        self.assertEqual(run["children"], [], "a refusal starts no child; got %r" % run["children"])
        self.assertEqual(run["files"], ["guard.log"], "a refusal writes the guard log only; got %r" % run["files"])
        self.assertIn("permissionDecision", run["out"], "a refusal denies")

    def test_the_one_call_fits_the_settings_row_timeout(self):
        row = cost_probe.settings_timeout("prose_judge.py", "PreToolUse")
        self.assertIsNotNone(row, "settings.json has a PreToolUse row for prose_judge.py")
        self.assertLess(pj.MODEL_TIMEOUT, row, "the model call's timeout must end before the row's hook timeout")


def main():
    for case in (case_a_other_paths_make_no_model_call, case_a_prose_named_in_a_ts_body_is_not_judged,
                 case_b_md_edit_calls_model_once_with_rule_and_change,
                 case_b_md_write_calls_model_once_with_rule_and_change,
                 case_b_model_call_shape_and_timeout, case_c_decisions_folder_is_judged,
                 case_d_model_block_denies_with_the_reason, case_d_model_error_fails_open,
                 case_d_bad_input_allows, case_e_a_skipped_input_loads_no_repo_module,
                 case_e_a_replaced_invoke_model_is_the_one_called,
                 case_e_the_unreplaced_call_reaches_decision_watch,
                 case_e_a_failed_decision_watch_import_does_not_block,
                 case_f_an_override_lifts_the_refusal,
                 case_g_one_kind_line_record_is_not_refused_for_a_kind_count):
        try:
            case()
        except Exception as exc:
            check(case.__name__, False, "raised %s: %s" % (type(exc).__name__, exc))
    if not cost_probe.run_class(CostTests):
        FAILED.append("CostTests")
    print("%s: %d failed" % ("FAIL" if FAILED else "OK", len(FAILED)))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
