#!/usr/bin/env python3
"""Fails if an agent role file or the lane start text lacks the one short-output line.

TERSE_LINE is the one home of the line. Each agents/*.md file and the lane start text
(skills/project-ops/templates/operating-model.md) must hold it in body text. A line inside a code
fence (``` or ~~~), an HTML comment, an inline code span, a 4-space indented code block or the YAML
frontmatter does not count: quoted text and metadata are not an instruction. A comment opened mid-line hides
text only up to its `-->` in the same paragraph, and a heading, fence, list item, quote, rule line or line-start
comment ends it too. A comment opened at a line start hides through the line that closes it. Whitespace collapses,
so the line may wrap.

    python3 lint/check_agent_terse_line.py [file ...]

With no argument it checks the ten named role files, every other agents/*.md, and the lane start text.
Exits 0 and prints nothing when clean. Exits 1 and names each file that lacks the line, or a named role
with no file. Exits 2 and names each file it could not read, as unknown, when no file lacks the line.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TERSE_LINE = ("Keep your prose to what the reader needs, with no narration; "
              "reasoning and tool inputs are never cut.")

# The ten roles. A deleted role file is a finding, so the list is pinned here, not read from agents/.
ROLES = ("builder", "claude-code-guide", "design-reviewer", "designer", "explore",
         "plan", "record-writer", "refuter", "reviewer", "test-author")
LANE_TEXT = os.path.join("skills", "project-ops", "templates", "operating-model.md")

FENCE = re.compile(r" {0,3}(`{3,}|~{3,})")  # matched at a line start
LIST_ITEM = re.compile(r" {0,3}(?:[-*+]|\d{1,9}[.)])(?:[ \t]|$)")  # matched at a line start
BLANK = re.compile(r"\n[ \t\r]*\n")  # a paragraph break: a blank line, CRLF or LF
# A rule line: three or more `-`, `*` or `_`, spaces between allowed. It is not a list item, so `- - -` ends a list.
RULE = r"(?:-[ \t]*){3,}(?=\r?(?:\n|\Z))|(?:\*[ \t]*){3,}(?=\r?(?:\n|\Z))|(?:_[ \t]*){3,}(?=\r?(?:\n|\Z))"
RULE_LINE = re.compile(r" {0,3}(?:" + RULE + r")")  # matched at a line start
# A line that ends a paragraph, so a comment opened mid-line above it ends there: a heading, a fence, a quote, a
# comment opener, a rule line or a non-empty list item, each after at most 3 spaces. Such a line is never a lazy
# continuation, so it also closes each list item it is not indented into. A list item or comment nested 4 or more
# columns in does not end it, and an ordered item ends it whatever its number; CommonMark's list rules are not rebuilt.
INTERRUPT = (r" {0,3}(?:#{1,6}(?=[ \t\r\n]|\Z)|`{3,}|~{3,}|>|<!--"
             r"|[-*+][ \t]+\S|\d{1,9}[.)][ \t]+\S|" + RULE + r")")
INTERRUPT_LINE = re.compile(INTERRUPT)  # matched at a line start
# A code span hides a comment opener inside it and is itself dropped. It ends at a paragraph break: a newline
# followed by a blank line cannot be inside it, so a lone backtick pairs with nothing across blank lines.
# An inline comment (a `<!--` that is not at a line start) is hidden only when its `-->` comes before the
# paragraph break or an INTERRUPT line. With no close there it is plain text and hides nothing. A comment at a
# line start is a block, read by `block_comment_end`.
SPAN_OR_COMMENT = re.compile(r"(?P<code>(`+)(?:(?!\2(?!`))[^\n]|\n(?![ \t\r]*\n))*?\2(?!`))"
                             r"|(?P<comment><!--(?:(?!-->)(?:[^\n]|\n(?![ \t\r]*\n)(?!" + INTERRUPT + r")))*-->)",
                             re.DOTALL)
ITEM_MARKER = re.compile(r" {0,3}(?:[-*+]|\d{1,9}[.)])( *)(\S?)")  # the marker and its gap, to find the content column


def strip_frontmatter(text: str) -> str:
    """The text after the YAML frontmatter: line 1 is `---` and the next `---` line closes it.

    A file with no frontmatter, or one whose opening `---` has no closing line, is read whole.
    """
    lines = text.split("\n")
    if lines[0].rstrip() != "---":
        return text
    for number in range(1, len(lines)):
        if lines[number].rstrip() == "---":
            return "\n".join(lines[number + 1:])
    return text


def item_width(line: str) -> int:
    """The column where a list item's content starts, for a line that matches LIST_ITEM."""
    found = ITEM_MARKER.match(line)
    gap = len(found.group(1))
    return found.start(1) + (gap if found.group(2) and 1 <= gap <= 4 else 1)


def block_comment_end(text: str, pos: int, end: int, in_list: bool, width: int):
    """Where a comment opened at the line start `pos` ends, or None when the line opens none.

    The opener is `<!--` after at most 3 spaces (counted from the list item's content column inside a
    list item). It closes on the line that holds `-->`, and the rest of that line is hidden too. With no
    close it hides the rest of the text, or inside a list item the rest of the item: the item ends at
    the next non-blank line indented less than its content column. It reads line by line from the opener
    and stops at the close or the item's end, so it scans only what it hides.
    """
    line = text[pos:end]
    spaces = len(line) - len(line.lstrip(" "))
    if not line.startswith("<!--", spaces):
        return None
    inside = in_list and spaces >= width
    if spaces - (width if inside else 0) > 3:
        return None
    if "-->" in line[spaces + 4:]:
        return min(end + 1, len(text))
    scan = end + 1
    while scan < len(text):
        stop = text.find("\n", scan)
        stop = len(text) if stop < 0 else stop
        row = text[scan:stop]
        if inside:
            flat = row.expandtabs(4)
            if flat.strip() and len(flat) - len(flat.lstrip(" ")) < width:
                return scan
        if "-->" in row:
            return min(stop + 1, len(text))
        scan = stop + 1
    return len(text)


