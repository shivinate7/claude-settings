#!/usr/bin/env python3
"""Fails when a session role has no role text or no brief template in skills/project-ops/templates/.

The roles are the ones the sentence "The session roles are the same on local and cloud: ..." of the
session-tiers record names (the folder layout.path(ROOT, "decisions") gives). Each role needs a
line `- **<Role>.** <words>` in templates/operating-model.md (any case, a hyphen stands for a space) and
a brief template with text in it: lane -> templates/brief.md, every other role ->
templates/brief-<role, spaces as hyphens>.md.
The record and operating-model.md are read outside fenced blocks and multi-line HTML comments; a fence
or comment left open in operating-model.md is named as a problem.

    python3 lint/check_project_ops_roles.py

Exits 0 and prints nothing when clean. Exits 1 and prints one line per problem, naming the role.
Exits 2, naming the path, when the record, operating-model.md, the templates folder or the
sentence cannot be read, the sentence gives no roles, or its role list has commas and no final "and"
(a stray period cut it).
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
ANCHOR = r"\s+".join(["The", "session", "roles", "are", "the", "same", "on", "local", "and", "cloud:"])
# The list runs to the first period outside a parenthetical; the anchor may wrap at any whitespace.
SENTENCE = re.compile(ANCHOR + r"((?:\([^)]*\)|[^.])*)\.")
PARENTHETICAL = re.compile(r"\([^)]*\)")
SPLIT = re.compile(r",|\band\b")


class RoleListError(Exception):
    """The sentence's role list ends at a stray period."""


def roles_of(record):
    """The roles the sentence names, in order, lowercased, with hyphens read as spaces. [] when the sentence is missing or
    names none. Raises RoleListError when the list has commas and no final "and"."""
    found = SENTENCE.search("\n".join(live_lines(record)))
    if not found:
        return []
    body = PARENTHETICAL.sub("", found.group(1))
    if "," in body and not re.search(r"\band\b", body):
        raise RoleListError("the role list has commas and no final and, so a stray period may end it early")
    parts = (" ".join(part.lower().replace("-", " ").split()) for part in SPLIT.split(body))
    return [part for part in parts if part]


def brief_name(role):
    return "brief.md" if role == "lane" else "brief-%s.md" % role.replace(" ", "-")


def role_text_pattern(role):
    """`- **<Role>.**` then words, any case; a space in the role matches a space or a hyphen."""
    name = r"[ -]".join(re.escape(word) for word in role.split())
    return re.compile(r"- \*\*%s\.\*\*\s*\S" % name, re.IGNORECASE)


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
    try:
        roles = roles_of(record)
    except RoleListError as err:
        print("check_project_ops_roles: %s: %s" % (RECORD, err))
        return 2
    if not roles:
        print("check_project_ops_roles: %s has no session roles sentence that names roles" % RECORD)
        return 2
    problems = []
    lines = list(live_lines(model, problems))
    problems[:] = ["%s: %s" % (MODEL, problem) for problem in problems]
    for role in roles:
        pattern = role_text_pattern(role)
        if not any(pattern.match(line) for line in lines):
            problems.append("role `%s`: no role text" % role)
        name = brief_name(role)
        path = os.path.join(TEMPLATES, name)
        if not os.path.isfile(path):
            problems.append("role `%s`: no brief template templates/%s" % (role, name))
        elif not read(path).strip():
            problems.append("role `%s`: brief template templates/%s is empty" % (role, name))
    if problems:
        print("\n".join(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
