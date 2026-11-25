#!/usr/bin/env python3
"""clear_rule.clears, called directly: the job-level rules of the failed-run clear (the module docstring of clear_rule.py).

Run: python3 actions/ci-alarm/test_clear_rule.py. Stdlib unittest. Each case builds its workflow text in memory; no file is read or written.
"""
import contextlib
import json
import os
import pathlib
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import clear_rule  # noqa: E402  the one home of the failed-run clear, beside this file
sys.path.insert(0, os.path.join(HERE, "..", "..", "merge"))
import merge  # noqa: E402  the merge tool's Host: RedMainJudge checks the home against its real base_state

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

    def test_a_pull_request_test_in_a_parenthesized_and_group_leaves_the_job_out(self):
        # `(A && github.event_name == 'pull_request')` is a conjunct of the whole if:, so the job runs only in a pull_request run.
        # Named failure: the group reads as one opaque conjunct, so the job stays needed and the push run's skip blocks the clear.
        want = "(!cancelled() && github.event_name == 'pull_request') && github.head_ref != 'x'"
        text = extra_workflow(f"if: {want}")
        self.assert_read(text, want)
        self.assertTrue(clear_rule.clears(self.R, self.N, PUSH, text),
                        "a pull_request test inside a parenthesized && group is a conjunct of the whole, so the job is left out and the push run clears")

    def test_an_or_inside_a_parenthesized_group_keeps_the_job_needed(self):
        # `(A || github.event_name == 'pull_request')` may be true in a push run, so the job stays needed and its skip blocks the clear.
        # Named failure: a fix that reads each event test inside a group as a conjunct, whatever the operator, leaves the job out.
        want = "(!cancelled() || github.event_name == 'pull_request') && github.head_ref != 'x'"
        text = extra_workflow(f"if: {want}")
        self.assert_read(text, want)
        self.assertFalse(clear_rule.clears(self.R, self.N, PUSH, text),
                         "an || inside a parenthesized group may run in a push run, so the job stays needed and its skip blocks the clear")


class ClearRuleNightly(unittest.TestCase):
    """R61 part 3: how a skipped nightly is classified. Controls: each holds on the rule as it stands, since a job whose `!=`
    if can run in the newer run is kept needed, and its skip there blocks the clear. They pin the classification the gate
    relies on: a skipped nightly never supersedes a red one."""
    MAC_IF = "if: ${{ github.event_name != 'push' }}"
    SKIP_IF = "if: ${{ github.event_name == 'schedule' }}"

    def test_a_skipped_nightly_behind_a_green_skip_does_not_clear_a_red_macos_nightly(self):
        # The red nightly failed checks-macos. The newer scheduled run's gate read skip: its checks-macos and checks were skipped,
        # and only the gate passed. Named failure: the skipped jobs read as passed, and the skipped run clears the red one.
        r = [job("checks-macos", "failure"), job("nightly-skip", "success"), job("checks", "success")]
        n = [job("nightly-skip", "success"), job("checks-macos", "skipped"), job("checks", "skipped")]
        text = workflow(("nightly-skip", ["runs-on: ubuntu-latest", self.SKIP_IF, *STEPS]),
                        ("checks", [RUNS_ON, *STEPS]),
                        ("checks-macos", ["runs-on: macos-latest", self.MAC_IF, *STEPS]))
        self.assertFalse(clear_rule.clears(r, n, "schedule", text),
                         "a skipped nightly cleared a red macOS nightly: its skipped jobs must not read as passed")

    def test_a_green_push_run_with_the_macos_job_skipped_does_not_clear_a_red_macos_nightly(self):
        # The push run skips checks-macos at job level (its != 'push' if). That job may run in a PR or a schedule run, so it stays
        # needed here, and its skip in the push run blocks the clear. Named failure: the push guard leaves the job out.
        r = [job("checks-macos", "failure"), job("checks", "success")]
        n = [job("checks", "success"), job("checks-macos", "skipped")]
        text = workflow(("checks", [RUNS_ON, *STEPS]), ("checks-macos", ["runs-on: macos-latest", self.MAC_IF, *STEPS]))
        self.assertFalse(clear_rule.clears(r, n, PUSH, text),
                         "a green push run cleared a red macOS nightly: the != push job was left out, so its skip read as passed")

    def test_a_push_run_whose_only_running_job_is_push_skip_does_not_clear_a_red_macos_nightly(self):
        # The red nightly failed checks-macos. The newer push run's push-skip job said skip, so push-skip is the one job that ran,
        # and it passed; checks-macos, checks and nightly-skip were skipped. The run reads green, but the red job did not pass.
        # Named failure: the green push-skip job reads as a passed run, and the push run clears the red nightly.
        push_skip_if = "if: ${{ github.event_name == 'push' }}"
        r = [job("checks-macos", "failure"), job("checks", "success"), job("nightly-skip", "success")]
        n = [job("push-skip", "success"), job("checks-macos", "skipped"), job("checks", "skipped"), job("nightly-skip", "skipped")]
        text = workflow(("nightly-skip", ["runs-on: ubuntu-latest", self.SKIP_IF, *STEPS]),
                        ("push-skip", ["runs-on: ubuntu-latest", push_skip_if, *STEPS]),
                        ("checks", [RUNS_ON, *STEPS]),
                        ("checks-macos", ["runs-on: macos-latest", self.MAC_IF, *STEPS]))
        self.assertFalse(clear_rule.clears(r, n, PUSH, text),
                         "a push run with only push-skip running cleared a red macOS nightly: the skipped red job read as passed")


