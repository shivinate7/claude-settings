#!/usr/bin/env python3
"""Cases for lint/check_plan_refuter.py. Standard library only.

    python3 lint/test_check_plan_refuter.py

A plan record is a file that the range adds directly in the plans home (lint/layout.json, kind "plans"),
named <name>.md. Each such plan must carry a `Refuter:` line at line start, optionally wrapped as `**Refuter:**`,
outside a fenced code block. The first word after the colon (and any `**`) must be the refuter role, compared
case-insensitively with REFUTER_ROLE in hooks/guard_core.py. The check reads the file as it stands at HEAD. Plans
that the range only modifies, plans in a subfolder of the plans home, and files that are not .md are not judged.

    python3 lint/check_plan_refuter.py --base <sha> [--root <dir>]
        # the base is env BASE_SHA when no flag is given; the repo is the current directory unless --root names one

Exit 0: clean. Exit 1: a judged plan lacks a line that names the refuter role, and its path is named.
Exit 2: UNKNOWN, because no base was given or git could not read the range. Unknown is never 0.

Each case builds a fixture repo under this run's folder (lint/_test_temp.py): a base commit that marks the
repo rolled out to the layout, then change commits on top. The check runs as the copy at
lint/check_plan_refuter.py, by its absolute path, from the fixture. CHECK_PLAN_REFUTER_UNDER_TEST overrides
the module path, which a mutant run uses.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per test run (lint/_test_temp.py)
import layout  # noqa: E402  the one home of the plans kind: lint/layout.json, kinds.plans
sys.path.append(os.path.join(HERE, "..", "hooks"))  # appended, so no hooks module shadows a lint one
from guard_core import REFUTER_ROLE  # noqa: E402  the one home of the refuter role's name (hooks/guard_core.py)
MODULE = os.path.abspath(os.environ.get("CHECK_PLAN_REFUTER_UNDER_TEST") or os.path.join(HERE, "check_plan_refuter.py"))
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  rm_tree clears read-only git objects (testing/tracked_tree.py)

PLANS = layout.layout()["kinds"]["plans"]["path"]  # the default plans home, read from the layout
EXTRAS_REL = ".claude/layout-extras.json"  # the layout's extras file; rolled out, so layout.path() reads PLANS
EXTRAS_TEXT = '{"kinds": {}, "rolled-out": true}\n'
TITLE = "# Plan: widget rollout\n\nWhat we build, and why.\n\n"
REFUTER = "Refuter: %s opus, 2026-11-06, PASS with two changes" % REFUTER_ROLE
BOLD_REFUTER = "**Refuter:** %s sonnet, 2026-11-06, PASS" % REFUTER_ROLE
OLD_PLAN = TITLE + "No review line. Written before the rule.\n"
SRC = "def widget():\n    return 1\n"
BIG_LINES = 3000  # a full-size plan: far more lines than a verdict needs

GIT_ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
for _name in list(GIT_ENV):
    if (_name.startswith("GIT_") and not _name.startswith("GIT_CONFIG_")) or _name in ("BASE_SHA", "CI"):
        del GIT_ENV[_name]  # the outer shell's repo and base never reach a fixture or a case

RUN_FOLDER = None


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    if RUN_FOLDER and os.path.isdir(RUN_FOLDER):
        tracked_tree.rm_tree(RUN_FOLDER)  # test-temp-standard: teardown removes the run folder


def plan(*lines):
    """A plan record: its title, then each line on its own."""
    return TITLE + "".join(line + "\n" for line in lines)


class Fixture(unittest.TestCase):
    """A fixture repo: a base commit that marks it rolled out to the layout, then the commits a case adds."""

    def setUp(self):
        self.tree = tempfile.mkdtemp(dir=RUN_FOLDER, prefix="cpc_")
        self.addCleanup(tracked_tree.rm_tree, self.tree)
        self.git("init", "-q")
        self.git("symbolic-ref", "HEAD", "refs/heads/main")
        self.base_sha = self.commit("fixture base", {EXTRAS_REL: EXTRAS_TEXT, PLANS + "/old-plan.md": OLD_PLAN,
                                                     "src/widgets.py": SRC})

    def git(self, *args, input=None):
        done = subprocess.run(["git", "-C", self.tree, "-c", "user.name=test", "-c", "user.email=test@example.com",
                               "-c", "core.autocrlf=false", *args],
                              check=True, capture_output=True, text=True, env=GIT_ENV, input=input)
        return done.stdout.strip()

    def commit(self, subject, files):
        """Write files (a None value deletes one), commit those paths only, and return the full sha of HEAD."""
        for rel, text in files.items():
            path = os.path.join(self.tree, *rel.split("/"))
            if text is None:
                os.remove(path)
                continue
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(text)
        self.git("add", "--", *files)
        self.git("commit", "-q", "--cleanup=verbatim", "-F", "-", input=subject + "\n")
        return self.git("rev-parse", "HEAD")

    def rebase_here(self):
        """Start a new scope at HEAD, so the next commit is the only one the check judges."""
        self.base_sha = self.git("rev-parse", "HEAD")

    def changed(self):
        """{path: status} for base...HEAD: the files in scope, as git lists them."""
        out = self.git("diff", "--no-renames", "--name-status", self.base_sha + "...HEAD")
        return {path: status for status, path in (line.split("\t", 1) for line in out.splitlines())}

    def assertStatus(self, rel, status):
        """Scope first: git lists rel with this status, so the verdict that follows judges the file the case names."""
        changed = self.changed()
        self.assertEqual(changed.get(rel), status, "scope: git does not list %s as %s:\n%s" % (rel, status, changed))

    def lint(self, args=None, env=None, cwd=None, module=None):
        """Run the check on the fixture repo, or from cwd. Returns (exit code, stdout and stderr)."""
        argv = ["--base", self.base_sha] if args is None else args
        done = subprocess.run([sys.executable, module or MODULE, *argv], cwd=cwd or self.tree, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", env=dict(GIT_ENV, **(env or {})))
        return done.returncode, done.stdout + done.stderr

    def assertClean(self, args=None, env=None, cwd=None):
        rc, out = self.lint(args, env, cwd)
        self.assertEqual(rc, 0, "expected exit 0, got %d:\n%s" % (rc, out))
        self.assertNotIn("Traceback", out, out)

    def assertNamed(self, rel, args=None, env=None, cwd=None):
        """Exit 1, and the output names rel. Returns the output."""
        rc, out = self.lint(args, env, cwd)
        self.assertEqual(rc, 1, "expected exit 1, got %d:\n%s" % (rc, out))
        self.assertIn(rel, out, "exit 1 does not name %s:\n%s" % (rel, out))
        self.assertNotIn("Traceback", out, out)
        return out


class PlanRefuterCase(Fixture):

    def test_control_fixture_resolves_the_default_plans_home(self):
        """Green on main, which has no check. The fixture's layout resolves PLANS, and git's range lists each
        file the cases below judge, with its status."""
        self.assertEqual(layout.path(self.tree, "plans"), PLANS, "the fixture does not resolve the default plans home")
        self.commit("add plans", {PLANS + "/new-plan.md": plan(), PLANS + "/folder/x.md": plan(),
                                  PLANS + "/old-plan.md": OLD_PLAN + "More text.\n", "src/widgets.py": SRC + "# edit\n"})
        self.assertStatus(PLANS + "/new-plan.md", "A")
        self.assertStatus(PLANS + "/folder/x.md", "A")
        self.assertStatus(PLANS + "/old-plan.md", "M")

    def test_added_plan_without_refuter_line_is_flagged(self):
        rel = PLANS + "/new-plan.md"
        self.commit("add widget plan", {rel: plan("Body only.")})
        self.assertStatus(rel, "A")
        self.assertNamed(rel)

    def test_refuter_with_nothing_after_it_is_flagged(self):
        for index, line in enumerate(["Refuter:", "Refuter:   ", "**Refuter:**", "**Refuter:**   "]):
            with self.subTest(line=line):
                self.rebase_here()
                rel = PLANS + "/empty-refuter-%d.md" % index
                self.commit("add empty refuter plan", {rel: plan(line)})
                self.assertStatus(rel, "A")
                self.assertNamed(rel)

    def test_refuter_with_no_word_after_it_is_flagged(self):
        """A Refuter line needs a word character after the colon, and after any `**`. A bare `**`, and the
        `<...>` placeholder of the template line, are not a verdict."""
        for index, line in enumerate(["Refuter: **", "**Refuter:** **", "Refuter: <role and model>, <date>, <verdict>"]):
            with self.subTest(line=line):
                self.rebase_here()
                rel = PLANS + "/no-word-refuter-%d.md" % index
                self.commit("add no-word refuter plan", {rel: plan(line)})
                self.assertStatus(rel, "A")
                self.assertNamed(rel)

    def test_refuter_with_the_role_and_a_verdict_passes(self):
        """Control for the cases above: a refuter role and a verdict after the colon pass."""
        rel = PLANS + "/word-refuter.md"
        self.commit("add plan", {rel: plan("Refuter: %s opus, 2026-11-06, PASS" % REFUTER_ROLE)})
        self.assertStatus(rel, "A")
        self.assertClean()

    def test_refuter_line_with_the_role_and_holds_passes(self):
        """The line a refuter writes, plain and wrapped: the refuter role first, then the model, date and verdict."""
        for index, line in enumerate(["Refuter: %s opus, 2026-11-08, holds" % REFUTER_ROLE,
                                      "**Refuter:** %s opus, 2026-11-08, holds" % REFUTER_ROLE]):
            with self.subTest(line=line):
                self.rebase_here()
                rel = PLANS + "/holds-%d.md" % index
                self.commit("add holds plan", {rel: plan(line)})
                self.assertStatus(rel, "A")
                self.assertClean()

    def test_refuter_role_matches_in_any_case(self):
        """The role is compared case-insensitively, so the upper-case form of the constant passes too."""
        rel = PLANS + "/upper-role.md"
        self.commit("add plan", {rel: plan("Refuter: %s opus, 2026-11-08, holds" % REFUTER_ROLE.upper())})
        self.assertStatus(rel, "A")
        self.assertClean()

    def test_planner_graded_refuter_line_is_flagged(self):
        """A planner who grades its own plan is no refuter: the role field names the planner, so the plan is named."""
        for index, line in enumerate(["Refuter: Plan opus, 2026-11-06, PASS",
                                      "**Refuter:** Plan opus, 2026-11-06, PASS"]):
            with self.subTest(line=line):
                self.rebase_here()
                rel = PLANS + "/planner-graded-%d.md" % index
                self.commit("add planner-graded plan", {rel: plan(line)})
                self.assertStatus(rel, "A")
                self.assertNamed(rel)

    def test_reviewer_graded_refuter_line_is_flagged(self):
        rel = PLANS + "/reviewer-graded.md"
        self.commit("add reviewer-graded plan", {rel: plan("Refuter: reviewer sonnet, 2026-11-06, PASS")})
        self.assertStatus(rel, "A")
        self.assertNamed(rel)

    def test_refuter_role_not_first_is_flagged(self):
        """The role is the first word after the colon. The refuter word later in the line does not name the role."""
        rel = PLANS + "/role-not-first.md"
        self.commit("add plan", {rel: plan("Refuter: Plan %s opus, 2026-11-06, PASS" % REFUTER_ROLE)})
        self.assertStatus(rel, "A")
        self.assertNamed(rel)

    def test_refuter_role_as_prefix_of_a_longer_word_is_flagged(self):
        """A prefix of the role is not the role: a check that reads startswith would pass this line."""
        rel = PLANS + "/role-prefix.md"
        self.commit("add plan", {rel: plan("Refuter: %sx opus, 2026-11-08, holds" % REFUTER_ROLE)})
        self.assertStatus(rel, "A")
        self.assertNamed(rel)

    def test_the_retired_word_is_no_refuter_line(self):
        """The line is `Refuter:` now. The retired word, with a verdict after it, is no line, so the plan is named."""
        rel = PLANS + "/retired-word.md"
        self.commit("add plan with the retired word", {rel: plan("Critic: %s opus, 2026-11-06, PASS" % REFUTER_ROLE)})
        self.assertStatus(rel, "A")
        self.assertNamed(rel)

    def test_refuter_only_inside_a_fenced_block_is_flagged(self):
        for index, (fence, line) in enumerate([("```", REFUTER), ("```text", BOLD_REFUTER)]):
            with self.subTest(fence=fence):
                self.rebase_here()
                rel = PLANS + "/fenced-%d.md" % index
                self.commit("add fenced refuter plan", {rel: plan(fence, line, "```")})
                self.assertStatus(rel, "A")
                self.assertNamed(rel)

    def test_a_fence_closes_only_at_a_run_as_long_as_its_opener(self):
        """CommonMark: a closer has at least as many backticks as the opener. A ``` line inside a ```` fence is text, so
        a Refuter line after it stays hidden until the ```` closes."""
        cases = [(["````", "```", REFUTER, "````"], True), (["````", "```", "````", REFUTER], False)]
        for index, (lines, flagged) in enumerate(cases):
            with self.subTest(lines=lines):
                self.rebase_here()
                rel = PLANS + "/long-fence-%d.md" % index
                self.commit("add plan with a longer fence", {rel: plan(*lines)})
                self.assertStatus(rel, "A")
                if flagged:
                    self.assertNamed(rel)
                else:
                    rc, out = self.lint()
                    self.assertEqual(rc, 0, "a ``` line closed the ```` fence, so the Refuter line after it is hidden:\n%s"
                                     % out)

    def test_a_closer_with_an_info_string_does_not_close_the_fence(self):
        """CommonMark: a closing fence has no info string. A ```text line inside a ``` fence is text, so a Refuter line
        after it stays hidden; the bare ``` after it closes the fence, so a Refuter line after that counts."""
        cases = [(["```", "```text", REFUTER, "```"], True), (["```", "```text", "```", REFUTER], False)]
        for index, (lines, flagged) in enumerate(cases):
            with self.subTest(lines=lines):
                self.rebase_here()
                rel = PLANS + "/info-closer-%d.md" % index
                self.commit("add plan with an info-string line in a fence", {rel: plan(*lines)})
                self.assertStatus(rel, "A")
                if flagged:
                    self.assertNamed(rel)
                else:
                    rc, out = self.lint()
                    self.assertEqual(rc, 0, "a ```text line closed the ``` fence, so the Refuter line after it counts:\n%s"
                                     % out)

    def test_a_line_that_opens_with_inline_code_is_not_a_fence(self):
        """CommonMark: a backtick fence's info string has no backtick. A line that starts with a code span is a
        paragraph, so the Refuter line after it is a real line and counts."""
        for index, line in enumerate(["```x``` is code", "```x` then the rest"]):
            with self.subTest(line=line):
                self.rebase_here()
                rel = PLANS + "/inline-code-%d.md" % index
                self.commit("add plan with an inline code run", {rel: plan(line, REFUTER)})
                self.assertStatus(rel, "A")
                rc, out = self.lint()
                self.assertEqual(rc, 0, "a line that opens with inline code opened a fence and hid the Refuter line:\n%s"
                                 % out)

    def test_refuter_mid_line_is_flagged(self):
        for index, line in enumerate(["The refuter: none", "See Refuter: %s opus, PASS" % REFUTER_ROLE,
                                      "Review by Refuter: %s opus, PASS" % REFUTER_ROLE]):
            with self.subTest(line=line):
                self.rebase_here()
                rel = PLANS + "/mid-line-%d.md" % index
                self.commit("add mid-line refuter plan", {rel: plan(line)})
                self.assertStatus(rel, "A")
                self.assertNamed(rel)

    def test_refuter_line_removed_before_merge_is_flagged(self):
        """The check reads the file as it stands at HEAD. A line that the range removes again does not count."""
        rel = PLANS + "/removed-refuter.md"
        self.commit("add plan with refuter", {rel: plan(REFUTER)})
        self.commit("drop the refuter line", {rel: plan("Body only.")})
        self.assertStatus(rel, "A")
        self.assertNamed(rel)

    def test_refuter_line_added_later_in_range_passes(self):
        """The same rule from the other side: the file as it stands at HEAD carries the line."""
        rel = PLANS + "/later-refuter.md"
        self.commit("add plan", {rel: plan("Body only.")})
        self.commit("add the refuter line", {rel: plan(REFUTER)})
        self.assertStatus(rel, "A")
        self.assertClean()

    def test_plan_with_refuter_line_passes(self):
        rel = PLANS + "/refuter-plan.md"
        self.commit("add plan", {rel: plan(REFUTER)})
        self.assertStatus(rel, "A")
        self.assertClean()

    def test_plan_with_bold_refuter_line_passes(self):
        rel = PLANS + "/bold-refuter-plan.md"
        self.commit("add plan", {rel: plan(BOLD_REFUTER)})
        self.assertStatus(rel, "A")
        self.assertClean()

    def test_refuter_after_a_closed_fence_passes(self):
        """The fence closes, so a real line after it counts: a fence that never closed would hide that line. The
        quote and the # inside the fence are plain text to it."""
        rel = PLANS + "/fence-then-refuter.md"
        self.commit("add plan", {rel: plan("Don't skip the review.", "```", "# not a heading",
                                           "Refuter: %s opus, example only" % REFUTER_ROLE, "```", "", REFUTER)})
        self.assertStatus(rel, "A")
        self.assertClean()

    def test_full_size_plan_with_refuter_at_its_end_passes(self):
        rel = PLANS + "/long-plan.md"
        body = "".join("Step %d of the plan.\n" % number for number in range(BIG_LINES))
        self.commit("add long plan", {rel: plan(body, REFUTER)})
        self.assertStatus(rel, "A")
        self.assertClean()

    def test_full_size_plan_without_refuter_is_flagged(self):
        rel = PLANS + "/long-plan.md"
        body = "".join("Step %d of the plan.\n" % number for number in range(BIG_LINES))
        self.commit("add long plan", {rel: plan(body)})
        self.assertStatus(rel, "A")
        self.assertNamed(rel)

    def test_plan_in_a_subfolder_is_not_judged(self):
        rel = PLANS + "/folder/x.md"
        self.commit("add subfolder plan", {rel: plan("Body only.")})
        self.assertStatus(rel, "A")
        self.assertClean()

    def test_folder_named_like_the_plans_home_is_not_judged(self):
        """A prefix check with no slash would read docs/plans-old as the plans home."""
        rel = PLANS + "-old/x.md"
        self.commit("add old-folder plan", {rel: plan("Body only.")})
        self.assertStatus(rel, "A")
        self.assertClean()

    def test_modified_old_plan_is_not_judged(self):
        rel = PLANS + "/old-plan.md"
        self.commit("edit old plan", {rel: OLD_PLAN + "More text.\n"})
        self.assertStatus(rel, "M")
        self.assertClean()

    def test_subfolder_plan_beside_a_direct_plan_is_not_named(self):
        """The direct plan is judged and named; the subfolder plan, which has no line either, is not."""
        direct, sub = PLANS + "/direct.md", PLANS + "/folder/x.md"
        self.commit("add two plans", {direct: plan("Body only."), sub: plan("Body only.")})
        self.assertStatus(direct, "A")
        self.assertStatus(sub, "A")
        out = self.assertNamed(direct)
        self.assertNotIn(sub, out, "the subfolder plan is judged, not only the direct one:\n" + out)

    def test_no_plans_touched_passes(self):
        self.commit("change widget source", {"src/widgets.py": SRC + "# edit\n"})
        self.assertEqual([path for path in self.changed() if path.startswith(PLANS + "/")], [],
                         "scope: a plan is in the range")
        self.assertClean()

    def test_empty_range_passes(self):
        self.rebase_here()
        self.assertEqual(self.changed(), {}, "scope: the range is not empty")
        self.assertClean()

    def test_non_md_file_in_the_plans_home_is_not_judged(self):
        rel = PLANS + "/notes.txt"
        self.commit("add plan notes", {rel: "Notes, not a plan.\n"})
        self.assertStatus(rel, "A")
        self.assertClean()

    def test_good_plan_beside_a_bad_plan_is_not_named(self):
        good, bad = PLANS + "/good.md", PLANS + "/bad.md"
        self.commit("add two plans", {good: plan(REFUTER), bad: plan("Body only.")})
        self.assertStatus(good, "A")
        self.assertStatus(bad, "A")
        out = self.assertNamed(bad)
        self.assertNotIn(good, out, "a plan with a Refuter line is named:\n" + out)

    def test_no_base_exits_two_as_unknown(self):
        rel = PLANS + "/new-plan.md"
        self.commit("add widget plan", {rel: plan("Body only.")})  # a real finding, so 0 would be wrong
        self.assertStatus(rel, "A")
        rc, out = self.lint([])
        self.assertEqual(rc, 2, out)
        self.assertIn("unknown", out.lower(), out)
        self.assertNotIn("Traceback", out, out)

    def test_unreadable_base_exits_two_as_unknown(self):
        rel = PLANS + "/new-plan.md"
        self.commit("add widget plan", {rel: plan("Body only.")})  # a real finding, so 0 would be wrong
        self.assertStatus(rel, "A")
        for args, env in ((["--base", "0" * 40], None), ([], {"BASE_SHA": "1" * 40})):
            with self.subTest(args=args, env=env):
                rc, out = self.lint(args, env)
                self.assertEqual(rc, 2, out)
                self.assertIn("unknown", out.lower(), out)
                self.assertNotIn("Traceback", out, out)

    def test_base_comes_from_base_sha_without_a_flag(self):
        rel = PLANS + "/new-plan.md"
        self.commit("add widget plan", {rel: plan("Body only.")})
        self.assertStatus(rel, "A")
        self.assertNamed(rel, args=[], env={"BASE_SHA": self.base_sha})

    def test_root_flag_names_the_repo_to_read(self):
        """--root picks the repo whatever the current directory is. The cwd here is outside every repo."""
        rel = PLANS + "/new-plan.md"
        self.commit("add widget plan", {rel: plan("Body only.")})
        self.assertStatus(rel, "A")
        cwd = tempfile.mkdtemp(dir=RUN_FOLDER, prefix="cwd_")
        self.addCleanup(tracked_tree.rm_tree, cwd)
        out = self.assertNamed(rel, args=["--root", self.tree, "--base", self.base_sha], cwd=cwd)
        self.assertNotIn("usage", out, out)

    def test_root_that_does_not_exist_exits_two_as_unknown(self):
        """A --root that names no folder is UNKNOWN: exit 2 and a line that says so, never a traceback with exit 1."""
        rel = PLANS + "/new-plan.md"
        self.commit("add widget plan", {rel: plan("Body only.")})  # a real finding, so 0 would be wrong
        self.assertStatus(rel, "A")
        missing = os.path.join(RUN_FOLDER, "no-such-repo")
        self.assertFalse(os.path.exists(missing), "scope: the --root path exists")
        rc, out = self.lint(["--root", missing, "--base", self.base_sha])
        self.assertEqual(rc, 2, "a --root that names no folder exits %d, not 2:\n%s" % (rc, out))
        self.assertIn("unknown", out.lower(), out)
        self.assertNotIn("Traceback", out, out)

    def test_an_extras_file_that_is_not_json_exits_two_as_unknown(self):
        """The layout reader wraps a decode failure as LayoutError, so the check prints UNKNOWN with exit 2: never a
        traceback, and never a green 0 on a layout it could not read. The range holds a real finding, so 0 or 1 is wrong."""
        for index, text in enumerate(["{ not json\n", ""]):
            with self.subTest(text=text):
                self.rebase_here()
                rel = PLANS + "/unknown-extras-%d.md" % index
                self.commit("add widget plan and break the extras file", {rel: plan("Body only."), EXTRAS_REL: text})
                self.assertStatus(rel, "A")
                rc, out = self.lint()
                self.assertEqual(rc, 2, "a non-JSON extras file exits %d, not 2:\n%s" % (rc, out))
                self.assertIn("UNKNOWN", out, out)
                self.assertNotIn("Traceback", out, out)

    def test_a_check_whose_hooks_do_not_import_exits_two_as_unknown(self):
        """The import-failure branch: REFUTER_ROLE is unread, so the check exits 2 and prints UNKNOWN, even on a real
        finding. Each variant runs a copy of the check beside lint/layout.py, the copy's reader, in a folder of its
        own. The copy's hooks/ is missing or broken, so the copy cannot read the role from the repo."""
        rel = PLANS + "/new-plan.md"
        self.commit("add widget plan", {rel: plan("Body only.")})  # a real finding, so 0 or 1 would be wrong
        self.assertStatus(rel, "A")
        variants = {
            "no hooks folder beside the check": None,
            "guard_core raises on import": {"guard_core.py": "raise ImportError('broken on purpose')\n",
                                            "_nowindow.py": "\n"},
        }
        for name, hooks in variants.items():
            with self.subTest(variant=name):
                home = tempfile.mkdtemp(dir=RUN_FOLDER, prefix="lone_")
                self.addCleanup(tracked_tree.rm_tree, home)
                os.makedirs(os.path.join(home, "lint"))
                shutil.copyfile(MODULE, os.path.join(home, "lint", "check_plan_refuter.py"))
                for lib in ("layout.py", "layout.json"):
                    shutil.copyfile(os.path.join(HERE, lib), os.path.join(home, "lint", lib))
                if hooks is not None:
                    os.makedirs(os.path.join(home, "hooks"))
                    for lib, text in hooks.items():
                        with open(os.path.join(home, "hooks", lib), "w", encoding="utf-8") as f:
                            f.write(text)
                rc, out = self.lint(module=os.path.join(home, "lint", "check_plan_refuter.py"))
                self.assertEqual(rc, 2, "the check exits %d, not 2, when hooks/ does not import:\n%s" % (rc, out))
                self.assertIn("UNKNOWN", out, out)
                self.assertNotIn("Traceback", out, out)


if __name__ == "__main__":
    unittest.main()
