#!/usr/bin/env python3
"""Cases for skills/project-ops/scripts/scaffold.py and protect.py. Standard library only.

    python3 skills/project-ops/tests/test_scaffold.py

Each case runs the scaffold into an empty temp folder, the dry run of the skill. The cases prove
the file list, the filled placeholders, the refusal over an existing file, and that nothing the
skill writes or ships names this project's threads, sessions or people. The HandoffCheck cases
judge scripts/check_handoff.py, and the Scaffold cases name the template lines that feed it.
Temp files: the run folder of lint/_test_temp.py (decision test-temp-standard).
"""
import contextlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(SKILL, "scripts"))
sys.path.insert(1, os.path.join(SKILL, "..", "..", "lint"))
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (the one home, lint/_test_temp.py)
import scaffold  # noqa: E402

try:
    import check_handoff  # noqa: E402
except ModuleNotFoundError as e:  # Only a missing check_handoff.py: a broken one must fail loud.
    if e.name != "check_handoff":
        raise
    check_handoff = None
CLI = os.path.join(SKILL, "scripts", "check_handoff.py")
RUN_FOLDER = None  # made in setUpModule

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


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


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


def pages_section(text):
    """The body of the `## Pages` section of a hand-off, or None."""
    m = re.search(r"## Pages\n(.*?)(?=\n## |\Z)", text, re.S)
    return m.group(1) if m else None


def rotation_rule(text):
    """The `## Rotation of standing sessions` section of the operating model."""
    return re.search(r"## Rotation of standing sessions.*?(?=\n## )", text, re.S).group(0)


def rotation_steps(rule):
    """The numbered steps of the rotation rule, number -> text on one line."""
    return dict(zip(map(int, re.findall(r"(?m)^\s+(\d+)\.\s", rule)),
                    [" ".join(t.split()) for t in re.split(r"(?m)^\s+\d+\.\s", rule)[1:]]))


class TempDest(unittest.TestCase):
    def setUp(self):
        self.dest = tempfile.mkdtemp(dir=RUN_FOLDER)
        self.addCleanup(shutil.rmtree, self.dest)


