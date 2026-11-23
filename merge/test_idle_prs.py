#!/usr/bin/env python3
"""Tests for the idle red pull request rule (owner, 2026-11-23 10:54 CST, "2 hours is great"): a non-draft PR whose head is red and
whose newest pull_request run is 2 hours old or more goes back to draft. Its comment says why and how to return.

Run: python3 merge/test_idle_prs.py

WHAT IT PROVES. `merge --draft-idle` (the janitor's entry), run in-process through merge.main with IdleHost (no gh call). It lists the
open pull requests once, drafts each non-draft PR whose head is red and idle, posts one comment per drafted PR, and prints a summary
line with the count drafted. A failed read is unknown: that PR is left alone, and a failed list read drafts nothing and exits nonzero.
The clash hook (a red idle PR does not block `merge <n> --ready`) is in test_lane_lint.py, class ReadyChecks, beside the pre-ready
clash cases, and uses IdleHost from here.

Host surface these cases pin (the names the builder implements; IdleHost is the fake of each):
  open_pulls()      one list read per sweep; REST rows of the open pulls
  runs(sha)         the pull_request runs of a head: name, status, conclusion, event, createdAt (ISO, GitHub's own field)
  head_state(n, sha) "red: <names>" for a completed failure, "pending: <names>" while a run is still going, "green" otherwise
  draft(n)          the local `gh pr ready <n> --undo`; a cloud host answers (False, merge.DRAFT_ROUTES)
  post_comment(n, body)  one comment per drafted PR

The clock is synthetic: every age is counted from test_merge.FAKE_NOW, so a module that reads the wall clock sees each fixture run
as weeks old and fails the 1 h 59 min and the newest-run cases. The 2-hour threshold is pinned by its edges (exactly 2 h drafts, one
second less does not), not by the module's constant name.

Cost pin: one open-pulls read per sweep, and at most one runs read per non-draft PR. No file is written, and no timer is started.
Not pinned here: a PR a person readies again with no push and that goes red and idle again. The sweep then drafts it, and a
second comment is not blocked by a comment read. That is an open design question for the report, not a case.

Each case runs the sweep first, then asserts its outcome, so a must-not case is never a pass on a missing entry. Each failure message
names one cause.
"""
import io
import itertools
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import merge  # noqa: E402
import test_merge as tm  # noqa: E402  the FakeHost, the Env fixture and the fake REST rows (one home)

HOUR = 3600
IDLE_SECONDS = 2 * HOUR  # the ruling's threshold, written as the test's own value
RULING = "owner, 2026-11-23 10:54 CST"
RED_JOB = "Lint and tests"
RUN_IDS = itertools.count(9000)


