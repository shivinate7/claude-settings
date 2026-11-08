#!/usr/bin/env python3
"""The Backlog line: a coordinator's or batch runner's report gives three counts, each read from the ledger.

Every runner and coordinator report gives reviewed PRs waiting past one batch cycle, open PRs with no next act, and
finished lanes not archived (rule reports-backlog-counts). A count not read says `unknown`. The rules the cases pin:

- Who owes: only a session whose own newest get_session record carries cs-build:coordinator or cs-build:batch-runner,
  with no set_session_tags call after it (hooks/guard_merge.py _own_tier_proved). A lane, a triage session, an untagged
  session, a session with no own record and a session with no remote id owe nothing.
- When: every Stop whose reply has the report shape (report_shape_ok), landed or not, and the rewrite after a
  missing-report block (rewrite_problems). A correction after a Backlog block is not checked again: a count blocks once.
- What: the report holds a Backlog item (at a line start, after a report label, or after "; " or ". "), plain or with the
  colon inside the bold word, with three fields, each a whole number or `unknown`. The item word and the labels come from
  hooks/shared_names.py (BACKLOG_ITEM, BACKLOG_FIELDS).
- Check: counts 1 and 2 equal the newest `merge --reviewed` read in the transcript after its newest compact_boundary, and
  count 3 the finished-lanes line of the newest `merge --idle-lanes` read. A read is found by its output line, not by its command form. A failed run
  has no output line, so it is found by its command: a merge or merge.py token must stand before the flag. A run through
  verdict is read from the log its FAIL line names, at that log's last run. No read in the window, or a failed read, means
  `unknown`. `unknown` always passes.
- Cost: no process and no network connection. A run through verdict opens only the log of the newest run.

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
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "hooks"))
sys.path.insert(0, os.path.join(HERE, "..", "skills", "roadmap"))
import report_guard  # noqa: E402  the guard's own backlog read, called in process (lint/report_guard.py)
import shared_names  # noqa: E402  the one home of the Backlog item word and labels (hooks/shared_names.py)
import test_report_guard as trg  # noqa: E402  the fixture, helpers and run folder (one home)
import test_report_guard_stalled as trs  # noqa: E402  the own-record, tag and tool-call helpers (one home)
import build  # noqa: E402  the idle-lanes row label, IDLE_LANES_LINE (one home, skills/roadmap/build.py)
from shared_names import BACKLOG_FIELDS, BACKLOG_ITEM, FINISHED_LANES_LINE  # noqa: E402  the Backlog item word, field labels and the finished-lanes label, one home each

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
# The forms a run of the merge script takes. Each has a merge or merge.py token before its flag, the mark of a merge run.
REVIEWED_FORMS = ("python3 -I merge/merge.py --reviewed", "./merge/merge.py --reviewed", "timeout 300 merge --reviewed")
IDLE_FORMS = ("python3 -I merge/merge.py --idle-lanes --live roadmap-live.json", "./merge/merge.py --idle-lanes --live roadmap-live.json",
              "timeout 300 merge --idle-lanes --live roadmap-live.json")
GREP_REVIEWED = "grep -n -- --reviewed merge/merge.py"
GREP_IDLE = "grep -n -- --idle-lanes merge/merge.py"
LAUNCH_REVIEWED_CMD = "python3 merge/launch.py --reviewed"  # the second merge script, a run of the same ledger
MERGE_REVIEWED_CMD = "python3 merge/merge.py --reviewed"

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


def idle_summary(archive):
    """The archive summary `merge --idle-lanes` prints after its list, with the row label from its one home."""
    return "merge: %d %s. Run get_session on each alone, then archive it." % (archive, build.IDLE_LANES_LINE)


def finished_line(lanes):
    """The finished-lanes line `merge --idle-lanes` prints after the archive summary: the count the third Backlog field reads."""
    return "merge: %d %s." % (lanes, FINISHED_LANES_LINE)


def finished_unknown_line(why="the live file has no sessions list"):
    """The unknown form of the finished-lanes line, with its reason."""
    return "merge: %s unknown (%s)." % (FINISHED_LANES_LINE, why)


def idle_read(lanes, archive=1, command=IDLE_CMD):
    """A `merge --idle-lanes` run that read the live file. It prints its archive list and summary (`archive` lanes), then the
    finished-lanes line (`lanes`). The two counts differ, so a guard that reads the archive summary as the third field fails."""
    return read_run(command, ["c1 lane-c1 completed", idle_summary(archive), finished_line(lanes)])


def archive_only_read(archive=3, command=IDLE_CMD):
    """A `merge --idle-lanes` run that printed its archive summary and no finished-lanes line."""
    return read_run(command, ["c1 lane-c1 completed", idle_summary(archive)])


def unknown_finished_read(archive=1, command=IDLE_CMD):
    """A `merge --idle-lanes` run whose finished-lanes line reads unknown, beside a readable archive summary."""
    return read_run(command, ["c1 lane-c1 completed", idle_summary(archive), finished_unknown_line()])


def failed_reviewed_read(command=REVIEWED_CMD):
    """A `merge --reviewed` run whose pull list did not read: exit 2, and no summary line."""
    return read_run(command, ["merge: reading pulls from GitHub failed"], rc=2)


def failed_idle_read(command=IDLE_CMD):
    """A `merge --idle-lanes` run whose live file did not read: an unknown row, and no summary line."""
    return read_run(command, ["unknown (the live read failed)"], rc=1)


def verdict_reviewed(log_path):
    """A `merge --reviewed` run through the verdict wrapper: its FAIL line names the log that holds the run's own lines."""
    return tool_pair("Bash", {"command": "~/.claude/bin/verdict merge --reviewed"},
                     "FAIL merge --reviewed rc=1 (0.3s) log=%s" % log_path, is_error=True)


