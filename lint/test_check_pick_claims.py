#!/usr/bin/env python3
"""Cases for lint/check_pick_claims.py. Run: python3 lint/test_check_pick_claims.py

A step note that says "Owner picked X on item N" claims what the page recorded. The check reads the answers
file that a session wrote from the page, and never a git copy of the page: the page is the one store. Each case
builds its fixtures in its own folder under this run's temp root (lint/_test_temp.py). No case waits on a clock.

CHECK_PICK_CLAIMS_UNDER_TEST overrides the module path. A red run on a commit before the check exists points it at
lint/pick_claims_stub_test.py, so each case fails on its own assertion and not on a missing name.
"""
import atexit
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per run (lint/_test_temp.py)

RUN = os.path.realpath(_test_temp.run_folder())
atexit.register(shutil.rmtree, RUN, True)
MODULE = os.path.abspath(os.environ.get("CHECK_PICK_CLAIMS_UNDER_TEST") or os.path.join(HERE, "check_pick_claims.py"))
_SPEC = importlib.util.spec_from_file_location("check_pick_claims_under_test", MODULE)
D = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(D)  # the module under test

READ = "2026-11-12T14:57:00-06:00"  # the answers file's read time: an ISO time with an offset
NOTE_SLUG = "step-restated-pick"
# Terms that name the git copy of the page or a roadmap branch ref. The check reads none of them.
FORBIDDEN = ("waiting/answers", "waiting/items", "origin/roadmap", "refs/heads/roadmap", "refs/remotes/origin/roadmap", "roadmap:")


def put(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def git_copy_mentions(text):
    """(line number, term) for each forbidden term that a line of `text` holds."""
    return [(n, term) for n, line in enumerate(text.splitlines(), 1) for term in FORBIDDEN if term in line]


class Claims(unittest.TestCase):
    def test_picked_key_on_item(self):
        self.assertEqual(D.claims("Owner picked b on item 279."), [(279, "b")], "the 'picked KEY on item N' form is not read")

    def test_picked_key_on_page_item(self):
        self.assertEqual(D.claims("Owner picked a on page item 381"), [(381, "a")], "the 'picked KEY on page item N' form is not read")

    def test_picked_number_then_key(self):
        self.assertEqual(D.claims("Owner picked 447 a on the page"), [(447, "a")], "the 'picked N KEY on the page' form is not read")

    def test_time_in_parentheses_is_no_claim(self):
        self.assertEqual(D.claims("Owner picked 466 a (19:22 CST Nov 9)"), [(466, "a")], "a time or date in parentheses is read as a claim")

    def test_quoted_label_between_key_and_item(self):
        self.assertEqual(D.claims('Owner picked b "refuter" on item 282'), [(282, "b")], "a quoted label between the key and the item breaks the claim")

    def test_the_owner_form(self):
        self.assertEqual(D.claims("The owner picked b on item 279"), [(279, "b")], "the 'The owner picked' form is not read")

    def test_match_ignores_case(self):
        self.assertEqual(D.claims("OWNER PICKED b ON ITEM 279"), [(279, "b")], "the claim match is case-sensitive")

    def test_pick_with_no_item_number_is_no_claim(self):
        self.assertEqual(D.claims("Owner picked the widening option"), [], "a pick with no item number is read as a claim")

    def test_until_item_picks_is_no_claim(self):
        self.assertEqual(D.claims("Wait until item 282 picks the word"), [], "'until item N picks' is read as a claim")


class Case(unittest.TestCase):
    """Fixtures in one folder per case: a steps folder of step json, and an answers file that a case may leave out."""

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="case-", dir=RUN)
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.steps_dir = os.path.join(self.folder, "steps")
        self.answers = os.path.join(self.folder, "answers.json")
        os.makedirs(self.steps_dir)

    def steps(self, notes):
        """One step json per slug, {slug: note}. A None note writes a step with no note key."""
        for slug, note in notes.items():
            doc = {"title": "A step"} if note is None else {"title": "A step", "note": note}
            put(os.path.join(self.steps_dir, slug + ".json"), json.dumps(doc))

    def page(self, answers, read=READ):
        """The answers file a session writes from the page. A None read time leaves the key out."""
        doc = {"answers": answers} if read is None else {"read": read, "answers": answers}
        put(self.answers, json.dumps(doc))

    def check(self):
        return D.check(self.steps_dir, self.answers)

    def cli(self):
        return subprocess.run([sys.executable, MODULE, "--steps", self.steps_dir, "--answers", self.answers],
                              cwd=self.folder, capture_output=True, text=True)

    def only(self, findings, what):
        """The one finding that `what` expects. The count is asserted first, then its fields (test-practices P7)."""
        self.assertEqual(len(findings), 1, "%s: expected one finding, got %r" % (what, findings))
        return findings[0]


