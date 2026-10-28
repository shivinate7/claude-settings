#!/usr/bin/env python3
"""No file names a retired repo. Standard library only.

    python3 -m unittest lint.test_retired_repos

The list is the "retired" object in docs/design/repo-colours.json, read through lint/repo_colour.py.
"""
import os
import re
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import repo_colour  # noqa: E402

REGISTRY = os.path.join("docs", "design", "repo-colours.json")


def names(text, old):
    """True when text names the retired repo: the bare name or owner/name, not a path part or a longer word."""
    return re.search(r"(?<![\w/.-])%s(?![\w-])|shivinate7/%s(?![\w-])" % ((re.escape(old),) * 2),
                     text, re.IGNORECASE) is not None


class RetiredRepos(unittest.TestCase):
    def setUp(self):
        self.retired = repo_colour.retired()
        self.assertTrue(self.retired, "the registry lists no retired repo")

    def test_registry_names_none(self):
        reg = repo_colour.load()
        for old in self.retired:
            self.assertNotIn(old, reg["repos"], "repos")
            self.assertNotIn(old, reg["sources"], "sources")
            self.assertNotIn(old, reg["rule"]["drawn"], "rule.drawn")
            self.assertIn(self.retired[old], reg["repos"], "the repo that took %s has no colour" % old)

    def test_matcher(self):
        for text in ("home-app's docs/design/", "shivinate7/home-app", "Home-App", "(home-app)"):
            self.assertTrue(names(text, "home-app"), text)
        for text in ("home's `records/home-app.md`", "ios/HomeApp/Views.swift", "home-apps", "my-home-app"):
            self.assertFalse(names(text, "home-app"), text)

    def test_no_tracked_file_names_a_retired_repo(self):
        files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                               check=True).stdout.splitlines()
        for rel in files:
            if rel in (REGISTRY.replace(os.sep, "/"), "lint/test_retired_repos.py") or not os.path.isfile(os.path.join(ROOT, rel)):
                continue
            with open(os.path.join(ROOT, rel), "rb") as f:
                text = f.read().decode("utf-8", "replace")
            for old in self.retired:
                self.assertFalse(names(text, old), "%s names retired %s" % (rel, old))


if __name__ == "__main__":
    unittest.main()
