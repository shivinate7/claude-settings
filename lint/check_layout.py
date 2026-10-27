#!/usr/bin/env python3
"""Checks that every reader of a record path takes it from lint/layout.json, and holds none of its own.

lint/layout.json is the one list of where each kind of file lives (decision one-layout-every-repo).
Three things can drift from it, and this check reads each:

  1. The guard's literal. hooks/guard.py reads the layout file at run time from RECORD_LAYOUT_FILE,
     its own literal. That literal must equal LAYOUT_FILE in lint/layout.py.
  2. A path literal in a reader: any Python file in lint/, hooks/, merge/ or janitor/, tests and
     mutation tests aside. A string constant there may not name a record
     path: a layout, legacy or legacy-repos path of a record or listed kind, the notes file or the todo file, followed by `/` or holding one, at
     either end or inside (`decisions/`, `docs/decisions`, `x/decisions/a.md`), or a bare folder
     name passed to a `join` or a `/` (`Path(root) / "decisions"`).
     Any other bare kind name (`"decisions"`) is a key into the layout, not a path, and passes. Docstrings pass. The Python parser reads the code,
     so a path in a comment never counts.
  3. The actions and the stamp examples. Each action input that names the records folder defaults
     to "" (the layout's folder), its script assigns no record path, and each stamp example keeps
     its record folders under docs/.

    python3 lint/check_layout.py [--root DIR]

Exits 0 and prints nothing on agreement. Exits 1 and names each site that disagrees.
"""
import ast
import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

GUARD = "hooks/guard.py"
GUARD_NAME = "RECORD_LAYOUT_FILE"
READER_DIRS = ("lint", "hooks", "merge", "janitor")  # every Python file in them, tests and mutation tests aside
NOT_READERS = ("test_", "mutate_", "prove_")
ACTION_INPUTS = (("actions/ruling-kind/action.yml", "records-dir"), ("actions/ste-lint/action.yml", "decisions-dir"))
ACTION_SCRIPTS = ("actions/ruling-kind/check.sh", "actions/ste-lint/run.sh")
STAMP_EXAMPLES = "actions/stamp/examples"


def read(rel):
    with open(os.path.join(ROOT, *rel.split("/")), encoding="utf-8") as handle:
        return handle.read()


FILE_KINDS = ("debt-notes", "todo")  # record files that are not a listed folder


def record_paths(data):
    """Every layout, legacy and legacy-repos path of a kind marked record or listed, or in FILE_KINDS."""
    paths = set()
    legacy = data.get("legacy", {})
    for name, kind in data["kinds"].items():
        if kind.get("record") or kind.get("listed") or name in FILE_KINDS:
            paths.add(kind["path"].strip("/"))
            if kind["path"] in legacy:
                paths.add(legacy[kind["path"]].strip("/"))
            paths.update(entry[name].strip("/") for entry in data.get("legacy-repos", {}).values() if name in entry)
    return paths


def path_literal(value, paths):
    """True when a string constant names a record path rather than a kind."""
    value = value.replace("\\", "/")
    if value.startswith("./"):
        value = value[2:]
    for path in paths:
        if value == path and "/" in path:
            return True
        if value.startswith(path + "/") or ("/" + path + "/") in value or value.endswith("/" + path):
            return True
    return False


def docstrings(tree):
    """The id of each docstring constant: the first statement of a module, class or function."""
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                found.add(id(first.value))
    return found


def guard_literal(tree):
    """The guard's RECORD_LAYOUT_FILE as a `/` path, or None when it is not a literal join or string."""
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == GUARD_NAME for t in node.targets):
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                return value.value.replace("\\", "/")
            if isinstance(value, ast.Call) and all(isinstance(a, ast.Constant) and isinstance(a.value, str) for a in value.args):
                return "/".join(a.value for a in value.args)
    return None


def input_default(text, name):
    """The `default:` of input `name` in an action.yml, unquoted, or None."""
    block = re.search(r"^  %s:\s*\n((?:    .*\n|\s*\n)*)" % re.escape(name), text, re.M)
    if not block:
        return None
    found = re.search(r"^    default:\s*(.*?)\s*$", block.group(1), re.M)
    return found.group(1).strip("\"'") if found else None


