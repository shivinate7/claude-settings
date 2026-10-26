#!/usr/bin/env python3
"""Fails when docs/decisions/agent-model-cap.md lacks one row per skill under skills/.

The model-per-role table has one row per skill, each saying
"no model pin; runs on the caller's model". A skill is a folder directly under skills/ that
holds SKILL.md, as in lint/check_agent_models.py. A row is a table line whose first cell is
skill `NAME`. NAME must equal the folder name. Rows inside a fenced block or a multi-line HTML
comment do not count.

    python3 lint/check_skill_model_rows.py

Exits 0 and prints nothing when clean. Exits 1 and prints one line per problem, naming the
skill. Exits 2, naming the path, when the record or skills/ cannot be read.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout  # noqa: E402  the one home of where records live (lint/layout.json)

RECORD = os.path.join(ROOT, *layout.path(ROOT, "decisions").split("/"), "agent-model-cap.md")
SKILLS = os.path.join(ROOT, "skills")
ROW = re.compile(r"^\|\s*skill `([^`]+)`\s*\|")
FENCE = re.compile(r"^(`{3,}|~{3,})")
CODE_SPAN = re.compile(r"(`+)(?!`).+?(?<!`)\1(?!`)")
PHRASES = ("no model pin", "runs on the caller's model")


def opens_comment(s, inside):
    """True when s leaves an HTML comment open at its end. `inside` says s starts in one.
    A "<!--" in a code span is plain text."""
    if inside:
        if "-->" not in s:
            return True
        s = s.split("-->", 1)[1]
    s = CODE_SPAN.sub("", s)
    pos = s.find("<!--")
    while pos != -1:
        end = s.find("-->", pos + 4)
        if end == -1:
            return True
        pos = s.find("<!--", end + 3)
    return False


def live_lines(text, problems=None):
    """Yield the lines outside fenced blocks and multi-line HTML comments. A fence or comment still open at
    the end hides every later line: when `problems` is a list, it gets one line naming the open one."""
    fence, comment = None, False
    fence_at = comment_at = 0
    for number, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if fence:
            # A fence closes only on the same character, at least as long, with nothing after it.
            if s and set(s) == {fence[0]} and len(s) >= len(fence):
                fence = None
            continue
        if not comment:
            opener = FENCE.match(s)
            if opener:
                fence, fence_at = opener.group(1), number
                continue
            yield line
        was = comment
        comment = opens_comment(s, comment)
        if comment and (not was or "-->" in s):
            comment_at = number
    if problems is not None:
        if fence:
            problems.append("unclosed fence opened on line %d: the lines after it are not read" % fence_at)
        if comment:
            problems.append("unclosed comment opened on line %d: the lines after it are not read" % comment_at)


def skill_names(skills=SKILLS):
    """Folders directly under skills/ that hold a file named exactly SKILL.md.
    `skills` is the folder to list. lint/hook_catalog.py passes its own root's skills/."""
    names = []
    if not os.path.isdir(skills):
        return names  # main() fails a missing skills/ itself; a settings root with no skills/ has none
    for name in os.listdir(skills):
        folder = os.path.join(skills, name)
        if name.startswith(".") or name == "__pycache__" or not os.path.isdir(folder):
            continue
        # listdir gives the real case on every platform; the entry must also be a file
        if "SKILL.md" in os.listdir(folder) and os.path.isfile(os.path.join(folder, "SKILL.md")):
            names.append(name)
    return sorted(names)


def main():
    try:
        with open(RECORD, encoding="utf-8-sig") as handle:
            text = handle.read()
        if not os.path.isdir(SKILLS):
            raise NotADirectoryError("%s is not a folder" % SKILLS)
        names = skill_names()
    except (OSError, UnicodeDecodeError) as err:
        print("check_skill_model_rows: cannot read input: %s" % err)
        return 2
    rows = {}
    problems = []
    for line in live_lines(text, problems):
        found = ROW.match(line.strip())
        if not found:
            continue
        name = found.group(1)
        rows[name] = rows.get(name, 0) + 1
        if not all(p in line.strip().split("|")[2] for p in PHRASES):  # the second cell only
            problems.append("skill `%s`: row must say \"%s\" and \"%s\"" % ((name,) + PHRASES))
    for name in names:
        if name not in rows:
            problems.append("skill `%s`: no row in %s" % (name, os.path.relpath(RECORD, ROOT).replace(os.sep, "/")))
    for name, count in sorted(rows.items()):
        if name not in names:
            problems.append("skill `%s`: stale row, no skills/%s/SKILL.md" % (name, name))
        if count > 1:
            problems.append("skill `%s`: %d rows, need exactly one" % (name, count))
    if problems:
        print("\n".join(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
