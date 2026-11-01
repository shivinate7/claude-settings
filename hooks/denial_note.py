#!/usr/bin/env python3
"""At PermissionDenied, notes each tool the auto-mode classifier refuses, so the Stop guard can make the reply ask the owner about it. Prints nothing.

Appends one JSON line {ts, tool_name, reason} to <config dir>/state/denials/<session_id>.jsonl.
lint/report_guard.py reads that file at Stop and blocks until the reply raises each refused
tool under Input Needed (decision denials-reach-the-owner).

- A reason that starts with "Auto mode could not evaluate this action" is a classifier outage with
  no verdict. It writes nothing.
- A tool_name already pending in the file is not written again.
- Prints nothing and never the `retry` decision (the only output the event reads). Exits 0 on
  every path, so a failure here never changes the denial.
"""
import datetime
import json
import os
import sys

NO_VERDICT = "Auto mode could not evaluate this action"


def pending_tools(path):
    try:
        with open(path, encoding="utf-8") as handle:
            rows = [json.loads(line) for line in handle if line.strip()]
    except FileNotFoundError:
        return set()
    return {row.get("tool_name") for row in rows if isinstance(row, dict)}


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
        path = shared_names.denials_path(data.get("session_id"))
        if path is None or not isinstance(tool, str) or not tool or reason.startswith(NO_VERDICT):
            return
        if tool in pending_tools(path):
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        row = {"ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
               "tool_name": tool, "reason": reason}
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")
    except Exception as err:  # fail open: the hook only notes, it never decides
        sys.stderr.write("denial_note failed open: %s\n" % err)


if __name__ == "__main__":
    main()
    sys.exit(0)
