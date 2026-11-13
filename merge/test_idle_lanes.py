#!/usr/bin/env python3
"""Fixture suite for `merge --idle-lanes --live FILE` (merge/merge.py), the reader of the roadmap's idle lanes.

Run: python3 merge/test_idle_lanes.py

WHAT IT PROVES. The command prints one line per lane to archive, then one `hold (...)` line per idle lane that a hold
reason keeps from archiving now, then one summary line that counts both. A hold line is never archived. Its reasons:
no cs-step tag; a step off the record branch with no Step trailer on main; or a step still doing under the lane and
not landed on main. A waiting lane prints no line. A whole-read failure prints one `unknown (` line and exits 1. It
takes its steps, marks and repo name from the checkout, as the roadmap build does. It stands alone: no other flag, and
no merge role in a cloud session. A missing --live file exits 1 and prints no summary, so an unread list never reads
as an empty one. A lane that only stale drafts hold prints one `joint (` line instead of nothing; the summary counts it
among the lanes to archive.

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
# The joint line for one lane: its stale draft PRs to close, their branches to archive, then the lane's session id.
JOINT = "joint (close #%d; archive archive/%s; archive lane %s)"
MIXED_TWO = "merge: 2 lanes to archive, 1 held. Run get_session on each lane line alone, then archive it; never archive a hold line."

# Made in setUpModule, not at import, so a helper that imports this file leaks no folder.
RUN_FOLDER = None


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


def lane(sid, step, bucket=roadmap.BUCKET_COMPLETED, status="SESSION_STATUS_IDLE"):
    """A lane row of this repo. step=None leaves out the cs-step tag."""
    step_tags = ("cs-step:" + step,) if step else ()
    return roadmap.session_row(sid, status, "cs-build:lane", *step_tags, REPO, status_bucket=bucket)


def stale_lane(sid, step):
    """A lane on `step` idle 13 h at the live read, with no unarchived commit: the kind of lane a stale draft can hold.
    readAt is five minutes old by default, so the idle time is counted from that read."""
    row = lane(sid, step)
    row["idle_since"] = roadmap.iso_ago(5 + 13 * 60)
    row["unarchived_epoch"] = 0
    return row


class IdleLanesCli(unittest.TestCase):
    """merge --idle-lanes against one roadmap fixture checkout whose origin is owner/fixture. c1 to c3 are done."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=RUN_FOLDER)
        done = {"status": "done"}
        self.repo = roadmap.make_repo(self.tmp.name, steps={"c1": dict(roadmap.STEP, order=1, **done),
                                                            "c2": dict(roadmap.STEP, order=2, **done),
                                                            "c3": dict(roadmap.STEP, order=3, **done)})
        roadmap.git(self.repo, "remote", "add", "origin", "git@github.com:owner/fixture.git")
        self.live = pathlib.Path(self.tmp.name) / "live.json"

    def tearDown(self):
        self.tmp.cleanup()

    def publish(self, sessions, read_at=None, pulls=()):
        """Write the --live file. Its readAt is five minutes old by default."""
        value = {"readAt": read_at or roadmap.iso_ago(5), "threads": [], "pulls": list(pulls), "items": [],
                 "sessions": list(sessions)}
        self.live.write_text(json.dumps(value), encoding="utf-8")

    def stale_draft(self, number, branch, **fields):
        """An open draft pull on `branch`, created 13 h before the live read, with its head off main: the record branch's
        tip, which main never reaches. `fields` set or add keys on the row."""
        row = {"number": number, "title": "lane " + branch, "branch": branch, "draft": True,
               "createdAt": roadmap.iso_ago(5 + 13 * 60), "head": roadmap.git(self.repo, "rev-parse", "roadmap").strip()}
        row.update(fields)
        return row

    def joint_for(self, entries, sid):
        """The joint lines that name lane `sid`."""
        return [e for e in entries if e.startswith("joint (") and e.endswith("; archive lane %s)" % sid)]

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
        step = dict(roadmap.STEP, order=3, status="doing", lane="session_a")
        (self.repo / "roadmap" / "data" / "steps" / "c3.json").write_text(json.dumps(step), encoding="utf-8")
        roadmap.git(self.repo, "add", "-A")
        roadmap.git(self.repo, "commit", "-q", "-m", "step c3")
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual(code, 0, err)
        self.assertRegex(out, r"(?m)^hold \(step c3 ", "a doing step under a completed lane printed no hold line: %r" % out)
        self.assertEqual(out.splitlines(), [DOING_HOLD % ("c3", "session_a"), HELD_ONE],
                         "the hold line is not the pinned text: %r" % out)

    def test_a_lane_only_a_stale_draft_holds_prints_one_joint_line_and_counts_it_to_archive(self):
        self.publish([stale_lane("session_a", "c1")], pulls=[self.stale_draft(101, "lane/c1")])
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines(), [JOINT % (101, "lane/c1", "session_a"), SUMMARY_ONE],
                         "a lane only a stale draft holds did not print its joint line and count it: %r" % out)

    def test_joint_line_is_counted_beside_a_plain_lane_and_a_hold_line(self):
        # session_b is the plain lane (no pull) and session_orphan the hold (its step is on no record or main). Both are
        # counted with the joint lane: two lanes to archive and one held.
        self.publish([stale_lane("session_a", "c1"), lane("session_b", "c2"), lane("session_orphan", "ghost")],
                     pulls=[self.stale_draft(101, "lane/c1")])
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual(code, 0, err)
        lines = out.splitlines()
        self.assertEqual(lines[-1:], [MIXED_TWO], out)
        self.assertEqual(lines[:-1], sorted(lines[:-1]), "the lane lines are not sorted: %r" % out)
        self.assertEqual(self.joint_for(lines, "session_a"), [JOINT % (101, "lane/c1", "session_a")], out)
        self.assertIn("session_b (c2; topic -)", lines, out)
        self.assertEqual(sum(line.startswith("hold (") for line in lines), 1, out)

    def test_a_stale_draft_the_runner_holds_or_a_lane_with_an_unarchived_commit_prints_no_joint_line(self):
        # session_a is the control: its stale draft and idle lane print the line. session_b's draft is held by the batch
        # runner, and session_c has one commit not archived. Each waits silently, as a lane does today.
        unarchived = stale_lane("session_c", "c3")
        unarchived["unarchived_epoch"] = 2
        self.publish([stale_lane("session_a", "c1"), stale_lane("session_b", "c2"), unarchived],
                     pulls=[self.stale_draft(101, "lane/c1"), self.stale_draft(102, "lane/c2", held=True),
                            self.stale_draft(103, "lane/c3")])
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual(code, 0, err)
        self.assertEqual(self.joint_for(out.splitlines(), "session_a"), [JOINT % (101, "lane/c1", "session_a")],
                         "control: the unheld stale draft's lane printed no joint line: %r" % out)
        self.assertEqual(out.splitlines(), [JOINT % (101, "lane/c1", "session_a"), SUMMARY_ONE],
                         "a held draft or an unarchived commit changed the output: %r" % out)


if __name__ == "__main__":
    unittest.main()
