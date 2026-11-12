#!/usr/bin/env python3
"""Cases for lint/check_plan_step_cites.py. Standard library only.

    python3 lint/test_check_plan_step_cites.py

A plan is a file directly in the plans home (lint/layout.json, kind "plans"), named <name>.md. The check judges it as
it stands in the working tree. A part is any indented numbered line: `N. text` with 2+ spaces before it. Its label is
the nearest bullet above it that opens a ruling, `- **<ID>.` (ID like R26, G1, D3), else `(no ruling id)`. Part text is
the part line plus the following lines indented deeper than its marker. It ends at the next part, bullet, heading,
blank line, or a line at the marker's indent or less. Each part needs one valid cite `step:<slug>` in its part text,
outside a code fence. A valid cite names a live step: a file roadmap/data/steps/<slug>.json on git branch roadmap, read
with git (origin/roadmap first, then roadmap), never the working tree. An opaque slug (one letter then digits, such as
c55) is valid only with a gloss in parentheses right after it.

    python3 lint/check_plan_step_cites.py [--root DIR]

Exit 0: clean. Exit 1: a part has no valid cite, printed as `<file>:<line>: <ruling> part <N>: <reason>`. Exit 2:
UNKNOWN, printed, when the roadmap branch or the plans home cannot be read. Unknown is never 0.

Each case builds a fixture repo under this run's folder (lint/_test_temp.py): a base commit that marks the repo rolled
out to the layout, a roadmap branch that holds the live steps, and plan files left in the working tree.
CHECK_PLAN_STEP_CITES_UNDER_TEST overrides the module path, which a mutant run uses.
"""
import os
import re
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
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  rm_tree clears read-only git objects (testing/tracked_tree.py)

MODULE = os.path.abspath(os.environ.get("CHECK_PLAN_STEP_CITES_UNDER_TEST")
                         or os.path.join(HERE, "check_plan_step_cites.py"))
PLANS = layout.layout()["kinds"]["plans"]["path"]  # the default plans home, read from the layout
EXTRAS_REL = ".claude/layout-extras.json"  # the layout's extras file; rolled out, so layout.path() reads PLANS
EXTRAS_TEXT = '{"kinds": {}, "rolled-out": true}\n'
STEPS = "roadmap/data/steps"  # the folder of step files on the roadmap branch
LIVE = ("build-widget", "ship-widget", "c55")  # the steps the roadmap branch holds by default; c55 is opaque
TITLE = "# Plan: widget rollout\n\nWhat we build, and why.\n\n"
RULING = "- **R26.** Widgets ship in two parts."
NO_RULING = "(no ruling id)"
SRC = "def widget():\n    return 1\n"
BIG_RULINGS = 200  # a full-size plan: each ruling adds its own parts, so the plan runs to thousands of lines

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
    """A plan: its title, then each line on its own."""
    return TITLE + "".join(line + "\n" for line in lines)


def line_of(text, start):
    """The 1-based number of the first line of text that starts with `start`, read from the text itself."""
    for number, line in enumerate(text.splitlines(), 1):
        if line.startswith(start):
            return number
    raise AssertionError("no line starts with %r in:\n%s" % (start, text))


