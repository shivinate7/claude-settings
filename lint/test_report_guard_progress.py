#!/usr/bin/env python3
"""The progress-claim check of report_guard.py (rule progress-claims-cite-live-read), run at Stop.

A reply line that says how far a step, lane, batch or PR has got ("still in progress", "nearly done", "waiting on CI")
must cite a live read made this turn, on the same line: get_session, list_events, pull_request_read,
list_pull_requests, "live read", "REST", a PR URL, or a read stamp such as "read at 11:43 CST". "unmeasured", "not read"
and "unknown" also pass. A bare `#n` names a PR and reads nothing. A line with no subject is no claim. A state word such
as "merged" or "finished", with no progress phrase, is no claim either.

Each case runs the Stop hook as a subprocess, as the other report_guard suites do. The Stop runner, the transcript
records, the run folder and the in-process opens watch come from lint/test_report_guard.py, the one home. Each case holds
a flagged twin beside its control, so a control that passes on code that does not yet check still fails here. Run with:

    python3 lint/test_report_guard_progress.py -v
"""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_report_guard as trg  # noqa: E402  the Stop runner, the transcript records, the run folder (one home)

RULE = "progress-claims-cite-live-read"
GET_SESSION = "get_session"
PULL_READ = "pull_request_read"
UNMEASURED = "unmeasured"
INCIDENT = "Step rounds-rules-one-record is still in progress."
LANE_NEAR = "Lane counts-from-rest is nearly done."
BATCH_WAIT = "Batch 133 is waiting on CI."
ANSWERED = "Answered: no permission rule can lift it."  # the answered check's own line, for the joined-reasons case

# One line per progress phrase, each with a lane subject. Each must be flagged.
PHRASE_LINES = (
    "Lane counts-from-rest is in progress.",
    "Lane counts-from-rest is still going.",
    "Lane counts-from-rest is still running.",
    "Lane counts-from-rest is nearly done.",
    "Lane counts-from-rest is almost done.",
    "Lane counts-from-rest is almost there.",
    "Lane counts-from-rest is almost finished.",
    "Lane counts-from-rest is close to done.",
    "Lane counts-from-rest is waiting on CI.",
    "Lane counts-from-rest is waiting for review.",
    "Lane counts-from-rest is in flight.",
    "Lane counts-from-rest is 40% done.",
    "Lane counts-from-rest is stalled.",
    "Lane counts-from-rest hasn't finished.",
)

# A step, a lane, a batch, a PR by its name, and a PR by its number alone. Each must be flagged.
SUBJECT_LINES = (
    "Step rounds-rules-one-record is nearly done.",
    "Lane counts-from-rest is nearly done.",
    "Batch 133 is nearly done.",
    "PR #2888 is nearly done.",
    "#2888 is nearly done.",
)

# (bare line, its live read). Each bare line is flagged, and passes with its read on the same line.
CITED = (
    (INCIDENT, "get_session at 11:43 CST: idle"),
    (LANE_NEAR, "list_events at 11:43 CST: last event idle"),
    (LANE_NEAR, "live read at 11:43 CST: idle"),
    (LANE_NEAR, "REST at 11:43 CST: idle"),
    (BATCH_WAIT, "pull_request_read on #2888: open, checks pending"),
    (BATCH_WAIT, "list_pull_requests: 1 open"),
    (BATCH_WAIT, "https://github.com/shivinate7/claude-settings/pull/2888"),
    (BATCH_WAIT, "read at 11:43 CST"),
)

# Lines that say "unmeasured", "not read" or "unknown" in place of a read. Each passes.
UNREAD = (
    "Lane counts-from-rest is nearly done (unmeasured).",
    "Lane counts-from-rest is nearly done; progress unmeasured.",
    "Lane counts-from-rest is nearly done; not read.",
    "Lane counts-from-rest is nearly done, how far unknown.",
)


def with_cite(line, read):
    """The line with `(read)` before its full stop, as a reply writes a cite."""
    return line[:-1] + " (" + read + ")."


def setUpModule():
    trg.setUpModule()  # the run folder, CLAUDE_CONFIG_DIR, the model stub and the missing route-rows seam


def tearDownModule():
    trg.tearDownModule()


