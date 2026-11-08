#!/usr/bin/env python3
"""The Backlog line: a coordinator's or batch runner's report gives three counts, each read from the ledger.

Owner ruling (waiting-page item 386, merge-follows-review, pick c, saved 2026-11-07 22:25 CST): every runner and coordinator report gives
reviewed PRs waiting past one batch cycle, open PRs with no next act, and finished lanes not archived. A count not
read says `unknown`. The rules the cases pin:

- Who owes: only a session whose own newest get_session record carries cs-build:coordinator or cs-build:batch-runner,
  with no set_session_tags call after it (hooks/guard_merge.py _own_tier_proved). A lane, a triage session, an untagged
  session, a session with no own record and a session with no remote id owe nothing.
- When: every Stop whose reply has the report shape (report_shape_ok), landed or not, and the rewrite after a
  missing-report block (rewrite_problems). A correction after a Backlog block is not checked again: a count blocks once.
- What: the report holds a `Backlog:` item (at a line start, after a report label, or after "; " or ". ") with three
  fields, each a whole number or `unknown`. The labels come from hooks/shared_names.py BACKLOG_FIELDS.
- Check: counts 1 and 2 equal the newest `merge --reviewed` summary line read in the transcript after its newest
  compact_boundary, and count 3 the newest `merge --idle-lanes` summary line. A read is found by its output line, not by
  its command form. A run through verdict is read from the log its FAIL line names, at that log's last run. No read in
  the window, or a failed read (no summary line), means `unknown`. `unknown` always passes.
- The Stop starts no process and opens no network connection.

The fixture, the own-record helpers and the Stop helper come from lint/test_report_guard.py and
lint/test_report_guard_stalled.py, one home each, and are reused by name, never copied. Run with:

    python3 lint/test_report_guard_backlog.py -v
"""
import json
import os
import re
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
sys.path.insert(0, os.path.join(HERE, "..", "skills", "roadmap"))
import test_report_guard as trg  # noqa: E402  the fixture, helpers and run folder (one home)
import test_report_guard_stalled as trs  # noqa: E402  the own-record, tag and tool-call helpers (one home)
import build  # noqa: E402  the idle-lanes row label, IDLE_LANES_LINE (one home, skills/roadmap/build.py)
import shared_names  # noqa: E402  the one home of the Backlog labels, BACKLOG_FIELDS (hooks/shared_names.py)

human = trg.human
assistant_text = trg.assistant_text
tool_use_msg = trg.tool_use_msg
tool_result_msg = trg.tool_result_msg
compact_boundary = trg.compact_boundary
compact_summary = trg.compact_summary
REPORT_GUARD = trg.REPORT_GUARD
own_record = trs.own_record
tool_pair = trs.tool_pair
set_tags = trs.set_tags

OWNER_SESSION = "session_stop1"  # the hook's own session id: a missing-report block's marker is named by it
COORD_ID, COORD_ENV = "session_coord1", "cse_coord1"
BATCH_ID, BATCH_ENV = "session_batch1", "cse_batch1"
LANE_ID, LANE_ENV = "session_lane1", "cse_lane1"
TRIAGE_ID, TRIAGE_ENV = "session_triage1", "cse_triage1"
SOLO_ID, SOLO_ENV = "session_solo1", "cse_solo1"
PARENT_ID = "session_parent1"
REVIEWED_CMD = "merge --reviewed"
IDLE_CMD = "merge --idle-lanes --live roadmap-live.json"
REFUSED = "the hook tried to start a process or open a socket"

# The Backlog labels in item order. The one home is BACKLOG_FIELDS in hooks/shared_names.py. Until that name exists, the
# owner's ruling words stand in, so each case fails on its own cause, not on the missing name. The one-home case below
# fails on the missing name, and the stand-in goes once the name exists.
SPEC_BACKLOG_FIELDS = ("reviewed past one batch cycle", "no next act", "lanes to archive")
BACKLOG_FIELDS = tuple(getattr(shared_names, "BACKLOG_FIELDS", SPEC_BACKLOG_FIELDS))

# The Stop run with a process start and a socket refused: each fails the run loudly instead of passing silently.
NO_IO_CODE = (
    "import runpy, socket, subprocess, sys\n"
    "def _refuse(*args, **kwargs):\n"
    "    raise RuntimeError('%s: %%r' %% (args,))\n"
    "subprocess.Popen = _refuse\n"
    "socket.socket = _refuse\n"
    "socket.create_connection = _refuse\n"
    "sys.argv = sys.argv[1:2]\n"
    "runpy.run_path(sys.argv[0], run_name='__main__')\n"
) % REFUSED


