#!/usr/bin/env python3
"""Cases for hooks/question_outcome.py. Standard library only, and no test runner.

Run it from the repository root:

    python hooks/test_question_outcome.py

Each case feeds one PreToolUse payload for AskUserQuestion to `main()` on stdin, as Claude Code
runs the hook, then reads stdout and the exit code. `invoke_model` is replaced by a stub, so no
case starts a real `claude` process. A fake `claude` also sits first on PATH; any real call
that gets past the stub is counted, and the run fails. CLAUDE_CONFIG_DIR is a scratch directory,
so the per-session state never reaches ~/.claude.

Interface the hook must match:
- The module imports `invoke_model` from hooks/decision_watch.py. `main()` looks up the
  module-level name `invoke_model` at call time, so the stub can replace it.
- Deny: stdout is one JSON object
  `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
  "permissionDecisionReason": "..."}}`, and exit 0.
- Allow: stdout is empty, or one JSON object holding only `systemMessage`, and exit 0.
- Check did not run: stdout is `{"systemMessage": "... did not run ..."}`, and exit 0.
- One deny per question: state file `<CLAUDE_CONFIG_DIR>/state/question-outcome/<sha256(session_id)>.json`.
- The model prompt is the first positional argument of `invoke_model`.
- Override the module under test with the env var QUESTION_OUTCOME_UNDER_TEST.
"""
import atexit
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE_PATH = os.environ.get("QUESTION_OUTCOME_UNDER_TEST") or os.path.join(HERE, "question_outcome.py")
sys.path.insert(0, HERE)

import decision_watch as dw  # noqa: E402  the proven model caller the hook must reuse

ROOT = tempfile.mkdtemp(prefix="question_outcome_cases_")
atexit.register(shutil.rmtree, ROOT, True)
CONFIG_DIR = os.path.join(ROOT, "claude-config")
os.makedirs(CONFIG_DIR, exist_ok=True)
os.environ["CLAUDE_CONFIG_DIR"] = CONFIG_DIR

CLAUDE_CALLS = os.path.join(ROOT, "claude-calls")
BINDIR = os.path.join(ROOT, "bin")
os.makedirs(BINDIR, exist_ok=True)
_launcher = os.path.join(BINDIR, "claude")
with open(_launcher, "w", encoding="utf-8") as _f:
    _f.write('#!/bin/sh\necho x >> "%s"\nexit 1\n' % CLAUDE_CALLS)
os.chmod(_launcher, 0o755)
os.environ["PATH"] = BINDIR + os.pathsep + os.environ.get("PATH", "")

LOAD_ERROR = None
qo = None
try:
    _spec = importlib.util.spec_from_file_location("question_outcome_under_test", MODULE_PATH)
    qo = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(qo)
except Exception as exc:  # the red reason: the module is not importable
    qo = None
    LOAD_ERROR = "%s: %s" % (type(exc).__name__, exc)

FAILED = []

RESTATE_RULE = "style-question-restates-goal"
WHY = "The wait option answers timing, not the three-try limit."
ALLOW = ({"verdict": "ALLOW"}, None)
FLAG = ({"verdict": "FLAG", "why": WHY}, None)
GOOD_Q = "You want: a three-try limit on the upload retry.\nShould the retry wait between tries?"
BAD_Q = "Should the retry wait between tries?"
LABELS = ["Wait one second", "No wait"]


def check(name, condition, detail=""):
    if condition:
        print("PASS: %s" % name)
    else:
        FAILED.append(name)
        print("FAIL: %s  %s" % (name, detail))


def need_module(name):
    """The module is missing or broken: one FAIL line for this case, then stop the case."""
    if qo is None:
        check(name, False, "question_outcome not importable (%s)" % LOAD_ERROR)
        return False
    return True


class Stub:
    """Replaces question_outcome.invoke_model. Returns `result`, and records each prompt."""

    def __init__(self, result):
        self.result = result
        self.prompts = []

    def __call__(self, prompt, *args, **kwargs):
        self.prompts.append(prompt)
        return self.result


@contextlib.contextmanager
def model_stub(result):
    stub = Stub(result)
    prior = qo.invoke_model
    qo.invoke_model = stub
    try:
        yield stub
    finally:
        qo.invoke_model = prior