def problems():
    spec = importlib.util.spec_from_file_location("layout_under_check", os.path.join(ROOT, "lint", "layout.py"))
    layout = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(layout)  # the module under check, from ROOT, never the one beside this file
    data = json.loads(read(layout.LAYOUT_FILE))
    layout.legacy_repos()  # LayoutError on an entry with an unknown kind or a path outside the repo
    paths = record_paths(data)
    found = []

    guard_tree = ast.parse(read(GUARD))
    literal = guard_literal(guard_tree)
    if literal != layout.LAYOUT_FILE:
        found.append("%s: %s is %r, not lint/layout.py LAYOUT_FILE %r" % (GUARD, GUARD_NAME, literal, layout.LAYOUT_FILE))

    readers = sorted("%s/%s" % (folder, name) for folder in READER_DIRS
                     if os.path.isdir(os.path.join(ROOT, folder))
                     for name in os.listdir(os.path.join(ROOT, folder))
                     if name.endswith(".py") and not name.startswith(NOT_READERS))
    for rel in readers:
        tree = guard_tree if rel == GUARD else ast.parse(read(rel))
        skip = docstrings(tree)
        joined = set()  # a bare folder name as a path part: os.path.join(ROOT, "decisions", ...)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", getattr(node.func, "id", "")) == "join":
                joined.update(id(a) for a in node.args if isinstance(a, ast.Constant) and a.value in paths)
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):  # Path(root) / "decisions"
                joined.update(id(a) for a in (node.left, node.right) if isinstance(a, ast.Constant) and a.value in paths)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip \
                    and (path_literal(node.value, paths) or id(node) in joined):
                found.append("%s:%d: holds the record path %r; read it from lint/layout.py" % (rel, node.lineno, node.value))

    for rel, name in ACTION_INPUTS:
        default = input_default(read(rel), name)
        if default != "":
            found.append("%s: input %s defaults to %r, not \"\" (the layout's folder)" % (rel, name, default))
    # A shell line names a record path when it holds one with a `/`, or gives a bare folder name as a
    # default or a value: `${X-decisions}`, `${X:-decisions}`, `X=decisions`. A word in a message does not.
    names = "|".join(map(re.escape, sorted(paths, key=len, reverse=True)))
    shell_path = re.compile(r"(?<![\w.-])(?:\./)?((?:%s)/[\w./-]*|(?:[\w.-]+/)+(?:%s)(?:/[\w./-]*)?)" % (names, names)
                            + r"|(?:\$\{\w+:?-|\b\w+=)[\"']?(%s)[\"']?(?=[\s}]|$)" % names)
    for rel in ACTION_SCRIPTS:
        for n, line in enumerate(read(rel).split("\n"), 1):
            hit = shell_path.search(line.split("#", 1)[0])
            if hit:
                found.append("%s:%d: names the record path %r; leave it to the layout" % (rel, n, hit.group(1) or hit.group(2)))

    names = sorted(n for n in os.listdir(os.path.join(ROOT, *STAMP_EXAMPLES.split("/"))) if n.endswith(".json"))
    for name in names:
        rel = STAMP_EXAMPLES + "/" + name
        for kind in json.loads(read(rel)).get("kinds", []):
            folder = kind.get("folder", "")
            if folder and not folder.startswith("docs/"):
                found.append("%s: kind %s keeps its records at %r, outside docs/" % (rel, kind.get("id"), folder))
    return found


def main(argv):
    global ROOT
    if argv[:1] == ["--root"] and len(argv) == 2:
        ROOT = os.path.abspath(argv[1])
    elif argv:
        print("check_layout: FAIL: usage: check_layout.py [--root DIR]")
        return 1
    try:
        found = problems()
    except Exception as err:  # a check that cannot read its sources is red, never green
        print("check_layout: FAIL: cannot read the layout or a reader: %s: %s" % (type(err).__name__, err))
        return 1
    for line in found:
        print("check_layout: FAIL: " + line)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