def body_text(text: str) -> str:
    """The text with fences, comments and code spans removed and whitespace collapsed.

    One pass in reading order, so each construct hides the others' markers: a fence marker inside a
    comment opens no fence, and a comment opener inside a fence or a code span opens no comment.
    A comment opened mid-line hides text only up to its `-->` in the same paragraph, and an INTERRUPT line
    ends it; with no close it is plain text. A comment opened at a line start is a block (`block_comment_end`).
    A fence opens only at a line start and closes on the same character, at least as long, with nothing else on
    the line; an unclosed fence runs to the end. A line indented 4 spaces (or a tab) is code, unless it
    continues a paragraph line just above it or sits in a list item. `widths` holds the content column of each
    open list item, innermost last; a column-0 fence empties it, and a list item, an INTERRUPT line, or a
    non-blank line after a blank line pops each item it is not indented into. A rule line is not a list item.
    A lazy text line pops nothing. A paragraph is searched for code spans and comments only when it holds a
    `-->` or two backticks, so a paragraph of bare openers, or with one lone backtick, costs one scan, not one
    search per opener.
    """
    kept, pos, size = [], 0, len(text)
    hit, searched = None, False
    prev, widths = "blank", []  # prev: the last line's kind, "blank", "text" or "code"
    pend, marked = -1, False  # the end of the paragraph holding pos, and whether it holds a backtick or a `-->`
    while pos < size:
        end = text.find("\n", pos)
        end = size if end < 0 else end
        at_line_start = pos == 0 or text[pos - 1] == "\n"
        found = FENCE.match(text, pos) if at_line_start else None
        if found:
            marker = found.group(1)
            if found.start(1) == pos:
                widths.clear()
            pos = end + 1
            while pos < size:
                end = text.find("\n", pos)
                end = size if end < 0 else end
                close = FENCE.match(text, pos)
                pos = end + 1
                if close and close.group(1)[0] == marker[0] and len(close.group(1)) >= len(marker) \
                        and not text[close.start():end].strip().strip(marker[0]):
                    break
            prev = "blank"
            continue
        if at_line_start:
            line = text[pos:end]
            flat = line.expandtabs(4)
            indent = len(flat) - len(flat.lstrip(" "))
            if not line.strip():
                prev = "blank"
            else:
                item = LIST_ITEM.match(line) and not RULE_LINE.match(text, pos)
                if prev == "blank" or item or INTERRUPT_LINE.match(text, pos):
                    while widths and indent < widths[-1]:
                        widths.pop()
                if line.startswith(("    ", "\t")) and prev != "text" and not widths:
                    prev = "code"
                    pos = end + 1
                    continue
                if item:
                    widths.append(item_width(line))
                prev = "text"
                skip = block_comment_end(text, pos, end, bool(widths), widths[-1] if widths else 0)
                if skip is not None:
                    pos = skip
                    continue
        if pos > pend:
            blank = BLANK.search(text, pos)
            pend = blank.start() if blank else size
            tick = text.find("`", pos, pend)
            marked = (tick >= 0 and text.find("`", tick + 1, pend) >= 0) or text.find("-->", pos, pend) >= 0
        if marked and (not searched or (hit and hit.start() < pos)):
            hit, searched = SPAN_OR_COMMENT.search(text, pos), True
        if marked and hit and hit.start() < end:
            kept.append(text[pos:hit.start()])
            kept.append(" " if hit.group("code") else "")
            pos = hit.end()
            prev = "text"
        else:
            kept.append(text[pos:end] + "\n")
            pos = end + 1
    return " ".join("".join(kept).split())


def holds_line(path: str) -> bool:
    with open(path, encoding="utf-8") as handle:
        return " ".join(TERSE_LINE.split()) in body_text(strip_frontmatter(handle.read()))


def default_paths(root: str):
    """The files a no-argument run reads. Returns (path, must_exist) pairs."""
    named = [os.path.join(root, "agents", role + ".md") for role in ROLES]
    folder = os.path.join(root, "agents")
    extra = []
    if os.path.isdir(folder):
        extra = sorted(os.path.join(folder, name) for name in os.listdir(folder)
                       if name.endswith(".md") and os.path.join(folder, name) not in named)
    return [(path, True) for path in named + extra + [os.path.join(root, LANE_TEXT)]]


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    targets = [(path, False) for path in argv] if argv else default_paths(ROOT)
    missing, unknown = [], []
    for path, must_exist in targets:
        if must_exist and not os.path.exists(path):
            missing.append("%s: file is missing; it must hold the terse line" % path)
            continue
        try:
            if not holds_line(path):
                missing.append("%s: lacks the terse line (TERSE_LINE in lint/check_agent_terse_line.py)" % path)
        except (OSError, UnicodeDecodeError) as err:
            unknown.append("%s: unknown, could not read it (%s)" % (path, err.__class__.__name__))
    for line in missing + unknown:
        print(line)
    return 1 if missing else 2 if unknown else 0


if __name__ == "__main__":
    sys.exit(main())
