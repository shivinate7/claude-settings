#!/usr/bin/env python3
"""Fixture suite for `merge --idle-lanes --live FILE` (merge/merge.py), the reader of the roadmap's idle lanes.

Run: python3 merge/test_idle_lanes.py

WHAT IT PROVES. The command prints one line per lane to archive, then one summary line. It takes its steps, marks and
repo name from the checkout, as the roadmap build does. It stands alone: no other flag, and no merge role in a cloud
session. A missing --live file exits 1 and prints no summary, so an unread list never reads as an empty one.

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

    def publish(self, sessions, read_at=None):
        """Write the --live file. Its readAt is five minutes old by default."""
        value = {"readAt": read_at or roadmap.iso_ago(5), "threads": [], "pulls": [], "items": [], "sessions": list(sessions)}
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
        self.assertEqual(lines[-1:], [SUMMARY_ONE], out)
        self.assertEqual([line.split(" ", 1)[0] for line in lines[:-1]], ["session_a"], out)

    def test_no_idle_lane_prints_a_zero_summary_and_no_entry(self):
        self.publish([lane("session_b", "c2", bucket=roadmap.BUCKET_WORKING, status="SESSION_STATUS_RUNNING")])
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines(), [SUMMARY_ZERO], out)

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


if __name__ == "__main__":
    unittest.main()
