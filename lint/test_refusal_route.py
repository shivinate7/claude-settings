#!/usr/bin/env python3
"""No refusal reason in the local merge gates names the route a session may not take (lane local-tier-file, rule
git-remedy-never-names-target). The launcher, its role file and its batch-runner argument are the route.

    python3 lint/test_refusal_route.py

Stdlib and unittest. The reason texts are read with the ast module, so a comment or a docstring that names the route is not a reason.
"""
import ast
import os
import unittest

REPO = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SOURCES = ("hooks/guard_merge.py", "merge/merge.py")
REASON_NAMES = ("_REASON", "_REFUSAL", "_CITE")  # a refusal's text, and the citation that closes it
FORBIDDEN = ("claude-role", "CS_SESSION_ROLE", "batch-runner launcher")


def reason_texts(path):
    """-> {name: text}: each module-level string constant named like a refusal, with its implicit concatenation joined."""
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    texts = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        name = node.targets[0].id
        if name.endswith(REASON_NAMES):
            texts[name] = "".join(part.value for part in ast.walk(node.value)
                                  if isinstance(part, ast.Constant) and isinstance(part.value, str))
    return texts


class RefusalRoute(unittest.TestCase):
    def test_the_scan_reaches_the_known_reasons(self):
        # Scope first: a walk that reads too little passes every reason below and proves nothing.
        guard = reason_texts(os.path.join(REPO, "hooks", "guard_merge.py"))
        merge = reason_texts(os.path.join(REPO, "merge", "merge.py"))
        self.assertIn("LOCAL_REPO_REASON", guard, "the scan does not reach guard_merge.py's LOCAL_REPO_REASON")
        self.assertIn("LOCAL_ROLE_REFUSAL", merge, "the scan does not reach merge.py's LOCAL_ROLE_REFUSAL")

    def test_no_refusal_reason_names_the_launcher_route(self):
        found = []
        for rel in SOURCES:
            for name, text in sorted(reason_texts(os.path.join(REPO, rel)).items()):
                for token in FORBIDDEN:
                    if token in text:
                        found.append("%s %s names %r" % (rel, name, token))
        self.assertEqual(found, [], "a refusal's remedy names the route a session may not take:\n  " + "\n  ".join(found))


if __name__ == "__main__":
    unittest.main(verbosity=2)
