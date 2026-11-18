"""The guard's role-limit family: a message that states a limit on a session's role must cite its ruling.

guard.py is the only entry point, and it runs these checks in its fixed order. Other files reach these names
through `guard`. The one rule here is goal-text-cites-role-ruling (decision goal-text-cites-role-ruling).

The send_message tool and SendMessage carry a message. The Agent tool, the Task tool and create_session carry a
prompt. The rule refuses a sentence that holds a role, then cannot, can't, can not, won't, may not, must not, mustn't,
should not, does not, isn't allowed to or is not permitted to, then merge, push or mark ready (words such as its, own,
lane or your may sit between mark and ready), unless the same sentence or the same line names a ruling or a decision
id. A role is a named session (triage, a runner with a number, a lane with a number or a slug, and the plural lanes) or
the second person: the text goes to another session, so "you cannot merge" limits its reader.
Three forms pass. A conditional: the sentence opens a clause with "if" before the limit (If you cannot push, stop and
report). The second person in an Agent or Task prompt: that text briefs the agent's own run, so "You must not push"
limits no session's role. A limit that states its cause after the act: a colon or "because" in the rest of the
sentence (The lane cannot push: the proxy returns 403). A limit in double or single quotes, a blockquote, a code span
or a closed fenced block is quoted text, and passes. A quote, code span or fence that never closes is plain text. A
cite is any hyphenated slug in backticks, whether or not a record holds it. The guard reads a cause and a cite for
their presence, never for their truth.
Cost: one pass over the message text, with no process, no file and no clock. It never raises: a message that is not
a string passes.
"""
import re

from guard_merge import BRIEF_TOOL
from shared_names import opens_fence

CREATE_SESSION_TOOL = "mcp__claude-code-remote__create_session"
# Each tool and the field that carries its text: a send holds a message, a spawn or a session start holds a prompt.
ROLE_LIMIT_FIELDS = {BRIEF_TOOL: "message", "SendMessage": "message", "Agent": "prompt", "Task": "prompt",
                     CREATE_SESSION_TOOL: "prompt"}
ROLE_LIMIT_TOOLS = tuple(ROLE_LIMIT_FIELDS)
# A spawn prompt briefs the spawned agent's own run, so the second person there limits no session's role.
SPAWN_PROMPT_TOOLS = ("Agent", "Task")
QUOTED = "\x01"  # stands in for each character of quoted text, so no limit or sentence end is read inside it

# An id is a hyphenated slug. A lane is named by a number or a slug, and a cite is a slug.
_SLUG = r"[a-z0-9]+(?:-[a-z0-9]+)+"
_ROLE = (r"(?P<role>triage(?: session)?|(?:(?:batch )?runner #?\d+)|batch runner|coordinator|lanes?(?: (?:\d+|%s))?"
         r"|consultant|arbiter|you)" % _SLUG)
_NOT = (r"(?:cannot|can['’]t|can not|won['’]t|may not|must not|mustn['’]t|should not|shouldn['’]t|does not|doesn['’]t"
        r"|(?:is|are)(?: not|n['’]t) (?:allowed|permitted) to)")
_ACT = (r"(?:merge|push|mark\s+(?:(?:it|them|the|its|own|lane|your|their|a|any|prs?|pull|requests?|#?\d+)\s+)*ready)")
LIMIT = re.compile(r"\b%s\s+%s\s+%s\b" % (_ROLE, _NOT, _ACT), re.IGNORECASE)
# A cite: an id in backticks, or the word ruling or decision with an id after it.
CITE = re.compile(r"`%s`|\b(?:ruling|decision)\s+`?%s" % (_SLUG, _SLUG), re.IGNORECASE)
# A limit that states its cause: a colon or because after the act, before a semicolon or the sentence end.
_CAUSE = re.compile(r"^[^;]*?(?::\s*\S|\bbecause\s+\S)", re.IGNORECASE)
_IF_CLAUSE = re.compile(r"\bif\b", re.IGNORECASE)
_SENTENCE_END = re.compile(r"[.!?]+(?=\s|\Z)|\n[ \t]*\n")

