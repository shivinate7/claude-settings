#!/usr/bin/env python3
"""Fails when a test_*.py file defines a unittest.TestCase and never calls unittest.main.

Run directly, such a file does nothing: its cases never run, and the run reads as a pass. CI runs most
steps without bin/verdict, the one place that fails a run of zero tests, so a suite that loses its
`unittest.main()` call stays green and silent.

    python3 lint/check_suites_have_main.py [--root DIR]

DIR defaults to the repo root. A file counts when its name is test_*.py, it defines a class that has
a base named TestCase (unittest.TestCase, TestCase, IsolatedAsyncioTestCase), and its syntax tree holds
no call to unittest.main (or to a `main` imported from unittest) and no call to run_class, the shared
runner of one TestCase class (testing/cost_probe.py: loads the class and runs it with unittest's own text
runner). Hand runners that run their CostTests class that way are not problems. The scan reads the syntax tree, so a
TestCase named only in a string or a comment is no class, and a script with no TestCase is no suite.
A file another runner imports and runs is still a problem, unless ALLOWED names it with a reason.

Skips .git, node_modules and any `worktrees` folder under .claude (other checkouts, not this tree).

Exits 0 and prints nothing when clean. Exits 1 and prints one line per file:
"<path>: defines a TestCase but never calls unittest.main". An unparseable file is a problem too, since an
unread file is never clean.
"""
import ast
import os
import sys

# Repo-relative path (forward slashes) -> why the file may define a TestCase and never call unittest.main.
ALLOWED = {}

SKIP_DIRS = {".git", "node_modules", "__pycache__"}
RUN_CLASS = "run_class"  # testing/cost_probe.py run_class(case_class), the one home of running one TestCase class
SUFFIX = "defines a TestCase but never calls unittest.main"


def _is_testcase_base(node):
    if isinstance(node, ast.Attribute):
        return node.attr.endswith("TestCase")
    return isinstance(node, ast.Name) and node.id.endswith("TestCase")


def _unittest_main_names(tree):
    """Names bound to unittest.main by `from unittest import main [as x]`."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "unittest" and node.level == 0:
            for alias in node.names:
                if alias.name == "main":
                    names.add(alias.asname or alias.name)
    return names


def _has_testcase(tree):
    return any(isinstance(n, ast.ClassDef) and any(_is_testcase_base(b) for b in n.bases) for n in ast.walk(tree))


def _calls_main(tree):
    bare = _unittest_main_names(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "main" and isinstance(func.value, ast.Name) \
                and func.value.id == "unittest":
            return True
        if isinstance(func, ast.Name) and func.id in bare | {RUN_CLASS}:
            return True
        if isinstance(func, ast.Attribute) and func.attr == RUN_CLASS:
            return True
    return False


def _test_files(root):
    for folder, dirs, files in os.walk(root):
        rel_folder = os.path.relpath(folder, root).replace(os.sep, "/")
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not (d == "worktrees" and rel_folder == ".claude"))
        for name in sorted(files):
            if name.startswith("test_") and name.endswith(".py"):
                yield os.path.join(folder, name)


def problems(root):
    """A list of "<path>: ..." strings, one per test_*.py that defines a TestCase and never calls unittest.main."""
    found = []
    for path in _test_files(root):
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        if rel in ALLOWED:
            continue
        try:
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=path)
        except (OSError, SyntaxError, ValueError) as e:
            found.append("%s: cannot be read or parsed (%s)" % (rel, e))
            continue
        if _has_testcase(tree) and not _calls_main(tree):
            found.append("%s: %s" % (rel, SUFFIX))
    return found


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    root = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    if "--root" in argv:
        root = argv[argv.index("--root") + 1]
    found = problems(root)
    for line in found:
        print(line)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
