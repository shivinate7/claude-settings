#!/usr/bin/env python3
"""Cases for lint/find_copies.py. Standard library only.

    python3 lint/test_find_copies.py

Each case builds a temp parent and a temp child, then runs the real script on them. The
fixtures copy the shape of the worked examples: q_max's drifted plain-english-map skill,
q_max's verbatim copy of a parent test with a header added, and the impeccable copies in
ios-adblock, joyous and degen, which differ from the parent and from each other.
FIND_COPIES_UNDER_TEST overrides the module path.
"""
import collections
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _test_temp  # noqa: E402
from rule_audit import REASON_MIN_WORDS  # noqa: E402  the one home of the exception reason's minimum (lint/rule_audit.py)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "testing"))
import tracked_tree  # noqa: E402  copies what git lists, for the cost case's script tree (testing/tracked_tree.py)
MODULE = os.environ.get("FIND_COPIES_UNDER_TEST") or os.path.join(HERE, "find_copies.py")
RUN_FOLDER = _test_temp.run_folder()  # test-temp-standard (one run folder per test run)

SKILL_MD = "---\nname: {name}\ndescription: A shared skill for the fixture.\n---\n\n" + "".join(
    f"Step {i}: do the shared thing number {i} with care.\n" for i in range(12)
)
HELPER = "".join(f"export function helper{i}(value) {{ return value * {i} + 1; }}\n" for i in range(15))
TEST = "// Red proof: node --test testing/\nimport { helper } from './helper.mjs';\n" + "".join(
    f"test('case {i} keeps its promise', () => assert.equal(helper({i}), {i * 2}));\n" for i in range(15)
)
# Comment openers inside strings, a multi-line template literal and a lone quote in text.
TRAPS = (
    "const a = 'not /* a comment';\nconst b = \"not // a comment either\";\nconst c = `line one\n"
    "line two # not a comment`;\nconst d = <p>Don't stop here</p>;\n"
    + "".join(f"const keep{i} = 'value number {i} for the trap file';\n" for i in range(10))
)


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def make_parent(root):
    write(root, "skills/impeccable/SKILL.md", SKILL_MD.format(name="impeccable"))
    write(root, "skills/impeccable/scripts/run.mjs", HELPER)
    write(root, "skills/impeccable/reference/document.md", "".join(f"Rule {i} of the reference.\n" for i in range(12)))
    write(root, "skills/plain-english-map/SKILL.md", SKILL_MD.format(name="plain-english-map"))
    write(root, "skills/plain-english-map/scripts/map-check.mjs", HELPER)
    write(root, "skills/plain-english-map/scripts/map-upgrade.mjs", HELPER.replace("helper", "upgrade"))
    write(root, "testing/skip-locally-fail-in-ci.test.mjs", TEST)
    write(root, "lint/traps.mjs", TRAPS)
    write(root, "LICENSE", "MIT License\n" * 30)
    write(root, "actions/stamp/examples/frontmatter.stamp.json", HELPER)


def run(parent, child, *extra):
    proc = subprocess.run(
        [sys.executable, MODULE, child, "--parent", parent, *extra],
        capture_output=True, text=True, timeout=60,
    )
    return proc


class RunFolderSweepTest(unittest.TestCase):
    def test_old_sibling_goes_and_new_one_stays(self):
        root = os.path.join(RUN_FOLDER, "root")
        old = os.path.join(root, "1-" + "a" * 32)
        new = os.path.join(root, "2-" + "b" * 32)
        other = os.path.join(root, "not-a-run-folder")
        for path in (old, new, other):
            os.makedirs(path)
        two_days_ago = time.time() - 2 * 24 * 60 * 60
        os.utime(old, (two_days_ago, two_days_ago))
        os.utime(other, (two_days_ago, two_days_ago))
        own = _test_temp.run_folder(root)
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.isdir(new))
        self.assertTrue(os.path.isdir(other))
        self.assertTrue(os.path.isdir(own))


class FindCopiesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=RUN_FOLDER)
        self.parent = os.path.join(self.tmp.name, "parent")
        self.child = os.path.join(self.tmp.name, "child")
        make_parent(self.parent)
        os.makedirs(self.child)

    def tearDown(self):
        self.tmp.cleanup()

    def findings(self, *extra):
        proc = run(self.parent, self.child, "--json", *extra)
        self.assertIn(proc.returncode, (0, 1), proc.stderr)
        return proc.returncode, json.loads(proc.stdout)

    def test_clean_child_is_quiet(self):
        write(self.child, "src/app.ts", "".join(f"export const own{i} = {i};\n" for i in range(20)))
        write(self.child, "LICENSE", "MIT License\n" * 30)
        proc = run(self.parent, self.child)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("no copies", proc.stdout)

    def test_drifted_skill_copy(self):
        # q_max shape: the copy lags the parent, with edits and a missing file.
        base = ".claude/skills/plain-english-map"
        write(self.child, f"{base}/SKILL.md", SKILL_MD.format(name="plain-english-map") + "A local edit.\n")
        write(self.child, f"{base}/scripts/map-check.mjs", HELPER)
        code, out = self.findings()
        self.assertEqual(code, 1)
        skills = [f for f in out["skills"] if f["skill"] == "plain-english-map"]
        self.assertEqual(len(skills), 1, out)
        s = skills[0]
        self.assertEqual(s["child_path"], base)
        self.assertEqual(s["state"], "drifted")
        self.assertEqual(s["differ"], ["SKILL.md"])
        self.assertEqual(s["only_in_parent"], ["scripts/map-upgrade.mjs"])
        # Files inside a reported skill copy are not reported again as file copies.
        self.assertEqual([f for f in out["files"] if f["child"].startswith(base)], [])

    def test_identical_skill_copy_is_still_a_copy(self):
        base = ".claude/skills/impeccable"
        write(self.child, f"{base}/SKILL.md", SKILL_MD.format(name="impeccable"))
        write(self.child, f"{base}/scripts/run.mjs", HELPER)
        write(self.child, f"{base}/reference/document.md", "".join(f"Rule {i} of the reference.\n" for i in range(12)))
        code, out = self.findings()
        self.assertEqual(code, 1)
        self.assertEqual([(s["skill"], s["state"]) for s in out["skills"]], [("impeccable", "same")])

    def test_three_impeccable_copies_that_differ(self):
        # ios-adblock, joyous and degen each hold a copy that differs from the parent and from
        # the others. Each child is its own run, so each run reports its own copy.
        edits = {
            "ios-adblock": ("SKILL.md", "Edited for ios-adblock.\n"),
            "joyous": ("scripts/run.mjs", "// joyous edit\n"),
            "degen": ("reference/document.md", "Degen's own rule.\n"),
        }
        for repo, (rel, extra) in edits.items():
            child = os.path.join(self.tmp.name, repo)
            base = os.path.join(child, ".claude/skills/impeccable")
            write(base, "SKILL.md", SKILL_MD.format(name="impeccable"))
            write(base, "scripts/run.mjs", HELPER)
            write(base, "reference/document.md", "".join(f"Rule {i} of the reference.\n" for i in range(12)))
            with open(os.path.join(base, rel), "a", encoding="utf-8") as f:
                f.write(extra)
            proc = run(self.parent, child, "--json")
            self.assertEqual(proc.returncode, 1, repo + proc.stderr)
            out = json.loads(proc.stdout)
            self.assertEqual(len(out["skills"]), 1, repo)
            self.assertEqual(out["skills"][0]["state"], "drifted", repo)
            self.assertEqual(out["skills"][0]["differ"], [rel], repo)

    def test_skill_found_by_frontmatter_name_under_another_folder(self):
        write(self.child, "tools/map-skill/SKILL.md", SKILL_MD.format(name="plain-english-map"))
        code, out = self.findings()
        self.assertEqual(code, 1)
        self.assertEqual([(s["skill"], s["child_path"]) for s in out["skills"]],
                         [("plain-english-map", "tools/map-skill")])

    def test_verbatim_test_copy_with_header(self):
        # q_max shape: the parent test, with a provenance header added on top.
        header = "// Copied verbatim from claude-settings, testing/skip-locally-fail-in-ci.test.mjs.\n// Import path adapted.\n"
        write(self.child, "harness/tests/skip-locally-fail-in-ci.test.mjs", header + TEST)
        code, out = self.findings()
        self.assertEqual(code, 1)
        self.assertEqual(len(out["files"]), 1, out)
        f = out["files"][0]
        self.assertEqual(f["parent"], "testing/skip-locally-fail-in-ci.test.mjs")
        self.assertEqual(f["child"], "harness/tests/skip-locally-fail-in-ci.test.mjs")
        self.assertEqual(f["kind"], "near-equal")
        self.assertGreaterEqual(f["score"], 0.8)

    def test_byte_equal_file_under_another_name(self):
        write(self.child, "vendor/whatever.mjs", TEST)
        code, out = self.findings()
        self.assertEqual(code, 1)
        self.assertEqual([(f["parent"], f["kind"]) for f in out["files"]],
                         [("testing/skip-locally-fail-in-ci.test.mjs", "byte-equal")])

    def test_scanner_traps_compare_as_plain_text(self):
        write(self.child, "src/traps.mjs", TRAPS)
        code, out = self.findings()
        self.assertEqual(code, 1)
        self.assertEqual([(f["parent"], f["kind"]) for f in out["files"]], [("lint/traps.mjs", "byte-equal")])

    def test_large_file_that_quotes_a_parent_file_is_not_a_copy(self):
        write(self.child, "src/big.mjs", TEST + "".join(f"const mine{i} = 'own line {i}';\n" for i in range(60)))
        code, out = self.findings()
        self.assertEqual(code, 0, out)

    def test_scanner_traps_near_equal(self):
        write(self.child, "src/traps.mjs", "// local header\n" + TRAPS)
        code, out = self.findings()
        self.assertEqual([(f["parent"], f["kind"]) for f in out["files"]], [("lint/traps.mjs", "near-equal")])

    def test_shared_boilerplate_is_not_a_copy(self):
        # A file that shares a few common lines with a parent file is not a copy.
        write(self.child, "src/other.mjs", HELPER[:200] + "".join(f"const mine{i} = {i};\n" for i in range(40)))
        code, out = self.findings()
        self.assertEqual(code, 0, out)

    def test_parent_example_is_meant_to_be_copied(self):
        write(self.child, ".github/stamp.json", HELPER.replace("helper1(", "local1("))
        code, out = self.findings()
        self.assertEqual([f["parent"] for f in out["files"]],
                         ["skills/impeccable/scripts/run.mjs"])

    def test_missing_child_is_unknown(self):
        proc = run(self.parent, os.path.join(self.tmp.name, "nowhere"))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("unknown", proc.stdout + proc.stderr)

    def test_reads_only(self):
        write(self.child, "harness/tests/copy.test.mjs", TEST)
        before = sorted(os.walk(self.child))
        run(self.parent, self.child)
        self.assertEqual(before, sorted(os.walk(self.child)))


