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
        self.assertEqual(out.splitlines(), ["hold (step c3 still doing under this lane; lane session_a)", HELD_ONE], out)


# A `gh` for the --sessions and --items cases. It answers `gh api repos/<owner>/<repo>/pulls` from the file named by
# FAKE_GH_PULLS, the way GitHub's list route does: state (open by default), page and per_page, a Link header with
# rel="next", and the -i header block that the merge tool's paged read takes. --paginate gets every row. Each argv is
# logged to FAKE_GH_LOG as one JSON line. Any other call fails here, so a missed shim never reaches the real gh.
FAKE_GH = r'''#!/usr/bin/env python3
import json, os, re, sys

args = sys.argv[1:]
with open(os.environ["FAKE_GH_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(args) + "\n")
text = " ".join(args)
path = next((a.split("?", 1)[0] for a in args if re.match(r"repos/[^/?]+/[^/?]+(/pulls)?(\?|$)", a)), None)
if args[:1] != ["api"] or path is None:
    sys.stderr.write("fake gh: only `gh api repos/<owner>/<repo>[/pulls]` is answered; got %r\n" % (args,))
    sys.exit(1)
if not path.endswith("/pulls"):
    # The repo read (`gh api repos/{owner}/{repo}`): the default branch, as GitHub answers it.
    sys.stdout.write(json.dumps({"full_name": "owner/fixture", "default_branch": "main"}))
    sys.exit(0)
route = path


def param(name, default):
    found = re.search(r"(?:^|[?& ])%s=([^& ]+)" % name, text)
    return found.group(1) if found else default


state = param("state", "open")
rows = [r for r in json.load(open(os.environ["FAKE_GH_PULLS"], encoding="utf-8")) if state == "all" or r["state"] == state]
link = None
if "--paginate" in args:
    body = rows
else:
    per, page = int(param("per_page", "30")), int(param("page", "1"))
    start = (page - 1) * per
    body = rows[start:start + per]
    if start + per < len(rows):
        link = '<https://api.github.com/%s?page=%d&per_page=%d>; rel="next"' % (route, page + 1, per)
if "-i" in args or "--include" in args:
    head = "HTTP/2.0 200 OK\r\nContent-Type: application/json; charset=utf-8\r\n" + ("Link: %s\r\n" % link if link else "")
    sys.stdout.write(head + "\r\n" + json.dumps(body))
else:
    sys.stdout.write(json.dumps(body))
'''


def rest_pull(number, branch, head, base="main", merged=False, closed=False, draft=False, body=None):
    """A pull as GitHub's list route returns it: state, merged_at (the list has no merged flag), head and base refs, draft,
    and the body, which GitHub sends as null when the description is empty."""
    done = merged or closed
    return {"number": number, "title": "lane " + branch, "state": "closed" if done else "open", "draft": draft,
            "merged_at": "2026-11-07T12:00:00Z" if merged else None, "body": body,
            "head": {"ref": branch, "sha": head}, "base": {"ref": base}}


def raw_page(rows, more):
    """One page of list_sessions as the tool returns it, with the rows under data and the paging keys. The outer `ccr` key is
    the shape the tool printed when measured; whether it is the tool's own return key is not yet confirmed."""
    ids = [row["id"] for row in rows]
    return {"ccr": {"data": rows, "has_more": more, "first_id": ids[0] if ids else None, "last_id": ids[-1] if ids else None}}


