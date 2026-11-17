#!/usr/bin/env python3
"""Fixture suite for Host.holds_head, the local-git reader of "does `other` contain `head`" (merge/merge.py), and for Host.holds_head_gh, the
GitHub compare that keeps the old read. Run: python3 merge/test_holds_head.py

THE CONTRACT THE CASES PIN (the builder meets it):
- Host.holds_head(head, other) is `git merge-base --is-ancestor head other`, run in the checkout Host.cwd names: ahead or identical holds, behind
  or diverged does not. It makes no gh call.
- A head the clone lacks is fetched from refs/pull/*/head, once per run, into refs/remotes/origin/pull/* (the namespace the failed-fetch case
  blocks). A branch name as `other` (main) is fetched as origin's branch first.
- Unknown, never clear: a head no remote holds, a failed fetch of the base branch, or a failed fetch of the pull request heads raises Stop.
- Host.holds_head_gh(head, other) keeps the GitHub compare: one gh call, compare/HEAD...OTHER, read as ahead or identical.

The fixture is merge/test_merge.py's ReviewEnv (imported, not copied): an origin with main and feat, and the clones co and other.
"""
import os
import pathlib
import subprocess
import sys
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import merge  # noqa: E402  merge/merge.py, the reader under test
import test_merge as tm  # noqa: E402  ReviewEnv (the origin and its two clones), PullsHost, sh and put: the one home
sys.path.insert(1, str(HERE.parent / "lint"))
import _test_git  # noqa: E402,F401  test-run signing opt-out (lint/_test_git.py)


