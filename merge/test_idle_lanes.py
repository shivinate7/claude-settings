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
among the lanes to archive. A lane whose pull closed as replaced (a closed landedPulls row with replacedBy) is listed as
superseded whatever its step status; a pull closed with no replacement is not.

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
HANDOFF_HELD_ONE = "merge: 1 lanes to archive, 1 held. Run get_session on each lane line alone, then archive it; never archive a hold line."
HANDOFF_HELD_ALL = "merge: 0 lanes to archive, 2 held. Run get_session on each lane line alone, then archive it; never archive a hold line."
HANDOFF_MIXED = "merge: 3 lanes to archive, 1 held. Run get_session on each lane line alone, then archive it; never archive a hold line."
# Each bad slug with the path a naive join would read on the record branch, so a builder that skips the check reads
# the lane clean. The `..` path is written at the file it resolves to, since git refuses a `..` in a path.
BAD_SLUGS = (("", "roadmap/outbox/-handoff.md"), ("a/b", "roadmap/outbox/a/b-handoff.md"),
             ("../up", "roadmap/up-handoff.md"), ("a..b", "roadmap/outbox/a..b-handoff.md"))
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


def lane(sid, step, bucket=roadmap.BUCKET_COMPLETED, status="SESSION_STATUS_IDLE", tags=()):
    """A lane row of this repo. step=None leaves out the cs-step tag."""
    step_tags = ("cs-step:" + step,) if step else ()
    return roadmap.session_row(sid, status, "cs-build:lane", *step_tags, REPO, *tags, status_bucket=bucket)


def archived(sid, step, slug):
    """A completed lane whose tags carry cs-archive-ready:<slug>."""
    return lane(sid, step, tags=("cs-archive-ready:" + slug,))