def verdict_idle(log_path):
    """A `merge --idle-lanes` run through the verdict wrapper: its FAIL line names the log that holds the run's own lines."""
    return tool_pair("Bash", {"command": "~/.claude/bin/verdict " + IDLE_CMD},
                     "FAIL merge --idle-lanes --live roadmap-live.json rc=1 (0.3s) log=%s" % log_path, is_error=True)


def reads(past=2, none=1, lanes=3):
    """The newest reads a coordinator's report is checked against: a `merge --reviewed` run and a `merge --idle-lanes` run."""
    return [reviewed_read(past=past, none=none), idle_read(lanes=lanes)]


def backlog(past="unknown", none="unknown", lanes="unknown", bold=False):
    """A Backlog item with its three fields, in item order. `bold` puts the colon inside the bold word, as **Done:** reads."""
    word = "**%s:**" % BACKLOG_ITEM if bold else "%s:" % BACKLOG_ITEM
    return "%s %s %s; %s %s; %s %s" % (word, BACKLOG_FIELDS[0], past, BACKLOG_FIELDS[1], none, BACKLOG_FIELDS[2], lanes)


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


def flat(records):
    """The records of a transcript, with each helper's list of records spread into its place. A helper such as coordinator() or
    reviewed_read() returns a list, and a list written as one line would hide its records from the transcript reader."""
    out = []
    for item in records:
        out.extend(flat(item) if isinstance(item, list) else [item])
    return out


