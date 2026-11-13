#!/usr/bin/env python3
"""Cases for the guard cull's readings of lint/report_guard.py (roadmap step guard-false-alarm-cull; decision
cull-guard-wrong-refusals).

- The Recovered check is removed. After a compaction, a report with no Recovered or Handoff line passes, and so
  does a Recovered item that names no source. These cases pin that reading, so a return of the refusal fails here
  (decision cull-guard-wrong-refusals). The handoff-unread guard is a different guard (hooks/guard.py) and is not
  touched here.
- A review PASS inside a statistic is not a review claim. A claim with no pull request still refuses on a lane,
  and that control stays.
- A review PASS that names a round, a reviewer or a pull request is a claim, even with a count word beside it. The
  statistic check must not read it as a count. A pull request named before the count, or in another clause, counts too.
- A reviewers word on a line does not make a PASS in another clause of that line a review claim.

Each case runs lint/report_guard.py as a Stop hook, the way Claude Code runs it, and reads only its output.
Run from the repository root:

    python3 lint/test_report_guard_cull.py

Standard library only. The Stop runner and transcript records come from lint/test_report_guard.py, and the lane
fixture from lint/test_report_guard_review.py: their one homes. Each case works in its own folder under this run's
folder (test-temp-standard).
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
import override  # noqa: E402  LANE_ENV, the env name that marks a lane session (hooks/override.py, one home)
import test_report_guard as trg  # noqa: E402  the Stop runner, transcript records and run folder (one home)
import test_report_guard_review as trr  # noqa: E402  the lane fixture: the lane's id, its parent and the env value
import report_guard as rg  # noqa: E402  review_claims, the review check's claim reader (one home, lint/report_guard.py)

RUN_FOLDER = trg.RUN_FOLDER
CALLS = trg.SameTurnWriter()  # builds tool-call records; holds no state
RECOVERED_REASON = "Recovered guard"
REVIEW_REASON = "Review-record guard"
NO_PR_TEXT = "names no pull request"
PLAIN_REPORT = "> **Done** OTHER read the state\n> **Deviations** none\n> **Next** wait"
# A Recovered item with no git, page or digest source, under Deviations.
UNSOURCED_RECOVERED = ("> **Done** OTHER read the state\n> **Deviations**\n> - Recovered: ruling X from the chat\n"
                       "> **Next** wait")
# A Recovered item with a source, and no Handoff gave line.
RECOVERED_ONLY = ("> **Done** OTHER read the state\n> **Deviations**\n> - Recovered: ruling X from PR 978 (git)\n"
                  "> **Next** wait")
BOTH_SOURCED = ("> **Done** OTHER read the state\n> **Deviations**\n"
                "> - Recovered: ruling X from PR 978 (git); fact Y (page)\n"
                "> - Handoff gave: none\n> **Next** wait")
COUNTED = "> **Done** OTHER counted the batch\n> **Deviations** none\n> **Next** wait"
STAT_LINES = (
    "Reviewer round 1 stats this batch: 9 of 10 lanes got PASS (PASS rate 90%).",
    "Round 1 reviewers this batch: PASS 9, FAIL 1, so the PASS count is 9.",
)
NO_PR_CLAIM = "Round 2 reviewer PASS on the lane's head."
# Claims that name pull request 12. Each has a count word that the statistic check strips today.
PR_CLAIMS = (
    "round 2 of 3 reviewers got PASS on #12.",
    "round 2 reviewer: 2 lanes got PASS on #12.",
    "3 reviewers got PASS on #12.",
    "round 2 reviewer on #12: PASS 2.",
    "round 2 reviewer: PR 12 PASS 2, FAIL 1.",
)
# Claims that name no pull request. The no-PR refusal needs no gh read, so these run the Stop hook end to end.
NO_PR_CLAIMS = ("round 2 reviewer PASS 12.", "(reviewer PASS 12)")
# Statistics that must stay no claim. The first three carry no round or reviewer word, so the trigger alone keeps them
# out; the last three carry one, so they test the statistic check itself.
STAT_CONTROLS = ("PASS rate 90%", "9 of 10 lanes got PASS", "the PASS count was 9",
                 "Round 2 stats: PASS rate 90%.", "Round 2 stats: 9 of 10 lanes got PASS.",
                 "Round 2 stats: the PASS count was 9.")
# Claims that name PR 12 before the count, or in another clause: the statistic check must not strip their PASS.
PR_IN_OTHER_CLAUSE = ("On #12, round 2: 2 reviewers got PASS.", "PR 12 round 2: 9 reviewers got PASS.",
                      "Round 2: 2 reviewers got PASS; PR #12 is merged.")
# A statistic-shaped line that names PR 12 is a claim, not a count.
PR_STAT_CLAIMS = ("Round 2 reviewers on #12: PASS rate 100%.", "Round 2 reviewers on #12: 100% PASS.")
# A round count that names no PR is a claim, refused on a lane as naming no pull request.
ROUND_COUNT_NO_PR = ("Round 2: 2 reviewers got PASS on the lane head.", "round 2 of 3 reviewers got PASS.")
# A reviewers word and a PASS in different clauses of one line: a count, not a claim.
REVIEWERS_APART_FROM_PASS = ("3 reviewers ran on the batch; 2 PASS.",
                             "Lint PASS; 2 reviewers asked for a rename on the helper.")


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)


def block_reason(out):
    """The block reason of a Stop output, or '' when the Stop passes."""
    if out and out.get("decision") == "block":
        return out.get("reason", "")
    return ""


def run_stop(records, lane=False):
    """The Stop output of `records`. A lane run names its session the way a lane's env does, so the review check reads it."""
    folder = tempfile.mkdtemp(dir=RUN_FOLDER)
    path = trg.write_transcript(records, folder)
    hook = {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": False, "cwd": folder,
            "session_id": "cull-sid-1"}
    env = dict(os.environ, CLAUDE_CONFIG_DIR=os.path.join(folder, "cfg"), CLAUDE_CODE_SUBAGENT_MODEL="sonnet")
    env.pop(override.LANE_ENV, None)
    if lane:
        env[override.LANE_ENV] = trr.LANE_ENV
    run = trg.run_guard(trg.REPORT_GUARD, hook, env=env)
    if run.returncode != 0:
        raise AssertionError("the guard exited %d: %s" % (run.returncode, run.stderr[-300:]))
    return json.loads(run.stdout) if run.stdout.strip() else None


