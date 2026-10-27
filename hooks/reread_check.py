#!/usr/bin/env python3
"""Claude Code hook: after compaction, check the session re-read its handoff.

Modes:
- --post-compact: After compaction, sets the session's flag that its handoff is not read.
- --pre-read: Before a Read, clears the session's flag that its handoff is not read, when the
  file is that handoff. Never denies the read. A payload with `agent_id` (the hook
  fired inside an agent) clears nothing: only the session's own Read counts.
- --stop: At Stop, while the session's flag that its handoff is not read is set and the
  handoff exists, blocks once per turn and names the handoff path.

Spec: docs/decisions/precompact-handoff.md, item 9. One flag file per session,
<config dir>/state/handoff/<session_id>.reread. Three modes, JSON on stdin:

  --post-compact (PostCompact)  sets the flag.
  --pre-read (PreToolUse, Read)  clears the flag when file_path is the session's own
      handoff, spelled as a full path, with forward slashes, as a short or long Windows
      name, or as ~/.claude/.... Never denies the read.
  --stop (Stop)  with the flag set and the handoff file present, prints
      {"decision": "block", "reason": ...} naming the handoff path. Exits quietly on
      stop_hook_active, so it cannot loop. The flag stays set until the handoff is read,
      so it blocks once per turn. SessionEnd (clear) deletes the flag.

Never exits 2: bad stdin, a failed import of the sibling precompact_handoff, and every
other failure exit 0.
"""
import json
import os
import sys

try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import precompact_handoff as ph  # one home for the handoff and flag paths
except Exception as e:
    sys.stderr.write("reread_check: cannot import precompact_handoff: %s\n" % e)
    sys.exit(0)


def names_handoff(file_path, session_id):
    return any(ph.same_dir(os.path.expanduser(file_path), want) for want in (
        ph.handoff_path(session_id),
        os.path.expanduser("~/.claude/handoffs/%s.md" % session_id)))


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:   # bad JSON, or a read that fails
        return 0
    sid = payload.get("session_id") if isinstance(payload, dict) else None
    if not sid or not isinstance(sid, str):
        return 0
    flag = ph.reread_flag_path(sid)
    args = sys.argv[1:]
    try:
        if "--post-compact" in args:
            os.makedirs(os.path.dirname(flag), exist_ok=True)
            with open(flag, "w", encoding="utf-8") as f:
                f.write("1")
        elif "--pre-read" in args:
            if payload.get("agent_id"):
                return 0
            fp = (payload.get("tool_input") or {}).get("file_path")
            if isinstance(fp, str) and fp and names_handoff(fp, sid) and os.path.isfile(flag):
                os.remove(flag)
        elif "--stop" in args:
            if (not payload.get("stop_hook_active") and os.path.isfile(flag)
                    and os.path.isfile(ph.handoff_path(sid))):
                print(json.dumps({"decision": "block", "reason": (
                    "Context was compacted and you have not re-read your handoff. Read %s "
                    "now, then continue." % ph.handoff_path(sid))}))
    except Exception as e:
        sys.stderr.write("reread_check: %s\n" % e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