class BacklogFixture(trg.SameTurnWriter):
    """test_report_guard's QuestionReachesPageTests fixture, borrowed name by name, as test_report_guard_stalled does. A case here
    reuses it and does not copy it, so a change to the shared fixture reaches this file."""

    PAGE = trg.QuestionReachesPageTests.PAGE  # named here, not aliased at module level: an alias loads its cases too
    setUp = trg.QuestionReachesPageTests.setUp
    make_repo = trg.QuestionReachesPageTests.make_repo
    stop = trg.QuestionReachesPageTests.stop

    def run_stop(self, records, env_id=COORD_ENV, stop_active=False):
        """Stop on `records` as the session env_id names, with the hook's own session id set."""
        return self.stop(flat(records), env_id=env_id, stop_active=stop_active, session_id=OWNER_SESSION)

    def stop_without_io(self, records, env_id=COORD_ENV):
        """Stop on `records`, with a process start and a socket refused. The run must finish with no refusal printed."""
        path = trg.write_transcript(flat(records), self.run_dir)
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

    def names_unknown_for(self, out, label):
        """The Stop was refused as a block, and the clause that names `label` in the refusal says `unknown`, in either order.
        A refusal for another cause names no such clause."""
        self.owed(out)
        name = re.escape(label)
        self.assertRegex(out["reason"], r"(?i)(?:%s[^;.<]*\bunknown\b|\bunknown\b[^;.<]*%s)" % (name, name),
                         "the refusal does not say unknown for %r: %r" % (label, out["reason"]))

    def released(self, out, cause=""):
        """The Stop was not refused as a block. `cause` names what a refusal would mean, when the case gives one."""
        message = "the Stop was refused with no Backlog count owed: %r" % (out,)
        self.assertFalse(out and out.get("decision") == "block", ("%s; " % cause if cause else "") + message)


