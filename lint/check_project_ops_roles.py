#!/usr/bin/env python3
"""Fails when a session role has no role text or no brief template in skills/project-ops/templates/.

The roles are the ones the sentence "The session roles are the same on local and cloud: ..." of the
session-tiers record names (the folder layout.path(ROOT, "decisions") gives). Each role needs a
line `- **<Role>.**` in templates/operating-model.md (any case) and a non-empty brief template:
lane -> templates/brief.md, every other role -> templates/brief-<role, spaces as hyphens>.md.
The record and operating-model.md are read outside fenced blocks and multi-line HTML comments.

    python3 lint/check_project_ops_roles.py

Exits 0 and prints nothing when clean. Exits 1 and prints one line per problem, naming the role.
Exits 2, naming the path, when the record, operating-model.md, the templates folder or the
sentence cannot be read, or the sentence gives no roles.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout  # noqa: E402  the one home of where records live (lint/layout.json)
from check_skill_model_rows import live_lines  # noqa: E402  the one home for fences and multi-line comments

RECORD = os.path.join(ROOT, *layout.path(ROOT, "decisions").split("/"), "session-tiers.md")  # glossary-ok: the record's file name
TEMPLATES = os.path.join(ROOT, "skills", "project-ops", "templates")
MODEL = os.path.join(TEMPLATES, "operating-model.md")
SENTENCE = re.compile(r"The session roles are the same on local and cloud: ([^.]*)\.")
PARENTHETICAL = re.compile(r"\([^)]*\)")
SPLIT = re.compile(r",|\band\b")


def roles_of(record):
    """The roles the sentence names, in order. [] when the sentence is missing or names none."""
    found = SENTENCE.search("\n".join(live_lines(record)))
    if not found:
        return []
    body = PARENTHETICAL.sub("", found.group(1))
    return [part.strip() for part in SPLIT.split(body) if part.strip()]


def brief_name(role):
    return "brief.md" if role == "lane" else "brief-%s.md" % role.replace(" ", "-")


def read(path):
    with open(path, encoding="utf-8-sig") as handle:
        return handle.read()


def main():
    try:
        record = read(RECORD)
        if not os.path.isdir(TEMPLATES):
            raise NotADirectoryError("%s is not a folder" % TEMPLATES)
        model = read(MODEL)
    except (OSError, UnicodeDecodeError) as err:
        print("check_project_ops_roles: cannot read input: %s" % err)
        return 2
    roles = roles_of(record)
    if not roles:
        print("check_project_ops_roles: %s has no session roles sentence that names roles" % RECORD)
        return 2
    lines = list(live_lines(model))
    problems = []
    for role in roles:
        pattern = re.compile(r"- \*\*%s\.\*\*" % re.escape(role), re.IGNORECASE)
        if not any(pattern.match(line) for line in lines):
            problems.append("role `%s`: no role text" % role)
        name = brief_name(role)
        path = os.path.join(TEMPLATES, name)
        if not os.path.isfile(path):
            problems.append("role `%s`: no brief template templates/%s" % (role, name))
        elif os.path.getsize(path) == 0:
            problems.append("role `%s`: brief template templates/%s is empty" % (role, name))
    if problems:
        print("\n".join(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
