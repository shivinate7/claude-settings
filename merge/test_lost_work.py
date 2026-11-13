#!/usr/bin/env python3
"""Fixture suite for the lost-work rows of the batch review (merge/merge.py reviewed_block): one row per open lane pull request in
each of five states, so a batch review names every lane pull request that work could be lost on.

Run: python3 merge/test_lost_work.py

THE CONTRACT THE CASES PIN (the builder meets it):
- reviewed_block(h, live=None) takes the publisher's --live file. The file is read as the roadmap build reads it (skills/roadmap/build.py
  live_work, with the record branch's steps). The return stays (lines, ok). live=None reads no file.
- A row is one line: `lost-work #<n> (<state>): <why>; owner <owner>`. The owner is the role LOST_WORK_OWNER names, except that a row for
  state b names the lane's session id (the session in the pull request body's footer). An unreadable lane prints one line
  `lost-work #<n> unknown: <why>` and names no state.
- LOST_WORK_OWNER (merge/merge.py) maps a, b, b-archived, c, d and e to their owners.
- a: a done record older than 6 h (h.now() less the record's created_at), and no other open pull request on the base holds its head
  (Host.holds_head, the local-git reader).
- b: an open or bad record whose lane was not told after tell_lanes sent its message. A lane that is archived gets b-archived.
- c: no review record, and the lane is idle (completed or review ready) with its newest thread (live file, `pr` = n) more than 12 h
  before h.now().
- d: the pull request's lane session (footer) is archived.
- e: the pull request's head ref names a step (lane_head_refs) that is doing, and that step's lane session is absent or archived.
- A pull request in two states gets one row for each.
- Cost: no gh call beyond the reviewed read's (the count case). The lost-work rows read the live file and git only.

Each case runs reviewed_block over a PullsHost (merge/test_merge.py, imported, not copied) on one roadmap checkout whose origin is a
local bare repo behind the GitHub remote name (insteadOf), so Host.holds_head reads real git. The clock is the host's, a fixed NOW.
"""
import datetime
import inspect
import json
import pathlib
import re
import shutil
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import merge  # noqa: E402  merge/merge.py, the batch review under test
import test_merge as tm  # noqa: E402  PullsHost, batch_pull, record_text, lint_of and the other fakes: the one home, imported not copied
sys.path.insert(1, str(HERE.parent / "lint"))
sys.path.insert(2, str(HERE.parent / "skills" / "roadmap"))
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)
import _test_temp  # noqa: E402  test-temp-standard: one run folder per test run (lint/_test_temp.py)
import test_build as roadmap  # noqa: E402  the roadmap fixture: make_repo, session_row, STEP, git, iso_ago (one home)

REPO_SLUG = "owner/fixture"
REMOTE = "git@github.com:owner/fixture.git"
REPO_TAG = "cs-repo:" + REPO_SLUG
LANE_TAG = "cs-build:lane"
ARCHIVED, IDLE, RUNNING = "SESSION_STATUS_ARCHIVED", "SESSION_STATUS_IDLE", "SESSION_STATUS_RUNNING"
NOW = datetime.datetime(2026, 11, 13, 16, 0, tzinfo=datetime.timezone.utc).timestamp()  # the host's clock: every age is measured from it
ROUNDS_DONE = ("Round 1: reviewer, sonnet, PASS", "Round 2: reviewer, sonnet, PASS", "Round 3: reviewer, sonnet, PASS")
ROUNDS_OPEN = ("Round 1: reviewer, sonnet, FAIL",)
LOST_ROW = re.compile(r"^lost-work #(\d+) \(([a-e])\): (.+); owner (.+)$")
UNKNOWN_ROW = re.compile(r"^lost-work #(\d+) unknown: (.+)$")
NO_MAIL = (0, "")
NO_ROUTE = (1, "no route to the lane")

# Made in setUpModule, not at import, so a helper that imports this file leaks no folder.
RUN_FOLDER = None


def setUpModule():
    global RUN_FOLDER
    RUN_FOLDER = _test_temp.run_folder()


def tearDownModule():
    shutil.rmtree(RUN_FOLDER, ignore_errors=True)  # test-temp-standard: teardown removes the run folder


def iso_before(minutes):
    """An ISO UTC time `minutes` before the host's clock, shaped as a record's created_at and a thread's lastActivity."""
    when = datetime.datetime.fromtimestamp(NOW, datetime.timezone.utc) - datetime.timedelta(minutes=minutes)
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def owner_of(key):
    """The owner LOST_WORK_OWNER names for state `key`. A missing constant or key reads as text that fails the case by name."""
    return (getattr(merge, "LOST_WORK_OWNER", None) or {}).get(key, "no LOST_WORK_OWNER entry for state %s" % key)