class BacklogCountTests(BacklogFixture, unittest.TestCase):
    """A coordinator or batch runner that owes the line: each count against its read."""

    # Owed and refused: each case names the refusal the check must give.

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
        cases = ((backlog(past=2), BACKLOG_FIELDS[0]), (backlog(none=1), BACKLOG_FIELDS[1]), (backlog(lanes=3), BACKLOG_FIELDS[2]))
        for line, field in cases:
            with self.subTest(field=field):
                self.names_unknown_for(self.run_stop([human("wake"), coordinator(), assistant_text(report(line))]), field)

    def test_bk_red_a_failed_idle_read_expects_unknown_for_lanes(self):
        # Catches: an idle-lanes run that did not read (an unknown row and no summary line) passes a lanes count of 0.
        records = [human("wake"), coordinator(), reviewed_read(past=0, none=0), failed_idle_read(),
                   assistant_text(report(backlog(past=0, none=0, lanes=0)))]
        self.names_unknown_for(self.run_stop(records), BACKLOG_FIELDS[2])

    def test_bk_red_the_third_count_reads_the_finished_line_not_the_archive_summary(self):
        # Catches: the third count reads the archive list's summary, so a count of the lanes to archive passes as the finished count.
        # The control is the finished line's own count, which passes.
        self.released(self.run_stop([human("wake"), coordinator(), idle_read(lanes=3, archive=1),
                                     assistant_text(report(backlog(lanes=3)))]))
        records = [human("wake"), coordinator(), idle_read(lanes=3, archive=1), assistant_text(report(backlog(lanes=1)))]
        self.names_value(self.run_stop(records), 3)

    def test_bk_red_an_archive_summary_with_no_finished_line_expects_unknown_for_the_third_count(self):
        # Catches: a run that printed only its archive summary (the run before the count) gives the third count a number.
        # The control is the same count from a run with its finished line, which passes.
        self.released(self.run_stop([human("wake"), coordinator(), idle_read(lanes=3), assistant_text(report(backlog(lanes=3)))]))
        records = [human("wake"), coordinator(), archive_only_read(archive=3), assistant_text(report(backlog(lanes=3)))]
        self.names_unknown_for(self.run_stop(records), FINISHED_LANES_LINE)

    def test_bk_red_an_older_finished_line_does_not_stand_in_for_a_newer_run_without_one(self):
        # Catches: the guard falls back to an older run's finished line when the newest run has none, so a stale count passes.
        records = [human("wake"), coordinator(), idle_read(lanes=3), archive_only_read(archive=1),
                   assistant_text(report(backlog(lanes=3)))]
        self.names_unknown_for(self.run_stop(records), FINISHED_LANES_LINE)

    def test_bk_red_an_unknown_finished_line_expects_unknown_for_the_third_count(self):
        # Catches: the unknown form of the finished line is read as a count, so a number beside it passes.
        records = [human("wake"), coordinator(), unknown_finished_read(), assistant_text(report(backlog(lanes=3)))]
        self.names_unknown_for(self.run_stop(records), FINISHED_LANES_LINE)

    def test_bk_red_a_verdict_log_of_an_idle_run_reads_its_finished_line(self):
        # Catches: a verdict-logged idle run is read for its archive summary, so the finished count in its log goes unchecked.
        # The control is the finished count the log holds, which passes.
        log = self.write_log("verdict-idle.log", [(IDLE_CMD, ["c1 lane-c1 completed", idle_summary(1), finished_line(3)])])
        self.released(self.run_stop([human("wake"), coordinator(), verdict_idle(log), assistant_text(report(backlog(lanes=3)))]))
        records = [human("wake"), coordinator(), verdict_idle(log), assistant_text(report(backlog(lanes=1)))]
        self.names_value(self.run_stop(records), 3)

    def test_bk_red_a_failed_reviewed_read_expects_unknown_for_its_two_counts(self):
        # Catches: a merge --reviewed run that did not read (exit 2, no summary line) passes its two counts.
        records = [human("wake"), coordinator(), failed_reviewed_read(), idle_read(lanes=2),
                   assistant_text(report(backlog(past=0, none=0, lanes=2)))]
        out = self.run_stop(records)
        self.names_unknown_for(out, BACKLOG_FIELDS[0])
        self.names_unknown_for(out, BACKLOG_FIELDS[1])

    def test_bk_red_a_read_before_the_newest_compact_boundary_does_not_count(self):
        # Catches: a read from before the compaction still decides a count, so a number from a read the window no longer holds passes.
        records = [human("wake"), coordinator(), *reads(past=2, lanes=3), compact_boundary(), compact_summary(), coordinator(),
                   assistant_text(report(backlog(past=2, lanes=3), carry=True))]
        out = self.run_stop(records)
        self.names_unknown_for(out, BACKLOG_FIELDS[0])
        self.names_unknown_for(out, BACKLOG_FIELDS[2])

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
                   assistant_text(report(next_text="wait; the old %s: 9 count is stale" % BACKLOG_ITEM))]
        self.owed(self.run_stop(records), "Backlog")

    def test_bk_red_a_malformed_backlog_item_is_refused(self):
        # Catches: a field that is neither a whole number nor `unknown`, or an item with two fields, passes.
        lines = ("%s: %s many; %s 1; %s 2" % ((BACKLOG_ITEM,) + BACKLOG_FIELDS),
                 "%s: %s 2; %s 1" % ((BACKLOG_ITEM,) + BACKLOG_FIELDS[:2]))
        for line in lines:
            with self.subTest(line=line):
                self.owed(self.run_stop([human("wake"), coordinator(), assistant_text(report(line))]), "Backlog")

    def test_bk_red_a_bold_backlog_item_that_matches_its_read_passes(self):
        # Catches: a bold item, with the colon inside the bold word as **Done:** reads, is refused as malformed though its counts match.
        records = [human("wake"), coordinator(), *reads(past=2, none=1, lanes=3),
                   assistant_text(report(backlog(past=2, none=1, lanes=3, bold=True)))]
        self.released(self.run_stop(records))

    def test_bk_red_a_bold_backlog_item_that_differs_from_its_read_is_refused(self):
        # Catches: a bold item is refused as malformed without its counts checked, so a count the read does not give goes unnamed.
        records = [human("wake"), coordinator(), *reads(past=2, none=1, lanes=3),
                   assistant_text(report(backlog(past=0, none=1, lanes=3, bold=True)))]
        self.names_value(self.run_stop(records), 2)

    def test_bk_red_a_failed_reviewed_read_in_any_form_expects_unknown(self):
        # Catches: a failed merge --reviewed run in a form the guard does not take for a run (a script path after python3 -I, a
        # relative path, a timeout wrapper) is passed over, so the good read before it still decides and its number passes.
        for command in REVIEWED_FORMS:
            with self.subTest(command=command):
                good = [human("wake"), coordinator(), reviewed_read(past=2, none=1)]
                self.released(self.run_stop(good + [assistant_text(report(backlog(past=2, none=1)))]))  # the precondition: the good read counts
                out = self.run_stop(good + [failed_reviewed_read(command), assistant_text(report(backlog(past=2, none=1)))])
                self.names_unknown_for(out, BACKLOG_FIELDS[0])
                self.names_unknown_for(out, BACKLOG_FIELDS[1])

    def test_bk_red_a_failed_idle_read_in_any_form_expects_unknown_for_lanes(self):
        # Catches: a failed merge --idle-lanes run in a form the guard does not take for a run is passed over, so the lane count of
        # the good read before it still passes.
        for command in IDLE_FORMS:
            with self.subTest(command=command):
                good = [human("wake"), coordinator(), idle_read(lanes=3)]
                self.released(self.run_stop(good + [assistant_text(report(backlog(lanes=3)))]))  # the precondition: the good read counts
                out = self.run_stop(good + [failed_idle_read(command), assistant_text(report(backlog(lanes=3)))])
                self.names_unknown_for(out, BACKLOG_FIELDS[2])

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

    # Controls: each is released. They pin the release rules the check must keep.

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

    def test_bk_green_a_grep_of_the_merge_script_does_not_reset_a_read(self):
        # Control: a grep that names the merge script after its flag is no merge run, so a newer grep leaves the read before it in charge.
        cases = ((reviewed_read(past=2, none=1), GREP_REVIEWED, "merge/merge.py:1204:    if args.reviewed:", backlog(past=2, none=1)),
                 (idle_read(lanes=3), GREP_IDLE, "merge/merge.py:1311:    if args.idle_lanes:", backlog(lanes=3)))
        for read, command, line, item in cases:
            with self.subTest(command=command):
                records = [human("wake"), coordinator(), read, read_run(command, [line]), assistant_text(report(item))]
                self.released(self.run_stop(records))


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


