#!/usr/bin/env python3
"""Fails when a test_*.py pops or deletes CLAUDE_CONFIG_DIR from the environment at import time and never sets it.

Such a file runs its cases with the variable unset, so a case that reads the config folder reads the real ~/.claude. Only an import-time
pop or del counts: it reaches every case. A pop inside one test method, or inside patch.dict, is that case's own choice. A pop is cleared
by a set at module level after it, or by a set in setUpModule(). A set in one test method or inside patch.dict does not clear it.
A test file that does not parse is a problem too.

    python3 lint/check_tests_set_config.py [--root DIR]     # DIR defaults to this script's repo
"""
import ast
import os
import sys

VAR = "CLAUDE_CONFIG_DIR"
SETTERS = ("update", "setdefault")  # os.environ.<name>(...) forms that set a key
SKIP_DIRS = ("node_modules", "__pycache__")


def is_environ(node):
    """True for `os.environ` or a bare `environ`."""
    return (isinstance(node, ast.Attribute) and node.attr == "environ") or (isinstance(node, ast.Name) and node.id == "environ")


def is_var(node):
    return isinstance(node, ast.Constant) and node.value == VAR


def names_var(node, loop_names):
    """True when `node` is the string VAR, or a loop variable that iterates over a literal holding it."""
    return is_var(node) or (isinstance(node, ast.Name) and node.id in loop_names)


def is_patch_dict(item):
    call = item.context_expr
    return isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == "dict"


def import_time(body, loop_names=()):
    """Yield each statement that runs at import time: the module body, and what sits in its if, for, while, try, with and class
    blocks. A def is skipped, and so is a with patch.dict block, whose changes the block undoes. `loop_names` holds the loop
    variables that iterate over a literal naming VAR."""
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if isinstance(node, ast.With) and any(is_patch_dict(item) for item in node.items):
            continue
        yield node, loop_names
        inner = loop_names
        if isinstance(node, ast.For) and isinstance(node.target, ast.Name) and isinstance(node.iter, (ast.Tuple, ast.List, ast.Set)) \
                and any(is_var(element) for element in node.iter.elts):
            inner = loop_names + (node.target.id,)
        for field in ("body", "orelse", "finalbody"):
            yield from import_time(getattr(node, field, None) or [], inner)
        for handler in getattr(node, "handlers", None) or []:
            yield from import_time(handler.body, inner)


def removal_line(statement, loop_names):
    """The line of an os.environ pop or del of VAR in this one statement, else None."""
    if isinstance(statement, ast.Delete):
        for target in statement.targets:
            if isinstance(target, ast.Subscript) and is_environ(target.value) and names_var(target.slice, loop_names):
                return statement.lineno
    if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
        call = statement.value
        if isinstance(call.func, ast.Attribute) and call.func.attr == "pop" and is_environ(call.func.value) \
                and call.args and names_var(call.args[0], loop_names):
            return statement.lineno
    return None


def sets_var(node):
    """True when `node` is, or holds, an assignment of VAR in os.environ."""
    for part in ast.walk(node):
        if isinstance(part, ast.Assign):
            for target in part.targets:
                if isinstance(target, ast.Subscript) and is_environ(target.value) and is_var(target.slice):
                    return True
        elif isinstance(part, ast.Call) and isinstance(part.func, ast.Attribute) and part.func.attr in SETTERS and is_environ(part.func.value):
            if any(keyword.arg == VAR for keyword in part.keywords):
                return True
            if any(isinstance(arg, ast.Dict) and any(is_var(key) for key in arg.keys) for arg in part.args):
                return True
            if part.func.attr == "setdefault" and part.args and is_var(part.args[0]):
                return True
        elif isinstance(part, ast.Call) and isinstance(part.func, ast.Attribute) and part.func.attr == "putenv" \
                and part.args and is_var(part.args[0]):
            return True
    return False


def file_problem(path, rel):
    """One problem string for the test file at `path`, else None."""
    try:
        with open(path, encoding="utf-8") as handle:
            tree = ast.parse(handle.read(), filename=path)
    except (OSError, SyntaxError, ValueError) as error:  # ValueError: a null byte; UnicodeDecodeError is one
        return "%s: does not parse (%s), so it is not known to set %s" % (rel, error.__class__.__name__, VAR)
    statements = list(import_time(tree.body))
    removals = [line for line in (removal_line(node, names) for node, names in statements) if line]
    if not removals:
        return None
    first = min(removals)
    for node, _ in statements:
        if getattr(node, "lineno", 0) > first and not isinstance(node, (ast.If, ast.For, ast.While, ast.Try, ast.With, ast.ClassDef)) \
                and sets_var(node):
            return None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "setUpModule" and sets_var(node):
            return None
    return "%s:%d: pops or deletes %s at import and never sets it, so its cases read the real ~/.claude" % (rel, first, VAR)


def problems(root):
    """One string per test_*.py under `root` that pops or deletes VAR at import and never sets it, each starting with `<path>:`."""
    found = []
    for folder, dirs, files in os.walk(root):
        dirs[:] = sorted(name for name in dirs if not name.startswith(".") and name not in SKIP_DIRS)
        for name in sorted(files):
            if name.startswith("test_") and name.endswith(".py"):
                path = os.path.join(folder, name)
                problem = file_problem(path, os.path.relpath(path, root).replace(os.sep, "/"))
                if problem:
                    found.append(problem)
    return found


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    if argv[:1] == ["--root"] and len(argv) > 1:
        root = argv[1]
    found = problems(root)
    for line in found:
        print(line)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