class ProgressClaimTests(unittest.TestCase):
    """The progress-claim verdict, in report_guard.py's Stop hook. On any turn, each reply line that says how far a
    step, lane, batch or PR has got must cite its live read on that line. Every case is red on the old code."""

    # The one home of the in-process opens watch is AnsweredNeedsSourceTests.guard_opens. It calls self.hook(reply).
    guard_opens = trg.AnsweredNeedsSourceTests.guard_opens

    def hook(self, reply, landed=False, stop_hook_active=False):
        records = [trg.human("ask the owner")]
        if landed:
            records += [trg.tool_use_msg("Bash", {"command": "git commit -m x"}), trg.tool_result_msg()]
        records.append(trg.assistant_text(reply))
        path = trg.write_transcript(records, tempfile.mkdtemp(dir=trg.RUN_FOLDER))
        return {"hook_event_name": "Stop", "transcript_path": path, "stop_hook_active": stop_hook_active}

    def verdict(self, reply, **kw):
        run = trg.run_guard(trg.REPORT_GUARD, self.hook(reply, **kw))
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertNotIn("Traceback", run.stderr, "the Stop hook crashed: " + run.stderr[-300:])
        return json.loads(run.stdout) if run.stdout.strip() else None

    def assert_blocked(self, reply, *needles, **kw):
        """A block for `reply` whose reason holds each needle. Returns the reason."""
        out = self.verdict(reply, **kw)
        self.assertIsNotNone(out, "the check did not refuse the reply ending %r" % reply[-120:])
        self.assertEqual(out.get("decision"), "block", "not a block, ending %r" % reply[-120:])
        reason = out.get("reason", "")
        for needle in needles:
            self.assertIn(needle, reason)
        return reason

    def assert_allowed(self, reply, **kw):
        out = self.verdict(reply, **kw)
        self.assertIsNone(out, "the check refused the reply ending %r: %s" % (reply[-120:], out and out.get("reason")))

    # Each method holds its flagged twin first, so a control fails on code that does not check yet.

    def test_pc_red_incident_replay_step_still_in_progress_blocks(self):
        # Incident replay: a step's "still in progress" with no read blocks, and the refusal offers unmeasured.
        # Catches: a step line with a progress phrase passes.
        self.assert_blocked(INCIDENT, INCIDENT, RULE, UNMEASURED)

    def test_pc_red_lane_nearly_done_blocks_and_names_get_session(self):
        # Catches: a lane line with "nearly done" passes, or the refusal does not name the lane's read.
        self.assert_blocked(LANE_NEAR, LANE_NEAR, RULE, GET_SESSION, UNMEASURED)

    def test_pc_red_batch_waiting_on_ci_blocks_and_names_pull_request_read(self):
        # Catches: a batch line with "waiting on" passes, or the refusal does not name the batch PR's read.
        self.assert_blocked(BATCH_WAIT, BATCH_WAIT, RULE, PULL_READ, UNMEASURED)

    def test_pc_red_pr_lines_block_and_name_pull_request_read(self):
        # Catches: a PR line passes when the PR is named as "PR #n" or by "#n" alone, or the refusal names no PR read.
        for line in ("PR #2888 is still going.", "#2888 is stalled."):
            with self.subTest(line=line):
                self.assert_blocked(line, line, RULE, PULL_READ, UNMEASURED)

    def test_pc_red_each_progress_phrase_blocks(self):
        # Catches: a phrase on the list passes.
        for line in PHRASE_LINES:
            with self.subTest(line=line):
                self.assert_blocked(line, line, RULE)

    def test_pc_red_each_subject_blocks(self):
        # Catches: a step, a lane, a batch, or a PR by "PR #n" or "#n" passes as no subject.
        for line in SUBJECT_LINES:
            with self.subTest(line=line):
                self.assert_blocked(line, line, RULE)

    def test_pc_red_a_claim_blocks_on_landed_and_unlanded_turns(self):
        # Catches: the check runs on one kind of turn only, or a live read on a landed turn is refused.
        self.assert_blocked(INCIDENT, INCIDENT, RULE)
        self.assert_blocked(INCIDENT + "\n\n" + trg.GOOD_REPORT, INCIDENT, RULE, landed=True)
        cited = with_cite(INCIDENT, "get_session at 11:43 CST: idle")
        self.assert_allowed(cited + "\n\n" + trg.GOOD_REPORT, landed=True)

    def test_pc_red_a_claim_inside_a_report_item_blocks(self):
        # Catches: a claim in a blockquote report item passes, since the quote marker hides its line.
        self.assert_blocked("> **Next** " + BATCH_WAIT, BATCH_WAIT, RULE)
        self.assert_allowed("> **Next** " + with_cite(BATCH_WAIT, "pull_request_read: open"))

    def test_pc_red_one_refusal_lists_both_bad_lines(self):
        # Catches: the second bad line is dropped, or the two lines come as two refusals.
        reason = self.assert_blocked(INCIDENT + "\n" + LANE_NEAR, INCIDENT, LANE_NEAR, RULE)
        self.assertEqual(reason.count(RULE), 1, "the reason names the rule more than once: %s" % reason)

    def test_pc_red_joins_an_answered_refusal_in_one_block(self):
        # Catches: the progress line is dropped when another check refuses the same reply, or comes as a second block.
        reason = self.assert_blocked(ANSWERED + "\n" + LANE_NEAR, ANSWERED, LANE_NEAR, RULE)
        self.assertEqual(reason.count(RULE), 1, "the reason names the rule more than once: %s" % reason)

    def test_pc_red_a_line_after_a_closed_fence_blocks_and_the_fenced_line_does_not(self):
        # Catches: a fence that never closes hides the line after it, or a fenced line is listed as a claim.
        reason = self.assert_blocked("```\n" + LANE_NEAR + "\n```\n" + BATCH_WAIT, BATCH_WAIT, RULE)
        self.assertNotIn(LANE_NEAR, reason, "a fenced line is listed: %s" % reason)

    def test_pc_red_a_line_after_a_closed_tilde_fence_blocks_and_the_fenced_line_does_not(self):
        # Catches: a ~~~ fence is read as text, so its lines are listed as claims.
        reason = self.assert_blocked("~~~\n" + LANE_NEAR + "\n~~~\n" + BATCH_WAIT, BATCH_WAIT, RULE)
        self.assertNotIn(LANE_NEAR, reason, "a fenced line is listed: %s" % reason)

    def test_pc_red_a_claim_at_the_end_of_a_long_reply_blocks_and_a_cited_one_passes(self):
        # Full-size state: 400 prose lines, then one claim. Catches: the scan stops before the last line.
        prose = ["Line %d of the reply is plain prose." % n for n in range(400)]
        self.assert_blocked("\n".join(prose + [LANE_NEAR]), LANE_NEAR, RULE)
        self.assert_allowed("\n".join(prose + [with_cite(LANE_NEAR, "get_session at 11:43 CST: idle")]))

    def test_pc_red_an_empty_reply_passes_and_a_claim_blocks(self):
        # Empty state: a reply with no text holds no claim. Catches: an empty reply is refused or crashes the check.
        self.assert_blocked(LANE_NEAR, LANE_NEAR, RULE)
        self.assert_allowed("")

    def test_pc_red_a_progress_phrase_needs_a_subject(self):
        # Scope first: a lane with the phrase blocks. The same phrase with no step, lane, batch or PR is no claim.
        self.assert_blocked("Lane counts-from-rest is in progress.", RULE)
        self.assert_allowed("Work is in progress on my laptop.")

    def test_pc_red_a_state_word_on_a_pr_is_no_claim(self):
        # Scope first: a lane's progress phrase on a PR blocks. A state word on the same PR passes.
        self.assert_blocked("Lane x is still going in #2888.", RULE)
        self.assert_allowed("Lane x merged in #2888.")
        self.assert_allowed("PR #2888 merged.")

    def test_pc_red_finished_is_a_state_and_almost_finished_is_a_claim(self):
        # Scope first: "almost finished" blocks. "finished" with a time and no progress phrase passes.
        self.assert_blocked("Lane counts-from-rest is almost finished.", RULE)
        self.assert_allowed("Lane counts-from-rest finished at 19:42 CST Nov 12.")

    def test_pc_red_a_live_read_on_the_line_passes_and_the_bare_line_blocks(self):
        # Each bare line blocks. With its live read on the same line, it passes.
        for bare, read in CITED:
            with self.subTest(read=read):
                self.assert_blocked(bare, bare, RULE)
                self.assert_allowed(with_cite(bare, read))

    def test_pc_red_a_bare_pr_ref_is_no_live_read(self):
        # Catches: "(PR #2888)" counts as a live read, so a claim that names its PR and reads nothing passes.
        self.assert_blocked(with_cite(BATCH_WAIT, "PR #2888"), BATCH_WAIT, RULE)
        self.assert_allowed(with_cite(BATCH_WAIT, "pull_request_read on PR #2888: open"))

    def test_pc_red_unmeasured_not_read_or_unknown_passes(self):
        # Each bare line blocks. Each line that says unmeasured, not read or unknown in its place passes.
        self.assert_blocked(LANE_NEAR, LANE_NEAR, RULE)
        for line in UNREAD:
            with self.subTest(line=line):
                self.assert_allowed(line)

    def test_pc_red_a_question_line_passes_and_the_statement_blocks(self):
        # Catches: a line that ends in "?" asks and claims nothing, so it is read as a claim.
        self.assert_blocked(LANE_NEAR, LANE_NEAR, RULE)
        self.assert_allowed("Is the lane counts-from-rest nearly done?")

    def test_pc_red_an_inline_code_mention_passes(self):
        # Catches: a phrase or line inside an inline code span is read as a claim.
        self.assert_blocked(LANE_NEAR, LANE_NEAR, RULE)
        self.assert_allowed("The check flags `Lane counts-from-rest is nearly done.` as a claim.")
        self.assert_allowed("The check reads the phrase `nearly done` on a lane line.")

    def test_pc_red_a_rewrite_under_stop_hook_active_stays_quiet(self):
        # Same shape as answered-needs-source: the rewrite that follows a block is not refused again.
        self.assert_blocked(LANE_NEAR, LANE_NEAR, RULE)
        self.assert_allowed(LANE_NEAR, stop_hook_active=True)

    def test_pc_red_the_check_reads_only_the_transcript_and_guard(self):
        # Cost: a regex over the reply, with no other file read. A flagged line is refused, and a claim-free line is not.
        out, opened, transcript = self.guard_opens(LANE_NEAR)
        self.assertEqual((json.loads(out) if out else {}).get("decision"), "block", out)
        self.assertEqual(set(opened), {transcript, trg.GUARD_PY})
        out, opened, transcript = self.guard_opens("Lane counts-from-rest finished at 19:42 CST Nov 12.")
        self.assertEqual(out, "")
        self.assertEqual(set(opened), {transcript, trg.GUARD_PY})


if __name__ == "__main__":
    unittest.main()
