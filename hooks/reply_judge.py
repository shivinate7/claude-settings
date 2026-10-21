#!/usr/bin/env python3
"""At Stop, a model (Haiku) judges the final reply against three style rules. It runs on every fifth Stop and never blocks. A finding comes back as a note on the next turn.

It is a command hook, not a `type: prompt` hook, because a prompt hook cannot exit on a field
in code. This hook does: `stop_hook_active` true means this Stop is already a rewrite, so it
exits 0 at once and never calls the model.

The model call is `decision_watch.invoke_model`, the one home for it: Haiku at effort xhigh,
`--safe-mode`, no tools, and an empty config dir and scratch cwd, so the child cannot fire this
hook again. This file passes its own accepted answer, `{"ok": true|false}`.

Sampling: the judge runs on Stop n of a session (counting only Stops that carry a reply) when (n - 1) % 5 == 0. A skipped Stop returns
at once with no model call and no output. The count is a file per session under the state folder.

Fail open. Any model error, timeout or odd answer prints one line on stderr, exits 0, and
blocks nothing. A finding never blocks: the hook runs async, and a finding prints
`{"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": NOTE}}` on stdout, which the
session reads as a note on the next turn.
"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

OK_SHAPE = {"ok": (True, False)}
MODEL_TIMEOUT = 20  # the Stop entry allows 25
SAMPLE_EVERY = 5  # the judge runs on Stops 1, 6, 11 of a session
STATE_DIR_NAME = "state"  # the same folder name as decision_watch.SEEN_DIR_NAME
COUNT_SUB = "reply-judge"  # <config dir>/state/reply-judge/<sha256 of session_id>.count
REPLY_MAX = 12000  # the prompt rides stdin, so no argv cap; the clip bounds cost and latency only (unmeasured)

INSTRUCTIONS = (
    "Judge the final reply below against three rules. "
    "output-start-with-point: the first sentence is the point, not a preamble. "
    "style-cut-narration: cut narration and recaps; narration means lines like \"I will now...\" or \"Let me...\"; "
    "a Done/Deviations/Input Needed/Next report is never narration. "
    "output-never-paste-passing-output: a passing run gets a verdict, not its pasted output. "
    "Running background work never makes a reply unfinished. "
    "Flag only on a clear breach; when unsure answer {\"ok\": true}. "
    "Reply JSON only: {\"ok\": true} or {\"ok\": false, \"reason\": \"<rule id and the fix, one line>\"}."
)


def build_prompt(reply):
    if len(reply) > REPLY_MAX:
        half = REPLY_MAX // 2
        reply = reply[:half] + "\n[middle of the reply cut for length]\n" + reply[-half:]
    return "%s\n\nReply:\n%s" % (INSTRUCTIONS, reply)


def count_this_stop(session_id):
    """Return this Stop's number n in its session and store it. Never raises. A counter that is
    missing, corrupt, unreadable or unkeyed reads as none, so this Stop is n = 1 and is judged;
    after a good read, a failed write removes the counter file, so the next Stop is judged; if
    the remove also fails, this Stop is judged (n = 1) and the stored count is left as it was."""
    path = None
    n = 1
    try:
        if isinstance(session_id, str) and session_id:
            from shared_names import config_dir  # stdlib only: a sampled-out Stop loads no guard
            key = hashlib.sha256(session_id.encode("utf-8", "replace")).hexdigest()
            path = os.path.join(config_dir(), STATE_DIR_NAME, COUNT_SUB, key + ".count")
            with open(path, "r", encoding="ascii") as f:
                n = int(f.read().strip()) + 1
            if n < 1:
                n = 1
    except Exception:
        n = 1
    try:
        if path:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path + ".tmp", "w", encoding="ascii") as f:
                f.write(str(n))
            os.replace(path + ".tmp", path)
    except Exception:
        # A write that fails would freeze the stored count and skip every later Stop. Drop the
        # file instead, so the next Stop reads a damaged counter and is judged.
        try:
            os.remove(path)
        except Exception:
            n = 1  # ponytail: write and remove both failed; judge this Stop, so no freeze
    return n


def main():
    try:
        hook = json.load(sys.stdin)
        if hook.get("stop_hook_active"):
            return 0
        reply = hook.get("last_assistant_message")
        if not isinstance(reply, str) or not reply.strip():
            return 0
        if (count_this_stop(hook.get("session_id")) - 1) % SAMPLE_EVERY:
            return 0
        import decision_watch
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