ROLE_LIMIT_REASON = (
    "This message states a limit on a session's role and cites no ruling or decision for it. A limit with no source "
    "can be wrong, and a session that reads it may drop work its own rulings let it do. Name the ruling or decision "
    "the limit rests on in the same sentence or on the same line: a decision id in backticks, or the word ruling or "
    "decision and then its id. Or leave the limit out. To pass on someone's words, put them in quotes or a "
    "code span. Rule goal-text-cites-role-ruling (decision goal-text-cites-role-ruling, a limit on a session's role "
    "cites its ruling).")


def _blank(chars, start, end):
    for index in range(start, end):
        if chars[index] != "\n":
            chars[index] = QUOTED


_SINGLE_CLOSER = re.compile(r"(?<=\S)['’](?!\w)")


def _mask_inline(line, offset, chars):
    """Mask the closed code spans and closed quotes of one line. An opener with no closer on the line is text. A single
    quote opens only where no word character comes before it, so an apostrophe in don't or runner 10's opens none."""
    i = 0
    while i < len(line):
        c = line[i]
        end = -1
        if c == "`":
            run = len(line[i:]) - len(line[i:].lstrip("`"))
            closer = re.compile(r"(?<!`)`{%d}(?!`)" % run).search(line, i + run)
            if closer:
                end = closer.end()
            else:
                i += run
                continue
        elif c in '"“':
            close = line.find('"' if c == '"' else "”", i + 1)
            end = close + 1 if close > 0 else -1
        elif c in "'‘" and not (i and (line[i - 1].isalnum() or line[i - 1] == "_")):
            closer = _SINGLE_CLOSER.search(line, i + 1)
            end = closer.end() if closer else -1
        if end > 0:
            _blank(chars, offset + i, offset + end)
            i = end
        else:
            i += 1


def _masked(text):
    """The text with each quoted character replaced by QUOTED, at the same offsets: a blockquote line, a closed fenced
    block, a closed code span and a closed double quote."""
    chars = list(text)
    lines = text.split("\n")
    starts, at = [], 0
    for line in lines:
        starts.append(at)
        at += len(line) + 1
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if opens_fence(stripped):
            closing = next((n for n in range(index + 1, len(lines)) if opens_fence(lines[n].strip())), None)
            if closing is not None:
                _blank(chars, starts[index], starts[closing] + len(lines[closing]))
                index = closing + 1
                continue
        if stripped.startswith(">"):
            _blank(chars, starts[index], starts[index] + len(lines[index]))
        else:
            _mask_inline(lines[index], starts[index], chars)
        index += 1
    return "".join(chars)


def _sentence_span(masked, start, end):
    """The offsets of the sentence that holds [start, end): from the last sentence end before it to the first after."""
    low, high = 0, len(masked)
    for found in _SENTENCE_END.finditer(masked):
        if found.end() <= start:
            low = found.end()
        elif found.start() >= end - 1 and found.end() >= end:
            high = found.end()
            break
    return low, high


def _line_span(text, start, end):
    return text.rfind("\n", 0, start) + 1, (text.find("\n", end) if "\n" in text[end:] else len(text))


def role_limit_hit(tool: str, tool_input):
    """The matched text of the first uncited limit on a role in this send or spawn, else None."""
    if tool not in ROLE_LIMIT_TOOLS or not isinstance(tool_input, dict):
        return None
    text = tool_input.get(ROLE_LIMIT_FIELDS[tool])
    if not isinstance(text, str) or not text:
        return None
    masked = _masked(text)
    for found in LIMIT.finditer(masked):
        start, end = found.span()
        if tool in SPAWN_PROMPT_TOOLS and found.group("role").lower() == "you":
            continue
        low, high = _sentence_span(masked, start, end)
        if _IF_CLAUSE.search(masked[low:start]) or _CAUSE.match(masked[end:high]):
            continue
        for low, high in (_sentence_span(masked, start, end), _line_span(text, start, end)):
            if CITE.search(text[low:high]):
                break
        else:
            return text[start:end][:120]
    return None

# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
