#!/usr/bin/env python3
"""The batch runner's Stop hold: a runner's turn does not end while a merge is unswept or a send-back is unanswered.

A session whose own newest get_session record carries cs-build:batch-runner (hooks/guard_merge.py _own_tier_proved)
is held while either act is owed:

- A merge result is newer than the newest `merge --idle-lanes` result. The merge result is the line
  `merge: #N merged as <sha>.`, read from a merge run's result in one of three places: a direct Bash result; the
  output file of a background run, which its completion record names by tool-use id and output file; or the log of a
  verdict run, whose FAIL line names the log (VERDICT_LOG_RE).
- A `send back: #N <session id> (<reason>)` line from `merge --reviewed` has no later send_message to that session id
  that names #N. A line with `no session` in the id's place is not owed.

The release rules the cases pin:

- An --idle-lanes run after the merge releases it. One before the merge does not.
- A send to the owed session id that names #N releases its line. A send to another id, a send that does not name #N
  (#640 is not #64), and a send before the line do not.
- On a second Stop (stop_hook_active), Input Needed naming the PR releases the merge hold, as triage_hold releases its
  entries. Input Needed that names only #640 does not.
- An owner override lifts the hold once, and the Stop it lifts spends it.
- A missing verdict log or output file reads as no merge result. An error in the hold's own import fails open.
- A session whose tier is not proved batch-runner never holds, and neither does a draft --confirm.

Each held case is red on the old code, where no hold exists. A release case first shows the Stop held, so it passes
only where the hold reads the line and then releases it. A control that must stay released passes on the old code.
The fixture, the Stop helper, the owner override and the transcript helpers come from lint/test_report_guard_stalled.py
and lint/test_report_guard.py (one home each). Run with:

    python3 lint/test_report_guard_idle_hold.py -v
"""
import itertools
import json
import os
import shutil
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_report_guard as trg  # noqa: E402  the transcript helpers and the guard runner (one home)
import test_report_guard_stalled as trs  # noqa: E402  the Stop fixture, the owner override and own records (one home)

human = trg.human
assistant_text = trg.assistant_text

RUNNER_ID = "session_runner1"
RUNNER_ENV = "cse_runner1"  # the remote id override.remote_session_id() reads as RUNNER_ID
RUNNER_TAG = "cs-build:batch-runner"
OTHER_RUNNER_ID = "session_runner2"
NONE_ID = "session_none1"
NONE_ENV = "cse_none1"
PARENT_ID = "session_parent1"
MERGE_CMD = "merge 64 --confirm"
VERDICT_MERGE_CMD = "~/.claude/bin/verdict python3 merge/merge.py 64 --confirm"
IDLE_CMD = "merge --idle-lanes --live live.md"
REVIEWED_CMD = "merge --reviewed"
MERGED_64 = "merge: #64 merged as 9f3c1a7e2."
MERGED_63 = "merge: #63 merged as 1d2e3f4a5."
IDLE_DONE = "merge: 0 lanes to archive. Run get_session on each alone, then archive it."
DRAFT_64 = ("merge: #64 stays a draft (no reason given). Mark it ready after its draft run shows, "
            "then run --confirm again to merge. Nothing was merged.")
WELL_FORMED = "\n".join(["> **Done** OTHER merge landed as 9f3c1a7e2", "> **Deviations** none",
                         "> **Input Needed** none", "> **Next** wait"])
CORRECTION_TAILS = ("Post only the corrected lines", "Never send the report again")
REPO_ROOT = os.path.dirname(HERE)  # the checkout under test: its merge/ is the one the global rules pointer names
INSTALL_IGNORE = shutil.ignore_patterns("test_*", "_test_*", "__pycache__")


def setUpModule():
    trs.setUpModule()  # the run folder and the environment, set as test_report_guard_stalled sets them


def tearDownModule():
    trs.tearDownModule()


def bash_call(command, result, is_error=False):
    """A Bash call and its result, as a transcript holds them."""
    return trs.tool_pair("Bash", {"command": command}, result, is_error=is_error)


def reviewed(*lines):
    """A merge --reviewed run whose result holds `lines`. Lines that are not send-backs are noise to the hold."""
    return bash_call(REVIEWED_CMD, "\n".join(lines))


def send_back(n, session_id, reason="CI red on the fix check"):
    """The line `merge --reviewed` prints for a reviewed PR whose session must hear about it."""
    return "send back: #%d %s (%s)" % (n, session_id, reason)


