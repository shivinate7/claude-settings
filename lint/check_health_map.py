#!/usr/bin/env python3
"""Fails when a hook, check or skill is named by no row of docs/health-map.json.

The health map lists what a person sees of this repo, one row per outcome: what it sees, a grade, why, and
the globs of the parts that serve it. A part that no row names is a part nobody grades, so the map would
read healthy while that part rots. This check keeps each part under at least one row.

A part is one of:
  hook   a hooks/*.py, hooks/*.mjs or hooks/*.sh file that is not a test (hooks/guard.py is_test_rel, the
         one home of what a test path is, and a name that starts with _test)
  check  a lint/check_*.py file that is not a test
  skill  a folder directly under skills/ (a folder whose name starts with a dot is not one)

A row covers a part when one of its globs matches the part's path with fnmatch rules. The path of a skill is
matched both as skills/<name> and as skills/<name>/. A glob that matches no part is not an error: the map
may name a part before it exists.

The map is {"rows": [{"n": int, "sees": str, "grade": str, "why": str, "covers": [glob, ...]}, ...]}. A grade
is green, amber, red or grey. Each n is unique and each covers list is not empty. Other keys are kept as
they are and never read. An empty rows list is valid: every part is then uncovered.

    python3 lint/check_health_map.py [--root DIR] [--map FILE]

DIR defaults to this script's repo. FILE defaults to docs/health-map.json under DIR.

Exit 0 prints "health map covers all N parts". Exit 1 prints one "uncovered <kind>: <path>" line per
uncovered part. Exit 2 prints "check_health_map: UNKNOWN, <reason>" when the map is missing, is not JSON, or
breaks the shape above, when the root holds no parts, or when a part's folder cannot be read. An unread map
is never clear.
"""
import fnmatch
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "hooks"))

NAME = "check_health_map"
MAP_REL = "docs/health-map.json"
GRADES = ("green", "amber", "red", "grey")
HOOK_EXTENSIONS = (".py", ".mjs", ".sh")


class Unknown(Exception):
    pass


def is_test_rel(rel):
    """The repo's one reader of what a test path is, loaded when the first path needs it.

    It does not know the test helpers named `_test*` (hooks/_test_x.py), so those are skipped here too."""
    if os.path.basename(rel).startswith("_test"):
        return True
    try:
        import guard  # hooks/guard.py is the one home of what a test path is
    except Exception as e:  # an import that fails for any reason must read as unknown, never as clear
        raise Unknown("cannot load hooks/guard.py to tell a test path: %s" % e)
    return guard.is_test_rel(rel)


def read_map(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except OSError as e:
        raise Unknown("%s does not read: %s" % (os.path.basename(path), e))
    except ValueError as e:
        raise Unknown("%s is not valid json: %s" % (os.path.basename(path), e))
    rows = data.get("rows") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise Unknown('%s has no "rows" list' % os.path.basename(path))
    seen = set()
    for i, r in enumerate(rows):
        label = "row %d" % (i + 1)
        if not isinstance(r, dict):
            raise Unknown("%s is not an object" % label)
        n = r.get("n")
        if isinstance(n, bool) or not isinstance(n, int):
            raise Unknown("%s has no integer n" % label)
        label = "row n=%d" % n
        if n in seen:
            raise Unknown("duplicate n: %d" % n)
        seen.add(n)
        for key in ("sees", "why"):
            if not isinstance(r.get(key), str):
                raise Unknown("%s has no %s text" % (label, key))
        if r.get("grade") not in GRADES:
            raise Unknown("%s has a bad grade %r, not one of %s" % (label, r.get("grade"), ", ".join(GRADES)))
        covers = r.get("covers")
        if not isinstance(covers, list) or not covers or not all(isinstance(g, str) and g for g in covers):
            raise Unknown("%s needs a covers list of globs, not empty" % label)
    return rows


def list_dir(path):
    try:
        return sorted(os.scandir(path), key=lambda e: e.name)
    except FileNotFoundError:
        return []  # a missing folder holds no parts; the zero-parts rule catches a root with none at all
    except OSError as e:
        raise Unknown("%s does not read: %s" % (path, e))


def find_parts(root):
    """Return [(kind, display path, [paths to match])], hooks first, then checks, then skills."""
    parts = []
    for e in list_dir(os.path.join(root, "hooks")):
        rel = "hooks/" + e.name
        if e.is_file() and e.name.endswith(HOOK_EXTENSIONS) and not is_test_rel(rel):
            parts.append(("hook", rel, [rel]))
    for e in list_dir(os.path.join(root, "lint")):
        rel = "lint/" + e.name
        if e.is_file() and e.name.startswith("check_") and e.name.endswith(".py") and not is_test_rel(rel):
            parts.append(("check", rel, [rel]))
    for e in list_dir(os.path.join(root, "skills")):
        if e.is_dir() and not e.name.startswith("."):
            rel = "skills/" + e.name
            parts.append(("skill", rel + "/", [rel, rel + "/"]))
    return parts


def covered(part, rows):
    return any(fnmatch.fnmatchcase(path, glob) for r in rows for glob in r["covers"] for path in part[2])


def main(argv):
    root = os.path.dirname(HERE)
    map_path = None
    args = list(argv)
    while args:
        a = args.pop(0)
        if a == "--root" and args:
            root = args.pop(0)
        elif a == "--map" and args:
            map_path = args.pop(0)
        else:  # an unknown option must never read as a pass
            print("%s: UNKNOWN, unknown option: %s" % (NAME, a))
            return 2
    try:
        rows = read_map(map_path or os.path.join(root, *MAP_REL.split("/")))
        parts = find_parts(root)
        if not parts:  # nothing scanned must never read as a pass
            raise Unknown("no parts under %s: no hooks, checks or skills, so the root is wrong" % root)
    except Unknown as e:
        print("%s: UNKNOWN, %s" % (NAME, e))
        return 2
    missing = [p for p in parts if not covered(p, rows)]
    for kind, rel, _ in missing:
        print("uncovered %s: %s" % (kind, rel))
    if missing:
        print("%s: FAIL: %d of %d parts have no row" % (NAME, len(missing), len(parts)))
        return 1
    print("health map covers all %d parts" % len(parts))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