class DailyRedClear(unittest.TestCase):
    """Owner page item 880 (11:53 CST Nov 15): a push starts no Windows or mutation job, since their job-level if is
    `github.event_name != 'push'`, and the daily scheduled run runs them. A red daily is cleared only by a run that passed every such
    job. A green dispatch run does. A Linux-only push run does not, and neither does a push run whose suite jobs were all skipped.
    The rule is unchanged (clear_rule.py is the one home), so these cases hold on the rule as it stands and pin the new job shape."""
    DAILY_IF = "if: ${{ github.event_name != 'push' }}"  # the job-level if of a Windows or mutation job from item 880
    TEXT = workflow(("checks", [RUNS_ON, *STEPS]),
                    ("checks-windows-merge-3", ["runs-on: windows-latest", DAILY_IF, *STEPS]),
                    ("checks-mutate-guard", ["runs-on: ubuntu-latest", DAILY_IF, *STEPS]))
    R = [job("checks", "success"), job("checks-windows-merge-3", "failure"), job("checks-mutate-guard", "success")]

    def test_a_linux_only_green_push_run_does_not_clear_a_red_daily(self):
        # Named failure: the != push Windows job is left out of the push run's need, so its skip there reads as passed.
        n = [job("checks", "success"), job("checks-windows-merge-3", "skipped"), job("checks-mutate-guard", "skipped")]
        self.assertFalse(clear_rule.clears(self.R, n, PUSH, self.TEXT),
                         "a Linux-only green push run cleared a red daily: its skipped Windows job read as passed")

    def test_a_linux_only_green_push_run_does_not_clear_a_red_mutation_job(self):
        # Named failure: the != push mutation job is left out of the push run's need, so its skip there reads as passed.
        r = [job("checks", "success"), job("checks-windows-merge-3", "success"), job("checks-mutate-guard", "failure")]
        n = [job("checks", "success"), job("checks-windows-merge-3", "skipped"), job("checks-mutate-guard", "skipped")]
        self.assertFalse(clear_rule.clears(r, n, PUSH, self.TEXT),
                         "a Linux-only green push run cleared a red mutation job: its skipped mutation job read as passed")

    def test_a_proven_push_run_with_every_suite_job_skipped_does_not_clear_a_red_daily(self):
        # Named failure: push-skip and scope read as the verdict, and the skipped suite jobs read as passed.
        n = [job("push-skip", "success"), job("scope", "skipped"), job("checks", "skipped"),
             job("checks-windows-merge-3", "skipped"), job("checks-mutate-guard", "skipped")]
        self.assertFalse(clear_rule.clears(self.R, n, PUSH, self.TEXT),
                         "a proven push run with its suite jobs skipped cleared a red daily: skipped is no pass")

    def test_a_green_push_run_that_skips_the_windows_and_mutation_jobs_does_not_clear_a_linux_red_daily(self):
        # The red job is a Linux job, so step one (red_stays) finds nothing: the rule reads the workflow and decides. The Windows and
        # mutation jobs are not red in the daily, and their != push guard keeps them needed, so the push run's skip of them blocks the clear.
        # Named failure: a rule that leaves a != push job out of the need reads the skip as passed, and the Linux-only push run clears the daily.
        r = [job("checks", "failure"), job("checks-windows-merge-3", "success"), job("checks-mutate-guard", "success")]
        n = [job("checks", "success"), job("checks-windows-merge-3", "skipped"), job("checks-mutate-guard", "skipped")]
        self.assertFalse(clear_rule.clears(r, n, PUSH, self.TEXT),
                         "a Linux-only green push run cleared a red Linux job of the daily: its skipped != push jobs were left out of the need")

    def test_a_green_dispatch_run_with_every_job_of_the_daily_clears_it(self):
        # Control: a dispatch runs every job, so every job the daily needed passed in it, and the red daily is lifted.
        n = [job("checks", "success"), job("checks-windows-merge-3", "success"), job("checks-mutate-guard", "success")]
        self.assertTrue(clear_rule.clears(self.R, n, "workflow_dispatch", self.TEXT),
                        "a green dispatch run with every job of the red daily passed did not clear it")


