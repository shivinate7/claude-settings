#!/usr/bin/env python3
"""Fails when a GLOSSARY.md row has no home, or a change adds a path that uses a "not" name.

GLOSSARY.md holds one table under the `## Terms` heading: term, meaning, home, not. Two tests:

- Each row's home is an existing file, or `rule:<id>` that names a rule marker in RULE_FILES.
- Each file the change adds (against origin/main, renames counted as adds) has no path segment
  that holds a name from a row's "not" cell. A name matches whole lowercase words, split on any
  character that is not a letter or a digit, inside one segment: `handover` matches
  `hooks/handover_note.py`, not `docs/handovers.md`.

It reads paths only, never prose, so a sentence that names a "not" word passes. A path that
already exists on the base is not checked or renamed.

    python3 lint/check_glossary.py [file ...]
        # files given: check those paths, skip git
"""
import os
import re
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
sys.path.insert(0, HERE)
import _nowindow  # noqa: E402  the one home of a no-window child start (hooks/_nowindow.py)
from rule_audit import ANCHOR_RE, RULE_FILES  # noqa: E402  the one home of the rule marker list

ROOT = os.path.dirname(HERE)
GLOSSARY = "GLOSSARY.md"
SECTION = "## Terms"
NONE = ("", "-", "—")  # a "not" cell that lists no name
WORD_RE = re.compile(r"[^a-z0-9]+")


def read(rel):
    try:
        with open(os.path.join(ROOT, *rel.split("/")), encoding="utf-8-sig") as f:
            return f.read()
    except OSError:
        return None


def words(text):
    return [w for w in WORD_RE.split(text.lower()) if w]


def cells(line):
    """The cells of one table row, or None when the line is not a row."""
    line = line.strip()
    if not (line.startswith("|") and line.endswith("|")):
        return None
    return [c.strip() for c in line[1:-1].split("|")]


def items(cell):
    """The comma-separated values of a cell, with backticks removed."""
    return [v.strip().strip("`").strip() for v in cell.split(",") if v.strip().strip("`").strip()]


def rows(text):
    """(term, homes, not names) for each data row of the table under SECTION."""
    out, inside = [], False
    for line in text.split("\n"):
        if line.startswith("## "):
            inside = line.strip() == SECTION
            continue
        c = cells(line) if inside else None
        if not c or len(c) != 4 or set(c[0]) <= set("-: "):
            continue
        if c[0].lower() == "term":  # the header row
            continue
        names = [] if c[3] in NONE else items(c[3])
        out.append((c[0].strip("`"), items(c[2]), names))
    return out


def home_problems(term, homes, ids):
    if not homes:
        return ["row '%s' has no home" % term]
    out = []
    for h in homes:
        if h.startswith("rule:"):
            if h[5:] not in ids:
                out.append("row '%s': home %s is not a rule marker in %s" % (term, h, ", ".join(RULE_FILES)))
        elif read(h) is None and not os.path.isdir(os.path.join(ROOT, *h.rstrip("/").split("/"))):
            out.append("row '%s': home %s does not exist" % (term, h))
    return out


def path_problems(path, table):
    out = []
    for seg in path.replace("\\", "/").split("/"):
        seg_words = words(seg)
        for term, _homes, names in table:
            for name in names:
                n = words(name)
                if n and any(seg_words[i:i + len(n)] == n for i in range(len(seg_words) - len(n) + 1)):
                    out.append("%s uses '%s'; the glossary name is '%s'" % (path, name, term))
    return out


def added():
    cmd = ["git", "diff", "--name-only", "--no-renames", "--diff-filter=A", "origin/main...HEAD"]
    r = _nowindow.run(cmd, cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")
    if r.returncode:
        print("check_glossary: UNKNOWN, git diff failed: " + r.stderr.strip())
        sys.exit(1 if os.environ.get("CI") else 0)  # CI exit code is a verdict: unknown is red there
    return r.stdout.split("\n")


def main(args):
    unknown = [a for a in args if a.startswith("-")]
    if unknown:  # read as a path, an unknown option would skip git and check nothing
        print("check_glossary: FAIL: unknown option: %s" % " ".join(unknown))
        return 1
    text = read(GLOSSARY)
    if text is None:
        print("check_glossary: FAIL: %s cannot be read" % GLOSSARY)
        return 1
    table = rows(text)
    if not table:  # a parser that finds nothing must not read as clean
        print("check_glossary: FAIL: %s has no rows under '%s'" % (GLOSSARY, SECTION))
        return 1
    ids = {i for rel in RULE_FILES for i in ANCHOR_RE.findall(read(rel) or "")}
    bad = [p for term, homes, _names in table for p in home_problems(term, homes, ids)]
    for path in [p for p in (args or added()) if p]:
        bad += path_problems(path, table)
    for p in bad:
        print("check_glossary: FAIL: " + p)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
