"""The one home of the route-row falsifier's reads: the rows file, the surface, and the match of a call to a row.

A route row records how an act fares on a surface: outcome "works" or "refused". Two hooks compare it with
what really happened and note a contradiction, never refuse on it:
- hooks/refusal_note.py (PermissionDenied): a refused call that a "works" row matches.
- lint/report_guard.py (Stop): a successful call that a "refused" row matches, and each `route_flag` the
  first hook wrote.
lint/report_guard.py also reads a row by id for the hand-off cite: a "Why yours" line must cite `(route <id>)`,
and judges with cite_covers that the cited row covers the act the page task names (act_texts, rows_covering).

Rows file: {"rows": [{id, act, route, surface, outcome, measured, cc_version, evidence, by, pattern,
alternates?}]}, at hooks/route_rows.json. The env GUARD_ROUTE_ROWS overrides the path, as
GUARD_ITEM_FIELDS_PAGE does for the waiting page (hooks/question_form.py). `rows_path()` is the one home of that
path: any other reader of the rows file (lint/stale_cites.py) calls it and keeps no copy. A missing or unreadable
file reads as no rows: a hook that cannot read a row cannot accuse. `read_rows()` keeps the two apart (None for a file that
does not read), for the reader that must report an unread file as UNKNOWN.

Cost: one file read per hook run that already runs, no process, no write. It never writes the rows file. A match
runs each row's pattern once per call target, over at most MAX_TARGET_CHARS of it, and skips a pattern longer than
MAX_PATTERN_CHARS. The cite cover is the same match over the pieces of one task's act text, so it costs no more
than a call with that many targets.
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


def row_matches(row, targets):
    """True when the row's pattern matches at least one of `targets` (strings the caller has already cut to
    MAX_TARGET_CHARS). A row with no readable pattern matches nothing. The one regex path of every match here."""
    pattern = row.get("pattern")
    compiled = _compile(pattern) if isinstance(pattern, str) else None
    return compiled is not None and any(compiled.search(target) for target in targets)


def matching_rows(rows, outcome, calls):
    """The rows of `outcome` on this surface that match at least one of `calls`, each a (tool_name,
    tool_input) pair, in the order of the rows. A row with no readable pattern matches nothing."""
    if not rows:
        return []
    here = surface()
    targets = [call_target(name, tool_input)[:MAX_TARGET_CHARS] for name, tool_input in calls]
    return [row for row in rows
            if row.get("surface") == here and row.get("outcome") == outcome and row_matches(row, targets)]


_ACT_SPLIT = re.compile(r"&&|\|\||;")
_CONTINUATION = re.compile(r"(?<!\\)((?:\\\\)*)\\\r?\n")  # a backslash-newline that is not itself escaped
# What a route row skips to reach the program: env, NAME=value, nohup, and timeout with its options and duration.
_TIMEOUT_OPTS = r"(?:\s+(?:--(?:foreground|preserve-status|verbose)|-[vp]|(?:-s|-k)\s+\S+|--(?:signal|kill-after)=\S+))*"
_ACT_PREFIX = re.compile(r"(?:(?:env|nohup)\s+|[A-Za-z_]\w*=\S*\s+|timeout" + _TIMEOUT_OPTS + r"\s+\d+(?:\.\d+)?[smhd]?\s+)*")
# gh's repo flag between `gh` and the subcommand; a row names the subcommand, so the cover reads the act without it.
_GH_REPO_FLAG = re.compile(r"^gh(?:\s+(?:-R|--repo)(?:=|\s+)(?:\"[^\"]*\"|'[^']*'|\S+))+")
_BACKTICK_SPAN = re.compile(r"`([^`]+)`")


def _split_line(line):
    """`line` split at &&, || and ; that sit outside quotes, so a `;` inside a quoted flag value stays in its act. A
    line whose quote never closes (a lone apostrophe in text) splits at every operator, as it did before quotes were read."""
    pieces, start, i, quote = [], 0, 0, None
    while i < len(line):
        char = line[i]
        if quote:
            if char == "\\" and quote == '"':
                i += 1
            elif char == quote:
                quote = None
        elif char == "\\" and line[i + 1:i + 2] in ("'", '"'):
            i += 1
        elif char in "'\"":
            quote = char
        elif line.startswith(("&&", "||"), i) or char == ";":
            pieces.append(line[start:i])
            i += 1 if char == ";" else 2
            start = i
            continue
        i += 1
    if quote:
        return _ACT_SPLIT.split(line)
    return pieces + [line[start:]]


def _act_of(piece):
    """One piece with its wrappers dropped (see _ACT_PREFIX) and, for gh, the repo flag before the subcommand."""
    return _GH_REPO_FLAG.sub("gh", _ACT_PREFIX.sub("", piece.strip(), count=1).strip(), count=1).strip()


class _Span(str):
    """A backtick span of a task's context. Unlike a command piece it may be a button label, not an act, so
    cite_covers counts it only when some row on this surface matches it."""


def act_texts(task):
    """The act pieces of a waiting-page task. With a "command" (a string, or each value of a dict of variants): a
    backslash-newline joins its two lines, each line is split at &&, || and ; outside quotes, and each piece drops
    its wrappers (see _act_of), since a route row names the program. With no command: each backtick span of its
    "context". Empty pieces are dropped. A route row names one act, and a command line chains several, so the cover
    reads each piece, not the whole line."""
    command = task.get("command")
    commands = list(command.values()) if isinstance(command, dict) else [command]
    pieces = [_act_of(piece)
              for text in commands if isinstance(text, str)
              for line in _CONTINUATION.sub(r"\1 ", text).splitlines()
              for piece in _split_line(line)]
    pieces = [piece for piece in pieces if piece]
    if pieces:
        return pieces
    context = task.get("context")
    if not isinstance(context, str):
        return []
    return [_Span(span.strip()) for span in _BACKTICK_SPAN.findall(context) if span.strip()]


def rows_covering(rows, texts):
    """The rows on this surface whose pattern matches any of the act pieces `texts`, in row order, whatever
    their outcome."""
    if not rows or not texts:
        return []
    here = surface()
    targets = [text[:MAX_TARGET_CHARS] for text in texts]
    return [row for row in rows if row.get("surface") == here and row_matches(row, targets)]


def cite_covers(rid, rows, texts):
    """Whether the row `rid` covers the act `texts`: "covers", "no", or "unknown". Unknown: no act text, no row
    on this surface holds rid, or that row has no readable pattern, since a cite that cannot be judged is
    never refused. A span (see _Span) that no row on this surface matches is no known act, so it is left out. A
    row's alternates name other acts and never cover."""
    texts = [text for text in texts or [] if not isinstance(text, _Span) or rows_covering(rows, [text])]
    if not texts:
        return "unknown"
    here = surface()
    cited = [row for row in rows if row.get("id") == rid and row.get("surface") == here]
    if not any(isinstance(row.get("pattern"), str) and _compile(row["pattern"]) for row in cited):
        return "unknown"
    return "covers" if any(row.get("id") == rid for row in rows_covering(cited, texts)) else "no"