class EmptyRun(unittest.TestCase):
    """clear_rule.empty_without_evidence: a green run of the push group that ran no suite job and carries no evidence is no verdict."""
    EMPTY = [job("push-skip", "success"), job("scope", "success"), job("checks", "skipped"), job("checks-macos", "skipped")]
    EVIDENCE = [job("push-skip", "success"), job("scope", "skipped"), job("checks", "skipped"), job("checks-macos", "skipped")]

    def test_a_push_run_with_every_suite_job_skipped_and_scope_run_is_empty(self):
        self.assertTrue(clear_rule.empty_without_evidence(self.EMPTY, PUSH))

    def test_a_push_run_whose_push_skip_succeeded_and_scope_was_skipped_carries_evidence(self):
        self.assertFalse(clear_rule.empty_without_evidence(self.EVIDENCE, PUSH))

    def test_a_dispatch_run_never_carries_evidence_even_with_jobs_shaped_like_it(self):
        self.assertTrue(clear_rule.empty_without_evidence(self.EVIDENCE, "workflow_dispatch"))

    def test_a_dispatch_run_with_no_suite_job_is_empty(self):
        self.assertTrue(clear_rule.empty_without_evidence([job("scope", "success"), job("checks", "skipped")], "workflow_dispatch"))

    def test_one_suite_job_that_succeeded_makes_the_run_not_empty(self):
        self.assertFalse(clear_rule.empty_without_evidence([*self.EMPTY[:3], job("checks-macos", "success")], PUSH))

    def test_a_matrix_job_that_succeeded_makes_the_run_not_empty(self):
        self.assertFalse(clear_rule.empty_without_evidence([*self.EMPTY, job("checks-windows (shard 1)", "success")], PUSH))

    def test_a_suite_job_that_was_cancelled_or_is_still_going_is_not_a_suite_that_ran(self):
        self.assertTrue(clear_rule.empty_without_evidence([*self.EMPTY[:2], job("checks", "cancelled")], PUSH))
        self.assertTrue(clear_rule.empty_without_evidence([*self.EMPTY[:2], {"name": "checks", "status": "in_progress", "conclusion": None}], PUSH))

    def test_the_nightly_skip_job_is_bookkeeping_and_makes_no_suite_that_ran(self):
        # nightly-skip has no job-level if, so it concludes success on every push run of checks.yml.
        # Named failure: it reads as a suite job that succeeded, and an empty push run reads as a verdict.
        shape = [job("nightly-skip", "success"), job("push-skip", "success"), job("scope", "success"), job("checks", "skipped")]
        self.assertTrue(clear_rule.empty_without_evidence(shape, PUSH))

    def test_a_push_skip_that_ran_with_scope_success_has_no_evidence(self):
        self.assertTrue(clear_rule.empty_without_evidence([job("push-skip", "success"), job("scope", "success")], PUSH))

    def test_a_scope_skipped_with_no_push_skip_job_has_no_evidence(self):
        self.assertTrue(clear_rule.empty_without_evidence([job("scope", "skipped"), job("checks", "skipped")], PUSH))

    def test_a_push_skip_that_failed_is_no_evidence(self):
        self.assertTrue(clear_rule.empty_without_evidence([job("push-skip", "failure"), job("scope", "skipped")], PUSH))

    def test_a_run_with_no_jobs_is_empty_without_evidence(self):
        self.assertTrue(clear_rule.empty_without_evidence([], PUSH))

    def test_the_bookkeeping_names_are_exact_not_prefixes(self):
        self.assertFalse(clear_rule.empty_without_evidence([*self.EMPTY[:2], job("scope-check", "success")], PUSH))

    def test_the_rule_judges_the_push_group_of_events_json_and_not_the_schedule(self):
        with open(clear_rule.EVENTS_FILE, encoding="utf-8") as f:
            events = json.load(f)
        self.assertEqual(clear_rule.rule_events(), sorted(e for e, g in events.items() if g == events["push"]))
        self.assertNotIn("schedule", clear_rule.rule_events())


