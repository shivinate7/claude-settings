#!/usr/bin/env python3
"""PreToolUse hook for AskUserQuestion: each question passes an outcome check first.

Spec: decisions/question-outcome-check.md. Rule: style-question-restates-goal.

Per question with two or more options (a clarifying question passes first):
- No `You want:` line: deny, no model call.
- Else one model call (decision_watch.invoke_model, the one model caller) judges whether the
  `You want:` line matches the owner's last messages, whether each option serves that goal,
  and whether a better option is missing. FLAG denies, and the reason goes to the session.
- After a deny, the next AskUserQuestion in the session passes with no model call and clears
  the state, so no deny can loop. When the state cannot be written, nothing is denied.
- A failed model call, unreadable transcript, or malformed input lets the question through,
  with one systemMessage saying the check did not run. It never echoes the prompt.

Deny: stdout one PreToolUse deny JSON, exit 0. Allow: empty stdout, exit 0.
"""
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "lint"))

from decision_watch import invoke_model  # noqa: E402  looked up at call time, in main()
from _transcript import is_last_human, safe_finding_text, tail_records  # noqa: E402

RULE = "style-question-restates-goal"
# THE TIME BUDGET. One model call per ask, so the settings.json PreToolUse entry for this
# hook carries "timeout": 105 = MODEL_TIMEOUT + 15 seconds margin. Change both together.
MODEL_TIMEOUT = 90
OWNER_MESSAGES = 3
MESSAGE_MAX = 1500
TAIL_BYTES = 2 * 1024 * 1024
MACHINE_TAGS = ("<system-reminder>", "<task-notification>")
YOU_WANT = re.compile(r"^[ 	]*You want:[ 	]*\S", re.MULTILINE)

PROMPT = (
    "You check a question an assistant is about to put to its owner. The owner's goal, read "
    "from their last messages, is below. Check three things: (1) does the `You want:` line "
    "match that goal; (2) does each option serve it; (3) is an option that serves it better "
    "missing. Be conservative: FLAG only a clear miss. Reply with one JSON object only: "
    '{"verdict": "ALLOW"} or {"verdict": "FLAG", "why": "<one line: what misses, and the fix>"}.'
)


def _owner_text(rec):
    """The genuine owner text of one transcript record, or "". A machine line is "": isMeta,
    a compact summary, a sidechain line, an origin other than human, a tool_result, and any
    block that opens with a harness tag."""
    if not is_last_human(rec) or rec.get("isMeta") or rec.get("isCompactSummary"):
        return ""
    origin = rec.get("origin")
    if origin is not None and (not isinstance(origin, dict) or origin.get("kind") != "human"):
        return ""
    content = rec["message"]["content"]
    blocks = [content] if isinstance(content, str) else [
        b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
    return "\n".join(b for b in blocks if not b.lstrip().startswith(MACHINE_TAGS)).strip()


def owner_messages(path):
    """The last OWNER_MESSAGES genuine owner messages, oldest first, read from the last
    TAIL_BYTES of the transcript. Raises OSError."""
    out = []
    for rec in tail_records(path, TAIL_BYTES):
        text = _owner_text(rec)
        if text:
            out.append(text[:MESSAGE_MAX])
            if len(out) == OWNER_MESSAGES:
                break
    return out[::-1]


def _state_path(session_id):
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    key = hashlib.sha256(str(session_id).encode("utf-8", "replace")).hexdigest()
    return os.path.join(base, "state", "question-outcome", key + ".json")


def _mark_denied(path):
    """Record that a deny was sent. False when the state cannot be written: then no deny may
    go out, because the retry could not pass and the deny would loop."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"denied": True}, f)
        return True
    except Exception:
        return False


def _take_denied(path):
    """True once after a deny: the next ask passes. Reading it clears it."""
    if not os.path.exists(path):
        return False
    try:
        os.remove(path)
    except OSError:
        pass
    return True


def _emit(obj):
    print(json.dumps(obj))
    sys.exit(0)


def _deny(reason):
    _emit({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                  "permissionDecisionReason": reason}})


def _options(q):
    return [o.get("label", "") for o in q.get("options") or [] if isinstance(o, dict)]


def _did_not_run(why):
    _emit({"systemMessage": "Question outcome check did not run: %s" % why})


def main():
    try:
        hook = json.load(sys.stdin)
        questions = [q for q in hook["tool_input"]["questions"] if isinstance(q, dict)]
    except Exception:
        _did_not_run("the hook input was not readable.")
    state = _state_path(hook.get("session_id"))
    if _take_denied(state):
        sys.exit(0)  # the retry after a deny passes, whatever its text
    todo = [(str(q.get("question", "")), _options(q)) for q in questions]
    todo = [(t, ls) for t, ls in todo if len(ls) >= 2]
    missing = [t for t, _ in todo if not YOU_WANT.search(t)]
    if missing:
        if not _mark_denied(state):
            _did_not_run("the state could not be written, so no deny was sent.")
        _deny("%s: open the question with one line `You want: <the goal, in the owner's "
              "terms>`. Missing on: %s" % (RULE, "; ".join(t[:80] for t in missing)))
    if not todo:
        sys.exit(0)

    try:
        owner = owner_messages(hook.get("transcript_path"))
    except Exception:
        owner = []
    if not owner:
        _did_not_run("no owner messages readable.")
    body = "\n\n".join("Question: %s\nOptions: %s" % (t, " | ".join(ls)) for t, ls in todo)
    prompt = "%s\n\nOwner's last messages:\n%s\n\n%s" % (PROMPT, "\n---\n".join(owner), body)
    verdict, _err = invoke_model(prompt, timeout=MODEL_TIMEOUT)  # _err can hold the prompt: never printed
    if not isinstance(verdict, dict):
        _did_not_run("the model call failed.")
    if verdict.get("verdict") == "FLAG":
        if not _mark_denied(state):
            _did_not_run("the state could not be written, so no deny was sent.")
        _deny("Question outcome check: %s Fix the question, then ask again."
              % safe_finding_text(str(verdict.get("why", ""))))
    sys.exit(0)


if __name__ == "__main__":
    main()
