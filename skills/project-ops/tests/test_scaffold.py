#!/usr/bin/env python3
"""Cases for skills/project-ops/scripts/scaffold.py and protect.py. Standard library only.

    python3 skills/project-ops/tests/test_scaffold.py

Each case runs the scaffold into an empty temp folder, the dry run of the skill. The cases prove
the file list, the filled placeholders, the refusal over an existing file, and that nothing the
skill writes or ships names this project's threads, sessions or people.
"""
import contextlib
import io
import os
import re
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(SKILL, "scripts"))
import scaffold  # noqa: E402

EXPECTED = [
    "CLAUDE.md",
    "roadmap/README.md",
    "roadmap/outbox/README.md",
    "roadmap/data/steps/.gitkeep",
    "roadmap/data/topics/.gitkeep",
    "roadmap/data/meta/.gitkeep",
    "briefs/.gitkeep",
    "handoffs/.gitkeep",
]
# A claude.ai thread or session id, the owner's names, and the live page of this project.
PRIVATE = re.compile(r"cmsg_|session_[0-9A-Za-z]{8}|shiv|R3iCpK91QRjC5he8bwfY7m", re.IGNORECASE)


def run(*args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = scaffold.main(list(args))
    return code, out.getvalue(), err.getvalue()


def tree(root):
    found = {}
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            path = os.path.join(base, name)
            with open(path, encoding="utf-8") as f:
                found[os.path.relpath(path, root).replace(os.sep, "/")] = f.read()
    return found


class Scaffold(unittest.TestCase):
    def setUp(self):
        self.dest = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dest)

    def test_writes_the_skeleton(self):
        code, out, err = run("--dest", self.dest, "--repo", "acme/widgets")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.split(), EXPECTED)
        self.assertEqual(sorted(tree(self.dest)), sorted(EXPECTED))

    def test_fills_the_placeholders(self):
        run("--dest", self.dest, "--repo", "acme/widgets", "--branch", "record")
        files = tree(self.dest)
        self.assertIn("acme/widgets, branch `record`", files["CLAUDE.md"])
        for rel, text in files.items():
            self.assertNotIn("{{", text, rel)

    def test_readme_points_at_the_roadmap_skill(self):
        run("--dest", self.dest, "--repo", "acme/widgets")
        readme = tree(self.dest)["roadmap/README.md"]
        self.assertIn("skills/roadmap", readme)
        self.assertIn("--live", readme)
        self.assertNotIn("build.py` on the", readme)
        self.assertNotIn("has no page", readme)

    def test_skill_files_name_no_stale_builder(self):
        for rel, text in tree(SKILL).items():
            if rel.startswith("tests/"):
                continue
            self.assertNotRegex(text, r"(?<!skills/)roadmap/build\.py", rel)
            self.assertNotIn("has no page", text, rel)

    def test_triage_passes_live_at_each_publish(self):
        text = tree(SKILL)["templates/operating-model.md"]
        bullet = re.search(r"- \*\*Triage\.\*\*.*?(?=\n- \*\*)", text, re.S).group(0)
        self.assertIn("publishes the roadmap page", bullet)
        self.assertIn("--live", bullet)

    def assertInOrder(self, flat, clauses):
        at = [flat.find(x) for x in clauses]
        for clause, pos in zip(clauses, at):
            self.assertNotEqual(pos, -1, clause)
        self.assertEqual(at, sorted(at), clauses)

    def test_handoff_template_lists_pages_to_watch(self):
        text = tree(SKILL)["templates/role-handoff.md"]
        section = re.search(r"## Pages\n(.*?)(?=\n## |\Z)", text, re.S)
        self.assertIsNotNone(section, "no Pages section")
        self.assertRegex(section.group(1), r"(?m)^Watches stopped at <time>$")
        flat = " ".join(section.group(1).split())
        self.assertIn("The URL of each page this role owns", flat)
        self.assertInOrder(flat, (
            "old session stopped watching each one at that time",
            "answered each comment still open at that time",
            "wrote this file",
            "successor watches each one at once",
            "reads its comments since that time"))

    def test_handoff_rule_moves_page_watches(self):
        text = tree(SKILL)["templates/operating-model.md"]
        rule = re.search(r"## Rotation of standing sessions.*?(?=\n## )", text, re.S).group(0)
        flat = " ".join(rule.split())
        self.assertInOrder(flat, (
            "old session stops watching each page its role owns",
            "It notes the time",
            "answers each comment still open at that time",
            "It drains its work in flight",
            "writes the hand-off file",
            "with that time",
            "each wait it handed over",
            "coordinator archives the old session",
            "coordinator starts the successor from the hand-off file",
            "successor watches each page at once",
            "reads each page's comments since the time in the hand-off file"))
        self.assertIn("The coordinator sends no broadcast. Sessions read the roster.", flat)
        self.assertEqual(flat.count("coordinator starts the successor from"), 1,
                         "one hand-off, one bullet")
        self.assertIn("external_metadata.context_usage", flat)
        self.assertIn("<triage limit>", flat)
        self.assertIn("<batch runner limit>", flat)
        self.assertIn("The coordinator never hands its own sessions to a successor", flat)

    def test_tiers_start_as_a_trio(self):
        text = tree(SKILL)["templates/operating-model.md"]
        tiers = re.search(r"## Session tiers.*?(?=\n## )", text, re.S).group(0)
        flat = " ".join(tiers.split())
        self.assertIn("starts triage and the batch runner together, as a trio, before any lane session", flat)
        self.assertIn("checks whether that repo has an active coordinator", flat)
        self.assertIn("It does not wait for a reply.", flat)
        self.assertIn("tags itself and each session it starts `cs-repo:<owner>/<repo>`", flat)
        self.assertIn("`list_sessions` for a session tagged `cs-repo:<owner>/<repo>`", flat)

    def test_brief_carries_repo_tag(self):
        flat = " ".join(tree(SKILL)["templates/brief.md"].split())
        self.assertIn("tag `cs-repo:<owner>/<repo>`", flat)

    def test_writes_nothing_private(self):
        run("--dest", self.dest, "--repo", "acme/widgets")
        for rel, text in tree(self.dest).items():
            self.assertIsNone(PRIVATE.search(text), rel)

    def test_ships_nothing_private(self):
        for rel, text in tree(SKILL).items():
            if rel.startswith("tests/"):
                continue
            self.assertIsNone(PRIVATE.search(text), rel)

    def test_refuses_over_an_existing_file(self):
        with open(os.path.join(self.dest, "CLAUDE.md"), "w", encoding="utf-8") as f:
            f.write("mine\n")
        code, out, err = run("--dest", self.dest, "--repo", "acme/widgets")
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("CLAUDE.md", err)
        self.assertEqual(tree(self.dest), {"CLAUDE.md": "mine\n"})

    def test_failed_write_leaves_no_files(self):
        # A file named like a folder the scaffold makes fails the write after earlier files land.
        with open(os.path.join(self.dest, "briefs"), "w", encoding="utf-8") as f:
            f.write("x")
        code, out, err = run("--dest", self.dest, "--repo", "acme/widgets")
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("write failed", err)
        self.assertEqual(tree(self.dest), {"briefs": "x"})

    def test_second_run_changes_nothing(self):
        run("--dest", self.dest, "--repo", "acme/widgets")
        before = tree(self.dest)
        code, _, _ = run("--dest", self.dest, "--repo", "acme/widgets")
        self.assertEqual(code, 1)
        self.assertEqual(tree(self.dest), before)

    def test_bad_arguments(self):
        self.assertEqual(run("--dest", self.dest, "--repo", "widgets")[0], 2)
        self.assertEqual(run("--dest", self.dest, "--repo", "a/b", "--branch", "x y")[0], 2)
        self.assertEqual(run("--dest", os.path.join(self.dest, "none"), "--repo", "a/b")[0], 2)
        self.assertEqual(tree(self.dest), {})