WF_CHECKS = ".github/workflows/checks.yml"
WF_LINKS = ".github/workflows/links.yml"
FLOWS = {WF_CHECKS, WF_LINKS}
CHECKS_TEXT = workflow(("checks", [RUNS_ON, *STEPS]))  # the file at every head: no job has an if:, so no job of a red run is left out
TIME_FMT = "%Y-%m-%dT%H:%M:%SZ"
START = datetime(2026, 11, 24, 10, 0, tzinfo=timezone.utc)  # a fixed start: a job's minutes come from its rows, never from the clock


def page_run(rid, conclusion, event=PUSH, name="checks", path=WF_CHECKS, status="completed", attempt=1):
    """A run as the runs API lists it. Its head is its id as 40 hex digits, so each run has its own commit."""
    return {"id": rid, "name": name, "path": path, "event": event, "status": status, "conclusion": conclusion,
            "run_attempt": attempt, "head_sha": f"{rid:040x}", "html_url": f"https://example.invalid/runs/{rid}"}


def job_row(name, conclusion, status="completed", minutes=None):
    """A job as the jobs API lists it. `minutes` sets its start and end, the two times a cap is judged on."""
    row = {"name": name, "status": status, "conclusion": conclusion, "html_url": f"https://example.invalid/jobs/{name}"}
    if minutes is not None:
        row["started_at"] = START.strftime(TIME_FMT)
        row["completed_at"] = (START + timedelta(minutes=minutes)).strftime(TIME_FMT)
    return row


@contextlib.contextmanager
def caps_read_as(caps):
    """Host.buckets reads each job's cap from the checkout's workflow files. Here the checkout's caps are `caps`, the same dict the home takes."""
    with mock.patch.object(merge, "workflow_dir", return_value=pathlib.Path(HERE)), mock.patch.object(merge, "job_caps", return_value=caps):
        yield


class ScriptedHost(merge.Host):
    """The real Host.base_state and Host.red_jobs over scripted REST: `page` is the runs list the API returns, `jobs` maps a run id to its job rows,
    and every workflow file reads as CHECKS_TEXT. Nothing is fetched."""
    def __init__(self, page, jobs):
        self.required, self.ignore, self.cwd, self.warned = "protection", {}, HERE, set()
        self.base_facts = None
        self.page, self.jobs = page, jobs

    def api(self, rel, *extra, method="GET", fields=None, **kw):
        if rel == "actions/runs":
            return 0, json.dumps({"workflow_runs": self.page})
        if rel.startswith("contents/"):
            return 0, CHECKS_TEXT
        raise AssertionError(f"the scripted host has no read for {rel}")

    def pages(self, rel, key=None, fields=None, **kw):
        return self.jobs[int(rel.split("/")[2])]


def base_judgment(page, jobs, caps=None):
    """base_state's verdict and red runs on a scripted host: (verdict, [(run id, red job names)]). This is the oracle the home is checked against."""
    host = ScriptedHost(page, jobs)
    with caps_read_as(caps or {}):
        verdict, _detail = host.base_state("main", FLOWS)
    facts = host.base_facts or {"red_ids": [], "red_jobs": []}
    return verdict, [(rid, list(names)) for rid, names in zip(facts["red_ids"], facts["red_jobs"])]


