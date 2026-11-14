"""The one home of the code-fence loops for the inbox and for handoff markdown. Standard library only.

feedback_guard.py (the Stop check: parse, unfenced, is_grant) and state_parse_check.py (the PostToolUse
check) both read the fence rule from here, so they agree on what a fence is. The loops sit in a leaf
module, apart from feedback_guard.py, because that module imports lint/_transcript.py and a chain of guard
modules. A PostToolUse hook that runs after each state-file edit must start without them, and must start in
a config folder that holds hooks/ and no lint/ (decision state-file-parse-check).
"""
import re

import local_time  # the one home of the inbox heading and stamp

HEADING_PREFIX = local_time.HEADING_PREFIX  # the heading and stamp the writer emits
HEADER = re.compile(re.escape(HEADING_PREFIX) + local_time.STAMP_PATTERN + "$")
FENCE_MARK = re.compile(r"\s*(`{3,}|~{3,})")


def inbox_scan(text):
    """(blocks, open_line) for the inbox. blocks: [{stamp, line, text, items, item_at, fenced}], `line` the
    heading's 1-based line number and `item_at` the line numbers of `items`. Lines inside a fence are never
    headers or items, and a `### ` line that is not the hook's own Central header is plain text. open_line:
    the 1-based line of the fence still open at the end of the text, or None. Only the first fence of a block
    counts, and it closes on a run of backticks at least as long."""
    blocks, fence, open_line = [], None, None
    for number, ln in enumerate(text.split("\n"), 1):
        ln = ln.rstrip("\r")
        if fence is not None:
            if re.fullmatch(r"`+", ln) and len(ln) >= len(fence):
                fence, open_line = None, None
            else:
                blocks[-1]["text"] = ln if blocks[-1]["text"] is None else blocks[-1]["text"] + "\n" + ln
        elif HEADER.match(ln):
            blocks.append({"stamp": ln[len(HEADING_PREFIX):], "line": number, "text": None, "items": [],
                           "item_at": [], "fenced": False})
        elif blocks and not blocks[-1]["fenced"] and re.fullmatch(r"`{3,}", ln):
            fence, open_line, blocks[-1]["fenced"] = ln, number, True
        elif blocks and ln.startswith("- fb-"):
            blocks[-1]["items"].append(ln)
            blocks[-1]["item_at"].append(number)
    return blocks, open_line


def fence_scan(text, indent_cap=None):
    """(kept, open_line) for markdown text: `kept` the lines outside its code fences, and `open_line` the
    1-based line of a fence left open to the end, or None. A fence is backticks or tildes with an info string
    allowed; it closes on a run of its own character, at least as long. `indent_cap` None reads a fence at any
    indent, a tab included (unfenced() and the grant check keep that); a number caps the indent in spaces: 3
    is CommonMark's rule, where four spaces make an indented code block, not a fence (the handoff check)."""
    mark_re = FENCE_MARK if indent_cap is None else re.compile(r" {0,%d}(`{3,}|~{3,})" % indent_cap)
    kept, fence, open_line = [], None, None
    for number, ln in enumerate(text.split("\n"), 1):
        mark = mark_re.match(ln)
        if fence is None:
            if mark:
                fence, open_line = mark.group(1), number
            else:
                kept.append(ln)
        elif mark and mark.group(1)[0] == fence[0] and len(mark.group(1)) >= len(fence):
            fence, open_line = None, None
    return kept, open_line