# One-home check, copies inside a repo (plan parts a and c). The parent holds rule sentences in its RULE_FILES and
# the child copies them. Every case runs `--in-repo` from the child folder with an explicit --parent, so no case reads
# this clone's own rule text. A case that expects no finding also carries a control copy in a sibling file, so a scan
# that prints nothing fails (decision test-practices, P7).
PARENT_RULES = (
    "# Parent rules\n\n"
    "**Briefs.** Write the `<!--` opener as text. Don't pad a brief: keep it to the task, the files, the governing "
    "rulings and the check that proves it done.<!-- rule:brief-contents -->\n\n"
    "**Comments.** Keep the `//` and `/*` marks out of a brief, and leave the text after them alone."
    "<!-- rule:comment-marks -->\n\n"
    "**Quoted.** Quote the form as `Quoted form in a span stays text, not a source, so copy it only as text."
    "<!-- rule:quoted-form -->` in a brief.\n\n"
    "**Output.** Write plainly: short sentences, one term per meaning, no filler.<!-- rule:output-plain -->\n"
)
RULE = "Don't pad a brief: keep it to the task, the files, the governing rulings and the check that proves it done."
MARKS = "Keep the `//` and `/*` marks out of a brief, and leave the text after them alone."
QUOTED = "Quoted form in a span stays text, not a source, so copy it only as text."
REASON = "this child keeps its own brief wording for a reason stated here"  # twelve words, over the minimum
CONTROL = {"agents/control.md": RULE + "\n"}
CONTROL_FINDING = ("agents/control.md", 1, "COPY001")
FIND_LINE = re.compile(r"^(.+?):(\d+): (COPY001|EXEMPT00[123]) (.*)$")


