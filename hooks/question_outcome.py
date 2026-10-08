#!/usr/bin/env python3
"""PreToolUse hook for AskUserQuestion: each question passes an outcome check first.

Spec: decisions/question-outcome-check.md. Rule: style-question-restates-goal.

Per question with two or more options (a clarifying question passes first):
- No `You want:` line: deny, no model call.
- Else one model call (decision_watch.invoke_model, the one model caller) judges whether the
  `You want:` line matches the owner's last messages, whether each option serves that goal,
  and whether a better option is missing. FLAG denies, and the reason goes to the session.
- One deny per question per session, restate denies too, so no deny can loop. The next try
  of the same question passes.
- A failed model call or unreadable transcript lets the question through, with one
  systemMessage saying the check did not run.

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
from _transcript import read_transcript, is_last_human  # noqa: E402

RULE = "style-question-restates-goal"
# THE TIME BUDGET. One model call per ask, so the settings.json PreToolUse entry for this
# hook carries "timeout": 105 = MODEL_TIMEOUT + 15 seconds margin. Change both together.
MODEL_TIMEOUT = 90
OWNER_MESSAGES = 3
MESSAGE_MAX = 1500
YOU_WANT = re.compile(r"^\s*You want:\s*\S", re.MULTILINE)

PROMPT = (
    "You check a question an assistant is about to put to its owner. The owner's goal, read "
    "from their last messages, is below. Check three things: (1) does the `You want:` line "
    "match that goal; (2) does each option serve it; (3) is an option that serves it better "
    "missing. Be conservative: FLAG only a clear miss. Reply with one JSON object only: "
    '{"verdict": "ALLOW"} or {"verdict": "FLAG", "why": "<one line: what misses, and the fix>"}.'
)


def owner_messages(path):
    """The last OWNER_MESSAGES genuine owner messages, oldest first. Raises OSError."""
    out = []
    for rec in read_transcript(path):
        if not is_last_human(rec):
            continue
        content = rec["message"]["content"]
        blocks = [content] if isinstance(content, str) else [
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        text = "\n".join(b for b in blocks if not b.lstrip().startswith("<system-reminder>")).strip()
        if text:
            out.append(text[:MESSAGE_MAX])
    return out[-OWNER_MESSAGES:]


def _state_path(session_id):
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    key = hashlib.sha256(str(session_id).encode("utf-8", "replace")).hexdigest()
    return os.path.join(base, "state", "question-outcome", key + ".json")


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return set(x for x in data if isinstance(x, str))
    except Exception:
        return set()


def _save(path, keys):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(sorted(keys), f)
        os.replace(path + ".tmp", path)
    except Exception:
        pass  # a lost write re-checks the question once more, never loops a deny


def _emit(obj):
    print(json.dumps(obj))
    sys.exit(0)


def _deny(reason):
    _emit({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                  "permissionDecisionReason": reason}})


def _options(q):
    return [o.get("label", "") for o in q.get("options") or [] if isinstance(o, dict)]


def main():
    try:
        hook = json.load(sys.stdin)
        questions = [q for q in hook["tool_input"]["questions"] if isinstance(q, dict)]
    except Exception:
        sys.exit(0)  # not an AskUserQuestion payload we can read: nothing to judge
    state = _state_path(hook.get("session_id"))
    seen = _load(state)
    todo = []  # (key, question text, labels) for each real, not yet denied question
    for q in questions:
        labels = _options(q)
        text = str(q.get("question", ""))
        key = hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()
        if len(labels) < 2 or key in seen:
            continue
        todo.append((key, text, labels))

    missing = [(k, t) for k, t, _ in todo if not YOU_WANT.search(t)]
    if missing:
        _save(state, seen | {k for k, _ in missing})
        _deny("%s: open the question with one line `You want: <the goal, in the owner's "
              "terms>`. Missing on: %s" % (RULE, "; ".join(t[:80] for _, t in missing)))
    if not todo:
        sys.exit(0)

    try:
        owner = owner_messages(hook.get("transcript_path"))
    except Exception:
        owner = []
    if not owner:
        _emit({"systemMessage": "Question outcome check did not run: no owner messages readable."})
    body = "\n\n".join("Question: %s\nOptions: %s" % (t, " | ".join(ls)) for _, t, ls in todo)
    prompt = "%s\n\nOwner's last messages:\n%s\n\n%s" % (PROMPT, "\n---\n".join(owner), body)
    verdict, err = invoke_model(prompt, timeout=MODEL_TIMEOUT)
    if verdict is None:
        _emit({"systemMessage": "Question outcome check did not run: %s" % err})
    if verdict.get("verdict") == "FLAG":
        _save(state, seen | {k for k, _, _ in todo})
        _deny("Question outcome check: %s Fix the question, then ask again." % verdict.get("why", ""))
    sys.exit(0)


if __name__ == "__main__":
    main()