def setUpModule():
    trg.setUpModule()  # the run folder, CLAUDE_CONFIG_DIR and the model stub, set as test_report_guard sets them


def tearDownModule():
    trg.tearDownModule()


# ---- the records a session leaves -------------------------------------------------------------------------------

def coordinator(tags=("cs-build:coordinator",), session=COORD_ID, parent=None):
    """This session's own get_session record, read with no argument."""
    return own_record(session, list(tags), parent=parent)


def read_run(command, lines, rc=0):
    """A Bash call and its result, as a transcript holds it. A nonzero exit is an error result, with its code first."""
    body = "\n".join(lines)
    if rc:
        body = "Exit code %d\n%s" % (rc, body)
    return tool_pair("Bash", {"command": command}, body, is_error=bool(rc))


def reviewed_summary(past, none=0, wait=6):
    """The last line `merge --reviewed` prints: the longest wait since a done record, the count with no next act, then the
    count of batch lines past one batch cycle."""
    return "longest wait since a done record: %dh; %s: %d; %s: %d" % (wait, BACKLOG_FIELDS[1], none, BACKLOG_FIELDS[0], past)


def reviewed_read(past, none=0, wait=6, rc=1, command=REVIEWED_CMD):
    """A `merge --reviewed` run. It exits 1 when a line is RED, and still prints its summary."""
    return read_run(command, ["#7 feat7 batch %dh" % wait, reviewed_summary(past, none, wait)], rc=rc)


def idle_summary(lanes):
    """The last line `merge --idle-lanes` prints, with the row label from its one home."""
    return "merge: %d %s. Run get_session on each alone, then archive it." % (lanes, build.IDLE_LANES_LINE)


def idle_read(lanes, command=IDLE_CMD):
    """A `merge --idle-lanes` run that read the live file."""
    return read_run(command, ["c1 lane-c1 completed", idle_summary(lanes)])


def failed_reviewed_read():
    """A `merge --reviewed` run whose pull list did not read: exit 2, and no summary line."""
    return read_run(REVIEWED_CMD, ["merge: reading pulls from GitHub failed"], rc=2)


def failed_idle_read():
    """A `merge --idle-lanes` run whose live file did not read: an unknown row, and no summary line."""
    return read_run(IDLE_CMD, ["unknown (the live read failed)"], rc=1)


def verdict_reviewed(log_path):
    """A `merge --reviewed` run through the verdict wrapper: its FAIL line names the log that holds the run's own lines."""
    return tool_pair("Bash", {"command": "~/.claude/bin/verdict merge --reviewed"},
                     "FAIL merge --reviewed rc=1 (0.3s) log=%s" % log_path, is_error=True)


def reads(past=2, none=1, lanes=3):
    """The newest reads a coordinator's report is checked against: a `merge --reviewed` run and a `merge --idle-lanes` run."""
    return [reviewed_read(past=past, none=none), idle_read(lanes=lanes)]


def backlog(past="unknown", none="unknown", lanes="unknown"):
    """A Backlog item with its three fields, in item order."""
    return "Backlog: %s %s; %s %s; %s %s" % (BACKLOG_FIELDS[0], past, BACKLOG_FIELDS[1], none, BACKLOG_FIELDS[2], lanes)


def report(line=None, next_text="wait", done_text="BUILT abc123", carry=False):
    """A report with the four labels in order. `line` is one more blockquote line, the Backlog item when a case gives one. `carry`
    adds the two compaction-carry lines, which a report after a compaction must hold."""
    lines = ["> **Done** %s" % done_text, "> **Deviations** none", "> **Input Needed** none", "> **Next** %s" % next_text]
    if line is not None:
        lines.append("> " + line)
    if carry:
        lines += ["> Recovered: none", "> Handoff gave: none"]
    return "\n".join(lines)


def landed(reply):
    """A turn that commits, then its reply."""
    return [tool_use_msg("Bash", {"command": "git commit -m x"}), tool_result_msg(), assistant_text(reply)]


