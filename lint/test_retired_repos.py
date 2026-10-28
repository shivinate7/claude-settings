#!/usr/bin/env python3
"""No file names a retired repo. Standard library only.

    python3 -m unittest lint.test_retired_repos

The list is the "retired" object in docs/design/repo-colours.json, read through lint/repo_colour.py.
"""
import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import repo_colour  # noqa: E402

REGISTRY = os.path.join("docs", "design", "repo-colours.json")


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

    def test_layout_legacy_repos_names_none(self):
        with open(os.path.join(HERE, "layout.json"), encoding="utf-8") as f:
            legacy = json.load(f)["legacy-repos"]
        for key in legacy:
            self.assertNotIn(key.lower().rsplit("/", 1)[-1], self.retired, "legacy-repos: " + key)

    def test_no_tracked_file_names_shivinate7_retired(self):
        files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                               check=True).stdout.splitlines()
        for old in self.retired:
            needle = ("shivinate7/" + old).encode()
            for rel in files:
                if rel == REGISTRY.replace(os.sep, "/") or not os.path.isfile(os.path.join(ROOT, rel)):
                    continue
                with open(os.path.join(ROOT, rel), "rb") as f:
                    self.assertFalse(needle in f.read().lower(), "%s names retired %s" % (rel, old))


if __name__ == "__main__":
    unittest.main()
