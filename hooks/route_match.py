"""The one home of the route-row falsifier's reads: the rows file, the surface, and the match of a call to a row.

A route row records how an act fares on a surface: outcome "works" or "refused". Two hooks compare it with
what really happened and note a contradiction, never refuse on it:
- hooks/refusal_note.py (PermissionDenied): a refused call that a "works" row matches.
- lint/report_guard.py (Stop): a successful call that a "refused" row matches, and each `route_flag` the
  first hook wrote.
lint/report_guard.py also reads a row by id for the hand-off cite: a "Why yours" line must cite `(route <id>)`.

Rows file: {"rows": [{id, act, route, surface, outcome, measured, cc_version, evidence, by, pattern,
alternates?}]}, at hooks/route_rows.json. The env GUARD_ROUTE_ROWS overrides the path, as
GUARD_ITEM_FIELDS_PAGE does for the waiting page (hooks/question_form.py). `rows_path()` is the one home of that
path: any other reader of the rows file (lint/stale_cites.py) calls it and keeps no copy. A missing or unreadable
file reads as no rows: a hook that cannot read a row cannot accuse. `read_rows()` keeps the two apart (None for a file that
does not read), for the reader that must report an unread file as UNKNOWN.

Cost: one file read per hook run that already runs, no process, no write. It never writes the rows file. A match
runs each row's pattern once per call target, over at most MAX_TARGET_CHARS of it, and skips a pattern longer than
MAX_PATTERN_CHARS.
The surface is guard_core.is_cloud, the one home of the cloud check.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from shared_names import install_root  # noqa: E402  stdlib only: the one home of the install root

ROUTE_ROWS_SEAM = "GUARD_ROUTE_ROWS"
# A stamped copy in hooks/guard.d/<id>/ holds no rows file, so the path goes through the install root (decision
# install-hooks-whole), the one home of the install lookup.
ROUTE_ROWS_FILE = os.path.join(install_root(HERE), "hooks", "route_rows.json")
# The rows file is data an owner edits, and Stop runs this match on every turn. A backtracking pattern over a
# long command (a heredoc, a pasted log) could stall the Stop, so a match reads a bounded slice and skips a
# pattern too long to be a plain act name. A route row names a verb at the start of a call, so the slice keeps it.
MAX_PATTERN_CHARS = 500
MAX_TARGET_CHARS = 4000
_compiled = {}  # pattern text -> compiled pattern, or None when it is too long or does not compile


def rows_path():
    """The path of the rows file: the GUARD_ROUTE_ROWS seam when set, else hooks/route_rows.json."""
    return os.environ.get(ROUTE_ROWS_SEAM) or ROUTE_ROWS_FILE


def _compile(pattern):
    """The compiled `pattern`, compiled once per process, or None for a pattern over MAX_PATTERN_CHARS or one that does not compile."""
    if pattern not in _compiled:
        try:
            _compiled[pattern] = re.compile(pattern) if len(pattern) <= MAX_PATTERN_CHARS else None
        except re.error:
            _compiled[pattern] = None
    return _compiled[pattern]


def surface():
    """The session's surface. Loads guard_core here, so a hook with no row to judge never pays for the import."""
    import guard_core
    return "cloud" if guard_core.is_cloud() else "local"


def read_rows():
    """The rows in the rows file, or None when the file or its list does not read. An empty list of rows is [], not
    None: a reader that must tell "no row holds this id" from "the file never read" (the hand-off cite in
    lint/report_guard.py) calls this one."""
    try:
        with open(rows_path(), encoding="utf-8") as handle:
            rows = json.load(handle).get("rows")
    except (OSError, ValueError, AttributeError):
        return None
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else None


def load_rows():
    """The rows in the rows file, or [] when the file or its list does not read."""
    return read_rows() or []


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
    targets = [call_target(name, tool_input)[:MAX_TARGET_CHARS] for name, tool_input in calls]
    found = []
    for row in rows:
        pattern = row.get("pattern")
        if row.get("surface") != here or row.get("outcome") != outcome or not isinstance(pattern, str):
            continue
        compiled = _compile(pattern)
        if compiled is None:
            continue
        if any(compiled.search(target) for target in targets):
            found.append(row)
    return found