def rows_for(lines, n):
    """-> the sorted (state, owner) of each lost-work row for pull request n, and ("unknown", why) for its unknown row."""
    found = []
    for line in lines:
        m = LOST_ROW.match(line)
        if m and int(m.group(1)) == n:
            found.append((m.group(2), m.group(4)))
        m = UNKNOWN_ROW.match(line)
        if m and int(m.group(1)) == n:
            found.append(("unknown", m.group(2)))
    return sorted(found)


class LostWorkRows(unittest.TestCase):
    """reviewed_block over one roadmap checkout. The record branch holds step c3, doing under session_gone. Each case adds its pull requests
    and lanes, writes the live file, and reads the lines of the batch review."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=RUN_FOLDER)
        steps = {"c3": dict(roadmap.STEP, order=3, status="doing", lane="session_gone")}
        self.repo = roadmap.make_repo(self.tmp.name, steps=steps)
        self.bare = pathlib.Path(self.tmp.name) / "origin.git"
        roadmap.git(self.tmp.name, "init", "-q", "--bare", str(self.bare))
        roadmap.git(self.repo, "remote", "add", "origin", REMOTE)
        roadmap.git(self.repo, "config", "url.%s.insteadOf" % self.bare, REMOTE)
        roadmap.git(self.repo, "push", "-q", str(self.bare), "main")
        self.main = roadmap.git(self.repo, "rev-parse", "main").strip()
        self.live = pathlib.Path(self.tmp.name) / "live.json"
        self.heads, self.pulls, self.comments, self.checks, self.sessions, self.threads = {}, [], [], {}, [], []
        self.publish()

    def tearDown(self):
        self.tmp.cleanup()

    def pr(self, n, parent=None, head_ref=None, session="session_a", record=None, at=60):
        """Open pull request n on main. `record` is "done" or "open", posted `at` minutes before now (a done record comes with a lane-lint
        PASS at its head), or None for no record. `session` is the lane session in the body's footer (None: no footer)."""
        tree = roadmap.git(self.repo, "rev-parse", (parent or self.main) + "^{tree}").strip()
        sha = roadmap.git(self.repo, "commit-tree", tree, "-p", parent or self.main, "-m", "pr %d" % n,
                          env=_test_git.apply({})).strip()
        roadmap.git(self.repo, "push", "-q", str(self.bare), "%s:refs/pull/%d/head" % (sha, n))
        self.heads[n] = sha
        body = "Lane work.\n\nhttps://claude.ai/code/%s" % session if session else ""
        self.pulls.append({**tm.batch_pull(n, sha, head_ref=head_ref, created_at="2026-11-01T00:00:00Z"), "body": body})
        self.checks[sha] = [tm.batch_run("checks", "completed", "success")]
        if record:
            rounds = ROUNDS_DONE if record == "done" else ROUNDS_OPEN
            self.comments.append(tm.review_comment(1000 + n * 10, n, tm.record_text(rounds=rounds, head=sha, n=n), created=iso_before(at)))
            if record == "done":
                self.comments.append(tm.lint_of(n, sha))

    def lane(self, sid, status=RUNNING, bucket=roadmap.BUCKET_WORKING, step="c1"):
        """A lane row of this repo: live unless `status` is archived."""
        self.sessions.append(roadmap.session_row(sid, status, LANE_TAG, "cs-step:" + step, REPO_TAG, status_bucket=bucket))

    def thread(self, n, minutes):
        """The newest activity of the thread that names pull request n, `minutes` before now."""
        self.threads.append({"title": "work on #%d" % n, "state": "working", "lastActivity": iso_before(minutes), "pr": n})

    def publish(self, read_at=None):
        """Write the live file: the lanes and threads so far, read `read_at` (default five minutes ago)."""
        value = {"readAt": read_at or roadmap.iso_ago(5), "threads": list(self.threads), "pulls": [], "items": [],
                 "sessions": list(self.sessions)}
        self.live.write_text(json.dumps(value), encoding="utf-8")

    def host(self, count_gh=False, mail_result=NO_MAIL):
        """A PullsHost over the pull requests so far, on this checkout (holds_head runs git here) and the fixed clock."""
        h = tm.PullsHost(list(self.pulls), dict(self.checks), comments=list(self.comments), repo=REPO_SLUG, count_gh=count_gh,
                         mail_result=mail_result)
        h.cwd, h.now = str(self.repo), (lambda: NOW)
        return h

    def block(self, h, live=True):
        """The lines of reviewed_block(h), read with the live file when `live`. A merge.py with no live= seam reads the lines alone, so the
        case fails on its missing row and not on the signature."""
        if "live" not in inspect.signature(merge.reviewed_block).parameters:
            return merge.reviewed_block(h)[0]
        lines, _ok = merge.reviewed_block(h, live=str(self.live) if live else None)
        return lines

    # State a: a done record older than 6 h, in no batch.

    def test_a_done_pr_in_no_batch_past_six_hours_lists_one_row(self):
        self.pr(7, record="done", at=361)
        self.lane("session_a")
        self.publish()
        lines = self.block(self.host())
        self.assertEqual(rows_for(lines, 7), [("a", owner_of("a"))], "no state-a row for #7, a done record 361 minutes old: %r" % lines)

    def test_a_done_pr_just_under_six_hours_lists_no_row(self):
        self.pr(7, record="done", at=359)
        self.lane("session_a")
        self.publish()
        lines = self.block(self.host())
        self.assertEqual(rows_for(lines, 7), [], "a row for #7 at 359 minutes, under the six-hour line: %r" % lines)

    def test_a_done_pr_held_by_another_open_pr_lists_no_row(self):
        # The control: alone, #7 is in no batch and lists its row. Then #9's head holds #7's head, so #7 is in a batch.
        self.pr(7, record="done", at=361)
        self.lane("session_a")
        self.publish()
        lines = self.block(self.host())
        self.assertEqual(rows_for(lines, 7), [("a", owner_of("a"))], "control: no state-a row for #7 while no open pull request holds it: %r" % lines)
        self.pr(9, parent=self.heads[7], session=None)
        lines = self.block(self.host())
        self.assertEqual(rows_for(lines, 7), [], "a row for #7 though #9 holds its head, so #7 is in a batch: %r" % lines)

    # State b: an open record whose lane was not told.

    def test_b_open_record_whose_lane_was_not_told_lists_a_row_for_the_lane(self):
        self.pr(7, record="open", at=30)
        self.lane("session_a")
        self.publish()
        lines = self.block(self.host(mail_result=NO_ROUTE))
        self.assertEqual(rows_for(lines, 7), [("b", "session_a")], "no state-b row for #7 naming session_a, its lane: %r" % lines)

    def test_b_open_record_whose_lane_was_told_lists_no_row(self):
        self.pr(7, record="open", at=30)
        self.lane("session_a")
        self.publish()
        lines = self.block(self.host(mail_result=NO_MAIL))
        self.assertEqual(rows_for(lines, 7), [], "a row for #7 though its lane was sent its message: %r" % lines)

    def test_b_with_an_archived_lane_names_the_coordinator(self):
        self.pr(7, record="open", at=30)
        self.lane("session_a", status=ARCHIVED, bucket=roadmap.BUCKET_COMPLETED)
        self.publish()
        rows = rows_for(self.block(self.host(mail_result=NO_ROUTE)), 7)
        self.assertIn(("b", owner_of("b-archived")), rows, "no state-b row for #7 that names the coordinator, the owner of an archived lane: %r" % rows)
        self.assertNotIn(("b", "session_a"), rows, "the state-b row for #7 names the archived session, not the coordinator: %r" % rows)

    # State c: no review record, and the lane idle over 12 h.

    def test_c_no_record_and_lane_idle_past_twelve_hours_lists_a_row(self):
        self.pr(7, record=None)
        self.lane("session_a", status=IDLE, bucket=roadmap.BUCKET_COMPLETED)
        self.thread(7, minutes=781)
        self.publish()
        lines = self.block(self.host())
        self.assertEqual(rows_for(lines, 7), [("c", owner_of("c"))], "no state-c row for #7, idle 781 minutes with no record: %r" % lines)

    def test_c_lane_idle_just_under_twelve_hours_lists_no_row(self):
        self.pr(7, record=None)
        self.lane("session_a", status=IDLE, bucket=roadmap.BUCKET_COMPLETED)
        self.thread(7, minutes=719)
        self.publish()
        lines = self.block(self.host())
        self.assertEqual(rows_for(lines, 7), [], "a row for #7 at 719 minutes idle, under the twelve-hour line: %r" % lines)

    # State d: the lane is archived and the pull request is open.

    def test_d_archived_lane_with_an_open_pr_lists_a_row(self):
        self.pr(7, record="done", at=60)
        self.lane("session_a", status=ARCHIVED, bucket=roadmap.BUCKET_COMPLETED)
        self.publish()
        lines = self.block(self.host())
        self.assertEqual(rows_for(lines, 7), [("d", owner_of("d"))], "no state-d row for #7, whose lane is archived: %r" % lines)

    def test_d_live_lane_with_an_open_pr_lists_no_row(self):
        self.pr(7, record="done", at=60)
        self.lane("session_a")
        self.publish()
        lines = self.block(self.host())
        self.assertEqual(rows_for(lines, 7), [], "a row for #7 whose lane is live: %r" % lines)

    # State e: the step is doing and its lane is gone.

    def test_e_doing_step_whose_lane_is_gone_lists_a_row(self):
        self.pr(7, head_ref="c3", record="done", at=60, session="session_gone")
        self.publish()  # no session row for session_gone: the lane is gone
        lines = self.block(self.host())
        self.assertEqual(rows_for(lines, 7), [("e", owner_of("e"))], "no state-e row for #7, on doing step c3 whose lane is gone: %r" % lines)

    def test_e_doing_step_whose_lane_is_live_lists_no_row(self):
        self.pr(7, head_ref="c3", record="done", at=60, session="session_gone")
        self.lane("session_gone", step="c3")
        self.publish()
        lines = self.block(self.host())
        self.assertEqual(rows_for(lines, 7), [], "a row for #7 on doing step c3 whose lane is live: %r" % lines)

    # Two states at once: one row for each.

    def test_a_pr_in_two_states_gets_one_row_for_each(self):
        self.pr(7, record="done", at=361)
        self.lane("session_a", status=ARCHIVED, bucket=roadmap.BUCKET_COMPLETED)
        self.publish()
        lines = self.block(self.host())
        self.assertEqual(rows_for(lines, 7), sorted([("a", owner_of("a")), ("d", owner_of("d"))]),
                         "#7 is in states a and d, and needs one row each: %r" % lines)

    # Failure classes: a false row on a healthy pull request, and an unreadable lane that must read unknown.

    def test_a_healthy_pr_lists_no_lost_work_row(self):
        self.pr(7, record="done", at=60)
        self.lane("session_a")
        self.thread(7, minutes=5)
        self.publish()
        lines = self.block(self.host())
        self.assertEqual([line for line in lines if line.startswith("lost-work ")], [], "a false row on a healthy pull request: %r" % lines)

    def test_unreadable_lane_data_prints_an_unknown_row_not_no_row(self):
        self.pr(7, record=None)
        self.lane("session_a", status=IDLE, bucket=roadmap.BUCKET_COMPLETED)
        self.thread(7, minutes=781)
        self.publish()
        control = rows_for(self.block(self.host()), 7)
        self.assertEqual(control, [("c", owner_of("c"))], "control: the live file reads, so no state-c row for #7 is missing: %r" % control)
        self.publish(read_at=roadmap.iso_ago(120))
        rows = rows_for(self.block(self.host()), 7)
        self.assertEqual([state for state, _why in rows], ["unknown"], "a stale live file gives #7 no unknown row: %r" % rows)

    # Cost, empty and full-size states.

    def test_the_lost_work_rows_add_no_gh_call_to_the_review_read(self):
        self.pr(7, record=None)
        self.lane("session_a", status=IDLE, bucket=roadmap.BUCKET_COMPLETED)
        self.thread(7, minutes=781)
        self.publish()
        with_live, without_live = self.host(count_gh=True), self.host(count_gh=True)
        lines = self.block(with_live, live=True)
        self.block(without_live, live=False)
        self.assertEqual(with_live.gh_calls, without_live.gh_calls,
                         "the live file adds gh calls to the review read: %r over %r" % (with_live.gh_calls, without_live.gh_calls))
        self.assertEqual(rows_for(lines, 7), [("c", owner_of("c"))], "no state-c row for #7 in the live run: %r" % lines)

    def test_no_open_pr_lists_no_lost_work_row(self):
        self.publish()
        lines = self.block(self.host())
        self.assertEqual([line for line in lines if line.startswith("lost-work ")], [], "a row with no open pull request: %r" % lines)

    def test_full_size_batch_lists_only_the_pr_in_a_state(self):
        # Twenty-five pull requests whose records are open and told, and one with no record whose lane is idle past 12 h.
        self.lane("session_a")
        for n in range(2, 27):
            self.pr(n, record="open", at=30)
        self.pr(40, record=None, session="session_b")
        self.lane("session_b", status=IDLE, bucket=roadmap.BUCKET_COMPLETED)
        self.thread(40, minutes=781)
        self.publish()
        lines = self.block(self.host())
        rows = [line for line in lines if line.startswith("lost-work ")]
        self.assertEqual([row.split(":")[0] for row in rows], ["lost-work #40 (c)"], "a row on a healthy pull request among 26: %r" % lines)
        self.assertEqual(rows_for(lines, 40), [("c", owner_of("c"))], "no state-c row for #40 in the full-size batch: %r" % lines)


class LostWorkOwners(unittest.TestCase):
    def test_owner_map_names_one_owner_per_state(self):
        self.assertEqual(getattr(merge, "LOST_WORK_OWNER", None),
                         {"a": "batch runner", "b": "the lane's own session", "b-archived": "coordinator", "c": "coordinator",
                          "d": "coordinator", "e": "triage"},
                         "merge.LOST_WORK_OWNER does not name the owner of each state")


if __name__ == "__main__":
    unittest.main()
