"""The guard's role-limit family: a message that states a limit on a session's role must cite its ruling.

guard.py is the only entry point, and it runs these checks in its fixed order. Other files reach these names
through `guard`. The one rule here is goal-text-cites-role-ruling (decision goal-text-cites-role-ruling).

The send_message tool and SendMessage carry a message. The rule refuses a sentence that holds a role, then cannot,
can't, can not, may not or must not, then merge, push or mark ready, unless the same sentence or the same line names
a ruling or a decision id. A limit in double quotes, a blockquote, a code span or a closed fenced block is quoted
text, and passes. A quote, code span or fence that never closes is plain text.
Cost: one pass over the message text, with no process, no file and no clock. It never raises: a message that is not
a string passes.
"""
import re

from guard_merge import BRIEF_TOOL
from shared_names import opens_fence

ROLE_LIMIT_TOOLS = (BRIEF_TOOL, "SendMessage")
QUOTED = "\x01"  # stands in for each character of quoted text, so no limit or sentence end is read inside it

_ROLE = r"(?:triage|(?:batch )?runner \d+|batch runner|coordinator|lane|consultant|arbiter)"
_NOT = r"(?:cannot|can['’]t|can not|may not|must not)"
_ACT = r"(?:merge|push|mark\s+(?:(?:it|them|the|its|a|any|prs?|pull|requests?|#?\d+)\s+)*ready)"
LIMIT = re.compile(r"\b%s\s+%s\s+%s\b" % (_ROLE, _NOT, _ACT), re.IGNORECASE)
# A cite: an id in backticks, or the word ruling or decision with an id after it. An id is a hyphenated slug.
_SLUG = r"[a-z0-9]+(?:-[a-z0-9]+)+"
CITE = re.compile(r"`%s`|\b(?:ruling|decision)\s+`?%s" % (_SLUG, _SLUG), re.IGNORECASE)
_SENTENCE_END = re.compile(r"[.!?]+(?=\s|\Z)|\n[ \t]*\n")

ROLE_LIMIT_REASON = (
    "This message states a limit on a session's role and cites no ruling or decision for it. A limit with no source "
    "can be wrong, and a session that reads it may drop work its own rulings let it do. Name the ruling or decision "
    "the limit rests on in the same sentence or on the same line: a decision id in backticks, or the word ruling or "
    "decision and then its id. Or leave the limit out. To pass on someone's words, put them in double quotes or a "
    "code span. Rule goal-text-cites-role-ruling (decision goal-text-cites-role-ruling, a limit on a session's role "
    "cites its ruling).")


def _blank(chars, start, end):
    for index in range(start, end):
        if chars[index] != "\n":
            chars[index] = QUOTED


def _mask_inline(line, offset, chars):
    """Mask the closed code spans and closed double quotes of one line. An opener with no closer on the line is text."""
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
    """The matched text of the first uncited limit on a role in this send, else None."""
    if tool not in ROLE_LIMIT_TOOLS or not isinstance(tool_input, dict):
        return None
    text = tool_input.get("message")
    if not isinstance(text, str) or not text:
        return None
    masked = _masked(text)
    for found in LIMIT.finditer(masked):
        start, end = found.span()
        for low, high in (_sentence_span(masked, start, end), _line_span(text, start, end)):
            if CITE.search(text[low:high]):
                break
        else:
            return text[start:end][:120]
    return None

# The installer swaps the next line for `INSTALL_ID = "<id>"` at copy time; guard.py compares the
# ids across the modules it loads. In the repo it stays a comment, which counts as a match.
# INSTALL_ID = "uninstalled"
