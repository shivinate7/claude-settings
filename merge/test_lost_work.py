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
- f: a branch on origin, ahead of main, with no open pull request and no `archive/` prefix. `main` and `batch-*` are never listed. Its row is
  `lost-work branch <name> (f): <why>; owner <owner>`; the owner is the coordinator (LOST_WORK_OWNER["f"]). The branch list comes from the
  live file's branches list and the ahead counts from local git: no gh call per branch.
- reviewed_ledger(h, live, verdicts) -> (rows, count_line, ok), the ledger. Its rows are the lost-work rows, one per pull request and one per
  f branch (pr = the branch name), with the keys in LEDGER_FIELDS, ordered by pr. It reads the live file once, through lost_work_rows.
  `verdicts` is the path of docs/backlog-drain/verdicts.tsv: a header row, then tab-separated PR, verdict, kind, step, head (the first 12
  characters of the pull request's head), reason. A row is sorted only when its verdict is keep, rebuild or close and its head is the live
  head. count_line is `unsorted: N`, or `unsorted: unknown-read` when the verdicts file cannot be read: then every row is unsorted and ok is False.
- The command line: `merge --reviewed --live FILE --ledger [--out FILE] --verdicts FILE` (build_parser).

Each case runs reviewed_block over a PullsHost (merge/test_merge.py, imported, not copied) on one roadmap checkout whose origin is a
local bare repo behind the GitHub remote name (insteadOf), so Host.holds_head reads real git. The clock is the host's, a fixed NOW.
"""
import contextlib
import datetime
import inspect
import io
import json
import pathlib
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

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
BRANCH_ROW = re.compile(r"^lost-work branch (\S+) \(f\): (.+); owner (\S+)$")
BRANCH = "claude/ecstatic-euler-capib9"  # the incident branch: pushed, one commit ahead of main, no pull request (state f)
BRANCH_FILE = "docs/plans/r42-part2-design.md"
BRANCH_TEXT = "R42 part 2 design\n"
VERDICT_COLUMNS = ("PR", "verdict", "kind", "step", "head", "reason")  # the verdicts.tsv header row
LEDGER_FIELDS = {"pr", "step", "state", "group", "record", "age_h", "commits_not_on_main", "subsumed_by", "files", "verdict", "sorted"}
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


def branch_rows(lines, name):
    """-> the sorted (why, owner) of each lost-work branch row (state f) that names branch `name`."""
    matches = [BRANCH_ROW.match(line) for line in lines]
    return sorted((m.group(2), m.group(3)) for m in matches if m and m.group(1) == name)


def row_of(rows, pr):
    """-> the ledger row for pull request number `pr` (or for branch name `pr`), or None."""
    return next((row for row in rows if row.get("pr") == pr), None)


class LostWorkFixture(unittest.TestCase):
    """The one roadmap checkout every case in this file builds on. The record branch holds step c3, doing under session_gone. Each case adds
    its pull requests, pushed branches and lanes, writes the live file, and reads what reviewed_block or reviewed_ledger prints."""

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
        self.branches = []  # the live file's branches list: each pushed branch, the publisher's read of origin
        role = mock.patch.object(merge, "read_merge_role", lambda: "batch-runner")  # the lane mail gate: a session with no batch-runner role sends nothing
        role.start()
        self.addCleanup(role.stop)
        self.publish()

    def tearDown(self):
        self.tmp.cleanup()

    def commit_on(self, parent, files=None, message="work"):
        """A commit on `parent` that adds `files` (path -> text) to its tree, or keeps the parent's tree when `files` is None. -> its sha."""
        if files:
            index = {"GIT_INDEX_FILE": str(pathlib.Path(self.tmp.name) / "index")}
            roadmap.git(self.repo, "read-tree", parent, env=index)
            for path, text in files.items():
                source = pathlib.Path(self.tmp.name) / "blob"
                source.write_text(text, encoding="utf-8")
                blob = roadmap.git(self.repo, "hash-object", "-w", str(source)).strip()
                roadmap.git(self.repo, "update-index", "--add", "--cacheinfo", "100644,%s,%s" % (blob, path), env=index)
            tree = roadmap.git(self.repo, "write-tree", env=index).strip()
        else:
            tree = roadmap.git(self.repo, "rev-parse", parent + "^{tree}").strip()
        return roadmap.git(self.repo, "commit-tree", tree, "-p", parent, "-m", message, env=_test_git.apply({})).strip()

    def push_branch(self, name, sha):
        """Push branch `name` to origin at `sha`, and list it in the live file's branches, as the publisher does. No pull request is opened."""
        roadmap.git(self.repo, "push", "-q", str(self.bare), "%s:refs/heads/%s" % (sha, name))
        self.branches.append({"name": name})

    def pr(self, n, parent=None, head_ref=None, session="session_a", record=None, at=60, files=None):
        """Open pull request n on main. `record` is "done" or "open", posted `at` minutes before now (a done record comes with a lane-lint
        PASS at its head), or None for no record. `session` is the lane session in the body's footer (None: no footer). `files` (path -> text)
        are the files its commit adds."""
        sha = self.commit_on(parent or self.main, files, "pr %d" % n)
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
                 "sessions": list(self.sessions), "branches": list(self.branches)}
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

