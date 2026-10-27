#!/usr/bin/env python3
"""Cases for lint/check_ruling_kind.py. Standard library only.

    python3 lint/test_check_ruling_kind.py

The format a changed decision record must carry, one line per item:

    Kind: build                      or      Kind: process
    Plan: <path>#<slug> (<platform>)         Home: rule:<id>   (a CLAUDE.md marker)
    Plan: <path>#<slug> (<platform>)         Home: <path>      (an existing file)

`<slug>` is the GitHub slug of a heading in the plan file. One link per line, so a writer's
line wrap cannot split it.

Each case builds a temp tree: a copy of the module, a CLAUDE.md, a plan file, and records.
It runs the real script from that tree. The diff cases also make a temp git repo and pass
`--base main`. A passing case must pass before a red one counts. RULING_KIND_UNDER_TEST
overrides the module path.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE = os.environ.get("RULING_KIND_UNDER_TEST") or os.path.join(HERE, "check_ruling_kind.py")
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  copies what git lists, so no fixture lists files (testing/tracked_tree.py)

PLAN = "plans/build-plan.md"
L1 = PLAN + "#phase-1-the-sweep"
L2 = PLAN + "#phase-2-the-proof"
REC = "decisions/new-rule.md"
OLD = "decisions/old-rule.md"
DOCS = "docs/decisions"  # a repo whose records live here passes --dir DOCS
NESTED = DOCS + "/x.md"
IGNORED = "docs/notdecisions/x.md"  # a folder that only contains the word
SIBLING = "docs/decisionsX/x.md"  # a folder that starts with the word
CSS = "src/index.css"  # a plan file with no markdown heading

PLAN_TEXT = """# Build plan

## Build lanes

### Phase 1: the sweep

Sweep the old branches.

### Phase 2: the proof

Prove the sweep.

### Don't stop: the sweep

A heading with an apostrophe.