def verdict_pass(command):
    """A run through verdict that passed. bin/verdict prints no log path on PASS, only the verdict line."""
    return tool_pair("Bash", {"command": "~/.claude/bin/verdict " + command}, "PASS %s (0.3s)" % command)


class VerdictRunTests(BacklogFixture, unittest.TestCase):
    """A run through verdict. A PASS names no log, so its read is the verdict line itself. A FAIL names its log, and that log is read."""

    def test_bk_red_a_pass_reviewed_verdict_reads_both_counts_zero(self):
        # Catches: a PASS verdict of merge --reviewed (no log, no RED line) is read as no read, so its two counts do not read 0.
        records = [human("wake"), coordinator(), verdict_pass(REVIEWED_CMD), assistant_text(report(backlog(past=2)))]
        self.names_value(self.run_stop(records), 0)

    def test_bk_green_a_pass_reviewed_verdict_with_zero_counts_passes(self):
        # Control: the same PASS read with its two counts at 0 is released.
        records = [human("wake"), coordinator(), verdict_pass(REVIEWED_CMD), assistant_text(report(backlog(past=0, none=0)))]
        self.released(self.run_stop(records))

    def test_bk_red_a_pass_idle_verdict_reads_unknown(self):
        # Catches: a PASS verdict of merge --idle-lanes names no log, so the lane count it gives is unread and must say unknown.
        # The idle read before it is older, so the PASS run is the newest read and its count is the one checked.
        records = [human("wake"), coordinator(), idle_read(lanes=3), verdict_pass(IDLE_CMD),
                   assistant_text(report(backlog(lanes=3)))]
        self.names_unknown_for(self.run_stop(records), BACKLOG_FIELDS[2])


