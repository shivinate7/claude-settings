#!/usr/bin/env python3
"""PreToolUse hook for AskUserQuestion: each question passes an outcome check first.

Spec: decisions/question-outcome-check.md. Rule: style-question-restates-goal.

Per question with two or more options (a clarifying question passes first):
- No `Goal:` line, or no `Problem:` line: deny, no model call.
- Else one model call (decision_watch.invoke_model, the one model caller) judges whether the
  `Goal:` line matches the owner's last messages, whether each option serves that goal,
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
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "lint"))

from decision_watch import invoke_model  # noqa: E402  looked up at call time, in main()
from _transcript import is_last_human, safe_finding_text, tail_records  # noqa: E402
from rule_audit import ANCHOR_RE  # noqa: E402  the one anchor parser (lint/ lands beside hooks/)

RULE = "style-question-restates-goal"
# THE TIME BUDGET. One model call per ask, so the settings.json PreToolUse entry for this
# hook carries "timeout": 105 = MODEL_TIMEOUT + 15 seconds margin. Change both together.
MODEL_TIMEOUT = 90
OWNER_MESSAGES = 3
MESSAGE_MAX = 1500
STATE_MAX_AGE = 30 * 60  # seconds; an older deny state is ignored
TAIL_BYTES = 2 * 1024 * 1024
MACHINE_TAGS = ("<system-reminder>", "<task-notification>")
# The two labels. Each sits in its style-file rule bullet; every use below reads these.
GOAL_LABEL = "Goal:"
PROBLEM_LABEL = "Problem:"
GOAL_LINE = re.compile(r"^[ \t]*%s[ \t]*\S" % re.escape(GOAL_LABEL), re.MULTILINE)
PROBLEM_LINE = re.compile(r"^[ \t]*%s[ \t]*\S" % re.escape(PROBLEM_LABEL), re.MULTILINE)

STYLE_FILE = os.path.join(HERE, "..", "output-styles", "shiv-stylisms.md")
PROBLEM_RULE = "style-question-states-problem"
STYLE_RULES = (PROBLEM_RULE, RULE)

PROMPT = (
    "You check a question an assistant is about to put to its owner. The owner's goal, read "
    "from their last messages, is below. The standard question has a `%s` line, a `%s` line, "
    "and options. Check three things: (1) does the `%s` line "
    "match that goal; (2) does each option serve it; (3) is an option that serves it better "
    "missing. A goal line is a paraphrase of the goal in plain words; a paraphrase is not grounds "
    "to deny or flag. Be conservative: FLAG only a clear miss. Reply with one JSON object only: "
    '{"verdict": "ALLOW"} or {"verdict": "FLAG", "why": "<one line: what misses, and the fix>"}.'
    % (PROBLEM_LABEL, GOAL_LABEL, GOAL_LABEL)
)


def _style_rules():
    """The two question-rule bullets of the style file, marker removed, whitespace collapsed,
    one per line. The check goes on without what is missing, and one stderr line names the
    missing file or anchor. A marker counts only at the end of a line, so a quoted one is no rule."""
    try:
        with open(STYLE_FILE, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except Exception:
        print("question_outcome: style file not readable: %s" % os.path.basename(STYLE_FILE),
              file=sys.stderr)
        return ""
    out = []
    for rule in STYLE_RULES:
        for i, line in enumerate(lines):
            m = next((m for m in ANCHOR_RE.finditer(line)
                      if m.group(1) == rule and not line[m.end():].strip()), None)
            if m:
                start = i
                while start > 0 and not lines[start].startswith("- "):
                    start -= 1
                body = "\n".join(lines[start:i] + [line[:m.start()]])
                out.append(" ".join(body[2:].split()))
                break
        else:
            print("question_outcome: style rule anchor not found: %s" % rule, file=sys.stderr)
    return "\n".join("- " + r for r in out)


def _asked_ids(records):
    """The ids of the AskUserQuestion tool_use blocks in main-chain assistant records."""
    ids = set()
    for rec in records:
        content = (rec.get("message") or {}).get("content")
        if rec.get("type") == "assistant" and not rec.get("isSidechain") and isinstance(content, list):
            ids.update(b.get("id") for b in content if isinstance(b, dict)
                       and b.get("type") == "tool_use" and b.get("name") == "AskUserQuestion")
    return ids


def _answer_text(rec, asked):
    """The owner's answers in an AskUserQuestion tool result, or "". Counts only a result whose
    tool_use_id is in ASKED (see _asked_ids). Its toolUseResult holds the `answers` map; a
    multiSelect answer is a list, joined with commas."""
    if rec.get("type") != "user" or rec.get("isSidechain") or rec.get("isMeta"):
        return ""
    result = rec.get("toolUseResult")
    answers = result.get("answers") if isinstance(result, dict) else None
    if not isinstance(answers, dict) or not isinstance(result.get("questions"), list):
        return ""
    content = (rec.get("message") or {}).get("content")
    if not isinstance(content, list) or not any(
            isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id") in asked
            for b in content):
        return ""
    lines = []
    for q, a in answers.items():
        if isinstance(a, list):
            a = ", ".join(x for x in a if isinstance(x, str))
        if isinstance(q, str) and isinstance(a, str):
            lines.append("%s: %s" % (q, a))
    return "\n".join(lines).strip()


def _owner_text(rec, asked=frozenset()):
    """The genuine owner text of one transcript record, or "". A machine line is "": isMeta,
    a compact summary, a sidechain line, an origin other than human, a tool_result (except an
    AskUserQuestion answer, the owner's own), and any block that opens with a harness tag."""
    answer = _answer_text(rec, asked)
    if answer:
        return answer
    if not is_last_human(rec) or rec.get("isMeta") or rec.get("isCompactSummary"):
        return ""
    origin = rec.get("origin")
    if not isinstance(origin, dict) or origin.get("kind") != "human":
        return ""
    content = rec["message"]["content"]
    blocks = [content] if isinstance(content, str) else [
        b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
    return "\n".join(b for b in blocks if not b.lstrip().startswith(MACHINE_TAGS)).strip()


def owner_messages(path):
    """The last OWNER_MESSAGES genuine owner messages, oldest first, read from the last
    TAIL_BYTES of the transcript. Raises OSError."""
    out = []
    records = list(tail_records(path, TAIL_BYTES))
    asked = _asked_ids(records)
    for rec in records:
        text = _owner_text(rec, asked)
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
    """True once after a deny: the next ask passes. Reading it clears it. A state older than
    STATE_MAX_AGE seconds (file mtime) is stale: removed if possible, else ignored. Raises
    OSError when a fresh state cannot be cleared: it would pass every later ask."""
    try:
        age = time.time() - os.path.getmtime(path)
    except OSError:
        return False
    try:
        os.remove(path)
    except FileNotFoundError:
        return False
    except OSError:
        if age > STATE_MAX_AGE:
            return False  # stale and stuck: ignored, the ask is judged
        raise
    return age <= STATE_MAX_AGE


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
        hook = json.loads(sys.stdin.buffer.read())
        questions = [q for q in hook["tool_input"]["questions"] if isinstance(q, dict)]
    except Exception:
        _did_not_run("the hook input was not readable.")
    state = _state_path(hook.get("session_id"))
    try:
        passed = _take_denied(state)
    except OSError:
        _did_not_run("the deny state could not be cleared, so the question was not judged.")
    if passed:
        sys.exit(0)  # the retry after a deny passes, whatever its text
    todo = [(str(q.get("question", "")), _options(q)) for q in questions]
    todo = [(t, ls) for t, ls in todo if len(ls) >= 2]
    absent = [(t, [lab for lab, rx in ((GOAL_LABEL, GOAL_LINE), (PROBLEM_LABEL, PROBLEM_LINE))
                   if not rx.search(t)]) for t, _ in todo]
    absent = [(t, labs) for t, labs in absent if labs]
    if absent:
        if not _mark_denied(state):
            _did_not_run("the state could not be written, so no deny was sent.")
        labs = [lab for lab in (GOAL_LABEL, PROBLEM_LABEL) if any(lab in l for _, l in absent)]
        _deny("%s: each question needs a line that opens with %s (`%s <the goal, in the owner's "
              "terms>`, `%s <the problem, in one plain sentence>`). Missing on: %s"
              % (RULE, " and ".join("`%s`" % l for l in labs), GOAL_LABEL, PROBLEM_LABEL,
                 safe_finding_text("; ".join("%s (no %s)" % (t[:80], " or ".join(l)) for t, l in absent))))
    if not todo:
        sys.exit(0)

    try:
        owner = owner_messages(hook.get("transcript_path"))
    except Exception:
        owner = []
    if not owner:
        _did_not_run("no owner messages readable.")
    body = "\n\n".join("Question: %s\nOptions: %s" % (t, " | ".join(ls)) for t, ls in todo)
    rules = _style_rules()
    rules = "Question rules, from the style file:\n%s\n\n" % rules if rules else ""
    prompt = "%s\n\n%sOwner's last messages:\n%s\n\n%s" % (PROMPT, rules, "\n---\n".join(owner), body)
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