def lane_own_record():
    """This lane's own get_session record, tagged cs-build:lane, as the review check reads it."""
    return CALLS.call("mcp__claude-code-remote__get_session", {"session_id": trr.LANE_ID},
                      result=json.dumps({"ccr": {"id": trr.LANE_ID, "tags": ["cs-build:lane"],
                                                 "parent_session_id": None}}))


def compacted(reply):
    """A compaction, then the report as the first reply after it."""
    return [trg.human("do the task"), trg.compact_boundary(), trg.compact_summary(), trg.assistant_text(reply)]


def done_report(text):
    """A report whose Done item is `text`. The other items hold nothing a check reads."""
    return "> **Done** OTHER " + text + "\n> **Deviations** none\n> **Next** wait"


def claim_prs(text):
    """The PR numbers of each review claim that review_claims reads in `text`, one list per claim line. It runs in
    process: a claim that names a PR is refused only after a gh read, and this file has no stand-in for gh
    (CLAIM_FORMS in test_report_guard_review.py cover that refusal)."""
    return [nums for _line, nums in rg.review_claims(done_report(text))]


class CullRecoveredCheckTests(unittest.TestCase):
    """DELETE ruling: the Recovered and Handoff gave report-line check is gone."""

    def test_cull_red_compacted_report_without_carry_line_passes(self):
        # Catches: a report after a compaction with no Recovered or Handoff gave line is refused by the Recovered check.
        out = run_stop(compacted(PLAIN_REPORT))
        self.assertNotIn(RECOVERED_REASON, block_reason(out),
                         "the Recovered check refused a report with no carry line after a compaction")

    def test_cull_red_recovered_item_without_a_source_passes(self):
        # Catches: a Recovered item that names no git, page or digest source is refused, after a compaction.
        out = run_stop(compacted(UNSOURCED_RECOVERED))
        self.assertNotIn(RECOVERED_REASON, block_reason(out),
                         "the Recovered check refused a Recovered item with no source after a compaction")

    def test_cull_red_recovered_without_handoff_gave_passes(self):
        # Catches: a report with a sourced Recovered line and no Handoff gave line is refused after a compaction.
        out = run_stop(compacted(RECOVERED_ONLY))
        self.assertNotIn(RECOVERED_REASON, block_reason(out),
                         "the Recovered check refused a report with no Handoff gave line after a compaction")

    def test_cull_green_compacted_report_with_both_lines_still_passes(self):
        # Control: a report after a compaction that holds both lines passes today and after the cull.
        self.assertEqual(block_reason(run_stop(compacted(BOTH_SOURCED))), "",
                         "control: a compacted report with both carry lines was refused")

    def test_cull_green_report_with_no_compaction_still_passes(self):
        # Control: with no compaction, a plain report passes today and after the cull.
        self.assertEqual(block_reason(run_stop([trg.human("do the task"), trg.assistant_text(PLAIN_REPORT)])), "",
                         "control: a plain report with no compaction was refused")


