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
PHRASES = ("no model pin", "runs on the caller's model")


def live_lines(text):
    """Yield the lines outside fenced blocks and multi-line HTML comments."""
    fence, comment = None, False
    for line in text.splitlines():
        s = line.strip()
        if fence:
            if s.startswith(fence):
                fence = None
        elif comment:
            comment = "-->" not in s
        elif s.startswith(("```", "~~~")):
            fence = s[:3]
        elif s.startswith("<!--") and "-->" not in s:
            comment = True
        else:
            yield line


def main():
    try:
        with open(RECORD, encoding="utf-8-sig") as handle:
            text = handle.read()
        names = sorted(n for n in os.listdir(SKILLS)
                       if os.path.isfile(os.path.join(SKILLS, n, "SKILL.md")))
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
    print("\n".join(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
