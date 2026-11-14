#!/usr/bin/env python3
"""Before a GitHub MCP `update_pull_request` call that marks a PR ready (`draft` false), warns when the session has not called `subscribe_pr_activity` for that PR.

PreToolUse hook (decision ci-wait-subscribes-first, rule git-ci-wait-checks-in). A session that waits on CI
subscribes to the PR first. The subscription wakes it on a comment, a review and a finished run. A timed
check-in reads only at its own hour. The hook prints one PreToolUse `additionalContext` warning and exits 0.
It never sets a permissionDecision, so it never refuses the ready mark.

`ci_wake.mcp_ready_calls`, the one parser of that call, finds the ready mark. The transcript is read once,
through `lint/_transcript.py` (`read_transcript`, `tool_uses`), and only after a ready mark is found. The latest
`subscribe_pr_activity` or `unsubscribe_pr_activity` call for that owner, repo and pullNumber decides. A
subscribe as the last word is silence. An unsubscribe, or none, is the warning. Cost: one transcript read per
ready mark; no process start, no timer, no file written, no log.

Advisory, fail-open and silent: bad stdin, no transcript_path, an unreadable transcript or any import error
prints nothing and exits 0.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SUBSCRIBE = "mcp__claude-code-remote__subscribe_pr_activity"
UNSUBSCRIBE = "mcp__claude-code-remote__unsubscribe_pr_activity"

WARNING = ("Marking PR %s ready with no subscribe_pr_activity call for it in this session. "
           "Subscribe first (mcp__claude-code-remote__subscribe_pr_activity), so its activity wakes the session. "
           "Keep one long send_later check-in only as a safety net (rule git-ci-wait-checks-in). "
           "Ignore this when the session merges without waiting.")


def pr_key(tool_input):
    """(owner, repo, number) of a PR call, in one comparable form, or None."""
    if not isinstance(tool_input, dict):
        return None
    owner, repo, number = tool_input.get("owner"), tool_input.get("repo"), tool_input.get("pullNumber")
    if not (isinstance(owner, str) and isinstance(repo, str)) or isinstance(number, bool):
        return None
    return (owner.lower(), repo.lower(), str(number))


def subscribed(records, tool_uses, want):
    """True when the last subscribe or unsubscribe call for `want` is a subscribe."""
    state = False
    for rec in records:
        for use in tool_uses(rec):
            name = use.get("name")
            if name in (SUBSCRIBE, UNSUBSCRIBE) and pr_key(use.get("input")) == want:
                state = name == SUBSCRIBE
    return state


def main():
    payload = json.loads(sys.stdin.read())
    if not isinstance(payload, dict):
        return
    sys.path.insert(0, HERE)
    sys.path.insert(0, os.path.join(HERE, "..", "lint"))
    from ci_wake import MCP_READY_TOOL, mcp_ready_calls  # the one parser of the MCP ready call
    if payload.get("tool_name") != MCP_READY_TOOL:
        return
    tool_input = payload.get("tool_input")
    if not mcp_ready_calls(tool_input):
        return
    path = payload.get("transcript_path")
    if not isinstance(path, str) or not path:
        return
    from _transcript import read_transcript, tool_uses
    want = pr_key(tool_input)
    if want is None or subscribed(read_transcript(path), tool_uses, want):
        return
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": WARNING % ("%s/%s#%s" % (tool_input["owner"], tool_input["repo"], tool_input["pullNumber"]))}}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
