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
import json
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
import protect  # noqa: E402
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


def section_of(text, title):
    """The body of the `## <title>` section of a template, or None."""
    m = re.search(r"(?m)^## " + re.escape(title) + r"\n(.*?)(?=\n## |\Z)", text, re.S)
    return m.group(1) if m else None


def pages_section(text):
    """The body of the `## Pages` section of a hand-off, or None."""
    return section_of(text, "Pages")


def rotation_rule(text):
    """The `## Rotation of standing sessions` section of the operating model."""
    return re.search(r"## Rotation of standing sessions.*?(?=\n## )", text, re.S).group(0)


def rotation_steps(rule):
    """The numbered steps of the rotation rule, number -> text on one line."""
    return dict(zip(map(int, re.findall(r"(?m)^\s+(\d+)\.\s", rule)),
                    [" ".join(t.split()) for t in re.split(r"(?m)^\s+\d+\.\s", rule)[1:]]))


# The lane brief's claims are judged one sentence at a time, so a neighbour's words cannot supply one.
NEGATION = r"\b(?:never|not|no|neither|nor|cannot|can't|won't)\b"
SHARING = r"\b(?:shar(?:e|es|ed|ing)|same (?:checkout|worktree)|one (?:checkout|worktree))\b"
# A sentence with no negation at all: the affirmative form of a claim, so its inverse cannot pass.
NO_NEGATION = r"^(?!.*" + NEGATION + r")"
# The builder may do the act: a permission word sits right before the verb, with no negation between.
PERMITS = (r"\bbuilders?\s+(?:may|can|could|might|(?:is|are)\s+(?:allowed|free)\s+to)\s+(?:also\s+)?"
           r"(?:cherry|amend|rewrit|rebas|squash|reword)")
# The builder never does it: the negation sits right before the verb, so a clause after the verb cannot supply it.
NEVER_REWRITES = (r"(?:\bbuilders?\s+(?:(?:must|do|does|shall|will)\s+)?(?:never|not|neither|cannot|can't|won't)\s+"
                  r"|\bno builders?\s+(?:(?:may|can|should)\s+)?)(?:cherry|amend|rewrit|rebas|squash|reword)")


def sentences(text):
    """The text, whitespace flattened and split after each sentence end."""
    return re.split(r"(?<=[.!?])\s+", " ".join(text.split()))


def has_sentence(sents, *patterns):
    """True when one sentence matches every pattern. No sentence at all is False, never an error."""
    return any(all(re.search(p, s, re.I) for p in patterns) for s in sents)


