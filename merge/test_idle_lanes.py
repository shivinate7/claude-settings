#!/usr/bin/env python3
"""Fixture suite for `merge --idle-lanes --live FILE` (merge/merge.py), the reader of the roadmap's idle lanes.

Run: python3 merge/test_idle_lanes.py

WHAT IT PROVES. The command prints one line per lane to archive, then one summary line, then the finished-lanes count line (the count
the Backlog check reads). It takes its steps, marks and
repo name from the checkout, as the roadmap build does. It stands alone: no other flag, and no merge role in a cloud
session. A missing --live file exits 1 and prints no summary, so an unread list never reads as an empty one. An unread archive
list still prints the finished-lanes line, its count or its unknown form, after its unknown entry, and exits 1. With main
unreadable, the finished-lanes line reads unknown, never a count: a draft pull's hold is tested against main.

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
sys.path.insert(2, str(HERE.parent / "hooks"))
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per test run (lint/_test_temp.py)
import test_build as roadmap  # noqa: E402  the roadmap fixture: make_repo, session_row, iso_ago (one home)
from shared_names import FINISHED_LANES_LINE  # noqa: E402  the one home of the finished-lanes label (hooks/shared_names.py)

REPO = "cs-repo:owner/fixture"
SUMMARY_ONE = "merge: 1 lanes to archive. Run get_session on each alone, then archive it."
SUMMARY_ZERO = "merge: 0 lanes to archive. Run get_session on each alone, then archive it."
SUMMARY_LINE = re.compile(r"^merge: \d+ lanes to archive\b", re.M)
ZERO_LINE = re.compile(r"^merge: 0 lanes to archive\.", re.M)
# The finished-lanes line, after the archive summary: a count, or the unknown form with its reason.
FINISHED = re.compile(r"^merge: (\d+) %s\.$" % re.escape(FINISHED_LANES_LINE), re.M)
FINISHED_UNKNOWN = re.compile(r"^merge: %s unknown \(.+\)\.$" % re.escape(FINISHED_LANES_LINE), re.M)


def finished_line(count):
    return "merge: %d %s." % (count, FINISHED_LANES_LINE)


def last_line(out):
    """The last line of a run's stdout, or "" when it printed none, so a missing line fails an assert and never raises."""
    return out.rstrip("\n").split("\n")[-1]


def draft_pull(head, branch="lane/c1", number=81):
    """An open draft pull on a lane's head ref. Its head sha is the one the draft-head test reads against main."""
    return {"number": number, "title": "lane " + branch, "branch": branch, "draft": True, "head": head}

# Made in setUpModule, not at import, so a helper that imports this file leaks no folder.
RUN_FOLDER = None


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