```
### Fake item
```
"""
CLAUDE_TEXT = "# Rules\n\nDemo rule text. <!-- rule:demo-rule -->\n"

BUILD_OK = ("Owner ruling, 2026-10-12. Ship it on both platforms.\n\n"
            "Kind: build\nPlan: %s (mac)\nPlan: %s (windows)" % (L1, L2))
PROCESS_OK = "Owner ruling, 2026-10-12. Process only.\n\nKind: process\nHome: rule:demo-rule"


def record(ruling, heading="## The ruling"):
    return ("# Demo rule\n\n## The question\n\nShould this land as a build task?\n\n"
            + heading + "\n\n" + ruling + "\n")


class RulingKindTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.isfile(MODULE), "module absent: lint/check_ruling_kind.py")
        self.tree = tempfile.mkdtemp(prefix="rkl_")
        self.addCleanup(tracked_tree.rm_tree, self.tree)
        tracked_tree.copy_tracked(self.tree, "lint", "hooks")  # the layout and the check's imports
        shutil.copyfile(MODULE, os.path.join(self.tree, "lint", "check_ruling_kind.py"))
        self.put("CLAUDE.md", CLAUDE_TEXT)
        self.put(PLAN, PLAN_TEXT)

    def put(self, rel, text, newline="\n"):
        path = os.path.join(self.tree, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline=newline) as f:
            f.write(text)

    def lint(self, *args):
        cmd = [sys.executable, os.path.join(self.tree, "lint", "check_ruling_kind.py"), *args]
        r = subprocess.run(cmd, cwd=self.tree, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        return r.returncode, r.stdout + r.stderr

    def assert_fails(self, rel, token, *flags):
        rc, out = self.lint(*flags, rel)
        self.assertEqual(rc, 1, out)
        self.assertIn("check_ruling_kind: FAIL:", out)
        self.assertIn(rel, out)
        self.assertIn(token.lower(), out.lower())

    def assert_passes(self, rel, *flags):
        rc, out = self.lint(*flags, rel)
        self.assertEqual(rc, 0, out)
        self.assertNotIn("FAIL", out)

    def git(self, *args):
        subprocess.run(["git", "-C", self.tree, "-c", "user.name=test",
                        "-c", "user.email=test@example.com", "-c", "commit.gpgsign=false", *args],
                       check=True, capture_output=True, text=True)

    def commit_base(self):
        self.git("init", "-q")
        self.git("symbolic-ref", "HEAD", "refs/heads/main")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")
        self.git("checkout", "-q", "-b", "change")

    def commit_change(self):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "change")

    # Positive controls first: a red case means nothing if the clean case fails.

    def test_build_with_a_link_per_platform_passes(self):
        self.put(REC, record(BUILD_OK))
        self.assert_passes(REC)

    def test_process_with_a_rule_home_passes(self):
        for ruling in (PROCESS_OK, PROCESS_OK.replace("rule:demo-rule", PLAN)):
            with self.subTest(ruling=ruling):
                self.put(REC, record(ruling))
                self.assert_passes(REC)

    def test_changed_record_without_kind_fails(self):
        cases = [
            ("## The ruling", "Owner ruling. Ship it."),
            ("## Decision", "Owner ruling. Ship it."),  # a heading name is no exemption
            ("## Verdict: the diff check logs", "Owner ruling. Log only."),
        ]
        for heading, ruling in cases:
            with self.subTest(heading=heading):
                self.put(REC, record(ruling, heading))
                self.assert_fails(REC, "Kind")

    def test_build_link_problems_fail(self):
        cases = [
            ("Kind: build", "plan"),  # no Plan line
            ("Kind: build\nPlan:", "plan"),  # empty Plan line
            ("Kind: build\nPlan: plans/missing.md#phase-1-the-sweep (mac)", "plans/missing.md"),
            ("Kind: build\nPlan: plans/build-plan.md#phase-9-nothing (mac)", "phase-9-nothing"),
            ("Kind: build\nPlan: %s" % L1, "phase-1-the-sweep"),  # no platform label
            # A platform label that is none or empty.
            ("Kind: build\nPlan: %s (none)" % L1, "plan"),
            ("Kind: build\nPlan: %s (None)" % L1, "plan"),
            ("Kind: build\nPlan: %s ()" % L1, "plan"),
        ]
        for ruling, token in cases:
            with self.subTest(ruling=ruling):
                self.put(REC, record(ruling))
                self.assert_fails(REC, token)

    def test_process_home_problems_fail(self):
        cases = [
            ("Kind: process", "home"),
            ("Kind: process\nHome:", "home"),
            ("Kind: process\nHome: rule:no-such-rule", "no-such-rule"),
            ("Kind: process\nHome: plans/gone.md", "plans/gone.md"),
        ]
        for ruling, token in cases:
            with self.subTest(ruling=ruling):
                self.put(REC, record(ruling))
                self.assert_fails(REC, token)

    def test_none_and_unknown_kind_fail(self):
        cases = [
            ("Kind: none", "none"),
            ("Kind: NONE", "none"),
            ("Kind: build\nPlan: none", "none"),
            ("Kind: process\nHome: None", "none"),
            ("Kind: maybe\nHome: rule:demo-rule", "maybe"),
        ]
        for ruling, token in cases:
            with self.subTest(ruling=ruling):
                self.put(REC, record(ruling))
                self.assert_fails(REC, token)

    def test_kind_line_placement_problems_fail(self):
        cases = [
            # two Kind lines: a second ruling in one record must be decided, not hidden
            ("Kind: build\nPlan: %s (mac)\n\nKind: none" % L1, "Kind"),
            # a Kind line inside a fenced example does not count
            ("```\nKind: build\nPlan: %s (mac)\n```" % L1, "Kind"),
            # a Kind word mid-sentence does not count
            ("Owner ruling. We set Kind: build for this one.\nPlan: %s (mac)" % L1, "Kind"),
        ]
        for ruling, token in cases:
            with self.subTest(ruling=ruling):
                self.put(REC, record(ruling))
                self.assert_fails(REC, token)

    def test_heading_inside_a_fence_is_not_an_item(self):
        self.put(REC, record("Kind: build\nPlan: plans/build-plan.md#fake-item (mac)"))
        self.assert_fails(REC, "fake-item")

    def test_prose_with_quotes_and_comment_openers_passes(self):
        ruling = ("Owner ruling, 2026-10-12. Don't ship it yet. Prose names `<!-- open` and "
                  "plans/build-plan.md#phase-9-gone, but it is not a link.\n\n"
                  "Kind: build\nPlan: %s (mac)" % L1)
        self.put(REC, record(ruling))
        self.assert_passes(REC)

    def test_apostrophe_heading_slugs_as_github_does(self):
        self.put(REC, record("Kind: build\nPlan: plans/build-plan.md#dont-stop-the-sweep (mac)"))
        self.assert_passes(REC)

    def test_crlf_record_parses(self):
        self.put(REC, record(BUILD_OK), newline="\r\n")
        self.assert_passes(REC)

    def test_plan_file_passed_in_is_ignored_and_default_folder_is_decisions_only(self):
        # The plan has no Kind line. It passes only because the lint does not check it.
        self.assert_passes(PLAN)
        # Without --dir only decisions/ is
        # checked, so a nested docs/decisions record passes. Named failure: the default check spreads
        # into docs/ and fails records that claude-settings never meant to check.
        self.css_plan()
        self.put(NESTED, record("Owner ruling. Ship it."))
        self.assert_passes(NESTED)
        self.put(NESTED, record("Kind: build\nPlan: src/index.css#no-such-heading (web)"))
        self.assert_passes(NESTED)

    def test_diff_unchanged_old_record_is_ignored(self):
        self.put(OLD, record("Old ruling, no kind line."))
        self.put("decisions/gone-rule.md", record("Gone ruling, no kind line."))
        self.commit_base()
        os.remove(os.path.join(self.tree, "decisions", "gone-rule.md"))
        self.put(REC, record(BUILD_OK))
        self.commit_change()
        rc, out = self.lint("--base", "main")
        self.assertEqual(rc, 0, out)
        self.assertNotIn("old-rule", out)
        self.assertNotIn("gone-rule", out)
        self.assertNotIn("FAIL", out)

    def test_diff_changed_old_record_fails(self):
        self.put(OLD, record("Old ruling, no kind line."))
        self.commit_base()
        self.put(OLD, record("Old ruling, edited, still no kind line."))
        self.commit_change()
        rc, out = self.lint("--base", "main")
        self.assertEqual(rc, 1, out)
        self.assertIn("check_ruling_kind: FAIL:", out)
        self.assertIn(OLD, out)

    def test_fence_closer_must_match_the_opener(self):
        cases = [
            # a 3-backtick line does not close a 4-backtick fence, so the Kind line stays inside
            ("````\n```\nKind: build\nPlan: %s (mac)\n````" % L1, False),
            # a closer has no info string, so ```python does not close a ``` fence
            ("```\n```python\nKind: build\nPlan: %s (mac)\n```" % L1, False),
            # a Kind line inside a fence opened with an info string is not counted
            ("```python\nKind: build\nPlan: %s (mac)\n```" % L1, False),
            # a 4-backtick fence closed by a 4-backtick line hides nothing after it
            ("````\n```\n````\n\nKind: build\nPlan: %s (mac)" % L1, True),
        ]
        for ruling, passes in cases:
            with self.subTest(ruling=ruling):
                self.put(REC, record(ruling))
                if passes:
                    self.assert_passes(REC)
                else:
                    self.assert_fails(REC, "Kind")

    def test_dot_slash_changed_path_is_checked(self):
        self.put(REC, record("Owner ruling. Ship it."))
        self.assert_fails("./" + REC, "Kind")

    def test_plan_with_a_bom_resolves_its_first_heading(self):
        self.put("plans/bom-plan.md", "﻿# Build plan\n\n## Build lanes\n\nText.\n")
        self.put(REC, record("Kind: build\nPlan: plans/bom-plan.md#build-plan (mac)"))
        self.assert_passes(REC)

    def test_heading_with_a_link_slugs_to_its_link_text(self):
        self.put("plans/link-plan.md", "# Build plan\n\n## See [the rule](x.md)\n\nText.\n")
        self.put(REC, record("Kind: build\nPlan: plans/link-plan.md#see-the-rule (mac)"))
        self.assert_passes(REC)

    def test_kind_inside_an_html_comment_is_not_counted(self):
        cases = [
            ("<!--\nKind: build\nPlan: %s (mac)\n-->" % L1, False),
            # a commented-out Kind line does not count, so the real one after it is the only one
            ("<!--\nKind: none\n-->\n\nKind: build\nPlan: %s (mac)" % L1, True),
        ]
        for ruling, passes in cases:
            with self.subTest(ruling=ruling):
                self.put(REC, record(ruling))
                if passes:
                    self.assert_passes(REC)
                else:
                    self.assert_fails(REC, "Kind")

    # --rules-file: a Home names a rule that lives in either rules file. Each file is one side:
    # the caller's CLAUDE.md and the claude-settings CLAUDE.md, passed by check.sh.

    def rules(self, rel, rule_id):
        """Write a rules file that holds one rule marker. Returns its absolute path."""
        self.put(rel, "# Rules\n\nRule text. <!-- rule:%s -->\n" % rule_id)
        return os.path.join(self.tree, rel)

    def rules_flags(self, *paths):
        return [flag for p in paths for flag in ("--rules-file", p)]

    def test_rule_home_resolves_in_either_rules_file(self):
        caller = self.rules("caller/CLAUDE.md", "caller-rule")
        action = self.rules("action/CLAUDE.md", "action-rule")
        flags = self.rules_flags(caller, action)
        cases = [("caller-rule", True), ("action-rule", True), ("neither-rule", False)]
        for rule, passes in cases:
            with self.subTest(rule=rule):
                self.put(REC, record("Kind: process\nHome: rule:%s" % rule))
                rc, out = self.lint(*flags, REC)
                if passes:
                    self.assertEqual(rc, 0, out)
                    self.assertNotIn("FAIL", out)
                else:
                    self.assertEqual(rc, 1, out)
                    self.assertIn("Home rule:neither-rule is not a rule marker", out)

    def test_missing_rules_file_is_skipped_when_another_is_readable(self):
        action = self.rules("action/CLAUDE.md", "action-rule")
        missing = os.path.join(self.tree, "caller", "CLAUDE.md")  # never written
        self.put(REC, record("Kind: process\nHome: rule:action-rule"))
        rc, out = self.lint(*self.rules_flags(missing, action), REC)
        self.assertEqual(rc, 0, out)
        self.assertNotIn("FAIL", out)

    def test_no_readable_rules_file_fails_a_rule_home_and_passes_a_path_home(self):
        flags = self.rules_flags(os.path.join(self.tree, "caller", "CLAUDE.md"),
                                 os.path.join(self.tree, "action", "CLAUDE.md"))
        # demo-rule is in the tree's own CLAUDE.md. --rules-file replaces that file, so it must not resolve.
        self.put(REC, record("Kind: process\nHome: rule:demo-rule"))
        rc, out = self.lint(*flags, REC)
        self.assertEqual(rc, 1, out)
        self.assertIn("FAIL", out)
        self.assertIn("cannot be checked", out)
        self.put(REC, record(PROCESS_OK.replace("rule:demo-rule", PLAN)))
        rc, out = self.lint(*flags, REC)
        self.assertEqual(rc, 0, out)
        self.assertNotIn("FAIL", out)

    def test_without_rules_file_the_root_claude_md_is_read(self):
        self.put("caller-root/CLAUDE.md", "# Rules\n\nRule text. <!-- rule:caller-root-rule -->\n")
        self.put("caller-root/" + REC, record("Kind: process\nHome: rule:caller-root-rule"))
        rc, out = self.lint("--root", os.path.join(self.tree, "caller-root"), REC)
        self.assertEqual(rc, 0, out)
        self.assertNotIn("FAIL", out)


    # --dir: the records folder the lint checks. The default is decisions/. A repo whose records
    # live in docs/decisions/ passes --dir docs/decisions. The default never checks that folder.

    def css_plan(self):
        # "#no-such-heading" has no space after the "#", so it is not a heading.
        self.put(CSS, "body { color: black; }\n#no-such-heading { color: red }\n")

    def test_dir_checks_records_in_the_named_folder(self):
        self.css_plan()
        cases = [
            (record("Owner ruling. Ship it."), "Kind"),  # (a) no Kind line
            (record("Kind: build\nPlan: src/index.css#no-such-heading (web)"),
             "not a heading in src/index.css"),  # (b) slug missing from a file that exists
        ]
        for text, token in cases:
            with self.subTest(token=token):
                self.put(NESTED, text)
                self.assert_fails(NESTED, token, "--dir", DOCS)

    def test_dir_passes_a_valid_record_in_the_named_folder(self):
        for kind, ruling in (("build", BUILD_OK), ("process", PROCESS_OK)):
            with self.subTest(kind=kind):
                self.put(NESTED, record(ruling))
                self.assert_passes(NESTED, "--dir", DOCS)

    def test_dir_ignores_folders_that_only_look_like_it(self):
        # The named folder must exist, so it holds one valid record. The look-alikes hold none.
        self.put(NESTED, record(BUILD_OK))
        self.assert_passes(NESTED, "--dir", DOCS)
        for rel in (IGNORED, SIBLING):
            with self.subTest(rel=rel):
                self.put(rel, record("Owner ruling. No kind line."))
                self.assert_passes(rel, "--dir", DOCS)

    def test_dir_checks_records_added_in_the_diff(self):
        # The CI path: no file arguments, the lint reads the diff against --base.
        self.commit_base()
        self.put(NESTED, record("Owner ruling. Ship it."))
        self.put(IGNORED, record("Owner ruling. No kind line."))
        self.commit_change()
        rc, out = self.lint("--dir", DOCS, "--base", "main")
        self.assertEqual(rc, 1, out)
        self.assertIn("check_ruling_kind: FAIL: %s:" % NESTED, out)
        self.assertNotIn(IGNORED, out)
        rc, out = self.lint("--base", "main")  # default folder: the same diff passes
        self.assertEqual(rc, 0, out)
        self.assertNotIn("FAIL", out)


    # --dir must name a folder that exists under the checkout, spelled as it is on disk. A check
    # that cannot read its own input exits non-zero, and names the folder it was given.
    # Case: on a case-insensitive disk "Decisions" resolves, so the spelling must be compared too.

    def test_dir_that_names_no_usable_folder_fails(self):
        # Rows: no usable folder (decision, docs/decisions-old, ., "", Decisions), and a name that is a
        # file (CLAUDE.md, decisions/x.md). The diff-mode
        # case is in test_dir_that_names_no_usable_folder_fails_in_the_diff. Named failure: a bad
        # --dir passes the lint instead of failing closed.
        self.put("decisions/x.md", record(BUILD_OK))
        self.put(REC, record(BUILD_OK))
        for value in ("decision", "docs/decisions-old", ".", "", "Decisions", "CLAUDE.md", "decisions/x.md"):
            with self.subTest(dir=value):
                rc, out = self.lint("--dir", value, REC)
                self.assertNotEqual(rc, 0, out)
                self.assertIn("'%s'" % value, out)
                self.assertNotIn("Traceback", out)

    def test_dir_that_names_no_usable_folder_fails_in_the_diff(self):
        self.commit_base()
        self.put(REC, record(BUILD_OK))
        self.commit_change()
        rc, out = self.lint("--dir", "decision", "--base", "main")
        self.assertNotEqual(rc, 0, out)
        self.assertIn("'decision'", out)
        self.assertNotIn("Traceback", out)

    def test_default_and_named_records_folder_pass(self):
        self.put(REC, record(BUILD_OK))
        self.assert_passes(REC)
        self.assert_passes(REC, "--dir", "decisions")

    # --dir=VALUE is read as --dir VALUE. A leftover option fails closed, never reads as a file name.

    def test_dir_equals_form_checks_the_named_folder(self):
        self.css_plan()
        self.put(NESTED, record("Owner ruling. Ship it."))  # no Kind line
        rc, out = self.lint("--dir=" + DOCS, NESTED)
        self.assertEqual(rc, 1, out)
        self.assertIn("check_ruling_kind: FAIL:", out)
        self.put(NESTED, record(BUILD_OK))
        self.assert_passes(NESTED, "--dir=" + DOCS)

    def test_dir_equals_form_that_names_no_folder_fails(self):
        rc, out = self.lint("--dir=nope")
        self.assertNotEqual(rc, 0, out)
        self.assertNotIn("Traceback", out)

    def test_unknown_option_fails_never_reads_as_a_file(self):
        self.put(REC, record(BUILD_OK))
        for opt in ("--bogus", "-x", "--dirs=decisions"):
            with self.subTest(opt=opt):
                rc, out = self.lint(opt, REC)
                self.assertNotEqual(rc, 0, out)
                self.assertNotIn("Traceback", out)


if __name__ == "__main__":
    unittest.main()