class Findings(Case):
    def test_matching_pick_is_no_finding(self):
        self.steps({NOTE_SLUG: "Owner picked a on item 279."})
        self.page({"279": "a"})
        self.assertEqual(self.check(), [], "a claim that matches the page's recorded choice is flagged")

    def test_mismatch_carries_the_claim_and_the_page_choice(self):
        self.steps({NOTE_SLUG: "Owner picked a on item 279."})
        self.page({"279": "c"})
        f = self.only(self.check(), "a mismatch")
        self.assertEqual((f.kind, f.slug, f.item, f.key, f.page), ("mismatch", NOTE_SLUG, 279, "a", "c"),
                         "a page choice that differs from the claim is not a mismatch finding with its fields")

    def test_item_absent_from_answers_is_unrecorded(self):
        self.steps({NOTE_SLUG: "Owner picked a on item 279."})
        self.page({})
        f = self.only(self.check(), "an absent item")
        self.assertEqual((f.kind, f.slug, f.item, f.key, f.page), ("unrecorded", NOTE_SLUG, 279, "a", None),
                         "an item the answers file lacks is not an unrecorded finding")

    def test_item_recorded_as_null_is_unrecorded(self):
        self.steps({NOTE_SLUG: "Owner picked a on item 279."})
        self.page({"279": None})
        f = self.only(self.check(), "a null item")
        self.assertEqual((f.kind, f.slug, f.item, f.key, f.page), ("unrecorded", NOTE_SLUG, 279, "a", None),
                         "an item recorded as null is not an unrecorded finding")

    def test_same_item_claimed_twice_flags_only_the_wrong_claim(self):
        self.steps({"step-first": "Owner picked a on item 279.", "step-second": "Owner picked b on item 279."})
        self.page({"279": "a"})
        f = self.only(self.check(), "the same item claimed twice")
        self.assertEqual((f.kind, f.slug, f.item, f.key, f.page), ("mismatch", "step-second", 279, "b", "a"),
                         "the wrong one of two claims on one item is not the one flagged")

    def test_step_with_no_note_adds_no_claim(self):
        self.steps({"step-empty": None, NOTE_SLUG: "Owner picked a on item 279."})
        self.page({"279": "c"})
        f = self.only(self.check(), "a step with no note beside a wrong claim")
        self.assertEqual(f.slug, NOTE_SLUG, "the step with no note is flagged, or the wrong step is")

    def test_empty_roadmap_and_empty_answers_are_clean(self):
        self.page({})
        self.assertEqual(self.check(), [], "an empty roadmap with an empty answers file is flagged")

    def test_full_roadmap_flags_only_the_one_wrong_pick(self):
        self.steps({"step-%03d" % n: "Owner picked a on item %d." % (300 + n) for n in range(150)})
        self.page({str(300 + n): ("c" if n == 77 else "a") for n in range(150)})
        f = self.only(self.check(), "one wrong pick in a full roadmap")
        self.assertEqual((f.kind, f.slug, f.item, f.key, f.page), ("mismatch", "step-077", 377, "a", "c"),
                         "a full roadmap does not flag its one wrong pick")


