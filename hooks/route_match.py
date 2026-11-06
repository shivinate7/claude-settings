"""The one home of the route-row falsifier's reads: the rows file, the surface, and the match of a call to a row.

A route row records how an act fares on a surface: outcome "works" or "refused". Two hooks compare it with
what really happened and note a contradiction, never refuse on it:
- hooks/refusal_note.py (PermissionDenied): a refused call that a "works" row matches.
- lint/report_guard.py (Stop): a successful call that a "refused" row matches, and each `note` the
  first hook wrote.

Rows file: {"rows": [{id, act, route, surface, outcome, measured, cc_version, evidence, by, pattern,
alternates?}]}, at hooks/route_rows.json. The env GUARD_ROUTE_ROWS overrides the path, as
GUARD_ITEM_FIELDS_PAGE does for the waiting page (hooks/question_form.py). A missing or unreadable file reads
as no rows: a hook that cannot read a row cannot accuse.

Cost: one file read per hook run that already runs, no process, no write. It never writes the rows file.
The surface is guard_core.is_cloud, the one home of the cloud check.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

ROUTE_ROWS_SEAM = "GUARD_ROUTE_ROWS"
ROUTE_ROWS_FILE = os.path.join(HERE, "route_rows.json")


def surface():
    """The session's surface. Loads guard_core here, so a hook with no row to judge never pays for the import."""
    import guard_core
    return "cloud" if guard_core.is_cloud() else "local"


def load_rows():
    """The rows in the rows file, or [] when the file or its list does not read."""
    path = os.environ.get(ROUTE_ROWS_SEAM) or ROUTE_ROWS_FILE
    try:
        with open(path, encoding="utf-8") as handle:
            rows = json.load(handle).get("rows")
    except (OSError, ValueError, AttributeError):
        return []
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def call_target(tool_name, tool_input):
    """The text a row's pattern is matched against: the command of a Bash call, else the tool name."""
    if tool_name == "Bash":
        command = tool_input.get("command") if isinstance(tool_input, dict) else None
        return command if isinstance(command, str) else ""
    return tool_name if isinstance(tool_name, str) else ""


def matching_rows(rows, outcome, calls):
    """The rows of `outcome` on this surface that match at least one of `calls`, each a (tool_name,
    tool_input) pair, in the order of the rows. A row with no readable pattern matches nothing."""
    if not rows:
        return []
    here = surface()
    targets = [call_target(name, tool_input) for name, tool_input in calls]
    found = []
    for row in rows:
        pattern = row.get("pattern")
        if row.get("surface") != here or row.get("outcome") != outcome or not isinstance(pattern, str):
            continue
        try:
            compiled = re.compile(pattern)
        except re.error:
            continue
        if any(compiled.search(target) for target in targets):
            found.append(row)
    return found
