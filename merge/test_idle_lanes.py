#!/usr/bin/env python3
"""Fixture suite for `merge --idle-lanes --live FILE` (merge/merge.py), the reader of the roadmap's idle lanes.

Run: python3 merge/test_idle_lanes.py

WHAT IT PROVES. The command prints one line per lane to archive, then one `hold (...)` line per idle lane that a hold
reason keeps from archiving now, then one summary line that counts both. A hold line is never archived. Its reasons:
no cs-step tag; a step off the record branch with no Step trailer on main; or a step still doing under the lane and
not landed on main. A waiting lane prints no line. A whole-read failure prints one `unknown (` line and exits 1. It
takes its steps, marks and repo name from the checkout, as the roadmap build does. It stands alone: no other flag, and
no merge role in a cloud session. A missing --live file exits 1 and prints no summary, so an unread list never reads
as an empty one. A session whose id is in keepSessions prints no line and is not counted; a keepSessions that is not a
list, or whose entry has no id, reads as unknown, never as an empty keep list. A padded keepSessions id still skips its
session. A non-archived session whose unarchived_epoch is an int above 0 prints one hold line, never a lane line, unless
it waits: a waiting lane prints no line, unarchived or not. A working session prints no line whatever its epoch. An
unarchived_epoch that is a bool, is not an int, or is negative, reads the whole list as unknown.

Each case runs merge.py as a subprocess in a roadmap fixture checkout, the way bin/merge runs it. The fixture is the
roadmap suite's make_repo (skills/roadmap/test_build.py), imported and not copied.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
MERGE = HERE / "merge.py"
sys.path.insert(0, str(HERE.parent / "skills" / "roadmap"))
sys.path.insert(1, str(HERE.parent / "lint"))
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per test run (lint/_test_temp.py)
import test_build as roadmap  # noqa: E402  the roadmap fixture: make_repo, session_row, iso_ago (one home)

REPO = "cs-repo:owner/fixture"
SUMMARY_ONE = "merge: 1 lanes to archive. Run get_session on each alone, then archive it."
SUMMARY_ZERO = "merge: 0 lanes to archive. Run get_session on each alone, then archive it."
SUMMARY_LINE = re.compile(r"^merge: \d+ lanes to archive\b", re.M)
ZERO_LINE = re.compile(r"^merge: 0 lanes to archive\.", re.M)
HELD_ONE = "merge: 0 lanes to archive, 1 held. Run get_session on each lane line alone, then archive it; never archive a hold line."
MIXED = "merge: 1 lanes to archive, 1 held. Run get_session on each lane line alone, then archive it; never archive a hold line."
# The hold line the CLI prints for a doing step under a lane. It pins the CLI's output on its own, as the summary lines do.
DOING_HOLD = "hold (step %s still doing under this lane; set the step's status to todo or done; lane %s)"

# Made in setUpModule, not at import, so a helper that imports this file leaks no folder.
RUN_FOLDER = None


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


def lane(sid, step, bucket=roadmap.BUCKET_COMPLETED, status="SESSION_STATUS_IDLE", **extra):
    """A lane row of this repo. step=None leaves out the cs-step tag. `extra` adds keys to the row, such as unarchived_epoch."""
    step_tags = ("cs-step:" + step,) if step else ()
    row = roadmap.session_row(sid, status, "cs-build:lane", *step_tags, REPO, status_bucket=bucket)
    row.update(extra)
    return row


class IdleLanesCli(unittest.TestCase):
    """merge --idle-lanes against one roadmap fixture checkout whose origin is owner/fixture. c1 and c2 are done."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=RUN_FOLDER)
        done = {"status": "done"}
        self.repo = roadmap.make_repo(self.tmp.name, steps={"c1": dict(roadmap.STEP, order=1, **done),
                                                            "c2": dict(roadmap.STEP, order=2, **done)})
        roadmap.git(self.repo, "remote", "add", "origin", "git@github.com:owner/fixture.git")
        self.live = pathlib.Path(self.tmp.name) / "live.json"

    def tearDown(self):
        self.tmp.cleanup()

    def publish(self, sessions, read_at=None, keep=None, pulls=(), items=()):
        """Write the --live file. Its readAt is five minutes old by default. `keep` is the file's keepSessions value, written
        only when given, so a case can name a value that is not a list. `pulls` and `items` are the file's pulls and items rows."""
        value = {"readAt": read_at or roadmap.iso_ago(5), "threads": [], "pulls": list(pulls), "items": list(items),
                 "sessions": list(sessions)}
        if keep is not None:
            value["keepSessions"] = keep
        self.live.write_text(json.dumps(value), encoding="utf-8")

    def commit_step(self, sid, step):
        """Write steps/<sid>.json on the fixture's record branch and commit it."""
        (self.repo / "roadmap" / "data" / "steps" / (sid + ".json")).write_text(json.dumps(step), encoding="utf-8")
        roadmap.git(self.repo, "add", "-A")
        roadmap.git(self.repo, "commit", "-q", "-m", "step " + sid)

    def run_merge(self, *argv, extra_env=None):
        """(exit code, stdout, stderr) of `merge.py <argv>`, run in the fixture checkout."""
        env = _test_git.apply({**os.environ, **roadmap.GIT_ENV, **(extra_env or {})})
        done = subprocess.run([sys.executable, str(MERGE), *argv], cwd=str(self.repo), capture_output=True,
                              text=True, env=env)
        return done.returncode, done.stdout, done.stderr

    def test_prints_each_idle_lane_then_the_summary_line(self):
        self.publish([lane("session_a", "c1"),
                      lane("session_b", "c2", bucket=roadmap.BUCKET_WORKING, status="SESSION_STATUS_RUNNING")])
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual(code, 0, err)
        lines = out.splitlines()
        self.assertEqual(lines[-1:], [SUMMARY_ONE], out)
        self.assertEqual([line.split(" ", 1)[0] for line in lines[:-1]], ["session_a"], out)

    def test_no_idle_lane_prints_a_zero_summary_and_no_entry(self):
        self.publish([lane("session_b", "c2", bucket=roadmap.BUCKET_WORKING, status="SESSION_STATUS_RUNNING")])
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines(), [SUMMARY_ZERO], out)

    def test_only_hold_lines_print_exit_0_and_a_summary_that_counts_the_holds(self):
        # The step is not on the record branch and main holds no Step trailer for it, so the lane is held and not listed.
        self.publish([lane("session_orphan", "ghost")])
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual(code, 0, "held lanes alone exit %d, so a caller reads them as an unread list: stderr %r" % (code, err))
        lines = out.splitlines()
        self.assertEqual(len(lines), 2, out)
        self.assertTrue(lines[0].startswith("hold (") and lines[0].endswith("; lane session_orphan)"), out)
        self.assertIn("ghost", lines[0])
        self.assertEqual(lines[1], HELD_ONE, out)

    def test_lane_with_no_cs_step_prints_a_hold_line_and_exit_0(self):
        self.publish([lane("session_nostep", None)])
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual(code, 0, err)
        lines = out.splitlines()
        self.assertEqual(len(lines), 2, out)
        self.assertTrue(lines[0].startswith("hold (") and lines[0].endswith("; lane session_nostep)"), out)
        self.assertIn("no cs-step tag", lines[0])
        self.assertEqual(lines[1], HELD_ONE, out)

    def test_archive_lines_and_hold_lines_are_counted_together(self):
        # The control is session_a, listed on c1. The held lane counts as held, never as a lane to archive.
        self.publish([lane("session_a", "c1"), lane("session_orphan", "ghost")])
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual(code, 0, err)
        lines = out.splitlines()
        self.assertIn("session_a (c1; topic -)", lines, out)
        self.assertEqual(sum(line.startswith("hold (") for line in lines), 1, out)
        self.assertEqual(lines[-1:], [MIXED], out)

    def test_empty_record_exits_1_with_one_unknown_line_and_no_summary(self):
        # No step file on the record branch means no lane can be judged. The list reads unknown and exits 1, so a caller
        # never reads it as an empty list.
        roadmap.git(self.repo, "rm", "-rq", "roadmap/data/steps")
        roadmap.git(self.repo, "commit", "-q", "-m", "drop every step")
        self.publish([lane("session_x", "x")])
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual(out.splitlines(), ["unknown (the record branch has no steps)"], "out: %r, err: %r" % (out, err))
        self.assertEqual(code, 1, "an empty record exits %d, so a caller reads the list as read: %s" % (code, err))
        self.assertNotRegex(out, SUMMARY_LINE)

    def test_stale_live_file_prints_one_unknown_line_and_no_empty_summary(self):
        self.publish([lane("session_a", "c1")], read_at=roadmap.iso_ago(120))
        _, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        lines = out.splitlines()
        self.assertTrue(any(line.startswith("unknown (") for line in lines), "out: %r, err: %r" % (out, err))
        self.assertFalse(any(line.startswith("session_a") for line in lines), out)
        self.assertNotRegex(out, ZERO_LINE)

    def test_missing_live_flag_exits_1_and_prints_no_summary_line(self):
        code, out, err = self.run_merge("--idle-lanes")
        self.assertEqual(code, 1, "exit %d, stderr: %s" % (code, err))
        self.assertNotRegex(out, SUMMARY_LINE)

    def test_idle_lanes_stands_alone_with_another_flag(self):
        self.publish([lane("session_a", "c1")])
        for extra in (["--reviewed"], ["7"]):
            with self.subTest(extra=extra):
                code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live), *extra)
                self.assertEqual(code, 2, err)
                self.assertIn("--idle-lanes stands alone", err)

    def test_every_entry_unknown_exits_1_with_no_summary(self):
        # The control is a readable file: its lane is listed and the command exits 0. An unread file is the whole list
        # unknown, so the command must exit 1, or a caller reads the exit code as "no lanes".
        self.publish([lane("session_a", "c1")])
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual(code, 0, err)
        code, out, err = self.run_merge("--idle-lanes", "--live", os.devnull)
        self.assertTrue(any(line.startswith("unknown (") for line in out.splitlines()), "out: %r, err: %r" % (out, err))
        self.assertEqual(code, 1, "every entry unknown exits %d, so an unread list reads as success" % code)
        self.assertNotRegex(out, SUMMARY_LINE)

    def test_unreadable_main_exits_1_with_one_unknown_line_and_no_summary(self):
        # The control is the same lane with main read: it is listed, the summary says 1, and the command exits 0. With
        # main renamed away, no step can be read as landed, so the one unknown line carries the failure and the command
        # exits 1 with no summary.
        self.publish([lane("session_a", "c1")])
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual((code, out.splitlines()[-1:]), (0, [SUMMARY_ONE]), "out: %r, err: %r" % (out, err))
        roadmap.git(self.repo, "branch", "-m", "main", "trunk")
        self.assertIsNone(roadmap.build.main_ref(self.repo, "main"), "the fixture must make main unreadable")
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertTrue(any(line.startswith("unknown (") for line in out.splitlines()),
                        "an unreadable main prints no unknown line: out: %r, err: %r" % (out, err))
        self.assertEqual(code, 1, "an unreadable main exits %d, so a caller reads the list as read" % code)
        self.assertNotRegex(out, SUMMARY_LINE)

    def test_idle_lanes_needs_no_merge_role_in_a_cloud_session(self):
        self.publish([lane("session_a", "c1")])
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live),
                                        extra_env={"CLAUDE_CODE_REMOTE": "true"})
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines()[-1:], [SUMMARY_ONE], out)

    def test_a_doing_step_under_a_completed_lane_prints_a_hold_line_and_counts_it_held(self):
        # The control is session_a with nothing under it: it is listed. Then c3 is doing under session_a, whose own step
        # c1 is done. The lane is held, not listed: its hold line names c3, and the summary counts one held lane and no
        # lane to archive.
        self.publish([lane("session_a", "c1")])
        _, before, _ = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual(before.splitlines()[-1:], [SUMMARY_ONE], "scope: session_a is not idle before c3 is doing")
        self.commit_step("c3", dict(roadmap.STEP, order=3, status="doing", lane="session_a"))
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual(code, 0, err)
        self.assertRegex(out, r"(?m)^hold \(step c3 ", "a doing step under a completed lane printed no hold line: %r" % out)
        self.assertEqual(out.splitlines(), [DOING_HOLD % ("c3", "session_a"), HELD_ONE],
                         "the hold line is not the pinned text: %r" % out)

    def test_a_kept_idle_lane_prints_no_line_and_is_not_counted(self):
        # The control is the same idle lane with no keep list: it is listed, and the summary counts it. Then keepSessions
        # names it: no line for it, and the summary counts no lane to archive.
        self.publish([lane("session_a", "c1")])
        _, before, _ = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual(before.splitlines()[-1:], [SUMMARY_ONE], "scope: session_a is not idle before it is kept: %r" % before)
        self.publish([lane("session_a", "c1")], keep=[{"id": "session_a", "reason": "kept for a reader"}])
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines(), [SUMMARY_ZERO], "a kept idle lane printed a line or was counted: %r" % out)

    def test_a_kept_hold_lane_prints_no_hold_line_and_is_not_counted_as_held(self):
        # The control is a lane with no cs-step tag: it prints a hold line and the summary counts one held lane. Then
        # keepSessions names it: no hold line, and no held lane in the summary.
        self.publish([lane("session_nostep", None)])
        _, before, _ = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual(before.splitlines()[-1:], [HELD_ONE], "scope: session_nostep is not held before it is kept: %r" % before)
        self.publish([lane("session_nostep", None)], keep=[{"id": "session_nostep", "reason": "kept for a reader"}])
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines(), [SUMMARY_ZERO], "a kept hold lane printed a hold line or was counted as held: %r" % out)

    def test_a_kept_idle_lane_is_skipped_and_a_non_kept_idle_lane_beside_it_still_prints(self):
        # The control lists both idle lanes: the summary counts two. Then keepSessions names session_a only: session_c still
        # prints, and the summary counts one lane to archive.
        self.publish([lane("session_a", "c1"), lane("session_c", "c2")])
        _, before, _ = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertRegex(before.splitlines()[-1], r"^merge: 2 lanes to archive\.", "scope: both lanes are not idle: %r" % before)
        self.publish([lane("session_a", "c1"), lane("session_c", "c2")], keep=[{"id": "session_a", "reason": "kept for a reader"}])
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual(code, 0, err)
        lines = out.splitlines()
        self.assertEqual([line.split(" ", 1)[0] for line in lines[:-1]], ["session_c"], "a kept lane printed, or session_c did not: %r" % out)
        self.assertEqual(lines[-1:], [SUMMARY_ONE], "the summary counts a kept lane: %r" % out)

    def test_malformed_keep_list_reads_as_unknown_not_as_an_empty_keep_list(self):
        # The control is the same idle lane with no keepSessions: it is listed and the command exits 0. Then keepSessions is
        # not a list, or an entry has no id. Either reads as unknown: one unknown line, no lane line, no summary, exit 1.
        self.publish([lane("session_a", "c1")])
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual((code, out.splitlines()[-1:]), (0, [SUMMARY_ONE]), "scope: session_a is not listed before the keep list: %r" % out)
        for keep in ("session_a", [{"reason": "no id"}]):
            with self.subTest(keep=keep):
                self.publish([lane("session_a", "c1")], keep=keep)
                code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
                lines = out.splitlines()
                self.assertTrue(any(line.startswith("unknown (") for line in lines),
                                "a malformed keepSessions printed no unknown line: out %r, err %r" % (out, err))
                self.assertFalse(any(line.startswith("session_a") for line in lines),
                                 "a malformed keepSessions read as an empty keep list: %r" % out)
                self.assertEqual(code, 1, "a malformed keepSessions exits %d, so a caller reads the list as read: %s" % (code, err))
                self.assertNotRegex(out, SUMMARY_LINE)

    def test_a_padded_keep_id_still_skips_its_lane(self):
        # The control is the idle lane with no keep list: it is listed. Then keepSessions names it with a space before its id,
        # then with one after. The id is stripped, so the lane prints no line and the summary counts none.
        self.publish([lane("session_a", "c1")])
        _, before, _ = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual(before.splitlines()[-1:], [SUMMARY_ONE], "scope: session_a is not idle before it is kept: %r" % before)
        for padded in (" session_a", "session_a "):
            with self.subTest(padded=padded):
                self.publish([lane("session_a", "c1")], keep=[{"id": padded, "reason": "kept for a reader"}])
                code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
                self.assertEqual(code, 0, err)
                self.assertEqual(out.splitlines(), [SUMMARY_ZERO], "a padded keepSessions id %r did not skip its lane: %r" % (padded, out))

    def test_a_keep_id_that_matches_no_row_is_not_an_error(self):
        # The control is the idle lane with no keep list: it prints its lane line and the summary counts it. keepSessions names
        # an id no row carries: the lane still prints, and the command exits 0.
        self.publish([lane("session_a", "c1")], keep=[{"id": "session_gone", "reason": "no longer listed"}])
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual(code, 0, "an unmatched keepSessions id exits %d: %s" % (code, err))
        self.assertEqual(out.splitlines(), ["session_a (c1; topic -)", SUMMARY_ONE], "an unmatched keepSessions id changed the list: %r" % out)

    def test_an_unarchived_lane_prints_a_hold_line_and_counts_it_held(self):
        # The control is the same idle lane with no unarchived_epoch: it is listed. Then the row carries an int epoch above 0:
        # the lane is held, its one hold line names the session, and the summary counts one held lane and no lane to archive.
        self.publish([lane("session_u", "c1")])
        _, before, _ = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual(before.splitlines()[-1:], [SUMMARY_ONE], "scope: session_u is not idle before its unarchived_epoch: %r" % before)
        self.publish([lane("session_u", "c1", unarchived_epoch=1763000000)])
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual(code, 0, err)
        lines = out.splitlines()
        self.assertFalse(any(line.startswith("session_u") for line in lines), "an unarchived lane printed a lane line: %r" % out)
        self.assertEqual(len(lines), 2, "an unarchived lane printed more than its hold line and the summary: %r" % out)
        self.assertTrue(lines[0].startswith("hold (") and lines[0].endswith("; lane session_u)"), "the hold line does not name session_u: %r" % out)
        self.assertEqual(lines[1], HELD_ONE, "the summary does not count the unarchived lane as held: %r" % out)

    def test_an_unarchived_epoch_of_zero_or_absent_leaves_the_lane_line(self):
        # An epoch above 0 holds a lane. Absent, or 0, is no hold: the lane prints its lane line and the summary counts it.
        for extra in ({}, {"unarchived_epoch": 0}):
            with self.subTest(extra=extra):
                self.publish([lane("session_u", "c1", **extra)])
                code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
                self.assertEqual(code, 0, err)
                self.assertEqual(out.splitlines(), ["session_u (c1; topic -)", SUMMARY_ONE], "the lane line changed for %r: %r" % (extra, out))

    def test_a_kept_session_with_an_unarchived_epoch_is_skipped_entirely(self):
        # The row is idle and not archived, so without the keep list it would be held. keepSessions skips it first: no lane
        # line, no hold line, and the summary counts neither.
        self.publish([lane("session_u", "c1", unarchived_epoch=1763000000)], keep=[{"id": "session_u", "reason": "kept for a reader"}])
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines(), [SUMMARY_ZERO], "a kept session with an unarchived_epoch printed a line or was counted: %r" % out)

    def test_a_bad_unarchived_epoch_reads_the_whole_list_unknown(self):
        # The control is the idle lane with no unarchived_epoch: it is listed and the command exits 0. A text epoch, a negative
        # one or a bool (True and False are ints to Python) reads the whole list unknown: one line, no lane line, no summary, exit 1.
        self.publish([lane("session_a", "c1")])
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual((code, out.splitlines()[-1:]), (0, [SUMMARY_ONE]), "scope: session_a is not listed before the epoch: %r" % out)
        for epoch in ("1763000000", -5, True, False):
            with self.subTest(epoch=epoch):
                self.publish([lane("session_a", "c1", unarchived_epoch=epoch)])
                code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
                lines = out.splitlines()
                self.assertEqual(len(lines), 1, "a bad unarchived_epoch %r did not read the whole list as one line: out %r, err %r" % (epoch, out, err))
                self.assertTrue(lines[0].startswith("unknown ("), "a bad unarchived_epoch %r printed no unknown line: %r" % (epoch, out))
                self.assertEqual(code, 1, "a bad unarchived_epoch %r exits %d, so a caller reads the list as read: %s" % (epoch, code, err))
                self.assertNotRegex(out, SUMMARY_LINE)

    def test_a_kept_session_with_a_bad_unarchived_epoch_is_skipped_before_the_epoch_check(self):
        # The control is the same row with no keep list: a bad epoch reads the whole list unknown. Then keepSessions names it: the
        # keep list skips the row before the epoch check, so no unknown line prints and the summary counts none.
        keep = [{"id": "session_u", "reason": "kept for a reader"}]
        for epoch in (True, -5):
            with self.subTest(epoch=epoch):
                self.publish([lane("session_u", "c1", unarchived_epoch=epoch)])
                _, before, _ = self.run_merge("--idle-lanes", "--live", str(self.live))
                self.assertTrue(before.startswith("unknown ("), "scope: the bad epoch %r is not unknown without its keep: %r" % (epoch, before))
                self.publish([lane("session_u", "c1", unarchived_epoch=epoch)], keep=keep)
                code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
                self.assertEqual(out.splitlines(), [SUMMARY_ZERO],
                                 "a kept session with unarchived_epoch %r printed an unknown line or was counted: %r" % (epoch, out))
                self.assertEqual(code, 0, err)

    def test_an_unarchived_lane_that_waits_prints_no_line_and_is_not_counted_held(self):
        # A waiting lane is not a hold, unarchived or not. Scope first: the same unarchived lane with nothing left to wait for
        # prints its hold line, and the summary counts it held. Then each reason it waits, one at a time: its step is not done,
        # its pull is open, or a page item it answers or owns is open. Each prints no line and counts no lane and no held lane.
        self.commit_step("c3", dict(roadmap.STEP, order=3, status="todo"))
        epoch = {"unarchived_epoch": 1763000000}
        self.publish([lane("session_u", "c1", **epoch)])
        _, before, _ = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual(before.splitlines()[-1:], [HELD_ONE], "scope: the unarchived lane is not held with nothing to wait for: %r" % before)
        open_pull = {"number": 1, "title": "lane c1", "branch": "lane/c1", "draft": False}
        waits = {
            "its step is not done": ([lane("session_u", "c3", **epoch)], [], []),
            "its pull is open": ([lane("session_u", "c1", **epoch)], [open_pull], []),
            "a page item answers its step": ([lane("session_u", "c1", **epoch)], [], [{"n": 1, "status": "open", "home": "c1", "lane": "c1"}]),
            "a page item is owned by it": ([lane("session_u", "c1", **epoch)], [], [{"n": 2, "status": "open", "home": "c1", "lane": None, "owner": "session_u"}]),
        }
        for why, (sessions, pulls, items) in waits.items():
            with self.subTest(why=why):
                self.publish(sessions, pulls=pulls, items=items)
                code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
                self.assertEqual(code, 0, err)
                self.assertEqual(out.splitlines(), [SUMMARY_ZERO], "an unarchived lane that waits (%s) printed a line or was counted held: %r" % (why, out))

    def test_a_working_lane_with_an_unarchived_epoch_prints_no_line(self):
        # A working lane is never listed or held, whatever its epoch. Scope first: an idle lane beside a working lane with no epoch
        # prints one lane line, and the summary counts one lane. Then the working lane carries an int epoch above 0: the output is
        # the same, so the working lane prints no line and is not counted held.
        idle = lane("session_c", "c2")

        def working(**extra):
            return lane("session_b", "c1", bucket=roadmap.BUCKET_WORKING, status="SESSION_STATUS_RUNNING", **extra)
        self.publish([idle, working()])
        _, before, _ = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual(before.splitlines(), ["session_c (c2; topic -)", SUMMARY_ONE], "scope: the idle lane and the working lane read differently: %r" % before)
        self.publish([idle, working(unarchived_epoch=1763000000)])
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines(), ["session_c (c2; topic -)", SUMMARY_ONE], "a working lane with an unarchived_epoch printed a line or was counted held: %r" % out)


if __name__ == "__main__":
    unittest.main()
