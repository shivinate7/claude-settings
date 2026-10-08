#!/usr/bin/env python3
"""Fails if an agent or skill file sets a Haiku model in its frontmatter.

The guard's subagent-model-floor rule reads the model a spawn names. An agent file's own
`model:` key names no model in the tool input, so the guard never sees it. This check reads
the files instead. Sonnet is the floor (owner ruling 2026-10-07), except for the agent files named in
the guard's HAIKU_ROLES.

    python3 lint/check_agent_models.py [file ...]

With no argument it checks agents/*.md and skills/*/SKILL.md. Exits 0 and prints nothing when
clean. Exits 1 and names each file that sets a Haiku model.
"""
import glob
import importlib.util
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# One home for the role list: the guard's HAIKU_ROLES. Read it, never copy it.
_spec = importlib.util.spec_from_file_location("guard", os.path.join(ROOT, "hooks", "guard.py"))
_guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_guard)
HAIKU_ROLES = tuple(role.lower() for role in _guard.HAIKU_ROLES)
MODEL_KEY = re.compile(r"^model\s*:\s*(.*)$", re.IGNORECASE)


def frontmatter(text: str):
    """Return the frontmatter lines, [] with no frontmatter, None when it never closes."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return []
    for end in range(1, len(lines)):
        if lines[end].strip() == "---":
            return lines[1:end]
    return None


def haiku_model(text: str) -> str:
    for line in frontmatter(text) or []:
        found = MODEL_KEY.match(line)
        if found and "haiku" in found.group(1).lower():
            return found.group(1).strip()
    return ""


def is_haiku_role(path: str) -> bool:
    return (os.path.basename(os.path.dirname(path)) == "agents"
            and os.path.splitext(os.path.basename(path))[0].lower() in HAIKU_ROLES)


def main(argv) -> int:
    files = argv or sorted(
        glob.glob(os.path.join(ROOT, "agents", "*.md"))
        + glob.glob(os.path.join(ROOT, "skills", "*", "SKILL.md"))
    )
    bad = 0
    for path in files:
        with open(path, encoding="utf-8-sig") as handle:
            text = handle.read()
        if frontmatter(text) is None:
            print("%s: frontmatter never closes. Cannot read its model." % path)
            bad = 1
        elif haiku_model(text) and not is_haiku_role(path):
            print("%s: frontmatter sets a model below Sonnet. Sonnet is the floor." % path)
            bad = 1
    return bad


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
