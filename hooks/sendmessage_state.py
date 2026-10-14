#!/usr/bin/env python3
"""PreToolUse hook for SendMessage: judge a message by the receiver's state on the session board.

Rule: parallelism-no-mid-task-talk (a lane messages a peer only when the branch must hear
something that changes its work). Spec: decisions/subagent-model-cap.md, the judge row.

The state comes from `claude agents --json`, read by mods/session-board/hooks/receiver-state.mjs
(lib.mjs is the one home of that read). One word: busy, idle, waiting or unseen.
- idle: allow, no model call. The message starts a turn; it interrupts nothing.
- waiting (on a permission answer): allow, no model call. The receiver is paused, not mid-task.
- busy: one model call (decision_watch.invoke_model, the one model caller). FLAG denies.
- unseen (main, an in-process teammate, no row, a duplicate name, node or claude missing): allow here.
  The wording judge, the SendMessage prompt hook in settings.json, covers that receiver.

Fail open. Any error exits 0 with one stderr line. Deny: one PreToolUse deny JSON, exit 0.
The receiver-state.mjs path resolves through this file's real path, so it needs the symlink
install: a copied hooks/ folder has no mods/ beside it, and every receiver reads as unseen.
"""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

READER = os.path.join(HERE, "..", "mods", "session-board", "hooks", "receiver-state.mjs")
OK_SHAPE = {"ok": (True, False)}
# THE TIME BUDGET. The reader allows 8 s and the model call MODEL_TIMEOUT, so the settings.json
# PreToolUse entry for this hook carries "timeout": 45 = 8 + MODEL_TIMEOUT + 12 s margin.
READER_TIMEOUT = 12
MODEL_TIMEOUT = 25
MESSAGE_MAX = 4000  # one argv element: Windows caps the command line near 32,767 characters


def receiver_state(name):
    node = shutil.which("node")
    if not node or not os.path.isfile(READER):
        return "unseen"
    run = subprocess.run([node, READER, name], capture_output=True, text=True, encoding="utf-8",
                         errors="replace", timeout=READER_TIMEOUT)
    word = run.stdout.strip()
    return word if run.returncode == 0 and word in ("busy", "idle", "waiting") else "unseen"


def build_prompt(to, message):
    return (
        "Judge this message from one agent to a peer. The peer is BUSY: mid-task on the session "
        "board right now.\nRule: parallelism-no-mid-task-talk (message a peer only when the branch "
        "must hear something that changes its work). Answer {\"ok\": true} when the message "
        "names a fact, a correction or a stop that changes the peer's work, or is a short status "
        "the peer needs now. Answer {\"ok\": false, \"reason\": \"<rule id and the fix, one line>\"} "
        "for chat, a progress check, or news the peer does not need before it finishes. When unsure "
        "answer {\"ok\": true}. Reply JSON only.\n\nTo: %s\nMessage:\n%s" % (to, message[:MESSAGE_MAX])
    )


def main():
    try:
        tool_input = json.load(sys.stdin).get("tool_input") or {}
        to, message = tool_input.get("to"), tool_input.get("message")
        if not isinstance(to, str) or not to.strip() or not isinstance(message, str):
            return 0
        if receiver_state(to) != "busy":
            return 0
        import decision_watch
        verdict, error = decision_watch.invoke_model(build_prompt(to, message), timeout=MODEL_TIMEOUT, shape=OK_SHAPE)
    except Exception as exc:
        error, verdict = "%s: %s" % (type(exc).__name__, exc), None
    if error:
        print("sendmessage state judge failed open: %s" % " ".join(error.split()), file=sys.stderr)
        return 0
    if verdict.get("ok") is False:
        reason = verdict.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            reason = "parallelism-no-mid-task-talk: the receiver is busy; send only what changes its work."
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                 "permissionDecision": "deny",
                                                 "permissionDecisionReason": reason}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