class Fixture(unittest.TestCase):
    """A fixture repo: a base commit marked rolled out, a roadmap branch with the live steps, and plans in the working tree."""

    def setUp(self):
        self.tree = tempfile.mkdtemp(dir=RUN_FOLDER, prefix="cpsc_")
        self.addCleanup(tracked_tree.rm_tree, self.tree)
        self.git("init", "-q")
        self.git("symbolic-ref", "HEAD", "refs/heads/main")
        self.write({EXTRAS_REL: EXTRAS_TEXT, "src/widgets.py": SRC})
        self.git("add", "--", EXTRAS_REL, "src/widgets.py")
        self.git("commit", "-q", "--cleanup=verbatim", "-F", "-", input="fixture base\n")
        self.make_branch("refs/heads/roadmap", LIVE)

    def git(self, *args, input=None, env=None):
        done = subprocess.run(["git", "-C", self.tree, "-c", "user.name=test", "-c", "user.email=test@example.com",
                               "-c", "core.autocrlf=false", *args],
                              check=True, capture_output=True, text=True, env=dict(GIT_ENV, **(env or {})),
                              input=input)
        return done.stdout.strip()

    def git_ok(self, *args):
        """True when git exits 0 for args. For a scope check on a ref that may be absent."""
        return subprocess.run(["git", "-C", self.tree, *args], capture_output=True, env=GIT_ENV).returncode == 0

    def write(self, files):
        for rel, text in files.items():
            path = os.path.join(self.tree, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(text)

    def make_branch(self, ref, slugs, files=None):
        """Point ref at a root commit with a step file per slug, plus any extra files. HEAD and the working tree stay as they are."""
        env = {"GIT_INDEX_FILE": os.path.join(self.tree, ".git", "step-index")}
        self.git("read-tree", "--empty", env=env)
        entries = {"%s/%s.json" % (STEPS, slug): '{"slug": "%s"}\n' % slug for slug in slugs}
        entries.update(files or {})
        for rel, text in entries.items():
            blob = self.git("hash-object", "-w", "--stdin", input=text)
            self.git("update-index", "--add", "--cacheinfo", "100644,%s,%s" % (blob, rel), env=env)
        tree = self.git("write-tree", env=env)
        commit = self.git("commit-tree", tree, "-m", "record branch", env=env)
        self.git("update-ref", ref, commit)

    def plan_file(self, name, text):
        """Write a plan into the plans home, in the working tree only. Returns its path from the repo root."""
        rel = PLANS + "/" + name
        self.write({rel: text})
        self.assertTrue(os.path.isfile(os.path.join(self.tree, *rel.split("/"))),
                        "scope: the plan is not in the working tree")
        return rel

    def reset_plans(self):
        """Empty the plans home, so the next lint judges only the plans that the subtest writes next."""
        shutil.rmtree(os.path.join(self.tree, *PLANS.split("/")), ignore_errors=True)

    def assertStepScope(self, slug, on_branch, in_tree):
        """Scope before the verdict: where the step file is, so the verdict that follows judges the step a case names."""
        self.assertEqual(self.git_ok("cat-file", "-e", "roadmap:%s/%s.json" % (STEPS, slug)), on_branch,
                         "scope: %s on the roadmap branch is not %s" % (slug, on_branch))
        self.assertEqual(os.path.isfile(os.path.join(self.tree, *STEPS.split("/"), slug + ".json")), in_tree,
                         "scope: %s in the working tree is not %s" % (slug, in_tree))

    def lint(self, args=None, cwd=None, module=None):
        """Run the check on the fixture repo, or from cwd. Returns (exit code, stdout and stderr)."""
        done = subprocess.run([sys.executable, module or MODULE, *(args or [])], cwd=cwd or self.tree,
                              capture_output=True, text=True, encoding="utf-8", errors="replace", env=GIT_ENV)
        return done.returncode, done.stdout + done.stderr

    def assertClean(self, args=None, cwd=None):
        rc, out = self.lint(args, cwd)
        self.assertEqual(rc, 0, "expected exit 0, got %d:\n%s" % (rc, out))
        self.assertNotIn("Traceback", out, out)

    def assertFlagged(self, rel, line, ruling, part, reason, args=None, cwd=None):
        """Exit 1, and exactly one part is flagged: this line, with this ruling, part number and reason."""
        rc, out = self.lint(args, cwd)
        self.assertEqual(rc, 1, "expected exit 1, got %d:\n%s" % (rc, out))
        self.assertNotIn("Traceback", out, out)
        want = "%s:%d: %s part %d: %s" % (rel, line, ruling, part, reason)
        self.assertTrue(re.search(re.escape(want) + r"[ \t]*$", out, re.M), "no line `%s` in:\n%s" % (want, out))
        flagged = [text for text in out.splitlines() if re.search(r" part \d+: ", text)]
        self.assertEqual(len(flagged), 1, "more than one part is flagged:\n%s" % out)

    def assertUnknown(self, args=None, cwd=None):
        rc, out = self.lint(args, cwd)
        self.assertEqual(rc, 2, "expected exit 2 (UNKNOWN), got %d:\n%s" % (rc, out))
        self.assertIn("UNKNOWN", out, out)
        self.assertNotIn("Traceback", out, out)


class StepCiteCase(Fixture):

    def test_control_fixture_reads_the_steps_from_the_branch(self):
        """Green on main, which has no check. The layout resolves the plans home, the live steps are on the roadmap
        branch and not in the working tree, and a plan file is in the working tree."""
        self.assertEqual(layout.path(self.tree, "plans"), PLANS, "the fixture does not resolve the default plans home")
        self.assertTrue(self.git_ok("rev-parse", "--verify", "-q", "refs/heads/roadmap"), "scope: no roadmap branch")
        self.assertStepScope("ship-widget", on_branch=True, in_tree=False)
        rel = self.plan_file("control.md", plan(RULING, "  1. Build the widget. step:build-widget"))
        self.assertTrue(os.path.isfile(os.path.join(self.tree, *rel.split("/"))))

    def test_part_with_no_cite_is_flagged(self):
        text = plan(RULING, "  1. Build the widget.", "  2. Ship it. step:ship-widget")
        self.assertStepScope("ship-widget", on_branch=True, in_tree=False)
        rel = self.plan_file("no-cite.md", text)
        self.assertFlagged(rel, line_of(text, "  1. "), "R26", 1, "no step cited")

    def test_part_citing_a_gone_step_is_flagged(self):
        text = plan(RULING, "  1. Build the widget. step:gone-step", "  2. Ship it. step:ship-widget")
        self.assertStepScope("gone-step", on_branch=False, in_tree=False)
        rel = self.plan_file("gone.md", text)
        self.assertFlagged(rel, line_of(text, "  1. "), "R26", 1, "step gone-step does not exist")

    def test_part_citing_a_live_step_passes(self):
        text = plan(RULING, "  1. Build the widget. step:build-widget", "  2. Ship it. step:ship-widget")
        self.assertStepScope("ship-widget", on_branch=True, in_tree=False)
        self.plan_file("live.md", text)
        self.assertClean()

    def test_opaque_step_with_a_gloss_passes(self):
        text = plan(RULING, "  1. Build the widget. step:c55 (short gloss)", "  2. Ship it. step:ship-widget")
        self.assertStepScope("c55", on_branch=True, in_tree=False)
        self.plan_file("gloss.md", text)
        self.assertClean()

    def test_opaque_step_without_a_gloss_is_flagged(self):
        text = plan(RULING, "  1. Build the widget. step:c55", "  2. Ship it. step:ship-widget")
        self.assertStepScope("c55", on_branch=True, in_tree=False)
        rel = self.plan_file("no-gloss.md", text)
        self.assertFlagged(rel, line_of(text, "  1. "), "R26", 1, "opaque step c55 needs a gloss")

    def test_any_one_valid_cite_passes_the_part(self):
        """A part passes when one of its cites is valid, even with a gone or gloss-less cite beside it."""
        for cites in ("step:gone-step step:ship-widget", "step:c55 step:ship-widget"):
            with self.subTest(cites=cites):
                self.reset_plans()
                self.plan_file("mixed.md", plan(RULING, "  1. Build the widget. " + cites,
                                                "  2. Ship it. step:ship-widget"))
                self.assertClean()

    def test_no_roadmap_branch_exits_two_as_unknown(self):
        text = plan(RULING, "  1. Build the widget.")  # a real finding, so 0 or 1 would be wrong
        self.plan_file("no-branch.md", text)
        self.git("update-ref", "-d", "refs/heads/roadmap")
        self.assertFalse(self.git_ok("rev-parse", "--verify", "-q", "refs/heads/roadmap"),
                         "scope: the roadmap branch is still there")
        self.assertFalse(self.git_ok("rev-parse", "--verify", "-q", "refs/remotes/origin/roadmap"),
                         "scope: origin/roadmap is there")
        self.assertUnknown()

    def test_cite_on_a_continuation_line_counts(self):
        text = plan(RULING, "  1. Build the widget and wire it to the line,",
                    "     as step:build-widget sets out.", "  2. Ship it. step:ship-widget")
        self.assertStepScope("build-widget", on_branch=True, in_tree=False)
        self.plan_file("continuation.md", text)
        self.assertClean()

    def test_cite_in_the_next_part_or_a_home_line_does_not_count(self):
        cases = {
            "next part": [RULING, "  1. Build the widget.", "  2. Ship it. step:ship-widget"],
            "home line": [RULING, "  1. Build the widget.", "  Home: see step:ship-widget"],
        }
        for name, lines in cases.items():
            with self.subTest(case=name):
                self.reset_plans()
                text = plan(*lines)
                rel = self.plan_file("outside.md", text)
                self.assertFlagged(rel, line_of(text, "  1. "), "R26", 1, "no step cited")

    def test_cite_on_the_ruling_line_or_after_a_blank_line_does_not_count(self):
        cases = {
            "ruling line": ["- **R26.** Widgets ship. step:ship-widget", "  1. Build the widget."],
            "after a blank line": [RULING, "  1. Build the widget.", "", "     see step:ship-widget"],
        }
        for name, lines in cases.items():
            with self.subTest(case=name):
                self.reset_plans()
                text = plan(*lines)
                rel = self.plan_file("outside-part.md", text)
                self.assertFlagged(rel, line_of(text, "  1. "), "R26", 1, "no step cited")

    def test_plan_with_no_numbered_parts_passes(self):
        text = plan(RULING, "- **R27.** A second ruling with no parts.", " 1. One space is not a part.",
                    "1. Column zero is not a part.", "Home: the rulings folder")
        self.plan_file("no-parts.md", text)
        self.assertClean()

    def test_numbered_line_with_no_ruling_above_is_flagged(self):
        """A part needs no ruling bullet above it. The label is the nearest ruling, else (no ruling id)."""
        text = plan("Widgets ship in two parts.", "  1. Build the widget.", "  2. Ship it. step:ship-widget")
        self.assertStepScope("ship-widget", on_branch=True, in_tree=False)
        rel = self.plan_file("no-ruling.md", text)
        self.assertFlagged(rel, line_of(text, "  1. "), NO_RULING, 1, "no step cited")

    def test_numbered_line_with_no_ruling_above_passes_with_a_cite(self):
        text = plan("Widgets ship in two parts.", "  1. Build the widget. step:build-widget",
                    "  2. Ship it. step:ship-widget")
        self.plan_file("no-ruling-cited.md", text)
        self.assertClean()

    def test_steps_are_read_from_the_branch_not_the_working_tree(self):
        self.write({"%s/ghost.json" % STEPS: '{"slug": "ghost"}\n'})
        self.assertStepScope("ghost", on_branch=False, in_tree=True)
        text = plan(RULING, "  1. Build the widget. step:ghost", "  2. Ship it. step:ship-widget")
        rel = self.plan_file("tree-only.md", text)
        self.assertFlagged(rel, line_of(text, "  1. "), "R26", 1, "step ghost does not exist")

    def test_origin_roadmap_is_read_before_the_local_branch(self):
        """origin/roadmap is tried first. Its steps decide, so a step only on the local branch does not count."""
        self.make_branch("refs/remotes/origin/roadmap", ["remote-only"])
        self.assertTrue(self.git_ok("cat-file", "-e", "refs/remotes/origin/roadmap:%s/remote-only.json" % STEPS),
                        "scope: remote-only is not on origin/roadmap")
        self.assertFalse(self.git_ok("cat-file", "-e", "refs/remotes/origin/roadmap:%s/ship-widget.json" % STEPS),
                         "scope: ship-widget is on origin/roadmap")
        self.assertStepScope("ship-widget", on_branch=True, in_tree=False)
        self.reset_plans()
        self.plan_file("remote.md", plan(RULING, "  1. Build the widget. step:remote-only",
                                         "  2. Ship it. step:remote-only"))
        self.assertClean()
        self.reset_plans()
        text = plan(RULING, "  1. Build the widget. step:ship-widget", "  2. Ship it. step:remote-only")
        rel = self.plan_file("local-only.md", text)
        self.assertFlagged(rel, line_of(text, "  1. "), "R26", 1, "step ship-widget does not exist")

    def test_cite_inside_a_code_fence_does_not_count(self):
        text = plan(RULING, "  1. Build the widget.", "     ```", "     step:build-widget", "     ```",
                    "  2. Ship it. step:ship-widget")
        self.assertStepScope("build-widget", on_branch=True, in_tree=False)
        rel = self.plan_file("fenced-cite.md", text)
        self.assertFlagged(rel, line_of(text, "  1. "), "R26", 1, "no step cited")

    def test_quotes_and_comment_openers_in_text_are_read_as_text(self):
        text = plan("- **R26.** Don't skip the review. See // and /* and <!-- in the spec.",
                    "  1. Don't skip it: keep the # sign and the // comment. step:build-widget",
                    "  2. Ship it, and don't stop at /* this one. step:ship-widget")
        self.plan_file("quotes.md", text)
        self.assertClean()

    def test_a_fenced_block_holds_no_ruling_and_no_part(self):
        """A fenced block is text. A ruling and a numbered line inside it are not read as a ruling or a part."""
        text = plan("```", "- **R99.** An example ruling in a block.", "  1. An example part with no cite.", "```",
                    RULING, "  1. Build the widget. step:build-widget", "  2. Ship it. step:ship-widget")
        self.plan_file("fenced-block.md", text)
        self.assertClean()

    def test_empty_plans_home_and_an_empty_plan_pass(self):
        home = os.path.join(self.tree, *PLANS.split("/"))
        os.makedirs(home)
        self.assertEqual(os.listdir(home), [], "scope: the plans home is not empty")
        self.assertClean()
        self.plan_file("empty.md", "")
        self.assertClean()

    def test_only_direct_md_files_in_the_plans_home_are_judged(self):
        sub, notes = PLANS + "/folder/x.md", PLANS + "/notes.txt"
        self.write({sub: plan("  1. Build the widget."), notes: plan("  1. Build the widget.")})
        self.assertTrue(os.path.isfile(os.path.join(self.tree, *sub.split("/"))), "scope: the subfolder plan is missing")
        self.assertTrue(os.path.isfile(os.path.join(self.tree, *notes.split("/"))), "scope: the notes file is missing")
        self.assertClean()

    def test_full_size_plan_with_a_cite_in_every_part_passes(self):
        lines = []
        for number in range(1, BIG_RULINGS + 1):
            lines += ["- **R%d.** Ruling %d of the widget plan." % (number, number),
                      "  1. Build part one. step:build-widget",
                      "  2. Ship part two. step:c55 (short gloss)"]
        self.plan_file("long.md", plan(*lines))
        self.assertClean()

    def test_full_size_plan_flags_a_two_digit_part_with_no_cite(self):
        lines = []
        for number in range(1, BIG_RULINGS + 1):
            lines.append("- **R%d.** Ruling %d of the widget plan." % (number, number))
            last = number == BIG_RULINGS
            for part in range(1, (10 if last else 2) + 1):
                cite = "" if (last and part == 10) else " step:build-widget"
                lines.append("  %d. Build part %d.%s" % (part, part, cite))
        text = plan(*lines)
        rel = self.plan_file("long-flagged.md", text)
        self.assertFlagged(rel, line_of(text, "  10. "), "R%d" % BIG_RULINGS, 10, "no step cited")

    def test_plans_home_that_is_a_file_exits_two_as_unknown(self):
        self.write({PLANS: "not a folder\n"})
        self.assertTrue(os.path.isfile(os.path.join(self.tree, *PLANS.split("/"))),
                        "scope: the plans home is not a file")
        self.assertUnknown()

    def test_root_flag_names_the_repo_to_read(self):
        text = plan(RULING, "  1. Build the widget.")
        rel = self.plan_file("root.md", text)
        cwd = tempfile.mkdtemp(dir=RUN_FOLDER, prefix="cwd_")  # outside every repo
        self.addCleanup(tracked_tree.rm_tree, cwd)
        self.assertFlagged(rel, line_of(text, "  1. "), "R26", 1, "no step cited", args=["--root", self.tree], cwd=cwd)

    def test_root_that_names_no_folder_exits_two_as_unknown(self):
        missing = os.path.join(RUN_FOLDER, "no-such-repo")
        self.assertFalse(os.path.exists(missing), "scope: the --root path exists")
        cwd = tempfile.mkdtemp(dir=RUN_FOLDER, prefix="cwd_")
        self.addCleanup(tracked_tree.rm_tree, cwd)
        self.assertUnknown(args=["--root", missing], cwd=cwd)


if __name__ == "__main__":
    unittest.main()