def rule_parent(root):
    write(root, "CLAUDE.md", PARENT_RULES)
    write(root, "output-styles/shiv-stylisms.md", "# Output style\n\nPlain prose, with no rule anchor.\n")
    write(root, "skills/README.md", "# Skills\n")


def parse_findings(out):
    """(path, line, code, text) for each finding line the scan printed."""
    return [(m.group(1), int(m.group(2)), m.group(3), m.group(4))
            for m in (FIND_LINE.match(line) for line in out.splitlines()) if m]


def keyed(found):
    return sorted((path, line, code) for path, line, code, _ in found)


AUDIT_RUNNER = '''import json, runpy, sys
events_path, module, argv = sys.argv[1], sys.argv[2], sys.argv[3:]
events = []


def hook(name, args):
    if name == "subprocess.Popen" and isinstance(args[1], (list, tuple)):
        events.append(["proc", " ".join(str(a) for a in args[1])])
    elif name == "open" and isinstance(args[0], str):
        events.append(["open", args[0], str(args[1])])


out = open(events_path, "w")
sys.addaudithook(hook)
sys.argv = [module] + argv
code = 0
try:
    runpy.run_path(module, run_name="__main__")
except SystemExit as exc:
    code = exc.code or 0
finally:
    out.write(json.dumps(events))
    out.close()
sys.exit(code)
'''


class OneHomeInRepoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=RUN_FOLDER)
        self.addCleanup(self.tmp.cleanup)
        self.parent = os.path.join(self.tmp.name, "parent")
        self.child = os.path.join(self.tmp.name, "child")
        rule_parent(self.parent)
        os.makedirs(self.child)

    def tracked(self, files, control=True):
        """Write `files` into the child and make it a git repo that tracks them, with the control copy beside them."""
        for rel, text in {**(CONTROL if control else {}), **files}.items():
            write(self.child, rel, text)
        subprocess.run(["git", "-C", self.child, "init", "-q"], check=True)
        subprocess.run(["git", "-C", self.child, "add", "-A"], check=True)

    def scan(self, child=None, parent=None):
        proc = subprocess.run([sys.executable, MODULE, "--in-repo", "--parent", parent or self.parent],
                              cwd=child or self.child, capture_output=True, text=True, timeout=60)
        return proc.returncode, proc.stdout + proc.stderr

    def verdict_scan(self):
        """(findings, out) of a scan that printed its verdict. No verdict line means the mode is not there."""
        rc, out = self.scan()
        lines = out.strip().splitlines()
        last = lines[-1] if lines else ""
        self.assertIn(last, ("copies: PASS", "copies: FAIL"),
                      "--in-repo printed no copies: verdict, so the mode is missing: %s" % out[-400:])
        self.assertEqual(rc, 1 if last == "copies: FAIL" else 0, out)
        return parse_findings(out), out

    def test_copy_of_a_rule_sentence_without_its_id_is_reported(self):
        self.tracked({"agents/brief.md": "# Brief\n\n%s\n" % RULE}, control=False)
        found, out = self.verdict_scan()
        self.assertEqual(keyed(found), [("agents/brief.md", 3, "COPY001")], out)
        self.assertEqual(found[0][3], "brief-contents copied", out)

    def test_seven_word_run_is_no_copy_and_eight_words_is(self):
        self.tracked({"agents/seven.md": "Keep it to the task, the files, then stop.\n",
                      "agents/eight.md": "Keep it to the task, the files, the rest waits.\n"}, control=False)
        found, out = self.verdict_scan()
        self.assertEqual(keyed(found), [("agents/eight.md", 1, "COPY001")], out)

    def test_rule_id_in_the_same_paragraph_exempts_the_copy(self):
        self.tracked({"agents/paragraph.md": "Per brief-contents, the brief reads:\n%s\n" % RULE})
        found, out = self.verdict_scan()
        self.assertEqual(keyed(found), [CONTROL_FINDING], out)

    def test_rule_id_in_the_same_table_row_exempts_the_copy(self):
        self.tracked({"agents/table.md": "| Rule | Text |\n| --- | --- |\n| brief-contents | %s |\n" % RULE})
        found, out = self.verdict_scan()
        self.assertEqual(keyed(found), [CONTROL_FINDING], out)

    def test_rule_id_in_the_same_fence_exempts_the_copy(self):
        self.tracked({"agents/fence.md": "```text\n%s <!-- rule:brief-contents -->\n```\n" % RULE})
        found, out = self.verdict_scan()
        self.assertEqual(keyed(found), [CONTROL_FINDING], out)

    def test_rule_id_in_the_same_blockquote_exempts_the_copy(self):
        self.tracked({"agents/quote.md": "> %s See brief-contents.\n" % RULE})
        found, out = self.verdict_scan()
        self.assertEqual(keyed(found), [CONTROL_FINDING], out)

    def test_rule_id_in_the_next_paragraph_does_not_exempt(self):
        self.tracked({"agents/next.md": "%s\n\nSee brief-contents.\n" % RULE})
        found, out = self.verdict_scan()
        self.assertEqual(keyed(found), sorted([CONTROL_FINDING, ("agents/next.md", 1, "COPY001")]), out)

    def test_rule_id_in_another_table_row_does_not_exempt(self):
        self.tracked({"agents/row.md": "| brief-contents | term |\n| Brief | %s |\n" % RULE})
        found, out = self.verdict_scan()
        self.assertEqual(keyed(found), sorted([CONTROL_FINDING, ("agents/row.md", 2, "COPY001")]), out)

    def test_stock_phrase_under_eight_words_is_no_copy(self):
        self.tracked({"agents/stock.md": "Start with the point. No preamble.\n"})
        found, out = self.verdict_scan()
        self.assertEqual(keyed(found), [CONTROL_FINDING], out)

    def test_glossary_and_records_pages_are_not_read(self):
        self.tracked({"GLOSSARY.md": "| Brief | %s |\n" % RULE, "docs/records.md": "%s\n" % RULE})
        found, out = self.verdict_scan()
        self.assertEqual(keyed(found), [CONTROL_FINDING], out)

    def test_untracked_markdown_is_not_read(self):
        self.tracked({})
        write(self.child, "agents/untracked.md", "%s\n" % RULE)
        found, out = self.verdict_scan()
        self.assertEqual(keyed(found), [CONTROL_FINDING], out)

    def test_import_only_file_is_no_copy(self):
        self.tracked({"CLAUDE.md": "@~/claude-settings-main/CLAUDE.md\n"})
        found, out = self.verdict_scan()
        self.assertEqual(keyed(found), [CONTROL_FINDING], out)

    def test_reflowed_copy_is_reported_inside_its_span(self):
        self.tracked({"agents/reflow.md": "Don't pad a brief: keep it to the task,\nthe files, the governing rulings "
                                          "and the check\nthat proves it done.\n"})
        found, out = self.verdict_scan()
        reflow = [line for path, line, _, _ in found if path == "agents/reflow.md"]
        self.assertEqual(len(reflow), 1, out)
        self.assertIn(reflow[0], (1, 2, 3), out)
        self.assertEqual([p for p, _, _, _ in found if p != "agents/reflow.md"], ["agents/control.md"], out)

    def test_comment_opener_in_a_code_span_before_the_copy_does_not_hide_it(self):
        self.tracked({"agents/opener.md": "Write the `<!--` opener as text. %s\n" % RULE})
        found, out = self.verdict_scan()
        self.assertEqual(keyed(found), sorted([CONTROL_FINDING, ("agents/opener.md", 1, "COPY001")]), out)

    def test_comment_marks_inside_the_copied_sentence_do_not_hide_it(self):
        self.tracked({"agents/marks.md": "%s\n" % MARKS})
        found, out = self.verdict_scan()
        self.assertEqual(keyed(found), sorted([CONTROL_FINDING, ("agents/marks.md", 1, "COPY001")]), out)

    def test_multi_line_code_span_before_the_copy_does_not_hide_it(self):
        self.tracked({"agents/span.md": "Use the form `brief\nspan closes here`, then: %s\n" % RULE})
        found, out = self.verdict_scan()
        span = [line for path, line, _, _ in found if path == "agents/span.md"]
        self.assertEqual(len(span), 1, out)
        self.assertIn(span[0], (1, 2), out)

    def test_a_rule_sentence_quoted_in_a_code_span_is_not_a_source(self):
        self.tracked({"agents/quoted.md": "%s\n" % QUOTED})
        found, out = self.verdict_scan()
        self.assertEqual(keyed(found), [CONTROL_FINDING], out)

    def test_child_exception_covers_its_own_copy_in_its_file(self):
        self.tracked({"agents/own.md": "<!-- exempt: brief-contents reason: %s -->\n%s\n" % (REASON, RULE)})
        found, out = self.verdict_scan()
        self.assertEqual(keyed(found), [CONTROL_FINDING], out)

    def test_exception_with_an_empty_reason_is_refused(self):
        self.tracked({"agents/empty.md": "<!-- exempt: brief-contents reason: -->\nNothing copied here.\n"})
        found, out = self.verdict_scan()
        self.assertIn(("agents/empty.md", 1, "EXEMPT001"), keyed(found), out)

    def test_exception_one_word_under_the_minimum_is_refused(self):
        short = " ".join(["word"] * (REASON_MIN_WORDS - 1))
        self.tracked({"agents/short.md": "<!-- exempt: brief-contents reason: %s -->\nNothing copied here.\n" % short})
        found, out = self.verdict_scan()
        self.assertIn(("agents/short.md", 1, "EXEMPT001"), keyed(found), out)

    def test_exception_at_the_minimum_is_accepted(self):
        exact = " ".join(["word"] * REASON_MIN_WORDS)
        self.tracked({"agents/exact.md": "<!-- exempt: brief-contents reason: %s -->\n%s\n" % (exact, RULE)})
        found, out = self.verdict_scan()
        self.assertEqual(keyed(found), [CONTROL_FINDING], out)

    def test_exception_for_a_rule_the_parent_lacks_is_refused(self):
        self.tracked({"agents/gone.md": "<!-- exempt: no-such-rule reason: %s -->\n%s\n" % (REASON, RULE)})
        found, out = self.verdict_scan()
        self.assertEqual(keyed(found), sorted([CONTROL_FINDING, ("agents/gone.md", 1, "EXEMPT002"),
                                               ("agents/gone.md", 2, "COPY001")]), out)

    def test_exception_with_no_copy_in_its_file_is_refused(self):
        self.tracked({"agents/unused.md": "<!-- exempt: brief-contents reason: %s -->\nNothing copied here.\n" % REASON})
        found, out = self.verdict_scan()
        self.assertIn(("agents/unused.md", 1, "EXEMPT003"), keyed(found), out)

    def test_exception_covers_only_its_own_file_and_rule(self):
        self.tracked({"agents/a.md": "<!-- exempt: brief-contents reason: %s -->\nNothing copied here.\n" % REASON,
                      "agents/b.md": "%s\n" % RULE,
                      "agents/c.md": "<!-- exempt: comment-marks reason: %s -->\n%s\n" % (REASON, RULE)})
        found, out = self.verdict_scan()
        copies = sorted(path for path, _, code, _ in found if code == "COPY001")
        self.assertEqual(copies, ["agents/b.md", "agents/c.md", "agents/control.md"], out)
        self.assertIn(("agents/a.md", 1, "EXEMPT003"), keyed(found), out)

    def test_missing_parent_is_unknown(self):
        self.tracked({}, control=False)
        rc, out = self.scan(parent=os.path.join(self.tmp.name, "nowhere"))
        self.assertEqual(rc, 2, out)
        self.assertIn("unknown", out, out)
        self.assertNotIn("copies:", out, out)

    def test_parent_without_rule_files_is_unknown(self):
        bare = os.path.join(self.tmp.name, "bare-parent")
        os.makedirs(bare)
        self.tracked({"agents/copy.md": "%s\n" % RULE}, control=False)
        rc, out = self.scan(parent=bare)
        self.assertEqual(rc, 2, out)
        self.assertIn("unknown", out, out)
        self.assertNotIn("copies: PASS", out, out)

    def test_child_with_no_markdown_passes(self):
        self.tracked({"src/app.py": "value = 1\n"}, control=False)
        found, out = self.verdict_scan()
        self.assertEqual(found, [], out)

    def test_full_size_child_reports_only_its_copy(self):
        files = {"docs/note%03d.md" % i: "Note %d: the team reviews the lane output each week.\n" % i
                 for i in range(300)}
        files["agents/copy.md"] = "%s\n" % RULE
        self.tracked(files, control=False)
        found, out = self.verdict_scan()
        self.assertEqual(keyed(found), [("agents/copy.md", 1, "COPY001")], out)

    def test_cross_repo_mode_still_reports_a_byte_equal_copy(self):
        # Green control: the existing cross-repo mode reads the same parent and still reports a verbatim copy.
        write(self.child, "vendor/rules.md", PARENT_RULES)
        proc = run(self.parent, self.child, "--json")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        out = json.loads(proc.stdout)
        self.assertIn("vendor/rules.md", [f["child"] for f in out["files"]], proc.stdout)

    def test_one_git_start_one_read_per_markdown_and_no_write(self):
        self.tracked({"docs/a.md": "Plain notes.\n", "agents/copy.md": "%s\n" % RULE})
        write(self.tmp.name, "audit_runner.py", AUDIT_RUNNER)
        scripts = os.path.join(self.tmp.name, "scripts")
        tracked_tree.copy_tracked(scripts, "lint", "hooks")
        module = os.path.join(scripts, "lint", "find_copies.py")
        events_path = os.path.join(self.tmp.name, "events.json")
        before = (sorted(os.walk(self.child)), sorted(os.walk(scripts)))
        env = dict(os.environ, TMPDIR=self.tmp.name)
        env.pop("PYTHONDONTWRITEBYTECODE", None)  # a set variable would hide a .pyc the scan writes
        env.pop("PYTHONPYCACHEPREFIX", None)
        proc = subprocess.run([sys.executable, os.path.join(self.tmp.name, "audit_runner.py"), events_path, module,
                               "--in-repo", "--parent", self.parent],
                              cwd=self.child, env=env, capture_output=True, text=True, timeout=60)
        self.assertIn("copies: FAIL", proc.stdout, proc.stdout + proc.stderr)
        with open(events_path, encoding="utf-8") as f:
            events = json.load(f)
        starts = [e[1] for e in events if e[0] == "proc"]
        self.assertEqual(len(starts), 1, "one git start expected, got %s" % starts)
        self.assertIn("ls-files", starts[0])
        opened = collections.Counter(os.path.realpath(e[1]) for e in events if e[0] == "open")
        for rel in ("docs/a.md", "agents/copy.md"):
            self.assertEqual(opened[os.path.realpath(os.path.join(self.child, rel))], 1, rel)
        writes = [e[1] for e in events if e[0] == "open" and any(c in e[2] for c in "wax+")]
        self.assertEqual(writes, [], "the scan opened a file for writing")
        self.assertEqual((sorted(os.walk(self.child)), sorted(os.walk(scripts))), before)


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        shutil.rmtree(RUN_FOLDER, ignore_errors=True)