def ago(seconds):
    """GitHub's createdAt for a run `seconds` before the fixture clock. The clock is tm.FAKE_NOW, never the real one."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(tm.FAKE_NOW - seconds))


def run(name, conclusion, status="completed", age=3 * HOUR, event="pull_request"):
    """One workflow run as `gh run list --json ...,createdAt` answers it."""
    rid = next(RUN_IDS)
    return {"name": name, "status": status, "conclusion": conclusion, "event": event, "createdAt": ago(age),
            "databaseId": rid, "workflowDatabaseId": rid}


def red(age=3 * HOUR, name=RED_JOB):
    return run(name, "failure", age=age)


def green(age=3 * HOUR):
    return run(RED_JOB, "success", age=age)


def pending(name, age=3 * HOUR):
    return run(name, None, status="in_progress", age=age)


def cancelled(age=3 * HOUR):
    return run(RED_JOB, "cancelled", age=age)


def sha_of(n):
    return "%040x" % n


class IdleHost(tm.FakeHost):
    """The fake GitHub half of the idle sweep and the clash hook. Scripted; no gh call.

    include_own: the open list keeps the lane's own pull request, as FakeHost lists it (the clash cases need it). A sweep does not.
    runs_by_sha: the runs a head reads as. A head with no entry falls through to FakeHost's own answers.
    runs_reads: each head runs() read, in order (the cost pin counts them).
    runs_fail: {sha: text}: a runs() read of that head raises merge.Stop with the text (unknown for that head).
    list_fail: the text the open-pulls read raises (unknown for the whole sweep).
    drafts: each n the local draft call drafted. draft_refuse: a cloud host, which cannot send the undo and answers the route.
    """

    def __init__(self, root, other, branch="feat"):
        super().__init__(root, other, branch)
        self.pulls = {}
        self.include_own = False
        self.runs_by_sha, self.runs_reads, self.runs_fail = {}, [], {}
        self.list_fail = None
        self.drafts, self.draft_refuse = [], False

    @classmethod
    def adopt(cls, host):
        """The same host as an IdleHost: its scripted state stays, and the idle fakes start empty."""
        new = cls(host.root, host.other, host.branch)
        new.__dict__.update(host.__dict__)
        return new

    def open_pulls(self):
        if self.include_own:
            return super().open_pulls()
        self.pull_list_reads += 1
        if self.list_fail:
            raise merge.Stop(self.list_fail)
        return [row for row in self.pulls.values() if row["state"] == "open"]

    def pages(self, rel, key=None, fields=None):
        return self.open_pulls() if rel == "pulls" else []

    def runs(self, sha):
        self.runs_reads.append(sha)
        if sha in self.runs_fail:
            raise merge.Stop(self.runs_fail[sha])
        return [dict(r) for r in self.runs_by_sha.get(sha, [])]

    def head_state(self, n, sha=None):
        if sha not in self.runs_by_sha:
            return super().head_state(n, sha)
        rows = self.runs_by_sha[sha]
        if not rows:
            return "pending: no run yet"
        failed = [r["name"] for r in rows if r["status"] == "completed" and r["conclusion"] == "failure"]
        going = [r["name"] for r in rows if r["status"] != "completed"]
        if failed:
            return "red: " + "; ".join(failed)
        if going:
            return "pending: " + ", ".join(going)
        return "green"

    def draft(self, n):
        if self.draft_refuse:
            return False, merge.DRAFT_ROUTES
        self.drafts.append(n)
        if n in self.pulls:
            self.pulls[n]["draft"] = True
        return True, ""


class IdleSweep(tm.Env):
    """One repo pair with an IdleHost. Pull requests are added with pr(); each sweep is one `merge --draft-idle` run."""

    def setUp(self):
        super().setUp()
        self.host = IdleHost(self.co, self.other)

    def pr(self, n, runs=(), draft=False):
        """Pull request n, non-draft unless `draft`, whose head (sha_of(n)) reads as `runs`. -> its head sha."""
        sha = sha_of(n)
        self.host.pulls[n] = tm.REST.list_item(n, sha, "pr-%d" % n, "main", body="", draft=draft)
        self.host.runs_by_sha[sha] = list(runs)
        return sha

    def sweep(self):
        """`merge --draft-idle` in this checkout. -> (rc, text). An argparse refusal of the flag is an answer too, not a crash."""
        out, err = io.StringIO(), io.StringIO()
        try:
            rc, text = self.run_merge_once("--draft-idle", stdout=out, stderr=err)
        except SystemExit as e:
            rc, text = (e.code if isinstance(e.code, int) else 1), out.getvalue() + err.getvalue()
        return rc, text

    def assert_sweep_ran(self, rc, text, reads=1):
        self.assertEqual(self.host.pull_list_reads, reads,
                         "merge --draft-idle did not list the open pull requests %d time(s) (rc %s): %s" % (reads, rc, text))

    def assert_nothing_drafted(self, text, why):
        self.assertEqual(self.host.drafts, [], "%s: a PR was drafted: %s" % (why, text))
        self.assertEqual(self.host.posted, [], "%s: a comment was posted: %s" % (why, text))

    def test_idle_red_pr_goes_back_to_draft_and_gets_one_comment_that_says_why(self):
        sha = self.pr(7, [red(age=3 * HOUR)])
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assertEqual(rc, 0, "the sweep exited %s with a drafted PR: %s" % (rc, text))
        self.assertEqual(self.host.drafts, [7], "the idle red PR #7 was not drafted: " + text)
        self.assertEqual([n for n, _ in self.host.posted], [7], "PR #7 did not get exactly one comment: " + text)
        body = self.host.posted[0][1]
        for needle, what in ((sha, "the head sha"), ("#7", "the PR number"), (RED_JOB, "the red job name"),
                             ("idle 3 h", "the hours idle"), (RULING, "the ruling"), ("merge 7 --ready", "how to return"),
                             ("push", "the fix-and-push step")):
            self.assertIn(needle, body, "the comment misses %s: %s" % (what, body))

    def test_red_pr_exactly_two_hours_idle_goes_back_to_draft(self):
        self.pr(7, [red(age=IDLE_SECONDS)])
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assertEqual(self.host.drafts, [7], "a red PR idle exactly 2 h was not drafted: " + text)

    def test_red_pr_one_second_short_of_two_hours_stays_ready(self):
        self.pr(7, [red(age=IDLE_SECONDS - 1)])
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assert_nothing_drafted(text, "a red PR idle 1 h 59 min 59 s")

    def test_red_pr_pushed_one_hour_fifty_nine_minutes_ago_stays_ready(self):
        self.pr(7, [red(age=HOUR + 59 * 60)])
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assert_nothing_drafted(text, "a red PR idle 1 h 59 min")

    def test_the_newest_run_decides_the_age_not_the_oldest(self):
        self.pr(7, [red(age=3 * HOUR), red(age=HOUR)])
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assert_nothing_drafted(text, "a head whose newest run is 1 h old, under an older red run of 3 h")

    def test_green_idle_pr_stays_ready(self):
        self.pr(7, [green(age=3 * HOUR)])
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assert_nothing_drafted(text, "a green PR idle 3 h")

    def test_red_idle_pr_with_a_run_still_going_on_its_head_stays_ready(self):
        self.pr(7, [red(age=3 * HOUR), pending("Deploy preview", age=3 * HOUR)])
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assert_nothing_drafted(text, "a red PR with a run in progress on its head")

    def test_cancelled_only_idle_pr_stays_ready(self):
        self.pr(7, [cancelled(age=3 * HOUR)])
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assert_nothing_drafted(text, "a PR whose only run was cancelled")

    def test_draft_pr_is_skipped_and_gets_no_comment(self):
        self.pr(7, [red(age=3 * HOUR)], draft=True)
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assert_nothing_drafted(text, "a PR that is already a draft")

    def test_pr_with_no_runs_at_all_stays_ready(self):
        self.pr(7, [])
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assert_nothing_drafted(text, "a PR with no runs on its head")

    def test_failed_runs_read_leaves_that_pr_alone_and_says_unknown_while_the_rest_is_swept(self):
        self.pr(7, [red(age=3 * HOUR)])
        self.pr(8, [red(age=3 * HOUR)])
        self.host.runs_fail[sha_of(7)] = "gh run list failed: HTTP 502"
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assertEqual(self.host.drafts, [8], "PR #8, whose runs read, was not drafted, or PR #7 was: " + text)
        self.assertIn("unknown", text, "the failed runs read of PR #7 is not printed as unknown: " + text)
        self.assertIn("#7", text, "the unknown line does not name PR #7: " + text)

    def test_failed_open_list_read_drafts_nothing_and_exits_nonzero(self):
        self.pr(7, [red(age=3 * HOUR)])
        self.host.list_fail = "gh api pulls failed: HTTP 502"
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assertNotEqual(rc, 0, "a failed open-list read exited 0: " + text)
        self.assertIn("unknown", text, "the failed open-list read is not printed as unknown: " + text)
        self.assert_nothing_drafted(text, "the open list did not read")

    def test_empty_open_list_drafts_nothing_and_counts_zero(self):
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assertEqual(rc, 0, "an empty sweep exited %s: %s" % (rc, text))
        self.assert_nothing_drafted(text, "no open pull requests")
        self.assertRegex(text, r"\bdrafted 0\b", "the summary does not count 0 drafted: " + text)

    def test_mixed_sweep_drafts_each_idle_red_pr_and_no_other(self):
        for n in (7, 8, 9, 10):
            self.pr(n, [red(age=3 * HOUR)])
        self.pr(11, [green(age=3 * HOUR)])
        self.pr(12, [red(age=IDLE_SECONDS - 1)])
        self.pr(13, [red(age=3 * HOUR)], draft=True)
        self.pr(14, [])
        self.pr(15, [red(age=3 * HOUR), pending("Deploy preview", age=3 * HOUR)])
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assertEqual(self.host.drafts, [7, 8, 9, 10], "the mixed sweep drafted the wrong PRs: " + text)
        self.assertEqual([n for n, _ in self.host.posted], [7, 8, 9, 10], "the mixed sweep commented on the wrong PRs: " + text)
        self.assertRegex(text, r"\bdrafted 4\b", "the summary does not count 4 drafted: " + text)

    def test_cost_one_list_read_and_at_most_one_runs_read_per_non_draft_pr(self):
        self.pr(7, [red(age=3 * HOUR)])
        self.pr(8, [green(age=3 * HOUR)])
        self.pr(9, [red(age=3 * HOUR)], draft=True)
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assertEqual(sorted(self.host.runs_reads), sorted([sha_of(7), sha_of(8)]),
                         "the runs reads are not one per non-draft PR: %s" % self.host.runs_reads)

    def test_second_sweep_posts_no_second_comment(self):
        self.pr(7, [red(age=3 * HOUR)])
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text)
        self.assertEqual(self.host.drafts, [7], "precondition: the first sweep did not draft PR #7: " + text)
        rc, text = self.sweep()
        self.assert_sweep_ran(rc, text, reads=2)
        self.assertEqual(len(self.host.posted), 1, "a second sweep posted another comment: %s" % self.host.posted)


if __name__ == "__main__":
    unittest.main()