class BacklogFixture(trg.SameTurnWriter):
    """test_report_guard's QuestionReachesPageTests fixture, borrowed name by name, as test_report_guard_stalled does. A case here
    reuses it and does not copy it, so a change to the shared fixture reaches this file."""

    PAGE = trg.QuestionReachesPageTests.PAGE  # named here, not aliased at module level: an alias loads its cases too
    setUp = trg.QuestionReachesPageTests.setUp
    make_repo = trg.QuestionReachesPageTests.make_repo
    stop = trg.QuestionReachesPageTests.stop

    def run_stop(self, records, env_id=COORD_ENV, stop_active=False):
        """Stop on `records` as the session env_id names, with the hook's own session id set."""
        return self.stop(records, env_id=env_id, stop_active=stop_active, session_id=OWNER_SESSION)

    def stop_without_io(self, records, env_id=COORD_ENV):
        """Stop on `records`, with a process start and a socket refused. The run must finish with no refusal printed."""
        path = trg.write_transcript(records, self.run_dir)
        hook = {"hook_event_name": "Stop", "session_id": OWNER_SESSION, "transcript_path": path,
                "stop_hook_active": False, "cwd": self.repo}
        env = dict(os.environ, CLAUDE_CONFIG_DIR=self.cfg, HOME=self.home)
        env.pop("CLAUDE_CODE_REMOTE_SESSION_ID", None)
        if env_id:
            env["CLAUDE_CODE_REMOTE_SESSION_ID"] = env_id
        run = subprocess.run([sys.executable, "-c", NO_IO_CODE, REPORT_GUARD], input=json.dumps(hook),
                             capture_output=True, text=True, timeout=15, env=env)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertNotIn(REFUSED, run.stderr, "the Stop tried a process or a connection: " + run.stderr[-400:])
        return json.loads(run.stdout) if run.stdout.strip() else None

    def write_log(self, name, runs):
        """A verdict log that holds one run per (command, lines), each under its header, as bin/verdict appends them."""
        path = os.path.join(self.run_dir, name)
        with open(path, "w", encoding="utf-8") as handle:
            for command, lines in runs:
                handle.write("=== verdict run 2026-11-07 22:00:00: %s\n" % command)
                handle.write("\n".join(lines) + "\n")
        return path

    def owed(self, out, *named):
        """The Stop was refused as a block, and the refusal names each of `named`."""
        self.assertIsNotNone(out, "the Stop was not refused: a report owed a Backlog count ended the turn")
        self.assertEqual(out.get("decision"), "block", "the Stop was not refused as a block: %r" % (out,))
        for word in named:
            self.assertIn(word, out["reason"], "the refusal does not name %r: %r" % (word, out["reason"]))

    def names_value(self, out, value):
        """The Stop was refused as a block, and the refusal names the value the read gives: a whole number, or `unknown`."""
        self.owed(out)
        self.assertRegex(out["reason"], r"(?i)(?<![\w-])%s(?![\w-])" % re.escape(str(value)),
                         "the refusal does not name the value the read gives (%s): %r" % (value, out["reason"]))

    def released(self, out):
        """The Stop was not refused as a block."""
        self.assertFalse(out and out.get("decision") == "block", "the Stop was refused with no Backlog count owed: %r" % (out,))