class LostWorkRows(LostWorkFixture):
    """reviewed_block's lost-work rows: the five pull request states, and the pushed branches (state f)."""

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

    def test_b_open_record_with_no_footer_names_the_coordinator(self):
        self.pr(7, record="open", at=30, session=None)  # no session in the footer: no lane to tell, so the coordinator owns the row
        self.publish()
        rows = rows_for(self.block(self.host()), 7)
        self.assertEqual(rows, [("b", "coordinator")], "no state-b row for #7, whose body has no session footer, that names the coordinator: %r" % rows)

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

    def test_c_stale_record_counts_as_no_record(self):
        self.pr(7, record="done", at=60)
        self.lane("session_a", status=IDLE, bucket=roadmap.BUCKET_COMPLETED)
        self.thread(7, minutes=781)
        self.publish()
        control = [state for state, _owner in rows_for(self.block(self.host()), 7)]
        self.assertNotIn("c", control, "control: #7 with a current done record gets a state-c row: %r" % control)
        # The pull request head moves: the done record names the old head, so it is stale and counts as no record.
        old = self.heads[7]
        sha = self.commit_on(old, None, "newer")
        roadmap.git(self.repo, "push", "-q", str(self.bare), "%s:refs/pull/7/head" % sha)
        self.heads[7] = sha
        pull = next(p for p in self.pulls if p["number"] == 7)
        pull["head"] = {**pull["head"], "sha": sha}
        self.checks[sha] = self.checks[old]
        rows = [state for state, _owner in rows_for(self.block(self.host()), 7)]
        self.assertIn("c", rows, "no state-c row for #7, whose done record names an older head, so it counts as no record: %r" % rows)

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

    def test_footer_session_absent_from_the_live_lanes_gives_an_unknown_row(self):
        self.pr(7, record="done", at=60, session="session_nowhere")  # no lane row for session_nowhere: the footer names a lane the read does not hold
        self.publish()
        rows = rows_for(self.block(self.host()), 7)
        self.assertEqual([state for state, _why in rows], ["unknown"], "no unknown row for #7, whose footer session is absent from the live lanes: %r" % rows)

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

    # State f: a pushed branch ahead of main, with no open pull request and no archive/ prefix. Each negative case lists, in the same run, the
    # branch that must stay listed, so a missing row cannot pass a negative case.

    def test_f_pushed_branch_ahead_of_main_with_no_pr_lists_a_row(self):
        self.push_branch(BRANCH, self.commit_on(self.main, {BRANCH_FILE: BRANCH_TEXT}))
        self.publish()
        rows = branch_rows(self.block(self.host()), BRANCH)
        self.assertEqual(len(rows), 1, "no state-f row for %s, pushed one commit ahead of main with no pull request: %r" % (BRANCH, rows))
        self.assertTrue(rows[0][0].strip(), "the state-f row for %s gives no why" % BRANCH)
        self.assertEqual(rows[0][1], owner_of("f"), "the state-f row for %s names %r, not the owner of state f" % (BRANCH, rows[0][1]))

    def test_f_archive_branch_lists_no_row(self):
        self.push_branch("archive/claude/old-plan", self.commit_on(self.main, {"docs/plans/old.md": "old plan\n"}))
        self.push_branch(BRANCH, self.commit_on(self.main, {BRANCH_FILE: BRANCH_TEXT}))
        self.publish()
        lines = self.block(self.host())
        self.assertEqual(len(branch_rows(lines, BRANCH)), 1, "control: no state-f row for %s, ahead of main with no pull request: %r" % (BRANCH, lines))
        self.assertEqual(branch_rows(lines, "archive/claude/old-plan"), [], "a state-f row for an archive/ branch: %r" % lines)

    def test_f_branch_with_an_open_pr_lists_no_f_row(self):
        self.pr(7, head_ref="claude/pr-held", record=None, session=None)
        self.push_branch("claude/pr-held", self.heads[7])
        self.push_branch(BRANCH, self.commit_on(self.main, {BRANCH_FILE: BRANCH_TEXT}))
        self.publish()
        lines = self.block(self.host())
        self.assertEqual(len(branch_rows(lines, BRANCH)), 1, "control: no state-f row for %s, ahead of main with no pull request: %r" % (BRANCH, lines))
        self.assertEqual(branch_rows(lines, "claude/pr-held"), [], "a state-f row for claude/pr-held, the head of open pull request #7: %r" % lines)

    def test_f_branch_fully_merged_into_main_lists_no_row(self):
        self.push_branch("claude/merged-last-week", self.main)
        self.push_branch(BRANCH, self.commit_on(self.main, {BRANCH_FILE: BRANCH_TEXT}))
        self.publish()
        lines = self.block(self.host())
        self.assertEqual(len(branch_rows(lines, BRANCH)), 1, "control: no state-f row for %s, ahead of main with no pull request: %r" % (BRANCH, lines))
        self.assertEqual(branch_rows(lines, "claude/merged-last-week"), [], "a state-f row for a branch at main, which is not ahead: %r" % lines)

    def test_f_branch_with_an_archive_copy_lists_no_row(self):
        filed = self.commit_on(self.main, {"docs/plans/filed.md": "filed\n"})
        self.push_branch("claude/filed", filed)
        self.push_branch("archive/claude/filed", filed)  # the work was filed away under archive/
        self.push_branch(BRANCH, self.commit_on(self.main, {BRANCH_FILE: BRANCH_TEXT}))
        self.publish()
        lines = self.block(self.host())
        self.assertEqual(len(branch_rows(lines, BRANCH)), 1, "control: no state-f row for %s, ahead of main with no pull request: %r" % (BRANCH, lines))
        self.assertEqual(branch_rows(lines, "claude/filed"), [], "a state-f row for claude/filed, which has an archive/claude/filed copy: %r" % lines)

    def test_f_branch_whose_tip_an_open_pr_holds_lists_no_row(self):
        held = self.commit_on(self.main, {"docs/held.md": "h\n"})
        self.push_branch("claude/under-a-pr", held)
        self.pr(7, parent=held, head_ref="claude/other-name", record=None, session=None)  # open pull request #7 holds the branch's tip, under another head ref
        self.push_branch(BRANCH, self.commit_on(self.main, {BRANCH_FILE: BRANCH_TEXT}))
        self.publish()
        lines = self.block(self.host())
        self.assertEqual(len(branch_rows(lines, BRANCH)), 1, "control: no state-f row for %s, ahead of main with no pull request: %r" % (BRANCH, lines))
        self.assertEqual(branch_rows(lines, "claude/under-a-pr"), [], "a state-f row for claude/under-a-pr, whose tip open pull request #7 holds: %r" % lines)

    def test_f_incident_branch_still_lists_beside_the_archive_and_pr_filters(self):
        # The control for the two skips above: the incident branch lists while an archive/ branch and an open pull request are in the same run.
        self.pr(7, record=None, session=None)
        self.push_branch(BRANCH, self.commit_on(self.main, {BRANCH_FILE: BRANCH_TEXT}))
        self.push_branch("archive/claude/other", self.commit_on(self.main, {"docs/o.md": "o\n"}))
        self.publish()
        self.assertEqual(len(branch_rows(self.block(self.host()), BRANCH)), 1, "no state-f row for %s beside an archive/ branch and an open pull request" % BRANCH)

    def test_f_main_and_integration_branches_are_never_listed(self):
        self.branches.append({"name": "main"})
        self.push_branch("batch-132", self.commit_on(self.main, {"docs/batch-note.md": "batch\n"}))
        self.push_branch(BRANCH, self.commit_on(self.main, {BRANCH_FILE: BRANCH_TEXT}))
        self.publish()
        lines = self.block(self.host())
        self.assertEqual(len(branch_rows(lines, BRANCH)), 1, "control: no state-f row for %s, ahead of main with no pull request: %r" % (BRANCH, lines))
        self.assertEqual(branch_rows(lines, "main"), [], "a state-f row for main: %r" % lines)
        self.assertEqual(branch_rows(lines, "batch-132"), [], "a state-f row for the integration branch batch-132: %r" % lines)

    def test_f_listing_adds_no_gh_call_to_the_review_read(self):
        self.pr(7, record="done", at=60)
        self.lane("session_a")
        self.publish()
        without = self.host(count_gh=True)
        self.block(without)
        self.push_branch(BRANCH, self.commit_on(self.main, {BRANCH_FILE: BRANCH_TEXT}))
        self.push_branch("archive/claude/old-plan", self.commit_on(self.main, {"docs/plans/old.md": "old plan\n"}))
        self.push_branch("claude/merged-last-week", self.main)
        self.publish()
        with_branches = self.host(count_gh=True)
        lines = self.block(with_branches)
        self.assertEqual(len(branch_rows(lines, BRANCH)), 1, "control: no state-f row for %s in the run with the branches: %r" % (BRANCH, lines))
        self.assertEqual(with_branches.gh_calls, without.gh_calls,
                         "the branch list adds gh calls to the review read: %r over %r" % (with_branches.gh_calls, without.gh_calls))