def run_main(payload):
    """Run main() with `payload` on stdin. Return (exit_code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    prior_stdin = sys.stdin
    sys.stdin = io.StringIO(json.dumps(payload))
    code = None
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                qo.main()
            except SystemExit as exc:
                code = exc.code
    finally:
        sys.stdin = prior_stdin
    return code, out.getvalue(), err.getvalue()


def _json_or_none(text):
    text = text.strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def deny_reason(stdout):
    """The permissionDecisionReason when stdout is a PreToolUse deny, else None."""
    obj = _json_or_none(stdout)
    hso = obj.get("hookSpecificOutput") if obj else None
    if not isinstance(hso, dict):
        return None
    if hso.get("hookEventName") != "PreToolUse" or hso.get("permissionDecision") != "deny":
        return None
    return hso.get("permissionDecisionReason", "")


def system_message(stdout):
    obj = _json_or_none(stdout)
    return obj.get("systemMessage") if obj else None


def question(text, labels=None):
    q = {"question": text, "header": "Retry", "multiSelect": False}
    if labels is not None:
        q["options"] = [{"label": lab, "description": "meaning of " + lab} for lab in labels]
    return q


def ask_payload(session_id, questions, transcript):
    return {
        "session_id": session_id,
        "transcript_path": transcript,
        "cwd": HERE,
        "hook_event_name": "PreToolUse",
        "tool_name": "AskUserQuestion",
        "tool_input": {"questions": questions},
    }


def write_transcript(name, records):
    path = os.path.join(ROOT, name + ".jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    return path


def owner(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


def owner_blocks(text):
    return {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": text}]}}


def tool_result(text):
    return {"type": "user", "message": {"role": "user", "content": [
        {"tool_use_id": "toolu_fixture", "type": "tool_result", "content": text}]}}


def assistant(text):
    return {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


_DEFAULT = []


def default_transcript():
    if not _DEFAULT:
        _DEFAULT.append(write_transcript("default", [owner("Add a three-try limit to the upload retry.")]))
    return _DEFAULT[0]


def _claude_calls():
    try:
        with open(CLAUDE_CALLS, encoding="utf-8") as f:
            return len(f.read())
    except OSError:
        return 0


# --------------------------------------------------------------------------- case 1

def case_1_missing_restate_is_denied():
    name = "case1 restate missing: deny, rule named, no model call"
    if not need_module(name):
        return
    with model_stub(ALLOW) as stub:
        code, out, _ = run_main(ask_payload("c1", [question(BAD_Q, LABELS)], default_transcript()))
    reason = deny_reason(out)
    check(name + ": exit 0", code in (0, None), code)
    check(name + ": denied", reason is not None, out)
    check(name + ": reason names " + RESTATE_RULE, reason is not None and RESTATE_RULE in reason, reason)
    check(name + ": invoke_model not called", stub.prompts == [], len(stub.prompts))


# --------------------------------------------------------------------------- case 2

def case_2_restated_and_allowed():
    name = "case2 restated question, model ALLOW: allow"
    if not need_module(name):
        return
    check(name + ": invoke_model is decision_watch's", qo.invoke_model is dw.invoke_model)
    with model_stub(ALLOW) as stub:
        code, out, _ = run_main(ask_payload("c2", [question(GOOD_Q, LABELS)], default_transcript()))
    check(name + ": exit 0", code in (0, None), code)
    check(name + ": not denied", deny_reason(out) is None, out)
    check(name + ": model called once", len(stub.prompts) == 1, len(stub.prompts))


# --------------------------------------------------------------------------- case 3

def case_3_flag_denies_with_why():
    name = "case3 model FLAG: deny, reason carries the why"
    if not need_module(name):
        return
    with model_stub(FLAG) as stub:
        code, out, _ = run_main(ask_payload("c3", [question(GOOD_Q, LABELS)], default_transcript()))
    reason = deny_reason(out)
    check(name + ": exit 0", code in (0, None), code)
    check(name + ": denied", reason is not None, out)
    check(name + ": reason carries the why", reason is not None and WHY in reason, reason)
    check(name + ": model called once", len(stub.prompts) == 1, len(stub.prompts))


# --------------------------------------------------------------------------- case 4

def case_4_timeout_allows_and_says_so():
    name = "case4 model timeout: allow, one line says the check did not run"
    if not need_module(name):
        return
    with model_stub((None, "timeout")):
        code, out, _ = run_main(ask_payload("c4", [question(GOOD_Q, LABELS)], default_transcript()))
    msg = system_message(out)
    check(name + ": exit 0", code in (0, None), code)
    check(name + ": not denied", deny_reason(out) is None, out)
    check(name + ": one output line", len(out.strip().splitlines()) == 1, out)
    check(name + ": systemMessage says did not run", msg is not None and "did not run" in msg, out)


# --------------------------------------------------------------------------- case 5

def case_5_one_deny_per_question_per_session():
    name = "case5 same question again in the same session: allow, no model call"
    if not need_module(name):
        return
    session = "c5-session"
    payload = ask_payload(session, [question(GOOD_Q, LABELS)], default_transcript())
    with model_stub(FLAG) as stub:
        _, out1, _ = run_main(payload)
        check(name + ": first ask denied", deny_reason(out1) is not None, out1)
        state = os.path.join(CONFIG_DIR, "state", "question-outcome",
                             hashlib.sha256(session.encode("utf-8")).hexdigest() + ".json")
        check(name + ": state file written under CLAUDE_CONFIG_DIR", os.path.isfile(state), state)
        _, out2, _ = run_main(payload)
    check(name + ": second ask allowed", deny_reason(out2) is None, out2)
    check(name + ": model called once in total", len(stub.prompts) == 1, len(stub.prompts))


# --------------------------------------------------------------------------- case 6

def case_6_prompt_holds_last_three_owner_messages():
    name = "case6 prompt: last 3 genuine owner messages, question, options"
    if not need_module(name):
        return
    transcript = write_transcript("case6", [
        owner("OWNER-1 an old request that must not appear."),
        assistant("Noted."),
        owner_blocks("OWNER-2 the upload should retry."),
        tool_result("TOOLRESULT-SENTINEL file listing that is not owner text."),
        assistant("Reading the file."),
        owner_blocks("<system-reminder>REMINDER-SENTINEL harness text, not the owner.</system-reminder>"),
        owner("OWNER-3 keep it to three tries."),
        owner("OWNER-4 the wait matters less than the limit."),
    ])
    qtext = "You want: a three-try limit on the upload retry.\nQSENT-Q should the retry wait?"
    labels = ["LABEL-ALPHA wait", "LABEL-BETA no wait"]
    with model_stub(ALLOW) as stub:
        run_main(ask_payload("c6", [question(qtext, labels)], transcript))
    prompt = stub.prompts[0] if stub.prompts else ""
    check(name + ": model called", len(stub.prompts) == 1, len(stub.prompts))
    for marker in ("OWNER-2", "OWNER-3", "OWNER-4"):
        check(name + ": holds " + marker, marker in prompt, marker)
    check(name + ": omits OWNER-1", "OWNER-1" not in prompt, "OWNER-1")
    check(name + ": omits tool_result text", "TOOLRESULT-SENTINEL" not in prompt, "TOOLRESULT-SENTINEL")
    check(name + ": omits system-reminder text", "REMINDER-SENTINEL" not in prompt, "REMINDER-SENTINEL")
    check(name + ": at most 3 owner messages", prompt.count("OWNER-") <= 3, prompt.count("OWNER-"))
    check(name + ": holds the question", "QSENT-Q" in prompt, "QSENT-Q")
    check(name + ": holds each option label",
          "LABEL-ALPHA wait" in prompt and "LABEL-BETA no wait" in prompt, "labels")


# --------------------------------------------------------------------------- case 7

def case_7_clarifying_question_passes_without_model():
    name = "case7 clarifying question (no or one option): allow, no model call"
    if not need_module(name):
        return
    for label, labels in (("options absent", None), ("single option", ["Only one"])):
        with model_stub(FLAG) as stub:
            code, out, _ = run_main(ask_payload("c7-" + label.replace(" ", "-"),
                                                [question(GOOD_Q, labels)], default_transcript()))
        check(name + ": " + label + ": not denied", deny_reason(out) is None, out)
        check(name + ": " + label + ": exit 0", code in (0, None), code)
        check(name + ": " + label + ": no model call", stub.prompts == [], len(stub.prompts))


def main():
    cases = (case_1_missing_restate_is_denied, case_2_restated_and_allowed,
             case_3_flag_denies_with_why, case_4_timeout_allows_and_says_so,
             case_5_one_deny_per_question_per_session,
             case_6_prompt_holds_last_three_owner_messages,
             case_7_clarifying_question_passes_without_model)
    for case in cases:
        case()
    if LOAD_ERROR is None:
        check("no real claude process started", _claude_calls() == 0, _claude_calls())

    if FAILED:
        print("test_question_outcome FAIL: %d failing check(s)" % len(FAILED))
        return 1
    print("test_question_outcome PASS: all checks right")
    return 0


if __name__ == "__main__":
    sys.exit(main())
