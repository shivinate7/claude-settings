#!/usr/bin/env python3
"""Fails when a hook module assigns one top-level name twice.

The second assignment replaces the first at import, so the first value is dead code. A refusal
text that is assigned twice sends the reader to the wrong remedy.

Counted: top-level `Assign` and `AnnAssign` (with a value) whose target is a Name, alone or inside
a Tuple, List or Starred. Not counted: Subscript and Attribute targets, augmented assigns, bare
annotations, and anything inside a def, class, if, try or for. Those are mutation or a branch,
not a second binding. `hooks/test_*.py` is skipped: tests keep scratch state, not refusal text.

An allowance is `{"hooks/x.py": {"NAME": "<reason>"}}` in lint/hook_dup_names_allow.json. An empty
reason fails, and so does an allowance for a name or file that is not duplicated now. A missing
allow file means no allowances.

    python3 lint/check_hook_dup_names.py [--root DIR]     # DIR defaults to this script's repo

Exit 0 clean and silent, 1 on a FAIL line, 2 when an input cannot be read (never green).
"""
import ast
import glob
import json
import os
import sys

NAME = "check_hook_dup_names"
ALLOW = "lint/hook_dup_names_allow.json"


class Unknown(Exception):
    pass


def target_names(target):
    """Yield each (name, lineno) bound by an assignment target; skip Subscript and Attribute."""
    if isinstance(target, ast.Name):
        yield target.id, target.lineno
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            yield from target_names(elt)
    elif isinstance(target, ast.Starred):
        yield from target_names(target.value)


def top_level_assignments(tree):
    """Map each name to the line numbers of its top-level assignments, in source order."""
    seen = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
        else:
            continue
        for target in targets:
            for name, line in target_names(target):
                seen.setdefault(name, []).append(line)
    return seen


def read_allow(root):
    path = os.path.join(root, *ALLOW.split("/"))
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise Unknown("%s does not read: %s" % (ALLOW, e))
    ok = isinstance(data, dict) and all(
        isinstance(names, dict) and all(isinstance(r, str) for r in names.values())
        for names in data.values())
    if not ok:
        raise Unknown('%s is not {"hooks/x.py": {"NAME": "reason"}}' % ALLOW)
    return data


def scan(root):
    hooks = os.path.join(root, "hooks")
    if not os.path.isdir(hooks):
        raise Unknown("no hooks folder under %s" % root)
    dups = {}  # rel path -> {name: [lines]} for names assigned more than once
    scanned = set()
    # The folder is escaped so a root such as r[x] is read as a path, not as a glob pattern.
    for path in sorted(glob.glob(os.path.join(glob.escape(hooks), "*.py"))):
        base = os.path.basename(path)
        if base.startswith("test_"):
            continue
        rel = "hooks/" + base
        scanned.add(rel)
        try:
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=rel)
        except (OSError, SyntaxError, ValueError) as e:
            raise Unknown("%s does not parse: %s" % (rel, e))
        found = {n: ls for n, ls in top_level_assignments(tree).items() if len(ls) > 1}
        if found:
            dups[rel] = found
    if not scanned:  # nothing scanned must never read as a pass
        raise Unknown("no hook modules under %s" % hooks)
    return dups, scanned


def main(argv):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    args = list(argv)
    while args:
        a = args.pop(0)
        if a == "--root" and args:
            root = args.pop(0)
        else:  # an unknown option must never read as a pass
            print("%s: FAIL: unknown option: %s" % (NAME, a))
            return 1
    try:
        allow = read_allow(root)
        dups, scanned = scan(root)
    except Unknown as e:
        print("%s: UNKNOWN, %s" % (NAME, e))
        return 2
    fails = []
    for rel, names in sorted(dups.items()):
        for name, lines in names.items():
            reason = allow.get(rel, {}).get(name)
            if reason is None:
                fails.append("%s: FAIL: %s: %s assigned at lines %s"
                             % (NAME, rel, name, ", ".join(str(n) for n in lines)))
            elif not reason.strip():
                fails.append("%s: FAIL: %s: %s: %s allowance for %s has an empty reason"
                             % (NAME, ALLOW, rel, name, name))
    for rel, names in sorted(allow.items()):
        if rel not in scanned:  # checked before the name loop so an empty name dict is still stale
            fails.append("%s: FAIL: %s: stale allowance, %s is not a scanned hook module"
                         % (NAME, ALLOW, rel))
            continue
        for name in names:
            if name not in dups.get(rel, {}):
                fails.append("%s: FAIL: %s: stale allowance, %s in %s is not assigned twice"
                             % (NAME, ALLOW, name, rel))
    for line in fails:
        print(line)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
