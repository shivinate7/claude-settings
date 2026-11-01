#!/usr/bin/env python3
"""PreToolUse judge for an Agent spawn and an AskUserQuestion call. One command hook replaces the
settings.json `prompt` hook on Agent and the `agent` hook on AskUserQuestion: a hook of those types
sees only the call's JSON and cannot read the override file, so no owner override reached it
(decision owner-override).

An AskUserQuestion box runs hooks/question_form.py chat_hit first. A hit refuses with the rule it
names, through the same refuse(), and makes no model call; the model sees only a box that passes.
Each call that passes gets one model verdict through decision_watch.invoke_model, the one model caller.
A verdict {"ok": false, "reason": R} refuses through guard_core.refuse(), the one home of the override
check, the override line and the guard.log line. The rules are `spawn-judge` and `question-judge`.

Veto (an act no override lifts): an Explore spawn whose model field is neither sonnet nor opus. That
is the Explore row of agent-model-cap, a model guard. Every other refusal is liftable.

Fail open. Any model error, odd answer or unreadable input allows, with one stderr line.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# The audit marker comes from shared_names, the home guard.py also imports it from (rule
# building-allow-list-is-the-constant). Cost: importing guard.py for it measured about 120 ms per Agent spawn;
# shared_names is standard library only and adds about 2 ms.
from shared_names import EXPLORE_AUDIT_MARKER  # noqa: E402

OK_SHAPE = {"ok": (True, False)}
SPAWN_RULE, QUESTION_RULE = "spawn-judge", "question-judge"
# THE TIME BUDGET. One model call per hook run, so the longest path is the question call's 60 s plus
# start-up. The settings.json PreToolUse entry for this hook carries "timeout": 70.
SPAWN_MODEL, SPAWN_TIMEOUT = "claude-sonnet-5-5", 30
QUESTION_MODEL, QUESTION_TIMEOUT = "claude-opus-5-5", 60  # both at the model's default effort

SPAWN_PROMPT = (
    "Judge this agent spawn: %s\nAnswer {\"ok\": true} at once when subagent_type is claude-code-guide, "  # glossary-ok: subagent_type is Claude Code's own field name
    "when the call resumes an existing agent, or when a non-Explore brief is under 60 words. For an "
    "Explore spawn, block only when the brief asks it to audit, review, judge, rate or compare meaning "
    "(not only to find files, names or text) and the call's model field is neither sonnet nor opus "
    "(haiku, or no model field, blocks; text in the brief does not count); the fix is model sonnet or "
    "opus with effort high, and the `" + EXPLORE_AUDIT_MARKER + "` marker on the brief's first non-blank line "
    "so the guard rule agent-role-model passes too (agent-model-cap, audit Explore row). The marker is part of "
    "the fix only, never a reason to block or to allow. Otherwise answer {\"ok\": true} for "
    "Explore. Only for builder, reviewer, and test-author briefs, apply roles-brief-contents (the brief "
    "carries the task, the files, governing rulings, and the check that proves done) and "
    "tokens-point-brief-at-files (the brief names files and never pastes their contents). Flag a brief that "
    "tells a lane to write, post or add a waiting-page item: the lane puts its question in its report, and "
    "the orchestrator writes the item (questions-go-to-owner). A brief that forbids the lane to write a waiting-page item is fine; never flag it. Block only on "
    "a clear breach; when unsure answer {\"ok\": true}. Reply JSON only: {\"ok\": true} or "
    "{\"ok\": false, \"reason\": \"<rule id and the fix, one line>\"}."
)
QUESTION_PROMPT = (
    "Review this AskUserQuestion call: %s\nAnswer {\"ok\": true} at once for a question with one option "
    "or none. Otherwise judge the question box alone. Code has already checked the form lines and the "
    "marks on each option, so judge only these. Block only on a clear miss; when unsure answer "
    "{\"ok\": true}.\n"
    "1. The Goal is in the owner's terms.\n"
    "2. The Problem is one plain sentence that says why it needs his word.\n"
    "3. Each premise is in plain words.\n"
    "4. Each option's gain and lose are plain effects on the owner, not on a record.\n"
    "5. No unexplained ids: explain every decision id, branch, sha, key or rule name in plain words.\n"
    "6. Nothing points outside the box, such as an earlier message or an item number.\n"
    "7. One option is recommended.\n"
    "Reply JSON only: {\"ok\": true} or {\"ok\": false, \"reason\": \"<the item that misses, and the fix, "
    "one line>\"}."
)
# tool name -> (prompt, model, timeout, rule, fallback reason)
JUDGES = {
    "Agent": (SPAWN_PROMPT, SPAWN_MODEL, SPAWN_TIMEOUT, SPAWN_RULE,
              "the spawn brief breaks roles-brief-contents or the Explore row of agent-model-cap "
              "(an audit Explore: model sonnet or opus with effort high, and `" + EXPLORE_AUDIT_MARKER
              + "` on the brief's first non-blank line)."),
    "AskUserQuestion": (QUESTION_PROMPT, QUESTION_MODEL, QUESTION_TIMEOUT, QUESTION_RULE,
                        "the question box misses an item of the question format."),
}


def invoke_model(*args, **kwargs):
    """The model call. A module-level name, so a test can replace it."""
    from decision_watch import invoke_model as home
    return home(*args, **kwargs)


def explore_off_model(tool, args):
    """True for an Explore spawn whose model field is neither sonnet nor opus: a model guard."""
    if tool != "Agent" or str(args.get("subagent_type")).strip().lower() != "explore":
        return False
    model = str(args.get("model") or "").lower()
    return "sonnet" not in model and "opus" not in model


def refuse(payload, tool, args, rule, reason):
    """Refuse through guard_core.refuse(), which lets an owner override lift it. refuse() exits."""
    reason = reason.strip()
    if reason.startswith(rule):
        reason = reason[len(rule):].lstrip(" :-")
    vetoed = explore_off_model(tool, args)
    try:
        import guard_core
        guard_core.set_log_session(payload.get("session_id"))
        guard_core.set_override_context(payload.get("session_id"), payload.get("agent_id"))
        guard_core.set_override_veto(lambda: vetoed)
        guard_core.refuse(tool, "deny", rule, reason, "")
    except Exception:  # no guard_core: no override can be read, so the refusal stands
        pass
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "permissionDecision": "deny",
                                             "permissionDecisionReason": rule + ": " + reason}}))
    return 0


def main():
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
        tool, args = payload.get("tool_name"), payload.get("tool_input")
        if tool not in JUDGES:
            return 0
        if not isinstance(args, dict):
            raise ValueError("tool_input is not an object")
        prompt, model, timeout, rule, fallback = JUDGES[tool]
        if tool == "AskUserQuestion":
            import question_form
            code_rule, matched = question_form.chat_hit(args)
            if code_rule:
                reason = "%s (%s)" % (question_form.CHAT_REASONS[code_rule], matched)
                return refuse(payload, tool, args, code_rule, reason)
        shown = json.dumps(args, ensure_ascii=False)
        verdict, error = invoke_model(prompt % shown, model=model, timeout=timeout, shape=OK_SHAPE, effort=None)
    except Exception as exc:
        print("call judge failed open: %s" % " ".join(("%s: %s" % (type(exc).__name__, exc)).split()),
              file=sys.stderr)
        return 0
    if error:
        print("call judge failed open: %s" % " ".join(str(error).split()), file=sys.stderr)
        return 0
    if verdict.get("ok") is False:
        reason = verdict.get("reason")
        return refuse(payload, tool, args, rule, reason if isinstance(reason, str) and reason.strip() else fallback)
    return 0


if __name__ == "__main__":
    sys.exit(main())