class CullReviewStatisticTests(unittest.TestCase):
    """A review PASS inside a statistic is not a review claim. The review check reads only a lane session."""

    @staticmethod
    def lane_turn(reply):
        return [*lane_own_record(), trg.peer_msg("count the batch", from_session=trr.PARENT), trg.assistant_text(reply)]

    def test_cull_red_pass_inside_a_statistic_is_not_a_review_claim(self):
        # Scope first (P7): the lane turn refuses a real claim with no PR, so the statistic cases judge a live check.
        scope = block_reason(run_stop(self.lane_turn(COUNTED + "\n\n" + NO_PR_CLAIM), lane=True))
        self.assertIn(REVIEW_REASON, scope, "scope: the lane fixture does not reach the review check")
        for line in STAT_LINES:
            with self.subTest(line=line):
                out = run_stop(self.lane_turn(COUNTED + "\n\n" + line), lane=True)
                self.assertNotIn(REVIEW_REASON, block_reason(out),
                                 "the review-record guard read a statistic's PASS as a review claim")

    def test_cull_green_review_pass_claim_without_a_pr_still_refuses(self):
        # Control: a line that claims a reviewer PASS and names no pull request still refuses on a lane.
        reason = block_reason(run_stop(self.lane_turn(COUNTED + "\n\n" + NO_PR_CLAIM), lane=True))
        self.assertIn(REVIEW_REASON, reason, "control: a review PASS claim with no PR was not refused")
        self.assertIn(NO_PR_TEXT, reason, "control: the refusal does not name the missing PR")