class LostWorkOwners(unittest.TestCase):
    def test_owner_map_names_one_owner_per_state(self):
        self.assertEqual(getattr(merge, "LOST_WORK_OWNER", None),
                         {"a": "batch runner", "b": "the lane's own session", "b-archived": "coordinator", "c": "coordinator",
                          "d": "coordinator", "e": "triage", "f": "coordinator"},
                         "merge.LOST_WORK_OWNER does not name the owner of each state")


class LostWorkLedger(LostWorkFixture):
    """reviewed_ledger: one row per lost-work pull request and per pushed branch in state f, each with its verdict from the verdicts file. The
    ledger reads the live file through the batch review's reader, so the states it names are the states the batch review names."""

    def ledger(self, h, verdicts):
        """-> (rows, count_line, ok) of merge.reviewed_ledger over this checkout's live file and the verdicts file at `verdicts`. A merge.py with
        no reviewed_ledger gives ([], None, None), so each case fails on the row or the count line it names, not on the missing name."""
        fn = getattr(merge, "reviewed_ledger", None)
        if fn is None:
            return [], None, None
        return fn(h, str(self.live), str(verdicts))

    def verdict_file(self, *rows):
        """The verdicts file: its header row, then each (PR, verdict, kind, step, head, reason) of `rows`. -> its path."""
        path = pathlib.Path(self.tmp.name) / "verdicts.tsv"
        lines = ["\t".join(VERDICT_COLUMNS)] + ["\t".join(str(cell) for cell in row) for row in rows]
        path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
        return path

    def verdict(self, n, verdict="keep", head=None):
        """A verdict row for pull request n at its live head (`head` replaces the head, to make the row stale). Call after pr(n)."""
        return (n, verdict, "code", "c1", (head or self.heads[n])[:12], "reason")

    def test_a_lost_pr_row_has_the_fields_the_ledger_names(self):
        self.pr(7, record="done", at=361)
        self.lane("session_a")
        self.publish()
        rows, _count, _ok = self.ledger(self.host(), self.verdict_file(self.verdict(7)))
        row = row_of(rows, 7)
        self.assertIsNotNone(row, "no ledger row for #7, a done record 361 minutes old: %r" % rows)
        self.assertEqual(set(row), LEDGER_FIELDS, "the ledger row's keys are not the fields the ledger names: %r" % sorted(row))
        self.assertEqual(row["state"], "a", "the ledger row for #7 names state %r, not a: %r" % (row["state"], row))
        self.assertIs(row["sorted"], True, "#7 has a verdict at its live head and reads sorted %r: %r" % (row["sorted"], row))

    def test_a_pr_with_no_verdict_is_unsorted(self):
        self.pr(7, record="done", at=361)
        self.lane("session_a")
        self.publish()
        rows, count, _ok = self.ledger(self.host(), self.verdict_file())
        row = row_of(rows, 7)
        self.assertIsNotNone(row, "no ledger row for #7, a done record 361 minutes old: %r" % rows)
        self.assertIs(row["sorted"], False, "#7 has no verdict and reads sorted %r: %r" % (row["sorted"], row))
        self.assertEqual(count, "unsorted: 1", "the count line for one pull request with no verdict: %r" % count)

    def test_a_pr_with_a_verdict_at_its_live_head_is_sorted(self):
        self.pr(7, record="done", at=361)
        self.lane("session_a")
        self.publish()
        rows, count, _ok = self.ledger(self.host(), self.verdict_file(self.verdict(7, "rebuild")))
        row = row_of(rows, 7)
        self.assertIsNotNone(row, "no ledger row for #7, a done record 361 minutes old: %r" % rows)
        self.assertIs(row["sorted"], True, "#7 has a verdict at its live head and reads sorted %r: %r" % (row["sorted"], row))
        self.assertEqual(row["verdict"], "rebuild", "the verdict of #7 is %r, not the one the file gives: %r" % (row["verdict"], row))
        self.assertEqual(count, "unsorted: 0", "the count line when every row has a verdict: %r" % count)

    def test_a_verdict_at_an_old_head_is_stale_and_unsorted(self):
        self.pr(7, record="done", at=361)
        self.lane("session_a")
        self.publish()
        rows, count, _ok = self.ledger(self.host(), self.verdict_file(self.verdict(7, head="0" * 40)))
        row = row_of(rows, 7)
        self.assertIsNotNone(row, "no ledger row for #7, a done record 361 minutes old: %r" % rows)
        self.assertIs(row["sorted"], False, "#7's verdict names another head, so it is stale, yet #7 reads sorted: %r" % row)
        self.assertEqual(count, "unsorted: 1", "the count line for one stale verdict: %r" % count)

    def test_the_unsorted_count_is_one_number_over_all_rows(self):
        self.pr(7, record="done", at=361)
        self.lane("session_a")
        self.pr(8, record="open", at=30, session="session_b")
        self.lane("session_b")
        self.pr(9, record="done", at=60, session="session_d")
        self.lane("session_d", status=ARCHIVED, bucket=roadmap.BUCKET_COMPLETED)
        self.publish()
        rows, count, _ok = self.ledger(self.host(mail_result=NO_ROUTE), self.verdict_file(self.verdict(7)))
        self.assertEqual([row.get("pr") for row in rows], [7, 8, 9], "scope: the ledger rows are not #7 (a), #8 (b) and #9 (d): %r" % rows)
        self.assertEqual(count, "unsorted: 2", "the count line for three rows, two with no verdict: %r" % count)

    def test_a_missing_verdicts_file_leaves_every_row_unsorted_and_reads_unknown(self):
        self.pr(7, record="done", at=361)
        self.lane("session_a")
        self.publish()
        rows, count, ok = self.ledger(self.host(), pathlib.Path(self.tmp.name) / "no-such-verdicts.tsv")
        self.assertEqual([row.get("pr") for row in rows], [7], "scope: the ledger has no row for #7: %r" % rows)
        self.assertEqual([row["sorted"] for row in rows], [False], "a row reads sorted with no verdicts file to read it from: %r" % rows)
        self.assertEqual(count, "unsorted: unknown-read", "a missing verdicts file reads as a count, not unknown-read: %r" % count)
        self.assertIs(ok, False, "a missing verdicts file leaves ok True: %r" % ok)

    def test_an_unreadable_verdicts_file_reads_unknown_never_clear(self):
        self.pr(7, record="done", at=361)
        self.lane("session_a")
        self.publish()
        directory = pathlib.Path(self.tmp.name) / "verdicts-dir"
        directory.mkdir()  # a directory cannot be read as the verdicts file
        rows, count, ok = self.ledger(self.host(), directory)
        self.assertEqual([row.get("pr") for row in rows], [7], "scope: the ledger has no row for #7: %r" % rows)
        self.assertEqual([row["sorted"] for row in rows], [False], "a row reads sorted with an unreadable verdicts file: %r" % rows)
        self.assertEqual(count, "unsorted: unknown-read", "an unreadable verdicts file reads as clear or as a count: %r" % count)
        self.assertIs(ok, False, "an unreadable verdicts file leaves ok True: %r" % ok)

    def test_a_verdict_word_outside_keep_rebuild_close_is_unsorted(self):
        self.pr(7, record="done", at=361)
        self.lane("session_a")
        self.publish()
        rows, count, _ok = self.ledger(self.host(), self.verdict_file(self.verdict(7, "maybe")))
        row = row_of(rows, 7)
        self.assertIsNotNone(row, "no ledger row for #7, a done record 361 minutes old: %r" % rows)
        self.assertIs(row["sorted"], False, "#7's verdict word is maybe, not keep, rebuild or close, yet #7 reads sorted: %r" % row)
        self.assertEqual(count, "unsorted: 1", "the count line for one unknown verdict word: %r" % count)

    def test_a_healthy_pr_gets_no_ledger_row(self):
        self.pr(7, record="done", at=361)
        self.pr(12, record="done", at=60)  # healthy: a done record 60 minutes old, its lane live
        self.lane("session_a")
        self.publish()
        rows, _count, _ok = self.ledger(self.host(), self.verdict_file(self.verdict(7), self.verdict(12)))
        self.assertIsNotNone(row_of(rows, 7), "scope: no ledger row for the lost pull request #7: %r" % rows)
        self.assertIsNone(row_of(rows, 12), "a ledger row for #12, a healthy pull request: %r" % rows)

    def test_rows_are_ordered_by_pr_and_a_rerun_writes_the_same_output(self):
        self.pr(9, record="done", at=361)
        self.pr(7, record="done", at=361)
        self.lane("session_a")
        self.publish()
        verdicts = self.verdict_file(self.verdict(7), self.verdict(9))
        first = self.ledger(self.host(), verdicts)
        second = self.ledger(self.host(), verdicts)
        self.assertEqual([row.get("pr") for row in first[0]], [7, 9], "the ledger rows are not in pr order: %r" % first[0])
        self.assertEqual(json.dumps(first[0], sort_keys=True), json.dumps(second[0], sort_keys=True), "a rerun writes other rows: %r" % first[0])
        self.assertEqual(first[1:], second[1:], "a rerun counts other unsorted rows: %r" % (first[1:],))

    def test_files_are_the_paths_the_pr_changes_against_its_merge_base(self):
        self.pr(7, record="done", at=361, files={BRANCH_FILE: BRANCH_TEXT})
        self.lane("session_a")
        self.publish()
        rows, _count, _ok = self.ledger(self.host(), self.verdict_file(self.verdict(7)))
        row = row_of(rows, 7)
        self.assertIsNotNone(row, "no ledger row for #7, a done record 361 minutes old: %r" % rows)
        self.assertEqual(row["files"], [BRANCH_FILE], "the files of #7 are not the paths its commit changes: %r" % row)

    def test_a_pushed_branch_gets_a_ledger_row_with_its_files(self):
        self.push_branch(BRANCH, self.commit_on(self.main, {BRANCH_FILE: BRANCH_TEXT}))
        self.publish()
        rows, _count, _ok = self.ledger(self.host(), self.verdict_file())
        row = row_of(rows, BRANCH)
        self.assertIsNotNone(row, "no ledger row for %s, pushed one commit ahead of main with no pull request: %r" % (BRANCH, rows))
        self.assertEqual(row["state"], "f", "the ledger row for %s names state %r, not f: %r" % (BRANCH, row["state"], row))
        self.assertEqual(row["files"], [BRANCH_FILE], "the files of %s are not the paths it changes: %r" % (BRANCH, row))

    def test_the_ledger_reads_the_live_file_once_as_the_batch_review_does(self):
        self.pr(7, record="done", at=361)
        self.lane("session_a")
        self.publish()
        build = merge.load_roadmap_build()  # one module object, so the spy sees each read the ledger and the review make
        with mock.patch.object(build, "live_work", wraps=build.live_work) as reads, mock.patch.object(merge, "load_roadmap_build", lambda: build):
            self.block(self.host())
            batch = reads.call_count
            self.ledger(self.host(), self.verdict_file(self.verdict(7)))
            ledger = reads.call_count - batch
        self.assertEqual(batch, 1, "control: the batch review reads the live file %d times, not once" % batch)
        self.assertEqual(ledger, 1, "the ledger reads the live file %d times, not once as the batch review does" % ledger)

    def test_the_ledger_and_the_batch_review_name_the_same_states(self):
        self.pr(7, record="done", at=361)
        self.lane("session_a")
        self.pr(8, record="open", at=30, session="session_b")
        self.lane("session_b")
        self.pr(9, record=None, session="session_c")
        self.lane("session_c", status=IDLE, bucket=roadmap.BUCKET_COMPLETED)
        self.thread(9, minutes=781)
        self.pr(10, record="done", at=60, session="session_d")
        self.lane("session_d", status=ARCHIVED, bucket=roadmap.BUCKET_COMPLETED)
        self.pr(11, head_ref="c3", record="done", at=60, session="session_gone")
        self.pr(12, record="done", at=60)
        self.publish()
        lines = self.block(self.host(mail_result=NO_ROUTE))
        batch = {n: "".join(state for state, _owner in rows_for(lines, n)) for n in range(7, 13)}
        self.assertEqual(batch, {7: "a", 8: "b", 9: "c", 10: "d", 11: "e", 12: ""}, "scope: the batch review's states are not one per pull request: %r" % lines)
        rows, _count, _ok = self.ledger(self.host(mail_result=NO_ROUTE), self.verdict_file())
        ledger = {n: (row_of(rows, n) or {}).get("state", "") for n in range(7, 13)}
        self.assertEqual(ledger, batch, "the ledger names other states than the batch review names: %r" % rows)

    def test_an_empty_batch_writes_no_rows_and_a_zero_count(self):
        self.publish()
        rows, count, _ok = self.ledger(self.host(), self.verdict_file())
        self.assertEqual(rows, [], "ledger rows with no open pull request: %r" % rows)
        self.assertEqual(count, "unsorted: 0", "the count line with no rows: %r" % count)

    def test_full_size_batch_writes_only_the_pr_in_a_state(self):
        self.lane("session_a")
        for n in range(2, 27):
            self.pr(n, record="open", at=30)
        self.pr(40, record=None, session="session_b")
        self.lane("session_b", status=IDLE, bucket=roadmap.BUCKET_COMPLETED)
        self.thread(40, minutes=781)
        self.publish()
        rows, count, _ok = self.ledger(self.host(), self.verdict_file())
        self.assertEqual([row.get("pr") for row in rows], [40], "the ledger rows among 26 pull requests are not #40 alone: %r" % rows)
        self.assertEqual(count, "unsorted: 1", "the count line for one row with no verdict among 26: %r" % count)

    def test_the_ledger_flags_are_on_the_command_line(self):
        argv = ["--reviewed", "--live", "live.json", "--ledger", "--out", "lost-prs.json", "--verdicts", "verdicts.tsv"]
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                parsed = merge.build_parser().parse_args(argv)
        except SystemExit:
            parsed = None
        self.assertIsNotNone(parsed, "merge's command line refuses `merge --reviewed --live FILE --ledger --out FILE --verdicts FILE`")

    def test_a_failed_lane_send_in_the_ledger_exits_one_and_writes_no_out(self):
        self.pr(7, record="open", at=30, session="session_b")  # its lane is told by mail, and the send fails
        self.lane("session_b")
        self.publish()
        out = pathlib.Path(self.tmp.name) / "lost-prs.json"
        argv = ["--reviewed", "--live", str(self.live), "--ledger", "--out", str(out), "--verdicts", str(self.verdict_file())]
        stderr = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
            rc = merge.main(argv, host=self.host(mail_result=NO_ROUTE))
        self.assertIn("was not sent", stderr.getvalue(), "scope: the failed lane send prints no line naming it: %r" % stderr.getvalue())
        self.assertEqual(rc, 1, "a failed lane send in --ledger exits %r, not 1: %s" % (rc, stderr.getvalue()))
        self.assertFalse(out.exists(), "--ledger wrote %s though a lane send failed" % out)


if __name__ == "__main__":
    unittest.main()