class VerdictReadCostTests(BacklogFixture, unittest.TestCase):
    """The reads a verdict run costs. The check opens the log of the newest run of a command, and no other."""

    def opened_reads(self, records):
        """(backlog_reads' result, the log paths it opened). The guard's log opener is counted in process, as the check calls it."""
        opened = []
        real = report_guard._verdict_log_text

        def counting(path):
            opened.append(path)
            return real(path)

        with mock.patch.object(report_guard, "_verdict_log_text", counting):
            result = report_guard.backlog_reads(flat(records))
        return result, opened

    def test_bk_red_five_failed_verdict_runs_open_only_the_newest_log(self):
        # Catches: each failed verdict run in the window has its log opened, so five runs cost five reads where the newest decides.
        logs = [self.write_log("verdict-run-%d.log" % n, [(REVIEWED_CMD, [reviewed_summary(past=n)])]) for n in range(5)]
        records = [human("wake"), coordinator(), [verdict_reviewed(log) for log in logs]]
        result, opened = self.opened_reads(records)
        self.assertEqual(result[0], (4, 0), "the newest run's count is not the one read: %r" % (result,))  # the scope: the newest run
        self.assertEqual(opened, logs[-1:], "the guard opened %d logs for five runs; it reads the newest run's log only" % len(opened))

    def test_bk_green_one_failed_verdict_run_opens_its_log(self):
        # Control: the one run's log is opened and its count read, so the counter sees the read the check must count.
        log = self.write_log("verdict-one.log", [(REVIEWED_CMD, [reviewed_summary(past=2)])])
        result, opened = self.opened_reads([human("wake"), coordinator(), verdict_reviewed(log)])
        self.assertEqual(result[0], (2, 0), "the one run's count is not read: %r" % (result,))
        self.assertEqual(opened, [log], "the one run's log is not the one opened: %r" % (opened,))


