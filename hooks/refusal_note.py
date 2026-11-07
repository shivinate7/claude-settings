#!/usr/bin/env python3
"""At PermissionDenied, notes each tool the auto-mode classifier refuses, so the Stop guard can make the reply ask the owner about it. Prints nothing.

Appends one JSON line {ts, tool_name, reason, tool_use_id} to <config dir>/state/refusals/<session_id>.jsonl,
plus agent_id when the payload names an agent. lint/report_guard.py reads that file at Stop, drops
an agent's row, and blocks until the reply raises each other refused tool (decision refusals-reach-the-owner).

- A reason that starts with "Auto mode could not evaluate this action" or "Classifier unavailable"
  is a classifier outage with no verdict. It writes nothing.
- A tool_name already pending in the file is not written again. An agent's row (one with agent_id)
  does not count as pending: the Stop side drops it, so it must not hide the orchestrator's refusal of
  the same tool.
- A refused call that a route row says works on this surface adds a `route_flag` key to its row, naming the row id
  (hooks/route_match.py holds the rows file, the surface and the match). lint/report_guard.py shows the flag at
  Stop. A rows file that does not read adds no flag and never stops the row from being written.
- Prints nothing and never the `retry` decision (the only output the event reads). Exits 0 on
  every path, so a failure here never changes the refusal.
"""
import datetime
import json
import os
import sys

NO_VERDICT = ("Auto mode could not evaluate this action", "Classifier unavailable")


def pending_tools(path):
    tools = set()
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                try:  # a bad line is skipped, as lint/report_guard.py skips it
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict) and not row.get("agent_id"):
                    tools.add(row.get("tool_name"))
    except FileNotFoundError:
        pass
    return tools


def route_flag(tool, tool_input):
    """The flag for a refusal that a route row contradicts, or None. Fails open: a rows file or a pattern that
    does not read adds no flag, and the refusal row is still written."""
    try:
        import route_match
        rows = route_match.matching_rows(route_match.load_rows(), "works", [(tool, tool_input)])
    except Exception as err:
        sys.stderr.write("refusal_note route read failed open: %s\n" % err)
        return None
    if not rows:
        return None
    return "; ".join("route row %s contradicted: it says this call works on %s, and the classifier refused it"
                     % (row.get("id"), row.get("surface")) for row in rows)


def main():
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import shared_names
        data = json.loads(sys.stdin.read() or "{}")
        if not isinstance(data, dict):
            return
        tool = data.get("tool_name")
        reason = data.get("reason")
        reason = reason if isinstance(reason, str) else ""
        path = shared_names.refusals_path(data.get("session_id"))
        if path is None or not isinstance(tool, str) or not tool or reason.startswith(NO_VERDICT):
            return
        if tool in pending_tools(path):
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        row = {"ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
               "tool_name": tool, "reason": reason}
        for key in ("tool_use_id", "agent_id"):
            if isinstance(data.get(key), str) and data[key]:
                row[key] = data[key]
        flag = route_flag(tool, data.get("tool_input"))
        if flag:
            row["route_flag"] = flag
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")
    except Exception as err:  # fail open: the hook only notes, it never decides
        sys.stderr.write("refusal_note failed open: %s\n" % err)


if __name__ == "__main__":
    main()
    sys.exit(0)
