#!/usr/bin/env python3
"""Warns when a CLAUDE.md passes 200 lines. Never fails: a warning exits 0.

Claude Code loads each CLAUDE.md whole into every session, and its memory docs aim under 200
lines. A section that matters only under one folder moves to a path-scoped rule
(.claude/rules/<topic>.md with a `paths:` list of globs), which loads only when Claude reads a
matching file. Bulk checked-in data (fixtures, demo assets, vendored data) gets a Read deny rule
in the repo's .claude/settings.json, not a CLAUDE.md mention.

    python3 lint/check_claude_md_size.py [file ...]
        # no files: CLAUDE.md and .claude/CLAUDE.md under the current directory

A child repo runs it from its own root with this repo's path. A missing file is a skip.
"""
import os
import sys

MAX = 200
DOC = "https://code.claude.com/docs/en/memory"
DEFAULT = ("CLAUDE.md", os.path.join(".claude", "CLAUDE.md"))

args = sys.argv[1:]
unknown = [a for a in args if a.startswith("-")]
if unknown:  # read as a file name, an unknown option would skip and check nothing
    print("check_claude_md_size: FAIL: unknown option: %s" % " ".join(unknown))
    sys.exit(2)
for path in args or DEFAULT:
    if not os.path.isfile(path):
        print("check_claude_md_size: skip, no file: %s" % path)
        continue
    with open(path, encoding="utf-8", errors="replace") as f:
        n = len(f.read().splitlines())
    if n > MAX:
        print("check_claude_md_size: WARN: %s: %d lines, over %d. Move a section that matters only"
              " under one folder to a path-scoped rule, and give bulk data a Read deny rule. See %s"
              % (path.replace("\\", "/"), n, MAX, DOC))
    else:
        print("check_claude_md_size: ok: %s: %d lines" % (path.replace("\\", "/"), n))
sys.exit(0)
