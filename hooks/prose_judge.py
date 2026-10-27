#!/usr/bin/env python3
"""PreToolUse judge for an Edit or Write of prose, against speak-rewrite-superseded-in-place and
rulings-declare-kind. One command hook replaces the two `type: prompt` hooks on Edit and Write: a
prompt hook cannot look at the path, so it judged every file.

Only a path with a `decisions` folder segment (either slash, any case) is judged. Any other
path exits 0 at once with no output and no model call. The model call is `decision_watch.invoke_model`,
the one home for it.

A model answer {"ok": false, "reason": R} refuses through guard_core.refuse(), so an owner override lifts it
(decision owner-override). The deny holds R. Any model error, timeout or
odd answer fails open: no output, exit 0, so a judge outage never stops an edit of a Markdown file.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def invoke_model(*args, **kwargs):
    """The model call. decision_watch loads on the first call, so a skipped path never pays for it.
    A module-level name, so a test can replace it."""
    from decision_watch import invoke_model as home
    return home(*args, **kwargs)


RULE = "prose-judge"
MODEL_TIMEOUT = 40  # the settings.json row allows 45
OK_SHAPE = {"ok": (True, False)}

COMMON = (
    "Rule: speak-rewrite-superseded-in-place (superseded text is rewritten in place; no story, no old quote, "
    "and no superseded ruling kept beside the new one). A record may state a current fact with its history in "
    "one clause; that is not a breach. "
)
TAIL = (
    "Block only on a clear breach; when unsure answer {\"ok\": true}. Reply JSON only: {\"ok\": true} or "
    "{\"ok\": false, \"reason\": \"<rule id and the fix, one line>\"}."
)
RULES = {
    "Edit": COMMON + (
        "Rule: rulings-declare-kind (refuse only an edit whose new text deletes a `Kind:`, `Plan:` or `Home:` "
        "line, or adds a ruling section with no `Kind:` line in the same text; you see only the changed text, "
        "so never refuse for a Kind line you cannot see). "
    ) + TAIL,
    "Write": COMMON + (
        "Rule: rulings-declare-kind (refuse a decision record that has no `Kind: build` with "
        "`Plan: <path>#<slug> (<platform>)` lines, or `Kind: process` with a `Home:` line). "
    ) + TAIL,
}


def is_prose(path):
    parts = path.replace("\\", "/").lower().split("/")
    return "decisions" in parts[:-1]


def refuse(payload, tool, reason):
    """Refuse through guard_core.refuse(), which lets an owner override lift it. refuse() exits, so its
    exit is returned to main()'s caller as the hook's exit code."""
    try:
        import guard_core
        guard_core.set_log_session(payload.get("session_id"))
        guard_core.set_override_context(payload.get("session_id"), payload.get("agent_id"))
        guard_core.set_override_veto(lambda: False)  # a prose rule is no act that no override lifts
        guard_core.refuse(tool, "deny", RULE, reason, "")
    except SystemExit as done:
        return done.code or 0
    except Exception:  # no guard_core: no override can be read, so the refusal stands
        pass
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                             "permissionDecision": "deny",
                                             "permissionDecisionReason": RULE + ": " + reason}}))
    return 0


def main():
    try:
        hook = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
        tool, args = hook.get("tool_name"), hook.get("tool_input")
        path = args.get("file_path")
        if tool not in RULES or not isinstance(path, str) or not is_prose(path):
            return 0
        if tool == "Edit":
            change = "old_string: %s\nnew_string: %s" % (args.get("old_string"), args.get("new_string"))
        else:
            change = "content: %s" % args.get("content")
        prompt = "Judge this edit to a file: %s\n%s\nfile_path: %s\n%s" % (tool, RULES[tool], path, change)
        verdict, error = invoke_model(prompt, timeout=MODEL_TIMEOUT, shape=OK_SHAPE)
    except Exception as exc:
        print("prose judge failed open: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return 0
    if error:
        print("prose judge failed open: %s" % " ".join(str(error).split()), file=sys.stderr)
        return 0
    if verdict.get("ok") is False:
        reason = verdict.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            reason = "prose judge: the edit breaks speak-rewrite-superseded-in-place."
        return refuse(hook, tool, reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