class Scaffold(TempDest):

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
        flat = " ".join(bullet.split())  # a line wrap must not split a phrase
        # The roadmap is a block of the repo's one page, which the waiting-page writer publishes (skill roadmap).
        self.assertRegex(flat, r"builds? the roadmap block", "triage must build the roadmap block")
        self.assertIn("--block", flat)
        self.assertIn("--live", flat)
        self.assertNotRegex(flat, r"(?i)roadmap page", "the roadmap is no page of its own: triage builds a block, the waiting-page writer publishes it")

    def assertInOrder(self, flat, clauses):
        at = [flat.find(x) for x in clauses]
        for clause, pos in zip(clauses, at):
            self.assertNotEqual(pos, -1, clause)
        self.assertEqual(at, sorted(at), clauses)

    def test_handoff_template_lists_pages_to_watch(self):
        text = tree(SKILL)["templates/role-handoff.md"]
        section = pages_section(text)
        self.assertIsNotNone(section, "no Pages section")
        self.assertRegex(section, r"(?m)^Watches stopped at <time>$")
        flat = " ".join(section.split())
        self.assertIn("The URL of each page this role owns", flat)
        self.assertInOrder(flat, (
            "old session stopped watching each one at that time",
            "answered each comment still open at that time",
            "wrote this file",
            "successor watches each one at once",
            "reads its comments since that time"))

    def test_handoff_rule_moves_page_watches(self):
        text = tree(SKILL)["templates/operating-model.md"]
        flat = " ".join(rotation_rule(text).split())
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

    def test_handoff_template_has_the_open_items_and_watch_lines(self):
        # The two fixed forms that scripts/check_handoff.py reads. A placeholder stands in for the values.
        section = pages_section(tree(SKILL)["templates/role-handoff.md"])
        self.assertIsNotNone(section, "no Pages section")
        line = re.search(r"(?m)^Open items: .*$", section)
        self.assertIsNotNone(line, "no `Open items:` line")
        # The home of the items is a URL, or `none`. A hand-off never carries item ids (the triage incident).
        self.assertRegex(line.group(0), r"(?i)\burl\b", "the `Open items:` line must offer the items collection by URL")
        self.assertRegex(line.group(0), r"\bnone\b", "the `Open items:` line must offer `none`")
        self.assertNotRegex(line.group(0), r"<n\b|\.\.\.", "the `Open items:` line must not offer a list of ids")
        self.assertNotRegex(section, r"(?i)number of each", "the Pages section must not tell the role to copy item numbers")
        self.assertRegex(section, r"(?m)^Watch: \S", "no `Watch: <page URL>` line")

    def test_rotation_runs_the_handoff_check_before_the_successor_starts(self):
        rule = rotation_rule(tree(SKILL)["templates/operating-model.md"])
        steps = rotation_steps(rule)
        holders = [n for n, text in sorted(steps.items()) if "check_handoff.py" in text]
        self.assertTrue(holders, "no rotation step names check_handoff.py")
        self.assertIn(holders[0], (3, 4), "the check belongs to the hand-off file step")
        self.assertInOrder(" ".join(rule.split()), (
            "writes the hand-off file",
            "check_handoff.py",
            "coordinator starts the successor from the hand-off file"))

    def test_rotation_hand_off_names_the_home_of_the_open_items_not_each_item(self):
        rule = rotation_rule(tree(SKILL)["templates/operating-model.md"])
        step = rotation_steps(rule)[3]
        self.assertIn("writes the hand-off file", step, "step 3 is the hand-off file step")
        self.assertIn("items collection", step, "step 3 must name the home of the open items")
        self.assertRegex(step, r"\bURL\b")
        self.assertNotRegex(step, r"(?i)\beach open\b[\w\s-]*\bitem\b", "step 3 must not copy each open item into the file")

    def test_tiers_start_as_a_trio(self):
        text = tree(SKILL)["templates/operating-model.md"]
        tiers = re.search(r"## Session tiers.*?(?=\n## )", text, re.S).group(0)
        flat = " ".join(tiers.split())
        self.assertIn("starts triage and the batch runner together, as a trio, before any lane session", flat)
        self.assertIn("checks whether that repo has an active coordinator", flat)
        self.assertIn("It does not wait for a reply.", flat)
        self.assertIn("tags itself and each session it starts `cs-repo:<owner>/<name>` and `cs-build:<tier>`", flat)
        self.assertIn("a live session tagged both `cs-repo:<other owner>/<other name>` and `cs-build:coordinator`", flat)
        self.assertIn("filters the tags itself", flat)

    def test_brief_carries_repo_tag(self):
        flat = " ".join(tree(SKILL)["templates/brief.md"].split())
        self.assertIn("tags `cs-repo:<owner>/<name>` and `cs-build:lane`", flat)

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


PAGE = "https://claude.ai/code/artifact/example"
PAGE_TWO = "https://claude.ai/code/artifact/example-two"
ITEMS = "https://claude.ai/code/artifact/example/items"  # the waiting page's items collection
# Each is a list of ids or numbers, which a hand-off must not carry. `05` and `0, 4` start with a zero.
IDS = ("12", "7", "10", "12, 14", "05", "0, 4", "A12, B14")
# A URL beside an id list is still a copied id list: the ids go stale, the URL does not.
IDS_BESIDE_URL = (f"12, 14, 15 ({PAGE})", f"{PAGE} 12, 14", f"#12 {PAGE}")
# A placeholder, or a URL that holds `<` or `>`, is no page and no items home.
BAD_WATCHES = ("https://<page-url>", "<page URL>", "https://claude.ai/code/artifact/<id>",
               "https://claude.ai/code/artifact/example>")
# The words of a missing Watch line. A Watch line that is there but wrong names its fault instead.
NO_WATCH_LINE = re.compile(r"(?i)\bno\s+`?watch\b")
# A message that still offers item numbers as the way to fill the `Open items:` line.
OFFERS_IDS = re.compile(r"(?i)\bitem numbers?\b")