def denies_sharing(sentence):
    """True when the sentence says the agents never share a checkout: a negation, then `share` within a few words, or `share no`."""
    return (re.search(NEGATION + r"\W+(?:\w+\W+){0,3}?" + SHARING, sentence, re.I) is not None
            or re.search(SHARING + r"\s+(?:no|none)\b", sentence, re.I) is not None)


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
        # The roadmap is a block of the repo's one page, which the page writer publishes (skill roadmap).
        self.assertRegex(flat, r"builds? the roadmap block", "triage must build the roadmap block")
        self.assertIn("--block", flat)
        self.assertIn("--live", flat)
        self.assertNotRegex(flat, r"(?i)roadmap page", "the roadmap is no page of its own: triage builds a block, the page writer publishes it")

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
        # session-tiers (owner): no usage limit. A standing session runs until autocompact.
        self.assertNotIn("<triage limit>", flat, "the rotation section still names the triage limit")
        self.assertNotIn("<batch runner limit>", flat, "the rotation section still names the batch runner limit")
        self.assertIn("The coordinator never hands its own sessions to a successor", flat)

    def rotation_flat(self):
        """The rotation section, flattened. The scope comes first: a missing section fails here, once."""
        text = tree(SKILL)["templates/operating-model.md"]
        self.assertIn("## Rotation of standing sessions", text, "the operating model has no rotation section")
        return " ".join(rotation_rule(text).split())

    def test_rotation_follows_the_no_limit_ruling(self):
        # session-tiers (owner): no usage limit. A standing session runs until
        # autocompact, and the coordinator rotates it only when it goes stale or breaks.
        flat = self.rotation_flat()
        for clause in ("session-tiers", "goes stale or breaks", "runs until autocompact"):
            with self.subTest(clause=clause):
                self.assertIn(clause, flat, f"the rotation section does not say {clause!r}")
        with self.subTest(clause="arbiter"):
            self.assertRegex(flat, r"\barbiter\b", "the rotation section does not name the arbiter")

    def test_rotation_names_no_limit_or_exemption(self):
        # session-tiers (owner): no usage limit, so no limit to be at or to exempt from.
        flat = self.rotation_flat()
        self.assertIn("The coordinator never hands its own sessions to a successor", flat,
                      "the rotation section lost its coordinator rule, so a cut-off section would pass")
        for stale in ("<triage limit>", "<batch runner limit>", "at its limit", "phase change", "exempt"):
            with self.subTest(stale=stale):
                self.assertNotIn(stale, flat.lower(), f"the rotation section still names {stale!r}")

    def test_roster_has_no_exemptions_line(self):
        # session-tiers (owner): no usage limit, so the roster has no exemption line.
        text = tree(SKILL)["templates/roster.md"]
        self.assertIn("## Standing sessions", text, "the roster has no standing sessions section")
        self.assertNotRegex(text, r"(?m)^Exemptions:", "the roster still has an Exemptions line")

    def test_skill_names_no_usage_tally(self):
        # session-tiers (owner): rotation runs until autocompact, not by a usage tally.
        flat = " ".join(tree(SKILL)["SKILL.md"].split())
        self.assertIn("name: project-ops", flat, "SKILL.md has no project-ops name")
        self.assertNotRegex(flat, r"(?i)usage tally", "SKILL.md still names a usage tally")

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
        self.assertIn("starts triage and the batch runner together, as a trio, before any lane", flat)
        self.assertIn("checks whether that repo has an active coordinator", flat)
        self.assertIn("It does not wait for a reply.", flat)
        self.assertIn("tags itself and each session it starts `cs-repo:<owner>/<name>` and `cs-build:<tier>`", flat)
        self.assertIn("a live session tagged both `cs-repo:<other owner>/<other name>` and `cs-build:coordinator`", flat)
        self.assertIn("filters the tags itself", flat)
        coordinator = re.search(r"- \*\*Coordinator\.\*\*.*?(?=\n- \*\*)", tiers, re.S).group(0)
        self.assertIn("`cs-step:<step id>`", " ".join(coordinator.split()))

    def test_batch_runner_reads_the_priority_rows_at_each_wake(self):
        text = tree(SKILL)["templates/operating-model.md"]
        bullet = re.search(r"- \*\*Batch runner\.\*\*.*?(?=\n- \*\*)", text, re.S)
        self.assertIsNotNone(bullet, "no Batch runner bullet")
        flat = " ".join(bullet.group(0).split())
        self.assertIn("merge --priority-rows", flat, "the batch runner's wake must run the priority rows read")
        self.assertRegex(flat, r"priority: <slug> \| (?:pr|branch): ", "the batch runner bullet must show the priority row form")

    def test_handoff_template_has_a_priorities_section_with_the_row_form(self):
        section = section_of(tree(SKILL)["templates/role-handoff.md"], "Priorities")
        self.assertIsNotNone(section, "no ## Priorities section in the hand-off template")
        flat = " ".join(section.split())
        self.assertRegex(flat, r"priority: <slug> \| (?:pr|branch): ", "the Priorities section must show the row form")

    def test_brief_carries_repo_tag(self):
        flat = " ".join(tree(SKILL)["templates/brief.md"].split())
        self.assertIn("tags `cs-repo:<owner>/<name>`, `cs-build:lane` and `cs-step:<step id>`", flat)

    def brief_sentences(self):
        """The lane brief as sentences. The scope comes first: a wrong file fails here, once."""
        text = tree(SKILL)["templates/brief.md"]
        self.assertIn("Lane brief:", text, "scope: templates/brief.md is not the lane brief")
        return sentences(text)

    def test_brief_isolates_test_author_and_builder(self):
        sents = self.brief_sentences()
        with self.subTest(claim="own isolated worktree"):
            self.assertTrue(
                has_sentence(sents, r"test[- ]author", r"\bbuilders?\b", r"\b(?:each|both|separately)\b",
                             r"\b(?:own|separate|dedicated)\b", r"\b(?:isolated|separate|dedicated)\b",
                             r"\b(?:worktrees?|checkouts?)\b"),
                "no sentence says the test-author and the builder each get their own isolated worktree")
        with self.subTest(claim="never share"):
            self.assertTrue(
                any(re.search(SHARING, s, re.I) and denies_sharing(s) for s in sents),
                "no sentence says the test-author and the builder never share a worktree")

    def test_brief_lands_test_commits_before_builder_starts(self):
        sents = self.brief_sentences()
        with self.subTest(claim="test commit lands first"):
            self.assertTrue(
                has_sentence(sents, r"\btest[- ]commits?\b", r"\b(?:lands?|landed|pushed|committed)\b",
                             r"\b(?:on|onto|to) the (?:lane )?branch\b",
                             r"\b(?:before|ahead of|prior to)\b.*\bbuilders?\b.*\bstart", NO_NEGATION),
                "no sentence says a test commit lands on the lane branch before the builder starts")
        with self.subTest(claim="builder starts from the branch head"):
            self.assertTrue(
                has_sentence(sents, r"\bbuilders?\b", r"\bworktrees?\b", r"\bstart\w*", r"\bfrom\b",
                             r"\b(?:head|tip)\b", NO_NEGATION),
                "no sentence says the builder's worktree starts from the branch head")

    def test_brief_forbids_builder_rewriting_test_commits(self):
        sents = self.brief_sentences()
        self.assertTrue(
            has_sentence(sents, NEVER_REWRITES, r"\bamend\w*", r"\b(?:rewrit|rebas|reword|squash)\w*",
                         r"\btest[- ]commits?\b"),
            "no sentence says the builder never cherry-picks, amends or rewrites a test commit")

    def test_brief_grants_no_shared_checkout_and_no_builder_rewrite(self):
        sents = self.brief_sentences()
        shared = [s for s in sents if re.search(SHARING, s, re.I) and not denies_sharing(s)]
        grants = [s for s in sents if re.search(PERMITS, s, re.I)]
        with self.subTest(claim="shared checkout"):
            self.assertEqual(shared, [], "a sentence says the test-author and the builder share a checkout")
        with self.subTest(claim="builder rewrite"):
            self.assertEqual(grants, [], "a sentence lets the builder cherry-pick, amend or rewrite a test commit")

    def test_brief_says_where_lane_lint_runs(self):
        files = tree(SKILL)
        self.assertIn("templates/brief.md", files)  # the scope first: a missing brief fails here, once
        flat = " ".join(files["templates/brief.md"].split())
        self.assertIn("Run `merge --lane-lint` from the main checkout, never from a session or agent "
                      "isolated in a worktree: Claude Code's worktree check can refuse it there.", flat,
                      "templates/brief.md does not say where lane lint runs")

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

    def test_a_count_in_parentheses_beside_the_url_is_no_id(self):
        # "(3 open)" counts the open items; it copies no id. A real id beside the URL is still caught.
        self.assertEqual(problems(handoff_text(ITEMS, [PAGE])), [])
        found = problems(handoff_text(f"{ITEMS} #123", [PAGE]))
        self.assertEqual(len(found), 1, found)
        self.assertRegex(found[0], r"(?i)\bids?\b")
        self.assertEqual(problems(handoff_text(f"{ITEMS} (3 open)", [PAGE])), [])

    def test_ids_written_inside_a_count_in_parentheses_are_still_caught(self):
        # The count is no id, but an id written inside the parentheses is: each one still gives the one problem.
        for items in (f"{ITEMS} (3 open: 12, 13)", f"{ITEMS} (2 open: #34)", f"{ITEMS} (3 open, ids 12 14)"):
            with self.subTest(items=items):
                found = problems(handoff_text(items, [PAGE]))
                self.assertEqual(len(found), 1, found)
                self.assertRegex(found[0], r"ids?")

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