class IdleLanesFromRawFiles(unittest.TestCase):
    """merge --idle-lanes --sessions FILE --items FILE, with no --live file. The pulls come from `gh api`, read once per
    state, through the fake gh on PATH. The repo has c3 doing, c4 done and c5 done. session_a (c3) is listed only through
    its merged pull. session_b (c4) waits on an open ready pull on lane/c4. session_c (c5) waits on an open page item."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=RUN_FOLDER)
        self.repo = roadmap.make_repo(self.tmp.name, steps={"c3": dict(roadmap.STEP, order=3, status="doing"),
                                                            "c4": dict(roadmap.STEP, order=4, status="done"),
                                                            "c5": dict(roadmap.STEP, order=5, status="done")})
        roadmap.git(self.repo, "remote", "add", "origin", "git@github.com:owner/fixture.git")
        self.off = roadmap.git(self.repo, "rev-parse", "HEAD").strip()  # the record branch: its commits never reach main
        self.bin = os.path.join(self.tmp.name, "bin")
        os.makedirs(self.bin)
        gh = os.path.join(self.bin, "gh")
        pathlib.Path(gh).write_text(FAKE_GH, encoding="utf-8")
        os.chmod(gh, 0o755)
        self.gh_log = os.path.join(self.tmp.name, "gh.log")
        self.gh_pulls = os.path.join(self.tmp.name, "pulls.json")
        pathlib.Path(self.gh_pulls).write_text(json.dumps([rest_pull(91, "lane/c3", self.off, merged=True),
                                                           rest_pull(92, "lane/c4", self.off, draft=False)]), encoding="utf-8")
        self.items = os.path.join(self.tmp.name, "items.json")
        pathlib.Path(self.items).write_text(json.dumps([{"id": "item-c5", "data": {
            "n": 1, "status": "open", "home": "step c5", "lane": "c5"}}]), encoding="utf-8")
        self.rows = [dict(lane("session_a", "c3"), title="lane: c3", created_at="2026-11-07T00:00:00Z"),
                     dict(lane("session_b", "c4"), title="lane: c4", created_at="2026-11-07T00:00:00Z"),
                     dict(lane("session_c", "c5"), title="lane: c5", created_at="2026-11-07T00:00:00Z")]
        self.sessions = os.path.join(self.tmp.name, "sessions.json")

    def tearDown(self):
        self.tmp.cleanup()

    def write_sessions(self, payload):
        pathlib.Path(self.sessions).write_text(json.dumps(payload), encoding="utf-8")

    def run_merge(self, *argv):
        """(exit code, stdout, stderr) of `merge.py <argv>` in the fixture checkout, with the fake gh first on PATH."""
        path = self.bin + os.pathsep + os.environ.get("PATH", os.defpath)
        env = _test_git.apply({**os.environ, **roadmap.GIT_ENV, "PATH": path,
                               "FAKE_GH_LOG": self.gh_log, "FAKE_GH_PULLS": self.gh_pulls})
        done = subprocess.run([sys.executable, str(MERGE), *argv], cwd=str(self.repo), capture_output=True,
                              text=True, env=env)
        return done.returncode, done.stdout, done.stderr

    def gh_calls(self):
        """The argv of each gh call the run made, one list per call."""
        p = pathlib.Path(self.gh_log)
        return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []

    def test_sessions_and_items_files_list_the_lane_whose_only_pull_merged_into_main(self):
        self.write_sessions(raw_page(self.rows, more=False))
        code, out, err = self.run_merge("--idle-lanes", "--sessions", self.sessions, "--items", self.items)
        self.assertEqual(out.splitlines(), ["session_a (c3; topic -)", SUMMARY_ONE],
                         "not listed from --sessions and --items (exit %d): stderr %r" % (code, err))
        pulls_calls = [call for call in self.gh_calls() if any("/pulls" in arg for arg in call)]
        self.assertTrue(pulls_calls, "gh was never asked for the pulls, so they did not come from the fetch")
        self.assertLessEqual(len(pulls_calls), 2, "the pull read made %d gh calls for the pulls: one per state, one page each, is the cost to hold" % len(pulls_calls))

    def test_sessions_and_items_files_list_a_lane_whose_only_pull_is_on_an_r2_head_that_names_it(self):
        # The lane's only pull is on c3-r2, outside lane_head_refs. Its body names the session, so the pull is in the lane's
        # PR set, and the merge into main lands the doing step. session_b stays held by its open pull.
        pathlib.Path(self.gh_pulls).write_text(json.dumps([
            rest_pull(92, "lane/c4", self.off, draft=False),
            rest_pull(93, "c3-r2", self.off, merged=True, body="Follow-up of https://claude.ai/code/session_a")]), encoding="utf-8")
        self.write_sessions(raw_page(self.rows, more=False))
        code, out, err = self.run_merge("--idle-lanes", "--sessions", self.sessions, "--items", self.items)
        self.assertEqual(out.splitlines(), ["session_a (c3; topic -)", SUMMARY_ONE],
                         "a pull on an -r2 head whose body names the session is not read through --sessions (exit %d): stderr %r" % (code, err))

    def test_sessions_as_a_list_of_pages_lists_a_lane_found_on_the_later_page(self):
        first, later = self.rows[1:], self.rows[:1]  # session_a, the listed lane, is on the second page
        self.write_sessions([raw_page(first, more=True), raw_page(later, more=False)])
        code, out, err = self.run_merge("--idle-lanes", "--sessions", self.sessions, "--items", self.items)
        self.assertEqual(out.splitlines(), ["session_a (c3; topic -)", SUMMARY_ONE],
                         "a lane on a later page of --sessions is not listed (exit %d): stderr %r" % (code, err))


if __name__ == "__main__":
    unittest.main()
