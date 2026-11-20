#!/usr/bin/env python3
"""At a startup, flags the session in its context when the machine is full. Prints nothing otherwise.

A SessionStart hook for source `startup` only (decision machine-load-brake). It never stops a
session: its one line is SessionStart additionalContext, with no `continue` and no `stopReason`. A session start
cannot be refused here (the app card, anthropics/claude-code#103832), and the hook cannot tell a lane from an owner
session, so it flags the start and addresses a session whose own get_session record (no session_id) carries the tag
cs-build:lane. A parent_session_id alone makes no lane: triage and the batch runner carry one (decision
machine-load-brake). The text names the readings and the decision, and tells the session what to do. A
session with the tag does no work and tells its parent (send_message @parent) what it started in. A session without the
tag (the owner's own, the coordinator, triage, the batch runner) goes on.

It reads no model. A Haiku start is not flagged: the spawn guard already checked the owner's model name
(guard.owner_names_model), and the started session cannot read that word (decision start-checks-after-call). In a local
session it reads the load once (guard.read_load) and asks guard.load_full for the readings over the full point. A cloud
session is never load-flagged.

Fail-open: a failed import of guard, bad JSON, a payload that is not an object, or any error prints nothing and exits
0. It never exits 2, starts no process and writes no file.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))

LANE_TAG = "cs-build:lane"
LANE_AND_OWNER = (
    "Read this session's own record with get_session, passing no session_id. If its tags include %s, it is a lane "
    "and does no work: it tells its parent (send_message to @parent) what it started in, and waits. A session "
    "without the tag (the owner's own, the coordinator, triage, the batch runner) goes on." % LANE_TAG
)


def flag_text(payload) -> str:
    """Why this start is flagged, or "" when it is not."""
    import guard  # imported here, inside main's try, so a failed import prints nothing
    if not isinstance(payload, dict) or payload.get("source") != "startup":
        return ""
    if guard.is_cloud():
        return ""
    full = guard.load_full(guard.read_load())
    if full:
        return "The machine is full: %s (decision machine-load-brake). %s" % (", ".join(full), LANE_AND_OWNER)
    return ""


def main() -> int:
    try:
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        text = flag_text(json.loads(sys.stdin.read()))
        if text:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