REPO_RULESETS = "repos/acme/widgets/rulesets"  # the rulesets route of the fake repo
ADMIN_ROLE = 5  # 5 is the id the ruling's form assumes and is unconfirmed against a live ruleset


def ruled_ruleset(ruleset_id, branch="main"):
    """A ruleset in the form decision `main-branch-protection` sets: the rollup as its one required check, deletion and force-push blocked,
    the Admin role bypassing on pull requests only. The cases copy it from here."""
    rollup = {"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": protect.REQUIRED_CHECK}]}}
    return {"id": ruleset_id, "name": "ruleset-%d" % ruleset_id, "target": "branch", "enforcement": "active",
            "conditions": {"ref_name": {"include": ["refs/heads/" + branch], "exclude": []}},
            "rules": [rollup, {"type": "deletion"}, {"type": "non_fast_forward"}],
            "bypass_actors": [{"actor_type": "RepositoryRole", "actor_id": ADMIN_ROLE, "bypass_mode": "pull_request"}]}


def summary(ruleset_id):
    """A ruleset as the list read gives it: no conditions, no rules, which only its own read gives."""
    return {"id": ruleset_id, "name": "ruleset-%d" % ruleset_id, "target": "branch"}


def list_page(args, items):
    """The items a list read gives for `args`, as gh api gives them: page `page` (1 when not given) of `per_page` items (30 when not given,
    100 at most), or every item under --paginate."""
    if "--paginate" in args:
        return list(items)
    fields = dict(args[i + 1].split("=", 1) for i, a in enumerate(args[:-1]) if a == "-f")
    size = max(1, min(int(fields.get("per_page", 30)), 100))
    n = int(fields.get("page", 1))
    return list(items)[(n - 1) * size:n * size]


