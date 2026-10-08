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
- Check did not run: stdout is one `{"systemMessage": "... did not run ..."}` line, exit 0.
- Retry rule (ruling, batch review): after ANY deny in a session, the NEXT AskUserQuestion in
  that session passes with no model call, whatever its text or options, and clears the state.
  A third ask after that pass is judged again.
- Owner text: `owner_messages(path)` returns only genuine owner text, oldest first, at most 3.
  Machine lines (isMeta, origin not "human", task-notification, peer messages, Stop-hook
  feedback, compact summary, sidechain text, tool_result, system-reminder) never count.
- The transcript is read at the tail only: at most 2 MiB of a 10 MB transcript is read.
- `You want:` needs text on its own line. Blank or whitespace-only after the marker is missing.
- The `why` in a FLAG deny is capped and sanitized with lint/_transcript.safe_finding_text
  (FINDING_MAX, FINDING_CUT_MARK). No control character reaches the reason.
- Unwritable state: a FLAG is allowed with a "did not run" note, never denied (no loop).
- Malformed stdin: allow, exit 0, one "did not run" line.
- A model failure (timeout included): one "did not run" line. The line never echoes the prompt.
- The model caller is `invoke_model` from hooks/decision_watch.py, returning (verdict, error).
- The state file is `<CLAUDE_CONFIG_DIR>/state/question-outcome/<sha256(session_id)>.json`.
- The model prompt is the first positional argument of `invoke_model`.
- Override the module under test with the env var QUESTION_OUTCOME_UNDER_TEST.
"""
import atexit
import builtins
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE_PATH = os.environ.get("QUESTION_OUTCOME_UNDER_TEST") or os.path.join(HERE, "question_outcome.py")
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "lint"))

import decision_watch as dw  # noqa: E402  the proven model caller the hook must reuse
import _transcript as tr  # noqa: E402  the sanitizer and cap the `why` must go through

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
REWORDED_Q = "You want: a three-try limit on the upload retry.\nShould each retry pause before it runs?"
LABELS = ["Wait one second", "No wait"]
REWORDED_LABELS = ["Pause first", "Run now"]
CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f]")
MIB = 1024 * 1024


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
    """Replaces question_outcome.invoke_model. `result` is a value, or a callable that takes the
    prompt and returns the value. Each prompt is recorded."""

    def __init__(self, result):
        self.result = result
        self.prompts = []

    def __call__(self, prompt, *args, **kwargs):
        self.prompts.append(prompt)
        return self.result(prompt) if callable(self.result) else self.result


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
    return run_raw(json.dumps(payload))


def run_raw(stdin_text):
    """Run main() with `stdin_text` as the whole of stdin. Return (exit_code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    prior_stdin = sys.stdin
    sys.stdin = io.StringIO(stdin_text)
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


def fresh_session(tag):
    """A session id no earlier case used, so no state from one case reaches the next."""
    return "%s-%s" % (tag, os.urandom(4).hex())


def write_transcript(name, records):
    path = os.path.join(ROOT, name + ".jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    return path


def owner(text):
    """A genuine owner line, in the shape the transcripts carry: origin kind "human"."""
    return {"type": "user", "origin": {"kind": "human"},
            "message": {"role": "user", "content": text}}


def owner_blocks(text):
    return {"type": "user", "origin": {"kind": "human"},
            "message": {"role": "user", "content": [{"type": "text", "text": text}]}}


def owner_pasted(text):
    """A genuine owner line whose text opens with a pasted block (a "<" first, legitimate)."""
    return {"type": "user", "origin": {"kind": "human"},
            "message": {"role": "user", "content": "\n\n<pasted_content id=\"p1\">\n%s\n</pasted_content>" % text}}


def tool_result(text):
    return {"type": "user", "isSidechain": False, "sourceToolAssistantUUID": "u-fixture",
            "toolUseResult": {"status": "completed", "agentId": "a-fixture"},
            "message": {"role": "user", "content": [
                {"tool_use_id": "toolu_fixture", "type": "tool_result", "content": text}]}}


def assistant(text):
    return {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


# The machine-written user lines seen in real transcripts, one per shape. Each is paired with
# a sentinel that must never reach the owner text. The origin and flag keys follow the shapes
# sampled from the transcripts under ~/.claude/projects.
MACHINE_SHAPES = [
    ("isMeta Stop-hook feedback", {"type": "user", "isMeta": True,
        "message": {"role": "user", "content": "Stop hook feedback:\nSTOPHOOK-SENTINEL report-shape gate."}}),
    ("isMeta skill base directory", {"type": "user", "isMeta": True,
        "message": {"role": "user", "content": [{"type": "text",
                    "text": "Base directory for this skill: SKILLBASE-SENTINEL"}]}}),
    ("task-notification text", {"type": "user",
        "origin": {"kind": "task-notification", "producer": "session-task"},
        "message": {"role": "user", "content": "<task-notification>\n<task-id>TASKNOTE-SENTINEL</task-id>\n"
                    "<output-file>x</output-file>\n</task-notification>"}}),
    ("cross-session peer message", {"type": "user", "isMeta": True,
        "origin": {"kind": "peer", "from": "uds:fixture-pipe", "fromSession": "local_fixture",
                   "fromMode": "bypass", "body": "PEER-SENTINEL body"},
        "message": {"role": "user", "content": "Another Claude session sent a message:\n"
                    "<cross-session-message from-session=\"local_fixture\">PEER-SENTINEL body"
                    "</cross-session-message>"}}),
    ("compact summary", {"type": "user", "isCompactSummary": True,
        "message": {"role": "user", "content": "This session is being continued from a previous "
                    "conversation. Summary: COMPACT-SENTINEL"}}),
    ("subagent hand-back as sidechain text", {"type": "user", "isSidechain": True,
        "message": {"role": "user", "content": "SIDECHAIN-SENTINEL subagent prompt"}}),
    ("subagent hand-back as tool_result", tool_result("SUBAGENT-RESULT-SENTINEL")),
    ("tool_result", tool_result("TOOLRESULT-SENTINEL file listing")),
    ("system-reminder text", {"type": "user",
        "message": {"role": "user", "content": "<system-reminder>REMINDER-SENTINEL harness text"
                    "</system-reminder>"}}),
    ("task-notification text with no origin", {"type": "user",
        "message": {"role": "user", "content": "<task-notification>NOORIGIN-SENTINEL</task-notification>"}}),
]


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


@contextlib.contextmanager
def unwritable_state_dir():
    """CLAUDE_CONFIG_DIR where `state` is a regular file, so the hook cannot create its state
    folder. Works the same on Windows, where chmod does not stop a write."""
    base = tempfile.mkdtemp(prefix="unwritable-state-", dir=ROOT)
    with open(os.path.join(base, "state"), "w", encoding="utf-8") as f:
        f.write("a file where the state folder should be\n")
    prior = os.environ.get("CLAUDE_CONFIG_DIR")
    os.environ["CLAUDE_CONFIG_DIR"] = base
    try:
        yield base
    finally:
        if prior is None:
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
        else:
            os.environ["CLAUDE_CONFIG_DIR"] = prior


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
# Re-pointed (batch review, orchestrator ruling Q2): after a deny, the NEXT ask passes with no
# model call, whatever its text or options. The old rule passed only the identical question.

def case_5_after_a_deny_the_next_ask_passes_whatever_its_text():
    name = "case5 after a deny, the next ask passes with no model call (reworded, new options)"
    if not need_module(name):
        return
    session = fresh_session("c5")
    first = ask_payload(session, [question(GOOD_Q, LABELS)], default_transcript())
    second = ask_payload(session, [question(REWORDED_Q, REWORDED_LABELS)], default_transcript())
    with model_stub(FLAG) as stub:
        _, out1, _ = run_main(first)
        check(name + ": first ask denied", deny_reason(out1) is not None, out1)
        code, out2, _ = run_main(second)
    check(name + ": reworded next ask allowed", deny_reason(out2) is None, out2)
    check(name + ": exit 0", code in (0, None), code)
    check(name + ": no model call on the next ask", len(stub.prompts) == 1, len(stub.prompts))


def case_5b_after_a_deny_the_next_ask_passes_without_you_want():
    name = "case5b after a flag deny, the next ask passes even with no You want line"
    if not need_module(name):
        return
    session = fresh_session("c5b")
    first = ask_payload(session, [question(GOOD_Q, LABELS)], default_transcript())
    second = ask_payload(session, [question(BAD_Q, ["Wait one second", "No wait", "Ask me later"])],
                         default_transcript())
    with model_stub(FLAG) as stub:
        _, out1, _ = run_main(first)
        check(name + ": first ask denied", deny_reason(out1) is not None, out1)
        _, out2, _ = run_main(second)
    check(name + ": next ask allowed", deny_reason(out2) is None, out2)
    check(name + ": no model call on the next ask", len(stub.prompts) == 1, len(stub.prompts))


def case_5c_after_a_restate_deny_the_next_ask_passes_with_no_model_call():
    name = "case5c after a restate deny (no model call), the next ask passes with no model call"
    if not need_module(name):
        return
    session = fresh_session("c5c")
    first = ask_payload(session, [question(BAD_Q, LABELS)], default_transcript())
    second = ask_payload(session, [question(GOOD_Q, LABELS)], default_transcript())
    with model_stub(ALLOW) as stub:
        _, out1, _ = run_main(first)
        check(name + ": first ask denied for the restate", RESTATE_RULE in (deny_reason(out1) or ""), out1)
        _, out2, _ = run_main(second)
    check(name + ": next ask allowed", deny_reason(out2) is None, out2)
    check(name + ": no model call at all", stub.prompts == [], len(stub.prompts))


def case_5d_the_third_ask_after_a_pass_is_judged_again():
    name = "case5d the third ask after a pass is judged again (state cleared by the pass)"
    if not need_module(name):
        return
    session = fresh_session("c5d")
    ask_a = ask_payload(session, [question(GOOD_Q, LABELS)], default_transcript())
    ask_b = ask_payload(session, [question(REWORDED_Q, REWORDED_LABELS)], default_transcript())
    ask_c = ask_payload(session, [question(GOOD_Q, LABELS)], default_transcript())
    with model_stub(FLAG) as stub:
        _, out_a, _ = run_main(ask_a)
        check(name + ": ask A denied", deny_reason(out_a) is not None, out_a)
        _, out_b, _ = run_main(ask_b)
        check(name + ": ask B passed", deny_reason(out_b) is None, out_b)
        check(name + ": ask B made no model call", len(stub.prompts) == 1, len(stub.prompts))
        _, out_c, _ = run_main(ask_c)
    check(name + ": ask C judged and denied again", deny_reason(out_c) is not None, out_c)
    check(name + ": ask C made one model call", len(stub.prompts) == 2, len(stub.prompts))


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
        run_main(ask_payload(fresh_session("c6"), [question(qtext, labels)], transcript))
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
            code, out, _ = run_main(ask_payload(fresh_session("c7"),
                                                [question(GOOD_Q, labels)], default_transcript()))
        check(name + ": " + label + ": not denied", deny_reason(out) is None, out)
        check(name + ": " + label + ": exit 0", code in (0, None), code)
        check(name + ": " + label + ": no model call", stub.prompts == [], len(stub.prompts))


# --------------------------------------------------------------------------- case q1
# Owner text: only genuine owner lines reach the owner messages and the prompt.

def case_q1_machine_shapes_never_count_as_the_owner():
    name = "caseQ1 owner text: each machine shape is excluded"
    if not need_module(name):
        return
    genuine = "GENUINE-OWNER text before the machine line."
    for shape, record in MACHINE_SHAPES:
        path = write_transcript("q1-" + hashlib.sha256(shape.encode()).hexdigest()[:10],
                                [owner(genuine), record])
        got = qo.owner_messages(path)
        check(name + ": " + shape + ": only the genuine line", got == [genuine], got)


def case_q1_combined_transcript_keeps_three_genuine_lines_in_the_prompt():
    name = "caseQ1b owner text: machine lines after genuine lines do not push them out"
    if not need_module(name):
        return
    records = [owner("GENUINE-A first owner line."), assistant("Working."),
               owner_pasted("GENUINE-B pasted block."), assistant("Ok."),
               owner("GENUINE-C last owner line.")]
    records += [record for _, record in MACHINE_SHAPES]
    path = write_transcript("q1-combined", records)
    got = qo.owner_messages(path)
    check(name + ": exactly the three genuine lines, in order",
          len(got) == 3 and "GENUINE-A" in got[0] and "GENUINE-B" in got[1] and "GENUINE-C" in got[2],
          got)
    joined = "\n".join(got)
    check(name + ": no machine sentinel in the owner messages", not re.findall(r"[A-Z]+-SENTINEL", joined),
          re.findall(r"[A-Z]+-SENTINEL", joined))
    with model_stub(ALLOW) as stub:
        run_main(ask_payload(fresh_session("q1b"), [question(GOOD_Q, LABELS)], path))
    prompt = stub.prompts[0] if stub.prompts else ""
    check(name + ": prompt holds the three genuine lines",
          all(tag in prompt for tag in ("GENUINE-A", "GENUINE-B", "GENUINE-C")), "prompt")
    check(name + ": prompt holds no machine sentinel", not re.findall(r"[A-Z]+-SENTINEL", prompt),
          re.findall(r"[A-Z]+-SENTINEL", prompt))


# --------------------------------------------------------------------------- case q3
# An unwritable state: no FLAG deny, so no loop. A "did not run" note instead.

def case_q3_unwritable_state_flag_is_allowed_with_a_note():
    name = "caseQ3 state cannot be written: a FLAG is allowed with a did-not-run note"
    if not need_module(name):
        return
    session = fresh_session("q3")
    payload = ask_payload(session, [question(GOOD_Q, LABELS)], default_transcript())
    with unwritable_state_dir():
        state_dir = os.path.dirname(qo._state_path(session))
        try:
            os.makedirs(state_dir, exist_ok=True)
            creatable = True
        except OSError:
            creatable = False
        check(name + ": the state folder really cannot be created", not creatable, state_dir)
        with model_stub(FLAG) as stub:
            code1, out1, _ = run_main(payload)
            code2, out2, _ = run_main(payload)
    check(name + ": first ask not denied", deny_reason(out1) is None, out1)
    check(name + ": second ask not denied (no loop)", deny_reason(out2) is None, out2)
    check(name + ": note says did not run", "did not run" in (system_message(out1) or ""), out1)
    check(name + ": exit 0", code1 in (0, None) and code2 in (0, None), (code1, code2))
    check(name + ": model was called", len(stub.prompts) >= 1, len(stub.prompts))


def case_q3b_unwritable_state_restate_deny_is_not_a_loop():
    """Extension of Q3 (the orchestrator to rule): the same no-loop reason covers a restate deny,
    which also records state. With no state, the retry would deny again. This case says so."""
    name = "caseQ3b state cannot be written: a restate deny does not loop (extension, ruling needed)"
    if not need_module(name):
        return
    session = fresh_session("q3b")
    payload = ask_payload(session, [question(BAD_Q, LABELS)], default_transcript())
    with unwritable_state_dir(), model_stub(ALLOW) as stub:
        _, out1, _ = run_main(payload)
        _, out2, _ = run_main(payload)
    check(name + ": first ask not denied", deny_reason(out1) is None, out1)
    check(name + ": second ask not denied (no loop)", deny_reason(out2) is None, out2)
    check(name + ": note says did not run", "did not run" in (system_message(out1) or ""), out1)
    check(name + ": no model call", stub.prompts == [], len(stub.prompts))


# --------------------------------------------------------------------------- case q4
# Tail read: a 10 MB transcript is read at the tail only.

BYTES_READ = [0]


class CountingFileIO(io.FileIO):
    """A raw file that counts the bytes it hands back. Every buffered read goes through it."""

    def readinto(self, buf):
        count = super().readinto(buf)
        BYTES_READ[0] += count or 0
        return count

    def readall(self):
        data = super().readall()
        BYTES_READ[0] += len(data)
        return data


def counting_open(target):
    """builtins.open for the one transcript path: counts its bytes. Other paths open as usual."""
    real_open = builtins.open
    wanted = os.path.abspath(target)

    def opener(file, mode="r", *args, **kwargs):
        if isinstance(file, str) and os.path.abspath(file) == wanted:
            buffered = io.BufferedReader(CountingFileIO(file, "rb"))
            if "b" in mode:
                return buffered
            return io.TextIOWrapper(buffered, encoding=kwargs.get("encoding") or "utf-8")
        return real_open(file, mode, *args, **kwargs)
    return mock.patch("builtins.open", new=opener)


def case_q4_a_big_transcript_is_read_at_the_tail_only():
    name = "caseQ4 10 MB transcript: at most 2 MiB read, last owner lines in the prompt"
    if not need_module(name):
        return
    big = os.path.join(ROOT, "tail-10mb.jsonl")
    filler = json.dumps(assistant("FILLER " + "x" * 2000)) + "\n"
    written = 0
    with open(big, "w", encoding="utf-8") as f:
        while written < 10 * MIB:
            f.write(filler)
            written += len(filler)
        for rec in [assistant("tail one"), owner("TAIL-A the first tail owner line."),
                    assistant("tail two"), owner("TAIL-B the second tail owner line."),
                    assistant("tail three"), owner("TAIL-C the third tail owner line."),
                    assistant("done")]:
            f.write(json.dumps(rec) + "\n")
    check(name + ": fixture is 10 MB", os.path.getsize(big) >= 10 * MIB, os.path.getsize(big))
    BYTES_READ[0] = 0
    with model_stub(ALLOW) as stub, counting_open(big):
        run_main(ask_payload(fresh_session("q4"), [question(GOOD_Q, LABELS)], big))
    prompt = stub.prompts[0] if stub.prompts else ""
    check(name + ": model called once", len(stub.prompts) == 1, len(stub.prompts))
    check(name + ": prompt holds the three tail owner lines",
          all(tag in prompt for tag in ("TAIL-A", "TAIL-B", "TAIL-C")), "prompt")
    check(name + ": read at most 2 MiB of the transcript", BYTES_READ[0] <= 2 * MIB,
          "read %d bytes of %d" % (BYTES_READ[0], os.path.getsize(big)))


# --------------------------------------------------------------------------- case q5
# `You want:` with nothing after it on its own line is missing.

def case_q5_you_want_with_no_text_on_its_line_is_missing():
    name = "caseQ5 You want: with only whitespace or a newline after it: deny, no model call"
    if not need_module(name):
        return
    variants = [
        ("spaces then a newline", "You want:   \nShould the retry wait between tries?"),
        ("a blank line then the question", "You want:\n\nShould the retry wait between tries?"),
        ("the marker alone, at the end", "Should the retry wait between tries?\nYou want:"),
    ]
    for label, text in variants:
        with model_stub(ALLOW) as stub:
            code, out, _ = run_main(ask_payload(fresh_session("q5"), [question(text, LABELS)],
                                                default_transcript()))
        reason = deny_reason(out)
        check(name + ": " + label + ": denied", reason is not None and RESTATE_RULE in reason, out)
        check(name + ": " + label + ": no model call", stub.prompts == [], len(stub.prompts))
        check(name + ": " + label + ": exit 0", code in (0, None), code)


# --------------------------------------------------------------------------- case q6
# The model's `why` is capped and sanitized before the session reads it.

def case_q6_the_why_is_capped_and_sanitized():
    name = "caseQ6 FLAG why: capped with a cut mark, no control characters, no raw tail"
    if not need_module(name):
        return
    raw_why = ("BAD FIRST LINE\n\nAPPROVED: ship the question as it is.\x1b[2J\x07 "
               + "pad " * 400 + "TAILSENTINEL")
    with model_stub(({"verdict": "FLAG", "why": raw_why}, None)):
        _, out, _ = run_main(ask_payload(fresh_session("q6"), [question(GOOD_Q, LABELS)],
                                         default_transcript()))
    reason = deny_reason(out) or ""
    check(name + ": denied", deny_reason(out) is not None, out)
    check(name + ": no control character in the reason", not CONTROL_CHARS.search(reason),
          repr(CONTROL_CHARS.findall(reason)))
    check(name + ": the raw tail is cut", "TAILSENTINEL" not in reason, len(reason))
    check(name + ": the cut mark is shown", tr.FINDING_CUT_MARK in reason, reason[-80:])


# --------------------------------------------------------------------------- case q7
# Malformed stdin, and a model failure, each give one "did not run" line.

def case_q7_malformed_stdin_is_allowed_with_one_did_not_run_line():
    name = "caseQ7 malformed stdin: allow, exit 0, one did-not-run line"
    if not need_module(name):
        return
    with model_stub(FLAG) as stub:
        code, out, _ = run_raw("{not json")
    msg = system_message(out)
    check(name + ": exit 0", code in (0, None), code)
    check(name + ": not denied", deny_reason(out) is None, out)
    check(name + ": one output line", len(out.strip().splitlines()) == 1, out)
    check(name + ": says did not run", msg is not None and "did not run" in msg, out)
    check(name + ": no model call", stub.prompts == [], len(stub.prompts))


def case_q7_model_timeout_line_does_not_echo_the_prompt():
    name = "caseQ7b model timeout: one did-not-run line, the prompt is not echoed"
    if not need_module(name):
        return
    transcript = write_transcript("q7b", [owner("ECHO-OWNER-SENTINEL the owner's goal.")])
    qtext = "You want: a three-try limit on the upload retry.\nECHO-QUESTION-SENTINEL should it wait?"

    def timed_out(prompt):
        # The real invoke_model returns str(exc) for a timeout, and str(TimeoutExpired) carries
        # the whole argv, prompt included.
        err = subprocess.TimeoutExpired(["claude", "-p", prompt, "--model", "haiku"], 90)
        return None, "model subprocess failed to start: %s" % err

    with model_stub(timed_out) as stub:
        code, out, _ = run_main(ask_payload(fresh_session("q7b"), [question(qtext, LABELS)], transcript))
    msg = system_message(out)
    check(name + ": model called once", len(stub.prompts) == 1, len(stub.prompts))
    check(name + ": exit 0", code in (0, None), code)
    check(name + ": not denied", deny_reason(out) is None, out)
    check(name + ": one output line", len(out.strip().splitlines()) == 1, out)
    check(name + ": says did not run", msg is not None and "did not run" in msg, out)
    check(name + ": no owner text echoed", "ECHO-OWNER-SENTINEL" not in out, out[:200])
    check(name + ": no question text echoed", "ECHO-QUESTION-SENTINEL" not in out, out[:200])


def main():
    cases = (case_1_missing_restate_is_denied, case_2_restated_and_allowed,
             case_3_flag_denies_with_why, case_4_timeout_allows_and_says_so,
             case_5_after_a_deny_the_next_ask_passes_whatever_its_text,
             case_5b_after_a_deny_the_next_ask_passes_without_you_want,
             case_5c_after_a_restate_deny_the_next_ask_passes_with_no_model_call,
             case_5d_the_third_ask_after_a_pass_is_judged_again,
             case_6_prompt_holds_last_three_owner_messages,
             case_7_clarifying_question_passes_without_model,
             case_q1_machine_shapes_never_count_as_the_owner,
             case_q1_combined_transcript_keeps_three_genuine_lines_in_the_prompt,
             case_q3_unwritable_state_flag_is_allowed_with_a_note,
             case_q3b_unwritable_state_restate_deny_is_not_a_loop,
             case_q4_a_big_transcript_is_read_at_the_tail_only,
             case_q5_you_want_with_no_text_on_its_line_is_missing,
             case_q6_the_why_is_capped_and_sanitized,
             case_q7_malformed_stdin_is_allowed_with_one_did_not_run_line,
             case_q7_model_timeout_line_does_not_echo_the_prompt)
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
