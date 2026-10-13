#!/usr/bin/env python3
"""Claude Code hook: reply judge (Stop). Judges the final reply against three style rules.

It replaces the `type: prompt` Stop judge, pulled 2026-10-12 because it ignored its own line
"if stop_hook_active is true, answer ok" and blocked done replies in a loop. A prompt hook
cannot exit on a field in code. This command hook does: `stop_hook_active` true means this Stop
is already a rewrite, so it exits 0 at once and never calls the model.

The model call is `decision_watch.invoke_model`, the one home for it: Haiku at effort xhigh,
`--safe-mode`, no tools, and an empty config dir and scratch cwd, so the child cannot fire this
hook again. This file passes its own accepted answer, `{"ok": true|false}`.

Fail open. Any model error, timeout or odd answer prints one line on stderr, exits 0, and
blocks nothing. A finding never blocks: the hook runs async, and a finding prints
`{"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": NOTE}}` on stdout, which the
session reads as a note on the next turn.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import decision_watch  # noqa: E402

OK_SHAPE = {"ok": (True, False)}
MODEL_TIMEOUT = 20  # measured 6.6, 7.0, 8.0 s per run on this machine; the Stop entry allows 25
REPLY_MAX = 12000  # one argv element: Windows caps the command line near 32,767 characters

INSTRUCTIONS = (
    "Judge the final reply below against three rules. "
    "output-start-with-point: the first sentence is the point, not a preamble. "
    "style-cut-narration: cut narration and recaps; narration means lines like \"I will now...\" or \"Let me...\"; "
    "a Done/Deviations/Input Needed/Next report is never narration. "
    "output-never-paste-passing-output: a passing run gets a verdict, not its pasted output. "
    "Running background work never makes a reply unfinished. "
    "Block only on a clear breach; when unsure answer {\"ok\": true}. "
    "Reply JSON only: {\"ok\": true} or {\"ok\": false, \"reason\": \"<rule id and the fix, one line>\"}."
)


def build_prompt(reply):
    if len(reply) > REPLY_MAX:
        half = REPLY_MAX // 2
        reply = reply[:half] + "\n[middle of the reply cut for length]\n" + reply[-half:]
    return "%s\n\nReply:\n%s" % (INSTRUCTIONS, reply)


def main():
    try:
        hook = json.load(sys.stdin)
        if hook.get("stop_hook_active"):
            return 0
        reply = hook.get("last_assistant_message")
        if not isinstance(reply, str) or not reply.strip():
            return 0
        verdict, error = decision_watch.invoke_model(
            build_prompt(reply), timeout=MODEL_TIMEOUT, shape=OK_SHAPE)
    except Exception as exc:
        error, verdict = "%s: %s" % (type(exc).__name__, exc), None
    if error:
        print("reply judge failed open: %s" % " ".join(error.split()), file=sys.stderr)
        return 0
    if verdict.get("ok") is False:
        reason = verdict.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            reason = "reply judge: the reply breaks a style rule."
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": reason}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