class BacklogCountTests(BacklogFixture, unittest.TestCase):
    """A coordinator or batch runner that owes the line: each count against its read."""

    # Owed and refused. Each is red on the current head: no Backlog check exists yet.

    def test_bk_red_coordinator_report_with_no_backlog_line_is_refused(self):
        # Catches: a coordinator's report with no Backlog line ends its turn.
        self.owed(self.run_stop([human("wake"), coordinator(), assistant_text(report())]), "Backlog")

    def test_bk_red_batch_runner_report_with_no_backlog_line_is_refused(self):
        # Catches: a batch runner's report with no Backlog line ends its turn (the second tier that owes the line).
        records = [human("wake"), coordinator(("cs-build:batch-runner",), BATCH_ID), assistant_text(report())]
        self.owed(self.run_stop(records, env_id=BATCH_ENV), "Backlog")

    def test_bk_red_landed_turn_with_no_backlog_line_is_refused(self):
        # Catches: the check runs on unlanded turns only, so a landed turn's report with no Backlog line passes.
        self.owed(self.run_stop([human("wake"), coordinator(), *landed(report())]), "Backlog")

    def test_bk_red_a_count_that_differs_from_its_read_is_refused(self):
        # Catches: a count the read does not give passes, so the report carries a number no read gave.
        cases = ((BACKLOG_FIELDS[0], backlog(past=1, none=1, lanes=3), 2),
                 (BACKLOG_FIELDS[1], backlog(past=2, none=4, lanes=3), 1),
                 (BACKLOG_FIELDS[2], backlog(past=2, none=1, lanes=0), 3))
        for field, line, expected in cases:
            with self.subTest(field=field):
                records = [human("wake"), coordinator(), *reads(), assistant_text(report(line))]
                self.names_value(self.run_stop(records), expected)

    def test_bk_red_a_number_with_no_read_in_the_window_expects_unknown(self):
        # Catches: a number with no read behind it passes. The ruling says such a count reads `unknown`.
        cases = ((backlog(past=2), "reviewed"), (backlog(none=1), "no next act"), (backlog(lanes=3), "lanes"))
        for line, field in cases:
            with self.subTest(field=field):
                self.names_value(self.run_stop([human("wake"), coordinator(), assistant_text(report(line))]), "unknown")

    def test_bk_red_a_failed_idle_read_expects_unknown_for_lanes(self):
        # Catches: an idle-lanes run that did not read (an unknown row and no summary line) passes a lanes count of 0.
        records = [human("wake"), coordinator(), reviewed_read(past=0, none=0), failed_idle_read(),
                   assistant_text(report(backlog(past=0, none=0, lanes=0)))]
        self.names_value(self.run_stop(records), "unknown")

    def test_bk_red_a_failed_reviewed_read_expects_unknown_for_its_two_counts(self):
        # Catches: a merge --reviewed run that did not read (exit 2, no summary line) passes its two counts.
        records = [human("wake"), coordinator(), failed_reviewed_read(), idle_read(lanes=2),
                   assistant_text(report(backlog(past=0, none=0, lanes=2)))]
        self.names_value(self.run_stop(records), "unknown")

    def test_bk_red_a_read_before_the_newest_compact_boundary_does_not_count(self):
        # Catches: a read from before the compaction still decides a count, so a number from a read the window no longer holds passes.
        records = [human("wake"), coordinator(), *reads(past=2, lanes=3), compact_boundary(), compact_summary(), coordinator(),
                   assistant_text(report(backlog(past=2, lanes=3), carry=True))]
        self.names_value(self.run_stop(records), "unknown")

    def test_bk_red_the_newest_read_in_the_window_decides(self):
        # Catches: the first read in the window decides, so an older summary keeps its count against a newer run.
        records = [human("wake"), coordinator(), reviewed_read(past=1), reviewed_read(past=3),
                   assistant_text(report(backlog(past=1)))]
        self.names_value(self.run_stop(records), 3)

    def test_bk_red_a_read_in_an_earlier_turn_counts_for_a_later_report(self):
        # Catches: only the current turn's reads count, so a count from an earlier read passes unchecked.
        records = [human("first"), coordinator(), reviewed_read(past=2), assistant_text("Read the ledger."),
                   human("wake"), assistant_text(report(backlog(past=0)))]
        self.names_value(self.run_stop(records), 2)

    def test_bk_red_a_verdict_failed_run_is_read_from_its_log(self):
        # Catches: a run through verdict shows only its FAIL line, so the summary in the log that line names goes unread.
        log = self.write_log("verdict-reviewed.log", [(REVIEWED_CMD, ["#7 feat7 batch 6h", reviewed_summary(past=2)])])
        records = [human("wake"), coordinator(), verdict_reviewed(log), assistant_text(report(backlog(past=0)))]
        self.names_value(self.run_stop(records), 2)

    def test_bk_red_a_verdict_log_reads_its_last_run(self):
        # Catches: the first run in a verdict log decides, so a newer run's count is not the one checked.
        log = self.write_log("verdict-two-runs.log", [(REVIEWED_CMD, [reviewed_summary(past=1)]),
                                                      (REVIEWED_CMD, [reviewed_summary(past=3)])])
        records = [human("wake"), coordinator(), verdict_reviewed(log), assistant_text(report(backlog(past=1)))]
        self.names_value(self.run_stop(records), 3)

    def test_bk_red_a_read_is_found_by_its_output_not_its_command(self):
        # Catches: a run under another command form (a direct script run, the bin wrapper) is missed, so its count goes unchecked.
        for command in ("python3 merge/merge.py --reviewed", "~/.claude/bin/merge --reviewed"):
            with self.subTest(command=command):
                records = [human("wake"), coordinator(), reviewed_read(past=2, command=command),
                           assistant_text(report(backlog(past=0)))]
                self.names_value(self.run_stop(records), 2)

    def test_bk_red_a_backlog_item_after_a_report_label_is_read(self):
        # Catches: an item after a report label is not read, so a wrong count there passes.
        records = [human("wake"), coordinator(), reviewed_read(past=2), assistant_text(report(next_text=backlog(past=0)))]
        self.names_value(self.run_stop(records), 2)

    def test_bk_red_a_backlog_item_after_a_semicolon_is_read(self):
        # Catches: an item after "; " in a report label's text is not read, so a wrong count there passes.
        records = [human("wake"), coordinator(), reviewed_read(past=2),
                   assistant_text(report(done_text="BUILT abc123; " + backlog(past=0)))]
        self.names_value(self.run_stop(records), 2)

    def test_bk_red_backlog_words_inside_a_sentence_are_no_item(self):
        # Catches: a Backlog phrase inside a sentence counts as the item, so a report that holds no item passes.
        records = [human("wake"), coordinator(), reviewed_read(past=2),
                   assistant_text(report(next_text="wait; the old Backlog: 9 count is stale"))]
        self.owed(self.run_stop(records), "Backlog")

    def test_bk_red_a_malformed_backlog_item_is_refused(self):
        # Catches: a field that is neither a whole number nor `unknown`, or an item with two fields, passes.
        lines = ("Backlog: %s many; %s 1; %s 2" % BACKLOG_FIELDS,
                 "Backlog: %s 2; %s 1" % BACKLOG_FIELDS[:2])
        for line in lines:
            with self.subTest(line=line):
                self.owed(self.run_stop([human("wake"), coordinator(), assistant_text(report(line))]), "Backlog")

    def test_bk_red_rewrite_after_a_missing_report_block_checks_the_counts(self):
        # Catches: the rewrite after a missing-report block skips the counts, so a rewritten report passes a wrong one.
        first = self.run_stop([human("wake"), coordinator(), *reads(past=2, lanes=3), *landed("All done.")])
        self.assertIsNotNone(first, "the first Stop was not refused for its missing report")  # the precondition
        self.assertIn("Send the report now", first["reason"], "the first Stop is not the missing-report block")
        rewrite = [human("wake"), coordinator(), *reads(past=2, lanes=3), *landed(report(backlog(past=0, lanes=3)))]
        self.names_value(self.run_stop(rewrite, stop_active=True), 2)

    def test_bk_red_a_correction_after_a_backlog_block_is_not_checked_again(self):
        # Catches: a count checked again on the correction blocks a second time. The ruling says a count blocks once.
        records = [human("wake"), coordinator(), reviewed_read(past=2), assistant_text(report(backlog(past=0)))]
        self.names_value(self.run_stop(records), 2)  # the precondition: the first Stop is refused
        self.released(self.run_stop(records, stop_active=True))

    # Controls: each passes on the current head too. They pin the release rules the check must keep.

    def test_bk_green_counts_that_match_their_reads_pass(self):
        records = [human("wake"), coordinator(), *reads(past=2, none=1, lanes=3),
                   assistant_text(report(backlog(past=2, none=1, lanes=3)))]
        self.released(self.run_stop(records))

    def test_bk_green_the_read_after_the_newest_compact_boundary_is_the_count(self):
        records = [human("wake"), coordinator(), reviewed_read(past=2), compact_boundary(), compact_summary(), coordinator(),
                   reviewed_read(past=5), assistant_text(report(backlog(past=5), carry=True))]
        self.released(self.run_stop(records))

    def test_bk_green_a_verdict_log_that_matches_passes(self):
        log = self.write_log("verdict-match.log", [(REVIEWED_CMD, [reviewed_summary(past=2)])])
        records = [human("wake"), coordinator(), verdict_reviewed(log), assistant_text(report(backlog(past=2)))]
        self.released(self.run_stop(records))

    def test_bk_green_unknown_passes_with_a_read_and_with_no_read(self):
        # `unknown` always passes: a count a read gives, and a count no read gives.
        self.released(self.run_stop([human("wake"), coordinator(), *reads(), assistant_text(report(backlog()))]))
        self.released(self.run_stop([human("wake"), coordinator(), assistant_text(report(backlog()))]))

    def test_bk_green_rewrite_with_the_right_counts_passes_and_the_marker_is_spent(self):
        first = self.run_stop([human("wake"), coordinator(), *reads(past=2, lanes=3), *landed("All done.")])
        self.assertIsNotNone(first, "the first Stop was not refused for its missing report")  # the precondition
        right = [human("wake"), coordinator(), *reads(past=2, lanes=3), *landed(report(backlog(past=2, lanes=3)))]
        self.released(self.run_stop(right, stop_active=True))
        wrong = [human("wake"), coordinator(), *reads(past=2, lanes=3), *landed(report(backlog(past=0, lanes=3)))]
        self.released(self.run_stop(wrong, stop_active=True))  # the marker is spent: a later rewrite is not checked

    def test_bk_green_the_missing_report_block_does_not_demand_the_backlog_line(self):
        # The report is missing, so the reply has no report shape and the Backlog check does not run.
        out = self.run_stop([human("wake"), coordinator(), *landed("All done.")])
        self.owed(out)
        self.assertNotIn("Backlog", out["reason"], "the missing-report block demands a Backlog count: %r" % (out["reason"],))

    def test_bk_green_an_unlanded_reply_with_no_report_owes_no_backlog(self):
        out = self.run_stop([human("wake"), coordinator(), *reads(), assistant_text("Status: waiting on the ledger.")])
        self.released(out)


