#!/usr/bin/env python3
"""Cases for two wrong refusals of lint/report_guard.py that the guard cull names (roadmap step
guard-false-alarm-cull; decision cull-guard-wrong-refusals).

- The Recovered check goes (owner-delegate DELETE ruling, coordinator 11:22 CST, 2026-11-12). After a compaction,
  a report with no Recovered or Handoff gave line passes, and so does a Recovered item that names no source.
  The handoff-unread guard is a different guard (hooks/guard.py) and is not touched here.
- A review PASS inside a statistic is not a review claim (retrospective session, 15:39 CST, 2026-11-10). A claim
  with no pull request still refuses on a lane, and that control stays.

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


if __name__ == "__main__":
    unittest.main()