class LedgerReadTests(BacklogFixture, unittest.TestCase):
    """What counts as a read, and how the owed check reads the own record. A run of either merge script is a ledger read. A PASS
    line reads only the command it names. The owed check reads the own record once, for both tiers."""

    def test_bk_red_a_launch_script_reviewed_run_is_a_read(self):
        # Catches: a run of merge/launch.py --reviewed is no ledger read, so its summary counts go unread and a matching number is refused.
        records = [human("wake"), coordinator(), reviewed_read(past=2, none=1, command=LAUNCH_REVIEWED_CMD),
                   assistant_text(report(backlog(past=2, none=1)))]
        self.released(self.run_stop(records), "merge/launch.py --reviewed is not read as a ledger run")

    def test_bk_green_a_merge_script_reviewed_run_is_a_read(self):
        # Control: the same counts from merge/merge.py --reviewed are released, so the refusal above is the launcher's alone.
        records = [human("wake"), coordinator(), reviewed_read(past=2, none=1, command=MERGE_REVIEWED_CMD),
                   assistant_text(report(backlog(past=2, none=1)))]
        self.released(self.run_stop(records))

    def test_bk_red_a_pass_of_another_command_in_one_call_is_no_reviewed_read(self):
        # Catches: the PASS line of ./run.sh, in the call that also runs merge --reviewed, is read as that merge run's PASS. So a 0
        # from a merge output with no summary passes unread. A PASS line reads only the command it names.
        call = read_run("verdict ./run.sh; merge --reviewed", ["PASS ./run.sh (0.3s)", "#7 feat7 batch 6h"])
        records = [human("wake"), coordinator(), call, assistant_text(report(backlog(past=0, none=0)))]
        out = self.run_stop(records)
        self.assertIsNotNone(out, "the PASS line of ./run.sh was read as the merge run's PASS, so its zero counts passed unread")
        self.names_unknown_for(out, BACKLOG_FIELDS[0])
        self.names_unknown_for(out, BACKLOG_FIELDS[1])

    def owed_check_reads(self, tags, session, env_id):
        """(the owed check's refusal, the own-record reads it made) for a report with no Backlog line. The check runs in process,
        as the Stop calls it, and the reads are counted where the check calls them."""
        import guard_merge  # hooks/guard_merge.py, on the path the header of this file sets
        records = flat([human("wake"), coordinator(tags, session)])
        hook = {"transcript_path": trg.write_transcript(records, self.run_dir), "session_id": OWNER_SESSION}
        counted = []
        real = guard_merge._own_session_read

        def counting(transcript, own_id, created=False):
            counted.append(own_id)
            return real(transcript, own_id, created)

        with mock.patch.dict(os.environ, {"CLAUDE_CODE_REMOTE_SESSION_ID": env_id}), \
                mock.patch.object(guard_merge, "_own_session_read", counting):
            problem = report_guard.backlog_problem(hook, records, report())
        return problem or "", counted

    def test_bk_red_a_batch_runner_check_reads_the_own_record_once(self):
        # Catches: the owed check reads the own record once for each tier, so a batch runner (the second tier) costs two reads of one
        # report. One read of the record tests both tiers.
        problem, counted = self.owed_check_reads(("cs-build:batch-runner",), BATCH_ID, BATCH_ENV)
        self.assertIn(BACKLOG_ITEM, problem, "the batch runner was not owed the Backlog line: the check did not refuse, so no read count applies")
        self.assertEqual(len(counted), 1, "the owed check read the own record %d times for one report, not once" % len(counted))

    def test_bk_green_a_coordinator_check_reads_the_own_record_once(self):
        # Control: a coordinator is the first tier, so one read decides it on both forms. The counter sees that one read.
        problem, counted = self.owed_check_reads(("cs-build:coordinator",), COORD_ID, COORD_ENV)
        self.assertIn(BACKLOG_ITEM, problem, "the coordinator was not owed the Backlog line: the check did not refuse, so no read count applies")
        self.assertEqual(len(counted), 1, "the owed check read the own record %d times for a coordinator, not once" % len(counted))


class ItemWordTests(unittest.TestCase):
    """The Backlog item word has one home beside the field labels, and the guard reads that word."""

    def test_bk_red_the_item_word_is_a_constant_beside_the_fields(self):
        # Catches: the item word is a literal in the guard or in the report writer, so it has no one home beside BACKLOG_FIELDS.
        self.assertEqual(getattr(shared_names, "BACKLOG_ITEM", None), "Backlog",
                         "hooks/shared_names.py does not define BACKLOG_ITEM, so the item word has no one home beside BACKLOG_FIELDS")

    def test_bk_red_the_third_field_is_the_finished_lanes_label(self):
        # Catches: the third Backlog field still names the archive list, so the count it reads is the archive summary's.
        self.assertEqual(BACKLOG_FIELDS[2], FINISHED_LANES_LINE,
                         "the third Backlog field is %r, not the finished-lanes label" % (BACKLOG_FIELDS[2],))

    def test_bk_red_the_finished_lanes_label_is_a_constant_with_its_text(self):
        # Catches: the constant in hooks/shared_names.py reads other text than the finished-lanes label. A missing constant fails
        # the import at the top of this module, so only its text is pinned here.
        self.assertEqual(getattr(shared_names, "FINISHED_LANES_LINE", None), "finished lanes not archived",
                         "hooks/shared_names.py does not define FINISHED_LANES_LINE as the finished-lanes label's text")

    def test_bk_green_the_guard_reads_an_item_written_with_the_constant(self):
        # Control: a block written with the constant reads its three counts, so the word the report writer uses is the word the guard reads.
        block = "%s: %s 1; %s 2; %s 3" % ((BACKLOG_ITEM,) + BACKLOG_FIELDS)
        self.assertEqual(report_guard._backlog_item(block), (True, [1, 2, 3]))


if __name__ == "__main__":
    unittest.main()