class OweNothingTests(BacklogFixture, unittest.TestCase):
    """A session that owes no Backlog line is never refused for one. Each reply below holds counts that every read refuses,
    so a release here is the tier's doing, not the counts'."""

    def wrong(self, own, env_id):
        """A reply with three wrong counts, after the reads, under the own records `own`."""
        records = [human("wake"), *own, *reads(), assistant_text(report(backlog(past=0, none=0, lanes=0)))]
        return self.run_stop(records, env_id=env_id)

    def test_bk_green_a_lane_owes_nothing(self):
        self.released(self.wrong([own_record(LANE_ID, ["cs-build:lane"], parent=PARENT_ID)], LANE_ENV))

    def test_bk_green_a_triage_session_owes_nothing(self):
        self.released(self.wrong([own_record(TRIAGE_ID, ["cs-build:triage"])], TRIAGE_ENV))

    def test_bk_green_an_untagged_session_owes_nothing(self):
        self.released(self.wrong([own_record(SOLO_ID, ["cs-repo:o/r"])], SOLO_ENV))

    def test_bk_green_a_session_with_no_own_record_owes_nothing(self):
        self.released(self.wrong([], COORD_ENV))

    def test_bk_green_a_session_with_no_remote_id_owes_nothing(self):
        self.released(self.wrong([coordinator()], None))

    def test_bk_green_a_coordinator_tag_set_after_its_record_ends_the_proof(self):
        self.released(self.wrong([coordinator(), set_tags([COORD_ID])], COORD_ENV))

    def test_bk_green_another_sessions_coordinator_record_owes_nothing(self):
        self.released(self.wrong([own_record("session_other9", ["cs-build:coordinator"])], COORD_ENV))


class NoProcessTests(BacklogFixture, unittest.TestCase):
    """The check reads the transcript and the verdict log. It starts nothing and opens no connection."""

    def test_bk_red_the_check_starts_no_process_and_opens_no_connection(self):
        # Catches: the check reruns merge, git or gh, or opens a connection, to read the counts again. The run refuses both, and the
        # mismatched count must still block, so the whole check ran.
        log = self.write_log("verdict-no-io.log", [(REVIEWED_CMD, [reviewed_summary(past=2)])])
        records = [human("wake"), coordinator(), reviewed_read(past=2), verdict_reviewed(log),
                   assistant_text(report(backlog(past=0)))]
        self.names_value(self.stop_without_io(records), 2)


class OneHomeTests(unittest.TestCase):
    """The Backlog labels have one home."""

    def test_bk_red_the_backlog_labels_have_one_home(self):
        # Red until hooks/shared_names.py names BACKLOG_FIELDS: the three labels are read from that one home, never retyped here.
        self.assertTrue(hasattr(shared_names, "BACKLOG_FIELDS"),
                        "hooks/shared_names.py names no BACKLOG_FIELDS, so the Backlog labels have no one home")


if __name__ == "__main__":
    unittest.main()