class Protect(unittest.TestCase):
    """c189 part 4: adopting a repo sets branch protection with its required checks, so no repo starts with none. A fake `gh` records each call."""

    def run_protect(self, *argv, existing=None, other_rules=False):
        import protect
        calls = []

        def gh(args, body=None):
            calls.append((list(args), body))
            if "GET" in args:
                if args[-1].endswith("/required_status_checks"):
                    if existing is not None:
                        return 0, '{"contexts": %s}' % __import__("json").dumps(existing)
                    return 1, "HTTP 404: Required status checks not enabled" if other_rules else "HTTP 404: Branch not protected"
                return (0, '{"required_pull_request_reviews": {"required_approving_review_count": 1},"enforce_admins": {"enabled": true}}') if other_rules else (1, "HTTP 404: Branch not protected")
            return 0, "{}"
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = protect.main(list(argv), gh=gh)
        return code, out.getvalue(), calls

    def test_preview_changes_nothing_and_names_the_call(self):
        code, out, calls = self.run_protect("--repo", "acme/widgets", "--check", "checks", "--check", "lint")
        self.assertEqual(code, 0, out)
        self.assertFalse([c for c in calls if "GET" not in c[0]], calls)
        self.assertIn("checks", out)
        self.assertIn("--confirm", out)

    def test_an_unprotected_branch_gets_protection_with_the_checks(self):
        code, out, calls = self.run_protect("--repo", "acme/widgets", "--check", "checks", "--check", "lint", "--confirm")
        self.assertEqual(code, 0, out)
        puts = [c for c in calls if "PUT" in c[0]]
        self.assertEqual(len(puts), 1, calls)
        self.assertIn("repos/acme/widgets/branches/main/protection", puts[0][0])
        self.assertEqual(puts[0][1]["required_status_checks"]["contexts"], ["checks", "lint"])

    def test_a_protected_branch_gets_its_checks_set_in_place(self):
        code, out, calls = self.run_protect("--repo", "acme/widgets", "--check", "checks", "--confirm", existing=["old"])
        self.assertEqual(code, 0, out)
        patches = [c for c in calls if "PATCH" in c[0]]
        self.assertEqual(len(patches), 1, calls)
        self.assertEqual(patches[0][1]["contexts"], ["checks"])
        self.assertFalse([c for c in calls if "PUT" in c[0]], calls)

    def test_checks_already_set_change_nothing(self):
        code, out, calls = self.run_protect("--repo", "acme/widgets", "--check", "b", "--check", "a", "--confirm", existing=["a", "b"])
        self.assertEqual(code, 0, out)
        self.assertFalse([c for c in calls if "GET" not in c[0]], calls)

    def test_no_checks_is_refused(self):
        for checks in (["--check", ""], ["--check", "  "], []):
            code, out, calls = self.run_protect("--repo", "acme/widgets", *checks, "--confirm")
            self.assertEqual(code, 2, out)
            self.assertEqual(calls, [])

    def test_a_matrix_name_with_a_comma_stays_one_check(self):
        code, out, calls = self.run_protect("--repo", "acme/widgets", "--check", "test (ubuntu, 3.11)", "--confirm")
        self.assertEqual(code, 0, out)
        self.assertEqual([c for c in calls if "PUT" in c[0]][0][1]["required_status_checks"]["contexts"], ["test (ubuntu, 3.11)"])

    def test_the_patch_leaves_strict_alone(self):
        _, _, calls = self.run_protect("--repo", "acme/widgets", "--check", "checks", "--confirm", existing=["old"])
        self.assertNotIn("strict", [c for c in calls if "PATCH" in c[0]][0][1])

    def test_a_branch_protected_without_a_check_rule_is_refused_not_replaced(self):  # a PUT would drop its review rule and restrictions
        code, out, calls = self.run_protect("--repo", "acme/widgets", "--check", "checks", "--confirm", other_rules=True)
        self.assertEqual(code, 1, out)
        self.assertFalse([c for c in calls if "GET" not in c[0]], calls)
        self.assertIn("required_pull_request_reviews", out)


if __name__ == "__main__":
    unittest.main()
