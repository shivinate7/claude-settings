#!/usr/bin/env python3
"""Fails when decisions/subagent-model-cap.md lacks one row per skill under skills/.

Owner ruling 2026-10-13: the model-per-role table has one row per skill, each saying
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
RECORD = os.path.join(ROOT, "decisions", "subagent-model-cap.md")
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


def live_lines(text):
    """Yield the lines outside fenced blocks and multi-line HTML comments."""
    fence, comment = None, False
    for line in text.splitlines():
        s = line.strip()
        if fence:
            # A fence closes only on the same character, at least as long, with nothing after it.
            if s and set(s) == {fence[0]} and len(s) >= len(fence):
                fence = None
            continue
        if not comment:
            opener = FENCE.match(s)
            if opener:
                fence = opener.group(1)
                continue
            yield line
        comment = opens_comment(s, comment)


def skill_names(skills=SKILLS):
    """Folders directly under skills/ that hold a file named exactly SKILL.md.
    `skills` is the folder to list. lint/hook_catalog.py passes its own root's skills/."""
    names = []
    for name in os.listdir(skills):
        folder = os.path.join(skills, name)
        if name.startswith(".") or name == "__pycache__" or not os.path.isdir(folder):
            continue
        if "SKILL.md" in os.listdir(folder):  # listdir gives the real case on every platform
            names.append(name)
    return sorted(names)


def main():
    try:
        with open(RECORD, encoding="utf-8-sig") as handle:
            text = handle.read()
        names = skill_names()
    except (OSError, UnicodeDecodeError) as err:
        print("check_skill_model_rows: cannot read input: %s" % err)
        return 2
    rows = {}
    problems = []
    for line in live_lines(text):
        found = ROW.match(line.strip())
        if not found:
            continue
        name = found.group(1)
        rows[name] = rows.get(name, 0) + 1
        if not all(p in line for p in PHRASES):
            problems.append("skill `%s`: row must say \"%s\" and \"%s\"" % ((name,) + PHRASES))
    for name in names:
        if name not in rows:
            problems.append("skill `%s`: no row in decisions/subagent-model-cap.md" % name)
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