def lane(sid, step, bucket=roadmap.BUCKET_COMPLETED, status="SESSION_STATUS_IDLE"):
    return roadmap.session_row(sid, status, "cs-build:lane", "cs-step:" + step, REPO, status_bucket=bucket)


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

    def publish(self, sessions=None, read_at=None, pulls=(), items=()):
        """Write the --live file. Its readAt is five minutes old by default. The sessions key is left out when sessions is None,
        and the items key when items is None."""
        value = {"readAt": read_at or roadmap.iso_ago(5), "threads": [], "pulls": list(pulls)}
        if items is not None:
            value["items"] = list(items)
        if sessions is not None:
            value["sessions"] = list(sessions)
        self.live.write_text(json.dumps(value), encoding="utf-8")

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
        self.assertEqual(lines[-2:], [SUMMARY_ONE, finished_line(1)], out)
        self.assertEqual([line.split(" ", 1)[0] for line in lines[:-2]], ["session_a"], out)

    def test_no_idle_lane_prints_a_zero_summary_and_no_entry(self):
        self.publish([lane("session_b", "c2", bucket=roadmap.BUCKET_WORKING, status="SESSION_STATUS_RUNNING")])
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines(), [SUMMARY_ZERO, finished_line(0)], out)

    def test_the_finished_line_counts_a_failed_lane_the_list_does_not_list(self):
        # The lanes are completed (listed), failed (counted, not listed) and working (neither). The count is 2.
        self.publish([lane("session_a", "c1"), lane("session_b", "c2", bucket=roadmap.BUCKET_FAILED),
                      lane("session_c", "c2", bucket=roadmap.BUCKET_WORKING, status="SESSION_STATUS_RUNNING")])
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual(code, 0, err)
        lines = out.splitlines()
        self.assertEqual(lines[-2:], [SUMMARY_ONE, finished_line(2)], out)
        self.assertEqual([line.split(" ", 1)[0] for line in lines[:-2]], ["session_a"], out)

    def test_a_review_ready_lane_counts_until_an_open_pull_holds_it(self):
        # The control is the lane with no pull: it is listed and counted. With an open pull on its lane head, the list and the
        # count both drop it, so the summary and the count read zero.
        self.publish([lane("session_r", "c2", bucket=roadmap.BUCKET_REVIEW_READY)])
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines()[-2:], [SUMMARY_ONE, finished_line(1)], out)
        self.publish([lane("session_r", "c2", bucket=roadmap.BUCKET_REVIEW_READY)],
                     pulls=[{"number": 81, "title": "lane c2", "branch": "lane/c2"}])
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines(), [SUMMARY_ZERO, finished_line(0)], out)

    def test_the_finished_line_reads_unknown_for_a_lane_row_with_no_usable_bucket(self):
        # The control is the completed lane alone: its finished line counts 1. Beside it, a row with a lowercase bucket is no
        # lane the list shows, and it makes the count unknown. The archive list still prints its lane and summary.
        good = lane("session_a", "c1")
        self.publish([good])
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines()[-2:], [SUMMARY_ONE, finished_line(1)], out)
        lower = roadmap.session_row("session_lower", "SESSION_STATUS_IDLE", "cs-build:lane", "cs-step:c2", REPO,
                                    status_bucket="completed")
        self.publish([good, lower])
        _, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        lines = out.splitlines()
        self.assertEqual(lines[-2], SUMMARY_ONE, out)
        self.assertRegex(lines[-1], FINISHED_UNKNOWN, "the finished line is not the unknown form: out: %r, err: %r" % (out, err))
        self.assertNotRegex(out, FINISHED)

    def test_a_live_file_with_no_sessions_list_prints_no_finished_count(self):
        # The control is an empty sessions list, a readable zero. With no sessions list the count is unknown, so no number
        # prints where a zero would read as "none".
        self.publish([])
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual(out.splitlines(), [SUMMARY_ZERO, finished_line(0)], out)
        self.publish(None)
        _, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertNotRegex(out, FINISHED, "a file with no sessions list printed a count: out: %r, err: %r" % (out, err))

    def test_stale_live_file_prints_unknown_lines_and_no_empty_summary(self):
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
        self.assertNotRegex(out, FINISHED)

    def test_an_unread_archive_list_still_prints_the_finished_count(self):
        # The control is the lane with its page items list: the list prints it, then the summary, then the count. With no items
        # list the archive list reads unknown, but the count reads from the sessions. The count line still prints, after the
        # unknown entry and with no summary, and the command exits 1 so the unread list never reads as empty.
        self.publish([lane("session_a", "c1")], items=[])
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual((code, out.splitlines()[-2:]), (0, [SUMMARY_ONE, finished_line(1)]), "out: %r, err: %r" % (out, err))
        self.publish([lane("session_a", "c1")], items=None)
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual(code, 1, "an unread list exits %d, so a caller reads it as success: err: %r" % (code, err))
        self.assertTrue(out.startswith("unknown ("), "the archive list is not the unknown entry: out: %r, err: %r" % (out, err))
        self.assertNotRegex(out, SUMMARY_LINE)
        self.assertEqual(out.splitlines()[-1:], [finished_line(1)],
                         "the count line is missing after an unread list: out: %r, err: %r" % (out, err))

    def test_both_unread_reads_print_their_unknown_lines_and_no_summary(self):
        # The live file has neither list, so the archive list and the count both read unknown for the same reason. The command
        # prints the unknown entry, then the unknown count line, with no summary and exit 1. Neither reads as a zero.
        self.publish(None, items=None)
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual(code, 1, "an unread list exits %d, so a caller reads it as success: err: %r" % (code, err))
        self.assertTrue(out.startswith("unknown ("), "the archive list is not the unknown entry: out: %r, err: %r" % (out, err))
        self.assertNotRegex(out, SUMMARY_LINE)
        self.assertNotRegex(out, FINISHED)
        self.assertRegex(out, FINISHED_UNKNOWN,
                         "the unknown count line is missing after an unread list: out: %r, err: %r" % (out, err))

    def make_main_unreadable(self):
        """Rename main away, so no ref named main reads in this checkout."""
        roadmap.git(self.repo, "branch", "-m", "main", "trunk")
        self.assertIsNone(roadmap.build.main_ref(self.repo, "main"), "the fixture must make main unreadable")

    def test_unreadable_main_exits_1_with_an_unknown_list_line_and_an_unknown_finished_line(self):
        # The control is the same lane with main read: it is listed, the summary says 1, and the command exits 0. With
        # main renamed away, no step can be read as landed, so the unknown list line carries the failure and the command
        # exits 1 with no summary. The finished count reads main too (a draft pull's head is tested against it), so its
        # line reads unknown, never a number.
        self.publish([lane("session_a", "c1")])
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual((code, out.splitlines()[-2:]), (0, [SUMMARY_ONE, finished_line(1)]), "out: %r, err: %r" % (out, err))
        self.make_main_unreadable()
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertTrue(any(line.startswith("unknown (") for line in out.splitlines()),
                        "an unreadable main prints no unknown line: out: %r, err: %r" % (out, err))
        self.assertEqual(code, 1, "an unreadable main exits %d, so a caller reads the list as read" % code)
        self.assertNotRegex(out, SUMMARY_LINE)
        self.assertRegex(last_line(out), FINISHED_UNKNOWN,
                         "an unreadable main does not make the finished line unknown: out: %r, err: %r" % (out, err))
        self.assertNotRegex(out, FINISHED, "an unreadable main prints a count on the finished line: out: %r, err: %r" % (out, err))

    def test_unreadable_main_reads_the_finished_line_unknown_under_a_draft_pull(self):
        # A review-ready lane under a draft pull is released only when the pull's head is on main, so the count reads main.
        # With main unreadable the hold cannot be cleared, and the count would print 0 for the lane. The line must read
        # unknown instead. The control is the same lane with main read: the draft's head is on main, so the lane is released
        # and counted as 1.
        head = roadmap.git(self.repo, "rev-parse", "main").strip()
        self.publish([lane("session_a", "c1", bucket=roadmap.BUCKET_REVIEW_READY)], pulls=[draft_pull(head)])
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual((code, out.splitlines()[-2:]), (0, [SUMMARY_ONE, finished_line(1)]), "out: %r, err: %r" % (out, err))
        self.make_main_unreadable()
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertNotRegex(out, FINISHED, "an unreadable main gives the draft-held lane a number: out: %r, err: %r" % (out, err))
        self.assertRegex(last_line(out), FINISHED_UNKNOWN,
                         "an unreadable main does not make the finished line unknown under a draft pull: out: %r, err: %r" % (out, err))

    def test_idle_lanes_needs_no_merge_role_in_a_cloud_session(self):
        self.publish([lane("session_a", "c1")])
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live),
                                        extra_env={"CLAUDE_CODE_REMOTE": "true"})
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines()[-2:], [SUMMARY_ONE, finished_line(1)], out)


if __name__ == "__main__":
    unittest.main()