def report_naming(text):
    """A report whose Input Needed item says `text`. Its Done line names no PR, so only Input Needed can release."""
    return "\n".join(["> **Done** OTHER merge landed as 9f3c1a7e2", "> **Input Needed** " + text, "> **Next** wait"])


def background_call(command, task_id):
    """A Bash call run in the background, and its immediate result. The result holds no output: the output goes to a
    file, and the completion record names that file."""
    use_id = "toolu_%s" % task_id
    use = {"type": "assistant", "isSidechain": False, "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": use_id, "name": "Bash",
         "input": {"command": command, "run_in_background": True}}]}}
    result = {"type": "user", "isSidechain": False, "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": use_id,
         "content": "Command running in background with ID: %s." % task_id}]}}
    return use_id, [use, result]


def completion(use_id, task_id, output_file):
    """The record a finished background task leaves: a queued_command attachment whose prompt names the call by its
    tool-use id and its output file. The attachment's shape is a real agent completion's, as the local transcripts hold
    it. No local transcript holds a background Bash run, so the summary text is modelled, not read."""
    prompt = ("<task-notification>\n<task-id>%s</task-id>\n<tool-use-id>%s</tool-use-id>\n"
              "<output-file>%s</output-file>\n<status>completed</status>\n"
              "<summary>Background command completed</summary>\n</task-notification>"
              % (task_id, use_id, output_file))
    return {"type": "attachment", "isSidechain": False,
            "attachment": {"type": "queued_command", "prompt": prompt}}


def install_copy(folder):
    """A copy of lint/ and hooks/ as an install holds them, under folder/installed. No merge/ sits beside them, and the
    copies are real files, not links, so their own real paths reach no checkout."""
    root = os.path.join(folder, "installed")
    for name in ("lint", "hooks"):
        shutil.copytree(os.path.join(REPO_ROOT, name), os.path.join(root, name), ignore=INSTALL_IGNORE)
    return root


_MESSAGE_IDS = itertools.count(1)


def one_message(*runs):
    """One assistant message that issues each (command, result) run in order, then one user record that returns their
    results in the reverse order. Only the order of the tool_use blocks says which call came first."""
    uses, results = [], []
    for command, result in runs:
        use_id = "toolu_msg%d" % next(_MESSAGE_IDS)
        uses.append({"type": "tool_use", "id": use_id, "name": "Bash", "input": {"command": command}})
        results.append({"type": "tool_result", "tool_use_id": use_id, "content": result, "is_error": False})
    return [{"type": "assistant", "isSidechain": False, "message": {"role": "assistant", "content": uses}},
            {"type": "user", "isSidechain": False, "message": {"role": "user", "content": results[::-1]}}]


