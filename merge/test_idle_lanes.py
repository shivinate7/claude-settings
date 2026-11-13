#!/usr/bin/env python3
"""Fixture suite for `merge --idle-lanes --live FILE` (merge/merge.py), the reader of the roadmap's idle lanes.

Run: python3 merge/test_idle_lanes.py

WHAT IT PROVES. The command prints one line per lane to archive, then one `hold (...)` line per idle lane that a hold
reason keeps from archiving now, then one summary line that counts both. A hold line is never archived. Its reasons:
no cs-step tag; a step off the record branch with no Step trailer on main; or a step still doing under the lane and
not landed on main. A waiting lane prints no line. A whole-read failure prints one `unknown (` line and exits 1. It
takes its steps, marks and repo name from the checkout, as the roadmap build does. It stands alone: no other flag, and
no merge role in a cloud session. A missing --live file exits 1 and prints no summary, so an unread list never reads
as an empty one.

A lane tagged cs-archive-ready:<slug> is printed with a HOLD marker when its handoff, roadmap/outbox/<slug>-handoff.md,
is not on the record branch, and the summary counts the held lanes. A slug that is empty or has a `/` or `..` reads the
lane unknown, never clear. The record branch is read from origin/roadmap, as a merge run from main reads it.

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
SUMMARY_ONE = "merge: 1 lanes to archive. Run get_session on each lane in one message, then archive them in the next message."
SUMMARY_ZERO = "merge: 0 lanes to archive. Run get_session on each lane in one message, then archive them in the next message."
SUMMARY_LINE = re.compile(r"^merge: \d+ lanes to archive\b", re.M)
ZERO_LINE = re.compile(r"^merge: 0 lanes to archive\.", re.M)
HOLD = "HOLD: handoff %s is not on the record branch"
HANDOFF = "roadmap/outbox/%s-handoff.md"
# N counts the clear lanes only; a held lane is printed with its HOLD marker and counted in M.
HANDOFF_HELD_ONE = "merge: 1 lanes to archive, 1 held. Run get_session on each alone, then archive it."
HANDOFF_HELD_ALL = "merge: 0 lanes to archive, 2 held. Run get_session on each alone, then archive it."
HANDOFF_MIXED = "merge: 3 lanes to archive, 1 held. Run get_session on each alone, then archive it."
# Each bad slug with the path a naive join would read on the record branch, so a builder that skips the check reads
# the lane clean. The `..` path is written at the file it resolves to, since git refuses a `..` in a path.
BAD_SLUGS = (("", "roadmap/outbox/-handoff.md"), ("a/b", "roadmap/outbox/a/b-handoff.md"),
             ("../up", "roadmap/up-handoff.md"), ("a..b", "roadmap/outbox/a..b-handoff.md"))
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


def lane(sid, step, bucket=roadmap.BUCKET_COMPLETED, status="SESSION_STATUS_IDLE", tags=()):
    """A lane row of this repo. step=None leaves out the cs-step tag."""
    step_tags = ("cs-step:" + step,) if step else ()
    return roadmap.session_row(sid, status, "cs-build:lane", *step_tags, REPO, *tags, status_bucket=bucket)


def archived(sid, step, slug):
    """A completed lane whose tags carry cs-archive-ready:<slug>."""
    return lane(sid, step, tags=("cs-archive-ready:" + slug,))


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

    def record_from_origin(self, record=(), main=()):
        """Read the record branch as a merge run from main does: origin/roadmap, with HEAD on main. `record` and `main`
        are repo paths to commit on the record branch and on main. Origin's URL stays in GitHub form, so the repo name
        still reads owner/fixture, and update-ref sets origin/roadmap with no remote to push to."""
        roadmap.git(self.repo, "checkout", "-q", "roadmap")
        self.commit_files(record, "handoffs on the record branch")
        roadmap.git(self.repo, "update-ref", "refs/remotes/origin/roadmap", "roadmap")
        roadmap.git(self.repo, "checkout", "-q", "main")
        self.commit_files(main, "handoffs on main")

    def commit_files(self, paths, message):
        """Commit each path with one line of text on the checked-out branch. No paths, no commit."""
        if not paths:
            return
        for path in paths:
            full = self.repo / path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text("# handoff\n", encoding="utf-8")
        roadmap.git(self.repo, "add", "-A")
        roadmap.git(self.repo, "commit", "-q", "-m", message)

    def run_idle(self):
        """The output of --idle-lanes --live on the fixture, which must exit 0: its lanes are all readable."""
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual(code, 0, err)
        return out

    def lane_line(self, out, sid):
        """The one output line whose first word is `sid`. Asserts the lane is listed once, before its line is read."""
        found = [line for line in out.splitlines() if line.split(" ", 1)[0] == sid]
        self.assertEqual(len(found), 1, "lane %s is not listed once: out: %r" % (sid, out))
        return found[0]

    def land_steps(self, stems):
        """Commit one done step per stem on the record branch, numbered from 3 (c1 and c2 are in setUp)."""
        roadmap.git(self.repo, "checkout", "-q", "roadmap")
        for order, stem in enumerate(stems, start=3):
            step = dict(roadmap.STEP, order=order, status="done")
            (self.repo / "roadmap" / "data" / "steps" / (stem + ".json")).write_text(json.dumps(step), encoding="utf-8")
        roadmap.git(self.repo, "add", "-A")
        roadmap.git(self.repo, "commit", "-q", "-m", "steps " + ", ".join(stems))

    def assert_unknown_never_clear(self, out, sid):
        """Lane `sid` is flagged unknown, on its line or as an entry naming it, and no line reads it clear."""
        flagged = [line for line in out.splitlines() if sid in line and "unknown (" in line]
        self.assertTrue(flagged, "no unknown flag names %s: out: %r" % (sid, out))
        clear = [line for line in out.splitlines() if line.startswith(sid + " ") and "unknown (" not in line]
        self.assertEqual(clear, [], "%s reads clear: out: %r" % (sid, out))

    def test_tagged_lane_whose_handoff_is_not_on_the_record_branch_is_marked_held(self):
        self.publish([archived("session_t", "c1", "alpha"), lane("session_u", "c2")])
        self.record_from_origin()
        out = self.run_idle()
        self.assertIn(HOLD % "alpha", self.lane_line(out, "session_t"), out)
        self.assertEqual(self.lane_line(out, "session_u"), "session_u (c2; topic -)", out)
        self.assertEqual(out.splitlines()[-1:], [HANDOFF_HELD_ONE], out)

    def test_tagged_lane_whose_handoff_is_on_the_record_branch_is_listed_clean(self):
        # The held lane keeps this case red on the current code: a fixture with no held lane reads the same there.
        self.publish([archived("session_f", "c1", "beta"), archived("session_t", "c2", "gamma")])
        self.record_from_origin(record=[HANDOFF % "beta"])
        out = self.run_idle()
        self.assertEqual(self.lane_line(out, "session_f"), "session_f (c1; topic -)", out)
        self.assertIn(HOLD % "gamma", self.lane_line(out, "session_t"), out)
        self.assertEqual(out.splitlines()[-1:], [HANDOFF_HELD_ONE], out)

    def test_untagged_lane_is_listed_with_no_marker_beside_a_held_lane(self):
        # The held lane keeps this case red on the current code: a fixture with no held lane reads the same there.
        self.publish([lane("session_u", "c1"), archived("session_t", "c2", "delta")])
        self.record_from_origin()
        out = self.run_idle()
        self.assertEqual(self.lane_line(out, "session_u"), "session_u (c1; topic -)", out)
        self.assertIn(HOLD % "delta", self.lane_line(out, "session_t"), out)
        self.assertEqual(out.splitlines()[-1:], [HANDOFF_HELD_ONE], out)

    def test_handoff_committed_only_on_main_is_not_on_the_record_branch(self):
        # The file is on main's disk, so a check of the checkout's files reads the lane clean. Only the record branch
        # counts.
        self.publish([archived("session_t", "c1", "alpha"), lane("session_u", "c2")])
        self.record_from_origin(main=[HANDOFF % "alpha"])
        out = self.run_idle()
        self.assertIn(HOLD % "alpha", self.lane_line(out, "session_t"), out)
        self.assertEqual(self.lane_line(out, "session_u"), "session_u (c2; topic -)", out)
        self.assertEqual(out.splitlines()[-1:], [HANDOFF_HELD_ONE], out)

    def test_every_listed_lane_held_counts_them_all(self):
        self.publish([archived("session_a", "c1", "alpha"), archived("session_b", "c2", "beta")])
        self.record_from_origin()
        out = self.run_idle()
        self.assertIn(HOLD % "alpha", self.lane_line(out, "session_a"), out)
        self.assertIn(HOLD % "beta", self.lane_line(out, "session_b"), out)
        self.assertEqual(out.splitlines()[-1:], [HANDOFF_HELD_ALL], out)

    def test_bad_archive_slug_flags_its_lane_unknown_never_clear(self):
        # Each bad slug's naive path is on the record branch, so a builder that joins the slug unchecked reads it clean.
        # The flag may sit on the lane's line or be an unknown entry that names the lane.
        self.record_from_origin(record=[path for _, path in BAD_SLUGS])
        for slug, _ in BAD_SLUGS:
            with self.subTest(slug=slug):
                self.publish([archived("session_x", "c1", slug), lane("session_u", "c2")])
                _, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
                self.assert_unknown_never_clear(out, "session_x")
                self.assertEqual(self.lane_line(out, "session_u"), "session_u (c2; topic -)", out)

    def test_unreadable_record_branch_after_a_held_lane_reads_unknown_exit_1_no_summary(self):
        # A pin of today's whole-list unknown: an unreadable record branch exits 1 and prints no summary. The HOLD check
        # first shows the lane was read from the record branch, so the unknown comes from the branch going missing.
        self.publish([archived("session_t", "c1", "alpha")])
        self.record_from_origin()
        out = self.run_idle()
        self.assertIn(HOLD % "alpha", self.lane_line(out, "session_t"), out)
        roadmap.git(self.repo, "update-ref", "-d", "refs/remotes/origin/roadmap")
        roadmap.git(self.repo, "branch", "-m", "roadmap", "roadmap-gone")
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertTrue(any(line.startswith("unknown (") for line in out.splitlines()),
                        "no unknown line: out: %r, err: %r" % (out, err))
        self.assertEqual(code, 1, "an unreadable record branch exits %d, so a caller reads the list as read" % code)
        self.assertNotRegex(out, SUMMARY_LINE)

    def test_summary_counts_only_the_clear_lanes_beside_one_held_lane(self):
        # The three clear lanes are the control: they list exactly as today, so the summary is what this case reads.
        self.land_steps(["c3", "c4"])
        self.publish([lane("session_a", "c1"), lane("session_b", "c2"), lane("session_c", "c3"),
                      archived("session_t", "c4", "alpha")])
        self.record_from_origin()
        out = self.run_idle()
        for sid, step in (("session_a", "c1"), ("session_b", "c2"), ("session_c", "c3")):
            self.assertEqual(self.lane_line(out, sid), "%s (%s; topic -)" % (sid, step), out)
        self.assertIn(HOLD % "alpha", self.lane_line(out, "session_t"), out)
        self.assertEqual(out.splitlines()[-1:], [HANDOFF_MIXED], out)

    def test_handoff_stored_as_a_tree_at_its_path_reads_held_not_clean(self):
        # A directory sits where the handoff file belongs, with a file under it: the handoff is not on the record branch.
        self.publish([archived("session_t", "c1", "alpha"), lane("session_u", "c2")])
        self.record_from_origin(record=[(HANDOFF % "alpha") + "/notes.md"])
        out = self.run_idle()
        self.assertIn(HOLD % "alpha", self.lane_line(out, "session_t"), out)
        self.assertEqual(self.lane_line(out, "session_u"), "session_u (c2; topic -)", out)

    def test_nul_bearing_slugs_read_their_lanes_unknown_never_clear(self):
        # A slug with a NUL byte cannot be sent to git, so its handoff read fails: each lane reads unknown. The clear
        # control shows the list was read.
        self.land_steps(["c3"])
        self.record_from_origin()
        self.publish([archived("session_n1", "c1", "al\x00pha"), archived("session_n2", "c2", "be\x00ta"),
                      lane("session_u", "c3")])
        _, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assert_unknown_never_clear(out, "session_n1")
        self.assert_unknown_never_clear(out, "session_n2")
        self.assertEqual(self.lane_line(out, "session_u"), "session_u (c3; topic -)", out)

    def test_nul_slug_reads_unknown_even_when_the_path_cut_at_the_nul_is_on_the_record_branch(self):
        # "al" is the slug cut at its NUL. The record branch holds that cut slug's handoff, so a reader that cuts the
        # slug reads the lane clear. The slug is refused, so it reads unknown.
        self.land_steps(["c3"])
        self.record_from_origin(record=[HANDOFF % "al"])
        self.publish([archived("session_x", "c1", "al\x00pha"), lane("session_u", "c3")])
        _, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assert_unknown_never_clear(out, "session_x")
        self.assertEqual(self.lane_line(out, "session_u"), "session_u (c3; topic -)", out)

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


if __name__ == "__main__":
    unittest.main()
