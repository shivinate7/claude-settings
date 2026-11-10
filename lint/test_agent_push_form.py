#!/usr/bin/env python3
"""Fixture suite for the push wording of the four role files. Run: python3 lint/test_agent_push_form.py

An agent pushes only to the branch its brief names, as `git push origin HEAD:<branch>`. The guard rule
push-agent-branch refuses a push of the worktree's own branch (worktree-agent-<hex>), so a role file that tells
the agent to commit and push its own branch sends it into that refusal. Whitespace is collapsed, so a line break
inside a sentence still matches. Each case reads only the four role files.
"""
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROLE_FILES = ("builder", "test-author", "designer", "record-writer")
PUSH_FORM = "git push origin HEAD:<branch>"
OWN_BRANCH_WORDING = "commit your work to your own branch and push it"


class PushForm(unittest.TestCase):
    def role_text(self, role):
        path = os.path.join(ROOT, "agents", role + ".md")
        self.assertTrue(os.path.isfile(path), "%s is missing" % path)  # scope before subject
        with open(path, encoding="utf-8") as handle:
            return " ".join(handle.read().split())

    def test_each_role_pushes_with_the_brief_branch_form(self):
        for role in ROLE_FILES:
            with self.subTest(role=role):
                self.assertTrue(PUSH_FORM in self.role_text(role),
                                "%s.md lacks the form %s" % (role, PUSH_FORM))

    def test_no_role_still_pushes_its_own_branch(self):
        for role in ROLE_FILES:
            with self.subTest(role=role):
                self.assertFalse(OWN_BRANCH_WORDING in self.role_text(role).lower(),
                                 "%s.md still says to push its own branch" % role)


if __name__ == "__main__":
    unittest.main()