class RedMainJudge(unittest.TestCase):
    """The red-main judgment moves from merge.py base_state into clear_rule.judge_main (decision no-merge-onto-red-main). Each case runs one page
    through base_state on the real Host (ScriptedHost) and through the home; the verdict and the red runs must agree. A missing home is an
    assert, so each case is red on the old code for the one cause: there is no home yet."""

    def judge_home(self):
        judge = getattr(clear_rule, "judge_main", None)
        self.assertTrue(callable(judge), "clear_rule has no judge_main: base_state still judges main in merge.py")
        return judge

    def judge_fixed(self, page, jobs, caps=None):
        """The home's (verdict, [(run id, red job names)]) for a page, read from clear_rule alone. The fixed cases pin their answer by hand, never base_state."""
        verdict, red = self.judge_home()(page, FLOWS, set(), caps or {}, lambda r: jobs.get(r["id"]), lambda r: CHECKS_TEXT)
        return verdict, [(rid, list(names)) for rid, names in red]

    def assert_same_judgment(self, page, jobs, caps=None):
        judge = self.judge_home()
        verdict, red = judge(page, FLOWS, set(), caps or {}, lambda r: jobs.get(r["id"]), lambda r: CHECKS_TEXT)
        self.assertEqual((verdict, [(rid, list(names)) for rid, names in red]), base_judgment(page, jobs, caps),
                         "judge_main gives a different verdict or red runs than base_state on the same page")

    def test_a_newest_completed_run_that_passed_judges_as_base_state_does(self):
        self.assert_same_judgment([page_run(2, "success")], {2: [job_row("scope", "success"), job_row("checks", "success")]})

    def test_a_red_job_in_the_newest_run_judges_as_base_state_does(self):
        self.assert_same_judgment([page_run(2, "failure")], {2: [job_row("scope", "success"), job_row("checks", "failure")]})

    def test_a_failed_run_with_no_red_job_judges_as_base_state_does(self):
        self.assert_same_judgment([page_run(2, "failure")], {2: [job_row("scope", "success")]})

    def test_an_unfinished_first_attempt_is_passed_over_for_the_older_run(self):
        self.assert_same_judgment([page_run(3, None, status="in_progress"), page_run(2, "success")],
                                  {3: [job_row("checks", None, status="in_progress")], 2: [job_row("checks", "success")]})

    def test_a_re_run_in_flight_judges_as_base_state_does(self):
        self.assert_same_judgment([page_run(3, None, status="in_progress", attempt=2), page_run(2, "success")],
                                  {3: [job_row("checks", None, status="in_progress")], 2: [job_row("checks", "success")]})

    def test_a_cancelled_run_with_no_red_job_judges_as_base_state_does(self):
        self.assert_same_judgment([page_run(3, "cancelled"), page_run(2, "success")],
                                  {3: [job_row("scope", "success"), job_row("checks", "cancelled")],
                                   2: [job_row("scope", "success"), job_row("checks", "success")]})

    def test_a_cancelled_run_cleared_by_a_newer_run_of_another_group_judges_as_base_state_does(self):
        self.assert_same_judgment([page_run(4, "success", event="schedule"), page_run(3, "cancelled")],
                                  {4: [job_row("scope", "success"), job_row("checks", "success")],
                                   3: [job_row("scope", "success"), job_row("checks", "cancelled")]})

    def test_an_empty_push_run_is_passed_over_for_the_older_red_run(self):
        self.assert_same_judgment([page_run(3, "success"), page_run(2, "failure")],
                                  {3: [job_row("scope", "success")], 2: [job_row("scope", "success"), job_row("checks", "failure")]})

    def test_a_push_run_proven_by_push_skip_counts_green_over_an_older_red_run(self):
        self.assert_same_judgment([page_run(3, "success"), page_run(2, "failure")],
                                  {3: [job_row("push-skip", "success"), job_row("scope", "skipped"), job_row("checks", "skipped")],
                                   2: [job_row("checks", "failure")]})

    def test_a_red_run_of_one_workflow_file_is_not_hidden_by_a_newer_green_run_of_another(self):
        self.assert_same_judgment([page_run(4, "success", name="links", path=WF_LINKS), page_run(3, "failure"), page_run(2, "success")],
                                  {4: [job_row("checks", "success")],
                                   3: [job_row("scope", "success"), job_row("checks", "failure")],
                                   2: [job_row("scope", "success"), job_row("checks", "success")]})

    def test_a_newer_push_run_that_skipped_the_red_schedule_job_does_not_clear_it(self):
        self.assert_same_judgment([page_run(3, "success", event=PUSH), page_run(2, "failure", event="schedule")],
                                  {3: [job_row("scope", "success"), job_row("checks", "skipped")],
                                   2: [job_row("scope", "success"), job_row("checks", "failure")]})

    def test_a_newer_push_run_that_passed_the_red_schedule_jobs_clears_it(self):
        self.assert_same_judgment([page_run(3, "success", event=PUSH), page_run(2, "failure", event="schedule")],
                                  {3: [job_row("scope", "success"), job_row("checks", "success")],
                                   2: [job_row("scope", "success"), job_row("checks", "failure")]})

    def test_an_empty_page_judges_as_base_state_does(self):
        self.assert_same_judgment([], {})

    def test_a_full_page_of_green_runs_judges_as_base_state_does(self):
        page = [page_run(rid, "success") for rid in range(merge.MAIN_RUNS_READ, 0, -1)]
        self.assert_same_judgment(page, {rid: [job_row("scope", "success"), job_row("checks", "success")] for rid in range(1, merge.MAIN_RUNS_READ + 1)})

    def test_a_cancelled_run_whose_job_hit_its_cap_judges_as_base_state_does_with_the_cap(self):
        jobs = {2: [job_row("scope", "success"), job_row("checks-macos", "cancelled", minutes=30)]}
        self.assert_same_judgment([page_run(2, "cancelled")], jobs, caps={"checks-macos": 20})

    def test_the_same_cancelled_run_with_no_cap_judges_as_base_state_does(self):
        jobs = {2: [job_row("scope", "success"), job_row("checks-macos", "cancelled", minutes=30)]}
        self.assert_same_judgment([page_run(2, "cancelled")], jobs)

    def test_the_red_job_names_are_the_names_host_red_jobs_gives(self):
        judge_names = getattr(clear_rule, "red_job_names", None)
        self.assertTrue(callable(judge_names), "clear_rule has no red_job_names: Host.red_jobs still decides which jobs are red in merge.py")
        rows = [job_row("passes", "success"), job_row("neutral", "neutral"), job_row("skipped", "skipped"), job_row("fails", "failure"),
                job_row("timed-out", "timed_out"), job_row("cancelled", "cancelled"), job_row("cap", "cancelled", minutes=30),
                job_row("running", None, status="in_progress")]
        caps = {"cap": 20}
        with caps_read_as(caps):
            _got, _red, want = ScriptedHost([], {}).red_jobs(rows)
        self.assertEqual(judge_names(rows, caps), want, "red_job_names and Host.red_jobs name different red jobs")

    def test_fixed_a_newest_run_that_passed_judges_green_with_no_red_run(self):
        self.assertEqual(self.judge_fixed([page_run(2, "success")], {2: [job_row("scope", "success"), job_row("checks", "success")]}),
                         ("green", []), "a newest run that passed is not green with no red run")

    def test_fixed_a_red_job_in_the_newest_run_judges_red_with_that_job_named(self):
        self.assertEqual(self.judge_fixed([page_run(2, "failure")], {2: [job_row("scope", "success"), job_row("checks", "failure")]}),
                         ("red", [(2, ["checks"])]), "a red job in the newest run is not red, named by that job")

    def test_fixed_a_cancelled_run_with_no_red_job_judges_unknown_with_no_red_run(self):
        self.assertEqual(self.judge_fixed([page_run(2, "cancelled")], {2: [job_row("scope", "success"), job_row("checks", "cancelled")]}),
                         ("unknown", []), "a cancelled run with no red job is not unknown with no red run")

    def test_fixed_a_re_run_in_flight_above_an_older_green_run_judges_unknown(self):
        self.assertEqual(self.judge_fixed([page_run(3, None, status="in_progress", attempt=2), page_run(2, "success")],
                                          {3: [job_row("checks", None, status="in_progress")], 2: [job_row("checks", "success")]}),
                         ("unknown", []), "a re-run in flight above a green run does not make main unknown")

    def test_fixed_an_empty_green_push_run_above_an_older_red_push_run_leaves_that_red_run_standing(self):
        self.assertEqual(self.judge_fixed([page_run(3, "success"), page_run(2, "failure")],
                                          {3: [job_row("scope", "success")], 2: [job_row("scope", "success"), job_row("checks", "failure")]}),
                         ("red", [(2, ["checks"])]), "an empty green push run hides the older red push run")

    def test_control_the_scripted_host_reads_a_red_job_red_through_base_state(self):
        """Control, green on the old code: the cases above compare with base_state, so base_state must show a red job red on this host."""
        verdict, red = base_judgment([page_run(2, "failure")], {2: [job_row("checks", "failure")]})
        self.assertEqual(verdict, "red")
        self.assertEqual(red, [(2, ["checks"])])


if __name__ == "__main__":
    unittest.main()