class HoldsHead(tm.ReviewEnv):
    """The three commits the cases read: B is ahead of A (B holds A), C splits from A (diverged with B), and X sits on refs/pull/9/head alone,
    so the clone `co` lacks it until a read fetches the pull request heads."""

    def setUp(self):
        super().setUp()
        self.A = tm.sh(self.other, "git", "rev-parse", "origin/main")
        self.B1 = self.commit_on("lane-b", self.A, "b1.txt", "b1\n")
        self.B = self.commit_on("lane-b", self.B1, "b2.txt", "b2\n")
        self.C = self.commit_on("lane-c", self.A, "c.txt", "c\n")
        self.X = self.commit_on("pull-9", self.A, "x.txt", "x\n")
        tm.sh(self.other, "git", "push", "-q", "origin", "lane-b", "lane-c", "pull-9:refs/pull/9/head")
        tm.sh(self.co, "git", "fetch", "-q", "origin")

    def commit_on(self, branch, start, path, text):
        """One commit on `branch` (reset to `start`) that adds `path`, in the other clone. -> its sha."""
        tm.sh(self.other, "git", "checkout", "-q", "-B", branch, start)
        tm.put(os.path.join(self.other, path), text)
        tm.sh(self.other, "git", "add", "-A")
        tm.sh(self.other, "git", "commit", "-q", "-m", path)
        return tm.sh(self.other, "git", "rev-parse", "HEAD")

    def reader(self, compares=None):
        """A PullsHost in the clone `co`, with no compare listed unless `compares` lists one (a pair not listed is diverged, as GitHub answers
        an unrelated pair). Every gh call it gets is kept in gh_seen, so a case sees a verdict read from gh as a call, and the fake's own
        refusals of a route stay out of it."""
        h = tm.PullsHost([], {}, compares=compares or {})
        h.cwd = self.co
        h.gh_seen = []
        real = h.gh

        def gh(args, cwd=None, **kw):
            h.gh_seen.append(list(args))
            return real(args, cwd, **kw)
        h.gh = gh
        return h

    def outcome(self, h, head, other):
        """-> ("stop", message) when h.holds_head(head, other) raises Stop, else ("verdict", its bool)."""
        try:
            return "verdict", h.holds_head(head, other)
        except merge.Stop as e:
            return "stop", str(e)

    def test_a_head_the_other_contains_holds_with_no_gh_call(self):
        h = self.reader()
        self.assertTrue(h.holds_head(self.A, self.B), "A is contained in B, so B holds A: the verdict is read from git, not from gh")
        self.assertEqual(h.gh_seen, [], "holds_head makes a gh call: %r" % h.gh_seen)

    def test_an_identical_head_holds_with_no_gh_call(self):
        h = self.reader()
        self.assertTrue(h.holds_head(self.B, self.B), "B is identical to itself, which holds")
        self.assertEqual(h.gh_seen, [], "holds_head makes a gh call: %r" % h.gh_seen)

    def test_a_head_the_other_lacks_does_not_hold_with_no_gh_call(self):
        h = self.reader()
        self.assertFalse(h.holds_head(self.B, self.A), "B is not contained in A, so A does not hold B")
        self.assertEqual(h.gh_seen, [], "holds_head makes a gh call: %r" % h.gh_seen)

    def test_a_diverged_head_does_not_hold_with_no_gh_call(self):
        h = self.reader()
        self.assertFalse(h.holds_head(self.C, self.B), "C is not contained in B, so B does not hold C")
        self.assertEqual(h.gh_seen, [], "holds_head makes a gh call: %r" % h.gh_seen)

    def test_a_head_the_clone_lacks_takes_its_verdict(self):
        absent = subprocess.run(["git", "cat-file", "-e", self.X + "^{commit}"], cwd=self.co, capture_output=True)
        self.assertNotEqual(absent.returncode, 0, "setup: the clone already holds X, so it does not lack it")
        self.assertTrue(self.reader().holds_head(self.A, self.X), "X contains A, so X holds A, though the clone has to fetch X to say so")

    def test_a_head_no_remote_holds_reads_unknown_never_clear(self):
        nowhere = "1" * 40  # no remote and no clone holds this head
        kind, got = self.outcome(self.reader(), nowhere, self.B)
        self.assertEqual(kind, "stop", "a head no remote holds read as %s (%r), not as unknown" % (kind, got))

    def test_a_failed_fetch_of_the_base_stops_and_never_reads_not_held(self):
        # origin's main moves to B after the clone's last fetch, so the clone's origin/main is the stale A, which does not hold B. origin then
        # hides refs/heads/main from every fetch, so the clone's fetch of the base fails. A read that went on from the stale A would say that
        # main does not hold B: a clear answer that a failed read must never give.
        tm.sh(self.other, "git", "push", "-q", "origin", f"{self.B}:refs/heads/main")
        self.assertEqual(tm.sh(self.bare, "git", "rev-parse", "refs/heads/main"), self.B, "setup: origin's main is not B")
        self.assertEqual(tm.sh(self.co, "git", "rev-parse", "origin/main"), self.A, "setup: the clone's origin/main is not the stale A")
        tm.sh(self.bare, "git", "config", "uploadpack.hideRefs", "refs/heads/main")
        kind, got = self.outcome(self.reader(), self.B, "main")
        self.assertEqual(kind, "stop", "a failed fetch of main read as a verdict (%r), not as a Stop, though the stale origin/main does not hold B" % (got,))
        self.assertIn("git fetch of main failed", got, "the Stop does not name the failed fetch of main: %s" % got)

    def test_a_failed_fetch_of_a_pull_ref_stops(self):
        # The clone's refs/remotes/origin/pull is a ref, so git cannot create refs/remotes/origin/pull/9 for the fetch of refs/pull/9/head, and
        # that fetch fails. B is in the clone and main is current, so a read that went on would answer a verdict.
        tm.sh(self.co, "git", "update-ref", "refs/remotes/origin/pull", self.A)
        fetch = subprocess.run(["git", "fetch", "-q", "origin", "+refs/pull/*/head:refs/remotes/origin/pull/*"], cwd=self.co, capture_output=True, text=True)
        self.assertNotEqual(fetch.returncode, 0, "setup: the fetch of the pull request heads succeeds, so no pull ref read fails")
        kind, got = self.outcome(self.reader(), self.B, "main")
        self.assertEqual(kind, "stop", "a failed fetch of a pull ref read as a verdict (%r), not as a Stop" % (got,))
        self.assertIn("git fetch of the pull request heads failed", got, "the Stop does not name the failed fetch of the pull request heads: %s" % got)

    def test_the_pull_request_heads_are_fetched_once_per_run(self):
        h = self.reader()
        with mock.patch.object(merge, "sh", wraps=merge.sh) as spy:
            first = h.holds_head(self.A, self.B)
            second = h.holds_head(self.C, self.B)
        fetches = [c for c in spy.call_args_list if "refs/pull/" in str(c)]
        self.assertEqual(len(fetches), 1, "the pull request heads are fetched %d times in two reads, not once per run: %r" % (len(fetches), spy.call_args_list))
        self.assertTrue(first, "A is contained in B, so B holds A")
        self.assertFalse(second, "C is not contained in B, so B does not hold C")

    def test_holds_head_gh_keeps_the_compare_read(self):
        fn = getattr(merge.Host, "holds_head_gh", None)
        if fn is None:
            self.fail("merge.Host.holds_head_gh is not defined: the GitHub compare the old holds_head read is gone")
        h = self.reader(compares={(self.A, self.B): "ahead"})
        self.assertTrue(fn(h, self.A, self.B), "holds_head_gh reads the compare A...B as ahead, so it holds")
        routes = [" ".join(args) for args in h.gh_seen]
        self.assertEqual(len(routes), 1, "holds_head_gh makes %d gh calls, not the one compare: %r" % (len(routes), routes))
        self.assertIn("compare/%s...%s" % (self.A, self.B), routes[0], "holds_head_gh does not read the compare A...B: %r" % routes)


if __name__ == "__main__":
    unittest.main()
