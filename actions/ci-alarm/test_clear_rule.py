#!/usr/bin/env python3
"""clear_rule.clears, called directly: the job-level rules of the failed-run clear (the module docstring of clear_rule.py).

Run: python3 actions/ci-alarm/test_clear_rule.py. Stdlib unittest. Each case builds its workflow text in memory; no file is read or written.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import clear_rule  # noqa: E402  the one home of the failed-run clear, beside this file

PUSH = "push"
RUNS_ON = "runs-on: ubuntu-latest"
STEPS = ["steps:", "  - run: echo ok"]


def job(name, conclusion):
    return {"name": name, "status": "completed", "conclusion": conclusion}


def workflow(*jobs):
    """A workflow file text: a header, then one block per job, given as (key, body lines). Each body line sits four spaces in, under its key."""
    lines = ["name: checks", "on: [push, schedule]", "jobs:"]
    for key, body in jobs:
        lines.append(f"  {key}:")
        lines.extend(f"    {line}" for line in body)
    return "\n".join(lines) + "\n"


def extra_workflow(*body):
    """A workflow text with `checks` and one job `extra`, whose body lines (the job's own if:, name: and comments) come first."""
    return workflow(("checks", [RUNS_ON, *STEPS]), ("extra", [RUNS_ON, *body, *STEPS]))


def runs(extra_name="extra"):
    """The red run and the newer push run as (R, N). The red run is a schedule run that failed on `checks`. The job `extra_name` was skipped
    there, and the newer push run skipped it too."""
    return [job("checks", "failure"), job(extra_name, "skipped")], [job("checks", "success"), job(extra_name, "skipped")]


class ClearRuleJobs(unittest.TestCase):
    R, N = runs()

    def test_a_multi_line_if_whose_continuation_names_the_push_event_keeps_the_job_needed(self):
        # The if: is one plain scalar over two lines, `... == 'pull_request'` then `|| ... == 'push'`, so it may run in a push run and stays
        # needed. Named failure: only the first line is read, so the job reads as pull_request-only and is left out.
        text = workflow(("checks", [RUNS_ON, *STEPS]),
                        ("extra", [RUNS_ON, "if: github.event_name == 'pull_request'", "  || github.event_name == 'push'", *STEPS]))
        self.assertFalse(clear_rule.clears(self.R, self.N, PUSH, text),
                         "a job whose if: may run in a push run must stay needed, so its skip in the push run blocks the clear")

    def test_a_single_line_if_naming_the_other_event_leaves_the_job_out(self):
        # Control for the case above: the same job with a one-line if: names pull_request only, so no push run runs it and the clear goes on.
        text = workflow(("checks", [RUNS_ON, *STEPS]),
                        ("extra", [RUNS_ON, "if: github.event_name == 'pull_request'", *STEPS]))
        self.assertTrue(clear_rule.clears(self.R, self.N, PUSH, text),
                        "a one-line if: that names only pull_request leaves the job out, so the skipped job does not block the clear")

    def test_a_job_name_shared_by_two_jobs_keeps_the_job_needed(self):
        # `pq` has no name:, so its name is its key. `other` is named pq and its if: names pull_request only. The name maps to two jobs,
        # so it maps to no job and pq stays needed. Named failure: a name: match beats a key match, so `other` decides and pq is left out.
        r = [job("checks", "failure"), job("pq", "success")]
        n = [job("checks", "success"), job("pq", "skipped")]
        text = workflow(("checks", [RUNS_ON, *STEPS]),
                        ("pq", [RUNS_ON, *STEPS]),
                        ("other", ["name: pq", RUNS_ON, "if: ${{ github.event_name == 'pull_request' }}", *STEPS]))
        self.assertFalse(clear_rule.clears(r, n, PUSH, text),
                         "an ambiguous job name maps to no job, so the job named pq stays needed and its skip blocks the clear")

    def test_a_job_matched_by_its_own_key_with_an_other_event_if_is_left_out(self):
        # Control for the case above: no other job is named pq, so the key matches the one job, whose if: names pull_request only.
        r = [job("checks", "failure"), job("pq", "success")]
        n = [job("checks", "success"), job("pq", "skipped")]
        text = workflow(("checks", [RUNS_ON, *STEPS]),
                        ("pq", [RUNS_ON, "if: ${{ github.event_name == 'pull_request' }}", *STEPS]))
        self.assertTrue(clear_rule.clears(r, n, PUSH, text),
                        "a key match with a pull_request-only if: leaves the job out, so the skip does not block the clear")


class ClearRuleScanner(unittest.TestCase):
    """The job-level if: and name: reads of clear_rule.parse_jobs, and the rule that uses them. Each case asserts the read first, then the
    rule, so a red names the read that broke."""
    R, N = runs()

    def assert_read(self, text, want_if, want_name=None):
        got = clear_rule.parse_jobs(text)["extra"]
        self.assertEqual(got["if"], want_if, "the job-level if: of extra is read wrong")
        if want_name is not None:
            self.assertEqual(got["name"], want_name, "the name: of extra is read wrong")

    def test_an_opener_inside_a_quoted_string_does_not_cut_a_real_pull_request_test(self):
        # `#`, `//` and `/*` sit inside quotes. The if: is one && chain with a real pull_request test, so the job is left out.
        # Named failure: a comment cut at the opener truncates the if:, the read fails, and the job reads as needed.
        for opener in ("#", "//", "/*"):
            with self.subTest(opener=opener):
                want = f"github.head_ref != 'a {opener} b' && github.event_name == 'pull_request'"
                text = extra_workflow(f"if: {want}")
                self.assert_read(text, want)
                self.assertTrue(clear_rule.clears(self.R, self.N, PUSH, text),
                                "a real && pull_request test leaves the job out, so its skip in the push run does not block the clear")

    def test_an_opener_inside_a_quoted_string_keeps_the_job_when_a_real_or_follows(self):
        # The || after the quoted opener is a real OR, so the job may run in a push run and stays needed.
        # Named failure: a comment cut at the opener truncates the if:, the read fails, and the || is lost.
        for opener in ("#", "//", "/*"):
            with self.subTest(opener=opener):
                want = f"github.event_name == 'pull_request' && github.head_ref != 'a {opener} b' || github.event_name == 'push'"
                text = extra_workflow(f"if: {want}")
                self.assert_read(text, want)
                self.assertFalse(clear_rule.clears(self.R, self.N, PUSH, text),
                                 "a real || means the job may run in a push run, so it stays needed and its skip blocks the clear")

    def test_an_event_test_inside_a_quoted_literal_is_not_the_test(self):
        # The literal reads `github.event_name == 'pull_request'` but is only text inside a string, so the if: has no test and the job is kept.
        # Named failure: an event test searched for anywhere in the if: finds the literal, so the job is left out.
        for want in ("github.head_ref == 'github.event_name == ''pull_request'''",
                     "github.head_ref == 'x && github.event_name == ''pull_request'''"):
            with self.subTest(want=want):
                text = extra_workflow(f"if: {want}")
                self.assert_read(text, want)
                self.assertFalse(clear_rule.clears(self.R, self.N, PUSH, text),
                                 "an event test inside a quoted literal is not a test, so the job stays needed")

    def test_a_real_pull_request_test_beside_a_quoted_push_literal_leaves_the_job_out(self):
        # Control for the case above: the real pull_request test leaves the job out, whatever the literal says.
        want = "github.event_name == 'pull_request' && github.head_ref == 'github.event_name == ''push'''"
        text = extra_workflow(f"if: {want}")
        self.assert_read(text, want)
        self.assertTrue(clear_rule.clears(self.R, self.N, PUSH, text),
                        "a real && pull_request test leaves the job out, so its skip in the push run does not block the clear")

    def test_a_lone_quote_in_a_name_maps_the_job_and_leaves_it_out_on_its_test(self):
        # `Don't` is the job's name:, and its if: names pull_request only, so the job maps by name and is left out.
        # Named failure: a name with an unbalanced quote reads as no name, the job maps to nothing, and it stays needed.
        R, N = runs("Don't")
        want = "github.event_name == 'pull_request'"
        text = extra_workflow("name: Don't", f"if: {want}")
        self.assert_read(text, want, want_name="Don't")
        self.assertTrue(clear_rule.clears(R, N, PUSH, text),
                        "a job named Don't with a pull_request-only if: is left out, so its skip does not block the clear")

    def test_a_lone_quote_in_a_name_keeps_the_job_when_its_if_has_a_real_or(self):
        R, N = runs("Don't")
        want = "github.event_name == 'pull_request' || github.event_name == 'push'"
        text = extra_workflow("name: Don't", f"if: {want}")
        self.assert_read(text, want, want_name="Don't")
        self.assertFalse(clear_rule.clears(R, N, PUSH, text),
                         "a real || means the job may run in a push run, so it stays needed and its skip blocks the clear")

    def test_a_lone_quote_in_plain_text_does_not_change_the_if_read(self):
        # A comment line and a trailing comment, each with a lone quote, around a pull_request-only if:. Both are text, so the if: reads as the test.
        # Named failure: a comment read as part of the if: makes it unreadable, so the job stays needed.
        want = "github.event_name == 'pull_request'"
        for body in (["# Don't run this on push", f"if: {want}"],
                     [f"if: {want} # Don't"]):
            with self.subTest(body=body[-1]):
                text = extra_workflow(*body)
                self.assert_read(text, want)
                self.assertTrue(clear_rule.clears(self.R, self.N, PUSH, text),
                                "a pull_request-only if: leaves the job out, so its skip does not block the clear")

    def test_a_block_scalar_if_whose_lines_join_to_a_real_or_keeps_the_job(self):
        # `>-` folds the body lines into one expression, so the || on the second line is a real OR and the job stays needed.
        # Named failure: only the first body line is read, so the job reads as pull_request-only and is left out.
        want = "github.event_name == 'pull_request' || github.event_name == 'push'"
        text = extra_workflow("if: >-", "  github.event_name == 'pull_request'", "  || github.event_name == 'push'")
        self.assert_read(text, want)
        self.assertFalse(clear_rule.clears(self.R, self.N, PUSH, text),
                         "a real || means the job may run in a push run, so it stays needed and its skip blocks the clear")

    def test_a_block_scalar_if_whose_pull_request_test_is_on_a_later_line_leaves_the_job_out(self):
        # The real pull_request test is the second line's && conjunct, so the job is left out.
        # Named failure: only the first body line is read, so the test is missed and the job stays needed.
        want = "github.ref != 'x' && github.event_name == 'pull_request'"
        text = extra_workflow("if: >-", "  github.ref != 'x'", "  && github.event_name == 'pull_request'")
        self.assert_read(text, want)
        self.assertTrue(clear_rule.clears(self.R, self.N, PUSH, text),
                        "a real && pull_request test leaves the job out, so its skip in the push run does not block the clear")

    def test_a_block_scalar_keeps_a_quoted_opener_before_a_real_or(self):
        # In a block scalar `#` is text, and the || after the quoted opener is a real OR, so the job stays needed.
        # Named failure: only the first body line is read, so the || is missed and the job reads as pull_request-only.
        want = "github.event_name == 'pull_request' && github.head_ref != ' #' || github.event_name == 'push'"
        text = extra_workflow("if: >-", "  github.event_name == 'pull_request' && github.head_ref != ' #'", "  || github.event_name == 'push'")
        self.assert_read(text, want)
        self.assertFalse(clear_rule.clears(self.R, self.N, PUSH, text),
                         "a real || means the job may run in a push run, so it stays needed and its skip blocks the clear")


if __name__ == "__main__":
    unittest.main()
