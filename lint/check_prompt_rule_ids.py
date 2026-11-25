#!/usr/bin/env python3
"""CI check: a rule id that a model prompt names has an anchor.

    python3 lint/check_prompt_rule_ids.py [--root DIR]

A model judge's prompt names the rule ids it may file a finding under. An id with no
`<!-- rule:<id> -->` anchor in a RULE_FILES file (lint/rule_audit.py) files its findings under a
dead id. The case that started this: JUDGED_RULES held `measure-before-priority`, and the anchor
was `style-measure-before-priority`.

WHAT IT READS. hooks/*.py with `ast`, only the prompt constants in PROMPT_CONSTANTS. A comment, a
docstring and any other string are not read. A name a prompt constant is built from (INSTRUCTIONS
= "..." + GH_PART) is read through, in the same module.
  - an `ids` constant (JUDGED_RULES): each string item is an id as written, whatever its prefix.
  - a `prose` constant: an id is a hyphenated word whose first segment is a family, that is, the
    first segment of some anchor in the rule files (`output`, `style`, `verification`, ...). An
    ordinary hyphenated word (`red-run`, `test-practices`) has no such first segment and is left
    alone.

WHAT IT CANNOT SEE. A prompt constant not in PROMPT_CONSTANTS (the other *_PROMPT constants of
hooks/call_judge.py, the prompts of other hook files) is not read. A prose id in a family no
anchor uses is not read, and an id split across two joined strings is not read. A hyphenated word
that starts with a family word reads as an id; a false alarm is cleared by renaming the word.

Exit 0 when each id has an anchor. Exit 1 and one line per bad id otherwise, or when no id was
read at all: a reader that sees nothing must not print ok.
"""
from __future__ import annotations

import ast
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import rule_audit  # noqa: E402  the one home of the anchor pattern and the anchor files

# hooks/ file -> {prompt constant: how its strings read}.
PROMPT_CONSTANTS = {
    "reply_judge.py": {"JUDGED_RULES": "ids", "INSTRUCTIONS": "prose"},
    "call_judge.py": {"SPAWN_PROMPT": "prose"},
    "sendmessage_state.py": {"WORDING_PROMPT": "prose"},
    "prose_judge.py": {"COMMON": "prose", "RULES": "prose"},
}
SLUG = r"[a-z0-9]+(?:-[a-z0-9]+)+"


def module_assignments(tree):
    """{name: [value node, ...]} for each module-level assignment."""
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            names = [node.target.id]
        else:
            continue
        for name in names:
            out.setdefault(name, []).append(node.value)
    return out


def constants_of(value, assigns, seen):
    """Each string Constant node under `value`, through a module-level name it uses."""
    found = []
    for node in ast.walk(value):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.append(node)
        elif isinstance(node, ast.Name) and node.id in assigns and node.id not in seen:
            seen.add(node.id)
            for part in assigns[node.id]:
                found.extend(constants_of(part, assigns, seen))
    return found


def physical_line(node, text, lines, start):
    """The 1-based line, from `start` on, inside `node`'s span, that holds `text`; the node's first line when none does."""
    end = getattr(node, "end_lineno", None) or node.lineno
    for n in range(max(start, node.lineno), end + 1):
        if text in lines[n - 1]:
            return n
    return node.lineno


def families(root):
    """The first segment of each anchor in the rule files under `root`."""
    return {a.split("-", 1)[0] for a in rule_audit.claude_md_anchors(rule_audit.rule_text(root))}


def prompt_ids(root):
    """[(path, line, id)] for each rule id a prompt constant names, sorted. path is `hooks/<file>.py`."""
    fams = families(root)
    prose_id = re.compile(r"(?<![\w-])((?:%s)-%s)(?![\w-])" % ("|".join(sorted(map(re.escape, fams))), SLUG)) if fams else None
    found = set()
    for path in sorted(glob.glob(os.path.join(root, "hooks", "*.py"))):
        wanted = PROMPT_CONSTANTS.get(os.path.basename(path))
        if not wanted:
            continue
        with open(path, encoding="utf-8") as f:
            source = f.read()
        lines = source.splitlines()
        tree = ast.parse(source)
        assigns = module_assignments(tree)
        rel = "hooks/" + os.path.basename(path)
        for name, kind in wanted.items():
            for value in assigns.get(name, []):
                for node in constants_of(value, assigns, {name}):
                    if kind == "ids":
                        ids = [node.value] if node.value else []
                    else:
                        ids = [m.group(1) for m in prose_id.finditer(node.value)] if prose_id else []
                    at = node.lineno
                    for i in ids:
                        at = physical_line(node, i, lines, at)
                        found.add((rel, at, i))
    return sorted(found)


def problems(root):
    """One message per id with no anchor, naming its file, line and id."""
    anchored = set(rule_audit.claude_md_anchors(rule_audit.rule_text(root)))
    where = " or ".join(p.replace(os.sep, "/") for p in rule_audit.RULE_FILES)
    return ["%s:%d: the prompt names rule id %s, which has no anchor in %s" % (path, line, rid, where)
            for path, line, rid in prompt_ids(root) if rid not in anchored]


def main(argv):
    root = rule_audit.ROOT
    if argv[:1] == ["--root"] and len(argv) == 2:
        root = os.path.abspath(argv[1])
    elif argv:
        print("usage: check_prompt_rule_ids.py [--root DIR]")
        return 2
    try:
        read = prompt_ids(root)
        bad = problems(root)
    except (OSError, SyntaxError, ValueError) as e:
        print("check_prompt_rule_ids: FAIL, could not read: %s" % e)
        return 1
    if not read:
        print("check_prompt_rule_ids: FAIL, no rule id read from any prompt constant (the reader sees nothing)")
        return 1
    for message in bad:
        print("check_prompt_rule_ids: FAIL, " + message)
    if bad:
        return 1
    print("check_prompt_rule_ids: ok, %d prompt rule ids, each anchored" % len(read))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