class IdleLaneHoldTests(trs.StalledFixture, unittest.TestCase):

    def runner_stop(self, records, env_id=RUNNER_ENV, stop_active=False):
        """Stop on `records` as the session env_id names, with the hook's own session id set."""
        return self.stop(records, env_id=env_id, stop_active=stop_active, session_id=trs.OWNER_SESSION)

    def runner(self):
        """This session's own get_session record, tagged as a batch runner."""
        return trs.own_record(RUNNER_ID, [RUNNER_TAG])

    def send_text(self, session_id, text):
        """A send_message to session_id whose text is `text`."""
        return self.call("mcp__claude-code-remote__send_message", {"session_id": session_id, "message": text},
                         result="sent")

    def output_file(self, task_id, lines):
        """The output file of a background task, written in this run's folder."""
        path = os.path.join(self.run_dir, "tasks", task_id + ".output")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
        return path

    def verdict_merge(self, lines):
        """A merge run through verdict that exits 1 after its merge, so verdict prints the FAIL line with the log path.
        verdict prints no log path on a PASS line, so a merge that passes is out of the hold's reach."""
        log = os.path.join(self.run_dir, "verdict-merge.log")
        with open(log, "w", encoding="utf-8") as handle:
            handle.write("=== verdict run 2026-11-08 10:40:00: python3 merge/merge.py 64 --confirm\n")
            handle.write("\n".join(lines) + "\n")
        body = "FAIL python3 merge/merge.py 64 --confirm rc=1 (2.1s) log=%s" % log
        return bash_call(VERDICT_MERGE_CMD, body, is_error=True), log

    def blocked_runner_stop(self, records, block):
        """Stop on `records` with the named modules unimportable, as an error in the hold's own imports would leave it."""
        path = trg.write_transcript(records, self.run_dir)
        hook = {"hook_event_name": "Stop", "session_id": trs.OWNER_SESSION, "transcript_path": path,
                "stop_hook_active": False, "cwd": self.repo}
        env = dict(os.environ, CLAUDE_CONFIG_DIR=self.cfg, HOME=self.home, CLAUDE_CODE_REMOTE_SESSION_ID=RUNNER_ENV)
        run = trg.run_guard(trg.REPORT_GUARD, hook, env=env, block=block)
        self.assertEqual(run.returncode, 0, run.stderr)
        return json.loads(run.stdout) if run.stdout.strip() else None

    def held_on_merge(self, out, n=64):
        """The Stop was refused as a block, and the refusal names the merged PR and the command that sweeps its lane."""
        self.assertIsNotNone(out, "the Stop was not refused: a runner ended its turn on a merge no --idle-lanes run swept")
        self.assertEqual(out.get("decision"), "block", "the Stop was not refused as a block: %r" % (out,))
        self.assertRegex(out["reason"], r"#%d(?!\d)" % n, "the refusal does not name the merged PR #%d" % n)
        self.assertIn("idle-lanes", out["reason"], "the refusal does not say to run merge --idle-lanes")

    def held_on_send_back(self, out, session_id, n=64):
        """The Stop was refused as a block, and the refusal names the session the send-back is owed to and its PR."""
        self.assertIsNotNone(out, "the Stop was not refused: a runner ended its turn on a send-back no session heard")
        self.assertEqual(out.get("decision"), "block", "the Stop was not refused as a block: %r" % (out,))
        self.assertIn(session_id, out["reason"], "the refusal does not name the session the send-back is owed to")
        self.assertRegex(out["reason"], r"#%d(?!\d)" % n, "the refusal does not name the reviewed PR #%d" % n)

    def released(self, out):
        """The Stop was not refused."""
        self.assertFalse(out and out.get("decision") == "block", "the Stop was refused although nothing is owed: %r" % (out,))

    # Held: each is red where no hold exists. Each names the cause in its own assert message.

    def test_idle_red_direct_merge_result_holds_the_runner_stop(self):
        # Catches: a runner ends its turn on a merge that no --idle-lanes run has swept, so the merged lane never archives.
        out = self.runner_stop([human("wake"), *self.runner(), *bash_call(MERGE_CMD, MERGED_64),
                                assistant_text(WELL_FORMED)])
        self.held_on_merge(out)

    def test_idle_red_background_merge_output_holds_the_runner_stop(self):
        # Catches: a merge run in the background leaves its result in an output file that the hold never reads.
        use_id, call = background_call(MERGE_CMD, "bgmerge1")
        path = self.output_file("bgmerge1", [MERGED_64])
        out = self.runner_stop([human("wake"), *self.runner(), *call, assistant_text("Merge running."),
                                completion(use_id, "bgmerge1", path), assistant_text(WELL_FORMED)])
        self.held_on_merge(out)

    def test_idle_red_verdict_merge_log_holds_the_runner_stop(self):
        # Catches: a merge run through verdict shows only its FAIL line and log path, so the merged line in its log goes unread.
        call, _ = self.verdict_merge([MERGED_64, "merge: #64 the step after the merge exited 1"])
        out = self.runner_stop([human("wake"), *self.runner(), *call, assistant_text(WELL_FORMED)])
        self.held_on_merge(out)

    def test_idle_red_merge_after_an_idle_run_holds_the_runner_stop(self):
        # Catches: an --idle-lanes run before the merge clears the merge, so the merged lane is never archived.
        out = self.runner_stop([human("wake"), *self.runner(), *bash_call(IDLE_CMD, IDLE_DONE),
                                *bash_call(MERGE_CMD, MERGED_64), assistant_text(WELL_FORMED)])
        self.held_on_merge(out)

    def test_idle_red_refusal_names_the_newest_merge_only(self):
        # Catches: the refusal names a PR that an earlier --idle-lanes run already swept, or misses the newest merge.
        out = self.runner_stop([human("wake"), *self.runner(), *bash_call(MERGE_CMD, MERGED_63),
                                *bash_call(IDLE_CMD, IDLE_DONE), *bash_call(MERGE_CMD, MERGED_64),
                                assistant_text(WELL_FORMED)])
        self.held_on_merge(out)
        self.assertNotRegex(out["reason"], r"#63(?!\d)",
                            "the refusal names #63, which the --idle-lanes run after it already swept")

    def test_idle_red_send_back_line_holds_the_runner_stop(self):
        # Catches: a runner ends its turn on a send-back line that no session heard, so the reviewed lane waits forever.
        out = self.runner_stop([human("wake"), *self.runner(), *reviewed(send_back(64, "session_lane2")),
                                assistant_text(WELL_FORMED)])
        self.held_on_send_back(out, "session_lane2")

    def test_idle_red_send_before_the_send_back_line_does_not_release(self):
        # Catches: a send made before the review's line counts as answering it.
        out = self.runner_stop([human("wake"), *self.runner(),
                                *self.send_text("session_lane2", "#64: the fix check failed; read the review."),
                                *reviewed(send_back(64, "session_lane2")), assistant_text(WELL_FORMED)])
        self.held_on_send_back(out, "session_lane2")

    def test_idle_red_send_to_another_session_does_not_release(self):
        # Catches: a send to any session releases the send-back, so the owed session never hears about its PR.
        out = self.runner_stop([human("wake"), *self.runner(), *reviewed(send_back(64, "session_lane2")),
                                *self.send_text("session_lane3", "#64: the fix check failed; read the review."),
                                assistant_text(WELL_FORMED)])
        self.held_on_send_back(out, "session_lane2")

    def test_idle_red_send_that_does_not_name_the_pr_does_not_release(self):
        # Catches: a send to the owed session releases the line whatever its text, so #640 passes for #64.
        plain = self.runner_stop([human("wake"), *self.runner(), *reviewed(send_back(64, "session_lane2")),
                                  *self.send_text("session_lane2", "read the review and fix the check."),
                                  assistant_text(WELL_FORMED)])
        self.held_on_send_back(plain, "session_lane2")
        longer = self.runner_stop([human("wake"), *self.runner(), *reviewed(send_back(64, "session_lane2")),
                                   *self.send_text("session_lane2", "#640 is the other lane; read the review."),
                                   assistant_text(WELL_FORMED)])
        self.held_on_send_back(longer, "session_lane2")

    def test_idle_red_second_send_back_line_stays_held_after_the_first_is_sent(self):
        # Catches: one send clears every send-back that a review printed, so the second PR's session never hears of it.
        out = self.runner_stop([human("wake"), *self.runner(),
                                *reviewed("#63 ready: review record ok, CI green", send_back(64, "session_lane2"),
                                          send_back(65, "session_lane3"), "#66 draft"),
                                *self.send_text("session_lane2", "#64: read the review and fix the check."),
                                assistant_text(WELL_FORMED)])
        self.held_on_send_back(out, "session_lane3", n=65)
        self.assertNotIn("session_lane2", out["reason"],
                         "the refusal names session_lane2, whose line the send already answered")

    def test_idle_red_second_stop_naming_only_640_stays_held(self):
        # Catches: an Input Needed that names #640 releases the hold for #64, because the digits match.
        records = [human("wake"), *self.runner(), *bash_call(MERGE_CMD, MERGED_64), assistant_text(WELL_FORMED)]
        out = self.runner_stop(records + [assistant_text(report_naming("Archive the lane of #640 by hand."))],
                               stop_active=True)
        self.held_on_merge(out)

    def test_idle_red_held_first_stop_on_a_well_formed_report_has_no_correction_tail(self):
        # Catches: the hold's refusal carries the report's correction tail, so a well-formed report is sent again.
        out = self.runner_stop([human("wake"), *self.runner(), *bash_call(MERGE_CMD, MERGED_64),
                                assistant_text(WELL_FORMED)])
        self.held_on_merge(out)
        for tail in CORRECTION_TAILS:
            self.assertNotIn(tail, out["reason"], "the hold's refusal carries the report's correction tail %r" % tail)

    # Released after the owed act, and fail-open cases. Each shows the Stop held first, so the release is the hold's.

    def test_idle_red_idle_run_after_the_merge_releases_it(self):
        # Catches: an --idle-lanes run after the merge does not clear it, so every merged lane stays held.
        records = [human("wake"), *self.runner(), *bash_call(MERGE_CMD, MERGED_64), assistant_text(WELL_FORMED)]
        self.held_on_merge(self.runner_stop(records))  # precondition: a merge no sweep has cleared is held
        out = self.runner_stop([human("wake"), *self.runner(), *bash_call(MERGE_CMD, MERGED_64),
                                *bash_call(IDLE_CMD, IDLE_DONE), assistant_text(WELL_FORMED)])
        self.released(out)

    def test_idle_red_idle_run_after_a_background_merge_releases_it(self):
        # Catches: the background shape is not read as a merge, so an --idle-lanes run after it does not clear it.
        use_id, call = background_call(MERGE_CMD, "bgmerge2")
        notice = completion(use_id, "bgmerge2", self.output_file("bgmerge2", [MERGED_64]))
        before = [human("wake"), *self.runner(), *call, assistant_text("Merge running."), notice]
        self.held_on_merge(self.runner_stop(before + [assistant_text(WELL_FORMED)]))  # precondition: held
        out = self.runner_stop(before + [*bash_call(IDLE_CMD, IDLE_DONE), assistant_text(WELL_FORMED)])
        self.released(out)

    def test_idle_red_sent_send_back_releases_the_stop(self):
        # Catches: a send to the owed session that names the PR does not clear its send-back line.
        owed = [human("wake"), *self.runner(), *reviewed(send_back(64, "session_lane2")), assistant_text(WELL_FORMED)]
        self.held_on_send_back(self.runner_stop(owed), "session_lane2")  # precondition: the line is owed
        sent = [human("wake"), *self.runner(), *reviewed(send_back(64, "session_lane2")),
                *self.send_text("session_lane2", "#64: read the review and fix the check."),
                assistant_text(WELL_FORMED)]
        self.released(self.runner_stop(sent))

    def test_idle_red_input_needed_naming_the_pr_releases_a_second_stop(self):
        # Catches: no escalation path, so a runner whose Input Needed names the merged PR loops on its second Stop.
        records = [human("wake"), *self.runner(), *bash_call(MERGE_CMD, MERGED_64), assistant_text(WELL_FORMED)]
        self.held_on_merge(self.runner_stop(records, stop_active=True))  # precondition: no names, so it is held
        out = self.runner_stop(records + [assistant_text(report_naming("Archive the lane of #64 by hand."))],
                               stop_active=True)
        self.released(out)

    def test_idle_red_owner_override_releases_the_hold(self):
        # Catches: the owner's typed override does not reach the hold, so the runner cannot end its turn on the owner's act.
        records = [human("wake"), *self.runner(), *bash_call(MERGE_CMD, MERGED_64), assistant_text(WELL_FORMED)]
        with mock.patch.dict(os.environ, {"LOCAL_TIME_NOW": trs.NOW}):
            self.held_on_merge(self.runner_stop(records))  # precondition: the hold stands before the override
            self.grant_once()
            self.released(self.runner_stop(records))

    def test_idle_red_a_stop_the_override_lifts_spends_it(self):
        # Catches: one typed override lifts every later Stop, so a runner is released for good on one act.
        records = [human("wake"), *self.runner(), *bash_call(MERGE_CMD, MERGED_64), assistant_text(WELL_FORMED)]
        with mock.patch.dict(os.environ, {"LOCAL_TIME_NOW": trs.NOW}):
            self.held_on_merge(self.runner_stop(records))  # precondition: the hold stands before the override
            self.grant_once()
            self.released(self.runner_stop(records))  # the one Stop the override lifts
            self.held_on_merge(self.runner_stop(records))  # the next Stop is held again: the override was spent

    def test_idle_red_missing_verdict_log_fails_open(self):
        # Catches: a verdict log that is gone raises in the hold, so the runner's Stop is refused on an unreadable record.
        call, log = self.verdict_merge([MERGED_64])
        records = [human("wake"), *self.runner(), *call, assistant_text(WELL_FORMED)]
        self.held_on_merge(self.runner_stop(records))  # precondition: the readable log holds the line
        os.remove(log)
        self.released(self.runner_stop(records))

    def test_idle_red_missing_background_output_fails_open(self):
        # Catches: a background run whose output file is gone raises in the hold, so the runner's Stop is refused on it.
        use_id, call = background_call(MERGE_CMD, "bgmerge3")
        path = self.output_file("bgmerge3", [MERGED_64])
        records = [human("wake"), *self.runner(), *call, completion(use_id, "bgmerge3", path),
                   assistant_text(WELL_FORMED)]
        self.held_on_merge(self.runner_stop(records))  # precondition: the readable output holds the line
        os.remove(path)
        self.released(self.runner_stop(records))

    def test_idle_red_error_in_the_hold_fails_open(self):
        # Catches: an error in the hold's own import holds the runner's Stop, instead of releasing it.
        records = [human("wake"), *self.runner(), *bash_call(MERGE_CMD, MERGED_64), assistant_text(WELL_FORMED)]
        self.held_on_merge(self.runner_stop(records))  # precondition: the hold stands with its imports whole
        self.released(self.blocked_runner_stop(records, ("guard_merge",)))

    # Controls: each must stay released. They pass on the old code, where no hold exists.

    def test_idle_control_draft_confirm_holds_nothing(self):
        # Catches: a --confirm on a draft reads as a merge, so a runner is held on a PR that never merged.
        out = self.runner_stop([human("wake"), *self.runner(), *bash_call(MERGE_CMD, DRAFT_64),
                                assistant_text(WELL_FORMED)])
        self.released(out)

    def test_idle_control_triage_session_holds_nothing(self):
        # Catches: the hold runs on every tier, so a triage session is held on a merge and a send-back it did not run.
        out = self.runner_stop([human("wake"), *trs.own_record(trs.TRIAGE_ID, ["cs-build:triage"]),
                                *bash_call(MERGE_CMD, MERGED_64), *reviewed(send_back(64, "session_lane2")),
                                assistant_text(WELL_FORMED)], env_id=trs.TRIAGE_ENV)
        self.released(out)

    def test_idle_control_lane_session_holds_nothing(self):
        # Catches: the hold runs on a lane, so a lane is held on a merge and a send-back it did not run.
        out = self.runner_stop([human("wake"),
                                *trs.own_record(trs.LANE_ID, ["cs-build:lane"], parent=PARENT_ID),
                                *bash_call(MERGE_CMD, MERGED_64), *reviewed(send_back(64, "session_lane2")),
                                assistant_text(WELL_FORMED)], env_id=trs.LANE_ENV)
        self.released(out)

    def test_idle_control_session_with_no_tags_holds_nothing(self):
        # Catches: a session with no tier is taken for a runner, so any merge it reads holds it.
        out = self.runner_stop([human("wake"), *trs.own_record(NONE_ID, []), *bash_call(MERGE_CMD, MERGED_64),
                                assistant_text(WELL_FORMED)], env_id=NONE_ENV)
        self.released(out)

    def test_idle_control_send_back_with_no_session_is_not_owed(self):
        # Catches: a send-back with no session to hear it is held, so the runner waits for a send that cannot happen.
        out = self.runner_stop([human("wake"), *self.runner(),
                                *reviewed("send back: #64 no session (the lane's session ended)"),
                                assistant_text(WELL_FORMED)])
        self.released(out)

    def test_idle_control_tags_set_after_the_runner_record_release_it(self):
        # Catches: a session whose runner tag was removed after its record still holds the Stop.
        out = self.runner_stop([human("wake"), *self.runner(), *trs.set_tags([RUNNER_ID]),
                                *bash_call(MERGE_CMD, MERGED_64), assistant_text(WELL_FORMED)])
        self.released(out)

    def test_idle_control_another_sessions_runner_record_holds_nothing(self):
        # Catches: a runner record for another session id is read as this session's own record.
        out = self.runner_stop([human("wake"), *trs.own_record(OTHER_RUNNER_ID, [RUNNER_TAG]),
                                *bash_call(MERGE_CMD, MERGED_64), assistant_text(WELL_FORMED)])
        self.released(out)

    def test_idle_control_no_remote_id_holds_nothing(self):
        # Catches: a session with no remote id is held on the record it cannot prove it owns.
        out = self.runner_stop([human("wake"), *self.runner(), *bash_call(MERGE_CMD, MERGED_64),
                                assistant_text(WELL_FORMED)], env_id=None)
        self.released(out)

    def test_idle_control_runner_stop_with_no_merge_opens_the_transcript_no_more_than_base(self):
        # Catches: the hold reads the own record and the transcript on every runner Stop, not only one that names a merge.
        opens = self.transcript_opens([human("wake"), *self.runner(), *bash_call("ls", "README.md"),
                                       assistant_text(WELL_FORMED)], env_id=RUNNER_ENV)
        self.assertLessEqual(opens, trs.BASE_OPENS,
                             "the Stop opened its transcript %d times; a plain Stop opens it %d times, and a runner "
                             "Stop with no merge line may add none" % (opens, trs.BASE_OPENS))

    # Round 1 review findings. Each case pins one: a merged line that another command prints, a sweep that never swept
    # or was refused, the order of calls in one message, and the correction tail on a report with its own defect.

    def test_idle_r1_merged_line_quoted_by_a_grep_holds_nothing(self):
        # Catches: a merged line that another command prints (a grep of a log) holds the runner as a merge of its own.
        self.held_on_merge(self.runner_stop([human("wake"), *self.runner(), *bash_call(MERGE_CMD, MERGED_64),
                                             assistant_text(WELL_FORMED)]))  # precondition: the merge run holds
        out = self.runner_stop([human("wake"), *self.runner(),
                                *bash_call("git log --oneline | grep merge", MERGED_64), assistant_text(WELL_FORMED)])
        self.released(out)

    def test_idle_r1_merged_line_of_another_pr_holds_nothing(self):
        # Catches: a merged line for #64 that a run for merge 65 prints holds the runner on a merge it did not make.
        self.held_on_merge(self.runner_stop([human("wake"), *self.runner(), *bash_call(MERGE_CMD, MERGED_64),
                                             assistant_text(WELL_FORMED)]))  # precondition: the merge run holds
        out = self.runner_stop([human("wake"), *self.runner(), *bash_call("merge 65 --confirm", MERGED_64),
                                assistant_text(WELL_FORMED)])
        self.released(out)

    def test_idle_r1_merge_by_path_or_quoted_path_holds(self):
        # Catches: a merge named by its path, a quoted path or a cd prefix is read as no merge, so it never holds.
        for command in ("~/.claude/bin/merge 64 --confirm", '"/opt/tools/merge" 64 --confirm',
                        "cd repo && python3 merge/merge.py 64 --confirm"):
            out = self.runner_stop([human("wake"), *self.runner(), *bash_call(command, MERGED_64),
                                    assistant_text(WELL_FORMED)])
            self.held_on_merge(out)

    def test_idle_r1_comment_that_names_the_sweep_does_not_release(self):
        # Catches: a comment whose body names the sweep command releases the merge, so its lane is never archived.
        comment = 'gh pr comment 64 --body "next: merge --idle-lanes --live live.md"'
        out = self.runner_stop([human("wake"), *self.runner(), *bash_call(MERGE_CMD, MERGED_64),
                                *bash_call(comment, IDLE_DONE), assistant_text(WELL_FORMED)])
        self.held_on_merge(out)

    def test_idle_r1_refused_sweep_does_not_release(self):
        # Catches: a sweep the hook refused counts as a sweep, so the merge is released with no lane list made.
        refusal = "PreToolUse:Bash hook error: the call was refused. To allow this act, type `override 15m`."
        out = self.runner_stop([human("wake"), *self.runner(), *bash_call(MERGE_CMD, MERGED_64),
                                *bash_call(IDLE_CMD, refusal, is_error=True), assistant_text(WELL_FORMED)])
        self.held_on_merge(out)

    def test_idle_r1_sweep_with_no_summary_does_not_release(self):
        # Catches: a sweep that dies with a traceback and no summary releases the merge, as if it had read the lanes.
        out = self.runner_stop([human("wake"), *self.runner(), *bash_call(MERGE_CMD, MERGED_64),
                                *bash_call(IDLE_CMD, "Traceback (most recent call last):"),
                                assistant_text(WELL_FORMED)])
        self.held_on_merge(out)

    def test_idle_r1_sweep_that_made_no_list_releases(self):
        # Catches: a sweep that exits 1 with "No list was made" leaves the merge held, so a runner that cannot read its lanes is stuck.
        no_list = "merge: --idle-lanes needs --live FILE, the publisher's live-work file. No list was made."
        records = [human("wake"), *self.runner(), *bash_call(MERGE_CMD, MERGED_64), assistant_text(WELL_FORMED)]
        self.held_on_merge(self.runner_stop(records))  # precondition: the merge stands before the sweep
        out = self.runner_stop([human("wake"), *self.runner(), *bash_call(MERGE_CMD, MERGED_64),
                                *bash_call(IDLE_CMD, no_list, is_error=True), assistant_text(WELL_FORMED)])
        self.released(out)

    def test_idle_r1_sweep_issued_before_the_merge_in_one_message_holds(self):
        # Catches: results are read in record order, so a sweep issued before a merge in one message is taken as after it.
        out = self.runner_stop([human("wake"), *self.runner(),
                                *one_message((IDLE_CMD, IDLE_DONE), (MERGE_CMD, MERGED_64)),
                                assistant_text(WELL_FORMED)])
        self.held_on_merge(out)

    def test_idle_r1_sweep_issued_after_the_merge_in_one_message_releases(self):
        # Catches: results are read in record order, so a sweep issued after a merge in one message does not clear it.
        self.held_on_merge(self.runner_stop([human("wake"), *self.runner(), *one_message((MERGE_CMD, MERGED_64)),
                                             assistant_text(WELL_FORMED)]))  # precondition: a lone merge in a message holds
        out = self.runner_stop([human("wake"), *self.runner(),
                                *one_message((MERGE_CMD, MERGED_64), (IDLE_CMD, IDLE_DONE)),
                                assistant_text(WELL_FORMED)])
        self.released(out)

    def test_idle_r1_held_stop_with_another_defect_keeps_the_correction_tail(self):
        # Catches: a held Stop whose report has its own defect drops the correction tail, so the defect is never sent back.
        bad_done = "\n".join(["> **Done** BUILT merge landed", "> **Deviations** none", "> **Input Needed** none",
                              "> **Next** wait"])
        out = self.runner_stop([human("wake"), *self.runner(), *bash_call("git commit -m x", "[main abc1234] x"),
                                *bash_call(MERGE_CMD, MERGED_64), assistant_text(bad_done)])
        self.held_on_merge(out)
        for tail in CORRECTION_TAILS:
            self.assertIn(tail, out["reason"], "the report has a defect of its own, but the tail %r is gone" % tail)


