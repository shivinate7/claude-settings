#!/usr/bin/env python3
"""Fails when a hook module assigns one top-level name twice, or two guard test sections bind one.

The second assignment replaces the first at import, so the first value is dead code. A refusal
text that is assigned twice sends the reader to the wrong remedy.

Counted: top-level `Assign` and `AnnAssign` (with a value) whose target is a Name, alone or inside
a Tuple, List or Starred. Not counted: Subscript and Attribute targets, augmented assigns, bare
annotations, and anything inside a def, class, if, try or for. Those are mutation or a branch,
not a second binding. `hooks/test_*.py` is skipped: tests keep scratch state, not refusal text.

Guard sections: hooks/test_guard.py execs every tests/guard/s*.py in one namespace, so a top-level
name that two section files bind (assign, def or class) makes the later one replace the first. The
FAIL line is `NAME assigned at FILE:LINE and FILE:LINE`, first section in run order (header number)
first. Not counted: names inside if, try, with or for, a rebind inside one file, a binding that reads
its own name (an accumulator such as `X = X + [1]`), and FAMILY and TEMP_DIR, which the runner binds
and each section sets. No allowance applies to sections. A missing or empty tests/guard exits 2.

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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _guard_sections  # noqa: E402  the one home of how a section file's header reads

NAME = "check_hook_dup_names"
ALLOW = "lint/hook_dup_names_allow.json"
SECTION_DIR = "tests/guard"
# The runner binds these at hooks/test_guard.py:259 (FAMILY) and :265 (TEMP_DIR) and each section
# sets them, so they are not a clash. The runner exports no constant for them.
RUNNER_NAMES = frozenset({"FAMILY", "TEMP_DIR"})


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


def reads_name(node, names):
    """True when the expression `node` loads any of `names` (an accumulator reads its own name)."""
    return any(isinstance(n, ast.Name) and n.id in names for n in ast.walk(node))


def section_bindings(tree):
    """Map each name a section binds at top level (assign, def, class) to the line of its first binding
    that does not read its own name. A binding that reads itself extends an earlier one: not a clash."""
    seen = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            seen.setdefault(node.name, node.lineno)
            continue
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        for target in targets:
            bound = list(target_names(target))
            if reads_name(value, {n for n, _ in bound}):
                continue
            for name, line in bound:
                seen.setdefault(name, line)
    return seen


def scan_sections(root):
    """-> [(name, "FILE:LINE", "FILE:LINE")] for each later section file that rebinds a name an earlier
    one bound, in run order (header number, then file name)."""
    folder = os.path.join(root, *SECTION_DIR.split("/"))
    sections = _guard_sections.read(folder)
    if not sections:
        raise Unknown("no guard section file under %s, so no section was scanned" % folder)
    order = sorted(sections, key=lambda s: (s[1] is None, s[1] or 0, s[0]))
    first = {}  # name -> "FILE:LINE" of its first binding
    clashes = []
    for fname, _, text in order:
        rel = "%s/%s" % (SECTION_DIR, fname)
        try:
            tree = ast.parse(text, filename=rel)
        except (SyntaxError, ValueError) as e:
            raise Unknown("guard section %s does not parse: %s" % (rel, e))
        for name, line in section_bindings(tree).items():
            if name in RUNNER_NAMES:
                continue
            here = "%s:%d" % (rel, line)
            if name in first:
                clashes.append((name, first[name], here))
            else:
                first[name] = here
    return clashes


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
    root = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
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
        clashes = scan_sections(root)
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
    for name, first, second in clashes:
        fails.append("%s: FAIL: %s assigned at %s and %s" % (NAME, name, first, second))
    for line in fails:
        print(line)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