def handoff_text(open_items="none", watches=()):
    """A full role hand-off. open_items=None leaves the `Open items:` line out. Each watch is the
    text after `Watch: `, one line each. The one fixture of the HandoffCheck cases: a case adds an option, never a copy."""
    pages = ["Watches stopped at 10:00", ""]
    if open_items is not None:
        pages.append(f"Open items: {open_items}")
    pages.extend(f"Watch: {w}" for w in watches)
    return "\n".join([
        "# Triage handoff, 2026-01-02", "",
        'From "old triage" at the limit. Checked: main abc1234, record branch def5678.', "",
        "## Standing instructions", "", "Don't skip the check.", "",
        "## State", "", "Item 12 is in flight.", "",
        "## Pages", "", *pages, "",
        "## Sessions", "", "The batch runner.", ""])


def problems(text):
    """handoff_problems(text), or a failure of the one case when check_handoff.py does not exist yet."""
    if check_handoff is None:
        raise AssertionError("skills/project-ops/scripts/check_handoff.py does not exist")
    return check_handoff.handoff_problems(text)


class HandoffCheck(TempDest):
    """A save of the waiting page wakes only a session that watches it. A successor that inherits open items
    and gets no Watch line hears nothing (the owner's two test saves). The check judges the hand-off file."""

    def test_open_items_without_a_watch_line_is_one_problem(self):
        found = problems(handoff_text(ITEMS))
        self.assertEqual(len(found), 1, found)
        self.assertRegex(found[0], r"(?i)watch")

    def test_a_watch_line_without_a_url_is_no_watch(self):
        for watch in ("", "<page URL>", "none"):
            with self.subTest(watch=watch):
                found = problems(handoff_text(ITEMS, [watch]))
                self.assertEqual(len(found), 1, found)
                self.assertRegex(found[0], r"(?i)watch")

    def test_open_items_with_a_watch_line_is_ok(self):
        for items in (ITEMS, "http://example.test/items"):
            with self.subTest(items=items):
                self.assertEqual(problems(handoff_text(items, [PAGE])), [])
                self.assertEqual(problems(handoff_text(items, [PAGE, PAGE_TWO])), [])

    def test_a_list_of_ids_is_a_problem_that_names_the_url_home(self):
        # A copied id list goes stale after a compaction and keeps closed items (the triage incident).
        for items in IDS + IDS_BESIDE_URL:
            with self.subTest(items=items):
                found = problems(handoff_text(items, [PAGE]))
                self.assertEqual(len(found), 1, found)
                self.assertRegex(found[0], r"(?i)items collection")
                self.assertRegex(found[0], r"(?i)\burl\b")
                self.assertRegex(found[0], r"(?i)\bids?\b")
                self.assertNotRegex(found[0], OFFERS_IDS)

    def test_a_url_alone_or_with_words_or_digits_in_its_path_is_ok(self):
        # The fix for ids beside a URL must not flag the URL itself: its path may hold digits.
        for items in (ITEMS, PAGE, f"see {ITEMS}", "https://claude.ai/code/artifact/abc123/items",
                      f"none, see {PAGE}"):
            with self.subTest(items=items):
                self.assertEqual(problems(handoff_text(items, [PAGE])), [])

    def test_a_placeholder_url_is_no_items_home(self):
        for items in BAD_WATCHES:
            with self.subTest(items=items):
                found = problems(handoff_text(items, [PAGE]))
                self.assertEqual(len(found), 1, found)
                self.assertIn("Open items", found[0])
                self.assertNotRegex(found[0], OFFERS_IDS)

    def test_no_open_items_still_needs_a_watch_url_or_watch_none(self):
        # Every role that rotates owns a page, so each hand-off names a real Watch URL.
        # The one exception is `Watch: none` together with `Open items: none`.
        self.assertEqual(problems(handoff_text("none", [PAGE])), [])
        self.assertEqual(problems(handoff_text("none", ["none"])), [])
        for watches in ((), ("<page URL>",)):
            with self.subTest(watches=watches):
                found = problems(handoff_text("none", watches))
                self.assertEqual(len(found), 1, found)
                self.assertRegex(found[0], r"(?i)watch")

    def test_open_items_with_watch_none_is_a_problem(self):
        found = problems(handoff_text(ITEMS, ["none"]))
        self.assertEqual(len(found), 1, found)
        self.assertRegex(found[0], r"(?i)watch")

    def test_a_none_line_with_extra_text_is_none(self):
        for items in ("none (all answered)", "None.", "0"):
            with self.subTest(items=items):
                self.assertEqual(problems(handoff_text(items, [PAGE])), [])
                self.assertEqual(problems(handoff_text(items, ["none"])), [])

    def test_a_number_that_starts_with_a_zero_is_not_none(self):
        # `0` is none. `05` and `0, 4` are ids: the zero needs a word boundary after it.
        for items in ("10", "05", "0, 4", "007"):
            with self.subTest(items=items):
                self.assertTrue(problems(handoff_text(items, ["none"])), "read as `none`")

    def test_a_placeholder_url_is_no_watch(self):
        for items in (ITEMS, "none"):
            for watch in BAD_WATCHES + ("https://<page-url> (waiting page)",):
                with self.subTest(items=items, watch=watch):
                    found = problems(handoff_text(items, [watch]))
                    self.assertEqual(len(found), 1, found)

    def test_a_watch_line_with_trailing_text_counts(self):
        for items in (ITEMS, "none"):
            with self.subTest(items=items):
                self.assertEqual(problems(handoff_text(items, [PAGE + " (waiting page)"])), [])

    def test_a_watch_line_that_is_wrong_says_what_is_wrong(self):
        # A Watch line that is there must not draw the message of a missing one.
        for watch in BAD_WATCHES + ("", "none"):
            with self.subTest(watch=watch):
                found = problems(handoff_text(ITEMS, [watch]))
                self.assertEqual(len(found), 1, found)
                self.assertNotRegex(found[0], NO_WATCH_LINE)
                if watch not in ("", "none"):
                    self.assertIn(watch, found[0])

    def test_a_missing_open_items_line_is_a_problem(self):
        for watches in ((), (PAGE,)):
            with self.subTest(watches=watches):
                found = problems(handoff_text(None, watches))
                self.assertTrue(found, "the hand-off must say whether items are open")
                self.assertTrue(any("Open items" in p for p in found), found)
                self.assertFalse(any(OFFERS_IDS.search(p) for p in found), found)
                self.assertTrue(any(re.search(r"(?i)\burl\b", p) for p in found), "the message must offer the URL home")

    def cli(self, *args):
        self.assertTrue(os.path.isfile(CLI), "skills/project-ops/scripts/check_handoff.py does not exist")
        r = subprocess.run([sys.executable, CLI, *args], capture_output=True, text=True)
        self.assertNotIn("Traceback", r.stderr)
        return r.returncode, r.stdout, r.stderr

    def write(self, text, name="handoff.md"):
        path = os.path.join(self.dest, name)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        return path

    def test_cli_exits_0_and_says_so_when_ok(self):
        code, out, err = self.cli(self.write(handoff_text(ITEMS, [PAGE])))
        self.assertEqual(code, 0, out + err)
        self.assertTrue(out.strip(), "an ok hand-off prints its verdict")

    def test_cli_exits_1_and_prints_each_problem(self):
        text = handoff_text(ITEMS)
        expected = problems(text)
        self.assertTrue(expected)
        code, out, err = self.cli(self.write(text))
        self.assertEqual(code, 1, out + err)
        for p in expected:
            self.assertIn(p, out + err)

    def test_cli_exits_2_on_bad_arguments_or_an_unreadable_file(self):
        good = self.write(handoff_text("none", ["none"]))
        for args in ((), (good, good), (os.path.join(self.dest, "none.md"),), (self.dest,)):
            with self.subTest(args=args):
                self.assertEqual(self.cli(*args)[0], 2)


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