def stale_lane(sid, step, tags=()):
    """A lane on `step` idle 13 h at the live read, with no unarchived commit: the kind of lane a stale draft can hold.
    readAt is five minutes old by default, so the idle time is counted from that read. `tags` go on the row as lane tags."""
    row = lane(sid, step, tags=tags)
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

    def publish(self, sessions, read_at=None, pulls=(), landed=None):
        """Write the --live file. Its readAt is five minutes old by default. `landed` is the landedPulls rows, written when given."""
        value = {"readAt": read_at or roadmap.iso_ago(5), "threads": [], "pulls": list(pulls), "items": [],
                 "sessions": list(sessions)}
        if landed is not None:
            value["landedPulls"] = list(landed)
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

    def run_merge(self, *argv, extra_env=None, cwd=None, drop=()):
        """(exit code, stdout, stderr) of `merge.py <argv>`, run in the fixture checkout (or `cwd`). `drop` names the
        variables the run leaves out."""
        env = _test_git.apply({k: v for k, v in {**os.environ, **roadmap.GIT_ENV, **(extra_env or {})}.items() if k not in drop})
        done = subprocess.run([sys.executable, str(MERGE), *argv], cwd=str(cwd or self.repo), capture_output=True,
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

    def single_branch_clone(self):
        """(origin, clone): a bare origin holding main and roadmap, and a --single-branch clone of its main. The clone
        has no local record branch, and origin does hold one."""
        return roadmap.single_branch_clone(self.tmp.name, self.repo, "idle", "main", "roadmap")

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

    def land_steps(self, stems, status="done", lane=None):
        """Commit one step per stem on the record branch, numbered from 3 (c1 to c3 are in setUp, so a stem
        already there changes nothing and the commit may be empty). Each step carries `status`, and `lane` when given."""
        roadmap.git(self.repo, "checkout", "-q", "roadmap")
        for order, stem in enumerate(stems, start=3):
            step = dict(roadmap.STEP, order=order, status=status)
            if lane:
                step["lane"] = lane
            (self.repo / "roadmap" / "data" / "steps" / (stem + ".json")).write_text(json.dumps(step), encoding="utf-8")
        roadmap.git(self.repo, "add", "-A")
        roadmap.git(self.repo, "commit", "-q", "--allow-empty", "-m", "steps " + ", ".join(stems))

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
        lines = out.splitlines()
        self.assertEqual(self.joint_for(lines, "session_a"), [JOINT % (101, "lane/c1", "session_a")],
                         "control: the unheld stale draft's lane printed no joint line: %r" % out)
        self.assertEqual(self.joint_for(lines, "session_b"), [],
                         "a lane whose stale draft the batch runner holds printed a joint line: %r" % out)
        self.assertEqual(self.joint_for(lines, "session_c"), [],
                         "a lane with an unarchived commit printed a joint line: %r" % out)
        self.assertEqual(lines, [JOINT % (101, "lane/c1", "session_a"), SUMMARY_ONE],
                         "the output has lines beyond the control's joint line and summary: %r" % out)

    def test_joint_lane_tagged_archive_ready_with_no_handoff_is_held_and_the_summary_takes_the_long_tail(self):
        # The joint line of an archive-ready lane takes the handoff check like a plain entry. Its handoff is not on the
        # record branch, so the line ends with the HOLD flag, no hold line prints, and the summary counts one held lane
        # with the long tail. record_from_origin reads the record branch; without it the lane reads unknown.
        self.publish([stale_lane("session_a", "c1", tags=("cs-archive-ready:alpha",))],
                     pulls=[self.stale_draft(101, "lane/c1")])
        self.record_from_origin()
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
        self.assertEqual(code, 0, err)
        lines = out.splitlines()
        self.assertEqual(lines[:-1], [JOINT % (101, "lane/c1", "session_a") + " " + HOLD % "alpha"],
                         "the held archive-ready joint lane did not print its joint line with the HOLD flag: %r" % out)
        self.assertEqual(lines[-1:], [HELD_ONE],
                         "a held joint line got the short tail, which names it archivable: %r" % out)


    def listed_ids(self, out):
        """The first word of each output line: the lane ids listed, and the word of each other line."""
        return [line.split(" ", 1)[0] for line in out.splitlines()]

    def closed_row(self, number, branch, head, **fields):
        """A landedPulls row for a pull closed unmerged. `fields` add keys, such as replacedBy."""
        return {"number": number, "branch": branch, "head": head, "merged": False, **fields}

    def record_tip(self):
        """The record branch's tip. The branch is an orphan from main, so main never reaches it: a head off main."""
        return roadmap.git(self.repo, "rev-parse", "roadmap").strip()

    def test_a_lane_whose_pull_closed_as_replaced_is_listed_as_superseded(self):
        # The step is todo and no Step trailer is on main, so nothing lands the step. Only the closed pull's replacedBy
        # link (#8) can list the lane. Its replacement is merged, or open on a branch that is no lane head. The stranded
        # test below is the same closed row with no link and no replacement.
        self.land_steps(["c4"], status="todo")
        head = self.record_tip()
        closed = self.closed_row(7, "lane/c4", head, replacedBy=8)
        open_replacement = [{"number": 8, "title": "batch 7", "branch": "batch-7", "draft": False, "head": head}]
        cases = (("merged", [closed, {"number": 8, "branch": "batch-7", "head": head, "merged": True}], ()),
                 ("open", [closed], open_replacement))
        for label, landed, pulls in cases:
            with self.subTest(replacement=label):
                self.publish([lane("session_a", "c4")], landed=landed, pulls=pulls)
                out = self.run_idle()
                self.assertIn("session_a", self.listed_ids(out),
                              "a lane whose pull closed as replaced by #8 is not listed as superseded: out: %r" % out)
                self.assertTrue(out.splitlines()[-1].startswith("merge: 1 lanes to archive"), out)

    def test_a_pull_closed_unmerged_with_no_replacement_is_not_listed(self):
        # The stranded lane: the same closed row as the replaced-lane test above, with no replacedBy link and no replacement pull.
        self.land_steps(["c4"], status="todo")
        self.publish([lane("session_a", "c4")], landed=[self.closed_row(7, "lane/c4", self.record_tip())])
        out = self.run_idle()
        self.assertNotIn("session_a", self.listed_ids(out),
                         "a lane whose pull closed with no replacement is listed as superseded: out: %r" % out)
        self.assertRegex(out, ZERO_LINE)

    def test_a_lane_with_an_open_pull_on_its_head_is_not_listed(self):
        # The control is the same lane with no pull: its step is done, so it is listed. Then an open pull on lane/c4
        # holds it.
        self.land_steps(["c4"])
        head = self.record_tip()
        self.publish([lane("session_a", "c4")])
        out = self.run_idle()
        self.assertIn("session_a", self.listed_ids(out), "scope: session_a is not listed before its pull opens: %r" % out)
        self.publish([lane("session_a", "c4")],
                     pulls=[{"number": 7, "title": "lane c4", "branch": "lane/c4", "draft": False, "head": head}])
        out = self.run_idle()
        self.assertNotIn("session_a", self.listed_ids(out),
                         "a lane with an open pull on its head is listed: out: %r" % out)

    def test_a_lane_whose_pull_merged_is_listed(self):
        # The control: the step is todo and no pull has landed, so the lane is not listed. Then its pull on lane/c4
        # merges, and the lane is listed.
        self.land_steps(["c4"], status="todo")
        head = self.record_tip()
        self.publish([lane("session_a", "c4")])
        out = self.run_idle()
        self.assertNotIn("session_a", self.listed_ids(out), "scope: a todo lane with no pull is listed: %r" % out)
        self.publish([lane("session_a", "c4")], landed=[{"number": 7, "branch": "lane/c4", "head": head, "merged": True}])
        out = self.run_idle()
        self.assertIn("session_a", self.listed_ids(out), "a lane whose pull merged is not listed: out: %r" % out)

    def test_a_superseded_lane_whose_replacement_closed_unmerged_is_not_listed(self):
        # The control is lane c4, whose pull closed as replaced by #8, and #8 is open. The subject is lane c5, whose pull
        # closed as replaced by #10, and #10 closed unmerged. No open pull and no merged one names that replacement, so
        # the lane waits. c4 and c5 are todo with no Step trailer on main, so only the replacedBy link can list a lane.
        self.land_steps(["c4", "c5"], status="todo")
        head = self.record_tip()
        landed = [self.closed_row(7, "lane/c4", head, replacedBy=8), self.closed_row(9, "lane/c5", head, replacedBy=10),
                  self.closed_row(10, "batch-9", head)]
        pulls = [{"number": 8, "title": "batch 7", "branch": "batch-7", "draft": False, "head": head}]
        self.publish([lane("session_a", "c4"), lane("session_b", "c5")], landed=landed, pulls=pulls)
        out = self.run_idle()
        self.assertIn("session_a", self.listed_ids(out),
                      "scope: a lane whose pull closed as replaced by the open #8 is not listed: out: %r" % out)
        self.assertNotIn("session_b", self.listed_ids(out),
                         "a lane whose pull closed as replaced by #10, closed unmerged, is listed as superseded: out: %r" % out)

    def test_a_superseded_lane_whose_step_is_doing_is_still_listed(self):
        # The control is lane session_b, whose step c5 is todo: it is listed. The subject is session_a, whose step c4 is
        # doing under it and whose pull closed as replaced by the open #8. The replacement carries the step on, so the
        # doing step holds nothing: session_a is listed as an archive line, not held by a hold line.
        self.land_steps(["c5"], status="todo")
        self.land_steps(["c4"], status="doing", lane="session_a")
        head = self.record_tip()
        landed = [self.closed_row(7, "lane/c4", head, replacedBy=8), self.closed_row(9, "lane/c5", head, replacedBy=8)]
        pulls = [{"number": 8, "title": "batch 7", "branch": "batch-7", "draft": False, "head": head}]
        self.publish([lane("session_a", "c4"), lane("session_b", "c5")], landed=landed, pulls=pulls)
        out = self.run_idle()
        self.assertIn("session_b", self.listed_ids(out), "scope: a todo superseded lane is not listed: out: %r" % out)
        self.assertIn("session_a", self.listed_ids(out),
                      "a superseded lane whose step is doing is not listed: out: %r" % out)

    def test_a_replaced_by_that_is_not_an_int_skips_the_row_and_the_list_reads_unknown(self):
        # The control is lane c1, done and idle, with no landedPulls row: it is listed and the command exits 0. Then its
        # closed row carries replacedBy as JSON null, then as JSON true. Neither is an int, so the row is skipped, and the
        # whole list reads one unknown line with exit 1, as a skipped landedPulls row does everywhere else.
        self.publish([lane("session_a", "c1")])
        out = self.run_idle()
        self.assertIn("session_a", self.listed_ids(out), "scope: a lane with no landedPulls row is not listed: out: %r" % out)
        head = self.record_tip()
        for bad in (None, True):
            with self.subTest(replacedBy=bad):
                self.publish([lane("session_a", "c1")], landed=[self.closed_row(7, "lane/c1", head, replacedBy=bad)])
                code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live))
                self.assertEqual(out.splitlines(), ["unknown (1 landedPulls rows skipped)"],
                                 "a non-int replacedBy is not skipped: out: %r, err: %r" % (out, err))
                self.assertEqual(code, 1, "a skipped landedPulls row exits %d, so a caller reads the list as read: %s" % (code, err))

    def test_idle_lanes_starts_no_fetch_or_ls_remote_when_origin_holds_the_record_branch(self):
        # The read is local. GIT_TRACE logs every git command this run starts, so a fetch or ls-remote shows up in it.
        origin, clone = self.single_branch_clone()
        self.publish([lane("session_a", "c1")])
        trace = pathlib.Path(self.tmp.name) / "git-trace.log"
        code, out, err = self.run_merge("--idle-lanes", "--live", str(self.live), cwd=clone,
                                        drop=roadmap.TOKEN_VARS + ("CLAUDE_CODE_REMOTE", "CLAUDE_CODE_REMOTE_SESSION_ID"),
                                        extra_env={"GIT_TRACE": str(trace)})
        ran = trace.read_text(encoding="utf-8") if trace.exists() else ""
        self.assertRegex(ran, r"\brev-parse\b", "the trace logs no git call, so it proves nothing:\n" + err)
        network = r"\bgit (?:-C \S+ )?(?:fetch|ls-remote)\b"
        self.assertNotRegex(ran, network, "merge --idle-lanes started a git fetch or ls-remote:\n"
                            + "\n".join(line for line in ran.splitlines() if re.search(network, line)))
        self.assertEqual(code, 1, err)
        self.assertTrue(any(line.startswith("unknown (") for line in out.splitlines()), "out: %r, err: %r" % (out, err))


if __name__ == "__main__":
    unittest.main()
