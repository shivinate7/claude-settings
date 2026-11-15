#!/usr/bin/env python3
"""Every name a hook or lint file imports from hooks/guard_merge.py resolves in that module (lane local-tier-file). A rename of a
helper leaves its importers behind; this is the check that finds them before a Stop hook does.

    python3 lint/test_guard_merge_imports.py

Stdlib and unittest. The importers are read with the ast module, at any depth, since lint/report_guard.py imports lazily in functions.
"""
import ast
import glob
import os
import sys
import unittest

REPO = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
HOOKS = os.path.join(REPO, "hooks")
sys.path.insert(0, HOOKS)  # guard_merge imports its sibling modules from the hooks folder


def guard_merge_imports(path):
    """-> [(line, name)]: each name the file imports from guard_merge, at any depth."""
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    return [(node.lineno, alias.name) for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module == "guard_merge" and not node.level
            for alias in node.names]


class GuardMergeImports(unittest.TestCase):
    def importers(self):
        """-> {relative path: [(line, name)]} for every hooks/ and lint/ file that imports from guard_merge."""
        found = {}
        for folder in ("hooks", "lint"):
            for path in sorted(glob.glob(os.path.join(REPO, folder, "*.py"))):
                names = guard_merge_imports(path)
                if names:
                    found[os.path.relpath(path, REPO).replace(os.sep, "/")] = names
        return found

    def test_the_walk_reaches_the_known_importers(self):
        # Scope first: a walk that finds too few importers passes every name below and proves nothing.
        found = self.importers()
        self.assertIn("lint/report_guard.py", found, "the walk does not reach lint/report_guard.py, which imports from guard_merge")
        self.assertIn("hooks/guard.py", found, "the walk does not reach hooks/guard.py, which imports from guard_merge")

    def test_every_name_imported_from_guard_merge_resolves(self):
        import guard_merge  # noqa: E402  the module under check; its own imports resolve from hooks/
        missing = []
        for rel, names in sorted(self.importers().items()):
            for line, name in names:
                if not hasattr(guard_merge, name):
                    missing.append("%s:%d imports %s, which hooks/guard_merge.py does not define" % (rel, line, name))
        self.assertEqual(missing, [], "a file imports a name guard_merge no longer defines:\n  " + "\n  ".join(missing))


if __name__ == "__main__":
    unittest.main(verbosity=2)
