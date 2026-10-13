#!/usr/bin/env python3
"""Claude Code hook: after compaction, check the session re-read its handoff.

Spec: decisions/handoff-hooks-wave-2.md, ruling item 2. One flag file per session,
<config dir>/state/handoff/<session_id>.reread. Three modes, JSON on stdin:

  --post-compact (PostCompact)  sets the flag.
  --pre-read (PreToolUse, Read)  clears the flag when file_path is the session's own
      handoff, spelled as a full path, with forward slashes, or as ~/.claude/....
      Never denies the read.
  --stop (Stop)  with the flag set, prints {"decision": "block", "reason": ...} naming
      the handoff path. Exits quietly on stop_hook_active, so it cannot loop. The flag
      stays set until the handoff is read.

Never exits 2: every failure is logged to stderr and the hook exits 0.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import precompact_handoff as ph  # noqa: E402  (one home for the handoff path)


def flag_path(session_id):
    return os.path.join(ph.config_dir(), "state", "handoff", "%s.reread" % session_id)


def _norm(path):
    return os.path.normcase(os.path.normpath(os.path.expanduser(path)))


def names_handoff(file_path, session_id):
    want = {_norm(ph.handoff_path(session_id)),
            _norm("~/.claude/handoffs/%s.md" % session_id)}
    return _norm(file_path) in want


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        payload = {}
    sid = payload.get("session_id") or ""
    if not sid:
        return 0
    flag = flag_path(sid)
    args = sys.argv[1:]
    try:
        if "--post-compact" in args:
            os.makedirs(os.path.dirname(flag), exist_ok=True)
            with open(flag, "w", encoding="utf-8") as f:
                f.write("1")
        elif "--pre-read" in args:
            fp = (payload.get("tool_input") or {}).get("file_path")
            if isinstance(fp, str) and fp and names_handoff(fp, sid) and os.path.isfile(flag):
                os.remove(flag)
        elif "--stop" in args:
            if not payload.get("stop_hook_active") and os.path.isfile(flag):
                print(json.dumps({"decision": "block", "reason": (
                    "Context was compacted and you have not re-read your handoff. Read %s "
                    "now, then continue." % ph.handoff_path(sid))}))
    except Exception as e:
        sys.stderr.write("reread_check: %s\n" % e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