class UnknownCauses(Case):
    def assert_unknown(self, what):
        r = self.cli()
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 2, "%s: exit %d, not 2 for an unknown read" % (what, r.returncode))
        self.assertIn("unknown", out.lower(), "%s: the output does not say unknown" % what)

    def test_missing_answers_file_is_unknown(self):
        self.steps({NOTE_SLUG: "Owner picked a on item 279."})
        self.assert_unknown("a missing answers file")

    def test_answers_not_json_is_unknown(self):
        self.steps({NOTE_SLUG: "Owner picked a on item 279."})
        put(self.answers, "{not json")
        self.assert_unknown("an answers file that is not JSON")

    def test_answers_without_read_time_is_unknown(self):
        self.steps({NOTE_SLUG: "Owner picked a on item 279."})
        self.page({"279": "a"}, read=None)
        self.assert_unknown("an answers file with no read time")

    def test_answers_not_an_object_is_unknown(self):
        self.steps({NOTE_SLUG: "Owner picked a on item 279."})
        put(self.answers, json.dumps({"read": READ, "answers": ["279"]}))
        self.assert_unknown("an answers value that is not an object")


class Cli(Case):
    def test_clean_check_exits_0(self):
        self.steps({NOTE_SLUG: "Owner picked a on item 279."})
        self.page({"279": "a"})
        r = self.cli()
        self.assertEqual(r.returncode, 0, "a clean check does not exit 0: %r" % (r.stdout + r.stderr))

    def test_mismatch_exits_1_and_names_the_step_claim_and_page_choice(self):
        self.steps({NOTE_SLUG: "Owner picked a on item 279."})
        self.page({"279": "c"})
        r = self.cli()
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 1, "a mismatch does not exit 1, got %d" % r.returncode)
        self.assertIn(NOTE_SLUG, out, "the finding output does not name the step")
        self.assertIn("Owner picked a on item 279", out, "the finding output does not quote the claim")
        self.assertRegex(out, r"(?<![A-Za-z0-9])c(?![A-Za-z0-9])", "the finding output does not name the page's choice")

    def test_unrecorded_claim_exits_1(self):
        self.steps({NOTE_SLUG: "Owner picked a on item 279."})
        self.page({})
        r = self.cli()
        self.assertEqual(r.returncode, 1, "an unrecorded claim does not exit 1, got %d" % r.returncode)


class NoGitCopy(unittest.TestCase):
    def test_check_source_names_no_git_copy_of_the_page(self):
        with open(MODULE, encoding="utf-8") as f:
            text = f.read()
        self.assertEqual(git_copy_mentions(text), [],
                         "the check's source names a git copy of the page or a roadmap ref; the answers file is the one input")

    def test_scanner_finds_a_term_after_a_comment_opener_in_a_string(self):
        self.assertEqual(git_copy_mentions('x = "# /* // waiting/answers"\n'), [(1, "waiting/answers")],
                         "the scanner misses a forbidden term that follows a comment opener inside a string")

    def test_scanner_finds_a_term_in_a_multi_line_string(self):
        text = 'DOC = """\nfirst line\nread origin/roadmap here\n"""\n'
        self.assertEqual(git_copy_mentions(text), [(3, "origin/roadmap")],
                         "the scanner misses a forbidden term inside a multi-line string")

    def test_scanner_reads_past_a_lone_quote_in_text(self):
        self.assertEqual(git_copy_mentions("# Don't read waiting/items\n"), [(1, "waiting/items")],
                         "the scanner misses a forbidden term after a lone quote")

    def test_scanner_passes_clean_text_with_quotes_and_openers(self):
        self.assertEqual(git_copy_mentions('# Don\'t use a git copy\nx = "# /* //"\n'), [],
                         "the scanner flags clean text that holds quotes and comment openers")


if __name__ == "__main__":
    unittest.main()