class CullReviewClaimTests(unittest.TestCase):
    """A review PASS that names a round, a reviewer or a pull request is a claim, even beside a count word. The
    statistic check must not read such a claim as a count."""

    def test_cull_red_pass_claim_naming_pr_12_is_read_as_a_claim(self):
        # Scope first (P7): a plain claim on #12 is read as one claim naming 12, so the lines below judge the statistic
        # check.
        self.assertEqual(claim_prs("round 2 PASS on #12."), [[12]],
                         "scope: review_claims does not read a plain claim on #12")
        for text in PR_CLAIMS:
            with self.subTest(line=text):
                self.assertEqual(claim_prs(text), [[12]],
                                 "review_claims does not read this line as one review claim naming PR 12")

    def test_cull_red_pass_claim_with_no_pr_is_refused_on_a_lane(self):
        # Scope first (P7): a plain claim with no PR is refused by the no-PR reason on a lane, so the lines below judge
        # the statistic check.
        out = run_stop(CullReviewStatisticTests.lane_turn(done_report(NO_PR_CLAIM)), lane=True)
        self.assertIn(NO_PR_TEXT, block_reason(out), "scope: the lane fixture does not refuse a plain claim with no PR")
        for text in NO_PR_CLAIMS:
            with self.subTest(line=text):
                out = run_stop(CullReviewStatisticTests.lane_turn(done_report(text)), lane=True)
                self.assertIn(NO_PR_TEXT, block_reason(out),
                              "the review-record guard passed a review PASS claim that names no PR")

    def test_cull_green_statistic_lines_are_not_claims(self):
        # Control: a count of PASS is no review claim, with or without a round or reviewer word beside it.
        for text in STAT_CONTROLS:
            with self.subTest(line=text):
                self.assertEqual(claim_prs(text), [], "review_claims reads a statistic line as a review claim")

    def test_cull_red_pr_before_the_count_or_in_another_clause_is_a_claim(self):
        # Scope first (P7): a plain reviewer PASS on #12 is read as one claim naming 12, so the lines below judge the
        # statistic check.
        self.assertEqual(claim_prs("Round 2 reviewer got PASS on #12."), [[12]],
                         "scope: review_claims does not read a plain claim on #12")
        for text in PR_IN_OTHER_CLAUSE:
            with self.subTest(line=text):
                self.assertEqual(claim_prs(text), [[12]],
                                 "the statistic check strips a count's PASS though PR 12 is named on the line")

    def test_cull_red_statistic_that_names_a_pr_is_a_claim(self):
        # Scope first (P7): a plain PASS on a line that names #12 is one claim naming 12, so the lines below judge the
        # statistic check.
        self.assertEqual(claim_prs("Round 2 reviewers on #12: PASS."), [[12]],
                         "scope: review_claims does not read a plain PASS on a line that names #12")
        for text in PR_STAT_CLAIMS:
            with self.subTest(line=text):
                self.assertEqual(claim_prs(text), [[12]],
                                 "the statistic check strips a PASS on a line that names PR 12")

    def test_cull_red_round_count_with_no_pr_is_refused_on_a_lane(self):
        # Scope first (P7): a plain claim with no PR is refused on a lane, so the lines below judge the statistic check.
        out = run_stop(CullReviewStatisticTests.lane_turn(done_report(NO_PR_CLAIM)), lane=True)
        self.assertIn(NO_PR_TEXT, block_reason(out), "scope: the lane fixture does not refuse a plain claim with no PR")
        for text in ROUND_COUNT_NO_PR:
            with self.subTest(line=text):
                self.assertEqual(claim_prs(text), [[]],
                                 "the statistic check strips a round count's PASS on a line that names no PR")
        for text in ROUND_COUNT_NO_PR:
            with self.subTest(line=text):
                out = run_stop(CullReviewStatisticTests.lane_turn(done_report(text)), lane=True)
                self.assertIn(NO_PR_TEXT, block_reason(out),
                              "the review-record guard passed a round-count review PASS that names no PR")

    def test_cull_red_reviewers_word_and_a_pass_in_other_clauses_is_not_a_claim(self):
        # Scope first (P7): a plain reviewer PASS with no count is one claim with no PR, so the lines below judge the
        # clause check.
        self.assertEqual(claim_prs("Round 2 reviewer got PASS."), [[]],
                         "scope: review_claims does not read a plain reviewer PASS as a claim")
        for text in REVIEWERS_APART_FROM_PASS:
            with self.subTest(line=text):
                self.assertEqual(claim_prs(text), [],
                                 "the reviewers word on the line makes a PASS in another clause a review claim")


if __name__ == "__main__":
    unittest.main()
