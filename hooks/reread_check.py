#!/usr/bin/env python3
"""Claude Code hook: after compaction, check the session re-read its handoff.

Modes:
- --post-compact: After compaction, sets the session's flag that its handoff is not read, and
  a second flag that the handoff audit (prompt step 3) is owed.
- --pre-read: Before a Read, clears the session's flag that its handoff is not read, when the
  file is that handoff. Never refuses the read. A payload with `agent_id` (the hook
  fired inside an agent) clears nothing: only the session's own Read counts.
- --stop: At Stop, while the session's flag that its handoff is not read is set and the
  handoff exists, refuses once per turn and names the handoff path. With that flag cleared
  and the audit flag still set, it refuses once per turn and names the Audit: remedy.

Spec: docs/decisions/precompact-handoff.md, items 9 and 16. Two flag files per session,
<config dir>/state/handoff/<session_id>.reread and <session_id>.audit. Three modes, JSON on stdin:

  --post-compact (PostCompact)  sets both flags.
  --pre-read (PreToolUse, Read)  clears the flag when file_path is the session's own
      handoff, spelled as a full path, with forward slashes, as a short or long Windows
      name, or as ~/.claude/.... Never refuses the read.
  unread_handoff(payload) (import, no flag)  the guard's PreToolUse check calls it. Returns the
      handoff path while the flag is set and the handoff exists, else "".
  audit_pending(payload) (import, no flag)  the guard's PreToolUse check calls it. Returns the
      handoff path while the audit flag is set, the re-read flag is already cleared and the call is
      the main session's, else "".
  audit_spawn(payload, spawn_tools) (import)  true for a spawn from the main session whose brief's
      first non-blank line carries the audit marker (shared_names.EXPLORE_AUDIT_MARKER, `Audit:`).
      audit_clear(payload) drops the audit flag; the guard calls it once the spawn has passed every rule.
  --stop (Stop)  with the flag set and the handoff file present, prints
      {"decision": "block", "reason": ...} naming the handoff path. Exits quietly on
      stop_hook_active, so it cannot loop. The flag stays set until the handoff is read,
      so it refuses once per turn. SessionEnd (clear) deletes both flags.

Never exits 2: bad stdin, a failed import of the sibling precompact_handoff, and every
other failure exit 0. Importing this module never exits: without the sibling,
`unread_handoff` and `audit_pending` return "".
"""
import json
import os
import re
import sys

try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import precompact_handoff as ph  # one home for the handoff and flag paths
except Exception as e:
    ph = None
    sys.stderr.write("reread_check: cannot import precompact_handoff: %s\n" % e)

try:
    # The audit marker's one home is shared_names.py: its first-line audit row of BRIEF_MARKERS, which the guard's
    # marker_hits reads too. This reader compiles that row, so the two cannot drift.
    from shared_names import BRIEF_MARKERS, EXPLORE_AUDIT_MARKER
    AUDIT_ROW = re.compile(next(rx for kind, rx, position in BRIEF_MARKERS
                                if kind == "audit" and position == "first-line"))
except Exception as e:
    AUDIT_ROW = EXPLORE_AUDIT_MARKER = None
    sys.stderr.write("reread_check: cannot read the audit marker from shared_names: %s\n" % e)


def names_handoff(file_path, session_id):
    return any(ph.same_dir(os.path.expanduser(file_path), want) for want in (
        ph.handoff_path(session_id),
        os.path.expanduser("~/.claude/handoffs/%s.md" % session_id)))


def unread_handoff(payload):
    """The session's handoff path while its re-read flag is set and the handoff exists, else "".
    An agent's call (`agent_id` on the payload) and a bad payload give "". Checks the flag first,
    so a session with no flag costs one existence check. Never raises."""
    try:
        if ph is None or not isinstance(payload, dict) or payload.get("agent_id"):
            return ""
        sid = payload.get("session_id")
        if not sid or not isinstance(sid, str) or not os.path.isfile(ph.reread_flag_path(sid)):
            return ""
        handoff = ph.handoff_path(sid)
        return handoff if os.path.isfile(handoff) else ""
    except Exception:
        return ""


def audit_pending(payload):
    """The session's handoff path while its audit flag is set, its re-read flag is already cleared (the
    handoff-unread check speaks first) and the call is the main session's, else "". An agent's call
    (`agent_id` on the payload) and a bad payload give "". Checks the audit flag first, so a session
    with no flag costs one existence check. Never raises."""
    try:
        if ph is None or not isinstance(payload, dict) or payload.get("agent_id"):
            return ""
        sid = payload.get("session_id")
        if not sid or not isinstance(sid, str) or not os.path.isfile(ph.audit_flag_path(sid)):
            return ""
        if os.path.isfile(ph.reread_flag_path(sid)):
            return ""
        return ph.handoff_path(sid)
    except Exception:
        return ""


def audit_spawn(payload, spawn_tools):
    """True when the call is a spawn (its tool is in `spawn_tools`, the guard's SPAWN_TOOLS) from the
    main session whose brief's first non-blank line carries the audit marker, as the one home reads it
    (shared_names.BRIEF_MARKERS, the first-line audit row: case-sensitive, text or markup may stand ahead of it).
    A line quoted further down does not count. Never raises."""
    try:
        if not isinstance(payload, dict) or payload.get("agent_id") or payload.get("tool_name") not in spawn_tools:
            return False
        tool_input = payload.get("tool_input")
        prompt = tool_input.get("prompt") if isinstance(tool_input, dict) else None
        if not isinstance(prompt, str):
            return False
        first = next((line for line in prompt.split("\n") if line.strip()), "")   # the guard's brief_first_line pick
        return AUDIT_ROW is not None and AUDIT_ROW.search(first) is not None
    except Exception:
        return False


def audit_clear(payload):
    """Drop the session's audit flag. Never raises."""
    try:
        os.remove(ph.audit_flag_path(payload["session_id"]))
    except Exception:
        pass


def audit_reason(handoff):
    """The Stop block's text. The guard's refusal has its own constant, COMPACTION_AUDIT_REASON."""
    return ("Context was compacted and the handoff audit is still owed. Spawn one Explore agent on "
            "Sonnet whose brief's first line is `%s`, as step 3 of the handoff prompt says "
            "(it reads the transcript from the last compaction marker and compares it with %s), "
            "then repeat. (decision precompact-handoff, item 16)" % (EXPLORE_AUDIT_MARKER or "Audit:", handoff))


def main():
    if ph is None:
        return 0
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:   # bad JSON, or a read that fails
        return 0
    sid = payload.get("session_id") if isinstance(payload, dict) else None
    if not sid or not isinstance(sid, str):
        return 0
    args = sys.argv[1:]
    try:
        flag = ph.reread_flag_path(sid)
        audit_flag = ph.audit_flag_path(sid)   # inside the try: a stale sibling without it must still exit 0
        if "--post-compact" in args:
            os.makedirs(os.path.dirname(flag), exist_ok=True)
            with open(flag, "w", encoding="utf-8") as f:
                f.write("1")
            with open(audit_flag, "w", encoding="utf-8") as f:
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
                    "now, then continue. (decision precompact-handoff)" % ph.handoff_path(sid))}))
            elif not payload.get("stop_hook_active") and audit_pending(payload):
                print(json.dumps({"decision": "block", "reason": audit_reason(ph.handoff_path(sid))}))
    except Exception as e:
        sys.stderr.write("reread_check: %s\n" % e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