class InstalledCopyHoldTests(trs.StalledFixture, unittest.TestCase):
    """The hold run from an installed copy of lint/ and hooks/, with no merge/ beside it. The merge tool is reachable only
    through the global rules pointer, the way guard_merge.merge_module() finds it. Helpers come from IdleLaneHoldTests, as
    the stalled suite borrows setUp, so the cases are not copied."""

    runner = IdleLaneHoldTests.runner
    runner_stop = IdleLaneHoldTests.runner_stop
    held_on_merge = IdleLaneHoldTests.held_on_merge

    def setUp(self):
        super().setUp()
        self.installed = install_copy(self.run_dir)
        with open(os.path.join(self.cfg, "CLAUDE.md"), "w", encoding="utf-8") as handle:
            handle.write("@%s/CLAUDE.md\n" % REPO_ROOT)  # the pointer line the global rules file carries

    def installed_stop(self, records, env_id=RUNNER_ENV):
        """Stop on `records` through the installed report_guard. A run that failed open says so on stderr, and that fails."""
        path = trg.write_transcript(records, self.run_dir)
        hook = {"hook_event_name": "Stop", "session_id": trs.OWNER_SESSION, "transcript_path": path,
                "stop_hook_active": False, "cwd": self.repo}
        env = dict(os.environ, CLAUDE_CONFIG_DIR=self.cfg, HOME=self.home, CLAUDE_CODE_REMOTE_SESSION_ID=env_id)
        run = trg.run_guard(os.path.join(self.installed, "lint", "report_guard.py"), hook, env=env)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertNotIn("failed open", run.stderr,
                         "the installed hold failed open: %s" % run.stderr.strip()[-300:])
        return json.loads(run.stdout) if run.stdout.strip() else None

    def held_installed(self, records):
        """The installed copy holds the transcript. Precondition: no merge/ sits beside the copy, and the pointer's
        checkout holds the merge tool, so the hold can only read it through the pointer."""
        self.assertFalse(os.path.exists(os.path.join(self.installed, "merge")),
                         "the installed copy has a merge/ beside it, so the pointer is not what the hold reads")
        self.assertTrue(os.path.isfile(os.path.join(REPO_ROOT, "merge", "merge.py")),
                        "the pointer's checkout has no merge/merge.py to read")
        self.held_on_merge(self.installed_stop(records))

    def test_idle_install_plain_merge_is_held_by_the_installed_copy(self):
        # Catches: the merge constants are read from merge/ beside report_guard, so an installed copy fails open and never holds.
        self.held_installed([human("wake"), *self.runner(), *bash_call(MERGE_CMD, MERGED_64),
                             assistant_text(WELL_FORMED)])

    def test_idle_install_subshell_merge_after_a_cd_is_held_by_the_installed_copy(self):
        # Catches: a merge run in a subshell after a cd is read as no merge run, so the installed copy never holds it.
        self.held_installed([human("wake"), *self.runner(),
                             *bash_call("(cd repo && merge 64 --confirm)", MERGED_64), assistant_text(WELL_FORMED)])

    def test_idle_install_time_prefixed_merge_is_held_by_the_installed_copy(self):
        # Catches: a merge run that `time` prefixes is read as no merge run, so the installed copy never holds it.
        self.held_installed([human("wake"), *self.runner(),
                             *bash_call("time merge 64 --confirm", MERGED_64), assistant_text(WELL_FORMED)])

    def test_idle_install_env_prefixed_merge_is_held_by_the_installed_copy(self):
        # Catches: a merge run that `env X=1` prefixes is read as no merge run, so the installed copy never holds it.
        self.held_installed([human("wake"), *self.runner(),
                             *bash_call("env X=1 merge 64 --confirm", MERGED_64), assistant_text(WELL_FORMED)])


if __name__ == "__main__":
    unittest.main()
