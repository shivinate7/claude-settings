#!/usr/bin/env python3
"""Fails if an agent role file or the lane start text lacks the one short-output line.

TERSE_LINE is the one home of the line. Each agents/*.md file and the lane start text
(skills/project-ops/templates/operating-model.md) must hold it in body text. A line inside a code
fence (``` or ~~~), an HTML comment or an inline code span does not count: quoted text is not an
instruction. Whitespace collapses, so the line may wrap.

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
# A code span hides a comment opener inside it and is itself dropped. A comment with no close hides the rest of the text.
SPAN_OR_COMMENT = re.compile(r"(?P<code>(`+)(?:(?!\2(?!`)).|\n)*?\2(?!`))|(?P<comment><!--.*?(?:-->|\Z))", re.DOTALL)


def body_text(text: str) -> str:
    """The text with fences, comments and code spans removed and whitespace collapsed.

    One pass in reading order, so each construct hides the others' markers: a fence marker inside a
    comment opens no fence, and a comment opener inside a fence or a code span opens no comment.
    A fence opens only at a line start and closes on the same character, at least as long, with
    nothing else on the line; an unclosed fence runs to the end.
    """
    kept, pos, size = [], 0, len(text)
    hit, searched = None, False
    while pos < size:
        end = text.find("\n", pos)
        end = size if end < 0 else end
        at_line_start = pos == 0 or text[pos - 1] == "\n"
        found = FENCE.match(text, pos) if at_line_start else None
        if found:
            marker = found.group(1)
            pos = end + 1
            while pos < size:
                end = text.find("\n", pos)
                end = size if end < 0 else end
                close = FENCE.match(text, pos)
                pos = end + 1
                if close and close.group(1)[0] == marker[0] and len(close.group(1)) >= len(marker) \
                        and not text[close.start():end].strip().strip(marker[0]):
                    break
            continue
        if not searched or (hit and hit.start() < pos):
            hit, searched = SPAN_OR_COMMENT.search(text, pos), True
        if hit and hit.start() < end:
            kept.append(text[pos:hit.start()])
            kept.append(" " if hit.group("code") else "")
            pos = hit.end()
        else:
            kept.append(text[pos:end] + "\n")
            pos = end + 1
    return " ".join("".join(kept).split())


def holds_line(path: str) -> bool:
    with open(path, encoding="utf-8") as handle:
        return " ".join(TERSE_LINE.split()) in body_text(handle.read())


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
