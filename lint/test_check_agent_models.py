#!/usr/bin/env python3
"""Fixture suite for lint/check_agent_models.py. Run: python3 lint/test_check_agent_models.py

Owner ruling 2026-10-07: Haiku is allowed only in the agent files for Explore, claude-code-guide,
test-author and reviewer. Every other agent or skill file keeps the Sonnet floor.
Failure classes: false deny (a listed role fails), false allow (another file passes, by name
collision, case or alias), unreadable frontmatter.
"""
import contextlib, io, os, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check_agent_models as C  # noqa: E402

ROLES = ("explore", "claude-code-guide", "test-author", "reviewer")
MODELS = ("haiku", "claude-haiku-5-5", "Haiku")


def verdict(relpath, model, closed=True):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, relpath)
        os.makedirs(os.path.dirname(path))
        with open(path, "w") as handle:
            handle.write("---\nname: x\nmodel: %s\n%sbody\n" % (model, "---\n" if closed else ""))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = C.main([path])
        return code, out.getvalue()


class Haiku(unittest.TestCase):
    def test_listed_roles_may_set_haiku(self):
        for role in ROLES:
            for model in MODELS:
                with self.subTest(role=role, model=model):
                    self.assertEqual(verdict("agents/%s.md" % role, model), (0, ""))

    def test_other_agents_still_fail(self):
        for name in ("builder", "plan", "general-purpose", "claude", "reviewer-lite", "explorer"):
            with self.subTest(name=name):
                self.assertEqual(verdict("agents/%s.md" % name, "haiku")[0], 1)

    def test_skill_files_still_fail(self):
        # A skill named like a role is still a skill.
        for name in ("deploy", "explore", "reviewer", "test-author"):
            with self.subTest(name=name):
                self.assertEqual(verdict("skills/%s/SKILL.md" % name, "haiku")[0], 1)

    def test_listed_roles_may_set_sonnet(self):
        for role in ROLES:
            self.assertEqual(verdict("agents/%s.md" % role, "sonnet"), (0, ""))

    def test_unclosed_frontmatter_still_fails_for_a_listed_role(self):
        self.assertEqual(verdict("agents/reviewer.md", "haiku", closed=False)[0], 1)


if __name__ == "__main__":
    unittest.main()