class Protect(unittest.TestCase):
    """Adopting a repo sets a ruleset on its default branch that requires its one required check (the rollup), so no repo starts with none
    (decision `main-branch-protection`). A fake `gh` records each call."""

    def required(self):
        return protect.REQUIRED_CHECK  # the one home of the name (protect.py): no case copies it

    def run_protect(self, *argv, existing=None, other_rules=False, rulesets=(), details=None, write_error=None):
        """`existing` is the classic required checks (None: no classic protection), `other_rules` a classic protection with no check rule. `rulesets`
        are the repo's ruleset summaries, `details` each one's full object by id, and `write_error` the (code, output) every ruleset write answers.
        A list read gives the page it asks for (list_page)."""
        calls = []
        details = details or {}

        def gh(args, body=None):
            calls.append((list(args), body))
            method, route = args[args.index("-X") + 1], args[-1]
            if method == "GET" and route.endswith("/required_status_checks"):
                if existing is not None:
                    return 0, '{"contexts": %s}' % json.dumps(existing)
                return 1, "HTTP 404: Required status checks not enabled" if other_rules else "HTTP 404: Branch not protected"
            if method == "GET" and route.endswith("/protection"):
                return (0, '{"required_pull_request_reviews": {"required_approving_review_count": 1},"enforce_admins": {"enabled": true}}') if other_rules else (1, "HTTP 404: Branch not protected")
            if route.split("?")[0] == REPO_RULESETS:
                if method == "GET":
                    return 0, json.dumps(list_page(args, rulesets))
                if method == "POST":
                    return write_error or (0, '{"id": 42}')
            m = re.fullmatch(r"repos/acme/widgets/rulesets/(\d+)", route)
            if m and method == "GET":
                return (0, json.dumps(details[int(m.group(1))])) if int(m.group(1)) in details else (1, "HTTP 404: Not Found")
            if m and method == "PUT":
                return write_error or (0, "{}")
            return 0, "{}"
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = protect.main(list(argv), gh=gh)
        self.last_stderr = err.getvalue()  # what a refusal printed to stderr, alone
        return code, out.getvalue() + err.getvalue(), calls

    def confirm(self, **kw):
        return self.run_protect("--repo", "acme/widgets", "--check", self.required(), "--confirm", **kw)

    def writes(self, calls):
        """Every call that changes something, as (method, route, body)."""
        return [(a[a.index("-X") + 1], a[-1], b) for a, b in calls if a[a.index("-X") + 1] != "GET"]

    def ruleset_post(self, calls, consequence):
        """The body of the run's one POST to the repo's rulesets. Scope first: a run with no such POST fails here, and `consequence` says what that costs."""
        posts = [(m, r, b) for m, r, b in self.writes(calls) if (m, r) == ("POST", REPO_RULESETS)]
        self.assertEqual(len(posts), 1, "no ruleset POST to the repo's rulesets (writes: %r), so %s" % ([(m, r) for m, r, _ in self.writes(calls)], consequence))
        return posts[0][2]

    def rule_types(self, body):
        return [r["type"] for r in body.get("rules", [])]

    def required_contexts(self, body):
        return [c["context"] for r in body.get("rules", []) if r["type"] == "required_status_checks"
                for c in r["parameters"]["required_status_checks"]]

    def classic_writes(self, calls):
        return [(m, r) for m, r, _ in self.writes(calls) if "/protection" in r]

    def test_the_required_check_is_the_rollup(self):
        self.assertEqual(protect.REQUIRED_CHECK, "all-jobs-passed")  # the one literal of the name in this file

    def test_preview_changes_nothing_and_names_the_call(self):
        code, out, calls = self.run_protect("--repo", "acme/widgets", "--check", self.required())
        self.assertEqual(code, 0, out)
        self.assertFalse([c for c in calls if "GET" not in c[0]], calls)
        self.assertIn(self.required(), out)
        self.assertIn("--confirm", out)

    def test_an_unprotected_branch_gets_a_ruleset_by_post(self):
        code, out, calls = self.confirm()
        self.assertEqual(code, 0, out)
        self.ruleset_post(calls, "main has no ruleset to set")

    def test_the_ruleset_is_active_and_applies_to_main(self):
        code, out, calls = self.confirm()
        self.assertEqual(code, 0, out)
        body = self.ruleset_post(calls, "it cannot be active on main")
        self.assertEqual(body.get("enforcement"), "active", "the ruleset must be active, not disabled or in evaluate mode")
        self.assertIn("refs/heads/main", body.get("conditions", {}).get("ref_name", {}).get("include", []), "the ruleset must name main")

    def test_the_ruleset_requires_only_the_rollup_check(self):
        code, out, calls = self.confirm()
        self.assertEqual(code, 0, out)
        body = self.ruleset_post(calls, "it cannot require the rollup")
        self.assertEqual(self.required_contexts(body), [self.required()], "the ruleset must require the rollup and no other check")

    def test_the_ruleset_blocks_deletion(self):
        code, out, calls = self.confirm()
        self.assertEqual(code, 0, out)
        body = self.ruleset_post(calls, "it cannot block deletion")
        self.assertIn("deletion", self.rule_types(body), "the ruleset must block deletion of main")

    def test_the_ruleset_blocks_force_pushes(self):
        code, out, calls = self.confirm()
        self.assertEqual(code, 0, out)
        body = self.ruleset_post(calls, "it cannot block force pushes")
        self.assertIn("non_fast_forward", self.rule_types(body), "the ruleset must block force pushes to main")

    def test_only_the_admin_role_may_bypass(self):
        code, out, calls = self.confirm()
        self.assertEqual(code, 0, out)
        body = self.ruleset_post(calls, "it cannot name a bypass")
        self.assertEqual([(b.get("actor_type"), b.get("actor_id")) for b in body.get("bypass_actors", [])],
                         [("RepositoryRole", ADMIN_ROLE)], "the Admin role is the only bypass actor")

    def test_the_admin_bypass_is_on_pull_requests_only(self):
        code, out, calls = self.confirm()
        self.assertEqual(code, 0, out)
        body = self.ruleset_post(calls, "it cannot name a bypass mode")
        self.assertEqual([b.get("bypass_mode") for b in body.get("bypass_actors", [])], ["pull_request"],
                         "the bypass holds on pull requests only, never on a direct push")

    def test_an_existing_ruleset_on_main_is_updated_in_place(self):
        stale = ruled_ruleset(9)
        stale["rules"] = [r for r in stale["rules"] if r["type"] != "deletion"]  # the form before the deletion block was added
        code, out, calls = self.confirm(rulesets=[summary(9)], details={9: stale})
        self.assertEqual(code, 0, out)
        self.assertEqual([(m, r) for m, r, _ in self.writes(calls)], [("PUT", REPO_RULESETS + "/9")],
                         "the stale ruleset on main is PUT in place, and no second ruleset is POSTed")
        self.assertIn("deletion", self.rule_types(self.writes(calls)[0][2]), "the PUT restores the deletion block")

    def test_a_ruleset_already_in_the_ruled_form_is_left_alone(self):
        code, out, calls = self.confirm(rulesets=[summary(9)], details={9: ruled_ruleset(9)})
        self.assertEqual(code, 0, out)
        self.assertEqual(self.writes(calls), [], "a ruleset already in the ruled form has nothing to set")

    def test_a_classic_protection_is_left_alone_and_the_ruleset_is_added(self):
        code, out, calls = self.confirm(existing=["old"])
        self.assertEqual(code, 0, out)
        self.ruleset_post(calls, "a classic protected main still needs the ruleset")
        self.assertEqual(self.classic_writes(calls), [], "the classic protection is not written: its removal is a later act")

    def test_the_ruleset_list_is_read_past_its_first_page(self):
        stale = ruled_ruleset(101)
        stale["rules"] = [r for r in stale["rules"] if r["type"] != "deletion"]
        # protect.py asks for 100 to a page: a full first page of 100, and main's ruleset is the 101st, on page 2
        rulesets = [summary(i) for i in range(1, 102)]
        details = {i: ruled_ruleset(i, branch="dev-%d" % i) for i in range(1, 101)}
        details[101] = stale
        code, out, calls = self.confirm(rulesets=rulesets, details=details)
        self.assertEqual(code, 0, out)
        self.assertEqual([(m, r) for m, r, _ in self.writes(calls)], [("PUT", REPO_RULESETS + "/101")],
                         "main's ruleset is on page 2: it is PUT, not POSTed as a second ruleset")

    def test_a_ruleset_not_active_on_main_is_set_active(self):
        for mode in ("disabled", "evaluate"):
            with self.subTest(mode=mode):
                stale = ruled_ruleset(9)
                stale["enforcement"] = mode
                code, out, calls = self.confirm(rulesets=[summary(9)], details={9: stale})
                self.assertEqual(code, 0, out)
                self.assertEqual([(m, r) for m, r, _ in self.writes(calls)], [("PUT", REPO_RULESETS + "/9")],
                                 "a ruleset on main in %s mode is not in the ruled form, so it is PUT" % mode)
                self.assertEqual(self.writes(calls)[0][2].get("enforcement"), "active", "the PUT sets the ruleset active")

    def test_a_ruleset_requiring_other_checks_is_set_to_the_rollup_alone(self):
        stale = ruled_ruleset(9)
        stale["rules"][0] = {"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": self.required()}, {"context": "lint"}]}}
        code, out, calls = self.confirm(rulesets=[summary(9)], details={9: stale})
        self.assertEqual(code, 0, out)
        self.assertEqual([(m, r) for m, r, _ in self.writes(calls)], [("PUT", REPO_RULESETS + "/9")],
                         "a ruleset that also requires lint is not in the ruled form, so it is PUT")
        self.assertEqual(self.required_contexts(self.writes(calls)[0][2]), [self.required()], "the PUT requires the rollup alone")

    def test_a_ruleset_missing_the_force_push_block_is_set(self):
        stale = ruled_ruleset(9)
        stale["rules"] = [r for r in stale["rules"] if r["type"] != "non_fast_forward"]
        code, out, calls = self.confirm(rulesets=[summary(9)], details={9: stale})
        self.assertEqual(code, 0, out)
        self.assertEqual([(m, r) for m, r, _ in self.writes(calls)], [("PUT", REPO_RULESETS + "/9")],
                         "a ruleset without the force-push block is not in the ruled form, so it is PUT")
        self.assertIn("non_fast_forward", self.rule_types(self.writes(calls)[0][2]), "the PUT blocks force pushes to main")

    def test_a_ruleset_with_another_bypass_is_set_to_the_admin_role_on_pull_requests(self):
        wrong = {
            "bypass on every push": [{"actor_type": "RepositoryRole", "actor_id": ADMIN_ROLE, "bypass_mode": "always"}],
            "another role": [{"actor_type": "RepositoryRole", "actor_id": ADMIN_ROLE + 1, "bypass_mode": "pull_request"}],
            "no bypass": [],
        }
        for name, actors in wrong.items():
            with self.subTest(bypass=name):
                stale = ruled_ruleset(9)
                stale["bypass_actors"] = actors
                code, out, calls = self.confirm(rulesets=[summary(9)], details={9: stale})
                self.assertEqual(code, 0, out)
                self.assertEqual([(m, r) for m, r, _ in self.writes(calls)], [("PUT", REPO_RULESETS + "/9")],
                                 "a ruleset whose bypass is %s is not in the ruled form, so it is PUT" % name)
                self.assertEqual(self.writes(calls)[0][2].get("bypass_actors"),
                                 [{"actor_type": "RepositoryRole", "actor_id": ADMIN_ROLE, "bypass_mode": "pull_request"}],
                                 "the PUT bypass is the Admin role on pull requests only")

    def test_an_in_form_ruleset_with_extra_rules_is_left_alone(self):
        ruled = ruled_ruleset(9)
        ruled["rules"] += [{"type": "pull_request", "parameters": {"required_approving_review_count": 1}}, {"type": "required_signatures"}]
        code, out, calls = self.confirm(rulesets=[summary(9)], details={9: ruled})
        self.assertEqual(code, 0, out)
        self.assertEqual(self.writes(calls), [], "a ruleset in the ruled form with rules the form does not name has nothing to set")

    def test_a_put_keeps_the_other_rules_the_ruled_form_does_not_name(self):
        stale = ruled_ruleset(9)
        stale["rules"] = [r for r in stale["rules"] if r["type"] != "deletion"] + [{"type": "pull_request", "parameters": {"required_approving_review_count": 1}}]
        code, out, calls = self.confirm(rulesets=[summary(9)], details={9: stale})
        self.assertEqual(code, 0, out)
        self.assertEqual([(m, r) for m, r, _ in self.writes(calls)], [("PUT", REPO_RULESETS + "/9")], "the stale ruleset is PUT in place")
        self.assertIn("pull_request", self.rule_types(self.writes(calls)[0][2]), "the PUT keeps the held pull_request rule")

    def test_a_put_keeps_the_strict_setting_of_the_held_required_checks(self):
        stale = ruled_ruleset(9)
        stale["rules"] = [r for r in stale["rules"] if r["type"] != "deletion"]
        stale["rules"][0]["parameters"]["strict_required_status_checks_policy"] = True
        code, out, calls = self.confirm(rulesets=[summary(9)], details={9: stale})
        self.assertEqual(code, 0, out)
        self.assertEqual([(m, r) for m, r, _ in self.writes(calls)], [("PUT", REPO_RULESETS + "/9")], "the stale ruleset is PUT in place")
        strict = [r["parameters"].get("strict_required_status_checks_policy") for r in self.writes(calls)[0][2]["rules"] if r["type"] == "required_status_checks"]
        self.assertEqual(strict, [True], "the PUT keeps the held strict setting")

    def test_a_put_keeps_the_conditions_of_the_held_ruleset(self):
        stale = ruled_ruleset(9)
        stale["rules"] = [r for r in stale["rules"] if r["type"] != "deletion"]
        stale["conditions"] = {"ref_name": {"include": ["refs/heads/main"], "exclude": ["refs/heads/hotfix-*"]}}
        code, out, calls = self.confirm(rulesets=[summary(9)], details={9: stale})
        self.assertEqual(code, 0, out)
        self.assertEqual([(m, r) for m, r, _ in self.writes(calls)], [("PUT", REPO_RULESETS + "/9")], "the stale ruleset is PUT in place")
        self.assertEqual(self.writes(calls)[0][2].get("conditions"), stale["conditions"], "the PUT keeps the held conditions")

    def test_a_put_keeps_the_name_of_the_held_ruleset(self):
        stale = ruled_ruleset(9)
        stale["rules"] = [r for r in stale["rules"] if r["type"] != "deletion"]
        stale["name"] = "main-guard"
        code, out, calls = self.confirm(rulesets=[summary(9)], details={9: stale})
        self.assertEqual(code, 0, out)
        self.assertEqual([(m, r) for m, r, _ in self.writes(calls)], [("PUT", REPO_RULESETS + "/9")], "the stale ruleset is PUT in place")
        self.assertEqual(self.writes(calls)[0][2].get("name"), "main-guard", "the PUT keeps the held ruleset's name")

    def test_a_ruleset_write_the_api_refuses_exits_1(self):
        code, out, calls = self.confirm(write_error=(1, "HTTP 422: Validation Failed"))
        self.assertEqual(code, 1, "a ruleset write the API refuses must exit 1\n" + out)

    def test_no_checks_is_refused(self):
        for checks in (["--check", ""], ["--check", "  "], []):
            code, out, calls = self.run_protect("--repo", "acme/widgets", *checks, "--confirm")
            self.assertEqual(code, 2, out)
            self.assertEqual(calls, [])

    def test_a_check_other_than_the_rollup_is_refused_before_any_gh_call(self):
        # a name off by a matrix part or a suffix is another check too: only the rollup may reach a PUT
        for name in ("checks", "test (ubuntu, 3.11)", f"{self.required()} (ubuntu)"):
            for confirm in ([], ["--confirm"]):
                with self.subTest(name=name, confirm=bool(confirm)):
                    code, out, calls = self.run_protect("--repo", "acme/widgets", "--check", name, *confirm)
                    self.assertEqual(code, 2, f"--check {name!r}: exit 2 expected\n{out}")
                    self.assertEqual(calls, [], f"--check {name!r}: no gh call expected, not even a GET")

    def test_a_refused_check_names_the_rollup(self):
        for confirm in ([], ["--confirm"]):
            with self.subTest(confirm=bool(confirm)):
                code, out, _ = self.run_protect("--repo", "acme/widgets", "--check", "checks", *confirm)
                self.assertEqual(code, 2, f"--check checks: exit 2 expected\n{out}")
                self.assertIn(self.required(), self.last_stderr, "--check checks: stderr must name the required check")

    def test_two_checks_are_refused_before_any_gh_call(self):
        for confirm in ([], ["--confirm"]):
            with self.subTest(confirm=bool(confirm)):
                code, out, calls = self.run_protect("--repo", "acme/widgets", "--check", self.required(), "--check", f"{self.required()} (ubuntu)", *confirm)
                self.assertEqual(code, 2, "two --check names: exit 2 expected\n" + out)
                self.assertEqual(calls, [], "two --check names: no gh call expected, not even a GET")
                self.assertRegex(self.last_stderr, r"(?i)only one (--)?check", "two --check names: stderr must say only one check is allowed")

    def test_an_empty_check_name_is_not_counted(self):
        code, out, calls = self.run_protect("--repo", "acme/widgets", "--check", "", "--check", self.required(), "--confirm")
        self.assertEqual(code, 0, out)
        body = self.ruleset_post(calls, "the empty name cannot be checked")
        self.assertEqual(self.required_contexts(body), [self.required()], "the empty name is no check: the ruleset names the rollup alone")

    def test_the_same_name_twice_is_one_check(self):
        code, out, calls = self.run_protect("--repo", "acme/widgets", "--check", self.required(), "--check", f" {self.required()}\t", "--confirm")
        self.assertEqual(code, 0, "the same name twice is one check: exit 0 expected\n" + out)
        body = self.ruleset_post(calls, "the repeated name cannot be checked")
        self.assertEqual(self.required_contexts(body), [self.required()], "the same name twice: the ruleset must name the check once")


if __name__ == "__main__":
    unittest.main()
